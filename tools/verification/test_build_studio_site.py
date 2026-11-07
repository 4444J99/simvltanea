"""The Pages build publishes a pinned library and staged code, never repository files."""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        # The public Pages source refuses urllib's default User-Agent (Cloudflare 1010).
        if self.headers.get('User-Agent', '').startswith('Python-urllib/'):
            self.send_error(403, 'Default Python User-Agent refused')
            return
        super().do_GET()


class BuildStudioSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-build-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / 'source' / 'library'
        (self.library / 'clips').mkdir(parents=True)
        self.data = b'\x00\x00\x00\x18ftypisom' + b'public clip bytes'
        clip_id = hashlib.sha256(self.data).hexdigest()[:12]
        self.clip = {'id': clip_id, 'file': f'clips/{clip_id}.mp4', 'width': 480,
                     'height': 270, 'orientation': 'landscape', 'duration_seconds': 2,
                     'bytes': len(self.data), 'tags': {}}
        (self.library / self.clip['file']).write_bytes(self.data)
        self.document = {'schema': 'simvltanea.public-demo/1', 'clips': [self.clip]}
        self.write_manifest()
        # Neither unrelated source files nor repository archives belong in the output.
        (self.library / 'repository.zip').write_bytes(b'not public site content')
        handler = functools.partial(QuietHandler, directory=str(self.root / 'source'))
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_port}/library/'
        self.output = self.root / 'site'

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def write_manifest(self):
        self.manifest = json.dumps(self.document).encode()
        (self.library / 'manifest.json').write_bytes(self.manifest)
        self.pin = hashlib.sha256(self.manifest).hexdigest()

    def run_build(self, pin=None):
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
        return subprocess.run(
            [sys.executable, '-m', 'tools.publishing.build_studio_site',
             '--library-url', self.url, '--manifest-sha256', pin or self.pin,
             '--output', str(self.output)], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30,
        )

    def assert_refused(self, result, message):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(message, result.stderr)
        self.assertFalse(self.output.exists())

    def test_build_copies_only_staged_site_and_pinned_library(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        files = {path.relative_to(self.output).as_posix()
                 for path in self.output.rglob('*') if path.is_file()}
        self.assertEqual(files, {'index.html', 'runtime.js', 'compiler.js', 'studio.js',
                                 'layouts.json', 'lab.html', 'lab_model.js', 'lab_engine.js', 'lab_ui.js',
                                 'lab_audio.js', 'library/manifest.json',
                                 'library/' + self.clip['file']})
        self.assertEqual((self.output / 'library/manifest.json').read_bytes(), self.manifest)
        self.assertEqual((self.output / 'library' / self.clip['file']).read_bytes(), self.data)
        self.assertIn('1 library clips', result.stdout)

    def add_boomerang(self):
        data = b'public boomerang bytes'
        clip_id = hashlib.sha256(data).hexdigest()[:12]
        variant = {'id': clip_id, 'file': f'clips/{clip_id}.mp4',
                   'width': 480, 'height': 270, 'orientation': 'landscape',
                   'bytes': len(data), 'duration_seconds': 3.8, 'fps': 30,
                   'frame_count': 114, 'seam_offset_seconds': 1.9,
                   'has_audio': False, 'lufs_integrated': None, 'peak_dbfs': None,
                   'envelope_hz': 10, 'rms_envelope': [0] * 38}
        self.clip['variants'] = {'boomerang': variant}
        (self.library / variant['file']).write_bytes(data)
        self.write_manifest()
        return variant, data

    def test_downloads_manifest_listed_variants_and_checks_their_hashes(self):
        variant, data = self.add_boomerang()
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / 'library' / variant['file']).read_bytes(), data)
        self.assertFalse((self.output / 'library/repository.zip').exists())

    def test_variant_file_size_limit_is_enforced_before_publication(self):
        variant, _data = self.add_boomerang()
        variant['bytes'] = 25 * 1024 * 1024 + 1
        self.write_manifest()
        self.assert_refused(self.run_build(), '25 MiB')

    def test_variant_corruption_refuses_publication(self):
        variant, data = self.add_boomerang()
        (self.library / variant['file']).write_bytes(data[:-1] + b'x')
        self.assert_refused(self.run_build(), 'does not match its manifest id')

    def test_builds_an_admitted_local_library_without_remote_downloads(self):
        variant, data = self.add_boomerang()
        (self.library / 'repository.zip').unlink()
        result = subprocess.run(
            [sys.executable, '-m', 'tools.publishing.build_studio_site',
             '--library', str(self.library), '--output', str(self.output)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / 'library' / variant['file']).read_bytes(), data)

    def test_manifest_change_refuses_publication(self):
        self.assert_refused(self.run_build(pin='0' * 64), 'manifest SHA-256')

    def test_clip_change_refuses_publication(self):
        (self.library / self.clip['file']).write_bytes(self.data[:-1] + b'x')
        self.assert_refused(self.run_build(), 'does not match its manifest id')

    def test_missing_clip_refuses_publication(self):
        (self.library / self.clip['file']).unlink()
        self.assert_refused(self.run_build(), '404')

    def test_truncated_clip_refuses_publication(self):
        (self.library / self.clip['file']).write_bytes(self.data[:-1])
        self.assert_refused(self.run_build(), 'size')

    def test_pages_file_size_limit_is_enforced_before_publication(self):
        self.clip['bytes'] = 25 * 1024 * 1024 + 1
        self.write_manifest()
        self.assert_refused(self.run_build(), '25 MiB')

    def test_invalid_manifest_cannot_fetch_outside_the_library(self):
        self.clip['file'] = '../repository.zip'
        self.write_manifest()
        self.assert_refused(self.run_build(), 'clips/<id>.mp4')

    def test_existing_content_is_preserved(self):
        self.output.mkdir()
        (self.output / 'keep.txt').write_text('preserve me')
        result = self.run_build()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual((self.output / 'keep.txt').read_text(), 'preserve me')
        self.assertEqual(list(self.output.iterdir()), [self.output / 'keep.txt'])


if __name__ == '__main__':
    unittest.main()
