"""Rate-changed loops show the intended source frame (issue #65), checked by decoding every output frame.

The source is a lossless ramp whose luma is twice the frame number, so a decoded frame names its source frame.
A rate r loop must show source frame start + floor(k * r) at output frame k. A positive control shows the
comparison notices the one-frame lead the old nearest-rounding chain produced.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import simvltanea.rendering.render_triptych as r

FPS = 30
START_FRAME = 15
OUTPUT_FRAMES = 24
RATES = (0.5, 0.75, 1.25, 1.5, 2.0, 3.0)


def make_ramp(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"color=c=black:s=64x64:r={FPS}:d=4,geq=lum='N*2':cb=128:cr=128",
         "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", "-g", "1", str(path)],
        check=True)


def decode_source_frames(ramp: Path, video_filter: str) -> list[int]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(ramp), "-filter_complex", video_filter, "-map", "[v]",
         # Inspect every filter output frame. FFmpeg 7 otherwise chooses a
         # 25-fps rawvideo output and drops frames from this 30-fps fixture.
         "-fps_mode", "passthrough", "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    size = 64 * 64
    frame_bytes = size * 3 // 2
    frames = []
    for index in range(len(raw) // frame_bytes):
        luma = sum(raw[index * frame_bytes:index * frame_bytes + size]) / size
        frames.append(round(luma / 2))
    return frames


def panel_filter(rate: float, duration: float) -> str:
    settings = SimpleNamespace(fps=FPS, tone_mode="none", media_fit="cover", focal=(0.5, 0.5), height=64,
                               video_direction="forward")
    panel = r.Panel(name="left", source_index=0, source_path=None, source_offset=START_FRAME / FPS,
                    source_duration=4.0, source_has_audio=False, playback_rate=rate, clocked=True)
    segment = r.Segment(index=0, start=0.0, duration=duration, panels=(panel,))
    return ";".join(r.video_source_filters(0, panel, segment, settings, 64, "[v]"))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
class RateFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.ramp = Path(cls.scratch.name) / "ramp.mp4"
        make_ramp(cls.ramp)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_every_output_frame_shows_the_floor_source_frame(self):
        duration = OUTPUT_FRAMES / FPS
        for rate in RATES:
            with self.subTest(rate=rate):
                expected = [START_FRAME + math.floor(k * rate + 1e-6) for k in range(OUTPUT_FRAMES)]
                seen = decode_source_frames(self.ramp, panel_filter(rate, duration))
                self.assertEqual(seen, expected)

    def test_rate_one_stays_frame_exact(self):
        duration = OUTPUT_FRAMES / FPS
        seen = decode_source_frames(self.ramp, panel_filter(1.0, duration))
        self.assertEqual(seen, [START_FRAME + k for k in range(OUTPUT_FRAMES)])

    def test_positive_control_old_nearest_rounding_leads_by_a_frame(self):
        rate, duration = 1.5, OUTPUT_FRAMES / FPS
        old = (f"[0:v]trim=start={r.seconds(START_FRAME / FPS)},setpts=PTS-STARTPTS,setpts=PTS/{r.seconds(rate)},"
               f"fps={FPS},tpad=stop_mode=clone:stop_duration={r.seconds(duration)},trim=duration={r.seconds(duration)},"
               "setpts=PTS-STARTPTS,format=yuv420p[v]")
        expected = [START_FRAME + math.floor(k * rate + 1e-6) for k in range(OUTPUT_FRAMES)]
        seen = decode_source_frames(self.ramp, old)
        self.assertNotEqual(seen, expected)
        self.assertTrue(any(a - b == 1 for a, b in zip(seen, expected)))
        self.assertTrue(all(a >= b for a, b in zip(seen, expected)))


if __name__ == "__main__":
    unittest.main()
