// FRAMING: derives, for every appearance of a clip, the window (sub-rectangle of the clip) a strip
// shows. Pure, seeded and deterministic: no DOM, no clocks, no Math.random.
//
// A window is {cx, cy, zoom} in normalised source coordinates (0..1 on both axes). It keeps the
// cell's aspect ratio: at zoom 1 it is the largest cell-shaped rectangle inside the source ("cover"),
// at zoom z it is 1/z of that. Windows are always clamped to lie inside the source and zoom is never
// below `minZoom` (>= 1), so a strip can never show empty space.
import { mulberry32, hashString } from './engine.js';
import { coverScale } from './layout.js';

export const MODES = ['center', 'random', 'thirds', 'detail', 'blend', 'contrast', 'drift'];
export const MAX_ZOOM = 64;
export const MEMORY_TOL = 0.08;      // two windows closer than this (relative to their size) count as the same
const HISTORY_CAP = 64;

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;

// ---- window geometry -----------------------------------------------------------------------
export function coverFraction(srcAspect, cellAspect) {
  return { w: Math.min(1, cellAspect / srcAspect), h: Math.min(1, srcAspect / cellAspect) };
}
export function windowSize(zoom, srcAspect, cellAspect) {
  const c = coverFraction(srcAspect, cellAspect);
  return { w: c.w / zoom, h: c.h / zoom };
}
// Clamp into the legal set: zoom in [minZoom, MAX_ZOOM], centre such that the window is inside the source.
export function clampWindow(win, srcAspect, cellAspect, minZoom = 1) {
  const lo = Math.max(1, Number.isFinite(minZoom) ? minZoom : 1);
  const zoom = clamp(Number.isFinite(win.zoom) ? win.zoom : lo, lo, Math.max(lo, MAX_ZOOM));
  const { w, h } = windowSize(zoom, srcAspect, cellAspect);
  const cx = clamp(Number.isFinite(win.cx) ? win.cx : 0.5, w / 2, 1 - w / 2);
  const cy = clamp(Number.isFinite(win.cy) ? win.cy : 0.5, h / 2, 1 - h / 2);
  return { ...win, cx, cy, zoom };
}
export function windowRect(win, srcAspect, cellAspect) {
  const { w, h } = windowSize(win.zoom, srcAspect, cellAspect);
  return { x0: win.cx - w / 2, y0: win.cy - h / 2, x1: win.cx + w / 2, y1: win.cy + h / 2, w, h };
}
// The visible window implied by a rendered fit (layout.fitVideo output) for a cw x ch cell.
export function windowFromFit(fit, cw, ch) {
  const w = cw / fit.sw, h = ch / fit.sh;
  return { cx: -fit.tx / fit.sw + w / 2, cy: -fit.ty / fit.sh + h / 2, zoom: fit.zoom, x0: -fit.tx / fit.sw, y0: -fit.ty / fit.sh, x1: -fit.tx / fit.sw + w, y1: -fit.ty / fit.sh + h };
}

// Smallest zoom at which a vw x vh clip covers a cw x ch cell that also sways by up to jx / jy pixels.
export function coverZoom(vw, vh, cw, ch, jx = 0, jy = 0) {
  return Math.max(1, coverScale(vw, vh, cw + 2 * jx, ch + 2 * jy) / coverScale(vw, vh, cw, ch));
}

// What the renderer (layout.fitVideo) is given for a slot. `center` returns the zoom module's own zoom
// and focal point untouched, so it is bit-for-bit the previous behaviour. Other modes use the derived
// window; if the zoom module's focal point is wandering (focal differs from staticFocal) the window is
// nudged by that wander. The result is always clamped inside the source.
export function renderWindow({ mode, win, baseZoom, minZoom = 1, srcAspect, cellAspect, focal, staticFocal = focal, wander = true }) {
  if (mode === 'center' || !win) return { zoom: baseZoom, focal };
  const dx = wander ? focal.x - staticFocal.x : 0, dy = wander ? focal.y - staticFocal.y : 0;
  const c = clampWindow({ cx: win.cx + dx, cy: win.cy + dy, zoom: Math.max(minZoom, baseZoom * win.zf) }, srcAspect, cellAspect, minZoom);
  return { zoom: c.zoom, focal: { x: c.cx, y: c.cy } };
}

// ---- colour data ---------------------------------------------------------------------------
const HEX384 = /^[0-9a-fA-F]{384}$/;
export function parseGrid8(text) {
  if (typeof text !== 'string' || !HEX384.test(text)) return null;
  const g = new Float32Array(192);
  for (let i = 0; i < 192; i++) g[i] = parseInt(text.substr(i * 2, 2), 16) / 255;
  return g;
}
function hslToRgb(h, s, l) {
  const f = (n) => { const k = (n + h * 12) % 12; return l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
  return [f(0), f(8), f(4)];
}
const flatGrid = (rgb) => { const g = new Float32Array(192); for (let i = 0; i < 64; i++) { g[i * 3] = rgb[0]; g[i * 3 + 1] = rgb[1]; g[i * 3 + 2] = rgb[2]; } return g; };
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);

const colourCache = new WeakMap();
// {grid, kind} for a clip record: 'grid8' (real 8x8 means), else a flat grid from 'palette', 'hue' or
// 'luma', else kind 'none' (grid null: modes that need colour fall back to random).
export function colourOf(rec) {
  if (!rec || typeof rec !== 'object') return { grid: null, kind: 'none' };
  let c = colourCache.get(rec);
  if (c) return c;
  const f = rec.raw && typeof rec.raw.features === 'object' && rec.raw.features ? rec.raw.features : {};
  const g8 = parseGrid8(f.grid8);
  if (g8) c = { grid: g8, kind: 'grid8' };
  else {
    const pal = Array.isArray(f.palette) ? f.palette.filter((p) => p && typeof p.hex === 'string' && /^#?[0-9a-fA-F]{6}$/.test(p.hex.trim())) : [];
    const hue = num(f.hue), luma = num(f.luma), sat = num(f.saturation);
    if (pal.length) {
      pal.sort((a, b) => (num(b.share) || 0) - (num(a.share) || 0));
      const hx = pal[0].hex.trim().replace('#', '');
      c = { grid: flatGrid([0, 2, 4].map((i) => parseInt(hx.substr(i, 2), 16) / 255)), kind: 'palette' };
    } else if (Number.isFinite(hue)) c = { grid: flatGrid(hslToRgb(((hue % 1) + 1) % 1, Number.isFinite(sat) ? clamp(sat, 0, 1) : 0.5, Number.isFinite(luma) ? clamp(luma, 0, 1) : 0.5)), kind: 'hue' };
    else if (Number.isFinite(luma)) c = { grid: flatGrid([clamp(luma, 0, 1), clamp(luma, 0, 1), clamp(luma, 0, 1)]), kind: 'luma' };
    else c = { grid: null, kind: 'none' };
  }
  colourCache.set(rec, c);
  return c;
}

// Bilinear sample of the 8x8 grid at normalised (u, v); cell centres at (i + 0.5) / 8.
export function sampleGrid(grid, u, v, out, o = 0) {
  const gx = clamp(u * 8 - 0.5, 0, 7), gy = clamp(v * 8 - 0.5, 0, 7);
  const x0 = Math.floor(gx), y0 = Math.floor(gy), x1 = Math.min(7, x0 + 1), y1 = Math.min(7, y0 + 1);
  const fx = gx - x0, fy = gy - y0;
  for (let c = 0; c < 3; c++) {
    const a = grid[(y0 * 8 + x0) * 3 + c], b = grid[(y0 * 8 + x1) * 3 + c], d = grid[(y1 * 8 + x0) * 3 + c], e = grid[(y1 * 8 + x1) * 3 + c];
    out[o + c] = lerp(lerp(a, b, fx), lerp(d, e, fx), fy);
  }
}

// ---- edge profiles and mismatch ------------------------------------------------------------
export const EDGE_POINTS = 8;
const BAND = [1 / 6, 0.5, 5 / 6];
const _px = new Float32Array(3);
// Colours (EDGE_POINTS x rgb) along one edge of a window rect; `band` is the sampled strip width as a
// fraction of the window's size across that edge. side: left | right | top | bottom.
export function edgeProfile(grid, rect, side, band) {
  const out = new Float32Array(EDGE_POINTS * 3);
  for (let i = 0; i < EDGE_POINTS; i++) {
    const f = (i + 0.5) / EDGE_POINTS;
    let r = 0, g = 0, b = 0;
    for (const t of BAND) {
      let u, v;
      if (side === 'left') { u = rect.x0 + band * rect.w * t; v = rect.y0 + f * rect.h; }
      else if (side === 'right') { u = rect.x1 - band * rect.w * t; v = rect.y0 + f * rect.h; }
      else if (side === 'top') { u = rect.x0 + f * rect.w; v = rect.y0 + band * rect.h * t; }
      else { u = rect.x0 + f * rect.w; v = rect.y1 - band * rect.h * t; }
      sampleGrid(grid, u, v, _px);
      r += _px[0]; g += _px[1]; b += _px[2];
    }
    out[i * 3] = r / BAND.length; out[i * 3 + 1] = g / BAND.length; out[i * 3 + 2] = b / BAND.length;
  }
  return out;
}

const luma709 = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
function hueSat(r, g, b) {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  if (d < 1e-6) return [0, 0];
  let h;
  if (mx === r) h = ((g - b) / d + 6) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4;
  return [h / 6, mx === 0 ? 0 : d / mx];
}
function colourDistance(a, i, b, j, matchOn) {
  if (matchOn === 'luma') return Math.abs(luma709(a[i], a[i + 1], a[i + 2]) - luma709(b[j], b[j + 1], b[j + 2]));
  if (matchOn === 'hue') {
    const [h1, s1] = hueSat(a[i], a[i + 1], a[i + 2]), [h2, s2] = hueSat(b[j], b[j + 1], b[j + 2]);
    const d = Math.abs(h1 - h2);
    return 2 * Math.min(d, 1 - d) * Math.min(s1, s2);
  }
  return Math.hypot(a[i] - b[j], a[i + 1] - b[j + 1], a[i + 2] - b[j + 2]) / Math.sqrt(3);
}
// Mean colour distance (0..1) between two edge profiles of equal length.
export function profileMismatch(pa, pb, matchOn = 'colour') {
  let s = 0;
  for (let i = 0; i < EDGE_POINTS; i++) s += colourDistance(pa, i * 3, pb, i * 3, matchOn);
  return s / EDGE_POINTS;
}

// The facing edges of two panels, A before B along the strip axis: A's trailing edge against B's leading edge.
// a / b: {win, grid, srcAspect, cellAspect}. Returns the mean mismatch (0 = identical colours).
export function edgeMismatch(a, b, { axis = 'columns', matchOn = 'colour', band = 0.1 } = {}) {
  const [sa, sb] = axis === 'rows' ? ['bottom', 'top'] : ['right', 'left'];
  const pa = edgeProfile(a.grid, windowRect(a.win, a.srcAspect, a.cellAspect), sa, band);
  const pb = edgeProfile(b.grid, windowRect(b.win, b.srcAspect, b.cellAspect), sb, band);
  return profileMismatch(pa, pb, matchOn);
}

// Local colour variance inside a window (sum of per-channel variances over a 6 x 6 lattice).
export function windowVariance(grid, rect) {
  const n = 6, px = new Float32Array(n * n * 3);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) sampleGrid(grid, rect.x0 + (i + 0.5) / n * rect.w, rect.y0 + (j + 0.5) / n * rect.h, px, (j * n + i) * 3);
  let v = 0;
  for (let c = 0; c < 3; c++) {
    let m = 0; for (let k = 0; k < n * n; k++) m += px[k * 3 + c];
    m /= n * n;
    let s = 0; for (let k = 0; k < n * n; k++) s += (px[k * 3 + c] - m) ** 2;
    v += s / (n * n);
  }
  return v;
}

// ---- parameters ----------------------------------------------------------------------------
// Picks the framing parameters out of an effective-value set (registry ids) into a plain object.
export function framingParams(e) {
  return {
    mode: e['framing.mode'], spread: e['framing.spread'], zoomJitter: e['framing.zoom_jitter'], candidates: e['framing.candidates'],
    temperature: e['framing.temperature'], neighbourInfluence: e['framing.neighbour_influence'], edgeSample: e['framing.edge_sample'],
    matchOn: e['framing.match_on'], vary: e['framing.vary_per_appearance'], memory: e['framing.memory'], driftSpeed: e['framing.drift_speed'],
  };
}

// ---- derivation ----------------------------------------------------------------------------
const THIRDS = [1 / 3, 2 / 3];
const seedOf = (seed, clipId, appearance, salt = '') => hashString(`${seed >>> 0}|${clipId}|${appearance}|${salt}`);

export function windowDistance(a, b, srcAspect, cellAspect) {
  const { w, h } = windowSize(Math.min(a.zoom, b.zoom), srcAspect, cellAspect);
  return Math.max(Math.abs(a.cx - b.cx) / w, Math.abs(a.cy - b.cy) / h, Math.abs(Math.log(a.zoom / b.zoom)));
}

// Place a window of the given zoom: u, v in [-1, 1] are fractions of the available travel, scaled by spread.
function place(u, v, zoom, spread, srcAspect, cellAspect) {
  const { w, h } = windowSize(zoom, srcAspect, cellAspect);
  return { cx: 0.5 + u * spread * (1 - w) / 2, cy: 0.5 + v * spread * (1 - h) / 2, zoom };
}
function drawZoom(rng, base, jit, minZoom) {
  return clamp(Math.max(minZoom, base * (1 + jit * (rng() * 2 - 1))), 1, MAX_ZOOM);
}

export function deriveWindow(input) {
  const { clip, srcAspect, cellAspect, axis = 'columns', baseZoom, seed, appearance = 0, history = [], neighbours = [], params: P, focal } = input;
  const minZoom = Math.max(1, input.minZoom ?? 1);
  const base = Math.max(minZoom, baseZoom);
  const fin = (win, extra) => {
    const c = clampWindow(win, srcAspect, cellAspect, minZoom);
    return { cx: c.cx, cy: c.cy, zoom: c.zoom, zf: c.zoom / base, ...extra };
  };
  const mode = MODES.includes(P.mode) ? P.mode : 'center';
  if (mode === 'center') {
    const f = focal || { x: 0.5, y: 0.5 };
    return fin({ cx: f.x, cy: f.y, zoom: base }, { mode, effectiveMode: 'center', info: {} });
  }
  const app = P.vary ? appearance : 0;
  const rng = mulberry32(seedOf(seed, clip.id, app, 'frame'));
  const spread = clamp(P.spread, 0, 1), jit = clamp(P.zoomJitter, 0, 100) / 100;
  const zoom = drawZoom(rng, base, jit, minZoom);
  const col = colourOf(clip);
  let eff = mode;
  if ((mode === 'detail' || mode === 'blend' || mode === 'contrast') && !col.grid) eff = 'random';

  // memory: the windows this clip showed in its last M-1 appearances must all differ from the new one
  const _memN = Math.max(0, Math.floor(P.memory) - 1);
  const recent = P.vary && _memN > 0 ? history.slice(-_memN) : [];
  const allowed = (c) => recent.every((h) => windowDistance(c, h, srcAspect, cellAspect) >= MEMORY_TOL);
  const gen = (n) => Array.from({ length: n }, () => { const u = rng() * 2 - 1, v = rng() * 2 - 1; return place(u, v, zoom, spread, srcAspect, cellAspect); });
  const farthest = (list) => {
    let best = list[0], bd = -1;
    for (const c of list) { const d = recent.length ? Math.min(...recent.map((h) => windowDistance(c, h, srcAspect, cellAspect))) : 1; if (d > bd) { bd = d; best = c; } }
    return best;
  };
  const info = { candidates: 0, allowed: 0, neighbours: 0, score: null };
  const done = (c, extra) => fin(c, { mode, effectiveMode: eff, info, ...extra });

  if (eff === 'thirds') {
    const { w, h } = windowSize(zoom, srcAspect, cellAspect);
    const combos = [];
    for (const px of THIRDS) for (const py of THIRDS) for (const qx of THIRDS) for (const qy of THIRDS) {
      combos.push(clampWindow({ cx: 0.5 + spread * (px - (qx - 0.5) * w - 0.5), cy: 0.5 + spread * (py - (qy - 0.5) * h - 0.5), zoom }, srcAspect, cellAspect, minZoom));
    }
    for (let i = combos.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [combos[i], combos[j]] = [combos[j], combos[i]]; }
    info.candidates = combos.length;
    const ok = combos.filter(allowed); info.allowed = ok.length;
    return done(ok.length ? ok[0] : farthest(combos));
  }

  if (eff === 'random' || eff === 'drift') {
    let first = null, all = [];
    for (let b = 0; b < 16 && !first; b++) {
      const batch = gen(b === 0 ? 1 : 16);
      all = all.concat(batch);
      first = batch.find(allowed) || null;
    }
    info.candidates = all.length; info.allowed = first ? 1 : 0;
    const c = first || farthest(all);
    if (eff === 'drift') {
      const legDur = 30 / Math.max(0.1, P.driftSpeed || 2);
      const path = { key: seedOf(seed, clip.id, app, 'drift'), hold: 0, legDur, start: { cx: c.cx, cy: c.cy, zf: clamp(c.zoom, 1, MAX_ZOOM) / base }, spread, jit };
      return done(c, { path });
    }
    return done(c);
  }

  // detail / blend / contrast: score K candidates
  const K = Math.max(1, Math.floor(P.candidates));
  let cands = gen(K), ok = cands.filter(allowed);
  for (let b = 0; b < 4 && !ok.length; b++) { const more = gen(K); cands = cands.concat(more); ok = more.filter(allowed); }
  info.candidates = cands.length; info.allowed = ok.length;
  if (!ok.length) return done(farthest(cands));
  let raw, sign, strength = 1;
  if (eff === 'detail') {
    raw = ok.map((c) => windowVariance(col.grid, windowRect(c, srcAspect, cellAspect))); sign = 1;
  } else {
    const nb = neighbours.map((n) => ({ n, g: colourOf(n.clip).grid })).filter((x) => x.g && x.n.win);
    info.neighbours = nb.length;
    const mine = (dir) => (axis === 'rows' ? (dir < 0 ? 'top' : 'bottom') : (dir < 0 ? 'left' : 'right'));
    const theirs = (dir) => (axis === 'rows' ? (dir < 0 ? 'bottom' : 'top') : (dir < 0 ? 'right' : 'left'));
    const refs = nb.map(({ n, g }) => ({ dir: n.dir, prof: edgeProfile(g, windowRect(n.win, n.srcAspect, n.cellAspect), theirs(n.dir), P.edgeSample) }));
    raw = ok.map((c) => {
      if (!refs.length) return 0;
      const rect = windowRect(c, srcAspect, cellAspect);
      let s = 0;
      for (const r of refs) s += profileMismatch(edgeProfile(col.grid, rect, mine(r.dir), P.edgeSample), r.prof, P.matchOn);
      return s / refs.length;
    });
    sign = eff === 'blend' ? -1 : 1; strength = clamp(P.neighbourInfluence, 0, 1);
  }
  let lo = Infinity, hi = -Infinity;
  for (const r of raw) { if (r < lo) lo = r; if (r > hi) hi = r; }
  const norm = raw.map((r) => (hi - lo > 1e-12 ? (r - lo) / (hi - lo) : 0));
  const logit = norm.map((s) => sign * strength * s);
  const T = Math.max(0, P.temperature);
  let pick = 0;
  if (T <= 1e-3) { for (let i = 1; i < logit.length; i++) if (logit[i] > logit[pick]) pick = i; }
  else {
    let mx = -Infinity; for (const l of logit) if (l > mx) mx = l;
    const w = logit.map((l) => Math.exp((l - mx) / T));
    let u = rng() * w.reduce((a, b) => a + b, 0);
    pick = w.length - 1;
    for (let i = 0; i < w.length; i++) { u -= w[i]; if (u <= 0) { pick = i; break; } }
  }
  info.score = raw[pick];
  return done(ok[pick]);
}

// ---- drift (Ken Burns) ---------------------------------------------------------------------
const smooth = (t) => t * t * (3 - 2 * t);
function driftTarget(path, j, ctx) {
  const rng = mulberry32(hashString(`${path.key}|${path.hold}|${j}`));
  const zoom = drawZoom(rng, ctx.baseZoom, path.jit, ctx.minZoom);
  const u = rng() * 2 - 1, v = rng() * 2 - 1;
  const c = place(u, v, zoom, path.spread, ctx.srcAspect, ctx.cellAspect);
  return { cx: c.cx, cy: c.cy, zf: zoom / ctx.baseZoom };
}
// The window `elapsed` seconds into a hold. Under reduced motion it never moves (the starting window).
// ctx: {srcAspect, cellAspect, baseZoom, minZoom}.
export function driftWindowAt(path, elapsed, ctx, reduced = false) {
  const base = Math.max(ctx.minZoom, ctx.baseZoom);
  const c2 = { ...ctx, baseZoom: base };
  let a = path.start, b = path.start, f = 0;
  if (!reduced && elapsed > 0) {
    const leg = Math.floor(elapsed / path.legDur);
    f = smooth(elapsed / path.legDur - leg);
    a = leg === 0 ? path.start : driftTarget(path, leg - 1, c2);
    b = driftTarget(path, leg, c2);
  }
  const win = { cx: lerp(a.cx, b.cx, f), cy: lerp(a.cy, b.cy, f), zoom: base * lerp(a.zf, b.zf, f) };
  const c = clampWindow(win, ctx.srcAspect, ctx.cellAspect, ctx.minZoom);
  return { cx: c.cx, cy: c.cy, zoom: c.zoom, zf: c.zoom / base };
}
// A new hold begins: the path continues from where the window is now towards fresh seeded targets.
export function nextHold(path, elapsed, ctx, reduced = false) {
  if (reduced) return path;
  const now = driftWindowAt(path, elapsed, ctx, false);
  return { ...path, hold: path.hold + 1, start: { cx: now.cx, cy: now.cy, zf: now.zf } };
}

// ---- per-clip appearance history -----------------------------------------------------------
export class Framer {
  constructor() { this.clear(); }
  clear() { this.count = new Map(); this.history = new Map(); }
  appearances(clipId) { return this.count.get(clipId) || 0; }
  // Derives the window for the next appearance of input.clip. Pass `appearance` to re-derive an
  // appearance that was already counted (parameters changed): counters stay, its history entry is replaced.
  assign(input, appearance) {
    const id = input.clip.id;
    const redo = appearance !== undefined;
    const a = redo ? appearance : this.count.get(id) || 0;
    const hist = this.history.get(id) || [];
    const res = deriveWindow({ ...input, appearance: a, history: hist.filter((h) => h.a < a) });
    if (!redo) this.count.set(id, a + 1);
    const next = hist.filter((h) => h.a !== a);
    next.push({ a, cx: res.cx, cy: res.cy, zoom: res.zoom });
    next.sort((x, y) => x.a - y.a);
    this.history.set(id, next.slice(-HISTORY_CAP));
    return { ...res, appearance: a };
  }
}
