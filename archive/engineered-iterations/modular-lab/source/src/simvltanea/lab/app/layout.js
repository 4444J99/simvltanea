// Pure layout maths: full-bleed strips, zoom curve, focal points, cover-fitting. No DOM.
import { mulberry32, hashString } from './engine.js';

const PHI = (1 + Math.sqrt(5)) / 2;

export function splitWeights(n, mode, custom = [], seed = 1) {
  let w;
  if (mode === 'random') {
    const rng = mulberry32((seed ^ 0x51ed) >>> 0);
    w = Array.from({ length: n }, () => 0.5 + rng());
  } else if (mode === 'golden') {
    w = Array.from({ length: n }, (_, i) => Math.pow(PHI, -i));
    const mean = w.reduce((a, b) => a + b, 0) / n;
    w = w.map((x) => Math.max(x, 0.25 * mean));
  } else if (mode === 'custom' && Array.isArray(custom) && custom.length) {
    w = Array.from({ length: n }, (_, i) => {
      const c = custom[i % custom.length];
      return Number.isFinite(c) && c > 0 ? c : 0.1;
    });
  } else w = new Array(n).fill(1);
  const sum = w.reduce((a, b) => a + b, 0);
  return w.map((x) => x / sum);
}

// 'auto' stacks strips along the viewport's long axis (columns on wide screens, rows on tall).
export function stripAxis(direction, W, H) {
  if (direction === 'columns' || direction === 'rows') return direction;
  return W >= H ? 'columns' : 'rows';
}

// Integer boundaries 0..total with n strips; each strip >= 1px when total >= n.
export function edgesFor(total, weights) {
  const n = weights.length;
  const edges = [0];
  let cum = 0;
  for (let i = 0; i < n - 1; i++) {
    cum += weights[i];
    edges.push(Math.round(total * cum));
  }
  edges.push(total);
  if (total >= n) {
    for (let i = 1; i < n; i++) if (edges[i] <= edges[i - 1]) edges[i] = edges[i - 1] + 1;
    for (let i = n - 1; i >= 1; i--) if (edges[i] > total - (n - i)) edges[i] = total - (n - i);
  }
  return edges;
}

export function computeLayout({ W, H, n, direction = 'auto', split = 'equal', custom = [], overlap = 0, seed = 1 }) {
  W = Math.max(1, Math.round(W)); H = Math.max(1, Math.round(H));
  n = Math.max(1, Math.round(n));
  const axis = stripAxis(direction, W, H);
  const total = axis === 'columns' ? W : H;
  const weights = splitWeights(n, split, custom, seed);
  const edges = edgesFor(total, weights);
  const o = Math.max(0, Math.round(overlap));
  const rects = [];
  for (let i = 0; i < n; i++) {
    const a = edges[i], b = edges[i + 1];
    const a2 = i === 0 ? a : Math.max(0, a - Math.floor(o / 2));
    const b2 = i === n - 1 ? b : Math.min(total, b + Math.ceil(o / 2));
    const mk = (s, e) => (axis === 'columns' ? { x: s, y: 0, w: e - s, h: H } : { x: 0, y: s, w: W, h: e - s });
    rects.push({ ...mk(a2, b2), tile: mk(a, b), index: i });
  }
  return { W, H, axis, n, weights, edges, rects };
}

// zoom(N) = max(floor, Z1 / N^gamma); manual override replaces the curve. Never below 1 (cover).
export function zoomFor(n, { z1 = 8, gamma = 0.6, floor = 1, manual = 0 } = {}) {
  const fl = Math.max(1, floor);
  if (manual > 0) return Math.max(fl, manual);
  return Math.max(fl, 1, z1 / Math.pow(Math.max(1, n), gamma));
}

export const coverScale = (vw, vh, cw, ch) => Math.max(cw / vw, ch / vh);

// Focal point (0..1 in the clip). static: stable pseudo-random spot near the centre per key.
export function focalPoint(mode, key, t = 0, driftPerMin = 0) {
  const h = hashString(String(key));
  const bx = 0.5 + (((h & 0xffff) / 65535) - 0.5) * 0.5;
  const by = 0.5 + ((((h >>> 16) & 0xffff) / 65535) - 0.5) * 0.5;
  if (mode !== 'drift' || driftPerMin <= 0) return { x: bx, y: by };
  const ph = (t * driftPerMin) / 60;
  const px = (h % 997) / 997, py = (h % 991) / 991;
  const clamp = (v) => Math.min(0.95, Math.max(0.05, v));
  return {
    x: clamp(bx + 0.25 * Math.sin((ph + px) * Math.PI * 2)),
    y: clamp(by + 0.25 * Math.sin((ph * 0.73 + py) * Math.PI * 2)),
  };
}

// Place a vw x vh video in a cw x ch cell. jitterAmp = max sideways sway in px on `axis`,
// jitterNow in [-1,1]. Returns scale, translation (video top-left within the cell) and share.
export function fitVideo({ cw, ch, vw, vh, zoom, focal, axis = 'columns', jitterAmp = 0, jitterNow = 0 }) {
  const jx = axis === 'columns' ? jitterAmp : 0;
  const jy = axis === 'rows' ? jitterAmp : 0;
  const cover = coverScale(vw, vh, cw + 2 * jx, ch + 2 * jy);
  const scale = Math.max(cover, coverScale(vw, vh, cw, ch) * Math.max(1, zoom));
  const sw = vw * scale, sh = vh * scale;
  const clampT = (t, cell, size) => Math.min(0, Math.max(cell - size, t));
  const tx = clampT(clampT(cw / 2 - focal.x * sw, cw, sw) + jitterNow * jx, cw, sw);
  const ty = clampT(clampT(ch / 2 - focal.y * sh, ch, sh) + jitterNow * jy, ch, sh);
  return { scale, tx, ty, sw, sh, zoom: scale / coverScale(vw, vh, cw, ch), share: Math.min(1, (cw * ch) / (sw * sh)) };
}

// -1..1 pan from the tile centre along the strip axis.
export function panFor(tile, axis, W, H, width = 1) {
  const total = axis === 'columns' ? W : H;
  const centre = axis === 'columns' ? tile.x + tile.w / 2 : tile.y + tile.h / 2;
  if (tile.w >= W && tile.h >= H) return 0;
  return Math.max(-1, Math.min(1, (centre / total) * 2 - 1)) * width;
}
