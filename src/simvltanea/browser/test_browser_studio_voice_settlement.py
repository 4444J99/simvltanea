"""Committed export metadata must not gate already-playing generated voices."""
from __future__ import annotations

import mimetypes
import unittest
from urllib.parse import urlparse

from simvltanea.browser import test_browser_filter_controls as fixture
from simvltanea.browser import test_browser_generated_filters as generated


class StudioVoiceSettlementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.FilterControlsBrowserTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.FilterControlsBrowserTests.tearDownClass.__func__(cls)

    wait = generated.GeneratedVoiceFilterTests.wait
    open_generated = generated.GeneratedVoiceFilterTests.open_generated

    def test_first_admitted_voice_runs_before_initial_export_plan_can_settle(self):
        context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True,
                                           service_workers='block')
        self.addCleanup(context.close)

        def route(request):
            parsed = urlparse(request.request.url)
            name = parsed.path.lstrip('/') or 'index.html'
            if parsed.netloc != 'studio.test':
                request.abort()
            elif name in self.files:
                request.fulfill(status=200, body=self.files[name],
                                content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream')
            else:
                request.fulfill(status=404, body='Missing fixture')

        context.route('**/*', route)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto('https://studio.test/watch.html?gen=1&seed=99&mix=s3.2&evolve=0', wait_until='domcontentloaded')
        page.evaluate(generated.VOICE_PROBE)
        page.evaluate('''() => {
          window.live=compositionRuntime;window.exportSettled=false;
          compositionIO.plan().then(plan=>{window.initialPlan=plan;exportSettled=true});
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{
            if(args[1].id==='loop-2'){
              window.secondHeld=true;
              await new Promise(resolve=>{window.releaseSecond=resolve});
            }
            return prime(...args);
          };
        }''')
        page.locator('#speaker').focus()
        page.keyboard.press('Enter')
        self.wait(page, "window.secondHeld && live.nodes.get('loop-1').active && voiceEdges.length===1", 20000)
        self.assertFalse(page.evaluate('exportSettled'), 'unadmitted second source leaked into the initial export plan')
        page.evaluate('''() => {
          window.firstNode=live.nodes.get('loop-1');window.firstVoice=voiceFor(firstNode.active);
          window.firstMedia=firstNode.media;window.firstBinding=firstNode.audio;window.firstFrames=firstNode.callbacks;
        }''')
        page.wait_for_timeout(2800)  # More than the grain voice's full 2.5s period.
        self.assertGreater(page.evaluate('firstVoice.events'), 0,
                           'first admitted generated voice was gated on unpublished export metadata')
        self.assertGreater(page.evaluate('firstNode.callbacks'), page.evaluate('firstFrames'))
        self.assertFalse(page.evaluate('exportSettled'))
        page.evaluate('releaseSecond()')
        self.wait(page, 'exportSettled && live.ready && !live.draining')
        self.assertTrue(page.evaluate('''() => firstNode.media===firstMedia && firstNode.audio===firstBinding &&
          voiceFor(firstNode.active)===firstVoice && firstVoice.disconnected===0 &&
          initialPlan.sources.every((source,i)=>source.sha256===[...live.nodes.values()][i].item.sha256)'''))

    def test_deferred_metadata_settlement_keeps_existing_voice_buses_scheduling(self):
        page = self.open_generated()
        page.evaluate('''() => {
          window.oldVoice=voiceFor(outgoing);window.otherVoice=voiceFor(siblingDeck);
          window.contextBefore=live.audio.context;
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{
            window.preparationHeld=true;
            await new Promise(resolve=>{window.releasePreparation=resolve});
            await prime(...args);args[0].media.pause();args[0].media.play=()=>Promise.resolve();
          };
          resident.box.click();
          window.exportSettled=false;
          compositionIO.plan().then(plan=>{window.settledPlan=plan;exportSettled=true});
        }''')
        self.wait(page, 'window.preparationHeld===true')
        self.assertFalse(page.evaluate('exportSettled'))
        page.wait_for_timeout(600)
        before = page.evaluate('otherVoice.events')
        page.wait_for_timeout(2800)
        self.assertGreater(page.evaluate('otherVoice.events'), before,
                           'pending metadata settlement stopped the unchanged generated voice')
        page.evaluate('releasePreparation()')
        self.wait(page, "exportSettled && !live.draining && live.events.some(e=>e.type==='handoff-deferred')")
        self.assertTrue(page.evaluate('''() => resident.active===outgoing && sibling.active===siblingDeck &&
          voiceFor(outgoing)===oldVoice && voiceFor(siblingDeck)===otherVoice &&
          oldVoice.disconnected===0 && otherVoice.disconnected===0 && live.audio.context===contextBefore &&
          settledPlan.sources.every((source,i)=>source.sha256===[...live.nodes.values()][i].item.sha256)'''))
        self.assertEqual(page.evaluate('siblingCalls'), [])
        self.assertEqual(page.evaluate('voiceEdges.length'), 2, 'metadata publication rebuilt generated voice buses')
