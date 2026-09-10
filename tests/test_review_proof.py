"""Proof-runner fault controls. Synthetic shards; no composition/browser proof.

Run directly with ``python -m unittest -v test_review_proof``. All outputs live
in temporary directories. No media, browser, network or provider is launched.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_review_proof as proof


class ReviewProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.output = self.root / 'runtime-proof' / 'run'
        self.receipt = self.root / 'child.json'

    @staticmethod
    def valid_receipt(**changes):
        value = dict(status='passed', tests_expected=1, tests_run=1,
                     failures=0, errors=0, skipped=0, unexpected_successes=0,
                     expected_failures=0)
        value.update(changes)
        return value

    def child(self, suite):
        with patch.object(proof.unittest.defaultTestLoader, 'loadTestsFromNames', return_value=suite), \
                contextlib.redirect_stderr(io.StringIO()):
            code = proof.child(self.receipt, ['synthetic'])
        return code, json.loads(self.receipt.read_text())

    def run_shards(self, outcomes, *, selected=None, transport='http'):
        registry = {f'shard-{i}': [f'synthetic_{i}'] for i in range(len(outcomes))}
        calls = []

        def launch(command, **kwargs):
            calls.append((command, kwargs))
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            payload, code = outcome
            if payload is not None:
                Path(command[3]).write_text(payload if isinstance(payload, str) else json.dumps(payload))
            return subprocess.CompletedProcess(command, code)

        with patch.object(proof, 'HERE', self.root), patch.object(proof, 'GROUPS', registry), \
                patch.object(proof.subprocess, 'run', side_effect=launch), \
                contextlib.redirect_stdout(io.StringIO()):
            code = proof.run(self.output, transport, selected if selected is not None else list(registry), 1)
        return code, json.loads((self.output / 'summary.json').read_text()), calls

    def assert_failed(self, report):
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(any(report['demonstrated'].values()))

    def test_child_zero_tests_is_not_a_pass(self):
        code, receipt = self.child(unittest.TestSuite())
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'failed')

    def test_child_passing_test_records_expected_count(self):
        suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        code, receipt = self.child(suite)
        self.assertEqual(code, 0)
        self.assertEqual(receipt['tests_expected'], 1)
        self.assertEqual(receipt['tests_run'], 1)

    def test_child_early_stop_is_not_a_pass(self):
        class StopsEarly(unittest.TestCase):
            def run(self, result=None):
                result.startTest(self)
                result.addSuccess(self)
                result.stopTest(self)
                result.stop()
                return result
        suite = unittest.TestSuite([StopsEarly(), unittest.FunctionTestCase(lambda: None)])
        code, receipt = self.child(suite)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['status'], 'failed')

    def test_child_expected_failure_is_not_a_pass(self):
        class Fixture(unittest.TestCase):
            @unittest.expectedFailure
            def runTest(self):
                self.fail('synthetic expected failure')
        code, receipt = self.child(unittest.TestSuite([Fixture()]))
        self.assertEqual(code, 1)
        self.assertEqual(receipt['expected_failures'], 1)

    def test_child_skip_is_not_a_pass(self):
        class Fixture(unittest.TestCase):
            def runTest(self):
                self.skipTest('synthetic skip')
        code, receipt = self.child(unittest.TestSuite([Fixture()]))
        self.assertEqual(code, 1)
        self.assertEqual(receipt['skipped'], 1)

    def test_real_child_process_rejects_empty_selection(self):
        completed = subprocess.run([proof.sys.executable, str(Path(proof.__file__).resolve()),
                                    '--child', str(self.receipt)], capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(json.loads(self.receipt.read_text())['status'], 'failed')

    def test_parent_valid_complete_synthetic_shards(self):
        code, report, calls = self.run_shards([(self.valid_receipt(), 0)] * 2)
        self.assertEqual(code, 0)
        self.assertEqual(report['totals']['tests_run'], 2)
        self.assertTrue(report['complete_group_set'])
        self.assertEqual(len(calls), 2)
        self.assertTrue(report['demonstrated']['served_http'])
        for key in ('physical_device', 'historical_original', 'deployment', 'artist_approval'):
            self.assertFalse(report['demonstrated'][key])

    def test_in_memory_transport_cannot_claim_http(self):
        code, report, calls = self.run_shards([(self.valid_receipt(), 0)], transport='in-memory')
        self.assertEqual(code, 0)
        self.assertFalse(report['demonstrated']['served_http'])
        self.assertEqual(calls[0][1]['env']['PORTVS_BROWSER_TRANSPORT'], 'in-memory')

    def test_partial_selection_cannot_claim_complete_proof(self):
        code, report, _ = self.run_shards([(self.valid_receipt(), 0)] * 2, selected=['shard-0'])
        self.assertEqual(code, 0)
        self.assertFalse(report['complete_group_set'])
        self.assertFalse(any(report['demonstrated'].values()))

    def test_parent_zero_test_receipt_rejected(self):
        code, report, _ = self.run_shards([(self.valid_receipt(tests_expected=0, tests_run=0), 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_incomplete_test_count_rejected(self):
        code, report, _ = self.run_shards([(self.valid_receipt(tests_expected=2), 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_contradictory_pass_receipts_rejected(self):
        for counter in ('failures', 'errors', 'skipped', 'unexpected_successes', 'expected_failures'):
            with self.subTest(counter=counter), tempfile.TemporaryDirectory() as directory:
                self.output = self.root / 'runtime-proof' / Path(directory).name
                code, report, _ = self.run_shards([(self.valid_receipt(**{counter: 1}), 0)])
                self.assertEqual(code, 1)
                self.assert_failed(report)

    def test_parent_invalid_counts_rejected(self):
        for value in (-1, True, 1.5, '1', None):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                self.output = self.root / 'runtime-proof' / Path(directory).name
                code, report, _ = self.run_shards([(self.valid_receipt(tests_run=value), 0)])
                self.assertEqual(code, 1)
                self.assert_failed(report)

    def test_parent_missing_counts_rejected(self):
        payload = self.valid_receipt()
        del payload['skipped']
        code, report, _ = self.run_shards([(payload, 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_non_object_receipt_rejected(self):
        code, report, _ = self.run_shards([('[]', 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_truncated_json_keeps_completed_evidence(self):
        code, report, calls = self.run_shards([(self.valid_receipt(), 0), ('{"status":', 0),
                                              (self.valid_receipt(), 0)])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual([group['status'] for group in report['groups']], ['passed', 'failed', 'passed'])
        self.assert_failed(report)

    def test_parent_duplicate_json_keys_rejected(self):
        payload = json.dumps(self.valid_receipt())[:-1] + ',"tests_run":1}'
        code, report, _ = self.run_shards([(payload, 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_missing_receipt_fails(self):
        code, report, _ = self.run_shards([(None, 0)])
        self.assertEqual(code, 1)
        self.assert_failed(report)

    def test_parent_nonzero_exit_overrides_pass_receipt(self):
        code, report, _ = self.run_shards([(self.valid_receipt(), 7)])
        self.assertEqual(code, 1)
        self.assertEqual(report['groups'][0]['exit_code'], 7)
        self.assert_failed(report)

    def test_parent_timeout_continues_without_retry(self):
        code, report, calls = self.run_shards([subprocess.TimeoutExpired('synthetic', 1),
                                              (self.valid_receipt(), 0)])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 2)
        self.assert_failed(report)

    def test_parent_launch_error_continues_without_retry(self):
        code, report, calls = self.run_shards([OSError('synthetic launch failure'),
                                              (self.valid_receipt(), 0)])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 2)
        self.assert_failed(report)

    def test_empty_group_selection_rejected_before_launch(self):
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(ValueError):
                proof.run(self.output, 'http', [], 1)
        launch.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_unknown_group_rejected_before_launch(self):
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(ValueError):
                proof.run(self.output, 'http', ['unknown'], 1)
        launch.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_duplicate_groups_rejected_before_launch(self):
        group = next(iter(proof.GROUPS))
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(ValueError):
                proof.run(self.output, 'http', [group, group], 1)
        launch.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_invalid_transport_rejected_before_launch(self):
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(ValueError):
                proof.run(self.output, 'automatic-fallback', [next(iter(proof.GROUPS))], 1)
        launch.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_existing_output_never_overwritten(self):
        self.output.mkdir(parents=True)
        marker = self.output / 'summary.json'
        marker.write_text('preserve')
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(FileExistsError):
                proof.run(self.output, 'http', [next(iter(proof.GROUPS))], 1)
        launch.assert_not_called()
        self.assertEqual(marker.read_text(), 'preserve')

    def test_output_escape_rejected(self):
        with patch.object(proof, 'HERE', self.root), patch.object(proof.subprocess, 'run') as launch:
            with self.assertRaises(ValueError):
                proof.run(self.root / 'outside', 'http', [next(iter(proof.GROUPS))], 1)
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
