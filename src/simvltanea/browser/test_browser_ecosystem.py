"""Deterministic behavioral proofs for the Studio's pure ecological scheduler."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ENGINE = HERE / 'browser.ecosystem.js'


def execute(body: str):
    if not ENGINE.is_file():
        raise AssertionError('Studio ecological scheduler has not been implemented')
    program = "const {Engine, criticalSpring} = require(process.argv[1]);\n" + body
    result = subprocess.run([shutil.which('node') or 'node', '-e', program, str(ENGINE)],
                            text=True, capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


class EcosystemTests(unittest.TestCase):
    def test_failed_or_delayed_retirement_does_not_restart_presence(self):
        result = execute('''
const results=[];
for(const reason of ['failed','busy','scarce']) {
  const e=new Engine({seed:1});
  const residents=[{id:'one',clipKey:'old',duration:2,energy:.5,hasAudio:true}];
  e.step(0,0,residents,{manualCount:true});
  const deadline=e.snapshot().residents[0].deadlineAge;
  const options={manualCount:true};
  if(reason==='busy')residents[0].pending=true;
  if(reason==='scarce')options.canReplace=false;
  let out=e.step(deadline,.1,residents,options);
  if(reason==='failed')e.settle(out.requests[0],false,deadline);
  out=e.step(deadline+.1,.1,residents,options);
  results.push({deadline,next:e.snapshot().residents[0].deadlineAge,
    presence:out.presence?out.presence[0]:null,born:e.snapshot().residents[0].born});
}
console.log(JSON.stringify(results));
''')
        for row in result:
            self.assertGreater(row['next'], row['deadline'])
            self.assertEqual(row['presence'], .12)
            self.assertEqual(row['born'], 0)

    def test_single_resident_presence_rises_and_falls_without_normalizing_gain(self):
        result = execute("""
const engine=new Engine({seed:42,maxSlots:4});
const residents=[{id:'a',clipKey:'one',duration:2,age:0,hasAudio:true}];
let out=engine.step(0,0,residents,{manualCount:true});
const deadline=engine.snapshot().residents[0].deadlineAge;
const values=[];
function capture(){values.push({presence:out.presence?out.presence[0]:null,gain:out.gains[0],weight:out.weights[0],snapshot:engine.snapshot().residents[0].presence??null});}
capture();
for(const time of [.6,1.2,(deadline+1.2)/2,deadline,deadline+5]) {
  out=engine.step(time,.1,residents,{manualCount:true}); capture();
}
console.log(JSON.stringify(values));
""")
        for actual, expected in zip(result, [0, .5, 1, .56, .12, .12]):
            self.assertIsNotNone(actual['presence'])
            self.assertAlmostEqual(actual['presence'], expected)
            self.assertAlmostEqual(actual['snapshot'], expected)
            self.assertAlmostEqual(actual['gain'], .85)
            self.assertAlmostEqual(actual['weight'], 1)

    def test_hold_attacks_then_stays_neutral_and_bypass_is_immediate(self):
        result = execute("""
const engine=new Engine({seed:42,maxSlots:2});
const residents=[{id:'a',clipKey:'one',duration:2,age:0,hasAudio:true}];
const held=[0,.6,1.2,100].map(time=>{
  const out=engine.step(time,.1,residents,{enabled:false});
  return {presence:out.presence?out.presence[0]:null,requests:out.requests.length};
});
const bypass=engine.step(101,.1,residents,{enabled:false,effects:false}).presence;
console.log(JSON.stringify({held,bypass:bypass?bypass[0]:null}));
""")
        self.assertEqual([v['presence'] for v in result['held']], [0, .5, 1, 1])
        self.assertEqual([v['requests'] for v in result['held']], [0] * 4)
        self.assertEqual(result['bypass'], 1)

    def test_resting_presence_and_output_array_reuse(self):
        result = execute("""
const engine=new Engine({seed:42,maxSlots:4});
const residents=[{id:'a',duration:2,age:2,hasAudio:true},{id:'b',duration:2,age:2,resting:true}];
const first=engine.step(0,0,residents,{enabled:false});
const arrays=Object.fromEntries(['weights','gains','prominence','space','fatigue','presence'].map(key=>[key,first[key]]));
const awake=first.presence?Array.from(first.presence):null;
const bypass=engine.step(.1,.1,residents,{enabled:false,effects:false});
const bypassed=bypass.presence?Array.from(bypass.presence):null;
const next=engine.step(.2,.1,residents.slice(0,1),{enabled:false});
console.log(JSON.stringify({awake,bypassed,current:next.presence?Array.from(next.presence):null,
  typed:next.presence instanceof Float64Array,
  same:Object.keys(arrays).every(key=>arrays[key]===next[key]),
  snapshot:engine.snapshot().residents.map(r=>r.presence??null)}));
""")
        self.assertEqual(result['awake'], [1, 0, 0, 0])
        self.assertEqual(result['bypassed'], [1, 1, 0, 0])
        self.assertEqual(result['current'], [1, 0, 0, 0])
        self.assertTrue(result['typed'])
        self.assertTrue(result['same'])
        self.assertEqual(result['snapshot'], [1])

    def test_effects_toggle_preserves_ecology_requests_and_seeded_state(self):
        result = execute("""
const on=new Engine({seed:42,maxSlots:4}), off=new Engine({seed:42,maxSlots:4});
const residents=[{id:'a',duration:2,age:0,hasAudio:true},{id:'b',duration:3,age:0,hasAudio:true}];
let equal=true;
for(let i=0;i<500;i++) {
  const a=on.step(i*.1,.1,residents,{manualCount:true});
  const b=off.step(i*.1,.1,residents,{manualCount:true,effects:false});
  for(const key of ['weights','gains','prominence','space','fatigue'])
    equal=equal&&JSON.stringify(Array.from(a[key]))===JSON.stringify(Array.from(b[key]));
  equal=equal&&JSON.stringify(a.requests)===JSON.stringify(b.requests);
  const snapshots=[on.snapshot(),off.snapshot()];
  for(const snapshot of snapshots)for(const resident of snapshot.residents)delete resident.presence;
  equal=equal&&JSON.stringify(snapshots[0])===JSON.stringify(snapshots[1]);
}
console.log(JSON.stringify(equal));
""")
        self.assertTrue(result)

    def test_lifetimes_are_full_loops_with_long_clip_exception(self):
        data = execute('''
          const engine = new Engine({seed: 1});
          engine.step(0, 0, [2, 3.7, 25, 600].map((duration, i) =>
            ({id: String(i), clipKey: 'a', duration, energy: .5, hasAudio: true})), {manualCount: true});
          console.log(JSON.stringify(engine.snapshot().residents));
        ''')
        for state in data:
            self.assertGreaterEqual(state['deadlineAge'], 10)
            self.assertAlmostEqual(state['deadlineAge'] / state['duration'],
                                   round(state['deadlineAge'] / state['duration']))
            self.assertLessEqual(state['deadlineAge'], max(24 + state['duration'], state['duration']))
        self.assertEqual(data[2]['deadlineAge'], 25)
        self.assertEqual(data[3]['deadlineAge'], 600)

    def test_pending_requests_coalesce_and_starvation_extends_one_loop(self):
        data = execute('''
          const e = new Engine({seed: 8});
          const r = [{id:'slot',clipKey:'a',duration:2,energy:.6,hasAudio:true}];
          e.step(0,0,r,{manualCount:true});
          const initial=e.snapshot().residents[0].deadlineAge;
          const request=e.step(initial,.1,r,{manualCount:true}).requests[0];
          const repeated=e.step(initial+.1,.1,r,{manualCount:true}).requests.length;
          e.settle(request,false,initial+.1);
          const extended=e.snapshot().residents[0].deadlineAge;
          const retry=e.step(initial+2,.1,r,{manualCount:true}).requests.length;
          console.log(JSON.stringify({request,repeated,initial,extended,retry}));
        ''')
        self.assertEqual(data['request']['type'], 'replace')
        self.assertEqual(data['repeated'], 0)
        self.assertEqual(data['extended'], data['initial'] + 2)
        self.assertEqual(data['retry'], 1)

    def test_no_replacement_pool_keeps_resident_and_full_loop_clock(self):
        data = execute('''
          const e=new Engine({seed:3});
          const r=[{id:'one',clipKey:'old',duration:3,energy:.5,hasAudio:true}];
          e.step(0,0,r,{manualCount:true});
          const before=e.snapshot().residents[0].deadlineAge;
          const count=e.step(before,.1,r,{manualCount:true,canReplace:false}).requests.length;
          console.log(JSON.stringify({before,count,state:e.snapshot().residents[0]}));
        ''')
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['state']['deadlineAge'], data['before'] + 3)
        self.assertEqual(data['state']['born'], 0)

    def test_new_clip_does_not_inherit_predecessors_age_or_request(self):
        data = execute('''
          const e=new Engine({seed:2});
          const r=[{id:'slot',clipKey:'old',duration:1,energy:.5,hasAudio:true}];
          e.step(0,0,r,{manualCount:true});
          const request=e.step(30,.1,r,{manualCount:true}).requests[0];
          r[0].clipKey='new';
          e.step(30.1,.1,r,{manualCount:true});
          e.settle(request,false,30.2); // late completion from the old resident must have no effect
          const output=e.step(31,.1,r,{manualCount:true});
          console.log(JSON.stringify({count:output.requests.length,state:e.snapshot().residents[0]}));
        ''')
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['state']['clipKey'], 'new')
        self.assertAlmostEqual(data['state']['born'], 30.1)
        self.assertGreaterEqual(data['state']['deadlineAge'], 10)

    def test_seeded_runs_reproduce_decisions_and_never_replace_newborns(self):
        data = execute('''
          function run(seed) {
            const e=new Engine({seed});
            const r=Array.from({length:4},(_,i)=>({id:String(i),clipKey:'a',duration:2+i*.25,
              energy:.3+i*.15,hasAudio:true,born:0}));
            const events=[];
            for(let tick=0;tick<3000;tick++) {
              const now=tick/10;
              for(const req of e.step(now,.1,r,{manualCount:true}).requests) {
                const slot=r[req.index]; events.push([now,req.type,req.id,now-slot.born]);
                slot.clipKey += 'x'; slot.born=now; e.settle(req,true,now);
              }
            }
            return events;
          }
          console.log(JSON.stringify({a:run(15),b:run(15),c:run(16)}));
        ''')
        self.assertEqual(data['a'], data['b'])
        self.assertNotEqual(data['a'], data['c'])
        self.assertGreater(len(data['a']), 20)
        self.assertTrue(all(event[1] == 'replace' and event[3] >= 10 for event in data['a']))
        self.assertTrue(all(b[0] - a[0] >= .19 for a, b in zip(data['a'], data['a'][1:])))

    def test_manual_counts_and_small_pools_never_rest(self):
        data = execute('''
          const violations=[];
          for(const count of [1,2,4,12]) {
            const e=new Engine({seed:10,maxSlots:12});
            const r=Array.from({length:count},(_,i)=>({id:String(i),clipKey:'a',duration:2,
              hasAudio:true,energy:.5}));
            for(let k=0;k<2400;k++) for(const req of e.step(k/10,.1,r,{manualCount:true}).requests) {
              if(req.type!=='replace')violations.push(req); e.settle(req,false,k/10);
            }
          }
          console.log(JSON.stringify(violations));
        ''')
        self.assertEqual(data, [])

    def test_sparse_target_has_correct_stationary_distribution_and_floor(self):
        data = execute('''
          const e=new Engine({seed:42});
          const r=Array.from({length:4},(_,i)=>({id:String(i),clipKey:'a',duration:1,
            hasAudio:true,energy:.5}));
          let sparse=0,three=0,min=4;
          for(let tick=0;tick<200000;tick++) {
            const out=e.step(tick/10,.1,r,{canReplace:false});
            min=Math.min(min,out.desiredActive);
            if(out.regime==='SPARSE_BREATH') {sparse++;if(out.desiredActive===3)three++;}
            for(const request of out.requests)e.settle(request,false,tick/10);
          }
          console.log(JSON.stringify({fraction:three/sparse,min}));
        ''')
        self.assertGreater(data['fraction'], .55)
        self.assertLess(data['fraction'], .65)
        self.assertEqual(data['min'], 2)

    def test_starvation_takes_priority_over_sparse_departures(self):
        data = execute(''' 
          const e=new Engine({seed:42});
          const residents=Array.from({length:4},(_,i)=>({id:String(i),clipKey:'a',duration:1,
            hasAudio:true,energy:.5}));
          const requests=[];
          for(let tick=0;tick<3000;tick++) {
            const out=e.step(tick/10,.1,residents,{canReplace:false});
            for(const req of out.requests) {requests.push(req.type);e.settle(req,false,tick/10);}
          }
          console.log(JSON.stringify(requests));
        ''')
        self.assertEqual(data, [])

    def test_rest_and_wake_preserve_population_floor_and_minimum_rest(self):
        data = execute(''' 
          const e=new Engine({seed:42});
          const r=Array.from({length:4},(_,i)=>({id:String(i),clipKey:'a',duration:1,
            hasAudio:true,energy:.5,resting:false,restStarted:0}));
          let minimum=4, maximumSeamDelay=0; const rests=[], wakes=[];
          for(let tick=0;tick<6000;tick++) {
            const now=tick/10;
            for(const request of e.step(now,.1,r,{}).requests) {
              const resident=r[request.index];
              if(request.type!=='wake') {
                const state=e.snapshot().residents.find(s=>s.id===request.id);
                maximumSeamDelay=Math.max(maximumSeamDelay,state.age-request.plannedAge);
              }
              if(request.type==='rest') {resident.resting=true;resident.restStarted=now;rests.push(now);}
              else if(request.type==='wake') {resident.resting=false;wakes.push(now-resident.restStarted);}
              else resident.clipKey+='x';
              e.settle(request,true,now);
            }
            minimum=Math.min(minimum,r.filter(v=>!v.resting).length);
          }
          console.log(JSON.stringify({minimum,rests,wakes,maximumSeamDelay}));
        ''')
        self.assertEqual(data['minimum'], 2)
        self.assertLessEqual(data['maximumSeamDelay'], .101)
        self.assertGreater(len(data['rests']), 5)
        self.assertGreater(len(data['wakes']), 5)
        self.assertTrue(all(duration >= 4 for duration in data['wakes']))

    def test_silence_and_rest_are_masked_and_coherent_gain_is_bounded(self):
        data = execute('''
          const e=new Engine({seed:12});
          const r=[{id:'a',clipKey:'a',duration:3,energy:1,hasAudio:true},
            {id:'b',clipKey:'a',duration:3,energy:1,hasAudio:false},
            {id:'c',clipKey:'a',duration:3,energy:1,hasAudio:true,resting:true},
            {id:'d',clipKey:'a',duration:3,energy:.3,hasAudio:true}];
          let out;for(let i=0;i<100;i++)out=e.step(i/60,1/60,r,{enabled:false});
          const gains=Array.from(out.gains.slice(0,4));
          const previousArrays=[out.gains,out.prominence,out.space];
          out=e.step(2,.1,r,{enabled:false});
          console.log(JSON.stringify({gains,stable:out.gains===previousArrays[0]&&
            out.prominence===previousArrays[1]&&out.space===previousArrays[2],
            space:Array.from(out.space.slice(0,4))}));
        ''')
        self.assertEqual(data['gains'][1:3], [0, 0])
        self.assertGreater(data['gains'][0], data['gains'][3])
        self.assertLessEqual(sum(data['gains']), .850001)
        self.assertTrue(data['stable'])
        self.assertTrue(all(.45 <= share <= 2.35 for share in data['space']))

    def test_dominance_builds_fatigue_and_suppressed_voice_recovers(self):
        data = execute('''
          const e=new Engine({seed:12});
          const r=[{id:'a',clipKey:'a',duration:60,energy:1,hasAudio:true},
            {id:'b',clipKey:'b',duration:60,energy:.05,hasAudio:true},
            {id:'c',clipKey:'c',duration:60,energy:.05,hasAudio:true},
            {id:'d',clipKey:'d',duration:60,energy:.05,hasAudio:true}];
          for(let i=0;i<600;i++)e.step(i/60,1/60,r,{enabled:false});
          const high=e.snapshot().residents[0].fatigue;
          r[0].energy=0;r[1].energy=1;
          for(let i=600;i<1800;i++)e.step(i/60,1/60,r,{enabled:false});
          const state=e.snapshot().residents;
          console.log(JSON.stringify({high,after:state[0].fatigue,newLeader:state[1].fatigue}));
        ''')
        self.assertGreater(data['high'], .3)
        self.assertLess(data['after'], data['high'])
        self.assertGreater(data['newLeader'], .2)

    def test_critical_spring_is_refresh_independent_and_bounded(self):
        data = execute('''
          const states=[30,60,120].map(rate=>{
            let x=.45,v=0;
            for(let i=0;i<rate*3;i++)[x,v]=criticalSpring(x,v,2.35,1/rate);
            return[x,v];
          });
          console.log(JSON.stringify(states));
        ''')
        for state in data:
            self.assertAlmostEqual(state[0], data[0][0], places=10)
            self.assertAlmostEqual(state[1], data[0][1], places=10)
            self.assertGreaterEqual(state[0], .45)
            self.assertLessEqual(state[0], 2.35)


if __name__ == '__main__':
    unittest.main()
