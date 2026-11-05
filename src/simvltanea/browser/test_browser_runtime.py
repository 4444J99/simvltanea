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

    def test_pr34_retry_releases_nodes_and_can_retry_again_after_failure(self):
        page = self.open_preview(3)
        result = page.evaluate("""async () => {
            const r = compositionRuntime, original = io.plan;
            const urls = [...r.sources.values()].map(s => s.url);
            const revoked = [], revoke = URL.revokeObjectURL;
            URL.revokeObjectURL = url => { revoked.push(url); revoke(url); };
            fail(Error('Media decode failed'), true);
            io.plan = async () => { throw Error('Cannot load compiled plan'); };
            try { await r.retry(); } catch (_) {}
            const retryable = r.retryable && !!r.error;
            io.plan = original;
            await r.retry();
            return {ready:r.ready, error:r.error, retryable,
                released:urls.every(url => revoked.includes(url)), nodes:r.nodes.size};
        }""")
        self.assertTrue(result['retryable'])
        self.assertTrue(result['released'])
        self.assertTrue(result['ready'])
        self.assertIsNone(result['error'])
        self.assertEqual(result['nodes'], 3)

    def test_pr34_dispose_cancels_plan_and_media_initialization(self):
        for boundary in ('plan', 'bytes', 'digest'):
            with self.subTest(boundary=boundary):
                page = self.open_preview(3)
                result = page.evaluate("""async boundary => {
                    const r=compositionRuntime;
                    r.dispose();
                    const original=io[boundary]; let release, entered;
                    const gate=new Promise(resolve => release=resolve);
                    const waiting=new Promise(resolve => entered=resolve);
                    io[boundary]=async (...args) => { entered(); await gate; return original(...args); };
                    const pending=r.initialize(); await waiting;
                    r.dispose(); release(); await pending;
                    return {ready:r.ready, initializing:r.initializing, disposed:r.disposed,
                        nodes:r.nodes.size, sources:r.sources.size, status:stage.dataset.status};
                }""", boundary)
                self.assertEqual(result, dict(ready=False, initializing=False, disposed=True,
                                             nodes=0, sources=0, status='disposed'))

    def test_pr34_finished_runtime_reinitializes_for_gesture(self):
        page = self.open_preview(3)
        result = page.evaluate("""async () => {
            const r=compositionRuntime;
            await r.seek(r.plan.frames/r.plan.fps - .01); await r.start();
            await new Promise(resolve => setTimeout(resolve, 150));
            const finished=r.finished;
            r.dispose(); await r.initialize(); await r.start();
            return {finished, running:r.running};
        }""")
        self.assertTrue(result['finished'])
        self.assertTrue(result['running'])

    def test_pr34_decimal_viewport_and_partial_to_full_fit(self):
        page = self.open_preview(3)
        result = page.evaluate("""() => {
            const n=compositionRuntime.nodes.values().next().value;
            n.item={viewport:{x:.25,y:.25,width:.5,height:.5}};
            applyLayout(); const partial=n.box.dataset.sliceRect;
            n.span.slice_rect=['0','0','1','1']; applyLayout();
            return {partial, fit:n.media.style.objectFit, expected:n.cell.fit};
        }""")
        self.assertEqual(result['partial'], '0.25,0.25,0.5,0.5')
        self.assertEqual(result['fit'], result['expected'])

    def test_pr34_invalid_decoder_cap_uses_default(self):
        page = self.open_preview(3)
        self.assertEqual(page.evaluate("compositionRuntime.pageSnapshot(Array.from({length:8},(_,i)=>({id:i})), {maxActiveDecoders:'bad'}).activeDecoders"), 6)

    def test_pr34_dispose_cancels_media_activation(self):
        page = self.open_preview(3)
        result = page.evaluate("""async () => {
            const r=compositionRuntime; r.dispose();
            let release, entered;
            const gate=new Promise(resolve=>release=resolve);
            const waiting=new Promise(resolve=>entered=resolve);
            const original=waitFor;
            waitFor=async (...args)=>{await original(...args); entered(); await gate;};
            const pending=r.initialize(); await waiting;
            r.dispose(); release(); await pending;
            waitFor=original;
            return {ready:r.ready,nodes:r.nodes.size,sources:r.sources.size,status:stage.dataset.status};
        }""")
        self.assertEqual(result,dict(ready=False,nodes=0,sources=0,status='disposed'))

    def test_pr34_stale_initialization_cannot_overwrite_new_generation(self):
        page = self.open_preview(3)
        result = page.evaluate("""async () => {
            const r=compositionRuntime, original=io.plan;
            let release, entered;
            const gate=new Promise(resolve=>release=resolve);
            const waiting=new Promise(resolve=>entered=resolve);
            io.plan=async ()=>{entered(); await gate; throw Error('stale plan failure');};
            const stale=r.initialize(); await waiting;
            io.plan=original; await r.initialize();
            const epoch=r.initEpoch;
            release(); await stale;
            return {ready:r.ready,error:r.error,epoch:r.initEpoch===epoch,nodes:r.nodes.size};
        }""")
        self.assertEqual(result,dict(ready=True,error=None,epoch=True,nodes=3))

    def test_pr34_pause_during_running_seek_prevents_restart(self):
        page=self.open_preview(3)
        result=page.evaluate("""async () => {
            const r=compositionRuntime; await r.start();
            let release, entered;
            const gate=new Promise(resolve=>release=resolve);
            const waiting=new Promise(resolve=>entered=resolve);
            const original=waitFor;
            waitFor=async (...args)=>{await original(...args); entered(); await gate;};
            const pending=r.seek(1); await waiting;
            r.pause(); release(); await pending; waitFor=original;
            return {running:r.running,pauseIntent:r.pauseIntent,status:stage.dataset.status};
        }""")
        self.assertEqual(result,dict(running=False,pauseIntent=False,status='paused'))

    def build_engine_absent_preview(self):
        """Stage state-3 with a real resolver refusal that names absolute paths."""
        import tempfile
        from simvltanea.browser import browser_runtime as runtime
        from simvltanea.browser.shared_engine import SharedEngineUnavailable, resolve_shared_engine
        isolated=Path(self.enterContext(tempfile.TemporaryDirectory()))/'consumer'/'src'
        isolated.mkdir(parents=True)
        (isolated.parent/'pyproject.toml').write_text('[project]\nname="isolated"\n')
        with self.assertRaises(SharedEngineUnavailable) as caught:resolve_shared_engine(isolated)
        detail=str(caught.exception)
        self.assertIn(str(isolated.parent.resolve()),detail)
        target=ROOT/'preview-engine-absent'
        with patch.object(runtime,'resolve_shared_engine',side_effect=caught.exception):
            build_preview(ROOT/'state-3.json',target)
        return target,detail

    def test_absent_shared_engine_is_ready_with_path_free_note(self):
        from simvltanea.browser import browser_runtime as runtime
        from simvltanea.paths import REPO_ROOT
        target,detail=self.build_engine_absent_preview()
        note=runtime.SHARED_ENGINE_NOT_FOUND_NOTE
        self.assertEqual((target/'shared-engine-unavailable.txt').read_text(),note+'\n')
        for path in target.rglob('*'):
            if path.suffix not in ('.html','.txt','.js','.json'):continue
            text=path.read_text()
            with self.subTest(staged=path.name):
                for fragment in ('/Users/','/Volumes/','/private/','/home/','/var/','/tmp/',str(REPO_ROOT)):
                    self.assertNotIn(fragment,text)
                self.assertNotRegex(text,r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]')
                for line in detail.splitlines()[1:-1]:self.assertNotIn(line.strip(),text)
        page=self.open_preview('engine-absent')
        page.wait_for_function("stage.dataset.status === 'ready'")
        view=page.evaluate("""() => ({status:stage.dataset.status,
            label:document.querySelector('#runtime-status').textContent,
            live:document.querySelector('#runtime-status').getAttribute('aria-live'),
            note:document.querySelector('#runtime-note')?.textContent ?? null,
            engine:compositionRuntime.snapshot().sharedEngine.error,
            lang:document.documentElement.lang, title:document.title,
            labels:[...document.querySelectorAll('#stage video')].map(v => v.getAttribute('aria-label'))})""")
        self.assertEqual(view,dict(status='ready',label='Click or press Space to play the silent field.',
                                   live='polite',note=note,engine=note,lang='en',title=runtime.PREVIEW_TITLE,
                                   labels=['Loop 1 of 3','Loop 2 of 3','Loop 3 of 3']))
        page.click('#stage')
        page.wait_for_function("stage.dataset.status === 'playing'")
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        self.assertEqual(page.locator('#runtime-note').inner_text(),note)

    def test_staged_engine_that_fails_to_load_still_reports_error(self):
        """Only a build-declared absence is informational; a staged engine failing is not."""
        target,_=self.build_engine_absent_preview()
        html=(target/'index.html').read_text()
        declared=html[html.index('<script>window.__sharedEngineUnavailable'):html.index('</script>\n',html.index('<script>window.__sharedEngineUnavailable'))+10]
        staged=('<script src="shared-engine-adapter.js" defer></script>\n'
                '<script type="module" src="shared-engine.js"></script>\n')
        adapter=(HERE/'shared_engine_adapter.js').read_text()
        for name,replacement,expected in (
                ('module-blocked',staged,'Shared engine unavailable: simvltanea shared-engine adapter: shared engine not found.'),
                ('adapter-missing','','Shared engine unavailable: shared-engine adapter did not load')):
            with self.subTest(case=name):
                page=self.browser.new_page(viewport={'width':390,'height':844});self.addCleanup(page.close)
                body=html.replace(declared,replacement)
                self.assertNotEqual(body,html)
                page.route('**/preview-engine-absent/',functools.partial(
                    lambda body,route:route.fulfill(status=200,content_type='text/html',body=body),body))
                page.route('**/shared-engine-adapter.js',lambda route:route.fulfill(
                    status=200,content_type='text/javascript',body=adapter))
                page.route('**/shared-engine.js',lambda route:route.abort())
                page.goto(f'{self.base}/{target.name}/')
                page.wait_for_function('compositionRuntime.ready || compositionRuntime.error',timeout=20000)
                page.wait_for_function("stage.dataset.status === 'error'")
                self.assertTrue(page.locator('#runtime-status').inner_text().startswith(expected))
                self.assertIsNone(page.evaluate('compositionRuntime.error'))
                self.assertEqual(page.locator('#runtime-note').count(),0)

    def test_set_orientation_pins_the_authored_layout_without_touching_clocks(self):
        page=self.open_preview(3);state=c.load_state(ROOT/'state-3.json')
        page.evaluate('compositionRuntime.start()')
        before=self.settled_snapshot(page,12,'orientation-auto')
        self.assertEqual((before['orientation'],before['orientationOverride']),('portrait',None))
        def cells(orientation):
            stage=page.evaluate('(() => { const r = stage.getBoundingClientRect(); return [r.width, r.height]; })()')
            return [[float(Fraction(v))*stage[i%2] for i,v in enumerate(cell['rect'])]
                    for cell in state['layouts'][orientation]['cells']]
        for value,expected in (('landscape','landscape'),('portrait','portrait'),(None,'portrait')):
            page.evaluate('value => compositionRuntime.setOrientation(value)',value)
            page.wait_for_timeout(350)
            after=self.snap(page,f'orientation-{value}')
            # The 390x844 stage is portrait-shaped; only the hook can choose landscape.
            self.assertEqual((after['orientation'],after['orientationOverride']),(expected,value))
            boxes=[[loop['rect'][key] for key in ('x','y','width','height')] for loop in after['loops']]
            for box,cell in zip(boxes,cells(expected)):
                for actual,wanted in zip(box,cell):self.assertAlmostEqual(actual,wanted,delta=1.5)
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i) => n.media === initialMedia[i] && n.box === initialBoxes[i])'))
            for old,new in zip(before['loops'],after['loops']):
                self.assertGreater(new['callbacks'],old['callbacks'])
                self.assertFalse(new['paused'])
            self.check_model(after,state)
            before=after
        events=page.evaluate('compositionRuntime.events')
        self.assertEqual([e['orientation'] for e in events if e['type']=='orientation-override'],['landscape','portrait',None])
        self.assertFalse([e for e in events if e['type'] in ('seek-command','source','loadstart') and e['frame']>12])
        error=page.evaluate("() => { try { compositionRuntime.setOrientation('square'); } catch (e) { return String(e); } }")
        self.assertEqual(error,'Error: Orientation must be "portrait", "landscape" or null')
        self.assertIsNone(page.evaluate('compositionRuntime.orientationOverride'))

    def test_seven_loop_videos_are_labelled_by_position(self):
        page=self.open_preview(7)
        self.assertEqual(page.locator('#stage video').evaluate_all('nodes => nodes.map(n => n.getAttribute("aria-label"))'),
                         [f'Loop {index} of 7' for index in range(1,8)])

    def finish(self,page):
        page.evaluate("""async () => {
            const r=compositionRuntime;
            await r.seek(r.plan.frames/r.plan.fps - .05); await r.start();
        }""")
        page.wait_for_function('compositionRuntime.finished',timeout=5000)
        self.assertEqual(page.evaluate('stage.dataset.status'),'finished')
        self.assertEqual(page.locator('#runtime-status').inner_text(),
                         'Composition finished. Click or press Space to play again.')
        return page.evaluate('compositionRuntime.events.length')

    def assert_restarted(self,page,state,before):
        page.wait_for_function("compositionRuntime.running && stage.dataset.status === 'playing'",timeout=5000)
        snapshot=self.settled_snapshot(page,12,'restart-after-finish')
        self.assertFalse(snapshot['finished'])
        self.assertLess(snapshot['compositionTime'],2)
        # Every loop resumed from its authored clock at the restart frame.
        self.check_model(snapshot,state)
        events=page.evaluate('compositionRuntime.events')
        tail=[event['type'] for event in events[before:]]
        self.assertIn('restart',tail)
        seeks=[event for event in events[before:] if event['type']=='transport-seek']
        self.assertEqual([event['time'] for event in seeks],[0])
        self.assertLess(tail.index('restart'),tail.index('transport-seek'))
        self.assertNotIn('error',tail)
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i) => n.media === initialMedia[i] && n.box === initialBoxes[i])'))

    def test_click_and_space_after_finish_restart_from_the_beginning(self):
        page=self.open_preview(3);state=c.load_state(ROOT/'state-3.json')
        before=self.finish(page)
        page.click('#stage')
        self.assert_restarted(page,state,before)
        page.evaluate('compositionRuntime.pause()')
        before=self.finish(page)
        page.evaluate('document.activeElement.blur()')
        self.assertTrue(page.evaluate('document.activeElement === document.body'))
        page.keyboard.press('Space')
        self.assert_restarted(page,state,before)

    def test_space_works_from_body_but_not_from_focused_controls(self):
        page=self.open_preview(3)
        page.evaluate("""() => { window.spaceSeen=[];
            window.addEventListener('keydown', e => { if (e.code === 'Space') spaceSeen.push(e.defaultPrevented); }); }""")
        self.assertTrue(page.evaluate('document.activeElement === document.body'))
        page.keyboard.press('Space')
        page.wait_for_function("stage.dataset.status === 'playing'")
        page.keyboard.press('Space')
        page.wait_for_function("stage.dataset.status === 'paused'")
        self.assertEqual(page.evaluate('spaceSeen'),[True,True])
        for markup in ('<button type="button">control</button>','<input type="text">','<a href="#x">link</a>',
                       '<select><option>a</option></select>','<textarea></textarea>'):
            with self.subTest(markup=markup):
                page.evaluate("""markup => { const holder=document.createElement('div');
                    holder.id='controls'; holder.innerHTML=markup; document.body.append(holder);
                    holder.firstElementChild.focus(); spaceSeen.length=0; }""",markup)
                page.keyboard.press('Space')
                page.wait_for_timeout(150)
                self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running, spaceSeen]'),
                                 ['paused',False,[False]])
                page.evaluate("document.querySelector('#controls').remove()")
        # Keyboard focus reaches the stage and shows a visible focus ring there.
        page.evaluate('document.activeElement.blur()')
        page.keyboard.press('Tab')
        focus=page.evaluate("""() => ({stage:document.activeElement === stage, visible:stage.matches(':focus-visible'),
            outline:getComputedStyle(stage).outlineStyle, ring:getComputedStyle(stage,'::after').boxShadow})""")
        self.assertTrue(focus['stage']);self.assertTrue(focus['visible'])
        self.assertEqual(focus['outline'],'solid');self.assertNotEqual(focus['ring'],'none')
        page.keyboard.press('Space')
        page.wait_for_function("stage.dataset.status === 'playing'")

    def watch_space(self,page):
        page.evaluate("""() => { window.spaceSeen=[];
            window.addEventListener('keydown', e => { if (e.code === 'Space') spaceSeen.push([e.defaultPrevented, e.repeat]); }); }""")

    def test_held_space_toggles_once_but_still_blocks_page_scroll(self):
        page=self.open_preview(3);self.watch_space(page)
        page.keyboard.down('Space')
        page.wait_for_function("stage.dataset.status === 'playing'")
        for _ in range(3):   # auto-repeat of the held key
            page.keyboard.down('Space');page.wait_for_timeout(60)
        page.wait_for_timeout(200)
        self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running]'),['playing',True])
        self.assertEqual(page.evaluate('spaceSeen'),[[True,False]]+[[True,True]]*3)
        page.keyboard.up('Space')
        page.keyboard.press('Space')
        page.wait_for_function("stage.dataset.status === 'paused'")
        # Holding the key after the composition finished restarts once and keeps playing.
        before=self.finish(page)
        page.keyboard.down('Space')
        page.wait_for_function("compositionRuntime.running && stage.dataset.status === 'playing'",timeout=5000)
        for _ in range(3):
            page.keyboard.down('Space');page.wait_for_timeout(60)
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running]'),['playing',True])
        tail=[event['type'] for event in page.evaluate('compositionRuntime.events')[before:]]
        self.assertEqual(tail.count('restart'),1);self.assertNotIn('paused',tail)
        page.keyboard.up('Space')

    def test_space_with_modifier_or_during_composition_is_left_to_the_browser(self):
        page=self.open_preview(3);self.watch_space(page)
        for state in ('ready','playing'):
            if state=='playing':
                page.evaluate('compositionRuntime.start()')
                page.wait_for_function("stage.dataset.status === 'playing'")
            for chord in ('Control+Space','Alt+Space','Meta+Space','Shift+Space'):
                with self.subTest(state=state,chord=chord):
                    page.evaluate('spaceSeen.length=0')
                    page.keyboard.press(chord)
                    page.wait_for_timeout(120)
                    self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running, spaceSeen]'),
                                     [state,state=='playing',[[False,False]]])
            with self.subTest(state=state,chord='composition'):
                composed=page.evaluate("""() => { const e=new KeyboardEvent('keydown',
                    {code:'Space',key:' ',isComposing:true,bubbles:true,cancelable:true});
                    return [document.body.dispatchEvent(e), e.defaultPrevented]; }""")
                page.wait_for_timeout(120)
                self.assertEqual(composed,[True,False])
                self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running]'),[state,state=='playing'])
        # A plain Space is still the toggle.
        page.keyboard.press('Space')
        page.wait_for_function("stage.dataset.status === 'paused'")

    def finish_during_transition(self,page):
        """Finish playback while a real media transition (a span boundary) is still busy."""
        page.evaluate("""async () => {
            const r=compositionRuntime, n=[...r.nodes.values()][0], play=n.media.play.bind(n.media);
            window.slowNode=n;
            // Delay the real activation at the last span boundary beyond the end of the composition.
            n.media.play=async () => { if (n.busy) await new Promise(resolve=>setTimeout(resolve,1800)); return play(); };
            await r.seek(r.plan.tracks[0].spans.at(-1).frame/r.plan.fps - 1/r.plan.fps); await r.start();
        }""")
        page.wait_for_function('compositionRuntime.finished',timeout=5000)
        self.assertTrue(page.evaluate('slowNode.busy'))
        self.assertEqual(page.evaluate('stage.dataset.status'),'finished')
        return page.evaluate('compositionRuntime.events.length')

    def test_restart_requested_during_busy_transition_runs_when_it_settles(self):
        for gesture in ('click','space'):
            with self.subTest(gesture=gesture):
                page=self.open_preview('trim');state=c.load_state(ROOT/'state-trim.json')
                before=self.finish_during_transition(page)
                if gesture=='click':page.click('#stage')
                else:
                    page.evaluate('document.activeElement.blur()');page.keyboard.press('Space')
                queued=page.evaluate("""() => ({status:stage.dataset.status, text:document.querySelector('#runtime-status').textContent,
                    running:compositionRuntime.running, intent:compositionRuntime.restartIntent})""")
                self.assertEqual(queued,dict(status='finished',running=False,intent=True,
                                             text='Composition finished. Restarting as soon as media is ready…'))
                page.click('#stage');page.keyboard.press('Space')   # no double start while waiting
                page.wait_for_function("compositionRuntime.running && stage.dataset.status === 'playing'",timeout=8000)
                self.assertFalse(page.evaluate('compositionRuntime.restartIntent'))
                self.assertFalse(page.evaluate('slowNode.busy'))
                page.wait_for_timeout(300)
                self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running]'),['playing',True])
                events=page.evaluate('compositionRuntime.events')[before:]
                tail=[event['type'] for event in events]
                self.assertEqual(tail.count('restart-intent'),1);self.assertEqual(tail.count('restart'),1)
                self.assertLess(tail.index('restart-intent'),tail.index('restart'))
                self.assertEqual([event['time'] for event in events if event['type']=='transport-seek'],[0])
                self.assertNotIn('error',tail)

    def test_queued_restart_is_cleared_by_pause_and_by_dispose(self):
        page=self.open_preview('trim')
        before=self.finish_during_transition(page)
        page.click('#stage')
        self.assertTrue(page.evaluate('compositionRuntime.restartIntent'))
        page.evaluate('compositionRuntime.pause()')
        self.assertEqual(page.evaluate("""() => [compositionRuntime.restartIntent, stage.dataset.status,
            document.querySelector('#runtime-status').textContent]"""),
            [False,'finished','Composition finished. Click or press Space to play again.'])
        page.wait_for_function('!slowNode.busy',timeout=5000);page.wait_for_timeout(300)
        self.assertEqual(page.evaluate('[compositionRuntime.running, compositionRuntime.finished]'),[False,True])
        self.assertNotIn('restart',[event['type'] for event in page.evaluate('compositionRuntime.events')[before:]])
        # The page can still be restarted by a fresh gesture.
        page.click('#stage')
        page.wait_for_function("compositionRuntime.running && stage.dataset.status === 'playing'",timeout=5000)
        # Dispose while a restart is queued: nothing restarts afterwards.
        page=self.open_preview('trim')
        self.finish_during_transition(page)
        page.click('#stage')
        self.assertTrue(page.evaluate('compositionRuntime.restartIntent'))
        page.evaluate('compositionRuntime.dispose()')
        self.assertFalse(page.evaluate('compositionRuntime.restartIntent'))
        page.wait_for_timeout(2200)
        self.assertEqual(page.evaluate('[compositionRuntime.running, compositionRuntime.disposed]'),[False,True])
        self.assertNotIn('restart',[event['type'] for event in page.evaluate('compositionRuntime.events')])


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

    def test_pr34_decoded_frame_callback_after_dispose_is_inert(self):
        script = r"""
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
const body=source.slice(source.indexOf('function frameProbe('),source.indexOf('function setCssProp('));
let callback;
const runtime={initEpoch:1,disposed:false};
const node={media:{requestVideoFrameCallback(fn){callback=fn;},isConnected:true},callbacks:0};
const ctx=vm.createContext({runtime,node});
vm.runInContext(body+';frameProbe(node);',ctx);
runtime.disposed=true; runtime.initEpoch++; node.media=null;
callback(1,{mediaTime:1,presentedFrames:1});
assert.equal(node.callbacks,0);
assert.equal(node.decoded,undefined);
"""
        subprocess.run(['node','-e',script,str(HERE/'browser.runtime.js')],check=True,
                       capture_output=True,text=True,timeout=15)

    def test_decimal_slice_arrays_render_and_malformed_arrays_fail(self):
        script=r"""
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
const ctx=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('const number ='),source.indexOf('const stage ='))+
    source.slice(source.indexOf('function sliceValues('),source.indexOf('function isPartialSlice(')),ctx);
assert.equal(vm.runInContext('sliceValues([.25,.25,.5,.5]).join(",")',ctx),'0.25,0.25,0.5,0.5');
assert.equal(vm.runInContext('sliceValues(["1/4","1/4","1/2","1/2"]).join(",")',ctx),'0.25,0.25,0.5,0.5');
for (const rect of ['[0,0,1]','[0,0,1,1,1]','[0,0,NaN,1]']) {
    assert.throws(()=>vm.runInContext('sliceValues('+rect+')',ctx));
}
assert.throws(()=>vm.runInContext('number(.25)',ctx)); // compiled clocks remain strict
"""
        subprocess.run(['node','-e',script,str(HERE/'browser.runtime.js')],check=True,
                       capture_output=True,text=True,timeout=15)


if __name__=='__main__':unittest.main()
