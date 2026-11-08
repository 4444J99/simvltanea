"""Native diagnostic observations stay together across asynchronous journaling."""
from pathlib import Path
import subprocess
import unittest


ADAPTER = Path(__file__).with_name('verify_webkit_seek_adapter.js')


FIXTURE = r"""
const assert=require('node:assert/strict');
const api=require(process.argv[1]);
const cohort=require(process.argv[1].replace('verify_webkit_seek_adapter.js','verify_webkit_seek_cohort.js'));
const targets=cohort.TARGETS;
const fixture=globalThis.fixture={wall:0,traces:[],journals:[],sibling:false,turns:0};
Object.defineProperty(globalThis,'performance',{value:{now:()=>fixture.wall},configurable:true});
globalThis.document={hidden:false};
const item=target=>({name:target.id,sha256:target.sha256});
const deck=(target,index)=>({item:target?item(target):null,binding:{},callbacks:3,epoch:1,
  decoded:{mediaTime:.1},changes:3,weight:target?1:0,
  media:{src:target?'blob:'+target.id:'',currentSrc:target?'blob:'+target.id:'',
    currentTime:.1,readyState:target?4:0,paused:!target,seeking:false,error:null,
    hasAttribute(){return Boolean(this.src)}},
  progress:{snapshot(wall,trace){const d=this.deck;return {schema:1,supported:true,live:true,
    url:d.media.src,epoch:d.epoch,changes:d.changes,sourceChanges:d.changes,
    lastChangeWall:wall,mediaTime:d.decoded.mediaTime,foreground:true,running:true,
    currentGapMs:0,maxGapMs:0,lifetimeMaxGapMs:0,...(trace?{trace:[]}: {})}}}});
const initial=['peer-1','peer-2','sibling-resident','predecessor'].map(role=>targets.find(t=>t.role===role));
const nodes=new Map(initial.map((target,index)=>{
  const decks=[deck(target,0),deck(null,1)];decks.forEach(d=>{d.progress.deck=d});
  return ['loop-'+(index+1),{id:'loop-'+(index+1),box:{},decks,active:decks[0],
    item:decks[0].item,source:{},birthTime:0,residentIdentity:{},phase:'ACTIVE'}];
}));
const runtime=globalThis.compositionRuntime={nodes,slots:nodes,options:{nativeLoopSeekPauseBeforeSeek:true},
  nativeLoopRescuePolicy:()=>({...cohort.RESCUE_POLICY}),running:true,maxForeground:4,
  activeStandbys:0,maxConcurrentStandbys:1,audio:{context:{state:'running'}}};
globalThis.__seekCohort={assignedAt:0,pauseBeforeSeek:true,beforeMedia:true};
fixture.tick=()=>{
  fixture.wall+=137;
  for(const node of nodes.values())for(const d of node.decks)if(d.item){
    d.changes++;d.callbacks++;d.decoded.mediaTime=[.1,.3,.05][d.changes%3];
    d.media.currentTime=d.decoded.mediaTime;
  }
};
fixture.native=node=>({id:node.id,item:node.item.name,sha:node.item.sha256,birth:node.birthTime,
  deck:node.decks.indexOf(node.active),decoded:node.active.decoded.mediaTime,
  current:node.active.media.currentTime,callbacks:node.active.callbacks,paused:false,ready:4,
  seeking:false,nativeError:null,progress:node.active.progress.snapshot(fixture.wall,false)});
function sampleFixture(includeTrace){
  fixture.traces.push(includeTrace);fixture.tick();
  if(fixture.sampleFailure&&fixture.sibling)throw Error('capture failed');
  if(fixture.promoteInSample&&fixture.sibling)fixture.finish();
  return {wall:fixture.wall,running:true,hidden:false,audioState:'running',
    foregroundLimit:4,populated:fixture.sibling?5:4,playing:fixture.sibling?5:4,
    standbys:runtime.activeStandbys,maxStandbys:1,nodes:[...runtime.nodes.values()].map(fixture.native),
    progressSummary:{schema:1,supported:true,maxGapMs:0,suspensionCount:0}};
}
fixture.promote=(node,incoming)=>{
  const old=node.active;old.item=null;old.media.src='';old.media.currentSrc='';old.media.paused=true;
  node.active=incoming;node.item=incoming.item;node.source={};node.birthTime=fixture.wall;
  node.residentIdentity={};node.phase='ACTIVE';runtime.activeStandbys=0;
};
fixture.page={evaluate(fn,arg){
  if(fn===api.admitPinned)return Promise.resolve({sources:targets});
  if(fn===api.replacePinned){
    const node=nodes.get(arg.slot),incoming=node.decks.find(d=>d!==node.active);
    incoming.item=item(arg);incoming.media.src=incoming.media.currentSrc='blob:'+arg.id;
    incoming.media.readyState=4;incoming.media.paused=false;runtime.activeStandbys=1;
    if(arg.slot==='loop-4'){fixture.promote(node,incoming);return Promise.resolve(true)}
    fixture.sibling=true;node.phase='CROSSFADING';
    return new Promise(resolve=>{fixture.finish=()=>{fixture.promote(node,incoming);fixture.sibling=false;resolve(true)}});
  }
  try{return Promise.resolve(structuredClone(fn(arg)))}catch(error){return Promise.reject(error)}
}};
fixture.journal={async append(type,row){
  fixture.journals.push({type,row:structuredClone(row)});
  if(type==='diagnostic-prelude-sample'&&fixture.sibling){
    fixture.turns++;await Promise.resolve();
    fixture.onJournal?.();
    // Promotion is a real boundary between separate page evaluations. The
    // observation itself must already have captured the last incoming frame.
    if(fixture.turns===3)fixture.finish();
  }
}};
fixture.prepare=()=>api.prepare(fixture.page,{sample:sampleFixture,pause:async()=>{fixture.wall+=137},
  journal:fixture.journal},targets,{}, {pauseBeforeSeek:true,manifestSha256:'fixture'});
"""


class AtomicSeekCaptureTests(unittest.TestCase):
    def run_node(self, body):
        result = subprocess.run(['node', '-e', FIXTURE + body, str(ADAPTER)],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_promotion_during_journaling_cannot_erase_incoming_observation(self):
        self.run_node(r"""
          (async()=>{
            const result=await fixture.prepare();
            assert.equal(result.siblingOverlap.length,3,'last pre-promotion overlap was lost during journaling');
            assert.equal(result.incomingObservations.length,3);
            assert.ok(result.siblingOverlap.every(row=>row.incoming.item==='99835e485b6e'));
            assert.ok(result.siblingOverlap.every(row=>row.nodes.find(n=>n.id==='loop-3').item==='3ffa0d345ed1'));
            assert.equal(result.afterSibling.nodes.find(n=>n.id==='loop-3').item,'99835e485b6e');
            assert.equal(fixture.journals.filter(x=>x.type==='diagnostic-sibling-incoming').length,3);
            assert.ok(fixture.traces.every(value=>value===true));
            const proof=cohort.coverage({prelude:result,samples:[]},targets);
            assert.equal(proof.overlap.pass,true);assert.equal(proof.overlap.advances,2);
            assert.equal(proof.incomingObservations.pass,true);
          })().catch(error=>{console.error(error);process.exitCode=1});
        """)

    def test_two_observations_still_fail_the_unchanged_overlap_gate(self):
        self.run_node(r"""
          (async()=>{
            const result=await fixture.prepare();
            result.siblingOverlap.pop();
            const proof=cohort.coverage({prelude:result,samples:[]},targets);
            assert.equal(proof.overlap.pass,false);
            assert.equal(proof.checks.siblingIncomingOverlap,false);
          })().catch(error=>{console.error(error);process.exitCode=1});
        """)

    def test_incoming_source_epoch_and_peer_mismatches_remain_observable(self):
        for mutation in ['currentSrc', 'epoch', 'peer']:
            with self.subTest(mutation=mutation):
                self.run_node("const mutation=" + repr(mutation) + r""";
                  fixture.onJournal=()=>{
                    if(fixture.turns!==1)return;
                    const node=compositionRuntime.nodes.get('loop-3');
                    const incoming=node.decks.find(d=>d!==node.active);
                    if(mutation==='currentSrc')incoming.media.currentSrc='blob:foreign';
                    if(mutation==='epoch')incoming.epoch++;
                    if(mutation==='peer'){
                      const peer=compositionRuntime.nodes.get('loop-1');
                      peer.item=peer.active.item={name:'foreign',sha256:'foreign'};
                    }
                  };
                  (async()=>{
                    const result=await fixture.prepare();
                    assert.equal(result.incomingObservations.length,3,'invalid raw observations were dropped');
                    const proof=cohort.coverage({prelude:result,samples:[]},targets);
                    assert.equal(proof.incomingObservations.pass,false);
                    assert.equal(proof.checks.siblingIncomingOverlap,false);
                  })().catch(error=>{console.error(error);process.exitCode=1});
                """)

    def test_a_promoted_deck_does_not_invent_an_incoming_snapshot(self):
        self.run_node(r"""
          fixture.promoteInSample=true;
          (async()=>{
            const result=await fixture.prepare();
            assert.equal(result.incomingObservations.length,0);
            assert.equal(result.siblingOverlap.length,0);
            assert.equal(fixture.journals.filter(x=>x.type==='diagnostic-sibling-incoming').length,0);
          })().catch(error=>{console.error(error);process.exitCode=1});
        """)

    def test_capture_errors_propagate_without_false_incoming_evidence(self):
        self.run_node(r"""
          fixture.sampleFailure=true;
          (async()=>{
            await assert.rejects(fixture.prepare(),/capture failed/);
            assert.equal(fixture.journals.filter(x=>x.type==='diagnostic-sibling-incoming').length,0);
          })().catch(error=>{console.error(error);process.exitCode=1});
        """)


if __name__ == '__main__':
    unittest.main()
