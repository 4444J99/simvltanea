"""A failed native seek may repair its decoder without changing its resident."""
from __future__ import annotations

import unittest
import json
from pathlib import Path
import subprocess

from simvltanea.browser import test_browser_failed_outgoing as fixture

PROOFS = Path(__file__).resolve().parents[3] / 'var' / 'proofs' / 'native-rescue'


class NativeRescueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.FailedOutgoingHandoffTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.FailedOutgoingHandoffTests.tearDownClass.__func__(cls)

    def open(self):
        page = fixture.FailedOutgoingHandoffTests.open(self)
        page.evaluate('live.options.nativeLoopStandbyRescue=true')
        page.evaluate('setClips([0,1,2,3])')
        page.evaluate('''() => {
          window.residentBefore={item:node.item,source:node.source,birth:node.birthTime,
            context:live.audio.context,master:live.master,generation:live.generation,
            deckCount:document.querySelectorAll('video').length};
          window.neighbors=[...live.nodes.values()].filter(n=>n!==node).map(n=>({node:n,
            deck:n.active,media:n.media,url:n.active.url,binding:n.audio,frames:n.callbacks}));
          window.neighborCalls=[];
          for(const row of neighbors)for(const name of ['play','pause','load']){
            const native=row.media[name].bind(row.media);
            row.media[name]=(...args)=>{neighborCalls.push([row.node.id,name]);return native(...args)};
          }
          live.setPresence(node.id,.42,.7);
          window.reveals=[];
          live.clock.subscribe(()=>{if(live.fade?.node===node)reveals.push({
            frames:incoming.progress.sourceChanges,seeking:incoming.media.seeking,
            paused:incoming.media.paused,presence:incoming.presence,oldOpacity:outgoing.media.style.opacity})});
        }''')
        return page

    def freeze(self, page, *, delayed=False):
        # Fault in the same task that observes the real end. A separate browser
        # protocol call can arrive after a healthy wrap has cleared endSeen.
        seam = page.evaluate('''delayed => new Promise((resolve,reject) => {
          let done=false;
          const timer=setTimeout(()=>{done=true;reject(Error('No observed native seam within 7000ms'))},7000);
          const check=()=>{
            if(done)return;
            const media=outgoing.media,state=outgoing.loopSeek;
            if(!state?.endSeen || media.seeking){requestAnimationFrame(check);return;}
            done=true;clearTimeout(timer);
            window.faultSeam={endSeen:state.endSeen,changes:state.changes,current:media.currentTime,
              decoded:outgoing.decoded.mediaTime,owned:node.active===outgoing && state.url===outgoing.url};
            HTMLMediaElement.prototype.pause.call(media);
            window.faultAt=performance.now();let current=0;
            Object.defineProperty(media,'currentTime',{configurable:true,
              get:()=>delayed && performance.now()-faultAt<450 ? media.duration-.001 : current,set:v=>{current=v}});
            Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
            Object.defineProperty(media,'seeking',{configurable:true,get:()=>!delayed || performance.now()-faultAt>=450});
            media.play=()=>Promise.resolve();resolve(faultSeam);
          };
          check();
        })''', delayed)
        self.assertTrue(seam['endSeen'] and seam['owned'])
        self.assertGreaterEqual(seam['changes'], 2)
        page.wait_for_function('Boolean(outgoing.loopSeek?.attempt)', timeout=3000)

    def test_failed_seek_automatically_repairs_same_resident_before_two_seconds(self):
        for delayed in (False, True):
            with self.subTest(delayed_initial_guard=delayed):
                page = self.open()
                self.freeze(page, delayed=delayed)
                # This is a behavior assertion on the unmodified production
                # handoff; only the failed outgoing native element is faulted.
                page.wait_for_timeout(1000)
                self.assertTrue(page.evaluate('node.active!==outgoing'),
                                'a fulfilled but frozen seek never escalated to the idle deck')
                result = page.evaluate('''() => ({
                  retired:live.proofRetired.find(row=>row.url===before.url),
                  same:node.item===residentBefore.item && node.source===residentBefore.source &&
                    node.birthTime===residentBefore.birth,
                  stable:live.audio.context===residentBefore.context && live.master===residentBefore.master &&
                    live.generation===residentBefore.generation,
                  neighbors:neighbors.every(row=>row.node.active===row.deck && row.node.media===row.media &&
                    row.deck.url===row.url && row.node.audio===row.binding && row.node.callbacks>row.frames),
                  calls:neighborCalls,reveals,permit:live.activeStandbys,maxPermit:live.maxConcurrentStandbys,
                  deckCount:document.querySelectorAll('video').length,
                  sourceUrl:live.sources.get(node.source)?.url,url:node.active.url,
                  retiredIdentity:outgoing.residentIdentity,
                  receipt:live.proofProgressSummary(performance.now(),true).nativeLoopRescue.receipts.find(
                    row=>row.type==='native-loop-rescue-committed')})''')
                self.assertLess(result['retired']['maxGapMs'], 2000)
                self.assertTrue(result['same'] and result['stable'] and result['neighbors'])
                self.assertEqual(result['calls'], [])
                self.assertEqual((result['permit'], result['maxPermit'], result['deckCount']), (0, 1, 8))
                self.assertEqual(result['sourceUrl'], result['url'])
                self.assertIsNone(result['retiredIdentity'])
                self.assertGreaterEqual(result['receipt']['admissionChanges'], 2)
                self.assertGreaterEqual(result['receipt']['promotionChanges'], 2)
                self.assertFalse(result['receipt']['admissionSeeking'] or result['receipt']['promotionSeeking'])
                self.assertTrue(result['reveals'])
                self.assertTrue(all(row['frames'] >= 2 and not row['seeking'] and not row['paused'] and
                                    row['presence'] == .42 and row['oldOpacity'] == '1'
                                    for row in result['reveals']))
                PROOFS.mkdir(parents=True, exist_ok=True)
                (PROOFS / ('delayed-trigger.json' if delayed else 'normal-trigger.json')).write_text(
                    json.dumps(result, indent=2) + '\n')
                page.close()

    def queue_behind_permit(self, page):
        page.evaluate('''() => {
          window.lease=live.withPreparation(()=>new Promise(resolve=>{window.releaseLease=resolve}));
        }''')
        page.wait_for_function('typeof releaseLease==="function"')
        self.freeze(page)
        page.wait_for_function('Boolean(node.nativeRescue)', timeout=3000)
        self.assertFalse(page.evaluate('Boolean(incoming.url)'), 'queued repair allocated a second standby')

    def test_queued_rescue_is_cancelled_after_outgoing_recovers(self):
        page = self.open()
        self.queue_behind_permit(page)
        page.evaluate('''async () => {
          const media=outgoing.media;
          for(const name of ['currentTime','paused','seeking','play'])delete media[name];
          await media.play();
        }''')
        page.wait_for_function('!node.nativeRescue')
        page.evaluate('releaseLease();lease')
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url'))
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])

    def test_native_repair_that_presents_two_frames_does_not_replace_its_decoder(self):
        page = self.open()
        self.freeze(page)
        page.evaluate('''async () => {
          const media=outgoing.media;
          for(const name of ['currentTime','paused','seeking','play'])delete media[name];
          media.currentTime=1/30;
          await media.play();
        }''')
        page.wait_for_function('live.events.some(e=>e.type==="native-loop-seek-recovered")')
        page.wait_for_timeout(300)
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url'))
        self.assertFalse(page.evaluate('live.events.some(e=>e.type==="native-loop-rescue-started")'))

    def test_queued_source_epoch_change_cancels_without_loading_a_stale_successor(self):
        page = self.open()
        self.queue_behind_permit(page)
        page.evaluate('outgoing.sourceEpoch++')
        page.wait_for_function('!node.nativeRescue')
        page.evaluate('releaseLease();lease')
        self.assertTrue(page.evaluate('node.active===outgoing && !incoming.url'))
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])

    def test_sibling_transition_and_queued_rescue_share_one_permit(self):
        page = self.open()
        page.evaluate('''() => {
          items.push({...items[1],name:'replacement',sha256:'5'.repeat(64)});
          const prime=live.prime.bind(live);
          let held=false;
          live.prime=async(...args)=>{await prime(...args);
            // This deliberate non-aborting fixture delays its first cleanup.
            // A yielded ordinary intent may then retry the same decoder.
            if(args[1].id==='loop-2' && !held){held=true;
              await new Promise(resolve=>{window.releaseSibling=resolve})}};
          window.siblingChange=setClips([0,4,2,3]);
        }''')
        page.wait_for_function('typeof releaseSibling==="function"')
        self.freeze(page)
        page.wait_for_function('Boolean(node.nativeRescue)')
        self.assertTrue(page.evaluate('live.draining && !node.busy && live.activeStandbys===1 && !incoming.url'))
        page.evaluate('releaseSibling();siblingChange')
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        self.assertTrue(page.evaluate('''node.item===residentBefore.item && live.nodes.get('loop-2').item===items[4] &&
          neighbors.slice(1).every(row=>row.node.active===row.deck && row.deck.url===row.url &&
            row.node.audio===row.binding && row.node.callbacks>row.frames)'''))
        self.assertEqual(page.evaluate('neighborCalls.filter(row=>row[0]!=="loop-2")'), [])
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('live.maxConcurrentStandbys'), 1)

    def test_same_slot_selection_during_rescue_fade_keeps_latest_intent(self):
        page = self.open()
        self.freeze(page)
        page.wait_for_function('live.fade?.node===node')
        page.evaluate('''() => {
          items.push({...items[0],name:'replacement',sha256:'5'.repeat(64)});
          window.selected=setClips([4,1,2,3]);
        }''')
        self.assertTrue(page.evaluate('selected'))
        self.assertTrue(page.evaluate('node.item===items[4] && live.sources.get(node.source).url===node.active.url'))
        self.assertFalse(page.evaluate('live.events.some(e=>e.type==="native-loop-rescue-committed")'))
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])

    def test_resume_rearms_failed_source_with_new_ownership_after_cancelling_rescue(self):
        page = self.open()
        self.queue_behind_permit(page)
        page.evaluate('live.pause();releaseLease();lease')
        page.wait_for_function('!node.nativeRescue && live.activeStandbys===0')
        page.evaluate('live.start()')
        page.wait_for_timeout(1300)
        self.assertTrue(page.evaluate('node.active!==outgoing'),
                        'the interrupted attempt permanently blocked repair after explicit resume')
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 1)
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-seek-recovery").length'), 2)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)

    def test_queued_rescue_cannot_overwrite_a_new_same_slot_selection(self):
        page = self.open()
        self.queue_behind_permit(page)
        page.evaluate('''() => {
          items.push({...items[0],name:'replacement',sha256:'5'.repeat(64)});
          window.selected=setClips([4,1,2,3]);
          releaseLease();
        }''')
        self.assertTrue(page.evaluate('selected'))
        self.assertTrue(page.evaluate('node.item===items[4] && !node.nativeRescue'))
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 0)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])

    def test_pause_hide_and_dispose_cancel_a_queued_rescue(self):
        for action in ('pause', 'hide', 'dispose'):
            with self.subTest(action=action):
                page = self.open()
                self.queue_behind_permit(page)
                page.evaluate('''action => {
                  if(action==='hide') {
                    Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                    document.dispatchEvent(new Event('visibilitychange'));
                  } else live[action]();
                  releaseLease();
                }''', action)
                page.wait_for_function('!node.nativeRescue && live.activeStandbys===0')
                self.assertTrue(page.evaluate('!live.running && !incoming.url'))
                self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 0)
                if action != 'dispose':
                    self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url'))
                page.close()

    def test_starved_rescue_remains_hidden_and_is_attempted_only_once(self):
        page = self.open()
        page.evaluate('''() => {
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{await prime(...args);args[0].media.pause();args[0].media.play=()=>Promise.resolve()};
        }''')
        self.freeze(page)
        page.wait_for_function('live.events.some(e=>e.type==="native-loop-rescue-deferred")', timeout=4000)
        page.wait_for_timeout(500)
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url'))
        self.assertEqual(page.evaluate('reveals.length'), 0)
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 1)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])

    def test_owned_native_abort_rejection_is_reported_and_keeps_outgoing(self):
        page = self.open()
        page.evaluate('''() => {
          const prime=live.prime.bind(live);
          live.prime=(...args)=>{
            args[0].media.play=()=>Promise.reject(new DOMException('native decoder refused','AbortError'));
            return prime(...args);
          };
        }''')
        self.freeze(page)
        page.wait_for_timeout(600)
        self.assertIn('Native playback rejected (AbortError)', page.evaluate('live.lastFailure') or '',
                      'an owned native playback refusal was mistaken for request cancellation')
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url'))
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)

    def test_pause_before_fresh_rescue_reveal_releases_permit(self):
        page = self.open()
        page.evaluate('''() => {
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{await prime(...args);args[0].media.pause();args[0].media.play=()=>Promise.resolve()};
        }''')
        self.freeze(page)
        page.wait_for_function('node.nativeRescue?.incoming && live.handoff')
        page.evaluate('live.pause()')
        page.wait_for_function('!node.nativeRescue && live.activeStandbys===0')
        self.assertTrue(page.evaluate('node.active===outgoing && !incoming.url && !live.running'))
        self.assertEqual(page.evaluate('reveals.length'), 0)

    def test_failed_rescue_promotion_rolls_back_to_retained_outgoing(self):
        page = self.open()
        page.evaluate('''() => {
          const promote=live.playPromoted.bind(live);
          live.playPromoted=(deck,...args)=>{deck.media.pause();deck.media.play=()=>Promise.resolve();return promote(deck,...args)};
        }''')
        self.freeze(page)
        page.wait_for_function('live.events.some(e=>e.type==="native-loop-rescue-deferred")', timeout=4000)
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url && outgoing.weight===1'))
        self.assertGreater(page.evaluate('reveals.length'), 2)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('neighborCalls'), [])


    def test_healthy_wrap_and_source_without_fps_never_request_rescue(self):
        page = self.open()
        page.wait_for_timeout(1600)
        self.assertFalse(page.evaluate('live.events.some(e=>e.type.startsWith("native-loop-rescue-"))'))
        page.evaluate('delete node.item.asset.fps')
        page.evaluate('''() => {
          HTMLMediaElement.prototype.pause.call(outgoing.media);
          Object.defineProperty(outgoing.media,'paused',{get:()=>false});
          Object.defineProperty(outgoing.media,'seeking',{get:()=>true});
          Object.defineProperty(outgoing.media,'currentTime',{get:()=>0,set:()=>{}});
        }''')
        page.wait_for_timeout(1200)
        self.assertFalse(page.evaluate('live.events.some(e=>e.type.startsWith("native-loop-rescue-"))'))
        self.assertEqual(page.evaluate('neighborCalls'), [])



class NativeRescueReceiptTests(unittest.TestCase):
    def test_bounded_receipts_survive_normal_event_eviction_without_allocating_in_normal_mode(self):
        result = subprocess.run(['node', '-e', r'''
const assert=require('node:assert/strict'),{Session}=require(process.argv[1]);
const session=Object.create(Session.prototype),events=[];
Object.assign(session,{proof:null,record(type,id,detail){events.push({type,id,...detail});if(events.length>256)events.shift()}});
session.recordNativeRescue('queued','one',{url:'blob:one'});
assert.equal(session.loopRescueProof,undefined);
session.proof={};
for(let i=0;i<20;i++)for(const phase of ['queued','started','committed'])
  session.recordNativeRescue(phase,'one',{url:'blob:one',sourceEpoch:i+1});
for(let i=0;i<300;i++)session.record('resident','one',{});
assert.equal(events.filter(event=>event.type.startsWith('native-loop-rescue-')).length,0);
assert.equal(session.loopRescueProof.queued,20);assert.equal(session.loopRescueProof.committed,20);
assert.equal(session.loopRescueProof.receipts.length,16);assert.equal(session.loopRescueProof.dropped,44);
assert.equal(session.loopRescueProof.receipts.at(-1).sourceEpoch,20);
''', str(fixture.live_tests.LIVE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
