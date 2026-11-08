"""The deploy helper assembles studio + public library, and refuses anything else without writing."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simvltanea.browser.browser_studio import STUDIO_FILES as STAGED_FILES, stage_studio
from tools.publishing.stage_library_site import (STUDIO_FILES, LibrarySiteError, main, stage_library_site,
                                                 validate_manifest)

REPOSITORY = Path(__file__).resolve().parents[2]


def clip_bytes(number: int) -> bytes:
    # Stand-in bytes: the helper checks names, sizes and digests, never decodes.
    return b'\x00\x00\x00\x18ftypisom' + bytes([number]) * (200 + number)


class StageLibrarySiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix='library-site-'))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.studio = self.temp / 'studio'
        stage_studio(self.studio)
        self.library = self.temp / 'library'
        (self.library / 'clips').mkdir(parents=True)
        clips = []
        for number in range(1, 4):
            data = clip_bytes(number)
            clip_id = hashlib.sha256(data).hexdigest()[:12]
            (self.library / 'clips' / f'{clip_id}.mp4').write_bytes(data)
            portrait = number % 2 == 1
            clips.append({'id': clip_id, 'file': f'clips/{clip_id}.mp4', 'width': 270 if portrait else 480,
                          'height': 480 if portrait else 270, 'orientation': 'portrait' if portrait else 'landscape',
                          'duration_seconds': 2.5, 'bytes': len(data),
                          'tags': {'keywords': ['sea'], 'mood': ['calm'], 'shot': 'wide', 'palette': ['blue']}})
        self.manifest = {'schema': 'simvltanea.public-demo/1', 'clips': clips}
        self.write_manifest()
        self.site = self.temp / 'site'

    def write_manifest(self, document=None):
        (self.library / 'manifest.json').write_text(json.dumps(document or self.manifest), encoding='utf-8')

    def refused(self, pattern: str):
        with self.assertRaisesRegex(LibrarySiteError, pattern):
            stage_library_site(self.studio, self.library, self.site)
        self.assertFalse(self.site.exists())

    def test_assembles_studio_and_library_on_one_origin(self):
        self.assertEqual(STUDIO_FILES, STAGED_FILES)
        self.assertEqual(stage_library_site(self.studio, self.library, self.site), 3)
        names = sorted(str(path.relative_to(self.site)) for path in self.site.rglob('*') if path.is_file())
        clips = sorted(f"library/{clip['file']}" for clip in self.manifest['clips'])
        self.assertEqual(names, sorted([*STUDIO_FILES, 'library/manifest.json', *clips]))
        for name in STUDIO_FILES:
            self.assertEqual((self.site / name).read_bytes(), (self.studio / name).read_bytes())
        self.assertEqual((self.site / 'library' / 'manifest.json').read_bytes(),
                         (self.library / 'manifest.json').read_bytes())

    def add_boomerang(self):
        data = clip_bytes(9)
        clip_id = hashlib.sha256(data).hexdigest()[:12]
        source = self.manifest['clips'][0]
        variant = {key: source[key] for key in ('width', 'height', 'orientation')}
        variant.update(id=clip_id, file=f'clips/{clip_id}.mp4', bytes=len(data),
                       duration_seconds=4.8, fps=30, frame_count=144,
                       seam_offset_seconds=2.4, has_audio=True,
                       lufs_integrated=-22.5, peak_dbfs=-5.2,
                       envelope_hz=10, rms_envelope=[0.1] * 48)
        source['variants'] = {'boomerang': variant}
        (self.library / variant['file']).write_bytes(data)
        self.write_manifest()
        return variant, data

    def test_stages_boomerang_without_changing_logical_clip_identity(self):
        variant, data = self.add_boomerang()
        source_id = self.manifest['clips'][0]['id']
        self.assertEqual(stage_library_site(self.studio, self.library, self.site), 3)
        self.assertEqual((self.site / 'library' / variant['file']).read_bytes(), data)
        document = json.loads((self.site / 'library/manifest.json').read_text())
        self.assertEqual(document['clips'][0]['id'], source_id)
        self.assertEqual(len(list((self.site / 'library/clips').iterdir())), 4)

    def test_rejects_invalid_boomerang_metadata_before_writing(self):
        variant, _data = self.add_boomerang()
        for field, value in [('fps', 29), ('frame_count', 145),
                             ('seam_offset_seconds', 5), ('has_audio', 1),
                             ('rms_envelope', [0.1] * 47), ('rms_envelope', [float('nan')] * 48),
                             ('lufs_integrated', float('inf')), ('peak_dbfs', None),
                             ('file', '../private.mov')]:
            with self.subTest(field=field, value=value):
                original = variant[field]
                variant[field] = value
                self.write_manifest()
                self.refused('manifest')
                variant[field] = original
        variant['id'] = self.manifest['clips'][0]['id']
        variant['file'] = self.manifest['clips'][0]['file']
        self.write_manifest()
        self.refused('duplicate')

    def test_identical_variant_content_is_deduplicated_across_logical_clips(self):
        variant, data = self.add_boomerang()
        self.manifest['clips'][1]['variants'] = {'boomerang': dict(variant)}
        self.write_manifest()
        self.assertEqual(stage_library_site(self.studio, self.library, self.site), 3)
        self.assertEqual((self.site / 'library' / variant['file']).read_bytes(), data)
        self.assertEqual(len(list((self.site / 'library/clips').iterdir())), 4)

    def test_duplicate_content_id_with_conflicting_facts_is_refused(self):
        variant, _data = self.add_boomerang()
        self.manifest['clips'][1]['variants'] = {'boomerang': {**variant, 'peak_dbfs': -4}}
        self.write_manifest()
        self.refused('conflicting asset facts')

    def test_silent_boomerang_allows_explicit_null_measurements(self):
        variant, _data = self.add_boomerang()
        variant.update(has_audio=False, lufs_integrated=None, peak_dbfs=None,
                       rms_envelope=[0] * 48)
        self.write_manifest()
        self.assertEqual(stage_library_site(self.studio, self.library, self.site), 3)

    def test_rejects_changed_missing_and_extra_variant_files(self):
        variant, data = self.add_boomerang()
        path = self.library / variant['file']
        path.write_bytes(data[:-1] + b'x')
        self.refused('does not match its manifest id')
        path.unlink()
        self.refused('missing')

    def test_optional_forward_audio_metadata_is_checked(self):
        source = self.manifest['clips'][0]
        source.update(has_audio=False, lufs_integrated=None, peak_dbfs=None,
                      envelope_hz=10, rms_envelope=[0] * 25)
        validate_manifest(self.manifest)
        source['rms_envelope'][0] = 2
        with self.assertRaisesRegex(LibrarySiteError, 'manifest'):
            validate_manifest(self.manifest)

    def test_an_existing_empty_site_is_accepted_and_a_full_one_refused(self):
        self.site.mkdir()
        self.assertEqual(stage_library_site(self.studio, self.library, self.site), 3)
        with self.assertRaisesRegex(LibrarySiteError, 'absent or an empty'):
            stage_library_site(self.studio, self.library, self.site)

    def test_refuses_a_library_without_a_valid_manifest(self):
        (self.library / 'manifest.json').unlink()
        self.refused('no manifest.json')
        (self.library / 'manifest.json').write_text('{not json', encoding='utf-8')
        self.refused('not JSON')
        clip = self.manifest['clips'][0]
        variants = {
            'schema': {**self.manifest, 'schema': 'simvltanea.public-demo/2'},
            'empty': {**self.manifest, 'clips': []},
            'traversal': {**self.manifest, 'clips': [{**clip, 'file': '../index.html'}]},
            'id-mismatch': {**self.manifest, 'clips': [{**clip, 'file': 'clips/0123456789ab.mp4'}]},
            'uppercase-id': {**self.manifest, 'clips': [{**clip, 'id': clip['id'].upper()}]},
            'duplicate': {**self.manifest, 'clips': [clip, clip]},
            'width': {**self.manifest, 'clips': [{**clip, 'width': 270.5}]},
            'bool-bytes': {**self.manifest, 'clips': [{**clip, 'bytes': True}]},
            'huge': {**self.manifest, 'clips': [{**clip, 'bytes': 65 * 1024 * 1024}]},
            'orientation': {**self.manifest, 'clips': [{**clip, 'orientation': 'landscape'}]},
            'duration': {**self.manifest, 'clips': [{**clip, 'duration_seconds': float('nan')}]},
            'short': {**self.manifest, 'clips': [{**clip, 'duration_seconds': 0.1}]},
            'tags': {**self.manifest, 'clips': [{**clip, 'tags': ['sea']}]},
        }
        for name, document in variants.items():
            with self.subTest(variant=name):
                (self.library / 'manifest.json').write_text(json.dumps(document), encoding='utf-8')
                self.refused('manifest')
                with self.assertRaises(LibrarySiteError):
                    validate_manifest(document)

    def test_refuses_clips_the_manifest_does_not_name(self):
        (self.library / 'clips' / 'ffffffffffff.mp4').write_bytes(b'extra')
        self.refused('does not list')

    def test_refuses_any_other_file_in_the_library(self):
        cases = {'notes.txt': 'other than', '.DS_Store': 'other than', 'clips/.DS_Store': 'does not list',
                 'clips/readme.txt': 'does not list'}
        for relative, pattern in cases.items():
            with self.subTest(file=relative):
                (self.library / relative).write_bytes(b'x')
                self.refused(pattern)
                (self.library / relative).unlink()
        (self.library / 'originals').mkdir()
        self.refused('other than')

    def test_refuses_missing_altered_or_linked_clips(self):
        first = self.library / self.manifest['clips'][0]['file']
        data = first.read_bytes()
        first.unlink()
        self.refused('missing')
        first.write_bytes(data[:-1] + bytes([data[-1] ^ 0xff]))
        self.refused('does not match its manifest id')
        first.write_bytes(data + b'\x00')
        self.refused('size does not match')
        first.unlink()
        first.symlink_to(self.library / self.manifest['clips'][1]['file'])
        self.refused('regular files')

    def test_refuses_a_studio_output_that_is_not_exactly_the_studio(self):
        (self.studio / 'extra.js').write_text('x')
        self.refused('exactly')
        (self.studio / 'extra.js').unlink()
        (self.studio / 'layouts.json').unlink()
        self.refused('exactly')

    def test_command_line_reports_counts_and_exit_codes(self):
        command = [sys.executable, '-m', 'tools.publishing.stage_library_site', '--studio-out', str(self.studio),
                   '--library', str(self.library), '--site', str(self.site)]
        env = {'PYTHONPATH': f'{REPOSITORY}:{REPOSITORY / "src"}', 'PATH': '/usr/bin:/bin'}
        done = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env, cwd=REPOSITORY)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), f'site assembled: {len(STUDIO_FILES)} studio files, 3 library clips')
        again = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env, cwd=REPOSITORY)
        self.assertEqual(again.returncode, 2)
        self.assertIn('refused: site must be absent or an empty directory', again.stderr)
        for clip in self.manifest['clips']:
            self.assertNotIn(clip['id'], done.stdout + again.stderr)
        self.assertEqual(main(['--studio-out', str(self.studio), '--library', str(self.temp / 'none'),
                               '--site', str(self.temp / 'other')]), 2)


if __name__ == '__main__':
    unittest.main()
