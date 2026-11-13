import test from 'node:test';
import assert from 'node:assert/strict';
import { Scheduler, mulberry32, buildRecords, normalizeClip, filterPool, orderPool, axisValue, pathPosition, playlistPosition,
  affinity, weightsFrom, polarity } from '../../app/engine.js';
import { makeRaw, makeRecords, params } from './helpers.mjs';

const recs = makeRecords(400);

// Run a scheduler for `seconds`, returning snapshots of on-screen clips every 0.5s plus changes.
function simulate(p, N, seconds, { seed = 3, records = recs, dt = 0.25 } = {}) {
  const s = new Scheduler(records, p, N, seed);
  const snaps = [], log = [];
  for (let t = 0; t <= seconds; t += dt) {
    const ch = s.tick(t);
    for (const c of ch) log.push({ t, ...c });
    snaps.push(s.onScreen().slice());
  }
  return { s, snaps, log };
}

test('RNG is deterministic', () => {
  const a = mulberry32(42), b = mulberry32(42), c = mulberry32(43);
  const xs = Array.from({ length: 5 }, a), ys = Array.from({ length: 5 }, b), zs = Array.from({ length: 5 }, c);
  assert.deepEqual(xs, ys); assert.notDeepEqual(xs, zs);
  assert.ok(xs.every((x) => x >= 0 && x < 1));
});

test('scheduler is deterministic for a fixed seed and differs across seeds', () => {
  const p = params({ 'path.shape': 'random', 'relation.strength': 1.5 });
  const a = simulate(p, 5, 120, { seed: 9 }).log, b = simulate(p, 5, 120, { seed: 9 }).log, c = simulate(p, 5, 120, { seed: 10 }).log;
  assert.deepEqual(a, b);
  assert.notDeepEqual(a, c);
  assert.ok(a.length > 20);
});

test('ordering by every axis is monotone with unknowns last', () => {
  const pool = Int32Array.from(recs.map((r) => r.i));
  for (const axis of ['captured_at', 'luma', 'saturation', 'hue', 'motion', 'duration', 'motion_level', 'shot', 'time_of_day', 'people']) {
    for (const dir of ['asc', 'desc']) {
      const o = orderPool(recs, pool, axis, dir, 1);
      assert.equal(o.length, pool.length);
      assert.equal(new Set(o).size, pool.length);
      const vals = Array.from(o, (i) => axisValue(recs[i], axis)).filter(Number.isFinite);
      assert.ok(vals.length > 100, axis + ' has values');
      for (let i = 1; i < vals.length; i++) assert.ok(dir === 'asc' ? vals[i] >= vals[i - 1] : vals[i] <= vals[i - 1], `${axis} ${dir}`);
    }
  }
  const o = orderPool(recs, pool, 'none', 'asc', 1), o2 = orderPool(recs, pool, 'none', 'asc', 2);
  assert.notDeepEqual(Array.from(o), Array.from(o2));
  assert.deepEqual(Array.from(o), Array.from(orderPool(recs, pool, 'none', 'asc', 1)));
  // unknown values go last
  const raw = makeRaw(30); delete raw[3].features; delete raw[7].features;
  const r2 = buildRecords(raw);
  const oo = orderPool(r2, Int32Array.from(r2.map((r) => r.i)), 'luma', 'desc', 1);
  assert.deepEqual(Array.from(oo.slice(-2)).sort(), [3, 7]);
});

test('path: sequential is monotone with wrap, bounce, restart, hold and stop', () => {
  const L = 10;
  const seq = (o, n) => Array.from({ length: n }, (_, i) => pathPosition({ shape: 'sequential', k: 0, N: 1, L, step: 1, ...o, n: i }));
  const wrap = seq({ wrap: true }, 25).map((r) => r.pos);
  assert.deepEqual(wrap.slice(0, 12), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1]);
  const bounce = seq({ wrap: false, onMeet: 'bounce' }, 22).map((r) => r.pos);
  assert.deepEqual(bounce.slice(8, 13), [8, 9, 8, 7, 6]);
  const hold = seq({ wrap: false, onMeet: 'hold' }, 15);
  assert.deepEqual(hold.map((r) => r.pos).slice(8, 14), [8, 9, 9, 9, 9, 9]); assert.ok(hold.every((r) => !r.stopped));
  const stop = seq({ wrap: false, onMeet: 'stop' }, 15);
  assert.equal(stop[9].stopped, false); assert.equal(stop[10].stopped, true); assert.equal(stop[14].pos, 9);
  const restart = seq({ wrap: false, onMeet: 'restart' }, 13).map((r) => r.pos);
  assert.deepEqual(restart.slice(9, 12), [9, 0, 1]);
  const step3 = seq({ wrap: true, step: 3 }, 5).map((r) => r.pos);
  assert.deepEqual(step3, [0, 3, 6, 9, 2]);
  for (const o of [{ wrap: true }, { wrap: false, onMeet: 'bounce' }, { wrap: false, onMeet: 'hold' }])
    for (const r of seq(o, 60)) assert.ok(r.pos >= 0 && r.pos < L);
  // panel start offsets spread over the order
  assert.deepEqual([0, 1, 2, 3].map((k) => pathPosition({ shape: 'sequential', k, n: 0, L: 100, N: 4 }).pos), [0, 25, 50, 75]);
});

test('path: converge approaches, meets, then follows on_meet', () => {
  const L = 21, o = { shape: 'converge', L, N: 2, step: 1, groups: 1, delay: 0 };
  const head = (n, onMeet) => pathPosition({ ...o, k: 0, n, onMeet });
  const tail = (n, onMeet) => pathPosition({ ...o, k: 1, n, onMeet });
  for (let n = 0; n < 10; n++) { assert.equal(head(n, 'hold').pos, n); assert.equal(tail(n, 'hold').pos, 20 - n); }
  assert.equal(head(10, 'hold').pos, 10); assert.equal(tail(10, 'hold').pos, 10); // meet (odd length: same slot)
  assert.equal(head(15, 'hold').pos, 10); assert.equal(head(15, 'hold').stopped, false);
  assert.equal(head(11, 'stop').stopped, true); assert.equal(head(10, 'stop').stopped, false);
  assert.deepEqual([9, 10, 11, 12].map((n) => head(n, 'bounce').pos), [9, 10, 9, 8]);
  assert.deepEqual([9, 10, 11].map((n) => head(n, 'restart').pos), [9, 10, 0]);
  assert.deepEqual([9, 10, 11].map((n) => tail(n, 'restart').pos), [11, 10, 20]);
  // diverge starts in the middle and ends at the ends
  assert.equal(pathPosition({ ...o, shape: 'diverge', k: 0, n: 0, onMeet: 'hold' }).pos, 10);
  assert.equal(pathPosition({ ...o, shape: 'diverge', k: 0, n: 10, onMeet: 'hold' }).pos, 0);
  assert.equal(pathPosition({ ...o, shape: 'diverge', k: 1, n: 10, onMeet: 'hold' }).pos, 20);
  // groups split the order in segments
  const g = pathPosition({ shape: 'converge', L: 20, N: 4, step: 1, groups: 2, delay: 0, onMeet: 'hold', k: 1, n: 0 });
  assert.equal(g.pos, 10);
});

test('scheduler converge on-screen: oldest and newest meet', () => {
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'converge', 'path.window': 0, 'path.on_meet': 'hold', 'timing.cooldown': 0,
    'timing.hold_min': 1, 'timing.hold_max': 1, 'timing.stagger': 0, 'timing.recency': 0, 'timing.novelty': 0 });
  const s = new Scheduler(recs, p, 2, 1);
  const L = s.order.length;
  const pos = [];
  for (let t = 0; t < 400; t++) { s.tick(t); pos.push(s.onScreen().map((c) => s.posOf[c])); }
  assert.deepEqual(pos[0], [0, L - 1]);
  assert.deepEqual(pos[5], [5, L - 6]);
  const last = pos[pos.length - 1];
  assert.ok(Math.abs(last[0] - last[1]) <= 1 && last[0] >= L / 2 - 2 && last[0] <= L / 2 + 2, JSON.stringify(last));
  for (let i = 1; i < 190; i++) assert.ok(pos[i][0] >= pos[i - 1][0] && pos[i][1] <= pos[i - 1][1]);
});

test('round canon: panel k equals panel 0 shifted by k*delay beats, exactly', () => {
  const d = 3, N = 4;
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'round', 'path.delay_beats': d, 'path.window': 0, 'path.voice': 'clips',
    'timing.cooldown': 0, 'timing.synchronized': true, 'timing.beat': 1, 'timing.hold_min': 1, 'timing.hold_max': 1,
    'timing.recency': 0, 'timing.novelty': 0 });
  const s = new Scheduler(recs, p, N, 1);
  const seqs = Array.from({ length: N }, () => []);
  for (let t = 0; t < 80; t++) { s.tick(t); s.onScreen().forEach((c, k) => seqs[k].push(c)); }
  for (let k = 1; k < N; k++) for (let n = k * d; n < 80; n++) assert.equal(seqs[k][n], seqs[0][n - k * d], `panel ${k} step ${n}`);
  // and the unique-on-screen rule holds in clips voice
  for (let n = 0; n < 80; n++) { const row = seqs.map((q) => q[n]); assert.equal(new Set(row).size, N); }
  assert.equal(seqs[0][1] !== seqs[0][0], true);
});

test('round with tags voice: later panels play different but related clips', () => {
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'round', 'path.voice': 'tags', 'path.delay_beats': 2, 'path.window': 30,
    'timing.cooldown': 0, 'timing.synchronized': true, 'timing.beat': 1, 'timing.hold_min': 1, 'timing.hold_max': 1, 'relation.temperature': 0 });
  const s = new Scheduler(recs, p, 3, 1);
  const seqs = [[], [], []];
  for (let t = 0; t < 40; t++) { s.tick(t); s.onScreen().forEach((c, k) => seqs[k].push(c)); }
  let same = 0, sim = 0, base = 0;
  for (let n = 4; n < 40; n++) {
    if (seqs[1][n] === seqs[0][n - 2]) same++;
    sim += affinity(recs[seqs[1][n]], recs[seqs[0][n - 2]], weightsFrom(p));
    base += affinity(recs[seqs[1][n]], recs[seqs[0][(n * 7) % 40]], weightsFrom(p));
  }
  assert.equal(same, 0, 'never the same clip as the reference');
  assert.ok(sim > base, 'resembles the reference more than a random leader clip');
});

test('playlist exhausts the pool before repeating', () => {
  const small = recs.slice(0, 60);
  const p = params({ 'path.shape': 'playlist', 'timing.cooldown': 0, 'path.window': 0, 'timing.hold_min': 0.5, 'timing.hold_max': 0.5, 'timing.stagger': 0 });
  const s = new Scheduler(small, p, 3, 1);
  const L = s.order.length;
  const seen = [];
  for (let t = 0; seen.length < L + 10 && t < 400; t += 0.5) for (const c of s.tick(t)) seen.push(c.clip);
  assert.equal(new Set(seen.slice(0, L)).size, L, 'first pass has no repeats');
  assert.equal(playlistPosition(1, 10, 2), 3, 'step 2 is nudged to 3 so it is coprime with 10');
  for (const [L2, st] of [[10, 2], [12, 4], [7, 3]]) assert.equal(new Set(Array.from({ length: L2 }, (_, c) => playlistPosition(c, L2, st))).size, L2);
});

test('follow keeps panels beside their left neighbour in the order', () => {
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'follow', 'path.window': 0, 'timing.cooldown': 0, 'timing.hold_min': 1, 'timing.hold_max': 1, 'timing.stagger': 0 });
  const s = new Scheduler(recs, p, 4, 1);
  for (let t = 0; t < 30; t++) s.tick(t);
  const pos = s.onScreen().map((c) => s.posOf[c]);
  for (let k = 1; k < 4; k++) assert.ok(Math.abs(pos[k] - pos[k - 1]) <= 3, JSON.stringify(pos));
});

test('stop freezes a panel; hold keeps it', () => {
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'sequential', 'path.wrap': false, 'path.on_meet': 'stop', 'path.window': 0, 'path.step': 50,
    'timing.cooldown': 0, 'timing.hold_min': 1, 'timing.hold_max': 1, 'timing.stagger': 0 });
  const s = new Scheduler(recs, p, 2, 1);
  for (let t = 0; t < 60; t++) s.tick(t);
  assert.ok(s.panels.every((q) => q.stopped));
  const a = s.onScreen();
  for (let t = 60; t < 90; t++) s.tick(t);
  assert.deepEqual(s.onScreen(), a);
});

function meanAffinity(snaps, w) {
  let sum = 0, cnt = 0;
  for (const row of snaps) for (let i = 0; i < row.length; i++) for (let j = i + 1; j < row.length; j++) { sum += affinity(recs[row[i]], recs[row[j]], w); cnt++; }
  return sum / cnt;
}

test('relation sign: negative strength repels, positive attracts, relative to random baseline', () => {
  const w = weightsFrom(params());
  const run = (S) => meanAffinity(simulate(params({ 'relation.strength': S, 'relation.temperature': 0.3, 'timing.hold_min': 1, 'timing.hold_max': 2, 'timing.cooldown': 5 }), 5, 400, { dt: 1 }).snaps.filter((_, i) => i > 20), w);
  const base = run(0), pos = run(3), neg = run(-3);
  assert.ok(pos > base + 0.08, `pos ${pos} vs base ${base}`);
  assert.ok(neg < base - 0.08, `neg ${neg} vs base ${base}`);
});

test('independence 1 ignores relation', () => {
  const w = weightsFrom(params());
  const run = (ind) => meanAffinity(simulate(params({ 'relation.strength': 4, 'relation.temperature': 0.2, 'relation.independence': ind, 'timing.hold_min': 1, 'timing.hold_max': 2, 'timing.cooldown': 5 }), 5, 400, { dt: 1 }).snaps.slice(20), w);
  assert.ok(run(0) > run(1) + 0.08);
});

test('per-attribute contrast changes the environments on screen', () => {
  const pol = polarity['relation.contrast_environment'];
  const spread = (snaps) => { let s = 0, c = 0; for (const row of snaps) for (let i = 0; i < row.length; i++) for (let j = i + 1; j < row.length; j++) { const a = pol(recs[row[i]]), b = pol(recs[row[j]]); if (Number.isFinite(a) && Number.isFinite(b)) { s += Math.abs(a - b); c++; } } return s / c; };
  const base = { 'relation.temperature': 0.2, 'timing.hold_min': 1, 'timing.hold_max': 2, 'timing.cooldown': 5 };
  const off = spread(simulate(params(base), 2, 300, { dt: 1 }).snaps.slice(10));
  const on = spread(simulate(params({ ...base, 'relation.contrast_environment': true }), 2, 300, { dt: 1 }).snaps.slice(10));
  assert.ok(on > off + 0.2, `on ${on} off ${off}`);
  // city vs nature: with 2 panels one of the two is nature and the other is not, most of the time
  const snaps = simulate(params({ ...base, 'relation.contrast_environment': true }), 2, 300, { dt: 1 }).snaps.slice(10);
  const mixed = snaps.filter((r) => { const e = r.map((c) => recs[c].environment); return e.includes('nature') && e.some((x) => x !== 'nature' && x !== 'domestic'); }).length;
  assert.ok(mixed / snaps.length > 0.5, 'nature against built environments ' + mixed / snaps.length);
});

test('no duplicate clip on screen at once, cooldown honoured', () => {
  for (const shape of ['random', 'sequential', 'converge', 'pingpong', 'round', 'follow', 'playlist']) {
    const p = params({ 'path.shape': shape, 'order.axis': 'captured_at', 'timing.hold_min': 0.5, 'timing.hold_max': 1.5, 'timing.cooldown': 0, 'path.window': 4 });
    const { snaps } = simulate(p, 8, 200, { dt: 0.25 });
    for (const row of snaps) assert.equal(new Set(row.filter((c) => c >= 0)).size, row.filter((c) => c >= 0).length, shape);
    assert.ok(snaps[0].every((c) => c >= 0), 'all panels filled immediately');
  }
  const cd = 40;
  const p = params({ 'timing.hold_min': 2, 'timing.hold_max': 4, 'timing.cooldown': cd, 'relation.strength': 2 });
  const { log } = simulate(p, 5, 600, { dt: 0.5 });
  const ends = new Map();
  for (const c of log) {
    if (c.prev >= 0) ends.set(c.prev, c.t);
    if (ends.has(c.clip)) assert.ok(c.t - ends.get(c.clip) >= cd - 1e-6, `clip returned after ${c.t - ends.get(c.clip)}s`);
  }
});

test('pool smaller than panel count still fills every panel without crashing', () => {
  const s = new Scheduler(recs.slice(0, 3), params(), 6, 1);
  s.tick(0);
  assert.ok(s.onScreen().every((c) => c >= 0));
  const e = new Scheduler([], params(), 3, 1);
  assert.deepEqual(e.tick(0), []);
});

test('changing the pool filter replaces excluded on-screen clips immediately', () => {
  const s = new Scheduler(recs, params(), 4, 1);
  s.tick(0);
  const tag = recs[s.onScreen()[0]].tokens.values().next().value;
  s.setParams(params({ 'source.tags_exclude': [tag] }));
  s.tick(0.01);
  for (const c of s.onScreen()) assert.ok(!recs[c].tokens.has(tag));
});

test('empty pool retires scheduled clips and refills at the same paused clock', () => {
  for (const timing of [{}, { 'timing.synchronized': true }, { 'timing.swap_interval': 3 }]) {
    const p = params({ ...timing, 'source.untagged': 'exclude' });
    const s = new Scheduler(recs, p, 3, 1);
    s.tick(0);
    const before = s.onScreen();
    assert.ok(before.every((clip) => clip >= 0));

    s.setParams({ ...p, 'source.tags_include': ['missing-tag'] });
    assert.equal(s.pool.length, 0);
    assert.deepEqual(s.tick(0), before.map((prev, panel) => ({ panel, clip: -1, prev })));
    assert.deepEqual(s.onScreen(), [-1, -1, -1]);
    assert.ok(before.every((clip) => s.lastEnd[clip] === 0));
    assert.deepEqual(s.tick(0), [], 'empty panels are retired only once');

    s.setParams(p);
    const restored = s.tick(0);
    assert.equal(restored.length, 3, 'restoration does not require advancing paused time');
    assert.ok(restored.every(({ clip, prev }) => clip >= 0 && prev === -1));
    assert.ok(s.onScreen().every((clip) => clip >= 0));
  }
});

test('synchronized changes happen on the beat grid for all panels together', () => {
  const p = params({ 'timing.synchronized': true, 'timing.beat': 2, 'timing.hold_min': 3, 'timing.hold_max': 3, 'timing.cooldown': 0 });
  const { log } = simulate(p, 4, 40, { dt: 0.25 });
  const times = [...new Set(log.filter((c) => c.t > 0).map((c) => c.t))];
  assert.ok(times.length >= 4);
  for (const t of times) assert.ok(Math.abs(t % 4) < 1e-6, 'change at t=' + t + ' is on the 4s beat grid');
  assert.ok(new Set(log.filter((c) => c.t === times[0]).map((c) => c.panel)).size >= 3, 'most panels change at the same tick');
});

test('swap interval changes one panel at a time', () => {
  const p = params({ 'timing.swap_interval': 2, 'timing.cooldown': 0 });
  const { log } = simulate(p, 4, 60, { dt: 0.25 });
  const later = log.filter((c) => c.t > 0);
  assert.ok(later.length >= 20 && later.length <= 32, String(later.length));
  assert.equal(new Set(later.map((c) => c.t)).size, later.length);
});

// ---- exclusions on adversarial records ----
const base = () => makeRaw(1)[0];
const adversarial = () => {
  const mk = (id, patch) => { const c = JSON.parse(JSON.stringify(base())); c.id = id; patch(c); return c; };
  return [
    mk('ok', () => {}),
    mk('verdict-review', (c) => { c.tags.safety.verdict = 'review'; }),
    mk('verdict-blocked', (c) => { c.tags.safety.verdict = 'BLOCKED'; }),
    mk('verdict-Clear-ws', (c) => { c.tags.safety.verdict = '  Clear '; }),
    mk('verdict-number', (c) => { c.tags.safety.verdict = 1; }),
    mk('verdict-missing', (c) => { delete c.tags.safety.verdict; }),
    mk('safety-missing', (c) => { delete c.tags.safety; }),
    mk('safety-string', (c) => { c.tags.safety = 'clear'; }),
    mk('sens-high', (c) => { c.tags.privacy.sharing_sensitivity = 'high'; }),
    mk('sens-High-ws', (c) => { c.tags.privacy.sharing_sensitivity = ' HIGH '; }),
    mk('sens-moderate', (c) => { c.tags.privacy.sharing_sensitivity = 'moderate'; }),
    mk('sens-number', (c) => { c.tags.privacy.sharing_sensitivity = 3; }),
    mk('sens-missing', (c) => { delete c.tags.privacy.sharing_sensitivity; }),
    mk('plate', (c) => { c.tags.privacy.license_plate = true; }),
    mk('plate-string', (c) => { c.tags.privacy.license_plate = 'True'; }),
    mk('plate-object', (c) => { c.tags.privacy.license_plate = {}; }),
    mk('plate-no-string', (c) => { c.tags.privacy.license_plate = 'no'; }),
    mk('minor', (c) => { c.tags.people.minors_apparent = true; }),
    mk('minor-str', (c) => { c.tags.people.minors_apparent = ' YES '; }),
    mk('minor-junk', (c) => { c.tags.people.minors_apparent = 'maybe'; }),
    mk('tags-string', (c) => { c.tags = 'outdoor'; }),
    mk('no-tags', (c) => { delete c.tags; }),
    mk('no-features', (c) => { delete c.features; }),
    mk('date-bad', (c) => { c.captured_at = 'yesterday'; }),
    mk('date-number', (c) => { c.captured_at = 1500000000; }),
    mk('date-missing', (c) => { delete c.captured_at; }),
    mk('date-2001', (c) => { c.captured_at = '2001-05-05T00:00:00Z'; }),
    mk('tag-case', (c) => { c.tags.subjects = ['  TREE ']; }),
    mk('subjects-junk', (c) => { c.tags.subjects = 'tree'; c.tags.keywords = [1, null, 'ok']; }),
  ];
};
const ids = (raw, over) => { const r = buildRecords(raw); return new Set(Array.from(filterPool(r, params(over)), (i) => r[i].id)); };

test('normalizeClip rejects unusable records', () => {
  assert.equal(normalizeClip(null), null); assert.equal(normalizeClip('x'), null); assert.equal(normalizeClip({}), null);
  assert.equal(normalizeClip({ id: 5, video: 'a' }), null); assert.equal(normalizeClip({ id: 'a' }), null);
  const r = buildRecords([...adversarial(), { id: 'ok', video: 'dup.mp4' }, 7, null]);
  assert.equal(r.rejected, 3);
  assert.equal(r.length, adversarial().length);
});

test('exclusions: safety verdict', () => {
  const s = ids(adversarial(), {});
  for (const bad of ['verdict-review', 'verdict-blocked', 'verdict-number', 'safety-string', 'tags-string']) assert.ok(!s.has(bad), bad);
  assert.ok(s.has('ok') && s.has('verdict-Clear-ws'), 'case/whitespace variants of clear are accepted');
  assert.ok(s.has('verdict-missing') && s.has('safety-missing'), 'missing = unknown follows policy include');
  const strict = ids(adversarial(), { 'source.untagged': 'exclude' });
  assert.ok(!strict.has('verdict-missing') && !strict.has('safety-missing') && !strict.has('no-tags'));
  assert.ok(strict.has('ok'));
  const any = ids(adversarial(), { 'source.safety': 'any' });
  assert.ok(any.has('verdict-review') && any.has('verdict-blocked'));
});

test('exclusions: sharing sensitivity limit incl. case/whitespace and malformed', () => {
  const lim = ids(adversarial(), { 'source.max_sensitivity': 'low' });
  for (const bad of ['sens-high', 'sens-High-ws', 'sens-moderate', 'sens-number']) assert.ok(!lim.has(bad), bad);
  assert.ok(lim.has('ok') && lim.has('sens-missing'));
  const mod = ids(adversarial(), { 'source.max_sensitivity': 'moderate' });
  assert.ok(!mod.has('sens-high') && !mod.has('sens-High-ws') && mod.has('sens-moderate'));
  assert.ok(!ids(adversarial(), { 'source.max_sensitivity': 'low', 'source.untagged': 'exclude' }).has('sens-missing'));
});

test('exclusions: privacy flags and minors', () => {
  const s = ids(adversarial(), {});
  for (const bad of ['plate', 'plate-string', 'plate-object', 'minor', 'minor-str', 'minor-junk']) assert.ok(!s.has(bad), bad);
  assert.ok(s.has('plate-no-string'));
  const off = ids(adversarial(), { 'source.exclude_privacy': [], 'source.exclude_minors': false });
  assert.ok(off.has('plate') && off.has('minor'));
  assert.ok(!ids(adversarial(), { 'source.exclude_privacy': ['readable_text', 'license_plate'] }).has('plate'));
});

test('exclusions: date range, tags include/exclude', () => {
  const y = ids(adversarial(), { 'source.year_min': 2010 });
  assert.ok(!y.has('date-2001') && !y.has('date-bad') && !y.has('date-number'));
  assert.ok(y.has('date-missing') && y.has('ok'));
  assert.ok(!ids(adversarial(), { 'source.year_min': 2010, 'source.untagged': 'exclude' }).has('date-missing'));
  const all = ids(adversarial(), { 'source.year_min': 1990, 'source.year_max': 2040 });
  assert.ok(all.has('date-2001') && all.has('date-bad'));
  const exc = ids(adversarial(), { 'source.tags_exclude': ['tree'] });
  assert.ok(!exc.has('tag-case'));
  const inc = ids(adversarial(), { 'source.tags_include': ['tree'] });
  assert.ok(inc.has('tag-case'));
});

test('performance: scheduling one change on 6,500 clips is a few ms (CPU time, so machine load does not matter)', () => {
  const cpu = () => { const u = process.cpuUsage(); return (u.user + u.system) / 1000; };
  const big = makeRecords(6500, 11);
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'random', 'relation.strength': 2, 'relation.contrast_environment': true, 'timing.hold_min': 0.5, 'timing.hold_max': 0.5 });
  let t0 = cpu();
  const s = new Scheduler(big, p, 16, 5);
  const setup = cpu() - t0;
  s.tick(0);
  const times = [];
  for (let t = 1; t < 200; t++) { const a = cpu(); const ch = s.tick(t); const b = cpu(); if (ch.length) times.push((b - a) / ch.length); }
  times.sort((a, b) => a - b);
  const p95 = times[Math.floor(times.length * 0.95)];
  console.log(`  setup ${setup.toFixed(0)} ms cpu, per-change median ${times[times.length >> 1].toFixed(3)} ms, p95 ${p95.toFixed(3)} ms (n=${times.length})`);
  assert.ok(times[times.length >> 1] < 2, 'median ' + times[times.length >> 1]);
  assert.ok(p95 < 5, 'p95 ' + p95);
  for (const shape of ['sequential', 'converge', 'round', 'playlist', 'follow']) {
    const s2 = new Scheduler(big, { ...p, 'path.shape': shape, 'path.window': 100 }, 16, 5);
    s2.tick(0); const a = cpu(); for (let t = 1; t < 100; t++) s2.tick(t * 1);
    assert.ok((cpu() - a) / 99 < 20, shape);
  }
  assert.ok(setup < 800, 'setup ' + setup);
});

test('windows do not wrap across the ends for non-cyclic paths (converge picks near the oldest end)', () => {
  const p = params({ 'order.axis': 'captured_at', 'path.shape': 'converge', 'path.window': 3, 'timing.cooldown': 0, 'relation.temperature': 2 });
  for (let seed = 1; seed < 40; seed++) {
    const s = new Scheduler(recs, p, 2, seed);
    s.tick(0);
    const pos = s.onScreen().map((c) => s.posOf[c]);
    assert.ok(pos[0] <= 3, `head at ${pos[0]}`);
    assert.ok(pos[1] >= s.order.length - 4, `tail at ${pos[1]}`);
  }
});

test('pool exactly as large as the panel count: re-picking never introduces duplicates', () => {
  const s = new Scheduler(recs.slice(0, 5), params({ 'timing.cooldown': 20 }), 5, 2);
  for (let t = 0; t < 400; t += 0.5) {
    if (t % 25 === 0) s.reset(t);
    s.tick(t);
    const on = s.onScreen();
    assert.equal(new Set(on).size, 5, `t=${t}`);
  }
});

test('reseed gives a reproducible run regardless of what happened before', () => {
  const p = params({ 'relation.strength': 1 });
  const run = (warm) => {
    const s = new Scheduler(recs, p, 4, 99);
    for (let t = 0; t < warm; t += 0.5) s.tick(t);
    s.reseed(1234);
    const out = [];
    for (let t = 1000; t < 1100; t += 0.5) for (const c of s.tick(t)) out.push([t - 1000, c.panel, c.clip]);
    return out;
  };
  assert.deepEqual(run(0), run(60));
  assert.deepEqual(run(0), run(300));
});
