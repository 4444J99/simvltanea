"""Cancelled decoder repairs must not restore superseded slot ownership."""
from __future__ import annotations

import unittest

from simvltanea.browser import test_browser_native_rescue as fixture


class NativeRescueOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.NativeRescueTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.NativeRescueTests.tearDownClass.__func__(cls)

    open = fixture.NativeRescueTests.open
    freeze = fixture.NativeRescueTests.freeze
    queue_behind_permit = fixture.NativeRescueTests.queue_behind_permit

    def hold_hidden_rescue(self, page, slot):
        page.evaluate('''slot => {
          window.node=live.nodes.get(slot);window.outgoing=node.active;
          window.incoming=node.decks.find(deck=>deck!==outgoing);
          window.originalPrime=live.prime.bind(live);
          live.prime=async(...args)=>{
            await originalPrime(...args);
            args[0].media.pause();args[0].media.play=()=>Promise.resolve();
          };
        }''', slot)
        self.freeze(page)
        page.wait_for_function('node.nativeRescue?.incoming && live.handoff')

    def test_removing_a_slot_during_rescue_does_not_resurrect_it_before_readmission(self):
        page = self.open()
        self.hold_hidden_rescue(page, 'loop-4')
        self.assertTrue(page.evaluate('setClips([0,1,2])'))
        page.wait_for_function('!node.nativeRescue && live.activeStandbys===0')
        self.assertTrue(page.evaluate('''!live.nodes.has(node.id) && !node.active && !node.item &&
          node.decks.every(deck=>!deck.url && !deck.media.hasAttribute('src'))'''),
                        'late rescue rollback resurrected the removed resident in its reusable slot')
        page.evaluate('''() => {
          live.prime=originalPrime;
          for(const deck of node.decks)for(const key of ['currentTime','paused','seeking','play'])delete deck.media[key];
        }''')
        self.assertTrue(page.evaluate('setClips([0,1,2,3])'))
        page.wait_for_function('node.active?.progress?.sourceChanges>=2')
        self.assertTrue(page.evaluate('''live.nodes.get(node.id)===node && node.item===items[3] &&
          node.active.url && node.media.hasAttribute('src') && !node.media.paused && live.ready'''))

    def test_same_item_source_reassignment_survives_late_rescue_rollback(self):
        page = self.open()
        self.hold_hidden_rescue(page, 'loop-1')
        self.assertTrue(page.evaluate('''() => {
          const plan=planFor([0,1,2,3]);plan.sources[0].id='source-renamed';
          plan.tracks[0].spans[0].source='source-renamed';
          return live.reconcile({plan,items,playing:true});
        }'''))
        page.wait_for_function('!node.nativeRescue && live.activeStandbys===0')
        self.assertEqual(page.evaluate('node.source'), 'source-renamed',
                         'late rescue rollback overwrote the newly accepted same-item source assignment')
        self.assertTrue(page.evaluate('''node.active===outgoing && node.item===items[0] && !incoming.url &&
          live.sources.get(node.source)?.url===outgoing.url && !live.sources.has('source-1')'''))

    def test_waking_a_resting_failed_source_does_not_leave_recovery_permanently_interrupted(self):
        page = self.open()
        self.queue_behind_permit(page)
        page.evaluate('live.setResting(node.id,true)')
        page.wait_for_function('!node.nativeRescue && outgoing.loopSeek?.attempt?.interrupted')
        page.evaluate('live.setResting(node.id,false);releaseLease();lease')
        page.wait_for_timeout(1500)
        self.assertTrue(page.evaluate('node.active!==outgoing'),
                        'ecological rest cancelled the repair but wake permanently retained its interrupted attempt')
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 1)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)

    def test_presence_update_at_verified_promotion_is_not_lost_by_decoder_transfer(self):
        page = self.open()
        page.evaluate('''() => {
          const promote=live.playPromoted.bind(live);
          live.playPromoted=async(...args)=>{
            const verified=await promote(...args);
            if(args[0]===incoming)live.setPresence(node.id,.73,.21);
            return verified;
          };
        }''')
        self.freeze(page)
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        result = page.evaluate('''({presence:node.active.presence,
          target:node.active.presenceTarget,spectral:node.active.spectralPriority})''')
        self.assertEqual(result, dict(presence=.73, target=.73, spectral=.21),
                         'decoder commit lost a presence update made after its final verified native frames')

    def hold_ordinary_replacement_across_rearm(self, page, action='resume'):
        self.queue_behind_permit(page)
        page.evaluate('''() => {
          items.push({...items[0],name:'replacement',sha256:'5'.repeat(64)});
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{
            const deck=args[0];
            // The failed ordinary successor and the later same-Blob rescue
            // reuse this element. Restore its native play method for rescue.
            if(deck.item!==items[4])delete deck.media.play;
            await prime(...args);
            if(deck.item===items[4]){
              deck.media.pause();deck.media.play=()=>Promise.resolve();
              window.ordinaryPrimeHeld=true;
              await new Promise(resolve=>{window.releaseOrdinaryPrime=resolve});
            }
          };
          window.selected=setClips([4,1,2,3]);releaseLease();
        }''')
        page.wait_for_function('window.ordinaryPrimeHeld && node.busy && !node.nativeRescue')
        # A second explicit resume must retain the same proved cause even
        # after the first ownership change has discarded the old operation.
        for _ in range(2 if action == 'resume' else 1):
            page.evaluate('''action => {
              if(action==='resume'){live.pause();live.start();}
              else {live.setResting(node.id,true);live.setResting(node.id,false);}
            }''', action)
            page.wait_for_function('''node.busy && live.running && !node.resting &&
              outgoing.loopSeek?.generation===live.generation && !outgoing.loopSeek.attempt''')

    def test_busy_resume_or_wake_preserves_failed_seek_until_ordinary_successor_defers(self):
        for action in ('resume', 'wake'):
            with self.subTest(action=action):
                page = self.open()
                try:
                    self.hold_ordinary_replacement_across_rearm(page, action)
                    self.assertFalse(page.evaluate('releaseOrdinaryPrime();selected'))
                    page.wait_for_function('!node.busy && live.activeStandbys===0')
                    page.wait_for_timeout(1800)
                    self.assertTrue(page.evaluate('node.active!==outgoing'),
                                    'busy ownership consumed the failed-seek evidence before the ordinary successor deferred')
                    self.assertTrue(page.evaluate('''node.item===residentBefore.item &&
                      node.birthTime===residentBefore.birth && !node.nativeRescue &&
                      live.events.filter(e=>e.type==='native-loop-seek-recovery').length===2 &&
                      live.events.filter(e=>e.type==='native-loop-rescue-started').length===1'''))
                    self.assertEqual(page.evaluate('live.activeStandbys'), 0)
                finally:
                    page.close()

    def test_outgoing_frames_while_busy_invalidate_rearm_before_an_unproven_later_seek(self):
        page = self.open()
        self.hold_ordinary_replacement_across_rearm(page)
        page.evaluate('''async () => {
          window.beforeBusyProgress=outgoing.progress.sourceChanges;
          const media=outgoing.media;
          for(const name of ['currentTime','paused','seeking','play'])delete media[name];
          await media.play();
        }''')
        # Real source-owned frames must advance while the ordinary successor
        # still holds the slot. No recovery clock or frame observer is replaced.
        page.wait_for_function('''node.busy && outgoing.progress.sourceChanges>=beforeBusyProgress+3 &&
          !outgoing.media.seeking && outgoing.media.currentTime<outgoing.media.duration-.2 &&
          outgoing.loopSeek.decoded===outgoing.decoded.mediaTime''')
        page.evaluate('''() => {
          const media=outgoing.media;HTMLMediaElement.prototype.pause.call(media);let current=1/30;
          Object.defineProperty(media,'currentTime',{configurable:true,get:()=>current,set:v=>{current=v}});
          Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
          Object.defineProperty(media,'seeking',{configurable:true,get:()=>true});
          media.play=()=>Promise.resolve();
        }''')
        # Let any already-dispatched native callback settle while the slot is
        # still ineligible; it cannot be mistaken for a new observed loop seam.
        page.wait_for_timeout(150)
        self.assertTrue(page.evaluate('node.busy && !outgoing.loopSeek.endSeen'))
        self.assertFalse(page.evaluate('releaseOrdinaryPrime();selected'))
        page.wait_for_function('!node.busy && live.activeStandbys===0')
        page.wait_for_timeout(1800)
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url && !incoming.url'),
                        'a new unproven seek reused failed-seek evidence invalidated by real frames during ordinary priming')
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-seek-recovery").length'), 1)
        self.assertEqual(page.evaluate('live.events.filter(e=>e.type==="native-loop-rescue-started").length'), 0)
