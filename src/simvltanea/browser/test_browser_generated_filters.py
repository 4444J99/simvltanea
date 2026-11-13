"""Generated Studio voices share persistent deck filters during handoff."""
from __future__ import annotations

import mimetypes
import time
import unittest
from urllib.parse import urlparse

from simvltanea.browser import test_browser_filter_controls as fixture


VOICE_PROBE = r"""() => {
  window.voiceEdges = [];
  window.voiceSources = 0;
  const connect = AudioNode.prototype.connect;
  const disconnect = AudioNode.prototype.disconnect;
  const createSource = AudioContext.prototype.createMediaElementSource;
  AudioContext.prototype.createMediaElementSource = function(...args) {
    voiceSources++;
    return createSource.apply(this, args);
  };
  AudioNode.prototype.connect = function(target, ...ports) {
    const result = connect.call(this, target, ...ports);
    // Each generated note/noise event connects its own envelope to this bus.
    for (const edge of voiceEdges) if (edge.input === target) edge.events++;
    const isDeckFilter = [...compositionRuntime.nodes.values()].some(node =>
      node.decks.some(deck => deck.binding?.filter === target));
    if (this instanceof GainNode && isDeckFilter) {
      const meter = this.context.createAnalyser();
      meter.fftSize = 256;
      connect.call(this, meter);
      voiceEdges.push({input:this, filter:target, meter, disconnected:0, peak:0, events:0});
    }
    return result;
  };
  AudioNode.prototype.disconnect = function(...args) {
    for (const edge of voiceEdges) if (edge.input === this) edge.disconnected++;
    return disconnect.apply(this, args);
  };
  window.voiceFor = deck => voiceEdges.find(edge => edge.filter === deck.binding?.filter && !edge.disconnected);
  setInterval(() => {
    for (const edge of voiceEdges) {
      const samples = new Float32Array(edge.meter.fftSize);
      edge.meter.getFloatTimeDomainData(samples);
      edge.peak = Math.max(edge.peak, ...samples.map(Math.abs));
    }
  }, 30);
}"""


class GeneratedVoiceFilterTests(unittest.TestCase):
    """Use real staged Studio scripts and canvas recordings, with no server."""

    @classmethod
    def setUpClass(cls):
        fixture.FilterControlsBrowserTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.FilterControlsBrowserTests.tearDownClass.__func__(cls)

    def wait(self, page, predicate, timeout=10000):
        # Poll through CDP evaluation: Playwright's in-page expression polling
        # uses eval, which the actual staged script-src policy forbids.
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if page.evaluate(predicate):
                return
            page.wait_for_timeout(30)
        self.fail(f'Timed out waiting for {predicate}')

    def open_generated(self, *, sound=True):
        context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True,
                                           service_workers='block')
        self.addCleanup(context.close)
        def route(request):
            parsed = urlparse(request.request.url)
            path = parsed.path.lstrip('/') or 'index.html'
            if parsed.netloc != 'studio.test':
                request.abort()
            elif path in self.files:
                request.fulfill(status=200, body=self.files[path],
                                content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
            else:
                request.fulfill(status=404, body='Missing fixture')
        context.route('**/*', route)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto('https://studio.test/watch.html?gen=1&seed=99&mix=s2.3&evolve=0')
        self.wait(page, 'compositionRuntime.ready && compositionRuntime.nodes.size===2 && !compositionRuntime.draining',
                  timeout=20000)
        self.assertEqual(page.evaluate('SimvltaneaStudio.snapshot().record'), 'recorded')
        page.evaluate(VOICE_PROBE)
        if sound:
            page.locator('#speaker').focus()
            page.keyboard.press('Enter')
            self.wait(page, 'compositionRuntime.audio.enabled && voiceEdges.length===2')
        page.evaluate("""() => {
          window.live = compositionRuntime;
          [window.resident, window.sibling] = [...live.nodes.values()];
          window.outgoing = resident.active;
          window.incoming = resident.decks.find(deck => deck !== outgoing);
          window.siblingDeck = sibling.active;
          window.siblingCalls = [];
          window.siblingFrames = sibling.callbacks;
          for (const name of ['play', 'pause', 'load']) {
            const native = sibling.media[name].bind(sibling.media);
            sibling.media[name] = (...args) => { siblingCalls.push(name); return native(...args); };
          }
        }""")
        return page

    def start_handoff(self, page, *, reject=False):
        page.evaluate("""reject => {
          if (reject) {
            const play = incoming.media.play.bind(incoming.media);
            incoming.media.play = () => incoming.media.dataset.deck === 'active'
              ? Promise.reject(new Error('fixture: incoming promotion refused')) : play();
          }
          window.handoff = live.replace(resident, sibling.item, sibling.source,
            new AbortController().signal, 1.8).then(() => null, error => error.message);
        }""", reject)
        self.wait(page, 'Boolean(live.fade) && live.clock.simTime-live.fade.began>.15')

    def test_generated_voices_overlap_through_their_own_deck_filters(self):
        page = self.open_generated()
        page.evaluate('window.oldVoice=voiceFor(outgoing); window.siblingVoice=voiceFor(siblingDeck)')
        self.start_handoff(page)
        self.assertTrue(page.evaluate('Boolean(voiceFor(incoming))'),
                        'incoming generated voice is missing during the visual crossfade')
        page.evaluate("""() => {
          window.enteringVoice = voiceFor(incoming);
          for (let i=0; i<3; i++) {
            live.options.onDeckAudio(incoming, live.audio.context);
            live.options.onDeckAudio(outgoing, live.audio.context);
            live.options.onAudioNode(resident, live.audio.context);
          }
        }""")
        self.assertEqual(page.evaluate('voiceEdges.length'), 3, 'repeated hooks recreated a voice bus')
        self.assertTrue(page.evaluate("""voiceFor(outgoing)===oldVoice && voiceFor(siblingDeck)===siblingVoice &&
          enteringVoice.input!==oldVoice.input && incoming.binding.filter!==outgoing.binding.filter &&
          incoming.weight>0 && outgoing.weight>0 && incoming.binding.target>0 && outgoing.binding.target>0"""))
        self.wait(page, 'enteringVoice.peak>.0001 && Boolean(live.fade)', timeout=1500)
        self.assertIsNone(page.evaluate('handoff'))
        self.assertEqual(page.evaluate('oldVoice.disconnected'), 1)
        self.assertEqual(page.evaluate('enteringVoice.disconnected'), 0)
        self.assertEqual(page.evaluate('siblingVoice.disconnected'), 0)
        self.assertTrue(page.evaluate('resident.active===incoming && voiceFor(incoming)===enteringVoice'))
        self.assertEqual(page.evaluate('voiceSources'), 3, 'media source bindings were rebuilt')
        self.assertEqual(page.evaluate('siblingCalls'), [])
        self.assertGreater(page.evaluate('sibling.callbacks'), page.evaluate('siblingFrames'))

    def test_rejected_successor_detaches_only_its_generated_voice(self):
        page = self.open_generated()
        page.evaluate('window.oldVoice=voiceFor(outgoing); window.siblingVoice=voiceFor(siblingDeck)')
        self.start_handoff(page, reject=True)
        self.assertTrue(page.evaluate('Boolean(voiceFor(incoming))'),
                        'prepared generated successor has no independent voice')
        page.evaluate('window.failedVoice=voiceFor(incoming)')
        self.assertEqual(page.evaluate('handoff'), 'fixture: incoming promotion refused')
        self.assertEqual(page.evaluate('failedVoice.disconnected'), 1)
        self.assertEqual(page.evaluate('oldVoice.disconnected'), 0)
        self.assertEqual(page.evaluate('siblingVoice.disconnected'), 0)
        self.assertTrue(page.evaluate("""resident.active===outgoing && voiceFor(outgoing)===oldVoice &&
          !resident.media.paused && !voiceFor(incoming) && incoming.item===null && live.activeStandbys===0"""))
        self.assertEqual(page.evaluate('voiceSources'), 3)
        self.assertEqual(page.evaluate('siblingCalls'), [])
        self.assertGreater(page.evaluate('sibling.callbacks'), page.evaluate('siblingFrames'))

    def test_sound_unlock_during_handoff_attaches_both_generated_decks(self):
        page = self.open_generated(sound=False)
        self.start_handoff(page)
        page.locator('#speaker').focus()
        page.keyboard.press('Enter')
        self.wait(page, 'live.audio.enabled && Boolean(voiceFor(incoming)) && Boolean(voiceFor(outgoing))')
        self.assertTrue(page.evaluate('Boolean(live.fade) && Boolean(voiceFor(siblingDeck))'))
        self.assertEqual(page.evaluate('voiceEdges.length'), 3)
        self.assertIsNone(page.evaluate('handoff'))
        self.assertEqual(page.evaluate('voiceEdges.filter(edge=>!edge.disconnected).length'), 2)
        self.assertEqual(page.evaluate('voiceSources'), 3)
        self.assertEqual(page.evaluate('siblingCalls'), [])

    def test_sibling_events_continue_during_pending_launch_and_stop_on_pause_or_dispose(self):
        page = self.open_generated()
        page.evaluate("""() => {
          window.siblingVoice = voiceFor(siblingDeck);
          const prime = live.prime.bind(live);
          live.prime = async (...args) => {
            window.preparationHeld = true;
            await new Promise(resolve => {window.releasePreparation=resolve;});
            return prime(...args);
          };
          // Exercise the real Studio launch, which replaces its metadata session
          // before waiting for this panel's successor. The sibling is unchanged.
          resident.box.click();
        }""")
        self.wait(page, 'window.preparationHeld===true')
        page.wait_for_timeout(600)  # Drain the scheduler's pre-existing 450 ms lookahead.
        before = page.evaluate('siblingVoice.events')
        page.wait_for_timeout(700)
        self.assertGreater(page.evaluate('siblingVoice.events'), before,
                           'pending Studio launch stopped new generated events in the sibling')
        self.assertEqual(page.evaluate('siblingCalls'), [])
        self.assertEqual(page.evaluate('siblingVoice.disconnected'), 0)
        page.evaluate('live.pause()')
        paused = page.evaluate('siblingVoice.events')
        page.wait_for_timeout(350)
        self.assertEqual(page.evaluate('siblingVoice.events'), paused)
        page.evaluate('live.start()')
        page.evaluate('releasePreparation()')
        self.wait(page, '!live.draining')
        page.evaluate('live.dispose()')
        disposed = page.evaluate('voiceEdges.map(edge=>edge.events)')
        page.wait_for_timeout(350)
        self.assertEqual(page.evaluate('voiceEdges.map(edge=>edge.events)'), disposed)
        self.assertTrue(page.evaluate('voiceEdges.every(edge=>edge.disconnected===1)'))


if __name__ == '__main__':
    unittest.main()
