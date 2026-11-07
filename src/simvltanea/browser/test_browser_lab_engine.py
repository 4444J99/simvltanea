"""Executable transport and real OfflineAudioContext checks for the Effects Lab."""
import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")
ENGINE = HERE / "browser.lab_engine.js"
MODEL = HERE / "browser.lab_model.js"
AUDIO = HERE / "browser.audio.js"


@unittest.skipUnless(NODE, "Node.js is required for engine unit tests")
class LabEngineUnitTests(unittest.TestCase):
    def run_js(self, body):
        script = f"""
const assert = require('node:assert/strict');
const {{Engine, createVoiceGraph}} = require({json.dumps(str(ENGINE))});
const canvas = {{width:640,height:360,getContext:()=>null}};
{body}
"""
        result = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sound_outlives_picture_and_sequence_skips_tail(self):
        self.run_js("""
(async()=>{
 const e = new Engine(canvas);
 const first = await e.addClip({name:'one',kind:'demo',demo:'tide'}, {videoLife:4,audioLife:12,attack:.1});
 const next = await e.addClip({name:'two',kind:'demo',demo:'prism'}, {videoLife:4,audioLife:12,attack:.1});
 e._activate(e.clips[0]); e.playing=true;
 e.setSequence({enabled:true,interval:5});
 e._advance(5);
 const a=e.snapshot().clips[0];
 assert.equal(a.video.active,false); assert.equal(a.audio.active,true);
 assert.equal(e.snapshot().clips[1].active,true);
 e._advance(5);
 assert.equal(e.snapshot().clips[0].age,10, 'active tail must not restart');
 assert.equal(e.snapshot().clips[1].age,5);
 e.dispose();
})();
""")

    def test_tracks_choose_independent_rates_each_repeat(self):
        self.run_js("""
(async()=>{
 const e=new Engine(canvas); await e.addClip({name:'one',kind:'demo',demo:'grain'}, {videoWander:.5,audioWander:.5,videoLife:120,audioLife:120});
 const c=e.clips[0]; e._activate(c);
 const beforeAudio=c.audio.rate;
 const prior=Math.random; Math.random=()=>1;
 e._repeat(c,'video');
 assert.ok(c.video.rate>1); assert.equal(c.audio.rate,beforeAudio);
 Math.random=()=>0; e._repeat(c,'audio');
 assert.ok(c.audio.rate<1); assert.equal(c.video.loops,1); assert.equal(c.audio.loops,1);
 Math.random=prior; e.dispose();
})();
""")

    def test_max_four_and_move_normalize_without_rebuilding(self):
        self.run_js("""
(async()=>{
 const e=new Engine(canvas);
 for(let i=0;i<4;i++)await e.addClip({name:String(i),kind:'demo',demo:'prism'});
 await assert.rejects(()=>e.addClip({name:'five',kind:'demo',demo:'tide'}),/four|4/i);
 const first=e.clips[0]; e.set(first.id,{audioGain:99,combMix:-2});
 assert.equal(first.settings.audioGain,1); assert.equal(first.settings.combMix,0);
 e.move(first.id,1); assert.equal(e.clips[1],first);
 assert.equal(e.snapshot().clips[1].capabilities.preservePitch,false);
 e.dispose();e.dispose();
})();
""")

    def test_pause_freezes_and_remove_disposes_owned_url(self):
        self.run_js("""
(async()=>{
 const revoked=[]; const original=URL.revokeObjectURL; URL.revokeObjectURL=u=>revoked.push(u);
 const e=new Engine(canvas); const id=await e.addClip({name:'one',kind:'demo',demo:'tide',url:'blob:test',ownedURL:true});
 e._activate(e.clips[0]);e.playing=true;e._advance(2);e.pause();
 e._advance(8);assert.equal(e.snapshot().time,2);assert.equal(e.snapshot().clips[0].age,2);
 e.remove(id);assert.deepEqual(revoked,['blob:test']);assert.equal(e.clips.length,0);
 URL.revokeObjectURL=original;e.dispose();
})();
""")

    def test_track_toggles_restore_frozen_clock_but_not_expired_track(self):
        self.run_js("""
(async()=>{
 const e=new Engine(canvas); const id=await e.addClip({kind:'demo'}, {videoLife:4,audioLife:12,attack:.1});
 const c=e.clips[0]; e._activate(c);e.playing=true;e._advance(1);
 e.set(id,{videoEnabled:false});const age=c.video.age,position=c.video.position;
 e._advance(2);e.set(id,{videoEnabled:true});
 assert.equal(c.video.active,true);assert.equal(c.video.age,age);assert.equal(c.video.position,position);
 e._advance(3);assert.equal(c.video.active,false);
 e.set(id,{videoEnabled:false});e.set(id,{videoEnabled:true});assert.equal(c.video.active,false);
 e.set(id,{audioEnabled:false});const audioAge=c.audio.age;
 e.set(id,{audioEnabled:true});assert.equal(c.audio.active,true);assert.equal(c.audio.age,audioAge);
 e.dispose();
})();
""")

    def test_sequence_rotates_fairly_and_keeps_full_queue_launch_pending(self):
        self.run_js("""
(async()=>{
 const e=new Engine(canvas);
 for(let i=0;i<3;i++)await e.addClip({kind:'demo'}, {videoLife:4,audioLife:4,attack:.1});
 e._activate(e.clips[0]);e.playing=true;e.setSequence({enabled:true,interval:5});
 e._advance(5);assert.equal(e.clips[1].active,true,'second clip must get its turn');
 e._advance(5);assert.equal(e.clips[2].active,true,'third clip must get its turn');e.dispose();
 const f=new Engine(canvas);
 for(let i=0;i<3;i++)await f.addClip({kind:'demo'}, {videoLife:24,audioLife:36,attack:.1});
 f._activate(f.clips[0]);f.playing=true;f.setSequence({enabled:true,interval:8});
 f._advance(35);assert.equal(f.clips[0].age,35,'active tail must remain untouched');
 f._advance(2);assert.equal(f.clips[0].age,1,'pending launch must happen at 36, not 40');
 assert.equal(f.clips[0].video.active,true);f.dispose();
})();
""")

    def test_clip_sweep_phase_is_independent_and_stable_when_reordered(self):
        self.run_js("""
(async()=>{
 const e=new Engine(canvas);await e.addClip({kind:'demo'});await e.addClip({kind:'demo'});
 const first=e.clips[0],second=e.clips[1];let applied;
 second.graph={apply:(...args)=>{applied=args[4]},dispose:()=>{}};
 e._updateVoice(second);const before=e.snapshot().clips;
 assert.notEqual(before[0].audio.combHz,before[1].audio.combHz);
 assert.ok(applied>0 && applied<1);
 e.move(second.id,-1);const after=e.snapshot().clips;
 assert.equal(after[0].audio.combHz,before[1].audio.combHz);
 assert.equal(after[1].audio.combHz,before[0].audio.combHz);e.dispose();
})();
""")


class LabEngineSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest('Playwright is required for browser signal tests')
        from simvltanea.browser.test_browser_runtime import browser_executable
        executable = browser_executable()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page=self.browser.new_page()
        self.addCleanup(self.page.close)
        for source in (MODEL,AUDIO,ENGINE):
            self.page.add_script_tag(content=source.read_text())

    def test_comb_notch_follows_frequency_above_render_quantum_limit(self):
        results=self.page.evaluate("""async()=>{
 const results=[];
 for(const spacing of [2400,8000]){
  const ctx=new OfflineAudioContext(1,48000,48000);
  const graph=SimvltaneaLabEngine.createVoiceGraph(ctx,ctx.destination);
  graph.apply({filterMode:'off',combMix:.5,combFeedback:0,combLow:100,combHigh:spacing,combPeriod:8,audioGain:1},1,'entering',4,0);
  const source=ctx.createBufferSource(); const buffer=ctx.createBuffer(1,48000,48000);
  const x=buffer.getChannelData(0); for(let n=0;n<x.length;n++)x[n]=.25*Math.sin(2*Math.PI*(spacing/2)*n/48000);
  source.buffer=buffer;source.connect(graph.input);source.start();const rendered=await ctx.startRendering();
  const y=rendered.getChannelData(0);let energy=0;for(let i=2400;i<y.length;i++)energy+=y[i]*y[i];
  results.push({spacing,rms:Math.sqrt(energy/(y.length-2400)),kind:graph.combType});graph.dispose();
 }
 return results;
}""")
        for result in results:
            self.assertLess(result['rms'], .006, result)
            self.assertEqual(result['kind'],'finite-feed-forward')

    def test_filter_off_is_sample_transparent(self):
        result=self.page.evaluate("""async()=>{
 const ctx=new OfflineAudioContext(1,24000,48000), g=SimvltaneaLabEngine.createVoiceGraph(ctx,ctx.destination);
 g.apply({filterMode:'off',combMix:0,audioGain:1},1,'entering',0,0);
 const s=ctx.createBufferSource(), b=ctx.createBuffer(1,24000,48000),x=b.getChannelData(0);
 for(let n=0;n<x.length;n++)x[n]=.2*Math.sin(2*Math.PI*18000*n/48000);
 s.buffer=b;s.connect(g.input);s.start();const out=(await ctx.startRendering()).getChannelData(0);
 let error=0;for(let n=1000;n<x.length;n++)error=Math.max(error,Math.abs(x[n]-out[n]));
 return {error};
}""")
        self.assertLess(result['error'], 0.00001)

    def test_demo_has_actual_multifrequency_sound_and_pause_resume(self):
        result=self.page.evaluate("""async()=>{
 const e=new SimvltaneaLabEngine.Engine(document.createElement('canvas'));
 await e.addClip({name:'Tide',kind:'demo',demo:'tide'});await e.play();
 const c=e.clips[0],data=c.buffer.getChannelData(0);let energy=0,peak=0;
 for(const x of data){energy+=x*x;peak=Math.max(peak,Math.abs(x));}
 await new Promise(r=>setTimeout(r,140));e.pause();const a=e.snapshot();
 await new Promise(r=>setTimeout(r,60));const b=e.snapshot();
 await e.play();await new Promise(r=>setTimeout(r,80));e.pause();const d=e.snapshot();e.dispose();
 return {rms:Math.sqrt(energy/data.length),peak,a:a.time,b:b.time,d:d.time,pitch:c.capabilities.preservePitch};
}""")
        self.assertGreater(result['rms'], .02)
        self.assertLessEqual(result['peak'], 1)
        self.assertEqual(result['a'],result['b'])
        self.assertGreater(result['d'],result['b'])
        self.assertFalse(result['pitch'])

    def test_default_starter_has_useful_level_through_the_complete_master_graph(self):
        result=self.page.evaluate("""async()=>{
 const e=new SimvltaneaLabEngine.Engine(document.createElement('canvas'));
 await e.addClip({kind:'demo',demo:'tide'});
 const ctx=new OfflineAudioContext(2,48000,48000);e.context=ctx;
 e.master=SimvltaneaLiveAudio.createMasterBus(ctx,{volume:e.volume,enabled:true});
 const c=e.clips[0];e._ensureVoice(c);c.graph.apply(c.settings,1,'entering',2,c.combPhase);
 const source=ctx.createBufferSource();source.buffer=c.buffer;source.connect(c.graph.input);source.start();
 const output=(await ctx.startRendering()).getChannelData(0);
 let energy=0,peak=0;for(let i=4800;i<output.length;i++){energy+=output[i]*output[i];peak=Math.max(peak,Math.abs(output[i]));}
 const result={rms:Math.sqrt(energy/(output.length-4800)),peak,voiceGain:c.headroom.gain.value};
 c.graph.dispose();e.master.dispose();e.context=null;e.master=null;e.dispose();return result;
}""")
        self.assertGreater(result['rms'], .01, result)
        self.assertLess(result['peak'], .25, result)

    def test_css_fallback_filters_the_whole_picture_when_canvas_filters_are_missing(self):
        from PIL import Image
        self.page.set_content('<body style="margin:0"><div style="position:relative;isolation:isolate;width:64px;height:64px">'
                              '<canvas id="stage" width="64" height="64"></canvas></div></body>')
        actual=self.page.evaluate("""async()=>{
 delete CanvasRenderingContext2D.prototype.filter;
 const detached=new SimvltaneaLabEngine.Engine(document.createElement('canvas'));
 await detached.addClip({kind:'demo'});const unsupported=detached.snapshot().clips[0].capabilities.pictureEffects;detached.dispose();
 window.lab=new SimvltaneaLabEngine.Engine(document.querySelector('#stage'));
 window.layerId=await lab.addClip({kind:'demo',demo:'tide'},
   {hold:true,attack:.1,blend:'multiply',opacity:1,brightness:1,contrast:1,saturation:1});
 const c=lab.clips[0];lab._activate(c);c.video.age=1;c.audio.age=1;lab._updateVoice(c);lab._draw();
 return {capabilities:lab.snapshot().capabilities,blend:c.layer.style.mixBlendMode,unsupported};
}""")
        self.assertFalse(actual['capabilities']['canvasFilters'], actual)
        self.assertFalse(actual['unsupported'], actual)
        self.assertTrue(actual['capabilities']['cssPictureFilters'], actual)
        self.assertEqual(actual['blend'], 'normal', actual)
        def pixel():
            return Image.open(io.BytesIO(self.page.screenshot(clip={'x':0,'y':0,'width':64,'height':64}))).convert('RGB').getpixel((32,48))
        full=pixel()
        self.page.evaluate('lab.set(layerId,{opacity:.5})')
        half=pixel()
        for whole,translucent,backdrop in zip(full,half,[6,8,13]):
            self.assertAlmostEqual(translucent,(whole+backdrop)/2,delta=2,msg=str((full,half)))
        self.page.evaluate('lab.set(layerId,{brightness:0,opacity:1})')
        self.assertEqual(pixel(),(0,0,0))
        self.page.evaluate('lab.dispose()')
        self.assertEqual(self.page.locator('canvas').count(),1)

    def test_fully_transparent_picture_does_not_claim_the_base_blend(self):
        result=self.page.evaluate("""async()=>{
 const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
 const e=new SimvltaneaLabEngine.Engine(canvas);
 await e.addClip({kind:'demo',demo:'tide'},{hold:true,attack:.1,opacity:0});
 const top=await e.addClip({kind:'demo',demo:'prism'},{hold:true,attack:.1,opacity:1,blend:'normal'});
 for(const c of e.clips){e._activate(c);c.video.age=1;e._updateVoice(c);}e._draw();
 const pixel=()=>Array.from(canvas.getContext('2d').getImageData(32,32,1,1).data);
 const normal=pixel();e.set(top,{blend:'multiply'});const multiply=pixel();e.dispose();return {normal,multiply};
}""")
        self.assertEqual(result['normal'],result['multiply'],result)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is required for native media fixture generation')
    def test_native_video_and_audio_repeat_independently_and_keep_the_sound_tail(self):
        fixture=subprocess.run([
            shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=size=64x48:rate=12',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '48k',
            '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1'
        ], capture_output=True, check=True)
        result=self.page.evaluate("""async encoded=>{
 const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
 const url=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
 const e=new SimvltaneaLabEngine.Engine(document.createElement('canvas'));
 const prior=Math.random;Math.random=()=>.75;
 try {
  await e.addClip({kind:'video',name:'Native AV',url,ownedURL:true},
    {videoLife:4,audioLife:12,attack:.1,videoRate:2,audioRate:.5,videoWander:.2,audioWander:.3,filterMode:'off',combMix:0});
  await e.addClip({kind:'demo',name:'Next',demo:'prism'},{videoLife:4,audioLife:4,attack:.1});
  e.setSequence({enabled:true,interval:2});await e.play();
  const c=e.clips[0],analyser=e.context.createAnalyser();analyser.fftSize=2048;c.headroom.connect(analyser);
  const silent=e.context.createGain();silent.gain.value=0;analyser.connect(silent);silent.connect(e.context.destination);
  await new Promise(r=>setTimeout(r,1350));
  const early={vloops:c.video.loops,aloops:c.audio.loops,vrate:c.video.rate,arate:c.audio.rate,vpos:c.videoElement.currentTime,apos:c.audioElement.currentTime};
  await new Promise(r=>setTimeout(r,3150));
  const signal=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(signal);
  const tail={...e.snapshot().clips[0],audioPlaying:!c.audioElement.paused,rms:Math.sqrt(signal.reduce((n,x)=>n+x*x,0)/signal.length)};
  e.pause();const paused={time:e.time,video:c.videoElement.currentTime,audio:c.audioElement.currentTime};
  await new Promise(r=>setTimeout(r,120));const frozen={time:e.time,video:c.videoElement.currentTime,audio:c.audioElement.currentTime};
  await e.play();await new Promise(r=>setTimeout(r,150));e.pause();
  const resumed={time:e.time,audio:c.audioElement.currentTime};
  analyser.disconnect();silent.disconnect();return {early,tail,paused,frozen,resumed};
 } finally {Math.random=prior;e.dispose();}
}""",base64.b64encode(fixture.stdout).decode())
        self.assertGreaterEqual(result['early']['vloops'], 1, result)
        self.assertEqual(result['early']['aloops'], 0, result)
        self.assertGreater(result['early']['vrate'], 2, result)
        self.assertEqual(result['early']['arate'], .5, result)
        self.assertFalse(result['tail']['video']['active'], result)
        self.assertTrue(result['tail']['audio']['active'], result)
        self.assertTrue(result['tail']['audioPlaying'], result)
        self.assertGreaterEqual(result['tail']['audio']['loops'], 1, result)
        self.assertGreater(result['tail']['rms'], .001, result)
        self.assertGreater(result['tail']['age'], 4, result)
        self.assertEqual(result['paused'], result['frozen'], result)
        self.assertGreater(result['resumed']['time'], result['paused']['time'], result)
        self.assertGreater(result['resumed']['audio'], result['paused']['audio'], result)


if __name__ == '__main__':
    unittest.main()
