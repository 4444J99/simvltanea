"""Audio v1.1 authoring opt-in, rational clock and media-binding contracts.

The video bindings in state fixtures are schema-only. Only temporary WAV bytes
in the binding tests are actual media, generated specifically for these tests.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "core", ROOT / "tools"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import composition as c
from artifact001_layouts import build_artifact001
from composition_model import (AUDIO_SCHEMA_VERSION, Composition, LoopAudio,
                               SilentAudio, SoundtrackAudio, SpatialLoopsAudio)


def soundtrack(**overrides):
    return SoundtrackAudio(source="audio/test.wav", sha256="a" * 64, duration="2", **overrides)


def state(audio=None):
    authored = build_artifact001(3)
    if audio is not None:
        authored = replace(authored, schema_version=AUDIO_SCHEMA_VERSION, audio=audio)
    sources = {loop.source: dict(id=f"source-{index}", path=f"media/{index}.mp4", kind="video",
                                 sha256=hashlib.sha256(f"schema-only-{index}".encode()).hexdigest(),
                                 duration="3") for index, loop in enumerate(authored.loops)}
    return c.from_authoring_model(authored, sources)


class AudioModelTests(unittest.TestCase):
    def test_v1_stays_silent_and_keeps_its_serialized_shape(self):
        authored = build_artifact001(3)
        self.assertNotIn("audio", authored.to_dict())
        historical = state()
        self.assertEqual((historical["schema_version"], historical["engine_version"]), (1, "1.0.0"))
        self.assertEqual(historical["audio"], dict(mode="none", routing=None, generative=None))
        self.assertEqual(c.audio_at(historical, 24, "portrait"), {"mode": "none"})

    def test_audio_requires_explicit_authoring_and_compiled_version(self):
        for audio in (soundtrack(), SpatialLoopsAudio()):
            with self.subTest(mode=audio.mode):
                with self.assertRaisesRegex(ValueError, "silent in v1"):
                    replace(build_artifact001(3), audio=audio).validate()
                current = state(audio)
                self.assertEqual((current["schema_version"], current["engine_version"]), ("1.1", "1.1.0"))
                current.update(schema_version=1, engine_version="1.0.0")
                with self.assertRaisesRegex(c.StateError, "silent in v1"):
                    c.validate_state(current)
        for version, engine in ((1, "1.1.0"), ("1.1", "1.0.0"), (1.1, "1.1.0")):
            current = state(SilentAudio())
            current.update(schema_version=version, engine_version=engine)
            with self.assertRaises(c.StateError):
                c.validate_state(current)

    def test_typed_audio_round_trips_with_safe_decimal_controls(self):
        for audio in (SilentAudio(), soundtrack(volume=0.8, fade_in_seconds=1.5, fade_out_seconds=2),
                      SpatialLoopsAudio(master_volume=0.7, per_loop={"loop-2": LoopAudio(gain=0.8)})):
            authored = replace(build_artifact001(3), schema_version=AUDIO_SCHEMA_VERSION, audio=audio)
            self.assertEqual(Composition.from_dict(json.loads(authored.to_json())), authored)
            compiled = state(audio)
            c.validate_state(compiled)
            if audio.mode == "soundtrack":
                self.assertEqual(compiled["audio"]["volume"], "4/5")
                self.assertEqual(compiled["audio"]["fade_in_seconds"], "3/2")
            if audio.mode == "spatial_loops":
                self.assertEqual(compiled["audio"]["master_volume"], "7/10")
                self.assertEqual(compiled["audio"]["per_loop"]["loop-2"]["gain"], "4/5")
                self.assertEqual(compiled["audio"]["per_loop"]["loop-1"], dict(gain="1", mute_on_hold=True))

    def test_audio_does_not_change_visual_clock_or_source_resolution(self):
        historical = state()
        for audio in (soundtrack(), SpatialLoopsAudio()):
            current = state(audio)
            for frame in (0, 13, 47, 71, 96, 143):
                self.assertEqual(c.resolve_at(current, frame), c.resolve_at(historical, frame))

    def test_unsupported_options_fail_instead_of_being_ignored(self):
        bad_audio = [dict(mode="generative"), dict(mode="mix"),
                     dict(mode="spatial_loops", vertical_focal_gain=True),
                     dict(mode="spatial_loops", per_loop={"missing": {"gain": 1}}),
                     dict(mode="spatial_loops", per_loop={"loop-1": {"pan": 0}}),
                     dict(mode="spatial_loops", per_loop={"loop-1": {"mute": True}}),
                     dict(mode="spatial_loops", per_loop={"loop-1": {"mute_on_hold": False}}),
                     dict(mode="none", routing="panel", generative=None)]
        for audio in bad_audio:
            with self.subTest(audio=audio):
                current = state(SilentAudio())
                current["audio"] = audio
                with self.assertRaises(c.StateError):
                    c.validate_state(current)
        # Edition validation may defer the loop-ID binding, state validation cannot.
        c.validate_audio(dict(mode="spatial_loops", per_loop={"future-loop": {"gain": 1}}))

    def test_invalid_controls_and_unbound_media_are_rejected(self):
        for field, values in (("volume", [True, -1, 1.1, math.nan, math.inf]),
                              ("fade_in_seconds", [True, -0.1, math.nan, math.inf]),
                              ("duration", [True, 0, 2.0, "nan", "14401"]),
                              ("loop", [0, "true"]),
                              ("source", ["../test.wav", "/test.wav", "https://example.com/test.wav", "..\\test.wav"]),
                              ("sha256", [None, "x" * 64, "A" * 64])):
            for value in values:
                with self.subTest(field=field, value=value):
                    current = state(soundtrack())
                    current["audio"][field] = value
                    with self.assertRaises(c.StateError):
                        c.validate_state(current)
        for field in ("sha256", "duration"):
            current = state(soundtrack())
            del current["audio"][field]
            with self.assertRaisesRegex(c.StateError, "missing fields"):
                c.validate_state(current)

    def test_soundtrack_uses_global_rational_modulo_and_rotation_does_not_restart(self):
        current = state(soundtrack())
        before = copy.deepcopy(current)
        for frame, expected in ((0, "0"), (13, "13/24"), (47, "47/24"), (48, "0"), (49, "1/24")):
            portrait = c.audio_at(current, frame, "portrait")
            self.assertEqual(portrait["source_offset"], expected)
            self.assertEqual(portrait, c.audio_at(current, frame, "landscape"))
        self.assertEqual(current, before)

    def test_soundtrack_nonloop_ending_and_fades_have_finite_composition_envelope(self):
        current = state(soundtrack(volume="4/5", loop=False, fade_in_seconds="3/2", fade_out_seconds="3/2"))
        at_middle = c.audio_at(current, 24, "portrait")
        # Overlap uses minimum linear envelope, not multiplied ramps.
        self.assertEqual(at_middle["gain"], "8/15")
        self.assertEqual(c.audio_at(current, 0, "portrait")["gain"], "0")
        ended = c.audio_at(current, 48, "portrait")
        self.assertEqual(ended, dict(mode="soundtrack", source_offset="2", gain="0", playing=False))
        current["audio"]["loop"] = True
        self.assertTrue(c.audio_at(current, 48, "portrait")["playing"])
        self.assertFalse(c.audio_at(current, current["frames"], "portrait")["playing"])

    def test_spatial_pan_uses_exact_layout_center_and_portrait_is_centered(self):
        current = state(SpatialLoopsAudio(master_volume="7/10", per_loop={"loop-1": LoopAudio(gain="4/5")}))
        landscape = c.audio_at(current, 13, "landscape")["loops"]
        portrait = c.audio_at(current, 13, "portrait")["loops"]
        for track, centered, cell in zip(landscape, portrait, current["layouts"]["landscape"]["cells"]):
            x, _, width, _ = map(Fraction, cell["rect"])
            self.assertEqual(Fraction(track["pan"]), 2 * x + width - 1)
            self.assertEqual(centered["pan"], "0")
            self.assertEqual(track["source_offset"], centered["source_offset"])
        self.assertEqual(landscape[0]["gain"], "14/25")
        current["audio"]["spatial_panning"] = False
        self.assertTrue(all(track["pan"] == "0" for track in c.audio_at(current, 13, "landscape")["loops"]))

    def test_hold_release_mutes_only_target_and_preserves_source_clock(self):
        current = state(SpatialLoopsAudio())
        baseline = copy.deepcopy(current)
        current["events"] = [dict(op="hold", frame=24, loop="loop-1", value=True),
                             dict(op="hold", frame=72, loop="loop-1", value=False)]
        c.validate_state(current)
        for frame in (24, 48, 71):
            tracks = c.audio_at(current, frame, "landscape")["loops"]
            self.assertEqual((tracks[0]["source_offset"], tracks[0]["gain"]), ("1", "0"))
            self.assertEqual(tracks[1:], c.audio_at(baseline, frame, "landscape")["loops"][1:])
        resumed = c.audio_at(current, 72, "landscape")["loops"][0]
        self.assertEqual((resumed["source_offset"], resumed["gain"], resumed["held"]), ("1", "1", False))
        current["sources"][0].update(kind="still", path="image.png")
        c.validate_state(current)
        self.assertEqual(c.audio_at(current, 73, "landscape")["loops"][0]["gain"], "0")


@unittest.skipUnless(shutil.which("ffprobe"), "ffprobe is required for real soundtrack binding verification")
class SoundtrackBindingTests(unittest.TestCase):
    def test_real_audio_hash_duration_and_symlink_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "audio" / "test.wav"
            media.parent.mkdir()
            with wave.open(str(media), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * n / 8000)))
                                            for n in range(16000)))
            current = state(soundtrack())
            current["audio"]["sha256"] = c.sha256_file(media)
            self.assertEqual(c.soundtrack_path(current, root), media)
            current["audio"]["duration"] = "3"
            with self.assertRaisesRegex(c.StateError, "duration disagrees"):
                c.soundtrack_path(current, root)
            current["audio"]["duration"] = "2"
            current["audio"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(c.StateError, "hash mismatch"):
                c.soundtrack_path(current, root)
            isolated = root / "isolated"
            isolated.mkdir()
            (isolated / "escape.wav").symlink_to(media)
            current["audio"]["source"] = "escape.wav"
            with self.assertRaisesRegex(c.StateError, "symlink escapes"):
                c.soundtrack_path(current, isolated, verify=False)


if __name__ == "__main__":
    unittest.main()
