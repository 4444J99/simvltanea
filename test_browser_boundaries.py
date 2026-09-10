"""Boundary and independent-instance proofs for the bounded native preview.

These use the same explicit transport switch as test_browser_runtime. No browser
or hardware is emulated as a substitute for actual native decoding. Fault cases
are labeled injections, not naturally observed network failures.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import composition as c
from browser_runtime import compile_plan, build_preview, HERE
from make_runtime_fixture import ROOT, prepare
import test_browser_runtime as legacy


class PlanBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare()

    def test_subminimum_video_rate_rejected_without_changing_model(self):
        state = c.load_state(ROOT / 'state-3.json')
        state['loops'][0]['rate'] = '1/1000'
        c.validate_state(state)  # The offline composition contract still permits this.
        with self.assertRaisesRegex(c.StateError, 'browser.*rate'):
            compile_plan(state)

    def test_browser_rate_boundary_is_inclusive(self):
        for rate in ('1/16', '8'):
            state = c.load_state(ROOT / 'state-3.json')
            state['frames'] = 24
            state['loops'][0]['rate'] = rate
            self.assertEqual(compile_plan(state)['tracks'][0]['spans'][0]['rate'], rate)

    def test_valid_fraction_spellings_compile_to_canonical_rationals(self):
        state = c.load_state(ROOT / 'state-3.json')
        state['sources'][0]['duration'] = '8.0'
        state['layouts']['portrait']['cells'][0]['rect'][0] = '4e-2'
        state['layouts']['portrait']['cells'][0]['focal'] = ['0.5', '1 / 2']
        plan = compile_plan(state)
        self.assertEqual(plan['sources'][0]['duration'], '8')
        cell = plan['layout_keyframes'][0]['layouts']['portrait']['cells'][0]
        self.assertEqual(cell['rect'][0], '1/25')
        self.assertEqual(cell['focal'], ['1/2', '1/2'])


class NativeBoundaryTests(unittest.TestCase):
    # Borrow setup/helpers without inheriting/recounting the original ten tests.
    @classmethod
    def setUpClass(cls):
        legacy.BrowserTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        legacy.BrowserTests.tearDownClass.__func__(cls)

    open_preview = legacy.BrowserTests.open_preview
    load_page = legacy.BrowserTests.load_page
    snap = legacy.BrowserTests.snap
    check_model = legacy.BrowserTests.check_model

    def record_proof(self, name, page, snapshots):
        (ROOT / f'evidence/boundary-{name}.json').write_text(json.dumps({
            'transport': self.transport, 'browser': self.browser.version,
            'snapshots': snapshots, 'events': page.evaluate('compositionRuntime.events'),
        }, indent=2) + '\n')

    def test_invalid_plan_rejected_before_media_io_or_mount(self):
        original = json.loads((ROOT / 'preview-3/plan.json').read_text())
        cases = {}
        for name, modify in (
            ('duplicate-loop', lambda p: p['tracks'].__setitem__(1, copy.deepcopy(p['tracks'][0]))),
            ('missing-source', lambda p: p['tracks'][0]['spans'][0].__setitem__('source', 'absent')),
            ('zero-fps', lambda p: p.__setitem__('fps', 0)),
            ('negative-bytes', lambda p: p['sources'][0].__setitem__('bytes', -1)),
            ('bad-rate', lambda p: p['tracks'][0]['spans'][0].__setitem__('rate', '1/1000')),
            ('missing-orientation', lambda p: p['layout_keyframes'][0]['layouts'].pop('portrait')),
            ('malformed-rational', lambda p: p['tracks'][0]['spans'][0].__setitem__('source_offset', '0/1/2')),
        ):
            plan = copy.deepcopy(original); modify(plan); cases[name] = plan
        observations = []
        for name, plan in cases.items():
            with self.subTest(name=name):
                page = self.browser.new_page()
                try:
                    page.set_content('<main id="stage"></main>')
                    page.evaluate('''plan => {
                        window.reads=0;
                        window.compositionIO={async plan(){return plan;},
                          async bytes(){window.reads++;return new Promise(()=>{});},
                          async digest(){throw Error('not reached');}};
                    }''', plan)
                    page.add_script_tag(content=(HERE / 'browser_runtime.js').read_text())
                    page.wait_for_timeout(100)
                    result = page.evaluate('''() => ({error:compositionRuntime.error, reads,
                        mounted:stage.children.length, ready:compositionRuntime.ready})''')
                    observations.append({'case': name, **result})
                    self.assertIsNotNone(result['error'])
                    self.assertEqual(result['reads'], 0)
                    self.assertEqual(result['mounted'], 0)
                    self.assertFalse(result['ready'])
                finally:
                    page.close()
        (ROOT / 'evidence/boundary-invalid-plans.json').write_text(json.dumps(observations, indent=2)+'\n')

    def test_error_during_start_cannot_be_overwritten_by_playing(self):
        page = self.open_preview(3)
        # A real media element receives an injected error while start() awaits
        # delayed play promises. This is a lifecycle fault, not decoder evidence.
        page.evaluate('''() => {
            for (const node of compositionRuntime.nodes.values()) {
                node.media.play = () => new Promise(resolve => setTimeout(resolve, 120));
            }
            window.startResult = compositionRuntime.start().then(()=> 'resolved', e=>String(e));
            [...compositionRuntime.nodes.values()][0].media.dispatchEvent(new Event('error'));
        }''')
        page.wait_for_timeout(200)
        status = page.evaluate('''() => ({status:stage.dataset.status, error:compositionRuntime.error,
            running:compositionRuntime.running, ready:compositionRuntime.ready})''')
        self.assertEqual(status['status'], 'error')
        self.assertIsNotNone(status['error'])
        self.assertFalse(status['running'])
        self.assertFalse(status['ready'])
        self.record_proof('start-error', page, [status])

    def test_explicit_source_reuse_preserves_independent_clocks_through_resize(self):
        state = c.load_state(ROOT / 'state-3.json')
        state['allow_source_reuse'] = True
        for loop in state['loops']:
            loop['bank'] = ['source-1']
        c.save_state(state, ROOT / 'state-shared-source.json')
        build_preview(ROOT / 'state-shared-source.json', ROOT / 'preview-shared-source')
        page = self.open_preview('shared-source')
        before = page.evaluate('compositionRuntime.events.length')
        page.evaluate('compositionRuntime.start()')
        snapshots = []
        for index, (width, height) in enumerate(((390,844),(844,390),(900,1300),(390,844))):
            page.set_viewport_size({'width':width,'height':height}); page.wait_for_timeout(350)
            snapshot = self.snap(page, f'shared-source-{index}'); self.check_model(snapshot,state)
            self.assertEqual({x['source'] for x in snapshot['loops']}, {'source-1'})
            self.assertEqual(len({x['id'] for x in snapshot['loops']}),3)
            self.assertTrue(page.evaluate('new Set(initialMedia).size===3 && [...compositionRuntime.nodes.values()].every((n,i)=>n.media===initialMedia[i] && n.box===initialBoxes[i])'))
            times=[x['currentTime'] for x in snapshot['loops']]
            self.assertLess(times[0],times[1]); self.assertLess(times[1],times[2])
            if snapshots:
                for old,new in zip(snapshots[-1]['loops'],snapshot['loops']):
                    self.assertGreater(new['currentTime'],old['currentTime'])
                    self.assertGreater(new['callbacks'],old['callbacks'])
            snapshots.append(snapshot)
        self.assertFalse([e for e in page.evaluate('compositionRuntime.events')[before:] if e['type'] in ('source','seek-command','loadstart')])
        self.record_proof('shared-source',page,snapshots)

    def test_hold_resize_release_and_finish_are_not_restarts(self):
        state = c.load_state(ROOT / 'state-3.json')
        state['frames'] = 108
        state['events'] = [dict(op='hold',frame=18,loop='loop-1',value=True),
                           dict(op='hold',frame=66,loop='loop-1',value=False)]
        c.save_state(state, ROOT / 'state-held-resize.json')
        build_preview(ROOT / 'state-held-resize.json', ROOT / 'preview-held-resize')
        page=self.open_preview('held-resize');page.evaluate('compositionRuntime.start()');snapshots=[]
        for index,(frame,width,height) in enumerate(((27,844,390),(40,390,844),(52,900,1300),(81,844,390))):
            page.wait_for_function(f'compositionRuntime.frame >= {frame}')
            before=page.evaluate('compositionRuntime.events.length')
            page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(80)
            snapshot=self.snap(page,f'held-resize-{index}');self.check_model(snapshot,state);snapshots.append(snapshot)
            self.assertFalse([e for e in page.evaluate('compositionRuntime.events')[before:] if e['type'] in ('source','seek-command','loadstart')])
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===initialMedia[i] && n.box===initialBoxes[i])'))
        for sample in snapshots[:3]:
            self.assertTrue(sample['loops'][0]['paused'])
            self.assertAlmostEqual(sample['loops'][0]['currentTime'],snapshots[0]['loops'][0]['currentTime'],delta=.001)
        self.assertGreater(snapshots[2]['loops'][1]['currentTime'],snapshots[0]['loops'][1]['currentTime'])
        self.assertFalse(snapshots[3]['loops'][0]['paused'])
        self.assertGreater(snapshots[3]['loops'][0]['currentTime'],snapshots[2]['loops'][0]['currentTime'])
        page.wait_for_function('compositionRuntime.finished')
        finished=page.evaluate('compositionRuntime.snapshot()');page.wait_for_timeout(200)
        self.assertEqual([x['currentTime'] for x in finished['loops']], [x['currentTime'] for x in page.evaluate('compositionRuntime.snapshot()')['loops']])
        self.assertTrue(all(x['paused'] for x in finished['loops']))
        self.assertEqual(page.evaluate('compositionRuntime.start().then(()=>"restarted",()=>"rejected")'), 'rejected')
        self.record_proof('held-resize-finish',page,snapshots+[finished])

    def test_zero_size_container_restores_without_reset(self):
        page=self.open_preview(3);page.evaluate('compositionRuntime.start()');page.wait_for_timeout(350)
        old=page.evaluate('compositionRuntime.snapshot()');before=page.evaluate('compositionRuntime.events.length')
        page.evaluate('stage.style.width="0px";stage.style.height="0px"');page.wait_for_timeout(250)
        page.evaluate('stage.style.width="390px";stage.style.height="180px"');page.wait_for_timeout(250)
        new=self.snap(page,'zero-size-restored')
        self.assertEqual(new['orientation'],'landscape')
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===initialMedia[i] && n.box===initialBoxes[i])'))
        for a,b in zip(old['loops'],new['loops']):
            self.assertGreater(b['currentTime'],a['currentTime'])
            self.assertGreater(b['callbacks'],a['callbacks'])
        self.assertFalse([e for e in page.evaluate('compositionRuntime.events')[before:] if e['type'] in ('source','seek-command','loadstart')])
        self.record_proof('zero-size',page,[old,new])


    def test_still_video_swap_preserves_loop_boxes_and_unrelated_video(self):
        import hashlib
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (160,160), 'white')
        draw = ImageDraw.Draw(image); draw.rectangle((12,12,147,147), outline='black', width=5)
        draw.text((22,72), 'STILL FIXTURE', fill='black')
        path = ROOT / 'media' / 'boundary-still.png'; image.save(path)
        state=c.load_state(ROOT/'state-3.json')
        state['sources'][2] = dict(id='source-3',path='media/boundary-still.png',
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kind='still',duration='8')
        state['events']=[dict(op='swap',frame=36,a='loop-1',b='loop-3'),
                         dict(op='swap',frame=84,a='loop-1',b='loop-3')]
        c.save_state(state,ROOT/'state-mixed.json')
        build_preview(ROOT/'state-mixed.json',ROOT/'preview-mixed')
        page=self.open_preview('mixed');page.evaluate('compositionRuntime.start()');snapshots=[]
        for index,(frame,width,height) in enumerate(((18,390,844),(48,844,390),(69,390,844),(99,844,390),(123,390,844))):
            page.wait_for_function(f'compositionRuntime.frame >= {frame}')
            before=page.evaluate('compositionRuntime.events.length')
            page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(70)
            snapshot=self.snap(page,f'mixed-{index}');self.check_model(snapshot,state)
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.box===initialBoxes[i])'))
            self.assertTrue(page.evaluate('compositionRuntime.nodes.get("loop-2").media===initialMedia[1]'))
            self.assertEqual(page.locator('#stage video').count(),2)
            self.assertEqual(page.locator('#stage img').count(),1)
            self.assertFalse([e for e in page.evaluate('compositionRuntime.events')[before:] if e['type'] in ('source','seek-command','loadstart')])
            snapshots.append(snapshot)
        self.assertEqual([x['kind'] for x in snapshots[0]['loops']],['video','video','still'])
        self.assertEqual([x['kind'] for x in snapshots[1]['loops']],['still','video','video'])
        self.assertEqual([x['kind'] for x in snapshots[-1]['loops']],['video','video','still'])
        self.record_proof('mixed-kind',page,snapshots)


if __name__ == '__main__':
    unittest.main()
