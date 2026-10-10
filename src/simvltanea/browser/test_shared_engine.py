"""Prove this composition executes the accepted shared engine, or refuses.

Every test here is a refusal test or an identity test. A copied directory, an
environment variable, or a manifest that quietly omits the executable graph would
pass a weaker suite; those are exactly the cases the review probe found and this
file covers.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from simvltanea.browser.shared_engine import (
    ENTRYPOINT,
    SharedEngineUnavailable,
    candidate_roots,
    load_pin,
    resolve_shared_engine,
)

HERE = Path(__file__).resolve().parent
TMB_ADAPTER = 'webcodecs-spike/shared-engine-adapter.js'
SIMVLTANEA_ADAPTER = HERE / 'shared-engine-adapter.js'
LAYOUT = {'panels': 4, 'duration': 8.0, 'sweep': 1.4, 'elevation': 0.35}


def node_available() -> bool:
    return shutil.which('node') is not None


def run_node(source: str) -> dict:
    result = subprocess.run(
        ['node', '--input-type=module', '-e', source],
        capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise AssertionError(f'node exited {result.returncode}:\n{result.stderr}')
    return json.loads(result.stdout)


class AcceptedPinTest(unittest.TestCase):
    """The pin is the consumer's own statement of what it accepts."""

    def setUp(self) -> None:
        self.pin = load_pin()

    def test_pin_covers_the_entrypoint_and_a_non_trivial_graph(self) -> None:
        self.assertIn(ENTRYPOINT, self.pin['runtime_graph'])
        self.assertGreaterEqual(len(self.pin['runtime_graph']), 4,
                                'a two-file pin does not cover the executable graph')

    def test_pin_names_an_accepted_release(self) -> None:
        self.assertRegex(self.pin['release']['commit'], r'^[0-9a-f]{40}$')

    def test_pin_digests_are_plausible_sha256(self) -> None:
        for relative, digest in self.pin['runtime_graph'].items():
            self.assertRegex(digest, r'^[0-9a-f]{64}$', relative)


class ResolutionTest(unittest.TestCase):

    def setUp(self) -> None:
        self.engine = resolve_shared_engine()

    def test_resolves_at_the_documented_sibling_location(self) -> None:
        self.assertEqual(self.engine.owner_directory, 'time-moment-brief')
        self.assertIn(self.engine.root, list(candidate_roots(HERE)))

    def test_every_pinned_digest_matches_the_bytes_on_disk(self) -> None:
        for relative, expected in self.pin_graph().items():
            target = self.engine.module_root / Path(relative).relative_to('shared-engine')
            self.assertTrue(target.is_file(), f'{relative} is absent')
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             expected, relative)

    def pin_graph(self) -> dict:
        return load_pin()['runtime_graph']

    def test_release_is_accepted_not_stale(self) -> None:
        pinned = self.pin_graph_release()
        self.assertTrue(
            _contains(self.engine.root, pinned),
            f'{self.engine.root} does not contain the accepted release {pinned[:12]}')

    @staticmethod
    def pin_graph_release() -> str:
        return load_pin()['release']['commit']

    def test_owner_manifest_agrees_with_this_consumer(self) -> None:
        graph = self.engine.provenance['runtime_graph']
        self.assertEqual(graph, self.pin_graph(),
                         'owner manifest and consumer pin describe different builds')

    def test_verify_receipt_covers_every_pinned_file(self) -> None:
        receipt = self.engine.verify()
        self.assertEqual(receipt['files_verified'], len(self.pin_graph()))
        self.assertEqual(receipt['entrypoint'], ENTRYPOINT)

    def test_no_private_media_is_published(self) -> None:
        for relative in self.pin_graph():
            self.assertFalse(relative.startswith('media/'),
                             'private media must stay in the ignored hydration root')

    def test_receipt_handle_carries_no_personal_path(self) -> None:
        """describe() is what a tracked receipt records; it must stay relative."""
        import json
        rendered = json.dumps(self.engine.describe())
        self.assertNotIn('/Users/', rendered)
        self.assertNotIn(str(self.engine.root), rendered)
        self.assertIn('time-moment-brief/shared-engine', rendered)


def _contains(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, 'HEAD'],
        capture_output=True, text=True, timeout=15, check=False)
    return result.returncode == 0


class RefusalTest(unittest.TestCase):
    """Each case is a defect the review probe found and the old resolver accepted."""

    def setUp(self) -> None:
        self.engine = resolve_shared_engine()
        self.staging = Path(self.enterContext(__import__('tempfile').TemporaryDirectory()))
        self.owner = self.staging / 'time-moment-brief'

    def clone_owner(self) -> Path:
        """A real git checkout of the owner, so release checks are meaningful.

        A plain directory copy would have no history, and the resolver would
        refuse it for the wrong reason -- which would make every refusal test
        below pass for a reason that has nothing to do with what it tests.
        """
        subprocess.run(
            ['git', 'clone', '-q', '--no-hardlinks', '--shared', '--branch',
             'agent7-stable-playback-base', str(self.engine.root), str(self.owner)],
            capture_output=True, text=True, check=True, timeout=120)
        return self.owner / 'shared-engine'

    def test_absent_engine_raises_with_the_searched_locations(self) -> None:
        empty = self.staging / 'empty'
        (empty / 'src' / 'simvltanea').mkdir(parents=True)
        (empty / 'pyproject.toml').write_text('[project]\nname = "probe"\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(empty / 'src' / 'simvltanea')
        message = str(caught.exception)
        self.assertIn('shared engine not found', message)
        self.assertIn('no local copy', message)
        self.assertIn(str(empty / 'time-moment-brief'), message,
                      'the refusal must name where it looked')

    def test_ambiguous_owners_are_refused(self) -> None:
        """Two copies would mean two implementations."""
        # The documented layout offers the owner beside the repository and beside its
        # parent. Two owners in those two slots is the ambiguous case.
        project = self.staging / 'proj'
        (project / 'src' / 'simvltanea').mkdir(parents=True)
        (project / 'pyproject.toml').write_text('[project]\nname = "probe"\n')
        far = self.staging / 'time-moment-brief'
        for destination in (project / 'time-moment-brief', far):
            clone = subprocess.run(
                ['git', 'clone', '-q', '--no-hardlinks',
                 '--branch', load_pin()['release']['branch'],
                 str(self.engine.root), str(destination)],
                capture_output=True, text=True, check=False, timeout=120)
            assert clone.returncode == 0, clone.stderr
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(project / 'src' / 'simvltanea')
        self.assertIn('ambiguously', str(caught.exception))

    def test_altered_entrypoint_is_refused(self) -> None:
        module = self.clone_owner()
        target = module / 'index.js'
        target.write_text(target.read_text() + '\nexport const reimplemented = () => {};\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        message = str(caught.exception)
        self.assertIn('does not match the accepted build', message)
        self.assertIn('index.js', message)

    def test_altered_implementation_module_is_refused(self) -> None:
        module = self.clone_owner()
        target = module / 'src' / 'spatial-score.js'
        target.write_text(target.read_text() + '\n// local edit\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('spatial-score.js', str(caught.exception))

    def test_empty_graph_manifest_is_refused(self) -> None:
        module = self.clone_owner()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        data = json.loads(manifest.read_text())
        data['runtime_graph'] = {}
        manifest.write_text(json.dumps(data))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('no runtime graph', str(caught.exception))

    def test_manifest_omitting_the_entrypoint_is_refused(self) -> None:
        module = self.clone_owner()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        data = json.loads(manifest.read_text())
        data['runtime_graph'].pop(ENTRYPOINT, None)
        manifest.write_text(json.dumps(data))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('does not cover the full executable graph',
                      str(caught.exception))
        self.assertIn(ENTRYPOINT, str(caught.exception))

    def test_stale_release_is_refused(self) -> None:
        """A checkout that predates the accepted release must not supply the engine."""
        self.clone_owner()
        module = self.owner / 'shared-engine'
        # Isolate the release check: the bytes and the manifest stay the accepted
        # ones, and only the pinned release moves to a commit this checkout does
        # not contain. Checking out an older commit instead would change the
        # manifest too, and the refusal would fire on incompleteness rather than
        # on staleness -- a different defect that happens to share a code path.
        # A real commit in this repository that HEAD does not contain: an orphan commit,
        # then reset back. A sha that does not exist at all would also fail the
        # ancestry check, but for the wrong reason -- it would prove the commit is
        # unknown rather than that this checkout is behind the accepted release.
        head = subprocess.run(
            ['git', '-C', str(self.owner), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True, timeout=60).stdout.strip()
        subprocess.run(
            ['git', '-C', str(self.owner), 'commit', '-q', '--allow-empty',
             '-m', 'a line that was never merged into the accepted release'],
            capture_output=True, text=True, check=True, timeout=60)
        older = subprocess.run(
            ['git', '-C', str(self.owner), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True, timeout=60).stdout.strip()
        subprocess.run(
            ['git', '-C', str(self.owner), 'reset', '-q', '--hard', head],
            capture_output=True, text=True, check=True, timeout=60)
        pin = load_pin()
        stale_pin = dict(pin, release=dict(pin['release'], commit=older))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests', pin=stale_pin)
        message = str(caught.exception)
        self.assertIn('stale', message)
        self.assertIn(older[:12], message)
        self.assertIn('accepted', message)

    def test_non_git_checkout_is_refused(self) -> None:
        module = self.clone_owner()
        shutil.rmtree(self.owner / '.git')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('git checkout', str(caught.exception))

    def test_environment_cannot_redirect_the_engine(self) -> None:
        """Configuration is not a dependency: an override must not select the module."""
        expected = self.engine.module_root
        forged = dict(SHARED_ENGINE_ROOT='/tmp/not-the-shared-engine',
                      SHARED_ENGINE='/tmp/not-the-shared-engine',
                      SHARED_ENGINE_STAGE_SOURCE='/tmp/not-the-shared-engine')
        import unittest.mock
        with unittest.mock.patch.dict('os.environ', forged):
            self.assertEqual(resolve_shared_engine().module_root, expected)

    def test_malformed_manifest_is_refused_not_treated_as_empty(self) -> None:
        module = self.clone_owner()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        manifest.write_text('{ this is not json')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('not readable JSON', str(caught.exception))

    def test_pin_path_escaping_the_module_is_refused(self) -> None:
        pin = load_pin()
        pin['runtime_graph'] = dict(pin['runtime_graph'],
                                    **{'shared-engine/../../etc/passwd': '0' * 64})
        module = self.clone_owner()
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests', pin=pin)
        self.assertIn('escapes', str(caught.exception))


@unittest.skipUnless(node_available(), 'node is required for adapter identity proof')
class BothConsumersBindOneImplementationTest(unittest.TestCase):
    """The cross-repository reuse proof: one module object, two consumers."""

    def setUp(self) -> None:
        self.engine = resolve_shared_engine()

    def test_both_adapters_bind_the_same_module_object(self) -> None:
        self.assertTrue((self.engine.root / TMB_ADAPTER).is_file(),
                        f'{TMB_ADAPTER} is not in the checkout that owns the engine')
        report = run_node(f"""
          import tmb from '{self.engine.root}/{TMB_ADAPTER}';
          import sim from '{SIMVLTANEA_ADAPTER}';
          import * as shared from '{self.engine.entrypoint}';
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

    def test_panel_orientation_comes_from_the_shared_evaluator(self) -> None:
        report = run_node(f"""
          import sim from '{SIMVLTANEA_ADAPTER}';
          import * as shared from '{self.engine.entrypoint}';
          const driver = sim.createPanelDriver(shared, {json.dumps(LAYOUT)});
          const panels = driver.evaluate(2.0);
          const block = driver.score.blocks[1];
          const direct = shared.evaluateSpatialScore(
            {{ blocks: [block] }}, 2.0 - block.start);
          console.log(JSON.stringify({{ panels, direct }}));
        """)
        self.assertEqual(len(report['panels']), LAYOUT['panels'])
        self.assertAlmostEqual(report['panels'][1]['azimuth'],
                               report['direct']['azimuth'], places=12)
        self.assertAlmostEqual(report['panels'][1]['elevation'],
                               report['direct']['elevation'], places=12)

    def test_simvltanea_adapter_fails_clearly_without_the_module(self) -> None:
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