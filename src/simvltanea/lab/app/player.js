// DOM side: video panels, scheduling loop, Web Audio graph, reveal overlay.
import { Scheduler, buildRecords } from './engine.js';
import { computeLayout, zoomFor, fitVideo, focalPoint, panFor } from './layout.js';
import { lfo } from './params.js';
import { Framer, framingParams, renderWindow, coverZoom, driftWindowAt, nextHold, windowFromFit, edgeMismatch, colourOf } from './framing.js';
import { clipGain, speechVerdict } from './speech.js';

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const el = (tag, cls, attrs = {}) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};

export class Player {
  constructor({ stage, store, revealRoot, base = './' }) {
    this.stage = stage; this.store = store; this.revealRoot = revealRoot;
    this.baseUrl = new URL(base, location.href);
    this.records = []; this.sched = null; this.panels = [];
    this.t = 0; this.paused = false; this.revealPaused = false;
    this.W = 0; this.H = 0; this.layout = null; this.layoutSig = ''; this.zoomInfo = { zoom: 1, share: 1, panels: [] };
    this.audio = { started: false, ctx: null, master: null, comp: null };
    this.eff = store.effective(0);
    this.listeners = new Set();
    this.tokenSeq = 0; this.frameNo = 0; this.lastTs = 0;
    this.autoSeed = (Math.floor(Math.random() * 999998) + 1);
    this.seed = 0; this.levels = [];
    this.reveal = null; this.lastSpeed = 1;
    this.framer = new Framer(); this.frameSig = ''; this.frameSeed = null; this.framingDirty = true;
    this.mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.mq.addEventListener?.('change', () => this._applyMotionPref());
    this._applyMotionPref();
    this.ro = new ResizeObserver(() => this.measure());
    this.ro.observe(stage);
    window.addEventListener('resize', () => this.measure());
    this.empty = el('div', 'stage-empty'); this.empty.hidden = true; stage.append(this.empty);
    store.on((ev) => this._onStore(ev));
  }

  get reduced() { return this.mq.matches; }
  _applyMotionPref() { document.documentElement.classList.toggle('reduced-motion', this.reduced); }
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit(ev) { for (const f of this.listeners) f(ev); }
  url(rel) { return new URL(rel, this.baseUrl).href; }

  // ---- data ----
  async load() {
    const target = new URL('data/clips.json', this.baseUrl);
    if (target.origin !== location.origin) throw new Error('data base must be same-origin: ' + this.baseUrl.href);
    const res = await fetch(target.href, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`could not load ${target.pathname} (HTTP ${res.status})`);
    const json = await res.json();
    if (!json || !Array.isArray(json.clips)) throw new Error('clips.json has no "clips" array');
    this.records = buildRecords(json.clips);
    this.rejected = this.records.rejected;
    this.dataVersion = json.version;
    this.seed = this.store.get('source.seed') || this.autoSeed;
    this.eff = this.store.effective(0);
    this.sched = new Scheduler(this.records, this.eff, this.eff['layout.panels'], this.seed);
    this.measure();
    this.syncPanels(this.eff['layout.panels']);
    requestAnimationFrame((ts) => { this.lastTs = ts; this._frame(ts); });
    return this.records.length;
  }

  measure() {
    const r = this.stage.getBoundingClientRect();
    this.W = Math.round(r.width); this.H = Math.round(r.height);
  }

  _onStore(ev) {
    if (ev.type === 'config' || ev.type === 'bypass' || ev.module === 'framing') this.framingDirty = true;
    if (!this.sched) return;
    if (ev.type === 'param' || ev.type === 'bypass') {
      const m = ev.module;
      if (ev.id === 'source.seed') return;
      if (m === 'source' || m === 'order' || m === 'path' || ev.id === 'audio.speech_policy') this._replan(false);
      else if (m === 'relation') this._replan(true);
    } else if (ev.type === 'config') { this._replanNow(); }
  }
  _replan(keepSteps) {
    clearTimeout(this._rt);
    this._rt = setTimeout(() => this.sched.reset(this.t, { keepSteps }), 250);
  }
  _replanNow() { clearTimeout(this._rt); this.sched.reset(this.t); }
  reshuffle() { this.seed = (Math.floor(Math.random() * 999998) + 1); this.sched.reseed(this.seed); }

  // ---- panels ----
  syncPanels(n) {
    while (this.panels.length < n) this._addPanel();
    while (this.panels.length > n) this._removePanel();
    this.sched.resize(n);
    this.layoutSig = '';
  }

  _addPanel() {
    const k = this.panels.length;
    const root = el('div', 'panel', { 'data-panel': String(k), role: 'button', tabindex: '0', 'aria-label': `Panel ${k + 1}: show the original` });
    const slots = [0, 1].map(() => {
      const v = el('video', 'clip');
      v.muted = !this.audio.started; v.loop = true; v.playsInline = true; v.preload = 'auto'; v.disablePictureInPicture = true;
      v.setAttribute('muted', ''); v.setAttribute('playsinline', '');
      root.append(v);
      return { video: v, src: null, gain: null, rec: null, vw: 0, vh: 0, token: 0, norm: 0, key: '', win: null, appearance: undefined, path: null, t0: 0, holdN: -1, cur: null };
    });
    const vu = el('div', 'vu'); vu.append(el('i'));
    const tools = el('div', 'ptools');
    const idx = el('span', 'pidx'); idx.textContent = String(k + 1);
    const mute = el('button', 'pbtn pmute', { type: 'button', 'aria-label': `Mute panel ${k + 1}`, 'aria-pressed': 'false', title: 'Mute' }); mute.textContent = 'M';
    const solo = el('button', 'pbtn psolo', { type: 'button', 'aria-label': `Solo panel ${k + 1}`, 'aria-pressed': 'false', title: 'Solo' }); solo.textContent = 'S';
    tools.append(idx, mute, solo);
    root.append(vu, tools);
    const panel = { k, root, slots, active: -1, rec: null, vu, mute, solo, bus: null, analyser: null, panner: null, buf: null, level: 0, pan: 0, size: 1, rect: null, lastBox: '', fx: null };
    root.addEventListener('click', (e) => { if (!e.target.closest('.ptools')) this.openReveal(panel.k); });
    root.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target === root) { e.preventDefault(); this.openReveal(panel.k); } });
    mute.addEventListener('click', (e) => { e.stopPropagation(); this.toggleList('audio.muted_panels', panel.k + 1); });
    solo.addEventListener('click', (e) => { e.stopPropagation(); this.toggleList('audio.solo_panels', panel.k + 1); });
    this.stage.insertBefore(root, this.empty);
    this.panels.push(panel);
    if (this.audio.started) this._ensurePanelAudio(panel);
  }

  toggleList(id, n) {
    const cur = new Set(this.store.get(id));
    cur.has(n) ? cur.delete(n) : cur.add(n);
    this.store.set(id, [...cur]);
  }

  _removePanel() {
    const p = this.panels.pop();
    for (const s of p.slots) { s.token = 0; s.video.pause(); s.video.removeAttribute('src'); try { s.src?.disconnect(); s.gain?.disconnect(); } catch { /* already gone */ } }
    try { p.bus?.disconnect(); p.panner?.disconnect(); p.analyser?.disconnect(); } catch { /* already gone */ }
    p.root.remove();
  }

  loadClip(k, ci) {
    const panel = this.panels[k], rec = this.records[ci];
    if (!panel || !rec) return;
    const idx = panel.active === 0 ? 1 : 0;
    const slot = panel.slots[idx];
    const token = ++this.tokenSeq;
    slot.token = token; slot.rec = rec;
    slot.vw = rec.width > 0 ? rec.width : 540; slot.vh = rec.height > 0 ? rec.height : 720;
    slot.key = ''; slot.win = null; slot.appearance = undefined; slot.path = null; slot.cur = null;
    const v = slot.video;
    v.classList.remove('on');
    v.poster = rec.still ? this.url(rec.still) : '';
    v.muted = !this.audio.started || this.speechMuted(rec);
    v.playbackRate = this.eff['timing.speed'];
    v.src = this.url(rec.video);
    const first = panel.active === -1;
    if (first) this._activate(panel, idx, true);
    const cleanup = () => { v.removeEventListener('loadeddata', ready); v.removeEventListener('error', fail); };
    const ready = () => {
      cleanup();
      if (slot.token !== token) return;
      if (v.videoWidth && (v.videoWidth !== slot.vw || v.videoHeight !== slot.vh)) { slot.vw = v.videoWidth; slot.vh = v.videoHeight; slot.key = ''; slot.winDirty = true; }
      if (!this.paused && !this.revealPaused) v.play().catch(() => {});
      if (!first) this._activate(panel, idx, false);
    };
    const fail = () => { cleanup(); if (slot.token === token) { this.sched.markBad(ci); } };
    v.addEventListener('loadeddata', ready); v.addEventListener('error', fail);
  }

  _fadeMs() { return this.reduced ? 0 : Math.round(this.eff['audio.fade'] * 1000); }

  _activate(panel, idx, immediate) {
    const slot = panel.slots[idx], old = panel.slots[1 - idx];
    const fade = immediate ? 0 : this._fadeMs();
    slot.video.style.zIndex = '2'; old.video.style.zIndex = '1';
    slot.video.style.transitionDuration = fade + 'ms';
    slot.video.classList.add('on');
    panel.active = idx; panel.rec = slot.rec;
    this._audioActivate(panel, slot, old);
    if (old.rec && old.token) {
      old.token = 0; // cancels any pending load for it; it is only being faded out now
      setTimeout(() => {
        if (old.token === 0 && panel.active === idx) {
          old.video.classList.remove('on'); old.video.pause(); old.video.removeAttribute('src'); old.rec = null; old.key = '';
          if (old.gain && this.audio.ctx) this._ramp(old.gain.gain, 0, 0.01);
        }
      }, fade + 60);
    }
    panel.root.setAttribute('aria-label', `Panel ${panel.k + 1}: show the original${slot.rec ? ', ' + this.dateText(slot.rec) : ''}`);
  }

  // ---- layout ----
  _layoutPass(wall) {
    const e = this.eff, n = this.panels.length;
    if (!this.W || !this.H || !n) return;
    const sig = [this.W, this.H, n, e['layout.direction'], e['layout.split'], e['layout.split_custom'].join(','), e['layout.overlap'], this.seed, e['layout.radius'], e['audio.size_gain']].join('|');
    if (sig !== this.layoutSig) {
      this.layoutSig = sig;
      this.layout = computeLayout({ W: this.W, H: this.H, n, direction: e['layout.direction'], split: e['layout.split'], custom: e['layout.split_custom'], overlap: e['layout.overlap'], seed: this.seed });
      this.layout.rects.forEach((r, i) => {
        const p = this.panels[i], s = p.root.style;
        s.left = r.x + 'px'; s.top = r.y + 'px'; s.width = r.w + 'px'; s.height = r.h + 'px';
        s.borderRadius = e['layout.radius'] + 'px';
        p.rect = r;
        p.root.classList.toggle('compact', Math.min(r.w, r.h) < 48);
        const share = (this.layout.axis === 'columns' ? r.tile.w / this.W : r.tile.h / this.H) * n;
        p.size = Math.pow(share, e['audio.size_gain']);
        p.pan = panFor(r.tile, this.layout.axis, this.W, this.H, 1);
      });
      this._audioLayoutDirty = true;
    }
    const zoom = zoomFor(n, { z1: e['zoom.z1'], gamma: e['zoom.gamma'], floor: e['zoom.floor'], manual: e['zoom.manual'] });
    const reduced = this.reduced;
    const jAmp = reduced ? 0 : e['layout.jitter'];
    const mode = reduced ? 'static' : e['zoom.focal_mode'];
    const fp = framingParams(e);
    this._framingSync();
    let shareSum = 0, shareCnt = 0, zSum = 0;
    const per = [];
    const axis = this.layout.axis;
    for (const p of this.panels) {
      const r = p.rect;
      if (!r) continue;
      for (let si = 0; si < 2; si++) {
        const s = p.slots[si];
        if (!s.rec || (si !== p.active && !s.token)) continue;
        const jx = axis === 'columns' ? jAmp : 0, jy = axis === 'rows' ? jAmp : 0;
        const key = `${p.k}:${s.rec.id}`;
        const ctx = { srcAspect: s.vw / s.vh, cellAspect: r.w / r.h, baseZoom: zoom, minZoom: coverZoom(s.vw, s.vh, r.w, r.h, jx, jy) };
        if (!s.win || s.winDirty) this._deriveSlot(p, s, fp, ctx, key, axis);
        let win = s.win;
        if (s.path) {
          const n = this.sched.panels[p.k]?.n;
          if (si === p.active && s.holdN !== n) { s.path = nextHold(s.path, this.t - s.t0, ctx, reduced); s.t0 = this.t; s.holdN = n; }
          win = driftWindowAt(s.path, this.t - s.t0, ctx, reduced);
        }
        const f = focalPoint(mode, key, wall, e['zoom.drift_speed']);
        const rw = renderWindow({ mode: s.win.mode, win, baseZoom: zoom, minZoom: ctx.minZoom, srcAspect: ctx.srcAspect, cellAspect: ctx.cellAspect, focal: f, staticFocal: focalPoint('static', key), wander: !s.path });
        const jn = jAmp > 0 ? lfo('random', wall, e['layout.jitter_rate'], 'jit' + p.k) : 0;
        const fit = fitVideo({ cw: r.w, ch: r.h, vw: s.vw, vh: s.vh, zoom: rw.zoom, focal: rw.focal, axis, jitterAmp: jAmp, jitterNow: jn });
        s.cur = windowFromFit(fit, r.w, r.h);
        s.curWin = win;
        const tkey = `${s.vw}x${s.vh}|${fit.scale.toFixed(4)}|${fit.tx.toFixed(1)}|${fit.ty.toFixed(1)}`;
        if (tkey !== s.key) {
          s.key = tkey;
          s.video.style.width = s.vw + 'px'; s.video.style.height = s.vh + 'px';
          s.video.style.transform = `translate(${fit.tx.toFixed(2)}px,${fit.ty.toFixed(2)}px) scale(${fit.scale.toFixed(5)})`;
        }
        if (si === p.active) { shareSum += fit.share; shareCnt++; zSum += fit.zoom; per.push({ zoom: fit.zoom, share: fit.share, x: fit.tx, y: fit.ty, w: fit.sw, h: fit.sh }); p.fx = per[per.length - 1]; }
      }
    }
    this.zoomInfo = { curve: zoom, zoom: shareCnt ? zSum / shareCnt : zoom, share: shareCnt ? shareSum / shareCnt : 0, panels: per };
  }

  // ---- framing ----
  // Re-derive every window when the stored FRAMING parameters change (live mode switch) or the seed changes.
  _framingSync() {
    if (this.frameSeed !== this.seed) {
      this.frameSeed = this.seed; this.framer.clear();
      for (const p of this.panels) for (const s of p.slots) { s.win = null; s.appearance = undefined; s.path = null; }
    }
    if (!this.framingDirty) return;
    this.framingDirty = false;
    const sig = JSON.stringify(framingParams(this.store.effective(0)));
    if (sig === this.frameSig) return;
    this.frameSig = sig;
    for (const p of this.panels) for (const s of p.slots) if (s.win) s.winDirty = true;
  }

  // The panel to the left/right (above/below) of p and its current window, for blend / contrast.
  _neighbours(p) {
    const out = [];
    for (const dir of [-1, 1]) {
      const nb = this.panels[p.k + dir];
      const ns = nb && nb.rect ? nb.slots[nb.active] : null;
      if (!ns || !ns.rec || !ns.win || !ns.cur) continue;
      out.push({ dir, win: { cx: ns.cur.cx, cy: ns.cur.cy, zoom: ns.cur.zoom }, clip: ns.rec, srcAspect: ns.vw / ns.vh, cellAspect: nb.rect.w / nb.rect.h });
    }
    return out;
  }

  _deriveSlot(p, s, fp, ctx, key, axis) {
    const redo = s.appearance;
    const res = this.framer.assign({ clip: s.rec, ...ctx, axis, seed: this.seed, neighbours: this._neighbours(p), params: fp, focal: focalPoint('static', key) }, redo);
    s.win = res; s.winDirty = false; s.appearance = res.appearance; s.path = res.path || null;
    s.t0 = this.t; s.holdN = this.sched.panels[p.k]?.n ?? -1;
  }

  framingState() {
    const axis = this.layout?.axis || 'columns';
    const e = this.eff;
    return this.panels.map((p) => {
      const s = p.slots[p.active];
      if (!s || !s.rec || !s.win || !s.cur) return { panel: p.k, clip: s?.rec?.id ?? null, appearance: null, mode: null, window: null };
      const left = this.panels[p.k - 1], ls = left ? left.slots[left.active] : null;
      let mismatch = null;
      const g = colourOf(s.rec).grid, lg = ls && ls.rec ? colourOf(ls.rec).grid : null;
      if (g && lg && ls.cur) {
        mismatch = edgeMismatch({ win: ls.cur, grid: lg, srcAspect: ls.vw / ls.vh, cellAspect: left.rect.w / left.rect.h },
          { win: s.cur, grid: g, srcAspect: s.vw / s.vh, cellAspect: p.rect.w / p.rect.h }, { axis, matchOn: e['framing.match_on'], band: e['framing.edge_sample'] });
      }
      const c = s.curWin || s.win;
      return {
        panel: p.k, clip: s.rec.id, appearance: s.appearance, mode: s.win.effectiveMode, requested: s.win.mode,
        window: { cx: c.cx, cy: c.cy, zoom: c.zoom }, applied: { cx: s.cur.cx, cy: s.cur.cy, zoom: s.cur.zoom, x0: s.cur.x0, y0: s.cur.y0, x1: s.cur.x1, y1: s.cur.y1 },
        colour: colourOf(s.rec).kind, info: s.win.info || {}, edgeMismatch: mismatch,
      };
    });
  }

  // ---- audio ----
  async startAudio() {
    if (this.audio.started) return true;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    const ctx = new Ctx({ latencyHint: 'interactive' });
    try { await ctx.resume(); } catch { /* resumed later by the gesture */ }
    const master = ctx.createGain();
    const comp = ctx.createDynamicsCompressor();
    master.connect(comp); comp.connect(ctx.destination);
    this.audio = { started: true, ctx, master, comp, lastLimiter: '' };
    for (const p of this.panels) {
      this._ensurePanelAudio(p);
      for (const s of p.slots) s.video.muted = this.speechMuted(s.rec);
    }
    for (const p of this.panels) { const s = p.slots[p.active]; if (s) this._audioActivate(p, s, p.slots[1 - p.active]); }
    this._audioLayoutDirty = true;
    this._emit({ type: 'audio' });
    return true;
  }

  _ensurePanelAudio(p) {
    const { ctx, master } = this.audio;
    if (!p.bus) {
      p.bus = ctx.createGain(); p.panner = ctx.createStereoPanner(); p.analyser = ctx.createAnalyser();
      p.analyser.fftSize = 512; p.buf = new Float32Array(p.analyser.fftSize);
      p.bus.connect(p.panner); p.panner.connect(master); p.bus.connect(p.analyser);
    }
    for (const s of p.slots) {
      if (s.src) continue;
      s.video.muted = this.speechMuted(s.rec);
      s.src = ctx.createMediaElementSource(s.video);
      s.gain = ctx.createGain(); s.gain.gain.value = 0;
      s.src.connect(s.gain); s.gain.connect(p.bus);
    }
  }

  _ramp(param, target, seconds) {
    const now = this.audio.ctx.currentTime;
    param.cancelScheduledValues(now);
    param.setValueAtTime(param.value, now);
    param.linearRampToValueAtTime(target, now + Math.max(0.01, seconds));
  }

  normGain(rec) { return clipGain(rec, this.eff); }

  // Muted by the speech policy (or unscreened): the picture plays, the sound never does.
  speechMuted(rec) {
    return !!rec && speechVerdict(rec, this.eff['audio.speech_policy'], this.eff['audio.mute_unscreened']).muted;
  }

  _audioActivate(panel, slot, old) {
    if (!this.audio.started) return;
    this._ensurePanelAudio(panel);
    const fade = this._fadeMs() / 1000;
    slot.norm = this.normGain(slot.rec);
    this._ramp(slot.gain.gain, slot.norm, fade);
    if (old && old.gain && old.rec) { old.norm = 0; this._ramp(old.gain.gain, 0, fade); }
  }

  silent(k) {
    const e = this.eff, solo = e['audio.solo_panels'], muted = e['audio.muted_panels'];
    return muted.includes(k + 1) || (solo.length > 0 && !solo.includes(k + 1));
  }

  _audioPass() {
    const a = this.audio, e = this.eff;
    const now = a.ctx.currentTime;
    const trim = e['audio.auto_trim'] ? 1 / Math.sqrt(Math.max(1, this.panels.length)) : 1;
    const mg = e['audio.master'] * trim;
    if (Math.abs((a.lastMaster ?? -1) - mg) > 1e-4) { a.master.gain.setTargetAtTime(mg, now, 0.02); a.lastMaster = mg; }
    const lim = e['audio.limiter'] ? `${e['audio.limiter_ceiling']}` : 'off';
    if (lim !== a.lastLimiter) {
      a.lastLimiter = lim;
      const c = a.comp;
      if (lim === 'off') { c.threshold.value = 0; c.ratio.value = 1; c.knee.value = 0; }
      else { c.threshold.value = e['audio.limiter_ceiling']; c.ratio.value = 20; c.knee.value = 0; c.attack.value = 0.003; c.release.value = 0.1; }
    }
    for (const p of this.panels) {
      if (!p.bus) continue;
      const g = this.silent(p.k) ? 0 : p.size;
      if (Math.abs((p.lastGain ?? -1) - g) > 1e-4) { p.bus.gain.setTargetAtTime(g, now, 0.02); p.lastGain = g; }
      const pan = e['audio.pan'] ? clamp(p.pan * e['audio.pan_width'], -1, 1) : 0;
      if (Math.abs((p.lastPan ?? 9) - pan) > 1e-4) { p.panner.pan.setTargetAtTime(pan, now, 0.02); p.lastPan = pan; }
      p.panValue = pan;
      for (const sl of p.slots) { const m = this.speechMuted(sl.rec); if (sl.video.muted !== m) sl.video.muted = m; }
      const s = p.slots[p.active];
      if (s && s.gain && s.rec) {
        const n = this.normGain(s.rec);
        if (Math.abs(n - s.norm) > 1e-4) { s.gain.gain.cancelScheduledValues(now); s.gain.gain.setTargetAtTime(n, now, 0.03); s.norm = n; }
      }
    }
  }

  audioState() {
    const e = this.eff;
    return this.panels.map((p) => {
      const s = p.slots[p.active];
      const norm = s ? (s.norm || this.normGain(s.rec)) : 0;
      const normTarget = s ? this.normGain(s.rec) : 0;
      const silent = this.silent(p.k);
      const pan = e['audio.pan'] ? clamp(p.pan * e['audio.pan_width'], -1, 1) : 0;
      return {
        panel: p.k, clip: p.rec?.id ?? null, hasAudio: !!p.rec?.hasAudio, speechMuted: this.speechMuted(p.rec), speechReason: p.rec ? speechVerdict(p.rec, e['audio.speech_policy'], e['audio.mute_unscreened']).reason : '', norm: normTarget, size: p.size, pan,
        gain: silent ? 0 : normTarget * p.size, muted: silent, mute: e['audio.muted_panels'].includes(p.k + 1), solo: e['audio.solo_panels'].includes(p.k + 1),
        level: p.level, elementMuted: s ? s.video.muted : null, routed: !!(s && s.src), actualNorm: norm,
        busGain: p.bus ? p.bus.gain.value : null, slotGain: s && s.gain ? s.gain.gain.value : null, panValue: p.panner ? p.panner.pan.value : null,
        ctxState: this.audio.ctx ? this.audio.ctx.state : null,
      };
    });
  }

  // ---- frame loop ----
  _frame(ts) {
    requestAnimationFrame((t) => this._frame(t));
    const dt = Math.min(0.1, Math.max(0, (ts - this.lastTs) / 1000)); this.lastTs = ts;
    const wall = ts / 1000;
    if (!this.paused && !this.revealPaused) this.t += dt;
    const eff = this.store.effective(wall);
    this.eff = eff;
    const sch = this.sched;
    const seedParam = eff['source.seed'];
    if (seedParam && seedParam !== this.seed) { this.seed = seedParam; sch.reseed(seedParam); }
    sch.setParams(eff);
    const n = eff['layout.panels'];
    if (n !== this.panels.length) this.syncPanels(n);
    if (!this.paused && !this.revealPaused) for (const c of sch.tick(this.t)) this.loadClip(c.panel, c.clip);
    else if (sch.panels.some((p) => p.clip < 0)) for (const c of sch.tick(this.t)) this.loadClip(c.panel, c.clip);
    this._layoutPass(wall);
    const speed = eff['timing.speed'];
    if (Math.abs(speed - this.lastSpeed) > 0.005) { this.lastSpeed = speed; for (const p of this.panels) for (const s of p.slots) s.video.playbackRate = speed; }
    if (this.audio.started) this._audioPass();
    if (this.frameNo % 2 === 0) this._vuPass();
    if (this.frameNo % 6 === 0) {
      this.empty.hidden = sch.pool.length > 0;
      if (!this.empty.hidden) this.empty.textContent = 'No clips match the SOURCE filters and the speech policy.';
      this._emit({ type: 'frame' });
    }
    if (this.reveal && this.reveal.outline) this._placeOutline();
    this.frameNo++;
  }

  _vuPass() {
    const e = this.eff;
    this.levels = this.panels.map((p) => {
      let lv = 0;
      if (p.analyser && !this.silent(p.k) && !this.paused) {
        p.analyser.getFloatTimeDomainData(p.buf);
        let s = 0; for (let i = 0; i < p.buf.length; i++) s += p.buf[i] * p.buf[i];
        lv = Math.sqrt(s / p.buf.length);
      }
      p.level = Math.max(lv, p.level * 0.8);
      const db = 20 * Math.log10(p.level + 1e-6);
      const v = clamp((db + 60) / 60, 0, 1);
      p.vu.firstChild.style.transform = `scaleY(${v.toFixed(3)})`;
      const m = e['audio.muted_panels'].includes(p.k + 1), so = e['audio.solo_panels'].includes(p.k + 1);
      if (p.mute.getAttribute('aria-pressed') !== String(m)) p.mute.setAttribute('aria-pressed', String(m));
      if (p.solo.getAttribute('aria-pressed') !== String(so)) p.solo.setAttribute('aria-pressed', String(so));
      return v;
    });
  }

  // ---- transport ----
  setPaused(p) {
    this.paused = p;
    for (const pn of this.panels) { const s = pn.slots[pn.active]; if (s?.rec) p ? s.video.pause() : s.video.play().catch(() => {}); }
    this._emit({ type: 'transport' });
  }
  togglePause() { this.setPaused(!this.paused); }

  // ---- reveal ----
  dateText(rec) {
    if (!Number.isFinite(rec.capturedMs)) return 'date unknown';
    return new Date(rec.capturedMs).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  }

  chips(rec) {
    const t = rec.raw?.tags;
    if (!t || typeof t !== 'object') return [];
    const out = [];
    for (const k of ['subjects', 'mood', 'palette']) if (Array.isArray(t[k])) out.push(...t[k].filter((x) => typeof x === 'string'));
    for (const k of ['environment', 'setting', 'time_of_day', 'shot', 'camera', 'motion_level']) if (typeof t[k] === 'string' && t[k] !== 'unclear') out.push(t[k].replace(/_/g, ' '));
    return [...new Set(out)];
  }

  openReveal(k) {
    if (this.reveal) return;
    const panel = this.panels[k];
    const rec = panel?.rec;
    if (!rec) return;
    const e = this.eff;
    const action = e['reveal.action'];
    const ms = this.reduced || e['reveal.animation'] === 'none' ? 0 : e['reveal.anim_ms'];
    const root = el('div', 'reveal', { role: 'dialog', 'aria-modal': 'true', 'aria-label': `Original, ${this.dateText(rec)}`, tabindex: '-1' });
    const back = el('div', 'reveal-back'); if (rec.still) back.style.backgroundImage = `url("${this.url(rec.still)}")`;
    const stageBox = el('div', 'reveal-stage');
    let outline = null;
    if (action !== 'video') {
      const img = el('img', 'reveal-still', { alt: `Original photo, ${this.dateText(rec)}`, 'data-clip': rec.id });
      img.src = this.url(rec.still || rec.video);
      stageBox.append(img);
      if (e['reveal.show_window']) {
        const box = el('div', 'reveal-window', { 'aria-hidden': 'true', 'data-clip': rec.id });
        stageBox.append(box);
        outline = { box, img, stageBox };
        img.addEventListener('load', () => this._placeOutline());
      }
    }
    if (action !== 'still') {
      const v = el('video', action === 'both' ? 'reveal-video inset' : 'reveal-video', { 'data-clip': rec.id });
      v.loop = true; v.playsInline = true; v.autoplay = true; v.muted = !this.audio.started || this.speechMuted(rec); v.src = this.url(rec.video); v.controls = false;
      v.addEventListener('click', (ev) => ev.stopPropagation());
      stageBox.append(v);
      v.play().catch(() => {});
    }
    root.append(back, stageBox);
    const meta = el('div', 'reveal-meta');
    if (e['reveal.show_date']) { const d = el('div', 'reveal-date'); d.textContent = this.dateText(rec); meta.append(d); }
    if (e['reveal.show_tags']) {
      const chips = this.chips(rec);
      if (chips.length) { const c = el('div', 'reveal-chips'); for (const t of chips) { const s = el('span', 'chip'); s.textContent = t; c.append(s); } meta.append(c); }
    }
    if (meta.childElementCount) root.append(meta);
    const close = el('button', 'reveal-close', { type: 'button', 'aria-label': 'Close' }); close.textContent = '\u00d7';
    root.append(close);
    root.addEventListener('click', () => this.closeReveal());
    this.revealRoot.append(root);
    this.reveal = { root, rec, k, ms, prevFocus: document.activeElement, outline };
    this._placeOutline();
    if (e['reveal.pause_others']) { this.revealPaused = true; for (const p of this.panels) for (const s of p.slots) s.video.pause(); this.reveal.paused = true; }
    root.focus({ preventScroll: true });
    const r = panel.rect;
    const mode = e['reveal.animation'];
    if (ms > 0) {
      const st = root.style;
      st.transition = 'none';
      if (mode === 'zoom') st.clipPath = `inset(${r.y}px ${this.W - r.x - r.w}px ${this.H - r.y - r.h}px ${r.x}px)`;
      else st.opacity = '0';
      void root.offsetWidth;
      st.transition = `clip-path ${ms}ms ease, opacity ${ms}ms ease`;
      st.clipPath = 'inset(0 0 0 0)'; st.opacity = '1';
    }
    this._emit({ type: 'reveal', open: true, clip: rec.id });
  }

  // "Where this panel was looking": the panel's current window drawn on the contained full still.
  _placeOutline() {
    const rv = this.reveal;
    if (!rv || !rv.outline) return;
    const { box, img, stageBox } = rv.outline;
    const panel = this.panels[rv.k], s = panel && panel.slots[panel.active];
    if (!s || !s.cur || s.rec !== rv.rec) { box.hidden = true; return; }
    const st = stageBox.getBoundingClientRect();
    const nw = img.naturalWidth || rv.rec.width || 540, nh = img.naturalHeight || rv.rec.height || 720;
    const k = Math.min(st.width / nw, st.height / nh), iw = nw * k, ih = nh * k;
    const ox = (st.width - iw) / 2, oy = (st.height - ih) / 2, w = s.cur;
    box.hidden = false;
    const css = box.style;
    css.left = (ox + w.x0 * iw).toFixed(1) + 'px'; css.top = (oy + w.y0 * ih).toFixed(1) + 'px';
    css.width = ((w.x1 - w.x0) * iw).toFixed(1) + 'px'; css.height = ((w.y1 - w.y0) * ih).toFixed(1) + 'px';
    box.dataset.window = [w.cx, w.cy, w.zoom].map((x) => x.toFixed(4)).join(',');
  }

  closeReveal() {
    const rv = this.reveal;
    if (!rv) return;
    this.reveal = null;
    const finish = () => {
      rv.root.remove();
      rv.root.querySelectorAll('video').forEach((v) => { v.pause(); v.removeAttribute('src'); });
      if (rv.paused) { this.revealPaused = false; if (!this.paused) for (const p of this.panels) { const s = p.slots[p.active]; if (s?.rec) s.video.play().catch(() => {}); } }
      this._emit({ type: 'reveal', open: false });
      try { rv.prevFocus?.focus?.({ preventScroll: true }); } catch { /* element gone */ }
    };
    rv.root.classList.add('closing');
    if (rv.ms > 0) {
      const panel = this.panels[rv.k], r = panel?.rect;
      const st = rv.root.style;
      if (this.eff['reveal.animation'] === 'zoom' && r) st.clipPath = `inset(${r.y}px ${this.W - r.x - r.w}px ${this.H - r.y - r.h}px ${r.x}px)`;
      else st.opacity = '0';
      setTimeout(finish, rv.ms + 20);
    } else finish();
  }

  // ---- debug ----
  debug() {
    const self = this;
    return {
      engine: () => self.panels.map((p) => p.rec?.id ?? null),
      scheduled: () => self.sched.onScreen().map((i) => (i >= 0 ? self.records[i].id : null)),
      layoutRects: () => self.panels.map((p) => ({ x: p.rect?.x, y: p.rect?.y, w: p.rect?.w, h: p.rect?.h, tile: p.rect?.tile, zoom: p.fx?.zoom, share: p.fx?.share, video: p.fx ? { x: p.fx.x, y: p.fx.y, w: p.fx.w, h: p.fx.h } : null })),
      audio: () => self.audioState(),
      framing: () => self.framingState(),
      seed: () => self.seed,
      axis: () => self.layout?.axis,
      zoomInfo: () => self.zoomInfo,
      reveal: () => ({ open: !!self.reveal, clip: self.reveal?.rec.id ?? null }),
      paused: () => self.paused,
      pool: () => self.sched.pool.length,
      reduced: () => self.reduced,
      records: () => self.records.length,
      audioStarted: () => self.audio.started,
    };
  }
}
