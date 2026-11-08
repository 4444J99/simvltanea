"""Settings, URL privacy and actual Studio controls with local synthetic media."""
from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
import subprocess
import time
import unittest
from urllib.parse import urlparse

HERE = Path(__file__).parent


def wait_for(page, expression, *, timeout=10000):
    """Poll through DevTools without requiring unsafe-eval in the staged CSP."""
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if page.evaluate(expression):
            return
        page.wait_for_timeout(25)
    raise AssertionError(f'Browser condition did not become true: {expression}')


def execute(body):
    script = r"""
require(process.argv[1] + '/browser.presence.js');
const S=require(process.argv[1] + '/browser.studio.js');
const supported=typeof S.effectSettingsFromSearch==='function' && typeof S.effectSettingsSearch==='function';
if(!supported){console.log(JSON.stringify({supported}));process.exit(0);}
""" + body
    result = subprocess.run(['node', '-e', script, str(HERE)], capture_output=True,
                            text=True, timeout=20, check=True)
    return json.loads(result.stdout)


class FilterSettingsUrlTests(unittest.TestCase):
    def test_named_settings_roundtrip_without_serializing_unknown_data(self):
        result = execute(r"""
const query=S.effectSettingsSearch('?seed=99&mix=s0.1&fx=0',{attackSeconds:3,curve:'smooth',gainDepth:.4,
  filename:'/private/user-film.mov',token:'not-an-effect'});
console.log(JSON.stringify({supported,query,settings:S.effectSettingsFromSearch(query)}));
""")
        self.assertTrue(result['supported'], 'adjustable URL settings are missing')
        self.assertIn('seed=99', result['query'])
        self.assertIn('mix=s0.1', result['query'])
        self.assertIn('fx=0', result['query'])
        self.assertNotIn('private', result['query'])
        self.assertNotIn('filename', result['query'])
        self.assertNotIn('token', result['query'])
        self.assertEqual(result['settings']['attackSeconds'], 3)
        self.assertEqual(result['settings']['curve'], 'smooth')
        self.assertEqual(result['settings']['gainDepth'], .4)

    def test_invalid_url_values_are_bounded_and_defaults_remove_only_effect_settings(self):
        result = execute(r"""
const values=S.effectSettingsFromSearch('?fx_attack=-500&fx_curve=wrong&fx_tail=Infinity&fx_blur=99&fx_gain=');
const query=S.effectSettingsSearch('?seed=4&fx=0&fx_attack=4&fx_curve=smooth',SimvltaneaPresence.DEFAULT_SETTINGS);
console.log(JSON.stringify({supported,values,query}));
""")
        self.assertTrue(result['supported'], 'adjustable URL settings are missing')
        self.assertEqual(result['values']['attackSeconds'], .1)
        self.assertEqual(result['values']['curve'], 'linear')
        self.assertEqual(result['values']['tail'], .12)
        self.assertEqual(result['values']['blurPx'], 2)
        self.assertEqual(result['values']['gainDepth'], 1)
        self.assertEqual(result['query'], 'seed=4&fx=0')


class FilterControlsBrowserTests(unittest.TestCase):
    """Route real staged bytes in-process; no server or production access required."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from simvltanea.browser.browser_studio import studio_files
        from simvltanea.browser.test_browser_runtime import browser_executable
        from simvltanea.browser.test_browser_studio import prepare_fixtures, probe
        cls.files = studio_files()
        cls.media = {}
        clips = []
        fixtures = prepare_fixtures()
        for index in range(1, 5):
            source = fixtures[f'loop-{index}.mp4']
            data = source.read_bytes()
            clip_id = hashlib.sha256(data).hexdigest()[:12]
            facts = probe(source)
            video = next(stream for stream in facts['streams'] if stream['codec_type'] == 'video')
            name = f'library/clips/{clip_id}.mp4'
            cls.media[name] = data
            clips.append(dict(id=clip_id, file=f'clips/{clip_id}.mp4', bytes=len(data),
                              width=video['width'], height=video['height'],
                              orientation='portrait' if video['height'] > video['width'] else 'landscape',
                              duration_seconds=float(facts['format']['duration']), tags={}))
        cls.files['library/manifest.json'] = json.dumps({'schema': 'simvltanea.public-demo/1', 'clips': clips}).encode()
        cls.files.update(cls.media)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                            args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, query='?seed=99&mix=s0.1&evolve=0', reduced_motion='no-preference', *, count=2):
        context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True,
                                           reduced_motion=reduced_motion, service_workers='block')
        self.addCleanup(context.close)
        requests, errors = [], []
        def route(request):
            parsed = urlparse(request.request.url)
            if parsed.netloc != 'studio.test':
                request.abort()
                return
            path = parsed.path.lstrip('/') or 'index.html'
            if path not in self.files:
                request.fulfill(status=404, body='Missing fixture')
                return
            content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            request.fulfill(status=200, body=self.files[path], content_type=content_type)
        context.on('request', lambda request: requests.append(request.url))
        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://studio.test/' + query)
        wait_for(page, f"window.compositionRuntime?.ready && compositionRuntime.nodes.size==={count} && !compositionRuntime.draining", timeout=20000)
        self.addCleanup(lambda: self.assertEqual(errors, []))
        return page, requests

    def test_controls_change_effects_without_reloading_clips_and_escape_returns_focus(self):
        page, requests = self.open()
        self.assertEqual(page.get_by_role('button', name='Filter settings', exact=True).count(), 1)
        page.locator('#speaker').click()
        wait_for(page, "compositionRuntime.audio.context?.state==='running' && [...compositionRuntime.nodes.values()].every(n=>Boolean(n.audio))")
        page.evaluate('''() => {window.nativeCalls=[];
          window.original=[...compositionRuntime.nodes.values()].map(n=>({media:n.media,binding:n.audio,frames:n.callbacks}));
          window.originalTime=compositionRuntime.clock.simTime;
          for(const node of compositionRuntime.nodes.values())for(const name of ['play','pause','load']) {
            const native=node.media[name].bind(node.media);
            node.media[name]=(...args)=>{nativeCalls.push({id:node.id,name});return native(...args)};
          }
        }''')
        page.get_by_role('button', name='Filter settings', exact=True).click()
        self.assertTrue(page.get_by_role('dialog', name='Clip filters', exact=True).is_visible())
        page.locator('#fx-gain').press('Home')
        page.locator('#fx-curve').select_option('smooth')
        self.assertEqual(page.evaluate('compositionRuntime.effectSettings.gainDepth'), 0)
        self.assertEqual(page.evaluate('compositionRuntime.effectSettings.curve'), 'smooth')
        self.assertIn('fx_gain=0', page.evaluate('location.search'))
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===original[i].media && n.audio===original[i].binding)'))
        wait_for(page, '[...compositionRuntime.nodes.values()].every((n,i)=>n.callbacks>original[i].frames+2)')
        self.assertGreater(page.evaluate('compositionRuntime.clock.simTime'), page.evaluate('originalTime'))
        self.assertEqual(page.evaluate('nativeCalls'), [])
        self.assertTrue(all(url.startswith('https://studio.test/') for url in requests))
        page.keyboard.press('Escape')
        self.assertFalse(page.get_by_role('dialog', name='Clip filters', exact=True).is_visible())
        self.assertEqual(page.evaluate('document.activeElement.id'), 'filter-tune')

    def test_settings_restore_reset_and_do_not_trigger_playback_shortcuts(self):
        page, _ = self.open('?seed=99&mix=s0.1&evolve=0&fx_attack=3&fx_curve=smooth&fx_blur=0')
        page.get_by_role('button', name='Filter settings', exact=True).click()
        self.assertEqual(page.locator('#fx-attack').input_value(), '3')
        self.assertEqual(page.locator('#fx-curve').input_value(), 'smooth')
        self.assertEqual(page.locator('#fx-blur').input_value(), '0')
        before = page.evaluate('SimvltaneaStudio.snapshot().seed')
        page.locator('#fx-curve').press('r')
        self.assertEqual(page.evaluate('SimvltaneaStudio.snapshot().seed'), before)
        page.get_by_role('button', name='Reset filters', exact=True).click()
        self.assertEqual(page.evaluate('compositionRuntime.effectSettings.attackSeconds'), 1.2)
        self.assertNotIn('fx_attack', page.evaluate('location.search'))
        self.assertNotIn('fx_curve', page.evaluate('location.search'))
        self.assertNotIn('fx_blur', page.evaluate('location.search'))

    def test_ecological_energy_changes_spectrum_without_rebinding_or_visual_changes(self):
        # Hold retirement so both independent entry envelopes become steady;
        # the real Studio ecology subscriber continues computing competition.
        page, _ = self.open()
        page.locator('#speaker').click()
        wait_for(page, '''() => {
          const runtime=compositionRuntime;
          return runtime.audio.context?.state==='running' && runtime.nodes.size===2 &&
            !runtime.draining && !runtime.fade && !SimvltaneaStudio.snapshot().busy &&
            [...runtime.nodes.values()].every(n=>!n.busy && !n.promoting && n.active &&
              n.media===n.active.media && n.item && n.active.item===n.item &&
              n.active.url && n.media.currentSrc===n.active.url && Number.isFinite(n.active.enteredAt) &&
              runtime.clock.simTime-n.active.enteredAt>=runtime.effectSettings.attackSeconds &&
              n.active.presence===1);
        }''')
        page.evaluate('''() => {
          window.competitors=[...compositionRuntime.nodes.values()];
          window.competitionContext=compositionRuntime.audio.context;
          window.competitionIdentity=competitors.map(n=>({media:n.media,source:n.audio.source,
            binding:n.audio,filter:n.audio.filter,image:n.media.style.filter,frames:n.callbacks}));
          window.competitionCalls=[];
          for(const n of competitors)for(const method of ['play','pause','load']) {
            const native=n.media[method].bind(n.media);
            n.media[method]=(...args)=>{competitionCalls.push(method);return native(...args)};
          }
          // Controlled recorded-envelope input; sourceEnergy performs its
          // normal normalization. Do not mock ecology or AudioParam setters.
          window.setCompetition=(left,right)=>competitors.forEach((n,i)=>{
            const asset={...n.item.asset,has_audio:true,envelope_hz:10,
              rms_envelope:Array(Math.ceil(n.media.duration*10)).fill([left,right][i])};
            n.item.asset=asset;
          });
          setCompetition(1,0);
        }''')
        wait_for(page, 'competitors[0].audio.filter.frequency.value>10000 && competitors[1].audio.filter.frequency.value<5000')
        self.assertGreater(page.evaluate('competitors[0].audio.target'), page.evaluate('competitors[1].audio.target'))
        page.evaluate('setCompetition(0,1)')
        wait_for(page, 'competitors[1].audio.filter.frequency.value>10000 && competitors[0].audio.filter.frequency.value<5000')
        self.assertTrue(page.evaluate('competitors.every((n,i)=>n.media.style.filter===competitionIdentity[i].image)'))

        # The strongest audible resident is neutral when its rival rests.
        page.evaluate('compositionRuntime.setResting(competitors[1].id,true)')
        wait_for(page, 'competitors[0].audio.filter.frequency.value>15000 && competitors[1].audio.target===0')
        page.evaluate('compositionRuntime.setResting(competitors[1].id,false)')
        wait_for(page, 'competitors[0].audio.filter.frequency.value<5000')
        page.get_by_role('button', name='Filter settings', exact=True).click()
        page.locator('#fx-lowpass').press('Home')
        wait_for(page, "competitors.every(n=>n.audio.filter.type==='allpass')")
        page.locator('#fx-lowpass').press('End')
        wait_for(page, "competitors[0].audio.filter.type==='lowpass' && competitors[0].audio.filter.frequency.value<5000")
        page.keyboard.press('Escape')
        page.locator('#effects').click()
        wait_for(page, "competitors.every(n=>n.audio.filter.type==='allpass')")
        page.locator('#effects').click()
        wait_for(page, "competitors[0].audio.filter.type==='lowpass' && competitors[0].audio.filter.frequency.value<5000")
        self.assertTrue(page.evaluate('''competitors.every((n,i)=>n.media===competitionIdentity[i].media &&
          n.audio===competitionIdentity[i].binding && n.audio.source===competitionIdentity[i].source &&
          n.audio.filter===competitionIdentity[i].filter && n.callbacks>competitionIdentity[i].frames) &&
          compositionRuntime.audio.context===competitionContext'''))
        self.assertEqual(page.evaluate('competitionCalls'), [])

    def test_tuning_during_handoff_preserves_four_plus_one_touch_budget_and_siblings(self):
        page, _ = self.open('?seed=99&mix=s0.1.2.3&evolve=0', count=4)
        page.locator('#speaker').click()
        wait_for(page, 'compositionRuntime.audio.enabled')
        page.evaluate('''() => {
          const live=compositionRuntime, [resident,...siblings]=[...live.nodes.values()];
          window.siblingState=siblings.map(n=>({node:n,media:n.media,binding:n.audio,frames:n.callbacks}));
          window.siblingCalls=[];
          for(const {node,media} of siblingState)for(const method of ['play','pause','load']) {
            const native=media[method].bind(media);
            media[method]=(...args)=>{siblingCalls.push({id:node.id,method});return native(...args)};
          }
          window.population=[];
          window.observePopulation=setInterval(()=>population.push(
            [...document.querySelectorAll('video')].filter(v=>v.getAttribute('src')).length),20);
          window.handoff=live.replace(resident,siblings[0].item,siblings[0].source,new AbortController().signal,1.2);
        }''')
        wait_for(page, 'Boolean(compositionRuntime.fade)')
        page.get_by_role('button', name='Filter settings', exact=True).click()
        page.locator('#fx-blur').press('Home')
        page.evaluate('handoff')
        page.evaluate('clearInterval(observePopulation)')
        self.assertEqual(page.evaluate('Math.max(...population)'), 5)
        self.assertEqual(page.evaluate('compositionRuntime.snapshot().activeStandbys'), 0)
        self.assertEqual(page.evaluate('compositionRuntime.snapshot().maxConcurrentStandbys'), 1)
        self.assertEqual(page.evaluate('compositionRuntime.effectSettings.blurPx'), 0)
        self.assertEqual(page.evaluate('siblingCalls'), [])
        self.assertTrue(page.evaluate('siblingState.every(s=>s.node.media===s.media && s.node.audio===s.binding && s.node.callbacks>s.frames)'))

    def test_reduced_motion_bypasses_effects_and_retains_safe_settings(self):
        page, _ = self.open('?seed=99&mix=s0.1&evolve=0&fx_attack=3', reduced_motion='reduce')
        self.assertFalse(page.evaluate('compositionRuntime.effectsEnabled'))
        self.assertTrue(page.evaluate("[...compositionRuntime.nodes.values()].every(n=>n.media.style.filter==='')"))
        self.assertEqual(page.evaluate('compositionRuntime.effectSettings.attackSeconds'), 3)
        self.assertTrue(page.get_by_role('button', name='Filter settings', exact=True).is_disabled())


if __name__ == '__main__':
    unittest.main()
