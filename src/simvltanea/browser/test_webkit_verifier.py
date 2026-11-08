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

ABORTED_FETCH = r'''
const fetchUrl = 'http://127.0.0.1/library/clip.mp4';
result.events.push({type: 'asset-request-aborted', url: fetchUrl, wall: 12000});
result.requestFailures = [Object.freeze({wall: 12100, phase: 'controls', url: fetchUrl,
  resourceType: 'fetch', failure: {errorText: 'cancelled'}})];
Object.freeze(result.requestFailures);
'''


def classify(mutation: str = '') -> dict:
    program = FIXTURE + mutation + '\nprocess.stdout.write(JSON.stringify(analyse(result)));'
    completed = subprocess.run(['node', '-e', program, str(VERIFIER)], check=True,
                               capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


class WebKitVerifierTests(unittest.TestCase):
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
