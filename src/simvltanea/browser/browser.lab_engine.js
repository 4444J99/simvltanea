/* Effects Lab playback is intentionally independent of the inherited Studio. */
(function (root, factory) {
  const model = typeof module === 'object' && module.exports ? require('./browser.lab_model.js') : root.SimvltaneaLabModel;
  const audio = typeof module === 'object' && module.exports ? require('./browser.audio.js') : root.SimvltaneaLiveAudio;
  const api = factory(root, model, audio);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SimvltaneaLabEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root, Model, LiveAudio) {
  'use strict';
  const TAP_COUNT = 12;
  const HEADROOM = 0.20;
  const DEMO_HEADROOM = 0.40;
  const EPS = 1e-6;
  function param(p, value, now, immediate) {
    if (!p || !Number.isFinite(value)) return;
    if (immediate) { p.cancelScheduledValues(now); p.setValueAtTime(value, now); return; }
    if (typeof p.cancelAndHoldAtTime === 'function') p.cancelAndHoldAtTime(now);
    else { p.cancelScheduledValues(now); p.setValueAtTime(p.value, now); }
    p.setTargetAtTime(value, now, 0.02);
  }
  function createVoiceGraph(context, destination) {
    const nodes = [];
    const gainNode = () => { const n = context.createGain(); nodes.push(n); return n; };
    const input = gainNode();
    function stage(type, previous) {
      const filter = context.createBiquadFilter(); filter.type = type; nodes.push(filter);
      const bypass = gainNode(), enabled = gainNode(), output = gainNode();
      previous.connect(filter); filter.connect(enabled); enabled.connect(output);
      previous.connect(bypass); bypass.connect(output);
      return { filter, bypass, enabled, output };
    }
    const lp = stage('lowpass', input), hp = stage('highpass', lp.output), bp = stage('bandpass', hp.output);
    const dry = gainNode(), wet = gainNode(), sum = gainNode(), gain = gainNode();
    bp.output.connect(dry); dry.connect(sum); wet.connect(sum); sum.connect(gain); gain.connect(destination);
    const taps = [];
    // Feed-forward taps retain sub-render-quantum spacing. DelayNode feedback
    // cycles cannot represent the requested high comb frequencies accurately.
    for (let i = 1; i <= TAP_COUNT; i++) {
      const delay = context.createDelay(0.4); nodes.push(delay);
      const level = gainNode(); bp.output.connect(delay); delay.connect(level); level.connect(wet);
      taps.push({ delay, gain: level });
    }
    let first = true, disposed = false;
    return {
      input, lowpass: lp.filter, highpass: hp.filter, bandpass: bp.filter,
      delay: taps[0].delay, feedback: taps[0].gain, wet, dry, gain, taps,
      combType: 'finite-feed-forward',
      apply(partial, presence, phase, time, offset) {
        if (disposed) return;
        const s = Model.normalizeSettings(partial), now = context.currentTime;
        const f = Model.filterTargets(presence, phase, s, context.sampleRate);
        [[lp, f.lowpassEnabled, f.lowpassHz], [hp, f.highpassEnabled, f.highpassHz], [bp, f.bandpassEnabled, f.bandpassHz]].forEach(([stage, active, frequency]) => {
          param(stage.enabled.gain, active ? 1 : 0, now, first);
          param(stage.bypass.gain, active ? 0 : 1, now, first);
          param(stage.filter.frequency, frequency, now, first);
          param(stage.filter.Q, stage === bp ? f.bandpassQ : s.resonance, now, first);
        });
        const hz = Model.combFrequency(time, s, offset || 0);
        const decay = s.combFeedback;
        const normalization = decay === 0 ? 1 : (1 - decay) / (1 - Math.pow(decay, TAP_COUNT));
        taps.forEach((tap, i) => {
          param(tap.delay.delayTime, (i + 1) / hz, now, first);
          param(tap.gain.gain, normalization * Math.pow(decay, i), now, first);
        });
        param(dry.gain, 1 - s.combMix, now, first);
        param(wet.gain, s.combMix, now, first);
        param(gain.gain, Math.max(0, Math.min(1, presence)) * s.audioGain, now, first);
        first = false;
      },
      dispose() { if (disposed) return; disposed = true; nodes.forEach(n => { try { n.disconnect(); } catch (_) {} }); }
    };
  }
  function clock() { return root.performance ? root.performance.now() / 1000 : Date.now() / 1000; }
  function track() { return { age: 0, position: 0, rate: 1, loops: 0, presence: 0, active: false }; }
  function safePause(media) { if (media) { try { media.pause(); } catch (_) {} } }
  function seek(media, position) { if (media) { try { media.currentTime = Math.max(0, position); } catch (_) {} } }
  function demoDuration(flavor) { return flavor === 'grain' ? 4 : flavor === 'prism' ? 5 : 6; }
  function seedFor(id, trackName) {
    let value = 2166136261;
    for (const character of `${id}:${trackName}`) value = Math.imul(value ^ character.charCodeAt(0), 16777619) >>> 0;
    return value;
  }
  function filterCSS(s) {
    return `brightness(${s.brightness}) contrast(${s.contrast}) saturate(${s.saturation}) hue-rotate(${s.hue}deg) blur(${s.blur}px) invert(${s.invert})`;
  }
  function supportsCanvasFilter() {
    if (!root.document) return false;
    try {
      const c = root.document.createElement('canvas'); c.width = c.height = 1;
      const x = c.getContext('2d'); if (!x || !('filter' in x)) return false;
      x.fillStyle = '#fff'; x.filter = 'brightness(0)'; x.fillRect(0, 0, 1, 1);
      const p = x.getImageData(0, 0, 1, 1).data; return p[0] === 0 && p[3] === 255;
    } catch (_) { return false; }
  }
  function demoBuffer(context, flavor) {
    const duration = demoDuration(flavor);
    const buffer = context.createBuffer(2, Math.round(context.sampleRate * duration), context.sampleRate);
    const notes = flavor === 'prism' ? [146.832, 220, 293.665, 369.994] : flavor === 'grain' ? [82.407, 123.471, 164.814] : [110, 164.814, 220, 277.183];
    let seed = 20261107;
    for (let channel = 0; channel < 2; channel++) {
      const data = buffer.getChannelData(channel); let filtered = 0;
      for (let i = 0; i < data.length; i++) {
        const t = i / context.sampleRate;
        seed = (1664525 * seed + 1013904223) >>> 0;
        const noise = seed / 2147483648 - 1; filtered = 0.86 * filtered + 0.14 * noise;
        const pulse = Math.exp(-((t + channel * .035) % .5) * 24);
        let chord = 0;
        notes.forEach((n, j) => { for (let harmonic = 1; harmonic <= 6; harmonic++) chord += Math.sin(2 * Math.PI * n * harmonic * t + channel * .13 * j) / (harmonic * notes.length * 6); });
        const edge = Math.min(1, t * 120, (duration - t) * 120);
        data[i] = edge * (.40 * chord + (flavor === 'grain' ? .18 : .085) * noise * pulse + .065 * filtered);
      }
    }
    // Normalize generated starters, whose layered synthesis is deliberately
    // quiet internally. Imported media retains the conservative voice gain.
    let peak = 0;
    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      for (const value of buffer.getChannelData(channel)) peak = Math.max(peak, Math.abs(value));
    }
    if (peak > 0) {
      const scale = .8 / peak;
      for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
        const data = buffer.getChannelData(channel);
        for (let i = 0; i < data.length; i++) data[i] *= scale;
      }
    }
    return buffer;
  }
  class Engine {
    constructor(canvas, options) {
      this.canvas = canvas; this.ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;
      this.options = options || {}; this.clips = []; this.playing = false; this.time = 0; this.volume = .45; this.muted = false;
      this.sequence = { enabled: false, interval: 8 }; this.context = null; this.master = null;
      this.transport = { mode: 'perform', looping: false, loopStart: 0, loopEnd: 60 };
      this.disposed = false; this._pending = 0; this._pendingIds = new Set(); this._serial = 0; this._sequenceAfter = null; this._nextSequence = 8; this._frame = null; this._last = 0; this._notifyAt = -Infinity;
      this._canvasFilters = supportsCanvasFilter(); this._cssLayers = !this._canvasFilters && !!(canvas && canvas.parentElement && root.document);
      this._visibility = () => { if (root.document.hidden && this.playing) this.pause(); };
      if (root.document) root.document.addEventListener('visibilitychange', this._visibility);
    }
    _emit(force) {
      if (this.disposed) return;
      if (force || this.time - this._notifyAt >= .1) {
        this._notifyAt = this.time;
        if (this.options.onChange) this.options.onChange(this.snapshot());
      }
    }
    _error(clip, error) {
      const message = error && error.message ? error.message : String(error);
      if (clip) clip.error = message;
      if (this.options.onError) this.options.onError(message);
      this._emit(true);
    }
    async addClip(source, partial) {
      if (this.disposed) throw new Error('Effects Lab is closed.');
      if (this.clips.length + this._pending >= Model.MAX_CLIPS) throw new Error(`Effects Lab supports at most ${Model.MAX_CLIPS} clips.`);
      if (!source || !['demo', 'video', 'audio'].includes(source.kind)) throw new Error('Choose a demo, video, or audio clip.');
      if (source.kind !== 'demo' && !source.url) throw new Error('This clip has no media URL.');
      let id = source.id;
      if (!id) { do { id = `lab-${++this._serial}`; } while (this._pendingIds.has(id) || this.clips.some(c => c.id === id)); }
      if (typeof id !== 'string') throw new Error('A clip ID must be a string.');
      if (this._pendingIds.has(id) || this.clips.some(c => c.id === id)) throw new Error('A clip with this ID already exists.');
      this._pending++; this._pendingIds.add(id);
      const c = { id, name: source.name || 'Untitled clip', kind: source.kind, source: { ...source }, settings: Model.normalizeSettings(partial), age: 0, active: false, error: null,
        video: track(), audio: track(), videoElement: null, audioElement: null, buffer: null, bufferSource: null, graph: null, headroom: null,
        mediaSource: null, generation: 0, audioGeneration: 0, primed: false, launched: false, layer: null, duration: 0, removed: false, blocked: { video: false, audio: false },
        capabilities: { preservePitch: source.kind !== 'demo', canvasFilters: this._canvasFilters, pictureEffects: this._canvasFilters || this._cssLayers, combType: 'finite-feed-forward' } };
      Object.defineProperty(c, 'combPhase', { value: ((seedFor(id, 'comb') - seedFor('lab-1', 'comb')) >>> 0) / 4294967296, enumerable: true });
      Object.defineProperty(c, 'videoSeed', { value: seedFor(id, 'video'), enumerable: true });
      Object.defineProperty(c, 'audioSeed', { value: seedFor(id, 'audio'), enumerable: true });
      try {
        if (source.kind !== 'demo') await this._loadNative(c);
        else c.duration = c.videoDuration = c.audioDuration = demoDuration(source.demo);
        if (this.disposed) throw new Error('Effects Lab was closed while loading.');
        if (this.clips.some(x => x.id === id)) throw new Error('A clip with this ID already exists.');
        if (root.document && c.kind !== 'audio') {
          c.layer = root.document.createElement('canvas'); c.layer.width = this.canvas.width; c.layer.height = this.canvas.height;
          if (this._cssLayers) {
            Object.assign(c.layer.style, { position: 'absolute', inset: '0', width: '100%', height: '100%', pointerEvents: 'none', zIndex: '0', display: 'none' });
            c.layer.setAttribute('aria-hidden', 'true'); this.canvas.parentElement.insertBefore(c.layer, this.canvas.nextSibling);
          }
        }
        this.clips.push(c); this._sortLayers();
        if (this.transport.mode === 'arrange') this._syncArrangement(true, c);
        this._draw(); this._emit(true); return id;
      } catch (error) { this._release(c); throw error; }
      finally { this._pending--; this._pendingIds.delete(id); }
    }
    _loadNative(c) {
      if (!root.document) return Promise.reject(new Error('Native media needs a browser.'));
      const make = tag => {
        const el = root.document.createElement(tag); el.preload = 'auto'; el.loop = false;
        el.setAttribute('playsinline', ''); el.playsInline = true;
        if (tag === 'video') { el.muted = true; el.defaultMuted = true; }
        el.src = c.source.url; return el;
      };
      c.audioElement = make('audio');
      if (c.kind === 'video') c.videoElement = make('video');
      const metadata = media => new Promise((resolve, reject) => {
        let timer;
        const clear = () => { clearTimeout(timer); media.removeEventListener('loadedmetadata', ready); media.removeEventListener('error', failed); };
        const ready = () => { if (!Number.isFinite(media.duration) || media.duration <= 0) { clear(); reject(new Error('This media has no finite playable duration.')); return; } clear(); resolve(media.duration); };
        const failed = () => { clear(); reject(new Error(`Cannot decode ${c.name}. Try a browser-supported video or audio format.`)); };
        media.addEventListener('loadedmetadata', ready); media.addEventListener('error', failed);
        timer = setTimeout(() => { clear(); reject(new Error(`Loading ${c.name} timed out.`)); }, 12000);
        if (media.readyState >= 1) ready(); else media.load();
      });
      return Promise.all([metadata(c.audioElement), c.videoElement ? metadata(c.videoElement) : Promise.resolve(0)]).then(([audioDuration, videoDuration]) => {
        c.duration = audioDuration; c.audioDuration = audioDuration; c.videoDuration = videoDuration;
        c.capabilities.preservePitch = 'preservesPitch' in c.audioElement || 'webkitPreservesPitch' in c.audioElement;
        c._audioEnded = () => this._nativeEnded(c, 'audio');
        c._videoEnded = () => this._nativeEnded(c, 'video');
        c._pictureReady = () => { if (!c.removed) this._draw(); };
        c.audioElement.addEventListener('ended', c._audioEnded);
        if (c.videoElement) {
          c.videoElement.addEventListener('ended', c._videoEnded);
          c.videoElement.addEventListener('seeked', c._pictureReady);
          c.videoElement.addEventListener('loadeddata', c._pictureReady);
        }
      });
    }
    _nativeEnded(c, key) {
      if (!this.playing || !c[key].active || c.removed) return;
      if (this.transport.mode === 'arrange') { this._refreshArrangementClock(); return; }
      c[key].position = 0; this._repeat(c, key); this._playNativeTrack(c, key);
    }
    _refreshArrangementClock() {
      if (!this.playing) return;
      const now = clock(), delta = this._last ? Math.max(0, now - this._last) : 0;
      this._last = now; this._advanceArrangement(delta);
    }
    _ensureAudio() {
      if (this.context) return;
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) throw new Error('Web Audio is not supported in this browser.');
      this.context = new AC();
      this.master = LiveAudio.createMasterBus(this.context, { volume: this.volume, enabled: !this.muted });
    }
    _ensureVoice(c) {
      if (c.graph) return;
      c.headroom = this.context.createGain(); c.headroom.gain.value = c.kind === 'demo' ? DEMO_HEADROOM : HEADROOM; c.headroom.connect(this.master.input);
      c.graph = createVoiceGraph(this.context, c.headroom);
      c.graph.apply(c.settings, 0, 'waiting', this.time, c.combPhase);
      if (c.kind === 'demo') { c.buffer = demoBuffer(this.context, c.source.demo || 'tide'); c.audioDuration = c.buffer.duration; c.videoDuration = c.buffer.duration; }
      else { c.mediaSource = this.context.createMediaElementSource(c.audioElement); c.mediaSource.connect(c.graph.input); }
    }
    _activate(c) {
      if (!c || c.removed) return;
      this._stopBuffer(c); safePause(c.videoElement); safePause(c.audioElement);
      c.generation++; c.age = 0; c.error = null; c.blocked = { video: false, audio: false }; c.launched = true; this._sequenceAfter = c.id;
      c.video = { ...track(), rate: c.settings.videoRate, active: c.settings.videoEnabled && c.kind !== 'audio' };
      c.audio = { ...track(), rate: c.settings.audioRate, active: c.settings.audioEnabled };
      c.active = c.video.active || c.audio.active;
      seek(c.videoElement, 0); seek(c.audioElement, 0); this._applyPitch(c); this._updateVoice(c);
    }
    _applyPitch(c) {
      if (!c.audioElement) return;
      if ('preservesPitch' in c.audioElement) c.audioElement.preservesPitch = c.settings.preservePitch;
      if ('webkitPreservesPitch' in c.audioElement) c.audioElement.webkitPreservesPitch = c.settings.preservePitch;
    }
    _repeat(c, key) {
      const t = c[key]; if (!t || !t.active) return;
      t.loops++; t.rate = Model.nextRate(t.rate, c.settings[key + 'Wander'], this.transport.mode === 'arrange' ? () => Model.repeatUnit(c[key + 'Seed'], t.loops) : Math.random);
      const media = key === 'video' ? c.videoElement : c.audioElement;
      if (media) media.playbackRate = t.rate;
      this._emit(true);
    }
    _playNativeTrack(c, key) {
      const media = key === 'video' ? c.videoElement : c.audioElement;
      if (!media || !c[key].active || !this.playing) return Promise.resolve();
      media.playbackRate = c[key].rate;
      const generation = c.generation;
      try {
        const result = media.play();
        return Promise.resolve(result).then(() => { c.primed = true; }, error => {
          if (c.removed || c.generation !== generation || !this.playing) return;
          c.blocked[key] = true;
          c[key].active = false; c[key].presence = 0; c.active = c.video.active || c.audio.active;
          this._updateVoice(c); this._error(c, new Error(`${c.name}: ${key} playback was blocked (${error.message || error}). Press Launch to retry.`));
        });
      } catch (error) {
        c.blocked[key] = true; c[key].active = false; c[key].presence = 0; c.active = c.video.active || c.audio.active; this._updateVoice(c); this._error(c, error); return Promise.resolve();
      }
    }
    _startBuffer(c) {
      if (!this.context || !c.buffer || !c.audio.active || !this.playing || c.bufferSource) return;
      const source = this.context.createBufferSource(); source.buffer = c.buffer;
      source.playbackRate.value = c.audio.rate; source.connect(c.graph.input); c.bufferSource = source;
      const generation = ++c.audioGeneration;
      c._bufferStarted = this.context.currentTime; c._bufferOffset = c.audio.position; c._bufferRate = c.audio.rate;
      source.onended = () => {
        if (generation !== c.audioGeneration || c.bufferSource !== source) return;
        source.disconnect(); c.bufferSource = null;
        if (this.playing && c.audio.active && !c.removed) {
          if (this.transport.mode === 'arrange') this._refreshArrangementClock();
          else { c.audio.position = 0; this._repeat(c, 'audio'); this._startBuffer(c); }
        }
      };
      source.start(0, c.audio.position % c.buffer.duration);
    }
    _stopBuffer(c) {
      c.audioGeneration++;
      if (!c.bufferSource) return;
      if (this.context && c.buffer && this.transport.mode !== 'arrange') c.audio.position = Math.min(c.buffer.duration, c._bufferOffset + (this.context.currentTime - c._bufferStarted) * c._bufferRate);
      c.bufferSource.onended = null;
      try { c.bufferSource.stop(); } catch (_) {} try { c.bufferSource.disconnect(); } catch (_) {} c.bufferSource = null;
    }
    _start(c) {
      if (c.kind === 'demo') { this._startBuffer(c); return []; }
      return [this._playNativeTrack(c, 'video'), this._playNativeTrack(c, 'audio')];
    }
    async play() {
      if (this.disposed || this.playing) return;
      try { this._ensureAudio(); this.clips.forEach(c => this._ensureVoice(c)); }
      catch (error) { this._error(null, error); return; }
      // All gesture-dependent calls occur before this method's first await.
      const resume = this.context.resume();
      if (this.transport.mode === 'arrange') this._syncArrangement(true);
      this.playing = true;
      if (this.transport.mode === 'perform' && !this.clips.some(c => c.active)) { const first = this.clips.find(c => c.settings.videoEnabled || c.settings.audioEnabled); if (first) this._activate(first); }
      const promises = [];
      this.clips.forEach(c => {
        if (c.active) promises.push(...this._start(c));
        else if (c.kind !== 'demo' && !c.primed) {
          [c.videoElement, c.audioElement].filter(Boolean).forEach(media => {
            try {
              const generation = c.generation;
              promises.push(Promise.resolve(media.play()).then(() => {
                c.primed = true; if (!c.removed && c.generation === generation && !c.active) { safePause(media); seek(media, 0); }
              }, () => { /* A later explicit Launch can retry this waiting clip. */ }));
            } catch (_) {}
          });
        }
      });
      this._last = clock(); this._schedule(); this._emit(true);
      try { await resume; await Promise.all(promises); }
      catch (error) { if (!this.disposed) { this.pause(); this._error(null, error); } }
    }
    pause() {
      if (this.disposed) return;
      if (this.playing && this._last) { const now = clock(); this._advance(Math.max(0, now - this._last)); }
      this.playing = false; this._last = 0;
      if (this._frame !== null && root.cancelAnimationFrame) root.cancelAnimationFrame(this._frame); this._frame = null;
      this.clips.forEach(c => { this._capture(c); this._stopBuffer(c); safePause(c.videoElement); safePause(c.audioElement); });
      if (this.context && this.context.state === 'running') this.context.suspend().catch(() => {});
      this._emit(true);
    }
    async launch(id) {
      const c = this.clips.find(x => x.id === id); if (!c || this.disposed) return;
      if (this.transport.mode === 'arrange') { this.seek(c.settings.timelineStart); return this.play(); }
      try { this._ensureAudio(); this._ensureVoice(c); } catch (error) { this._error(c, error); return; }
      this._activate(c);
      if (!this.playing) return this.play();
      const resume = this.context.resume(); const promises = this._start(c);
      this._emit(true); await Promise.all([resume, ...promises]);
    }
    set(id, partial) {
      const c = this.clips.find(x => x.id === id); if (!c || this.disposed) return;
      const previous = c.settings; this._capture(c);
      c.settings = Model.normalizeSettings(partial, c.settings);
      if (this.transport.mode === 'arrange') {
        const resetKeys = ['video', 'audio'].filter(key => previous[key + 'Rate'] !== c.settings[key + 'Rate'] || previous[key + 'Wander'] !== c.settings[key + 'Wander']);
        this._applyPitch(c); this._syncArrangement(previous.timelineStart !== c.settings.timelineStart, c, resetKeys);
        this._draw(); this._emit(true); return;
      }
      if (partial.videoRate !== undefined) { c.video.rate = c.settings.videoRate; if (c.videoElement) c.videoElement.playbackRate = c.video.rate; }
      if (partial.audioRate !== undefined) {
        this._capture(c); this._stopBuffer(c); c.audio.rate = c.settings.audioRate;
        if (c.audioElement) c.audioElement.playbackRate = c.audio.rate;
        if (this.playing && c.audio.active && c.kind === 'demo') this._startBuffer(c);
      }
      if (!c.settings.videoEnabled) { c.video.active = false; c.video.presence = 0; safePause(c.videoElement); }
      if (!c.settings.audioEnabled) { c.audio.active = false; c.audio.presence = 0; this._stopBuffer(c); safePause(c.audioElement); }
      const restored = [];
      ['video', 'audio'].forEach(key => {
        if (!previous[key + 'Enabled'] && c.settings[key + 'Enabled'] && c.launched &&
            (key !== 'video' || c.kind !== 'audio') && (c.settings.hold || c[key].age < c.settings[key + 'Life'])) {
          c[key].active = true; restored.push(key);
        }
      });
      c.active = c.video.active || c.audio.active; this._applyPitch(c); this._updateVoice(c); this._draw(); this._emit(true);
      if (this.playing) restored.forEach(key => {
        if (c.kind === 'demo') { if (key === 'audio') this._startBuffer(c); }
        else this._playNativeTrack(c, key);
      });
    }
    setMaster(partial) {
      if (partial.volume !== undefined) { const v = Number(partial.volume); if (Number.isFinite(v)) this.volume = Math.max(0, Math.min(1, v)); }
      if (partial.muted !== undefined) this.muted = !!partial.muted;
      if (this.master) this.master.setVolume(this.volume, !this.muted); this._emit(true);
    }
    setSequence(partial) {
      if (partial.enabled !== undefined) this.sequence.enabled = this.transport.mode === 'perform' && !!partial.enabled;
      if (partial.interval !== undefined) { const n = Number(partial.interval); if (Number.isFinite(n)) this.sequence.interval = Math.max(1, Math.min(120, n)); }
      this._nextSequence = this.time + this.sequence.interval; this._emit(true);
    }
    setTransport(partial = {}) {
      if (this.disposed) return;
      const previous = this.transport.mode;
      if (partial.mode === 'arrange' || partial.mode === 'perform') this.transport.mode = partial.mode;
      if (partial.looping !== undefined) this.transport.looping = !!partial.looping;
      for (const key of ['loopStart', 'loopEnd']) {
        const value = Number(partial[key]);
        if (partial[key] !== undefined && Number.isFinite(value)) this.transport[key] = Math.max(0, Math.min(4500, value));
      }
      if (this.transport.loopEnd <= this.transport.loopStart) this.transport.loopEnd = this.transport.loopStart + .25;
      if (this.transport.mode === 'arrange') {
        this.sequence.enabled = false; this._syncArrangement(previous !== 'arrange');
      }
      if (previous !== this.transport.mode) this._last = this.playing ? clock() : 0;
      this._draw(); this._emit(true);
    }
    seek(seconds) {
      if (this.disposed || !Number.isFinite(Number(seconds))) return;
      this.time = Math.max(0, Math.min(4500, Number(seconds))); this._notifyAt = -Infinity;
      this._last = this.playing ? clock() : 0;
      if (this.transport.mode === 'arrange') this._syncArrangement(true);
      this._draw(); this._emit(true);
    }
    stop() {
      if (this.disposed) return;
      this.pause();
      if (this.transport.mode === 'perform') this.clips.forEach(c => {
        c.generation++; c.age = 0; c.active = false; c.launched = false;
        c.video = { ...track(), rate: c.settings.videoRate }; c.audio = { ...track(), rate: c.settings.audioRate };
        seek(c.videoElement, 0); seek(c.audioElement, 0); this._updateVoice(c);
      });
      this.seek(0); this._nextSequence = this.sequence.interval;
    }
    _syncArrangement(force = false, only = null, resetKeys = []) {
      const clips = only ? [only] : this.clips;
      clips.forEach(c => {
        const local = this.time - c.settings.timelineStart;
        if (force) { c.generation++; c.error = null; c.blocked = { video: false, audio: false }; }
        c.age = Math.max(0, local); c.launched = local >= 0;
        if (this.playing && this.context && !c.graph) this._ensureVoice(c);
        const starts = [];
        ['video', 'audio'].forEach(key => {
          const old = c[key], life = c.settings[key + 'Life'], age = Math.max(0, Math.min(life, local));
          const duration = c[key + 'Duration'] || 0;
          const position = Model.positionAt(age, duration, c.settings[key + 'Rate'], c.settings[key + 'Wander'], c[key + 'Seed']);
          const active = local >= 0 && local < life - EPS && c.settings[key + 'Enabled'] && (key !== 'video' || c.kind !== 'audio') && !c.blocked[key];
          const reset = force || resetKeys.includes(key) || (active && !old.active) || old.loops !== position.loops || old.rate !== position.rate;
          if (key === 'audio' && c.bufferSource && (reset || !active)) this._stopBuffer(c);
          c[key] = { ...old, ...position, age, active };
          const media = key === 'video' ? c.videoElement : c.audioElement;
          if (media) {
            if (!active) safePause(media);
            const drift = Math.abs(media.currentTime - position.position);
            if (reset || (active && !media.seeking && drift > .2)) seek(media, position.position);
            if (media.playbackRate !== position.rate) media.playbackRate = position.rate;
            if (this.playing && active && (reset || (media.paused && !media.ended))) starts.push(key);
          }
        });
        c.active = c.video.active || c.audio.active; this._updateVoice(c);
        if (this.playing) {
          if (c.kind === 'demo') this._startBuffer(c);
          else starts.forEach(key => this._playNativeTrack(c, key));
        }
      });
    }
    _advanceArrangement(delta) {
      let remaining = delta;
      while (remaining > EPS) {
        if (this.transport.looping && this.time + EPS >= this.transport.loopEnd) {
          this.time = this.transport.loopStart + Math.max(0, this.time - this.transport.loopEnd) % (this.transport.loopEnd - this.transport.loopStart);
          this._notifyAt = -Infinity; // A wrapped timeline must not wait for its previous notification time.
          this._syncArrangement(true);
        }
        let step = remaining;
        if (this.transport.looping) step = Math.min(step, this.transport.loopEnd - this.time);
        this.clips.forEach(c => {
          const start = c.settings.timelineStart;
          for (const boundary of [start, start + c.settings.videoLife, start + c.settings.audioLife]) {
            if (boundary > this.time + EPS) step = Math.min(step, boundary - this.time);
          }
        });
        this.time += step; remaining -= step; this._syncArrangement();
      }
      if (this.transport.looping && this.time + EPS >= this.transport.loopEnd) {
        this.time = this.transport.loopStart + Math.max(0, this.time - this.transport.loopEnd) % (this.transport.loopEnd - this.transport.loopStart);
        this._notifyAt = -Infinity;
        this._syncArrangement(true);
      } else if (delta === 0) this._syncArrangement();
      this._draw(); this._emit(false);
    }
    move(id, delta) {
      const from = this.clips.findIndex(c => c.id === id); if (from < 0) return;
      const to = Math.max(0, Math.min(this.clips.length - 1, from + Math.trunc(delta)));
      const [clip] = this.clips.splice(from, 1); this.clips.splice(to, 0, clip); this._sortLayers(); this._draw(); this._emit(true);
    }
    remove(id) { const i = this.clips.findIndex(c => c.id === id); if (i < 0) return; this._release(this.clips[i]); this.clips.splice(i, 1); this._draw(); this._emit(true); }
    _capture(c) {
      if (this.transport.mode === 'arrange') return;
      if (c.videoElement && c.video.active && Number.isFinite(c.videoElement.currentTime)) c.video.position = c.videoElement.currentTime;
      if (c.audioElement && c.audio.active && Number.isFinite(c.audioElement.currentTime)) c.audio.position = c.audioElement.currentTime;
      if (c.bufferSource && this.context) c.audio.position = Math.min(c.buffer.duration, c._bufferOffset + (this.context.currentTime - c._bufferStarted) * c._bufferRate);
    }
    _updateVoice(c) {
      ['video', 'audio'].forEach(key => {
        const t = c[key], life = c.settings[key + 'Life'];
        t.presence = t.active ? (c.settings.hold ? (this.transport.mode === 'arrange' ? 1 : Math.min(1, t.age / c.settings.attack)) : Model.envelope(t.age, life, c.settings.attack)) : 0;
      });
      if (c.graph) c.graph.apply(c.settings, c.audio.presence, Model.phase(c.audio.age, c.settings.audioLife, c.settings.attack), this.time, c.combPhase);
    }
    _sequenceLaunch() {
      if (this.transport.mode !== 'perform' || !this.sequence.enabled || this.time + EPS < this._nextSequence || !this.clips.length) return;
      const start = (this.clips.findIndex(c => c.id === this._sequenceAfter) + 1) % this.clips.length;
      for (let offset = 0; offset < this.clips.length; offset++) {
        const c = this.clips[(start + offset) % this.clips.length];
        if (c.active || c.error || (!c.settings.audioEnabled && (!c.settings.videoEnabled || c.kind === 'audio'))) continue;
        if (this.context) this._ensureVoice(c);
        this._activate(c); this._start(c); this._nextSequence = this.time + this.sequence.interval; return;
      }
      // Leave the deadline pending while every admitted pair has a live tail.
    }
    _advance(delta) {
      if (!this.playing || this.disposed || !Number.isFinite(delta) || delta < 0) return;
      if (this.transport.mode === 'arrange') { this._advanceArrangement(delta); return; }
      // Split at sequence deadlines and track endings: a pending launch starts
      // as soon as a slot opens, without truncating an existing sound tail.
      let remaining = delta;
      while (remaining > EPS) {
        this._sequenceLaunch();
        const toBoundary = this.sequence.enabled ? Math.max(0, this._nextSequence - this.time) : Infinity;
        let toEnd = Infinity;
        this.clips.forEach(c => {
          if (c.settings.hold) return;
          ['video', 'audio'].forEach(key => { if (c[key].active) toEnd = Math.min(toEnd, Math.max(EPS, c.settings[key + 'Life'] - c[key].age)); });
        });
        const step = Math.min(remaining, toBoundary || remaining, toEnd);
        this.time += step; remaining -= step;
        this.clips.forEach(c => {
          if (!c.active) return;
          c.age += step;
          ['video', 'audio'].forEach(key => {
            const t = c[key]; if (!t.active) return;
            t.age += step;
            if (c.kind === 'demo') {
              if (key === 'video' || !c.bufferSource) {
                t.position += step * t.rate;
                const duration = c[key + 'Duration'] || 6;
                // Virtual picture loops and non-playing test clocks are independent.
                while (t.position >= duration) { t.position -= duration; this._repeat(c, key); }
              }
            }
            if (!c.settings.hold && t.age + EPS >= c.settings[key + 'Life']) {
              t.active = false; t.presence = 0;
              if (key === 'audio') { this._stopBuffer(c); safePause(c.audioElement); }
              else safePause(c.videoElement);
            }
          });
          c.active = c.video.active || c.audio.active; this._capture(c); this._updateVoice(c);
        });
        this._sequenceLaunch();
      }
      this._draw(); this._emit(false);
    }
    _schedule() {
      if (!root.requestAnimationFrame || !this.playing || this.disposed) return;
      this._frame = root.requestAnimationFrame(() => {
        this._frame = null; if (!this.playing || this.disposed) return;
        const now = clock(); const delta = Math.max(0, now - this._last); this._last = now; this._advance(delta); this._schedule();
      });
    }
    _sortLayers() {
      this.clips.forEach(c => { if (c.layer && c.layer.parentNode) c.layer.parentNode.appendChild(c.layer); });
    }
    _picture(x, c, w, h) {
      if (c.kind === 'video') {
        const el = c.videoElement; if (!el || el.readyState < 2 || !el.videoWidth) return;
        const ratio = Math.max(w / el.videoWidth, h / el.videoHeight), dw = el.videoWidth * ratio, dh = el.videoHeight * ratio;
        x.drawImage(el, (w - dw) / 2, (h - dh) / 2, dw, dh); return;
      }
      const t = c.video.position, demo = c.source.demo || 'tide';
      if (demo === 'prism') {
        x.fillStyle = '#120b25'; x.fillRect(0, 0, w, h);
        for (let i = 0; i < 7; i++) {
          x.save(); x.translate(w * .5, h * .5); x.rotate(t * .12 + i * .48);
          x.fillStyle = `hsla(${(i * 51 + t * 12) % 360},90%,62%,.65)`;
          x.fillRect(-w * .7, (i - 3) * h * .09, w * 1.4, h * .075); x.restore();
        }
      } else if (demo === 'grain') {
        x.fillStyle = '#081817'; x.fillRect(0, 0, w, h);
        for (let i = 0; i < 160; i++) {
          const px = ((i * 137.508 + t * (12 + i % 9)) % w), py = ((i * 83.17 + Math.sin(t + i) * 28 + h) % h);
          x.fillStyle = `hsla(${160 + i % 80},80%,${35 + i % 55}%,.8)`;
          x.fillRect(px, py, 2 + i % 17, 2 + i % 7);
        }
      } else {
        const gradient = x.createLinearGradient(0, 0, w, h); gradient.addColorStop(0, '#021c3b'); gradient.addColorStop(1, '#dd7353'); x.fillStyle = gradient; x.fillRect(0, 0, w, h);
        for (let i = 0; i < 9; i++) {
          x.beginPath(); x.moveTo(0, h);
          for (let px = 0; px <= w + 12; px += 12) x.lineTo(px, h * (.2 + i * .08) + Math.sin(px / w * 8 + t * .65 + i * .7) * h * .1);
          x.lineTo(w, h); x.closePath(); x.fillStyle = `hsla(${190 + i * 9},80%,${25 + i * 5}%,.43)`; x.fill();
        }
      }
    }
    _draw() {
      if (!this.canvas) return;
      const w = this.canvas.width || 960, h = this.canvas.height || 540;
      if (this.ctx) { this.ctx.save(); this.ctx.setTransform(1, 0, 0, 1, 0, 0); this.ctx.filter = 'none'; this.ctx.globalAlpha = 1; this.ctx.globalCompositeOperation = 'source-over'; this.ctx.fillStyle = '#06080d'; this.ctx.fillRect(0, 0, w, h); this.ctx.restore(); }
      let hasPicture = false;
      this.clips.forEach(c => {
        const visible = c.video.active && c.video.presence > 0 && c.settings.opacity > 0 &&
          (c.kind !== 'video' || (c.videoElement && c.videoElement.readyState >= 2 && c.videoElement.videoWidth > 0));
        if (this._cssLayers && c.layer) c.layer.style.display = visible ? 'block' : 'none';
        if (!visible || !c.layer) return;
        if (c.layer.width !== w) c.layer.width = w; if (c.layer.height !== h) c.layer.height = h;
        const x = c.layer.getContext('2d'); if (!x) return;
        // Build one opaque picture before applying this clip's opacity, filter,
        // and blend. Applying them per primitive changes the intended result.
        x.save(); x.setTransform(1, 0, 0, 1, 0, 0); x.filter = 'none'; x.globalAlpha = 1; x.globalCompositeOperation = 'source-over';
        x.clearRect(0, 0, w, h); this._picture(x, c, w, h); x.restore();
        const blend = hasPicture ? c.settings.blend : 'normal'; hasPicture = true;
        if (this._cssLayers) {
          c.layer.style.filter = filterCSS(c.settings); c.layer.style.opacity = String(c.settings.opacity * c.video.presence);
          c.layer.style.mixBlendMode = blend;
        } else if (this.ctx) {
          this.ctx.save(); this.ctx.filter = filterCSS(c.settings); this.ctx.globalAlpha = c.settings.opacity * c.video.presence;
          this.ctx.globalCompositeOperation = blend === 'normal' ? 'source-over' : blend;
          this.ctx.drawImage(c.layer, 0, 0); this.ctx.restore();
        }
      });
    }
    snapshot() {
      return { playing: this.playing, time: this.time, volume: this.volume, muted: this.muted, sequence: { ...this.sequence }, transport: { ...this.transport },
        capabilities: { canvasFilters: this._canvasFilters, cssPictureFilters: this._cssLayers, combType: 'finite-feed-forward' },
        clips: this.clips.map(c => ({ id: c.id, name: c.name, kind: c.kind, active: c.active, settings: { ...c.settings }, age: c.age, error: c.error,
          capabilities: { ...c.capabilities }, video: { ...c.video, duration: c.videoDuration || 0 }, audio: { ...c.audio, duration: c.audioDuration || 0, combHz: Model.combFrequency(this.time, c.settings, c.combPhase) } })) };
    }
    _release(c) {
      if (c.removed) return; c.removed = true; c.generation++; this._stopBuffer(c);
      [[c.videoElement, c._videoEnded], [c.audioElement, c._audioEnded]].forEach(([media, ended]) => {
        if (!media) return; safePause(media); if (ended) media.removeEventListener('ended', ended); media.removeAttribute('src'); try { media.load(); } catch (_) {}
      });
      if (c.videoElement && c._pictureReady) {
        c.videoElement.removeEventListener('seeked', c._pictureReady); c.videoElement.removeEventListener('loadeddata', c._pictureReady);
      }
      if (c.mediaSource) { try { c.mediaSource.disconnect(); } catch (_) {} }
      if (c.graph) c.graph.dispose(); if (c.headroom) { try { c.headroom.disconnect(); } catch (_) {} }
      if (c.layer) c.layer.remove(); if (c.source.ownedURL && c.source.url && root.URL) root.URL.revokeObjectURL(c.source.url);
    }
    dispose() {
      if (this.disposed) return; this.pause(); this.disposed = true;
      this.clips.forEach(c => this._release(c)); this.clips.length = 0;
      if (root.document) root.document.removeEventListener('visibilitychange', this._visibility);
      if (this.master) this.master.dispose(); if (this.context && this.context.state !== 'closed') this.context.close().catch(() => {});
    }
  }
  return { Engine, createVoiceGraph };
});
