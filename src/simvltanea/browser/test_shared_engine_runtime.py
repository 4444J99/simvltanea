"""The shared engine actually runs in this composition's rendered preview.

The resolver tests prove the right bytes resolve. They do not prove the page uses
them. These tests build a real preview over real HTTP in an installed Chromium
and assert the shared evaluator moves the panel framing, which is the difference
between a wired consumer and a resolvable one.
"""
from __future__ import annotations

import functools
import http.server
import json
import threading
import unittest
from pathlib import Path

from simvltanea.browser.browser_runtime import build_preview
from simvltanea.browser.shared_engine import resolve_shared_engine, SharedEngineUnavailable
from simvltanea.generators.make_runtime_fixture import ROOT, prepare


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # pragma: no cover - noise control
        pass


def _browser_executable() -> str:
    """An installed Chromium only. No download, no skip substitution."""
    import os
    import shutil

    from simvltanea.browser.test_browser_runtime import browser_executable

    return browser_executable()


@unittest.skipUnless(shutil_which := __import__('shutil').which, 'shutil is unavailable')
class SharedEngineRuntimeTest(unittest.TestCase):
    """Rendered-frame evidence: the module runs in the composition, not beside it."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            resolve_shared_engine()
        except SharedEngineUnavailable as error:
            if not str(error).startswith('shared engine not found.'):
                raise
            raise unittest.SkipTest(f'owner integration not available: {error}') from error
        prepare()
        cls.preview = ROOT / 'preview-shared-engine'
        cls.plan = build_preview(ROOT / 'state-3.json', cls.preview)

        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0),
            functools.partial(_QuietHandler, directory=str(ROOT)))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(
            executable_path=_browser_executable(), headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        self.page = self.browser.new_page()
        self.errors: list[str] = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(f'http://127.0.0.1:{self.port}/preview-shared-engine/index.html')
        self.page.wait_for_function(
            'window.compositionRuntime && window.compositionRuntime.ready', timeout=20000)

    def tearDown(self) -> None:
        self.page.close()

    # ------------------------------------------------------------- staging

    def test_legacy_engine_inventory_rejects_nested_extras(self):
        import tempfile
        from pathlib import Path
        from simvltanea.browser.browser_runtime import PREVIEW_MARKER
        from simvltanea.authoring.composition import StateError
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'legacy'
            build_preview(ROOT/'state-3.json',target)
            (target/PREVIEW_MARKER).unlink()
            build_preview(ROOT/'state-3.json',target)
            (target/PREVIEW_MARKER).unlink()
            extra=target/'shared-engine/src/personal.js'
            extra.write_bytes(b'preserve user-authored bytes')
            before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
            with self.assertRaises(StateError):build_preview(ROOT/'state-3.json',target)
            self.assertEqual(before,{p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()})

    def test_modified_legacy_release_receipt_is_preserved(self):
        import tempfile
        from simvltanea.browser.browser_runtime import PREVIEW_MARKER
        from simvltanea.authoring.composition import StateError
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'legacy'
            build_preview(ROOT/'state-3.json',target)
            (target/PREVIEW_MARKER).unlink()
            path=target/'index.html';original=path.read_text()
            edited=original.replace(resolve_shared_engine().pin['release']['commit'][:12],'0'*12)
            self.assertNotEqual(original,edited)
            path.write_text(edited)
            with self.assertRaises(StateError):build_preview(ROOT/'state-3.json',target)
            self.assertEqual(path.read_text(),edited)

    def test_preview_stages_the_verified_module_rather_than_a_copy_of_the_maths(self):
        """The bytes in the preview are the bytes that were digest-verified."""
        engine = resolve_shared_engine()
        for relative in ('index.js', 'src/spatial-score.js',
                         'src/panoramic-projection.js', 'src/video-texture.js'):
            source = engine.module_root / relative
            staged = self.preview / 'shared-engine' / relative
            self.assertTrue(staged.is_file(), f'{relative} was not staged')
            self.assertEqual(staged.read_bytes(), source.read_bytes(), relative)
        self.assertTrue((self.preview / 'shared-engine-adapter.js').is_file())
        self.assertTrue((self.preview / 'shared-engine.js').is_file())

    def test_preview_html_loads_the_shared_engine_and_the_adapter(self):
        html = (self.preview / 'index.html').read_text()
        self.assertIn('shared-engine-adapter.js', html)
        self.assertIn('type="module" src="shared-engine.js"', html)
        self.assertNotIn('panelDriver = (t) =>', html,
                         'the preview must not inline its own orientation maths')

    # ------------------------------------------------------------- runtime

    def test_shared_engine_publishes_the_accepted_build(self):
        shared = self.page.evaluate(
            '() => window.compositionRuntime.snapshot().sharedEngine')
        self.assertIsNone(shared['error'], shared['error'])
        self.assertEqual(shared['panels'], len(self.plan['tracks']))
        self.assertEqual(shared['build'],
                         'shared-engine@time-moment-brief/' + resolve_shared_engine().pin['release']['commit'])

    def test_shared_evaluator_moves_the_rendered_panel_framing(self):
        """The claim under test: a score drives a rendered view, not a test fixture."""
        self.page.evaluate('() => window.compositionRuntime.start()')
        samples = self.page.evaluate("""async () => {
          const out = [];
          for (let i = 0; i < 4; i++) {
            await new Promise((r) => setTimeout(r, 400));
            const snapshot = window.compositionRuntime.snapshot();
            out.push({
              time: snapshot.compositionTime,
              positions: [...document.querySelectorAll('.loop video, .loop img')]
                .map((node) => node.style.objectPosition),
              azimuths: snapshot.sharedEngine.poses.map((pose) => pose.azimuth),
            });
          }
          return out;
        }""")
        self.assertGreater(len(samples[0]['positions']), 0, 'no panels rendered')
        for sample in samples:
            self.assertGreater(sample['time'], 0, 'playback never advanced')
        # Every panel must move: a score that only animates one panel is a bug,
        # not a composition.
        for index in range(len(samples[0]['positions'])):
            series = [sample['positions'][index] for sample in samples]
            self.assertGreater(len(set(series)), 1,
                               f'panel {index} framing never changed: {series[0]}')
            azimuths = [sample['azimuths'][index] for sample in samples]
            self.assertGreater(len(set(azimuths)), 1,
                               f'panel {index} azimuth never changed')

    def test_rendered_poses_match_the_shared_evaluator_exactly(self):
        """The page reports the module's own numbers, not a local approximation."""
        self.page.evaluate('() => window.compositionRuntime.start()')
        observed = self.page.evaluate("""async () => {
          await new Promise((r) => setTimeout(r, 400));
          const snapshot = window.compositionRuntime.snapshot();
          return { poses: snapshot.sharedEngine.poses, time: snapshot.sharedEngine.renderedTime };
        }""")
        # Recompile the same score in the page and evaluate it at the same time.
        direct = self.page.evaluate("""async (t) => {
          const adapter = window.SimvltaneaSharedEngineAdapter;
          const plan = window.compositionRuntime.plan;
          const driver = adapter.createPanelDriver(window.SharedEngine, {
            panels: plan.tracks.length,
            duration: plan.frames / plan.fps,
            sweep: 0.35,
            elevation: 0.12,
          });
          return driver.evaluate(t);
        }""", observed['time'])
        for index, pose in enumerate(observed['poses']):
            self.assertAlmostEqual(pose['azimuth'], direct[index]['azimuth'], places=12)
            self.assertAlmostEqual(pose['elevation'], direct[index]['elevation'], places=12)

    def test_every_panel_is_in_motion_simultaneously(self):
        """Panels offset in phase; they must not take turns."""
        self.page.evaluate('() => window.compositionRuntime.start()')
        sample = self.page.evaluate("""async () => {
          await new Promise((r) => setTimeout(r, 500));
          const snapshot = window.compositionRuntime.snapshot();
          return { poses: snapshot.sharedEngine.poses, time: snapshot.sharedEngine.renderedTime };
        }""")
        azimuths = [pose['azimuth'] for pose in sample['poses']]
        self.assertEqual(len(set(round(a, 6) for a in azimuths)), len(azimuths),
                         f'panels share an azimuth at t={sample["time"]}: {azimuths}')

    def test_absent_shared_engine_is_reported_not_silently_centred(self):
        """Withhold the module and the runtime must say so."""
        page = self.browser.new_page()
        try:
            blocked: list[str] = []
            page.route('**/shared-engine.js', lambda route: blocked.append(route.request.url)
                       or route.abort())
            page.goto(f'http://127.0.0.1:{self.port}/preview-shared-engine/index.html')
            page.wait_for_function(
                'window.compositionRuntime && window.compositionRuntime.ready', timeout=20000)
            page.evaluate('() => window.compositionRuntime.start()')
            page.wait_for_timeout(600)
            shared = page.evaluate('() => window.compositionRuntime.snapshot().sharedEngine')
            self.assertTrue(blocked, 'the module request was never made')
            self.assertIsNotNone(shared['error'],
                                 'an unavailable module must be reported, not defaulted')
            self.assertEqual(shared['poses'], [], 'poses were reported without a module')
        finally:
            page.close()

    def test_snapshot_describes_the_visible_frame_after_pause(self):
        self.page.evaluate('() => window.compositionRuntime.start()')
        self.page.wait_for_timeout(350)
        self.page.evaluate('() => window.compositionRuntime.pause()')
        before = self.page.evaluate('() => window.compositionRuntime.snapshot().sharedEngine')
        styles = self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>n.style.objectPosition)')
        self.page.wait_for_timeout(120)
        after = self.page.evaluate('() => window.compositionRuntime.snapshot().sharedEngine')
        self.assertEqual(before, after)
        self.assertEqual(styles, self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>n.style.objectPosition)'))

    def test_reordered_orientation_preserves_pose_identity(self):
        self.page.evaluate("""() => {
          const runtime=window.compositionRuntime;
          const landscape=structuredClone(runtime.plan.layout_keyframes[0].layouts.landscape);
          landscape.cells.reverse();
          runtime.plan.layout_keyframes[0].layouts.portrait=landscape;
        }""")
        before = self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>n.style.objectPosition)')
        self.page.set_viewport_size({'width':480,'height':800})
        self.page.wait_for_function('window.compositionRuntime.orientation === "portrait"')
        after = self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>n.style.objectPosition)')
        self.assertEqual(before, after)

    def test_slice_preview_renders_motion_in_source_offsets(self):
        build_preview(ROOT / 'state-slice-3.json', ROOT / 'preview-shared-slice')
        self.page.goto(f'http://127.0.0.1:{self.port}/preview-shared-slice/index.html')
        self.page.wait_for_function('window.compositionRuntime && window.compositionRuntime.ready')
        before = self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>[n.style.left,n.style.top])')
        self.page.evaluate('() => window.compositionRuntime.start()')
        self.page.wait_for_timeout(500)
        after = self.page.locator('.loop video, .loop img').evaluate_all(
            '(nodes) => nodes.map(n=>[n.style.left,n.style.top])')
        self.assertNotEqual(before, after)
        self.page.evaluate('() => window.compositionRuntime.pause()')
        for width, height in ((480,800),(1200,400)):
            with self.subTest(width=width,height=height):
                self.page.set_viewport_size({'width':width,'height':height})
                self.page.wait_for_timeout(150)
                geometry=self.page.evaluate("""() => [...window.compositionRuntime.nodes.values()]
                  .filter(n=>n.span.slice_rect).map(n=>{
                    const box=n.box.getBoundingClientRect(), media=n.media.getBoundingClientRect();
                    return {delta:media.top-box.top, expected:parseFloat(n.media.style.top)*box.height/100,
                            top:media.top, bottom:media.bottom, boxTop:box.top, boxBottom:box.bottom};
                  })""")
                self.assertTrue(geometry)
                for item in geometry:
                    self.assertAlmostEqual(item['delta'],item['expected'],delta=1)
                    self.assertLessEqual(item['top'],item['boxTop']+1)
                    self.assertGreaterEqual(item['bottom'],item['boxBottom']-1)
        self.assertEqual(self.errors, [])

    def test_no_page_errors_during_playback(self):
        self.page.evaluate('() => window.compositionRuntime.start()')
        self.page.wait_for_timeout(800)
        self.assertEqual(self.errors, [], f'page reported errors: {self.errors}')


if __name__ == '__main__':
    unittest.main()
