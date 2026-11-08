"""Boundary policy for reasserting native playback without rebuilding a deck."""
from __future__ import annotations

import json
import subprocess
import unittest

from simvltanea.browser import test_browser_live as fixture


PROBE = r'''
const {Session} = require(process.argv[1]);
if (typeof Session.prototype.observeDecodedFrame !== 'function') {
  process.stdout.write(JSON.stringify({supported:false})); process.exit(0);
}
const session = Object.create(Session.prototype), errors = [];
let plays = 0;
session.running = true; session.disposed = false; session.fade = null; session.reassertNativeLoops = true;
session.report = error => errors.push(String(error.message || error));
const media = {paused:false, play:() => {plays++;return Promise.resolve();}};
const binding = {}, item = {}, deck = {media,url:'blob:resident',callbacks:0,loopPlayRequests:0,
  decoded:{mediaTime:3.8},enteredAt:4,presence:.6,binding,item};
const node = {active:deck,promoting:null,callbacks:0,decoded:null,birthTime:4,item};
const frame = value => session.observeDecodedFrame(node,deck,100,{mediaTime:value,presentedFrames:10});
(async () => {
'''


class NativeLoopWrapPolicyTests(unittest.TestCase):
    def test_default_policy_is_limited_to_the_webkit_family(self):
        program = r'''
const api=require(process.argv[1]), supported=typeof api.needsNativeLoopReplay==='function';
const agents=[
 'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15',
 'Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 CriOS/150.0 Mobile/15E148 Safari/604.1',
 'Mozilla/5.0 (iPad) AppleWebKit/605.1.15 FxiOS/150.0 Mobile/15E148 Safari/605.1.15',
 'Mozilla/5.0 AppleWebKit/537.36 Chrome/156.0.0.0 Safari/537.36',
 'Mozilla/5.0 AppleWebKit/537.36 Chromium/156.0.0.0 Safari/537.36',
 'Mozilla/5.0 Gecko/20100101 Firefox/150.0',''];
process.stdout.write(JSON.stringify({supported,values:supported?
 agents.map(userAgent=>api.needsNativeLoopReplay({navigator:{userAgent}})):[]}));
'''
        done = subprocess.run(['node', '-e', program, str(fixture.LIVE)], check=True,
                              capture_output=True, text=True, timeout=10)
        result = json.loads(done.stdout)
        self.assertTrue(result['supported'], 'WebKit-specific policy is unavailable')
        self.assertEqual(result['values'], [True, True, True, False, False, False, False])

    def probe(self, body):
        script = PROBE + body + r'''
})().catch(error => {console.error(error);process.exitCode=1;});
'''
        done = subprocess.run(['node', '-e', script, str(fixture.LIVE)], check=True,
                              capture_output=True, text=True, timeout=10)
        result = json.loads(done.stdout)
        self.assertTrue(result.get('supported', True), 'Native frame-boundary handling is unavailable')
        return result

    def test_wrap_reasserts_play_and_preserves_residency(self):
        r = self.probe(r'''
await frame(3.9); const steady=plays;
await frame(0); const wrapped=plays;
await frame(0); await frame(.033);
process.stdout.write(JSON.stringify({steady,wrapped,plays,requests:deck.loopPlayRequests,callbacks:node.callbacks,
  preserved:node.active===deck && node.item===item && deck.binding===binding &&
    node.birthTime===4 && deck.enteredAt===4 && deck.presence===.6,
  decoded:node.decoded.mediaTime,errors}));
''')
        self.assertEqual((r['steady'], r['wrapped'], r['plays']), (0, 1, 1))
        self.assertEqual(r['requests'], 1)
        self.assertTrue(r['preserved'])
        self.assertEqual(r['callbacks'], 4)
        self.assertAlmostEqual(r['decoded'], .033)
        self.assertEqual(r['errors'], [])

    def test_paused_disposed_and_standby_decks_do_not_restart(self):
        r = self.probe(r'''
for (const condition of ['paused-session','paused-media','disposed','standby','unloaded','disabled-policy']) {
  session.reassertNativeLoops=condition!=='disabled-policy';
  session.running=condition!=='paused-session';session.disposed=condition==='disposed';
  media.paused=condition==='paused-media';node.active=condition==='standby'?null:deck;
  deck.url=condition==='unloaded'?null:'blob:resident';deck.decoded={mediaTime:3.9};
  await frame(0);
}
process.stdout.write(JSON.stringify({plays,errors}));
''')
        self.assertEqual(r, {'plays': 0, 'errors': []})

    def test_revealed_incoming_deck_can_reassert_its_own_playback(self):
        r = self.probe(r'''
node.active={};session.fade={incoming:deck};await frame(0);
deck.decoded={mediaTime:3.9};session.fade=null;node.promoting=deck;await frame(0);
process.stdout.write(JSON.stringify({plays,errors}));
''')
        self.assertEqual(r, {'plays': 2, 'errors': []})

    def test_rejection_is_reported_only_while_the_same_deck_is_live(self):
        r = self.probe(r'''
media.play=()=>{plays++;return Promise.reject(new Error('native playback refused'));};
await frame(0);let release;
media.play=()=>new Promise((_,reject)=>{release=reject;});deck.decoded={mediaTime:3.9};
const pending=frame(0);deck.url=null;release(new Error('retired read'));await pending;
process.stdout.write(JSON.stringify({plays,errors}));
''')
        self.assertEqual(r['errors'], ['native playback refused'])


class NativeLoopWrapBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.PersistentSessionTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.PersistentSessionTests.tearDownClass.__func__(cls)

    open = fixture.PersistentSessionTests.open

    def test_native_wrap_keeps_element_and_envelope_clock(self):
        page = self.open(effects=True)
        page.evaluate('setClips([0])')
        page.evaluate('''() => {
          // Exercise the WebKit request policy on a real Chromium media host.
          // Native WebKit remediation is checked separately on macOS CI.
          live.reassertNativeLoops=true;
          const n=live.nodes.get('loop-1'), d=n.active;
          globalThis.wrapProof={node:n,deck:d,media:d.media,birth:n.birthTime,entered:d.enteredAt,plays:0};
          const play=d.media.play.bind(d.media);
          d.media.play=()=>{wrapProof.plays++;return play();};
        }''')
        duration = page.evaluate('wrapProof.media.duration')
        page.wait_for_function('wrapProof.plays>0', timeout=int(duration * 1000 + 10000))
        state = page.evaluate('''() => ({plays:wrapProof.plays,
          same:live.nodes.get('loop-1')===wrapProof.node && wrapProof.node.active===wrapProof.deck &&
            wrapProof.node.media===wrapProof.media,
          birth:wrapProof.node.birthTime===wrapProof.birth,
          entered:wrapProof.deck.enteredAt===wrapProof.entered,
          paused:wrapProof.media.paused,phase:wrapProof.node.phase})''')
        self.assertTrue(state['same'])
        self.assertTrue(state['birth'])
        self.assertTrue(state['entered'])
        self.assertFalse(state['paused'])
        self.assertEqual(state['phase'], 'ACTIVE')


if __name__ == '__main__':
    unittest.main()
