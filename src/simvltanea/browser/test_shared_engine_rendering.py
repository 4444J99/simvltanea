"""Exercise the real runtime's frame transforms in a small DOM fixture.

This is a Node logic tier, not browser, decoded-media or hardware acceptance.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class RenderedPoseTest(unittest.TestCase):
    def test_visible_transforms_and_snapshot_share_one_rendered_pose(self):
        runtime = Path(__file__).with_name('browser.runtime.js')
        adapter = Path(__file__).with_name('shared_engine_adapter.js')
        script = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const stage = {dataset:{}, addEventListener(){}};
const context = vm.createContext({
  window:{}, document:{querySelector(){return stage;}},
  performance:{now(){return 99000;}},
  ResizeObserver:class {observe(){}}, fetch(){return new Promise(()=>{});},
  setTimeout, clearTimeout, URL, Blob, console,
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
vm.runInContext(`
  window.__sharedEngineReceipt = {release:'accepted-release'};
  window.SharedEngine = {evaluateSpatialScore(score, t) {
    const block=score.blocks[0];
    return {azimuth:block.azimuthStart+t*0.1, elevation:0.1, fov:1};
  }};
  const makeNode = (id) => ({id,span:{},media:{style:{}},box:{getBoundingClientRect(){return {toJSON(){return {};}}}}});
  runtime.nodes.set('a',makeNode('a')); runtime.nodes.set('b',makeNode('b'));
  const a={loop:'a',focal:['1/2','1/2']}, b={loop:'b',focal:['1/2','1/2']};
  runtime.plan={fps:24,frames:240,tracks:[{id:'a'},{id:'b'}],
    layout_keyframes:[{layouts:{landscape:{cells:[a,b]},portrait:{cells:[b,a]}}}]};
  runtime.orientation='landscape';
  installPanelDriver(runtime.plan.layout_keyframes[0].layouts.landscape);
  applyPanelOrientation(2);
  const positions=[runtime.nodes.get('a').media.style.objectPosition,runtime.nodes.get('b').media.style.objectPosition];
  if(!(parseFloat(positions[0])<50))throw Error('positive azimuth must move source focal point left');
  if(!(parseFloat(positions[0].split(' ')[1])<50))throw Error('positive elevation must move source focal point up');
  runtime.orientation='portrait'; applyPanelOrientation(2);
  if(JSON.stringify(positions)!==JSON.stringify([runtime.nodes.get('a').media.style.objectPosition,runtime.nodes.get('b').media.style.objectPosition]))
    throw Error('orientation reordered loop identity');
  const snapshot=runtime.snapshot();
  if(snapshot.sharedEngine.renderedTime!==2 || snapshot.compositionTime===2)throw Error('snapshot must retain rendered time rather than transport time');
  if(snapshot.sharedEngine.build!=='shared-engine@time-moment-brief/accepted-release')throw Error('stale build receipt');
  const paused=JSON.stringify(snapshot.sharedEngine.poses);
  runtime.position=7;
  if(JSON.stringify(runtime.snapshot().sharedEngine.poses)!==paused)throw Error('snapshot reevaluated an unapplied pose');
  const node=runtime.nodes.get('a');node.span.slice_rect=['1/4','1/4','1/2','1/2'];
  applySlice(node); const initial=node.media.style.left;
  applyPanelOrientation(2);
  if(node.media.style.left===initial)throw Error('slice transform ignored pose');
  const offset2=node.media.style.left;
  applyPanelOrientation(3);
  if(node.media.style.left===offset2)throw Error('slice did not continue moving');
  const x=-parseFloat(node.media.style.left)*0.5/100;
  if(x<0 || x>0.5)throw Error('slice escaped source bounds');
  if(node.media.style.marginTop!=='0' || !node.media.style.top.endsWith('%'))throw Error('slice vertical offset must use height-relative top');
  console.log(JSON.stringify({direction:true,identity:true,snapshot:true,slice:true,release:true}));
`,context);
'''
        result = subprocess.run(['node', '-e', script, str(runtime), str(adapter)],
                                check=True, capture_output=True, text=True, timeout=30)
        self.assertTrue(all(json.loads(result.stdout).values()))
