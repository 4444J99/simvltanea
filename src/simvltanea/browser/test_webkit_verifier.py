"""Fail-closed classification of recorded WebKit playback; no browser required."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


VERIFIER = Path(__file__).with_name('verify_webkit_sustained.js')
FIXTURE = r'''
const {analyse} = require(process.argv[1]);
const result = {
  completed: true, elapsedMs: 182000, errors: [], consoleErrors: [], httpErrors: [], events: [],
  coarse: ['SPARSE_BREATH', 'STEADY_FLOW', 'BURST_CHORUS'].map(regime => ({studio: {ecosystem: {regime}}})),
  samples: Array.from({length: 1300}, (_, index) => ({
    wall: index * 140, running: true, hidden: false, audioState: 'running', lastFailure: null,
    foregroundLimit: 4, populated: 4, playing: 4, standbys: 0, maxStandbys: 1,
    nodes: Array.from({length: 4}, (_, slot) => ({
      id: `loop-${slot + 1}`, item: `clip-${slot}`, sha: `${index < 500 ? 'first' : 'next'}-${slot}`,
      deck: index < 500 ? 0 : 1, birth: index < 500 ? 0 : 70,
      current: (index % 20) / 10, decoded: (index % 20) / 10, callbacks: index,
      paused: false, resting: false, nativeError: null, phase: 'ACTIVE', ready: 4, seeking: false,
    })),
  })),
};
'''

NATIVE_PROGRESS = r'''
result.progressSchema = 1;
for (const [index, row] of result.samples.entries()) {
  row.progressSummary = {schema: 1, supported: true, maxGapMs: 140,
    suspensionCount: 0, retiredCount: index < 500 ? 0 : 4, retired: []};
  row.decks = row.nodes.map(node => {
    const url = `blob:${node.sha}`;
    node.progress = {schema: 1, supported: true, live: true, url, epoch: 1,
      changes: index + 1, sourceChanges: index < 500 ? index + 1 : index - 499,
      lastChangeWall: row.wall, mediaTime: node.decoded, foreground: true, running: true,
      foregroundSince: index < 500 ? 0 : 70000, lastForegroundChangeWall: row.wall,
      currentGapMs: 0, maxGapMs: 140, lifetimeMaxGapMs: 140};
    return {id: node.id, deck: node.deck, active: true, populated: true, paused: false,
      src: url, currentSrc: url, nativeError: null, progress: node.progress};
  });
}
'''

TRACE_RECOVERY = r'''
const recoveredUrl = 'blob:http://127.0.0.1/recovered';
result.requestFailures = [{wall: 12100, url: recoveredUrl, failure: {errorText: 'cancelled'}}];
const callbackProof = {schema: 1, supported: true, live: true, url: recoveredUrl,
  epoch: 1, changes: 102, sourceChanges: 2, lastChangeWall: 12400, mediaTime: .7,
  trace: [{wall: 12200, mediaTime: .6, changes: 101}, {wall: 12400, mediaTime: .7, changes: 102}]};
// The host receives the trace after the original 1s recovery deadline.
result.samples[100].decks = [{id: 'loop-1', deck: 0, active: true, populated: true,
  src: recoveredUrl, currentSrc: recoveredUrl, progress: callbackProof, nativeError: null}];
'''

RETIRED_BLOB = r'''
const retiredUrl = 'blob:http://127.0.0.1/retired';
result.events.push({type: 'resource-retired', role: 'deck', id: 'loop-1',
  url: retiredUrl, wall: 12000, readyState: 0, paused: true});
result.consoleErrors.push(Object.freeze({wall: 12100, phase: 'sustained', url: retiredUrl,
  message: 'Failed to load resource: The operation couldn’t be completed. (WebKitBlobResource error 1.)'}));
result.requestFailures = [{wall: 12100, phase: 'sustained', url: retiredUrl,
  failure: {errorText: 'cancelled'}}];
Object.freeze(result.consoleErrors);
'''

RECOVERED_BLOB = r'''
const recoveredUrl = 'blob:http://127.0.0.1/recovered';
result.requestFailures = [Object.freeze({wall: 12100, phase: 'sustained', url: recoveredUrl,
  failure: {errorText: 'cancelled'}})];
for (const [index, decoded, callbacks] of [[87, .6, 101], [88, .7, 102]]) {
  result.samples[index].decks = [{id: 'loop-1', deck: 0, active: true, populated: true,
    src: recoveredUrl, currentSrc: recoveredUrl, decoded, callbacks, nativeError: null}];
}
Object.freeze(result.requestFailures);
'''

PRELUDE_TRACE_RECOVERY = TRACE_RECOVERY + r'''
result.progressSchema = 1;
result.prelude = {samples: [{...result.samples[100]}]};
delete result.samples[100].decks;
// The controlled prelude ends before the sustained observation window begins.
for (const row of result.samples) row.wall += 20000;
'''

PRELUDE_SAMPLED_RECOVERY = RECOVERED_BLOB + r'''
result.prelude = {samples: [87, 88].map(index => ({...result.samples[index]}))};
delete result.samples[87].decks; delete result.samples[88].decks;
for (const row of result.samples) row.wall += 20000;
'''

ABORTED_FETCH = r'''
const fetchUrl = 'http://127.0.0.1/library/clip.mp4';
result.events.push({type: 'asset-request-aborted', url: fetchUrl, wall: 12000});
result.requestFailures = [Object.freeze({wall: 12100, phase: 'controls', url: fetchUrl,
  resourceType: 'fetch', failure: {errorText: 'cancelled'}})];
Object.freeze(result.requestFailures);
'''

PARKED_BLOB = r'''
// Timings default to the original held-source cancellation. Other two native
// failures use the same observed ownership/parking/admission sequence below.
const parkedCase = globalThis.parkedCase || {id: 'loop-2', before: 38178, error: 38504,
  first: 38429, parked: 38642, lastPark: 42006, resume: 42157,
  frames: [42163, 42196], visible: 42196, promoted: 43501};
const parkedUrl = 'blob:http://127.0.0.1/parked-' + parkedCase.id;
const oldUrl = 'blob:http://127.0.0.1/outgoing-' + parkedCase.id;
const makeParkRow = (wall, phase, paused, visible, active, count, current) => {
  const points = [{wall: parkedCase.first, mediaTime: 0, changes: 1},
    {wall: parkedCase.frames[0], mediaTime: 1 / 30, changes: 2},
    {wall: parkedCase.frames[1], mediaTime: 2 / 30, changes: 3}].slice(0, count);
  const last = points.at(-1), progress = {schema: 1, supported: true, live: true,
    url: parkedUrl, epoch: 1, changes: count, sourceChanges: count,
    lastChangeWall: last?.wall ?? null, mediaTime: last?.mediaTime ?? null,
    foreground: visible, running: visible, foregroundSince: visible ? parkedCase.visible : null,
    lastForegroundChangeWall: visible ? parkedCase.visible : null,
    maxGapMs: visible ? wall - parkedCase.visible : 0,
    currentGapMs: visible ? wall - parkedCase.visible : 0,
    lifetimeMaxGapMs: visible ? wall - parkedCase.visible : 0, trace: points};
  const outgoing = {id: parkedCase.id, deck: 0, active: !active, populated: true,
    src: oldUrl, currentSrc: oldUrl, paused: false, seeking: false, ready: 4,
    current, duration: 6, decoded: current, callbacks: wall, nativeError: null,
    progress: {schema: 1, supported: true, live: true, url: oldUrl, epoch: 1,
      changes: wall, sourceChanges: wall, lastChangeWall: wall, mediaTime: current,
      foreground: true, running: true, foregroundSince: 1, lastForegroundChangeWall: wall,
      currentGapMs: 0, maxGapMs: 140, lifetimeMaxGapMs: 140}};
  const incoming = {id: parkedCase.id, deck: 1, active, populated: true, src: parkedUrl,
    currentSrc: count ? parkedUrl : '', paused, seeking: false, ready: count ? 4 : 0,
    current: last?.mediaTime ?? 0, decoded: last?.mediaTime ?? null, callbacks: count + 1,
    weight: visible ? active ? 1 : .1 : 0, muted: !visible, nativeError: null, progress};
  const node = {id: parkedCase.id, deck: active ? 1 : 0, phase, busy: !active,
    resting: false, paused: false, nativeError: null, current, decoded: current,
    callbacks: wall, progress: active ? progress : outgoing.progress};
  return {wall, running: true, hidden: false, audioState: 'running', lastFailure: null,
    standbys: active ? 0 : 1, progressSummary: {suspensionCount: 0}, nodes: [node], decks: [outgoing, incoming]};
};
const parkRows = [makeParkRow(parkedCase.before, 'PRIMING', false, false, false, 0, .2)];
for (let wall = parkedCase.parked; wall < parkedCase.lastPark; wall += 140)
  parkRows.push(makeParkRow(wall, 'READY', true, false, false, 1, .4 + (wall - parkedCase.parked) / 1000));
parkRows.push(makeParkRow(parkedCase.lastPark, 'READY', true, false, false, 1, 5.9));
const hiddenResume = parkedCase.resume
  ? makeParkRow(parkedCase.resume, 'READY', false, false, false,
    1 + parkedCase.frames.filter(wall => wall <= parkedCase.resume).length, .01) : null;
if (hiddenResume) parkRows.push(hiddenResume);
parkRows.push(makeParkRow(parkedCase.visible + 50, 'CROSSFADING', false, true, false, 3, .02));
const firstVisibleRow = parkRows.at(-1), resumeRow = hiddenResume || firstVisibleRow;
parkRows.push(makeParkRow(parkedCase.visible + 700, 'CROSSFADING', false, true, false, 3, .2));
parkRows.push(makeParkRow(parkedCase.promoted, 'ACTIVE', false, true, true, 3, .3));
result.progressSchema = 1; result.samples = []; result.prelude = {samples: parkRows};
result.requestFailures = [{wall: parkedCase.error, url: parkedUrl, method: 'GET',
  resourceType: 'other', failure: {errorText: 'cancelled'}}];
'''


PARKED_THEN_RETIRED_BLOB = r'''
// Native run 42457345385 held-source timings: the later ordinary retirement
// must not invalidate a separately proven earlier preparation/admission.
globalThis.parkedCase = {id: 'loop-4', before: 23522, error: 23548, first: 23507,
  parked: 23693, lastPark: 25749, frames: [25928, 25959],
  visible: 25959, promoted: 27349};
''' + PARKED_BLOB + r'''
parkRows[0] = makeParkRow(parkedCase.before, 'READY', true, false, false, 1, .2);
const retiredAt = 118092;
result.events.push({type: 'resource-retired', role: 'deck', id: parkedCase.id,
  url: parkedUrl, wall: retiredAt, readyState: 0, paused: true});
result.consoleErrors.push({wall: 118161, url: parkedUrl,
  message: 'Failed to load resource: The operation couldn’t be completed. (WebKitBlobResource error 1.)'});
parkRows.push({wall: 118200, nodes: [], decks: []});
'''


def classify(mutation: str = '') -> dict:
    program = FIXTURE + mutation + '\nprocess.stdout.write(JSON.stringify(analyse(result)));'
    completed = subprocess.run(['node', '-e', program, str(VERIFIER)], check=True,
                               capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


def classify_resources(mutation: str) -> dict:
    program = FIXTURE + mutation + r'''
const resourceErrors = require(process.argv[1]).classifyResourceErrors(result);
process.stdout.write(JSON.stringify({pass: resourceErrors.unexpected.length === 0, resourceErrors}));
'''
    completed = subprocess.run(['node', '-e', program, str(VERIFIER)], check=True,
                               capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


class WebKitVerifierTests(unittest.TestCase):
    def test_studio_proofs_target_watch_and_preserve_seeded_controls(self):
        program = r'''
const {studioPageUrl} = require(process.argv[1]);
const urls = [
  studioPageUrl('http://127.0.0.1:8456/', '?seed=7&mix=s0.1.2.3&evolve=0&proof=1'),
  studioPageUrl('https://example.invalid/subpath/', '?proof=1'),
  studioPageUrl('https://example.invalid/subpath/index.html'),
];
process.stdout.write(JSON.stringify(urls));
'''
        completed = subprocess.run(['node', '-e', program, str(VERIFIER)], check=True,
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(completed.stdout), [
            'http://127.0.0.1:8456/watch.html?seed=7&mix=s0.1.2.3&evolve=0&proof=1',
            'https://example.invalid/subpath/watch.html?proof=1',
            'https://example.invalid/subpath/watch.html',
        ])

    def assert_refused(self, mutation: str, check: str) -> dict:
        summary = classify(mutation)
        self.assertFalse(summary['pass'], summary)
        self.assertFalse(summary['checks'][check], summary)
        return summary

    def test_healthy_progression_with_native_wraps_and_successors_passes(self):
        summary = classify()
        self.assertTrue(summary['pass'], summary)
        self.assertGreater(summary['wraps'], 0)
        self.assertEqual(set(summary['changedSlots']), {'loop-1', 'loop-2', 'loop-3', 'loop-4'})
        self.assertEqual(summary['births'], 8)

    def test_proven_prior_blob_retirement_is_reported_without_discarding_raw_errors(self):
        summary = classify(RETIRED_BLOB)
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(len(summary['resourceErrors']['expectedRetirements']), 2)
        self.assertEqual(summary['resourceErrors']['unexpected'], [])
        self.assertEqual(summary['resourceErrors']['expectedRetirements'][0]['lagMs'], 100)

    def test_delayed_retirement_message_is_allowed_without_source_readmission(self):
        summary = classify(RETIRED_BLOB + '''
result.events[0].wall = 3100;
result.samples[100].decks = [{active: false, populated: false, src: '', currentSrc: retiredUrl}];
''')
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['resourceErrors']['expectedRetirements'][0]['lagMs'], 9000)

    def test_source_readmission_after_error_invalidates_retirement_proof(self):
        for deck in (
            "{active: false, populated: true, src: retiredUrl, currentSrc: ''}",
            "{active: true, populated: true, src: 'blob:new', currentSrc: retiredUrl}",
            "{active: true, populated: true, src: retiredUrl, currentSrc: retiredUrl}",
        ):
            with self.subTest(deck=deck):
                self.assert_refused(RETIRED_BLOB + 'result.samples[100].decks = [' + deck + '];', 'noErrors')

    def test_browser_cancellation_dialect_still_requires_the_same_positive_evidence(self):
        for fixture, category in (
            (RETIRED_BLOB, 'expectedRetirements'),
            (RECOVERED_BLOB, 'recoveredReads'),
            (ABORTED_FETCH, 'expectedAborts'),
        ):
            with self.subTest(category=category):
                summary = classify(fixture + '''
result.requestFailures = [{...result.requestFailures[0], failure: {errorText: 'net::ERR_ABORTED'}}];
''')
                self.assertTrue(summary['pass'], summary)
                self.assertTrue(summary['resourceErrors'][category])
        self.assert_refused('''
result.requestFailures = [{wall: 12100, url: 'blob:unexplained', failure: {errorText: 'net::ERR_ABORTED'}}];
''', 'noErrors')

    def test_verified_delayed_retirement_does_not_hide_a_native_hold_or_error(self):
        self.assert_refused(RETIRED_BLOB + '''
result.events[0].wall = 3100;
result.samples.slice(800, 840).forEach(row => {row.nodes[0].decoded = .5;});
''', 'decodedProgress')
        self.assert_refused(RETIRED_BLOB + '''
result.events[0].wall = 3100;
result.samples[900].nodes[0].nativeError = {code: 3, message: 'Decode failed'};
''', 'validMedia')

    def test_unknown_or_active_resource_failures_are_not_retirement_cancellations(self):
        for mutation in (
            "result.events[0].url = 'blob:http://127.0.0.1/different';",
            'result.events[0].wall = 12200;',
            'result.events[0].wall = null;',
            'result.events[0].paused = false;',
            'result.events[0].readyState = 4;',
            "result.events[0].type = 'resident';",
            "result.events[0].role = 'unknown';",
            "result.requestFailures[0].failure.errorText = 'network failed';",
            "result.requestFailures[0].url = 'http://127.0.0.1/library/clip.mp4';",
            "result.requestFailures[0].wall = null;",
            "result.samples[86].decks = [{active: true, populated: true, src: retiredUrl, currentSrc: retiredUrl}];",
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(RETIRED_BLOB + mutation, 'noErrors')

    def test_retirement_does_not_hide_other_console_errors(self):
        self.assert_refused(RETIRED_BLOB + r'''
result.consoleErrors = [{wall: 12100, url: retiredUrl, message: 'A real script error'}];
''', 'noErrors')

    def test_cancelled_blob_read_requires_proven_frame_recovery(self):
        summary = classify(RECOVERED_BLOB)
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['resourceErrors']['unexpected'], [])
        recovered = summary['resourceErrors']['recoveredReads']
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]['url'], 'blob:http://127.0.0.1/recovered')
        self.assertEqual([frame['decoded'] for frame in recovered[0]['frames']], [.6, .7])
        self.assertEqual([frame['callbacks'] for frame in recovered[0]['frames']], [101, 102])

    def test_deliberately_aborted_fetch_is_reported_with_exact_prior_proof(self):
        summary = classify(ABORTED_FETCH)
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(len(summary['resourceErrors']['expectedAborts']), 1)
        self.assertEqual(summary['resourceErrors']['expectedAborts'][0]['lagMs'], 100)

    def test_hidden_preparation_cancellation_requires_verified_same_source_admission(self):
        cases = (
            {'id': 'loop-2', 'before': 38178, 'error': 38504, 'first': 38429,
             'parked': 38642, 'lastPark': 42006, 'resume': 42157, 'frames': [42163, 42196],
             'visible': 42196, 'promoted': 43501},
            {'id': 'loop-4', 'before': 8938, 'error': 9133, 'first': 9138,
             'parked': 9143, 'lastPark': 14861, 'frames': [14939, 14973],
             'visible': 14973, 'promoted': 16352},
            {'id': 'loop-3', 'before': 19270, 'error': 19527, 'first': 19455,
             'parked': 19664, 'lastPark': 23322, 'resume': 23538, 'frames': [23506, 23541],
             'visible': 23542, 'promoted': 24960},
        )
        for case in cases:
            with self.subTest(case=case['id']):
                summary = classify_resources('globalThis.parkedCase = ' + json.dumps(case) + ';\n' + PARKED_BLOB)
                self.assertTrue(summary['pass'], summary)
                self.assertEqual(summary['resourceErrors']['recoveredReads'], [])
                proof = summary['resourceErrors']['admittedPreparations'][0]
                self.assertEqual(proof['id'], case['id'])
                self.assertEqual(proof['deck'], 1)
                self.assertEqual(proof['epoch'], 1)
                self.assertEqual([frame['wall'] for frame in proof['frames']], case['frames'])
                self.assertEqual(proof['promotedAt'], case['promoted'])

    def test_proven_later_retirement_preserves_prior_preparation_admission(self):
        summary = classify_resources(PARKED_THEN_RETIRED_BLOB)
        self.assertTrue(summary['pass'], summary)
        errors = summary['resourceErrors']
        self.assertEqual(errors['recoveredReads'], [])
        self.assertEqual(errors['expectedRetirements'], [{
            'kind': 'consoleErrors', 'index': 0, 'url': 'blob:http://127.0.0.1/parked-loop-4',
            'wall': 118161, 'role': 'deck', 'id': 'loop-4', 'retiredAt': 118092, 'lagMs': 69,
        }])
        proof = errors['admittedPreparations'][0]
        self.assertEqual((proof['id'], proof['deck'], proof['epoch']), ('loop-4', 1, 1))
        self.assertEqual(proof['bracket'], [23522, 23693])
        self.assertEqual(proof['lastParkedAt'], 25749)
        self.assertEqual([frame['wall'] for frame in proof['frames']], [25928, 25959])
        self.assertEqual((proof['foregroundAt'], proof['promotedAt']), (25959, 27349))

    def test_unproven_retirement_console_error_still_blocks_admission(self):
        mutations = (
            'result.events.length = 0;',
            "result.events[0].url = 'blob:other';",
            'result.events[0].wall = 118162;',
            'result.events[0].wall = null;',
            'result.events[0].readyState = 4;',
            'result.events[0].paused = false;',
            "result.events[0].type = 'resident';",
            "result.events[0].role = 'unknown';",
            "result.consoleErrors[0].message = 'Fatal network failure';",
            'result.consoleErrors[0].wall = parkedCase.error;',
            "parkRows.at(-1).decks = [{populated: true, active: false, src: parkedUrl}];",
            "parkRows.at(-1).decks = [{populated: true, active: true, src: '', currentSrc: parkedUrl}];",
            "result.consoleErrors.push({...result.consoleErrors[0], wall: parkedCase.error});",
            "result.consoleErrors.push({...result.consoleErrors[0], message: 'Fatal decoder failure'});",
            "result.httpErrors.push({wall: parkedCase.error, url: parkedUrl, status: 500});",
            "parkRows[2].decks[1].nativeError = {code: 3};",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                summary = classify_resources(PARKED_THEN_RETIRED_BLOB + mutation)
                self.assertFalse(summary['pass'], summary)
                self.assertEqual(summary['resourceErrors']['admittedPreparations'], [])

    def test_hidden_preparation_requires_every_ownership_parking_and_admission_fact(self):
        mutations = (
            'parkRows[1].decks[1].active = true;',
            'parkRows[1].decks[1].weight = .01;',
            'parkRows[1].decks[1].muted = false;',
            'parkRows[1].decks[1].paused = false;',
            'parkRows[1].decks[1].seeking = true;',
            'parkRows[1].decks[1].ready = 2;',
            "parkRows[1].nodes[0].phase = 'ACTIVE';",
            'parkRows[1].nodes[0].busy = false;',
            'parkRows[1].nodes[0].resting = true;',
            'parkRows[1].decks[1].progress.foregroundSince = 1;',
            'parkRows[1].decks[1].progress.maxGapMs = 100;',
            '''parkRows.unshift(structuredClone(parkRows[0]));
parkRows[0].wall -= 140; parkRows[0].decks[1].progress.foregroundSince = 1;''',
            'parkRows[2].running = false;',
            'parkRows[2].hidden = true;',
            "parkRows[2].audioState = 'suspended';",
            'parkRows[2].progressSummary.suspensionCount = 1;',
            "parkRows[2].lastFailure = 'native failure';",
            'parkRows[2].standbys = 2;',
            "parkRows[2].decks[1].src = 'blob:other';",
            'parkRows[2].decks[1].progress.epoch = 2;',
            'parkRows[2].decks[1].deck = 0;',
            'parkRows[2].decks[1].nativeError = {code: 3};',
            "parkRows[2].decks[0].progress.url = 'blob:other';",
            'parkRows[2].decks[0].progress.epoch = 2;',
            'resumeRow.decks[0].current = 6;',
            'firstVisibleRow.decks[1].progress.foregroundSince = parkedCase.frames[0];',
            'resumeRow.decks[1].paused = true;',
            'resumeRow.decks[1].seeking = true;',
            'parkRows.at(-1).decks[1].active = false;',
            'parkRows.at(-1).decks[1].progress.epoch = 2;',
            'parkRows.at(-1).decks[1].progress.foreground = false;',
            'parkRows.at(-1).decks[1].progress.running = false;',
            'parkRows.forEach(row => {row.decks[0].decoded = .1;});',
            '''parkRows.filter(row => row.decks[1].progress.foreground).forEach(row => {
  const p = row.decks[1].progress; p.trace.pop(); p.changes = p.sourceChanges = 2;
  p.lastChangeWall = parkedCase.frames[0]; p.mediaTime = 1 / 30;
});''',
            'parkRows.splice(-2);',
            'parkRows.splice(3, 12);',
            'parkRows[0].wall -= 1000;',
            'delete result.progressSchema;',
            "result.requestFailures[0].failure.errorText = 'network failed';",
            "result.requestFailures[0].resourceType = 'fetch';",
            "result.requestFailures[0].method = 'POST';",
            "result.consoleErrors.push({wall: parkedCase.error, url: parkedUrl, message: 'decode failure'});",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                summary = classify_resources(PARKED_BLOB + mutation)
                self.assertFalse(summary['pass'], summary)
                self.assertEqual(summary['resourceErrors'].get('admittedPreparations', []), [])

    def test_hidden_resume_cannot_delay_visibility_beyond_its_evidence_deadline(self):
        # Two early decoded frames cannot justify a later visibility boundary.
        case = {'id': 'loop-2', 'before': 38178, 'error': 38504, 'first': 38429,
                'parked': 38642, 'lastPark': 42006, 'resume': 42157,
                'frames': [42163, 42196], 'visible': 43007, 'promoted': 44312}
        summary = classify_resources('globalThis.parkedCase = ' + json.dumps(case) + ';\n' + PARKED_BLOB)
        self.assertFalse(summary['pass'], summary)
        self.assertEqual(summary['resourceErrors']['admittedPreparations'], [])

    def test_unknown_http_request_failure_cannot_use_abort_classification(self):
        for mutation in (
            'result.events.length = 0;',
            'result.events[0].wall = 12200;',
            'result.events[0].wall = 10000;',
            'result.events[0].wall = null;',
            "result.events[0].url = 'http://127.0.0.1/library/other.mp4';",
            "result.events[0].type = 'resource-retired';",
            "result.requestFailures = [{...result.requestFailures[0], resourceType: 'media'}];",
            "result.requestFailures = [{...result.requestFailures[0], failure: {errorText: 'network failed'}}];",
            'result.httpErrors.push({url: fetchUrl, status: 500});',
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(ABORTED_FETCH + mutation, 'noErrors')

    def test_cancelled_blob_without_same_resource_progress_cannot_pass(self):
        for mutation in (
            'delete result.samples[87].decks; delete result.samples[88].decks;',
            'delete result.samples[88].decks;',
            'result.samples[88].decks[0].decoded = .6;',
            'result.samples[88].decks[0].callbacks = 101;',
            'result.samples[88].decks[0].decoded = null;',
            'result.samples[88].decks[0].callbacks = null;',
            "result.samples[88].decks[0].id = 'loop-2';",
            'result.samples[88].decks[0].deck = 1;',
            "result.samples[88].decks[0].src = 'blob:wrong';",
            "result.samples[88].decks[0].currentSrc = 'blob:wrong';",
            'result.requestFailures = [{...result.requestFailures[0], wall: 11000}];',
            'result.requestFailures = [{...result.requestFailures[0], wall: 12500}];',
            'result.requestFailures = [{...result.requestFailures[0], wall: null}];',
            "result.requestFailures = [{...result.requestFailures[0], url: 'http://127.0.0.1/clip.mp4'}];",
            "result.requestFailures = [{...result.requestFailures[0], failure: {errorText: 'network failed'}}];",
            "result.samples[88].decks[0].nativeError = {code: 3, message: 'decode failure'};",
            "result.samples[89].decks = [{...result.samples[88].decks[0], nativeError: {code: 3}}];",
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(RECOVERED_BLOB + mutation, 'noErrors')

    def test_recovered_read_does_not_hide_console_http_or_continuity_failures(self):
        for mutation in (
            "result.consoleErrors.push({wall: 12100, url: recoveredUrl, message: 'Failed to load resource: The operation couldn’t be completed. (WebKitBlobResource error 1.)'});",
            'result.httpErrors.push({wall: 12100, url: recoveredUrl, status: 404});',
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(RECOVERED_BLOB + mutation, 'noErrors')
        self.assert_refused(RECOVERED_BLOB + '''
result.samples.slice(800, 840).forEach(row => {row.nodes[0].decoded = .5;});
''', 'decodedProgress')

    def test_native_callback_coverage_resolves_full_loop_phase_alias(self):
        summary = classify(NATIVE_PROGRESS + 'result.samples.splice(201, 19);')
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['verdict'], 'PASS')
        self.assertEqual(summary['progressCoverage']['maxSampleGapMs'], 2800)
        self.assertLess(summary['longestDecodedHoldMs'], 2000)

    def test_legacy_sparse_polling_is_inconclusive_even_with_changed_phase(self):
        for removed in (19, 20):
            with self.subTest(removed=removed):
                summary = self.assert_refused(f'result.samples.splice(201, {removed});', 'observationCoverage')
                self.assertEqual(summary['verdict'], 'INCONCLUSIVE')
                self.assertTrue(summary['checks']['decodedProgress'])

    def test_current_schema_requires_complete_consistent_native_evidence(self):
        for mutation in (
            'delete result.samples[800].progressSummary;',
            'delete result.samples[800].progressSummary.supported;',
            'delete result.samples[800].progressSummary.suspensionCount;',
            'result.samples[800].progressSummary.maxGapMs = 0;',
            'result.samples[800].progressSummary.retiredCount = 0;',
            'delete result.samples[800].decks;',
            'result.samples[800].decks[0].active = false;',
            'result.samples[800].decks[0].src = "blob:other";',
            'delete result.samples[800].nodes[0].progress;',
            'result.samples[800].nodes[0].progress.supported = false;',
            'result.samples[800].nodes[0].progress.epoch = 0;',
            'result.samples[800].nodes[0].progress.url = "blob:other";',
            'result.samples[800].nodes[0].progress.changes = 1;',
            'result.samples[800].nodes[0].progress.sourceChanges = 0;',
            'result.samples[800].nodes[0].progress.lastForegroundChangeWall -= 100;',
            'result.samples[800].nodes[0].progress.foregroundSince = -1;',
            'result.samples[800].nodes[0].progress.currentGapMs = -1;',
            'result.samples[800].nodes[0].progress.lifetimeMaxGapMs = 0;',
            'result.samples[800].nodes[0].progress.mediaTime = null;',
            'result.progressSchema = 2;',
            'delete result.progressSchema;',
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(NATIVE_PROGRESS + mutation, 'observationCoverage')

    def test_one_native_stall_between_polls_is_tolerated_and_reported(self):
        # The running maximum stays latched at the stall for the rest of the run (and after its source is
        # gone); only the rise opens an episode, so the latched value must not condemn the run.
        for mutation in (
            'result.samples.slice(800).forEach(row => {row.progressSummary.maxGapMs = 2100;});',
            'result.samples.slice(500).forEach(row => {row.progressSummary.maxGapMs = 2100;});',
        ):
            with self.subTest(mutation=mutation):
                summary = classify(NATIVE_PROGRESS + mutation)
                self.assertTrue(summary['pass'], summary)
                self.assertEqual(summary['stalls'], {'episodes': 1, 'peakMs': 2100, 'tolerated': True})
                self.assertEqual(summary['progressCoverage']['nativeMaximumGapMs'], 2100)

    def test_a_stalled_run_that_never_recovers_or_stalls_repeatedly_still_fails(self):
        three = (
            'result.samples.slice(300).forEach(row => {row.progressSummary.maxGapMs = 2100;});\n'
            'result.samples.slice(600).forEach(row => {row.progressSummary.maxGapMs = 2200;});\n'
            'result.samples.slice(900).forEach(row => {row.progressSummary.maxGapMs = 2300;});')
        for mutation, episodes in (
            # One stall longer than the cap: the decoder stayed frozen.
            ('result.samples.slice(800).forEach(row => {row.progressSummary.maxGapMs = 4500;});', 1),
            # Growing without end, as a frozen decoder reports.
            ('result.samples.slice(800).forEach((row, index) => '
             '{row.progressSummary.maxGapMs = 2100 + index * 137;});', 1),
            # Three separate stalls, each recovered, each higher than the last.
            (three, 3),
        ):
            with self.subTest(mutation=mutation):
                summary = self.assert_refused(NATIVE_PROGRESS + mutation, 'decodedProgress')
                self.assertEqual(summary['verdict'], 'FAIL')
                self.assertEqual(summary['stalls']['episodes'], episodes)
                self.assertFalse(summary['stalls']['tolerated'])

    def test_two_recovered_stalls_pass(self):
        two = (
            'result.samples.slice(300).forEach(row => {row.progressSummary.maxGapMs = 2100;});\n'
            'result.samples.slice(700).forEach(row => {row.progressSummary.maxGapMs = 2600;});')
        summary = classify(NATIVE_PROGRESS + two)
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['stalls'], {'episodes': 2, 'peakMs': 2600, 'tolerated': True})

    def test_provisional_incoming_may_await_its_first_tracked_frame(self):
        summary = classify(NATIVE_PROGRESS + '''
const row = result.samples[800];
row.decks.push({id: 'loop-1', deck: 0, active: false, populated: true, paused: false,
  src: 'blob:incoming', currentSrc: 'blob:incoming',
  progress: {...row.nodes[0].progress, url: 'blob:incoming', epoch: 2, changes: 500,
    sourceChanges: 0, lastChangeWall: null, mediaTime: null, foregroundSince: row.wall}});
''')
        self.assertTrue(summary['pass'], summary)

    def test_hidden_global_pause_does_not_pass_a_sustained_run(self):
        self.assert_refused(NATIVE_PROGRESS + '''
result.samples.slice(800).forEach(row => {row.progressSummary.suspensionCount = 1;});
''', 'noUnexpectedPause')

    def test_trace_proves_recovery_within_original_deadline_after_late_host_poll(self):
        summary = classify_resources(TRACE_RECOVERY)
        self.assertTrue(summary['pass'], summary)
        frames = summary['resourceErrors']['recoveredReads'][0]['frames']
        self.assertEqual([frame['wall'] for frame in frames], [12200, 12400])
        self.assertEqual([frame['origin'] for frame in frames], ['callback-trace'] * 2)

    def test_recorded_prelude_trace_proves_same_source_read_recovery(self):
        summary = classify_resources(PRELUDE_TRACE_RECOVERY)
        self.assertTrue(summary['pass'], summary)
        frames = summary['resourceErrors']['recoveredReads'][0]['frames']
        self.assertEqual([frame['wall'] for frame in frames], [12200, 12400])
        self.assertEqual([frame['origin'] for frame in frames], ['callback-trace'] * 2)

    def test_prelude_recovery_rejects_wrong_late_or_invalid_source_evidence(self):
        for mutation in (
            "result.prelude.samples[0].decks[0].currentSrc = 'blob:other';",
            'callbackProof.trace[1].wall = 13200; callbackProof.lastChangeWall = 13200;',
            'callbackProof.trace[1].mediaTime = .6; callbackProof.mediaTime = .6;',
            'callbackProof.epoch = 0;',
            'callbackProof.supported = false;',
            'result.prelude.samples[0].decks[0].nativeError = {code: 3};',
            '''result.samples[0].decks = [{...result.prelude.samples[0].decks[0],
              progress: {...callbackProof, epoch: 2}}];''',
        ):
            with self.subTest(mutation=mutation):
                summary = classify_resources(PRELUDE_TRACE_RECOVERY + mutation)
                self.assertFalse(summary['pass'], summary)
                self.assertEqual(summary['resourceErrors']['recoveredReads'], [])

    def test_prelude_resource_samples_do_not_mutate_or_extend_sustained_analysis(self):
        program = FIXTURE + PRELUDE_SAMPLED_RECOVERY + r'''
const assert = require('node:assert/strict');
const samples = result.samples, before = JSON.stringify(result);
const summary = analyse(result);
assert.equal(result.samples, samples);
assert.equal(JSON.stringify(result), before);
process.stdout.write(JSON.stringify(summary));
'''
        completed = subprocess.run(['node', '-e', program, str(VERIFIER)], check=True,
                                   capture_output=True, text=True, timeout=15)
        summary = json.loads(completed.stdout)
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['samples'], 1300)
        frames = summary['resourceErrors']['recoveredReads'][0]['frames']
        self.assertEqual([frame['wall'] for frame in frames], [12180, 12320])
        self.assert_refused(PRELUDE_SAMPLED_RECOVERY + '''
result.samples.slice(800, 840).forEach(row => {row.nodes[0].decoded = .5;});
''', 'decodedProgress')
        self.assert_refused(PRELUDE_SAMPLED_RECOVERY + 'result.elapsedMs = 1000;', 'fullDuration')

    def test_prelude_readmission_cannot_be_hidden_by_retirement_classification(self):
        summary = classify_resources(RETIRED_BLOB + '''
result.prelude = {samples: [{wall: 12050, decks: [{active: true, populated: true,
  src: retiredUrl, currentSrc: retiredUrl}]}]};
''')
        self.assertFalse(summary['pass'], summary)
        self.assertEqual(summary['resourceErrors']['expectedRetirements'], [])

    def test_retired_bounded_trace_can_prove_same_source_recovery(self):
        summary = classify_resources(TRACE_RECOVERY + '''
result.samples[100].decks = [];
result.samples[100].progressSummary = {retired: [{...callbackProof,
  id: 'loop-1', deck: 0, live: false, retiredAt: 13000, nativeError: null}]};
''')
        self.assertTrue(summary['pass'], summary)

    def test_malformed_or_wrong_source_trace_cannot_explain_cancellation(self):
        for mutation in (
            'delete callbackProof.schema;',
            'callbackProof.supported = false;',
            'callbackProof.live = false;',
            'callbackProof.epoch = 0;',
            'callbackProof.sourceChanges = 0;',
            'callbackProof.changes = 101;',
            'callbackProof.lastChangeWall = 12000;',
            'callbackProof.trace[1].wall = 13200; callbackProof.lastChangeWall = 13200;',
            'callbackProof.trace[1].wall = 14200; callbackProof.lastChangeWall = 14200;',
            'callbackProof.trace[0].wall = -1;',
            'callbackProof.trace[1].mediaTime = .6;',
            'callbackProof.trace[1].changes = 101;',
            'callbackProof.trace.reverse();',
            'callbackProof.trace[0] = null;',
            'result.samples[100].progressSummary = {retired: [null]};',
            'callbackProof.trace = Array(129).fill(callbackProof.trace[0]);',
            'result.samples[100].decks[0].currentSrc = "blob:other";',
            'result.samples[100].decks[0].nativeError = {code: 3};',
            'result.samples[101].decks = [{...result.samples[100].decks[0], progress: {...callbackProof, epoch: 2}}];',
            'result.samples[101].decks = [{...result.samples[100].decks[0], progress: {...callbackProof, mediaTime: .9, trace: [{wall: 12250, mediaTime: .8, changes: 101}, {wall: 12400, mediaTime: .9, changes: 102}]}}];',
            'result.samples[101].progressSummary = {retired: [{...callbackProof, id: "loop-2", deck: 0, retiredAt: 14100}]};',
            'result.samples[100].decks = []; result.samples[100].progressSummary = {retired: [{...callbackProof, id: "loop-1", deck: 0, retiredAt: 12300}]};',
            'result.samples[100].decks = []; result.samples[100].progressSummary = {retired: [{...callbackProof, id: "loop-1", deck: 0, retiredAt: 13000, nativeError: {code: 3}}]};',
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(TRACE_RECOVERY + mutation, 'noErrors')

    def test_sampled_recovery_cannot_mix_current_schema_source_epochs(self):
        self.assert_refused(RECOVERED_BLOB + '''
result.progressSchema = 1;
for (const [n, index] of [87, 88].entries()) {
  const deck = result.samples[index].decks[0];
  deck.progress = {schema: 1, supported: true, live: true, url: recoveredUrl, epoch: n + 1,
    changes: 101 + n, sourceChanges: 1, lastChangeWall: result.samples[index].wall,
    mediaTime: deck.decoded, currentGapMs: 0, maxGapMs: 10, lifetimeMaxGapMs: 10};
}
''', 'noErrors')

    def test_journal_bounds_records_and_propagates_backpressure_and_write_failures(self):
        program = r'''
const assert = require('node:assert/strict');
const {Writable} = require('node:stream');
const {proofJournal} = require(process.argv[1]);
(async () => {
  const records = [];
  const journal = proofJournal('', '', () => new Writable({highWaterMark: 1,
    write(chunk, _, callback) {setImmediate(() => {records.push(JSON.parse(chunk)); callback();});}}));
  await journal.append('sample', {wall: 1}); await journal.close();
  assert.deepEqual(records, [{type: 'sample', value: {wall: 1}}]);
  const failed = proofJournal('', '', () => new Writable({highWaterMark: 1,
    write(_, __, callback) {setImmediate(() => callback(new Error('disk full')));}}));
  await assert.rejects(failed.append('sample', {}), /disk full/);
  await assert.rejects(failed.append('sample', {}), /disk full/);
  await assert.rejects(failed.close(), /disk full/);
  const oversized = proofJournal('', '', () => new Writable({write(_, __, callback) {callback();}}));
  await assert.rejects(oversized.append('sample', 'x'.repeat(2 * 1024 * 1024)), /exceeds 2 MiB/);
  await oversized.close();
  const closeFailure = proofJournal('', '', () => new Writable({
    write(_, __, callback) {callback();}, final(callback) {callback(new Error('flush failed'));}}));
  await assert.rejects(closeFailure.close(), /flush failed/);
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        subprocess.run(['node', '-e', program, str(VERIFIER)], check=True, capture_output=True, text=True, timeout=15)

    def test_dense_prelude_metadata_is_bounded_and_reconstructs_all_raw_evidence(self):
        program = r'''
const assert = require('node:assert/strict');
const {Writable} = require('node:stream');
const {proofJournal, preludeJournalMetadata} = require(process.argv[1]);
const rows = Array.from({length: 40}, (_, index) => ({wall: 1000 + index * 137,
  incoming: {id: 'loop-3', deck: 1, item: 'clip', sha: 'pinned', callbacks: index + 3,
    progress: {url: 'blob:incoming', epoch: 2, sourceChanges: index + 3}}, tracePayload: 'x'.repeat(35000)}));
const prelude = {scope: 'fixture', samples: [{wall: 1}], before: {wall: 2},
  incomingObservations: rows, siblingOverlap: rows.slice(2)};
const before = JSON.stringify(prelude), legacy = {samples: prelude.samples.length,
  incomingObservations: rows, siblingOverlap: rows.slice(2)};
assert.ok(Buffer.byteLength(JSON.stringify(legacy)) > 2 * 1024 * 1024);
(async () => {
  const records = [], journal = proofJournal('', '', () => new Writable({write(chunk, _, done) {
    records.push(JSON.parse(chunk)); done(); }}));
  for (const row of rows) await journal.append('diagnostic-sibling-incoming', row);
  await journal.append('diagnostic-prelude', preludeJournalMetadata(prelude)); await journal.close();
  const metadata = records.at(-1).value, raw = records.slice(0, -1).map(record => record.value);
  assert.equal(metadata.incomingObservations.journalType, 'diagnostic-sibling-incoming');
  assert.equal(metadata.incomingObservations.count, 40);
  assert.equal(metadata.siblingOverlap.source, 'incomingObservations');
  assert.equal(metadata.siblingOverlap.count, 38);
  assert.deepEqual(raw, rows);
  assert.deepEqual(metadata.siblingOverlap.indices.map(index => raw[index]), prelude.siblingOverlap);
  assert.equal(metadata.samples, 1);assert.deepEqual(metadata.before, {wall: 2});
  assert.ok(Buffer.byteLength(JSON.stringify(records.at(-1))) < 10000);
  assert.equal(JSON.stringify(prelude), before);
  // The reference metadata must also work with deserialized final JSON.
  assert.deepEqual(preludeJournalMetadata(JSON.parse(before)), metadata);
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        subprocess.run(['node', '-e', program, str(VERIFIER)], check=True, capture_output=True, text=True, timeout=15)

    def test_prelude_metadata_rejects_unwitnessed_or_changed_source_rows(self):
        program = r'''
const assert = require('node:assert/strict');
const {preludeJournalMetadata} = require(process.argv[1]);
const row = {wall: 100, incoming: {id: 'loop-3', deck: 1, item: 'clip', sha: 'hash',
  callbacks: 4, progress: {url: 'blob:one', epoch: 2, sourceChanges: 3}}};
const prelude = {samples: [], incomingObservations: [row], siblingOverlap: [row]};
for (const change of [copy => {copy.incoming.progress.epoch++;}, copy => {copy.incoming.sha = 'other';},
  copy => {copy.incoming.callbacks++;}, copy => {copy.wall++;}, copy => {copy.extra = 'not in raw';}]) {
  const changed = structuredClone(row); change(changed);
  assert.throws(() => preludeJournalMetadata({...prelude, siblingOverlap: [changed]}), /witnessed|match/);
}
assert.throws(() => preludeJournalMetadata({...prelude, siblingOverlap: [row, row]}), /order|duplicate/);
assert.throws(() => preludeJournalMetadata({...prelude, incomingObservations: []}), /witnessed/);
const ordinary = {samples: [{wall: 1}], before: {wall: 2}, after: {wall: 3}};
assert.deepEqual(preludeJournalMetadata(ordinary), {samples: 1, before: {wall: 2}, after: {wall: 3}});
'''
        subprocess.run(['node', '-e', program, str(VERIFIER)], check=True, capture_output=True, text=True, timeout=15)

    def test_recorded_failure_after_completed_sampling_cannot_pass(self):
        self.assert_refused("result.failure = 'Screenshot failed after the browser closed';", 'noFailure')

    def test_missing_or_disappeared_residents_cannot_pass(self):
        for mutation in (
            'result.samples.forEach(row => row.nodes.pop());',
            'result.samples.slice(800).forEach(row => {row.nodes = []; row.populated = row.playing = 0;});',
            "result.samples.slice(800).forEach(row => {row.nodes[0].id = 'unexpected-slot';});",
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(mutation, 'validMedia')

    def test_rising_callback_count_does_not_hide_frozen_media(self):
        summary = self.assert_refused('''
result.samples.slice(800, 830).forEach(row => {
  row.nodes[0].current = row.nodes[0].decoded = .5;
});
''', 'jointProgress')
        self.assertFalse(summary['checks']['decodedProgress'])
        self.assertGreaterEqual(summary['longestJointHoldMs'], 2000)

    def test_advancing_current_time_does_not_hide_frozen_decoded_time(self):
        self.assert_refused('''
result.samples.slice(800, 830).forEach(row => {row.nodes[0].decoded = .5;});
''', 'decodedProgress')

    def test_rest_boundary_does_not_reset_a_continuous_frame_hold(self):
        summary = self.assert_refused('''
result.samples.slice(800, 830).forEach((row, index) => {
  const node = row.nodes[0];
  node.current = node.decoded = .5;
  node.resting = index < 15;
  node.phase = node.resting ? 'RESTING' : 'ACTIVE';
});
''', 'decodedProgress')
        self.assertGreaterEqual(summary['longestDecodedHoldMs'], 4000)
        self.assertLess(summary['longestRestingDecodedHoldMs'], 2000)

    def test_resting_residents_must_continue_presenting_frames(self):
        for mutation in (
            'node.current = node.decoded = .5;',
            'node.decoded = .5;',
            'node.paused = true;',
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused('''
result.samples.slice(800, 830).forEach(row => {
  const node = row.nodes[0]; node.resting = true; node.phase = 'RESTING';
''' + mutation + '\n});', 'restingProgress')

    def test_healthy_moving_resting_resident_passes(self):
        summary = classify('''
result.samples.slice(800, 900).forEach(row => {
  row.nodes[0].resting = true; row.nodes[0].phase = 'RESTING';
});
''')
        self.assertTrue(summary['pass'], summary)
        self.assertEqual(summary['restingSamples'], 100)
        self.assertEqual(summary['maxResting'], 1)

    def test_runtime_failure_toast_or_event_cannot_pass(self):
        for mutation in (
            "result.samples[900].lastFailure = 'Incoming clip could not be decoded';",
            "result.events.push({type: 'media-failure', message: 'Incoming clip could not be decoded'});",
            "result.events.push({type: 'observer-failure'});",
        ):
            with self.subTest(mutation=mutation):
                self.assert_refused(mutation, 'noErrors')

    def test_structured_console_error_cannot_pass(self):
        self.assert_refused('''
result.consoleErrors.push({message: 'Native media error', phase: 'sustained',
  epochMs: 1794096000000, wall: 120000, location: {url: 'blob:failed-source', lineNumber: 0}});
''', 'noErrors')

    def test_failed_requests_cannot_pass_including_cleanup(self):
        for phase in ('navigation', 'sustained', 'closing'):
            with self.subTest(phase=phase):
                self.assert_refused('''
result.requestFailures = [{url: 'blob:failed-source', method: 'GET', resourceType: 'media',
  failure: {errorText: 'Native resource load failed'}, phase: ''' + json.dumps(phase) + '''}];
''', 'noErrors')


if __name__ == '__main__':
    unittest.main()
