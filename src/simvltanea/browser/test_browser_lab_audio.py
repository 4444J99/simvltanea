"""Rendered signals verify the lab's pass direction and bounded comb tail."""
from pathlib import Path
import unittest

from simvltanea.browser.test_browser_runtime import browser_executable

HERE = Path(__file__).resolve().parent


class EffectsLabAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                            args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        for name in ['browser.compiler.js', 'browser.lab_model.js', 'browser.audio.js', 'browser.lab_engine.js']:
            self.page.add_script_tag(path=str(HERE / name))

    def test_presence_filters_change_the_actual_spectrum_in_both_directions(self):
        outputs = self.page.evaluate('''async () => {
          const outputs = [];
          for (const mode of ['presence', 'presence-reverse']) {
            for (const phase of ['entering', 'leaving']) {
              const context = new OfflineAudioContext(1, 24000, 48000);
              const graph = SimvltaneaLabEngine.createVoiceGraph(context, context.destination);
              graph.apply({filterMode:mode, combMix:0, audioGain:1}, .2, phase, 0, 0);
              const source = context.createBufferSource();
              source.buffer = context.createBuffer(1, 24000, 48000);
              const data = source.buffer.getChannelData(0);
              for (let n=0; n<data.length; n++) {
                data[n] = .2 * (Math.sin(2*Math.PI*100*n/48000) + Math.sin(2*Math.PI*10000*n/48000));
              }
              source.connect(graph.input); source.start();
              const out = (await context.startRendering()).getChannelData(0);
              const amplitude = frequency => {
                let real=0, imaginary=0;
                for (let n=12000; n<out.length; n++) {
                  real += out[n]*Math.cos(2*Math.PI*frequency*n/48000);
                  imaginary += out[n]*Math.sin(2*Math.PI*frequency*n/48000);
                }
                return 2*Math.hypot(real, imaginary)/12000;
              };
              outputs.push({mode, phase, low:amplitude(100), high:amplitude(10000)});
              graph.dispose();
            }
          }
          return outputs;
        }''')
        for result in outputs:
            low_pass = ((result['mode'] == 'presence') == (result['phase'] == 'entering'))
            passed, attenuated = ((result['low'], result['high']) if low_pass
                                  else (result['high'], result['low']))
            self.assertGreater(passed, .03, result)
            self.assertLess(attenuated, passed / 30, result)

    def test_maximum_comb_decay_has_bounded_amplitude_and_a_finite_tail(self):
        result = self.page.evaluate('''async () => {
          const context = new OfflineAudioContext(1, 48000, 48000);
          const graph = SimvltaneaLabEngine.createVoiceGraph(context, context.destination);
          graph.apply({filterMode:'off', combMix:1, combFeedback:.75,
            combLow:40, combHigh:100, audioGain:1}, 1, 'entering', 0, 0);
          const source = context.createBufferSource();
          source.buffer = context.createBuffer(1, 4800, 48000);
          const data = source.buffer.getChannelData(0);
          for (let n=0; n<data.length; n++) data[n] = n % 241 < 120 ? .4 : -.4;
          source.connect(graph.input); source.start();
          const out = (await context.startRendering()).getChannelData(0);
          let peak=0, tail=0, finite=true;
          for (let n=0; n<out.length; n++) {
            finite = finite && Number.isFinite(out[n]);
            peak = Math.max(peak, Math.abs(out[n]));
            if (n>=24000) tail = Math.max(tail, Math.abs(out[n]));
          }
          graph.dispose(); return {peak, tail, finite};
        }''')
        self.assertTrue(result['finite'], result)
        self.assertGreater(result['peak'], .1, result)
        self.assertLessEqual(result['peak'], .40001, result)
        self.assertLess(result['tail'], .00001, result)


if __name__ == '__main__':
    unittest.main()
