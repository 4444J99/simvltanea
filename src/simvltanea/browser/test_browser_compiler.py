"""Parity proofs for the client-side compiler browser.compiler.js.

Supported subset, mirrored from the compiler header: schema_version 1 with
silent audio; N=1..12 loops; banks of one or more sources with seeded selection,
every source in some bank, distinct IDs and media digests, allow_source_reuse
false; video and still sources; offset, rate, trim and initial held; fps 1..60;
reroll and swap events (every play state); layouts with the optional full_bleed,
presentation and lateral_offset declarations; the state-wide slice, enabled or
not; seam absent or disabled. Inside the subset the JavaScript plan must equal
Python's compile_plan byte for byte. Outside it the JavaScript must throw a
CompilerError, never return a differing plan. Hold and move events stay outside.

Play states come from the play engine itself (schedule_play on the synthetic pool
of test_gravity_pool, through test_play_support.play) for N=3 and N=7.

The layout-file half (strict JSON, presets, pairs, strips expansion, adjacency and
the two bundle formats) is proven against authoring/layout_presets.py: the same
canonical JSON for every valid input and the same LayoutError code (and message)
for every invalid one, over examples/layout-presets/ and fixtures/layouts/.

Every refusal is a CompilerError. Python-accepted states outside the subset throw with
unsupported true; Python-accepted spellings and seeds the compiler will not read
(decimal strings, '+1/2', seeds above 2**53) throw with unsupported false. Only plain
objects are accepted, and only their own enumerable keys count.

Node.js 22 is a CI prerequisite. These tests fail, never skip, without it.
"""
from __future__ import annotations

import bisect
import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import simvltanea.authoring.composition as c
from simvltanea.authoring import (
    AUTHORED,
    LayoutError,
    adjacency,
    build_artifact001,
    build_strips,
    from_authoring_model,
    load_layout_file,
    strips_layouts,
    strips_slice,
)
from simvltanea.authoring.layout_presets import DEFAULT_STRIPS_PRESET
from simvltanea.browser.browser_runtime import HERE, compile_plan
from simvltanea.browser.layout_bundle import BUNDLE_AUTHORED_COUNTS, authored_layout_bundle, authored_layouts, layout_bundle_v2, render_bundle, strips_entry
from simvltanea.paths import WORK_DIR

COMPILER = HERE / 'browser.compiler.js'
REPOSITORY = HERE.parents[2]
CORPUS = REPOSITORY / 'fixtures' / 'layouts'
EXAMPLE_PRESET = REPOSITORY / 'examples' / 'layout-presets' / 'strips.json'
PARITY_COUNTS = (1, 2, 3, 5, 8, 12)
# sha256 of `python -m simvltanea.browser.layout_bundle` output, taken before bundle v2 existed.
LEGACY_BUNDLE_SHA256 = 'ac4b534880b150acebaa128451c20660b7d43b6abfe108951d06a0e040e1e76b'
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
      return {ok: false, name: error.name, message: error.message, unsupported: error.unsupported === true,
        code: error.code ?? null};
    }
  });
  process.stdout.write(JSON.stringify(results));
});
'''


# Builds objects with inherited or hidden properties, which JSON cannot express.
INHERITANCE_DRIVER = r'''
const C = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const base = JSON.parse(input);
  const clone = value => JSON.parse(JSON.stringify(value));
  // Move the named keys of a plain object onto its prototype.
  const inherit = (object, keys) => {
    const prototype = {};
    const own = Object.create(prototype);
    for (const [key, value] of Object.entries(object)) (keys.includes(key) ? prototype : own)[key] = value;
    return own;
  };
  const hide = (object, key) => {
    const copy = {};
    for (const [name, value] of Object.entries(object)) {
      Object.defineProperty(copy, name, {value, enumerable: name !== key, writable: true, configurable: true});
    }
    return copy;
  };
  const variants = {};
  const edit = (name, change) => { const state = clone(base); variants[name] = change(state) || state; };
  edit('control-plain', () => {});
  edit('control-null-prototype', state => {
    const strip = value => Array.isArray(value) ? value.map(strip) : value && typeof value === 'object'
      ? Object.assign(Object.create(null), Object.fromEntries(Object.entries(value).map(([k, v]) => [k, strip(v)])))
      : value;
    return strip(state);
  });
  edit('inherited-trim', state => {
    state.loops[0].trim = ['1', '2'];
    state.loops[0] = inherit(state.loops[0], ['trim']);
  });
  edit('inherited-trim-second-loop', state => {
    state.loops[1].trim = ['1/2', '3'];
    state.loops[1] = inherit(state.loops[1], ['trim']);
  });
  edit('hidden-own-trim', state => {
    state.loops[0].trim = ['1', '2'];
    state.loops[0] = hide(state.loops[0], 'trim');
  });
  edit('inherited-loop-field', state => { state.loops[0] = inherit(state.loops[0], ['rate']); });
  edit('inherited-source-field', state => { state.sources[0] = inherit(state.sources[0], ['duration']); });
  edit('inherited-cell-field', state => {
    state.layouts.portrait.cells[0] = inherit(state.layouts.portrait.cells[0], ['fit']);
  });
  edit('inherited-layout-field', state => { state.layouts.landscape = inherit(state.layouts.landscape, ['name']); });
  edit('inherited-layouts-orientation', state => { state.layouts = inherit(state.layouts, ['portrait']); });
  edit('inherited-state-field', state => inherit(state, ['fps']));
  edit('inherited-enabled-seam', state => inherit({...state, seam: {enabled: true}}, ['seam']));
  edit('inherited-disabled-slice', state => inherit({...state, slice: {enabled: false}}, ['slice']));
  edit('inherited-audio-routing', state => { state.audio = inherit(state.audio, ['routing', 'generative']); });
  edit('inherited-audio-nonbmp-keys', state => {
    const audio = Object.create({routing: null, generative: null});
    Object.assign(audio, {mode: 'none', '\u{1F600}': 1, '\uE000': 2});
    state.audio = audio;
  });
  edit('hidden-audio-key', state => { state.audio = hide(state.audio, 'generative'); });
  edit('class-instance-loop', state => {
    class Loop { constructor(fields) { Object.assign(this, fields); } }
    state.loops[0] = new Loop(state.loops[0]);
  });
  edit('class-instance-state', state => {
    class State { constructor(fields) { Object.assign(this, fields); } }
    return new State(state);
  });
  const results = {};
  for (const [name, state] of Object.entries(variants)) {
    try { results[name] = {ok: true, plan: C.compilePlan(state), digest: C.stateDigest(state)}; }
    catch (error) {
      results[name] = {ok: false, name: error.name, message: error.message, unsupported: error.unsupported === true};
    }
  }
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


# Each item is [path, name]: the file's bytes go through loadLayoutBytes(bytes, name); a
# preset is expanded at every count it declares. Canonical JSON is computed in JavaScript.
LAYOUT_DRIVER = r'''
const C = require(process.argv[1]); const fs = require('fs');
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const pairAdjacency = pair => ({portrait: C.adjacency(pair.portrait.cells), landscape: C.adjacency(pair.landscape.cells)});
  const results = JSON.parse(input).map(([path, name]) => {
    try {
      const data = C.loadLayoutBytes(fs.readFileSync(path), name), info = C.describeLayoutFile(data, name);
      const out = {ok: true, data: C.canonicalJson(data), info, counts: {}};
      for (const count of info.counts) {
        const entry = C.layoutFromFile(data, count, name);
        out.counts[count] = {entry: C.canonicalJson(entry), adjacency: C.canonicalJson(pairAdjacency(entry.layouts))};
        if (info.kind === 'preset') {
          out.counts[count].layouts = C.canonicalJson(C.stripsLayouts(count, data, name));
          out.counts[count].slice = C.canonicalJson(C.stripsSlice(count, data, name));
        } else {
          out.counts[count].adjacency_raw = C.canonicalJson(pairAdjacency(data));
        }
      }
      return out;
    } catch (error) {
      return {ok: false, name: error.name, code: error.code ?? null, message: error.message};
    }
  });
  process.stdout.write(JSON.stringify(results));
});
'''


def node_layout_files(items) -> list[dict]:
    completed = subprocess.run([node_executable(), '-e', LAYOUT_DRIVER, str(COMPILER)],
                               input=json.dumps([[str(path), name] for path, name in items]),
                               capture_output=True, text=True, check=True, timeout=300)
    return json.loads(completed.stdout)


def python_layout_file(path: Path) -> dict:
    """The Python reference for one layout file, shaped like LAYOUT_DRIVER's result."""
    try:
        data = load_layout_file(path)
    except LayoutError as error:
        return {'ok': False, 'code': error.code, 'message': str(error)}
    out = {'ok': True, 'data': c.canonical_json(data), 'counts': {}}
    if data['format'] == 'simvltanea.layout-preset/1':
        counts = {**DEFAULT_STRIPS_PRESET['counts'], **data.get('counts', {})}
        for count in range(counts['min'], counts['max'] + 1):
            layouts = strips_layouts(count, path)
            out['counts'][str(count)] = {
                'layouts': c.canonical_json(layouts), 'slice': c.canonical_json(strips_slice(count, path)),
                'adjacency': c.canonical_json({o: adjacency(layouts[o]['cells']) for o in c.ORIENTATIONS})}
    else:
        out['counts'][str(data['count'])] = {
            'adjacency': c.canonical_json({o: adjacency(data[o]['cells']) for o in c.ORIENTATIONS})}
    return out


def scratch() -> tempfile.TemporaryDirectory:
    """A disposable directory under var/work (generated output never leaves var/)."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix='compiler-layouts-', dir=WORK_DIR)


def strips_state(count: int, slice_value='strips', *, preset='strips', fps: int = 24, frames: int = 240,
                 seed=444499) -> dict:
    """A strips state whose loops wrap several times: periods (9 + 2k)/8 s, rates 1 + 7k/100."""
    sources = [dict(id=f'media-{k}', path=f'media/strip-{k}.mp4', sha256=digest(f'strip-{count}-{k}'),
                    kind='video', duration=f'{9 + 2 * k}/8') for k in range(1, count + 1)]
    state = build_strips(count, preset, sources=sources, frames=frames, fps=fps)
    state['seed'] = seed
    if slice_value is None:
        del state['slice']
    elif slice_value != 'strips':
        state['slice'] = slice_value
    c.validate_state(state)
    return state


def node_inheritance(state: dict) -> dict:
    completed = subprocess.run([node_executable(), '-e', INHERITANCE_DRIVER, str(COMPILER)],
                               input=json.dumps(state), capture_output=True, text=True, check=True, timeout=300)
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
                layouts=authored_layouts(count), fps=24, frames=48)
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
        calls, states = [], {}
        for count in sorted(AUTHORED):
            state = states[count] = authored_state(count)
            ids = [loop['id'] for loop in state['loops']]
            calls.append(['buildState', dict(
                sources=state['sources'], seed=state['seed'], fps=24, frames=144,
                loops=[dict(id=loop['id'], source=loop['bank'][0], offset=loop['offset'], rate=loop['rate'])
                       for loop in state['loops']],
                layouts=authored_layouts(count))])
            calls.append(['compilePlan', state])
            calls.append(['bindLayouts', authored_layouts(count), ids])
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
        def bank_collision(state):
            """An epoch at which loop-1's bank picks loop-2's source at frame 0."""
            return next(epoch for epoch in range(64)
                        if c.choose_source(state, dict(state['loops'][0], epoch=epoch), 0) == 'media-2')
        # Reroll and swap events and multi-source banks compile (PlayStateCompilerTests); hold and move do not.
        events = {
            'hold': dict(op='hold', frame=12, loop='loop-1', value=True),
            'move': dict(op='move', frame=12, loop='loop-1', orientation='portrait',
                         rect=['1/10', '3/100', '4/5', '21/50']),
            'hold-after-reroll': [dict(op='reroll', frame=6, loop='loop-2'),
                                  dict(op='hold', frame=12, loop='loop-1', value=True)],
        }
        # Python compiles these; the JavaScript must refuse them instead of differing.
        python_accepts = {
            'thirteen-loops': (n_loops(13), 'N=1..12'),
            'thirty-two-loops': (n_loops(32), 'N=1..12'),
            **{f'event-{name}': (edit(lambda s, e=event: s.__setitem__('events', e if isinstance(e, list) else [e])),
                                 'hold and move events')
               for name, event in events.items()},
            'audio-v1.1': (edit(lambda s: s.update(schema_version='1.1', engine_version='1.1.0')), 'Audio v1.1'),
            'unbanked-source-beside-a-bank': (edit(lambda s: (add_source(s), s['loops'][0].__setitem__(
                'bank', ['media-1', 'extra']), s['sources'].append(dict(
                    id='spare', path='media/spare.mp4', sha256=digest('spare'), kind='video', duration='8')))),
                'filler'),
            'seam-enabled': (edit(lambda s: s.__setitem__('seam', {'enabled': True})), 'seams are compiled by Python'),
            'seam-enabled-beside-slice': (edit(lambda s: s.update(slice={'enabled': True}, seam={'enabled': True})),
                                          'seams are compiled by Python'),
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
            'event-cue': (edit(lambda s: s.__setitem__('events', [dict(op='cue', frame=12, loop='loop-1')])),
                          'unsupported event: cue'),
            'event-without-op': (edit(lambda s: s.__setitem__('events', [dict(frame=12, loop='loop-1')])),
                                 'unsupported event: None'),
            'events-out-of-order': (edit(lambda s: s.__setitem__('events', [
                dict(op='reroll', frame=12, loop='loop-1'), dict(op='reroll', frame=11, loop='loop-2')])),
                'events must be ordered'),
            'event-beyond-last-frame': (edit(lambda s: s.__setitem__('events', [
                dict(op='reroll', frame=48, loop='loop-1')])), 'event.frame must be an integer'),
            'event-absent-loop': (edit(lambda s: s.__setitem__('events', [
                dict(op='reroll', frame=1, loop='loop-9')])), 'absent loop'),
            'event-extra-field': (edit(lambda s: s.__setitem__('events', [
                dict(op='reroll', frame=1, loop='loop-1', value=True)])), 'unsupported fields'),
            'swap-one-loop': (edit(lambda s: s.__setitem__('events', [dict(op='swap', frame=1, a='loop-1',
                                                                         b='loop-1')])), 'two different loops'),
            'hold-value-string': (edit(lambda s: s.__setitem__('events', [
                dict(op='hold', frame=1, loop='loop-1', value='yes')])), 'hold.value must be boolean'),
            'move-bad-rect': (edit(lambda s: s.__setitem__('events', [dict(
                op='move', frame=1, loop='loop-1', orientation='portrait', rect=['0', '0', '2', '1'])])),
                'positive area'),
            'bank-selection-reuses-a-source': (edit(lambda s: (add_source(s), s['loops'][0].__setitem__(
                'bank', ['media-2', 'extra']), s['loops'][0].__setitem__('epoch', bank_collision(s)))),
                'duplicated'),
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
            'zero-loops': (edit(lambda s: s.update(loops=[], sources=s['sources'][:1])), 'loop count must be 1..32'),
            'thirty-three-loops': (n_loops(33), 'loop count must be 1..32'),
            'per-loop-slice': (edit(lambda s: s['loops'][0].__setitem__('slice', {'enabled': True})),
                               'unsupported fields'),
            'slice-full-width': (edit(lambda s: s.__setitem__('slice', {'enabled': True, 'width': '1'})),
                                 'slice.width'),
            'slice-unknown-key': (edit(lambda s: s.__setitem__('slice', {'enabled': True, 'x': '0'})),
                                  'unsupported fields'),
            'slice-enabled-string': (edit(lambda s: s.__setitem__('slice', {'enabled': 'yes'})), 'boolean'),
            'layout-unknown-key': (edit(lambda s: s['layouts']['portrait'].__setitem__('gutter', '0')),
                                   'unsupported fields'),
            'cell-unknown-key': (edit(lambda s: s['layouts']['portrait']['cells'][0].__setitem__('z', 0)),
                                 'unsupported fields'),
            'full-bleed-with-gaps': (edit(lambda s: s['layouts']['portrait'].__setitem__('full_bleed', True)),
                                     'tile the unit square'),
            'presentation-missing-keys': (edit(lambda s: s['layouts']['portrait'].__setitem__(
                'presentation', {'overlap_px': 2})), 'missing fields'),
            'lateral-offset-without-jitter': (edit(lambda s: s['layouts']['portrait']['cells'][0].__setitem__(
                'lateral_offset', '0')), 'lateral_jitter > 0'),
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

    def test_oversized_rational_strings_are_refused_like_python(self):
        """Fraction() refuses integer strings above 4300 digits; leading zeros count."""
        limit = 4300
        def padded(value: int, digits: int) -> str:
            return str(value).zfill(digits)
        def edit(change):
            state = authored_state(2, frames=48)
            change(state)
            return state
        def loop_field(key, value):
            return lambda s: s['loops'][0].__setitem__(key, value)
        def duration(value):
            return lambda s: s['sources'][0].__setitem__('duration', value)
        def rect(value):
            return lambda s: s['layouts']['portrait']['cells'][0]['rect'].__setitem__(0, value)
        def trim(value):
            return lambda s: s['loops'][0].__setitem__('trim', ['0', value])
        # Each spelling is shown at the limit (accepted by both) and one digit beyond (refused by both).
        spellings = {
            'offset-numerator': (loop_field, 'offset', lambda d: padded(1, d) + '/2'),
            'offset-denominator': (loop_field, 'offset', lambda d: '1/' + padded(2, d)),
            'offset-integer-string': (loop_field, 'offset', lambda d: padded(3, d)),
            'rate-denominator': (loop_field, 'rate', lambda d: '1/' + padded(1, d)),
            'rate-padded-fraction': (loop_field, 'rate', lambda d: f'{padded(12, d)}/{padded(24, d)}'),
            'duration-numerator': (duration, None, lambda d: padded(8, d) + '/1'),
            'duration-denominator': (duration, None, lambda d: '16/' + padded(2, d)),
            'trim-bound': (trim, None, lambda d: padded(5, d)),
            'rect-numerator': (rect, None, lambda d: padded(0, d)),
            'negative-offset-zero': (loop_field, 'offset', lambda d: '-' + padded(0, d) + '/1'),
        }
        states = {}
        for name, (maker, key, spell) in spellings.items():
            for digits in (limit, limit + 1):
                change = maker(key, spell(digits)) if key else maker(spell(digits))
                states[name, digits] = edit(change)
        keys = list(states)
        results = node(*(['compilePlan', states[key]] for key in keys),
                       ['compilePlan', edit(loop_field('offset', '1/' + padded(2, limit + 1)))])
        for key, result in zip(keys, results):
            name, digits = key
            with self.subTest(case=name, digits=digits):
                if digits <= limit:
                    self.assertTrue(result['ok'], result)
                    self.assertSamePlan(result['value'], compile_plan(states[key]))
                else:
                    self.assertFalse(result['ok'], f'{name} with {digits} digits compiled')
                    self.assertEqual(result['name'], 'CompilerError')
                    self.assertFalse(result['unsupported'], result)
                    self.assertRegex(result['message'], f'exceeds {limit} digits')
                    with self.assertRaises(c.StateError):
                        compile_plan(states[key])
        self.assertRegex(results[-1]['message'], 'offset: rational numerator or denominator exceeds 4300 digits')

    def test_inherited_and_hidden_properties_are_refused_consistently(self):
        """No inherited property may change a plan without changing state_sha256."""
        state = authored_state(3, frames=48)
        results = node_inheritance(state)
        control = results['control-plain']
        self.assertTrue(control['ok'], control)
        self.assertSamePlan(control['plan'], compile_plan(state))
        # Null-prototype objects are plain: they behave exactly like JSON objects.
        self.assertEqual(results['control-null-prototype']['plan'], control['plan'])
        # A non-enumerable own property is not a key: validation, compilation and hashing all ignore it.
        hidden = results['hidden-own-trim']
        self.assertTrue(hidden['ok'], hidden)
        self.assertEqual(hidden['plan'], control['plan'])
        refused = [name for name in results if not name.startswith('control-') and name != 'hidden-own-trim']
        self.assertEqual(len(refused), 15)
        for name in refused:
            result = results[name]
            with self.subTest(case=name):
                self.assertFalse(result['ok'], f'{name} compiled to a plan with state_sha256 '
                                 f'{result.get("plan", {}).get("state_sha256")}')
                self.assertEqual(result['name'], 'CompilerError')
        self.assertRegex(results['inherited-trim']['message'], 'loop must be an object')
        self.assertRegex(results['class-instance-state']['message'], 'state must be an object')
        # The same loop with its trim as an own key is accepted and hashes differently.
        trimmed = copy.deepcopy(state)
        trimmed['loops'][0]['trim'] = ['1', '2']
        (own,) = node(['compilePlan', trimmed])
        self.assertTrue(own['ok'], own)
        self.assertSamePlan(own['value'], compile_plan(trimmed))
        self.assertNotEqual(own['value']['state_sha256'], control['plan']['state_sha256'])

    def test_canonical_json_sorts_keys_by_code_point_like_python(self):
        """JS sorts UTF-16 units: U+1F600 (surrogates) would precede U+E000; Python orders the reverse."""
        value = {'\U0001f600': 1, '\ue000': 2, 'a': [{'\U00010000': 3, '\uffff': 4, 'b': 5}]}
        (result,) = node(['canonicalJson', value])
        self.assertEqual(result['value'], c.canonical_json(value))
        self.assertLess(result['value'].index('\ue000'), result['value'].index('\U0001f600'))
        (hashed,) = node(['stateDigest', value])
        self.assertEqual(hashed['value'], hashlib.sha256(c.canonical_json(value).encode()).hexdigest())


class LoopCountTests(unittest.TestCase):
    """The browser subset is N=1..12: one and eight loops compile like Python; 0 and 13 refuse."""

    def grid_state(self, count: int, frames: int = 48) -> dict:
        sources = caller_sources(count, [f'{5 + k}/2' for k in range(count)])
        cells = [dict(loop=f'loop-{i + 1}', rect=[f'{i}/{count}', '0', f'1/{count}', '1'], fit='cover',
                      focal=['1/2', '1/2']) for i in range(count)]
        return dict(schema_version=1, engine_version='1.0.0', rng='sha256-counter-v1', seed=7, fps=24,
                    frames=frames, allow_source_reuse=False, sources=sources,
                    loops=[dict(id=f'loop-{i}', bank=[f'media-{i}'], offset=f'{i}/3', rate=f'{20 + i}/20',
                                period=sources[i - 1]['duration'], epoch=0, held=False) for i in range(1, count + 1)],
                    layouts={o: dict(name=f'grid-{count}-{o}', cells=copy.deepcopy(cells)) for o in c.ORIENTATIONS},
                    events=[], audio=dict(mode='none', routing=None, generative=None))

    def test_supported_counts_are_one_to_twelve(self):
        script = 'const C = require(process.argv[1]); process.stdout.write(JSON.stringify(' \
                 '[C.SUPPORTED_LOOP_COUNTS, C.MIN_LOOPS, C.MAX_LOOPS, Object.isFrozen(C.SUPPORTED_LOOP_COUNTS)]))'
        completed = subprocess.run([node_executable(), '-e', script, str(COMPILER)], capture_output=True, text=True,
                                   check=True, timeout=60)
        self.assertEqual(json.loads(completed.stdout), [list(range(1, 13)), 1, 12, True])

    def test_one_and_eight_loops_compile_like_python(self):
        states = {count: self.grid_state(count) for count in (1, 8, 12)}
        results = node(*(['compilePlan', state] for state in states.values()))
        for (count, state), result in zip(states.items(), results):
            with self.subTest(count=count):
                self.assertTrue(result['ok'], result)
                self.assertEqual(json.dumps(result['value']), json.dumps(compile_plan(state)))
                self.assertEqual(len(result['value']['tracks']), count)

    def test_zero_and_thirteen_loops_are_refused(self):
        zero = self.grid_state(1)
        zero.update(loops=[])
        thirteen = self.grid_state(13)
        compile_plan(thirteen)  # Python compiles it: the refusal is the browser subset, not the engine guard
        with self.assertRaises(c.StateError):
            compile_plan(zero)
        refused_zero, refused_thirteen = node(['compilePlan', zero], ['compilePlan', thirteen])
        self.assertFalse(refused_zero['ok'])
        self.assertFalse(refused_zero['unsupported'])
        self.assertRegex(refused_zero['message'], 'loop count must be 1..32')
        self.assertFalse(refused_thirteen['ok'])
        self.assertTrue(refused_thirteen['unsupported'])
        self.assertEqual(refused_thirteen['message'], 'outside the browser compiler subset: 13 loops; the browser '
                         'compiler covers N=1..12 independent loops (no filler, no implicit duplication)')


class SliceParityTests(unittest.TestCase):
    """An enabled state-wide slice compiles in JavaScript to exactly Python's plan."""

    def assertSamePlan(self, javascript: dict, python: dict):
        self.assertEqual(javascript, python)
        self.assertEqual(json.dumps(javascript), json.dumps(python))

    @staticmethod
    def span_at(track: dict, frame: int) -> dict:
        return [span for span in track['spans'] if span['frame'] <= frame][-1]

    def test_global_slice_matches_python_over_counts_orientations_and_period_wraps(self):
        custom = CORPUS / 'valid' / 'strips-custom-preset.json'
        states = {}
        for count in PARITY_COUNTS:
            states[count, 'no-slice'] = strips_state(count, None)
            states[count, 'disabled-slice'] = strips_state(count, {'enabled': False, 'width': '1/3'})
            states[count, 'strips-zoom'] = strips_state(count)
            states[count, 'strips-zoom-text-seed'] = strips_state(count, seed='graine-\u00e9t\u00e9')
            if count >= 2:  # landscape rows, portrait reversed, jitter and radius at their maxima
                states[count, 'custom-preset'] = strips_state(count, preset=custom, fps=25, frames=250)
        states[3, 'default-size'] = strips_state(3, {'enabled': True})
        states[5, 'height-only'] = strips_state(5, {'enabled': True, 'height': '1/3'})
        states[8, 'limit-denominator'] = strips_state(8, {'enabled': True, 'width': '123456789/987654321',
                                                          'height': '999999999/1000000000'})
        states[2, 'non-canonical-size'] = strips_state(2, {'enabled': True, 'width': '2/4', 'height': '06/10'})
        held = states[1, 'held'] = strips_state(1, seed=2**40)
        held['loops'][0].update(held=True, offset='50')
        trimmed = states[5, 'trimmed-fps-30'] = strips_state(5, fps=30, frames=300)
        for index, loop in enumerate(trimmed['loops']):
            loop['trim'] = [f'{index}/10', trimmed['sources'][index]['duration']]
        long = states[12, 'fps-60-long'] = strips_state(12, fps=60, frames=1200)
        long['loops'][11]['offset'] = '999999'
        for state in states.values():
            c.validate_state(state)
        keys = list(states)
        results = node(*(['compilePlan', states[key]] for key in keys))
        wraps = {}
        for key, result in zip(keys, results):
            state = states[key]
            with self.subTest(case=key):
                self.assertTrue(result['ok'], result)
                plan, expected = result['value'], compile_plan(state)
                self.assertSamePlan(plan, expected)
                layouts = plan['layout_keyframes'][0]['layouts']
                self.assertEqual(set(layouts), {'portrait', 'landscape'})
                self.assertEqual(layouts, json.loads(json.dumps(state['layouts'])))
                enabled = state.get('slice', {}).get('enabled', False)
                self.assertEqual(plan['slice']['enabled'], enabled)
                # Several times, every period wrap included: the active span carries resolve_at's window.
                frames = sorted({0, 1, state['fps'] - 1, state['fps'], state['frames'] - 1,
                                 *range(0, state['frames'], 7),
                                 *(span['frame'] for track in plan['tracks'] for span in track['spans'])})
                for frame in frames:
                    resolved = {loop['id']: loop for loop in c.resolve_at(state, frame)['loops']}
                    for track in plan['tracks']:
                        span = self.span_at(track, frame)
                        self.assertEqual(span.get('slice_rect'), resolved[track['id']].get('slice_rect'),
                                         (key, frame, track['id']))
                if enabled:
                    windows = [len({tuple(span['slice_rect']) for span in track['spans']}) for track in plan['tracks']]
                    wraps[key] = windows
                    self.assertTrue(all('slice_rect' in span for track in plan['tracks'] for span in track['spans']))
                else:
                    self.assertFalse(any('slice_rect' in span for track in plan['tracks'] for span in track['spans']))
        # Periods wrap: every unheld loop draws several windows in one piece; a held loop keeps one.
        for key, windows in wraps.items():
            with self.subTest(wraps=key):
                if key == (1, 'held'):
                    self.assertEqual(windows, [1])
                else:
                    self.assertGreaterEqual(min(windows), 3, windows)
        self.assertEqual(results[keys.index((5, 'height-only'))]['value']['slice'],
                         {'enabled': True, 'height': '1/3', 'width': '1/2'})
        self.assertEqual(results[keys.index((2, 'non-canonical-size'))]['value']['slice'],
                         {'enabled': True, 'width': '1/2', 'height': '3/5'})
        # limit_denominator really ran: x = (v/1000)(1 - w) has a denominator above 10**9 before it.
        rects = {tuple(span['slice_rect']) for track in results[keys.index((8, 'limit-denominator'))]['value']['tracks']
                 for span in track['spans']}
        self.assertTrue(any(Fraction(rect[0]).denominator > 1000 for rect in rects))

    def test_strips_states_built_in_javascript_compile_like_python(self):
        """The studio path: a bundle entry (layouts + slice) through buildState and compilePlan."""
        bundle = layout_bundle_v2()
        calls, expected = [], []
        for count in PARITY_COUNTS:
            entry = bundle['families']['strips']['counts'][str(count)]
            state = strips_state(count)
            data = dict(sources=state['sources'], seed=state['seed'], fps=24, frames=240, slice=entry['slice'],
                        layouts={'portrait': entry['portrait'], 'landscape': entry['landscape']},
                        loops=[dict(id=loop['id'], source=loop['bank'][0], offset=loop['offset'], rate=loop['rate'])
                               for loop in state['loops']])
            calls += [['buildState', data], ['compile', data]]
            expected.append(state)
        results = node(*calls)
        for index, count in enumerate(PARITY_COUNTS):
            built, plan = results[2 * index:2 * index + 2]
            with self.subTest(count=count):
                self.assertTrue(built['ok'] and plan['ok'], (built, plan))
                self.assertEqual(built['value'], expected[index])
                self.assertEqual(json.dumps(plan['value']), json.dumps(compile_plan(built['value'])))


class StripsExpansionParityTests(unittest.TestCase):
    """stripsLayouts, stripsSlice and adjacency give Python's canonical JSON byte for byte."""

    def test_default_strips_match_python_for_every_count(self):
        calls = []
        for count in range(1, 13):
            calls += [['stripsLayouts', count], ['stripsSlice', count]]
        results = node(*calls, ['canonicalJson', json.loads(EXAMPLE_PRESET.read_text())],
                       ['stripsLayouts', 0], ['stripsLayouts', 13], ['stripsLayouts', 3, 'authored'])
        for count in range(1, 13):
            layouts, size = results[2 * count - 2:2 * count]
            with self.subTest(count=count):
                self.assertTrue(layouts['ok'] and size['ok'], (layouts, size))
                self.assertEqual(c.canonical_json(layouts['value']), c.canonical_json(strips_layouts(count)))
                self.assertEqual(json.dumps(layouts['value']), json.dumps(strips_layouts(count)))
                self.assertEqual(json.dumps(size['value']), json.dumps(strips_slice(count)))
        self.assertEqual(results[24]['value'], c.canonical_json(DEFAULT_STRIPS_PRESET))
        for result, code in zip(results[25:], ('count-range', 'count-range', 'preset')):
            self.assertFalse(result['ok'])
            self.assertEqual(result['code'], code)
        self.assertEqual(results[26]['message'], "strips preset 'strips' supports N=1..12; count 13 is refused "
                         '(no filler, no duplication, never moved to another family)')

    def test_default_preset_data_is_python_data(self):
        script = 'const C = require(process.argv[1]); process.stdout.write(C.canonicalJson(C.DEFAULT_STRIPS_PRESET))'
        completed = subprocess.run([node_executable(), '-e', script, str(COMPILER)], capture_output=True, text=True,
                                   check=True, timeout=60)
        self.assertEqual(completed.stdout, c.canonical_json(DEFAULT_STRIPS_PRESET))

    def test_preset_objects_are_checked_at_every_advertised_count(self):
        """A preset object is refused when any count it advertises fails, not only the requested one."""
        # N=2 alone is fine (s = 1/2); N=1 rounds 1/5 to an empty slice at quantum 1/2.
        preset = {'format': 'simvltanea.layout-preset/1', 'name': 'zoomy', 'family': 'strips',
                  'counts': {'min': 1, 'max': 2}, 'zoom': {'z1': '5', 'gamma': '1', 'quantum': 2}}
        results = node(['stripsLayouts', 2, preset], ['stripsSlice', 2, preset])
        for result, function in zip(results, (strips_layouts, strips_slice)):
            with self.subTest(function=function.__name__):
                with self.assertRaises(LayoutError) as caught:
                    function(2, preset)
                self.assertEqual(caught.exception.code, 'zoom')
                self.assertFalse(result['ok'], result)
                self.assertEqual((result['code'], result['message']), (caught.exception.code, str(caught.exception)))

    def test_oversized_count_keys_are_refused_with_the_call_site_code(self):
        """A 5000-digit count key is refused before conversion, with a bounded key excerpt.

        The message is the one layout_presets._count_key gives since it checks the length before int()
        (origin/main 404a71c). An older _count_key raises ValueError past 4300 digits, so the codes are
        compared with Python under an unlimited int() digit limit.
        """
        key = '9' * 5000
        base = {'format': 'simvltanea.layout-preset/1', 'name': 'huge', 'family': 'strips'}
        cases = [('weights', {'weights': {'default': 'equal', 'by_count': {key: ['1']}}}, 'weights.by_count', 1, 12),
                 ('focal', {'focal': {'default': ['1/2', '1/2'], 'by_index': {key: ['0', '0']}}}, 'focal.by_index',
                  0, 11),
                 ('zoom', {'zoom': {'table': {key: '1/2'}}}, 'zoom.table', 1, 12)]
        results = node(*(['stripsLayouts', 1, {**base, **change}] for _, change, _, _, _ in cases))
        limit = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(0)
        self.addCleanup(sys.set_int_max_str_digits, limit)
        for (code, change, label, low, high), result in zip(cases, results):
            with self.subTest(code=code):
                with self.assertRaises(LayoutError) as caught:
                    strips_layouts(1, {**base, **change})
                self.assertEqual(caught.exception.code, code)
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['code'], code)
                self.assertEqual(result['message'], f'{label} key {key[:40]!r} must be an integer string in {low}..{high}')

    def generated_presets(self, root: Path) -> list[Path]:
        def preset(name, **changes):
            data = {'format': 'simvltanea.layout-preset/1', 'name': name, 'family': 'strips', **changes}
            path = root / f'{name}.json'
            path.write_text(json.dumps(data, indent=1))
            return path
        primes = ['2', '3', '5', '7', '11', '13', '17', '19', '23', '29', '31', '37']
        return [
            preset('jitter-max', style={'corner_radius': '1/20', 'lateral_jitter': '1/20'}, overlap_px=8),
            preset('jitter-max-b', style={'corner_radius': '0', 'lateral_jitter': '1/20'}),
            preset('jitter-step', style={'corner_radius': '0', 'lateral_jitter': '1/1000'}),
            preset('jitter-below-step', style={'corner_radius': '0', 'lateral_jitter': '1/1999'}),
            preset('unequal', weights={'default': 'equal', 'by_count': {
                str(n): primes[:n][::-1] if n % 2 else [f'{k + 1}/{n}' for k in range(n)] for n in range(1, 13)}}),
            # Edges and sizes at denominator exactly 10**9: the largest the weights bound accepts.
            preset('weights-bound', weights={'default': 'equal', 'by_count': {'2': ['999999999', '1']}}),
            preset('spelled', weights={'default': 'equal', 'by_count': {
                '4': ['0.5', ' 1/3 ', '1_0', '1 / 3'], '3': ['1e1', '+2', '25E-1']}}),
            preset('turned', orientations={'portrait': {'direction': 'columns', 'order': 'reverse'},
                                           'landscape': {'direction': 'rows', 'order': 'reverse'}},
                   focal={'default': ['0', '1'], 'by_index': {'0': ['1/3', '2/3'], '11': ['1', '0']}}),
            preset('gamma-zero', zoom={'gamma': '0', 'z1': '7/2'}),
            preset('gamma-two', zoom={'gamma': '2', 'z1': '50', 'quantum': 97}),
            preset('gamma-fine', zoom={'gamma': '99/100', 'z1': '9', 'quantum': 999983, 'min_zoom': '1001/1000'}),
            preset('gamma-tiny', zoom={'gamma': '1/100', 'z1': '3', 'quantum': 1000000}),
            preset('tiny-z1', zoom={'z1': '1/1000000000', 'gamma': '3/5'}),
            preset('table', counts={'min': 4, 'max': 9}, zoom={'table': {'9': '1/1000', '4': '9/10', '6': '1/2'}}),
            preset('contain', fit='contain', full_bleed=False, overlap_px=0),
        ]

    def test_preset_files_expand_like_python(self):
        with scratch() as tmp:
            files = [EXAMPLE_PRESET, *(CORPUS / name for name in json.loads((CORPUS / 'corpus.json').read_text())['valid']),
                     *self.generated_presets(Path(tmp))]
            results = node_layout_files((path, str(path)) for path in files)
            expanded = 0
            for path, result in zip(files, results):
                expected = python_layout_file(path)
                with self.subTest(file=path.name):
                    self.assertTrue(expected['ok'], expected)
                    self.assertTrue(result['ok'], result)
                    self.assertEqual(result['data'], expected['data'])
                    self.assertEqual(sorted(result['counts'], key=int), sorted(expected['counts'], key=int))
                    data = json.loads(path.read_text())
                    for count, values in expected['counts'].items():
                        mine = result['counts'][count]
                        self.assertEqual(mine['adjacency'], values['adjacency'], count)
                        if 'layouts' in values:
                            expanded += 1
                            self.assertEqual(mine['layouts'], values['layouts'], count)
                            self.assertEqual(mine['slice'], values['slice'], count)
                            self.assertEqual(mine['entry'], c.canonical_json(
                                {'layouts': json.loads(values['layouts']), 'slice': json.loads(values['slice'])}))
                        else:
                            self.assertEqual(mine['adjacency_raw'], values['adjacency'])
                            canonical = copy.deepcopy({o: data[o] for o in c.ORIENTATIONS})
                            for layout in canonical.values():
                                for cell in layout['cells']:
                                    for key in ('rect', 'focal'):
                                        cell[key] = [str(c.rational(v, key)) for v in cell[key]]
                                    if 'lateral_offset' in cell:
                                        cell['lateral_offset'] = str(c.rational(cell['lateral_offset'], 'offset'))
                                for key in ('corner_radius', 'lateral_jitter'):
                                    if 'presentation' in layout:
                                        layout['presentation'][key] = str(c.rational(layout['presentation'][key], key))
                            self.assertEqual(mine['entry'], c.canonical_json({'layouts': canonical, 'slice': None}))
            self.assertGreater(expanded, 150)
            # The maxima really are exercised: offsets reach both signs and the unequal weights differ.
            jitter = json.loads(results[files.index(Path(tmp) / 'jitter-max.json')]['counts']['12']['layouts'])
            offsets = [Fraction(cell['lateral_offset']) for cell in jitter['portrait']['cells']]
            self.assertTrue(min(offsets) < 0 < max(offsets) and max(map(abs, offsets)) <= Fraction(1, 20))
            unequal = json.loads(results[files.index(Path(tmp) / 'unequal.json')]['counts']['5']['layouts'])
            self.assertEqual(len({cell['rect'][3] for cell in unequal['portrait']['cells']}), 5)


class LayoutFileErrorParityTests(unittest.TestCase):
    """Invalid layout files fail in JavaScript with Python's LayoutError code and message."""

    def assertSameFailure(self, path: Path, result: dict, code: str | None = None):
        expected = python_layout_file(path)
        self.assertFalse(expected['ok'], f'{path.name} is valid in Python')
        self.assertFalse(result['ok'], f'{path.name} loaded in JavaScript: {result}')
        self.assertEqual(result['code'], expected['code'], (result['message'], expected['message']))
        if code is not None:
            self.assertEqual(expected['code'], code)
        if expected['code'] == 'json':
            # Syntax wording comes from each JSON decoder; both name the file first.
            self.assertTrue(result['message'].startswith(f'{path}: '), result['message'])
        else:
            self.assertEqual(result['message'], expected['message'])

    def test_conformance_corpus_fails_with_the_same_codes(self):
        manifest = json.loads((CORPUS / 'corpus.json').read_text())
        items = list(manifest['invalid'].items())
        results = node_layout_files((CORPUS / name, str(CORPUS / name)) for name, _ in items)
        for (name, code), result in zip(items, results):
            with self.subTest(file=name):
                self.assertSameFailure(CORPUS / name, result, code)
        self.assertEqual(len(results), 39)

    def test_corner_rule_needs_earlier_spans_along_the_whole_radius(self):
        # A 1/100 corner cell backs the wide cell's rounded corner for 1/100 of the width, not the 1/20 radius.
        def pair_file(directory, edge):
            e = Fraction(edge)
            rects = [['0', '0', edge, '1/2'], [str(1 - e), '0', edge, '1/2'], ['0', '1/2', '1', '1/2'],
                     [edge, '0', '1/50', '1/2'], [str(e + Fraction(1, 50)), '0', str(1 - 2 * e - Fraction(1, 50)), '1/2']]
            layout = {'name': f'corner-{edge}', 'full_bleed': True,
                      'presentation': {'overlap_px': 2, 'corner_radius': '1/20', 'lateral_jitter': '0'},
                      'cells': [{'loop': f'loop-{k + 1}', 'rect': rect, 'fit': 'cover', 'focal': ['1/2', '1/2']}
                                for k, rect in enumerate(rects)]}
            path = Path(directory) / f"corner-{edge.replace('/', '-')}.json"
            path.write_text(json.dumps({'format': 'simvltanea.layout-pair/1', 'count': 5,
                                        'portrait': layout, 'landscape': layout}))
            return path
        with tempfile.TemporaryDirectory() as tmp:
            narrow, exact_radius = pair_file(tmp, '1/100'), pair_file(tmp, '1/20')
            results = node_layout_files((path, str(path)) for path in (narrow, exact_radius))
            self.assertSameFailure(narrow, results[0], 'corner-rule')
            self.assertIn('has earlier-drawn neighbours beneath only 1/100 from it, less than corner_radius 1/20',
                          results[0]['message'])
            self.assertTrue(python_layout_file(exact_radius)['ok'])
            self.assertTrue(results[1]['ok'], results[1])

    def test_pair_files_beyond_the_compiler_subset_are_refused_when_described(self):
        # Python accepts pairs of up to 32 loops; the studio asks describeLayoutFile what a file offers, so a pair
        # the compiler cannot play must be refused there, before anyone picks videos for it.
        def pair_of(count):
            cells = lambda: [{'loop': f'loop-{i + 1}', 'rect': ['0', f'{i}/{count}', '1', f'1/{count}'],
                              'fit': 'cover', 'focal': ['1/2', '1/2']} for i in range(count)]
            return {'format': 'simvltanea.layout-pair/1', 'count': count,
                    'portrait': {'name': f'rows-{count}', 'cells': cells()},
                    'landscape': {'name': f'rows-{count}', 'cells': cells()}}
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for count in (12, 13, 32):
                paths[count] = Path(tmp) / f'rows-{count}.json'
                paths[count].write_text(json.dumps(pair_of(count)))
                self.assertTrue(python_layout_file(paths[count])['ok'], count)  # valid in Python at every count
            results = node_layout_files((paths[count], str(paths[count])) for count in (12, 13, 32))
        self.assertTrue(results[0]['ok'], results[0])
        for count, result in zip((13, 32), results[1:]):
            with self.subTest(count=count):
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['name'], 'CompilerError')
                self.assertIn(f'places {count} loops; the browser compiler covers N=1..12', result['message'])

    def test_mutated_files_fail_like_python(self):
        pair = json.loads((CORPUS / 'valid' / 'strips-3-pair.json').read_text())
        base = {'format': 'simvltanea.layout-preset/1', 'name': 'm', 'family': 'strips'}

        def mutate_pair(change):
            data = copy.deepcopy(pair)
            change(data)
            return json.dumps(data)

        texts = {
            'float-overlap': json.dumps({**base, 'overlap_px': 2}).replace('"overlap_px": 2', '"overlap_px": 2.0'),
            'float-count-min': json.dumps({**base, 'counts': {'min': 2, 'max': 4}}).replace('"min": 2', '"min": 2.0'),
            'exponent-quantum': json.dumps({**base, 'zoom': {'quantum': 1000}}).replace('1000', '1e3'),
            'nan': json.dumps(base)[:-1] + ', "overlap_px": NaN}',
            'infinity': json.dumps(base)[:-1] + ', "overlap_px": -Infinity}',
            'nested-duplicate': json.dumps(base)[:-1] + ', "counts": {"min": 1, "min": 2}}',
            'bom': '\ufeff' + json.dumps(base),
            'trailing-comma': json.dumps(base)[:-1] + ',}',
            'empty': '',
            'extra-data': json.dumps(base) + ' {}',
            'top-level-array': '[]',
            'no-format': json.dumps({'name': 'x'}),
            'format-quote': json.dumps({**base, 'format': "it's"}),
            'format-null': json.dumps({**base, 'format': None}),
            'format-list': json.dumps({**base, 'format': [1, 'a', True, {'b': None}]}),
            'format-float': json.dumps({**base, 'format': 1e16}),
            'format-small-float': json.dumps({**base, 'format': 0.0001}),
            'weights-order': '{"format": "simvltanea.layout-preset/1", "name": "m", "family": "strips", '
                             '"weights": {"default": "equal", "by_count": {"12": ["1"], "3": ["1", "0", "1"]}}}',
            'weights-key': json.dumps({**base, 'weights': {'default': 'equal', 'by_count': {'03': ['1', '1', '1']}}}),
            'weights-huge-exponent': json.dumps({**base, 'weights': {'default': 'equal',
                                                                     'by_count': {'2': ['1e999999', '1']}}}),
            'weights-tiny-exponent': json.dumps({**base, 'weights': {'default': 'equal',
                                                                     'by_count': {'2': ['1e-50000', '1']}}}),
            'weights-bool': json.dumps({**base, 'weights': {'default': 'equal', 'by_count': {'2': [True, '1']}}}),
            'weights-huge-integer': json.dumps({**base, 'weights': {'default': 'equal',
                                                                    'by_count': {'2': [10**30, 1]}}}),
            'weights-size-denominator': json.dumps({**base, 'weights': {'default': 'equal',
                                                                        'by_count': {'2': ['1', '1000000000']}}}),
            'weights-edge-denominator': json.dumps({**base, 'weights': {'default': 'equal',
                                                                        'by_count': {'2': ['2', '999999999']}}}),
            'focal-index-range': json.dumps({**base, 'counts': {'min': 1, 'max': 3},
                                             'focal': {'default': ['1/2', '1/2'], 'by_index': {'3': ['0', '0']}}}),
            'min-zoom-empty-slice': json.dumps({**base, 'zoom': {'min_zoom': '1000', 'quantum': 2}}),
            'table-not-multiple': json.dumps({**base, 'zoom': {'table': {'3': '1/3'}}}),
            'gamma-denominator': json.dumps({**base, 'zoom': {'gamma': '1/101'}}),
            'curve': json.dumps({**base, 'zoom': {'curve': 'exponential'}}),
            'orientation-not-object': json.dumps({**base, 'orientations': {'portrait': 'rows'}}),
            'name-invalid': json.dumps({**base, 'name': 'has space'}),
            'counts-inverted': json.dumps({**base, 'counts': {'min': 5, 'max': 4}}),
            'radius-reverse-single': json.dumps({**base, 'counts': {'min': 1, 'max': 2},
                                                 'style': {'corner_radius': '1/40', 'lateral_jitter': '0'},
                                                 'orientations': {'portrait': {'order': 'reverse'}}}),
            'pair-count-float': mutate_pair(lambda d: d.__setitem__('count', 3)).replace('"count": 3', '"count": 3.0'),
            'pair-count-33': mutate_pair(lambda d: d.__setitem__('count', 33)),
            # The cell count is checked before any per-cell geometry, so the bad fit on cell 0 is never reached.
            'pair-count-before-geometry': mutate_pair(lambda d: (
                d.__setitem__('count', 2), d['portrait']['cells'][0].__setitem__('fit', 'stretch'))),
            'pair-portrait-string': mutate_pair(lambda d: d.__setitem__('portrait', 'rows')),
            'pair-landscape-first': json.dumps({'format': pair['format'], 'count': 3,
                                                'landscape': {**pair['landscape'], 'name': ''},
                                                'portrait': {**pair['portrait'], 'gutter': 1}}),
            'pair-rect-infinite': mutate_pair(lambda d: d['portrait']['cells'][0].__setitem__('rect', [0, 0, 1, 1e400])),
            'pair-focal-bool': mutate_pair(lambda d: d['portrait']['cells'][1].__setitem__('focal', [True, '1/2'])),
            'pair-focal-second-bad': mutate_pair(lambda d: d['portrait']['cells'][1].__setitem__('focal', ['1/2', 'x'])),
            'pair-loop-id': mutate_pair(lambda d: d['landscape']['cells'][2].__setitem__('loop', 'loop 3')),
            'pair-jitter-offset-decimal': mutate_pair(lambda d: (
                d['portrait']['presentation'].__setitem__('lateral_jitter', '1/40'),
                [cell.__setitem__('lateral_offset', '0.03') for cell in d['portrait']['cells']])),
            'pair-radius-text': mutate_pair(lambda d: d['portrait']['presentation'].__setitem__('corner_radius', '1/0')),
            'pair-overlap-bool': mutate_pair(lambda d: d['portrait']['presentation'].__setitem__('overlap_px', True)),
            'pair-full-bleed-null': mutate_pair(lambda d: d['portrait'].__setitem__('full_bleed', None)),
            'pair-cells-object': mutate_pair(lambda d: d['portrait'].__setitem__('cells', {})),
            'pair-duplicate-loop': mutate_pair(lambda d: d['portrait']['cells'][2].__setitem__('loop', 'loop-1')),
            'pair-control-character': json.dumps(pair).replace('strips-3-portrait', 'strips-3\\u0000') + '',
            'pair-raw-control-character': json.dumps(pair).replace('strips-3-portrait', 'strips\t3'),
            'pair-bad-escape': json.dumps(pair).replace('strips-3-portrait', 'strips\\q'),
        }
        with scratch() as tmp:
            paths = {}
            for name, value in texts.items():
                paths[name] = Path(tmp) / f'{name}.json'
                paths[name].write_text(value, encoding='utf-8')
            paths['not-utf8'] = Path(tmp) / 'not-utf8.json'
            paths['not-utf8'].write_bytes(b'{"format": "\xff"}')
            results = node_layout_files((path, str(path)) for path in paths.values())
            # An escaped NUL is a legal JSON string and layout name; a reversed pair rounds only shared corners.
            valid = {'pair-control-character', 'radius-reverse-single'}
            codes = {'weights-size-denominator': 'weights', 'weights-edge-denominator': 'weights',
                     'pair-count-before-geometry': 'cell-count'}
            for (name, path), result in zip(paths.items(), results):
                with self.subTest(case=name):
                    if name in valid:
                        self.assertTrue(python_layout_file(path)['ok'])
                        self.assertTrue(result['ok'], result)
                    else:
                        self.assertSameFailure(path, result, codes.get(name))

    def test_valid_spellings_and_the_non_ascii_digit_deviation(self):
        """Python's Fraction() spellings load; non-ASCII digits are the one documented refusal."""
        base = {'format': 'simvltanea.layout-preset/1', 'name': 'digits', 'family': 'strips',
                'weights': {'default': 'equal', 'by_count': {'2': ['\u0661', '1']}}}
        with scratch() as tmp:
            path = Path(tmp) / 'digits.json'
            path.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
            self.assertTrue(python_layout_file(path)['ok'])
            (result,) = node_layout_files([(path, 'digits.json')])
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'weights')
        self.assertEqual(result['message'], 'digits.json, count 2: weights.by_count: invalid rational')


class LayoutBundleTests(unittest.TestCase):
    def test_bundle_is_derived_from_authored_geometry(self):
        bundle = authored_layout_bundle()
        self.assertEqual(list(bundle), [str(count) for count in BUNDLE_AUTHORED_COUNTS])
        self.assertEqual(list(bundle), ['2', '3', '4', '5', '6', '7'])
        self.assertEqual(sorted(AUTHORED), list(range(2, 13)), 'authored counts 8..12 exist but are not bundled')
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

    def run_module(self, *arguments: str) -> bytes:
        src = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(src), str(src.parent)]))
        return subprocess.run([sys.executable, '-m', 'simvltanea.browser.layout_bundle', *arguments], env=env,
                              capture_output=True, check=True, timeout=120).stdout

    def test_module_entry_prints_the_bundle(self):
        output = self.run_module()
        self.assertEqual(json.loads(output), authored_layout_bundle())

    def test_default_output_is_the_legacy_bundle_byte_for_byte(self):
        """No flag (and --format 1) keeps the pre-v2 bytes; the digest was taken before v2 existed."""
        for arguments in ((), ('--format', '1')):
            with self.subTest(arguments=arguments):
                output = self.run_module(*arguments)
                self.assertEqual(hashlib.sha256(output).hexdigest(), LEGACY_BUNDLE_SHA256)
                self.assertEqual(output, (render_bundle(1) + '\n').encode())

    def test_format_two_has_the_specified_shape(self):
        output = self.run_module('--format', '2')
        self.assertEqual(output, (render_bundle(2) + '\n').encode())
        bundle = json.loads(output)
        self.assertEqual(bundle, layout_bundle_v2())
        self.assertEqual(list(bundle), ['format', 'default_family', 'families'])
        self.assertEqual((bundle['format'], bundle['default_family']), ('simvltanea.layout-bundle/2', 'strips'))
        self.assertEqual(list(bundle['families']), ['authored', 'strips'])
        authored, strips = bundle['families']['authored'], bundle['families']['strips']
        self.assertEqual(authored, {'counts': authored_layout_bundle()})
        self.assertEqual(list(authored['counts']), [str(n) for n in range(2, 8)])
        self.assertEqual(strips['preset'], {'format': 'simvltanea.layout-preset/1', 'name': 'strips'})
        self.assertEqual(list(strips['counts']), [str(n) for n in range(1, 13)])
        for count, entry in strips['counts'].items():
            with self.subTest(count=count):
                n = int(count)
                self.assertEqual(list(entry), ['portrait', 'landscape', 'slice', 'adjacency'])
                self.assertEqual({'portrait': entry['portrait'], 'landscape': entry['landscape']}, strips_layouts(n))
                self.assertEqual(entry['slice'], strips_slice(n))
                self.assertEqual(entry['adjacency'], {o: adjacency(entry[o]['cells']) for o in c.ORIENTATIONS})
                self.assertEqual(len(entry['adjacency']['portrait']), n - 1)
                self.assertEqual(entry, strips_entry(n))
        self.assertEqual(strips['counts']['5']['slice'], {'enabled': True, 'width': '41/125', 'height': '41/125'})
        self.assertEqual(strips['counts']['3']['adjacency']['portrait'],
                         [{'a': 0, 'b': 1, 'edge': 'bottom', 'span': ['0', '1']},
                          {'a': 1, 'b': 2, 'edge': 'bottom', 'span': ['0', '1']}])

    def test_compiler_reads_both_bundle_formats(self):
        legacy, v2 = authored_layout_bundle(), layout_bundle_v2()
        broken = copy.deepcopy(v2)
        broken['families']['strips']['counts']['13'] = broken['families']['strips']['counts']['12']
        results = node(['layoutFamilies', legacy], ['layoutFamilies', v2],
                       ['layoutEntry', legacy, 'authored', 3], ['layoutEntry', v2, 'authored', 3],
                       ['layoutEntry', v2, 'strips', 5], ['layoutEntry', v2, 'authored', 8],
                       ['layoutEntry', v2, 'strips', 13], ['layoutEntry', legacy, 'strips', 5],
                       ['layoutFamilies', broken], ['layoutFamilies', dict(v2, format='simvltanea.layout-bundle/3')],
                       ['layoutFamilies', dict(v2, default_family='grid')])
        self.assertEqual(results[0]['value'], {'format': 'simvltanea.layout-bundle/1', 'default_family': 'authored',
                                               'families': {'authored': {'counts': list(range(2, 8)), 'preset': None}}})
        self.assertEqual(results[1]['value'], {'format': 'simvltanea.layout-bundle/2', 'default_family': 'strips',
                                               'families': {'authored': {'counts': list(range(2, 8)), 'preset': None},
                                                            'strips': {'counts': list(range(1, 13)),
                                                                       'preset': v2['families']['strips']['preset']}}})
        self.assertEqual(results[2]['value'], {'layouts': legacy['3'], 'slice': None, 'adjacency': None})
        self.assertEqual(results[3]['value'], results[2]['value'])
        entry = strips_entry(5)
        self.assertEqual(results[4]['value'], {'layouts': {'portrait': entry['portrait'], 'landscape': entry['landscape']},
                                               'slice': entry['slice'], 'adjacency': entry['adjacency']})
        for result, pattern in zip(results[5:], ('authored family has no layout for 8 loops; it covers 2, 3, 4, 5, 6, 7',
                                                  'strips family has no layout for 13 loops',
                                                  'no family "strips"', 'count 13; the browser compiler covers N=1..12',
                                                  'format must be simvltanea.layout-bundle/2', 'default_family')):
            with self.subTest(pattern=pattern):
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['name'], 'CompilerError')
                self.assertIn(pattern, result['message'])


class StagingParityTests(unittest.TestCase):
    """stagePreview reproduces build_preview's plan for the generated N=2..12 fixtures."""

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


# compilePlan on one state, timed inside Node so the JSON transfer is not counted.
TIMED_DRIVER = r'''
const C = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const state = JSON.parse(input), start = process.hrtime.bigint();
  const plan = C.compilePlan(state);
  const seconds = Number(process.hrtime.bigint() - start) / 1e9;
  process.stdout.write(JSON.stringify({seconds, plan}));
});
'''
# Generous on purpose: 0.1 to 0.9 s measured in Node 26, against the 35 to 40 s of the per-frame replay (issue #61).
LARGE_STATE_SECONDS = 20


def play_state(n: int, seconds: float, seed=7, pool: int = 60, **sections) -> dict:
    """A state from the play engine itself (schedule_play on test_gravity_pool's synthetic pool)."""
    from simvltanea.authoring.test_play_support import cfg, play
    return play(cfg('sticky', **sections), n, seconds, seed, pool=pool)


def source_at(spans: list[dict], frame: int) -> str:
    return spans[bisect.bisect_right([span['frame'] for span in spans], frame) - 1]['source']


class PlayStateCompilerTests(unittest.TestCase):
    """Play states (reroll and swap events over multi-source banks) compile to Python's plan exactly."""

    def assertSamePlan(self, javascript: dict, python: dict):
        self.assertEqual(javascript, python)
        self.assertEqual(json.dumps(javascript), json.dumps(python))

    def assertSameOutcome(self, state: dict, result: dict):
        """The JavaScript plan equals Python's, or both refuse (Python refuses, JS throws unsupported false)."""
        try:
            expected = compile_plan(state)
        except c.StateError as error:
            self.assertFalse(result['ok'], f'Python refused ({error}) but JavaScript compiled')
            self.assertEqual(result['name'], 'CompilerError')
            self.assertFalse(result['unsupported'], result['message'])
            return None
        self.assertTrue(result['ok'], result)
        self.assertSamePlan(result['value'], expected)
        return expected

    def test_play_states_for_three_and_seven_loops_match_python(self):
        cases = {
            'n3-swaps': play_state(3, 30, timing={'swap_interval': 2.0})['state'],
            'n3': play_state(3, 60, seed='three')['state'],
            'n7': play_state(7, 60)['state'],
            'n7-seed-2': play_state(7, 45, seed=2)['state'],
        }
        for name, state in list(cases.items()):
            sliced = copy.deepcopy(state)
            sliced['slice'] = {'enabled': True, 'width': '1/3', 'height': '1/2'}
            cases[f'{name}-slice'] = sliced
        results = node(*(['compilePlan', state] for state in cases.values()))
        for (name, state), result in zip(cases.items(), results):
            with self.subTest(case=name):
                ops = {event['op'] for event in state['events']}
                self.assertIn('reroll', ops)
                self.assertTrue(any(len(loop['bank']) > 1 for loop in state['loops']))
                if name.startswith('n3-swaps'):
                    self.assertIn('swap', ops)
                self.assertTrue(result['ok'], result)
                self.assertSamePlan(result['value'], compile_plan(state))
                spans = sum(len(track['spans']) for track in result['value']['tracks'])
                self.assertGreater(spans, len(state['loops']), 'events must split spans')

    def test_positive_controls_a_mutated_seed_or_event_changes_the_plan(self):
        out = play_state(3, 30, timing={'swap_interval': 2.0})
        state = out['state']
        original = compile_plan(state)['tracks']
        rerolls = [index for index, event in enumerate(state['events']) if event['op'] == 'reroll']
        # Two rerolls of different loops at different frames, exchanged between the loops.
        first = rerolls[0]
        second = next(index for index in rerolls if state['events'][index]['loop'] != state['events'][first]['loop']
                      and state['events'][index]['frame'] != state['events'][first]['frame'])
        swaps = [index for index, event in enumerate(state['events']) if event['op'] == 'swap']
        mutants = {}
        for seed in (8, 9, 10, 'other'):
            mutants[f'seed-{seed}'] = dict(copy.deepcopy(state), seed=seed)
        exchanged = copy.deepcopy(state)
        events = exchanged['events']
        events[first]['loop'], events[second]['loop'] = events[second]['loop'], events[first]['loop']
        mutants['exchanged-rerolls'] = exchanged
        mutants['dropped-swap'] = dict(copy.deepcopy(state),
                                       events=[e for i, e in enumerate(state['events']) if i != swaps[0]])
        mutants['dropped-reroll'] = dict(copy.deepcopy(state),
                                         events=[e for i, e in enumerate(state['events']) if i != first])
        results = node(['compilePlan', state], *(['compilePlan', mutant] for mutant in mutants.values()))
        self.assertSamePlan(results[0]['value'], compile_plan(state))
        compiled = 0
        for (name, mutant), result in zip(mutants.items(), results[1:]):
            with self.subTest(mutant=name):
                expected = self.assertSameOutcome(mutant, result)
                if expected is not None:
                    compiled += 1
                    self.assertNotEqual(result['value']['tracks'], original, f'{name} left every span unchanged')
        self.assertGreaterEqual(compiled, 3, 'too few mutants compiled to show that plans change')

    def test_single_source_bank_play_states_compile_as_before(self):
        every = [['loop-1', 'clip-001'], ['loop-2', 'clip-002'], ['loop-3', 'clip-003']]
        pinned = play_state(3, 20, path={'pins': every})['state']
        partly = play_state(3, 20, path={'pins': every[:1]})['state']
        self.assertEqual((pinned['events'], [len(loop['bank']) for loop in pinned['loops']]), ([], [1, 1, 1]))
        self.assertEqual(len(partly['loops'][0]['bank']), 1)
        self.assertGreater(len(partly['loops'][1]['bank']), 1)
        # The same pinned state built through buildState, the pre-play path, gives the same plan.
        caller = dict(sources=pinned['sources'], seed=pinned['seed'], fps=pinned['fps'], frames=pinned['frames'],
                      layouts=pinned['layouts'],
                      loops=[dict(id=loop['id'], source=loop['bank'][0], offset=loop['offset'], rate=loop['rate'])
                             for loop in pinned['loops']])
        results = node(['compilePlan', pinned], ['compilePlan', partly], ['compile', caller])
        for name, state, result in (('pinned', pinned, results[0]), ('partly-pinned', partly, results[1])):
            with self.subTest(case=name):
                self.assertTrue(result['ok'], result)
                self.assertSamePlan(result['value'], compile_plan(state))
        self.assertTrue(results[2]['ok'], results[2])
        self.assertEqual(results[2]['value']['tracks'], results[0]['value']['tracks'])

    def cycle_state(self, slice_value=None) -> dict:
        """Banks whose pick also changes with the selection cycle (short periods), trims, swaps and rerolls."""
        state = authored_state(3, frames=96)
        extra = {'alt-1-a': '5/2', 'alt-1-b': '3', 'alt-2-a': '7/2', 'alt-2-b': '4'}
        state['sources'] += [dict(id=ident, path=f'media/{ident}.mp4', sha256=digest(ident), kind='video',
                                  duration=duration) for ident, duration in extra.items()]
        one, two, three = state['loops']
        one.update(bank=['media-1', 'alt-1-a', 'alt-1-b'], period='1/2', rate='1', offset='0')
        two.update(bank=['alt-2-a', 'media-2', 'alt-2-b'], period='2/3', rate='5/4', offset='1/3')
        three.update(bank=['media-3'], period='1', trim=['1', '2'])
        state['events'] = [dict(op='reroll', frame=10, loop='loop-1'), dict(op='reroll', frame=20, loop='loop-3'),
                           dict(op='swap', frame=30, a='loop-1', b='loop-2'),
                           dict(op='reroll', frame=50, loop='loop-1'), dict(op='reroll', frame=50, loop='loop-2'),
                           dict(op='reroll', frame=50, loop='loop-2'),
                           # Two swaps of one pair at one frame cancel out: the second reads the pins the first set.
                           dict(op='swap', frame=70, a='loop-2', b='loop-1'),
                           dict(op='swap', frame=70, a='loop-1', b='loop-2')]
        if slice_value is not None:
            state['slice'] = slice_value
        return state

    def test_selection_cycles_trims_and_epoch_only_rerolls_match_python(self):
        plain, sliced = self.cycle_state(), self.cycle_state({'enabled': True, 'width': '1/2', 'height': '2/5'})
        too_long = self.cycle_state()
        too_long['loops'][0]['bank'] = ['alt-1-a']
        too_long['sources'] = [s for s in too_long['sources'] if s['id'] not in ('media-1', 'alt-1-b')]
        too_long['loops'][2]['trim'] = ['1', '3']
        too_long['events'] = [dict(op='swap', frame=5, a='loop-1', b='loop-3')]
        results = node(['compilePlan', plain], ['compilePlan', sliced], ['compilePlan', too_long])
        plans = {}
        for name, state, result in (('plain', plain, results[0]), ('slice', sliced, results[1])):
            with self.subTest(case=name):
                self.assertTrue(result['ok'], result)
                self.assertSamePlan(result['value'], compile_plan(state))
                plans[name] = result['value']['tracks']
        # Source changes at frames without an event come from the selection cycle alone.
        event_frames = {event['frame'] for event in plain['events']}
        by_cycle = [(track['id'], span['frame']) for track in plans['plain'][:2]
                    for before, span in zip(track['spans'], track['spans'][1:])
                    if span['frame'] not in event_frames and span['source'] != before['source']]
        self.assertGreaterEqual(len(by_cycle), 2, by_cycle)
        # loop-3's single-source bank is rerolled at frame 20: only the slice window (epoch domain) moves.
        self.assertNotIn(20, [span['frame'] for span in plans['plain'][2]['spans']])
        self.assertIn(20, [span['frame'] for span in plans['slice'][2]['spans']])
        self.assertFalse(results[2]['ok'], results[2])
        self.assertRegex(results[2]['message'], 'does not fit loop trim')
        self.assertFalse(results[2]['unsupported'])
        with self.assertRaisesRegex(c.StateError, 'does not fit loop trim'):
            compile_plan(too_long)

    def test_unsupported_constructs_in_a_play_state_are_still_refused(self):
        state = play_state(3, 20)['state']
        last = state['frames'] - 1
        with_hold = dict(copy.deepcopy(state), events=[*state['events'],
                                                       dict(op='hold', frame=last, loop='loop-1', value=True)])
        with_move = dict(copy.deepcopy(state), events=[*state['events'], dict(
            op='move', frame=last, loop='loop-1', orientation='portrait',
            rect=state['layouts']['portrait']['cells'][0]['rect'])])
        with_cue = dict(copy.deepcopy(state), events=[*state['events'], dict(op='cue', frame=last, loop='loop-1')])
        with_seam = dict(copy.deepcopy(state), seam={'enabled': True})
        results = node(*(['compilePlan', s] for s in (with_hold, with_move, with_cue, with_seam)))
        for name, mutant, result, pattern, python_compiles in (
                ('hold', with_hold, results[0], 'hold and move events are resolved by composition.py only', True),
                ('move', with_move, results[1], 'hold and move events are resolved by composition.py only', True),
                ('cue', with_cue, results[2], 'unsupported event: cue', False),
                ('seam', with_seam, results[3], 'seams are compiled by Python only', True)):
            with self.subTest(construct=name):
                self.assertFalse(result['ok'], f'{name} compiled')
                self.assertEqual(result['name'], 'CompilerError')
                self.assertRegex(result['message'], pattern)
                self.assertEqual(result['unsupported'], python_compiles, result['message'])
                if python_compiles:
                    self.assertRegex(result['message'], '^outside the browser compiler subset: ')
                    compile_plan(mutant)
                else:
                    with self.assertRaisesRegex(c.StateError, pattern):
                        compile_plan(mutant)

    def test_a_ten_minute_seven_loop_play_state_compiles_in_one_pass(self):
        out = play_state(7, 600, seed=1, pool=120)
        state = out['state']
        self.assertEqual(state['frames'], 14400)
        self.assertGreater(len(state['events']), 25000)
        completed = subprocess.run([node_executable(), '-e', TIMED_DRIVER, str(COMPILER)], input=json.dumps(state),
                                   capture_output=True, text=True, check=True, timeout=300)
        result = json.loads(completed.stdout)
        self.assertLess(result['seconds'], LARGE_STATE_SECONDS,
                        f"{len(state['events'])} events took {result['seconds']:.2f} s")
        tracks = {track['id']: track['spans'] for track in result['plan']['tracks']}
        # Python's compile_plan replays every event at every frame, too slow here, so check against two
        # independent references: the schedule's own timeline and composition.resolve_at at every event frame.
        timeline = out['schedule'].timeline()
        starts = [frame for frame, _ in timeline]
        for ident, spans in tracks.items():
            for index, span in enumerate(spans):
                end = spans[index + 1]['frame'] if index + 1 < len(spans) else state['frames']
                for frame in (span['frame'], (span['frame'] + end - 1) // 2, end - 1):
                    snapshot = timeline[bisect.bisect_right(starts, frame) - 1][1]
                    self.assertEqual(span['source'], snapshot[ident], (ident, frame))
        for frame in sorted({0, state['frames'] - 1, *(event['frame'] for event in state['events'])}):
            for loop in c.resolve_at(state, frame)['loops']:
                self.assertEqual(source_at(tracks[loop['id']], frame), loop['source'], (loop['id'], frame))
        self.assertEqual(result['plan']['state_sha256'], hashlib.sha256(c.canonical_json(state).encode()).hexdigest())


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
                }''', dict(count=count, pair=authored_layouts(count), fixtures=fixtures))
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
