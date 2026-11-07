import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecords, filterPool, Scheduler } from '../../app/engine.js';
import { SPEECH_FLAGS, SPEECH_POLICIES, parseAudioInfo, hasSpeech, speechVerdict, clipGain } from '../../app/speech.js';
import { defaults, byId, coerce, encodeShare, decodeShare, defaultConfig, randomizeValues } from '../../app/params.js';
import { PRESETS, applyPreset } from '../../app/presets.js';
import { mulberry32 } from '../../app/engine.js';
import { makeRaw, params } from './helpers.mjs';

const A = (o) => ({ screened: true, speech: false, words: 0, flags: [], low_confidence: false, ...o });
function recs() {
  const raw = makeRaw(60, 11);
  raw.forEach((c, i) => {
    if (i % 3 === 1) c.audio = A({ speech: true, words: 12 });                 // speech
    else if (i % 12 === 0) c.audio = A({ flags: [SPEECH_FLAGS[(i / 12) % 5]] }); // a flag without speech === true
    else if (i % 12 === 2) delete c.audio;                                    // never screened
    else if (i % 12 === 5) c.audio = A({ screened: false });                  // screening not done
    else c.audio = A();                                                       // clean
  });
  return buildRecords(raw);
}

test('policy registry: three policies, default mute, never randomized, mute_unscreened default on', () => {
  assert.deepEqual(SPEECH_POLICIES, ['play', 'mute', 'exclude']);
  assert.deepEqual(byId['audio.speech_policy'].options, SPEECH_POLICIES);
  assert.equal(defaults()['audio.speech_policy'], 'mute');
  assert.equal(defaults()['audio.mute_unscreened'], true);
  assert.equal(byId['audio.speech_policy'].randomizable, false);
  assert.equal(byId['audio.mute_unscreened'].randomizable, false);
  for (let seed = 1; seed < 40; seed++) {
    const v = randomizeValues({ ...defaults(), 'audio.speech_policy': 'exclude', 'audio.mute_unscreened': true }, [], mulberry32(seed));
    assert.equal(v['audio.speech_policy'], 'exclude'); assert.equal(v['audio.mute_unscreened'], true);
  }
  assert.equal(coerce('audio.speech_policy', 'shout').ok, false);
});

test('audio info parsing: cautious about malformed data, no transcript is kept', () => {
  assert.equal(parseAudioInfo(undefined).present, false);
  assert.equal(parseAudioInfo(undefined).screened, false);
  assert.equal(parseAudioInfo(A({ speech: true })).speech, true);
  assert.equal(parseAudioInfo({ screened: 'yes', speech: false }).screened, false, 'only a real true counts as screened');
  assert.equal(parseAudioInfo({ screened: true, speech: 'maybe' }).speech, true, 'malformed speech counts as speech');
  assert.equal(parseAudioInfo({ screened: true, speech: false, flags: 'email_like' }).speech, true, 'malformed flags count as speech');
  assert.deepEqual(parseAudioInfo({ screened: true, speech: false, flags: [' Email_Like ', 7, ''] }).flags, ['email_like']);
  assert.ok(!('transcript' in parseAudioInfo({ screened: true, transcript: 'hello' })));
});

test('flags: number_sequence, email_like, introduces_self, possible_name, long_speech all count as speech', () => {
  assert.equal(SPEECH_FLAGS.length, 5);
  for (const f of SPEECH_FLAGS) {
    const [r] = buildRecords([{ id: 'a', video: 'a.mp4', audio: A({ flags: [f] }) }]);
    assert.equal(hasSpeech(r), true, f);
    assert.equal(speechVerdict(r, 'mute', false).muted, true, f + ' muted under mute');
    assert.equal(speechVerdict(r, 'exclude', false).excluded, true, f + ' excluded under exclude');
    assert.equal(speechVerdict(r, 'play', false).muted, false, f + ' plays under play');
  }
  const [clean] = buildRecords([{ id: 'b', video: 'b.mp4', audio: A() }]);
  assert.deepEqual(speechVerdict(clean, 'exclude', true), { excluded: false, muted: false, reason: '' });
});

test('exclude: pool filtering removes every speech clip (and only them); play / mute keep them', () => {
  const records = recs();
  const speechy = new Set(records.filter(hasSpeech).map((r) => r.i));
  assert.ok(speechy.size >= 15 && speechy.size < 45);
  const pool = (policy) => new Set(filterPool(records, params({ 'audio.speech_policy': policy })));
  const ex = pool('exclude');
  for (const r of records) assert.equal(ex.has(r.i), !speechy.has(r.i), r.id);
  assert.equal(pool('mute').size, records.length);
  assert.equal(pool('play').size, records.length);
  assert.equal(ex.size, records.length - speechy.size);
});

test('exclude: the scheduler never puts a speech clip on a panel, over a long run, for every path shape', () => {
  const records = recs();
  for (const shape of ['random', 'sequential', 'converge', 'round', 'playlist', 'follow']) {
    const s = new Scheduler(records, params({ 'audio.speech_policy': 'exclude', 'path.shape': shape, 'timing.cooldown': 0 }), 5, 3);
    for (let t = 0; t < 300; t += 0.5) {
      s.tick(t);
      for (const ci of s.onScreen()) if (ci >= 0) assert.equal(hasSpeech(records[ci]), false, `${shape}: ${records[ci].id} on screen`);
    }
  }
});

test('switching the policy to exclude replaces a speech clip that is already on screen', () => {
  const records = recs();
  const s = new Scheduler(records, params({ 'audio.speech_policy': 'play', 'timing.hold_min': 50, 'timing.hold_max': 60 }), 6, 5);
  for (let t = 0; t < 3; t += 0.5) s.tick(t);
  assert.ok(s.onScreen().some((ci) => hasSpeech(records[ci])), 'precondition: some speech on screen');
  s.setParams(params({ 'audio.speech_policy': 'exclude', 'timing.hold_min': 50, 'timing.hold_max': 60 }));
  for (let t = 3; t < 8; t += 0.5) s.tick(t);
  for (const ci of s.onScreen()) assert.equal(hasSpeech(records[ci]), false);
});

test('mute: gain is exactly 0 for speech clips and flagged clips, normal for clean clips; play restores it', () => {
  const records = recs();
  const e = (o) => params({ 'audio.mute_unscreened': false, ...o });
  let muted = 0, loud = 0;
  for (const r of records) {
    const g = clipGain(r, e({ 'audio.speech_policy': 'mute' }));
    if (hasSpeech(r)) { assert.equal(g, 0, r.id); muted++; } else { assert.ok(g > 0, r.id); loud++; }
    assert.ok(clipGain(r, e({ 'audio.speech_policy': 'play' })) > 0, r.id + ' play');
  }
  assert.ok(muted > 5 && loud > 5);
  const clean = records.find((r) => !hasSpeech(r) && r.audio.screened && Number.isFinite(r.loudness));
  const g = clipGain(clean, e({ 'audio.speech_policy': 'mute', 'audio.norm_target_db': -30 }));
  assert.ok(Math.abs(g - Math.pow(10, Math.min(20, -30 - clean.loudness) / 20)) < 1e-9, 'loudness normalisation still applies');
  assert.equal(clipGain({ ...clean, hasAudio: false }, e({ 'audio.speech_policy': 'play' })), 0);
});

test('mute_unscreened: unscreened clips (screened false OR no audio record) are silent while on, audible when off', () => {
  const records = recs();
  const un = records.filter((r) => !r.audio.screened);
  assert.ok(un.length >= 5 && un.some((r) => !r.audio.present) && un.some((r) => r.audio.present));
  for (const r of un) {
    assert.equal(clipGain(r, params({ 'audio.speech_policy': 'play', 'audio.mute_unscreened': true })), 0, r.id);
    assert.ok(clipGain(r, params({ 'audio.speech_policy': 'play', 'audio.mute_unscreened': false })) > 0, r.id);
    assert.equal(speechVerdict(r, 'mute', true).reason, 'unscreened');
  }
  // never filters the pool
  assert.equal(filterPool(records, params({ 'audio.mute_unscreened': true })).length, records.length);
});

test('no preset or scene can silently re-enable speech or sound for unscreened clips', () => {
  for (const pr of PRESETS) {
    assert.ok(!('audio.speech_policy' in pr.values) && !('audio.mute_unscreened' in pr.values), pr.id + ' sets the speech policy');
    assert.ok(!pr.resets.includes('audio'), pr.id + ' resets AUDIO');
    for (const start of ['mute', 'exclude', 'play']) for (const un of [true, false]) {
      const out = applyPreset({ ...defaults(), 'audio.speech_policy': start, 'audio.mute_unscreened': un }, pr);
      assert.equal(out['audio.speech_policy'], start, `${pr.id} changed the policy from ${start}`);
      assert.equal(out['audio.mute_unscreened'], un, `${pr.id} changed mute_unscreened`);
    }
  }
});

test('the policy round-trips through the share URL and defaults are left out of it', () => {
  const c = defaultConfig();
  assert.ok(!decodeShare('#' + encodeShare(c)) || decodeShare('#' + encodeShare(c)).values['audio.speech_policy'] === 'mute');
  for (const pol of SPEECH_POLICIES) for (const un of [true, false]) {
    const k = defaultConfig(); k.values['audio.speech_policy'] = pol; k.values['audio.mute_unscreened'] = un;
    assert.deepEqual(decodeShare('#' + encodeShare(k)).values['audio.speech_policy'], pol);
    assert.equal(decodeShare('#' + encodeShare(k)).values['audio.mute_unscreened'], un);
  }
});
