"""Prepared public-library loops: exact presentation timing and safe publication."""
from __future__ import annotations

from array import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.media import build_boomerangs as loops
from tools.media import verify_boomerangs as verification


FFMPEG = unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg prerequisite')


def source_clip(path, *, audio=True, short_audio=False, vfr=False):
    args = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=64x48:rate=30:duration=1.0']
    if audio:
        args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=' +
                 ('0.3' if short_audio else '1.0')]
    if vfr:
        args += ['-vf', r'settb=1/1000,setpts=N*33.333+mod(N\,3)*2', '-fps_mode', 'vfr']
    args += ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']
    if audio:
        args += ['-c:a', 'aac']
    subprocess.run([*args, str(path)], check=True, capture_output=True)


def make_library(root, **options):
    root.mkdir()
    (root / 'clips').mkdir()
    temporary = root / 'temporary.mp4'
    source_clip(temporary, **options)
    blob = temporary.read_bytes()
    identity = hashlib.sha256(blob).hexdigest()[:12]
    file = f'clips/{identity}.mp4'
    temporary.rename(root / file)
    clip = {'id': identity, 'file': file, 'width': 64, 'height': 48,
            'orientation': 'landscape', 'duration_seconds': 1.0, 'bytes': len(blob),
            'tags': {'keywords': ['test'], 'mood': ['calm']}}
    (root / 'manifest.json').write_text(json.dumps({'schema': 'simvltanea.public-demo/1', 'clips': [clip]}))
    return clip


class ArgumentTests(unittest.TestCase):
    def test_frame_arithmetic_and_invalid_overlap(self):
        self.assertEqual(loops.loop_frame_count(90, 0), 178)
        self.assertEqual(loops.loop_frame_count(90, 2), 176)
        for count, overlap in [(7, 2), (8, -1), (8, 1.5), (8, 5), (90, float('nan'))]:
            with self.subTest(count=count, overlap=overlap), self.assertRaises(loops.BuildError):
                loops.loop_frame_count(count, overlap)

    def test_refuses_existing_or_nested_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'library'
            source.mkdir()
            for out in [source, source / 'nested', Path(tmp)]:
                with self.subTest(out=out), self.assertRaises(loops.BuildError):
                    loops.build_library(source, out)

    def test_parallel_jobs_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for jobs in [0, 9, 1.5, True]:
                with self.subTest(jobs=jobs), self.assertRaises(loops.BuildError):
                    loops.build_library(root / 'source', root / 'out', jobs=jobs)

    def test_refuses_oversized_forward_asset_before_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            with mock.patch.object(loops, 'check_library', return_value=[{'bytes': 25 * 1024 * 1024 + 1}]), \
                    mock.patch.object(loops, 'build_variant') as encode:
                with self.assertRaises(loops.BuildError):
                    loops.build_library(source, root / 'output')
                encode.assert_not_called()
            self.assertFalse((root / 'output').exists())

    def test_measurement_failure_does_not_fabricate_loudness(self):
        with mock.patch.object(loops, 'run', side_effect=loops.BuildError('failed')):
            with self.assertRaises(loops.BuildError):
                loops.audio_facts(Path('x.mp4'), 1.0, True)


@FFMPEG
class MediaTests(unittest.TestCase):
    def test_cfr_publication_preserves_forward_identity_tags_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_library(root / 'source')
            source_manifest = (root / 'source/manifest.json').read_bytes()
            result = loops.build_library(root / 'source', root / 'output')
            new = result['clips'][0]
            for field in old:
                self.assertEqual(new[field], old[field])
            self.assertEqual((root / 'source/manifest.json').read_bytes(), source_manifest)
            self.assertEqual((root / 'source' / old['file']).read_bytes(),
                             (root / 'output' / new['file']).read_bytes())
            variant = new['variants']['boomerang']
            self.assertEqual(variant['frame_count'], 56)
            self.assertEqual(variant['fps'], 30)
            self.assertNotEqual(variant['id'], old['id'])
            self.assertEqual(variant['id'], hashlib.sha256(
                (root / 'output' / variant['file']).read_bytes()).hexdigest()[:12])
            self.assertEqual(variant['file'], f"clips/{variant['id']}.mp4")
            self.assertTrue(variant['has_audio'])
            self.assertTrue(math.isfinite(variant['lufs_integrated']))
            self.assertEqual(len(variant['rms_envelope']), math.ceil(variant['duration_seconds'] * 10))
            proof = loops.verify_encoded(root / 'output' / variant['file'], 56)
            self.assertLess(proof['av_delta_seconds'], .001)
            self.assertEqual(proof['r_frame_rate'], '30/1')
            self.assertEqual(proof['avg_frame_rate'], '30/1')
            receipt = verification.verify_library(root / 'output', jobs=1)
            self.assertEqual(receipt['logical_clips'], 1)
            self.assertEqual(receipt['variants'], 1)
            self.assertLess(receipt['max_av_delta_seconds'], .001)
            self.assertEqual(receipt['assets'][0]['logical_id'], old['id'])
            with self.assertRaises(loops.BuildError):
                verification.verify_library(root / 'source', jobs=1)

    def test_vfr_short_audio_and_silent_sources_have_exact_encoded_lengths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, options in [('vfr', {'vfr': True}), ('short', {'short_audio': True}),
                                  ('silent', {'audio': False})]:
                with self.subTest(name=name):
                    source = root / (name + '.mp4')
                    source_clip(source, **options)
                    if name == 'vfr':
                        frames = loops.probe(source, frames=True)['frames']
                        times = [int(frame['pts']) for frame in frames]
                        self.assertGreater(len({b - a for a, b in zip(times, times[1:])}), 1)
                    destination = root / (name + '-boom.mp4')
                    stats = loops.build_variant(source, destination)
                    self.assertGreaterEqual(stats['frame_count'], 54)
                    proof = loops.verify_encoded(destination, stats['frame_count'])
                    self.assertLess(proof['av_delta_seconds'], .001)
                    if name == 'silent':
                        self.assertFalse(stats['has_audio'])
                        self.assertIsNone(stats['lufs_integrated'])
                        self.assertIsNone(stats['peak_dbfs'])
                        self.assertTrue(all(x == 0 for x in stats['rms_envelope']))

    def test_zero_overlap_frame_count_and_reverse_audio_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.mp4'
            source_clip(source)
            for mode in ['forward', 'reverse']:
                stats = loops.build_variant(source, root / (mode + '.mp4'), fade_frames=0, audio_mode=mode)
                self.assertEqual(stats['frame_count'], 58)
                self.assertLess(loops.verify_encoded(root / (mode + '.mp4'), 58)['av_delta_seconds'], .001)

    def test_mono_measurement_preserves_native_amplitude(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'mono.mp4'
            source_clip(source)
            decoded = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(source),
                                               '-map', '0:a:0', '-af', 'atrim=duration=1',
                                               '-ar', '48000', '-f', 'f32le', '-'])
            samples = array('f')
            samples.frombytes(decoded)
            expected = 20 * math.log10(max(abs(value) for value in samples))
            facts = loops.audio_facts(source, 1.0, True)
            self.assertAlmostEqual(facts['peak_dbfs'], expected, places=5)
            expected_rms = math.sqrt(sum(value * value for value in samples[:4800]) / 4800)
            self.assertAlmostEqual(facts['rms_envelope'][0], expected_rms, places=6)

    def test_numbered_frames_do_not_duplicate_apex_or_wrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = root / 'numbered.mp4', root / 'boomerang.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            "nullsrc=size=32x32:rate=30:duration=1,geq=lum='16+6*N':cb=128:cr=128",
                            '-c:v', 'libx264', '-crf', '0', str(source)], check=True, capture_output=True)
            loops.build_variant(source, destination, fade_frames=0)
            def levels(path):
                return list(subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                                                     '-map', '0:v:0', '-vf', 'scale=1:1,format=gray',
                                                     '-f', 'rawvideo', '-']))
            forward, actual = levels(source), levels(destination)
            indices = [min(range(len(forward)), key=lambda i: abs(forward[i] - level)) for level in actual]
            self.assertEqual(indices, list(range(30)) + list(range(28, 0, -1)))

    def test_build_failure_does_not_publish_partial_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_library(root / 'source')
            with mock.patch.object(loops, 'build_variant', side_effect=loops.BuildError('encode failure')):
                with self.assertRaises(loops.BuildError):
                    loops.build_library(root / 'source', root / 'output')
            self.assertFalse((root / 'output').exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['source'])


if __name__ == '__main__':
    unittest.main()
