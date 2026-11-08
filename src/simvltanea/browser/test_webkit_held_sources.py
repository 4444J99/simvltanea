"""Positive asset and decoded-wrap evidence for the optional WebKit replay."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


HELPER = Path(__file__).with_name('verify_webkit_held_sources.js')

FIXTURE = r'''
const api = require(process.argv[1]);
const crypto = require('node:crypto');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const files = new Map(), targets = [];
const original = {schema: 'simvltanea.public-demo/1', clips: []};
for (let index = 0; index < 6; index++) {
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
  if (index < 5) targets.push({id, sha256, forwardSha256, role: index < 4 ? 'held' : 'predecessor'});
}
const readAsset = name => {
  if (!files.has(name)) throw new Error('Missing fixture asset: ' + name);
  return files.get(name);
};
const rejected = fn => {try {fn(); return false;} catch (_) {return true;}};
function rowsFor(target = targets[0]) {
  return [4.8, 4.95, .1].map((decoded, index) => {
    const wall = 1000 + index * 137, url = 'blob:http://studio.test/resident';
    const progress = {schema: 1, supported: true, live: true, foreground: true,
      running: true, url, epoch: 1, sourceChanges: 100 + index, changes: 100 + index,
      mediaTime: decoded, lastChangeWall: wall, foregroundSince: 1000,
      lastForegroundChangeWall: wall, currentGapMs: 0, maxGapMs: 137, lifetimeMaxGapMs: 137};
    const node = {id: 'loop-1', item: target.id, sha: target.sha256, deck: 0, birth: 0,
      phase: 'ACTIVE', busy: false, resting: false, current: decoded, decoded,
      callbacks: 100 + index, paused: false, seeking: false, ready: 4, nativeError: null, progress};
    return {wall, running: true, hidden: false, audioState: 'running', nodes: [node],
      decks: [{id: 'loop-1', deck: 0, active: true, populated: true, src: url,
        currentSrc: url, ready: 4, paused: false, decoded, callbacks: node.callbacks,
        nativeError: null, progress}]};
  });
}
'''


def execute(body: str):
    completed = subprocess.run(['node', '-e', FIXTURE + body, str(HELPER)],
                               check=True, capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


class HeldSourceManifestTests(unittest.TestCase):
    def test_diagnostic_admits_library_without_browser_globals(self):
        # Requiring the diagnostic also imports the real Studio source. Its
        # browser-only URL synchronization must not prevent Node verification.
        result = execute(r'''
const out = api.buildManifest(original, readAsset, targets);
console.log(JSON.stringify({window: typeof window, history: typeof history,
  document: typeof document, clips: out.manifest.clips.length}));
''')
        self.assertEqual(result, {'window': 'undefined', 'history': 'undefined',
                                  'document': 'undefined', 'clips': 5})

    def test_query_admits_predecessor_and_three_siblings_using_canonical_indexes(self):
        result = execute(r'''
original.clips.reverse();
const out = api.buildManifest(original, readAsset, targets);
const {libraryClips} = require(require('node:path').join(require('node:path').dirname(process.argv[1]), 'browser.studio.js'));
const sorted = libraryClips(out.manifest), params = new URLSearchParams(out.query);
const mix = params.get('mix');
console.log(JSON.stringify({selected: mix.slice(1).split('.').map(index => sorted[Number(index)].id),
  expected: [targets[4].id, ...targets.slice(1, 4).map(target => target.id)],
  family: mix[0], evolve: params.get('evolve'), loop: params.get('loop'), proof: params.get('proof')}));
''')
        self.assertEqual(result['selected'], result['expected'])
        self.assertEqual((result['family'], result['evolve'], result['loop'], result['proof']),
                         ('s', '0', 'boomerang', '1'))

    def test_subset_retains_exact_original_entries_and_bytes(self):
        result = execute(r'''
const before = JSON.stringify(original), read = [];
const out = api.buildManifest(original, name => {read.push(name); return readAsset(name);}, targets);
console.log(JSON.stringify({manifest: out.manifest,
  expected: original.clips.filter(clip => targets.some(target => target.id === clip.id)),
  unchanged: JSON.stringify(original) === before, read: [...new Set(read)].sort(),
  expectedFiles: original.clips.slice(0, 5).flatMap(clip => [clip.file, clip.variants.boomerang.file]).sort()}));
''')
        self.assertTrue(result['unchanged'])
        self.assertEqual(result['manifest']['schema'], 'simvltanea.public-demo/1')
        self.assertEqual(sorted(result['manifest']['clips'], key=lambda clip: clip['id']),
                         sorted(result['expected'], key=lambda clip: clip['id']))
        self.assertEqual(result['read'], result['expectedFiles'])

    def test_missing_target_or_invalid_original_manifest_is_rejected(self):
        result = execute(r'''
const mutations = [
  value => {value.clips.shift();},
  value => {value.schema = 'unknown/1';},
  // The full library must be valid, including entries outside the replay subset.
  value => {value.clips[5].file = '../untrusted.mp4';},
  value => {value.clips[0].variants.boomerang.frame_count = 149;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const value = structuredClone(original); mutate(value);
  return rejected(() => api.buildManifest(value, readAsset, targets));
})));
''')
        self.assertEqual(result, [True] * 4)

    def test_same_length_changed_bytes_cannot_satisfy_either_full_hash(self):
        result = execute(r'''
console.log(JSON.stringify(['forward', 'boomerang'].map(kind => {
  const clip = original.clips[0], name = kind === 'forward' ? clip.file : clip.variants.boomerang.file;
  return rejected(() => api.buildManifest(original, file => {
    const bytes = Buffer.from(readAsset(file));
    if (file === name) bytes[bytes.length - 1] ^= 1;
    return bytes;
  }, targets));
})));
''')
        self.assertEqual(result, [True, True])

    def test_manifest_byte_length_and_missing_asset_fail_closed(self):
        result = execute(r'''
const changed = structuredClone(original); changed.clips[0].bytes++;
const wrongLength = rejected(() => api.buildManifest(changed, readAsset, targets));
const missing = rejected(() => api.buildManifest(original, name => {
  if (name === original.clips[0].variants.boomerang.file) throw new Error('Missing asset');
  return readAsset(name);
}, targets));
console.log(JSON.stringify([wrongLength, missing]));
''')
        self.assertEqual(result, [True, True])


class HeldSourceObservationTests(unittest.TestCase):
    def test_advancing_decoded_frames_and_wrap_prove_one_active_source(self):
        result = execute(r'''
console.log(JSON.stringify(api.observeSources(rowsFor(), [targets[0]])));
''')
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['pass'])
        self.assertEqual(result[0]['observations'], 3)
        self.assertEqual(result[0]['advances'], 2)
        self.assertEqual(result[0]['wraps'], 1)

    def test_prefetched_or_inactive_deck_does_not_prove_resident_admission(self):
        result = execute(r'''
const rows = rowsFor();
for (const row of rows) {
  row.nodes = [];
  row.decks[0].active = false;
  row.decks[0].item = targets[0].id; row.decks[0].sha = targets[0].sha256;
}
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['observations'], 0)

    def test_wrong_content_hash_does_not_prove_requested_clip(self):
        result = execute(r'''
const rows = rowsFor();
for (const row of rows) row.nodes[0].sha = targets[1].sha256;
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['observations'], 0)

    def test_current_time_wrap_cannot_replace_decoded_frame_evidence(self):
        result = execute(r'''
const rows = rowsFor();
for (const row of rows) {
  row.nodes[0].decoded = 4.8;
  row.nodes[0].progress.mediaTime = 4.8;
}
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['advances'], 0)
        self.assertEqual(result['wraps'], 0)

    def test_decoded_change_without_native_counter_advance_is_not_progress(self):
        result = execute(r'''
const rows = rowsFor();
for (const row of rows) row.nodes[0].progress.sourceChanges = 100;
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['advances'], 0)
        self.assertEqual(result['wraps'], 0)

    def test_new_source_epoch_or_slot_identity_cannot_masquerade_as_wrap(self):
        result = execute(r'''
const changes = [
  node => {node.progress.epoch++;},
  node => {node.progress.url = 'blob:http://studio.test/replacement';},
  node => {node.birth = 2;},
  node => {node.deck = 1;},
  node => {node.id = 'loop-2';},
];
console.log(JSON.stringify(changes.map(change => {
  const rows = rowsFor(); change(rows[2].nodes[0]);
  return api.observeSources(rows, [targets[0]])[0];
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertEqual(report['wraps'], 0)

    def test_two_second_observation_gap_cannot_prove_a_wrap(self):
        result = execute(r'''
const rows = rowsFor(); rows[2].wall = rows[1].wall + 2000;
Object.assign(rows[2].nodes[0].progress, {lastChangeWall: rows[2].wall,
  lastForegroundChangeWall: rows[2].wall});
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['wraps'], 0)

    def test_missing_resident_observation_breaks_the_decoded_wrap_chain(self):
        result = execute(r'''
const rows = rowsFor();
rows.splice(2, 0, {wall: rows[1].wall + 30, running: true, hidden: false, nodes: [], decks: []});
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['wraps'], 0)

    def test_transient_metadata_ready_at_wrap_keeps_positive_native_frame_evidence(self):
        # Native smoke recorded HAVE_METADATA during a wrap while the retained
        # texture's native gap was only 16.9 ms; subsequent frames progressed.
        result = execute(r'''
const rows = rowsFor(), metadata = structuredClone(rows[1]);
metadata.wall += 16.9;
metadata.nodes[0].ready = 1;
metadata.nodes[0].progress.currentGapMs = 16.9;
rows.splice(2, 0, metadata);
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertTrue(result['pass'])
        self.assertEqual(result['advances'], 2)
        self.assertEqual(result['wraps'], 1)

    def test_same_wall_duplicates_neither_fail_nor_create_progress(self):
        result = execute(r'''
const rows = rowsFor(); rows.splice(2, 0, structuredClone(rows[1]));
const sameWall = rowsFor();
for (const row of sameWall) row.wall = 1000;
console.log(JSON.stringify([api.observeSources(rows, [targets[0]])[0],
  api.observeSources(sameWall, [targets[0]])[0]]));
''')
        self.assertTrue(result[0]['pass'])
        self.assertEqual(result[0]['advances'], 2)
        self.assertEqual(result[0]['wraps'], 1)
        self.assertFalse(result[1]['pass'])
        self.assertEqual(result[1]['advances'], 0)
        self.assertEqual(result[1]['wraps'], 0)

    def test_backwards_observation_time_cannot_prove_wrap(self):
        result = execute(r'''
const rows = rowsFor(); rows[2].wall = rows[1].wall - 1;
console.log(JSON.stringify(api.observeSources(rows, [targets[0]])[0]));
''')
        self.assertFalse(result['pass'])
        self.assertEqual(result['wraps'], 0)

    def test_native_current_or_historical_gap_at_ceiling_cannot_pass(self):
        result = execute(r'''
console.log(JSON.stringify(['currentGapMs', 'maxGapMs'].map(key => {
  const rows = rowsFor(); rows[1].nodes[0].progress[key] = 2000;
  return api.observeSources(rows, [targets[0]])[0];
})));
''')
        self.assertEqual([report['pass'] for report in result], [False, False])

    def test_absent_native_proof_and_nonplaying_samples_cannot_pass(self):
        result = execute(r'''
const mutations = [
  row => {row.running = false;}, row => {row.hidden = true;},
  row => {row.nodes[0].paused = true;}, row => {row.nodes[0].ready = 0;},
  row => {row.audioState = 'suspended';},
  row => {row.nodes[0].progress.mediaTime = 99;},
  row => {row.nodes[0].progress.schema = 2;},
  row => {row.nodes[0].progress.live = false;},
  row => {row.nodes[0].progress.supported = false;},
  row => {row.nodes[0].progress.foreground = false;},
  row => {row.nodes[0].progress.running = false;},
  row => {row.nodes[0].progress.url = 'https://studio.test/clip.mp4';},
  row => {delete row.nodes[0].progress;},
];
console.log(JSON.stringify(mutations.map(mutate => {
  const rows = rowsFor(); rows.forEach(mutate);
  return api.observeSources(rows, [targets[0]])[0];
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertEqual(report['observations'], 0)


REPLAY = r'''
function quartet(selected, startWall, promoted = false) {
  return [0, 1, 2].map(index => {
    const wall = startWall + index * 137;
    const nodes = selected.map((target, slot) => {
      const node = rowsFor(target)[index].nodes[0];
      node.id = `loop-${slot + 1}`;
      node.progress.url = `blob:http://studio.test/${target.id}`;
      node.progress.lastChangeWall = node.progress.lastForegroundChangeWall = wall;
      node.callbacks = node.progress.sourceChanges = node.progress.changes = 100 + (wall - 1000) / 137;
      if (promoted && slot === 0) {node.deck = 1; node.birth = 1;}
      return node;
    });
    return {wall, running: true, hidden: false, audioState: 'running', nodes,
      foregroundLimit: 4, populated: 4, playing: 4, standbys: 0, maxStandbys: 1,
      progressSummary: {schema: 1, supported: true, maxGapMs: 137, suspensionCount: 0}};
  });
}
const beforeRows = quartet([targets[4], ...targets.slice(1, 4)], 1000);
const afterRows = quartet(targets.slice(0, 4), 1411, true);
const replay = {prelude: {samples: [...beforeRows, ...afterRows], before: beforeRows[2], after: afterRows[0]},
  samples: quartet(targets.slice(0, 4), 1822, true), initialStudio: {evolving: true, loopMode: 'boomerang'}};
'''


class HeldSourceCoverageTests(unittest.TestCase):
    def test_prelude_resource_overflow_or_invalid_foreground_set_fails(self):
        result = execute(REPLAY + r'''
const changes = [
  row => {row.populated = 6;}, row => {row.playing = 6;},
  row => {row.standbys = 2;}, row => {row.maxStandbys = 2;},
  row => {row.foregroundLimit = 5;}, row => {row.nodes.pop();},
  row => {row.nodes[3].id = row.nodes[2].id;},
  row => {row.populated = NaN;}, row => {row.populated = -1;},
  row => {row.playing = .5;}, row => {row.playing = 5;},
  row => {row.standbys = 1; row.maxStandbys = 0;},
];
console.log(JSON.stringify(changes.map(change => {
  const value = structuredClone(replay); change(value.prelude.samples[1]);
  return api.coverage(value, targets);
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertFalse(report['checks']['preludeResources'])

    def test_retired_gap_or_missing_native_summary_cannot_pass_prelude(self):
        result = execute(REPLAY + r'''
const changes = [
  row => {row.progressSummary.maxGapMs = 2100;},
  row => {delete row.progressSummary;},
  row => {row.progressSummary.supported = false;},
  row => {row.progressSummary.schema = 2;},
  row => {row.progressSummary.suspensionCount = 1;},
  row => {row.progressSummary.maxGapMs = NaN;},
  row => {row.progressSummary.maxGapMs = -1;},
];
console.log(JSON.stringify(changes.map(change => {
  const value = structuredClone(replay); change(value.prelude.samples[1]);
  return api.coverage(value, targets);
})));
''')
        for report in result:
            self.assertFalse(report['pass'])
            self.assertFalse(report['checks']['preludeNativeProgress'])

    def test_all_five_assets_and_held_body_wraps_prove_replay_coverage(self):
        result = execute(REPLAY + r'''
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertTrue(result['pass'])
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual(len(result['sources']), 5)
        self.assertTrue(all(source['pass'] for source in result['sources']))

    def test_requested_predecessor_without_decoded_admission_is_not_coverage(self):
        result = execute(REPLAY + r'''
replay.prelude.samples = replay.prelude.samples.map(row => ({...row,
  nodes: row.nodes.filter(node => node.item !== targets[4].id)}));
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertFalse(result['pass'])
        self.assertFalse(result['checks']['allSourcesDecodedAndWrapped'])

    def test_prelude_wrap_does_not_substitute_for_sustained_held_source_evidence(self):
        result = execute(REPLAY + r'''
for (const row of replay.samples) {
  row.nodes[0].decoded = row.nodes[0].progress.mediaTime = 4.8;
}
console.log(JSON.stringify(api.coverage(replay, targets)));
''')
        self.assertFalse(result['pass'])
        self.assertTrue(result['checks']['allSourcesDecodedAndWrapped'])
        self.assertFalse(result['checks']['heldSourcesSustained'])

    def test_sibling_replacement_or_disabled_evolution_fails_replay_contract(self):
        result = execute(REPLAY + r'''
const changedSibling = structuredClone(replay);
changedSibling.prelude.after.nodes[1].birth++;
const staticField = structuredClone(replay); staticField.initialStudio.evolving = false;
console.log(JSON.stringify([api.coverage(changedSibling, targets), api.coverage(staticField, targets)]));
''')
        self.assertFalse(result[0]['pass'])
        self.assertFalse(result[0]['checks']['siblingIdentities'])
        self.assertFalse(result[1]['pass'])
        self.assertFalse(result[1]['checks']['evolutionEnabled'])


if __name__ == '__main__':
    unittest.main()
