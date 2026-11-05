"""Strips fixtures: ramp clips with distinguishable rows and N=1, 5, 8, 12 states.

The generators keep their authored loops over N=2..7 unchanged and add full-bleed
strips states in both orientations. Media is synthetic and stays below ``var/``.
"""
from __future__ import annotations

import subprocess
import unittest
from fractions import Fraction

from simvltanea.authoring import composition as c
from simvltanea.authoring import build_artifact001, from_authoring_model, strips_slice
from simvltanea.generators import make_artifact_001, make_runtime_fixture as runtime
from simvltanea.paths import ARTIFACT_OUTPUT_DIR, PROOFS_DIR

COUNTS = (1, 5, 8, 12)


def check_strips_state(test: unittest.TestCase, state: dict, count: int) -> None:
    c.validate_state(state)
    test.assertEqual(len(state['loops']), count)
    test.assertEqual(state['slice'], strips_slice(count))
    for orientation, direction in (('portrait', 1), ('landscape', 0)):
        layout = state['layouts'][orientation]
        test.assertIs(layout['full_bleed'], True)
        test.assertEqual(len(layout['cells']), count)
        test.assertEqual([cell['loop'] for cell in layout['cells']], [f'loop-{k + 1}' for k in range(count)])
        # Strip k starts where strip k-1 ends: rows in portrait, columns in landscape.
        starts = [Fraction(cell['rect'][direction]) for cell in layout['cells']]
        test.assertEqual(starts, [Fraction(k, count) for k in range(count)])


class RampMediaTests(unittest.TestCase):
    def test_ramp_rows_columns_and_tints_are_distinguishable(self):
        width, height = runtime.RAMP_SIZE
        tints = [runtime.ramp_tint(k) for k in range(12)]
        self.assertEqual(len(set(tints)), 12)
        self.assertGreaterEqual(min(b - a for a, b in zip(tints, tints[1:])), 14)
        for k in (0, 11):
            pixels = runtime.ramp_frame(k).load()
            for y in (0, 1, 359, 718, 719):
                red, green, blue = pixels[17, y]
                self.assertEqual(red, runtime.ramp_level(y, height))
                self.assertEqual(blue, tints[k])
                self.assertLessEqual(abs(runtime.ramp_row(red) - y), height / (runtime.RAMP_SPAN - 1) / 2)
            for x in (0, 270, 539):
                self.assertLessEqual(abs(runtime.ramp_row(pixels[x, 400][1], width) - x),
                                     width / (runtime.RAMP_SPAN - 1) / 2)
            self.assertEqual(pixels[0, 0][:2], (runtime.RAMP_LOW, runtime.RAMP_LOW))
            self.assertEqual(pixels[width - 1, height - 1][:2], (runtime.RAMP_LOW + runtime.RAMP_SPAN - 1,) * 2)
            # No ramp pixel is near black, so near-black export pixels are exposed background.
            self.assertGreaterEqual(runtime.ramp_frame(k).getextrema()[2][0], 80)  # blue floor bounds every pixel

    def test_encoded_ramp_decodes_to_its_source_rows(self):
        sources = runtime.ramp_sources(PROOFS_DIR)
        self.assertEqual([s['id'] for s in sources], [f'strip-{k + 1}' for k in range(12)])
        width, height = runtime.RAMP_SIZE
        path = PROOFS_DIR / sources[4]['path']
        self.assertEqual(c.sha256_file(path), sources[4]['sha256'])
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v', '1', '-f', 'rawvideo',
                              '-pix_fmt', 'yuv444p', '-'], capture_output=True, check=True).stdout
        plane = width * height
        def rgb(x, y):
            i = y * width + x
            luma, cb, cr = 1.164 * (raw[i] - 16), raw[plane + i] - 128, raw[2 * plane + i] - 128
            return luma + 1.596 * cr, luma - 0.392 * cb - 0.813 * cr, luma + 2.017 * cb
        for y in range(4, height, 60):
            red = sum(rgb(x, y)[0] for x in range(8, width - 8)) / (width - 16)
            self.assertLess(abs(runtime.ramp_row(red) - y), 0.005 * height, y)
        self.assertLess(abs(rgb(width // 2, height // 2)[2] - runtime.ramp_tint(4)), 3)


class StripsFixtureTests(unittest.TestCase):
    def test_runtime_fixture_strips_states_and_previews(self):
        sources, commands = [], []
        paths = runtime.prepare_strips(PROOFS_DIR, sources, commands)
        self.assertEqual([p.name for p in paths],
                         [f'state-strips-{n}{suffix}.json' for n in COUNTS for suffix in ('', '-styled')])
        self.assertEqual(len(sources), 12)
        self.assertEqual(len(commands), 12)
        for path in paths:
            count = int(path.stem.split('-')[2])
            state = c.load_state(path)
            check_strips_state(self, state, count)
            self.assertEqual([loop['bank'] for loop in state['loops']], [[f'strip-{k + 1}'] for k in range(count)])
            preview = PROOFS_DIR / path.stem.replace('state-', 'preview-')
            self.assertTrue((preview / 'index.html').is_file())
            for layout in state['layouts'].values():
                presentation = layout['presentation']
                if path.stem.endswith('-styled'):
                    self.assertEqual(presentation['lateral_jitter'], '1/20')
                    self.assertEqual(presentation['corner_radius'], '1/20' if count > 1 else '0')
                    self.assertTrue(all('lateral_offset' in cell for cell in layout['cells']))
                else:
                    self.assertEqual(presentation, {'overlap_px': 2 if count > 1 else 0,
                                                    'corner_radius': '0', 'lateral_jitter': '0'})

    def test_artifact_family_adds_strips_and_keeps_authored_pairs(self):
        paths = make_artifact_001.prepare(ARTIFACT_OUTPUT_DIR)
        names = [p.name for p in paths]
        self.assertEqual(names[:7], [f'state-{n}.json' for n in range(2, 8)] + ['state-still-controls.json'])
        self.assertEqual(names[7:], [f'state-strips-{n}.json' for n in COUNTS])
        sources = {s['id']: s for s in c.load_state(ARTIFACT_OUTPUT_DIR / 'state-strips-12.json')['sources']}
        for count in range(2, 8):
            expected = from_authoring_model(build_artifact001(count),
                                            {f'fixtures/loop-{i + 1}.mp4': sources[f'media-{i + 1}'] for i in range(count)})
            self.assertEqual(c.load_state(ARTIFACT_OUTPUT_DIR / f'state-{count}.json'), expected)
        for count in COUNTS:
            check_strips_state(self, c.load_state(ARTIFACT_OUTPUT_DIR / f'state-strips-{count}.json'), count)


if __name__ == '__main__':
    unittest.main()
