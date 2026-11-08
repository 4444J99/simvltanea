"""Rendered pixels establish whole-layer opacity and usable base blend modes."""
from pathlib import Path
import io
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
        for name in ['browser.compiler.js', 'browser.lab_model.js', 'browser.audio.js', 'browser.lab_engine.js']:
            self.page.add_script_tag(path=str(HERE / name))

    def start_layer(self):
        self.page.evaluate('''async () => {
          window.lab = new SimvltaneaLabEngine.Engine(document.querySelector('#stage'));
          lab.setLayout({count:1});
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

    def test_separate_panels_keep_their_own_base_blend_and_dormant_assignment(self):
        actual = self.page.evaluate('''async () => {
          const canvas=document.querySelector('#stage'),lab=new SimvltaneaLabEngine.Engine(canvas);
          lab.setLayout({count:2});lab._picture=(ctx,c,w,h)=>{ctx.fillStyle=c.source.color;ctx.fillRect(0,0,w,h);};
          const add=async(color,panel,blend)=>{const id=await lab.addClip({kind:'demo',color},{panel,blend,opacity:1,brightness:1,contrast:1,saturation:1,hold:true,attack:.01});
            const c=lab.clips.find(c=>c.id===id);lab._activate(c);c.video.age=c.audio.age=1;lab._updateVoice(c);lab._draw();return id;};
          const pixel=x=>Array.from(canvas.getContext('2d').getImageData(x,90,1,1).data).slice(0,3);
          const red=await add('#ff0000',1,'multiply'),green=await add('#00ff00',2,'multiply');
          const separate=[pixel(80),pixel(240)];lab.move(green,-1);const reordered=[pixel(80),pixel(240)];
          await add('#0000ff',1,'screen');const blended=[pixel(80),pixel(240)];
          lab.setLayout({count:1});const parked=lab.snapshot().clips.find(c=>c.id===green);
          lab.setLayout({count:2});const restored=[pixel(80),pixel(240)];lab.dispose();
          return {separate,reordered,blended,parked,restored};
        }''')
        self.assertEqual(actual['separate'], [[255,0,0],[0,255,0]],actual)
        self.assertEqual(actual['reordered'], actual['separate'],actual)
        self.assertEqual(actual['blended'], [[255,0,255],[0,255,0]],actual)
        self.assertEqual(actual['parked']['settings']['panel'],2,actual)
        self.assertTrue(actual['parked']['video']['active'],actual)
        self.assertTrue(actual['parked']['audio']['active'],actual)
        self.assertEqual(actual['restored'],actual['blended'],actual)

    def test_filtered_picture_cannot_bleed_outside_its_panel(self):
        actual=self.page.evaluate('''async()=>{
          const canvas=document.querySelector('#stage'),lab=new SimvltaneaLabEngine.Engine(canvas);
          lab.setLayout({count:2});lab._picture=(ctx,c,w,h)=>{ctx.fillStyle='#ff0000';ctx.fillRect(0,0,w,h);};
          await lab.addClip({kind:'demo'},{panel:2,opacity:1,brightness:1,contrast:1,saturation:1,blur:12,hold:true,attack:.01});
          const c=lab.clips[0];lab._activate(c);c.video.age=1;lab._updateVoice(c);lab._draw();
          const pixel=x=>Array.from(canvas.getContext('2d').getImageData(x,90,1,1).data).slice(0,3);
          const result={outside:pixel(159),edge:pixel(160),inside:pixel(240)};lab.dispose();return result;
        }''')
        self.assertEqual(actual['outside'],[6,8,13],actual)
        self.assertGreater(actual['inside'][0],240,actual)
        self.assertLess(actual['edge'][0],actual['inside'][0]-20,actual)

    def test_fill_fit_and_original_slice_render_different_framing(self):
        actual=self.page.evaluate('''async()=>{
          const canvas=document.querySelector('#stage'),lab=new SimvltaneaLabEngine.Engine(canvas);
          lab.setLayout({count:2});lab._demoPicture=(ctx,c,w,h)=>{ctx.fillStyle='#ff0000';ctx.fillRect(0,0,w,h);ctx.fillStyle='#0000ff';ctx.fillRect(w*.45,0,w*.1,h);};
          await lab.addClip({kind:'demo'},{panel:1,opacity:1,brightness:1,contrast:1,saturation:1,hold:true,attack:.01});
          const c=lab.clips[0];lab._activate(c);c.video.age=1;lab._updateVoice(c);lab._draw();
          const pixel=(x,y)=>Array.from(canvas.getContext('2d').getImageData(x,y,1,1).data).slice(0,3);
          const fill={top:pixel(80,10),middle:pixel(40,90)};
          lab.setLayout({framing:'contain'});const fit={top:pixel(80,10),middle:pixel(40,90)};
          lab.setLayout({framing:'slice'});const slice={middle:pixel(40,90),rect:lab.snapshot().panels[0].slice};
          const noAudio=lab.context===null;lab.dispose();return {fill,fit,slice,noAudio};
        }''')
        self.assertNotEqual(actual['fill']['top'],[6,8,13],actual)
        self.assertEqual(actual['fit']['top'],[6,8,13],actual)
        self.assertEqual(actual['fill']['middle'],[255,0,0],actual)
        self.assertEqual(actual['slice']['middle'],[0,0,255],actual)
        self.assertLess(actual['slice']['rect'][2],1,actual)
        self.assertTrue(actual['noAudio'],actual)

    def test_css_panel_clipping_matches_the_contained_canvas_and_cleans_up(self):
        from PIL import Image
        self.page.set_content('<body style="margin:0"><div style="position:relative;isolation:isolate;width:320px;height:240px;background:#111">'
                              '<canvas id="stage" width="320" height="180" style="display:block;width:100%;height:100%;object-fit:contain"></canvas></div></body>')
        actual=self.page.evaluate('''async()=>{
          delete CanvasRenderingContext2D.prototype.filter;
          window.lab=new SimvltaneaLabEngine.Engine(document.querySelector('#stage'));lab.setLayout({count:2});
          lab._picture=(ctx,c,w,h)=>{ctx.fillStyle=c.source.color;ctx.fillRect(0,0,w,h);};
          await lab.addClip({kind:'demo',color:'#ff0000'},{panel:2,blend:'multiply',blur:12,opacity:1,brightness:1,contrast:1,saturation:1,hold:true,attack:.01});
          const c=lab.clips[0];lab._activate(c);c.video.age=1;lab._updateVoice(c);lab._draw();
          return {fallback:lab.snapshot().capabilities.cssPictureFilters,base:c.layer.style.mixBlendMode,
            clip:c.layer.parentElement.style.overflow,isolation:c.layer.parentElement.style.isolation};
        }''')
        self.assertEqual(actual,{'fallback':True,'base':'normal','clip':'hidden','isolation':'isolate'})
        def pixels():
            with Image.open(io.BytesIO(self.page.screenshot(clip={'x':0,'y':0,'width':320,'height':240}))) as image:
                image=image.convert('RGB')
                return {'outside':image.getpixel((159,120)),'letterbox':image.getpixel((240,20)),'inside':image.getpixel((240,120))}
        actual=pixels()
        self.assertEqual(actual['outside'],(6,8,13),actual)
        self.assertEqual(actual['letterbox'],(17,17,17),actual)
        self.assertGreater(actual['inside'][0],240,actual)
        self.page.evaluate('''async()=>{
          await lab.addClip({kind:'demo',color:'#00ff00'},{panel:1,blend:'multiply',opacity:1,brightness:1,contrast:1,saturation:1,hold:true,attack:.01});
          const c=lab.clips[1];lab._activate(c);c.video.age=1;lab._updateVoice(c);lab._draw();
        }''')
        self.assertEqual(pixels()['outside'],(0,255,0))
        self.page.evaluate('lab.dispose()')
        self.assertEqual(self.page.locator('[data-lab-css-panels]').count(),0)


if __name__ == '__main__':
    unittest.main()
