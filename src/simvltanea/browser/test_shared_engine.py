"""Prove this composition executes the accepted shared engine, or refuses.

Every test here is a refusal test or an identity test. A copied directory, an
environment variable, or a manifest that quietly omits the executable graph would
pass a weaker suite; those are exactly the cases the review probe found and this
file covers.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import unittest
import tempfile
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
SIMVLTANEA_ADAPTER = HERE / 'shared_engine_adapter.js'
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


class HermeticEngineFixture:
    """Synthetic graph and real git history; no ambient checkout or runtime claim."""

    def setUp(self) -> None:
        self.fixture_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        owner = self.fixture_root / 'time-moment-brief'
        module = owner / 'shared-engine'
        self.pin = load_pin()
        graph = {}
        for relative in self.pin['runtime_graph']:
            target = owner / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            content = f'// synthetic resolver fixture: {relative}\n'.encode()
            target.write_bytes(content)
            graph[relative] = hashlib.sha256(content).hexdigest()
        self.pin['runtime_graph'] = graph
        self.pin['entrypoint_sha256'] = graph[ENTRYPOINT]
        (module / 'PROVENANCE.json').write_text(json.dumps(dict(
            entrypoint=ENTRYPOINT, runtime_graph=graph)))
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(owner)], check=True)
        subprocess.run(['git', '-C', str(owner), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(owner), '-c', 'user.name=fixture',
                        '-c', 'user.email=f@x', 'commit', '-q', '-m', 'fixture'], check=True)
        commit = subprocess.check_output(['git', '-C', str(owner), 'rev-parse', 'HEAD'], text=True).strip()
        self.pin['release'] = dict(self.pin['release'], commit=commit, branch='main')
        self.start = self.fixture_root / 'consumer' / 'src'
        self.start.mkdir(parents=True)
        (self.start.parent / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
        self.engine = resolve_shared_engine(self.start, pin=self.pin)


class ResolutionTest(HermeticEngineFixture, unittest.TestCase):

    def test_resolves_at_the_documented_sibling_location(self) -> None:
        self.assertEqual(self.engine.owner_directory, 'time-moment-brief')
        self.assertIn(self.engine.root, list(candidate_roots(self.start)))

    def test_every_pinned_digest_matches_the_bytes_on_disk(self) -> None:
        for relative, expected in self.pin_graph().items():
            target = self.engine.module_root / Path(relative).relative_to('shared-engine')
            self.assertTrue(target.is_file(), f'{relative} is absent')
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             expected, relative)

    def pin_graph(self) -> dict:
        return self.pin['runtime_graph']

    def test_release_is_accepted_not_stale(self) -> None:
        """The hermetic owner checkout is accepted, or provably unprovable.

        A shallow clone of the accepted branch is a legitimate checkout: its bytes
        are verified, but ancestry cannot be walked. The test asserts the reported
        status is honest about which of those it is, rather than hardcoding
        "accepted" -- which is what made it fail in a fresh-path clone where the
        owner is shallow.
        """
        pinned = self.pin_graph_release()
        shallow = _is_shallow(self.engine.root)
        if shallow:
            self.assertIn('shallow', self.engine.release_status)
        else:
            self.assertEqual(self.engine.release_status, 'accepted')
            self.assertTrue(_contains(self.engine.root, pinned),
                            f'{self.engine.root} does not contain {pinned[:12]}')

    def pin_graph_release(self) -> str:
        return self.pin['release']['commit']

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


def _is_shallow(root: Path) -> bool:
    result = subprocess.run(
        ['git', '-C', str(root), 'rev-parse', '--is-shallow-repository'],
        capture_output=True, text=True, timeout=15, check=False)
    return result.returncode == 0 and result.stdout.strip() == 'true'


class RefusalTest(HermeticEngineFixture, unittest.TestCase):
    """Each case is a defect the review probe found and the old resolver accepted."""

    def setUp(self) -> None:
        super().setUp()
        self.staging = Path(self.enterContext(__import__('tempfile').TemporaryDirectory()))
        self.owner = self.staging / 'time-moment-brief'

    def clone_owner(self) -> Path:
        """A self-contained owner fixture with full, known history.

        Cloning the ambient owner checkout made these tests depend on that
        checkout's depth: a shallow ambient clone produced a shallow fixture whose
        ancestry could not be walked, so a genuine staleness case read as
        unprovable. A tiny repository built here has exactly the history each case
        needs, and the module bytes are copied from the synthetic source so the
        digest checks still exercise actual file content.
        """
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.owner)],
                       capture_output=True, text=True, check=True, timeout=60)
        shutil.copytree(self.engine.module_root, self.owner / 'shared-engine')
        git = ['git', '-C', str(self.owner)]
        env = dict(os.environ, GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='f@x',
                   GIT_COMMITTER_NAME='fixture', GIT_COMMITTER_EMAIL='f@x')
        def run(*args, check=True):
            return subprocess.run([*git, *args], capture_output=True, text=True,
                                  check=check, timeout=60, env=env)
        run('add', '-A')
        run('-c', 'user.name=fixture', '-c', 'user.email=f@x',
            'commit', '-q', '-m', 'accepted release')
        self.fixture_commit = subprocess.run(
            [*git, 'rev-parse', 'HEAD'], capture_output=True, text=True,
            check=True, timeout=60).stdout.strip()
        return self.owner / 'shared-engine'

    def fixture_pin(self) -> dict:
        """The synthetic pin, pointed at this fixture's own accepted commit.

        The digests describe synthetic fixture bytes, so the checks exercise
        hashing and manifest agreement without claiming owner integration. Only
        the release moves, which is what lets each case below isolate the defect it
        names instead of tripping the release check first.
        """
        pin = self.pin
        return dict(pin, release=dict(pin['release'], commit=self.fixture_commit))

    def orphan_commit(self) -> str:
        """A real commit object that HEAD does not contain.

        Made on a side branch and then left behind by returning to main, so the
        object exists in the repository while the ancestry walk proves it is not
        part of this checkout's history. A sha that was never in the repository
        would fail the same check for an unrelated reason.
        """
        git = ['git', '-C', str(self.owner)]
        env = dict(os.environ, GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='f@x',
                   GIT_COMMITTER_NAME='fixture', GIT_COMMITTER_EMAIL='f@x')
        subprocess.run([*git, 'checkout', '-q', '-b', 'side'], capture_output=True,
                       text=True, check=True, timeout=60, env=env)
        subprocess.run([*git, 'commit', '-q', '--allow-empty',
                        '-m', 'a line never merged into the accepted release'],
                       capture_output=True, text=True, check=True, timeout=60, env=env)
        divergent = subprocess.run([*git, 'rev-parse', 'HEAD'], capture_output=True,
                                   text=True, check=True, timeout=60).stdout.strip()
        subprocess.run([*git, 'checkout', '-q', 'main'], capture_output=True,
                       text=True, check=True, timeout=60, env=env)
        return divergent

    def probe(self, name: str) -> Path:
        """A minimal consumer that resolves to exactly one owner.

        ``repository_root`` walks up to the project marker, so the probe's
        repository root is the directory holding ``pyproject.toml`` -- not the
        ``src/simvltanea`` path. Getting that wrong silently moves every candidate
        root, and a case about ambiguity then resolves a single owner and passes
        for the wrong reason. The assertion below pins the relationship instead of
        relying on it.
        """
        probe = self.staging / name
        (probe / 'src' / 'simvltanea').mkdir(parents=True)
        (probe / 'pyproject.toml').write_text('[project]\nname = "probe"\n')
        resolved = {candidate.resolve() for candidate
                      in candidate_roots(probe / 'src' / 'simvltanea')}
        self.assertIn(self.owner.resolve(), resolved,
                      'the probe does not resolve to the fixture owner')
        return probe / 'src' / 'simvltanea'

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
        """Two copies would mean two implementations.

        The documented layout offers the owner beside the repository and beside its
        parent. Two owners in those two slots is the ambiguous case.
        """
        # Two owners in the two documented slots: beside the probe's repository root, and
        # beside the staging root one level up. Both carry the same fixture commit,
        # so both verify and the refusal is genuinely about the ambiguity rather
        # than about one copy being stale.
        self.clone_owner()
        pin = self.fixture_pin()
        probe = self.probe('ambiguous')
        shutil.copytree(self.owner, probe.parents[1] / 'time-moment-brief')
        resolved = {candidate.resolve() for candidate
                    in candidate_roots(probe)}
        self.assertEqual(len({c for c in resolved if (c / 'shared-engine' / 'PROVENANCE.json').is_file()}),
                         2, 'the fixture did not produce two discoverable owners')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(probe, pin=pin)
        self.assertIn('ambiguously', str(caught.exception))
        self.assertIn('Two owners', str(caught.exception))

    def test_altered_entrypoint_is_refused(self) -> None:
        module = self.clone_owner()
        pin = self.fixture_pin()
        target = module / 'index.js'
        target.write_text(target.read_text() + '\nexport const reimplemented = () => {};\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('altered-entry'), pin=pin)
        message = str(caught.exception)
        self.assertIn('does not match the accepted build', message)
        self.assertIn('index.js', message)

    def test_altered_implementation_module_is_refused(self) -> None:
        module = self.clone_owner()
        pin = self.fixture_pin()
        target = module / 'src' / 'spatial-score.js'
        target.write_text(target.read_text() + '\n// local edit\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('altered-module'), pin=pin)
        self.assertIn('spatial-score.js', str(caught.exception))

    def test_empty_graph_manifest_is_refused(self) -> None:
        self.clone_owner()
        pin = self.fixture_pin()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        data = json.loads(manifest.read_text())
        data['runtime_graph'] = {}
        manifest.write_text(json.dumps(data))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('empty-graph'), pin=pin)
        self.assertIn('no runtime graph', str(caught.exception))

    def test_manifest_omitting_the_entrypoint_is_refused(self) -> None:
        self.clone_owner()
        pin = self.fixture_pin()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        data = json.loads(manifest.read_text())
        data['runtime_graph'].pop(ENTRYPOINT, None)
        manifest.write_text(json.dumps(data))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('omitted-entrypoint'), pin=pin)
        self.assertIn('does not cover the full executable graph',
                      str(caught.exception))
        self.assertIn(ENTRYPOINT, str(caught.exception))

    def test_shallow_clone_of_the_accepted_branch_is_not_mistaken_for_stale(self) -> None:
        """Ancestry is unknowable in a shallow clone, which is not the same as false.

        Refusing here would refuse a correct checkout of the accepted branch over a
        missing-history artefact, and would push an operator toward re-pinning
        whatever happened to be present -- the exact habit the pin exists to stop.
        """
        probe = self.staging / 'proj-shallow'
        (probe / 'src' / 'simvltanea').mkdir(parents=True)
        (probe / 'pyproject.toml').write_text('[project]\nname = "probe"\n')
        # Cloned directly into its final slot. Cloning into the staging root first
        # would leave a second owner one level up, and the resolver would refuse it
        # as ambiguous -- correctly, but for a reason this case is not about.
        subprocess.run(['git', '-C', str(self.engine.root), '-c', 'user.name=fixture',
                        '-c', 'user.email=f@x', 'commit', '-q', '--allow-empty',
                        '-m', 'successor'], check=True)
        shallow = subprocess.run(
            ['git', 'clone', '-q', '--depth', '1', '--no-hardlinks',
             '--branch', self.pin['release']['branch'],
             # file:// is required: git silently ignores --depth for a plain local
             # path, which would hand back a full clone and prove nothing.
             f'file://{self.engine.root}', str(probe / 'time-moment-brief')],
            capture_output=True, text=True, check=False, timeout=120)
        assert shallow.returncode == 0, shallow.stderr
        self.assertTrue(_is_shallow(probe / 'time-moment-brief'),
                        'the clone is not shallow, so this case would pass for the wrong reason')
        engine = resolve_shared_engine(probe / 'src' / 'simvltanea', pin=self.pin)
        self.assertIn('shallow', engine.release_status)
        self.assertEqual(engine.verify()['files_verified'],
                         len(self.pin['runtime_graph']))

    def test_full_history_of_the_accepted_release_reports_accepted(self) -> None:
        """The accepted-reporting case is proved on a full-history fixture.

        Cloning the ambient owner cannot supply one: git propagates the source's
        shallowness, so the fixture would be shallow wherever the machine happens
        to have a shallow checkout. The local fixture repository has exactly the
        history this case needs.
        """
        self.clone_owner()
        pin = self.fixture_pin()
        self.assertFalse(_is_shallow(self.owner))
        probe = self.probe('full-history')
        engine = resolve_shared_engine(probe, pin=pin)
        self.assertEqual(engine.release_status, 'accepted')
        self.assertEqual(engine.verify()['release_status'], 'accepted')
        self.assertEqual(engine.verify()['files_verified'],
                         len(pin['runtime_graph']))

    def test_stale_release_is_refused(self) -> None:
        """A checkout that predates the accepted release must not supply the engine.

        The bytes and the manifest stay the accepted ones; only the pinned release
        moves to a real commit this checkout does not contain. Checking out an
        older commit instead would change the manifest too, and the refusal would
        fire on incompleteness rather than staleness -- a different defect that
        happens to share a code path.
        """
        self.clone_owner()
        pin = self.fixture_pin()
        divergent = self.orphan_commit()
        stale_pin = dict(pin, release=dict(pin['release'], commit=divergent))
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('stale-release'), pin=stale_pin)
        message = str(caught.exception)
        self.assertIn('stale', message)
        self.assertIn(divergent[:12], message)
        self.assertIn('accepted', message)

    def test_non_git_checkout_is_refused(self) -> None:
        self.clone_owner()
        pin = self.fixture_pin()
        shutil.rmtree(self.owner / '.git')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(self.probe('non-git'), pin=pin)
        self.assertIn('git checkout', str(caught.exception))

    def test_environment_cannot_redirect_the_engine(self) -> None:
        """Configuration is not a dependency: an override must not select the module."""
        expected = self.engine.module_root
        forged = dict(SHARED_ENGINE_ROOT='/tmp/not-the-shared-engine',
                      SHARED_ENGINE='/tmp/not-the-shared-engine',
                      SHARED_ENGINE_STAGE_SOURCE='/tmp/not-the-shared-engine')
        import unittest.mock
        with unittest.mock.patch.dict('os.environ', forged):
            self.assertEqual(resolve_shared_engine(self.start, pin=self.pin).module_root, expected)

    def test_malformed_manifest_is_refused_not_treated_as_empty(self) -> None:
        module = self.clone_owner()
        manifest = self.owner / 'shared-engine' / 'PROVENANCE.json'
        manifest.write_text('{ this is not json')
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests')
        self.assertIn('not readable JSON', str(caught.exception))

    def test_pin_path_escaping_the_module_is_refused(self) -> None:
        pin = dict(self.pin)
        pin['runtime_graph'] = dict(pin['runtime_graph'],
                                    **{'shared-engine/../../etc/passwd': '0' * 64})
        module = self.clone_owner()
        pin['release'] = dict(pin['release'], commit=self.fixture_commit)
        with self.assertRaises(SharedEngineUnavailable) as caught:
            resolve_shared_engine(module / 'tests', pin=pin)
        self.assertIn('escapes', str(caught.exception))


class RefreshedVerificationTest(HermeticEngineFixture, unittest.TestCase):
    def test_default_resolution_uses_the_selected_workspace(self):
        from unittest.mock import patch
        from simvltanea import paths
        with patch.object(paths, 'REPO_ROOT', self.start.parent):
            self.assertEqual(resolve_shared_engine(pin=self.pin).root, self.engine.root)

    def test_verify_reloads_provenance(self):
        manifest = self.engine.module_root / 'PROVENANCE.json'
        manifest.write_text('{}')
        with self.assertRaises(SharedEngineUnavailable):
            self.engine.verify()

    def test_verify_refreshes_git_release_and_rejects_lost_ancestry(self):
        git = ['git', '-C', str(self.engine.root)]
        subprocess.run([*git, '-c', 'user.name=f', '-c', 'user.email=f@x',
                        'commit', '-q', '--allow-empty', '-m', 'successor'], check=True)
        receipt = self.engine.verify()
        self.assertNotEqual(receipt['release'], self.engine.git_commit)
        subprocess.run([*git, 'checkout', '-q', '--orphan', 'unrelated'], check=True)
        subprocess.run([*git, '-c', 'user.name=f', '-c', 'user.email=f@x',
                        'commit', '-q', '-m', 'unrelated'], check=True)
        with self.assertRaisesRegex(SharedEngineUnavailable, 'stale'):
            self.engine.verify()

    def test_malformed_digest_values_are_refused(self):
        manifest = self.engine.module_root / 'PROVENANCE.json'
        for digest in (None, 42, [], 'bad'):
            with self.subTest(digest=digest):
                graph = dict(self.pin['runtime_graph'], **{ENTRYPOINT:digest})
                manifest.write_text(json.dumps(dict(entrypoint=ENTRYPOINT, runtime_graph=graph)))
                with self.assertRaisesRegex(SharedEngineUnavailable, 'SHA-256'):
                    resolve_shared_engine(self.start, pin=self.pin)

    def test_non_utf8_provenance_is_unavailable(self):
        (self.engine.module_root / 'PROVENANCE.json').write_bytes(b'\xff')
        with self.assertRaisesRegex(SharedEngineUnavailable, 'not readable JSON'):
            resolve_shared_engine(self.start, pin=self.pin)


@unittest.skipUnless(node_available(), 'node is required for adapter identity proof')
class BothConsumersBindOneImplementationTest(unittest.TestCase):
    """The cross-repository reuse proof: one module object, two consumers."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.engine = resolve_shared_engine()
        except SharedEngineUnavailable as error:
            if not str(error).startswith('shared engine not found.'):
                raise
            raise unittest.SkipTest(f'owner integration not available: {error}') from error

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