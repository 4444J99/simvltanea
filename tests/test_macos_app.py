"""The native Mac app writes the same library the Python stager accepts."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.publishing import stage_library_site as stager

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'tools' / 'mac-app'
MEDIA = ROOT / 'archive' / 'chatgpt' / 'media'


def swift_constants() -> dict[str, str]:
    text = (APP / 'sources' / 'kit' / 'manifest.swift').read_text(encoding='utf-8')
    return dict(re.findall(r'public static let (\w+) = ([^\n]+)', text))


class SwiftLimitsMatchThePythonStager(unittest.TestCase):
    def test_every_bound_is_the_same_number(self):
        found = swift_constants()
        self.assertEqual(found['schema'].strip('"'), stager.SCHEMA)
        self.assertEqual(int(found['maxClips']), stager.MAX_CLIPS)
        self.assertEqual(eval(found['maxClipBytes']), stager.MAX_CLIP_BYTES)
        self.assertEqual(int(found['maxSide']), stager.MAX_SIDE)
        self.assertEqual(float(found['minSeconds']), stager.MIN_SECONDS)
        self.assertEqual(float(found['maxSeconds']), float(stager.MAX_SECONDS))
        self.assertEqual(int(found['envelopeHz']), 10)

    def test_the_test_registry_lists_every_test(self):
        result = subprocess.run([sys.executable, str(APP / 'tests' / 'kit' / 'generate_main.py'), '--check'])
        self.assertEqual(result.returncode, 0, 'run tools/mac-app/tests/kit/generate_main.py to refresh main.swift')

    def test_the_app_bundle_asks_for_photos_access_with_a_reason(self):
        plist = (APP / 'app_info.plist').read_text(encoding='utf-8')
        self.assertIn('NSPhotoLibraryUsageDescription', plist)
        self.assertNotIn('NSAllowsArbitraryLoads', plist)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swift') and MEDIA.is_dir(),
                     'needs macOS with the Swift toolchain and the archived media')
class SwiftLibraryPassesPythonChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = subprocess.run(['swift', 'build', '--build-system', 'native', '--product', 'simv-library'],
                               cwd=APP, capture_output=True, text=True, timeout=1500)
        if build.returncode:
            raise AssertionError(build.stdout[-2000:] + build.stderr[-2000:])
        cls.tool = APP / '.build' / 'debug' / 'simv-library'

    def test_imported_folder_is_a_valid_library_with_sound_metadata(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / 'videos').mkdir()
            for source in sorted(MEDIA.glob('*.mp4')):
                shutil.copyfile(source, work / 'videos' / source.name)
            run = subprocess.run([str(self.tool), 'import-folder', str(work / 'videos'), str(work / 'root')],
                                 capture_output=True, text=True, timeout=600)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            library = work / 'root' / 'library'
            clips = stager.check_library(library)
            self.assertEqual({clip['orientation'] for clip in clips}, {'portrait', 'landscape'})
            document = json.loads((library / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(stager.validate_manifest(document), clips)
            for clip in clips:
                self.assertEqual(len(clip['rms_envelope']), -(-int(clip['duration_seconds'] * 1000) // 100))
            verify = subprocess.run([str(self.tool), 'verify', str(work / 'root')], capture_output=True, text=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            site = work / 'site'
            studio = work / 'studio'
            from simvltanea.browser import stage_studio
            stage_studio(studio)
            self.assertEqual(stager.stage_library_site(studio, library, site), len(clips))


if __name__ == '__main__':
    unittest.main()
