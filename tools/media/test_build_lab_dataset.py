"""Build a lab dataset from synthesized clips and tag records: no network, no Photos.app, no real media, no model.

The card clips come from the proxy command's own test fixtures (Pillow plus FFmpeg), so the range-and-matrix pixel
test runs on this builder's output exactly as it does on ``proxy``'s. Without Pillow or FFmpeg those tests skip.
"""
import contextlib
import hashlib
import hmac
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.media import build_lab_dataset as builder
from tools.media.video_geometry import probe_geometry

HAS_PIL = importlib.util.find_spec("PIL") is not None
needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                                   "ffmpeg and ffprobe not installed (system prerequisite)")
needs_fixtures = unittest.skipUnless(HAS_PIL and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                                     "Pillow and FFmpeg are needed to synthesize the card clips")
REAL_WHICH = shutil.which
SIPS_REASON = "sips not found (macOS only): HEIC/JPEG still conversion is not tested on this machine"
needs_sips = unittest.skipUnless(REAL_WHICH("sips") and HAS_PIL, SIPS_REASON)

CREATION = "2019-03-04T05:06:07.000000Z"
COORDINATES = "+12.3456+045.6789"
UUIDS = {
    "speech": "aaaaaaaa-0000-4000-8000-000000000001",     # landscape, BT.601 full range, screened with speech
    "rotated": "bbbbbbbb-0000-4000-8000-000000000002",    # coded landscape, display rotation -90, screened without
    "unrecorded": "cccccccc-0000-4000-8000-000000000003",  # no audio screen record at all
    "unsafe": "dddddddd-0000-4000-8000-000000000004",
    "untagged": "eeeeeeee-0000-4000-8000-000000000005",
    "v1": "ffffffff-0000-4000-8000-000000000006",
    "review": "11111111-0000-4000-8000-000000000007",
}
CLEAR = ("speech", "rotated", "unrecorded")
ROTATIONS = {"speech": 0, "rotated": -90, "unrecorded": 0}

ANALYSIS = {
    "subjects": ["sky", "tree"], "setting": "outdoor", "environment": "nature", "time_of_day": "day",
    "camera": "locked", "motion_level": "subtle", "shot": "wide", "palette": ["blue"], "mood": ["calm"],
    "caption": "SECRET CAPTION", "keywords": ["tree"],
    "people": {"count": "0", "faces_visible": False, "minors_apparent": False},
    "privacy": {"readable_text": False, "license_plate": False, "document_or_screen": False,
                "location_identifiable": False, "sharing_sensitivity": "low", "sharing_note": "SECRET NOTE"},
    "safety": {"verdict": "clear", "categories": [], "reason": "SECRET REASON"},
}


def tag_record(uuid: str, verdict="clear", schema=builder.SCHEMA_ID, analysis=True, needs_review=False) -> dict:
    body = json.loads(json.dumps(ANALYSIS))
    body["safety"]["verdict"] = verdict
    return {"uuid": uuid, "schema": schema, "analysis": body if analysis else None,
            "error": None if analysis else "refusal", "needs_review": needs_review,
            "features": {"luma": 0.5, "luma_spread": 0.1, "saturation": 0.4, "hue": 0.3, "motion": 0.2,
                         "palette": ["blue"], "caption": "SECRET FEATURE"}}


def ffmpeg(*arguments: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *arguments],
                   check=True, capture_output=True)


def ffprobe_json(path: pathlib.Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def keys_of(value):
    """Every dict key anywhere in a JSON value."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys_of(item)


class DatasetCase(unittest.TestCase):
    def run_builder(self, root, dest, *extra, without=()):
        """Run ``main``; tools named in ``without`` look absent (``sips`` always does unless asked for)."""
        hidden = set(without)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(shutil, "which", lambda name, *a, **k: None if name in hidden else REAL_WHICH(name, *a, **k)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["--root", str(root), "--dest", str(dest), *extra])
        return code, out.getvalue(), err.getvalue()


@needs_fixtures
class BuiltDatasetTests(DatasetCase):
    @classmethod
    def setUpClass(cls):
        from independent_loop_compositor import test_proxy as proxy_tests
        cls.proxy_tests = proxy_tests
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        base = pathlib.Path(cls._tmp.name).resolve()
        cls.root, cls.dest = base / "live-photos", base / "lab-data"
        card = base / "card.png"
        proxy_tests.make_card(card, 1440, 1080)
        specs = {
            "speech": dict(codec="h264", matrix="bt601", tag="smpte170m", rotation=0),
            "rotated": dict(codec="h264", matrix="bt709", tag=None, rotation=-90),
            "unrecorded": dict(codec="h264", matrix="bt709", tag="bt709", rotation=0),
            "unsafe": dict(codec="h264", matrix="bt709", tag="bt709", rotation=0),
            "untagged": dict(codec="h264", matrix="bt709", tag="bt709", rotation=0),
            "v1": dict(codec="h264", matrix="bt709", tag="bt709", rotation=0),
            "review": dict(codec="h264", matrix="bt709", tag="bt709", rotation=0),
        }
        tags = cls.root / "analysis" / "tags"
        tags.mkdir(parents=True)
        records = {
            "speech": tag_record(UUIDS["speech"]), "rotated": tag_record(UUIDS["rotated"]),
            "unrecorded": tag_record(UUIDS["unrecorded"]),
            "unsafe": tag_record(UUIDS["unsafe"], verdict="exclude"),
            "untagged": tag_record(UUIDS["untagged"], analysis=False),
            "v1": tag_record(UUIDS["v1"], schema="clip-analysis/v1"),
            "review": tag_record(UUIDS["review"], verdict="review", needs_review=True),
        }
        for name, spec in specs.items():
            uuid = UUIDS[name]
            folder = cls.root / "originals" / uuid
            folder.mkdir(parents=True)
            raw = folder / "raw.mov"
            proxy_tests.make_clip(card, raw, fps=30, duration=1.0, audio=True, **spec)
            ffmpeg("-i", str(raw), "-c", "copy", "-metadata", f"creation_time={CREATION}",
                   "-metadata", f"location={COORDINATES}/", "-metadata", f"location-eng={COORDINATES}/", str(folder / f"{uuid}.mov"))
            raw.unlink()
            (folder / f"{uuid}.heic").write_bytes(b"placeholder still")
            (tags / f"{uuid}.json").write_text(json.dumps(records[name]))
        audio = cls.root / "analysis" / "audio"
        audio.mkdir(parents=True)
        (audio / f"{UUIDS['speech']}.json").write_text(json.dumps(
            {"screened": True, "has_audio": True, "speech": True, "words": 11, "flags": ["possible_name", 3],
             "low_confidence": False}))
        (audio / f"{UUIDS['speech']}.txt").write_text("SECRET TRANSCRIPT")
        (audio / f"{UUIDS['rotated']}.json").write_text(json.dumps(
            {"screened": True, "has_audio": True, "speech": False, "words": 0, "flags": [], "low_confidence": True}))
        cls.code, cls.stdout, cls.stderr = cls.run_builder(cls, cls.root, cls.dest, without=("sips",))
        cls.clips = {c["id"]: c for c in json.loads((cls.dest / "data" / "clips.json").read_text())["clips"]}
        cls.ids = staticmethod(builder.opaque_ids(cls.root))
        cls.by_name = {name: cls.clips.get(cls.ids(UUIDS[name])) for name in UUIDS}

    def test_clear_clips_land_in_clips_json_and_the_others_do_not(self):
        self.assertEqual(self.code, 0, self.stderr)
        for name in CLEAR:  # positive control first: a clear clip IS built, so the absences below mean something
            with self.subTest(clear=name):
                self.assertIsNotNone(self.by_name[name])
        self.assertEqual(len(self.clips), len(CLEAR))
        for name in ("unsafe", "untagged", "v1", "review"):
            with self.subTest(skipped=name):
                self.assertIsNone(self.by_name[name])
                self.assertFalse((self.dest / "media" / f"{self.ids(UUIDS[name])}.mp4").exists())
        self.assertIn(f"lab dataset: {len(CLEAR)} clips, 4 skipped", self.stdout)

    def test_ids_are_opaque_stable_and_match_the_file_names(self):
        for name in CLEAR:
            clip = self.by_name[name]
            self.assertRegex(clip["id"], r"^[0-9a-f]{20}$")
            self.assertEqual(clip["video"], f"media/{clip['id']}.mp4")
            self.assertTrue((self.dest / clip["video"]).is_file())
            self.assertEqual(clip["still"], "")  # no converter in this run; the stills test below covers the rest
        names = sorted(p.relative_to(self.dest).as_posix() for p in self.dest.rglob("*") if p.is_file())
        self.assertEqual(names, sorted([f"media/{i}.mp4" for i in self.clips] + ["data/clips.json"]))
        everything = " ".join(names) + (self.dest / "data" / "clips.json").read_text()
        for uuid in UUIDS.values():
            self.assertNotIn(uuid, everything)
            self.assertNotIn(uuid.split("-")[0], everything)
        expected = hmac.new(bytes.fromhex((self.root / "analysis" / "lab-id-salt").read_text().strip()),
                            UUIDS["speech"].encode(), hashlib.sha256).hexdigest()[:20]
        self.assertEqual(self.by_name["speech"]["id"], expected)
        salt = self.root / "analysis" / "lab-id-salt"
        self.assertEqual(salt.stat().st_mode & 0o777, 0o600)

    def test_a_rerun_keeps_ids_skips_built_clips_and_a_new_salt_changes_ids(self):
        mp4 = self.dest / self.by_name["speech"]["video"]
        before = (mp4.stat().st_mtime_ns, (self.dest / "data" / "clips.json").read_bytes())
        again = self.dest.parent / "again"
        self.assertEqual(self.run_builder(self.root, self.dest, without=("sips",))[0], 0)
        self.assertEqual((mp4.stat().st_mtime_ns, (self.dest / "data" / "clips.json").read_bytes()), before)
        self.assertEqual(self.run_builder(self.root, again, without=("sips",))[0], 0)
        self.assertEqual(sorted(json.loads((again / "data" / "clips.json").read_text())["clips"], key=lambda c: c["id"])[0]["id"],
                         sorted(self.clips)[0])
        with tempfile.TemporaryDirectory() as other:
            self.assertNotEqual(builder.opaque_ids(pathlib.Path(other))(UUIDS["speech"]), self.by_name["speech"]["id"])
        shutil.rmtree(again)

    def test_the_audio_key_is_always_written_in_all_three_states(self):
        self.assertEqual(self.by_name["speech"]["audio"], {"screened": True, "speech": True, "words": 11,
                                                           "flags": ["possible_name"], "low_confidence": False})
        self.assertEqual(self.by_name["rotated"]["audio"], {"screened": True, "speech": False, "words": 0,
                                                            "flags": [], "low_confidence": True})
        self.assertEqual(self.by_name["unrecorded"]["audio"], {"screened": False})
        for clip in self.clips.values():
            self.assertIn("audio", clip)
        self.assertNotIn("SECRET TRANSCRIPT", (self.dest / "data" / "clips.json").read_text())

    def test_captured_at_is_the_container_time_and_no_location_can_appear(self):
        source = ffprobe_json(self.root / "originals" / UUIDS["speech"] / f"{UUIDS['speech']}.mov")
        tags = source["format"]["tags"]
        self.assertIn(COORDINATES, json.dumps(tags))  # positive control: the source really carries a location
        for name in CLEAR:
            self.assertTrue(self.by_name[name]["captured_at"].startswith("2019-03-04T05:06:07"))
        text = (self.dest / "data" / "clips.json").read_text()
        for needle in ("12.3456", "045.6789", "ISO6709"):
            self.assertNotIn(needle, text)
        banned = re.compile(r"gps|latitude|longitude|coordinate|iso6709|location(?!_identifiable)", re.I)
        self.assertEqual([k for k in keys_of(json.loads(text)) if banned.search(str(k))], [])
        built = ffprobe_json(self.dest / self.by_name["speech"]["video"])
        self.assertNotIn(COORDINATES, json.dumps(built))
        self.assertNotIn("creation_time", json.dumps(built))

    def test_no_caption_note_or_reason_is_written(self):
        text = (self.dest / "data" / "clips.json").read_text()
        for needle in ("SECRET CAPTION", "SECRET NOTE", "SECRET REASON", "SECRET FEATURE", "sharing_note", "caption"):
            self.assertNotIn(needle, text)
        clip = self.by_name["speech"]
        self.assertEqual(clip["tags"]["safety"], {"verdict": "clear"})
        self.assertEqual(clip["features"]["luma"], 0.5)
        self.assertEqual(len(clip["features"]["grid8"]), 384)

    def test_display_orientation_comes_from_the_rotation_not_the_coded_size(self):
        source = probe_geometry(self.root / "originals" / UUIDS["rotated"] / f"{UUIDS['rotated']}.mov")
        self.assertEqual((source["coded_width"], source["coded_height"], source["rotation"]), (1440, 1080, -90))
        self.assertEqual(source["orientation"], "portrait")  # positive control: the source is rotated
        rotated, landscape = self.by_name["rotated"], self.by_name["speech"]
        self.assertEqual((rotated["width"], rotated["height"], rotated["orientation"]), (540, 720, "portrait"))
        self.assertEqual((landscape["width"], landscape["height"], landscape["orientation"]), (720, 540, "landscape"))
        built = probe_geometry(self.dest / rotated["video"])
        self.assertEqual((built["rotation"], built["coded_width"], built["coded_height"]), (0, 540, 720))

    def test_the_video_is_limited_range_bt709_cfr_h264_with_mono_aac_audio(self):
        for name in CLEAR:
            data = ffprobe_json(self.dest / self.by_name[name]["video"])
            video = next(s for s in data["streams"] if s["codec_type"] == "video")
            audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
            with self.subTest(name=name):
                self.assertEqual((video["codec_name"], video["pix_fmt"], video["color_range"], video["color_space"]),
                                 ("h264", "yuv420p", "tv", "bt709"))
                self.assertEqual((video["avg_frame_rate"], video["r_frame_rate"]), ("24/1", "24/1"))
                self.assertEqual(min(video["width"], video["height"]), 540)
                self.assertEqual([(s["codec_name"], s["channels"]) for s in audio], [("aac", 1)])
                self.assertTrue(self.by_name[name]["has_audio"])
                self.assertIsInstance(self.by_name[name]["loudness_db"], float)
                self.assertAlmostEqual(self.by_name[name]["duration"], 1.0, delta=0.1)

    def test_range_and_matrix_pixel_test_on_the_builders_output(self):
        tests = self.proxy_tests
        scratch = self.dest.parent / "scratch"
        scratch.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, scratch, True)
        for name in CLEAR:
            rotation, video = ROTATIONS[name], self.dest / self.by_name[name]["video"]
            with self.subTest(name=name):
                self.assertEqual(tests.card_errors(tests.first_frame_rgb(video, scratch), rotation), [])
                stored = tests.raw_luma(video, [tests.displayed_point(0.1, 0.25, rotation),
                                                tests.displayed_point(0.9, 0.25, rotation)])
                self.assertLessEqual(abs(stored[0] - 16), 2, stored)
                self.assertLessEqual(abs(stored[1] - 235), 2, stored)

    def test_the_encode_reuses_the_proxy_recipe_and_only_ffmpeg_61_options(self):
        from independent_loop_compositor import proxy
        commands = []
        real_run = builder.run

        def spy(command):
            commands.append(command)
            return real_run(command)

        source = self.root / "originals" / UUIDS["speech"] / f"{UUIDS['speech']}.mov"
        target = self.dest.parent / "recipe.mp4"
        self.addCleanup(target.unlink, True)
        with mock.patch.object(builder, "run", spy):
            self.assertTrue(builder.transcode(source, target))
        command = commands[0]
        facts = proxy.probe_source(source, proxy.pixel_format_depths())
        graph = proxy.filter_graph(facts, proxy.target_size(facts.displayed_size, 540), builder.FPS)
        self.assertEqual(command[command.index("-vf") + 1], graph)
        self.assertIn("in_color_matrix=smpte170m:out_color_matrix=bt709", graph)
        self.assertIn("in_range=pc:out_range=tv", graph)
        self.assertNotIn("-autorotate", command)
        self.assertNotIn("-noautorotate", command)
        self.assertEqual(command[command.index("-fps_mode") + 1], "cfr")

    def test_stills_skipped_without_sips_say_so_once_and_exit_zero(self):
        self.assertEqual(self.code, 0)
        lines = [line for line in self.stdout.splitlines() if line.startswith("stills skipped")]
        self.assertEqual(lines, [builder.STILLS_SKIPPED])
        self.assertIn("sips not found", lines[0])
        self.assertEqual(list((self.dest / "still").iterdir()), [])

    def test_stale_built_files_are_pruned_and_unrelated_files_are_kept(self):
        stale = self.dest / "media" / ("0" * 20 + ".mp4")
        stale_still = self.dest / "still" / ("0" * 20 + ".jpg")
        keep = self.dest / "media" / "readme.txt"
        for path in (stale, stale_still, keep):
            path.write_bytes(b"x")
        self.addCleanup(keep.unlink, True)
        self.assertEqual(self.run_builder(self.root, self.dest, without=("sips",))[0], 0)
        self.assertFalse(stale.exists() or stale_still.exists())
        self.assertTrue(keep.exists())
        self.assertEqual(len(json.loads((self.dest / "data" / "clips.json").read_text())["clips"]), len(CLEAR))


@needs_sips
class StillConversionTests(DatasetCase):
    def test_a_still_is_converted_to_a_1280_px_jpeg_named_by_the_opaque_id(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp).resolve()
            root, dest, uuid = base / "root", base / "dest", UUIDS["speech"]
            folder = root / "originals" / uuid
            folder.mkdir(parents=True)
            (root / "analysis" / "tags").mkdir(parents=True)
            (root / "analysis" / "tags" / f"{uuid}.json").write_text(json.dumps(tag_record(uuid)))
            ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=1", "-c:v", "libx264",
                   "-pix_fmt", "yuv420p", str(folder / f"{uuid}.mov"))
            Image.new("RGB", (2000, 1500), (10, 120, 200)).save(folder / f"{uuid}.jpg")
            code, out, _ = self.run_builder(root, dest)
            self.assertEqual(code, 0, out)
            clip = json.loads((dest / "data" / "clips.json").read_text())["clips"][0]
            self.assertEqual(clip["still"], f"still/{clip['id']}.jpg")
            with Image.open(dest / clip["still"]) as image:
                self.assertEqual(max(image.size), 1280)
            self.assertNotIn("stills skipped", out)


class EligibilityTests(unittest.TestCase):
    def test_only_v2_error_free_clear_review_free_records_with_sensitivity_qualify(self):
        self.assertIsNotNone(builder.eligible(tag_record(UUIDS["speech"])))
        bad = [tag_record(UUIDS["v1"], schema="clip-analysis/v1"), tag_record(UUIDS["unsafe"], verdict="exclude"),
               tag_record(UUIDS["review"], verdict="review"), tag_record(UUIDS["review"], needs_review=True),
               tag_record(UUIDS["untagged"], analysis=False), {}, [], None, "x"]
        missing = tag_record(UUIDS["speech"])
        del missing["analysis"]["privacy"]["sharing_sensitivity"]
        for record in bad + [missing]:
            self.assertIsNone(builder.eligible(record), record)

    def test_audio_screen_never_leaks_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "analysis" / "audio").mkdir(parents=True)
            (root / "analysis" / "audio" / "u.json").write_text(json.dumps(
                {"screened": True, "speech": True, "words": "4", "transcript": "SECRET", "flags": ["a", 1]}))
            self.assertEqual(builder.audio_screen(root, "u"), {"screened": True, "speech": True, "words": 4,
                                                               "flags": ["a"], "low_confidence": False})
            (root / "analysis" / "audio" / "bad.json").write_text("not json")
            self.assertEqual(builder.audio_screen(root, "bad"), {"screened": False})
            self.assertEqual(builder.audio_screen(root, "absent"), {"screened": False})


class PrerequisiteTests(DatasetCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = pathlib.Path(self._tmp.name).resolve()

    def one_line(self, stderr, fragment):
        self.assertEqual(len(stderr.strip().splitlines()), 1, stderr)
        self.assertIn(fragment, stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_ffmpeg_or_ffprobe_is_one_clear_line_and_nonzero(self):
        for tool in ("ffmpeg", "ffprobe"):
            with self.subTest(tool=tool):
                code, out, err = self.run_builder(self.base / "root", self.base / "dest", without=(tool,))
                self.assertEqual((code, out), (builder.EXIT_MISSING, ""))
                self.one_line(err, f"{tool} not found")
        self.assertFalse((self.base / "dest").exists())

    def test_missing_options_are_one_clear_line_each(self):
        saved = {name: os.environ.pop(name, None) for name in (builder.ROOT_ENV, builder.DEST_ENV)}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) for k, v in saved.items() if v is not None])
        for argv, fragment in (([], "--root"), (["--root", str(self.base)], "--dest")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(argv), builder.EXIT_MISSING)
            self.one_line(err.getvalue(), fragment)
        with mock.patch.dict(os.environ, {builder.ROOT_ENV: "/r", builder.DEST_ENV: "/d"}):
            args = builder.build_parser().parse_args([])
        self.assertEqual((args.root, args.dest), (pathlib.Path("/r"), pathlib.Path("/d")))

    def test_help_needs_nothing_installed(self):
        completed = subprocess.run([sys.executable, "-m", "tools.media.build_lab_dataset", "--help"],
                                   capture_output=True, text=True,
                                   env={"PATH": "/nonexistent", "PYTHONPATH": os.pathsep.join(sys.path)},
                                   cwd=pathlib.Path(__file__).resolve().parents[2])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--dest", completed.stdout)

    def test_root_or_dest_inside_a_photos_library_package_is_refused_in_any_case(self):
        for name in ("Photos Library.photoslibrary", "Pictures.PhotosLibrary"):
            library = self.base / name
            library.mkdir()
            ok = self.base / f"ok-{name}"
            for root, dest in ((library / "x", ok), (ok, library / "x"), (library, ok)):
                with self.subTest(name=name, root=root.name), self.assertRaises(SystemExit) as caught:
                    self.run_builder(root, dest)
                self.assertIn("Photos library", str(caught.exception))
            self.assertEqual(list(library.iterdir()), [])
            self.assertFalse(ok.exists())


if __name__ == "__main__":
    unittest.main()
