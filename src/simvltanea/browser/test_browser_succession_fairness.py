"""Retirement fairness under real admission delays and a five-clip pool."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ENGINE = Path(__file__).with_name('browser.ecosystem.js')


def execute(body):
    result = subprocess.run(
        [shutil.which('node') or 'node', '-e',
         'const {Engine}=require(process.argv[1]);\n' + body, str(ENGINE)],
        capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


class SuccessionFairnessTests(unittest.TestCase):
    def test_distant_long_clip_seam_does_not_reserve_every_other_slot(self):
        result = execute('''
const engine=new Engine({seed:1});
const residents=[
 {id:'long',clipKey:'old',duration:600,age:1200,hasAudio:true},
 {id:'short',clipKey:'young',duration:2,age:100,hasAudio:true,pending:true}
];
engine.step(0,0,residents,{manualCount:true});
residents[1].pending=false;
const requests=engine.step(2.1,.1,residents,{manualCount:true}).requests;
console.log(JSON.stringify({requests,state:engine.snapshot().residents[0]}));
''')
        self.assertEqual(result['state']['deadlineAge'], 1800)
        self.assertGreater(result['state']['deadlineAge'] - result['state']['age'], 590)
        self.assertEqual([r['id'] for r in result['requests']], ['short'])

    def test_failure_requeues_behind_other_debt_and_stale_settle_cannot_restore_it(self):
        result = execute('''
const engine=new Engine({seed:1});
const residents=[
 {id:'older',clipKey:'old',duration:6,age:100,hasAudio:true},
 {id:'younger',clipKey:'young',duration:1,age:30,hasAudio:true}
];
engine.step(0,0,residents,{manualCount:true,enabled:false});
const failed={...engine.step(2,.1,residents,{manualCount:true}).requests[0]};
engine.settle(failed,false,2);
const afterFailure=engine.snapshot().residents[0];
const cooldown=engine.step(3,.1,residents,{manualCount:true}).requests.map(r=>({...r}));
const next=engine.step(4.1,.1,residents,{manualCount:true}).requests.map(r=>({...r}));
residents[0].clipKey='new';residents[0].age=0;
engine.step(4.2,.1,residents,{manualCount:true,enabled:false});
const beforeStale=engine.snapshot().residents[0];
const staleAccepted=engine.settle(failed,false,4.3);
const afterStale=engine.snapshot().residents[0];
engine.step(4.4,.1,residents.slice(1),{manualCount:true,enabled:false});
engine.step(5,.1,residents,{manualCount:true,enabled:false});
console.log(JSON.stringify({failed,afterFailure,cooldown,next,beforeStale,afterStale,
 staleAccepted,readded:engine.snapshot().residents.find(r=>r.id==='older')}));
''')
        self.assertEqual(result['failed']['id'], 'older')
        self.assertEqual(result['afterFailure']['deadlineAge'], 108)
        self.assertEqual(result['afterFailure']['retirementAge'], 108)
        self.assertEqual(result['cooldown'], [])
        self.assertEqual([r['id'] for r in result['next']], ['younger'])
        self.assertFalse(result['staleAccepted'])
        self.assertEqual(result['beforeStale'], result['afterStale'])
        self.assertEqual(result['afterStale']['born'], 4.2)
        self.assertEqual(result['afterStale']['retirementAge'], result['afterStale']['deadlineAge'])
        self.assertEqual(result['readded']['born'], 5)
        self.assertEqual(result['readded']['retirementAge'], result['readded']['deadlineAge'])

    def test_hold_suppresses_requests_and_wake_starts_a_new_retirement_turn(self):
        result = execute('''
const engine=new Engine({seed:1});
const residents=[{id:'one',clipKey:'same',duration:6,age:100,hasAudio:true}];
const counts=[];
for(const time of [0,50])counts.push(engine.step(time,.1,residents,{enabled:false}).requests.length);
residents[0].resting=true;
counts.push(engine.step(51,.1,residents,{enabled:false}).requests.length);
residents[0].resting=false;
counts.push(engine.step(52,.1,residents,{enabled:false}).requests.length);
const awake=engine.snapshot().residents[0];
counts.push(engine.step(53,.1,residents,{manualCount:true}).requests.length);
const due=engine.step(56,.1,residents,{manualCount:true}).requests;
console.log(JSON.stringify({counts,awake,due}));
''')
        self.assertEqual(result['counts'], [0, 0, 0, 0, 0])
        self.assertEqual(result['awake']['deadlineAge'], 156)
        self.assertEqual(result['awake']['retirementAge'], 156)
        self.assertEqual([r['id'] for r in result['due']], ['one'])

    def test_busy_and_unavailable_spare_keep_every_request_blocked(self):
        result = execute('''
const output=[];
for(const reason of ['busy','scarce']) {
 const engine=new Engine({seed:1});
 const residents=[{id:'one',clipKey:'same',duration:6,age:100,hasAudio:true}];
 engine.step(0,0,residents,{enabled:false});
 const initial=engine.snapshot().residents[0];
 const counts=[];
 for(const time of [2,4,6,8]) {
  residents[0].pending=reason==='busy';
  counts.push(engine.step(time,.1,residents,{manualCount:true,canReplace:reason!=='scarce'}).requests.length);
 }
 const state=engine.snapshot().residents[0];
 output.push({reason,initial,state,counts});
}
console.log(JSON.stringify(output));
''')
        for row in result:
            self.assertEqual(row['counts'], [0, 0, 0, 0])
            self.assertEqual(row['state']['retirementAge'], row['initial']['retirementAge'])
            self.assertGreater(row['state']['deadlineAge'], row['initial']['deadlineAge'])
            self.assertAlmostEqual(row['state']['deadlineAge'] / 6,
                                   round(row['state']['deadlineAge'] / 6))

    def test_oldest_retirement_keeps_its_turn_across_a_busy_seam(self):
        result = execute('''
const engine=new Engine({seed:1});
const residents=[
 {id:'older',clipKey:'old',duration:6,age:100,hasAudio:true},
 {id:'younger',clipKey:'young',duration:1,age:30,hasAudio:true,pending:true}
];
engine.step(0,0,residents,{manualCount:true});
const deferred=engine.snapshot();
residents[1].pending=false;
const early=engine.step(1.1,.1,residents,{manualCount:true}).requests.map(r=>({...r}));
const seam=engine.step(2.1,.1,residents,{manualCount:true}).requests.map(r=>({...r}));
console.log(JSON.stringify({deferred,early,seam}));
''')
        self.assertEqual(result['deferred']['residents'][0]['deadlineAge'], 102)
        self.assertEqual(result['early'], [], 'A younger seam must not steal the reserved turn')
        self.assertEqual([r['id'] for r in result['seam']], ['older'])
        self.assertEqual(result['seam'][0]['plannedAge'], 102)

    def test_five_clip_pool_serves_every_slot_despite_ten_second_cooldown(self):
        result = execute('''
const durations=[6+1/3,5.2,5+2/3,5+2/15,3.4];
function run(hz) {
 const engine=new Engine({seed:25}), residents=[], starts=[0,.312,.564,.831];
 const departed=new Map(), events=[], changes=[0,0,0,0], violations=[];
 let handoff=null, manual=false;
 // Four running sources plus one spare. A prepared successor waits for the
 // outgoing whole-loop seam, then fades for1.2s before releasing admission.
 for(let tick=0;tick<=196*hz;tick++) {
  const time=tick/hz;
  for(let i=residents.length;i<4&&time>=starts[i];i++) {
   const clip=i===0?4:i;
   residents.push({id:'loop-'+(i+1),clipKey:'clip-'+clip,duration:durations[clip],
     born:starts[i],resting:false,hasAudio:true,energy:.5});
  }
  // The same public manual handoff shape used by the native held-source
  // prelude, followed by ordinary evolution; no private engine state edits.
  if(!manual&&time>=8.382&&residents.length===4) {
   manual=true; residents[0].clipKey='clip-0';residents[0].duration=durations[0];
   residents[0].born=8.382;departed.set(4,time);
  }
  if(handoff&&time>=handoff.done) {
   const resident=residents[handoff.request.index];
   departed.set(Number(resident.clipKey.slice(5)),time);
   resident.clipKey='clip-'+handoff.fresh;resident.duration=durations[handoff.fresh];
   resident.born=handoff.seam;engine.settle(handoff.request,true,time);
   events.push({time,id:resident.id});changes[handoff.request.index]++;handoff=null;
  }
  const present=new Set(residents.map(r=>Number(r.clipKey.slice(5))));
  const spare=durations.findIndex((_,i)=>!present.has(i)&&
    (!departed.has(i)||time-departed.get(i)>=10));
  for(const resident of residents) {
   resident.age=time-resident.born;resident.pending=Boolean(handoff);
  }
  const out=engine.step(time,1/hz,residents,
    {enabled:time>=15.198,manualCount:true,canReplace:spare>=0&&!handoff});
  for(const request of out.requests) {
   const resident=residents[request.index];
   if(handoff||spare<0||request.type!=='replace'||time-resident.born<10)
     violations.push({time,request});
   if(Math.abs(request.plannedAge/request.duration-Math.round(request.plannedAge/request.duration))>1e-8)
     violations.push({reason:'noninteger loop deadline',request});
   const seam=resident.born+Math.ceil((time+.1-resident.born)/resident.duration)*resident.duration;
   handoff={request,fresh:spare,seam,done:seam+1.2};
  }
 }
 return {hz,changes,events,violations,final:engine.snapshot()};
}
console.log(JSON.stringify([30,60,120].map(run)));
''')
        for run in result:
            with self.subTest(hz=run['hz']):
                self.assertEqual(run['violations'], [])
                self.assertTrue(all(count > 0 for count in run['changes']),
                                f"A continuously playable slot starved: {run['changes']}")


if __name__ == '__main__':
    unittest.main()
