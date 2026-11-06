"""Full-bleed raster in the browser runtime: bleed, crop-then-cover, corners, jitter.

Spec: docs/plans/2026-11-05-full-bleed-layout-presets.md (lane B). The Node tier
checks the runtime's adjacency helper against Python ``adjacency`` on the whole
conformance corpus (seam test 5, runtime half), the plan validator and the raster
decisions of ``rasterLayout`` (corner backing, coverage guard, bleed clamp) and
``overscanFor`` (jitter axis). The browser
tier runs the real runtime in headless Chrome on synthetic ``ffmpeg lavfi`` clips:
the hairline matrix for N=5 and N=12 (seam test 6; the full N=1, 5, 8, 12 matrix is
``python -m tools.verification.verify_strips_hairlines``), aspect-preserving slices,
bleed and corner geometry, jitter overscan and full_bleed refusals.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import simvltanea.authoring.composition as c
from simvltanea.authoring import adjacency, build_artifact001, build_strips, strips_layouts
from simvltanea.authoring.layout_presets import DEFAULT_STRIPS_PRESET
from simvltanea.browser.browser_runtime import HERE, compile_plan
from simvltanea.browser.test_browser_runtime import browser_executable
from tools.verification import verify_strips_hairlines as hairlines

REPO = Path(__file__).resolve().parents[3]
CORPUS = REPO / 'fixtures' / 'layouts'
RUNTIME_JS = HERE / 'browser.runtime.js'
# Load the whole runtime in a Node VM, as the existing Node-tier runtime tests do.
NODE_PRELUDE = r'''
const vm = require('node:vm'), fs = require('node:fs');
const stage = {dataset:{}, style:{setProperty(){}, removeProperty(){}}, addEventListener(){}};
const context = vm.createContext({
  window:{}, document:{querySelector(){return stage;}, addEventListener(){}},
  performance:{now(){return 1000;}},
  ResizeObserver:class {observe(){}}, fetch(){return new Promise(()=>{});},
  setTimeout, clearTimeout, URL, Blob, console,
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const runtime = context.window.compositionRuntime;
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
'''


def run_node(body: str, payload) -> object:
    result = subprocess.run(['node', '-e', NODE_PRELUDE + body, str(RUNTIME_JS)], input=json.dumps(payload),
                            check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def corpus_layouts() -> list[tuple[str, list]]:
    """Every layout of every valid corpus file; presets are expanded at every count."""
    manifest = json.loads((CORPUS / 'corpus.json').read_text())
    layouts = []
    for relative in manifest['valid']:
        path = CORPUS / relative
        data = json.loads(path.read_text())
        if data['format'] == 'simvltanea.layout-pair/1':
            pairs = {data['count']: data}
        else:
            counts = data.get('counts', {'min': 1, 'max': 12})
            pairs = {n: strips_layouts(n, path) for n in range(counts.get('min', 1), counts.get('max', 12) + 1)}
        for count, pair in pairs.items():
            for orientation in ('portrait', 'landscape'):
                layouts.append((f'{relative} N={count} {orientation}', pair[orientation]['cells']))
    return layouts


def fake_sources(count: int) -> list[dict]:
    """Plan-shaped sources for Node validation; no bytes are read there."""
    sources = []
    for k in range(count):
        digest = hashlib.sha256(f'raster plan source {k}'.encode()).hexdigest()
        sources.append(dict(id=f'source-{k + 1}', path=f'media/{digest}.mp4', sha256=digest, kind='video',
                            duration='4'))
    return sources


def node_plan(count: int, radius='0', jitter='0', frames=24) -> dict:
    state = build_strips(count, hairlines.strips_preset(radius, jitter), sources=fake_sources(count), frames=frames)
    plan = compile_plan(state)
    for source in plan['sources']:
        source['bytes'] = 1000
    return plan


class AdjacencyParityTests(unittest.TestCase):
    def test_runtime_adjacency_matches_python_on_every_valid_corpus_layout(self):
        layouts = corpus_layouts()
        expected = [c.canonical_json(adjacency(cells)) for _, cells in layouts]
        actual = run_node(r'''
const canonical = value => Array.isArray(value) ? `[${value.map(canonical).join(',')}]` :
  value && typeof value === 'object' ?
    `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}` :
    JSON.stringify(value);
console.log(JSON.stringify(input.map(cells => canonical(runtime.adjacency(cells)))));
''', [cells for _, cells in layouts])
        self.assertEqual(len(actual), len(expected))
        for (label, _), python, javascript in zip(layouts, expected, actual):
            with self.subTest(layout=label):
                self.assertEqual(javascript, python)
        # The corpus exercises every case: no edge (N=1), rows, columns, a grid, unequal weights.
        self.assertGreater(len(layouts), 40)
        self.assertIn('[]', expected)
        for edge in ('bottom', 'right', 'top'):
            self.assertTrue(any(f'"edge":"{edge}"' in item for item in expected), edge)
        self.assertTrue(any('"span":["1/2","1"]' in item for item in expected))

    def test_runtime_adjacency_is_exact_below_float_resolution(self):
        # Denominators near 10^9: a shared span shorter than 1e-12, and a gap of about 1e-18 that is no edge.
        tiny_span = [['0', '0', '999999999/1000000000', '1/2'], ['999999998/999999999', '1/2', '1/999999999', '1/2']]
        gap = [['0', '0', '1', '999999998/999999999'], ['0', '999999999/1000000000', '1', '1/1000000000']]
        layouts = [[dict(rect=rect) for rect in rects] for rects in (tiny_span, gap)]
        expected = [c.canonical_json(adjacency(cells)) for cells in layouts]
        self.assertNotEqual(expected[0], '[]')
        self.assertEqual(expected[1], '[]')
        actual = run_node(r'''
const canonical = value => Array.isArray(value) ? `[${value.map(canonical).join(',')}]` :
  value && typeof value === 'object' ?
    `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}` :
    JSON.stringify(value);
console.log(JSON.stringify(input.map(cells => canonical(runtime.adjacency(cells)))));
''', layouts)
        self.assertEqual(actual, expected)

    def test_spec_example_for_three_portrait_strips(self):
        cells = strips_layouts(3)['portrait']['cells']
        self.assertEqual(run_node('console.log(JSON.stringify(runtime.adjacency(input)));', cells),
                         [{"a": 0, "b": 1, "edge": "bottom", "span": ["0", "1"]},
                          {"a": 1, "b": 2, "edge": "bottom", "span": ["0", "1"]}])


def hand_layout(rects, overlap=2, radius='0', jitter='0') -> dict:
    """A layout with ``presentation`` over hand-written rects (draw order = list order)."""
    return dict(name='hand', presentation=dict(overlap_px=overlap, corner_radius=radius, lateral_jitter=jitter),
                cells=[dict(loop=f'loop-{k + 1}', rect=list(rect), fit='cover', focal=['1/2', '1/2'])
                       for k, rect in enumerate(rects)])


GROW = r'''
console.log(JSON.stringify(input.map(({layout, width, height, ratio}) =>
  runtime.rasterLayout(layout, width, height, ratio).cells.map(cell => cell.grow))));
'''


class CornerBackingTests(unittest.TestCase):
    """A rounded corner must always have the earlier strip beneath its whole cutout (always-fill)."""

    BACKING = r'''
console.log(JSON.stringify(input.map(({layout, width, height, ratio, configured}) => {
  const raster = runtime.rasterLayout(layout, width, height, ratio);
  const edges = runtime.adjacency(layout.cells).map(({a, b, edge}) => ({a, b, edge,
    backing: raster.cells[a].grow[edge] * ratio, radius: raster.cells[b].radius,
    rounded: [...raster.cells[b].rounded]}));
  return {configured, overlap: layout.presentation.overlap_px, ratio, edges};
})));
'''

    @staticmethod
    def case(count, orientation, width, height, ratio, weights=None):
        preset = copy.deepcopy(DEFAULT_STRIPS_PRESET)
        preset['style'] = {'corner_radius': '1/20', 'lateral_jitter': '0'}
        if weights:
            preset['weights'] = {'default': 'equal', 'by_count': {str(count): weights}}
        layout = strips_layouts(count, preset)[orientation]
        return dict(layout=layout, width=width, height=height, ratio=ratio,
                    configured=float(Fraction(1, 20) * min(width, height)))

    def assert_backed(self, out):
        for index, result in enumerate(out):
            for edge in result['edges']:
                with self.subTest(case=index, edge=(edge['a'], edge['b'])):
                    # The earlier cell extends under the later one by at least overlap + the rounded radius.
                    self.assertGreaterEqual(edge['backing'] + 1e-6, result['overlap'] + edge['radius'] * result['ratio'])
                    self.assertLessEqual(edge['radius'], result['configured'] + 1e-9)
                    self.assertGreater(edge['radius'], 0)
                    self.assertTrue(edge['rounded'])

    def test_backing_covers_every_rounded_corner_and_thin_strips_get_a_smaller_radius(self):
        cases = [self.case(2, 'portrait', 900, 1000, 1, ['99', '1']),    # a 10 px strip
                 self.case(12, 'landscape', 360, 360, 1),                # 30 px strips, radius 18 px
                 self.case(12, 'landscape', 360, 360, 2),
                 self.case(5, 'portrait', 375, 812, 3)]                  # roomy strips: radius unchanged
        out = run_node(self.BACKING, cases)
        self.assert_backed(out)
        reduced = [edge['radius'] for edge in out[0]['edges']] + [edge['radius'] for edge in out[1]['edges']]
        self.assertTrue(all(radius < out[1]['configured'] for radius in reduced), reduced)
        self.assertAlmostEqual(out[0]['edges'][0]['radius'], 3.0)         # (10 / 2 - 2) px
        self.assertAlmostEqual(out[1]['edges'][0]['radius'], 13.0)        # (30 / 2 - 2) px
        self.assertTrue(all(abs(edge['radius'] - out[3]['configured']) < 1e-9 for edge in out[3]['edges']))

    def test_a_thin_sibling_on_the_same_side_reduces_the_radius_of_the_wide_neighbour(self):
        # Cell 0's bottom is shared with a 500 px cell and a 50 px cell: its bleed is capped at 25 px,
        # so the wide cell's corners can only be backed behind 25 - 2 = 23 px, not the configured 50 px.
        layout = hand_layout([['0', '0', '1', '1/2'], ['0', '1/2', '1/2', '1/2'], ['1/2', '1/2', '1/2', '1/20'],
                              ['1/2', '11/20', '1/2', '9/20']], overlap=2, radius='1/20')
        out = run_node(self.BACKING, [dict(layout=layout, width=1000, height=1000, ratio=1, configured=50.0)])
        self.assert_backed(out)
        for edge in out[0]['edges']:
            if edge['a'] == 0:
                self.assertAlmostEqual(edge['radius'], 23)


    def test_a_dropped_bleed_leaves_no_rounded_corner_without_backing(self):
        # A 2x2 grid drawn BR, TL, TR, BL: the corner-square check drops one side's bleed, and the cell next
        # to it must then lose the rounding that bleed was meant to back (or its cutout would show the canvas).
        layout = hand_layout([['1/2', '1/2', '1/2', '1/2'], ['0', '0', '1/2', '1/2'], ['1/2', '0', '1/2', '1/2'],
                              ['0', '1/2', '1/2', '1/2']], overlap=2, radius='1/20')
        out = run_node(self.BACKING, [dict(layout=layout, width=1000, height=1000, ratio=1, configured=50.0),
                                      dict(layout=layout, width=1000, height=1000, ratio=2, configured=50.0)])
        for index, result in enumerate(out):
            for edge in result['edges']:
                with self.subTest(case=index, edge=(edge['a'], edge['b'])):
                    backed = max(0.0, edge['backing'] - result['overlap'])
                    self.assertLessEqual(edge['radius'] * result['ratio'], backed + 1e-6)
                    if edge['radius'] == 0:
                        self.assertEqual(edge['rounded'], [])
        # The guard really bites in this layout: some cell loses its rounding because its backing was dropped.
        self.assertTrue(any(edge['radius'] == 0 for result in out for edge in result['edges']), out)


class CoverageGuardTests(unittest.TestCase):
    """A side grows only where later cells hide the whole bleed, as in render_triptych.presentation_placements."""

    def test_side_grows_only_when_later_cells_cover_the_whole_strip(self):
        partial = hand_layout([['0', '0', '1/2', '1/2'], ['0', '1/2', '1/4', '1/2']])   # bottom half exposed
        full = hand_layout([['0', '0', '1/2', '1/2'], ['0', '1/2', '1/2', '1/2']])
        out = run_node(GROW, [dict(layout=layout, width=1000, height=1000, ratio=ratio)
                              for layout in (partial, full) for ratio in (1, 2)])
        self.assertEqual([grows[0]['bottom'] for grows in out], [0, 0, 2, 1])
        self.assertTrue(all(grows[1] == {'top': 0, 'right': 0, 'bottom': 0, 'left': 0} for grows in out))

    def test_an_uncovered_grown_corner_square_drops_the_horizontal_side(self):
        # No fourth cell: cell 0's right and bottom strips are covered, the square between them is not.
        layout = hand_layout([['0', '0', '1/2', '1/2'], ['1/2', '0', '1/2', '1/2'], ['0', '1/2', '1/2', '1/2']])
        out = run_node(GROW, [dict(layout=layout, width=1000, height=1000, ratio=1)])
        self.assertEqual(out[0][0], {'top': 0, 'right': 0, 'bottom': 2, 'left': 0})
        self.assertEqual(out[0][1], {'top': 0, 'right': 0, 'bottom': 0, 'left': 0})

    def test_grid_fixture_keeps_its_bleed_where_fully_covered(self):
        portrait = json.loads((CORPUS / 'valid' / 'grid-4-bleed-pair.json').read_text())['portrait']
        out = run_node(GROW, [dict(layout=portrait, width=375, height=812, ratio=2)])[0]
        # Radius 1/20 * 375 = 18.75 CSS px = 37.5 device px; bleed 8 + ceil(37.5) = 46 device px = 23 CSS px.
        # Cell 1's left and cell 2's top touch earlier cells, so they never grow.
        none = {'top': 0, 'right': 0, 'bottom': 0, 'left': 0}
        self.assertEqual(out, [dict(none, right=23, bottom=23), dict(none, bottom=23), dict(none, right=23), none])


class BleedClampTests(unittest.TestCase):
    """The bleed is at most half of the thinnest later neighbour's device-pixel extent."""

    def test_bleed_is_clamped_to_half_the_neighbour_and_to_the_thinnest_of_several(self):
        thin = hand_layout([['0', '0', '1', '99/100'], ['0', '99/100', '1', '1/100']], overlap=8)   # a 10 px strip
        siblings = hand_layout([['0', '0', '1', '1/2'], ['0', '1/2', '1/2', '1/2'], ['1/2', '1/2', '1/2', '1/100'],
                                ['1/2', '51/100', '1/2', '49/100']], overlap=8)
        out = run_node(GROW, [dict(layout=thin, width=1000, height=1000, ratio=1),       # cap 5 device px
                              dict(layout=thin, width=1000, height=1000, ratio=2),       # cap 10: overlap 8 fits
                              dict(layout=siblings, width=1000, height=1000, ratio=1)])  # min(250, 5) = 5
        self.assertEqual(out[0][0]['bottom'], 5)
        self.assertEqual(out[1][0]['bottom'], 4)
        self.assertEqual(out[2][0]['bottom'], 5)
        self.assertEqual(out[2][1]['right'], 8)


class JitterAxisTests(unittest.TestCase):
    """overscanFor picks the jitter axis by render_triptych._jitter_axis's rule."""

    def test_axis_follows_the_export_rule(self):
        layout = hand_layout([['0', '0', '1', '1']], overlap=0, jitter='1/20')
        cases = [(['0', '0', '1/2', '1/2'], 'portrait', 375, 812),     # 2x2 grid cell, taller: y
                 (['0', '0', '1/2', '1/2'], 'landscape', 1280, 720),   # wider: x
                 (['0', '0', '1/2', '1/2'], 'landscape', 500, 500),    # square: x
                 (['0', '0', '1', '1/5'], 'landscape', 1280, 720),     # full-width row: x
                 (['0', '0', '1/5', '1'], 'portrait', 375, 812),       # full-height column: y
                 (['0', '0', '1', '1'], 'portrait', 375, 812),         # one strip: orientation
                 (['0', '0', '1', '1'], 'landscape', 1280, 720)]
        out = run_node(r'''
console.log(JSON.stringify(input.cases.map(([rect, orientation, width, height]) =>
  runtime.overscanFor({rect, lateral_offset:'0'}, input.layout, orientation, width, height).axis)));
''', dict(layout=layout, cases=cases))
        self.assertEqual(out, ['y', 'x', 'x', 'x', 'y', 'x', 'y'])


class PlanValidationTests(unittest.TestCase):
    """validatePlan accepts the optional fields within the spec's bounds and nothing else."""

    VALIDATE = r'''
console.log(JSON.stringify(input.map(plan => {
  try { runtime.validatePlan(plan); return null; } catch (error) { return String(error.message); }
})));
'''

    def outcomes(self, plans):
        return run_node(self.VALIDATE, plans)

    def test_strips_and_legacy_plans_are_accepted(self):
        legacy_state = c.from_authoring_model(build_artifact001(5), {
            f'fixtures/loop-{k + 1}.mp4': source for k, source in enumerate(fake_sources(5))})
        legacy_state['frames'] = 24
        legacy = compile_plan(legacy_state)
        for source in legacy['sources']:
            source['bytes'] = 1000
        plans = [node_plan(1), node_plan(5), node_plan(12), node_plan(5, '1/20', '1/20'), node_plan(12, '1/20', '1/20'),
                 node_plan(1, '1/20', '1/20'), legacy]
        self.assertEqual(self.outcomes(plans), [None] * len(plans))

    def test_out_of_bounds_and_unknown_fields_are_refused(self):
        base = node_plan(5, '1/40', '1/40')
        portrait = lambda plan: plan['layout_keyframes'][0]['layouts']['portrait']
        cases = {
            'contain cell': (lambda p: portrait(p)['cells'][2].__setitem__('fit', 'contain'),
                             'portrait layout "strips-5-portrait": full_bleed requires fit cover on every cell; cell 2'),
            'gap of 1/10^9': (lambda p: portrait(p)['cells'][4]['rect'].__setitem__(3, '199999999/1000000000'),
                              'portrait layout "strips-5-portrait": full_bleed requires the rects to tile'),
            'overlap_px 9': (lambda p: portrait(p)['presentation'].__setitem__('overlap_px', 9), 'overlap_px'),
            'overlap_px negative': (lambda p: portrait(p)['presentation'].__setitem__('overlap_px', -1), 'overlap_px'),
            'overlap_px fraction': (lambda p: portrait(p)['presentation'].__setitem__('overlap_px', 1.5), 'overlap_px'),
            'overlap_px string': (lambda p: portrait(p)['presentation'].__setitem__('overlap_px', '2'), 'overlap_px'),
            'radius above 1/20': (lambda p: portrait(p)['presentation'].__setitem__('corner_radius', '1/19'),
                                  'corner_radius must be in 0..1/20'),
            'jitter above 1/20': (lambda p: portrait(p)['presentation'].__setitem__('lateral_jitter', '1/19'),
                                  'lateral_jitter must be in 0..1/20'),
            'offset beyond jitter': (lambda p: portrait(p)['cells'][1].__setitem__('lateral_offset', '1/39'),
                                     '|lateral_offset| must not exceed'),
            'offset missing': (lambda p: portrait(p)['cells'][3].pop('lateral_offset'),
                               'requires a resolved lateral_offset'),
            'offset without jitter': (lambda p: portrait(p)['presentation'].__setitem__('lateral_jitter', '0'),
                                      'lateral_offset requires presentation.lateral_jitter > 0'),
            'full_bleed not boolean': (lambda p: portrait(p).__setitem__('full_bleed', 'yes'), 'full_bleed must be boolean'),
            'unknown layout key': (lambda p: portrait(p).__setitem__('gutter', '0'), 'layout fields'),
            'unknown cell key': (lambda p: portrait(p)['cells'][0].__setitem__('z', 1), 'cell fields'),
            'unknown keyframe key': (lambda p: p['layout_keyframes'][0].__setitem__('bleed', 2), 'layout fields'),
            'unknown presentation key': (lambda p: portrait(p)['presentation'].__setitem__('order', 'forward'),
                                         'presentation needs exactly'),
            'missing presentation key': (lambda p: portrait(p)['presentation'].pop('corner_radius'),
                                         'presentation needs exactly'),
            'non-canonical rational': (lambda p: portrait(p)['presentation'].__setitem__('corner_radius', '0.025'),
                                       'canonical rational'),
            # In 0..1/20 exactly, but beyond composition.rational's 10^9 bounds and number()'s range.
            'radius of 800 digits': (lambda p: portrait(p)['presentation'].__setitem__(
                'corner_radius', f'{10**400}/{40 * 10**400 + 1}'), 'corner_radius: out of bounds'),
            'jitter of 800 digits': (lambda p: portrait(p)['presentation'].__setitem__(
                'lateral_jitter', f'{10**400}/{40 * 10**400 + 1}'), 'lateral_jitter: out of bounds'),
            'offset of 800 digits': (lambda p: portrait(p)['cells'][0].__setitem__(
                'lateral_offset', f'{10**400}/{80 * 10**400 + 1}'), 'lateral_offset: out of bounds'),
            'radius denominator above 10^9': (lambda p: portrait(p)['presentation'].__setitem__(
                'corner_radius', '1/1000000001'), 'corner_radius: out of bounds'),
            # Reduces to 1/40 (within bounds, as Python accepts), but the raw spelling is not finite as a float.
            'unreduced radius of 800 digits': (lambda p: portrait(p)['presentation'].__setitem__(
                'corner_radius', f'{10**400}/{40 * 10**400}'), 'corner_radius must be a canonical rational'),
            'unreduced jitter of 800 digits': (lambda p: portrait(p)['presentation'].__setitem__(
                'lateral_jitter', f'{10**400}/{40 * 10**400}'), 'lateral_jitter must be a canonical rational'),
            'unreduced offset of 800 digits': (lambda p: portrait(p)['cells'][0].__setitem__(
                'lateral_offset', f'{10**400}/{80 * 10**400}'), 'lateral_offset must be a canonical rational'),
            'interior overlap': (lambda p: portrait(p)['cells'][1]['rect'].__setitem__(1, '1/10'), 'overlapping cells'),
        }
        plans, expected = [], []
        for name, (modify, message) in cases.items():
            plan = copy.deepcopy(base)
            modify(plan)
            plans.append(plan)
            expected.append((name, message))
        for (name, message), outcome in zip(expected, self.outcomes(plans)):
            with self.subTest(case=name):
                self.assertIsNotNone(outcome)
                self.assertIn(message, outcome)

    def test_thirteen_cells_are_refused_even_without_the_builder(self):
        """build_strips stops at 12; validatePlan must hold the same ceiling on a hand-built plan."""
        plan = node_plan(12)
        source = copy.deepcopy(plan['sources'][-1]) | {'id': 'source-13', 'sha256': 'f' * 64,
                                                       'path': f"media/{'f' * 64}.mp4"}
        track = copy.deepcopy(plan['tracks'][-1]) | {'id': 'loop-13'}
        for span in track['spans']:
            span.update(id='loop-13', source='source-13')
        plan['sources'].append(source)
        plan['tracks'].append(track)
        for keyframe in plan['layout_keyframes']:
            for orientation, layout in keyframe['layouts'].items():
                layout['cells'].append(copy.deepcopy(layout['cells'][-1]) | {'loop': 'loop-13'})
                for k, cell in enumerate(layout['cells']):
                    start = str(Fraction(k, 13))
                    cell['rect'] = ['0', start, '1', '1/13'] if orientation == 'portrait' else [start, '0', '1/13', '1']
        accepted, refused = self.outcomes([node_plan(12), plan])
        self.assertIsNone(accepted)
        self.assertIsNotNone(refused)
        self.assertIn('full_bleed and presentation are supported for 1..12 cells, not 13', refused)

    def test_single_strip_bleed_and_corner_rules(self):
        one = node_plan(1)
        bleed, rounded = copy.deepcopy(one), copy.deepcopy(one)
        bleed['layout_keyframes'][0]['layouts']['landscape']['presentation']['overlap_px'] = 2
        rounded['layout_keyframes'][0]['layouts']['landscape']['presentation']['corner_radius'] = '1/40'
        # Corpus case pair-corner-rule: the wide bottom cell's top-right corner has no earlier cell beneath.
        bad_corner = node_plan(3)
        layout = bad_corner['layout_keyframes'][0]['layouts']['portrait']
        for cell, rect in zip(layout['cells'], (['0', '0', '1/2', '1/2'], ['0', '1/2', '1', '1/2'],
                                                ['1/2', '0', '1/2', '1/2'])):
            cell['rect'] = rect
        layout['presentation']['corner_radius'] = '1/40'
        # Drawing the wide cell last puts both earlier cells beneath its rounded corners.
        good_grid = copy.deepcopy(bad_corner)
        cells = good_grid['layout_keyframes'][0]['layouts']['portrait']['cells']
        cells[:] = [cells[0], cells[2], cells[1]]
        outcomes = self.outcomes([bleed, rounded, bad_corner, good_grid])
        self.assertIn('this layout has no shared edge', outcomes[0])
        self.assertIn('corner_radius > 0 requires cells that share an edge', outcomes[1])
        self.assertIn('has no earlier-drawn neighbour beneath it', outcomes[2])
        self.assertIsNone(outcomes[3])

    def test_rounded_corner_needs_earlier_spans_along_the_whole_radius(self):
        # rasterLayout backs a corner by the earlier cells' bleed depth only; a 1/100 corner cell next to a later
        # 1/50 cell left 95 px of the wide cell's 50 px cutout over the background at 1000x1000 (CodeRabbit #57).
        def plan(edge):
            result = node_plan(5, '1/20')
            rects = [['0', '0', edge, '1/2'], [str(1 - Fraction(edge)), '0', edge, '1/2'], ['0', '1/2', '1', '1/2'],
                     [edge, '0', '1/50', '1/2'], [str(Fraction(edge) + Fraction(1, 50)), '0',
                                                  str(1 - 2 * Fraction(edge) - Fraction(1, 50)), '1/2']]
            for cell, rect in zip(result['layout_keyframes'][0]['layouts']['portrait']['cells'], rects):
                cell['rect'] = rect
            return result
        narrow, exact_radius = self.outcomes([plan('1/100'), plan('1/20')])
        self.assertIsNotNone(narrow)
        self.assertIn('cell 2: rounded top corner at 0 has earlier-drawn neighbours beneath only 1/100 from it, '
                      'less than corner_radius 1/20', narrow)
        self.assertIsNone(exact_radius)

    def test_full_bleed_needs_exact_bounds_and_disjoint_interiors(self):
        # Each slack is below the float check's 1e-12, the area is exactly 1 and every denominator is within 10^9.
        def plan(first, second):
            result = node_plan(2)
            cells = result['layout_keyframes'][0]['layouts']['landscape']['cells']
            cells[0]['rect'], cells[1]['rect'] = first, second
            return result
        overlap = plan(['0', '0', '500001/1000001', '1'], ['500002/1000003', '0', '500000/1000001', '1'])
        overflow = plan(['0', '0', '500002/1000003', '1'], ['500001/1000001', '0', '500001/1000003', '1'])
        flush = plan(['0', '0', '500001/1000001', '1'], ['500001/1000001', '0', '500000/1000001', '1'])
        overlapped, overflowed, accepted = self.outcomes([overlap, overflow, flush])
        self.assertIsNotNone(overlapped)
        self.assertIn('landscape layout "strips-2-landscape": full_bleed cells 0 and 1 overlap', overlapped)
        self.assertIsNotNone(overflowed)
        self.assertIn('landscape layout "strips-2-landscape": full_bleed cell 1 extends past the unit square',
                      overflowed)
        self.assertIsNone(accepted)


class HairlineBrowserPinTests(unittest.TestCase):
    """The matrix's PORTVS_BROWSER_EXECUTABLE pin is used or refused, never replaced by another browser."""

    def test_an_invalid_pin_is_refused(self):
        for value in ('chrome', '/nonexistent/portvs-chrome'):
            with self.subTest(value=value), mock.patch.dict(os.environ, {'PORTVS_BROWSER_EXECUTABLE': value}):
                with self.assertRaises(RuntimeError) as caught:
                    hairlines.browser_executable()
                self.assertIn(value, str(caught.exception))

    def test_a_valid_pin_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'chrome'
            executable.write_text('#!/bin/sh\n')
            executable.chmod(0o700)
            with mock.patch.dict(os.environ, {'PORTVS_BROWSER_EXECUTABLE': str(executable)}):
                self.assertEqual(hairlines.browser_executable(), str(executable))


class RasterProbeCleanupTests(unittest.TestCase):
    """A probe that fails to start or to load a plan releases what it has opened."""

    def test_a_failed_launch_releases_the_server_and_playwright(self):
        from playwright.sync_api import sync_playwright
        before = set(threading.enumerate())
        probe = hairlines.RasterProbe(executable='/bin/echo')   # exists, but is no browser
        with self.assertRaises(Exception):
            probe.__enter__()
        self.assertEqual([thread.name for thread in set(threading.enumerate()) - before
                          if 'serve_forever' in thread.name], [])
        with sync_playwright():   # refused inside a leaked Playwright asyncio loop
            pass

    def test_open_closes_its_context_when_loading_fails(self):
        for step in ('goto', 'wait_for_function'):
            with self.subTest(step=step):
                probe = hairlines.RasterProbe.__new__(hairlines.RasterProbe)
                probe.browser, probe.base, probe.runtime_js = mock.MagicMock(), 'http://127.0.0.1:1', ''
                context = probe.browser.new_context.return_value
                getattr(context.new_page.return_value, step).side_effect = TimeoutError(step)
                with self.assertRaises(TimeoutError):
                    probe.open({}, 375, 812, 1)
                context.close.assert_called_once_with()

    def test_open_hands_its_context_to_the_caller_on_success(self):
        probe = hairlines.RasterProbe.__new__(hairlines.RasterProbe)
        probe.browser, probe.base, probe.runtime_js = mock.MagicMock(), 'http://127.0.0.1:1', ''
        context = probe.browser.new_context.return_value
        context.new_page.return_value.evaluate.return_value = None
        self.assertIs(probe.open({}, 375, 812, 1)[0], context)
        context.close.assert_not_called()


class RasterBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = hairlines.prepare_clips()
        cls.probe = hairlines.RasterProbe(executable=browser_executable()).__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.probe.__exit__(None, None, None)

    def open(self, plan, width, height, ratio, start=True):
        context, page, errors = self.probe.open(plan, width, height, ratio, start=start)
        self.addCleanup(context.close)
        self.addCleanup(lambda: self.assertEqual(errors, []))
        return page

    def boxes(self, page):
        return page.evaluate("""() => [...compositionRuntime.nodes.values()].map(n => {
          const box = n.box.getBoundingClientRect(), media = n.media.getBoundingClientRect(), s = getComputedStyle(n.box);
          return {id:n.id, box:box.toJSON(), media:media.toJSON(), vw:n.media.videoWidth, vh:n.media.videoHeight,
            fit:getComputedStyle(n.media).objectFit, clip:n.media.style.clipPath,
            slice:(n.span.slice_rect || []).map(v => { const [p, q = 1] = String(v).split('/').map(Number); return p / q; }),
            radii:[s.borderTopLeftRadius, s.borderTopRightRadius, s.borderBottomRightRadius, s.borderBottomLeftRadius]};
        })""")

    def test_hairline_matrix_n5_and_n12_has_zero_background_pixels(self):
        rows = []
        for count in hairlines.DEFAULT_COUNTS:
            for style in hairlines.STYLES:
                plan = hairlines.strips_plan(count, self.sources, style=style)
                for ratio, sizes in hairlines.VIEWPORTS:
                    rows.extend(self.probe.measure(plan, ratio, sizes, label=f'strips N={count} {style}'))
        (hairlines.ROOT / 'hairline-default.json').write_text(json.dumps(rows, indent=2) + '\n')
        self.assertEqual(len(rows), len(hairlines.DEFAULT_COUNTS) * len(hairlines.STYLES) * 19)
        near_square = {'360x360', '744x768', '800x800'}
        self.assertEqual({row['viewport'] for row in rows} & near_square, near_square)
        # 800x800 at 2x is the canvas where the unreduced corner radius showed 44 background pixels at N=12.
        self.assertTrue(any(row['viewport'] == '800x800' and row['ratio'] == 2 and row['case'] == 'strips N=12 max'
                            for row in rows))
        self.assertEqual([hairlines.format_row(row) for row in hairlines.failures(rows)], [])
        self.assertEqual(sum(row['background'] for row in rows), 0)
        self.assertEqual({row['orientation'] for row in rows}, {'portrait', 'landscape'})
        self.assertTrue(all(row['running'] for row in rows))
        self.assertEqual(sum(row['stalled'] for row in rows), 0)

    def test_probe_sees_hairlines_when_the_bleed_is_removed(self):
        """Negative control: without overlap_px the spec's measured hairlines come back."""
        rows = hairlines.run_controls(self.probe, self.sources)
        self.assertEqual(len(rows), 3)
        for row in rows:
            with self.subTest(case=row['case'], viewport=row['viewport'], ratio=row['ratio']):
                self.assertGreater(row['background'], 0)

    def test_a_frozen_unpaused_loop_counts_as_stalled(self):
        """Negative control for the playback gate: a loop that stops presenting frames is a stall unpaused too."""
        load = self.probe.open

        def frozen(*args, **kwargs):
            context, page, errors = load(*args, **kwargs)
            page.evaluate('[...compositionRuntime.nodes.values()][2].media.playbackRate = 0')
            page.wait_for_timeout(200)   # let a frame already queued be presented first
            return context, page, errors

        with mock.patch.object(self.probe, 'open', frozen):
            rows = self.probe.measure(hairlines.strips_plan(5, self.sources), 1, ((375, 812), (1280, 720)),
                                      label='strips N=5 frozen loop-3')
        self.assertEqual([row['stalled'] for row in rows], [1, 1])
        self.assertEqual(len(hairlines.failures(rows)), 2)

    def test_a_loop_that_presents_a_frame_within_the_wait_is_not_stalled(self):
        """Measuring between two video frames must not read as a stall: a frame that arrives a little later counts."""
        load = self.probe.open

        def late_frames(*args, **kwargs):
            context, page, errors = load(*args, **kwargs)
            # Loop 3 stops presenting on its own, then a frame is "presented" every 700 ms, later than a
            # measurement that does not wait would look, and well inside the wait window.
            page.evaluate("""() => { const n = [...compositionRuntime.nodes.values()][2];
              n.media.playbackRate = 0; setInterval(() => { n.callbacks += 1; }, 700); }""")
            page.wait_for_timeout(200)
            return context, page, errors

        with mock.patch.object(self.probe, 'open', late_frames):
            rows = self.probe.measure(hairlines.strips_plan(5, self.sources), 1, ((375, 812), (1280, 720)),
                                      label='strips N=5 late frames loop-3')
        self.assertEqual([row['stalled'] for row in rows], [0, 0])
        self.assertEqual(hairlines.failures(rows), [])

    def test_slice_is_crop_then_cover_without_stretch(self):
        count = 5
        state_slice = Fraction(build_strips(count, sources=self.sources[:count])['slice']['width'])
        page = self.open(hairlines.strips_plan(count, self.sources), 375, 812, 1)
        for width, height in ((375, 812), (1280, 720)):
            self.probe.settle(page, width, height)
            for item in self.boxes(page):
                with self.subTest(viewport=(width, height), loop=item['id']):
                    box, media = item['box'], item['media']
                    sx, sy, sw, sh = item['slice']
                    self.assertEqual((sw, sh), (float(state_slice), float(state_slice)))
                    # Element aspect is the source aspect (the old fill stretch was 3.08 here).
                    stretch = (media['width'] / media['height']) / (item['vw'] / item['vh'])
                    self.assertAlmostEqual(stretch, 1, delta=0.005)
                    # Magnification over plain cover is exactly 1/s.
                    cover = max(box['width'] / item['vw'], box['height'] / item['vh'])
                    self.assertAlmostEqual(media['width'] / item['vw'] / cover, 1 / float(state_slice), delta=0.01)
                    # The slice window covers the cell box, centred by the focal point.
                    left = media['x'] + sx * media['width']
                    top = media['y'] + sy * media['height']
                    right, bottom = left + sw * media['width'], top + sh * media['height']
                    self.assertLessEqual(left, box['x'] + 1e-3)
                    self.assertLessEqual(top, box['y'] + 1e-3)
                    self.assertGreaterEqual(right, box['right'] - 1e-3)
                    self.assertGreaterEqual(bottom, box['bottom'] - 1e-3)
                    self.assertAlmostEqual((left + right) / 2, (box['x'] + box['right']) / 2, delta=0.5)
                    self.assertAlmostEqual((top + bottom) / 2, (box['y'] + box['bottom']) / 2, delta=0.5)
                    self.assertEqual(item['clip'], '')

    def test_bleed_extends_under_the_later_neighbour_and_corners_round_only_on_shared_edges(self):
        count, ratio = 5, 2
        for style, radius_fraction in (('flat', 0), ('max', Fraction(1, 20))):
            page = self.open(hairlines.strips_plan(count, self.sources, style=style), 375, 812, ratio)
            for width, height, portrait in ((375, 812, True), (1280, 720, False)):
                self.probe.settle(page, width, height)
                radius = float(radius_fraction) * min(width, height)
                bleed = (2 + (math.ceil(radius * ratio - 1e-9) if radius_fraction else 0)) / ratio
                extent = height if portrait else width
                items = self.boxes(page)
                for k, item in enumerate(items):
                    with self.subTest(style=style, viewport=(width, height), strip=k):
                        box = item['box']
                        start, end = (box['y'], box['bottom']) if portrait else (box['x'], box['right'])
                        cross = (box['x'], box['right']) if portrait else (box['y'], box['bottom'])
                        self.assertEqual(cross, (0, width) if portrait else (0, height))
                        # The later cell keeps its exact nominal edge (Chrome stores 1/64 px).
                        self.assertAlmostEqual(start, extent * k / count, delta=1 / 64)
                        nominal_end = extent * (k + 1) / count
                        # start + size are each floored to 1/64 px, so the far edge is within 2/64.
                        self.assertAlmostEqual(end, nominal_end + (bleed if k < count - 1 else 0), delta=1 / 32)
                        rounded = f'{radius:g}px' if radius_fraction else '0px'
                        if k == 0 or not radius_fraction:
                            self.assertEqual(item['radii'], ['0px'] * 4)
                        elif portrait:  # top-left, top-right rounded; bottom square
                            self.assertEqual(item['radii'], [rounded, rounded, '0px', '0px'])
                        else:  # columns: left corners rounded
                            self.assertEqual(item['radii'], [rounded, '0px', '0px', rounded])

    def test_reverse_order_bleeds_from_the_start_edge_and_leaves_no_background(self):
        """order: reverse draws strip N-1 first, so each strip's bleed grows its top/left under strip k-1."""
        count, ratio = 5, 2
        for style, radius_fraction in (('flat', 0), ('max', Fraction(1, 20))):
            plan = hairlines.strips_plan(count, self.sources, style=style)
            for keyframe in plan['layout_keyframes']:
                for layout in keyframe['layouts'].values():
                    layout['cells'].reverse()   # what layout_presets._expand does for order: reverse
            page = self.open(plan, 375, 812, ratio)
            for width, height, portrait in ((375, 812, True), (1280, 720, False)):
                self.probe.settle(page, width, height)
                radius = float(radius_fraction) * min(width, height)
                bleed = (2 + (math.ceil(radius * ratio - 1e-9) if radius_fraction else 0)) / ratio
                extent = height if portrait else width
                for k, item in enumerate(self.boxes(page)):
                    with self.subTest(style=style, viewport=(width, height), strip=k):
                        box = item['box']
                        start, end = (box['y'], box['bottom']) if portrait else (box['x'], box['right'])
                        self.assertAlmostEqual(start, extent * k / count - (bleed if k > 0 else 0), delta=1 / 32)
                        self.assertAlmostEqual(end, extent * (k + 1) / count, delta=1 / 32)
                        rounded = f'{radius:g}px' if radius_fraction else '0px'
                        if k == count - 1 or not radius_fraction:
                            self.assertEqual(item['radii'], ['0px'] * 4)
                        elif portrait:  # the earlier strip is below: bottom corners rounded
                            self.assertEqual(item['radii'], ['0px', '0px', rounded, rounded])
                        else:  # the earlier strip is to the right: right corners rounded
                            self.assertEqual(item['radii'], ['0px', rounded, rounded, '0px'])
            rows = self.probe.measure(plan, ratio, ((375, 812), (1280, 720)), label=f'reverse N={count} {style}')
            self.assertEqual([hairlines.format_row(row) for row in hairlines.failures(rows)], [])
            self.assertEqual(sum(row['background'] for row in rows), 0)

    def test_lateral_jitter_overscans_the_media_inside_the_unchanged_cell(self):
        count, jitter = 5, 1 / 20
        plan = hairlines.strips_plan(count, self.sources, style='max', zoom=False)
        page = self.open(plan, 375, 812, 1)
        for width, height, orientation in ((375, 812, 'portrait'), (1280, 720, 'landscape')):
            self.probe.settle(page, width, height)
            cells = plan['layout_keyframes'][0]['layouts'][orientation]['cells']
            for cell, item in zip(cells, self.boxes(page)):
                with self.subTest(viewport=(width, height), loop=item['id']):
                    offset = float(Fraction(cell['lateral_offset']))
                    self.assertLessEqual(abs(offset), jitter)
                    box, media = item['box'], item['media']
                    along = 'x' if orientation == 'portrait' else 'y'
                    size = 'width' if along == 'x' else 'height'
                    extent = width if along == 'x' else height
                    guard = hairlines_cover_guard()
                    self.assertAlmostEqual(media[along] - box[along], (offset - jitter) * extent - guard, delta=1 / 32)
                    self.assertAlmostEqual(media[size], (1 + 2 * jitter) * extent + 2 * guard, delta=1 / 32)
                    # Across the strip the media is exactly the box plus the guard; it covers the box.
                    self.assertLessEqual(media['x'], box['x'])
                    self.assertLessEqual(media['y'], box['y'])
                    self.assertGreaterEqual(media['right'], box['right'])
                    self.assertGreaterEqual(media['bottom'], box['bottom'])
                    self.assertEqual(item['fit'], 'cover')

    def test_full_bleed_layout_with_contain_or_a_gap_is_refused_by_name(self):
        plan = hairlines.strips_plan(5, self.sources)
        contain, gap = copy.deepcopy(plan), copy.deepcopy(plan)
        for keyframe in contain['layout_keyframes']:
            keyframe['layouts']['landscape']['cells'][3]['fit'] = 'contain'
        for keyframe in gap['layout_keyframes']:
            keyframe['layouts']['portrait']['cells'][0]['rect'][3] = '199/1000'
        for case, message in ((contain, 'landscape layout "strips-5-landscape": full_bleed requires fit cover'),
                              (gap, 'portrait layout "strips-5-portrait": full_bleed requires the rects to tile')):
            with self.subTest(message=message):
                context = self.probe.browser.new_context()
                self.addCleanup(context.close)
                page = context.new_page()
                page.goto(f'{self.probe.base}/index.html')
                page.evaluate("""plan => { window.reads = 0; window.compositionIO = {
                  async plan() { return plan; }, async bytes() { window.reads++; return new Promise(() => {}); },
                  async digest() { throw Error('not reached'); } }; }""", case)
                page.add_script_tag(content=self.probe.runtime_js)
                page.wait_for_function('window.compositionRuntime?.error')
                result = page.evaluate("""() => ({error:compositionRuntime.error, reads,
                  mounted:document.querySelectorAll('#stage > .loop').length})""")
                self.assertIn(message, result['error'])
                self.assertEqual((result['reads'], result['mounted']), (0, 0))

    def test_layouts_without_the_new_keys_keep_exact_boxes_and_square_corners(self):
        sources = {f'fixtures/loop-{k + 1}.mp4': source for k, source in enumerate(self.sources[:5])}
        state = c.from_authoring_model(build_artifact001(5), sources)
        state['frames'] = 240
        plan = compile_plan(state)
        for source in plan['sources']:
            source['bytes'] = (hairlines.ROOT / source['path']).stat().st_size
        page = self.open(plan, 375, 812, 2)
        styles = page.evaluate("""() => [...compositionRuntime.nodes.values()].map(n => ({
          id:n.id, box:n.box.getBoundingClientRect().toJSON(), css:[n.box.style.left, n.box.style.top,
          n.box.style.width, n.box.style.height].join(' '), radius:n.box.style.borderTopLeftRadius,
          position:n.media.style.position, mediaWidth:n.media.style.width}))""")
        cells = {cell['loop']: cell for cell in plan['layout_keyframes'][0]['layouts']['portrait']['cells']}
        for item in styles:
            with self.subTest(loop=item['id']):
                x, y, w, h = (float(Fraction(v)) for v in cells[item['id']]['rect'])
                self.assertNotIn('calc', item['css'])
                for actual, expected in zip((item['box']['x'], item['box']['y'], item['box']['width'],
                                             item['box']['height']), (x * 375, y * 812, w * 375, h * 812)):
                    self.assertAlmostEqual(actual, expected, delta=1 / 64)
                self.assertEqual((item['radius'], item['position'], item['mediaWidth']), ('', '', '100%'))

def hairlines_cover_guard() -> float:
    """The runtime's COVER_GUARD constant, read from the source rather than duplicated."""
    text = RUNTIME_JS.read_text()
    value = text.split('const COVER_GUARD = ', 1)[1].split(';', 1)[0]
    numerator, denominator = value.split('/')
    return int(numerator) / int(denominator)


if __name__ == '__main__':
    unittest.main()
