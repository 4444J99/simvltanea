"""Diagnostic setup owns options before media admission and preserves real API boundaries."""
from pathlib import Path
import subprocess
import unittest


ADAPTER = Path(__file__).with_name('verify_webkit_seek_adapter.js')


class SeekAdapterTests(unittest.TestCase):
    def run_node(self, body):
        result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict'); const api=require(process.argv[1]);\n" + body,
                                 str(ADAPTER)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_strategy_is_applied_at_assignment_before_initial_media(self):
        self.run_node("""
          for (const pauseBeforeSeek of [false,true]) {
            delete globalThis.compositionRuntime;
            api.installStrategy({pauseBeforeSeek});
            const session={options:{unrelated:17},nodes:new Map()};
            globalThis.compositionRuntime=session;
            assert.equal(session.options.nativeLoopSeekPauseBeforeSeek,pauseBeforeSeek);
            assert.equal(session.options.unrelated,17);
            assert.equal(globalThis.compositionRuntime,session);
            assert.equal(Object.getOwnPropertyDescriptor(globalThis,'compositionRuntime').get,undefined);
            const report=api.strategySnapshot();
            assert.equal(report.pauseBeforeSeek,pauseBeforeSeek);
            assert.equal(report.beforeMedia,true);
            assert.equal(report.standbyRescue,true);
            assert.ok(Number.isFinite(report.assignedAt));
          }
        """)

    def test_control_and_candidate_cannot_silently_disable_production_rescue(self):
        self.run_node("""
          for (const pauseBeforeSeek of [false,true]) {
            delete globalThis.compositionRuntime;
            api.installStrategy({pauseBeforeSeek});
            assert.throws(()=>{globalThis.compositionRuntime={
              options:{nativeLoopStandbyRescue:false},nodes:new Map()};}, /rescue/);
          }
        """)

    def test_physical_isolation_is_preserved_beside_logical_resident_evidence(self):
        self.run_node("""
          const nodes=new Map(Array.from({length:4},(_,index)=>{
            const decks=[{media:{},binding:{}},{media:{},binding:{}}];
            return ['loop-'+(index+1),{box:{},decks,active:decks[0],item:{},source:{},
              birthTime:7,residentIdentity:{}}];
          }));
          globalThis.compositionRuntime={nodes};globalThis.__seekCohort={};
          api.rememberSlots();
          const peer=nodes.get('loop-1');peer.active=peer.decks[1];
          let report=api.isolation('loop-4');
          assert.equal(report.slotsStable,true);assert.equal(report.peersStable,false);
          assert.equal(report.logicalPeersStable,true);
          peer.birthTime++;
          assert.equal(api.isolation('loop-4').logicalPeersStable,false);
          peer.birthTime--;peer.active=peer.decks[0];peer.active.binding={};
          assert.equal(api.isolation('loop-4').logicalPeersStable,false);
        """)

    def test_late_strategy_installation_is_rejected(self):
        self.run_node("""
          globalThis.compositionRuntime={options:{},nodes:new Map()};
          assert.throws(()=>api.installStrategy({pauseBeforeSeek:false}),/before/);
          assert.equal(globalThis.compositionRuntime.options.nativeLoopSeekPauseBeforeSeek,undefined);
        """)

    def test_pinned_admission_checks_manifest_and_full_bytes_before_reconcile(self):
        self.run_node("""
          const crypto=require('node:crypto');globalThis.crypto=crypto.webcrypto;
          const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
          const bytes=Buffer.from('pinned media'), sha256=hash(bytes), id=sha256.slice(0,12);
          const asset={file:'clips/'+id+'.mp4',bytes:bytes.length,width:10,height:20,duration_seconds:1,fps:30};
          const clip={id:'source',variants:{boomerang:asset}};
          const manifest='original exact manifest bytes';
          let wrong=false;
          globalThis.SimvltaneaStudio={FPS:24,libraryClips:()=>[clip,...Array(5).fill({})],
            quantizeDuration:seconds=>({seconds,frames:24,duration:{num:1,den:1}}),audioStream:()=>null};
          globalThis.fetch=async url=>url.endsWith('manifest.json')?{ok:true,text:async()=>manifest}:
            {ok:true,arrayBuffer:async()=>Uint8Array.from(wrong?Buffer.from('other bytes'):bytes).buffer};
          const target={id:'source',role:'target',file:asset.file,sha256};
          globalThis.__seekCohort={};
          (async()=>{
            // Schema parser is real in production; this fixture isolates the byte ownership boundary.
            globalThis.fetch=async url=>url.endsWith('manifest.json')?{ok:true,text:async()=>JSON.stringify({clips:[clip]})}:
              {ok:true,arrayBuffer:async()=>Uint8Array.from(wrong?Buffer.from('other bytes'):bytes).buffer};
            const manifestSha256=hash(JSON.stringify({clips:[clip]}));
            await assert.rejects(api.admitPinned({targets:[target],manifestSha256:'wrong'}),/manifest hash/);
            wrong=true;await assert.rejects(api.admitPinned({targets:[target],manifestSha256}),/hash.size/);
            wrong=false;const receipt=await api.admitPinned({targets:[target],manifestSha256});
            const item=globalThis.__seekCohort.items.get('source');
            assert.ok(item.file instanceof Blob);assert.equal(item.sha256,sha256);
            assert.equal(hash(Buffer.from(await item.file.arrayBuffer())),sha256);
            assert.equal(item.asset,asset);assert.equal(receipt.sources[0].bytes,bytes.length);
          })().catch(error=>{console.error(error);process.exitCode=1;});
        """)

    def test_reconcile_changes_only_requested_admitted_item(self):
        self.run_node("""
          const old=[1,2,3,4].map(index=>({name:'old'+index,sha256:'sha'+index,file:new Blob(['x']),
            quantized:{duration:{num:1,den:1}},audioStream:{codec:'aac',channels:2}}));
          const incoming={...old[3],name:'new',sha256:'newsha',size:99,suffix:'mp4'};
          const plan={sources:old.map((item,index)=>({id:'source-'+(index+1),path:'media/old.mp4'})),
            tracks:old.map((_,index)=>({id:'loop-'+(index+1)})),unchanged:{x:1}};
          let request;
          globalThis.compositionRuntime={plan,nodes:new Map(old.map((item,index)=>['loop-'+(index+1),{item}])),
            reconcile:async value=>{request=value;return true;}};
          globalThis.__seekCohort={items:new Map([['new',incoming]])};
          (async()=>{
            const ok=await api.replacePinned({id:'new',slot:'loop-4'});
            assert.equal(ok,true); assert.equal(request.playing,true); assert.equal(request.atLoopBoundary,true);
            assert.deepEqual(request.items.slice(0,3),old.slice(0,3));assert.equal(request.items[3],incoming);
            assert.equal(request.plan.sources[3].sha256,'newsha');assert.equal(request.plan.sources[3].bytes,99);
            assert.equal(plan.sources[3].sha256,undefined);assert.deepEqual(request.plan.tracks,plan.tracks);
            assert.deepEqual(request.plan.unchanged,{x:1});
          })().catch(error=>{console.error(error);process.exitCode=1;});
        """)

    def test_interventions_require_matching_source_epoch_and_strategy(self):
        self.run_node("""
          const target={id:'clip',slot:'loop-4',sha256:'sha'};
          const event={type:'native-loop-seek-recovery',id:'loop-4',url:'blob:one',sourceEpoch:2,
            wall:100,time:1,strategy:'seek-play'};
          const recovered={...event,type:'native-loop-seek-recovered',wall:200,time:2,attemptedAt:1,decodedChanges:2,seeking:false};
          const row={wall:250,nodes:[{id:'loop-4',item:'clip',sha:'sha',progress:{url:'blob:one',epoch:2}}],
            progressSummary:{nativeLoopSeek:{attempted:1,recovered:1,rejected:0,interrupted:0,
              dropped:0,receipts:[event,recovered]}}};
          const result={cohortOptions:{pauseBeforeSeek:false},prelude:{strategyStart:{assignedAt:10},samples:[row]},samples:[row]};
          // The runtime event ring is clocked just before the authoritative proof receipt.
          result.events=[{...event,wall:99.9},{...recovered,wall:199.9}];
          let report=api.interventions(result,[target]);
          assert.equal(report.pass,true);assert.equal(report.status,'RECOVERY_OBSERVED');
          assert.equal(report.attempts.length,1);assert.equal(report.recoveries.length,1);
          recovered.sourceEpoch=3;report=api.interventions(result,[target]);
          assert.equal(report.recoveries.length,0);assert.equal(report.pass,false);
          recovered.sourceEpoch=2;event.strategy='pause-seek-play';
          assert.equal(api.interventions(result,[target]).pass,false);
          event.strategy='seek-play';event.wall=5;
          assert.equal(api.interventions(result,[target]).attempts.length,0);
          assert.equal(api.interventions(result,[target]).pass,false);
        """)

    def test_zero_attempts_are_not_exercised_and_missing_receipts_fail(self):
        self.run_node("""
          const row={nodes:[],progressSummary:{nativeLoopSeek:{attempted:0,recovered:0,rejected:0,interrupted:0,dropped:0,receipts:[]}}};
          const result={cohortOptions:{pauseBeforeSeek:true},prelude:{strategyStart:{assignedAt:10},samples:[row]},samples:[row]};
          assert.equal(api.interventions(result,[]).status,'NOT_EXERCISED');
          assert.equal(api.interventions(result,[]).pass,true);
          row.progressSummary.nativeLoopSeek.attempted=1;
          assert.equal(api.interventions(result,[]).pass,false);
        """)


if __name__ == '__main__':
    unittest.main()
