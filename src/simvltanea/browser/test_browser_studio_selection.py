"""Retained resident overrides follow logical slots through selection repair."""
from pathlib import Path
import subprocess
import unittest


STUDIO = Path(__file__).with_name('browser.studio.js')


class StudioRetainedSelectionTests(unittest.TestCase):
    def run_js(self, body):
        script = r'''
const fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8'),api=require(process.argv[1]);
const extract=(start,end)=>{const at=source.indexOf(start);assert.ok(at>=0);const until=source.indexOf(end,at);assert.ok(until>at);return source.slice(at,until)};
const repair=extract('  function repairSelection()', '\n  function fallbackToGenerated');
const bounded=extract('  function boundedSelection(', '\n  // ---- Toast');
const selected=extract('  const selectedItems =', '\n  const itemsReady');
''' + body
        result = subprocess.run(['node', '-e', script, str(STUDIO)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('complete', result.stdout)

    def test_failed_fetch_repair_moves_retained_override_with_its_surviving_clip(self):
        self.run_js(r'''
const run=Function('api','assert',`
const oldB={name:'old-B-variant',sha256:'old-B'};
const sourcePool=[{name:'A-bad'},{name:'new-B-variant',sha256:'new-B'},{name:'C-good',sha256:'C'}];
let selection={family:'strips',loops:[0,1],retained:new Map([[1,oldB]])};
const pool=()=>sourcePool,usingLibrary=()=>true,available=()=>2;
const library={broken:new Set([0])},familyCounts=()=>({strips:[2]}),nearestCount=api.nearestCount;
const moreLoops=(used,count)=>sourcePool.map((_,i)=>i).filter(i=>!used.includes(i)&&!library.broken.has(i)).slice(0,count);
const launch=()=>{throw Error('unexpected launch')},fallbackToGenerated=()=>{throw Error('unexpected fallback')};
let captured;const edited=()=>{captured=selectedItems()};
${selected}\n${repair}
repairSelection();
assert.deepEqual(selection.loops,[1,2]);assert.equal(captured[0],oldB);
assert.equal(captured[1],sourcePool[2]);assert.deepEqual([...selection.retained.keys()],[0]);
assert.equal(sourcePool[1].sha256,'new-B','repair must not overwrite the current library asset');
`);run(api,assert);console.log('complete');
''')

    def test_bounded_shrink_drops_retired_override_before_later_growth(self):
        self.run_js(r'''
const run=Function('api','assert',`
const oldB={name:'old-B'},retiredC={name:'retired-C'};
const sourcePool=[{name:'A'},{name:'new-B'},{name:'new-C'},{name:'D'}];
const pool=()=>sourcePool,available=()=>4,live={maxForeground:2};
const layout={families:{strips:{counts:[1,2,3,4]}}},nearestCount=api.nearestCount;
let selection={family:'strips',loops:[0,1,2],retained:new Map([[1,oldB],[2,retiredC]])};
${selected}\n${bounded}
selection=boundedSelection(selection);
assert.deepEqual(selection.loops,[0,1]);assert.equal(selection.retained.get(1),oldB);
assert.equal(selection.retained.has(2),false,'retired slot override must not survive the device cap');
selection={...selection,loops:[...selection.loops,2]};
assert.equal(selectedItems()[2],sourcePool[2],'a newly added slot must not resurrect the retired source');
`);run(api,assert);console.log('complete');
''')
