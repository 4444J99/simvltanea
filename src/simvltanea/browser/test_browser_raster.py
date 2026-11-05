"""Full-bleed raster in the browser runtime: bleed, crop-then-cover, corners, jitter.

Spec: docs/plans/2026-11-05-full-bleed-layout-presets.md (lane B). The Node tier
checks the runtime's adjacency helper against Python ``adjacency`` on the whole
conformance corpus (seam test 5, runtime half) and the plan validator. The browser
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
import subprocess
import unittest
from fractions import Fraction
from pathlib import Path

import simvltanea.authoring.composition as c
from simvltanea.authoring import adjacency, build_artifact001, build_strips, strips_layouts
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

    def test_spec_example_for_three_portrait_strips(self):
        cells = strips_layouts(3)['portrait']['cells']
        self.assertEqual(run_node('console.log(JSON.stringify(runtime.adjacency(input)));', cells),
                         [{"a": 0, "b": 1, "edge": "bottom", "span": ["0", "1"]},
                          {"a": 1, "b": 2, "edge": "bottom", "span": ["0", "1"]}])


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
        self.assertEqual(len(rows), len(hairlines.DEFAULT_COUNTS) * len(hairlines.STYLES) * 13)
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
