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
