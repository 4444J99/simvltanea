import test from 'node:test';
import assert from 'node:assert/strict';
import { computeLayout, splitWeights, zoomFor, fitVideo, focalPoint, coverScale, stripAxis, panFor, edgesFor } from '../../app/layout.js';

const VIEWPORTS = [[320, 320], [375, 812], [812, 375], [1280, 720], [1024, 1024], [2400, 600], [2560, 1440], [600, 2400], [1600, 400], [400, 1600], [333, 777]];

test('strips tile the viewport exactly for N=1..16, all viewports, splits and directions', () => {
  for (const [W, H] of VIEWPORTS) for (let n = 1; n <= 16; n++) for (const split of ['equal', 'random', 'golden', 'custom']) for (const direction of ['auto', 'rows', 'columns']) {
    const L = computeLayout({ W, H, n, split, direction, custom: [5, 1, 2], overlap: 0, seed: n });
    assert.equal(L.rects.length, n);
    const along = L.axis === 'columns' ? 'x' : 'y', size = L.axis === 'columns' ? 'w' : 'h';
    const total = L.axis === 'columns' ? W : H;
    let cursor = 0;
    for (const r of L.rects) {
      assert.equal(r[along], cursor, `gap at ${W}x${H} n=${n} ${split}`);
      assert.ok(r[size] >= 1);
      assert.ok(Number.isInteger(r.x) && Number.isInteger(r.y) && Number.isInteger(r.w) && Number.isInteger(r.h));
      cursor += r[size];
      // full cross extent
      if (L.axis === 'columns') { assert.equal(r.y, 0); assert.equal(r.h, H); } else { assert.equal(r.x, 0); assert.equal(r.w, W); }
    }
    assert.equal(cursor, total);
  }
});

test('overlap: neighbours overlap by the configured px, union still covers, nothing leaves the viewport', () => {
  for (const [W, H] of VIEWPORTS) for (const n of [2, 3, 7, 16]) for (const o of [1, 3, 4, 15]) {
    const L = computeLayout({ W, H, n, overlap: o });
    const along = L.axis === 'columns' ? 'x' : 'y', size = L.axis === 'columns' ? 'w' : 'h', total = L.axis === 'columns' ? W : H;
    let covered = 0;
    for (let i = 0; i < n; i++) {
      const r = L.rects[i];
      assert.ok(r[along] >= 0 && r[along] + r[size] <= total);
      if (i > 0) { const prev = L.rects[i - 1]; assert.equal(prev[along] + prev[size] - r[along], o, 'overlap px'); }
      covered = Math.max(covered, r[along] + r[size]);
      assert.deepEqual(r.tile, computeLayout({ W, H, n, overlap: 0 }).rects[i].tile);
    }
    assert.equal(covered, total); assert.equal(L.rects[0][along], 0);
  }
});

test('orientation follows the viewport shape', () => {
  assert.equal(stripAxis('auto', 1280, 720), 'columns'); assert.equal(stripAxis('auto', 375, 812), 'rows');
  assert.equal(stripAxis('auto', 500, 500), 'columns');
  assert.equal(stripAxis('rows', 1280, 720), 'rows'); assert.equal(stripAxis('columns', 375, 812), 'columns');
  const L = computeLayout({ W: 2400, H: 600, n: 4 }); assert.equal(L.axis, 'columns');
  const P = computeLayout({ W: 600, H: 2400, n: 4 }); assert.equal(P.axis, 'rows');
});

test('split weights: normalised, positive, modes differ, custom cycles', () => {
  for (const mode of ['equal', 'random', 'golden', 'custom']) for (const n of [1, 2, 9, 16]) {
    const w = splitWeights(n, mode, [3, 0, -1, 2], 4);
    assert.equal(w.length, n); assert.ok(Math.abs(w.reduce((a, b) => a + b, 0) - 1) < 1e-9); assert.ok(w.every((x) => x > 0));
  }
  const g = splitWeights(5, 'golden'); assert.ok(g[0] > g[1] && g[1] > g[2]);
  assert.ok(Math.abs(g[0] / g[1] - 1.618) < 0.01);
  assert.deepEqual(splitWeights(4, 'random', [], 1), splitWeights(4, 'random', [], 1));
  assert.notDeepEqual(splitWeights(4, 'random', [], 1), splitWeights(4, 'random', [], 2));
  const c = splitWeights(4, 'custom', [3, 1]); assert.ok(Math.abs(c[0] - c[2]) < 1e-12 && c[0] > c[1] * 2.9);
  assert.deepEqual(edgesFor(10, [0.5, 0.5]), [0, 5, 10]);
  const e = edgesFor(16, new Array(16).fill(1 / 16)); assert.deepEqual(e, Array.from({ length: 17 }, (_, i) => i));
});

test('zoom curve: default values, monotone decreasing, never below cover, N=1 extreme', () => {
  assert.equal(zoomFor(1, { z1: 8, gamma: 0.6 }), 8);
  assert.ok(Math.abs(zoomFor(4, { z1: 8, gamma: 0.6 }) - 8 / Math.pow(4, 0.6)) < 1e-12);
  let prev = Infinity;
  for (let n = 1; n <= 16; n++) { const z = zoomFor(n, {}); assert.ok(z <= prev && z >= 1); prev = z; }
  assert.ok(zoomFor(16, { z1: 8, gamma: 2 }) === 1);
  assert.equal(zoomFor(3, { z1: 0.2, gamma: 0, floor: 0 }), 1);
  assert.equal(zoomFor(3, { floor: 2.5, z1: 2 }), 2.5);
  assert.equal(zoomFor(3, { manual: 12 }), 12); assert.equal(zoomFor(3, { manual: 0.4 }), 1);
});

test('fitVideo always covers the cell (zoom, focal, jitter, any aspect), and zoom reduces visible share', () => {
  const cells = [[80, 720], [1280, 45], [2400, 150], [320, 320], [1, 600], [375, 51]];
  const videos = [[540, 720], [720, 540], [540, 540], [1080, 1920], [100, 100]];
  for (const [cw, ch] of cells) for (const [vw, vh] of videos) for (const zoom of [1, 1.5, 8, 40]) for (const axis of ['columns', 'rows'])
    for (const f of [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 0.5, y: 0.5 }, { x: 0.05, y: 0.95 }, { x: -3, y: 7 }]) for (const amp of [0, 25, 80]) for (const jn of [-1, 0, 1, 0.37]) {
      const r = fitVideo({ cw, ch, vw, vh, zoom, focal: f, axis, jitterAmp: amp, jitterNow: jn });
      const eps = 1e-6;
      assert.ok(r.tx <= eps && r.ty <= eps && r.tx + r.sw >= cw - eps && r.ty + r.sh >= ch - eps, `uncovered ${cw}x${ch} v${vw}x${vh} z${zoom} a${amp}`);
      assert.ok(r.zoom >= 1 - 1e-9 && r.zoom >= Math.min(zoom, 40) - 1e-9);
      assert.ok(r.share > 0 && r.share <= 1);
    }
  const a = fitVideo({ cw: 300, ch: 400, vw: 540, vh: 720, zoom: 1, focal: { x: 0.5, y: 0.5 } });
  const b = fitVideo({ cw: 300, ch: 400, vw: 540, vh: 720, zoom: 8, focal: { x: 0.5, y: 0.5 } });
  assert.ok(Math.abs(b.zoom - 8) < 1e-9 && b.share < a.share / 50);
  // jitter reaches both sides without empty space
  const lo = fitVideo({ cw: 100, ch: 400, vw: 540, vh: 720, zoom: 1, focal: { x: 0.5, y: 0.5 }, jitterAmp: 30, jitterNow: -1 });
  const hi = fitVideo({ cw: 100, ch: 400, vw: 540, vh: 720, zoom: 1, focal: { x: 0.5, y: 0.5 }, jitterAmp: 30, jitterNow: 1 });
  assert.ok(hi.tx - lo.tx > 50);
});

test('focal point: static is stable and bounded, drift moves and stays bounded', () => {
  const a = focalPoint('static', 'k', 0, 5), b = focalPoint('static', 'k', 99, 5);
  assert.deepEqual(a, b); assert.notDeepEqual(a, focalPoint('static', 'other', 0, 0));
  let moved = false;
  for (let t = 0; t < 120; t += 0.5) { const f = focalPoint('drift', 'k', t, 6); assert.ok(f.x >= 0.05 && f.x <= 0.95 && f.y >= 0.05 && f.y <= 0.95); if (Math.abs(f.x - a.x) > 0.05) moved = true; }
  assert.ok(moved);
  assert.deepEqual(focalPoint('drift', 'k', 50, 0), a);
});

test('pan is distinct per panel and symmetric', () => {
  const L = computeLayout({ W: 1280, H: 720, n: 5 });
  const pans = L.rects.map((r) => panFor(r.tile, L.axis, 1280, 720, 1));
  assert.equal(new Set(pans).size, 5);
  assert.ok(pans.every((p, i) => i === 0 || p > pans[i - 1]));
  assert.ok(Math.abs(pans[0] + pans[4]) < 0.01 && Math.abs(pans[2]) < 0.01);
  assert.equal(panFor(computeLayout({ W: 100, H: 100, n: 1 }).rects[0].tile, 'columns', 100, 100), 0);
  const R = computeLayout({ W: 375, H: 812, n: 4 });
  const rp = R.rects.map((r) => panFor(r.tile, R.axis, 375, 812, 0.8));
  assert.equal(new Set(rp).size, 4); assert.ok(Math.abs(rp[0]) <= 0.8);
  assert.ok(coverScale(540, 720, 100, 100) > 0);
});
