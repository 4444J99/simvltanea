"""Opted-in Audio v1.1: verified local assets and native Web Audio signal proof.

The tones are new synthetic engineering fixtures. No historical soundtrack or
physical speaker, mobile-device or sample-exact A/V proof is asserted here.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import struct
import subprocess
import sys
import unittest
import wave
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / 'core', _ROOT / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import composition as c
from browser_runtime import build_preview, compile_plan, HERE
from make_runtime_fixture import ROOT, prepare
import test_browser_runtime as legacy


def prepare_audio():
    """All source media are generated beneath the ignored proof lane."""
    prepare()
    state = c.load_state(ROOT / 'state-3.json')
    state['schema_version'] = '1.1'
    state['engine_version'] = '1.1.0'
    for index, source in enumerate(state['sources']):
        original = ROOT / source['path']
        target = ROOT / 'media' / f'audio-tone-{index}.mp4'
        if not target.exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(original),
                '-f', 'lavfi', '-i', f'sine=frequency={220+index*220}:sample_rate=48000:duration=8',
                '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
                '-t', '8', str(target)], check=True)
        source['path'] = str(target.relative_to(ROOT))
        source['sha256'] = c.sha256_file(target)
    state['audio'] = dict(mode='spatial_loops', master_volume='7/10', spatial_panning=True,
                          per_loop={'loop-1': {'gain': '1/2', 'mute_on_hold': True}})
    state['events'] = [dict(op='hold', frame=24, loop='loop-1', value=True),
                       dict(op='hold', frame=48, loop='loop-1', value=False)]
    c.save_state(state, ROOT / 'state-audio-spatial.json')
    build_preview(ROOT / 'state-audio-spatial.json', ROOT / 'preview-audio-spatial')
    track = ROOT / 'media' / 'audio-master.wav'
    with wave.open(str(track), 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(48000)
        handle.writeframes(b''.join(struct.pack('<h', round(8000*math.sin(2*math.pi*330*i/48000)))
                                   for i in range(96000)))
    state['events'] = []
    state['audio'] = dict(mode='soundtrack', source=str(track.relative_to(ROOT)),
        sha256=c.sha256_file(track), duration='2', volume='4/5', loop=True,
        fade_in_seconds='1/2', fade_out_seconds='1/2')
    c.save_state(state, ROOT / 'state-audio-soundtrack.json')
    build_preview(ROOT / 'state-audio-soundtrack.json', ROOT / 'preview-audio-soundtrack')


class AudioPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): prepare_audio()

    def test_legacy_plan_is_still_silent_v1(self):
        plan = compile_plan(c.load_state(ROOT / 'state-3.json'))
        self.assertEqual((plan['plan_version'], plan['engine_version'], plan['audio']), (1, '1.0.0', 'none'))

    def test_soundtrack_rebased_hashed_and_portable(self):
        target = ROOT / 'preview-audio-soundtrack'
        plan = json.loads((target / 'plan.json').read_text())
        portable = c.load_state(target / 'state.json')
        path = c.soundtrack_path(portable, target)
        self.assertEqual(plan['plan_version'], 2)
        self.assertEqual(plan['audio']['asset']['sha256'], c.sha256_file(path))
        self.assertEqual(plan['audio']['asset']['bytes'], path.stat().st_size)
        self.assertEqual(plan['state_sha256'], hashlib.sha256(c.canonical_json(portable).encode()).hexdigest())
        self.assertEqual(plan['audio']['source'], portable['audio']['source'])

    def test_audio_configuration_does_not_change_visual_spans(self):
        spatial = c.load_state(ROOT / 'state-audio-spatial.json')
        silent = copy.deepcopy(spatial)
        silent['audio'] = {'mode': 'none', 'routing': None, 'generative': None}
        self.assertEqual(compile_plan(spatial)['tracks'], compile_plan(silent)['tracks'])

    def test_bad_soundtrack_hash_rejected_before_preview(self):
        state = c.load_state(ROOT / 'state-audio-soundtrack.json')
        state['audio']['sha256'] = '0'*64
        c.save_state(state, ROOT / 'state-audio-invalid-hash.json')
        with self.assertRaisesRegex(c.StateError, 'hash|SHA|digest'):
            build_preview(ROOT / 'state-audio-invalid-hash.json', ROOT / 'preview-audio-invalid-hash')

    def test_spatial_rejects_unverified_present_audio_codec(self):
        state = c.load_state(ROOT / 'state-audio-spatial.json')
        source = state['sources'][0]
        target = ROOT / 'media' / 'audio-unsupported-alac.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(ROOT / source['path']),
                        '-c:v', 'copy', '-c:a', 'alac', str(target)], check=True)
        source['path'] = str(target.relative_to(ROOT)); source['sha256'] = c.sha256_file(target)
        c.save_state(state, ROOT / 'state-audio-unsupported.json')
        with self.assertRaisesRegex(c.StateError, 'AAC mono/stereo'):
            build_preview(ROOT / 'state-audio-unsupported.json', ROOT / 'preview-audio-unsupported')

    def test_spatial_video_without_audio_is_explicit_silent_contribution(self):
        state = c.load_state(ROOT / 'state-3.json')
        state.update(schema_version='1.1', engine_version='1.1.0', audio={'mode': 'spatial_loops'})
        c.save_state(state, ROOT / 'state-audio-absent.json')
        plan = build_preview(ROOT / 'state-audio-absent.json', ROOT / 'preview-audio-absent')
        self.assertTrue(all(source['audio_stream'] is None for source in plan['sources']))


class NativeAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        legacy.BrowserTests.setUpClass.__func__(cls)
        prepare_audio()

    @classmethod
    def tearDownClass(cls): legacy.BrowserTests.tearDownClass.__func__(cls)

    def load_page(self, page, root):
        if self.transport == 'http':
            page.goto(f'{self.base}/{root.name}/'); return
        plan = json.loads((root / 'plan.json').read_text())
        assets = list(plan['sources'])
        if isinstance(plan['audio'], dict) and plan['audio']['mode'] == 'soundtrack':
            assets.append(plan['audio']['asset'])
        payload = {src['id']: base64.b64encode((root / src['path']).read_bytes()).decode() for src in assets}
        page.expose_function('fixtureDigest', lambda data: hashlib.sha256(bytes(data)).hexdigest())
        page.set_content((root / 'index.html').read_text().replace('<script src="runtime.js" defer></script>', ''))
        page.evaluate('''({plan,payload}) => {window.compositionIO={
          async plan(){return plan;},
          async bytes(source){return Uint8Array.from(atob(payload[source.id]),c=>c.charCodeAt(0)).buffer;},
          async digest(bytes){return fixtureDigest(Array.from(new Uint8Array(bytes)));}};}''',
          dict(plan=plan, payload=payload))
        page.add_script_tag(content=(root / 'runtime.js').read_text())

    open_preview = legacy.BrowserTests.open_preview

    def attach_meters(self, page):
        page.evaluate('''() => {
          const r=compositionRuntime, context=r.audio.context;
          window.meters={};
          function meter(id,gain){
            const stereo=context.createGain();stereo.channelCount=2;stereo.channelCountMode='explicit';
            const split=context.createChannelSplitter(2), a=context.createAnalyser(),b=context.createAnalyser();
            a.fftSize=b.fftSize=1024; gain.connect(stereo);stereo.connect(split);split.connect(a,0);split.connect(b,1);meters[id]=[a,b];
          }
          for(const node of r.nodes.values()) if(node.audio) meter(node.id,node.audio.gain);
          if(r.audio.gain) meter('soundtrack',r.audio.gain);
          window.readLevels=()=>Object.fromEntries(Object.entries(meters).map(([id,items])=>[id,items.map(a=>{
            const data=new Float32Array(a.fftSize);a.getFloatTimeDomainData(data);
            return Math.sqrt(data.reduce((sum,x)=>sum+x*x,0)/data.length);
          })]));
        }''')

    def proof(self, name, page, observations):
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        (ROOT / f'evidence/audio-{name}.json').write_text(json.dumps(dict(
            transport=self.transport, browser=self.browser.version, kind='synthetic-native-WebAudio',
            runtime_sha256=c.sha256_file(HERE / 'browser_runtime.js'), observations=observations,
            events=page.evaluate('compositionRuntime.events')), indent=2)+'\n')

    def test_v1_keeps_silent_native_media_and_no_audio_context(self):
        page = self.open_preview(3)
        page.click('#stage', position={'x': 4, 'y': 4})
        page.wait_for_timeout(250)
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every(n=>n.media.muted)'))
        self.assertEqual(page.evaluate('compositionRuntime.audio.mode'), 'none')
        self.assertIsNone(page.evaluate('compositionRuntime.audio.context'))

    def test_spatial_native_signal_hold_ramp_siblings_and_orientation(self):
        page = self.open_preview('audio-spatial')
        self.assertFalse(page.evaluate('compositionRuntime.audio.enabled'))
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every(n=>n.media.muted)'))
        self.attach_meters(page)
        page.click('#stage', position={'x': 4, 'y': 4})
        page.wait_for_function('compositionRuntime.running')
        page.wait_for_function('compositionRuntime.snapshot().compositionTime>.7')
        before = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertTrue(all(min(value)>.002 for value in before['levels'].values()))
        ramp = page.evaluate('''async()=>{
          const points=[];while(compositionRuntime.snapshot().compositionTime<1.14){
            points.push({time:compositionRuntime.snapshot().compositionTime,
              gain:compositionRuntime.nodes.get('loop-1').audio.gain.gain.value});
            await new Promise(requestAnimationFrame);
          } return points;
        }''')
        self.assertTrue(any(0<p['gain']<.34 for p in ramp if .94<p['time']<1.01), ramp)
        held = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertLess(max(held['levels']['loop-1']), .00001)
        self.assertGreater(min(held['levels']['loop-2']), .002)
        self.assertTrue(held['snapshot']['loops'][0]['paused'])
        event_count = page.evaluate('compositionRuntime.events.length')
        page.evaluate('window.originalAudio=[...compositionRuntime.nodes.values()].map(n=>n.audio)')
        page.set_viewport_size({'width': 844, 'height': 390})
        page.wait_for_timeout(270)
        landscape = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.audio===originalAudio[i]&&n.media===initialMedia[i])'))
        config = json.loads((ROOT / 'preview-audio-spatial/plan.json').read_text())
        cells = config['layout_keyframes'][0]['layouts']['landscape']['cells']
        from fractions import Fraction
        for loop, cell in zip(landscape['snapshot']['loops'], cells):
            x, _, width, _ = map(Fraction, cell['rect'])
            self.assertAlmostEqual(loop['audio']['pan'], float(2*(x+width/2)-1), delta=.001)
        self.assertFalse([event for event in page.evaluate('compositionRuntime.events')[event_count:]
                          if event['type'] in ('source', 'seek-command', 'loadstart')])
        page.wait_for_function('compositionRuntime.snapshot().compositionTime>2.2')
        released = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertGreater(max(released['levels']['loop-1']), .002)
        self.assertFalse(released['snapshot']['loops'][0]['paused'])
        self.proof('spatial-hold-pan', page, [before, {'gain_ramp': ramp}, held, landscape, released])

    def test_soundtrack_native_signal_clock_resize_pause_seek_resume_and_end(self):
        page = self.open_preview('audio-soundtrack')
        self.attach_meters(page)
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every(n=>n.media.muted)'))
        page.click('#stage', position={'x': 4, 'y': 4})
        page.wait_for_function('compositionRuntime.running')
        page.wait_for_timeout(600)
        first = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertGreater(min(first['levels']['soundtrack']), .05)
        page.evaluate('window.originalSoundtrack=compositionRuntime.audio.source')
        before = page.evaluate('compositionRuntime.events.length')
        page.set_viewport_size({'width': 844, 'height': 390}); page.wait_for_timeout(250)
        self.assertTrue(page.evaluate('compositionRuntime.audio.source===originalSoundtrack'))
        self.assertFalse([event for event in page.evaluate('compositionRuntime.events')[before:]
                          if event['type'] in ('soundtrack-start', 'source', 'seek-command', 'loadstart')])
        page.evaluate('compositionRuntime.pause()')
        paused = page.evaluate('compositionRuntime.snapshot()')
        page.wait_for_timeout(150)
        self.assertEqual(paused['compositionTime'], page.evaluate('compositionRuntime.snapshot().compositionTime'))
        self.assertFalse(page.evaluate('compositionRuntime.snapshot().audio.soundtrackPlaying'))
        page.evaluate('compositionRuntime.seek(2.25)')
        page.click('#stage', position={'x': 4, 'y': 4})
        page.wait_for_timeout(250)
        starts = page.evaluate('compositionRuntime.events.filter(e=>e.type==="soundtrack-start")')
        self.assertAlmostEqual(starts[-1]['offset'], .25, delta=.0001)
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every(n=>n.media.muted)'))
        duration = page.evaluate('compositionRuntime.plan.frames/compositionRuntime.plan.fps')
        page.evaluate('compositionRuntime.seek(compositionRuntime.plan.frames/compositionRuntime.plan.fps-.3)')
        page.wait_for_function('compositionRuntime.finished')
        page.wait_for_timeout(100)
        finished = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertLess(max(finished['levels']['soundtrack']), .00001)
        self.assertAlmostEqual(finished['snapshot']['compositionTime'], duration)
        self.assertTrue(all(loop['paused'] for loop in finished['snapshot']['loops']))
        self.proof('soundtrack-transport', page, [first, paused, {'starts': starts}, finished])

    def test_invalid_audio_plan_rejected_before_media_io(self):
        plan = json.loads((ROOT / 'preview-audio-soundtrack/plan.json').read_text())
        plan['audio']['asset']['path'] = '../unverified.wav'
        page = self.browser.new_page(); self.addCleanup(page.close)
        page.set_content('<main id="stage"></main>')
        page.evaluate('''plan=>{window.reads=0;window.compositionIO={async plan(){return plan},
          async bytes(){reads++;throw Error('must not read')},async digest(){throw Error('must not digest')}}}''', plan)
        page.add_script_tag(content=(HERE / 'browser_runtime.js').read_text())
        page.wait_for_function('compositionRuntime.error')
        self.assertEqual(page.evaluate('reads'), 0)
        self.assertEqual(page.locator('.loop').count(), 0)

    def test_native_spatial_audio_rate_extremes_remain_audible(self):
        observations = []
        for rate in ('1/16', '8'):
            with self.subTest(rate=rate):
                state = c.load_state(ROOT / 'state-audio-spatial.json')
                state['events'] = []
                state['loops'][0]['rate'] = rate
                c.save_state(state, ROOT / 'state-audio-rate.json')
                build_preview(ROOT / 'state-audio-rate.json', ROOT / 'preview-audio-rate')
                page = self.open_preview('audio-rate'); self.attach_meters(page)
                page.click('#stage', position={'x': 4, 'y': 4}); page.wait_for_timeout(500)
                observation = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
                observations.append({'rate': rate, **observation})
                self.assertGreater(max(observation['levels']['loop-1']), .001)
                self.assertIsNone(observation['snapshot']['error'])
                page.close()
        (ROOT / 'evidence/audio-rate-extremes.json').write_text(json.dumps(observations, indent=2)+'\n')

    def test_nonloop_end_and_declared_duration_normalization(self):
        state = c.load_state(ROOT / 'state-audio-soundtrack.json')
        state['audio']['duration'] = '51/25'  # 40ms PCM silence padding within one frame tolerance.
        state['audio']['loop'] = False
        c.save_state(state, ROOT / 'state-audio-nonloop.json')
        build_preview(ROOT / 'state-audio-nonloop.json', ROOT / 'preview-audio-nonloop')
        page = self.open_preview('audio-nonloop'); self.attach_meters(page)
        self.assertAlmostEqual(page.evaluate('compositionRuntime.audio.buffer.duration'), 2.04, delta=.00003)
        self.assertTrue(page.evaluate('compositionRuntime.audio.buffer.getChannelData(0).slice(-1000).every(x=>x===0)'))
        page.evaluate('compositionRuntime.seek(1.8)')
        page.click('#stage', position={'x': 4, 'y': 4}); page.wait_for_timeout(500)
        snapshot = page.evaluate('({snapshot:compositionRuntime.snapshot(),levels:readLevels()})')
        self.assertTrue(snapshot['snapshot']['running'])
        self.assertFalse(snapshot['snapshot']['audio']['soundtrackPlaying'])
        self.assertLess(max(snapshot['levels']['soundtrack']), .00001)
        self.proof('nonloop-normalized-duration', page, [snapshot])

    def test_autoplay_denial_is_retryable_and_decode_failure_is_visible(self):
        page = self.open_preview('audio-spatial')
        # Explicit lifecycle fault injection. Signal assertions elsewhere use
        # the real browser source, clock, decoder and AudioContext unmodified.
        result = page.evaluate('''async()=>{
          const context=compositionRuntime.audio.context;
          window.nativeResume=context.resume.bind(context);
          context.resume=()=>Promise.reject(new DOMException('Policy denied audio','NotAllowedError'));
          try{await compositionRuntime.start();}catch(_){}
          context.resume=nativeResume;
          return {snapshot:compositionRuntime.snapshot(),ready:compositionRuntime.ready,
            label:document.querySelector('#runtime-status').textContent};
        }''')
        self.assertTrue(result['ready'])
        self.assertIsNone(result['snapshot']['error'])
        self.assertFalse(result['snapshot']['running'])
        self.assertIn('blocked', result['label'])
        page.click('#stage', position={'x': 4, 'y': 4})
        page.wait_for_function('compositionRuntime.running')
        page.evaluate('[...compositionRuntime.nodes.values()][0].media.dispatchEvent(new Event("error"))')
        page.wait_for_function('compositionRuntime.error')
        self.assertFalse(page.evaluate('compositionRuntime.running'))
        self.assertIn('Media failure', page.locator('#runtime-status').inner_text())
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every(node=>node.media.paused)'))


if __name__ == '__main__': unittest.main()
