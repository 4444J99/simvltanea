import test from 'node:test';
import assert from 'node:assert/strict';
import { PARAMS, MODULES, byId, defaults, coerce, defaultConfig, sanitizeConfig, toJSON, fromJSON, encodeShare, decodeShare,
  effectiveValues, randomizeValues, lfo, configReferenceMarkdown } from '../../app/params.js';
import { mulberry32 } from '../../app/engine.js';

test('registry entries are complete and unique', () => {
  const ids = new Set();
  for (const p of PARAMS) {
    assert.ok(!ids.has(p.id), 'duplicate ' + p.id); ids.add(p.id);
    assert.ok(MODULES.some((m) => m.id === p.module), p.id + ' module');
    assert.ok(['float', 'int', 'enum', 'bool', 'multi', 'list'].includes(p.type));
    for (const k of ['label', 'description', 'default', 'unit', 'modulatable']) assert.ok(k in p, `${p.id} lacks ${k}`);
    assert.ok(p.description.length > 5 && p.label.length > 0);
    if (p.type === 'float' || p.type === 'int') {
      assert.ok(p.min < p.max && p.step > 0, p.id);
      assert.ok(p.default >= p.min && p.default <= p.max, p.id + ' default in range');
    }
    if (p.type === 'enum') assert.ok(p.options.includes(p.default), p.id);
    assert.equal(coerce(p.id, p.default).ok, true, p.id + ' default coerces');
    assert.deepEqual(coerce(p.id, p.default).value, p.default, p.id + ' default stable');
  }
  for (const m of MODULES) assert.ok(PARAMS.some((p) => p.module === m.id), m.id + ' empty');
});

test('spec parameters exist with the required defaults', () => {
  const d = defaults();
  assert.equal(d['zoom.z1'], 8); assert.equal(d['zoom.gamma'], 0.6);
  assert.equal(d['layout.radius'], 0);
  assert.deepEqual([byId['layout.panels'].min, byId['layout.panels'].max], [1, 16]);
  assert.deepEqual([byId['relation.strength'].min, byId['relation.strength'].max], [-4, 4]);
  assert.ok(byId['audio.master'] && byId['audio.limiter'] && byId['reveal.action'] && byId['source.seed']);
  for (const f of PARAMS.filter((p) => p.type === 'float')) assert.equal(f.modulatable, true);
});

test('coerce clamps numbers and rejects junk', () => {
  assert.equal(coerce('layout.panels', 99).value, 16);
  assert.equal(coerce('layout.panels', 0).value, 1);
  assert.equal(coerce('layout.panels', '5').value, 5);
  assert.equal(coerce('layout.panels', 'x').ok, false);
  assert.equal(coerce('layout.panels', NaN).ok, false);
  assert.equal(coerce('path.shape', 'bogus').ok, false);
  assert.equal(coerce('path.wrap', 'yes').ok, false);
  assert.equal(coerce('nope', 1).ok, false);
  assert.deepEqual(coerce('source.tags_include', ' Tree, SKY ,, ').value, ['tree', 'sky']);
  assert.deepEqual(coerce('layout.split_custom', '3, x, 1').value, [3, 1]);
  assert.deepEqual(coerce('audio.muted_panels', [3, 1, 99]).value, [1, 3]);
});

test('config round trips through JSON', () => {
  const c = defaultConfig();
  c.values['zoom.z1'] = 12.5; c.values['path.shape'] = 'converge'; c.values['source.tags_include'] = ['tree'];
  c.values['audio.muted_panels'] = [2, 4];
  c.mods['relation.strength'] = { on: true, shape: 'triangle', rate: 0.3, depth: 0.5 };
  c.bypass = ['audio']; c.locks = ['zoom.gamma'];
  assert.deepEqual(fromJSON(toJSON(c)), c);
});

test('config round trips through the share hash (incl. unicode tags)', () => {
  const c = defaultConfig();
  c.values['order.axis'] = 'hue'; c.values['layout.panels'] = 11; c.values['source.tags_exclude'] = ['café', '犬'];
  c.mods['zoom.gamma'] = { on: true, shape: 'random', rate: 1.5, depth: 0.2 };
  c.bypass = ['reveal']; c.locks = ['layout.panels'];
  const h = encodeShare(c);
  assert.ok(/^p=[A-Za-z0-9_-]+$/.test(h));
  assert.deepEqual(decodeShare('#' + h), c);
  assert.equal(decodeShare('#p=@@@'), null);
  assert.equal(decodeShare(''), null);
  assert.ok(h.length < encodeShare(sanitizeConfig({ values: Object.fromEntries(PARAMS.map((p) => [p.id, p.type === 'bool' ? !p.default : p.default])) })).length);
});

test('sanitizeConfig drops unknown ids and invalid values', () => {
  const c = sanitizeConfig({ values: { 'zoom.z1': 'abc', 'bogus.x': 1, 'layout.panels': 40 }, mods: { 'layout.panels': { on: true }, 'zoom.z1': { on: true, shape: 'zzz', rate: 99, depth: -1 } }, bypass: ['audio', 'nope'] });
  assert.equal(c.values['zoom.z1'], 8); assert.equal(c.values['layout.panels'], 16);
  assert.ok(!c.mods['layout.panels']); assert.equal(c.mods['zoom.z1'].shape, 'sine');
  assert.equal(c.mods['zoom.z1'].rate, 5); assert.equal(c.mods['zoom.z1'].depth, 0);
  assert.deepEqual(c.bypass, ['audio']);
});

test('LFOs stay in [-1,1], are deterministic and move', () => {
  for (const s of ['sine', 'triangle', 'random', 'square']) {
    let lo = 9, hi = -9;
    for (let t = 0; t < 50; t += 0.07) { const v = lfo(s, t, 0.5, 'k'); assert.ok(v >= -1 && v <= 1); lo = Math.min(lo, v); hi = Math.max(hi, v); assert.equal(v, lfo(s, t, 0.5, 'k')); }
    assert.ok(hi - lo > 0.5, s + ' moves');
  }
});

test('effectiveValues: modulation stays in range; bypass restores defaults', () => {
  const c = defaultConfig();
  c.values['relation.strength'] = 3.9; c.mods['relation.strength'] = { on: true, shape: 'sine', rate: 1, depth: 1 };
  for (let t = 0; t < 5; t += 0.1) { const v = effectiveValues(c, t)['relation.strength']; assert.ok(v >= -4 && v <= 4); }
  c.values['relation.strength'] = 0;
  assert.notEqual(effectiveValues(c, 0.1)['relation.strength'], effectiveValues(c, 0.4)['relation.strength']);
  c.values['relation.strength'] = 3.9;
  c.values['audio.master'] = 1.2; c.bypass = ['audio', 'relation'];
  assert.equal(effectiveValues(c, 1)['audio.master'], 0.8);
  assert.equal(effectiveValues(c, 1)['relation.strength'], 0);
});

test('randomize respects locks, ranges and the non-randomizable set', () => {
  const base = defaults();
  const rng = mulberry32(5);
  const out = randomizeValues(base, ['zoom.gamma', 'layout.panels'], rng);
  assert.equal(out['zoom.gamma'], base['zoom.gamma']); assert.equal(out['layout.panels'], base['layout.panels']);
  for (const p of PARAMS) {
    if (!p.randomizable) assert.deepEqual(out[p.id], base[p.id], p.id);
    assert.equal(coerce(p.id, out[p.id]).ok, true);
    assert.deepEqual(coerce(p.id, out[p.id]).value, out[p.id]);
  }
  assert.equal(out['layout.radius'], 0);
  let changed = 0; for (const p of PARAMS) if (JSON.stringify(out[p.id]) !== JSON.stringify(base[p.id])) changed++;
  assert.ok(changed > 15);
  for (const s of [1, 2, 3, 4, 5]) assert.equal(randomizeValues(base, [], mulberry32(s))['source.safety'], 'clear');
});

test('config reference mentions every parameter', () => {
  const md = configReferenceMarkdown();
  for (const p of PARAMS) assert.ok(md.includes('`' + p.id + '`'), p.id);
});

test('LAB.md configuration table is in sync with the registry (docs cannot drift)', async () => {
  const { execFileSync } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const script = fileURLToPath(new URL('../../scripts/gen_config_reference.mjs', import.meta.url));
  const out = execFileSync(process.execPath, [script, '--check'], { encoding: 'utf8' });
  assert.match(out, /up to date/);
});
