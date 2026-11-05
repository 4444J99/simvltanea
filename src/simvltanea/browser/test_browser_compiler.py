"""Parity proofs for the client-side compiler browser.compiler.js.

Supported subset, mirrored from the compiler header: schema_version 1 with
silent audio; N=2..7 loops; exactly one source per bank, every source bound to
one loop, distinct IDs and media digests, allow_source_reuse false; video and
still sources; offset, rate, trim and initial held; fps 1..60; no events; slice
and seam absent or disabled. Inside the subset the JavaScript plan must equal
Python's compile_plan byte for byte. Outside it the JavaScript must throw a
CompilerError, never return a differing plan.

Node.js 22 is a CI prerequisite. These tests fail, never skip, without it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path

import simvltanea.authoring.composition as c
from simvltanea.authoring import AUTHORED, build_artifact001, from_authoring_model
from simvltanea.browser.browser_runtime import HERE, compile_plan
from simvltanea.browser.layout_bundle import authored_layout_bundle

COMPILER = HERE / 'browser.compiler.js'
# Each call is [function name, *JSON arguments]; {"$number": "NaN"} revives non-JSON numbers.
DRIVER = r'''
const C = require(process.argv[1]);
const revive = (key, value) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === 1 && '$number' in value ? Number(value.$number) : value;
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const results = JSON.parse(input, revive).map(([name, ...args]) => {
    try { return {ok: true, value: C[name](...args)}; }
    catch (error) {
      return {ok: false, name: error.name, message: error.message, unsupported: error.unsupported === true};
    }
  });
  process.stdout.write(JSON.stringify(results));
});
'''


def node_executable() -> str:
    executable = shutil.which('node')
    if executable is None:
        raise RuntimeError('Node.js 22 is required for browser compiler parity (no skip substituted)')
    return executable


def wire(value):
    """Encode Python values for the driver, preserving non-finite floats."""
    if isinstance(value, float) and not math.isfinite(value):
        return {'$number': repr(value).replace('inf', 'Infinity').replace('nan', 'NaN')}
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, list):
        return [wire(item) for item in value]
    return value


def node(*calls) -> list[dict]:
    completed = subprocess.run([node_executable(), '-e', DRIVER, str(COMPILER)],
                               input=json.dumps(wire(list(calls))), capture_output=True,
                               text=True, check=True, timeout=300)
    return json.loads(completed.stdout)


def digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def caller_sources(count: int, durations=None) -> list[dict]:
    durations = durations or ['8'] * count
    return [dict(id=f'media-{i}', path=f'media/loop-{i}.mp4', sha256=digest(f'loop-{i}'),
                 kind='video', duration=durations[i - 1]) for i in range(1, count + 1)]


def caller_input(count: int, **overrides) -> dict:
    data = dict(sources=caller_sources(count),
                loops=[dict(id=f'loop-{i}', source=f'media-{i}') for i in range(1, count + 1)],
                layouts=authored_layout_bundle()[str(count)], fps=24, frames=48)
    data.update(overrides)
    return data


def authored_state(count: int, frames: int = 144, fps: int = 24) -> dict:
    composition = build_artifact001(count)
    bindings = {loop.source: source for loop, source in zip(composition.loops, caller_sources(count))}
    return from_authoring_model(composition, bindings, frames=frames, fps=fps)


class CompilerParityTests(unittest.TestCase):
    def assertSamePlan(self, javascript: dict, python: dict):
        self.assertEqual(javascript, python)
        # Key order and spelling too: the plan is a transport document.
        self.assertEqual(json.dumps(javascript), json.dumps(python))

    def test_supported_counts_match_python_state_and_plan(self):
        bundle = authored_layout_bundle()
        calls, states = [], {}
        for count in sorted(AUTHORED):
            state = states[count] = authored_state(count)
            ids = [loop['id'] for loop in state['loops']]
            calls.append(['buildState', dict(
                sources=state['sources'], seed=state['seed'], fps=24, frames=144,
                loops=[dict(id=loop['id'], source=loop['bank'][0], offset=loop['offset'], rate=loop['rate'])
                       for loop in state['loops']],
                layouts=bundle[str(count)])])
            calls.append(['compilePlan', state])
            calls.append(['bindLayouts', bundle[str(count)], ids])
        results = node(*calls)
        for index, count in enumerate(sorted(AUTHORED)):
            built, plan, bound = results[3 * index:3 * index + 3]
            with self.subTest(count=count):
                self.assertTrue(built['ok'] and plan['ok'] and bound['ok'], (built, plan, bound))
                self.assertEqual(json.dumps(built['value']), json.dumps(states[count]))
                self.assertEqual(bound['value'], states[count]['layouts'])
                self.assertSamePlan(plan['value'], compile_plan(states[count]))

    def test_clock_trim_rate_fps_and_spelling_variants_match_python(self):
        variants = {
            'trim': caller_input(3, loops=[dict(id='loop-1', source='media-1', trim=['1', '2']),
                                           dict(id='loop-2', source='media-2', trim=['1/3', '5/2'], rate='3/2'),
                                           dict(id='loop-3', source='media-3', trim=[0, 8], offset='15/2')]),
            'rational-rates': caller_input(5, loops=[
                dict(id=f'loop-{i}', source=f'media-{i}', rate=rate)
                for i, rate in enumerate(('3/2', '7/3', '1/16', '8', 2), 1)]),
            'offsets': caller_input(4, loops=[
                dict(id=f'loop-{i}', source=f'media-{i}', offset=offset)
                for i, offset in enumerate(('5/4', '100', 0, '-0'), 1)]),
            'differing-durations': caller_input(
                4, sources=caller_sources(4, ['8', '5/2', '13/3', '1/7']), frames=72,
                loops=[dict(id=f'loop-{i}', source=f'media-{i}', rate='9/8') for i in range(1, 5)]),
            'fps-1': caller_input(2, fps=1, frames=20),
            'fps-25': caller_input(3, fps=25, frames=100, loops=[
                dict(id=f'loop-{i}', source=f'media-{i}', rate=f'{20 + i}/20') for i in range(1, 4)]),
            'fps-30': caller_input(6, fps=30, frames=90),
            'fps-60-long': caller_input(7, fps=60, frames=1440, loops=[
                dict(id=f'loop-{i}', source=f'media-{i}', rate=f'{100 + 7 * i}/100', offset=f'{31 * i}/100')
                for i in range(1, 8)]),
            'single-frame': caller_input(2, frames=1),
            'non-canonical-spelling': caller_input(
                2, sources=caller_sources(2, ['016/2', 8]), seed='seed-text',
                loops=[dict(id='loop-1', source='media-1', offset='2/4', rate='12/8'),
                       dict(id='loop-2', source='media-2', offset=3, rate=1)]),
            'still-and-held': caller_input(
                3, sources=[*caller_sources(2), dict(id='media-3', path='media/frame.PNG',
                                                     sha256=digest('still'), kind='still', duration='1/2')],
                loops=[dict(id='loop-1', source='media-1', held=True, offset='3/2'),
                       dict(id='loop-2', source='media-2'),
                       dict(id='loop-3', source='media-3', rate='1/100')]),
        }
        calls = []
        for data in variants.values():
            calls += [['buildState', data], ['compile', data]]
        results = node(*calls)
        for index, name in enumerate(variants):
            built, plan = results[2 * index:2 * index + 2]
            with self.subTest(variant=name):
                self.assertTrue(built['ok'] and plan['ok'], (built, plan))
                c.validate_state(built['value'])
                self.assertSamePlan(plan['value'], compile_plan(built['value']))
        spans = {name: sum(len(t['spans']) for t in results[2 * i + 1]['value']['tracks'])
                 for i, name in enumerate(variants)}
        self.assertGreater(spans['differing-durations'], 4, 'wraps must split spans')
        self.assertEqual(spans['still-and-held'], 3, 'held and still loops never split')

    def test_disabled_optional_fields_and_unicode_hash_match_python(self):
        state = authored_state(3)
        state['seam'] = {'enabled': False, 'width': '2/80', 'mode': 'blur', 'sigma': '1/200'}
        state['slice'] = {'enabled': False, 'height': '1/3'}
        state['layouts']['portrait']['name'] = 'portrait \u00e9t\u00e9 \u2014 \U0001f300 "quoted"\n'
        state['seed'] = 'graine-\u00e9'
        (result,) = node(['compilePlan', state])
        self.assertTrue(result['ok'], result)
        self.assertSamePlan(result['value'], compile_plan(state))
        self.assertEqual(result['value']['seam']['width'], '2/80', 'disabled configs pass through verbatim')

    def test_unsupported_states_fail_explicitly(self):
        base = authored_state(3, frames=48)
        def n_loops(count):
            state = copy.deepcopy(base)
            state['sources'] = caller_sources(count)
            state['loops'] = [dict(id=f'loop-{i}', bank=[f'media-{i}'], offset='0', rate='1', period='8',
                                   epoch=0, held=False) for i in range(1, count + 1)]
            cells = [dict(loop=f'loop-{i + 1}', rect=[f'{i}/{count}', '0', f'1/{count}', '1'],
                          fit='cover', focal=['1/2', '1/2']) for i in range(count)]
            state['layouts'] = {o: dict(name=f'grid-{o}', cells=copy.deepcopy(cells)) for o in c.ORIENTATIONS}
            return state
        def edit(change):
            state = copy.deepcopy(base)
            change(state)
            return state
        def add_source(state, sha=None):
            state['sources'].append(dict(id='extra', path='media/extra.mp4', sha256=sha or digest('extra'),
                                         kind='video', duration='8'))
        events = {
            'hold': dict(op='hold', frame=12, loop='loop-1', value=True),
            'reroll': dict(op='reroll', frame=12, loop='loop-1'),
            'swap': dict(op='swap', frame=12, a='loop-1', b='loop-2'),
            'move': dict(op='move', frame=12, loop='loop-1', orientation='portrait',
                         rect=['1/10', '3/100', '4/5', '21/50']),
        }
        # Python compiles these; the JavaScript must refuse them instead of differing.
        python_accepts = {
            'one-loop': (n_loops(1), 'N=2..7'),
            'eight-loops': (n_loops(8), 'N=2..7'),
            **{f'event-{name}': (edit(lambda s, e=event: s.__setitem__('events', [e])), 'events')
               for name, event in events.items()},
            'audio-v1.1': (edit(lambda s: s.update(schema_version='1.1', engine_version='1.1.0')), 'Audio v1.1'),
            'multi-source-bank': (edit(lambda s: (add_source(s), s['loops'][0].__setitem__(
                'bank', ['media-1', 'extra']))), 'bank'),
            'slice-enabled': (edit(lambda s: s.__setitem__('slice', {'enabled': True})), 'slice'),
            'seam-enabled': (edit(lambda s: s.__setitem__('seam', {'enabled': True})), 'seam'),
            'explicit-reuse': (edit(lambda s: (s.__setitem__('allow_source_reuse', True),
                                               s['loops'][1].__setitem__('bank', ['media-1']))), 'reuse'),
            'unused-source': (edit(add_source), 'filler'),
            'decimal-rate-string': (edit(lambda s: s['loops'][0].__setitem__('rate', '1.5')), 'decimals'),
            'decimal-duration-string': (edit(lambda s: s['sources'][0].__setitem__('duration', '8.0')), 'decimals'),
            'decimal-rect-string': (edit(lambda s: s['layouts']['portrait']['cells'][0]['rect']
                                         .__setitem__(0, '0.04')), 'decimals'),
            'exponent-string': (edit(lambda s: s['loops'][0].__setitem__('offset', '1e1')), 'decimals'),
        }
        python_rejects = {
            'duplicate-media': (edit(lambda s: s['sources'][1].__setitem__('sha256', s['sources'][0]['sha256'])),
                                'duplicated'),
            'shared-source': (edit(lambda s: s['loops'][1].__setitem__('bank', ['media-1'])), 'duplicated'),
            'float-offset': (edit(lambda s: s['loops'][0].__setitem__('offset', 1.5)), 'decimals'),
            'nan-rate': (edit(lambda s: s['loops'][0].__setitem__('rate', float('nan'))), 'non-finite'),
            'infinite-duration': (edit(lambda s: s['sources'][0].__setitem__('duration', float('inf'))),
                                  'non-finite'),
            'empty-sources': (edit(lambda s: s.__setitem__('sources', [])), 'sources must be a nonempty array'),
            'fractional-frames': (edit(lambda s: s.__setitem__('frames', 1.5)), 'frames must be an integer'),
            'string-frames': (edit(lambda s: s.__setitem__('frames', '48')), 'frames must be an integer'),
            'zero-frames': (edit(lambda s: s.__setitem__('frames', 0)), 'frames must be an integer'),
            'too-many-frames': (edit(lambda s: s.__setitem__('frames', 14401)), 'frames must be an integer'),
            'fractional-fps': (edit(lambda s: s.__setitem__('fps', 23.976)), 'fps must be an integer'),
            'browser-rate-guard': (edit(lambda s: s['loops'][0].__setitem__('rate', '1/32')), '1/16..8'),
            'overlap': (edit(lambda s: s['layouts']['portrait']['cells'][1].__setitem__(
                'rect', ['1/25', '3/100', '1/2', '1/2'])), 'overlapping'),
            'missing-orientation': (edit(lambda s: s['layouts'].pop('landscape')), 'missing fields'),
            'trim-beyond-source': (edit(lambda s: s['loops'][0].__setitem__('trim', ['0', '9'])), 'trim'),
            'lone-surrogate': (edit(lambda s: s['layouts']['portrait'].__setitem__('name', 'x\ud800')),
                               'well-formed'),
        }
        names = [*python_accepts, *python_rejects]
        states = [state for state, _ in (*python_accepts.values(), *python_rejects.values())]
        results = node(*(['compilePlan', state] for state in states))
        for name, result in zip(names, results):
            accepted = name in python_accepts
            state, pattern = python_accepts[name] if accepted else python_rejects[name]
            with self.subTest(case=name):
                self.assertFalse(result['ok'], f'{name} compiled instead of failing')
                self.assertEqual(result['name'], 'CompilerError')
                self.assertRegex(result['message'], pattern)
                if accepted:
                    # Decimal spellings are refused as malformed wire rationals, like the runtime does.
                    self.assertEqual(result['unsupported'], 'decimals' not in pattern, result['message'])
                    compile_plan(state)
                else:
                    with self.assertRaises((c.StateError, UnicodeEncodeError)):
                        compile_plan(state)

    def test_caller_data_errors_fail_before_compilation(self):
        cases = {
            'empty-sources': (caller_input(2, sources=[]), 'sources must be a nonempty array'),
            'absent-source': (caller_input(2, loops=[dict(id='loop-1', source='media-1'),
                                                     dict(id='loop-2', source='nowhere')]), 'absent source'),
            'unknown-field': (dict(caller_input(2), audio='soundtrack'), 'unsupported fields'),
            'unknown-loop-field': (caller_input(2, loops=[dict(id='loop-1', source='media-1', bank=['x']),
                                                          dict(id='loop-2', source='media-2')]),
                                   'unsupported fields'),
            'non-integer-frames': (caller_input(2, frames=2.5), 'frames must be an integer'),
            'missing-frames': ({k: v for k, v in caller_input(2).items() if k != 'frames'}, 'missing fields'),
            'nan-duration': (caller_input(2, sources=caller_sources(2, [float('nan'), '8'])), 'non-finite'),
            'layout-count-mismatch': (caller_input(2, layouts=authored_layout_bundle()['3']), 'every loop'),
        }
        results = node(*(['compile', data] for data, _ in cases.values()),
                       ['bindLayouts', authored_layout_bundle()['3'], ['a', 'b']],
                       ['bindLayouts', authored_layout_bundle()['2'], ['a', 'a']])
        for (name, (_, pattern)), result in zip(cases.items(), results):
            with self.subTest(case=name):
                self.assertFalse(result['ok'])
                self.assertRegex(result['message'], pattern)
        self.assertRegex(results[-2]['message'], 'cell count must equal the loop count')
        self.assertRegex(results[-1]['message'], 'unique')

    def test_state_digest_matches_python_canonical_json(self):
        values = [authored_state(2), {'b': [1, None, True], 'a': 'caf\u00e9 \u0001\t\U0001f300'}, -7, 'x' * 70]
        results = node(*(['stateDigest', value] for value in values))
        for value, result in zip(values, results):
            self.assertEqual(result['value'], hashlib.sha256(c.canonical_json(value).encode()).hexdigest())


class LayoutBundleTests(unittest.TestCase):
    def test_bundle_is_derived_from_authored_geometry(self):
        bundle = authored_layout_bundle()
        self.assertEqual(list(bundle), [str(count) for count in sorted(AUTHORED)])
        self.assertEqual(list(bundle), ['2', '3', '4', '5', '6', '7'])
        for count, pair in bundle.items():
            for orientation in c.ORIENTATIONS:
                with self.subTest(count=count, orientation=orientation):
                    layout = pair[orientation]
                    geometry = AUTHORED[int(count)][orientation]
                    self.assertEqual(layout['name'], f'artifact001-{count}-{orientation}')
                    self.assertEqual([cell['loop'] for cell in layout['cells']],
                                     [f'loop-{i}' for i in range(1, int(count) + 1)])
                    for cell, rect in zip(layout['cells'], geometry, strict=True):
                        self.assertEqual([Fraction(v) for v in cell['rect']],
                                         [Fraction(str(round(v, 9))) for v in rect])
                        self.assertEqual((cell['fit'], cell['focal']), ('cover', ['1/2', '1/2']))
            self.assertEqual(pair, authored_state(int(count))['layouts'])

    def test_module_entry_prints_the_bundle(self):
        src = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(src), str(src.parent)]))
        completed = subprocess.run([sys.executable, '-m', 'simvltanea.browser.layout_bundle'], env=env,
                                   capture_output=True, text=True, check=True, timeout=120)
        self.assertEqual(json.loads(completed.stdout), authored_layout_bundle())


class StagingParityTests(unittest.TestCase):
    """stagePreview reproduces build_preview's plan for the generated N=2..7 fixtures."""

    @classmethod
    def setUpClass(cls):
        from simvltanea.generators.make_runtime_fixture import ROOT, prepare
        prepare()
        cls.root = ROOT

    def test_staged_plans_equal_python_previews(self):
        calls, expected = [], []
        for count in sorted(AUTHORED):
            state = c.load_state(self.root / f'state-{count}.json')
            sizes = {s['id']: (self.root / s['path']).stat().st_size for s in state['sources']}
            calls.append(['stagePreview', state, sizes])
            expected.append((json.loads((self.root / f'preview-{count}/plan.json').read_text()),
                             c.load_state(self.root / f'preview-{count}/state.json')))
        for count, result, (plan, portable) in zip(sorted(AUTHORED), node(*calls), expected):
            with self.subTest(count=count):
                self.assertTrue(result['ok'], result)
                self.assertEqual(json.dumps(result['value']['plan']), json.dumps(plan))
                self.assertEqual(result['value']['state'], portable)

    def test_staging_requires_mp4_and_byte_counts(self):
        state = c.load_state(self.root / 'state-2.json')
        sizes = {s['id']: 1000 for s in state['sources']}
        avi = copy.deepcopy(state)
        avi['sources'][0]['path'] = 'media/source-1.avi'
        results = node(['stagePreview', avi, sizes], ['stagePreview', state, {'source-1': 1000}],
                       ['stagePreview', state, {s['id']: 200 * 1024 * 1024 for s in state['sources']}])
        self.assertRegex(results[0]['message'], 'MP4')
        self.assertRegex(results[1]['message'], 'byte count required')
        self.assertRegex(results[2]['message'], '256 MiB')


class RuntimePlaybackTests(unittest.TestCase):
    """The unmodified runtime validates and plays plans compiled inside Chrome."""

    @classmethod
    def setUpClass(cls):
        from simvltanea.browser import test_browser_runtime as legacy
        legacy.BrowserTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from simvltanea.browser import test_browser_runtime as legacy
        legacy.BrowserTests.tearDownClass.__func__(cls)

    def test_browser_compiled_plans_play_in_unmodified_runtime(self):
        from simvltanea.generators.make_runtime_fixture import ROOT
        fixtures = json.loads((ROOT / 'sources.json').read_text())['sources']
        bundle = authored_layout_bundle()
        for count in sorted(AUTHORED):
            with self.subTest(count=count):
                page = self.browser.new_page(viewport={'width': 390, 'height': 844})
                self.addCleanup(page.close)
                page.goto(f'{self.base}/sources.json')
                page.set_content('<main id="stage"></main><p id="runtime-status"></p>')
                page.add_script_tag(content=COMPILER.read_text())
                compiled = page.evaluate('''async ({count, pair, fixtures}) => {
                  const C = SimvltaneaCompiler, chosen = fixtures.slice(0, count);
                  const ids = chosen.map((_, i) => `panel-${String.fromCharCode(97 + i)}`);
                  const hex = b => [...new Uint8Array(b)].map(v => v.toString(16).padStart(2, '0')).join('');
                  const bytes = {}, sizes = {};
                  for (const source of chosen) {
                    const buffer = await (await fetch(source.path)).arrayBuffer();
                    bytes[source.sha256] = buffer; sizes[source.id] = buffer.byteLength;
                  }
                  const state = C.buildState({sources: chosen, frames: 96, layouts: C.bindLayouts(pair, ids),
                    loops: chosen.map((source, i) => ({id: ids[i], source: source.id, offset: `${i}/3`,
                      rate: `${12 + i}/12`}))});
                  const staged = C.stagePreview(state, sizes);
                  window.compositionIO = {plan: async () => staged.plan, bytes: async s => bytes[s.sha256],
                    digest: async b => hex(await crypto.subtle.digest('SHA-256', b))};
                  return {state, plan: staged.plan};
                }''', dict(count=count, pair=bundle[str(count)], fixtures=fixtures))
                expected = compile_plan(compiled['state'])
                for key in ('tracks', 'layout_keyframes', 'fps', 'frames', 'audio', 'seam', 'slice'):
                    self.assertEqual(compiled['plan'][key], expected[key])
                self.assertEqual(compiled['plan']['origin_state_sha256'], expected['state_sha256'])
                page.add_script_tag(content=(HERE / 'browser.runtime.js').read_text())
                page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error',
                                       timeout=20000)
                self.assertIsNone(page.evaluate('compositionRuntime.error'))
                self.assertEqual(page.evaluate('compositionRuntime.nodes.size'), count)
                page.evaluate('compositionRuntime.start()')
                page.wait_for_function('compositionRuntime.error || compositionRuntime.frame >= 24', timeout=20000)
                state = page.evaluate('({error: compositionRuntime.error, running: compositionRuntime.running})')
                self.assertEqual(state, {'error': None, 'running': True})


if __name__ == '__main__':
    unittest.main()
