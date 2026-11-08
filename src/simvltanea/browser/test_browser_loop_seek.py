"""Experimental source-isolated recovery for an observed native loop seek stall."""
from pathlib import Path
import subprocess
import unittest

LIVE = Path(__file__).with_name('browser.live.js')
FIXTURE = r'''
const assert=require('node:assert/strict');
const {Session}=require(process.argv[1]);
global.document={hidden:false};
let seeks=[],plays=[],events=[],wall=0;
const make=(id='one')=>{
 let current=0;
 const media={duration:4.8,loop:true,paused:false,seeking:false,readyState:4,error:null,currentSrc:'blob:'+id,
  get currentTime(){return current},set currentTime(v){current=v;seeks.push({id,value:v})},
  play(){plays.push(id);return Promise.resolve()},pause(){throw Error('unexpected pause')},load(){throw Error('unexpected load')}};
 const deck={url:'blob:'+id,sourceEpoch:1,media,item:{asset:{fps:30}},decoded:{mediaTime:0,wall:0},binding:{id}};
 return {id,active:deck,media,decks:[deck],audio:deck.binding,resting:false,busy:false,phase:'ACTIVE'};
};
const n=make(),sibling=make('sibling');
const session=Object.create(Session.prototype);
Object.assign(session,{nodes:new Map([['one',n],['sibling',sibling]]),running:true,draining:false,disposed:false,generation:1,record(type,id,detail){events.push({type,id,...detail})}});
const current=(node,v,decoded,dt=.1)=>{node.media.currentTime=v;seeks.pop();if(decoded!==undefined)node.active.decoded={mediaTime:decoded,wall:wall};wall+=dt;session.recoverNativeLoop(node,wall,dt)};
const progress=()=>{current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);current(n,4.78,4.7666667);};
const seek=(dt=.1)=>{n.media.seeking=true;current(n,0,undefined,dt)};
'''

class NativeLoopSeekTests(unittest.TestCase):
    def run_js(self, body):
        result=subprocess.run(['node','-e',FIXTURE+body,str(LIVE)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return result

    def test_true_stall_reseeks_once_without_touching_sibling_or_graph(self):
        self.run_js('''progress();const before={node:sibling,media:sibling.media,deck:sibling.active,audio:sibling.audio};
for(let i=0;i<7;i++)seek();assert.deepEqual(seeks,[{id:'one',value:1/30}]);assert.deepEqual(plays,['one']);
for(let i=0;i<40;i++)seek();assert.equal(plays.length,1);assert.equal(events.filter(e=>e.type==='native-loop-seek-recovery').length,1);
assert.equal(sibling,before.node);assert.equal(sibling.media,before.media);assert.equal(sibling.active,before.deck);assert.equal(sibling.audio,before.audio);
const e=events.find(e=>e.type==='native-loop-seek-recovery');assert.equal(e.sourceEpoch,1);assert.equal(e.url,'blob:one');assert.equal(e.seeking,true);assert.equal(e.current,0);assert.ok(e.stalledSimSec>=.6);
''')

    def test_normal_wrap_and_single_host_gap_never_reseek(self):
        self.run_js('''progress();for(let i=0;i<4;i++)seek();n.media.seeking=false;current(n,.06,.033333);assert.equal(plays.length,0);
progress();seek(9);n.media.seeking=false;current(n,.1,.1);assert.equal(plays.length,0);''')

    def test_pause_hidden_rest_busy_and_removal_do_not_accumulate_a_stall(self):
        self.run_js('''for(const mode of ['pause','hidden','rest','busy','removed']){
 progress();if(mode==='pause')session.running=false;if(mode==='hidden')document.hidden=true;if(mode==='rest')n.resting=true;if(mode==='busy')n.busy=true;if(mode==='removed')session.nodes.delete(n.id);
 for(let i=0;i<20;i++)seek();assert.equal(plays.length,0,mode);
 session.running=true;document.hidden=false;n.resting=false;n.busy=false;session.nodes.set(n.id,n);n.media.seeking=false;current(n,.1,.1);
}''')

    def test_pending_sibling_drain_preserves_seam_stall_and_recovery(self):
        result=self.run_js('''(async()=>{
for(const began of ['before-seam','during-stall']){
 n.active.sourceEpoch++;n.media.seeking=false;seeks=[];plays=[];events=[];
 n.item={sha256:'resident-one'};sibling.item={sha256:'resident-sibling'};
 const identity={media:n.media,deck:n.active,audio:n.audio,url:n.active.url,epoch:n.active.sourceEpoch,
   siblingMedia:sibling.media,siblingDeck:sibling.active,siblingAudio:sibling.audio};
 let release,settled=false;
 const plan={tracks:[{id:n.id},{id:sibling.id}],sources:[{id:'source-one'},{id:'source-sibling'}]};
 Object.assign(session,{slots:new Map(session.nodes),playingIntent:true,revision:1,sources:new Map(),
   applyLayout(){},updateAudio(){},status(){},report(error){throw error},
   pending:{plan,items:[n.item,{sha256:'next-sibling'}],playing:true,revision:1,
     resolve(value){assert.equal(value,true);settled=true}},
   async replace(node){assert.equal(node,sibling);node.busy=true;node.phase='PRIMING';
     try{await new Promise(resolve=>{release=resolve})}finally{node.busy=false;node.phase='ACTIVE'}}});
 if(began==='during-stall'){progress();for(let i=0;i<3;i++)seek();}
 const draining=session.drain();
 assert.equal(session.draining,true);assert.equal(sibling.busy,true);assert.equal(n.busy,false);
 if(began==='before-seam')progress();
 for(let i=0;i<(began==='before-seam'?6:3);i++)seek();
 assert.deepEqual(seeks,[{id:'one',value:1/30}],began);assert.deepEqual(plays,['one'],began);
 assert.equal(settled,false);assert.equal(session.draining,true);
 n.media.seeking=false;current(n,.05,.033333);current(n,.1,.066667);
 const recovered=events.filter(e=>e.type==='native-loop-seek-recovered');
 assert.equal(recovered.length,1);assert.equal(recovered[0].sourceEpoch,identity.epoch);
 assert.equal(recovered[0].url,identity.url);assert.equal(recovered[0].decodedChanges,2);
 assert.equal(n.media,identity.media);assert.equal(n.active,identity.deck);assert.equal(n.audio,identity.audio);
 assert.equal(sibling.media,identity.siblingMedia);assert.equal(sibling.active,identity.siblingDeck);assert.equal(sibling.audio,identity.siblingAudio);
 assert.equal(sibling.busy,true);assert.equal(session.draining,true);
 release();await draining;assert.equal(settled,true);assert.equal(session.draining,false);
}
console.log('sibling-drain-complete');
})().catch(error=>{console.error(error);process.exitCode=1});''')
        self.assertIn('sibling-drain-complete',result.stdout)

    def test_no_unproven_source_or_nonloop_or_error_or_nonzero_seek(self):
        self.run_js('''for(const mode of ['unproven','loop','error','ready','source','midseek']){
 n.active.loopSeek=null;seeks=[];plays=[];if(mode!=='unproven')progress();
 if(mode==='loop')n.media.loop=false;if(mode==='error')n.media.error={code:3};if(mode==='ready')n.media.readyState=1;if(mode==='source')n.media.currentSrc='blob:retired';
 for(let i=0;i<20;i++){n.media.seeking=true;current(n,mode==='midseek'?1:0);}
 assert.equal(plays.length,0,mode);n.media.loop=true;n.media.error=null;n.media.readyState=4;n.media.currentSrc=n.active.url;n.media.seeking=false;
}''')

    def test_native_seam_history_handles_stale_midclip_decoded_position(self):
        self.run_js('''progress();current(n,4.8,.9);for(let i=0;i<7;i++)seek();assert.equal(plays.length,1);''')

    def test_source_epoch_and_resume_invalidate_stale_seam_evidence(self):
        self.run_js('''progress();for(let i=0;i<4;i++)seek();n.active.sourceEpoch++;n.active.url='blob:new';n.media.currentSrc='blob:new';
for(let i=0;i<20;i++)seek();assert.equal(plays.length,0);
n.media.seeking=false;progress();for(let i=0;i<4;i++)seek();session.generation++;
for(let i=0;i<20;i++)seek();assert.equal(plays.length,0);''')

    def test_recovery_requires_two_distinct_nonseeking_frames_and_a_new_seam(self):
        self.run_js('''progress();for(let i=0;i<7;i++)seek();
current(n,.033333,.033333);for(let i=0;i<10;i++)current(n,.033333,.033333);assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,0);
n.media.seeking=false;current(n,.066666,.066666);current(n,.1,.1);
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,1);for(let i=0;i<20;i++)seek();assert.equal(plays.length,1);
n.media.seeking=false;progress();for(let i=0;i<7;i++)seek();assert.equal(plays.length,2);''')

    def test_late_play_rejection_from_retired_source_has_no_effect(self):
        self.run_js('''let reject;n.media.play=()=>{plays.push('one');return new Promise((_,r)=>{reject=r})};
progress();for(let i=0;i<7;i++)seek();n.active.sourceEpoch++;n.active.url='blob:next';n.media.currentSrc='blob:next';
reject(Error('old source'));Promise.resolve().then(()=>assert.equal(events.filter(e=>e.type==='native-loop-seek-play-rejected').length,0));''')

    def test_deliberate_resume_cannot_be_misattributed_as_recovery(self):
        self.run_js('''let reject;n.media.play=()=>{plays.push('one');return new Promise((_,r)=>{reject=r})};
progress();for(let i=0;i<7;i++)seek();session.running=false;session.generation++;seek();
session.running=true;session.generation++;n.media.seeking=false;current(n,.1,.1);current(n,.2,.2);current(n,.3,.3);
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovered').length,0);
reject(Error('paused'));Promise.resolve().then(()=>assert.equal(events.filter(e=>e.type==='native-loop-seek-play-rejected').length,0));''')

    def test_proof_recovery_counts_survive_event_eviction_with_bounded_receipts(self):
        self.run_js('''Object.assign(session,{proof:{},slots:new Map(),proofRetired:[],proofMaxGapMs:0,proofSuspensionCount:0,proofRetiredCount:0});
session.record=(type,id,detail)=>{events.push({type,id,...detail});if(events.length>256)events.shift()};
for(let episode=0;episode<20;episode++){
 n.active.sourceEpoch++;n.media.seeking=false;progress();for(let i=0;i<7;i++)seek();
 n.media.seeking=false;current(n,.1,.1);current(n,.2,.2);
}
for(let i=0;i<300;i++)session.record('resident','one',{});
assert.equal(events.filter(e=>e.type==='native-loop-seek-recovery').length,0);
const summary=session.proofProgressSummary(100000,true).nativeLoopSeek;
assert.equal(summary.attempted,20);assert.equal(summary.recovered,20);assert.equal(summary.receipts.length,16);assert.equal(summary.dropped,24);
assert.equal(session.proofProgressSummary(100000).nativeLoopSeek.receipts.length,0);
assert.equal(summary.receipts.at(-1).sourceEpoch,n.active.sourceEpoch);
''')

    def test_proof_records_rejection_and_interruption_but_normal_mode_allocates_no_receipts(self):
        self.run_js('''session.proof={};n.media.play=()=>{throw Error('refused')};
progress();for(let i=0;i<7;i++)seek();session.running=false;seek();seek();
assert.equal(session.loopSeekProof.attempted,1);assert.equal(session.loopSeekProof.rejected,1);assert.equal(session.loopSeekProof.interrupted,1);
assert.equal(session.loopSeekProof.recovered,0);
session.proof=null;session.loopSeekProof=null;session.recordLoopSeek('native-loop-seek-recovery','one',{});
assert.equal(session.loopSeekProof,null);''')
