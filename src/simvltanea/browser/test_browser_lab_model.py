"""Behavioral checks for the lab's independent envelopes and filter targets."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

MODULE = Path(__file__).with_name('browser.lab_model.js')


@unittest.skipUnless(shutil.which('node'), 'Node.js is required')
class EffectsLabModelTests(unittest.TestCase):
    def evaluate(self, expression: str):
        self.assertTrue(MODULE.is_file(), 'The Effects Lab model has not been implemented')
        code = f'const m=require({json.dumps(str(MODULE))}); console.log(JSON.stringify({expression}));'
        result = subprocess.run(['node', '-e', code], check=True, text=True, capture_output=True)
        return json.loads(result.stdout)

    def test_picture_can_end_while_audio_still_has_presence(self):
        values = self.evaluate('[m.envelope(26,24,2),m.envelope(26,36,2),m.envelope(0,24,2),m.envelope(2,24,2)]')
        self.assertEqual(values[0], 0)
        self.assertGreater(values[1], 0)
        self.assertEqual(values[2:], [0, 1])

    def test_attack_cannot_consume_the_whole_lifetime(self):
        values = self.evaluate('[m.envelope(2,4,10),m.envelope(4,4,10),m.envelope(-1,24,2),m.envelope(Infinity,24,2)]')
        self.assertEqual(values, [1, 0, 0, 0])

    def test_comb_visits_both_frequency_bounds_and_returns(self):
        values = self.evaluate('[0,2,4,6,8].map(t=>m.combFrequency(t,{combLow:100,combHigh:1600,combPeriod:8}))')
        for actual, expected in zip(values, [100, 400, 1600, 400, 100]):
            self.assertAlmostEqual(actual, expected)

    def test_voice_phase_offsets_do_not_share_a_sweep_clock(self):
        values = self.evaluate('[m.combFrequency(0,m.DEFAULTS,0),m.combFrequency(0,m.DEFAULTS,.5)]')
        self.assertEqual(values, [100, 2400])

    def test_presence_opens_on_arrival_and_thins_on_departure(self):
        values = self.evaluate("['entering','leaving'].map(phase=>m.filterTargets(.2,phase,m.DEFAULTS))")
        self.assertLess(values[0]['lowpassHz'], values[1]['lowpassHz'])
        self.assertLess(values[0]['highpassHz'], values[1]['highpassHz'])
        self.assertTrue(values[0]['lowpassEnabled'])
        self.assertTrue(values[1]['highpassEnabled'])

    def test_reversing_pass_roles_reverses_entrance_and_departure(self):
        values = self.evaluate("['entering','leaving'].map(phase=>m.filterTargets(.2,phase,{filterMode:'presence-reverse'}))")
        self.assertGreater(values[0]['highpassHz'], values[1]['highpassHz'])
        self.assertGreater(values[0]['lowpassHz'], values[1]['lowpassHz'])

    def test_off_disables_all_spectral_pass_stages(self):
        value = self.evaluate("m.filterTargets(0,'leaving',{filterMode:'off'})")
        self.assertFalse(value['lowpassEnabled'])
        self.assertFalse(value['highpassEnabled'])
        self.assertFalse(value['bandpassEnabled'])

    def test_cutoffs_remain_below_actual_sample_rate_limit(self):
        values = self.evaluate("['presence','presence-reverse','lowpass','highpass','bandpass','off'].map(filterMode=>m.filterTargets(.1,'leaving',{filterMode,cutoff:16000},8000))")
        for value in values:
            for key in ['lowpassHz', 'highpassHz', 'bandpassHz']:
                self.assertGreater(value[key], 0)
                self.assertLessEqual(value[key], 3600)

    def test_distinct_loop_draws_produce_distinct_audio_and_video_rates(self):
        values = self.evaluate('[m.nextRate(1,.3,()=>.1),m.nextRate(1,.3,()=>.9),m.nextRate(1,0,()=>0)]')
        self.assertLess(values[0], 1)
        self.assertGreater(values[1], 1)
        self.assertEqual(values[2], 1)

    def test_variation_matches_the_displayed_percentage(self):
        values = self.evaluate('[m.nextRate(1,.2,()=>0),m.nextRate(1,.2,()=>1)]')
        self.assertEqual(values, [.8, 1.2])

    def test_extreme_rate_and_feedback_inputs_remain_bounded(self):
        value = self.evaluate("({settings:m.normalizeSettings({audioRate:900,videoRate:-2,combFeedback:1,combLow:2000,combHigh:100,blur:Infinity,blend:'bad',preservePitch:'false'}),rates:[m.nextRate(3,.5,()=>1),m.nextRate(.25,.5,()=>0)]})")
        self.assertEqual(value['settings']['audioRate'], 3)
        self.assertEqual(value['settings']['videoRate'], .25)
        self.assertEqual(value['settings']['combFeedback'], .75)
        self.assertGreaterEqual(value['settings']['combHigh'], value['settings']['combLow'])
        self.assertEqual(value['settings']['blur'], 0)
        self.assertEqual(value['settings']['blend'], 'screen')
        self.assertIs(value['settings']['preservePitch'], False)
        self.assertEqual(value['rates'], [3, .25])

    def test_settings_change_isolated_to_requested_keys(self):
        value = self.evaluate("(()=>{const base=m.normalizeSettings({audioRate:1.4,videoRate:.8});const changed=m.normalizeSettings({combMix:.9},base);return {base,changed,frozen:Object.isFrozen(m.DEFAULTS)}})()")
        self.assertTrue(value['frozen'])
        self.assertEqual(value['base']['combMix'], .45)
        self.assertEqual(value['changed']['combMix'], .9)
        self.assertEqual(value['changed']['audioRate'], 1.4)
        self.assertEqual(value['changed']['videoRate'], .8)


if __name__ == '__main__':
    unittest.main()
