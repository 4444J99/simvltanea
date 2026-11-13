"""Retain a witnessed native wrap when the clock outruns decoded frames."""
import subprocess
import unittest

from simvltanea.browser.test_browser_loop_seek import FIXTURE, LIVE


class AdvancingLoopWrapTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(
            ['node', '-e', FIXTURE + body, str(LIVE)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_observed_wrap_repairs_frozen_frames_despite_advancing_clock(self):
        # Native run 42477914946: currentTime .018 -> 1.940, decoded=0,
        # readyState=4, seeking=false, no new callback for 2119 ms.
        for resting in (False, True):
            with self.subTest(resting=resting):
                self.run_js('''
n.resting=RESTING;current(n,.05,.05);progress();
const before={media:n.media,deck:n.active,url:n.active.url,audio:n.audio,
 siblingMedia:sibling.media,siblingDeck:sibling.active,siblingAudio:sibling.audio};
current(n,.018,0);
for(let i=1;i<=5;i++)current(n,.018+i/10,0);
assert.deepEqual(operations,[],'retain the normal stall allowance');
current(n,.618,0);
assert.deepEqual(operations,[{id:'one',op:'pause'},{id:'one',op:'seek',value:1/30},{id:'one',op:'play'}]);
assert.equal(n.media,before.media);assert.equal(n.active,before.deck);
assert.equal(n.active.url,before.url);assert.equal(n.audio,before.audio);
assert.equal(sibling.media,before.siblingMedia);assert.equal(sibling.active,before.siblingDeck);
assert.equal(sibling.audio,before.siblingAudio);assert.equal(sibling.media.paused,false);
const receipt=events.find(e=>e.type==='native-loop-seek-recovery');
assert.equal(receipt.current,.618);assert.equal(receipt.decoded,0);
assert.equal(receipt.seeking,false);assert.equal(receipt.advancingWrap,true);
for(let i=7;i<30;i++)current(n,.018+i/10,0);
assert.equal(plays.length,1,'one repair per witnessed wrap');
'''.replace('RESTING', str(resting).lower()))

    def test_first_post_wrap_frame_consumes_authority(self):
        self.run_js('''
progress();current(n,.018,0);current(n,.08,1/30);
for(let i=1;i<30;i++)current(n,.08+i/10,1/30);
assert.deepEqual(operations,[],'a later midclip stall cannot reuse the wrap');
''')

    def test_advancing_startup_or_midclip_freeze_has_no_wrap_authority(self):
        self.run_js('''
for(const mode of ['startup','midclip','no-end']){
 n.active.sourceEpoch++;operations=[];plays=[];
 if(mode==='midclip'){current(n,1,1);current(n,2,2);current(n,3,3);}
 if(mode==='no-end'){current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);}
 current(n,.018,0);
 for(let i=1;i<30;i++)current(n,.018+i/10,0);
 assert.deepEqual(operations,[],mode);
}
''')

    def test_rest_transition_and_other_ownership_changes_discard_wrap(self):
        self.run_js('''
for(const mode of ['rest','wake','pause','hidden','busy','generation','epoch','source','removed']){
 n.active.sourceEpoch++;n.resting=mode==='wake';current(n,.05,.05);progress();current(n,.018,0);
 current(n,.118,0);operations=[];plays=[];
 if(mode==='rest')n.resting=true;if(mode==='wake')n.resting=false;
 if(mode==='pause')session.running=false;if(mode==='hidden')document.hidden=true;
 if(mode==='busy')n.busy=true;if(mode==='generation')session.generation++;
 if(mode==='epoch')n.active.sourceEpoch++;if(mode==='source')n.media.currentSrc='blob:other';
 if(mode==='removed')session.nodes.delete(n.id);
 current(n,.218,0);
 session.running=true;document.hidden=false;n.busy=false;n.media.currentSrc=n.active.url;session.nodes.set(n.id,n);
 for(let i=3;i<30;i++)current(n,.018+i/10,0);
 assert.deepEqual(operations,[],mode);
}
''')

    def test_delayed_host_tick_and_healthy_wrap_do_not_repair(self):
        self.run_js('''
progress();current(n,.018,0);current(n,.118,0,9);
current(n,.16,1/30);current(n,.20,2/30);
assert.deepEqual(operations,[]);
''')

    def test_interrupted_attempt_does_not_block_a_later_fresh_resting_wrap(self):
        self.run_js('''
progress();current(n,0,0);for(let i=0;i<6;i++)current(n,0,0);
assert.equal(plays.length,1);
n.resting=true;current(n,0,0);
assert.equal(n.active.loopSeek.attempt.interrupted,true);
current(n,.1,.1);current(n,.2,.2);progress();current(n,.018,0);
for(let i=1;i<=6;i++)current(n,.018+i/10,0);
assert.equal(plays.length,2,'a fresh resting wrap owns a new attempt');
''')

    def test_owned_pending_seek_retains_its_budget_during_native_buffering(self):
        for ready in (1, 2):
            with self.subTest(ready=ready):
                self.run_js('''
progress();for(let i=0;i<6;i++)seek();
const attempt=n.active.loopSeek.attempt;
n.media.readyState=READY;current(n,1/30,0);
assert.equal(attempt.interrupted,undefined,'native seek buffering must not cancel its own operation');
assert.ok(attempt.waited>=.1,'buffering must not reset or stop the operation budget');
n.media.readyState=4;n.media.seeking=false;current(n,.05,1/30);current(n,.1,2/30);
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,1);
assert.equal(plays.length,1);
'''.replace('READY', str(ready)))

    def test_buffering_exception_never_admits_or_revives_unowned_seeks(self):
        self.run_js('''
for(const mode of ['no-attempt','zero-ready','nonseeking','paused','hidden','epoch','source','interrupted',
                   'error','generation','busy','rest']){
 n.active.sourceEpoch++;n.media.readyState=4;n.media.seeking=false;n.media.paused=false;
 n.media.error=null;n.busy=false;n.resting=false;
 document.hidden=false;n.media.currentSrc=n.active.url;operations=[];plays=[];progress();
 if(mode!=='no-attempt')for(let i=0;i<6;i++)seek();
 const attempt=n.active.loopSeek.attempt;
 n.media.readyState=mode==='zero-ready'?0:1;n.media.seeking=mode!=='nonseeking';
 if(mode==='paused')n.media.paused=true;if(mode==='hidden')document.hidden=true;
 if(mode==='epoch')n.active.sourceEpoch++;if(mode==='source')n.media.currentSrc='blob:other';
 if(mode==='interrupted')attempt.interrupted=true;
 if(mode==='error')n.media.error={code:3};if(mode==='generation')session.generation++;
 if(mode==='busy')n.busy=true;if(mode==='rest')n.resting=true;
 for(let i=0;i<10;i++)current(n,1/30,0);
 assert.equal(plays.length,mode==='no-attempt'?0:1,mode);
 if(attempt && mode!=='epoch')assert.equal(attempt.interrupted,true,mode);
}
''')

    def test_pending_seek_buffering_still_escalates_at_the_existing_budget(self):
        self.run_js('''
n.active.item.file={};n.item=n.active.item;n.source='source-one';session.crossfadeSec=.2;
let replacements=0;
session.replace=()=>{replacements++;return new Promise(()=>{})};
progress();for(let i=0;i<6;i++)seek();
n.media.readyState=1;current(n,1/30,0);
assert.equal(replacements,0,'the first100ms remains inside native recovery grace');
n.media.readyState=2;current(n,1/30,0);
assert.equal(replacements,1,'buffering must not postpone the200ms rescue budget');
for(let i=0;i<20;i++)current(n,1/30,0);
assert.equal(replacements,1);assert.equal(plays.length,1);
assert.equal(events.filter(e=>e.type==='native-loop-rescue-queued').length,1);
''')


class AdvancingLoopWrapBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        NativeRescueTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        NativeRescueTests.tearDownClass.__func__(cls)

    def test_advancing_clock_repairs_active_and_resting_visible_residents(self):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        for resting in (False, True):
            with self.subTest(resting=resting):
                page = NativeRescueTests.open(self)
                result = None
                try:
                    seam = page.evaluate('''resting => new Promise((resolve,reject) => {
                      live.setResting(node.id,resting);
                      const media=outgoing.media;
                      window.wrapFaultTrace=[];
                      const state=()=>({wall:performance.now(),ready:media.readyState,paused:media.paused,
                        seeking:media.seeking,current:media.currentTime,currentSrc:media.currentSrc,
                        running:live.running,hidden:document.hidden,generation:live.generation,
                        seek:outgoing.loopSeek ? {...outgoing.loopSeek,
                          attempt:outgoing.loopSeek.attempt ? {...outgoing.loopSeek.attempt} : null} : null});
                      const guard=live.recoverNativeLoop.bind(live);
                      live.recoverNativeLoop=(target,time,dt)=>{
                        const before=target===node && window.faultNative && wrapFaultTrace.length<160 ? state() : null;
                        const result=guard(target,time,dt);
                        if(before)wrapFaultTrace.push({before,after:state()});
                        return result;
                      };
                      let done=false;
                      const timer=setTimeout(()=>{done=true;reject(Error('No native first wrap frame'))},7000);
                      const frame=(wall,metadata)=>{
                        if(done)return;
                        const state=outgoing.loopSeek;
                        if(!state?.endSeen || metadata.mediaTime>1/30 || media.readyState<3 ||
                            media.seeking || media.currentSrc!==outgoing.url){
                          media.requestVideoFrameCallback(frame);return;
                        }
                        done=true;clearTimeout(timer);
                        const observed={endSeen:state.endSeen,changes:state.changes,decoded:metadata.mediaTime,
                          ready:media.readyState,seeking:media.seeking,sourceOwned:media.currentSrc===outgoing.url,
                          owned:node.active===outgoing && state.url===outgoing.url};
                        window.faultNative={wall:performance.now(),ready:media.readyState,paused:media.paused,
                          seeking:media.seeking,current:media.currentTime,currentSrc:media.currentSrc,
                          source:outgoing.url,decoded:outgoing.decoded};
                        // The end and first wrapped frame are native. Fault only
                        // this decoder afterward: its clock runs but it emits no
                        // further frames, matching the captured WebKit state.
                        HTMLMediaElement.prototype.pause.call(media);
                        media.cancelVideoFrameCallback(outgoing.frameId);
                        window.faultCallbacks=outgoing.callbacks;
                        let base=.018,anchor=performance.now();
                        Object.defineProperty(media,'currentTime',{configurable:true,
                          get:()=>base+(performance.now()-anchor)/1000,
                          set:value=>{base=value;anchor=performance.now()}});
                        Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
                        Object.defineProperty(media,'seeking',{configurable:true,get:()=>false});
                        media.play=()=>Promise.resolve();resolve(observed);
                      };
                      media.requestVideoFrameCallback(frame);
                    })''', resting)
                    self.assertTrue(seam['endSeen'] and seam['owned'])
                    self.assertGreaterEqual(seam['changes'], 2)
                    self.assertLessEqual(seam['decoded'], 1 / 30)
                    self.assertGreaterEqual(seam['ready'], 3)
                    self.assertFalse(seam['seeking'])
                    self.assertTrue(seam['sourceOwned'])
                    try:
                        page.wait_for_function('node.active!==outgoing && !node.nativeRescue', timeout=5000)
                    except Exception as error:
                        import json
                        self.fail(f'{error}\n' + json.dumps(page.evaluate('''() => ({
                          events:live.events,seek:outgoing.loopSeek,phase:node.phase,resting:node.resting,
                          decoded:outgoing.decoded,current:outgoing.media.currentTime,
                          busy:node.busy,rescue:Boolean(node.nativeRescue)})'''), indent=2))
                    result = page.evaluate('''() => ({
                      resting:node.resting,phase:node.phase,
                      faultCallbacks,finalCallbacks:outgoing.callbacks,
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
                    self.assertEqual(result['resting'], resting)
                    self.assertEqual(result['phase'], 'RESTING' if resting else 'ACTIVE')
                    self.assertEqual(result['faultCallbacks'], result['finalCallbacks'])
                    self.assertTrue(result['same'] and result['graph'] and result['neighbors'])
                    self.assertEqual(result['calls'], [])
                    self.assertEqual((result['permits'], result['maxPermit']), (0, 1))
                    self.assertLess(result['retired']['maxGapMs'], 2000)
                    self.assertTrue(result['seek']['advancingWrap'])
                    self.assertGreater(result['seek']['current'], .5)
                    self.assertGreaterEqual(result['rescue']['admissionChanges'], 2)
                    self.assertGreaterEqual(result['rescue']['promotionChanges'], 2)
                    self.assertFalse(result['rescue']['admissionSeeking'] or result['rescue']['promotionSeeking'])
                finally:
                    import hashlib
                    import json
                    import time
                    from pathlib import Path
                    proof = Path(__file__).resolve().parents[3] / 'var/proofs/advancing-wrap'
                    proof.mkdir(parents=True, exist_ok=True)
                    diagnostic = page.evaluate('''() => ({faultNative:window.faultNative,
                      trace:window.wrapFaultTrace,events:live.events,seek:outgoing.loopSeek,
                      decoded:outgoing.decoded,stillActive:node.active===outgoing})''')
                    diagnostic['runtimeSha256'] = hashlib.sha256(LIVE.read_bytes()).hexdigest()
                    diagnostic['verification'] = result
                    (proof / f'advancing-{resting}-{time.time_ns()}.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
                    page.close()

    def test_wake_or_manual_selection_supersedes_a_queued_resting_rescue(self):
        from simvltanea.browser.test_browser_native_rescue import NativeRescueTests
        for action in ('wake', 'selection'):
            with self.subTest(action=action):
                page = NativeRescueTests.open(self)
                try:
                    page.evaluate('''() => {
                      live.setResting(node.id,true);
                      window.lease=live.withPreparation(()=>new Promise(resolve=>{window.releaseLease=resolve}));
                    }''')
                    page.wait_for_function('typeof releaseLease==="function"')
                    NativeRescueTests.freeze(self, page)
                    page.wait_for_function('Boolean(node.nativeRescue)')
                    self.assertFalse(page.evaluate('Boolean(incoming.url)'))
                    refused = page.evaluate('''action => {
                      window.oldRestRescue=node.nativeRescue;
                      if(action==='wake')live.setResting(node.id,false);
                      else {
                        items.push({...items[0],name:'replacement',sha256:'5'.repeat(64)});
                        window.selected=setClips([4,1,2,3]);
                      }
                      let refused=false;
                      try{oldRestRescue.assert()}catch(error){refused=error.name==='AbortError'}
                      releaseLease();return refused;
                    }''', action)
                    self.assertTrue(refused, 'presence/selection change must invalidate ownership before another tick')
                    if action == 'selection':
                        self.assertTrue(page.evaluate('selected'))
                        self.assertTrue(page.evaluate('node.item===items[4] && !node.nativeRescue'))
                    else:
                        page.wait_for_function('node.active!==outgoing && !node.nativeRescue', timeout=5000)
                        self.assertTrue(page.evaluate('node.item===residentBefore.item && !node.resting'))
                    self.assertFalse(page.evaluate('''live.events.some(event=>
                      event.type==='native-loop-rescue-started' &&
                      event.attemptedAt===oldRestRescue.detail.attemptedAt)'''))
                    self.assertEqual(page.evaluate('live.activeStandbys'), 0)
                    self.assertEqual(page.evaluate('neighborCalls'), [])
                finally:
                    page.close()


class CallbackEndFrameTests(unittest.TestCase):
    """Native run 43474710487: a slow host tick skipped the clip's end window."""

    def run_js(self, body):
        result = subprocess.run(
            ['node', '-e', FIXTURE + body, str(LIVE)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_callback_end_frame_proves_a_seam_the_tick_never_polled(self):
        self.run_js('''
current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);current(n,2.4,2.4);
// No tick observed currentTime in the final two frames, but the frame
// callback delivered the source's last frame before the wrap.
session.noteEndFrame(n.active,4.7666667);
n.active.decoded={mediaTime:4.7666667,wall};
n.media.seeking=true;current(n,0,4.7666667);
for(let i=0;i<5;i++)seek();
assert.deepEqual(operations,[],'the normal 600 ms stall allowance still applies');
seek();
assert.deepEqual(operations,[{id:'one',op:'pause'},{id:'one',op:'seek',value:1/30},{id:'one',op:'play'}]);
assert.equal(sibling.media.paused,false);assert.equal(n.active.url,'blob:one');
''')

    def test_end_frame_then_advancing_clock_with_frozen_frames_repairs(self):
        # The first tick after the skipped window already sees currentTime>0
        # and a changed decoded frame; the callback evidence must not be
        # discarded by that tick's progress reset before wrap detection.
        self.run_js('''
current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);current(n,2.4,2.4);
session.noteEndFrame(n.active,4.7666667);n.active.decoded={mediaTime:4.7666667,wall};
current(n,.018,0);
for(let i=1;i<=5;i++)current(n,.018+i/10,0);
assert.deepEqual(operations,[]);
current(n,.618,0);
assert.deepEqual(operations,[{id:'one',op:'pause'},{id:'one',op:'seek',value:1/30},{id:'one',op:'play'}]);
''')

    def test_capture_requires_the_sources_own_end_frame(self):
        self.run_js('''
session.noteEndFrame(n.active,2.4);assert.equal(n.active.endFrame,undefined);
session.noteEndFrame(n.active,Number.NaN);assert.equal(n.active.endFrame,undefined);
n.media.currentSrc='blob:other';session.noteEndFrame(n.active,4.7666667);
assert.equal(n.active.endFrame,undefined,'a callback from another native source');
n.media.currentSrc='blob:one';session.noteEndFrame(n.active,4.7666667);
assert.deepEqual(n.active.endFrame,{url:'blob:one',epoch:1,mediaTime:4.7666667});
''')

    def test_stale_early_other_epoch_or_healthy_end_frames_have_no_authority(self):
        self.run_js('''
for(const mode of ['none','epoch','early','healthy','suspended']){
 n.active.sourceEpoch++;operations=[];plays=[];n.media.seeking=false;n.active.endFrame=undefined;
 if(mode==='early')session.noteEndFrame(n.active,4.7666667);
 current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);current(n,2.4,2.4);
 if(mode==='epoch'){session.noteEndFrame(n.active,4.7666667);n.active.endFrame.epoch--;}
 if(mode==='suspended'){session.noteEndFrame(n.active,4.7666667);session.running=false;current(n,2.5,2.5);session.running=true;
  assert.equal(n.active.endFrame,null,'reset discards callback evidence');}
 if(mode==='healthy'){session.noteEndFrame(n.active,4.7666667);current(n,4.7,4.7666667);current(n,.05,.05);
  for(let i=0;i<30;i++)current(n,.05+i/10,.05+i/30);}
 else{n.media.seeking=true;current(n,0,mode==='suspended'?2.5:4.7666667);for(let i=0;i<30;i++)seek();}
 assert.deepEqual(operations,[],mode);
}
''')
