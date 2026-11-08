"""Recover an observed loop-boundary freeze even when WebKit reports no seek."""
import subprocess
import unittest

from simvltanea.browser.test_browser_loop_seek import FIXTURE, LIVE


class UnflaggedLoopWrapTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(
            ['node', '-e', FIXTURE + body, str(LIVE)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_decoded_zero_at_proven_wrap_recovers_without_seeking_flag(self):
        # d2 native fresh/held captures both reach decoded=current=0 with
        # seeking=false after an observed end, then remain frozen for seconds.
        self.run_js('''
progress();
const original={media:n.media,deck:n.active,audio:n.audio,url:n.active.url,
 siblingMedia:sibling.media,siblingDeck:sibling.active,siblingAudio:sibling.audio};
n.media.seeking=false;current(n,0,0);
for(let i=0;i<5;i++)current(n,0,0);
assert.deepEqual(operations,[],'the existing stall allowance is still required');
current(n,0,0);
assert.deepEqual(operations,[{id:'one',op:'pause'},{id:'one',op:'seek',value:1/30},{id:'one',op:'play'}]);
assert.equal(n.media,original.media);assert.equal(n.active,original.deck);assert.equal(n.audio,original.audio);
assert.equal(n.active.url,original.url);assert.equal(sibling.media,original.siblingMedia);
assert.equal(sibling.active,original.siblingDeck);assert.equal(sibling.audio,original.siblingAudio);
assert.equal(sibling.media.paused,false);
const receipt=events.find(e=>e.type==='native-loop-seek-recovery');
assert.equal(receipt.seeking,false);assert.equal(receipt.current,0);assert.equal(receipt.decoded,0);
assert.equal(receipt.priorSeamCurrent,4.78);assert.ok(receipt.stalledSimSec>=.6);
for(let i=0;i<20;i++)current(n,0,0);
assert.equal(plays.length,1,'one operation per stalled seam');
''')

    def test_false_seeking_startup_and_midclip_stalls_have_no_seam_authority(self):
        self.run_js('''
for(const mode of ['startup','midclip','stale-end']){
 n.active.sourceEpoch++;n.media.seeking=false;operations=[];plays=[];
 if(mode==='midclip'){current(n,1,1);current(n,2,2);current(n,3,3);}
 if(mode==='stale-end'){progress();current(n,.1,.1);current(n,.2,.2);}
 for(let i=0;i<20;i++)current(n,0,0);
 assert.equal(plays.length,0,mode);assert.deepEqual(operations,[],mode);
}
''')

    def test_healthy_false_seeking_wrap_and_single_delayed_tick_do_not_recover(self):
        self.run_js('''
progress();current(n,0,0);for(let i=0;i<4;i++)current(n,0,0);
current(n,.04,1/30);current(n,.08,2/30);
assert.equal(plays.length,0);
progress();current(n,0,0);current(n,0,0,9);
current(n,.04,1/30);assert.equal(plays.length,0);
''')

    def test_changing_decoded_frames_at_zero_never_accumulate_a_stall(self):
        self.run_js('''
progress();current(n,0,0);
for(let i=1;i<=30;i++)current(n,0,i/30);
assert.equal(plays.length,0);assert.deepEqual(operations,[]);
''')

    def test_false_seeking_guard_obeys_pause_hidden_rest_busy_and_source_ownership(self):
        self.run_js('''
for(const mode of ['pause','hidden','rest','busy','removed','source','ready','error','nonloop']){
 n.active.sourceEpoch++;n.media.seeking=false;operations=[];plays=[];progress();current(n,0,0);
 if(mode==='pause')session.running=false;if(mode==='hidden')document.hidden=true;
 if(mode==='rest')n.resting=true;if(mode==='busy')n.busy=true;
 if(mode==='removed')session.nodes.delete(n.id);if(mode==='source')n.media.currentSrc='blob:other';
 if(mode==='ready')n.media.readyState=1;if(mode==='error')n.media.error={code:3};if(mode==='nonloop')n.media.loop=false;
 for(let i=0;i<20;i++)current(n,0,0);
 assert.equal(plays.length,0,mode);assert.deepEqual(operations,[],mode);
 session.running=true;document.hidden=false;n.resting=false;n.busy=false;session.nodes.set(n.id,n);
 n.media.currentSrc=n.active.url;n.media.readyState=4;n.media.error=null;n.media.loop=true;
}
''')

    def test_source_epoch_and_resume_discard_false_seeking_seam_history(self):
        self.run_js('''
for(const mode of ['epoch','generation']){
 n.active.sourceEpoch++;n.media.seeking=false;operations=[];plays=[];progress();current(n,0,0);
 for(let i=0;i<4;i++)current(n,0,0);
 if(mode==='epoch')n.active.sourceEpoch++;else session.generation++;
 for(let i=0;i<20;i++)current(n,0,0);
 assert.equal(plays.length,0,mode);assert.deepEqual(operations,[],mode);
}
''')

    def test_false_seeking_recovery_requires_two_frames_and_new_seam(self):
        self.run_js('''
progress();current(n,0,0);for(let i=0;i<6;i++)current(n,0,0);
assert.equal(plays.length,1);
current(n,1/30,1/30);
for(let i=0;i<10;i++)current(n,1/30,1/30);
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,0);
current(n,2/30,2/30);
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,1);
for(let i=0;i<20;i++)current(n,0,0);
assert.equal(plays.length,1,'old seam cannot authorize a second repair');
progress();current(n,0,0);for(let i=0;i<6;i++)current(n,0,0);
assert.equal(plays.length,2);
''')

    def test_sibling_preparation_does_not_disable_false_seeking_recovery(self):
        self.run_js('''
session.draining=true;sibling.busy=true;sibling.phase='PRIMING';
progress();current(n,0,0);for(let i=0;i<6;i++)current(n,0,0);
assert.equal(plays.length,1);assert.equal(sibling.busy,true);assert.equal(session.draining,true);
assert.equal(sibling.phase,'PRIMING');assert.deepEqual(pauses,['one']);
''')


class UnflaggedLoopWrapBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        NativeRescueTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        NativeRescueTests.tearDownClass.__func__(cls)

    def test_unflagged_frozen_wrap_repairs_one_real_slot_and_keeps_siblings_playing(self):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        page = NativeRescueTests.open(self)
        seam = page.evaluate('''() => new Promise((resolve,reject) => {
          let done=false;
          const timer=setTimeout(()=>{done=true;reject(Error('No observed native seam'))},7000);
          const check=()=>{
            if(done)return;
            const media=outgoing.media,state=outgoing.loopSeek;
            if(!state?.endSeen || media.seeking){requestAnimationFrame(check);return;}
            done=true;clearTimeout(timer);
            const observed={endSeen:state.endSeen,changes:state.changes,current:media.currentTime,
              owned:node.active===outgoing && state.url===outgoing.url};
            HTMLMediaElement.prototype.pause.call(media);
            let current=0;
            Object.defineProperty(media,'currentTime',{configurable:true,get:()=>current,set:v=>{current=v}});
            Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
            Object.defineProperty(media,'seeking',{configurable:true,get:()=>false});
            media.play=()=>Promise.resolve();resolve(observed);
          };check();
        })''')
        self.assertTrue(seam['endSeen'] and seam['owned'])
        self.assertGreaterEqual(seam['changes'], 2)
        # Observe completed ownership, then assert the native retirement gap.
        # A controller poll before 2 s must not reject a valid later commit.
        page.wait_for_function('node.active!==outgoing', timeout=5000)
        result = page.evaluate('''() => ({
          repaired:node.active!==outgoing,
          same:node.item===residentBefore.item && node.source===residentBefore.source &&
            node.birthTime===residentBefore.birth,
          graph:live.audio.context===residentBefore.context && live.master===residentBefore.master,
          neighbors:neighbors.every(row=>row.node.active===row.deck && row.node.media===row.media &&
            row.deck.url===row.url && row.node.audio===row.binding && row.node.callbacks>row.frames),
          calls:neighborCalls,permits:live.activeStandbys,maxPermit:live.maxConcurrentStandbys,
          retired:live.proofRetired.find(row=>row.url===before.url),
          seek:live.proofProgressSummary(performance.now(),true).nativeLoopSeek.receipts.find(
            row=>row.type==='native-loop-seek-recovery'),
          rescue:live.proofProgressSummary(performance.now(),true).nativeLoopRescue.receipts.find(
            row=>row.type==='native-loop-rescue-committed')})''')
        self.assertTrue(result['repaired'], 'seeking=false left the proved wrap frozen indefinitely')
        self.assertTrue(result['same'] and result['graph'] and result['neighbors'])
        self.assertEqual(result['calls'], [])
        self.assertEqual((result['permits'], result['maxPermit']), (0, 1))
        self.assertLess(result['retired']['maxGapMs'], 2000)
        self.assertFalse(result['seek']['seeking'])
        self.assertGreaterEqual(result['rescue']['admissionChanges'], 2)
        self.assertGreaterEqual(result['rescue']['promotionChanges'], 2)
        self.assertFalse(result['rescue']['admissionSeeking'] or result['rescue']['promotionSeeking'])
        from pathlib import Path
        import json
        proof = Path(__file__).resolve().parents[3] / 'var/proofs/native-unflagged-wrap'
        proof.mkdir(parents=True, exist_ok=True)
        (proof / 'browser-result.json').write_text(json.dumps(result, indent=2) + '\n')
