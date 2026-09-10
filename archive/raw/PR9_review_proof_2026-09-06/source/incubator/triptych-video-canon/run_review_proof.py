#!/usr/bin/env python3
"""Run bounded review-proof shards with explicit transport and no skipped-pass.

Default HTTP exercises real fetch/WebCrypto. `--transport in-memory` is an
explicit narrower proof, never an automatic fallback. Neither proves physical
devices, historical fidelity, deployment or artist approval. Exit nonzero on any
failure, timeout or skipped test; always retain completed shard evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GROUPS = {
    'model': ['test_composition_model', 'test_authoring_contract',
              'test_composition_render', 'test_browser_runtime.PlanTests',
              'test_browser_boundaries.PlanBoundaryTests'],
    'counts-3-5': [f'test_browser_runtime.BrowserTests.test_{n}_loop_native_continuity' for n in (3,4,5)],
    'counts-6-7': ['test_browser_runtime.BrowserTests.test_6_loop_native_continuity',
                   'test_browser_runtime.BrowserTests.test_7_loop_experimental_continuity'],
    'load-resize': ['test_browser_runtime.BrowserTests.test_container_resize_without_viewport_change',
                    'test_browser_runtime.BrowserTests.test_browser_rejects_altered_media_before_mounting',
                    'test_browser_runtime.BrowserTests.test_resize_while_media_is_loading'],
    'controls': ['test_browser_runtime.BrowserTests.test_native_controls_hold_release_swap_reroll_move',
                 'test_browser_runtime.BrowserTests.test_native_trim_loop_boundaries'],
    'invalid-input': ['test_browser_boundaries.NativeBoundaryTests.test_invalid_plan_rejected_before_media_io_or_mount',
                      'test_browser_boundaries.NativeBoundaryTests.test_error_during_start_cannot_be_overwritten_by_playing'],
    'shared-hidden': ['test_browser_boundaries.NativeBoundaryTests.test_explicit_source_reuse_preserves_independent_clocks_through_resize',
                      'test_browser_boundaries.NativeBoundaryTests.test_zero_size_container_restores_without_reset'],
    'hold-still': ['test_browser_boundaries.NativeBoundaryTests.test_hold_resize_release_and_finish_are_not_restarts',
                   'test_browser_boundaries.NativeBoundaryTests.test_still_video_swap_preserves_loop_boxes_and_unrelated_video'],
    'independent-a': ['test_browser_continuity.ContinuityTests.test_3', 'test_browser_continuity.ContinuityTests.test_4', 'test_browser_continuity.ContinuityTests.test_5', 'test_browser_continuity.ContinuityTests.test_6'],
    'independent-b': ['test_browser_continuity.ContinuityTests.test_7_experimental', 'test_browser_continuity.ContinuityTests.test_container_only', 'test_browser_continuity.ContinuityTests.test_held_loop_survives_resize', 'test_browser_continuity.ContinuityTests.test_reject_wrong_layout'],
    'independent-c': ['test_browser_continuity.ContinuityTests.test_reject_time_reset', 'test_browser_continuity.ContinuityTests.test_reject_same_source_reload', 'test_browser_continuity.ContinuityTests.test_reject_source_reroll', 'test_browser_continuity.ContinuityTests.test_reject_transient_duplicate'],
    'independent-d': ['test_browser_continuity.ContinuityTests.test_reject_transient_removal', 'test_browser_continuity.ContinuityTests.test_reject_same_id_replacement', 'test_browser_continuity.ContinuityTests.test_reject_pause', 'test_browser_continuity.ContinuityTests.test_reject_rate_change'],
}


def child(output: Path, names: list[str]) -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped
    output.write_text(json.dumps(dict(
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), unexpected_successes=len(result.unexpectedSuccesses),
        status='passed' if passed else 'failed'), indent=2)+'\n')
    return 0 if passed else 1


def run(output: Path, transport: str, groups: list[str], timeout: float) -> int:
    output = output.resolve()
    if not output.is_relative_to(HERE / 'runtime-proof') or output == HERE / 'runtime-proof':
        raise ValueError('Evidence output must be a child of runtime-proof inside the incubator')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, transport=transport, python=platform.python_version(),
                  status='running', groups=[], scope='incubator-only; not a whole-repository or hosted-CI check',
                  demonstrated=dict(local_narrow_tests=False, served_http=False, physical_device=False,
                                    historical_original=False, deployment=False, artist_approval=False))
    report_path = output/'summary.json'
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    env = dict(os.environ, PORTVS_BROWSER_TRANSPORT=transport)
    for group in groups:
        path = output/f'{group}.json'
        command = [sys.executable, str(Path(__file__).resolve()), '--child', str(path), *GROUPS[group]]
        started = time.monotonic()
        with (output/f'{group}.log').open('w') as log:
            try:
                process = subprocess.run(command, cwd=HERE, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=timeout)
                facts = json.loads(path.read_text()) if path.exists() else dict(status='failed', reason='no child receipt')
                if process.returncode:
                    facts['status'] = 'failed'
                facts['exit_code'] = process.returncode
            except subprocess.TimeoutExpired:
                facts = dict(status='failed', reason='timeout; incomplete tests are not counted as passed')
        facts.update(group=group, elapsed_seconds=round(time.monotonic()-started,3), tests=GROUPS[group])
        report['groups'].append(facts)
        report_path.write_text(json.dumps(report, indent=2)+'\n')
        print(f"{group}: {facts['status']}", flush=True)
    passed = all(item['status']=='passed' for item in report['groups'])
    report['status'] = 'passed' if passed else 'failed'
    report['totals'] = {key:sum(item.get(key,0) for item in report['groups'])
                        for key in ('tests_run','failures','errors','skipped','unexpected_successes')}
    complete = set(groups) == set(GROUPS)
    report['complete_group_set'] = complete
    report['demonstrated']['local_narrow_tests'] = passed and complete
    report['demonstrated']['served_http'] = passed and complete and transport=='http'
    report['source_sha256'] = {
        path.name:hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(HERE.glob('*')) if path.suffix in ('.py','.js')
    }
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], totals=report['totals'], transport=transport)), flush=True)
    return 0 if passed else 1


def main() -> int:
    if len(sys.argv)>1 and sys.argv[1]=='--child':
        return child(Path(sys.argv[2]), sys.argv[3:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('http','in-memory'), default='http')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group', action='append', choices=tuple(GROUPS))
    parser.add_argument('--timeout', type=float, default=90, help='per-shard timeout, seconds')
    args=parser.parse_args()
    if not 1 <= args.timeout <= 600:
        parser.error('timeout must be in 1..600')
    return run(args.output, args.transport, list(dict.fromkeys(args.group or GROUPS)), args.timeout)


if __name__=='__main__':
    raise SystemExit(main())
