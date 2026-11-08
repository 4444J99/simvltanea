import { Store } from './store.js';
import { Player } from './player.js';
import { initUI } from './ui.js';
import { decodeShare, defaultConfig } from './params.js';

const $ = (id) => document.getElementById(id);
const q = new URLSearchParams(location.search);
let base = q.get('data') || './';
if (!base.endsWith('/')) base += '/';

const store = new Store(decodeShare(location.hash) || defaultConfig());
const player = new Player({ stage: $('stage'), store, revealRoot: $('reveal-root'), base });
const ui = initUI({ store, player, rack: $('rack'), modulesEl: $('rack-modules'), toast: $('toast') });

const msg = $('message');
const fail = (err) => { msg.hidden = false; msg.textContent = `Could not load the clips: ${err.message}`; console.warn('lab:', err.message); };
player.load().then((n) => {
  if (n === 0) fail(new Error('clips.json contains no usable clips'));
  window.__labReady = true;
}).catch(fail);

// ---- start overlay, chrome ----
$('start-btn').addEventListener('click', async () => { await ui.start(); $('start').hidden = true; });
player.on((ev) => { if (ev.type === 'audio') $('start').hidden = true; });
const body = document.body;
const hideUI = (on) => body.classList.toggle('ui-hidden', on);
$('rack-hide').addEventListener('click', () => hideUI(true));
$('ui-restore').addEventListener('click', () => hideUI(false));
$('ui-fab').addEventListener('click', () => {
  const open = body.classList.toggle('rack-open');
  $('ui-fab').setAttribute('aria-expanded', String(open));
});

// ---- keyboard ----
const NATIVE = 'input, select, textarea, button, [role=switch], [role=checkbox]';
document.addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  const typing = t instanceof Element && t.matches('input:not([type=file]), textarea, select');
  if (e.key === 'Escape') {
    if (player.reveal) { e.preventDefault(); player.closeReveal(); }
    return;
  }
  if (typing) return;
  if (e.key === 'h' || e.key === 'H') { e.preventDefault(); hideUI(!body.classList.contains('ui-hidden')); return; }
  if (e.key === ' ' || e.code === 'Space') {
    if (t instanceof Element && t.matches(NATIVE)) return; // let switches/buttons use Space natively
    e.preventDefault();
    player.togglePause();
  }
});

// ---- debug API for tests ----
const dbg = player.debug();
window.__lab = {
  params: () => JSON.parse(JSON.stringify(store.cfg.values)),
  effective: () => ({ ...player.eff }),
  set: (id, value) => store.set(id, value),
  config: () => store.snapshot(),
  engine: dbg.engine, scheduled: dbg.scheduled, layoutRects: dbg.layoutRects, audio: dbg.audio, seed: dbg.seed,
  axis: dbg.axis, zoomInfo: dbg.zoomInfo, reveal: dbg.reveal, paused: dbg.paused, pool: dbg.pool, reduced: dbg.reduced,
  records: dbg.records, audioStarted: dbg.audioStarted, framing: dbg.framing,
  store, player,
};
