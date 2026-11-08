"""The editor's spatial panels retain the canonical compositor geometry."""
from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest

from simvltanea.browser.layout_bundle import layout_bundle_v2

HERE = Path(__file__).resolve().parent
NODE = shutil.which('node')
ORIENTATIONS = ('portrait', 'landscape')
FRAMINGS = ('cover', 'contain', 'slice')
DRIVER = r'''
require(process.argv[1]);
const Model = require(process.argv[2]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const request = JSON.parse(input);
  const before = JSON.stringify(request);
  const cells = request.layouts.map(layout => Model.panelCells(layout, request.bundle));
  process.stdout.write(JSON.stringify({cells, unchanged: JSON.stringify(request) === before}));
});
'''


@unittest.skipUnless(NODE, 'Node.js is required for editor panel parity')
class EffectsLabPanelParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = layout_bundle_v2()

    def layouts(self, framings=FRAMINGS):
        return [
            dict(family=family, count=int(count), orientation=orientation, framing=framing)
            for family, data in self.bundle['families'].items()
            for count in sorted(data['counts'], key=int)
            for orientation in ORIENTATIONS
            for framing in framings
        ]

    def evaluate(self, layouts):
        result = subprocess.run(
            [NODE, '-e', DRIVER, str(HERE / 'browser.compiler.js'),
             str(HERE / 'browser.lab_model.js')],
            input=json.dumps(dict(bundle=self.bundle, layouts=layouts)),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value['unchanged'], 'Panel lookup changed the shared canonical bundle or layout request')
        self.assertEqual(len(value['cells']), len(layouts))
        return value['cells']

    def canonical(self, layout):
        return self.bundle['families'][layout['family']]['counts'][str(layout['count'])]

    def test_every_supported_panel_layout_matches_the_canonical_bundle(self):
        layouts = self.layouts()
        for layout, actual in zip(layouts, self.evaluate(layouts)):
            with self.subTest(**layout):
                entry = self.canonical(layout)
                expected = entry[layout['orientation']]['cells']
                numbers = {cell['loop']: index for index, cell in
                           enumerate(entry['portrait']['cells'], 1)}
                self.assertEqual(len(actual), layout['count'])
                self.assertEqual(len(actual), len(expected))
                for panel, cell in zip(actual, expected):
                    self.assertEqual(panel['number'], numbers[cell['loop']])
                    self.assertIs(type(panel['number']), int)
                    self.assertEqual(len(panel['rect']), 4)
                    for coordinate, rational in zip(panel['rect'], cell['rect']):
                        self.assertIsInstance(coordinate, (int, float))
                        self.assertNotIsInstance(coordinate, bool)
                        self.assertTrue(math.isfinite(coordinate))
                        self.assertAlmostEqual(coordinate, float(Fraction(rational)), places=12)

    def test_panel_identity_survives_family_count_orientation_and_framing_changes(self):
        layouts = self.layouts()
        reference = dict(family='strips', count=12, orientation='landscape', framing='cover')
        values = self.evaluate([reference, *layouts])
        reference_ids = {panel['number']: panel['id'] for panel in values[0]}
        self.assertEqual(set(reference_ids), set(range(1, 13)))
        self.assertEqual(len(set(reference_ids.values())), 12)
        for layout, panels in zip(layouts, values[1:]):
            with self.subTest(**layout):
                self.assertEqual({panel['number'] for panel in panels}, set(range(1, layout['count'] + 1)))
                for panel in panels:
                    self.assertEqual(panel['id'], reference_ids[panel['number']])

    def test_framing_retains_canonical_focal_points_and_strips_slice_sizes(self):
        layouts = self.layouts()
        for layout, actual in zip(layouts, self.evaluate(layouts)):
            with self.subTest(**layout):
                entry = self.canonical(layout)
                expected = entry[layout['orientation']]['cells']
                for panel, cell in zip(actual, expected):
                    focal = [Fraction(value) for value in cell['focal']]
                    self.assertEqual(len(panel['focal']), 2)
                    for coordinate, rational in zip(panel['focal'], focal):
                        self.assertAlmostEqual(coordinate, float(rational), places=12)
                    self.assertEqual(panel['fit'], 'contain' if layout['framing'] == 'contain' else 'cover')
                    if layout['family'] == 'strips' and layout['framing'] == 'slice':
                        width, height = [Fraction(entry['slice'][axis]) for axis in ('width', 'height')]
                        crop = [(1 - width) * focal[0], (1 - height) * focal[1], width, height]
                        self.assertEqual(len(panel['slice']), 4)
                        for coordinate, rational in zip(panel['slice'], crop):
                            self.assertAlmostEqual(coordinate, float(rational), places=12)
                    else:
                        self.assertIsNone(panel['slice'], 'Cover/contain and authored layouts must not inherit strips zoom')


if __name__ == '__main__':
    unittest.main()
