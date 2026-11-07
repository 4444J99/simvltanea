"""Behavioral proofs for the pure clip presence envelope and filter targets."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
PRESENCE = HERE / 'browser.presence.js'


def execute(body: str):
    if not PRESENCE.is_file():
        raise AssertionError('Clip presence helper has not been implemented')
    result = subprocess.run(
        [shutil.which('node') or 'node', '-e',
         "const api = require(process.argv[1]); const {ATTACK_SECONDS, presenceEnvelope, filterTargets} = api;\n" + body,
         str(PRESENCE)], text=True, capture_output=True, timeout=30, check=True,
    )
    return json.loads(result.stdout)


class PresenceTests(unittest.TestCase):
    def test_attack_peak_release_and_waiting_tail(self):
        result = execute("console.log(JSON.stringify({attack:ATTACK_SECONDS, values:[-1,0,.3,.6,1.2,5.6,10,100].map(age=>presenceEnvelope(age,10))}));")
        self.assertEqual(result['attack'], 1.2)
        for actual, expected in zip(result['values'], [0, 0, .25, .5, 1, .56, .12, .12]):
            self.assertAlmostEqual(actual, expected)

    def test_short_lifetime_has_an_early_peak(self):
        result = execute("console.log(JSON.stringify([0,.25,.5,.75,1,2].map(age=>presenceEnvelope(age,1))));")
        for actual, expected in zip(result, [0, .5, 1, .56, .12, .12]):
            self.assertAlmostEqual(actual, expected)

    def test_invalid_inputs_and_extreme_lifetimes_stay_bounded(self):
        result = execute("""
const invalid = [NaN, Infinity, -Infinity, undefined, null, '1'];
console.log(JSON.stringify({
  invalidAges: invalid.map(age=>presenceEnvelope(age,10)),
  fallbackPeaks: [...invalid,0,-1].map(lifetime=>presenceEnvelope(1.2,lifetime)),
  fallbackTails: [...invalid,0,-1].map(lifetime=>presenceEnvelope(2.4,lifetime)),
  tiny: presenceEnvelope(Number.MIN_VALUE,Number.MIN_VALUE),
  huge: presenceEnvelope(Number.MAX_VALUE/2,Number.MAX_VALUE)
}));
""")
        self.assertEqual(result['invalidAges'], [0] * 6)
        self.assertEqual(result['fallbackPeaks'], [1] * 8)
        self.assertEqual(result['fallbackTails'], [.12] * 8)
        self.assertEqual(result['tiny'], .12)
        self.assertTrue(0 <= result['huge'] <= 1)

    def test_filter_endpoints_and_exponential_midpoint(self):
        result = execute("console.log(JSON.stringify([0,.5,1].map(p=>filterTargets(p))));")
        for actual, expected in zip(result, [
            {'gain': 0, 'cutoffHz': 420, 'brightness': .55, 'saturation': .3, 'blurPx': 2},
            {'gain': .5, 'cutoffHz': (420 * 16000) ** .5, 'brightness': .775, 'saturation': .65, 'blurPx': 1},
            {'gain': 1, 'cutoffHz': 16000, 'brightness': 1, 'saturation': 1, 'blurPx': 0},
        ]):
            self.assertEqual(set(actual), set(expected))
            for field, value in expected.items():
                self.assertAlmostEqual(actual[field], value)

    def test_filter_clamping_invalid_values_and_sample_rate_cap(self):
        result = execute("""
const invalid = [NaN, Infinity, -Infinity, undefined, null, '1'];
console.log(JSON.stringify({
  clamped:[filterTargets(-2),filterTargets(2)],
  invalid:invalid.map(p=>filterTargets(p)),
  invalidRates:[...invalid,0,-1].map(rate=>filterTargets(1,rate)),
  capped:[filterTargets(0,22050),filterTargets(1,22050),filterTargets(0,800),filterTargets(1,800)]
}));
""")
        self.assertEqual([x['gain'] for x in result['clamped']], [0, 1])
        self.assertEqual([x['gain'] for x in result['invalid']], [0] * 6)
        for target in result['invalidRates']:
            self.assertAlmostEqual(target['cutoffHz'], 16000)
        for target, expected in zip(result['capped'], [420, 9922.5, 360, 360]):
            self.assertAlmostEqual(target['cutoffHz'], expected)

    def test_browser_global_and_commonjs_have_same_behavior(self):
        result = execute("""
const fs=require('fs'), vm=require('vm');
const sandbox={}; vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
console.log(JSON.stringify({keys:Object.keys(sandbox.SimvltaneaPresence).sort(),
  value:sandbox.SimvltaneaPresence.presenceEnvelope(5.6,10),
  targets:sandbox.SimvltaneaPresence.filterTargets(.5)}));
""")
        self.assertEqual(result['keys'], ['ATTACK_SECONDS', 'filterTargets', 'presenceEnvelope'])
        self.assertAlmostEqual(result['value'], .56)
        self.assertAlmostEqual(result['targets']['gain'], .5)
