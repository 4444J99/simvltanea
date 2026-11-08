"""The playable Effects Lab travels with the compositor's static staging."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simvltanea.browser.browser_lab import LAB_FILES
from simvltanea.browser.browser_studio import INDEX_HTML, STUDIO_FILES, stage_studio, studio_files
from tools.publishing.stage_library_site import check_studio


class EffectsLabIntegrationTests(unittest.TestCase):
    def test_lab_is_reachable_and_all_its_dependencies_are_staged(self):
        files = studio_files()
        self.assertIn('href="./#compose"', INDEX_HTML)
        required = set(LAB_FILES)
        self.assertTrue({'lab_compiler.js', 'lab_layouts.js'} <= required)
        self.assertTrue(required <= set(files), 'The playable lab or its dependencies are missing')
        self.assertEqual(set(files), set(STUDIO_FILES))
        self.assertEqual(files['lab.html'], files['workspace.html'])
        html = files['workspace.html'].decode()
        self.assertIn('href="./#watch"', html)
        self.assertIn('aria-current="page"', html)
        for name in required - {'lab.html', 'workspace.html'}:
            self.assertIn(f'src="{name}"', html)
        self.assertLess(html.index('src="lab_compiler.js"'), html.index('src="lab_layouts.js"'))
        self.assertLess(html.index('src="lab_layouts.js"'), html.index('src="lab_model.js"'))
        self.assertLess(html.index('src="lab_model.js"'), html.index('src="lab_engine.js"'))

    def test_library_publisher_accepts_the_same_studio_file_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'studio'
            stage_studio(output)
            check_studio(output)
            self.assertTrue((output / 'lab.html').is_file(), 'Library publication must retain the lab')
            for name in LAB_FILES:
                self.assertEqual((output / name).read_bytes(), studio_files()[name])


if __name__ == '__main__':
    unittest.main()
