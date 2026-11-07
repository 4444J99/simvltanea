"""Behavioral proofs for adjustable presence envelopes and effect depths."""
from __future__ import annotations

import unittest

from simvltanea.browser.test_browser_presence import execute


DEFAULTS = {
    'attackSeconds': 1.2,
    'curve': 'linear',
    'tail': .12,
    'gainDepth': 1,
    'lowpassDepth': 1,
    'brightnessDepth': 1,
    'saturationDepth': 1,
    'blurPx': 2,
}


class PresenceSettingsTests(unittest.TestCase):
    def assertValuesAlmostEqual(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target)

    def test_defaults_and_normalized_settings_are_frozen_and_do_not_mutate_input(self):
        result = execute("""
const input = Object.freeze({attackSeconds: 2, curve: 'smooth', gainDepth: .4, extra: 99});
const settings = api.normalizeSettings(input);
console.log(JSON.stringify({defaults: api.DEFAULT_SETTINGS, settings, input,
  frozen: [Object.isFrozen(api.DEFAULT_SETTINGS), Object.isFrozen(settings)],
  malformed: [undefined, null, false, 2, 'smooth', []].map(value => api.normalizeSettings(value))}));
""")
        self.assertEqual(result['defaults'], DEFAULTS)
        self.assertEqual(result['settings'], dict(DEFAULTS, attackSeconds=2, curve='smooth', gainDepth=.4))
        self.assertEqual(result['input'], {'attackSeconds': 2, 'curve': 'smooth', 'gainDepth': .4, 'extra': 99})
        self.assertEqual(result['frozen'], [True, True])
        self.assertEqual(result['malformed'], [DEFAULTS] * 6)

    def test_numeric_settings_are_bounded_and_invalid_values_use_defaults_without_coercion(self):
        result = execute("""
const keys = ['attackSeconds', 'tail', 'gainDepth', 'lowpassDepth',
  'brightnessDepth', 'saturationDepth', 'blurPx'];
const make = value => Object.fromEntries(keys.map(key => [key, value]));
console.log(JSON.stringify({
  lower: api.normalizeSettings({...make(-100), curve: 'SMOOTH'}),
  upper: api.normalizeSettings({...make(100), curve: 'smooth'}),
  invalid: [NaN, Infinity, -Infinity, undefined, null, '0.5', true, false, [], {}]
    .map(value => api.normalizeSettings({...make(value), curve: value})),
  fractional: api.normalizeSettings({attackSeconds: .75, tail: .3, gainDepth: .2,
    lowpassDepth: .4, brightnessDepth: .6, saturationDepth: .8, blurPx: 1.5})
}));
""")
        self.assertEqual(result['lower'], dict(DEFAULTS, attackSeconds=.1, tail=.05,
                         gainDepth=0, lowpassDepth=0, brightnessDepth=0, saturationDepth=0, blurPx=0))
        self.assertEqual(result['upper'], dict(DEFAULTS, attackSeconds=5, tail=.5, curve='smooth'))
        self.assertEqual(result['invalid'], [DEFAULTS] * 10)
        self.assertEqual(result['fractional'], dict(DEFAULTS, attackSeconds=.75, tail=.3,
                         gainDepth=.2, lowpassDepth=.4, brightnessDepth=.6, saturationDepth=.8, blurPx=1.5))

    def test_entrance_envelope_uses_configured_attack_and_shared_curve(self):
        result = execute("""
console.log(JSON.stringify({
  linear: [0,.5,1,2,10,Number.MAX_VALUE].map(age => api.entranceEnvelope(age, {attackSeconds: 2})),
  smooth: [0,.5,1,1.5,2,10].map(age => api.entranceEnvelope(age, {attackSeconds: 2, curve: 'smooth'})),
  defaults: [.3,.6,1.2,10].map(age => api.entranceEnvelope(age)),
  invalid: [-1,0,NaN,Infinity,-Infinity,undefined,null,'1'].map(age => api.entranceEnvelope(age)),
  normalized: [api.entranceEnvelope(.05, {attackSeconds: 0}),
    api.entranceEnvelope(3, {attackSeconds: 100}), api.entranceEnvelope(.6, {attackSeconds: '2'})]
}));
""")
        self.assertValuesAlmostEqual(result['linear'], [0,.25,.5,1,1,1])
        self.assertValuesAlmostEqual(result['smooth'], [0,.15625,.5,.84375,1,1])
        self.assertValuesAlmostEqual(result['defaults'], [.25,.5,1,1])
        self.assertEqual(result['invalid'], [0] * 8)
        self.assertValuesAlmostEqual(result['normalized'], [.5,.6,.5])

    def test_linear_envelope_uses_custom_attack_and_waiting_tail(self):
        result = execute("""
console.log(JSON.stringify([0,.5,1,2,6,10,100].map(age =>
  presenceEnvelope(age, 10, {attackSeconds: 2, tail: .25}))));
""")
        self.assertValuesAlmostEqual(result, [0,.25,.5,1,.625,.25,.25])

    def test_smooth_envelope_shapes_both_rise_and_fall(self):
        result = execute("""
console.log(JSON.stringify([.5,1,2,4,6,8,10,100].map(age =>
  presenceEnvelope(age, 10, {attackSeconds: 2, tail: .25, curve: 'smooth'}))));
""")
        self.assertValuesAlmostEqual(result, [.15625,.5,1,.8828125,.625,.3671875,.25,.25])

    def test_short_lifetime_caps_attack_at_half_duration_for_each_curve(self):
        result = execute("""
console.log(JSON.stringify(['linear','smooth'].map(curve =>
  [.125,.25,.5,.625,.75,.875,1,2].map(age =>
    presenceEnvelope(age, 1, {attackSeconds: 6, tail: .2, curve})))));
""")
        self.assertValuesAlmostEqual(result[0], [.25,.5,1,.8,.6,.4,.2,.2])
        self.assertValuesAlmostEqual(result[1], [.15625,.5,1,.875,.6,.325,.2,.2])

    def test_configured_envelope_preserves_invalid_age_and_lifetime_safeguards(self):
        result = execute("""
const settings = {attackSeconds: .4, tail: .3, curve: 'smooth'};
const invalid = [NaN,Infinity,-Infinity,undefined,null,'1',0,-1];
console.log(JSON.stringify({
  ages: invalid.map(age => presenceEnvelope(age, 10, settings)),
  fallback: invalid.map(duration => [.4,1.4,2.4,100].map(age => presenceEnvelope(age, duration, settings))),
  tiny: [presenceEnvelope(Number.MIN_VALUE, Number.MIN_VALUE, settings),
    presenceEnvelope(Number.MIN_VALUE, 2 * Number.MIN_VALUE, settings),
    presenceEnvelope(2 * Number.MIN_VALUE, 4 * Number.MIN_VALUE, settings),
    presenceEnvelope(3 * Number.MIN_VALUE, 4 * Number.MIN_VALUE, settings)],
  huge: [presenceEnvelope(Number.MAX_VALUE / 2, Number.MAX_VALUE, settings),
    presenceEnvelope(Number.MAX_VALUE, Number.MAX_VALUE, settings)]
}));
""")
        self.assertEqual(result['ages'], [0] * 8)
        for values in result['fallback']:
            self.assertValuesAlmostEqual(values, [1,.65,.3,.3])
        self.assertValuesAlmostEqual(result['tiny'], [.3,1,1,.65])
        self.assertValuesAlmostEqual(result['huge'], [.65,.3])

    def test_filter_depths_apply_independently_with_exponential_lowpass(self):
        result = execute("""
console.log(JSON.stringify(filterTargets(.5, 48000, {gainDepth: .25,
  lowpassDepth: .5, brightnessDepth: .5, saturationDepth: .25, blurPx: 1})));
""")
        expected = {'gain': .875, 'cutoffHz': (16000 ** .75) * (420 ** .25),
                    'brightness': .8875, 'saturation': .9125, 'blurPx': .5}
        self.assertEqual(set(result), set(expected))
        for field, value in expected.items():
            self.assertAlmostEqual(result[field], value)

    def test_zero_depths_disable_effects_and_full_presence_is_neutral(self):
        result = execute("""
const disabled = {gainDepth: 0, lowpassDepth: 0, brightnessDepth: 0, saturationDepth: 0, blurPx: 0};
console.log(JSON.stringify({
  disabled: [0,.3,1].map(p => filterTargets(p, 22050, disabled)),
  neutral: filterTargets(1, 48000, {gainDepth: .3, lowpassDepth: .8, brightnessDepth: .4, saturationDepth: .6, blurPx: 1.5}),
  independent: ['gainDepth','lowpassDepth','brightnessDepth','saturationDepth','blurPx']
    .map(key => filterTargets(0, 48000, {[key]: 0}))
}));
""")
        self.assertEqual(result['disabled'], [
            {'gain': 1, 'cutoffHz': 9922.5, 'brightness': 1, 'saturation': 1, 'blurPx': 0}
        ] * 3)
        self.assertEqual(result['neutral'], {'gain': 1, 'cutoffHz': 16000,
                         'brightness': 1, 'saturation': 1, 'blurPx': 0})
        fields = ['gain', 'cutoffHz', 'brightness', 'saturation', 'blurPx']
        for index, targets in enumerate(result['independent']):
            expected = {'gain': 0, 'cutoffHz': 420, 'brightness': .55, 'saturation': .3, 'blurPx': 2}
            expected[fields[index]] = [1,16000,1,1,0][index]
            for field, value in expected.items():
                self.assertAlmostEqual(targets[field], value)

    def test_filter_inputs_are_bounded_without_coercion_and_rates_remain_finite(self):
        result = execute("""
const settings = {gainDepth: .5, lowpassDepth: .5, brightnessDepth: .5, saturationDepth: .5, blurPx: 1};
const invalid = [NaN,Infinity,-Infinity,undefined,null,'1'];
console.log(JSON.stringify({
  invalidPresence: invalid.map(p => filterTargets(p, 48000, settings)),
  bounds: [-1,0,1,2].map(p => filterTargets(p, 48000, settings)),
  invalidRates: [...invalid,0,-1].map(rate => filterTargets(.5, rate, settings)),
  rates: [Number.MIN_VALUE, 2*Number.MIN_VALUE, 1e-200, 800, 22050, Number.MAX_VALUE]
    .map(rate => [0,.5,1].map(p => filterTargets(p, rate, settings)))
}));
""")
        self.assertEqual(result['invalidPresence'], [result['bounds'][1]] * 6)
        self.assertEqual(result['bounds'][0], result['bounds'][1])
        self.assertEqual(result['bounds'][2], result['bounds'][3])
        for target in result['invalidRates']:
            self.assertAlmostEqual(target['cutoffHz'], (16000 ** .75) * (420 ** .25))
        for targets in result['rates']:
            for target in targets:
                self.assertTrue(all(isinstance(value, (int, float)) for value in target.values()))
                self.assertTrue(0 <= target['cutoffHz'] <= 16000)
        self.assertEqual([target['cutoffHz'] for target in result['rates'][0]], [0,0,0])
        self.assertEqual([target['cutoffHz'] for target in result['rates'][3]], [360,360,360])

    def test_helpers_accept_partial_and_invalid_settings_without_mutation(self):
        result = execute("""
const settings = Object.freeze({attackSeconds: 2, curve: 'smooth', tail: .25,
  gainDepth: .5, lowpassDepth: .5, brightnessDepth: .5, saturationDepth: .5, blurPx: 1, extra: 99});
const normalized = api.normalizeSettings(settings);
const evaluate = input => [api.entranceEnvelope(.5, input), presenceEnvelope(4, 10, input), filterTargets(.5, 48000, input)];
console.log(JSON.stringify({raw: evaluate(settings), normalized: evaluate(normalized),
  input: settings, defaults: evaluate(),
  invalid: [null,false,1,'smooth',[]].map(evaluate)}));
""")
        self.assertEqual(result['raw'], result['normalized'])
        self.assertEqual(result['input'], dict(DEFAULTS, attackSeconds=2, curve='smooth', tail=.25,
                         gainDepth=.5, lowpassDepth=.5, brightnessDepth=.5, saturationDepth=.5, blurPx=1, extra=99))
        self.assertEqual(result['invalid'], [result['defaults']] * 5)
