"""A decoder repair is not a new logical resident in the native verdict."""
import json
from pathlib import Path
import subprocess
import unittest


class LogicalSuccessionTests(unittest.TestCase):
    def test_same_resident_decoder_repairs_cannot_satisfy_natural_succession(self):
        program = r'''
const {analyse} = require(process.argv[1]);
const samples = Array.from({length: 1300}, (_, index) => ({
  wall: index * 140, running: true, hidden: false, audioState: 'running',
  foregroundLimit: 4, populated: 4, playing: 4, standbys: 0, maxStandbys: 1,
  nodes: Array.from({length: 4}, (_, slot) => ({
    id: `loop-${slot + 1}`, item: `clip-${slot}`, sha: `sha-${slot}`, birth: 0,
    deck: index < 500 ? 0 : 1, current: (index % 20) / 10, decoded: (index % 20) / 10,
    callbacks: index, paused: false, resting: false, phase: 'ACTIVE', ready: 4,
  })),
}));
const result = {completed: true, elapsedMs: 182000, samples, coarse: [], errors: [],
  httpErrors: [], consoleErrors: [], requestFailures: [], events: []};
const repair = analyse(result);
for (const row of samples.slice(500)) for (const node of row.nodes) {
  node.birth = 70; node.item += '-successor'; node.sha += '-successor';
}
const succession = analyse(result);
console.log(JSON.stringify({repair: {births: repair.births, changedSlots: repair.changedSlots,
  succession: repair.checks.succession}, succession: {births: succession.births,
  changedSlots: succession.changedSlots, succession: succession.checks.succession}}));
'''
        result = subprocess.run(['node', '-e', program,
                                 str(Path(__file__).with_name('verify_webkit_sustained.js'))],
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['repair'], {'births': 4, 'changedSlots': [], 'succession': False})
        self.assertEqual(report['succession'], {'births': 8,
                         'changedSlots': ['loop-1', 'loop-2', 'loop-3', 'loop-4'], 'succession': True})
