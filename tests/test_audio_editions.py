"""Edition declarations and the boundary around the historical exporter."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT / 'core', ROOT / 'tools'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import export_project
import verify_editions


class AudioEditionTests(unittest.TestCase):
    def check_audio(self, audio):
        errors = []
        verify_editions.validate_audio(errors, 'synthetic-proof', {'audio': audio})
        return errors

    def test_existing_registry_still_valid_and_unchanged(self):
        registry = json.loads((ROOT / 'editions.json').read_text())
        before = copy.deepcopy(registry)
        errors, records = verify_editions.validate_payload(registry, ROOT / 'site')
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 7)
        self.assertEqual(before, registry)

    def test_legacy_modes_retain_existing_controls(self):
        for mode in ('none', 'panel', 'mix'):
            with self.subTest(mode=mode):
                self.assertEqual(self.check_audio(dict(mode=mode, panel='left', gain=.8,
                    fade_seconds=.05, panel_gains={'left': 1.2, 'right': 0})), [])
                export_project.require_legacy_audio({'mode': mode})

    def test_approved_soundtrack_declaration(self):
        self.assertEqual(self.check_audio(dict(mode='soundtrack', source='audio/synthetic.wav',
            sha256='a' * 64, duration='5/2', volume=.8, loop=True,
            fade_in_seconds=1.5, fade_out_seconds=2.0)), [])

    def test_spatial_controls_validate_without_claiming_loop_bindings(self):
        self.assertEqual(self.check_audio(dict(mode='spatial_loops', master_volume=.7,
            spatial_panning=True, per_loop={'loop-1': {'gain': .8, 'mute_on_hold': True}})), [])

    def test_new_modes_reject_invalid_or_unimplemented_controls(self):
        for audio in (
            {'mode': 'soundtrack', 'source': '../private.wav', 'sha256': 'a' * 64, 'duration': '2'},
            {'mode': 'soundtrack', 'source': 'audio.wav', 'duration': '2'},
            {'mode': 'spatial_loops', 'master_volume': float('nan')},
            {'mode': 'spatial_loops', 'per_loop': {'loop-1': {'gain': -1}}},
            {'mode': 'spatial_loops', 'per_loop': {'loop-1': {'mute_on_hold': False}}},
            {'mode': 'spatial_loops', 'panel': 'left'},
        ):
            with self.subTest(audio=audio):
                self.assertTrue(self.check_audio(audio))

    def test_historical_exporter_explains_versioned_entrypoint(self):
        for mode in ('soundtrack', 'spatial_loops'):
            with self.subTest(mode=mode), self.assertRaisesRegex(SystemExit, '--state'):
                export_project.render_command(ROOT / 'synthetic.json', ROOT,
                    {'audio': {'mode': mode}}, {'name': 'proof'}, True, False)


if __name__ == '__main__':
    unittest.main()
