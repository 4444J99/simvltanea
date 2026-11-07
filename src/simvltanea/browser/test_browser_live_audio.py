"""Real-browser sample-peak proofs for the persistent Studio master bus.

These tests render the production JavaScript in OfflineAudioContext. They make
no true-peak, physical-speaker or iPhone claim. Missing browser/audio support is
an error; a mathematical fallback cannot substitute for this proof.
"""
from pathlib import Path
import unittest

from simvltanea.browser.test_browser_runtime import browser_executable


AUDIO_JS = Path(__file__).with_name('browser.audio.js')
CEILING = 10 ** (-1 / 20)


class LiveAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=browser_executable(), headless=True,
            args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.add_script_tag(content=AUDIO_JS.read_text())
        self.assertTrue(self.page.evaluate("typeof OfflineAudioContext === 'function'"))

    def test_coherent_gain_normalization_handles_silence_and_invalid_weights(self):
        result = self.page.evaluate('''() => {
          const normalize = SimvltaneaLiveAudio.normalizeGains;
          return {equal:[...normalize([1,1,1,1])], silence:[...normalize([0,0])],
            invalid:[...normalize([-1,NaN,Infinity,1])], empty:[...normalize([])],
            extreme:[...normalize([1e308,1e308])],
            limited:[...normalize([1,1],0.4)]};
        }''')
        self.assertAlmostEqual(sum(result['equal']), 0.85, places=6)
        self.assertEqual(result['silence'], [0, 0])
        self.assertEqual(result['invalid'][:3], [0, 0, 0])
        self.assertAlmostEqual(result['invalid'][3], 0.85, places=6)
        self.assertEqual(result['empty'], [])
        self.assertAlmostEqual(sum(result['extreme']), 0.85, places=6)
        self.assertAlmostEqual(sum(result['limited']), 0.4, places=6)

    def test_bus_is_persistent_and_disposal_does_not_close_context(self):
        result = self.page.evaluate('''() => {
          const ctx = new OfflineAudioContext(1,48000,48000);
          const first = SimvltaneaLiveAudio.createMasterBus(ctx);
          const second = SimvltaneaLiveAudio.createMasterBus(ctx,{volume:1,enabled:true});
          const initial = first.volume.gain.value;
          first.dispose(); first.dispose();
          const third = SimvltaneaLiveAudio.createMasterBus(ctx,{volume:.5,enabled:true});
          return {same:first===second, initial, different:first!==third,
            contextClosed:ctx.state==='closed', volume:third.volume.gain.value};
        }''')
        self.assertTrue(result['same'])
        self.assertEqual(result['initial'], 0)
        self.assertTrue(result['different'])
        self.assertFalse(result['contextClosed'])
        self.assertEqual(result['volume'], 0.5)

    def test_four_correlated_native_oscillators_obey_sample_ceiling(self):
        result = self.page.evaluate('''async () => {
          const ctx = new OfflineAudioContext(2,24000,48000);
          const bus = SimvltaneaLiveAudio.createMasterBus(ctx,{volume:1,enabled:true});
          for(let i=0;i<4;i++) {
            const osc=ctx.createOscillator(), gain=ctx.createGain();
            osc.frequency.value=440; gain.gain.value=.425;
            osc.connect(gain); gain.connect(bus.input); osc.start(0);
          }
          const rendered=await ctx.startRendering();
          let peak=0;
          for(let c=0;c<rendered.numberOfChannels;c++)
            for(const sample of rendered.getChannelData(c)) peak=Math.max(peak,Math.abs(sample));
          return {peak,dbfs:20*Math.log10(peak)};
        }''')
        self.assertGreater(result['peak'], 0.1)
        self.assertLessEqual(result['peak'], CEILING + 1e-6, result)

    def test_native_impulses_high_frequencies_and_steps_obey_sample_ceiling(self):
        results = self.page.evaluate('''async () => {
          const rows=[];
          for(const rate of [44100,48000]) for(const channels of [1,2])
          for(const stimulus of ['high','impulse','step','square']) {
            const ctx=new OfflineAudioContext(channels,Math.floor(rate/2),rate);
            const bus=SimvltaneaLiveAudio.createMasterBus(ctx,{volume:1,enabled:true});
            const buffer=ctx.createBuffer(channels,Math.floor(rate/2),rate);
            for(let c=0;c<channels;c++) {
              const data=buffer.getChannelData(c);
              for(let i=0;i<data.length;i++) {
                const x=stimulus==='high' ? 1.7*Math.sin(2*Math.PI*11025*i/rate) :
                  stimulus==='impulse' ? (i%1024===128 ? 1.7 : 0) :
                  stimulus==='step' ? (i<128 ? 0 : 1.7) : (i%24<12 ? 1.7 : -1.7);
                data[i]=c ? -x : x;
              }
            }
            const source=ctx.createBufferSource(); source.buffer=buffer;
            source.connect(bus.input); source.start();
            const rendered=await ctx.startRendering(); let peak=0;
            for(let c=0;c<channels;c++) for(const sample of rendered.getChannelData(c))
              peak=Math.max(peak,Math.abs(sample));
            rows.push({rate,channels,stimulus,peak});
          }
          return rows;
        }''')
        self.assertEqual(len(results), 16)
        for result in results:
            with self.subTest(**result):
                self.assertGreater(result['peak'], 0.1)
                self.assertLessEqual(result['peak'], CEILING + 1e-6)

    def test_volume_unlock_mute_and_small_signal_linearity(self):
        results = self.page.evaluate('''async () => {
          const rows=[];
          for(const mode of ['locked','unity','volume','disable','invalid']) {
            const ctx=new OfflineAudioContext(1,24000,48000);
            const enabled=mode!=='locked', volume=mode==='volume' ? .5 : 1;
            const bus=SimvltaneaLiveAudio.createMasterBus(ctx,{volume,enabled});
            if(mode==='disable') bus.setVolume(1,false);
            if(mode==='invalid') bus.setVolume(NaN,true);
            const source=ctx.createConstantSource(); source.offset.value=.1;
            source.connect(bus.input); source.start();
            const rendered=await ctx.startRendering();
            rows.push({mode,sample:rendered.getChannelData(0)[20000]});
          }
          // DynamicsCompressorNode applies its own makeup gain. Check the
          // soft transfer's unity gain independently, then volume ratios in
          // the actual master chain without mistaking compression for a wire.
          const ctx=new OfflineAudioContext(1,24000,48000);
          const source=ctx.createConstantSource(), half=ctx.createGain();
          source.offset.value=.1; half.gain.value=.5;
          const shaper=ctx.createWaveShaper();
          shaper.curve=SimvltaneaLiveAudio.buildSoftClipCurve();
          shaper.oversample='4x';
          source.connect(half); half.connect(shaper); shaper.connect(ctx.destination);
          source.start();
          const rendered=await ctx.startRendering();
          return {...Object.fromEntries(rows.map(row=>[row.mode,row.sample])),
            transferUnity:rendered.getChannelData(0)[20000]};
        }''')
        self.assertEqual(results['locked'], 0)
        self.assertAlmostEqual(results['transferUnity'], .1, places=5)
        self.assertAlmostEqual(results['volume'] / results['unity'], .5, places=5)
        self.assertAlmostEqual(results['disable'], 0, places=6)
        self.assertAlmostEqual(results['invalid'], 0, places=6)


if __name__ == '__main__':
    unittest.main()
