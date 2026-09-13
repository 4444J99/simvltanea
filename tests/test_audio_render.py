"""Decoded synthetic-tone evidence for opt-in Audio v1.1; no archival audio claims."""
from __future__ import annotations

import array
import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "core"))
import composition as c
import render_triptych as r

RATE = 48000


def decoded(path: Path) -> tuple[array.array, array.array]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0",
                          "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
                         check=True, capture_output=True).stdout
    values = array.array("f")
    values.frombytes(raw)
    return values[::2], values[1::2]


def rms(values: array.array, start: float, end: float) -> float:
    window = values[round(start * RATE):round(end * RATE)]
    return math.sqrt(sum(value * value for value in window) / len(window))


def amplitude(values: array.array, frequency: float, start: float, end: float) -> float:
    low, high = round(start * RATE), round(end * RATE)
    cosine = sine = 0.0
    for sample in range(low, high):
        angle = 2 * math.pi * frequency * sample / RATE
        cosine += values[sample] * math.cos(angle)
        sine += values[sample] * math.sin(angle)
    return 2 * math.hypot(cosine, sine) / (high - low)


def write_tone(path: Path, duration: int, channels: int = 1, stepped: bool = False) -> None:
    samples = array.array("h")
    for index in range(duration * RATE):
        t = index / RATE
        for channel in range(channels):
            frequency = (220 * (1 + int(t)) if stepped else 880) if channels == 1 else (440 if channel == 0 else 660)
            samples.append(round(7000 * math.sin(2 * math.pi * frequency * t)))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(samples.tobytes())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class AudioRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generated = HERE / "runtime-proof"
        generated.mkdir(exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix="audio-tests-", dir=generated)
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.root = Path(cls.scratch.name)
        for name, channels, stepped in (("steps", 1, True), ("sibling", 1, False), ("stereo", 2, False)):
            audio = cls.root / f"{name}.wav"
            write_tone(audio, 4, channels, stepped)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "color=c=blue:s=64x64:r=20:d=4", "-i", str(audio), "-c:v", "libx264",
                            "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
                            "-t", "4", str(cls.root / f"{name}.mov")], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=red:s=64x64:r=20:d=4", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-an", str(cls.root / "silent.mp4")], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=green:s=64x64:r=20:d=4", "-itsoffset", "1", "-i",
                        str(cls.root / "sibling.wav"), "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "4", str(cls.root / "delayed.mp4")],
                       check=True, capture_output=True)
        write_tone(cls.root / "master.wav", 1, stepped=True)
        with patch.object(sys, "argv", ["render_triptych.py"]):
            cls.defaults = r.build_settings(r.parse_args())

    def state(self) -> dict:
        names = ("steps.mov", "sibling.mov", "silent.mp4")
        sources = [dict(id=f"source-{i}", path=name, sha256=c.sha256_file(self.root / name),
                        kind="video", duration="4") for i, name in enumerate(names)]
        loops = [dict(id=f"loop-{i}", bank=[f"source-{i}"], offset="0", rate="1", period="10",
                      epoch=0, held=False) for i in range(3)]
        layouts = {}
        for orientation in ("portrait", "landscape"):
            cells = []
            for i in range(3):
                rect = [f"{i}/3", "0", "1/3", "1"] if orientation == "landscape" else ["0", f"{i}/3", "1", "1/3"]
                cells.append(dict(loop=f"loop-{i}", rect=rect, fit="cover", focal=["1/2", "1/2"]))
            layouts[orientation] = dict(name=orientation, cells=cells)
        return dict(schema_version="1.1", engine_version="1.1.0", rng=c.RNG, seed="audio-proof",
                    fps=20, frames=80, allow_source_reuse=False, sources=sources, loops=loops,
                    layouts=layouts, events=[], audio=dict(mode="spatial_loops", master_volume=0.6,
                    spatial_panning=True, per_loop={f"loop-{i}": dict(gain=1 if i == 0 else 0) for i in range(3)}))

    def soundtrack(self, state: dict, **overrides) -> None:
        state["audio"] = dict(mode="soundtrack", source="master.wav",
                              sha256=c.sha256_file(self.root / "master.wav"), duration="1",
                              volume=0.8, loop=True, fade_in_seconds=0.2, fade_out_seconds=0.2,
                              **overrides)

    def setup_render(self, state: dict, orientation: str = "landscape"):
        width, height = (100, 56) if orientation == "landscape" else (56, 100)
        segments = c.compile_segments(state, self.root, orientation, width, height)
        config = c.audio_config(state)
        settings = replace(self.defaults, width=width, height=height, fps=state["fps"], preset="ultrafast",
                           work_dir=self.root / "work", output_file=self.root / "final.mp4",
                           composition_audio=config if config["mode"] != "none" else None,
                           soundtrack_path=c.soundtrack_path(state, self.root))
        return segments, settings

    def render_audio(self, state: dict, orientation: str = "landscape"):
        segments, settings = self.setup_render(state, orientation)
        output = self.root / "decoded.wav"
        r.render_composition_audio(segments, settings, output)
        return decoded(output)

    def test_soundtrack_global_loop_fades_and_segment_independence(self):
        state = self.state()
        self.soundtrack(state)
        plain = self.render_audio(state)[0]
        state["events"] = [dict(op="hold", loop="loop-0", frame=10, value=True),
                           dict(op="hold", loop="loop-0", frame=30, value=False)]
        segmented = self.render_audio(state)[0]
        self.assertEqual(plain, segmented, "visual segmentation must not reset soundtrack samples")
        self.assertEqual(len(segmented), 4 * RATE)
        self.assertEqual(segmented[RATE:2 * RATE], segmented[2 * RATE:3 * RATE])
        self.assertLess(rms(segmented, 0, 0.02), rms(segmented, 0.3, 0.4) * 0.12)
        self.assertLess(rms(segmented, 3.98, 4), rms(segmented, 3.3, 3.4) * 0.12)

    def test_nonloop_fade_ends_at_source_end_and_then_exact_silence(self):
        state = self.state()
        self.soundtrack(state)
        state["audio"].update(loop=False, fade_in_seconds=0, fade_out_seconds=0.2)
        left, right = self.render_audio(state)
        self.assertLess(rms(left, 0.98, 1), rms(left, 0.5, 0.6) * 0.12)
        self.assertEqual(max(abs(value) for value in left[RATE:]), 0)
        self.assertEqual(left, right)

    def test_mono_soundtrack_uses_unity_speaker_upmix(self):
        state = self.state()
        self.soundtrack(state)
        state["audio"].update(volume=1, fade_in_seconds=0, fade_out_seconds=0)
        left, right = self.render_audio(state)
        with wave.open(str(self.root / "master.wav"), "rb") as stream:
            source = array.array("h")
            source.frombytes(stream.readframes(RATE))
        expected = math.sqrt(sum((value / 32768) ** 2 for value in source) / RATE)
        self.assertAlmostEqual(rms(left, 0, 1), expected, places=6)
        self.assertEqual(left, right)

    def test_delayed_source_audio_preserves_source_video_clock(self):
        state = self.state()
        state["sources"][0].update(path="delayed.mp4", sha256=c.sha256_file(self.root / "delayed.mp4"))
        left, _ = self.render_audio(state)
        self.assertLess(rms(left, 0.1, 0.9), 0.0001)
        self.assertGreater(amplitude(left, 880, 1.1, 1.4), 0.1)
        self.assertGreater(amplitude(left, 880, 3.5, 3.8), 0.1)

    def test_soundtrack_overlapping_fades_use_shared_min_envelope(self):
        state = self.state()
        self.soundtrack(state)
        state["audio"].update(loop=False, fade_in_seconds=1, fade_out_seconds=1)
        left, _ = self.render_audio(state)
        normal = copy.deepcopy(state)
        normal["audio"].update(fade_in_seconds=0, fade_out_seconds=0)
        unfaded, _ = self.render_audio(normal)
        for when in (0.25, 0.5, 0.75):
            ratio = amplitude(left, 220, when - 0.02, when + 0.02) / amplitude(unfaded, 220, when - 0.02, when + 0.02)
            self.assertAlmostEqual(ratio, min(when, 1 - when), delta=0.015)

    def test_spatial_pan_uses_normalized_geometry_and_portrait_centers(self):
        state = self.state()
        segments, _ = self.setup_render(state)
        self.assertAlmostEqual(segments[0].panels[0].audio_pan, -2 / 3)
        self.assertEqual(segments[0].placements[0].width, 34)  # quantized pixels differ from 1/3
        left, right = self.render_audio(state)
        expected = math.cos(math.pi / 12) / math.sin(math.pi / 12)
        self.assertAlmostEqual(rms(left, 0.1, 0.4) / rms(right, 0.1, 0.4), expected, places=5)
        centered_left, centered_right = self.render_audio(state, "portrait")
        self.assertEqual(centered_left, centered_right)
        state["audio"]["spatial_panning"] = False
        disabled_left, disabled_right = self.render_audio(state)
        self.assertEqual(disabled_left, disabled_right)

    def test_stereo_pan_preserves_both_input_channels(self):
        state = self.state()
        state["sources"][0].update(path="stereo.mov", sha256=c.sha256_file(self.root / "stereo.mov"))
        left, right = self.render_audio(state)
        # At pan=-2/3, left output contains original left + cos(pi/6)*right.
        left_right_tone = amplitude(left, 660, 0.1, 0.4)
        right_right_tone = amplitude(right, 660, 0.1, 0.4)
        self.assertAlmostEqual(left_right_tone / right_right_tone, math.sqrt(3), delta=0.002)
        self.assertGreater(amplitude(left, 440, 0.1, 0.4), 0.1)
        self.assertLess(amplitude(right, 440, 0.1, 0.4), 0.0001)

    def test_hold_ramp_release_and_sibling_samples_are_independent(self):
        state = self.state()
        state["events"] = [dict(op="hold", loop="loop-0", frame=20, value=True),
                           dict(op="hold", loop="loop-0", frame=40, value=False)]
        held, _ = self.render_audio(state)
        self.assertLess(rms(held, 0.99, 1), rms(held, 0.90, 0.94) * 0.15)
        self.assertGreater(rms(held, 0.955, 0.965), rms(held, 0.985, 0.995) * 3)
        self.assertEqual(max(abs(value) for value in held[RATE:2 * RATE]), 0)
        self.assertGreater(amplitude(held, 440, 2.1, 2.4), 0.1, "release resumes held source offset 1s")
        state["audio"]["per_loop"]["loop-0"]["gain"] = 0
        state["audio"]["per_loop"]["loop-1"]["gain"] = 1
        sibling = self.render_audio(state)
        state["events"] = []
        self.assertEqual(sibling, self.render_audio(state), "sibling PCM must be byte-identical across holds")

    def test_source_offset_rate_and_trim_wrap_are_audible_at_resolved_clock(self):
        state = self.state()
        state["loops"][0].update(offset="1/4", rate="2", trim=["1", "3"])
        left, _ = self.render_audio(state)
        for when, tone in ((0.1, 440), (0.6, 660), (1.1, 440), (1.6, 660)):
            self.assertGreater(amplitude(left, tone, when, when + 0.15), 0.09)
            other = 660 if tone == 440 else 440
            self.assertLess(amplitude(left, other, when, when + 0.15), 0.006)

    def test_bank_reroll_changes_audio_source_and_initial_hold_and_no_stream_are_silent(self):
        state = self.state()
        state["allow_source_reuse"] = True
        state["loops"][0]["bank"] = ["source-0", "source-1"]
        state["events"] = [dict(op="reroll", loop="loop-0", frame=20)]
        for seed in range(30):
            state["seed"] = seed
            before = c.resolve_at(state, 5)["loops"][0]["source"]
            after = c.resolve_at(state, 25)["loops"][0]["source"]
            if before != after:
                break
        self.assertNotEqual(before, after)
        left, _ = self.render_audio(state)
        for when, source in ((0.2, before), (1.2, after)):
            tone = 880 if source == "source-1" else (220 if when < 1 else 440)
            self.assertGreater(amplitude(left, tone, when, when + 0.2), 0.1)
        state = self.state()
        state["loops"][0]["held"] = True
        self.assertEqual(max(abs(value) for value in self.render_audio(state)[0]), 0)
        state["audio"]["per_loop"]["loop-0"]["gain"] = 0
        state["audio"]["per_loop"]["loop-2"]["gain"] = 1
        self.assertEqual(max(abs(value) for value in self.render_audio(state)[0]), 0)

    def test_final_mux_has_exact_video_clock_and_one_continuous_audio_stream(self):
        state = self.state()
        state["frames"] = 40
        state["events"] = [dict(op="hold", loop="loop-0", frame=10, value=True),
                           dict(op="hold", loop="loop-0", frame=30, value=False)]
        self.soundtrack(state)
        segments, settings = self.setup_render(state)
        r.render(segments, settings)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                          "-of", "json", str(settings.output_file)],
                                         check=True, capture_output=True, text=True).stdout)
        videos = [stream for stream in probe["streams"] if stream["codec_type"] == "video"]
        audios = [stream for stream in probe["streams"] if stream["codec_type"] == "audio"]
        self.assertEqual(len(audios), 1)
        self.assertEqual(int(videos[0]["nb_frames"]), 40)
        self.assertAlmostEqual(float(videos[0]["duration"]), 2, places=5)
        self.assertAlmostEqual(float(audios[0]["duration"]), 2, places=5)
        left, _ = decoded(settings.output_file)
        for boundary in (0.5, 1, 1.5):
            self.assertGreater(rms(left, boundary - 0.01, boundary + 0.01), 0.07)


if __name__ == "__main__":
    unittest.main()
