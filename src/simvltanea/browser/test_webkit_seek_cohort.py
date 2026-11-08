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

# The predecessor is observed before its guard. The successor's native callback
# trace independently proves two hidden frames and two post-promotion frames.
RESCUE = r'''
replay.cohortOptions.recoveryChain = 1;
replay.cohortOptions.standbyRescue = true;
replay.prelude.strategyStart.standbyRescue = true;
replay.strategyFinal.standbyRescue = true;
const rescuePolicy = {enabled: true, graceSimSec: .2, maximumFadeSec: .2, fadeSec: .2};
replay.cohortOptions.rescuePolicy = {...rescuePolicy};
replay.prelude.strategyStart.rescuePolicy = {...rescuePolicy};
replay.strategyFinal.rescuePolicy = {...rescuePolicy};
const predecessor = replay.samples[0].nodes[3];
const base = {id: predecessor.id, url: predecessor.progress.url, sourceEpoch: 1, deck: 1,
  attemptedAt: 2.7, strategy: 'pause-seek-play', item: predecessor.item,
  sha256: predecessor.sha, birth: predecessor.birth};
const guard = {...base, type: 'native-loop-seek-recovery', wall: 2700, time: 2.7};
const queued = {...base, type: 'native-loop-rescue-queued', wall: 2900, time: 2.9};
const started = {...base, type: 'native-loop-rescue-started', wall: 2901, time: 2.901};
const committed = {...base, type: 'native-loop-rescue-committed', wall: 3000, time: 3,
  successorUrl: 'blob:http://studio.test/rescue', successorEpoch: 1, successorDeck: 0,
  freshAfterWall: 2910, freshAfterChanges: 0, admissionChanges: 2, admissionLastWall: 2930,
  admissionDecoded: .2, admissionSeeking: false, promotionAfterWall: 2950,
  promotionAfterChanges: 2, promotionChanges: 2, promotionLastWall: 2970,
  promotionDecoded: .4, promotionSeeking: false};
const rescueReceipts = [queued, started, committed];
const interrupted = {...base, type: 'native-loop-seek-interrupted', wall: 2999, time: 2.999,
  reason: 'retired'};
const freshTrace = [{wall: 2920, mediaTime: .1, changes: 1}, {wall: 2930, mediaTime: .2, changes: 2},
  {wall: 2960, mediaTime: .3, changes: 3}, {wall: 2970, mediaTime: .4, changes: 4}];
for (const [index, row] of quartet(finalCohort, 3055).entries()) {
  const node = row.nodes[3]; node.deck = 0;
  node.progress.url = committed.successorUrl;
  node.progress.foregroundSince = committed.admissionLastWall + 1;
  node.progress.sourceChanges = node.progress.changes = node.callbacks = 5 + index;
  node.progress.trace = [...freshTrace, ...Array.from({length: index + 1}, (_, n) => ({
    wall: 3055 + n * 137, mediaTime: [4.8, 4.95, .1][n], changes: 5 + n}))];
  Object.assign(row.decks[3], {deck: 0, src: committed.successorUrl, currentSrc: committed.successorUrl,
    callbacks: node.callbacks, progress: node.progress});
  replay.samples.push(row);
}
for (const row of [...replay.prelude.samples, ...replay.samples]) {
  const receipts = rescueReceipts.filter(event => event.wall <= row.wall);
  row.progressSummary.nativeLoopRescue = {queued: Number(row.wall >= 2900), started: Number(row.wall >= 2901),
    committed: Number(row.wall >= 3000), cancelled: 0, deferred: 0, dropped: 0, receipts};
  row.progressSummary.nativeLoopSeek = {attempted: Number(row.wall >= 2700), recovered: 0, rejected: 0,
    interrupted: Number(row.wall >= 2999), dropped: 0,
    receipts: [guard, interrupted].filter(event => event.wall <= row.wall)};
}
'''


RETIRED_RESCUE = r'''
const lastLive = replay.samples.at(-1), lastDeck = lastLive.decks[3];
const retired = {id:lastDeck.id, deck:lastDeck.deck, ...structuredClone(lastDeck.progress),
  live:false, foreground:false, running:false, currentGapMs:0, retiredAt:3400, nativeError:null};
const unloaded = {...structuredClone(lastDeck), active:false, populated:false, src:'',
  currentSrc:committed.successorUrl, paused:true, seeking:false, ready:0, weight:0,
  progress:{...structuredClone(retired)}};
for (const wall of [3466, 3603]) {
  const row = structuredClone(lastLive); row.wall = wall;
  row.nodes = row.nodes.filter(node => node.id !== 'loop-4');
  row.decks[3] = structuredClone(unloaded);
  row.progressSummary.retired = wall === 3603 ? [structuredClone(retired)] : [];
  replay.samples.push(row);
}
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


class RescueCohortTests(unittest.TestCase):
    def test_repeated_retirement_trace_cannot_supply_different_frozen_witnesses(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
console.log(JSON.stringify([false, true].map(inject => {
  const value = structuredClone(replay), early = value.samples.at(-2), late = value.samples.at(-1);
  early.progressSummary.retired = [structuredClone(late.progressSummary.retired[0])];
  if (inject) {
    // Only the later retirement would supply the missing first admission frame.
    early.progressSummary.retired[0].trace.shift();
    for (const row of value.samples) for (const deck of row.decks)
      if (deck.progress?.url === committed.successorUrl && deck.progress.trace) deck.progress.trace.shift();
  } else late.progressSummary.retired[0].trace.shift();
  return api.rescueAudit(value, targets).pass;
})));
''')
        self.assertEqual(result, [False, False])

    def test_unloaded_optional_trace_must_match_the_frozen_retirement(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
console.log(JSON.stringify([[], {}, null, unloaded.progress.trace.slice(0, -1)].map(trace => {
  const value = structuredClone(replay); value.samples.at(-2).decks[3].progress.trace = trace;
  return api.rescueAudit(value, targets).pass;
})));
''')
        self.assertEqual(result, [False] * 4)

    def test_malformed_retirement_trace_is_rejected_without_parser_exception(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
console.log(JSON.stringify([null, {}, 'not a trace'].map(trace => {
  const value = structuredClone(replay); value.samples.at(-1).progressSummary.retired[0].trace = trace;
  try { return {pass:api.rescueAudit(value, targets).pass, threw:false}; }
  catch (_) { return {pass:null, threw:true}; }
})));
''')
        self.assertEqual(result, [{'pass': False, 'threw': False}] * 3)

    def test_verified_retirement_allows_later_unloaded_native_source_duplicates(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
const before = JSON.stringify(replay), report = api.rescueAudit(replay, targets);
console.log(JSON.stringify({pass:report.pass,bridges:report.bridges.length,
  unchanged:JSON.stringify(replay)===before}));
''')
        self.assertEqual(result, {'pass': True, 'bridges': 1, 'unchanged': True})

    def test_retired_native_frames_remain_admission_and_promotion_evidence(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
for (const row of replay.samples) for (const deck of row.decks)
  if (deck.progress?.url === committed.successorUrl) delete deck.progress.trace;
const report = api.rescueAudit(replay, targets);
console.log(JSON.stringify({pass:report.pass,bridges:report.bridges.length}));
''')
        self.assertEqual(result, {'pass': True, 'bridges': 1})

    def test_retired_duplicate_exception_requires_exact_proof_and_unloaded_state(self):
        result = execute(COHORT + RESCUE + RETIRED_RESCUE + r'''
const mutations = [
  value => {value.samples.at(-1).progressSummary.retired = [];},
  value => {value.samples.at(-1).progressSummary.retired[0].retiredAt = 3467;},
  value => {value.samples.at(-1).progressSummary.retired[0].retiredAt = 2900;},
  value => {value.samples.at(-1).progressSummary.retired[0].id = 'loop-1';},
  value => {value.samples.at(-1).progressSummary.retired[0].deck = 1;},
  value => {value.samples.at(-1).progressSummary.retired[0].epoch = 2;},
  value => {value.samples.at(-1).progressSummary.retired[0].url = 'blob:foreign';},
  value => {value.samples.at(-1).progressSummary.retired[0].live = true;},
  value => {value.samples.at(-1).progressSummary.retired[0].supported = false;},
  value => {value.samples.at(-1).progressSummary.retired[0].nativeError = {code:3};},
  value => {delete value.samples.at(-1).progressSummary.retired[0].trace;},
  value => {value.samples.at(-1).progressSummary.retired[0].trace.at(-1).wall = 3401;},
  value => {delete value.samples.at(-1).progressSummary.retired[0].lastChangeWall;},
  value => {value.samples.at(-2).decks[3].active = true;},
  value => {value.samples.at(-2).decks[3].populated = true;},
  value => {value.samples.at(-2).decks[3].src = committed.successorUrl;},
  value => {value.samples.at(-2).decks[3].currentSrc = 'blob:foreign';},
  value => {value.samples.at(-2).decks[3].paused = false;},
  value => {value.samples.at(-2).decks[3].ready = 1;},
  value => {value.samples.at(-2).decks[3].weight = .1;},
  value => {value.samples.at(-2).decks[3].nativeError = {code:3};},
  value => {value.samples.at(-2).decks[3].progress.live = true;},
  value => {value.samples.at(-2).decks[3].progress.epoch = 2;},
  value => {value.samples.at(-2).decks[3].progress.foreground = true;},
  value => {value.samples.at(-2).decks[3].progress.sourceChanges++;},
  value => {value.samples.at(-2).decks[3].progress.trace.at(-1).wall = 3401;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value); return api.rescueAudit(value, targets).pass;
})));
''')
        self.assertEqual(result, [False] * 26)

    def test_later_foreground_snapshot_cannot_backdate_reveal_before_admission(self):
        result = execute(COHORT + RESCUE + r'''
for (const row of replay.samples) for (const deck of row.decks)
  if (deck.progress?.url === committed.successorUrl) deck.progress.foregroundSince = committed.admissionLastWall - 1;
console.log(JSON.stringify(api.rescueAudit(replay, targets).pass));
''')
        self.assertFalse(result)

    def test_partial_new_protocol_cannot_downgrade_to_legacy_strategy_checks(self):
        result = execute(COHORT + r'''
const mutations = [
  value => {value.cohortOptions.recoveryChain = null;},
  value => {value.cohortOptions.standbyRescue = false;},
  value => {value.strategyFinal.rescuePolicy = {enabled: false};},
  value => {for (const row of [...value.prelude.samples, ...value.samples])
    row.progressSummary.nativeLoopRescue = {queued:0,started:0,committed:0,cancelled:0,deferred:0,dropped:0,receipts:[]};},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  return api.coverage(value, targets).checks.strategiesMatch;
})));
''')
        self.assertEqual(result, [False] * 4)

    def test_observed_successor_must_remain_hidden_until_its_second_fresh_frame(self):
        result = execute(COHORT + RESCUE + r'''
const early = replay.samples.find(row => row.wall === 2918);
early.decks.push({id: 'loop-4', deck: 0, active: false, weight: 0, populated: true,
  src: committed.successorUrl, currentSrc: committed.successorUrl, nativeError: null,
  progress: {schema:1, supported:true, live:true, url:committed.successorUrl, epoch:1,
    changes:0, sourceChanges:0, foreground:false, running:false, foregroundSince:null,
    lastForegroundChangeWall:null, currentGapMs:0, maxGapMs:0, trace:[]}});
const baseline = api.rescueAudit(replay, targets).pass;
const mutations = [
  deck => {deck.weight = 1;}, deck => {deck.weight = NaN;}, deck => {delete deck.weight;},
  deck => {deck.active = true;}, deck => {deck.progress.foreground = true;},
  deck => {deck.progress.running = true;}, deck => {deck.progress.foregroundSince = 2900;},
];
console.log(JSON.stringify({baseline, invalid: mutations.map(mutate => {
  const value = structuredClone(replay);
  mutate(value.samples.find(row => row.wall === 2918).decks.at(-1));
  return api.rescueAudit(value, targets).pass;
})}));
''')
        self.assertTrue(result['baseline'])
        self.assertEqual(result['invalid'], [False] * 7)

    def test_causal_attempt_and_lifecycle_times_cannot_be_missing_or_regress(self):
        result = execute(COHORT + RESCUE + r'''
const mutations = [
  value => {for (const row of value.samples) {
    for (const event of row.progressSummary.nativeLoopRescue.receipts) delete event.attemptedAt;
    for (const event of row.progressSummary.nativeLoopSeek.receipts) {
      delete event.attemptedAt; if (event.type === 'native-loop-seek-recovery') delete event.time;
    }
  }},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts) event.time = -1;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('started')) event.time = 100;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopSeek.receipts)
    if (event.type.endsWith('interrupted')) delete event.time;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value); return api.rescueAudit(value, targets).pass;
})));
''')
        self.assertEqual(result, [False] * 4)

    def test_terminal_seek_guard_cannot_authorize_a_later_rescue_commit(self):
        result = execute(COHORT + RESCUE + r'''
const cases = ['native-loop-seek-recovered', 'native-loop-seek-interrupted'].flatMap(type => [2800, 2950].map(wall => ({type, wall})));
console.log(JSON.stringify(cases.map(({type, wall}) => {
  const value = structuredClone(replay), event = {...guard, type, wall, time:wall/1000,
    attemptedAt:guard.time, decodedChanges:2, seeking:false, reason:'source-changed'};
  for (const row of value.samples) if (row.wall >= wall) {
    row.progressSummary.nativeLoopSeek.receipts.push(event);
    row.progressSummary.nativeLoopSeek[type.endsWith('recovered') ? 'recovered' : 'interrupted']++;
  }
  return api.rescueAudit(value, targets).pass;
})));
''')
        self.assertEqual(result, [False] * 4)

    def test_recovery_after_queue_may_cancel_rescue_without_authorizing_a_bridge(self):
        result = execute(COHORT + RESCUE + r'''
committed.type = 'native-loop-rescue-cancelled'; committed.reason = 'outgoing-recovered';
const recovered = {...guard, type:'native-loop-seek-recovered', wall:2998, time:2.998,
  attemptedAt:guard.time, decodedChanges:2, seeking:false};
for (const row of replay.samples) {
  if (row.wall >= 2998) {row.progressSummary.nativeLoopSeek.receipts.push(recovered); row.progressSummary.nativeLoopSeek.recovered = 1;}
  if (row.wall >= 3000) {row.progressSummary.nativeLoopRescue.committed = 0; row.progressSummary.nativeLoopRescue.cancelled = 1;}
}
const cancelled = api.rescueAudit(replay, targets);
committed.type = 'native-loop-rescue-deferred'; committed.reason = 'Incoming frames did not become ready';
for (const row of replay.samples) if (row.wall >= 3000) {
  row.progressSummary.nativeLoopRescue.cancelled = 0; row.progressSummary.nativeLoopRescue.deferred = 1;
  row.progressSummary.nativeLoopSeek.recovered = 0;
  row.progressSummary.nativeLoopSeek.receipts = row.progressSummary.nativeLoopSeek.receipts.filter(event => event !== recovered);
}
const deferred = api.rescueAudit(replay, targets);
console.log(JSON.stringify([cancelled, deferred].map(report => ({pass:report.pass,bridges:report.bridges.length}))));
''')
        self.assertEqual(result, [{'pass': True, 'bridges': 0}] * 2)

    def test_both_arms_require_the_recorded_production_rescue_policy(self):
        result = execute(COHORT + RESCUE + r'''
const mutations = [
  value => {delete value.strategyFinal.rescuePolicy;},
  value => {value.prelude.strategyStart.rescuePolicy.enabled = false;},
  value => {value.strategyFinal.rescuePolicy.graceSimSec = .5;},
  value => {value.strategyFinal.rescuePolicy.fadeSec = 1.2;},
  value => {value.cohortOptions.rescuePolicy.maximumFadeSec = 1.2;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  return api.coverage(value, targets).checks.strategiesMatch;
})));
''')
        self.assertEqual(result, [False] * 5)

    def test_logical_peer_claim_alone_cannot_override_a_physical_isolation_failure(self):
        result = execute(COHORT + r'''
replay.prelude.targetIsolation.peersStable = false;
replay.prelude.targetIsolation.logicalPeersStable = true;
console.log(JSON.stringify(api.coverage(replay, targets).checks));
''')
        self.assertFalse(result['targetIsolation'])

    def test_owned_rescue_preserves_held_composition_without_rewriting_raw_observations(self):
        result = execute(COHORT + RESCUE + r'''
const before = JSON.stringify(replay);
const report = api.coverage(replay, targets);
console.log(JSON.stringify({report, unchanged: JSON.stringify(replay) === before}));
''')
        self.assertTrue(result['report']['pass'], result['report'])
        self.assertTrue(result['unchanged'])
        self.assertEqual(len(result['report']['rescueAudit']['bridges']), 1)
        self.assertFalse(result['report']['physicalStability']['heldComposition'])

    def test_owned_peer_rescue_keeps_exact_sibling_incoming_frame_ownership(self):
        result = execute(COHORT + RESCUE + r'''
for (const event of [guard, queued, started, committed, interrupted]) event.wall -= 1300;
for (const key of ['freshAfterWall', 'admissionLastWall', 'promotionAfterWall', 'promotionLastWall'])
  committed[key] -= 1300;
for (const point of freshTrace) point.wall -= 1300;
for (const row of [...replay.prelude.samples, ...replay.samples]) {
  const node = row.nodes[3];
  if (row.wall >= committed.wall) {
    node.deck = 0; node.progress.url = committed.successorUrl;
    node.progress.foregroundSince = committed.admissionLastWall + 1;
    const local = 5 + Math.round((row.wall - 1822) / 137);
    node.progress.sourceChanges = node.progress.changes = node.callbacks = local;
    node.progress.trace = [...freshTrace, {wall: row.wall, mediaTime: node.decoded, changes: local}];
    Object.assign(row.decks[3], {deck: 0, src: committed.successorUrl, currentSrc: committed.successorUrl,
      callbacks: local, progress: node.progress});
  }
  row.progressSummary.nativeLoopRescue = {queued: Number(row.wall >= queued.wall),
    started: Number(row.wall >= started.wall), committed: Number(row.wall >= committed.wall),
    cancelled: 0, deferred: 0, dropped: 0, receipts: rescueReceipts.filter(event => event.wall <= row.wall)};
  row.progressSummary.nativeLoopSeek = {attempted: Number(row.wall >= guard.wall), recovered: 0, rejected: 0,
    interrupted: Number(row.wall >= interrupted.wall), dropped: 0,
    receipts: [guard, interrupted].filter(event => event.wall <= row.wall)};
}
for (const row of replay.prelude.incomingObservations) {
  row.peersStable = false; row.logicalPeersStable = true;
}
replay.prelude.siblingIsolation.peersStable = false;
replay.prelude.siblingIsolation.logicalPeersStable = true;
const report = api.coverage(replay, targets);
console.log(JSON.stringify({checks: report.checks, audit: report.rescueAudit, physical: report.physicalStability}));
''')
        self.assertTrue(result['audit']['pass'], result['audit'])
        self.assertTrue(all(result['checks'].values()), result['checks'])
        self.assertFalse(result['physical']['siblingIsolation'])
        self.assertIs(result['physical'].get('siblingIncomingOverlap'), False)

    def test_unproven_rescue_cannot_authorize_a_decoder_identity_change(self):
        result = execute(COHORT + RESCUE + r'''
const mutations = [
  value => {for (const row of value.samples) delete row.progressSummary.nativeLoopRescue;},
  value => {for (const row of value.samples) row.progressSummary.nativeLoopRescue.committed = 2;},
  value => {for (const row of value.samples) row.progressSummary.nativeLoopRescue.receipts =
    row.progressSummary.nativeLoopRescue.receipts.filter(event => event.type !== 'native-loop-rescue-started');},
  value => {for (const row of [...value.prelude.samples, ...value.samples])
    row.progressSummary.nativeLoopSeek.receipts = [];},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('committed')) event.successorUrl = 'blob:foreign';},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    event.sha256 = targets[0].sha256;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('committed')) event.admissionChanges = 1;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('committed')) event.admissionSeeking = true;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('committed')) event.promotionChanges = 1;},
  value => {for (const row of value.samples) for (const event of row.progressSummary.nativeLoopRescue.receipts)
    if (event.type.endsWith('committed')) event.freshAfterWall = 2940;},
  value => {for (const row of value.samples) for (const deck of row.decks)
    if (deck.progress.url === committed.successorUrl) deck.progress.trace = [];},
  value => {for (const row of value.samples) for (const deck of row.decks)
    if (deck.progress.url === committed.successorUrl) deck.progress.trace[1].mediaTime = .1;},
  value => {for (const row of value.samples) for (const node of row.nodes)
    if (node.progress.url === committed.successorUrl) node.birth++;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets);
  return {pass: report.pass, held: report.checks.heldComposition};
})));
''')
        self.assertEqual(result, [{'pass': False, 'held': False}] * 13)

    def test_rescue_does_not_exempt_native_hold_or_source_wrap_gates(self):
        result = execute(COHORT + RESCUE + r'''
const cases = [
  ['preludeNativeProgress', value => {value.prelude.samples[0].progressSummary.maxGapMs = 2000;}],
  ['finalSourcesSustained', value => {for (const row of value.samples) for (const node of row.nodes)
    if (node.id === 'loop-1') node.decoded = node.progress.mediaTime = .1;}],
];
console.log(JSON.stringify(cases.map(([check, mutate]) => {
  const value = structuredClone(replay); mutate(value);
  const report = api.coverage(value, targets); return {pass: report.pass, gate: report.checks[check]};
})));
''')
        self.assertEqual(result, [{'pass': False, 'gate': False}] * 2)


if __name__ == '__main__':
    unittest.main()
