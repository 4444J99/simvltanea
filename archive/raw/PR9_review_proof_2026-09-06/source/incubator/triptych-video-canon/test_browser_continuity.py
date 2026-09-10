"""Independent native-browser resize oracle; no runtime snapshot/log is trusted.

Uses the existing browser fixture/transport (HTTP by default, explicit in-memory
only where required). Never falls back, mocks media clocks, downloads a browser,
or relaxes browser policy. Synthetic N=7 remains experimental. See the receipt.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from fractions import Fraction

import composition as c
from browser_runtime import build_preview
from make_runtime_fixture import HERE, ROOT
import test_browser_runtime as existing

PROBE = HERE / 'browser_continuity_probe.js'
OUT = ROOT / 'evidence' / 'independent-continuity'
SOURCE_COLORS = {f'source-{index}':rgb for index,rgb in enumerate(
    [(170,45,45),(32,125,70),(35,80,170),(120,50,155),(170,110,25),(25,130,145),(145,45,100)],1)}
CLOCK_TOLERANCE = .15  # Seconds, from the arm baseline at every sampled animation frame.
GEOMETRY_TOLERANCE = 1.1  # CSS pixels; rational geometry is browser-rasterized.


def verify_trace(trace: dict, state: dict, checkpoints: list[dict]) -> dict:
    """Fail closed on absent evidence, mutations, drift, duplication or wrong layout."""
    def require(condition, code):
        if not condition:
            raise AssertionError(code)

    baseline = trace['initial']
    require(len(trace['samples']) >= 5 and len(checkpoints) >= 2, 'missing-samples')
    require(not trace['events'], 'media-or-dom-mutation')
    require(trace['samples'][-1]['wall'] - baseline['wall'] >= 200, 'short-window')
    expected = {loop['id']: loop for loop in c.resolve_at(state, 0)['loops']}
    initial = {loop['id']: loop for loop in baseline['loops']}
    require(set(initial) == set(expected), 'loop-identity')
    require(len({loop['src'] for loop in initial.values()}) == len(expected), 'source-duplication')
    require(len({loop['token'] for loop in initial.values()}) == len(expected), 'node-duplication')
    maximum_error = 0.
    for sample in [baseline, *trace['samples'], *checkpoints]:
        require(sample['stageToken'] == baseline['stageToken'], 'stage-replaced')
        loops = sample['loops']
        require(sample['boxCount'] == len(expected) == len(loops), 'loop-count')
        require({loop['id'] for loop in loops} == set(expected), 'loop-identity')
        require(len({loop['src'] for loop in loops}) == len(expected), 'source-duplication')
        elapsed = (sample['wall'] - baseline['wall']) / 1000
        for loop in loops:
            old, model = initial[loop['id']], expected[loop['id']]
            require(loop['token'] == old['token'] and loop['boxToken'] == old['boxToken'], 'node-replaced')
            require(loop['connected'] and loop['boxId'] == loop['id'], 'detached-or-rekeyed')
            require(loop['src'] == old['src'] and loop['attrSrc'] == old['attrSrc'], 'source-changed')
            require(loop['rate'] == float(Fraction(model['rate'])), 'rate-changed')
            require(loop['paused'] == model['held'] and not loop['seeking'], 'playback-state')
            require(loop['readyState'] >= 2, 'no-decoded-data')
            predicted = old['time'] + (0 if model['held'] else elapsed * old['rate'])
            error = abs(loop['time'] - predicted)
            maximum_error = max(maximum_error, error)
            require(error <= CLOCK_TOLERANCE, 'clock-discontinuity')
    for checkpoint in checkpoints:
        stage = checkpoint['stage']
        orientation = 'landscape' if stage['width'] >= stage['height'] else 'portrait'
        cells = {cell['loop']: cell for cell in state['layouts'][orientation]['cells']}
        for loop in checkpoint['loops']:
            cell = cells[loop['id']]
            color = SOURCE_COLORS[expected[loop['id']]['source']]
            require(all(abs(a-b) <= 12 for a,b in zip(loop['pixels']['backgroundRGB'],color)), 'decoded-wrong-source')
            x, y, w, h = map(lambda value: float(Fraction(value)), cell['rect'])
            actual = loop['rect']
            target = {'x':stage['x']+x*stage['width'], 'y':stage['y']+y*stage['height'],
                      'width':w*stage['width'], 'height':h*stage['height']}
            require(all(abs(actual[key]-value) <= GEOMETRY_TOLERANCE for key,value in target.items()), 'layout-geometry')
            require(loop['fit'] == cell['fit'] and loop['display'] != 'none', 'layout-fit')
    for before, after in zip(checkpoints, checkpoints[1:]):
        previous = {loop['id']:loop for loop in before['loops']}
        for loop in after['loops']:
            old = previous[loop['id']]
            if expected[loop['id']]['held']:
                require(abs(loop['time']-old['time']) <= .001, 'hold-lost')
                require(loop['pixels']['hash'] == old['pixels']['hash'], 'held-pixels-changed')
            else:
                require(loop['time'] > old['time'], 'clock-frozen')
                require(loop['decoded']['callbacks'] > old['decoded']['callbacks'], 'decoder-frozen')
                require(loop['decoded']['mediaTime'] > old['decoded']['mediaTime'], 'decoded-time-reset')
                require(loop['pixels']['hash'] != old['pixels']['hash'], 'pixels-frozen')
    return {'loops':len(expected), 'samples':len(trace['samples']), 'checkpoints':len(checkpoints),
            'duration_seconds':(trace['samples'][-1]['wall']-baseline['wall'])/1000,
            'max_clock_error_seconds':maximum_error, 'unexpected_events':len(trace['events']),
            'max_reported_dropped_frames':max(loop['droppedFrames'] for sample in trace['samples'] for loop in sample['loops'])}


class ContinuityTests(unittest.TestCase):
    # Reuse transport and media generation, not the existing test's assertions.
    load_page = existing.BrowserTests.load_page

    @classmethod
    def setUpClass(cls):
        existing.BrowserTests.setUpClass.__func__(cls)
        OUT.mkdir(parents=True, exist_ok=True)
        held = c.load_state(ROOT / 'state-3.json')
        held['loops'][0]['held'] = True
        c.save_state(held, ROOT / 'state-held.json')
        build_preview(ROOT / 'state-held.json', ROOT / 'preview-held')

    @classmethod
    def tearDownClass(cls):
        existing.BrowserTests.tearDownClass.__func__(cls)

    def open(self, name):
        page = self.browser.new_page(viewport={'width':390,'height':844})
        self.addCleanup(page.close)
        self.errors = []
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.add_init_script(path=str(PROBE))
        if self.transport == 'in-memory':
            page.evaluate(PROBE.read_text())
        self.load_page(page, ROOT / f'preview-{name}')
        page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error', timeout=20000)
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        page.evaluate('continuityProbe.prepare()')
        page.locator('#stage').click()  # Exercise the real preview gesture, not a fake clock.
        page.wait_for_function('compositionRuntime.running || compositionRuntime.error')
        page.wait_for_timeout(220)  # Arm after initial native play/seek events have settled.
        page.evaluate('continuityProbe.arm()')
        return page, c.load_state(ROOT / f'state-{name}.json')

    def save(self, name, page, state, checkpoints, expected_failure=None):
        trace = page.evaluate('continuityProbe.finish()')
        record = {'transport':self.transport, 'browser':self.browser.version,
                  'runtime_sha256':hashlib.sha256((HERE/'browser_runtime.js').read_bytes()).hexdigest(),
                  'probe_sha256':hashlib.sha256(PROBE.read_bytes()).hexdigest(),
                  'state_sha256':hashlib.sha256(c.canonical_json(state).encode()).hexdigest(),
                  'trace':trace, 'checkpoints':checkpoints, 'page_errors':self.errors,
                  'expected_failure':expected_failure, 'passed':False}
        try:
            self.assertEqual(self.errors, [])
            if expected_failure:
                with self.assertRaisesRegex(AssertionError, expected_failure):
                    verify_trace(trace, state, checkpoints)
                record['negative_control_rejected'] = True
            else:
                record['metrics'] = verify_trace(trace, state, checkpoints)
            record['passed'] = True
        finally:
            (OUT/f'{name}.json').write_text(json.dumps(record, indent=2)+'\n')
        return record

    def continuity(self, count, *, container=False, held=False):
        page, state = self.open('held' if held else count)
        checkpoints = []
        shapes = [(390,844),(1280,720),(900,1300),(844,390),(700,700),(390,844)]
        if container:
            shapes = [(390,844),(844,390),(450,900),(900,450),(700,700),(390,844)]
            page.set_viewport_size({'width':1600,'height':1000})
        for index, (width,height) in enumerate(shapes):
            if container:
                page.evaluate('([w,h]) => {const s=document.querySelector("#stage");s.style.width=w+"px";s.style.height=h+"px"}', [width,height])
            else:
                page.set_viewport_size({'width':width,'height':height})
            page.wait_for_timeout(250)
            checkpoint = page.evaluate('continuityProbe.checkpoint()')
            self.assertEqual(checkpoint['viewport'], {'width':1600,'height':1000} if container else {'width':width,'height':height})
            checkpoints.append(checkpoint)
            if index in (0,1,5):
                page.screenshot(path=str(OUT/f'{count}-{container}-{held}-{index}.png'))
        # No authored source/hold/wrap boundary is allowed in this oracle window.
        elapsed_frame = page.evaluate('compositionRuntime.frame')
        plan = json.loads((ROOT/f'preview-{"held" if held else count}'/'plan.json').read_text())
        self.assertTrue(all(all(span['frame']>elapsed_frame for span in track['spans'][1:]) for track in plan['tracks']))
        self.save(f'positive-{count}-container-{container}-held-{held}',page,state,checkpoints)

    def test_3(self): self.continuity(3)
    def test_4(self): self.continuity(4)
    def test_5(self): self.continuity(5)
    def test_6(self): self.continuity(6)
    def test_7_experimental(self): self.continuity(7)
    def test_container_only(self): self.continuity(3, container=True)
    def test_held_loop_survives_resize(self): self.continuity(3, held=True)

    def mutation(self, name, script, code='media-or-dom-mutation'):
        page, state = self.open(3)
        checkpoints = [page.evaluate('continuityProbe.checkpoint()')]
        page.set_viewport_size({'width':844,'height':390})
        page.wait_for_timeout(80)
        page.evaluate(script)
        page.wait_for_timeout(300)
        checkpoints.append(page.evaluate('continuityProbe.checkpoint()'))
        self.save(f'negative-{name}',page,state,checkpoints,code)

    def test_reject_wrong_layout(self):
        self.mutation('wrong-layout', 'document.querySelector(".loop").style.left="0%"', 'layout-geometry')

    def test_reject_time_reset(self):
        self.mutation('time-reset', 'document.querySelector("video").currentTime=0')

    def test_reject_same_source_reload(self):
        self.mutation('same-source-reload', 'document.querySelector("video").load()')

    def test_reject_source_reroll(self):
        self.mutation('source-reroll', 'const v=[...document.querySelectorAll("video")];v[0].src=v[1].src')

    def test_reject_transient_duplicate(self):
        self.mutation('transient-duplicate', 'const v=document.querySelector("video"),clone=v.cloneNode(true);v.parentElement.append(clone);clone.remove()')

    def test_reject_transient_removal(self):
        self.mutation('transient-removal', 'const v=document.querySelector("video"),box=v.parentElement;v.remove();box.append(v)')

    def test_reject_same_id_replacement(self):
        self.mutation('same-id-replacement', 'const v=document.querySelector("video");v.replaceWith(v.cloneNode(true))')

    def test_reject_pause(self):
        self.mutation('pause', 'document.querySelector("video").pause()')

    def test_reject_rate_change(self):
        self.mutation('rate-change', 'document.querySelector("video").playbackRate=2')


if __name__ == '__main__':
    unittest.main()
