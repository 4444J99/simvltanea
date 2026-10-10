"""Admission and artwork semantics for the bounded TMB composition importer."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simvltanea.authoring import composition as c
from simvltanea.browser.browser_runtime import compile_plan
from tools.editions import build_tmb_composition as importer


def video_facts() -> dict:
    return dict(streams=[dict(codec_type='video', codec_name='h264', pix_fmt='yuv420p',
                             duration='8.000000', start_time='0.000000', width=768,
                             height=528, nb_frames='192', avg_frame_rate='24/1')])


def audio_facts() -> dict:
    return dict(streams=[dict(codec_type='audio', codec_name='aac', duration='8.000000',
                             start_time='0.000000', channels=2, sample_rate='48000')])


def bound_media() -> list[dict]:
    return [dict(path=f'media/generation-{index:02d}.mp4', sha256=str(index) * 64)
            for index in (1, 2)]


class AdmissionTests(unittest.TestCase):
    def test_missing_source_is_refused_before_git_blob_read(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(importer, 'run') as run:
            with self.assertRaisesRegex(c.StateError, 'missing regular source'):
                importer.verify_blob(Path(directory), Path('absent.mp4'), importer.ATLAS_REVISION)
            run.assert_not_called()

    def test_changed_video_is_refused_against_pinned_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.mp4').write_bytes(b'changed')
            with patch.object(importer, 'run', return_value=b'accepted'):
                with self.assertRaisesRegex(c.StateError, 'source hash differs'):
                    importer.verify_blob(root, Path('source.mp4'), importer.ATLAS_REVISION)

    def test_symbolic_revision_cannot_replace_explicit_pin(self):
        with self.assertRaisesRegex(c.StateError, 'full pinned Git commit'):
            importer.verify_revision(Path('.'), 'HEAD')

    def test_invalid_duration_frame_count_and_audio_format_refused(self):
        importer.validate_streams(video_facts(), 'video')
        importer.validate_streams(audio_facts(), 'audio')
        for kind, field, value in [('video', 'duration', '7.999'),
                                    ('video', 'nb_frames', '191'),
                                    ('video', 'width', 384),
                                    ('audio', 'channels', 4),
                                    ('audio', 'start_time', '0.021')]:
            facts = video_facts() if kind == 'video' else audio_facts()
            facts['streams'][0][field] = value
            with self.subTest(kind=kind, field=field):
                with self.assertRaises(c.StateError):
                    importer.validate_streams(facts, kind)

    def test_audio_digest_is_required_even_when_video_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / importer.MEDIA
            media.mkdir(parents=True)
            manifest = dict(schema='synchronized-generation-audio/0.1',
                            generations={'G01': {'sha256': hashlib.sha256(b'accepted').hexdigest()}})
            (media / 'audio-manifest.json').write_text(json.dumps(manifest))
            (media / 'generation-01.audio.m4a').write_bytes(b'changed')
            identity = {'sha256': importer.digest(media / 'audio-manifest.json')}
            with patch.object(importer, 'verify_revision'), patch.object(importer, 'verify_blob', return_value=identity):
                with self.assertRaisesRegex(c.StateError, 'audio hash mismatch'):
                    importer.admit_sources(root, importer.SOURCE_REVISION, importer.ATLAS_REVISION)

    def test_manifest_change_between_authentication_and_parse_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / importer.MEDIA
            media.mkdir(parents=True)
            (media / 'audio-manifest.json').write_text('{}')
            with patch.object(importer, 'verify_revision'), patch.object(
                    importer, 'verify_blob', return_value={'sha256': '0' * 64}):
                with self.assertRaisesRegex(c.StateError, 'manifest changed'):
                    importer.admit_sources(root, importer.SOURCE_REVISION, importer.ATLAS_REVISION)

    def test_preview_digests_cover_nested_served_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'media').mkdir()
            (root / 'index.html').write_bytes(b'html')
            (root / 'media' / 'video.mp4').write_bytes(b'video')
            self.assertEqual(importer.preview_digests(root), {
                'index.html': hashlib.sha256(b'html').hexdigest(),
                'media/video.mp4': hashlib.sha256(b'video').hexdigest(),
            })

    def test_preview_digests_refuse_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target').write_bytes(b'source')
            (root / 'alias').symlink_to(root / 'target')
            with self.assertRaisesRegex(c.StateError, 'symbolic link'):
                importer.preview_digests(root)

    def test_existing_output_is_refused_even_when_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(c.StateError, 'already occupied'):
                importer.validate_output(Path(directory))

    def test_output_outside_proof_lane_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(c.StateError, 'ignored proof lane'):
                importer.validate_output(Path(directory) / 'new-edition')

    def test_broken_destination_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'link'
            target.symlink_to(Path(directory) / 'absent')
            with self.assertRaisesRegex(c.StateError, 'already occupied'):
                importer.validate_output(target)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.authored, self.state = importer.composition_state(bound_media())

    def test_version_audio_and_atomic_generations(self):
        self.assertEqual((self.state['schema_version'], self.state['engine_version']), ('1.1', '1.1.0'))
        self.assertEqual(self.state['audio']['mode'], 'spatial_loops')
        self.assertEqual(len(self.state['sources']), 2)
        self.assertEqual([loop['bank'] for loop in self.state['loops']],
                         [['generation-01'], ['generation-02']])
        self.assertFalse(self.state['allow_source_reuse'])
        self.assertEqual([loop['rate'] for loop in self.state['loops']], ['1', '1'])
        self.assertEqual([loop['offset'] for loop in self.state['loops']], ['0', '1'])

    def test_independent_phase_and_wrap_preserve_atlas_time(self):
        for frame, expected in [(0, ['0', '1']), (24, ['1', '2']),
                                (168, ['7', '0']), (192, ['0', '1'])]:
            with self.subTest(frame=frame):
                snapshot = c.resolve_at(self.state, frame)
                self.assertEqual([loop['source_offset'] for loop in snapshot['loops']], expected)

    def test_orientation_changes_only_geometry_and_pan(self):
        portrait = c.presentation_at(self.state, 31, 528, 768)
        landscape = c.presentation_at(self.state, 31, 768, 528)
        self.assertEqual(portrait['loops'], landscape['loops'])
        self.assertTrue(all(cell['fit'] == 'contain' for cell in portrait['layout']['cells']))
        self.assertTrue(all(cell['fit'] == 'contain' for cell in landscape['layout']['cells']))
        landscape_audio = c.audio_at(self.state, 31, 'landscape')['loops']
        portrait_audio = c.audio_at(self.state, 31, 'portrait')['loops']
        self.assertEqual([track['gain'] for track in landscape_audio], ['14/25', '21/50'])
        self.assertEqual([track['pan'] for track in portrait_audio], ['0', '0'])
        self.assertLess(float(c.rational(landscape_audio[0]['pan'], 'pan')), 0)
        self.assertGreater(float(c.rational(landscape_audio[1]['pan'], 'pan')), 0)

    def test_holding_one_loop_does_not_stop_other_generation(self):
        held = copy.deepcopy(self.state)
        held['events'] = [dict(op='hold', frame=24, loop='loop-1', value=True)]
        audio = c.audio_at(held, 48, 'landscape')['loops']
        baseline = c.audio_at(self.state, 48, 'landscape')['loops']
        self.assertEqual(audio[0]['source_offset'], '1')
        self.assertEqual(audio[0]['gain'], '0')
        self.assertEqual(audio[1], baseline[1])

    def test_audio_opt_in_does_not_change_visual_spans(self):
        silent = copy.deepcopy(self.state)
        silent['audio'] = dict(mode='none', routing=None, generative=None)
        self.assertEqual(compile_plan(silent)['tracks'], compile_plan(self.state)['tracks'])

    def test_reusing_one_generation_as_two_loops_is_refused(self):
        media = bound_media()
        media[1]['sha256'] = media[0]['sha256']
        with self.assertRaisesRegex(c.StateError, 'two distinct generations'):
            importer.composition_state(media)


if __name__ == '__main__':
    unittest.main()
