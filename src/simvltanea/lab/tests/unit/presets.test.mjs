import test from 'node:test';
import assert from 'node:assert/strict';
import { PRESETS, presetById, validatePreset, applyPreset } from '../../app/presets.js';
import { defaults, coerce, byId } from '../../app/params.js';
import { Scheduler } from '../../app/engine.js';
import { makeRecords } from './helpers.mjs';

const REQUIRED = ['random', 'chronological', 'reverse_chronological', 'oldest_meets_newest', 'newest_meets_oldest', 'round_clips', 'round_tags',
  'opposites', 'city_vs_nature', 'near_vs_far', 'drift', 'sticky', 'magnetic', 'calm_to_intense', 'dark_to_light', 'rainbow'];

test('all required presets exist, ids unique, plus combined scenes', () => {
  for (const id of REQUIRED) assert.ok(presetById[id], id);
  assert.equal(new Set(PRESETS.map((p) => p.id)).size, PRESETS.length);
  assert.ok(PRESETS.filter((p) => p.kind === 'scene').length >= 3);
  for (const p of PRESETS) assert.ok(p.label && p.description);
});

test('every preset validates against the registry', () => {
  for (const p of PRESETS) assert.deepEqual(validatePreset(p), [], p.id);
  assert.ok(validatePreset({ id: 'x', resets: ['order'], values: { 'nope': 1, 'zoom.z1': 99, 'path.shape': 'zzz' } }).length === 3);
});

test('applying a preset resets its modules and keeps the others', () => {
  const v = { ...defaults(), 'relation.strength': 3, 'audio.master': 1.3, 'layout.panels': 9, 'timing.hold_min': 20 };
  const o = applyPreset(v, presetById.chronological);
  assert.equal(o['order.axis'], 'captured_at'); assert.equal(o['relation.strength'], 0); assert.equal(o['timing.hold_min'], defaults()['timing.hold_min']);
  assert.equal(o['audio.master'], 1.3); assert.equal(o['layout.panels'], 9);
  const sc = applyPreset(v, presetById.scene_triptych_time);
  assert.equal(sc['layout.panels'], 3); assert.equal(sc['audio.master'], 1.3);
  for (const id of Object.keys(sc)) assert.equal(coerce(id, sc[id]).ok, true);
  assert.notEqual(o, v);
});

test('every preset drives the scheduler: panels fill, no duplicates, deterministic', () => {
  const recs = makeRecords(300, 3);
  for (const pr of PRESETS) {
    const run = () => {
      const p = applyPreset(defaults(), pr);
      const s = new Scheduler(recs, p, Math.max(2, p['layout.panels']), 4);
      const log = [];
      for (let t = 0; t < 120; t += 0.5) { for (const c of s.tick(t)) log.push([t, c.panel, c.clip]); const on = s.onScreen(); assert.ok(on.every((c) => c >= 0), pr.id + ' filled'); assert.equal(new Set(on).size, on.length, pr.id + ' unique'); }
      return log;
    };
    const a = run();
    assert.deepEqual(a, run(), pr.id + ' deterministic');
    assert.ok(a.length >= 2, pr.id + ' produced changes');
  }
});

test('preset spec facts', () => {
  assert.equal(presetById.round_clips.values['path.shape'], 'round');
  assert.equal(presetById.oldest_meets_newest.values['path.shape'], 'converge');
  assert.equal(presetById.reverse_chronological.values['order.direction'], 'desc');
  assert.ok(byId['path.shape'].options.includes(presetById.round_tags.values['path.shape']));
});
