"""Displayed geometry from ffprobe facts: mocked JSON samples, real rotated clips, parity with proxy.py.

Tests that need FFmpeg skip cleanly when ``ffmpeg``/``ffprobe`` are absent. No Pillow, no network.
"""
import importlib
import json
import math
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.media import video_geometry as vg

needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                                   "ffmpeg/ffprobe not installed (system prerequisite)")

ROTATIONS = (0, 90, -90, 180, 270)
# What the display of a 64x48 landscape-coded clip looks like for each ffprobe rotation.
EXPECTED = {0: (64, 48, "landscape"), 90: (48, 64, "portrait"), -90: (48, 64, "portrait"),
            180: (64, 48, "landscape"), 270: (48, 64, "portrait")}


def stream(width=64, height=48, **extra) -> dict:
    return {"codec_type": "video", "width": width, "height": height, **extra}


def with_side_rotation(value, **kwargs) -> dict:
    return stream(side_data_list=[{"side_data_type": "Display Matrix", "rotation": value}], **kwargs)


def make_rotated_clip(folder: pathlib.Path, rotation: int) -> pathlib.Path:
    """64x48 coded clip with a display matrix; the same two-step form proxy's tests use (FFmpeg 6.1 and later)."""
    staging, output = folder / f"staging-{rotation}.mov", folder / f"clip{rotation}.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(staging)], check=True)
    command = ["ffmpeg", "-v", "error", "-y"]
    if rotation:
        command += ["-display_rotation:v:0", str(rotation)]
    subprocess.run([*command, "-i", str(staging), "-c", "copy", str(output)], check=True)
    return output


class RotationParsingTests(unittest.TestCase):
    def test_side_data_rotation_is_read_with_its_sign(self):
        for value in (0, 90, -90, 180, -180, 270):
            self.assertEqual(vg.stream_rotation(with_side_rotation(value)), value)
        self.assertEqual(vg.stream_rotation(with_side_rotation("-90.000000")), -90)
        self.assertEqual(vg.stream_rotation(with_side_rotation(-90.0)), -90)

    def test_side_data_wins_over_the_legacy_tag_and_is_found_among_other_items(self):
        mixed = stream(side_data_list=[{"side_data_type": "Other"}, {"rotation": -90}], tags={"rotate": "180"})
        self.assertEqual(vg.stream_rotation(mixed), -90)

    def test_legacy_rotate_tag_counts_the_other_way_round(self):
        self.assertEqual(vg.stream_rotation(stream(tags={"rotate": "90"})), -90)
        self.assertEqual(vg.stream_rotation(stream(tags={"rotate": "270"})), -270)
        self.assertEqual(vg.stream_rotation(stream(tags={"rotate": "0"})), 0)

    def test_missing_malformed_non_finite_and_oblique_rotations_mean_zero(self):
        samples = {
            "no rotation anywhere": stream(),
            "empty side data": stream(side_data_list=[]),
            "side data without rotation": stream(side_data_list=[{"side_data_type": "Mastering display metadata"}]),
            "null side data": stream(side_data_list=None),
            "side data not a list": stream(side_data_list="x"),
            "side data item not a dict": stream(side_data_list=["rotation"]),
            "empty rotate tag": stream(tags={"rotate": ""}),
            "malformed rotate tag": stream(tags={"rotate": "ninety"}),
            "tags not a dict": stream(tags=["rotate"]),
            "non-numeric side data": with_side_rotation("sideways"),
            "null side data rotation": with_side_rotation(None),
            "boolean side data rotation": with_side_rotation(True),
            "nan": with_side_rotation(float("nan")),
            "infinity": with_side_rotation(float("inf")),
            "nan tag": stream(tags={"rotate": "nan"}),
            "inf tag": stream(tags={"rotate": "inf"}),
            "45 degrees": with_side_rotation(45),
            "45 degree tag": stream(tags={"rotate": "45"}),
            "89.5 degrees": with_side_rotation(89.5),
        }
        for name, sample in samples.items():
            with self.subTest(name):
                self.assertEqual(vg.stream_rotation(sample), 0)
        self.assertEqual(vg.stream_rotation(None), 0)

    def test_a_malformed_side_data_rotation_does_not_fall_back_to_the_tag(self):
        self.assertEqual(vg.stream_rotation(with_side_rotation("sideways", tags={"rotate": "90"})), 0)


class DisplayGeometryTests(unittest.TestCase):
    def test_quarter_turns_swap_width_and_height(self):
        for rotation, swapped in {0: False, 90: True, -90: True, 180: False, -180: False, 270: True, -270: True}.items():
            self.assertEqual(vg.display_size(64, 48, rotation), (48, 64) if swapped else (64, 48), rotation)

    def test_orientation_rule_keeps_a_square_clip_landscape(self):
        self.assertEqual(vg.orientation_for(48, 64), "portrait")
        self.assertEqual(vg.orientation_for(64, 48), "landscape")
        self.assertEqual(vg.orientation_for(64, 64), "landscape")
        self.assertEqual(vg.orientation_for(None, None), "landscape")
        self.assertEqual(vg.ORIENTATIONS, ("portrait", "landscape"))

    def test_geometry_from_a_rotated_phone_stream_is_portrait_while_the_coded_size_stays(self):
        geometry = vg.geometry_from_stream(with_side_rotation(-90, width=1920, height=1080))
        self.assertEqual(geometry, {"rotation": -90, "coded_width": 1920, "coded_height": 1080,
                                    "display_width": 1080, "display_height": 1920, "orientation": "portrait"})

    def test_geometry_without_rotation_or_with_an_oblique_one_is_the_coded_size(self):
        for sample in (stream(1920, 1080), with_side_rotation(45, width=1920, height=1080)):
            geometry = vg.geometry_from_stream(sample)
            self.assertEqual((geometry["rotation"], geometry["display_width"], geometry["display_height"],
                              geometry["orientation"]), (0, 1920, 1080, "landscape"))

    def test_a_stream_without_a_usable_size_has_no_geometry(self):
        for sample in ({}, None, stream(0, 48), stream(64, None), stream("wide", 48), stream(True, 48)):
            self.assertIsNone(vg.geometry_from_stream(sample))

    def test_first_stream_tolerates_odd_probe_output(self):
        for data in (None, {}, {"streams": []}, {"streams": None}, {"streams": ["x"]}):
            self.assertEqual(vg.first_stream(data), {})
        self.assertEqual(vg.first_stream({"streams": [{"a": 1}, {"b": 2}]}), {"a": 1})


class RunFfprobeTests(unittest.TestCase):
    def completed(self, code=0, out="{}"):
        return subprocess.CompletedProcess([], code, out, "")

    def test_it_asks_for_whole_streams_not_side_data_entries(self):
        with mock.patch.object(subprocess, "run", return_value=self.completed(out='{"streams": []}')) as run:
            self.assertEqual(vg.run_ffprobe(pathlib.Path("x.mov")), {"streams": []})
        command = run.call_args.args[0]
        self.assertEqual(command[:-1], ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                                        "-show_format", "-of", "json"])
        self.assertNotIn("-show_entries", command)

    def test_unreadable_results_are_none(self):
        for outcome in (self.completed(1), self.completed(out="not json"), self.completed(out="[1]")):
            with mock.patch.object(subprocess, "run", return_value=outcome):
                self.assertIsNone(vg.run_ffprobe(pathlib.Path("x.mov")))
        for error in (FileNotFoundError("ffprobe"), subprocess.TimeoutExpired("ffprobe", 1)):
            with mock.patch.object(subprocess, "run", side_effect=error):
                self.assertIsNone(vg.run_ffprobe(pathlib.Path("x.mov")))

    def test_probe_geometry_reads_the_mocked_json(self):
        facts = {"streams": [with_side_rotation(-90, width=1920, height=1080)], "format": {"duration": "1"}}
        with mock.patch.object(subprocess, "run", return_value=self.completed(out=json.dumps(facts))):
            self.assertEqual(vg.probe_geometry(pathlib.Path("x.mov"))["orientation"], "portrait")
        with mock.patch.object(subprocess, "run", return_value=self.completed(1)):
            self.assertIsNone(vg.probe_geometry(pathlib.Path("x.mov")))


class ProxyParityTests(unittest.TestCase):
    """This module duplicates proxy.stream_rotation on purpose (tools/media stays usable with Pillow only)."""

    def test_both_parsers_agree_on_valid_ffprobe_samples(self):
        try:
            proxy = importlib.import_module("independent_loop_compositor.proxy")
        except ImportError as exc:  # pragma: no cover - the src tree is on the path in every supported run
            self.fail(f"proxy module not importable: {exc}")
        samples = [stream(), with_side_rotation(0), with_side_rotation(-90), with_side_rotation(90),
                   with_side_rotation(180), with_side_rotation(-180), with_side_rotation(270),
                   with_side_rotation("-90.000000"), stream(tags={"rotate": "90"}), stream(tags={"rotate": "270"}),
                   stream(tags={"rotate": "180"}), stream(tags={"rotate": "0"}), stream(tags={"rotate": ""}),
                   stream(side_data_list=[], tags={"rotate": "90"}),
                   with_side_rotation(-90, tags={"rotate": "180"}),
                   stream(side_data_list=[{"side_data_type": "Other"}, {"rotation": 90}])]
        for sample in samples:
            with self.subTest(sample=json.dumps(sample, sort_keys=True)):
                theirs = proxy.stream_rotation(sample)
                self.assertTrue(math.isfinite(theirs))
                self.assertEqual(vg.stream_rotation(sample), theirs)

    def test_both_parsers_give_the_same_displayed_orientation(self):
        proxy = importlib.import_module("independent_loop_compositor.proxy")
        for rotation in (0, 90, -90, 180, 270):
            sample = with_side_rotation(rotation, width=1920, height=1080)
            theirs = proxy.stream_rotation(sample)
            width, height = (1080, 1920) if abs(theirs) % 180 == 90 else (1920, 1080)
            ours = vg.geometry_from_stream(sample)
            self.assertEqual((ours["display_width"], ours["display_height"]), (width, height))


@needs_ffmpeg
class RealRotatedClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.clips = {rotation: make_rotated_clip(pathlib.Path(cls._tmp.name), rotation) for rotation in ROTATIONS}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_rotation_reports_its_displayed_size_and_orientation(self):
        for rotation, clip in self.clips.items():
            with self.subTest(rotation=rotation):
                geometry = vg.probe_geometry(clip)
                width, height, orientation = EXPECTED[rotation]
                self.assertEqual((geometry["coded_width"], geometry["coded_height"]), (64, 48))
                self.assertEqual((geometry["display_width"], geometry["display_height"]), (width, height))
                self.assertEqual(geometry["orientation"], orientation)
                self.assertEqual(geometry["rotation"] % 360, rotation % 360)

    def test_the_stream_parser_and_the_real_ffprobe_json_agree_with_proxy(self):
        proxy = importlib.import_module("independent_loop_compositor.proxy")
        for rotation, clip in self.clips.items():
            with self.subTest(rotation=rotation):
                found = vg.first_stream(vg.run_ffprobe(clip))
                self.assertEqual(vg.stream_rotation(found), proxy.stream_rotation(found))


if __name__ == "__main__":
    unittest.main()
