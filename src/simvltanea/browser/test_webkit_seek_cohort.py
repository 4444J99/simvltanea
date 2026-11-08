"""Exact-source admission and isolated verdict rules for the controlled seek cohort."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


HELPER = Path(__file__).with_name('verify_webkit_seek_cohort.js')

FIXTURE = r'''
const api = require(process.argv[1]);
const crypto = require('node:crypto');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const roles = ['peer-1', 'peer-2', 'sibling-resident', 'target', 'predecessor', 'sibling-incoming'];
const slots = ['loop-1', 'loop-2', 'loop-3', 'loop-4', 'loop-4', 'loop-3'];
const files = new Map(), targets = [];
const original = {schema: 'simvltanea.public-demo/1', clips: []};
for (let index = 0; index < 7; index++) {
  const forward = Buffer.from(`original forward bytes ${index}`);
  const reverse = Buffer.from(`original boomerang bytes ${index}`);
  const forwardSha256 = hash(forward), sha256 = hash(reverse);
  const id = forwardSha256.slice(0, 12), variantId = sha256.slice(0, 12);
  const audio = {has_audio: false, envelope_hz: 10, rms_envelope: Array(50).fill(0),
    lufs_integrated: null, peak_dbfs: null};
  const clip = {id, file: `clips/${id}.mp4`, bytes: forward.length,
    width: 360, height: 480, orientation: 'portrait', duration_seconds: 5,
    tags: {palette: ['blue'], mood: ['quiet'], shot: 'detail'}, ...audio,
    variants: {boomerang: {id: variantId, file: `clips/${variantId}.mp4`,
      bytes: reverse.length, width: 360, height: 480, orientation: 'portrait',
      duration_seconds: 5, fps: 30, frame_count: 150, seam_offset_seconds: 2.5, ...audio}}};
  files.set(clip.file, forward); files.set(clip.variants.boomerang.file, reverse);
  original.clips.push(clip);
  if (index < 6) targets.push({id, sha256, forwardSha256, role: roles[index], slot: slots[index]});
}
const readAsset = name => {
  if (!files.has(name)) throw new Error('Missing fixture asset: ' + name);
  return files.get(name);
};
const rejected = fn => {try {fn(); return false;} catch (_) {return true;}};
'''

VERDICT = r'''
const raw = {pass: false, verdict: 'FAIL', checks: {
  completed: true, noFailure: true, fullDuration: true, enoughSamples: true,
  observationCoverage: true, jointProgress: true, decodedProgress: true,
  restingProgress: true, decodeBudget: true, validMedia: true,
  noUnexpectedPause: true, succession: false, nativeWraps: true, noErrors: true},
  samples: 1300, longestDecodedHoldMs: 137, longestJointHoldMs: 137};
const sourceCoverage = {pass: true, checks: {
  initialSet: true, targetSet: true, targetIsolation: true,
  siblingSet: true, siblingIsolation: true, siblingIncomingOverlap: true,
  preludeResources: true, preludeNativeProgress: true,
  allSourcesDecodedAndWrapped: true, finalSourcesSustained: true,
  heldComposition: true, strategiesMatch: true}};
'''

COHORT = r'''
function sourceNode(target, wall, decoded, sourceChanges) {
  const promoted = ['target', 'sibling-incoming'].includes(target.role);
  const url = `blob:http://studio.test/${target.id}`;
  const progress = {schema: 1, supported: true, live: true, foreground: true,
    running: true, url, epoch: 1, sourceChanges, changes: sourceChanges,
    mediaTime: decoded, lastChangeWall: wall, foregroundSince: 1000,
    lastForegroundChangeWall: wall, currentGapMs: 0, maxGapMs: 137, lifetimeMaxGapMs: 137};
  return {id: target.slot, item: target.id, sha: target.sha256,
    deck: promoted ? 1 : 0, birth: target.role === 'target' ? 1 : target.role === 'sibling-incoming' ? 2 : 0,
    phase: 'ACTIVE', busy: false, resting: false, current: decoded, decoded,
    callbacks: sourceChanges, paused: false, seeking: false, ready: 4, nativeError: null, progress};
}
function quartet(selected, startWall) {
  return [4.8, 4.95, .1].map((decoded, index) => {
    const wall = startWall + index * 137, changes = 100 + (wall - 1000) / 137;
    const nodes = selected.map(target => sourceNode(target, wall, decoded, changes));
    return {wall, running: true, hidden: false, audioState: 'running', nodes,
      foregroundLimit: 4, populated: 4, playing: 4, standbys: 0, maxStandbys: 1,
      progressSummary: {schema: 1, supported: true, maxGapMs: 137, suspensionCount: 0},
      decks: nodes.map(node => ({id: node.id, deck: node.deck, active: true,
        populated: true, src: node.progress.url, currentSrc: node.progress.url,
        ready: 4, paused: false, decoded, callbacks: changes, nativeError: null,
        progress: node.progress}))};
  });
}
const initial = [targets[0], targets[1], targets[2], targets[4]];
const targetCohort = targets.slice(0, 4);
const finalCohort = [targets[0], targets[1], targets[5], targets[3]];
const beforeRows = quartet(initial, 1000), targetRows = quartet(targetCohort, 1411);
const overlapRows = quartet(targetCohort, 1822).map((row, index) => {
  const source = sourceNode(targets[5], row.wall, [4.8, 4.95, .1][index], 106 + index);
  const incoming = {id: 'loop-3', deck: 1, item: targets[5].id, sha: targets[5].sha256,
    src: source.progress.url, currentSrc: source.progress.url, paused: false, ready: 4,
    decoded: source.decoded, callbacks: source.callbacks, nativeError: null,
    progress: {...source.progress, foreground: false, running: false}};
  return {...row, populated: 5, playing: 5, standbys: 1, incoming,
    slotsStable: true, peersStable: true};
});
const siblingRows = quartet(finalCohort, 2233);
const replay = {cohortOptions: {pauseBeforeSeek: true},
  prelude: {samples: [...beforeRows, ...targetRows, ...overlapRows, ...siblingRows],
    before: beforeRows[2], afterTarget: targetRows[0], afterSibling: siblingRows[0],
    targetIsolation: {slotsStable: true, peersStable: true},
    siblingIsolation: {slotsStable: true, peersStable: true},
    incomingObservations: overlapRows, siblingOverlap: overlapRows,
    strategyStart: {pauseBeforeSeek: true, assignedAt: 500}},
  strategyFinal: {pauseBeforeSeek: true},
  initialStudio: {evolving: false, loopMode: 'boomerang'},
  samples: quartet(finalCohort, 2644)};
'''


def execute(body: str):
    completed = subprocess.run(['node', '-e', FIXTURE + body, str(HELPER)],
                               capture_output=True, text=True, timeout=15)
    if completed.returncode:
        raise AssertionError(f'Node contract check failed:\n{completed.stderr}')
    return json.loads(completed.stdout)


class SeekCohortManifestTests(unittest.TestCase):
    def test_six_source_subset_preserves_original_entries_and_checks_all_twelve_assets(self):
        result = execute(r'''
const before = JSON.stringify(original), read = [];
const out = api.buildManifest(original, name => {read.push(name); return readAsset(name);}, targets);
console.log(JSON.stringify({unchanged: JSON.stringify(original) === before,
  entries: out.manifest.clips, expected: original.clips.slice(0, 6),
  read: [...new Set(read)].sort(), expectedFiles: original.clips.slice(0, 6)
    .flatMap(clip => [clip.file, clip.variants.boomerang.file]).sort(),
  schema: out.manifest.schema}));
''')
        self.assertTrue(result['unchanged'])
        self.assertEqual(result['schema'], 'simvltanea.public-demo/1')
        self.assertEqual(sorted(result['entries'], key=lambda entry: entry['id']),
                         sorted(result['expected'], key=lambda entry: entry['id']))
        self.assertEqual(result['read'], result['expectedFiles'])
        self.assertEqual(len(result['read']), 12)

    def test_initial_query_selects_exact_peers_resident_and_target_predecessor(self):
        result = execute(r'''
original.clips.reverse();
const out = api.buildManifest(original, readAsset, targets);
const {libraryClips} = require(require('node:path').join(require('node:path').dirname(process.argv[1]), 'browser.studio.js'));
const clips = libraryClips(out.manifest), params = new URLSearchParams(out.query), mix = params.get('mix');
console.log(JSON.stringify({selected: mix.slice(1).split('.').map(index => clips[Number(index)].id),
  expected: [targets[0].id, targets[1].id, targets[2].id, targets[4].id],
  family: mix[0], evolve: params.get('evolve'), loop: params.get('loop'), proof: params.get('proof')}));
''')
        self.assertEqual(result['selected'], result['expected'])
        self.assertEqual((result['family'], result['evolve'], result['loop'], result['proof']),
                         ('s', '0', 'boomerang', '1'))

    def test_every_target_and_both_asset_variants_are_required(self):
        result = execute(r'''
console.log(JSON.stringify(targets.map(target => {
  const value = structuredClone(original); value.clips = value.clips.filter(clip => clip.id !== target.id);
  const clip = original.clips.find(entry => entry.id === target.id);
  return {missingEntry: rejected(() => api.buildManifest(value, readAsset, targets)),
    missingAssets: [clip.file, clip.variants.boomerang.file].map(missing =>
      rejected(() => api.buildManifest(original, name => {
        if (name === missing) throw new Error('Missing asset');
        return readAsset(name);
      }, targets)))};
})));
''')
        self.assertEqual(result, [{'missingEntry': True, 'missingAssets': [True, True]}] * 6)

    def test_same_length_content_changes_fail_full_hash_admission_for_every_asset(self):
        result = execute(r'''
console.log(JSON.stringify(original.clips.slice(0, 6).flatMap(clip =>
  [clip.file, clip.variants.boomerang.file].map(changed =>
    rejected(() => api.buildManifest(original, name => {
      const bytes = Buffer.from(readAsset(name));
      if (name === changed) bytes[bytes.length - 1] ^= 1;
      return bytes;
    }, targets))))));
''')
        self.assertEqual(result, [True] * 12)

    def test_declared_byte_counts_must_match_each_forward_and_boomerang_asset(self):
        result = execute(r'''
console.log(JSON.stringify(targets.flatMap((target, index) => ['forward', 'boomerang'].map(kind => {
  const value = structuredClone(original);
  const asset = kind === 'forward' ? value.clips[index] : value.clips[index].variants.boomerang;
  asset.bytes++;
  return rejected(() => api.buildManifest(value, readAsset, targets));
}))));
''')
        self.assertEqual(result, [True] * 12)

    def test_invalid_full_manifest_is_rejected_even_outside_selected_cohort(self):
        result = execute(r'''
const mutations = [
  value => {value.schema = 'unknown/1';},
  value => {value.clips[6].file = '../untrusted.mp4';},
  value => {value.clips[0].variants.boomerang.frame_count = 149;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(original); mutate(value);
  return rejected(() => api.buildManifest(value, readAsset, targets));
})));
''')
        self.assertEqual(result, [True] * 3)

    def test_missing_duplicate_or_misassigned_target_roles_cannot_define_the_cohort(self):
        result = execute(r'''
const mutations = [
  value => {value.pop();},
  value => {value[5] = {...value[4]};},
  value => {value[3].role = 'peer-1';},
  value => {value[5].slot = 'loop-4';},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(targets); mutate(value);
  return rejected(() => api.buildManifest(original, readAsset, value));
})));
''')
        self.assertEqual(result, [True] * 4)


class SeekCohortVerdictTests(unittest.TestCase):
    def test_only_succession_is_omitted_from_controlled_verdict_without_mutating_raw(self):
        result = execute(VERDICT + r'''
const beforeRaw = JSON.stringify(raw), beforeCoverage = JSON.stringify(sourceCoverage);
Object.freeze(raw.checks); Object.freeze(raw); Object.freeze(sourceCoverage.checks); Object.freeze(sourceCoverage);
const out = api.controlledVerdict(raw, sourceCoverage);
console.log(JSON.stringify({out, rawUnchanged: JSON.stringify(raw) === beforeRaw,
  coverageUnchanged: JSON.stringify(sourceCoverage) === beforeCoverage,
  expectedChecks: {...Object.fromEntries(Object.entries(raw.checks).filter(([key]) => key !== 'succession')),
    sourceCoverage: true}}));
''')
        self.assertTrue(result['rawUnchanged'])
        self.assertTrue(result['coverageUnchanged'])
        self.assertTrue(result['out']['pass'])
        self.assertEqual(result['out']['verdict'], 'PASS')
        self.assertEqual(result['out']['checks'], result['expectedChecks'])
        self.assertEqual(result['out']['rawVerdict'], 'FAIL')
        self.assertEqual(list(result['out']['notApplicable']), ['succession'])

    def test_every_other_false_raw_gate_still_fails_even_if_raw_pass_claims_success(self):
        result = execute(VERDICT + r'''
console.log(JSON.stringify(Object.keys(raw.checks).filter(key => key !== 'succession').map(key => {
  const value = structuredClone(raw); value.pass = true; value.verdict = 'PASS'; value.checks[key] = false;
  const out = api.controlledVerdict(value, sourceCoverage);
  return {key, pass: out.pass, verdict: out.verdict, retained: out.checks[key]};
})));
''')
        self.assertEqual(len(result), 13)
        for report in result:
            with self.subTest(check=report['key']):
                self.assertFalse(report['pass'])
                self.assertEqual(report['verdict'], 'FAIL')
                self.assertFalse(report['retained'])

    def test_missing_or_nonboolean_required_raw_checks_cannot_gain_the_exemption(self):
        result = execute(VERDICT + r'''
console.log(JSON.stringify(Object.keys(raw.checks).flatMap(key =>
  ['missing', null, 1, 'true'].map(invalid => {
    const value = structuredClone(raw);
    if (invalid === 'missing') delete value.checks[key]; else value.checks[key] = invalid;
    return {key, invalid, pass: api.controlledVerdict(value, sourceCoverage).pass};
  }))));
''')
        self.assertEqual(len(result), 56)
        for report in result:
            with self.subTest(check=report['key'], invalid=report['invalid']):
                self.assertFalse(report['pass'])

    def test_new_raw_check_cannot_be_silently_dropped(self):
        result = execute(VERDICT + r'''
raw.checks.futureNativeGate = false;
console.log(JSON.stringify(api.controlledVerdict(raw, sourceCoverage)));
''')
        self.assertFalse(result['pass'])
        self.assertFalse(result['checks']['futureNativeGate'])

    def test_missing_empty_or_invalid_source_coverage_fails_closed(self):
        result = execute(VERDICT + r'''
const invalid = [undefined, null, {}, {pass: true}, {pass: true, checks: {}},
  {pass: false, checks: {exact: true}}, {pass: true, checks: {exact: false}},
  {pass: true, checks: {exact: 1}}, {pass: true, checks: {exact: 'true'}},
  {pass: 'true', checks: {exact: true}}];
console.log(JSON.stringify(invalid.map(value => api.controlledVerdict(raw, value).pass)));
''')
        self.assertEqual(result, [False] * 10)

    def test_each_failed_source_coverage_requirement_blocks_controlled_pass(self):
        result = execute(VERDICT + r'''
console.log(JSON.stringify(Object.keys(sourceCoverage.checks).map(key => {
  const value = structuredClone(sourceCoverage); value.checks[key] = false;
  return {key, pass: api.controlledVerdict(raw, value).pass};
})));
''')
        self.assertEqual(len(result), 12)
        self.assertTrue(all(report['pass'] is False for report in result))


class SeekCohortCoverageTests(unittest.TestCase):
    def test_exact_six_sources_overlap_and_final_fixed_cohort_prove_coverage(self):
        result = execute(COHORT + r'''
const before = JSON.stringify(replay);
const report = api.coverage(replay, targets);
console.log(JSON.stringify({report, unchanged: JSON.stringify(replay) === before}));
''')
        self.assertTrue(result['unchanged'])
        self.assertTrue(result['report']['pass'], result['report'])
        self.assertEqual(result['report']['checks'], {
            'initialSet': True, 'targetSet': True, 'targetIsolation': True,
            'siblingSet': True, 'siblingIsolation': True, 'siblingIncomingOverlap': True,
            'preludeResources': True, 'preludeNativeProgress': True,
            'allSourcesDecodedAndWrapped': True, 'finalSourcesSustained': True,
            'heldComposition': True, 'strategiesMatch': True,
        })

    def test_wrong_source_or_slot_cannot_satisfy_any_stage_identity(self):
        result = execute(COHORT + r'''
const cases = [
  ['initialSet', value => {value.prelude.before.nodes[3].sha = targets[3].sha256;}],
  ['targetSet', value => {value.prelude.afterTarget.nodes[3].item = targets[4].id;}],
  ['siblingSet', value => {value.prelude.afterSibling.nodes[2].sha = targets[2].sha256;}],
  ['siblingSet', value => {value.prelude.afterSibling.nodes[2].id = 'loop-4';}],
];
console.log(JSON.stringify(cases.map(([check, mutate]) => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets); return {check, pass: report.pass, gate: report.checks[check]};
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertFalse(report['gate'], report['check'])

    def test_peer_identity_mutations_fail_despite_claimed_isolation(self):
        result = execute(COHORT + r'''
const cases = [
  ['targetIsolation', value => {value.prelude.afterTarget.nodes[0].birth++;}],
  ['targetIsolation', value => {value.prelude.afterTarget.nodes[1].progress.epoch++;}],
  ['siblingIsolation', value => {value.prelude.afterSibling.nodes[3].birth++;}],
  ['siblingIsolation', value => {value.prelude.afterSibling.nodes[0].deck = 1;}],
  ['targetIsolation', value => {value.prelude.targetIsolation.slotsStable = false;}],
  ['siblingIsolation', value => {value.prelude.siblingIsolation.peersStable = false;}],
];
console.log(JSON.stringify(cases.map(([check, mutate]) => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets); return {check, pass: report.pass, gate: report.checks[check]};
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertFalse(report['gate'], report['check'])

    def test_every_source_needs_positive_decoded_wrap_in_prelude(self):
        result = execute(COHORT + r'''
console.log(JSON.stringify(targets.map(target => {
  const value = structuredClone(replay);
  for (const row of value.prelude.samples) for (const node of row.nodes) if (node.item === target.id) {
    node.decoded = node.progress.mediaTime = 4.8;
  }
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.allSourcesDecodedAndWrapped};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 6)

    def test_prelude_progress_cannot_replace_final_cohort_sustained_progress(self):
        result = execute(COHORT + r'''
console.log(JSON.stringify(finalCohort.map(target => {
  const value = structuredClone(replay);
  for (const row of value.samples) for (const node of row.nodes) if (node.item === target.id) {
    node.decoded = node.progress.mediaTime = 4.8;
  }
  const report = api.coverage(value, targets);
  return {pass: report.pass, prelude: report.checks.allSourcesDecodedAndWrapped,
    sustained: report.checks.finalSourcesSustained};
})));
''')
        self.assertEqual(result, [{'pass': False, 'prelude': True, 'sustained': False}] * 4)

    def test_missing_or_stale_incoming_overlap_cannot_prove_the_fifth_decoder(self):
        result = execute(COHORT + r'''
const mutations = [
  value => {value.prelude.siblingOverlap = [];},
  value => {value.prelude.siblingOverlap = value.prelude.siblingOverlap.slice(0, 1);},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.sha = targets[2].sha256;},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.currentSrc = 'blob:unrelated';},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.progress.sourceChanges = 106;},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.callbacks = 106;},
  value => {for (const row of value.prelude.siblingOverlap) {
    row.incoming.decoded = row.incoming.progress.mediaTime = 4.8;
  }},
  value => {for (const [index, row] of value.prelude.siblingOverlap.entries()) row.incoming.progress.epoch = index + 1;},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.nativeError = {code: 3};},
  value => {for (const row of value.prelude.siblingOverlap) row.incoming.progress.supported = false;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.siblingIncomingOverlap};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 10)

    def test_overlap_requires_outgoing_resident_target_identity_and_bounded_resources(self):
        result = execute(COHORT + r'''
const mutations = [
  row => {row.nodes[2].item = targets[5].id; row.nodes[2].sha = targets[5].sha256;},
  row => {row.nodes[3].birth++;},
  row => {row.nodes[3].progress.epoch++;},
  row => {row.slotsStable = false;}, row => {row.peersStable = false;},
  row => {row.populated = 6;}, row => {row.playing = 6;},
  row => {row.standbys = 2;}, row => {row.maxStandbys = 2;},
  row => {row.audioState = 'suspended';}, row => {row.hidden = true;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); value.prelude.siblingOverlap.forEach(mutate);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.siblingIncomingOverlap};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 11)

    def test_missing_or_invalid_incoming_readiness_cannot_prove_native_admission(self):
        result = execute(COHORT + r'''
const mutations = [
  incoming => {delete incoming.ready;}, incoming => {incoming.ready = NaN;},
  incoming => {incoming.ready = 5;}, incoming => {incoming.ready = '4';},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay);
  for (const row of value.prelude.siblingOverlap) mutate(row.incoming);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.siblingIncomingOverlap};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 4)

    def test_priming_is_preserved_but_only_ready_decoded_overlap_supplies_positive_proof(self):
        result = execute(COHORT + r'''
const priming = structuredClone(overlapRows[0]);
priming.wall = 1760; priming.playing = 4;
Object.assign(priming.incoming, {ready: 0, paused: true, currentSrc: '', decoded: null, callbacks: 0});
Object.assign(priming.incoming.progress, {sourceChanges: 0, changes: 0, mediaTime: null,
  lastChangeWall: null, currentGapMs: 0, maxGapMs: 0});
replay.prelude.incomingObservations = [priming, ...overlapRows];
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertTrue(result['pass'], result)
        self.assertTrue(result['checks']['siblingIncomingOverlap'])

    def test_three_qualifying_observations_and_two_decoded_advances_are_required(self):
        result = execute(COHORT + r'''
replay.prelude.siblingOverlap = overlapRows.slice(0, 2);
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertFalse(result['pass'])
        self.assertFalse(result['checks']['siblingIncomingOverlap'])

    def test_raw_priming_observations_cannot_hide_errors_resource_excess_or_wrong_ownership(self):
        result = execute(COHORT + r'''
const mutations = [
  row => {row.populated = 6;}, row => {row.playing = 6;}, row => {row.standbys = 2;},
  row => {row.incoming.nativeError = {code: 3};}, row => {row.nodes[3].nativeError = {code: 3};},
  row => {row.incoming.sha = targets[2].sha256;}, row => {row.incoming.progress.epoch++;},
  row => {row.nodes[3].birth++;}, row => {row.incoming.progress.maxGapMs = 2000;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay), raw = structuredClone(value.prelude.siblingOverlap[0]);
  raw.wall = 1760; raw.playing = 4;
  Object.assign(raw.incoming, {ready: 0, paused: true, currentSrc: '', decoded: null, callbacks: 0});
  Object.assign(raw.incoming.progress, {sourceChanges: 0, changes: 0, mediaTime: null,
    lastChangeWall: null, currentGapMs: 0, maxGapMs: 0});
  mutate(raw); value.prelude.incomingObservations = [raw, ...value.prelude.incomingObservations];
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.siblingIncomingOverlap};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 9)

    def test_qualified_overlap_cannot_be_invented_outside_raw_observations(self):
        result = execute(COHORT + r'''
const cases = [
  value => {delete value.prelude.incomingObservations;},
  value => {value.prelude.incomingObservations = value.prelude.incomingObservations.slice(0, 2);},
  value => {value.prelude.siblingOverlap = structuredClone(value.prelude.siblingOverlap);
    value.prelude.siblingOverlap[1].wall += .5;},
];
console.log(JSON.stringify(cases.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.siblingIncomingOverlap};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 3)

    def test_prelude_budget_and_native_hold_failures_are_preserved(self):
        result = execute(COHORT + r'''
const cases = [
  ['preludeResources', row => {row.populated = 6;}],
  ['preludeResources', row => {row.playing = 6;}],
  ['preludeResources', row => {row.standbys = 2;}],
  ['preludeResources', row => {row.foregroundLimit = 5;}],
  ['preludeResources', row => {row.nodes.pop();}],
  ['preludeNativeProgress', row => {row.progressSummary.maxGapMs = 2000;}],
  ['preludeNativeProgress', row => {row.progressSummary.suspensionCount = 1;}],
  ['preludeNativeProgress', row => {delete row.progressSummary;}],
  ['preludeNativeProgress', row => {row.progressSummary.supported = false;}],
];
console.log(JSON.stringify(cases.map(([check, mutate]) => {
  const value = structuredClone(replay); mutate(value.prelude.samples[1]);
  const report = api.coverage(value, targets); return {check, pass: report.pass, gate: report.checks[check]};
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertFalse(report['gate'], report['check'])

    def test_strategy_must_be_explicit_consistent_and_assigned_before_observation(self):
        result = execute(COHORT + r'''
const mutations = [
  value => {value.strategyFinal.pauseBeforeSeek = false;},
  value => {value.prelude.strategyStart.pauseBeforeSeek = false;},
  value => {delete value.cohortOptions;}, value => {delete value.strategyFinal;},
  value => {value.prelude.strategyStart.assignedAt = 1500;},
  value => {value.cohortOptions.pauseBeforeSeek = 'true';},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.strategiesMatch};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 6)

    def test_consistently_unpaused_control_strategy_has_equal_coverage_requirements(self):
        result = execute(COHORT + r'''
replay.cohortOptions.pauseBeforeSeek = false;
replay.prelude.strategyStart.pauseBeforeSeek = false;
replay.strategyFinal.pauseBeforeSeek = false;
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertTrue(result['pass'], result)
        self.assertTrue(result['checks']['strategiesMatch'])

    def test_fixed_hold_cannot_claim_coverage_after_evolution_or_loop_mode_changes(self):
        result = execute(COHORT + r'''
const mutations = [
  value => {value.initialStudio.evolving = true;},
  value => {value.initialStudio.loopMode = 'forward';},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets);
  return {pass: report.pass, gate: report.checks.heldComposition};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 2)

    def test_fixed_cohort_replacement_cannot_hide_behind_earlier_baseline_wraps(self):
        result = execute(COHORT + r'''
const late = structuredClone(replay.samples[2]); late.wall += 137;
late.nodes[3].birth++;
replay.samples.push(late);
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertFalse(result['pass'])
        self.assertFalse(result['checks']['heldComposition'])


if __name__ == '__main__':
    unittest.main()
