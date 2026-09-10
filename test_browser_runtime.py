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
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import composition as c
from browser_runtime import build_preview, compile_plan
from make_runtime_fixture import HERE, ROOT, prepare


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

    def test_preview_media_symlink_escape_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            target=Path(temp)/'preview';target.mkdir();(target/'media').symlink_to(Path(temp),target_is_directory=True)
            with self.assertRaises(c.StateError):build_preview(ROOT/'state-3.json',target)

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
        page.add_script_tag(content=(HERE/'browser_runtime.js').read_text())
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
    def test_7_loop_experimental_continuity(self):self.continuity(7)

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


if __name__=='__main__':unittest.main()
