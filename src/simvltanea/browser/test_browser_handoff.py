"""Owned, bounded freshness/progress monitoring across one incoming handoff."""
from pathlib import Path
import subprocess
import unittest

LIVE = Path(__file__).with_name('browser.live.js')
FIXTURE = r'''
const assert=require('node:assert/strict');
const {Session}=require(process.argv[1]);
let wall=0,serial=0,plays=0;const jobs=new Map();
global.performance={now:()=>wall};global.document={hidden:false};
global.setTimeout=(fn,ms)=>{const id=++serial;jobs.set(id,{fn,at:wall+ms});return id};
global.clearTimeout=id=>jobs.delete(id);
const advance=ms=>{wall+=ms;for(let i=0;i<100;i++){
 const job=[...jobs].find(([,j])=>j.at<=wall);if(!job)return;
 jobs.delete(job[0]);job[1].fn();}throw Error('timer did not settle')};
const media=Object.assign(new EventTarget(),{currentSrc:'blob:incoming',currentTime:0,paused:false,seeking:false,
 readyState:4,error:null,requestVideoFrameCallback(){},play(){plays++;this.paused=false;return Promise.resolve()}});
const outgoing={url:'blob:outgoing'},incoming={url:'blob:incoming',sourceEpoch:1,media,decoded:{mediaTime:0}};
const node={id:'one',active:outgoing};const session=Object.create(Session.prototype);
Object.assign(session,{nodes:new Map([['one',node]]),disposed:false,running:true,generation:1,progressTimeoutMs:2000,
 primeTimeoutMs:1200,proofMaxGapMs:1234,fade:null,promotion:null});
const controller=new AbortController();
const state=session.watchHandoff(node,incoming,outgoing,controller.signal);
const frame=(t,ms=50)=>{wall+=ms;state.observe(wall,t)};
'''

REPLACEMENT = r'''
// Native media delivery is controlled; the production prime, freshness, fade,
// promotion and rollback methods run unchanged. This tests scheduling, not a
// claim about a native decoder's maximum latency on every machine.
state.stop();
const {FrameProgress}=require(process.argv[1]);
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
const beginReplacement=async({isRescue=true,frozen=true,duration=.2}={})=>{
  wall=850;session.clock={simTime:.85};
  const item={file:new Blob(['public clip']),sha256:'a'.repeat(64)},source='source-one';
  const residentIdentity={};
  const oldMedia=Object.assign(new EventTarget(),{currentSrc:'blob:outgoing',currentTime:0,
    paused:false,seeking:frozen,readyState:4,error:null,style:{opacity:'1'},dataset:{loopId:'one'},
    pause(){this.paused=true},removeAttribute(){this.currentSrc=''},load(){}});
  Object.assign(outgoing,{media:oldMedia,sourceEpoch:1,item,weight:1,presence:.42,
    presenceTarget:.42,spectralPriority:.7,enteredAt:0,residentIdentity,
    callbacks:10,decoded:{mediaTime:5.4},progress:new FrameProgress(true)});
  outgoing.progress.assign(outgoing.url,0);outgoing.progress.observe(0,5.4);
  outgoing.progress.setForeground(true,0,true);
  outgoing.loopSeek={id:'one',url:outgoing.url,epoch:1,attempt:{generation:1,
    decoded:5.4,progressed:!frozen,time:.63,strategy:'pause-seek-play'}};
  const callbacks=new Map();let frameId=0;
  Object.assign(media,{style:{opacity:'0'},dataset:{loopId:'one'},
    load(){this.currentSrc=this.src||''},pause(){this.paused=true},
    removeAttribute(){this.src='';this.currentSrc=''},
    requestVideoFrameCallback(fn){const id=++frameId;callbacks.set(id,fn);return id},
    cancelVideoFrameCallback(id){callbacks.delete(id)}});
  Object.assign(incoming,{progress:new FrameProgress(true),weight:0,presence:1,
    presenceTarget:null,spectralPriority:1,enteredAt:null,callbacks:0,decoded:null});
  Object.assign(node,{decks:[outgoing,incoming],media:oldMedia,item,source,
    residentIdentity,birthTime:12,audio:null,box:{style:{}},resting:false});
  let leases=0;
  Object.assign(session,{options:{nativeLoopSeekRecovery:false},audio:{context:null,enabled:false},
    sound:{enabled:false},sources:new Map(),events:[],effectsEnabled:false,
    proof:{},proofAt:Infinity,proofRetired:[],proofRetiredCount:0,proofMaxGapMs:0,
    gate:{async acquire(){assert.equal(leases++,0);return()=>{leases--}}},
    applyLayout(){},applyDeckEffects(){},notifyDeckAudio(){},notifyAudio(){},updateAudio(){},updateNodeAudio(){}});
  const rescue=isRescue?{outgoing,detail:{url:outgoing.url,sourceEpoch:1},
    assert(){assert.equal(node.active,outgoing);assert.equal(session.generation,1)}}:null;
  node.nativeRescue=rescue;
  let outcome;
  const pending=session.replacePrepared(node,item,source,controller.signal,duration,false,rescue,{urgent:isRescue})
    .then(()=>{outcome='committed'},error=>{outcome=error});
  await flush();assert.equal(node.phase,'PRIMING');
  const present=async(t,ms=0)=>{
    advance(ms);session.clock.simTime=wall/1000;media.currentTime=t;
    incoming.decoded={mediaTime:t};incoming.callbacks++;incoming.progress.observe(wall,t);
    incoming.handoff?.observe(wall,t);
    const ready=[...callbacks.values()];callbacks.clear();
    for(const callback of ready)callback(wall,{mediaTime:t});
    await flush();
  };
  const fresh=async()=>{
    // Recorded macOS overrun: last old frame -> first incoming frame1714ms,
    // fresh admission1915ms, retirement2133ms. Remove avoidable fade latency;
    // native CI must still prove the unchanged2000ms limit independently.
    advance(864);await present(0);
    assert.equal(session.fade,null);
    advance(0);await flush();await present(1/30,100);
    assert.equal(session.fade,null,'one incoming frame must not reveal a successor');
    await present(2/30,100);
    assert.ok(session.fade);assert.equal(node.active,outgoing);
  };
  const tick=async(ms)=>{advance(ms);session.clock.simTime=wall/1000;
    session.tick(session.clock.simTime,ms/1000);await flush()};
  return {fresh,present,tick,pending,rescue,item,source,get outcome(){return outcome},get leases(){return leases}};
};
'''


class HandoffMonitorTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(['node', '-e', FIXTURE + '\n(async()=>{' + body +
                                 "\nconsole.log('complete')})().catch(error=>{console.error(error);process.exitCode=1});", str(LIVE)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('complete', result.stdout)

    def test_delayed_frozen_rescue_uses_short_fade_and_still_proves_promoted_frames(self):
        self.run_js(REPLACEMENT + '''const r=await beginReplacement();await r.fresh();
await r.tick(51);
assert.ok(session.promotion,'fresh rescue must stop retaining the frozen picture for the full200ms fade');
assert.equal(node.active,outgoing);assert.equal(r.leases,1);
await r.present(.1,10);assert.equal(node.active,outgoing,'one promoted frame cannot commit');
await r.present(4/30,10);await r.pending;
assert.equal(r.outcome,'committed');assert.equal(node.active,incoming);assert.equal(r.leases,0);
assert.equal(node.item,r.item);assert.equal(node.source,r.source);assert.equal(node.birthTime,12);
assert.equal(r.rescue.committed,true);
const retired=session.proofRetired.find(row=>row.url==='blob:outgoing');
assert.ok(retired.maxGapMs<2000);assert.ok(retired.maxGapMs>=1900,'old gap must not be reset');
const receipt=session.events.find(event=>event.type==='native-loop-rescue-committed');
assert.equal(receipt.admissionChanges,2);assert.equal(receipt.promotionChanges,2);
assert.equal(receipt.admissionSeeking,false);assert.equal(receipt.promotionSeeking,false);
assert.equal(jobs.size,0);''')

    def test_short_rescue_fade_preserves_promotion_failure_rollback(self):
        self.run_js(REPLACEMENT + '''const r=await beginReplacement();await r.fresh();
media.play=()=>Promise.reject(new DOMException('Native playback refused','NotAllowedError'));
await r.tick(51);assert.ok(r.outcome,'failed promotion must settle after the shortened fade');await r.pending;
assert.equal(r.outcome.name,'NotAllowedError');assert.equal(node.active,outgoing);
assert.equal(node.media,outgoing.media);assert.equal(outgoing.url,'blob:outgoing');
assert.equal(outgoing.weight,1);assert.equal(incoming.url,null);assert.equal(r.leases,0);
assert.equal(session.events.some(event=>event.type==='native-loop-rescue-committed'),false);
assert.equal(jobs.size,0);''')

    def test_rescue_shortcut_preserves_ordinary_and_recovered_source_fades(self):
        for options, expected in (
            ('{isRescue:false,frozen:false,duration:1.2}', 1.2),
            ('{isRescue:false,frozen:true,duration:1.2}', .2),
            ('{isRescue:true,frozen:false,duration:.2}', .2),
        ):
            with self.subTest(options=options):
                self.run_js(REPLACEMENT + f'''const r=await beginReplacement({options});await r.fresh();
await r.tick(51);assert.ok(session.fade);assert.equal(session.fade.duration,{expected});
assert.equal(session.promotion,null);assert.equal(node.active,outgoing);
controller.abort();await r.pending;assert.equal(r.outcome.name,'AbortError');
assert.equal(node.active,outgoing);assert.equal(r.leases,0);assert.equal(jobs.size,0);''')

    def test_freshness_needs_two_distinct_nonseeking_frames_and_fulfilled_play(self):
        self.run_js('''let ready=false;state.ready.then(()=>{ready=true},()=>{});
advance(0);await Promise.resolve();assert.equal(plays,1);
media.seeking=true;frame(.1);frame(.2);await Promise.resolve();assert.equal(ready,false);
media.seeking=false;frame(.3);frame(.3);await Promise.resolve();assert.equal(ready,false);
frame(.4);await Promise.resolve();assert.equal(ready,true);state.stop();assert.equal(jobs.size,0);''')

    def test_deadline_crosses_fade_and_promotion_and_cancels_owned_waiters(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;state.phase='fade';const finished=[];
session.fade={incoming,handoff:state,finish(error){finished.push(['fade',error.name]);session.fade=null}};
advance(400);state.phase='promotion';
session.promotion={deck:incoming,handoff:state,finish(error){finished.push(['promotion',error.name]);session.promotion=null}};
advance(400);assert.equal(state.error.name,'DeferredHandoffError');
assert.deepEqual(finished,[['fade','DeferredHandoffError'],['promotion','DeferredHandoffError']]);
assert.equal(session.handoff,null);assert.equal(incoming.handoff,null);assert.equal(jobs.size,0);
assert.equal(session.proofMaxGapMs,1234);frame(.3);assert.equal(jobs.size,0);''')

    def test_visible_pause_excludes_only_paused_time_from_existing_gap(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;state.visible=true;
advance(300);session.running=false;session.generation++;state.pause();advance(10000);
assert.equal(state.error,null);session.running=true;session.generation++;state.resume();
advance(499);assert.equal(state.error,null);advance(1);assert.equal(state.error.name,'DeferredHandoffError');''')

    def test_pause_before_reveal_cancels_hidden_play_task_and_defers(self):
        self.run_js('''session.running=false;session.generation++;state.pause();
session.running=true;session.generation++;state.resume();advance(1000);
assert.equal(plays,0);assert.equal(state.error.name,'DeferredHandoffError');assert.equal(jobs.size,0);''')

    def test_abort_and_reused_epoch_cannot_run_late_hidden_play_or_frame(self):
        self.run_js('''controller.abort();incoming.sourceEpoch++;incoming.url='blob:reused';
advance(1000);frame(.1);assert.equal(plays,0);assert.equal(state.error.name,'AbortError');
assert.equal(incoming.url,'blob:reused');assert.equal(jobs.size,0);''')

    def test_actual_decode_error_is_not_readiness_deferral(self):
        self.run_js('''advance(0);await Promise.resolve();media.error={code:3};media.dispatchEvent(new Event('error'));
assert.equal(state.error.name,'Error');assert.match(state.error.message,/decoded/);assert.equal(jobs.size,0);''')

    def test_decode_error_beats_simultaneous_pause_deferral(self):
        self.run_js('''media.error={code:3};session.running=false;state.pause();
assert.equal(state.error.name,'Error');assert.match(state.error.message,/decoded/);assert.equal(jobs.size,0);''')

    def test_changing_but_seeking_or_paused_frames_cannot_extend_freshness_forever(self):
        for mode in ('seeking', 'paused'):
            with self.subTest(mode=mode):
                self.run_js(f'''advance(0);await Promise.resolve();media.{mode}=true;
for(let i=1;i<=16;i++){{frame(i/30);advance(0)}}
assert.equal(state.error.name,'DeferredHandoffError');
assert.match(state.error.message,/did not become ready/);assert.equal(jobs.size,0);''')

    def test_healthy_visible_fade_can_exceed_freshness_budget_while_frames_advance(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;state.phase='fade';
for(let i=1;i<=40;i++){frame(i/30+.2);advance(0)}
assert.equal(state.error,null);state.stop();assert.equal(jobs.size,0);''')

    def test_late_second_frame_cannot_beat_delayed_freshness_timer(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1,700);frame(.2,150);
await Promise.resolve();assert.equal(state.error.name,'DeferredHandoffError');assert.equal(jobs.size,0);''')

    def test_late_play_resolution_cannot_beat_freshness_deadline_or_decode_error(self):
        self.run_js('''let release;media.play=()=>new Promise(resolve=>{release=resolve});advance(0);
frame(.1);frame(.2);wall=850;release();await Promise.resolve();
assert.equal(state.error.name,'DeferredHandoffError');assert.equal(jobs.size,0);''')
        self.run_js('''let release;media.play=()=>new Promise(resolve=>{release=resolve});advance(0);
frame(.1);frame(.2);media.error={code:3};release();await Promise.resolve();
assert.equal(state.error.name,'Error');assert.equal(jobs.size,0);''')

    def test_pending_hidden_play_has_bounded_freshness_even_with_frames(self):
        self.run_js('''media.play=()=>{plays++;return new Promise(()=>{})};advance(0);
for(let i=1;i<=16;i++){frame(i/30);advance(0)}
assert.equal(plays,1);assert.equal(state.error.name,'DeferredHandoffError');
assert.match(state.error.message,/play did not settle/);assert.equal(jobs.size,0);''')

    def test_owned_promotion_timeout_defers_but_play_rejection_stays_fatal(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;state.phase='promotion';media.play=()=>new Promise(()=>{});
const result=session.playPromoted(incoming,controller.signal,state).catch(error=>error);
for(let i=1;i<=24;i++){frame(.2+i/30);advance(0)}
assert.equal((await result).name,'DeferredHandoffError');assert.equal(jobs.size,0);''')
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;state.phase='promotion';media.play=()=>Promise.reject(new DOMException('Refused','NotAllowedError'));
const result=await session.playPromoted(incoming,controller.signal,state).catch(error=>error);
assert.equal(result.name,'NotAllowedError');state.stop();assert.equal(jobs.size,0);''')

    def test_initial_promotion_timeout_without_outgoing_is_a_hard_error(self):
        self.run_js('''state.stop();media.play=()=>new Promise(()=>{});
const result=session.playPromoted(incoming,controller.signal).catch(error=>error);advance(1200);
assert.equal((await result).name,'Error');assert.equal(jobs.size,0);''')

    def test_promotion_requires_two_consecutive_valid_playing_frames_and_allows_wrap(self):
        for invalid in ('seeking', 'paused', 'nonfinite'):
            with self.subTest(invalid=invalid):
                self.run_js(f'''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;let callback,verified=false;
media.requestVideoFrameCallback=fn=>{{callback=fn;return 1}};
media.cancelVideoFrameCallback=()=>{{callback=null}};
const present=t=>{{const fn=callback;callback=null;fn(wall,{{mediaTime:t}})}};
const result=session.playPromoted(incoming,controller.signal,state).then(value=>{{verified=value}});
await Promise.resolve();present(.3);
const invalid='{invalid}';if(invalid!=='nonfinite')media[invalid]=true;
present(invalid==='nonfinite'?NaN:.4);assert.ok(session.promotion,'invalid frame must not commit promotion');
present(invalid==='nonfinite'?Infinity:.5);
await Promise.resolve();assert.equal(verified,false);
media.seeking=false;media.paused=false;present(.8);await Promise.resolve();assert.equal(verified,false);
present(.8);await Promise.resolve();assert.equal(verified,false);
present(0);await result;assert.equal(verified,true);state.stop();assert.equal(jobs.size,0);''')

    def test_promotion_fulfillment_rechecks_playing_and_source_ownership(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;let callback,release,verified=false;
media.requestVideoFrameCallback=fn=>{callback=fn;return 1};media.cancelVideoFrameCallback=()=>{callback=null};
media.play=()=>new Promise(resolve=>{release=resolve});
const present=t=>{const fn=callback;callback=null;fn(wall,{mediaTime:t})};
const result=session.playPromoted(incoming,controller.signal,state).then(value=>{verified=value});
present(.3);present(.4);media.seeking=true;release();await Promise.resolve();
assert.ok(session.promotion,'play fulfillment while seeking must not commit promotion');assert.equal(verified,false);
media.seeking=false;present(.5);await Promise.resolve();assert.equal(verified,false);
present(.6);await result;assert.equal(verified,true);state.stop();''')
        for lost in ('currentSrc', 'url', 'sourceEpoch', 'generation'):
            with self.subTest(lost=lost):
                self.run_js(f'''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;let callback;
media.requestVideoFrameCallback=fn=>{{callback=fn;return 1}};media.cancelVideoFrameCallback=()=>{{callback=null}};
const result=session.playPromoted(incoming,controller.signal,state).catch(error=>error);await Promise.resolve();
const lost='{lost}';if(lost==='currentSrc')media.currentSrc='blob:other';
else if(lost==='url')incoming.url='blob:other';else if(lost==='sourceEpoch')incoming.sourceEpoch++;else session.generation++;
callback(wall,{{mediaTime:.3}});const error=await result;assert.equal(error.name,'AbortError');state.stop();assert.equal(jobs.size,0);''')

    def test_owned_native_abort_rejections_are_not_transaction_cancellation(self):
        self.run_js('''const nativeError=new DOMException('Native interrupted playback','AbortError');
media.play=()=>Promise.reject(nativeError);advance(0);await Promise.resolve();
assert.equal(state.error.name,'Error');assert.equal(state.error.cause,nativeError);assert.equal(jobs.size,0);''')
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;
state.visible=true;const nativeError=new DOMException('Native interrupted playback','AbortError');
media.play=()=>Promise.reject(nativeError);
const error=await session.playPromoted(incoming,controller.signal,state).catch(error=>error);
assert.equal(error.name,'Error');assert.equal(error.cause,nativeError);state.stop();''')

    def test_late_rejection_after_source_or_generation_loss_cannot_report_new_failure(self):
        self.run_js('''advance(0);await Promise.resolve();frame(.1);frame(.2);await state.ready;state.visible=true;
let reject;media.play=()=>new Promise((_,r)=>{reject=r});
const result=session.playPromoted(incoming,controller.signal,state).catch(error=>error);
session.generation++;reject(new DOMException('Old play','AbortError'));
assert.equal((await result).name,'AbortError');state.stop();assert.equal(jobs.size,0);''')
