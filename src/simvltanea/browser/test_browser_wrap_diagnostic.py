"""Contracts for the separate native wrap experiment, never acceptance gates."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

HARNESS = Path(__file__).with_name('diagnose_webkit_wrap_plateau.js')


def execute(body):
    result = subprocess.run(
        [shutil.which('node') or 'node', '-e',
         'const harness=require(process.argv[1]);\n' + body, str(HARNESS)],
        capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


class WrapDiagnosticTests(unittest.TestCase):
    def test_errors_and_missing_counter_never_report_clean_absence(self):
        result = execute('''
const clean={completed:true,errors:[],sourceErrors:[],events:[],
 observation:{coverageComplete:true,foregroundSlots:['loop-1','loop-2','loop-3','loop-4'],
 nearCoincidentFirstWraps:true,observedOverTwoSeconds:false},
 final:{progressSummary:{nativeLoopSeek:{attempted:0}},decks:[]}};
const classify=harness.classify;
console.log(JSON.stringify({clean:classify(clean),
 page:classify({...clean,errors:['uncaught page error']}),
 source:classify({...clean,sourceErrors:[{wall:100,lastFailure:'media failed'}]}),
 finalSource:classify({...clean,final:{...clean.final,decks:[{nativeError:{code:3}}]}}),
 missing:classify({...clean,completed:false,final:undefined}),
 invalidCounter:classify({...clean,final:{progressSummary:{nativeLoopSeek:{attempted:-1}}}}),
 attempted:classify({...clean,final:{progressSummary:{nativeLoopSeek:{attempted:1}}}})}));
''')
        self.assertEqual(result['clean']['outcome'], 'NOT_REPRODUCED')
        self.assertEqual(result['clean']['guardStatus'], 'NOT_EXERCISED')
        for case in ('page', 'source', 'finalSource'):
            self.assertEqual(result[case]['outcome'], 'DIAGNOSTIC_ERROR', case)
            self.assertFalse(result[case]['coverageComplete'], case)
        self.assertEqual(result['missing']['outcome'], 'SETUP_OR_CAPTURE_FAILED')
        self.assertEqual(result['missing']['guardStatus'], 'UNKNOWN')
        self.assertEqual(result['invalidCounter']['guardStatus'], 'UNKNOWN')
        self.assertEqual(result['attempted']['guardStatus'], 'EXERCISED')

    def test_native_duration_is_fixed_and_non_native_is_explicit(self):
        result = execute('''
const bad=[];
for(const [args,os] of [[['site','out'],'linux'],
 [['site','out','--duration=1'],'darwin'],
 [['site','out','--mechanics','--mechanics'],'darwin']]){
 try{harness.options(args,os);bad.push(false);}catch(_){bad.push(true);}
}
console.log(JSON.stringify({bad,native:harness.options(['site','out'],'darwin'),
 local:harness.options(['site','out','--mechanics'],'linux')}));
''')
        self.assertEqual(result['bad'], [True, True, True])
        self.assertEqual(result['native']['durationMs'], 60000)
        self.assertFalse(result['native']['mechanics'])
        self.assertEqual(result['local']['durationMs'], 8000)
        self.assertTrue(result['local']['mechanics'])

    def test_stale_parked_and_paused_callbacks_cannot_prove_foreground_stalls(self):
        result = execute('''
const source={id:0,slot:'loop-2',deck:0,url:'blob:one',epoch:1};
const row=(wall,time,active=1,paused=0,owner=0)=>
 [wall,wall,0,owner,owner===0?1:0,time,1,wall,wall,0,time,0,paused,4,active,1];
const chunk=(rows)=>({sources:[source],frames:rows.flat(),raf:[0,0,0,0,16,16,.016,.016],droppedFrames:0,droppedRaf:0});
const inspect=rows=>harness.analyseFrames([chunk(rows)]);
console.log(JSON.stringify({
 valid:inspect([row(0,4.7),row(2100,0)]),
 stale:inspect([row(0,4.7),row(2100,0,1,0,1)]),
 parked:inspect([row(0,4.7,0),row(2100,0,0)]),
 paused:inspect([row(0,4.7,1,1),row(2100,0)]),
 stationary:inspect([row(0,0),row(500,0),row(2100,.033)])}));
''')
        self.assertTrue(result['valid']['observedOverTwoSeconds'])
        self.assertTrue(result['valid']['gaps'][0]['resting'])
        self.assertEqual(result['valid']['maxRafGapMs'], 16)
        for case in ('stale', 'parked', 'paused'):
            self.assertFalse(result[case]['observedOverTwoSeconds'], case)
        self.assertEqual(result['stale']['invalidSourceCallbacks'], 1)
        self.assertEqual(result['stationary']['maximumObservedGapMs'], 2100)

    def test_unresolved_tail_requires_the_same_current_foreground_source(self):
        result = execute('''
const source={id:0,slot:'loop-3',deck:1,url:'blob:one',epoch:3};
const chunk={sources:[source],frames:[100,100,0,0,1,0,1,100,100,0,0,0,0,4,1,0],
 raf:[],droppedFrames:0,droppedRaf:0};
const deck={id:'loop-3',deck:1,active:true,paused:false,currentSrc:'blob:one',
 progress:{url:'blob:one',epoch:3}};
const inspect=d=>harness.analyseFrames([chunk],{wall:2201,decks:[d]});
console.log(JSON.stringify({same:inspect(deck),retired:inspect({...deck,active:false}),
 newSource:inspect({...deck,progress:{url:'blob:one',epoch:4}})}));
''')
        self.assertTrue(result['same']['observedOverTwoSeconds'])
        self.assertTrue(result['same']['gaps'][0]['openAtEnd'])
        self.assertFalse(result['retired']['observedOverTwoSeconds'])
        self.assertFalse(result['newSource']['observedOverTwoSeconds'])

    def test_observer_records_registration_epoch_and_bounds_memory(self):
        result = execute('''
let callback,stops=0;
const media={currentSrc:'blob:one',currentTime:0,seeking:false,paused:false,readyState:4,
 requestVideoFrameCallback(fn){callback=fn;return 1;},cancelVideoFrameCallback(){stops++;}};
const deck={media,url:'blob:one',sourceEpoch:1};
const node={id:'loop-1',decks:[deck],active:deck,resting:false};
globalThis.compositionRuntime={slots:new Map([['loop-1',node]]),clock:{simTime:0},audio:{}};
globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
harness.installObservers();
const fire=(n)=>callback(n,{mediaTime:n/30,presentedFrames:n,presentationTime:n,
 expectedDisplayTime:n,processingDuration:.001});
fire(1);deck.sourceEpoch=2;fire(2);fire(3);
const first=__wrapDiagnostic.drain();
for(let i=0;i<4100;i++)fire(i+4);
const bounded=__wrapDiagnostic.drain();__wrapDiagnostic.stop();
console.log(JSON.stringify({first,boundedCount:bounded.frames.length/16,
 dropped:bounded.droppedFrames,additionalSources:bounded.sources.length,stops}));
''')
        first = result['first']
        self.assertEqual([s['epoch'] for s in first['sources']], [1, 2])
        self.assertEqual([first['frames'][i + 4] for i in (0, 16, 32)], [1, 0, 1])
        self.assertEqual(first['frames'][16 + 2:16 + 4], [0, 1])
        self.assertEqual(result['boundedCount'], 4096)
        self.assertEqual(result['dropped'], 4)
        self.assertEqual(result['additionalSources'], 0)
        self.assertEqual(result['stops'], 1)


if __name__ == '__main__':
    unittest.main()
