"""Decoder rescue preserves a pending Studio export's logical residents."""
from __future__ import annotations

import unittest

from simvltanea.browser import test_browser_studio_settlement as fixture


class StudioNativeRescueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.studio_tests.StudioLibraryTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.studio_tests.StudioLibraryTests.tearDownClass.__func__(cls)

    open = fixture.StudioSettlementTests.open
    snapshot = fixture.StudioSettlementTests.snapshot
    playing = fixture.StudioSettlementTests.playing
    unlock = fixture.StudioSettlementTests.unlock
    ready = fixture.StudioSettlementTests.ready
    settled = fixture.StudioSettlementTests.settled
    defer = fixture.StudioSettlementTests.defer
    edit_two_new_panels = fixture.StudioSettlementTests.edit_two_new_panels
    report = fixture.StudioSettlementTests.report
    assert_plan_matches_residents = fixture.StudioSettlementTests.assert_plan_matches_residents

    def pending_partial_compilation(self, page):
        self.defer(page, 'loop-1')
        page.evaluate('window.holdSettlementRecovery=true')
        self.edit_two_new_panels(page)
        page.wait_for_function('() => settlementHeldCompilers.length === 1', timeout=15000)
        self.assertTrue(page.evaluate('''() => {
          const old=settlementBefore.residents, r=compositionRuntime;
          return r.nodes.get('loop-1').item===old[0].item &&
            r.nodes.get('loop-2').item!==old[1].item && !r.draining;
        }'''), 'the fixture must contain a real partial admission awaiting its corrective compiler')
        page.evaluate('''() => {
          restoreSettlementFault();
          window.exportState='pending';
          compositionIO.plan().then(plan=>{window.requestedExport=plan;exportState='ready'},
            error=>{window.exportError=String(error);exportState='failed'});
          window.rescuedNode=compositionRuntime.nodes.get('loop-3');
          window.rescuedBefore={deck:rescuedNode.active,item:rescuedNode.item,
            source:rescuedNode.source,birth:rescuedNode.birthTime,identity:rescuedNode.residentIdentity};
          // The fixture encodes actual 30 fps video. Supply that source metadata
          // without replacing the production guard or either freshness gate.
          rescuedNode.item.asset={...rescuedNode.item.asset,fps:30};
        }''')

    def rescue_held_resident(self, page):
        # Preserve the real seam evidence across the fault injection, without
        # a second protocol call in which the native loop could already wrap.
        page.evaluate('''() => new Promise((resolve,reject) => {
          let done=false;
          const timer=setTimeout(()=>{done=true;reject(Error('No observed native seam within 7000ms'))},7000);
          const check=()=>{
            if(done)return;
            const media=rescuedBefore.deck.media;
            if(!rescuedBefore.deck.loopSeek?.endSeen || media.seeking){requestAnimationFrame(check);return;}
            done=true;clearTimeout(timer);
            HTMLMediaElement.prototype.pause.call(media);let current=0;
            Object.defineProperty(media,'currentTime',{configurable:true,get:()=>current,set:v=>{current=v}});
            Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
            Object.defineProperty(media,'seeking',{configurable:true,get:()=>true});
            media.play=()=>Promise.resolve();resolve();
          };
          check();
        })''')
        page.wait_for_function('''() => rescuedNode.active!==rescuedBefore.deck && !rescuedNode.busy &&
          compositionRuntime.events.some(e=>e.type==='native-loop-rescue-committed' && e.id===rescuedNode.id)''',
                               timeout=5000)
        self.assertTrue(page.evaluate('''rescuedNode.item===rescuedBefore.item &&
          rescuedNode.source===rescuedBefore.source && rescuedNode.birthTime===rescuedBefore.birth &&
          rescuedNode.residentIdentity===rescuedBefore.identity &&
          rescuedNode.active.residentIdentity===rescuedBefore.identity'''))
        self.assertEqual(page.evaluate('exportState'), 'pending')

    def test_same_resident_rescue_during_corrective_compilation_keeps_export_available(self):
        page = self.ready()
        self.pending_partial_compilation(page)
        self.rescue_held_resident(page)
        page.evaluate('releaseSettlementCompilers()')
        page.wait_for_function("() => exportState!=='pending'", timeout=10000)
        self.assertEqual(page.evaluate('exportState'), 'ready',
                         'verified same-item decoder rescue invalidated the accepted resident cohort')
        self.settled(page)
        result = self.report(page, 'native-rescue-during-settlement')
        self.assert_plan_matches_residents(result)
        self.assertTrue(result['context'] and result['clock'] and result['generation'])
        self.assertIsNone(result['failure'])
        self.assertEqual(result['permits'], 0)

    def test_ordinary_readmission_cannot_inherit_the_repaired_resident_exception(self):
        page = self.ready()
        self.pending_partial_compilation(page)
        # Exercise the ordinary native admission path with identical bytes.
        # It must not obtain the identity exception reserved for a verified
        # decoder repair simply because its digest and slot are unchanged.
        page.evaluate('''async () => {
          const r=compositionRuntime,n=rescuedNode;
          await r.replace(n,n.item,n.source,new AbortController().signal,.2);
        }''')
        self.assertTrue(page.evaluate('''rescuedNode.active!==rescuedBefore.deck &&
          rescuedNode.item===rescuedBefore.item && rescuedNode.source===rescuedBefore.source &&
          rescuedNode.residentIdentity!==rescuedBefore.identity'''))
        page.evaluate('releaseSettlementCompilers()')
        page.wait_for_function("() => exportState!=='pending'", timeout=10000)
        self.assertEqual(page.evaluate('exportState'), 'failed',
                         'an ordinary new admission bypassed the captured physical and logical identity fences')
