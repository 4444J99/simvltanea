"""Executed browser proof: native playback, keyed nodes, container-only layout.

Requires Python Playwright, an installed Chromium/Chrome, Pillow, FFmpeg and ffprobe.
No browser download, remote endpoint or public deployment is used by the suite.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import os
import functools
import http.server
import json
import shutil
import subprocess
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch


import simvltanea.authoring.composition as c
from simvltanea.browser.browser_runtime import build_preview, compile_plan
from simvltanea.generators.make_runtime_fixture import HERE, ROOT, prepare


def browser_executable() -> str:
    """Resolve a caller-pinned or preinstalled browser without downloading one."""
    configured = os.environ.get('PORTVS_BROWSER_EXECUTABLE')
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise RuntimeError('PORTVS_BROWSER_EXECUTABLE must be an absolute path')
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError('PORTVS_BROWSER_EXECUTABLE does not exist') from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise RuntimeError('PORTVS_BROWSER_EXECUTABLE must be an executable file')
        return str(resolved)
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable'):
        executable = shutil.which(name)
        if executable:
            return executable
    for app_path in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                     '/Applications/Chromium.app/Contents/MacOS/Chromium'):
        if Path(app_path).is_file() and os.access(app_path, os.X_OK):
            return app_path
    # Fallback to Playwright's bundled Chromium (installed via `playwright install --with-deps chromium`)
    # when no system chrome is on PATH (e.g. ubuntu-latest without google-chrome-stable).
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            exe = pw.chromium.executable_path
            if exe and Path(exe).is_file() and os.access(exe, os.X_OK):
                return exe
        finally:
            pw.stop()
    except Exception:
        pass
    raise RuntimeError(
        'Installed Chromium/Chrome is required; set PORTVS_BROWSER_EXECUTABLE '
        'to an absolute executable path (no download or skip substituted)')


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): prepare()

    def test_compiler_replays_every_loop_at_every_frame(self):
        for name in ('3','4','5','6','7','controls','trim'):
            state=c.load_state(ROOT/f'state-{name}.json');plan=compile_plan(state)
            for frame in range(state['frames']):
                resolved={x['id']:x for x in c.resolve_at(state,frame)['loops']}
                for track in plan['tracks']:
                    span=next(x for x in reversed(track['spans']) if x['frame']<=frame)
                    expected=resolved[track['id']]
                    self.assertEqual((span['source'],span['kind'],span['held']),
                                     (expected['source'],expected['kind'],expected['held']))
                    delta=Fraction(0) if span['held'] or span['kind']=='still' else Fraction(frame-span['frame'],state['fps'])*Fraction(span['rate'])
                    self.assertEqual(Fraction(span['source_offset'])+delta,Fraction(expected['source_offset']))

    def test_geometry_never_splits_unrelated_loop_tracks(self):
        state=c.load_state(ROOT/'state-3.json');before=compile_plan(state)
        state['events']=[dict(op='move',frame=24,loop='loop-1',orientation='portrait',rect=['1/10','3/100','4/5','21/50'])]
        after=compile_plan(state)
        self.assertEqual(before['tracks'],after['tracks'])
        self.assertEqual(len(after['layout_keyframes']),2)

    def test_missing_pair_is_rejected_even_for_higher_count(self):
        state=c.load_state(ROOT/'state-7.json');del state['layouts']['portrait']
        with self.assertRaises(c.StateError):compile_plan(state)

    def test_time_driven_source_collision_rejected_before_browser(self):
        state=c.load_state(ROOT/'state-3.json')
        state['loops'][0]['bank']=['source-1','source-2']
        # Every source/seed combination is evaluated; validation may reject at frame zero.
        found=False
        for seed in range(20):
            state['seed']=seed
            try:compile_plan(state)
            except c.StateError:found=True;break
        self.assertTrue(found)

    def test_state_hash_and_media_hashes_preserved(self):
        state=c.load_state(ROOT/'state-7.json');plan=compile_plan(state)
        self.assertEqual(len(plan['tracks']),7)
        self.assertEqual({s['sha256'] for s in plan['sources']},{s['sha256'] for s in state['sources']})
        self.assertEqual(plan,compile_plan(copy.deepcopy(state)))

    def test_portable_preview_state_resolves_actual_copied_bytes(self):
        target=ROOT/'preview-portable';plan=build_preview(ROOT/'state-3.json',target)
        saved=c.load_state(target/'state.json')
        self.assertEqual(hashlib.sha256(c.canonical_json(saved).encode()).hexdigest(),plan['state_sha256'])
        self.assertEqual(len(c.media_paths(saved,target)),3)
        self.assertEqual(c.resolve_at(saved,95)['loops'],c.resolve_at(c.load_state(ROOT/'state-3.json'),95)['loops'])

    def test_verified_legacy_preview_can_be_replaced_but_loose_media_is_preserved(self):
        from simvltanea.browser.browser_runtime import PREVIEW_MARKER
        import tempfile
        target=Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT)))/'preview-legacy'
        build_preview(ROOT/'state-3.json',target)
        (target/PREVIEW_MARKER).unlink()
        build_preview(ROOT/'state-3.json',target)
        self.assertTrue((target/PREVIEW_MARKER).is_file())
        (target/PREVIEW_MARKER).unlink()
        extra=target/'media'/'personal-original.mp4'
        extra.write_bytes(b'preserve original')
        with self.assertRaises(c.StateError):
            build_preview(ROOT/'state-3.json',target)
        self.assertEqual(extra.read_bytes(),b'preserve original')

    def test_preview_media_symlink_escape_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'preview';target.mkdir();(target/'media').symlink_to(Path(temp),target_is_directory=True)
            with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',target)

    def test_legacy_nested_extras_and_modified_executables_are_preserved(self):
        from simvltanea.browser.browser_runtime import PREVIEW_MARKER
        import tempfile
        for relative, content in (('shared-engine/src/personal.js', b'preserve'),
                                  ('runtime.js', b'user-authored runtime'),
                                  ('media/empty-directory', None)):
            with self.subTest(relative=relative):
                target=Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT)))/'legacy'
                build_preview(ROOT/'state-3.json',target)
                (target/PREVIEW_MARKER).unlink()
                extra=target/relative
                extra.parent.mkdir(parents=True,exist_ok=True)
                if content is None:extra.mkdir()
                else:extra.write_bytes(content)
                before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
                with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',target)
                self.assertEqual(before,{p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()})
                self.assertTrue(extra.exists())

    def test_legacy_plan_byte_edits_are_preserved(self):
        from simvltanea.browser.browser_runtime import PREVIEW_MARKER
        import tempfile
        for variant in ('compact','reordered','duplicate-key'):
            with self.subTest(variant=variant):
                target=Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT)))/'legacy'
                build_preview(ROOT/'state-3.json',target)
                (target/PREVIEW_MARKER).unlink()
                path=target/'plan.json';raw=path.read_text();plan=json.loads(raw)
                if variant=='compact':edited=json.dumps(plan)+'\n'
                elif variant=='reordered':edited=json.dumps(dict(reversed(list(plan.items()))),indent=2)+'\n'
                else:edited=raw.replace('"plan_version": 1,','"plan_version": 99,\n  "plan_version": 1,')
                self.assertNotEqual(raw,edited)
                self.assertEqual(plan,json.loads(edited))
                path.write_text(edited)
                with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',target)
                self.assertEqual(path.read_text(),edited)

    def test_late_legacy_plan_edit_is_restored_after_exchange(self):
        from simvltanea.browser import browser_runtime as runtime
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'legacy'
            build_preview(ROOT/'state-3.json',target)
            (target/runtime.PREVIEW_MARKER).unlink()
            raw=(target/'plan.json').read_text()
            rename=runtime._rename_preview;calls=0
            def edit_after_exchange(staging, output, *, exchange):
                nonlocal calls
                calls+=1
                rename(staging,output,exchange=exchange)
                if calls==1:(staging/'plan.json').write_text(raw+' ')
            with patch.object(runtime,'_rename_preview',side_effect=edit_after_exchange):
                with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',target)
            self.assertEqual((target/'plan.json').read_text(),raw+' ')

    def test_late_writes_through_displaced_legacy_handle_are_retained(self):
        from simvltanea.browser import browser_runtime as runtime
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'legacy'
            build_preview(ROOT/'state-3.json',target)
            (target/runtime.PREVIEW_MARKER).unlink()
            descriptor=os.open(target,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try:
                validate=runtime._validate_preview_destination
                def write_after_validation(state, path, **kwargs):
                    identity=validate(state,path,**kwargs)
                    if kwargs.get('tracked_output') == target:
                        file=os.open('personal-original',os.O_WRONLY|os.O_CREAT,0o600,dir_fd=descriptor)
                        with os.fdopen(file,'wb') as stream:stream.write(b'preserve late original')
                    return identity
                with patch.object(runtime,'_validate_preview_destination',side_effect=write_after_validation):
                    build_preview(ROOT/'state-3.json',target)
                archived=list(target.parent.glob('.legacy-retained-*/generation'))
                self.assertEqual(len(archived),1)
                self.assertEqual((archived[0]/'personal-original').read_bytes(),b'preserve late original')
                self.assertFalse((target/'personal-original').exists())
            finally:os.close(descriptor)

    def test_preview_rejects_unverified_browser_container(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            temp=Path(temp);state=c.load_state(ROOT/'state-3.json')
            for source in state['sources']:
                path=ROOT/source['path'];target=temp/path.name
                if source['id']=='source-1':target=target.with_suffix('.avi')
                shutil.copyfile(path,target);source['path']=target.name
            c.save_state(state,temp/'state.json')
            with self.assertRaisesRegex(c.StateError,'MP4'):
                build_preview(temp/'state.json',temp/'preview')

    def test_preview_cannot_replace_source_state(self):
        with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',ROOT)

    def test_browser_discovery_accepts_pinned_absolute_executable(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            executable = Path(temp) / 'chrome'
            executable.write_text('#!/bin/sh\n')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'PORTVS_BROWSER_EXECUTABLE': str(executable)}):
                self.assertEqual(browser_executable(), str(executable.resolve()))

    def test_browser_discovery_rejects_relative_or_missing_override(self):
        for value in ('chrome', str((ROOT / 'missing-chrome').resolve())):
            with self.subTest(value=value), \
                    patch.dict(os.environ, {'PORTVS_BROWSER_EXECUTABLE': value}):
                with self.assertRaises(RuntimeError):
                    browser_executable()

    def test_browser_discovery_supports_github_runner_chrome(self):
        def locate(name):
            return '/usr/bin/google-chrome' if name == 'google-chrome' else None
        with patch.dict(os.environ, {}, clear=True), patch.object(shutil, 'which', side_effect=locate):
            self.assertEqual(browser_executable(), '/usr/bin/google-chrome')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        prepare()
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.pw=sync_playwright().start()
        executable=browser_executable()
        cls.browser=cls.pw.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.transport=os.environ.get('PORTVS_BROWSER_TRANSPORT','http')
        if cls.transport not in ('http','in-memory'):raise ValueError('Unknown browser transport')
        (ROOT/'evidence/browser-transport.txt').write_text(cls.transport+'\n')
        (ROOT/'evidence/browser-version.txt').write_text(cls.browser.version+'\n')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def open_preview(self,name):
        page=self.browser.new_page(viewport={'width':390,'height':844})
        self.addCleanup(page.close)
        self.load_page(page, ROOT/f'preview-{name}')
        page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error',timeout=20000)
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        page.evaluate('window.initialMedia = [...compositionRuntime.nodes.values()].map(n => n.media)')
        page.evaluate('window.initialBoxes = [...compositionRuntime.nodes.values()].map(n => n.box)')
        return page

    def load_page(self,page,root):
        if self.transport == 'http':
            page.goto(f'{self.base}/{root.name}/')
            return
        # about:blank runs real Chromium DOM and native video decoders without
        # HTTP navigation. Only IO is injected; clocks/playback are not mocked.
        plan=json.loads((root/'plan.json').read_text())
        payload={src['id']:base64.b64encode((root/src['path']).read_bytes()).decode() for src in plan['sources']}
        page.expose_function('fixtureDigest',lambda data:hashlib.sha256(bytes(data)).hexdigest())
        page.set_content((root/'index.html').read_text().replace('<script src="runtime.js" defer></script>',''))
        page.evaluate("""({plan,payload}) => {
          window.compositionIO = {
            async plan() { return plan; },
            async bytes(source) { return Uint8Array.from(atob(payload[source.id]), c => c.charCodeAt(0)).buffer; },
            async digest(bytes) { return fixtureDigest(Array.from(new Uint8Array(bytes))); }
          };
        }""", dict(plan=plan,payload=payload))
        page.add_script_tag(content=(root/'runtime.js').read_text())

    def snap(self,page,name):
        snapshot=page.evaluate('compositionRuntime.snapshot()')
        self.assertIsNone(snapshot['error'])
        page.screenshot(path=str(ROOT/f'evidence/{name}.png'))
        return snapshot

    def settled_snapshot(self, page, frame, name):
        """Capture a frame only after every asynchronous source transition settles."""
        page.wait_for_function(
            """target => {
              const value = window.compositionRuntime;
              return value && (value.error || (value.frame >= target &&
                [...value.nodes.values()].every(node => !node.busy)));
            }""", arg=frame)
        return self.snap(page, name)

    def check_model(self,snapshot,state,tolerance=.18):
        expected={x['id']:x for x in c.resolve_at(state,snapshot['frame'])['loops']}
        for loop in snapshot['loops']:
            target=expected[loop['id']]
            self.assertEqual(loop['source'],target['source'])
            if loop['kind']=='video':
                self.assertFalse(loop['busy'], 'media transition did not settle at checkpoint')
                self.assertGreater(loop['callbacks'],0)
                self.assertAlmostEqual(loop['currentTime'],float(Fraction(target['source_offset'])),delta=tolerance)

    def continuity(self,count):
        page=self.open_preview(count);state=c.load_state(ROOT/f'state-{count}.json')
        before=page.evaluate('compositionRuntime.events.length')
        page.evaluate('compositionRuntime.start()')
        snapshots=[]
        shapes=[(390,844),(1280,720),(900,1300),(844,390),(390,844)]
        for index,(width,height) in enumerate(shapes):
            page.set_viewport_size({'width':width,'height':height})
            page.wait_for_timeout(450)
            snapshot=self.snap(page,f'{count}-viewport-{index}')
            self.assertEqual(snapshot['orientation'],'landscape' if width>=height else 'portrait')
            self.assertEqual(len(snapshot['loops']),count)
            self.assertEqual(len({x['id'] for x in snapshot['loops']}),count)
            self.assertEqual(len({x['source'] for x in snapshot['loops']}),count)
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i) => n.media === initialMedia[i] && n.box === initialBoxes[i])'))
            self.assertEqual(page.locator('#stage > .loop').count(),count)
            self.assertEqual(page.locator('#stage video').count(),count)
            self.check_model(snapshot,state)
            if snapshots:
                previous=snapshots[-1];elapsed=(snapshot['wall']-previous['wall'])/1000
                for old,new in zip(previous['loops'],snapshot['loops']):
                    self.assertGreater(new['currentTime'],old['currentTime'])
                    self.assertGreater(new['callbacks'],old['callbacks'])
                    self.assertGreater(new['decoded']['mediaTime'],old['decoded']['mediaTime'])
                    self.assertAlmostEqual(new['currentTime']-old['currentTime'],elapsed*new['rate'],delta=.12)
            snapshots.append(snapshot)
        events=page.evaluate('compositionRuntime.events')
        self.assertFalse([x for x in events[before:] if x['type'] in ('seek-command','source','loadstart')])
        self.assertEqual(len({x['id'] for x in events if x['type']=='source'}),count)
        (ROOT/f'evidence/browser-{count}.json').write_text(json.dumps(dict(snapshots=snapshots,events=events),indent=2)+'\n')

    def test_resize_while_media_is_loading(self):
        page=self.browser.new_page(viewport={'width':390,'height':844});self.addCleanup(page.close)
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_content('<main id="stage" style="width:390px;height:844px"></main>')
        plan=json.loads((ROOT/'preview-3/plan.json').read_text())
        page.evaluate("""plan => {
            window.compositionIO={async plan(){return plan;},
                async bytes(){return new Promise(()=>{});},async digest(){throw Error('not reached');}};
        }""",plan)
        page.add_script_tag(content=(HERE/'browser.runtime.js').read_text())
        page.wait_for_timeout(50)
        page.evaluate('stage.style.width="844px";stage.style.height="390px"')
        page.wait_for_timeout(100)
        self.assertEqual(errors,[])
        self.assertEqual(page.locator('#stage > .loop').count(),0)
        self.assertFalse(page.evaluate('compositionRuntime.ready'))

    def test_3_loop_native_continuity(self):self.continuity(3)
    def test_4_loop_native_continuity(self):self.continuity(4)
    def test_5_loop_native_continuity(self):self.continuity(5)
    def test_6_loop_native_continuity(self):self.continuity(6)
    def test_7_loop_native_continuity(self):self.continuity(7)

    def test_container_resize_without_viewport_change(self):
        page=self.open_preview(3)
        page.set_viewport_size({'width':1600,'height':1000})
        before=page.evaluate('compositionRuntime.events.length')
        page.evaluate('compositionRuntime.start()');snapshots=[]
        for index,(width,height) in enumerate(((390,844),(844,390),(450,900))):
            page.evaluate('([w,h]) => {stage.style.width=w+"px";stage.style.height=h+"px";}',[width,height])
            page.wait_for_timeout(450)
            snapshot=self.snap(page,f'container-{index}')
            self.assertEqual(snapshot['orientation'],'landscape' if width>=height else 'portrait')
            self.assertEqual(page.viewport_size,{'width':1600,'height':1000})
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===initialMedia[i])'))
            snapshots.append(snapshot)
        events=page.evaluate('compositionRuntime.events')
        self.assertFalse([x for x in events[before:] if x['type'] in ('source','seek-command','loadstart')])
        for old,new in zip(snapshots,snapshots[1:]):
            self.assertTrue(all(b['currentTime']>a['currentTime'] and b['callbacks']>a['callbacks'] for a,b in zip(old['loops'],new['loops'])))
        (ROOT/'evidence/browser-container.json').write_text(json.dumps(dict(snapshots=snapshots,events=events),indent=2)+'\n')

    def test_native_controls_hold_release_swap_reroll_move(self):
        page=self.open_preview('controls');state=c.load_state(ROOT/'state-controls.json')
        page.evaluate('compositionRuntime.start()');snapshots=[]
        for frame in (30,40,54,67,91,118,140):
            snapshot=self.settled_snapshot(page,frame,f'controls-{frame}');self.check_model(snapshot,state)
            snapshots.append(snapshot)
        a,b=snapshots[:2]
        self.assertAlmostEqual(a['loops'][0]['currentTime'],b['loops'][0]['currentTime'],delta=.001)
        self.assertTrue(b['loops'][0]['paused'])
        self.assertGreater(b['loops'][1]['currentTime'],a['loops'][1]['currentTime'])
        self.assertNotEqual(snapshots[2]['loops'][1]['source'],snapshots[3]['loops'][1]['source'])
        self.assertEqual(snapshots[2]['loops'][0]['source'],snapshots[3]['loops'][0]['source'])
        self.assertEqual(snapshots[2]['loops'][2]['source'],snapshots[3]['loops'][2]['source'])
        self.assertFalse(snapshots[2]['loops'][0]['paused'])
        self.assertGreater(snapshots[2]['loops'][0]['currentTime'],b['loops'][0]['currentTime'])
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i) => n.media === initialMedia[i])'))
        events=page.evaluate('compositionRuntime.events')
        self.assertTrue(any(x['type']=='source' and x['frame']>=84 for x in events))
        (ROOT/'evidence/browser-controls.json').write_text(json.dumps(dict(snapshots=snapshots,events=events),indent=2)+'\n')

    def test_native_trim_loop_boundaries(self):
        page=self.open_preview('trim');state=c.load_state(ROOT/'state-trim.json')
        page.evaluate('compositionRuntime.start()');snapshots=[]
        for frame in (30,54,78,102):
            snapshot=self.settled_snapshot(page,frame,f'trim-{frame}');self.check_model(snapshot,state)
            self.assertGreaterEqual(snapshot['loops'][0]['currentTime'],1)
            self.assertLess(snapshot['loops'][0]['currentTime'],2)
            snapshots.append(snapshot)
        events=page.evaluate('compositionRuntime.events')
        seeks=[x for x in events if x['type']=='seek-command' and x['reason']=='timeline-boundary']
        self.assertGreaterEqual(len(seeks),4)
        self.assertEqual({x['id'] for x in seeks},{'loop-1'})
        (ROOT/'evidence/browser-trim.json').write_text(json.dumps(dict(snapshots=snapshots,events=events),indent=2)+'\n')

    def test_browser_rejects_altered_media_before_mounting(self):
        target=ROOT/'preview-corrupt';plan=build_preview(ROOT/'state-3.json',target)
        (target/plan['sources'][0]['path']).write_bytes(b'not the hashed video')
        page=self.browser.new_page();self.addCleanup(page.close)
        self.load_page(page,target)
        page.wait_for_function('window.compositionRuntime?.error')
        self.assertIn('Media integrity',page.evaluate('compositionRuntime.error'))
        self.assertEqual(page.locator('#stage > .loop').count(),0)
        # Restore the private synthetic test copy so the deliverable has no corrupt media.
        build_preview(ROOT/'state-3.json',target)

    def test_paused_intent_preserved_during_async_start(self):
        page = self.open_preview(3)
        res = page.evaluate("""async () => {
            const r = window.compositionRuntime;
            const startPromise = r.start();
            r.pause();
            await startPromise;
            return {
                running: r.running,
                datasetStatus: stage.dataset.status,
                pauseIntent: r.pauseIntent,
                events: r.events.map(e => e.type),
            };
        }""")
        self.assertFalse(res['running'])
        self.assertEqual(res['datasetStatus'], 'paused')
        self.assertFalse(res['pauseIntent'])
        self.assertIn('pause-intent', res['events'])
        self.assertIn('paused', res['events'])

    def test_bounded_event_log_cap(self):
        page = self.open_preview(3)
        res = page.evaluate("""() => {
            const r = window.compositionRuntime;
            r.maxEvents = 10;
            for (let i = 0; i < 25; i++) {
                record('test-cap-event', null, {index: i});
            }
            return {
                eventCount: r.events.length,
                firstIndex: r.events[0].index,
                lastIndex: r.events[r.events.length - 1].index,
            };
        }""")
        self.assertEqual(res['eventCount'], 10)
        self.assertEqual(res['firstIndex'], 15)
        self.assertEqual(res['lastIndex'], 24)

    def test_repeated_initialization_and_dispose_cleanup(self):
        page = self.open_preview(3)
        self.assertTrue(page.evaluate('compositionRuntime.ready'))
        self.assertGreater(page.locator('#stage > .loop').count(), 0)
        # Dispose
        page.evaluate('compositionRuntime.dispose()')
        snap = page.evaluate('compositionRuntime.snapshot()')
        self.assertFalse(page.evaluate('compositionRuntime.ready'))
        self.assertTrue(snap['disposed'])
        self.assertEqual(page.locator('#stage > .loop').count(), 0)
        self.assertEqual(page.evaluate('compositionRuntime.sources.size'), 0)
        self.assertEqual(page.evaluate('compositionRuntime.nodes.size'), 0)
        # Re-initialize
        page.evaluate('compositionRuntime.initialize()')
        page.wait_for_function('compositionRuntime.ready')
        self.assertTrue(page.evaluate('compositionRuntime.ready'))
        self.assertGreater(page.locator('#stage > .loop').count(), 0)

    def test_explicit_controls_play_pause_resume_replay(self):
        page = self.open_preview(3)
        # play()
        page.evaluate('compositionRuntime.play()')
        page.wait_for_function('compositionRuntime.running')
        self.assertTrue(page.evaluate('compositionRuntime.running'))
        # pause()
        page.evaluate('compositionRuntime.pause()')
        self.assertFalse(page.evaluate('compositionRuntime.running'))
        # resume()
        page.evaluate('compositionRuntime.resume()')
        self.assertTrue(page.evaluate('compositionRuntime.running'))
        # replay()
        page.wait_for_timeout(150)
        page.evaluate('compositionRuntime.replay()')
        page.wait_for_function('compositionRuntime.running')
        self.assertTrue(page.evaluate('compositionRuntime.running'))

    def test_asset_load_failure_explicit_retryable_state(self):
        page = self.open_preview(3)
        res = page.evaluate("""async () => {
            const r = window.compositionRuntime;
            const originalPlan = r.plan;
            fail(new Error('Missing media: source-1'), true);
            const snap = r.snapshot();
            const planRetained = (r.plan === originalPlan);
            return {
                retryable: r.retryable,
                hasAssetError: !!r.assetError,
                error: r.error,
                planRetained: planRetained,
                snapshotRetryable: snap.retryable,
            };
        }""")
        self.assertTrue(res['retryable'])
        self.assertTrue(res['hasAssetError'])
        self.assertIn('Missing media', res['error'])
        self.assertTrue(res['planRetained'])
        self.assertTrue(res['snapshotRetryable'])

    def test_browser_page_snapshot_and_viewport_rendering(self):
        page = self.open_preview(3)
        res = page.evaluate("""() => {
            const r = window.compositionRuntime;
            const items = Array.from({length: 30}, (_, i) => ({id: 'c' + i}));
            const p = r.pageSnapshot(items, { pageSize: 24, seed: 1234 });
            const node = r.nodes.get('loop-1');
            node.span.slice_rect = ['1/4', '1/4', '1/2', '1/2'];
            r.applySlice(node);
            return {
                totalPages: p.totalPages,
                activeDecoders: p.activeDecoders,
                maxActiveDecoders: p.maxActiveDecoders,
                datasetSliceRect: node.box.dataset.sliceRect,
                cssSliceX: node.media.style.getPropertyValue('--slice-x'),
            };
        }""")
        self.assertEqual(res['totalPages'], 2)
        self.assertEqual(res['maxActiveDecoders'], 6)
        self.assertEqual(res['activeDecoders'], 6)
        self.assertEqual(res['datasetSliceRect'], '0.25,0.25,0.5,0.5')
        self.assertEqual(res['cssSliceX'], '0.25')


class SnapshotPagingAndViewportTests(unittest.TestCase):
    def test_page_snapshot_pure_helper_and_decoder_bounds(self):
        runtime_js = HERE / 'browser.runtime.js'
        script = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const stage = {dataset:{}, style:{setProperty(){}, removeProperty(){}}, addEventListener(){}};
const context = vm.createContext({
  window:{}, document:{querySelector(){return stage;}, addEventListener(){}},
  performance:{now(){return 1000;}},
  ResizeObserver:class {observe(){}}, fetch(){return new Promise(()=>{});},
  setTimeout, clearTimeout, URL, Blob, console,
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const r = context.window.compositionRuntime;
const pageSnapshot = r.pageSnapshot || context.window.pageSnapshot;
assert(typeof pageSnapshot === 'function', 'pageSnapshot must be exported');

// 1. Empty items
const empty = pageSnapshot([], { pageSize: 24 });
assert.equal(empty.totalItems, 0);
assert.equal(empty.totalPages, 0);
assert.equal(empty.pageIndex, 0);
assert.equal(empty.hasNextPage, false);
assert.equal(empty.hasPrevPage, false);
assert.deepEqual(empty.items, []);

// 2. 100 items paged at 24 items per page
const catalogue = Array.from({length: 100}, (_, i) => ({ id: `clip-${i}`, name: `Clip ${i}` }));
const p0 = pageSnapshot(catalogue, { pageIndex: 0, pageSize: 24 });
assert.equal(p0.totalItems, 100);
assert.equal(p0.totalPages, 5);
assert.equal(p0.pageSize, 24);
assert.equal(p0.pageIndex, 0);
assert.equal(p0.items.length, 24);
assert.equal(p0.hasNextPage, true);
assert.equal(p0.hasPrevPage, false);
assert.equal(p0.maxActiveDecoders, 6);
assert.equal(p0.activeDecoders, 6);

// Decoder cap invariant: exactly first 6 items have activeDecoder true, remaining false
const activeCount = p0.items.filter(it => it.activeDecoder).length;
assert.equal(activeCount, 6);
assert.equal(p0.items[5].activeDecoder, true);
assert.equal(p0.items[6].activeDecoder, false);

// Last page (index 4)
const p4 = pageSnapshot(catalogue, { pageIndex: 4, pageSize: 24 });
assert.equal(p4.pageIndex, 4);
assert.equal(p4.items.length, 4);
assert.equal(p4.hasNextPage, false);
assert.equal(p4.hasPrevPage, true);
assert.equal(p4.activeDecoders, 4);

// Clamping out-of-bounds pageIndex
const pOver = pageSnapshot(catalogue, { pageIndex: 99, pageSize: 24 });
assert.equal(pOver.pageIndex, 4);

// Clamping maxActiveDecoders > 6
const pClamp = pageSnapshot(catalogue, { pageSize: 24, maxActiveDecoders: 16 });
assert.equal(pClamp.maxActiveDecoders, 6);

// Deterministic seeding
const seedA1 = pageSnapshot(catalogue, { seed: 'seed-xyz', pageSize: 10 });
const seedA2 = pageSnapshot(catalogue, { seed: 'seed-xyz', pageSize: 10 });
assert.deepEqual(seedA1.items.map(i => i.id), seedA2.items.map(i => i.id));

const seedB = pageSnapshot(catalogue, { seed: 'seed-diff', pageSize: 10 });
assert.notDeepEqual(seedA1.items.map(i => i.id), seedB.items.map(i => i.id));

console.log(JSON.stringify({ok: true}));
'''
        result = subprocess.run(['node', '-e', script, str(runtime_js)],
                                check=True, capture_output=True, text=True, timeout=15)
        self.assertTrue(json.loads(result.stdout).get('ok'))

    def test_apply_slice_viewport_crop_and_css_properties(self):
        runtime_js = HERE / 'browser.runtime.js'
        script = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const stage = {dataset:{}, style:{setProperty(){}, removeProperty(){}}, addEventListener(){}};
const context = vm.createContext({
  window:{}, document:{querySelector(){return stage;}, addEventListener(){}},
  performance:{now(){return 1000;}},
  ResizeObserver:class {observe(){}}, fetch(){return new Promise(()=>{});},
  setTimeout, clearTimeout, URL, Blob, console,
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const r = context.window.compositionRuntime;
const applySlice = r.applySlice;
assert(typeof applySlice === 'function');

const props = {};
const mediaStyle = {
  setProperty(k, v) { props[k] = v; },
  removeProperty(k) { delete props[k]; }
};
const boxProps = {};
const boxStyle = {
  setProperty(k, v) { boxProps[k] = v; },
  removeProperty(k) { delete boxProps[k]; }
};
const node = {
  id: 'panel-0',
  box: { dataset: {}, style: boxStyle },
  media: { dataset: {}, style: mediaStyle },
  span: { slice_rect: ['1/3', '1/4', '1/3', '1/2'] }
};

applySlice(node);
assert.equal(node.box.dataset.sliceRect, `${1/3},${1/4},${1/3},${1/2}`);
assert.equal(node.media.dataset.sliceRect, `${1/3},${1/4},${1/3},${1/2}`);
assert.equal(props['--slice-x'], String(1/3));
assert.equal(props['--slice-y'], String(1/4));
assert.equal(props['--slice-w'], String(1/3));
assert.equal(props['--slice-h'], String(1/2));
assert.equal(boxProps['--slice-x'], String(1/3));

// Full-frame slice clears dataset and custom properties
node.span.slice_rect = ['0', '0', '1', '1'];
applySlice(node);
assert.equal(node.box.dataset.sliceRect, undefined);
assert.equal(node.media.dataset.sliceRect, undefined);
assert.equal(props['--slice-x'], undefined);

console.log(JSON.stringify({ok: true}));
'''
        result = subprocess.run(['node', '-e', script, str(runtime_js)],
                                check=True, capture_output=True, text=True, timeout=15)
        self.assertTrue(json.loads(result.stdout).get('ok'))


if __name__=='__main__':unittest.main()
