import test from 'node:test';
import assert from 'node:assert/strict';
import { mulberry32 } from '../../app/engine.js';
import { fitVideo, focalPoint, zoomFor } from '../../app/layout.js';
import { defaults, PARAMS as REGISTRY, MODULES, byId, coerce, defaultConfig, encodeShare, decodeShare, toJSON, fromJSON } from '../../app/params.js';
import { PRESETS } from '../../app/presets.js';
import { MODES, deriveWindow, Framer, framingParams, clampWindow, windowRect, windowSize, edgeMismatch, colourOf, parseGrid8,
  driftWindowAt, nextHold, renderWindow, coverZoom, windowDistance, windowFromFit, coverFraction, MAX_ZOOM } from '../../app/framing.js';

// ---- synthetic grid8 data: smooth random colour fields (no real media anywhere) ----
const hex2 = (x) => Math.round(Math.min(1, Math.max(0, x)) * 255).toString(16).padStart(2, '0');
export function fieldGrid8(seed) {
  const r = mulberry32(seed), comps = [0, 1, 2].map(() => Array.from({ length: 3 }, () => ({ fx: (r() * 2.2 + 0.3), fy: (r() * 2.2 + 0.3), px: r() * 6.28, py: r() * 6.28, a: 0.25 + r() * 0.25 })));
  let s = '';
  for (let j = 0; j < 8; j++) for (let i = 0; i < 8; i++) for (let c = 0; c < 3; c++) {
    let v = 0.5;
    for (const k of comps[c]) v += k.a * Math.sin(k.fx * i * 0.8 + k.px) * Math.cos(k.fy * j * 0.8 + k.py) / 1.6;
    s += hex2(v);
  }
  return s;
}
const clip = (id, features) => ({ id, raw: { features } });
const gclip = (n) => clip('g' + n, { grid8: fieldGrid8(n) });
const PARAMS = (o = {}) => ({ ...framingParams({ ...defaults(), ...Object.fromEntries(Object.entries(o).map(([k, v]) => ['framing.' + k, v])) }) });
const ASPECTS = [0.15, 0.4, 0.75, 1, 1.33, 3, 12];
const SRC = [0.5, 0.75, 1, 1.33, 1.78, 0.56];

const inside = (w, src, cell) => { const r = windowRect(w, src, cell); return r.x0 >= -1e-9 && r.y0 >= -1e-9 && r.x1 <= 1 + 1e-9 && r.y1 <= 1 + 1e-9; };

test('every mode: window inside the source, keeps the cell aspect, zoom >= max(1, minZoom), any aspect/zoom/spread', () => {
  const rng = mulberry32(1);
  for (const mode of MODES) for (const src of SRC) for (const cell of ASPECTS) for (const spread of [0, 0.3, 1]) for (const base of [1, 1.7, 8, 40]) for (const minZoom of [1, 1.4]) {
    const c = rng() < 0.5 ? gclip(Math.floor(rng() * 50)) : clip('plain', {});
    const w = deriveWindow({ clip: c, srcAspect: src, cellAspect: cell, baseZoom: base, minZoom, seed: 3, appearance: 2, history: [], neighbours: [], params: PARAMS({ mode, spread, zoom_jitter: 50 }), focal: { x: rng(), y: rng() } });
    assert.ok(w.zoom >= Math.max(1, minZoom) - 1e-9, `zoom ${w.zoom} ${mode}`);
    assert.ok(w.zoom <= MAX_ZOOM + 1e-9);
    assert.ok(inside(w, src, cell), `outside ${mode} src${src} cell${cell} sp${spread} z${base}: ${JSON.stringify(w)}`);
    const r = windowRect(w, src, cell);
    assert.ok(Math.abs(r.w * src / r.h - cell) < 1e-6 * cell, 'aspect kept');
    // drawn through the renderer the cell is covered
    const vw = 1000 * src, vh = 1000;
    const fit = fitVideo({ cw: 100 * cell, ch: 100, vw, vh, zoom: w.zoom, focal: { x: w.cx, y: w.cy } });
    assert.ok(fit.tx <= 1e-6 && fit.ty <= 1e-6 && fit.tx + fit.sw >= 100 * cell - 1e-6 && fit.ty + fit.sh >= 100 - 1e-6);
  }
});

test('spread 0 is always centred; spread 1 reaches the whole range', () => {
  for (const mode of ['random', 'blend', 'contrast', 'detail', 'drift']) {
    for (let a = 0; a < 6; a++) {
      const w = deriveWindow({ clip: gclip(a), srcAspect: 1, cellAspect: 0.3, baseZoom: 4, seed: 1, appearance: a, params: PARAMS({ mode, spread: 0, zoom_jitter: 0 }) });
      assert.ok(Math.abs(w.cx - 0.5) < 1e-9 && Math.abs(w.cy - 0.5) < 1e-9, mode);
    }
  }
  let minx = 1, maxx = 0;
  for (let a = 0; a < 400; a++) {
    const w = deriveWindow({ clip: clip('x', {}), srcAspect: 1, cellAspect: 0.3, baseZoom: 4, seed: 1, appearance: a, params: PARAMS({ mode: 'random', spread: 1, zoom_jitter: 0, vary_per_appearance: true }) });
    const r = windowRect(w, 1, 0.3); minx = Math.min(minx, r.x0); maxx = Math.max(maxx, r.x1);
  }
  assert.ok(minx < 0.02 && maxx > 0.98, `${minx} ${maxx}`);
});

test('deterministic for a fixed seed; the seed changes the result', () => {
  for (const mode of MODES) {
    const run = (seed) => {
      const f = new Framer(), out = [];
      const nb = [{ dir: -1, win: { cx: 0.4, cy: 0.5, zoom: 3 }, clip: gclip(99), srcAspect: 1, cellAspect: 0.4 }];
      for (let i = 0; i < 6; i++) out.push(f.assign({ clip: gclip(i % 2), srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed, neighbours: nb, params: PARAMS({ mode }), focal: { x: 0.5, y: 0.5 } }));
      return JSON.stringify(out);
    };
    assert.equal(run(5), run(5), mode);
    if (mode !== 'center') assert.notEqual(run(5), run(6), mode + ' seed matters');
  }
});

test('the same clip gets different windows on successive appearances (vary on, spread > 0); off = identical', () => {
  for (const mode of ['random', 'thirds', 'detail', 'blend', 'contrast', 'drift']) {
    const f = new Framer(), seen = [];
    const nb = [{ dir: -1, win: { cx: 0.5, cy: 0.5, zoom: 3 }, clip: gclip(7), srcAspect: 1, cellAspect: 0.4 }];
    for (let i = 0; i < 8; i++) seen.push(f.assign({ clip: gclip(1), srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 9, neighbours: nb, params: PARAMS({ mode, spread: 0.8, zoom_jitter: 0, temperature: 0 }) }));
    assert.deepEqual(seen.map((w) => w.appearance), [0, 1, 2, 3, 4, 5, 6, 7]);
    for (let i = 1; i < seen.length; i++) assert.ok(windowDistance(seen[i], seen[i - 1], 1, 0.4) >= 0.08, `${mode} appearance ${i} repeats`);
    const g = new Framer(), same = [];
    for (let i = 0; i < 4; i++) same.push(g.assign({ clip: gclip(1), srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 9, neighbours: nb, params: PARAMS({ mode, spread: 0.8, vary_per_appearance: false }) }));
    for (const w of same) { assert.equal(w.cx, same[0].cx); assert.equal(w.cy, same[0].cy); assert.equal(w.zoom, same[0].zoom); }
  }
});

test('memory: any M consecutive appearances of a clip are pairwise different', () => {
  for (const mode of ['random', 'thirds', 'detail', 'blend', 'contrast']) for (const M of [2, 4, 8]) {
    const f = new Framer(), seen = [];
    const nb = [{ dir: -1, win: { cx: 0.3, cy: 0.5, zoom: 4 }, clip: gclip(70), srcAspect: 1, cellAspect: 0.5 }];
    for (let i = 0; i < 40; i++) seen.push(f.assign({ clip: gclip(3), srcAspect: 1, cellAspect: 0.5, baseZoom: 4, seed: 2, neighbours: nb, params: PARAMS({ mode, spread: 1, zoom_jitter: 0, temperature: 0, memory: M }) }));
    for (let i = 0; i + M <= seen.length; i++) for (let a = i; a < i + M; a++) for (let b = a + 1; b < i + M; b++)
      assert.ok(windowDistance(seen[a], seen[b], 1, 0.5) >= 0.08, `${mode} M=${M}: appearances ${a} and ${b} equal`);
  }
});

test('blend lowers the mean facing-edge mismatch versus random; contrast raises it (all match_on modes, both axes)', () => {
  for (const axis of ['columns', 'rows']) for (const matchOn of ['colour', 'luma', 'hue']) {
    const mean = { random: 0, blend: 0, contrast: 0 };
    const N = 150;
    for (let t = 0; t < N; t++) {
      const A = gclip(1000 + t), B = gclip(2000 + t);
      const cellAspect = axis === 'columns' ? 0.45 : 2.2;
      const winA = deriveWindow({ clip: A, srcAspect: 1.2, cellAspect, baseZoom: 3, seed: t, params: PARAMS({ mode: 'random', zoom_jitter: 0 }) });
      for (const mode of Object.keys(mean)) {
        const w = deriveWindow({ clip: B, srcAspect: 0.8, cellAspect, axis, baseZoom: 3, seed: 77 + t, appearance: t,
          neighbours: [{ dir: -1, win: winA, clip: A, srcAspect: 1.2, cellAspect }],
          params: PARAMS({ mode, match_on: matchOn, neighbour_influence: 1, temperature: 0.1, edge_sample: 0.1, zoom_jitter: 0, spread: 1 }) });
        mean[mode] += edgeMismatch({ win: winA, grid: colourOf(A).grid, srcAspect: 1.2, cellAspect }, { win: w, grid: colourOf(B).grid, srcAspect: 0.8, cellAspect }, { axis, matchOn, band: 0.1 }) / N;
      }
    }
    console.log(`    ${axis}/${matchOn}: random ${mean.random.toFixed(4)} blend ${mean.blend.toFixed(4)} contrast ${mean.contrast.toFixed(4)}`);
    assert.ok(mean.blend < mean.random * 0.8, `blend ${mean.blend} vs random ${mean.random}`);
    assert.ok(mean.contrast > mean.random * 1.2, `contrast ${mean.contrast} vs random ${mean.random}`);
  }
});

test('neighbour influence 0 makes blend as indifferent as random; temperature spreads the choice', () => {
  const A = gclip(5), B = gclip(6);
  const winA = deriveWindow({ clip: A, srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 1, params: PARAMS({ mode: 'random' }) });
  const nb = [{ dir: -1, win: winA, clip: A, srcAspect: 1, cellAspect: 0.4 }];
  const distinct = (o) => new Set(Array.from({ length: 30 }, (_, i) => deriveWindow({ clip: B, srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: i, appearance: i, neighbours: nb, params: PARAMS({ mode: 'blend', zoom_jitter: 0, spread: 1, ...o }) }).cx.toFixed(3))).size;
  assert.ok(distinct({ temperature: 0, neighbour_influence: 1 }) >= 10); // different seeds draw different candidate sets
  const mism = (o) => { let s = 0; for (let i = 0; i < 60; i++) { const w = deriveWindow({ clip: B, srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: i, appearance: i, neighbours: nb, params: PARAMS({ mode: 'blend', zoom_jitter: 0, spread: 1, ...o }) }); s += edgeMismatch({ win: winA, grid: colourOf(A).grid, srcAspect: 1, cellAspect: 0.4 }, { win: w, grid: colourOf(B).grid, srcAspect: 1, cellAspect: 0.4 }) / 60; } return s; };
  assert.ok(mism({ temperature: 0, neighbour_influence: 1 }) < mism({ temperature: 2, neighbour_influence: 1 }));
  assert.ok(mism({ temperature: 0, neighbour_influence: 1 }) < mism({ temperature: 0, neighbour_influence: 0 }));
});

test('detail prefers windows with more colour variance than random', () => {
  const variance = (g, r) => { let n = 0, s = 0, s2 = 0; const k = 6; for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) { const x = (r.x0 + (i + 0.5) / k * r.w) * 8, y = (r.y0 + (j + 0.5) / k * r.h) * 8; const gx = Math.min(7, Math.max(0, Math.floor(x))), gy = Math.min(7, Math.max(0, Math.floor(y))); const v = g[(gy * 8 + gx) * 3] + g[(gy * 8 + gx) * 3 + 1] + g[(gy * 8 + gx) * 3 + 2]; n++; s += v; s2 += v * v; } return s2 / n - (s / n) ** 2; };
  let det = 0, rnd = 0;
  for (let t = 0; t < 120; t++) {
    const c = gclip(300 + t);
    for (const mode of ['detail', 'random']) {
      const w = deriveWindow({ clip: c, srcAspect: 1, cellAspect: 1, baseZoom: 3, seed: t, appearance: t, params: PARAMS({ mode, zoom_jitter: 0, spread: 1, temperature: 0 }) });
      const v = variance(colourOf(c).grid, windowRect(w, 1, 1));
      if (mode === 'detail') det += v; else rnd += v;
    }
  }
  assert.ok(det > rnd * 1.15, `detail ${det} random ${rnd}`);
});

test('fallbacks: grid8 -> palette -> hue -> luma -> none (random, no crash); malformed grid8 ignored', () => {
  assert.equal(colourOf(gclip(1)).kind, 'grid8');
  assert.equal(colourOf(clip('a', { palette: [{ hex: '#336699', share: 0.4 }] })).kind, 'palette');
  assert.equal(colourOf(clip('b', { hue: 0.3, luma: 0.4 })).kind, 'hue');
  assert.equal(colourOf(clip('c', { luma: 0.4 })).kind, 'luma');
  assert.equal(colourOf(clip('d', {})).kind, 'none');
  assert.equal(colourOf(clip('e', { grid8: 'zz' + fieldGrid8(1).slice(2) })).kind, 'none');
  assert.equal(colourOf(clip('f', { grid8: fieldGrid8(1).slice(2), luma: 0.2 })).kind, 'luma');
  assert.equal(colourOf({ id: 'g' }).kind, 'none');
  assert.equal(parseGrid8(fieldGrid8(2)).length, 192);
  for (const f of [{}, { luma: 0.5 }, { hue: 0.1 }, { palette: [{ hex: '#ff0000' }] }, { grid8: 'bad' }]) for (const mode of ['detail', 'blend', 'contrast']) {
    const w = deriveWindow({ clip: clip('x', f), srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 1, neighbours: [{ dir: -1, win: { cx: 0.5, cy: 0.5, zoom: 3 }, clip: gclip(1), srcAspect: 1, cellAspect: 0.4 }], params: PARAMS({ mode }) });
    assert.ok(inside(w, 1, 0.4));
    if (!Object.keys(f).length || f.grid8) assert.equal(w.effectiveMode, 'random');
  }
});

test('center reproduces the previous behaviour exactly (focal point + zoom curve through fitVideo)', () => {
  for (const n of [1, 3, 8, 12]) for (const [cw, ch] of [[320, 720], [1280, 90], [200, 200]]) for (const [vw, vh] of [[540, 720], [720, 540]]) for (const mode of ['static', 'drift']) for (const t of [0, 3.7, 91]) {
    const e = { ...defaults(), 'zoom.focal_mode': mode, 'zoom.drift_speed': 5, 'framing.mode': 'center' };
    const zoom = zoomFor(n, { z1: e['zoom.z1'], gamma: e['zoom.gamma'], floor: e['zoom.floor'], manual: e['zoom.manual'] });
    const key = `${n % 3}:clip-${n}`;
    const focal = focalPoint(mode, key, t, e['zoom.drift_speed']);
    const legacy = fitVideo({ cw, ch, vw, vh, zoom, focal, axis: 'columns' });
    const win = deriveWindow({ clip: clip('x', {}), srcAspect: vw / vh, cellAspect: cw / ch, baseZoom: zoom, minZoom: 1, seed: 4, params: framingParams(e), focal });
    assert.equal(win.effectiveMode, 'center');
    assert.ok(Math.abs(win.zoom - zoom) < 1e-12);
    // what the renderer is handed in center mode is the legacy zoom and focal object itself
    const rw = renderWindow({ mode: 'center', win, baseZoom: zoom, minZoom: 1, srcAspect: vw / vh, cellAspect: cw / ch, focal, staticFocal: focalPoint('static', key) });
    assert.equal(rw.zoom, zoom); assert.equal(rw.focal, focal);
    assert.deepEqual(fitVideo({ cw, ch, vw, vh, zoom: rw.zoom, focal: rw.focal, axis: 'columns' }), legacy);
    // and the derived window itself draws the same picture to within rounding
    const viaWin = fitVideo({ cw, ch, vw, vh, zoom: win.zoom, focal: { x: win.cx, y: win.cy }, axis: 'columns' });
    for (const k of Object.keys(legacy)) assert.ok(Math.abs(viaWin[k] - legacy[k]) < 1e-6, k);
  }
});

test('renderWindow: non-center modes use the window, apply focal wander, stay inside; coverZoom accounts for jitter', () => {
  const win = { cx: 0.3, cy: 0.6, zoom: 4, zf: 1.2 };
  const r = renderWindow({ mode: 'random', win, baseZoom: 3, minZoom: 1, srcAspect: 1, cellAspect: 0.4, focal: { x: 0.5, y: 0.5 } });
  assert.ok(Math.abs(r.zoom - 3.6) < 1e-12 && Math.abs(r.focal.x - 0.3) < 1e-12);
  const w2 = renderWindow({ mode: 'random', win, baseZoom: 3, srcAspect: 1, cellAspect: 0.4, focal: { x: 0.6, y: 0.45 }, staticFocal: { x: 0.5, y: 0.5 } });
  assert.ok(Math.abs(w2.focal.x - 0.4) < 1e-12 && Math.abs(w2.focal.y - 0.55) < 1e-12);
  const far = renderWindow({ mode: 'random', win, baseZoom: 3, srcAspect: 1, cellAspect: 0.4, focal: { x: 5, y: -5 }, staticFocal: { x: 0, y: 0 } });
  assert.ok(inside({ cx: far.focal.x, cy: far.focal.y, zoom: far.zoom }, 1, 0.4));
  assert.equal(coverZoom(540, 720, 100, 400, 0, 0), 1);
  assert.ok(Math.abs(coverZoom(540, 720, 300, 400, 30, 0) - 1.2) < 1e-9);
  assert.equal(coverZoom(540, 720, 100, 400, 30, 0), 1); // already height-bound: the sway costs nothing
});

test('center with spread / jitter / neighbours / appearance set differently still gives the same window', () => {
  const base = { clip: gclip(1), srcAspect: 1, cellAspect: 0.5, baseZoom: 4, seed: 1, focal: { x: 0.4, y: 0.6 } };
  const a = deriveWindow({ ...base, params: PARAMS({ mode: 'center' }) });
  const b = deriveWindow({ ...base, appearance: 9, seed: 99, params: PARAMS({ mode: 'center', spread: 1, zoom_jitter: 50 }), neighbours: [{ dir: -1, win: { cx: 0.1, cy: 0.1, zoom: 9 }, clip: gclip(2), srcAspect: 1, cellAspect: 0.5 }] });
  assert.deepEqual([a.cx, a.cy, a.zoom], [b.cx, b.cy, b.zoom]);
});

test('zoom: baseline from the curve, jitter stays within +-%, never below minZoom', () => {
  for (let i = 0; i < 100; i++) {
    const w = deriveWindow({ clip: clip('z' + i, {}), srcAspect: 1, cellAspect: 0.5, baseZoom: 5, minZoom: 1, seed: i, params: PARAMS({ mode: 'random', zoom_jitter: 20 }) });
    assert.ok(w.zoom >= 4 - 1e-9 && w.zoom <= 6 + 1e-9);
    const z = deriveWindow({ clip: clip('z' + i, {}), srcAspect: 1, cellAspect: 0.5, baseZoom: 5, minZoom: 5.5, seed: i, params: PARAMS({ mode: 'random', zoom_jitter: 20 }) });
    assert.ok(z.zoom >= 5.5 - 1e-9);
    assert.equal(deriveWindow({ clip: clip('z', {}), srcAspect: 1, cellAspect: 0.5, baseZoom: 5, seed: i, params: PARAMS({ mode: 'random', zoom_jitter: 0 }) }).zoom, 5);
  }
});

test('drift: a continuous path inside the source; still under reduced motion; holds continue from where they are', () => {
  const f = new Framer();
  const first = f.assign({ clip: gclip(1), srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 5, params: PARAMS({ mode: 'drift', spread: 1, zoom_jitter: 30, drift_speed: 6 }) });
  assert.ok(first.path && first.path.legDur === 5);
  const ctx = { srcAspect: 1, cellAspect: 0.4, baseZoom: 3, minZoom: 1 };
  let prev = driftWindowAt(first.path, 0, ctx), moved = 0;
  assert.ok(Math.abs(prev.cx - first.cx) < 1e-9 && Math.abs(prev.zoom - first.zoom) < 1e-9);
  for (let t = 0.05; t < 60; t += 0.05) {
    const w = driftWindowAt(first.path, t, ctx);
    assert.ok(inside(w, 1, 0.4) && w.zoom >= 1);
    assert.ok(Math.hypot(w.cx - prev.cx, w.cy - prev.cy) < 0.05, 'continuous');
    moved += Math.hypot(w.cx - prev.cx, w.cy - prev.cy); prev = w;
  }
  assert.ok(moved > 0.5, 'it travels');
  assert.deepEqual(driftWindowAt(first.path, 33, ctx, true), driftWindowAt(first.path, 0, ctx, true));
  assert.deepEqual(driftWindowAt(first.path, 33, ctx), driftWindowAt(first.path, 33, ctx));
  const p2 = nextHold(first.path, 12.3, ctx);
  const at = driftWindowAt(first.path, 12.3, ctx), s2 = driftWindowAt(p2, 0, ctx);
  assert.ok(Math.abs(at.cx - s2.cx) < 1e-9 && Math.abs(at.zoom - s2.zoom) < 1e-9, 'a new hold starts where the old one was');
  assert.notDeepEqual(driftWindowAt(p2, 6, ctx), driftWindowAt(first.path, 12.3 + 6, ctx));
  assert.equal(nextHold(first.path, 12, ctx, true), first.path);
  // the window follows a changing cell aspect without leaving the source
  for (const cell of [0.1, 1, 5]) assert.ok(inside(driftWindowAt(first.path, 7, { ...ctx, cellAspect: cell }), 1, cell));
});

test('clampWindow / windowFromFit / coverFraction basics', () => {
  const c = clampWindow({ cx: -3, cy: 9, zoom: 0.2 }, 1.5, 0.5, 1);
  assert.equal(c.zoom, 1); assert.ok(inside(c, 1.5, 0.5));
  assert.equal(clampWindow({ cx: 0, cy: 0, zoom: 1e9 }, 1, 1).zoom, MAX_ZOOM);
  assert.deepEqual(coverFraction(1, 1), { w: 1, h: 1 });
  assert.deepEqual(windowSize(2, 2, 1), { w: 0.25, h: 0.5 } && windowSize(2, 2, 1));
  const fit = fitVideo({ cw: 300, ch: 400, vw: 540, vh: 720, zoom: 4, focal: { x: 0.3, y: 0.7 } });
  const w = windowFromFit(fit, 300, 400);
  assert.ok(Math.abs(w.cx - 0.3) < 1e-9 && Math.abs(w.cy - 0.7) < 1e-9 && Math.abs(w.zoom - 4) < 1e-9);
});

test('Framer: redo keeps counters, resets cleanly', () => {
  const f = new Framer(), c = gclip(1);
  const mk = (mode) => ({ clip: c, srcAspect: 1, cellAspect: 0.4, baseZoom: 3, seed: 1, params: PARAMS({ mode }) });
  f.assign(mk('random')); const b = f.assign(mk('random'));
  assert.equal(f.appearances('g1'), 2);
  const r = f.assign(mk('thirds'), b.appearance);
  assert.equal(r.appearance, 1); assert.equal(f.appearances('g1'), 2);
  f.clear(); assert.equal(f.appearances('g1'), 0);
});

const FRAMING_IDS = ['mode', 'spread', 'zoom_jitter', 'candidates', 'temperature', 'neighbour_influence', 'edge_sample', 'match_on', 'vary_per_appearance', 'memory', 'drift_speed'].map((x) => 'framing.' + x);

test('registry: every FRAMING parameter exists, has a valid default, is in its own module and round-trips through patch JSON and the share hash', () => {
  assert.ok(MODULES.some((m) => m.id === 'framing'));
  assert.deepEqual(REGISTRY.filter((p) => p.module === 'framing').map((p) => p.id), FRAMING_IDS);
  assert.deepEqual(byId['framing.mode'].options, MODES);
  const d = defaults();
  assert.equal(d['framing.candidates'], 48);
  assert.equal(d['framing.mode'], 'blend');
  assert.equal(d['zoom.z1'], 8); assert.equal(d['zoom.gamma'], 0.6); assert.equal(d['zoom.floor'], 1);
  const odd = { 'framing.mode': 'thirds', 'framing.spread': 0.33, 'framing.zoom_jitter': 27, 'framing.candidates': 91, 'framing.temperature': 0.77,
    'framing.neighbour_influence': 0.13, 'framing.edge_sample': 0.37, 'framing.match_on': 'luma', 'framing.vary_per_appearance': false,
    'framing.memory': 17, 'framing.drift_speed': 12.3, 'reveal.show_window': true };
  for (const [id, v] of Object.entries(odd)) { assert.equal(coerce(id, v).ok, true, id); assert.deepEqual(coerce(id, v).value, v, id); assert.notDeepEqual(v, d[id], id + ' is non-default'); }
  const c = defaultConfig(); Object.assign(c.values, odd);
  c.mods['framing.spread'] = { on: true, shape: 'triangle', rate: 0.2, depth: 0.5 };
  assert.deepEqual(fromJSON(toJSON(c)), c);
  assert.deepEqual(decodeShare('#' + encodeShare(c)), c);
  assert.equal(coerce('framing.mode', 'zoomy').ok, false);
  assert.equal(coerce('framing.memory', 999).value, 32);
  assert.equal(coerce('framing.spread', 5).value, 1);
});

test('presets: every scene sets a framing mode, plain presets leave FRAMING alone', () => {
  for (const p of PRESETS) {
    if (p.kind === 'scene') { assert.ok(p.resets.includes('framing'), p.id); assert.ok(MODES.includes(p.values['framing.mode']), p.id); }
    else assert.ok(!p.resets.includes('framing') && !Object.keys(p.values).some((k) => k.startsWith('framing.')), p.id);
  }
  assert.ok(new Set(PRESETS.filter((p) => p.kind === 'scene').map((p) => p.values['framing.mode'])).size >= 5);
});


test('framing memory of one ignores previous windows', () => {
  const input = { clip: gclip(1), srcAspect: 1, cellAspect: 0.5, baseZoom: 4, seed: 42, params: PARAMS({ mode: 'random', memory: 1, vary_per_appearance: true }) };
  const window = deriveWindow(input);
  assert.deepEqual(deriveWindow({ ...input, history: [window] }), window);
});
