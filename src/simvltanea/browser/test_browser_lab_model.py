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
        result = subprocess.run(['node', '-e', code], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
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

    def test_workspace_supports_eight_pairs_and_fractional_regions(self):
        value = self.evaluate("({max:m.MAX_CLIPS,s:m.normalizeSettings({timelineStart:12.75,videoLife:.5,audioLife:1.25,attack:.04})})")
        self.assertEqual(value['max'], 8)
        self.assertEqual(value['s']['timelineStart'], 12.75)
        self.assertEqual(value['s']['videoLife'], .5)
        self.assertEqual(value['s']['audioLife'], 1.25)
        self.assertEqual(value['s']['attack'], .04)

    def test_scrubbing_recovers_independent_constant_rate_positions(self):
        values = self.evaluate('[m.positionAt(5,2,.5,0,1),m.positionAt(5,2,2,0,2)]')
        self.assertEqual(values[0], {'position': .5, 'loops': 1, 'rate': .5})
        self.assertEqual(values[1], {'position': 0, 'loops': 5, 'rate': 2})

    def test_seek_matches_the_repeat_history_instead_of_redrawing_rates(self):
        value = self.evaluate('''(()=>{
          const duration=2.5,seed=374,initial=.8,wander=.3;
          let rate=initial,time=0;
          for(let repeat=1;repeat<=12;repeat++){
            time+=duration/rate;
            rate=m.nextRate(rate,wander,()=>m.repeatUnit(seed,repeat));
          }
          return {expectedRate:rate,a:m.positionAt(time+.3,duration,initial,wander,seed),
            b:m.positionAt(time+.3,duration,initial,wander,seed),
            other:m.positionAt(time+.3,duration,initial,wander,seed+1)};
        })()''')
        self.assertEqual(value['a'], value['b'])
        self.assertEqual(value['a']['loops'], 12)
        self.assertAlmostEqual(value['a']['rate'], value['expectedRate'])
        self.assertAlmostEqual(value['a']['position'], .3 * value['expectedRate'])
        self.assertNotEqual(value['a'], value['other'])

    def test_exact_loop_boundary_seeks_to_the_new_repeat(self):
        value = self.evaluate('({at:m.positionAt(6,6,1,.25,99),before:m.positionAt(6-1e-7,6,1,.25,99),expected:m.nextRate(1,.25,()=>m.repeatUnit(99,1))})')
        self.assertEqual(value['at']['loops'], 1)
        self.assertAlmostEqual(value['at']['position'], 0)
        self.assertAlmostEqual(value['at']['rate'], value['expected'])
        self.assertEqual(value['before']['loops'], 0)

    def test_invalid_seek_input_never_creates_nan_or_an_infinite_loop(self):
        values = self.evaluate('[m.positionAt(-3,2,1,.2,1),m.positionAt(Infinity,2,1,.2,1),m.positionAt(3,0,1,.2,1),m.positionAt(3,NaN,1,.2,1)]')
        for value in values:
            self.assertEqual(value, {'position': 0, 'loops': 0, 'rate': 1})

    def test_panel_assignment_is_integer_and_not_limited_by_visible_count(self):
        values = self.evaluate('[m.normalizeSettings({panel:12}).panel,m.normalizeSettings({panel:2.7}).panel,m.normalizeSettings({panel:-1}).panel,m.normalizeSettings({panel:Infinity},m.normalizeSettings({panel:9})).panel]')
        self.assertEqual(values, [12, 3, 1, 9])

    def test_layout_normalizes_supported_families_counts_and_framing(self):
        values = self.evaluate('''({defaults:m.DEFAULT_LAYOUT,frozen:Object.isFrozen(m.DEFAULT_LAYOUT),
          strips:m.normalizeLayout({count:18,orientation:'portrait',framing:'slice'}),
          authored:m.normalizeLayout({family:'authored',count:12,framing:'slice'}),
          small:m.normalizeLayout({family:'authored',count:1}),
          merged:m.normalizeLayout({framing:'contain'},{family:'strips',count:6,orientation:'portrait',framing:'cover'})})''')
        self.assertEqual(values['defaults'], {'family':'strips','count':3,'orientation':'landscape','framing':'cover'})
        self.assertTrue(values['frozen'])
        self.assertEqual(values['strips'], {'family':'strips','count':12,'orientation':'portrait','framing':'slice'})
        self.assertEqual(values['authored'], {'family':'authored','count':7,'orientation':'landscape','framing':'cover'})
        self.assertEqual(values['small']['count'], 2)
        self.assertEqual(values['merged'], {'family':'strips','count':6,'orientation':'portrait','framing':'contain'})

    def test_panel_cells_use_canonical_strips_and_original_slice(self):
        compiler = json.dumps(str(MODULE.with_name('browser.compiler.js')))
        values = self.evaluate(f'''(()=>{{const compiler=require({compiler});
          const number=x=>{{const [n,d=1]=String(x).split('/').map(Number);return n/d;}};
          return [1,3,12].flatMap(count=>['landscape','portrait'].map(orientation=>{{
            const cells=m.panelCells({{family:'strips',count,orientation,framing:'slice'}});
            const canonical=compiler.stripsLayouts(count)[orientation].cells;
            const slice=compiler.stripsSlice(count);
            return {{cells,rects:canonical.map(c=>c.rect.map(number)),size:[number(slice.width),number(slice.height)]}};
          }}));}})()''')
        for result in values:
            self.assertEqual([c['rect'] for c in result['cells']], result['rects'])
            for index, cell in enumerate(result['cells'], 1):
                self.assertEqual((cell['number'],cell['id']), (index,f'panel-{index}'))
                self.assertEqual(cell['slice'][2:], result['size'])

    def test_authored_panels_come_from_the_provided_canonical_bundle(self):
        from simvltanea.browser.layout_bundle import layout_bundle_v2
        bundle = layout_bundle_v2()
        result = self.evaluate(f"m.panelCells({{family:'authored',count:7,orientation:'portrait',framing:'contain'}},{json.dumps(bundle)})")
        canonical = bundle['families']['authored']['counts']['7']['portrait']['cells']
        from fractions import Fraction
        for panel, cell in zip(result, canonical):
            self.assertEqual(panel['rect'], [float(Fraction(value)) for value in cell['rect']])
            self.assertEqual(panel['fit'], 'contain')
            self.assertIsNone(panel['slice'])


if __name__ == '__main__':
    unittest.main()
