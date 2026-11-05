"""Run the real ``proxy`` command on synthetic phone-like clips and probe what it writes.

Fixtures are generated with FFmpeg at test time and mimic aggregate facts about
phone clips: QuickTime containers, HEVC (hvc1) and H.264, full-range yuvj420p,
landscape-coded 1440x1080 frames with a display-matrix rotation, variable frame
rate and an audio track. Nothing is mocked.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROGRAM = "independent-loop-compositor"
DEBUG = "SIMVLTANEA_DEBUG"
GREYS = (0, 32, 128, 224, 255)
COLOURS = ((200, 60, 40), (40, 180, 90), (50, 70, 200))
CHANNEL_TOLERANCE = 6
FPS = Fraction(24)

# name: (expected proxy size, source rotation as reported by ffprobe)
CONVERTED = {
    "portrait-hevc.MOV": ((540, 720), -90),
    "landscape-h264.mov": ((720, 540), 0),
    "small-ccw.mp4": ((240, 320), 90),
    "odd-size.avi": ((300, 226), 0),
}
CARD_CLIPS = ("portrait-hevc.MOV", "landscape-h264.mov", "small-ccw.mp4")
TEN_BIT = "ten-bit.mkv"


def ffmpeg(*arguments: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *arguments],
                   check=True, capture_output=True, text=True)


def probe(path: Path) -> dict:
    completed = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                str(path)], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def video_stream(data: dict) -> dict:
    return next(stream for stream in data["streams"] if stream["codec_type"] == "video")


def rotation_of(stream: dict) -> float | None:
    for item in stream.get("side_data_list", []):
        if "rotation" in item:
            return float(item["rotation"])
    return None


def packet_times(path: Path) -> list[float]:
    completed = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "packet=pts_time", "-of", "csv=p=0", str(path)],
                               check=True, capture_output=True, text=True)
    return sorted(float(line.strip(",")) for line in completed.stdout.split() if line.strip(","))


def card_points():
    """Normalized centres of the card's patches and their RGB values."""
    for index, grey in enumerate(GREYS):
        yield ((2 * index + 1) / 10, 0.25), (grey, grey, grey)
    for index, colour in enumerate(COLOURS):
        yield ((2 * index + 1) / 6, 0.75), colour


def make_card(path: Path, width: int, height: int) -> None:
    """Top half: grey bands 0, 32, 128, 224, 255; bottom half: three colour patches."""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for index, grey in enumerate(GREYS):
        draw.rectangle([round(index * width / 5), 0, round((index + 1) * width / 5) - 1, height // 2 - 1],
                       fill=(grey, grey, grey))
    for index, colour in enumerate(COLOURS):
        draw.rectangle([round(index * width / 3), height // 2, round((index + 1) * width / 3) - 1, height - 1],
                       fill=colour)
    image.save(path)


def make_clip(card: Path, output: Path, *, codec: str, matrix: str, tag: str | None, fps: int,
              duration: float, vfr: bool = False, audio: bool = False, rotation: int = 0) -> None:
    """Full-range yuvj420p clip of a still card; ``matrix`` is the RGB->YUV matrix actually used."""
    staging = output.with_name(f"staging-{output.stem}.mov") if rotation else output
    arguments = ["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", str(card)]
    if audio:
        arguments += ["-f", "lavfi", "-t", str(duration), "-i", "sine=frequency=440:sample_rate=48000"]
    chain = (["select='lt(mod(n\\,5)\\,3)'"] if vfr else []) + [
        f"scale=out_range=pc:out_color_matrix={matrix}", "format=yuvj420p"] + (
        [] if tag else ["setparams=colorspace=unknown:color_primaries=unknown:color_trc=unknown"])
    arguments += ["-vf", ",".join(chain)] + (["-fps_mode", "vfr"] if vfr else [])
    if codec == "hevc":
        arguments += ["-c:v", "libx265", "-tag:v", "hvc1", "-x265-params", "log-level=error"]
    else:
        arguments += ["-c:v", "libx264"]
    arguments += ["-preset", "ultrafast", "-pix_fmt", "yuvj420p", "-color_range", "pc"]
    if tag:
        arguments += ["-colorspace", tag, "-color_primaries", tag, "-color_trc", tag]
    arguments += ["-c:a", "aac"] if audio else ["-an"]
    ffmpeg(*arguments, str(staging))
    if rotation:
        # A display matrix is an input-side option in FFmpeg 6+; stream copy keeps the coded frames.
        ffmpeg("-display_rotation:v:0", str(rotation), "-i", str(staging), "-c", "copy", str(output))
        staging.unlink()


def displayed_point(u: float, v: float, rotation: int) -> tuple[float, float]:
    """Where a stored-frame point appears once the display matrix is honoured.

    ffprobe reports -90 for a clockwise display rotation (phone portrait) and 90
    for counter-clockwise.
    """
    turn = rotation % 360
    if turn == 270:
        return 1 - v, u
    if turn == 90:
        return v, 1 - u
    if turn == 180:
        return 1 - u, 1 - v
    return u, v


def first_frame_rgb(video: Path, scratch: Path, untagged_matrix: str | None = None) -> Image.Image:
    """Decode with FFmpeg honouring the stream's range and matrix tags, as a player would.

    FFmpeg reads an untagged matrix as BT.601; ``untagged_matrix`` names the one a fixture really used.
    """
    picture = scratch / f"{video.stem}-{hashlib.sha256(str(video).encode()).hexdigest()[:8]}.png"
    graph = ["-vf", f"scale=in_color_matrix={untagged_matrix},format=rgb24"] if untagged_matrix else []
    ffmpeg("-i", str(video), "-frames:v", "1", *graph, "-pix_fmt", "rgb24", str(picture))
    with Image.open(picture) as image:
        return image.convert("RGB")


def patch_mean(image: Image.Image, u: float, v: float) -> tuple[int, int, int]:
    x, y = int(u * image.width), int(v * image.height)
    pixels = [image.getpixel((x + dx, y + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]
    return tuple(round(sum(pixel[channel] for pixel in pixels) / len(pixels)) for channel in range(3))


def card_errors(image: Image.Image, rotation: int) -> list[str]:
    """Card patches whose decoded RGB is more than CHANNEL_TOLERANCE away from the source RGB."""
    errors = []
    for (u, v), expected in card_points():
        found = patch_mean(image, *displayed_point(u, v, rotation))
        if max(abs(a - b) for a, b in zip(found, expected)) > CHANNEL_TOLERANCE:
            errors.append(f"expected {expected}, decoded {found}")
    return errors


def raw_luma(video: Path, points: list[tuple[float, float]]) -> list[int]:
    """Stored Y samples of the first frame, read without any range conversion."""
    stream = video_stream(probe(video))
    width, height = int(stream["width"]), int(stream["height"])
    completed = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-noautorotate",
                                "-i", str(video),
                                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", stream["pix_fmt"], "-"],
                               check=True, capture_output=True)
    plane = completed.stdout[:width * height]
    return [plane[int(v * height) * width + int(u * width)] for u, v in points]


class ProxyCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing:
            raise RuntimeError(f"{', '.join(missing)} must be on PATH: FFmpeg is a system prerequisite")
        cls._directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._directory.cleanup)
        cls.workspace = Path(cls._directory.name).resolve()
        cls.scratch = cls.workspace / "scratch"
        cls.scratch.mkdir()
        cls.empty_path = cls.workspace / "empty-bin"
        cls.empty_path.mkdir()
        cls.phone = cls.workspace / "phone"
        cls.phone.mkdir()
        large, small = cls.scratch / "card-1440.png", cls.scratch / "card-320.png"
        make_card(large, 1440, 1080)
        make_card(small, 320, 240)
        # Phone portrait: HEVC, coded landscape, -90 display matrix, VFR, audio, no matrix tag.
        make_clip(large, cls.phone / "portrait-hevc.MOV", codec="hevc", matrix="bt709", tag=None, fps=30,
                  duration=1.5, vfr=True, audio=True, rotation=-90)
        # Phone landscape: H.264 full range, BT.601 matrix and tags, constant 30 fps, audio.
        make_clip(large, cls.phone / "landscape-h264.mov", codec="h264", matrix="bt601", tag="smpte170m",
                  fps=30, duration=1.0, audio=True)
        # Smaller than the target, rotated counter-clockwise: must keep its size.
        make_clip(small, cls.phone / "small-ccw.mp4", codec="h264", matrix="bt709", tag="bt709", fps=25,
                  duration=1.0, rotation=90)
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=0.5,scale=301:227,setsar=1,format=yuvj444p",
               "-c:v", "mjpeg", str(cls.phone / "odd-size.avi"))
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x120:r=24:d=0.5", "-c:v", "libx265",
               "-x265-params", "log-level=error", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le",
               str(cls.phone / TEN_BIT))
        (cls.phone / "notes.txt").write_text("not a clip", encoding="utf-8")
        (cls.phone / "._portrait-hevc.MOV").write_bytes(b"AppleDouble sidecar")
        cls.batch = cls.run_command("proxy", str(cls.phone), "--out", "proxies", "--json")
        cls.proxies = cls.workspace / "proxies"

    @classmethod
    def run_command(cls, *arguments, path=None, cwd=None):
        env = {key: value for key, value in os.environ.items() if key != DEBUG}
        env.update(PYTHONPATH=str(SOURCE_ROOT), SIMVLTANEA_ROOT=str(cls.workspace))
        if path is not None:
            env["PATH"] = str(path)
        return subprocess.run([sys.executable, "-m", "independent_loop_compositor", *arguments],
                              cwd=cwd or cls.workspace, env=env, text=True, capture_output=True, timeout=600)

    def assertFriendly(self, result, *fragments):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(result.stderr.startswith(f"{PROGRAM}: error: "), result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)

    def assertPromised(self, video: Path, size: tuple[int, int], source: Path, fps: Fraction = FPS,
                       short_side: int = 540):
        data = probe(video)
        stream = video_stream(data)
        self.assertEqual([item["codec_type"] for item in data["streams"]], ["video"], "audio must be stripped")
        self.assertEqual((stream["codec_name"], stream["profile"], stream["pix_fmt"]), ("h264", "Main", "yuv420p"))
        self.assertEqual((stream["color_range"], stream["color_space"], stream["color_primaries"],
                          stream["color_transfer"]), ("tv", "bt709", "bt709", "bt709"))
        self.assertEqual(stream.get("side_data_list", []), [], "no display matrix may remain")
        self.assertNotIn("rotate", stream.get("tags", {}))
        self.assertEqual((stream["width"], stream["height"]), size)
        self.assertLessEqual(min(size), short_side)
        self.assertEqual(Fraction(stream["avg_frame_rate"]), fps)
        self.assertEqual(Fraction(stream["r_frame_rate"]), fps)
        times = packet_times(video)
        steps = {round(later - earlier, 4) for earlier, later in zip(times, times[1:])}
        self.assertEqual(steps, {round(1 / float(fps), 4)}, "frames must be evenly spaced")
        source_data = probe(source)
        source_duration = float(video_stream(source_data).get("duration") or source_data["format"]["duration"])
        self.assertLessEqual(abs(float(stream["duration"]) - source_duration), 1 / float(fps) + 0.002)
        with video.open("rb") as handle:
            head = handle.read(4096)
        self.assertNotEqual(head.find(b"moov"), -1, "faststart puts moov at the start of the file")
        self.assertTrue(head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat"))

    # -- the fixtures really look like phone clips -----------------------------------

    def test_fixtures_mimic_phone_clips(self):
        portrait = probe(self.phone / "portrait-hevc.MOV")
        stream = video_stream(portrait)
        self.assertEqual((stream["codec_name"], stream["codec_tag_string"]), ("hevc", "hvc1"))
        self.assertEqual((stream["width"], stream["height"]), (1440, 1080))
        self.assertEqual((stream["pix_fmt"], stream["color_range"]), ("yuvj420p", "pc"))
        self.assertNotIn("color_space", stream, "the portrait clip exercises the untagged-matrix default")
        self.assertEqual(rotation_of(stream), -90.0)
        self.assertEqual(stream["side_data_list"][0]["side_data_type"], "Display Matrix")
        self.assertNotEqual(Fraction(stream["avg_frame_rate"]), Fraction(stream["r_frame_rate"]), "VFR")
        times = packet_times(self.phone / "portrait-hevc.MOV")
        self.assertGreater(len({round(later - earlier, 4) for earlier, later in zip(times, times[1:])}), 1,
                           "variable frame intervals")
        self.assertIn("audio", [item["codec_type"] for item in portrait["streams"]])
        landscape = video_stream(probe(self.phone / "landscape-h264.mov"))
        self.assertEqual((landscape["codec_name"], landscape["pix_fmt"], landscape["color_range"],
                          landscape["color_space"]), ("h264", "yuvj420p", "pc", "smpte170m"))
        self.assertIsNone(rotation_of(landscape))
        self.assertEqual(rotation_of(video_stream(probe(self.phone / "small-ccw.mp4"))), 90.0)
        self.assertEqual(video_stream(probe(self.phone / TEN_BIT))["pix_fmt"], "yuv420p10le")
        # Full-range extremes really are stored as Y = 0 and Y = 255.
        bands = [point for point, colour in card_points() if colour[0] == colour[1] == colour[2]]
        for name in CARD_CLIPS:
            with self.subTest(name=name):
                self.assertEqual(raw_luma(self.phone / name, bands), list(GREYS))
                rotation = CONVERTED[name][1]
                matrix = "bt709" if name == "portrait-hevc.MOV" else None
                image = first_frame_rgb(self.phone / name, self.scratch, untagged_matrix=matrix)
                self.assertEqual(card_errors(image, rotation), [],
                                 f"{name} (rotation {rotation}) decodes to the card")

    # -- encoded properties ----------------------------------------------------------

    def test_batch_converts_every_supported_clip_and_refuses_ten_bit(self):
        self.assertEqual(self.batch.returncode, 1, self.batch.stderr)
        self.assertNotIn("Traceback", self.batch.stderr)
        self.assertEqual(sorted(path.name for path in self.proxies.iterdir()),
                         sorted(f"{Path(name).stem}.mp4" for name in CONVERTED))
        lines = self.batch.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, self.batch.stderr)
        self.assertTrue(lines[0].startswith(f"{TEN_BIT}: refused: 10-bit input (yuv420p10le)"), lines[0])
        self.assertIn("out of scope", lines[0])

    def test_every_output_has_the_promised_properties(self):
        for name, (size, _rotation) in CONVERTED.items():
            with self.subTest(name=name):
                self.assertPromised(self.proxies / f"{Path(name).stem}.mp4", size, self.phone / name)

    def test_rotation_is_baked_into_the_displayed_orientation(self):
        # Stored left edge (black band) appears at the top after a clockwise (-90) display rotation,
        # and at the bottom after a counter-clockwise (+90) one.
        portrait = first_frame_rgb(self.proxies / "portrait-hevc.mp4", self.scratch)
        self.assertEqual(portrait.size, (540, 720))
        self.assertLess(max(patch_mean(portrait, 0.75, 0.1)), CHANNEL_TOLERANCE)
        self.assertGreater(min(patch_mean(portrait, 0.75, 0.9)), 255 - CHANNEL_TOLERANCE)
        small = first_frame_rgb(self.proxies / "small-ccw.mp4", self.scratch)
        self.assertEqual(small.size, (240, 320))
        self.assertLess(max(patch_mean(small, 0.25, 0.9)), CHANNEL_TOLERANCE)
        self.assertGreater(min(patch_mean(small, 0.25, 0.1)), 255 - CHANNEL_TOLERANCE)
        for name in ("portrait-hevc.mp4", "small-ccw.mp4"):
            self.assertIsNone(rotation_of(video_stream(probe(self.proxies / name))))

    def test_range_and_matrix_pixel_test(self):
        """Full-range black, white, mid-grey and colours survive the conversion to limited BT.709."""
        for name in CARD_CLIPS:
            rotation = CONVERTED[name][1]
            proxy = self.proxies / f"{Path(name).stem}.mp4"
            with self.subTest(name=name):
                image = first_frame_rgb(proxy, self.scratch)
                self.assertEqual(card_errors(image, rotation), [])
                (black_u, black_v), (white_u, white_v) = (displayed_point(0.1, 0.25, rotation),
                                                          displayed_point(0.9, 0.25, rotation))
                self.assertLessEqual(max(patch_mean(image, black_u, black_v)), 3)
                self.assertGreaterEqual(min(patch_mean(image, white_u, white_v)), 252)
                # Stored samples are limited range: black at 16 and white at 235.
                stored = raw_luma(proxy, [displayed_point(0.1, 0.25, rotation),
                                          displayed_point(0.9, 0.25, rotation)])
                self.assertLessEqual(abs(stored[0] - 16), 2, stored)
                self.assertLessEqual(abs(stored[1] - 235), 2, stored)

    def test_pixel_test_rejects_naive_conversions(self):
        """The same check fails crushed, washed-out and wrong-matrix encodes of the BT.601 clip."""
        source = self.phone / "landscape-h264.mov"
        tags = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709"
        naive = {
            # Full-range samples declared limited: shadows crushed, highlights clipped.
            "crushed": f"format=yuv420p,scale=w=320:h=240:in_range=tv:out_range=tv:in_color_matrix=bt601"
                       f":out_color_matrix=bt709,{tags}:range=tv",
            # Converted to limited but tagged full: washed-out blacks and dull whites.
            "washed": f"scale=w=320:h=240:in_range=pc:out_range=tv:in_color_matrix=bt601"
                      f":out_color_matrix=bt709,format=yuv420p,{tags}:range=pc",
            # Range right, BT.601 input read as BT.709: hues shift.
            "matrix": f"scale=w=320:h=240:in_range=pc:out_range=tv:in_color_matrix=bt709"
                      f":out_color_matrix=bt709,format=yuv420p,{tags}:range=tv",
        }
        for label, graph in naive.items():
            with self.subTest(variant=label):
                output = self.scratch / f"naive-{label}.mp4"
                ffmpeg("-i", str(source), "-vf", graph, "-c:v", "libx264", "-crf", "28", "-an", str(output))
                self.assertNotEqual(card_errors(first_frame_rgb(output, self.scratch), 0), [])

    def test_small_inputs_are_never_upscaled(self):
        for name in ("small-ccw.mp4", "odd-size.avi"):
            with self.subTest(name=name):
                stream = video_stream(probe(self.phone / name))
                output = video_stream(probe(self.proxies / f"{Path(name).stem}.mp4"))
                coded = sorted((stream["width"], stream["height"]))
                self.assertLessEqual(sorted((output["width"], output["height"]))[0], coded[0])
                self.assertLessEqual(sorted((output["width"], output["height"]))[1], coded[1])
        odd = video_stream(probe(self.proxies / "odd-size.mp4"))
        self.assertEqual((odd["width"], odd["height"]), (300, 226), "301x227 rounds down to even")

    def test_custom_settings(self):
        result = self.run_command("proxy", str(self.phone / "landscape-h264.mov"), "--out", "custom",
                                  "--short-side", "360", "--crf", "32", "--fps", "30000/1001", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["clips"][0]
        self.assertEqual((report["settings"]["crf"], report["settings"]["fps"], report["settings"]["short_side"]),
                         (32, "30000/1001", 360))
        self.assertPromised(self.workspace / "custom" / "landscape-h264.mp4", (480, 360),
                            self.phone / "landscape-h264.mov", fps=Fraction(30000, 1001), short_side=360)

    # -- reports -----------------------------------------------------------------------

    def test_json_report_is_complete_and_has_no_absolute_paths(self):
        report = json.loads(self.batch.stdout)
        clips = {clip["input"]: clip for clip in report["clips"]}
        self.assertEqual(set(clips), set(CONVERTED) | {TEN_BIT})
        for name, (size, rotation) in CONVERTED.items():
            clip = clips[name]
            output = self.proxies / clip["output"]
            self.assertEqual((clip["status"], clip["output"]), ("converted", f"{Path(name).stem}.mp4"))
            self.assertEqual(clip["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(clip["output_bytes"], output.stat().st_size)
            self.assertEqual(clip["input_bytes"], (self.phone / name).stat().st_size)
            self.assertEqual((clip["width"], clip["height"]), size)
            self.assertEqual(clip["source"]["rotation"], rotation)
            self.assertLessEqual(abs(clip["duration"] - clip["input_duration"]), 1 / 24 + 0.002)
            self.assertEqual(clip["settings"]["encoder"], "libx264")
        self.assertTrue(clips["portrait-hevc.MOV"]["source"]["variable_frame_rate"])
        self.assertEqual(clips["portrait-hevc.MOV"]["settings"]["in_color_matrix"], "bt709")
        self.assertEqual(clips["landscape-h264.mov"]["settings"]["in_color_matrix"], "smpte170m")
        self.assertEqual(clips["landscape-h264.mov"]["settings"]["in_range"], "pc")
        self.assertEqual(clips[TEN_BIT]["status"], "failed")
        self.assertIsNone(clips[TEN_BIT]["sha256"])
        summary = report["summary"]
        self.assertEqual((summary["converted"], summary["failed"], summary["failures"]),
                         (len(CONVERTED), 1, [TEN_BIT]))
        self.assertNotIn(str(self.workspace), self.batch.stdout)
        self.assertNotIn(str(SOURCE_ROOT), self.batch.stdout)

        def strings(value):
            if isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, str):
                yield value
        for text in strings(report):
            self.assertFalse(os.path.isabs(text), text)

    def test_text_lines_dry_run_writes_nothing(self):
        before = sorted(str(path) for path in self.workspace.rglob("*"))
        result = self.run_command("proxy", str(self.phone), "--out", "planned", "--dry-run")
        self.assertEqual(result.returncode, 1, "the 10-bit clip is still refused in a dry run")
        self.assertEqual(sorted(str(path) for path in self.workspace.rglob("*")), before)
        self.assertFalse((self.workspace / "planned").exists())
        lines = result.stdout.strip().splitlines()
        self.assertTrue(lines[0].startswith(
            "landscape-h264.mov: H264 1440x1080 rot 0 CFR yuvj420p -> 720x540 24fps h264 ("), lines[0])
        self.assertTrue(lines[1].startswith(
            "odd-size.avi: MJPEG 301x227 rot 0 CFR yuvj444p -> 300x226 24fps h264 ("), lines[1])
        self.assertTrue(lines[2].startswith(
            "portrait-hevc.MOV: HEVC 1440x1080 rot -90 VFR yuvj420p -> 540x720 24fps h264 ("), lines[2])
        self.assertTrue(lines[3].startswith(
            "small-ccw.mp4: H264 320x240 rot 90 CFR yuvj420p -> 240x320 24fps h264 ("), lines[3])
        self.assertTrue(all(line.endswith("[dry run]") for line in lines[:4]), lines)
        self.assertEqual(lines[-1].split(";")[0], "5 clip(s), 4 planned, 0 skipped, 1 failed")
        self.assertIn("failed: ten-bit.mkv", lines[-1])
        self.assertEqual(result.stderr.strip().splitlines()[0].split(":")[0], TEN_BIT)

    def test_text_line_reports_output_and_input_sizes(self):
        result = self.run_command("proxy", str(self.phone / "portrait-hevc.MOV"), "--out", "text")
        self.assertEqual(result.returncode, 0, result.stderr)
        first, last = result.stdout.strip().splitlines()
        self.assertRegex(first, r"^portrait-hevc\.MOV: HEVC 1440x1080 rot -90 VFR yuvj420p -> 540x720 24fps h264 "
                                r"\d+(\.\d)? [KM]B \(\d+(\.\d)? [KM]B\)$")
        self.assertRegex(last, r"^1 clip\(s\), 1 converted, 0 skipped, 0 failed; input .+ -> .+$")

    # -- outputs never collide or overwrite --------------------------------------------

    def test_same_stems_get_suffixes_and_existing_outputs_are_kept_unless_forced(self):
        root = self.workspace / "collide"
        for relative in ("a/clip.mov", "a/clip.mp4", "b/clip.MOV"):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.phone / "small-ccw.mp4", root / relative)
        first = self.run_command("proxy", "a", "b", cwd=root)
        self.assertEqual(first.returncode, 0, first.stderr)
        outputs = root / "proxies"  # the default --out
        self.assertEqual(sorted(path.name for path in outputs.iterdir()), ["clip-2.mp4", "clip-3.mp4", "clip.mp4"])
        lines = first.stdout.splitlines()
        self.assertNotIn(" as ", lines[0])
        self.assertIn(" as clip-2.mp4 ", lines[1])
        self.assertIn(" as clip-3.mp4 ", lines[2])
        identity = {path.name: (path.stat().st_ino, path.read_bytes()) for path in outputs.iterdir()}

        again = self.run_command("proxy", "a", "b", cwd=root)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout.count("already exists in --out (use --force to replace it)"), 3)
        self.assertEqual({path.name: (path.stat().st_ino, path.read_bytes()) for path in outputs.iterdir()},
                         identity)

        forced = self.run_command("proxy", "a", "b", "--force", cwd=root)
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertTrue(forced.stdout.splitlines()[-1].startswith("3 clip(s), 3 converted, 0 skipped, 0 failed"))
        for path in outputs.iterdir():
            self.assertNotEqual(path.stat().st_ino, identity[path.name][0], "replaced by a new file")
            self.assertPromised(path, (240, 320), root / "a" / "clip.mov")
        self.assertEqual([path.name for path in outputs.iterdir() if path.name.startswith(".")], [])

    def test_never_writes_next_to_or_over_inputs(self):
        root = self.workspace / "beside"
        root.mkdir()
        shutil.copyfile(self.phone / "small-ccw.mp4", root / "clip.mp4")
        before = sorted(root.iterdir())
        result = self.run_command("proxy", str(root), "--out", str(root))
        self.assertFriendly(result, "contains input clips")
        self.assertEqual(sorted(root.iterdir()), before)
        inside = self.workspace / "inside"
        (inside / "proxies").mkdir(parents=True)
        shutil.copyfile(self.phone / "small-ccw.mp4", inside / "proxies" / "small.mp4")
        self.assertFriendly(self.run_command("proxy", "proxies", cwd=inside), "contains input clips")
        self.assertEqual(sorted(path.name for path in (inside / "proxies").iterdir()), ["small.mp4"])

    # -- friendly failures -------------------------------------------------------------

    def test_cli_errors_are_one_line(self):
        empty = self.workspace / "empty-folder"
        empty.mkdir()
        self.assertFriendly(self.run_command("proxy", str(empty)), "no video files found")
        self.assertFriendly(self.run_command("proxy", "missing-folder"), "input not found: missing-folder")
        self.assertFriendly(self.run_command("proxy", str(self.phone / "notes.txt")), "not a supported video file")
        blocker = self.workspace / "blocker"
        blocker.write_text("a file", encoding="utf-8")
        self.assertFriendly(self.run_command("proxy", str(self.phone / "small-ccw.mp4"), "--out", "blocker"),
                            "--out blocker exists and is not a directory")
        bad = self.run_command("proxy", str(self.phone), "--short-side", "541")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("must be an even number", bad.stderr)
        self.assertNotIn("Traceback", bad.stderr)

    def test_unwritable_out_is_a_one_line_error(self):
        locked = self.workspace / "read-only"
        locked.mkdir()
        locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(locked.chmod, stat.S_IRWXU)
        result = self.run_command("proxy", str(self.phone / "small-ccw.mp4"), "--out", "read-only/proxies")
        self.assertFriendly(result, "--out read-only/proxies is not writable")
        self.assertFalse((locked / "proxies").exists())

    def test_unreadable_clip_fails_alone(self):
        folder = self.workspace / "unreadable"
        folder.mkdir()
        shutil.copyfile(self.phone / "small-ccw.mp4", folder / "a-readable.mp4")
        shutil.copyfile(self.phone / "small-ccw.mp4", folder / "b-locked.mp4")
        (folder / "b-locked.mp4").chmod(0)
        self.addCleanup((folder / "b-locked.mp4").chmod, stat.S_IRUSR | stat.S_IWUSR)
        corrupt = folder / "c-corrupt.mov"
        corrupt.write_bytes(b"\x00" * 64)
        result = self.run_command("proxy", str(folder), "--out", "unreadable-out")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        failures = result.stderr.strip().splitlines()
        self.assertEqual(len(failures), 2, result.stderr)
        self.assertEqual(failures[0], "b-locked.mp4: cannot read file: permission denied")
        self.assertTrue(failures[1].startswith("c-corrupt.mov: not a readable video ("), failures[1])
        self.assertNotIn(str(folder), result.stderr)
        self.assertEqual(sorted(path.name for path in (self.workspace / "unreadable-out").iterdir()),
                         ["a-readable.mp4"])

    def test_missing_ffmpeg_points_at_doctor(self):
        result = self.run_command("proxy", str(self.phone), path=self.empty_path)
        self.assertFriendly(result, "ffmpeg not found on PATH", f"{PROGRAM} doctor")

    def test_top_level_help_lists_proxy(self):
        result = self.run_command("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^\s+proxy\s+\S")
        help_text = self.run_command("proxy", "--help")
        self.assertEqual(help_text.returncode, 0, help_text.stderr)
        for option in ("--out", "--short-side", "--crf", "--fps", "--dry-run", "--force", "--json"):
            self.assertIn(option, help_text.stdout)


if __name__ == "__main__":
    unittest.main()
