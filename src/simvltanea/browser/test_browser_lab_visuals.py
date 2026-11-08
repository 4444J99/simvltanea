"""Rendered pixels establish whole-layer opacity and usable base blend modes."""
from pathlib import Path
import unittest

from simvltanea.browser.test_browser_runtime import browser_executable

HERE = Path(__file__).resolve().parent


class EffectsLabVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                            args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.set_content('<div style="position:relative;isolation:isolate;width:320px;height:180px">'
                              '<canvas id="stage" width="320" height="180"></canvas></div>')
        for name in ['browser.lab_model.js', 'browser.audio.js', 'browser.lab_engine.js']:
            self.page.add_script_tag(path=str(HERE / name))

    def start_layer(self):
        self.page.evaluate('''async () => {
          window.lab = new SimvltaneaLabEngine.Engine(document.querySelector('#stage'));
          window.layerId = await lab.addClip({kind:'demo',name:'Tide',demo:'tide'},
            {hold:true,attack:.1,blend:'normal',opacity:1,brightness:1,contrast:1,saturation:1});
          await lab.launch(layerId);
        }''')
        self.page.wait_for_function('lab.snapshot().clips[0].video.presence === 1')
        self.page.evaluate('lab.pause()')

    def test_opacity_is_applied_once_to_the_complete_layer(self):
        self.start_layer()
        actual = self.page.evaluate('''() => {
          const pixel=()=>Array.from(document.querySelector('#stage').getContext('2d').getImageData(160,170,1,1).data).slice(0,3);
          const full=pixel();lab.set(layerId,{opacity:.5});const half=pixel();lab.set(layerId,{opacity:0});const backdrop=pixel();
          return {full,half,backdrop};
        }''')
        for full, half, backdrop in zip(actual['full'], actual['half'], actual['backdrop']):
            self.assertAlmostEqual(half, (full + backdrop) / 2, delta=2.0, msg=str(actual))

    def test_darkening_modes_do_not_black_out_the_base_picture(self):
        self.start_layer()
        actual = self.page.evaluate('''() => {
          const pixel=()=>Array.from(document.querySelector('#stage').getContext('2d').getImageData(160,170,1,1).data).slice(0,3);
          const normal=pixel();lab.set(layerId,{blend:'multiply'});const multiply=pixel();
          lab.set(layerId,{blend:'darken'});return {normal,multiply,darken:pixel()};
        }''')
        self.assertEqual(actual['normal'], actual['multiply'])
        self.assertEqual(actual['normal'], actual['darken'])


if __name__ == '__main__':
    unittest.main()
