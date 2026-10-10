"""Prove this composition runs the same shared engine bytes as time-moment-brief.

A copied directory or a configurable environment variable would satisfy every
test here except the one that matters. These tests assert module *identity*: both
consumers resolve one file on disk, its bytes match the SHA-256 recorded by the
extractor, and both adapters bind that one module. Tampering, relocation, or an
environment override fails closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import unittest
import unittest.mock
from pathlib import Path

from simvltanea.browser.shared_engine import (
    SharedEngine,
    SharedEngineUnavailable,
    resolve_shared_engine,
)

TMB_ADAPTER = 'webcodecs-spike/shared-engine-adapter.js'
HERE = Path(__file__).resolve().parent
SIMVLTANEA_ADAPTER = HERE / 'shared-engine-adapter.js'
LAYOUT = {'panels': 4, 'duration': 8.0, 'sweep': 1.4, 'elevation': 0.35}


def node_available() -> bool:
    return shutil.which('node') is not None


def run_node(source: str) -> dict:
    """Run an ES module snippet and return its JSON stdout, failing loudly."""
    result = subprocess.run(
        ['node', '--input-type=module', '-e', source],
        capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise AssertionError(f'node exited {result.returncode}:\n{result.stderr}')
    return json.loads(result.stdout)


class SharedEngineResolutionTest(unittest.TestCase):

    def setUp(self) -> None:
        self.engine = resolve_shared_engine()

    def test_resolves_relative_to_the_checkout(self) -> None:
        self.assertTrue(self.engine.entrypoint.is_file(),
                        'resolved entrypoint does not exist')
        self.assertEqual(self.engine.module_root.name, 'shared-engine')
        self.assertEqual(self.engine.entrypoint.parent, self.engine.module_root)

    def test_every_recorded_digest_matches_the_bytes_on_disk(self) -> None:
        recorded = {e['generated']: e['generated_sha256']
                    for e in self.engine.provenance['files']}
        self.assertTrue(recorded, 'provenance recorded no files; extraction is unproven')
        for relative, expected in recorded.items():
            actual = hashlib.sha256(
                (self.engine.root / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, f'{relative} bytes diverge from provenance')

    def test_required_modules_are_present(self) -> None:
        for module in ('index.js', 'src/spatial-score.js',
                       'src/panoramic-projection.js', 'src/video-texture.js'):
            self.assertTrue((self.engine.module_root / module).is_file(), f'missing {module}')

    def test_no_private_media_is_published(self) -> None:
        """The tracked module carries code and provenance, never recordings."""
        for entry in self.engine.provenance['files']:
            self.assertFalse(entry['generated'].startswith('media/'),
                             'private media must stay in the ignored hydration root')


class AbsentAndTamperedEngineTest(unittest.TestCase):
    """Failure must be loud and specific, never a silent default pose."""

    def test_absent_engine_raises_with_searched_paths(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(SharedEngineUnavailable) as caught:
                resolve_shared_engine(Path(empty))
            message = str(caught.exception)
        self.assertIn('shared engine not found', message)
        self.assertIn('no local copy', message)
        self.assertIn(empty.rsplit('/', 1)[-1], message,
                      'the failure must name what it looked for')

    def test_tampered_bytes_fail_closed(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as staging:
            root = Path(staging) / 'time-moment-brief' / 'shared-engine'
            shutil.copytree(resolve_shared_engine().module_root, root)
            target = root / 'src' / 'spatial-score.js'
            target.write_text(target.read_text() + '\n// local edit\n')
            with self.assertRaises(SharedEngineUnavailable) as caught:
                resolve_shared_engine(root)
        self.assertIn('provenance mismatch', str(caught.exception))
        self.assertIn('spatial-score.js', str(caught.exception))
        self.assertIn('stage_shared_engine.py', str(caught.exception),
                      'the failure must name the command that repairs it')

    def test_environment_cannot_redirect_the_engine(self) -> None:
        """Configuration is not reuse: an override must not select the module."""
        expected = resolve_shared_engine().root
        forged = dict(os.environ, SHARED_ENGINE_ROOT='/tmp/not-the-shared-engine',
                      SHARED_ENGINE='/tmp/not-the-shared-engine')
        with unittest.mock.patch.dict(os.environ, forged, clear=False):
            self.assertEqual(resolve_shared_engine().root, expected)


@unittest.skipUnless(node_available(), 'node is required for adapter identity proof')
class BothConsumersBindOneImplementationTest(unittest.TestCase):
    """The actual cross-repository reuse proof."""

    def test_both_adapters_bind_the_same_module_object(self) -> None:
        engine = resolve_shared_engine()
        # The resolved checkout must be the one that also carries the other
        # consumer's adapter. A worktree of time-moment-brief may sit under a
        # different directory name, so ownership is proven by content, not by
        # the folder a human happened to check the branch out into.
        self.assertEqual(engine.module_root.name, 'shared-engine')
        self.assertTrue((engine.root / TMB_ADAPTER).is_file(),
                        f'{TMB_ADAPTER} is not in the checkout that owns the shared engine')
        report = run_node(f"""
          import tmb from '{engine.root}/{TMB_ADAPTER}';
          import sim from '{SIMVLTANEA_ADAPTER}';
          import * as shared from '{engine.entrypoint}';
          if (tmb.sharedEngine !== shared) throw new Error('time-moment-brief bound a copy');
          if (!sim.assertSharedEngine(shared)) throw new Error('simvltanea refused the module');
          console.log(JSON.stringify({{
            one: true,
            tmbBuild: tmb.SHARED_ENGINE_BUILD_ID,
            simBuild: sim.BUILD_ID,
          }}));
        """)
        self.assertTrue(report['one'])
        self.assertEqual(report['tmbBuild'], report['simBuild'],
                         'consumers disagree about which shared build they run')

    def test_simvltanea_panel_orientation_comes_from_the_shared_evaluator(self) -> None:
        engine = resolve_shared_engine()
        layout = json.dumps(LAYOUT)
        report = run_node(f"""
          import sim from '{SIMVLTANEA_ADAPTER}';
          import * as shared from '{engine.entrypoint}';
          const driver = sim.createPanelDriver(shared, {layout});
          const panels = driver.evaluate(2.0);
          const direct = shared.evaluateSpatialScore(
            {{ blocks: [driver.score.blocks[1]] }},
            2.0 - driver.score.blocks[1].start);
          console.log(JSON.stringify({{ panels, direct }}));
        """)
        self.assertEqual(len(report['panels']), LAYOUT['panels'])
        self.assertAlmostEqual(report['panels'][1]['azimuth'],
                               report['direct']['azimuth'], places=12)
        self.assertAlmostEqual(report['panels'][1]['elevation'],
                               report['direct']['elevation'], places=12)

    def test_simvltanea_adapter_fails_clearly_without_the_module(self) -> None:
        engine = resolve_shared_engine()
        report = run_node(f"""
          import sim from '{SIMVLTANEA_ADAPTER}';
          let message = null;
          try {{ sim.createPanelDriver(null, {json.dumps(LAYOUT)}); }}
          catch (error) {{ message = String(error.message); }}
          console.log(JSON.stringify({{ message }}));
        """)
        self.assertIn('shared engine not found', report['message'])
        self.assertIn('no local copy', report['message'])


if __name__ == '__main__':
    unittest.main()
