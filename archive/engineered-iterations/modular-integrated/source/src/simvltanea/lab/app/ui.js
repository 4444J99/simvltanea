// The modular-synth panel: knobs, switches, selectors, module cards, patch bank.
import { MODULES, PARAMS, paramsOf, byId, rangeText, parseList, randomizeValues, encodeShare, sanitizeConfig, LFO_SHAPES, MOD_DEFAULT } from './params.js';
import { PRESETS, applyPreset } from './presets.js';
import { mulberry32 } from './engine.js';

const NS = 'http://www.w3.org/2000/svg';
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const h = (tag, cls, attrs = {}, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
};
const pretty = (s) => String(s).replace(/_/g, ' ');
const decimals = (step) => (String(step).split('.')[1] || '').length;

// ---- knob ------------------------------------------------------------------------------------
const A0 = -135, A1 = 135;
const polar = (a, r) => { const t = ((a - 90) * Math.PI) / 180; return [26 + r * Math.cos(t), 26 + r * Math.sin(t)]; };
function arc(a0, a1, r) {
  if (Math.abs(a1 - a0) < 0.01) return '';
  const [x0, y0] = polar(a0, r), [x1, y1] = polar(a1, r);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${Math.abs(a1 - a0) > 180 ? 1 : 0} ${a1 > a0 ? 1 : 0} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

// spec: {id,label,min,max,step,unit,type,description}; get()/set(v) bind it to the store.
export function createKnob(spec, get, set, { small = false } = {}) {
  const wrap = h('div', 'ctl knob' + (small ? ' small' : ''), { 'data-param': spec.id });
  const dial = h('div', 'dial', { role: 'slider', tabindex: '0', 'aria-label': spec.label, 'aria-valuemin': spec.min, 'aria-valuemax': spec.max });
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 52 52'); svg.setAttribute('aria-hidden', 'true');
  const mk = (cls, d) => { const p = document.createElementNS(NS, 'path'); p.setAttribute('class', cls); if (d) p.setAttribute('d', d); svg.append(p); return p; };
  mk('trk', arc(A0, A1, 20));
  const val = mk('arcv'), eff = mk('arce');
  const body = document.createElementNS(NS, 'circle'); body.setAttribute('cx', 26); body.setAttribute('cy', 26); body.setAttribute('r', 14); body.setAttribute('class', 'cap'); svg.append(body);
  const ptr = document.createElementNS(NS, 'line'); ptr.setAttribute('class', 'ptr'); svg.append(ptr);
  dial.append(svg);
  const out = h('output', 'val', { 'aria-hidden': 'true' });
  const lab = h('label', 'lbl', {}, spec.label);
  wrap.append(dial, out, lab);
  const dec = decimals(spec.step);
  const bipolar = spec.min < 0 && spec.max > 0;
  const norm = (v) => (v - spec.min) / (spec.max - spec.min);
  const ang = (v) => A0 + (A1 - A0) * clamp(norm(v), 0, 1);
  const fmt = (v) => Number(v).toFixed(dec);
  const text = (v) => `${fmt(v)}${spec.unit ? ' ' + spec.unit : ''}`;

  function render() {
    const v = get();
    const a = ang(v), a0 = bipolar ? ang(0) : A0;
    val.setAttribute('d', arc(Math.min(a0, a), Math.max(a0, a), 20));
    const [x0, y0] = polar(a, 6), [x1, y1] = polar(a, 20);
    ptr.setAttribute('x1', x0); ptr.setAttribute('y1', y0); ptr.setAttribute('x2', x1); ptr.setAttribute('y2', y1);
    dial.setAttribute('aria-valuenow', v); dial.setAttribute('aria-valuetext', text(v));
    if (!wrap.classList.contains('editing')) out.textContent = text(v);
    dial.dataset.value = String(v);
  }
  wrap.update = render;
  wrap.setEff = (v) => {
    if (v === null) { eff.removeAttribute('d'); return; }
    const a = ang(v);
    eff.setAttribute('d', arc(Math.max(A0, a - 4), Math.min(A1, a + 4), 24));
  };
  const commit = (v) => { set(v); render(); };
  const stepBy = (n) => commit(clamp(Number(get()) + n * spec.step, spec.min, spec.max));

  let drag = null;
  dial.addEventListener('pointerdown', (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    dial.setPointerCapture(e.pointerId);
    drag = { y: e.clientY, x: e.clientX, n: norm(get()) };
    dial.focus(); e.preventDefault(); wrap.classList.add('dragging');
  });
  dial.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const sens = e.shiftKey ? 900 : 180;
    const n = clamp(drag.n + ((drag.y - e.clientY) + (e.clientX - drag.x) * 0.25) / sens, 0, 1);
    commit(spec.min + n * (spec.max - spec.min));
  });
  const end = (e) => { if (drag) { drag = null; wrap.classList.remove('dragging'); try { dial.releasePointerCapture(e.pointerId); } catch { /* released */ } } };
  dial.addEventListener('pointerup', end); dial.addEventListener('pointercancel', end);
  dial.addEventListener('wheel', (e) => { e.preventDefault(); stepBy(e.deltaY < 0 ? (e.shiftKey ? 0.2 : 1) : (e.shiftKey ? -0.2 : -1)); }, { passive: false });
  dial.addEventListener('keydown', (e) => {
    const big = e.shiftKey ? 10 : 1;
    switch (e.key) {
      case 'ArrowUp': case 'ArrowRight': stepBy(big); break;
      case 'ArrowDown': case 'ArrowLeft': stepBy(-big); break;
      case 'PageUp': stepBy(Math.max(1, Math.round((spec.max - spec.min) / spec.step / 10))); break;
      case 'PageDown': stepBy(-Math.max(1, Math.round((spec.max - spec.min) / spec.step / 10))); break;
      case 'Home': commit(spec.min); break;
      case 'End': commit(spec.max); break;
      case 'Enter': startEdit(); break;
      default: return;
    }
    e.preventDefault();
  });

  function startEdit() {
    if (wrap.classList.contains('editing')) return;
    wrap.classList.add('editing');
    const input = h('input', 'val-edit', { type: 'text', inputmode: 'decimal', 'aria-label': `${spec.label} value` });
    input.value = fmt(get());
    out.textContent = ''; out.append(input);
    input.focus(); input.select();
    let done = false;
    const finish = (ok) => {
      if (done) return; done = true;
      if (ok) { const n = Number(input.value.replace(',', '.')); if (Number.isFinite(n)) set(clamp(n, spec.min, spec.max)); }
      wrap.classList.remove('editing'); out.textContent = ''; render(); dial.focus();
    };
    input.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
    input.addEventListener('blur', () => finish(true));
  }
  dial.addEventListener('dblclick', startEdit);
  out.addEventListener('dblclick', startEdit);
  render();
  return wrap;
}

// ---- other controls --------------------------------------------------------------------------
function tooltip(p) {
  return `${p.label}: ${p.description} [${rangeText(p)}${p.unit ? ' ' + p.unit : ''}; default ${Array.isArray(p.default) ? '[' + p.default.join(', ') + ']' : p.default}]`;
}

function makeControl(p, store) {
  let ctl;
  const set = (v) => store.set(p.id, v);
  if (p.type === 'float' || (p.type === 'int' && p.max - p.min <= 1000)) {
    ctl = createKnob(p, () => store.get(p.id), set);
    if (p.modulatable) {
      const modBtn = h('button', 'modbtn', { type: 'button', 'aria-pressed': 'false', 'aria-label': `Modulate ${p.label} with an LFO`, title: 'MOD: assign an LFO' }, 'MOD');
      const row = h('div', 'modrow'); row.hidden = true;
      const sel = h('select', 'sel mini', { 'aria-label': `${p.label} LFO shape` });
      for (const s of LFO_SHAPES) sel.append(h('option', '', { value: s }, s === 'random' ? 'random walk' : s));
      const mod = () => store.cfg.mods[p.id] || MOD_DEFAULT;
      const rate = createKnob({ id: p.id + '~rate', label: 'rate', min: 0.01, max: 5, step: 0.01, unit: 'Hz' }, () => mod().rate, (v) => store.mod(p.id, { rate: v }), { small: true });
      const depth = createKnob({ id: p.id + '~depth', label: 'depth', min: 0, max: 1, step: 0.01, unit: '' }, () => mod().depth, (v) => store.mod(p.id, { depth: v }), { small: true });
      row.append(sel, rate, depth);
      modBtn.addEventListener('click', () => store.mod(p.id, { on: !mod().on }));
      sel.addEventListener('change', () => store.mod(p.id, { shape: sel.value }));
      ctl.append(modBtn); ctl.modRow = row;
      const upd = ctl.update;
      ctl.update = () => {
        upd();
        const m = mod();
        modBtn.setAttribute('aria-pressed', String(!!m.on)); ctl.classList.toggle('modded', !!m.on);
        row.hidden = !m.on; sel.value = m.shape; rate.update(); depth.update();
        if (!m.on) ctl.setEff(null);
      };
    }
  } else if (p.type === 'int') {
    ctl = h('div', 'ctl numeric wide', { 'data-param': p.id });
    const lab = h('label', 'lbl', {}, p.label);
    const input = h('input', 'num', { type: 'number', min: p.min, max: p.max, step: p.step });
    const id = 'in-' + p.id.replace(/\./g, '-'); input.id = id; lab.htmlFor = id;
    input.addEventListener('change', () => { if (!store.set(p.id, input.value)) ctl.update(); });
    ctl.append(lab, input);
    if (p.id === 'source.seed') {
      const dice = h('button', 'btn small', { type: 'button', 'aria-label': 'Random seed' }, 'dice');
      dice.addEventListener('click', () => store.set(p.id, 1 + Math.floor(Math.random() * 999998)));
      ctl.append(dice);
    }
    ctl.update = () => { input.value = store.get(p.id); };
  } else if (p.type === 'enum') {
    ctl = h('div', 'ctl select wide', { 'data-param': p.id });
    const lab = h('label', 'lbl', {}, p.label);
    const sel = h('select', 'sel', {});
    const id = 'in-' + p.id.replace(/\./g, '-'); sel.id = id; lab.htmlFor = id;
    for (const o of p.options) sel.append(h('option', '', { value: o }, pretty(o)));
    sel.addEventListener('change', () => set(sel.value));
    ctl.append(lab, sel);
    ctl.update = () => { sel.value = store.get(p.id); };
  } else if (p.type === 'bool') {
    ctl = h('div', 'ctl switch', { 'data-param': p.id });
    const b = h('button', 'sw', { type: 'button', role: 'switch', 'aria-checked': 'false', 'aria-label': p.label });
    b.append(h('span', 'knob-sw'));
    const lab = h('span', 'lbl', {}, p.label);
    lab.addEventListener('click', () => b.click());
    b.addEventListener('click', () => set(!store.get(p.id)));
    ctl.append(b, lab);
    ctl.update = () => b.setAttribute('aria-checked', String(!!store.get(p.id)));
  } else if (p.type === 'multi') {
    ctl = h('div', 'ctl multi wide', { 'data-param': p.id, role: 'group', 'aria-label': p.label });
    ctl.append(h('span', 'lbl', {}, p.label));
    const chips = h('div', 'chips');
    const btns = p.options.map((o) => {
      const b = h('button', 'chip-btn', { type: 'button', role: 'checkbox', 'aria-checked': 'false', 'data-option': String(o) }, pretty(o));
      b.setAttribute('aria-label', `${p.label}: ${pretty(o)}`);
      b.addEventListener('click', () => { const cur = new Set(store.get(p.id)); cur.has(o) ? cur.delete(o) : cur.add(o); set([...cur]); });
      chips.append(b);
      return [o, b];
    });
    ctl.append(chips);
    ctl.update = () => { const cur = new Set(store.get(p.id)); for (const [o, b] of btns) b.setAttribute('aria-checked', String(cur.has(o))); };
  } else {
    ctl = h('div', 'ctl list wide', { 'data-param': p.id });
    const lab = h('label', 'lbl', {}, p.label);
    const input = h('input', 'txt', { type: 'text', spellcheck: 'false', placeholder: p.item === 'number' ? '3, 2, 1' : 'tree, sky' });
    const id = 'in-' + p.id.replace(/\./g, '-'); input.id = id; lab.htmlFor = id;
    const commit = () => { set(parseList(input.value, p.item)); ctl.update(); };
    input.addEventListener('change', commit);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') commit(); });
    ctl.append(lab, input);
    ctl.update = () => { input.value = store.get(p.id).join(', '); };
  }
  ctl.title = tooltip(p);
  ctl.dataset.type = p.type;
  if (p.randomizable) {
    const lock = h('button', 'lockbtn', { type: 'button', 'aria-pressed': 'false', 'aria-label': `Lock ${p.label} against randomize`, title: 'Lock against RANDOMIZE' }, 'LOCK');
    lock.addEventListener('click', () => store.lock(p.id, !store.cfg.locks.includes(p.id)));
    ctl.append(lock);
    const upd = ctl.update;
    ctl.update = () => { upd(); const l = store.cfg.locks.includes(p.id); lock.setAttribute('aria-pressed', String(l)); ctl.classList.toggle('locked', l); };
  }
  return ctl;
}

// ---- module cards ----------------------------------------------------------------------------
function buildModule(m, store, controls) {
  const card = h('section', 'module', { 'data-module': m.id });
  const head = h('header', 'mod-head');
  const title = h('button', 'mod-title', { type: 'button', 'aria-expanded': 'true', 'aria-controls': `body-${m.id}` });
  title.append(h('span', 'chev', {}, '\u25be'), h('span', 'ttl', {}, m.label));
  title.title = m.blurb;
  const byp = h('button', 'mini-btn byp', { type: 'button', role: 'switch', 'aria-checked': 'false', 'aria-label': `Bypass ${m.label}`, title: 'Bypass: use this module\'s defaults' }, 'BYP');
  const rst = h('button', 'mini-btn rst', { type: 'button', 'aria-label': `Reset ${m.label}`, title: 'Reset this module to defaults' }, 'RST');
  head.append(title, byp, rst);
  const body = h('div', 'mod-body', { id: `body-${m.id}` });
  body.append(h('p', 'blurb', {}, m.blurb));
  const grid = h('div', 'ctl-grid');
  body.append(grid);
  card.append(head, body);
  title.addEventListener('click', () => {
    const collapsed = card.classList.toggle('collapsed');
    title.setAttribute('aria-expanded', String(!collapsed));
    body.hidden = collapsed;
  });
  byp.addEventListener('click', () => store.bypass(m.id, !store.cfg.bypass.includes(m.id)));
  rst.addEventListener('click', () => store.resetModule(m.id));
  for (const p of paramsOf(m.id)) {
    const c = makeControl(p, store);
    controls.set(p.id, c);
    grid.append(c);
    if (c.modRow) grid.append(c.modRow);
  }
  card.syncBypass = () => {
    const on = store.cfg.bypass.includes(m.id);
    byp.setAttribute('aria-checked', String(on)); card.classList.toggle('bypassed', on);
  };
  return { card, body, grid };
}

// ---- patch bank ------------------------------------------------------------------------------
const BANK_KEY = 'lab.patches.v1';
export const bank = {
  all() { try { return JSON.parse(localStorage.getItem(BANK_KEY)) || {}; } catch { return {}; } },
  save(name, cfg) { const b = this.all(); b[name] = { app: 'lab', version: 1, name, config: cfg }; localStorage.setItem(BANK_KEY, JSON.stringify(b)); },
  remove(name) { const b = this.all(); delete b[name]; localStorage.setItem(BANK_KEY, JSON.stringify(b)); },
};

export function parsePatchText(text) {
  const j = JSON.parse(text);
  const cfg = j && typeof j === 'object' && j.config ? j.config : j;
  if (!cfg || typeof cfg !== 'object' || Array.isArray(cfg) || !cfg.values || typeof cfg.values !== 'object' || Array.isArray(cfg.values)) throw new Error('not a lab patch');
  return { name: typeof j.name === 'string' ? j.name : '', config: sanitizeConfig(cfg) };
}

// ---- assembly --------------------------------------------------------------------------------
export function initUI({ store, player, rack, modulesEl, toast }) {
  const controls = new Map();
  const cards = new Map();
  const say = (msg) => { toast.textContent = msg; toast.classList.add('show'); clearTimeout(say.t); say.t = setTimeout(() => toast.classList.remove('show'), 2600); };

  // PATCH card
  const pc = h('section', 'module patch', { 'data-module': 'patch' });
  const phead = h('header', 'mod-head');
  const ptitle = h('button', 'mod-title', { type: 'button', 'aria-expanded': 'true', 'aria-controls': 'body-patch' });
  ptitle.append(h('span', 'chev', {}, '\u25be'), h('span', 'ttl', {}, 'PATCH'));
  phead.append(ptitle);
  const pbody = h('div', 'mod-body', { id: 'body-patch' });
  ptitle.addEventListener('click', () => { const c = pc.classList.toggle('collapsed'); ptitle.setAttribute('aria-expanded', String(!c)); pbody.hidden = c; });
  pc.append(phead, pbody);

  const row = (cls) => { const r = h('div', 'prow ' + (cls || '')); pbody.append(r); return r; };
  const btn = (id, text, aria, cls = 'btn') => h('button', cls, { type: 'button', id, ...(aria ? { 'aria-label': aria } : {}) }, text);

  const r1 = row();
  const presetLabel = h('label', 'lbl', { for: 'preset-select' }, 'Preset');
  const presetSel = h('select', 'sel', { id: 'preset-select' });
  presetSel.append(h('option', '', { value: '' }, 'custom'));
  for (const [kind, label] of [['preset', 'How it plays'], ['scene', 'Scenes']]) {
    const og = h('optgroup', '', { label });
    for (const p of PRESETS.filter((x) => x.kind === kind)) og.append(h('option', '', { value: p.id, title: p.description }, p.label));
    presetSel.append(og);
  }
  r1.append(presetLabel, presetSel);
  const presetDesc = h('p', 'blurb', { id: 'preset-desc' }); pbody.append(presetDesc);
  presetSel.addEventListener('change', () => {
    const pr = PRESETS.find((p) => p.id === presetSel.value);
    if (!pr) return;
    store.setMany(applyPreset(store.cfg.values, pr));
    presetSel.value = pr.id; presetDesc.textContent = pr.description;
    say(`Preset: ${pr.label}`);
  });

  const r2 = row('transport');
  const bSound = btn('btn-sound', 'Sound: off', 'Start sound');
  const bPause = btn('btn-pause', 'Pause', 'Pause or resume (Space)');
  const bShuffle = btn('btn-shuffle', 'Reshuffle', 'Re-seed and pick everything again');
  r2.append(bSound, bPause, bShuffle);
  bSound.addEventListener('click', () => start());
  bPause.addEventListener('click', () => player.togglePause());
  bShuffle.addEventListener('click', () => { player.reshuffle(); player.sched.reset(player.t); say(`New seed ${player.seed}`); });
  async function start() { const ok = await player.startAudio(); say(ok ? 'Sound on' : 'Web Audio is not available'); }

  const r3 = row();
  const nameLabel = h('label', 'lbl', { for: 'patch-name' }, 'Patch');
  const name = h('input', 'txt', { id: 'patch-name', type: 'text', placeholder: 'name', maxlength: '40' });
  const bSave = btn('patch-save', 'Save');
  r3.append(nameLabel, name, bSave);
  const r4 = row();
  const list = h('select', 'sel', { id: 'patch-list', 'aria-label': 'Saved patches' });
  const bLoad = btn('patch-load', 'Load'), bDel = btn('patch-delete', 'Delete');
  r4.append(list, bLoad, bDel);
  const refreshList = () => {
    const b = bank.all(); list.textContent = '';
    list.append(h('option', '', { value: '' }, Object.keys(b).length ? 'saved patches...' : '(none saved)'));
    for (const n of Object.keys(b).sort()) list.append(h('option', '', { value: n }, n));
  };
  bSave.addEventListener('click', () => {
    const n = name.value.trim();
    if (!n) { say('Give the patch a name first'); name.focus(); return; }
    bank.save(n, store.snapshot()); refreshList(); list.value = n; say(`Saved "${n}"`);
  });
  bLoad.addEventListener('click', () => {
    const n = list.value, p = bank.all()[n];
    if (!p) { say('Pick a saved patch'); return; }
    store.load(p.config); name.value = n; say(`Loaded "${n}"`);
  });
  bDel.addEventListener('click', () => { const n = list.value; if (n) { bank.remove(n); refreshList(); say(`Deleted "${n}"`); } });

  const r5 = row();
  const bExport = btn('patch-export', 'Export JSON');
  const importId = 'patch-import';
  const importLabel = h('label', 'btn', { for: importId }, 'Import JSON');
  const importIn = h('input', 'file', { id: importId, type: 'file', accept: '.json,application/json' });
  r5.append(bExport, importLabel, importIn);
  bExport.addEventListener('click', () => {
    const nm = name.value.trim() || 'patch';
    const blob = new Blob([JSON.stringify({ app: 'lab', version: 1, name: nm, config: store.snapshot() }, null, 1)], { type: 'application/json' });
    const a = h('a', '', { href: URL.createObjectURL(blob), download: `${nm.replace(/[^\w-]+/g, '_')}.lab.json` });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    say('Exported');
  });
  importIn.addEventListener('change', async () => {
    const f = importIn.files[0]; if (!f) return;
    try { const { name: n, config } = parsePatchText(await f.text()); store.load(config); if (n) name.value = n; say(`Imported ${n || f.name}`); }
    catch (err) { say(`Import failed: ${err.message}`); }
    importIn.value = '';
  });

  const r6 = row();
  const bShare = btn('patch-share', 'Copy share URL');
  const shareUrl = h('input', 'txt', { id: 'share-url', type: 'text', readonly: '', 'aria-label': 'Share URL' });
  r6.append(bShare, shareUrl);
  const makeShare = () => `${location.origin}${location.pathname}${location.search}#${encodeShare(store.cfg)}`;
  bShare.addEventListener('click', async () => {
    shareUrl.value = makeShare();
    try { await navigator.clipboard.writeText(shareUrl.value); say('Share URL copied'); } catch { shareUrl.select(); say('Share URL ready: copy it from the box'); }
  });

  const r7 = row();
  const bRand = btn('btn-randomize', 'Randomize', 'Randomize unlocked parameters within their ranges');
  const bResetAll = btn('btn-reset-all', 'Reset all');
  r7.append(bRand, bResetAll);
  bRand.addEventListener('click', () => {
    store.setMany(randomizeValues(store.cfg.values, store.cfg.locks, mulberry32((Date.now() ^ Math.floor(Math.random() * 1e9)) >>> 0)));
    presetSel.value = ''; presetDesc.textContent = '';
    say('Randomized (locked and SOURCE/limiter/speech-policy controls untouched)');
  });
  bResetAll.addEventListener('click', () => { store.resetAll(); presetSel.value = ''; presetDesc.textContent = ''; say('Reset all'); });
  pbody.append(h('p', 'blurb keys', {}, 'Keys: H hide panel \u00b7 Space pause \u00b7 Enter on a panel reveals \u00b7 Esc closes'));

  modulesEl.append(pc);
  for (const m of MODULES) {
    const { card, body } = buildModule(m, store, controls);
    cards.set(m.id, card);
    modulesEl.append(card);
    if (m.id === 'zoom') { const o = h('output', 'readout', { id: 'zoom-readout', role: 'status', 'aria-live': 'off' }); body.insertBefore(o, body.children[1]); }
    if (m.id === 'framing') { const o = h('output', 'readout', { id: 'framing-readout', role: 'status', 'aria-live': 'off' }); body.insertBefore(o, body.children[1]); }
    if (m.id === 'audio') { const mx = h('div', 'mixer', { id: 'mixer', 'aria-label': 'Panel levels' }); body.insertBefore(mx, body.children[1]); }
  }
  const zoomOut = modulesEl.querySelector('#zoom-readout');
  const framingOut = modulesEl.querySelector('#framing-readout');
  const mixer = modulesEl.querySelector('#mixer');

  const updateAll = () => {
    for (const c of controls.values()) c.update();
    for (const c of cards.values()) c.syncBypass();
  };
  store.on((ev) => {
    if (ev.type === 'param') {
      controls.get(ev.id)?.update();
      if (['order', 'path', 'relation', 'timing'].includes(ev.module)) { presetSel.value = ''; presetDesc.textContent = ''; }
    } else if (ev.type === 'lock' || ev.type === 'mod') controls.get(ev.id)?.update();
    else updateAll();
  });
  updateAll(); refreshList();

  // live readouts
  let mixN = -1;
  player.on((ev) => {
    if (ev.type === 'audio') { bSound.textContent = 'Sound: on'; bSound.setAttribute('aria-pressed', 'true'); }
    if (ev.type === 'transport') { bPause.textContent = player.paused ? 'Play' : 'Pause'; bPause.setAttribute('aria-pressed', String(player.paused)); }
    if (ev.type !== 'frame') return;
    const z = player.zoomInfo;
    if (z && zoomOut) zoomOut.textContent = `zoom ${z.zoom.toFixed(2)}\u00d7, ${(z.share * 100).toFixed(z.share < 0.1 ? 2 : 1)}% of the clip visible`;
    if (framingOut && player.frameNo % 12 === 0) {
      const fr = player.framingState().filter((x) => x.window);
      const mm = fr.map((x) => x.edgeMismatch).filter((x) => x !== null);
      const modes = [...new Set(fr.map((x) => x.mode))].join('/');
      framingOut.textContent = fr.length ? `${fr.length} windows (${modes}); mean edge mismatch with the neighbour ${mm.length ? (mm.reduce((a, b) => a + b, 0) / mm.length).toFixed(3) : 'n/a'}` : '';
    }
    const n = player.panels.length;
    if (mixer) {
      if (mixN !== n) { mixer.textContent = ''; for (let i = 0; i < n; i++) { const b = h('span', 'vu-mini', { 'data-panel': String(i) }); b.append(h('i')); mixer.append(b); } mixN = n; }
      for (let i = 0; i < n; i++) mixer.children[i].firstChild.style.transform = `scaleY(${(player.levels[i] || 0).toFixed(3)})`;
    }
    for (const [id, c] of controls) {
      if (!c.setEff) continue;
      const m = store.cfg.mods[id];
      if (m && m.on && !store.cfg.bypass.includes(byId[id].module)) c.setEff(player.eff[id]); else c.setEff(null);
    }
  });

  // rack chrome
  const dockBtns = [...rack.querySelectorAll('[data-dock-set]')];
  const setDock = (d) => { rack.dataset.dock = d; dockBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.dockSet === d))); try { localStorage.setItem('lab.dock', d); } catch { /* storage off */ } };
  dockBtns.forEach((b) => b.addEventListener('click', () => setDock(b.dataset.dockSet)));
  let savedDock = 'right'; try { savedDock = localStorage.getItem('lab.dock') || 'right'; } catch { /* storage off */ }
  setDock(['left', 'right', 'bottom'].includes(savedDock) ? savedDock : 'right');
  rack.querySelector('#rack-collapse').addEventListener('click', () => {
    const all = [...modulesEl.querySelectorAll('.module')];
    const anyOpen = all.some((c) => !c.classList.contains('collapsed'));
    for (const c of all) { c.classList.toggle('collapsed', anyOpen); c.querySelector('.mod-title').setAttribute('aria-expanded', String(!anyOpen)); c.querySelector('.mod-body').hidden = anyOpen; }
  });
  return { say, start, controls, updateAll };
}
