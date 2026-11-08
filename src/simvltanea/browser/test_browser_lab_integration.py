"""The playable Effects Lab travels with the compositor's static staging."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simvltanea.browser.browser_studio import INDEX_HTML, STUDIO_FILES, stage_studio, studio_files
from tools.publishing.stage_library_site import check_studio


class EffectsLabIntegrationTests(unittest.TestCase):
    def test_lab_is_reachable_and_all_its_dependencies_are_staged(self):
        files = studio_files()
        self.assertIn('href="lab.html"', INDEX_HTML)
        required = {'lab.html', 'lab_model.js', 'lab_engine.js', 'lab_ui.js', 'lab_audio.js'}
        self.assertTrue(required <= set(files), 'The playable lab or its dependencies are missing')
        self.assertEqual(set(files), set(STUDIO_FILES))
        html = files['lab.html'].decode()
        for name in required - {'lab.html'}:
            self.assertIn(f'src="{name}"', html)

    def test_library_publisher_accepts_the_same_studio_file_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'studio'
            stage_studio(output)
            check_studio(output)
            self.assertTrue((output / 'lab.html').is_file(), 'Library publication must retain the lab')


if __name__ == '__main__':
    unittest.main()
