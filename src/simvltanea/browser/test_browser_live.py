"""Behavioral proofs for persistent Studio media, separate from authored playback."""
from __future__ import annotations

import base64
import io
import json
import subprocess
import unittest
from pathlib import Path

from simvltanea.browser.test_browser_runtime import browser_executable
from simvltanea.browser.test_browser_studio import ffmpeg, prepare_fixtures

HERE = Path(__file__).parent
LIVE = HERE / 'browser.live.js'


class MasterSimClockTests(unittest.TestCase):
    def test_live_presence_is_applied_after_mix_gain_and_can_be_bypassed(self):
        # Exercise the real Session methods with tiny host objects; real browser
        # tests below additionally verify rendering and native AudioParam values.
        script = r'''
const {Session} = require(process.argv[1]);
const session=Object.create(Session.prototype);
const supported=typeof session.setPresence==='function' && typeof session.setEffects==='function';
if(!supported) {process.stdout.write(JSON.stringify({supported}));process.exit(0);}
require(process.argv[2]);
const style={filter:'',opacity:'1'}, gain={value:0,setTargetAtTime(v){this.value=v}},
  frequency={value:20000,setTargetAtTime(v){this.value=v}};
const deck={media:{style,muted:false},weight:1,presence:1,binding:{target:0,
  gain:{gain},filter:{type:'lowpass',frequency},cutoff:null}};
const node={id:'one',decks:[deck],active:deck,resting:false,targetGain:.8};
session.nodes=new Map([['one',node]]);session.audio={enabled:true,context:{state:'running',currentTime:0,sampleRate:48000}};
session.sound={enabled:true};session.running=true;session.fade=null;session.options={};
session.setEffects(true);session.setPresence('one',.25);
const quiet={gain:gain.value,filter:style.filter,frequency:frequency.value};
session.setPresence('one',1);const peak={gain:gain.value,filter:style.filter,frequency:frequency.value};
session.setEffects(false);const bypass={gain:gain.value,filter:style.filter,type:deck.binding.filter.type};
process.stdout.write(JSON.stringify({supported,quiet,peak,bypass}));
'''
        result = subprocess.run(['node', '-e', script, str(LIVE), str(HERE / 'browser.presence.js')],
                                check=True, capture_output=True, text=True)
        values = json.loads(result.stdout)
        self.assertTrue(values['supported'], 'live presence controls have not been implemented')
        self.assertAlmostEqual(values['quiet']['gain'], .2, places=6)
        self.assertAlmostEqual(values['peak']['gain'], .8, places=6)
        self.assertLess(values['quiet']['frequency'], values['peak']['frequency'])
        self.assertIn('blur(1.5px)', values['quiet']['filter'])
        self.assertEqual(values['bypass'], dict(gain=.8, filter='', type='allpass'))

    def test_foreground_budget_treats_touch_and_coarse_devices_conservatively(self):
        script = r'''
const api = require(process.argv[1]);
const environments = [
  {navigator:{maxTouchPoints:1}},
  {navigator:{maxTouchPoints:0},matchMedia:q=>({matches:q==='(any-pointer: coarse)'})},
  {navigator:{maxTouchPoints:0,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)'}},
  {navigator:{maxTouchPoints:0,userAgent:'Mozilla/5.0 (X11; Linux x86_64)'},matchMedia:()=>({matches:false})}
];
process.stdout.write(JSON.stringify(api.foregroundLimit ? environments.map(api.foregroundLimit) : []));
'''
        result = subprocess.run(['node', '-e', script, str(LIVE)], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), [4, 4, 4, 12])

    def test_clock_freezes_pause_and_ignores_background_catchup(self):
        self.assertTrue(LIVE.exists(), 'persistent Studio runtime is not implemented')
        script = r'''
const {MasterSimClock} = require(process.argv[1]);
const clock = new MasterSimClock({requestFrame: () => 1, cancelFrame: () => {}});
clock.start(); clock.tick(1000); clock.tick(1030); clock.tick(2030);
const before = clock.simTime; clock.pause(); clock.tick(9999);
const paused = clock.simTime; clock.start(); clock.tick(10000); clock.tick(10020);
process.stdout.write(JSON.stringify({before, paused, after: clock.simTime}));
'''
        result = subprocess.run(['node', '-e', script, str(LIVE)], check=True, capture_output=True, text=True)
        values = json.loads(result.stdout)
        self.assertAlmostEqual(values['before'], .13)
        self.assertEqual(values['paused'], values['before'])
        self.assertAlmostEqual(values['after'], .15)


class PersistentSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.fixtures = prepare_fixtures()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                           args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, has_touch=False, effects=False):
        self.assertTrue(LIVE.exists(), 'persistent Studio runtime is not implemented')
        context = self.browser.new_context(viewport={'width': 800, 'height': 500}, has_touch=has_touch)
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_content('<style>#stage{position:relative;width:800px;height:500px}.loop{position:absolute;overflow:hidden}</style><main id="stage"></main>')
        if effects:
            page.add_script_tag(path=str(HERE / 'browser.presence.js'))
        page.add_script_tag(path=str(LIVE))
        page.evaluate('enabled => {window.presenceEffects=enabled}', effects)
        payload = [base64.b64encode(self.fixtures[f'loop-{i}.mp4'].read_bytes()).decode() for i in range(1, 5)]
        page.evaluate(r'''payload => {
          window.items = payload.map((encoded, i) => ({name:`clip-${i}`, sha256:String(i+1).padStart(64,'0'),
            file:new Blob([Uint8Array.from(atob(encoded), c=>c.charCodeAt(0))], {type:'video/mp4'}), type:'video/mp4'}));
          window.planFor = indices => {
            const cells = indices.map((_,i)=>({loop:`loop-${i+1}`,rect:[`${i}/${indices.length}`,'0',`1/${indices.length}`,'1'],fit:'cover',focal:['1/2','1/2']}));
            return {plan_version:1,frames:2880,fps:24,sources:indices.map((i,j)=>({id:`source-${j+1}`,sha256:items[i].sha256})),
              tracks:indices.map((_,i)=>({id:`loop-${i+1}`,spans:[{source:`source-${i+1}`}]})),
              layout_keyframes:[{layouts:{portrait:{cells},landscape:{cells}}}]};
          };
          window.live = new SimvltaneaLive.Session(document.querySelector('#stage'),{crossfadeSec:.1,primeTimeoutMs:1200,effects:presenceEffects});
          window.setClips = indices => live.reconcile({plan:planFor(indices),items:indices.map(i=>items[i]),playing:true});
        }''', payload)
        page.evaluate('setClips([0,1])')
        return page

    def test_presence_modulates_native_audio_without_recreating_media(self):
        page = self.open(effects=True)
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('''() => {window.original=live.nodes.get('loop-1').media;
          live.setTargetGain('loop-1',.8);live.setTargetGain('loop-2',0);
          live.setPresence('loop-1',1);window.meter=live.audio.context.createAnalyser();meter.fftSize=2048;
          live.audio.input.connect(meter);window.rms=()=>{const data=new Float32Array(meter.fftSize);
            meter.getFloatTimeDomainData(data);return Math.sqrt(data.reduce((s,x)=>s+x*x,0)/data.length)};}''')
        page.wait_for_function('rms()>.02')
        before = page.evaluate('rms()')
        page.evaluate("live.setPresence('loop-1',.25)")
        page.wait_for_function("Math.abs(live.nodes.get('loop-1').audio.gain.gain.value-.2)<.001")
        page.wait_for_function('rms()<.015')
        self.assertLess(page.evaluate('rms()'), before * .4)
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').media===original && !original.paused"))
        self.assertIn('blur(1.5px)', page.evaluate('original.style.filter'))
        page.evaluate('live.setEffects(false)')
        page.wait_for_function("Math.abs(live.nodes.get('loop-1').audio.gain.gain.value-.8)<.001")
        self.assertEqual(page.evaluate('original.style.filter'), '')
        self.assertEqual(page.evaluate("live.nodes.get('loop-1').audio.filter.type"), 'allpass')

    def test_successor_has_its_own_rising_filter_and_reveal_clock(self):
        page = self.open(effects=True)
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate("() => {live.setPresence('loop-1',.12);live.crossfadeSec=1.2;window.change=setClips([2,1]);}")
        page.wait_for_function('Boolean(live.fade)')
        values = page.evaluate('''() => {
          live.clock.pause();const fade=live.fade;window.revealTime=fade.began;
          live.tick(fade.began+.6);
          return {old:fade.outgoing.presence,fresh:fade.incoming.presence,
            oldCutoff:fade.outgoing.binding.cutoff,newCutoff:fade.incoming.binding.cutoff,
            oldAlpha:fade.outgoing.media.style.opacity,newAlpha:fade.incoming.media.style.opacity,
            ready:fade.incoming.media.readyState};
        }''')
        self.assertAlmostEqual(values['old'], .12)
        self.assertAlmostEqual(values['fresh'], .5)
        self.assertGreater(values['newCutoff'], values['oldCutoff'])
        self.assertEqual(values['oldAlpha'], '1')
        self.assertAlmostEqual(float(values['newAlpha']), .5)
        self.assertGreaterEqual(values['ready'], 2)
        page.evaluate('live.tick(revealTime+1.3)')
        page.evaluate('change')
        self.assertEqual(page.evaluate("live.nodes.get('loop-1').birthTime"), page.evaluate('revealTime'))
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').decks.every(d=>d.url || (d.enteredAt===null && d.media.style.filter===''))"))

    def test_picture_brightens_at_presence_peak_and_pause_freezes_filters(self):
        from PIL import Image
        page = self.open(effects=True)
        white = self.fixtures['loop-1.mp4'].parent / 'live-presence-white.mp4'
        if not white.exists():
            ffmpeg('-f', 'lavfi', '-i', 'color=c=white:size=64x64:rate=30', '-t', '2',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(white))
        page.evaluate('''encoded => {items[2]={...items[2],file:new Blob([
          Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))],{type:'video/mp4'})};}''',
                      base64.b64encode(white.read_bytes()).decode())
        page.evaluate('setClips([2,1])')
        page.evaluate("live.setPresence('loop-1',.2)")
        dim = Image.open(io.BytesIO(page.screenshot())).getpixel((100, 100))[:3]
        page.evaluate("live.setPresence('loop-1',1)")
        peak = Image.open(io.BytesIO(page.screenshot())).getpixel((100, 100))[:3]
        self.assertLess(max(dim), 185)
        self.assertGreater(min(dim), 130)
        self.assertGreaterEqual(min(peak), 248)
        page.evaluate('live.pause()')
        before = page.evaluate("({time:live.clock.simTime,filter:live.nodes.get('loop-1').media.style.filter})")
        page.wait_for_timeout(200)
        self.assertEqual(page.evaluate("({time:live.clock.simTime,filter:live.nodes.get('loop-1').media.style.filter})"), before)

    def test_replacement_and_sound_preserve_sibling_media_and_clock(self):
        page = self.open()
        page.evaluate('''() => { window.sibling=live.nodes.get('loop-2').media; window.originalBox=live.nodes.get('loop-2').box;
          window.clockBefore=live.clock.simTime; window.calls=[];
          for(const name of ['play','pause','load']) { const native=sibling[name].bind(sibling); sibling[name]=(...args)=>{calls.push(name);return native(...args)}; }
        }''')
        page.evaluate('setClips([2,1])')
        result = page.evaluate('''() => ({same:live.nodes.get('loop-2').media===sibling,box:live.nodes.get('loop-2').box===originalBox,
          calls,advancing:live.clock.simTime>clockBefore,loop:sibling.loop,peak:live.snapshot().maxConcurrentStandbys,
          slots:document.querySelectorAll('#stage .loop').length,videos:document.querySelectorAll('#stage video').length})''')
        self.assertEqual(result, dict(same=True, box=True, calls=[], advancing=True, loop=True, peak=1, slots=2, videos=4))
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock()},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('live.setSound({enabled:true,volume:.5})')
        page.evaluate('live.setSound({enabled:false,volume:.5})')
        self.assertTrue(page.evaluate("live.nodes.get('loop-2').media===sibling"))
        self.assertEqual(page.evaluate('calls'), [])
        self.assertEqual(page.evaluate('live.audio.context.state'), 'running')

    def test_touch_session_refuses_overbudget_reconcile_before_mutating_residents(self):
        page = self.open(has_touch=True)
        page.evaluate('setClips([0,1,2,3])')
        page.evaluate('window.previous=[...live.nodes.values()].map(node=>node.media)')
        result = page.evaluate('''async () => {
          try {await setClips(Array.from({length:12},(_,i)=>i%4));return 'accepted';}
          catch(error) {return 'rejected';}
        }''')
        self.assertEqual(result, 'rejected')
        self.assertTrue(page.evaluate('[...live.nodes.values()].every((node,i)=>node.media===previous[i] && !node.media.paused)'))
        self.assertEqual(page.evaluate('live.nodes.size'), 4)
        # Different slot IDs must not temporarily retain four old and four new foregrounds.
        result = page.evaluate('''async () => {
          const plan=planFor([0,1,2,3]);
          plan.tracks.forEach((track,i)=>track.id=`new-${i}`);
          for(const layout of Object.values(plan.layout_keyframes[0].layouts))
            layout.cells.forEach((cell,i)=>cell.loop=`new-${i}`);
          try {await live.reconcile({plan,items,playing:true});return 'accepted';}
          catch(error) {return 'rejected';}
        }''')
        self.assertEqual(result, 'rejected')
        self.assertTrue(page.evaluate('[...live.nodes.values()].every((node,i)=>node.media===previous[i])'))

    def test_bad_replacement_keeps_outgoing_moving_and_releases_budget(self):
        page = self.open()
        page.evaluate('''() => { window.outgoing=live.nodes.get('loop-1').media;
          items[2]={...items[2],file:new Blob(['not video'],{type:'video/mp4'})}; }''')
        page.evaluate('setClips([2,1])')
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').media===outgoing && !outgoing.paused"))
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)
        page.evaluate('setClips([3,1])')
        self.assertFalse(page.evaluate("live.nodes.get('loop-1').media===outgoing"))

    def test_coalescing_rotation_and_pause_leave_no_stranded_transition(self):
        page = self.open()
        page.evaluate('''async () => { window.requests=[setClips([2,1]),setClips([3,1]),setClips([0,1])];
          await Promise.all(requests); }''')
        self.assertEqual(page.evaluate("live.nodes.get('loop-1').item.name"), 'clip-0')
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)
        self.assertLessEqual(page.evaluate('live.snapshot().maxConcurrentStandbys'), 1)
        page.evaluate('''() => {window.media=live.nodes.get('loop-2').media;live.setOrientation('portrait');live.pause();}''')
        self.assertTrue(page.evaluate("live.nodes.get('loop-2').media===media && media.paused"))
        before = page.evaluate('live.clock.simTime')
        page.wait_for_timeout(150)
        self.assertEqual(page.evaluate('live.clock.simTime'), before)
        page.evaluate('live.play()')
        self.assertFalse(page.evaluate('media.paused'))

    def test_pause_during_fade_settles_permit_and_reuses_retired_slot(self):
        page = self.open()
        page.evaluate("() => {window.retired=live.nodes.get('loop-2');live.crossfadeSec=2;window.change=setClips([2,1]);}")
        page.wait_for_function("live.nodes.get('loop-1').phase==='CROSSFADING'")
        page.evaluate('live.pause()')
        self.assertTrue(page.evaluate('change'))
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').media.paused"))
        page.evaluate('setClips([2])')
        page.evaluate('setClips([2,1])')
        self.assertTrue(page.evaluate("live.nodes.get('loop-2')===retired"))
        self.assertEqual(page.evaluate("document.querySelectorAll('#stage video').length"), 4)

    def test_admission_and_transition_share_single_preparation_permit(self):
        page = self.open()
        page.evaluate('''() => {
          window.probeEntered=false;window.probeRelease=null;
          window.probe=live.withPreparation(()=>new Promise(resolve=>{probeEntered=true;probeRelease=resolve}));
        }''')
        page.wait_for_function('probeEntered')
        page.evaluate('() => {window.replacement=setClips([2,1]);}')
        page.wait_for_timeout(50)
        self.assertEqual(page.evaluate("live.nodes.get('loop-1').item.name"), 'clip-0')
        self.assertFalse(page.evaluate("live.nodes.get('loop-1').busy"))
        page.evaluate('probeRelease();Promise.all([probe,replacement])')
        self.assertEqual(page.evaluate('live.snapshot().maxConcurrentStandbys'), 1)
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)

    def test_native_wraps_keep_presenting_new_decoded_frames(self):
        page = self.open()
        page.evaluate('''() => { window.loopMedia=live.nodes.get('loop-1').media;window.framesBefore=live.nodes.get('loop-1').callbacks;
          window.seeks=0;const original=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'currentTime');
          Object.defineProperty(loopMedia,'currentTime',{get(){return original.get.call(this)},set(value){seeks++;original.set.call(this,value)}});
        }''')
        page.wait_for_function("live.nodes.get('loop-1').callbacks > framesBefore+80", timeout=8000)
        self.assertEqual(page.evaluate('seeks'), 0)
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').media===loopMedia && loopMedia.loop && !loopMedia.paused"))

    def test_first_audio_unlock_during_fade_binds_both_decks_to_master(self):
        page = self.open()
        page.evaluate("() => {live.crossfadeSec=1;window.change=setClips([2,1]);}")
        page.wait_for_function('Boolean(live.fade)')
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.1});},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('Promise.all([change,unlocked])')
        self.assertTrue(page.evaluate("Boolean(live.nodes.get('loop-1').audio)"), 'incoming audio bypasses the master bus')
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').decks.every(d=>!d.url || d.binding)"))

    def test_retired_resting_slot_returns_fully_visible(self):
        page = self.open()
        page.evaluate("live.setResting('loop-2',true);live.setTargetGain('loop-2',0)")
        page.evaluate('setClips([0])')
        page.evaluate('setClips([0,1])')
        self.assertEqual(page.evaluate("live.nodes.get('loop-2').box.style.opacity"), '1')
        self.assertIsNone(page.evaluate("live.nodes.get('loop-2').targetGain"))

    def test_audio_observer_failure_does_not_black_out_committed_resident(self):
        page = self.open()
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock()},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate("() => {live.options.onAudioNode=()=>{throw Error('observer failed')};}")
        page.evaluate('setClips([2,1])')
        self.assertTrue(page.evaluate("Boolean(live.nodes.get('loop-1').active.url)"))
        self.assertFalse(page.evaluate("live.nodes.get('loop-1').media.paused"))

    def test_spectral_ducking_attenuates_actual_media_audio(self):
        page = self.open()
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        self.assertTrue(page.evaluate("[...live.nodes.values()].every(node=>Boolean(node.audio.filter))"), 'resident filter is missing')
        page.evaluate('''() => {window.meter=live.audio.context.createAnalyser();meter.fftSize=2048;
          live.audio.input.connect(meter);window.rms=()=>{const data=new Float32Array(meter.fftSize);meter.getFloatTimeDomainData(data);
            return Math.sqrt(data.reduce((sum,x)=>sum+x*x,0)/data.length)};}''')
        page.wait_for_function('rms()>.005')
        before = page.evaluate('rms()')
        # Isolate the native filter response from the live effect writer while
        # keeping the source media and AudioContext playing.
        page.evaluate("live.clock.pause();[...live.nodes.values()].forEach(node=>{node.audio.filter.type='lowpass';node.audio.filter.frequency.value=30})")
        page.wait_for_timeout(350)
        self.assertLess(page.evaluate('rms()'), before * .2)

    def test_crossfade_preserves_opaque_white_without_midpoint_darkening(self):
        from PIL import Image
        page = self.open()
        white = self.fixtures['loop-1.mp4'].parent / 'live-white.mp4'
        if not white.exists():
            ffmpeg('-f', 'lavfi', '-i', 'color=c=white:size=64x64:rate=30', '-t', '2',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(white))
        encoded = base64.b64encode(white.read_bytes()).decode()
        page.evaluate('''encoded => {const file=new Blob([Uint8Array.from(atob(encoded), c=>c.charCodeAt(0))],{type:'video/mp4'});
          items[2]={...items[2],file};items[3]={...items[3],file};live.stage.style.background='#000';}''', encoded)
        page.evaluate('setClips([2,1])')
        page.evaluate('() => {live.crossfadeSec=1;window.change=setClips([3,1]);}')
        page.wait_for_function('live.fade && live.clock.simTime-live.fade.began>.4 && live.clock.simTime-live.fade.began<.6')
        image = Image.open(io.BytesIO(page.screenshot()))
        self.assertGreaterEqual(min(image.getpixel((100, 100))[:3]), 248, 'crossfade shows the black stage through both decks')
        page.evaluate('change')

    def test_automatic_replacement_waits_for_outgoing_native_loop_boundary(self):
        page = self.open()
        page.wait_for_function("live.nodes.get('loop-1').media.currentTime>.3 && live.nodes.get('loop-1').media.currentTime<.5")
        page.evaluate('''() => {live.crossfadeSec=.4;window.outgoing=live.nodes.get('loop-1').media;
          window.change=live.reconcile({plan:planFor([2,1]),items:[items[2],items[1]],playing:true,atLoopBoundary:true});}''')
        page.wait_for_timeout(200)
        self.assertFalse(page.evaluate('Boolean(live.fade)'), 'automatic replacement ignored the loop seam')
        page.wait_for_function('Boolean(live.fade)', timeout=4000)
        self.assertLess(page.evaluate('outgoing.currentTime'), .2)
        page.evaluate('change')
        age = page.evaluate("live.clock.simTime-live.nodes.get('loop-1').birthTime")
        self.assertGreaterEqual(age, .4)
        self.assertLess(age, .65, 'priming time leaked into the new resident lifetime')

    def test_territory_changes_framing_without_restarting_residents(self):
        page = self.open()
        self.assertTrue(page.evaluate("typeof live.applyTerritory==='function'"), 'live territory geometry is missing')
        page.evaluate("() => {window.resident=live.nodes.get('loop-1').media;live.applyTerritory([.7,.3]);}")
        self.assertAlmostEqual(page.evaluate("live.nodes.get('loop-1').box.getBoundingClientRect().width"), 560, delta=1)
        self.assertAlmostEqual(page.evaluate("live.nodes.get('loop-2').box.getBoundingClientRect().width"), 240, delta=1)
        self.assertTrue(page.evaluate("resident===live.nodes.get('loop-1').media && !resident.paused"))

    def test_territory_preserves_reversed_strip_order(self):
        page = self.open()
        page.evaluate('''async () => {const plan=planFor([0,1]);
          for(const layout of Object.values(plan.layout_keyframes[0].layouts)) {
            layout.cells[0].rect[0]='1/2';layout.cells[1].rect[0]='0';
          }
          await live.reconcile({plan,items:[items[0],items[1]],playing:true});
          live.applyTerritory([.7,.3]);}''')
        self.assertGreater(page.evaluate("live.nodes.get('loop-1').box.getBoundingClientRect().left"),
                           page.evaluate("live.nodes.get('loop-2').box.getBoundingClientRect().left"))

    def test_promoted_deck_requests_play_after_its_primed_frame(self):
        page = self.open()
        page.evaluate('''() => {
          const node=live.nodes.get('loop-1'), next=node.decks.find(d=>d!==node.active).media;
          window.promotionCalls=[];const play=HTMLMediaElement.prototype.play;
          next.play=function(){promotionCalls.push(this.dataset.deck);const promise=play.call(this);
            if(promotionCalls.length===1) this.requestVideoFrameCallback(()=>HTMLMediaElement.prototype.pause.call(this));
            return promise;};
          window.siblingCalls=[];const sibling=live.nodes.get('loop-2').media;
          for(const name of ['play','pause','load']) {const native=sibling[name].bind(sibling);
            sibling[name]=(...args)=>{siblingCalls.push(name);return native(...args)};}
        }''')
        page.evaluate('setClips([2,1])')
        self.assertFalse(page.evaluate("live.nodes.get('loop-1').media.paused"), 'primed frame never resumed after promotion')
        self.assertEqual(page.evaluate('promotionCalls'), ['standby', 'active'])
        self.assertEqual(page.evaluate('siblingCalls'), [])
        page.evaluate("window.presented=live.nodes.get('loop-1').callbacks")
        page.wait_for_function("live.nodes.get('loop-1').callbacks>presented+5")

    def test_rejected_post_promotion_play_restores_outgoing_resident(self):
        page = self.open()
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.2})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('''() => {
          const node=live.nodes.get('loop-1');window.previous={active:node.active,media:node.media,item:node.item,
            source:node.source,audio:node.audio,birthTime:node.birthTime,url:node.active.url};
          const incoming=node.decks.find(d=>d!==node.active).media, play=incoming.play.bind(incoming);
          incoming.play=()=>incoming.dataset.deck==='active' ? Promise.reject(new DOMException('Promotion refused','NotAllowedError')) : play();
        }''')
        self.assertFalse(page.evaluate('setClips([2,1])'))
        restored = page.evaluate('''() => {const node=live.nodes.get('loop-1');return {
          identity:['active','media','item','source','audio','birthTime'].every(key=>node[key]===previous[key]),
          url:node.active.url===previous.url,moving:!node.media.paused,audible:!node.media.muted,phase:node.phase,
          incomingEmpty:node.decks.filter(d=>d!==node.active).every(d=>d.url===null),
          preparing:live.snapshot().activeStandbys};}''')
        self.assertEqual(restored, dict(identity=True, url=True, moving=True, audible=True, phase='ACTIVE', incomingEmpty=True, preparing=0))

    def test_delayed_promotion_rejection_never_replaces_ecological_residency(self):
        page = self.open(effects=True)
        page.add_script_tag(path=str(HERE / 'browser.ecosystem.js'))
        page.evaluate('''() => {
          window.ecology=new SimvltaneaEcosystem.Engine({seed:1});window.observed=[];
          const sample=time=>{
            const n=live.nodes.get('loop-1');if(!n.item)return;
            ecology.step(time,.016,[{id:n.id,clipKey:n.item.sha256,duration:2,age:time-n.birthTime,
              energy:.5,hasAudio:true}],{enabled:false});
            observed.push(n.item.sha256);
          };
          sample(live.clock.simTime);live.clock.subscribe(sample);
          window.before=ecology.snapshot().residents[0];
          const n=live.nodes.get('loop-1'),incoming=n.decks.find(d=>d!==n.active).media;
          const play=incoming.play.bind(incoming);
          incoming.play=()=>incoming.dataset.deck==='active' ? new Promise((resolve,reject)=>
            setTimeout(()=>reject(new DOMException('Late refusal','NotAllowedError')),150)) : play();
        }''')
        self.assertFalse(page.evaluate('setClips([2,1])'))
        page.wait_for_timeout(40)
        result = page.evaluate('''() => ({sameKeys:observed.every(key=>key===before.clipKey),
          before,after:ecology.snapshot().residents[0],preparing:live.activeStandbys})''')
        self.assertTrue(result['sameKeys'], 'uncommitted replacement escaped into ecological state')
        self.assertEqual(result['after']['deadlineAge'], result['before']['deadlineAge'])
        self.assertAlmostEqual(result['after']['born'], result['before']['born'])
        self.assertEqual(result['preparing'], 0)

    def test_pending_instant_promotion_does_not_double_the_slot_gain(self):
        page = self.open()
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('''() => {
          live.crossfadeSec=0;live.setTargetGain('loop-1',.4);
          const n=live.nodes.get('loop-1'),incoming=n.decks.find(d=>d!==n.active).media;
          const play=incoming.play.bind(incoming);
          incoming.play=()=>incoming.dataset.deck==='active' ? new Promise(resolve=>{
            const native=play();window.releasePromotion=()=>native.then(resolve);
          }) : play();
          window.change=setClips([2,1]);
        }''')
        page.wait_for_function('Boolean(window.releasePromotion)')
        target = page.evaluate("live.nodes.get('loop-1').decks.reduce((sum,d)=>sum+(d.binding?.target||0),0)")
        self.assertAlmostEqual(target, .4)
        self.assertEqual(page.evaluate("live.nodes.get('loop-1').item.sha256"), '1'.zfill(64))
        page.evaluate('releasePromotion();change')
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)

    def test_reused_deck_enters_with_closed_native_filter(self):
        page = self.open(effects=True)
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('setClips([2,1])')
        page.evaluate('''() => {
          const n=live.nodes.get('loop-1'),standby=n.decks.find(d=>d!==n.active);
          standby.binding.filter.frequency.setValueAtTime(16000,live.audio.context.currentTime);
          live.crossfadeSec=1.2;window.change=setClips([3,1]);
        }''')
        page.wait_for_function('Boolean(live.fade)')
        cutoff = page.evaluate('live.fade.incoming.binding.filter.frequency.value')
        self.assertLess(cutoff, 1000, 'new entrance inherited the preceding clip cutoff')
        page.evaluate('change')

    def test_superseding_pending_post_promotion_play_releases_preparation(self):
        page = self.open()
        page.evaluate('''() => {
          const node=live.nodes.get('loop-1');window.original=node.media;
          const incoming=node.decks.find(d=>d!==node.active).media, play=incoming.play.bind(incoming);
          incoming.play=()=>{if(incoming.dataset.deck==='active') {window.promotionPending=true;return new Promise(()=>{});}return play();};
          window.change=setClips([2,1]);
        }''')
        page.wait_for_function('window.promotionPending===true', timeout=3000)
        page.evaluate('setClips([0,1])')
        self.assertFalse(page.evaluate('change'))
        self.assertTrue(page.evaluate("live.nodes.get('loop-1').media===original && !original.paused"))
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)


if __name__ == '__main__':
    unittest.main()
