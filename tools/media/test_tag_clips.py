"""Exercise the clip tagger with generated frames and a stub Batch API: no network, no real key.

Tests that need the optional ``analysis`` extra (anthropic, Pillow) are skipped with a message only
when that package is genuinely absent.
"""
import contextlib
import hashlib
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
from types import SimpleNamespace
from unittest import mock

from tools.media import tag_clips, video_geometry
from tools.paths import REPO_ROOT

HAS_SDK = importlib.util.find_spec("anthropic") is not None and importlib.util.find_spec("pydantic") is not None
HAS_PIL = importlib.util.find_spec("PIL") is not None
needs_sdk = unittest.skipUnless(HAS_SDK, "anthropic SDK not installed (python3 -m pip install -e '.[analysis]')")
needs_pillow = unittest.skipUnless(HAS_PIL, "Pillow not installed (python3 -m pip install -e '.[analysis]')")
needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed (system prerequisite)")

REAL_RUN = subprocess.run  # the private-root guard runs the real git even while ffmpeg is faked
REAL_WHICH = shutil.which

FAKE_KEY = "sk-ant-test-0123456789-not-a-real-key"
UUID_A = "aaaaaaaa-0000-4000-8000-000000000001"
UUID_B = "bbbbbbbb-0000-4000-8000-000000000002"
UUID_C = "cccccccc-0000-4000-8000-000000000003"
UUID_D = "dddddddd-0000-4000-8000-000000000004"

GOOD_ANALYSIS = {
    "subjects": ["sky", "sky", "tree"], "setting": "outdoor", "environment": "nature", "time_of_day": "day",
    "camera": "locked", "motion_level": "subtle", "shot": "wide", "palette": ["blue", "green"], "mood": ["calm"],
    "caption": "A tree against a clear sky.", "keywords": ["tree", "sky"],
    "people": {"count": "0", "faces_visible": False, "minors_apparent": False},
    "privacy": {"readable_text": False, "license_plate": False, "document_or_screen": False,
                "location_identifiable": False, "sharing_sensitivity": "low", "sharing_note": ""},
    "safety": {"verdict": "clear", "categories": [], "reason": ""},
}


def save_frame(path: pathlib.Path, color, size=(96, 64)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG", quality=95)


def make_receipt(width=1080, height=1920, duration=1.8, rotation=0) -> dict:
    """A receipt as the exporter writes it today: coded size plus rotation. ``rotation=None`` gives the
    legacy shape (written before issue #60) that has no ``rotation`` key at all."""
    video = {"name": "clip.mov", "duration": duration, "width": width, "height": height}
    if rotation is not None:
        video.update(rotation=rotation, **dict(zip(("display_width", "display_height"),
                                                   (height, width) if abs(rotation) % 180 == 90 else (width, height))))
    return {"video": video}


def succeeded(uuid: str, text: str, stop_reason="end_turn", input_tokens=1000, output_tokens=300):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    message = SimpleNamespace(stop_reason=stop_reason, usage=usage, content=[SimpleNamespace(type="text", text=text)])
    return SimpleNamespace(custom_id=uuid, result=SimpleNamespace(type="succeeded", message=message))


def errored(uuid: str, kind="errored"):
    return SimpleNamespace(custom_id=uuid, result=SimpleNamespace(type=kind))


class StubBatches:
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.created: list[list] = []
        self.create_options: list[dict] = []  # client options in force for each create() call
        self.scope: dict = {}
        self.polls = 0

    def create(self, requests):
        self.created.append(list(requests))
        self.create_options.append(dict(self.scope))
        return SimpleNamespace(id=f"msgbatch_test{len(self.created)}")

    def retrieve(self, batch_id):
        self.polls += 1
        status = "in_progress" if self.polls == 1 else "ended"
        return SimpleNamespace(processing_status=status, request_counts="counts")

    def results(self, batch_id):
        return iter(self.entries)


class ScopedBatches:
    """What ``client.with_options(...).messages.batches`` looks like: the same batches, other options."""

    def __init__(self, batches: StubBatches, options: dict):
        self.batches, self.options = batches, options

    def create(self, requests):
        self.batches.scope = self.options
        try:
            return self.batches.create(requests)
        finally:
            self.batches.scope = {}

    def __getattr__(self, name):
        return getattr(self.batches, name)


class StubClient:
    def __init__(self, entries=()):
        self.messages = SimpleNamespace(batches=StubBatches(entries))

    def with_options(self, **options):
        view = StubClient.__new__(StubClient)
        view.messages = SimpleNamespace(batches=ScopedBatches(self.messages.batches, options))
        return view


class TaggerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name).resolve() / "live-photos"

    def add_clip(self, uuid: str, **receipt_kwargs):
        folder = self.root / "originals" / uuid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".done").write_text(json.dumps(make_receipt(**receipt_kwargs)))

    def add_frames(self, uuid: str, colors=((200, 30, 30), (30, 200, 30), (30, 30, 200))):
        for index, color in enumerate(colors):
            save_frame(self.root / "analysis" / "frames" / uuid / f"f{index}.jpg", color)

    def add_features(self, uuid: str):
        path = self.root / "analysis" / "features"
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{uuid}.json").write_text(json.dumps({"luma": 0.5}))

    def write_batch(self, batch_id="msgbatch_test1", uuids=(UUID_A,), model="claude-haiku-5-5"):
        path = self.root / "analysis" / "batches"
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{batch_id}.json").write_text(json.dumps({"batch": batch_id, "model": model, "uuids": list(uuids)}))

    def run_main(self, *argv, client=None):
        out, err = io.StringIO(), io.StringIO()
        patches = [contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)]
        if client is not None:
            patches.append(mock.patch.object(tag_clips, "make_client", return_value=client))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            code = tag_clips.main([*argv, "--root", str(self.root)])
        self.output = out.getvalue() + err.getvalue()
        return code

    def tag(self, uuid: str) -> dict:
        return json.loads((self.root / "analysis" / "tags" / f"{uuid}.json").read_text())


class ImportWithoutSdkTests(unittest.TestCase):
    def test_module_imports_and_vocabularies_work_when_the_sdk_is_absent(self):
        code = (
            "import sys\n"
            "for name in ('anthropic', 'pydantic', 'PIL'):\n"
            "    sys.modules[name] = None\n"
            "from tools.media import tag_clips as t\n"
            "assert 'sky' in t.SUBJECTS and 'exclude' in t.VERDICTS and t.PRICES\n"
            "assert t.estimate('claude-haiku-5-5', 10, 640) > 0\n"
            "t.build_parser().parse_args(['report', '--root', '/tmp/x'])\n"
            "try:\n"
            "    t.make_client()\n"
            "except SystemExit as exc:\n"
            "    assert '.[analysis]' in str(exc.code), exc.code\n"
            "else:\n"
            "    raise AssertionError('make_client must fail clearly without the SDK')\n"
            "print('ok')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "ok"), proc.stderr)

    def test_vocabularies_are_unique_and_fixed(self):
        for name in ("SUBJECTS", "COLORS", "MOODS", "SAFETY_CATEGORIES", "SETTINGS", "ENVIRONMENTS", "TIMES_OF_DAY",
                     "CAMERAS", "MOTION_LEVELS", "SHOTS", "VERDICTS"):
            values = getattr(tag_clips, name)
            self.assertEqual(len(values), len(set(values)), name)
        self.assertEqual(tag_clips.VERDICTS, ("clear", "review", "exclude"))
        self.assertEqual(len(tag_clips.SUBJECTS), 39)

    def test_prompt_forbids_identification(self):
        self.assertIn("Never identify, name, or guess who anyone is", tag_clips.PROMPT)

    def test_estimate_scales_linearly_with_clip_count_and_model_price(self):
        one = tag_clips.estimate("claude-haiku-5-5", 1, 640)
        self.assertAlmostEqual(tag_clips.estimate("claude-haiku-5-5", 100, 640), 100 * one)
        self.assertGreater(tag_clips.estimate("claude-opus-5-5", 1, 640), one)


@needs_sdk
class SchemaTests(unittest.TestCase):
    def test_schema_survives_transform_schema_with_strict_objects_and_all_fields_required(self):
        import anthropic

        model = tag_clips.clip_analysis_model()
        schema = anthropic.transform_schema(model)
        self.assertEqual(schema["type"], "object")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(sorted(schema["required"]), sorted(schema["properties"]))
        self.assertEqual(set(schema["properties"]), {
            "subjects", "setting", "environment", "time_of_day", "camera", "motion_level", "shot", "palette",
            "mood", "caption", "keywords", "people", "privacy", "safety"})
        self.assertEqual(schema["properties"]["subjects"]["items"]["enum"], list(tag_clips.SUBJECTS))
        self.assertEqual(schema["properties"]["safety"]["$ref"].split("/")[-1], "Safety")
        self.assertEqual(schema["$defs"]["Safety"]["properties"]["verdict"]["enum"], list(tag_clips.VERDICTS))
        for definition in schema["$defs"].values():
            self.assertIs(definition["additionalProperties"], False)
        json.dumps(schema)

    def test_model_is_built_once_and_validates_only_controlled_values(self):
        model = tag_clips.clip_analysis_model()
        self.assertIs(model, tag_clips.clip_analysis_model())
        parsed = model.model_validate_json(json.dumps(GOOD_ANALYSIS))
        self.assertEqual(parsed.safety.verdict, "clear")
        bad = {**GOOD_ANALYSIS, "subjects": ["unicorn"]}
        with self.assertRaises(ValueError):
            model.model_validate_json(json.dumps(bad))
        bad_verdict = {**GOOD_ANALYSIS, "safety": {"verdict": "maybe", "categories": [], "reason": ""}}
        with self.assertRaises(ValueError):
            model.model_validate_json(json.dumps(bad_verdict))


@needs_pillow
class LocalFeatureTests(TaggerTestCase):
    def features(self, colors, **receipt_kwargs):
        frames = []
        for index, color in enumerate(colors):
            path = self.root / f"f{index}.jpg"
            save_frame(path, color)
            frames.append(path)
        return tag_clips.local_features(frames, make_receipt(**receipt_kwargs))

    def test_values_stay_in_documented_ranges(self):
        for colors in (((0, 0, 0),) * 3, ((255, 255, 255),) * 3, ((255, 0, 0), (0, 255, 0), (0, 0, 255)),
                       ((10, 200, 90), (250, 250, 20), (90, 10, 140))):
            features = self.features(colors)
            for name in ("luma", "luma_spread", "saturation", "hue", "motion"):
                self.assertGreaterEqual(features[name], 0.0, name)
                self.assertLessEqual(features[name], 1.0, name)
            self.assertLessEqual(len(features["palette"]), 5)
            self.assertLessEqual(sum(entry["share"] for entry in features["palette"]), 1.001)
            for entry in features["palette"]:
                self.assertRegex(entry["hex"], r"^#[0-9a-f]{6}$")

    def test_same_frames_give_identical_features(self):
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        self.assertEqual(self.features(colors), self.features(colors))

    def test_features_track_what_the_frames_contain(self):
        black = self.features(((0, 0, 0),) * 3)
        self.assertEqual((black["luma"], black["motion"], black["saturation"], black["luma_spread"]), (0, 0, 0, 0))
        flashing = self.features(((0, 0, 0), (255, 255, 255), (0, 0, 0)))
        self.assertAlmostEqual(flashing["motion"], 1.0, places=2)
        self.assertGreater(flashing["luma_spread"], 0.9)
        gray = self.features(((128, 128, 128),) * 3)
        red = self.features(((255, 0, 0),) * 3)
        self.assertEqual(gray["saturation"], 0)
        self.assertGreater(red["saturation"], 0.9)
        self.assertLessEqual(min(red["hue"], 1 - red["hue"]), 0.05)  # red sits at the hue wrap-around

    def test_orientation_and_video_facts_come_from_the_receipt(self):
        colors = ((10, 10, 10),) * 3
        portrait = self.features(colors, width=1080, height=1920, duration=2.5)
        landscape = self.features(colors, width=1920, height=1080)
        self.assertEqual((portrait["orientation"], portrait["width"], portrait["height"], portrait["duration"]),
                         ("portrait", 1080, 1920, 2.5))
        self.assertEqual(landscape["orientation"], "landscape")

    def test_features_are_json_serialisable(self):
        json.dumps(self.features(((1, 2, 3), (4, 5, 6), (7, 8, 9))))


@needs_pillow
@needs_ffmpeg
class RealFrameExtractionTests(TaggerTestCase):
    def test_extract_writes_three_downscaled_frames_from_a_generated_clip(self):
        folder = self.root / "originals" / UUID_A
        folder.mkdir(parents=True)
        clip = folder / "clip.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=1",
                        "-pix_fmt", "yuv420p", str(clip)], check=True)
        (folder / ".done").write_text(json.dumps(make_receipt(width=320, height=180, duration=1.0)))
        frames = tag_clips.extract(self.root, UUID_A, 128)
        self.assertEqual([f.name for f in frames], ["f0.jpg", "f1.jpg", "f2.jpg"])
        from PIL import Image

        for frame in frames:
            with Image.open(frame) as image:
                self.assertEqual(image.size[0], 128)
                self.assertLessEqual(image.size[1], 128)
        features = tag_clips.local_features(frames, make_receipt(width=320, height=180, duration=1.0))
        self.assertEqual(features["orientation"], "landscape")


@needs_sdk
@needs_pillow
def make_fixture_clips(folder: pathlib.Path) -> dict[str, pathlib.Path]:
    """Synthetic clips: ``short`` is 3 video frames (0.4 s at 7.5 fps, 1440x1080) next to a 0.66 s audio
    track, so the container is longer than the video, exactly like the reported Live Photo."""
    folder.mkdir(parents=True, exist_ok=True)
    common = ["ffmpeg", "-v", "error", "-y"]
    encode = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    clips = {name: folder / f"{name}.mov" for name in ("short", "single", "normal", "garbage")}
    subprocess.run([*common, "-f", "lavfi", "-i", "testsrc=size=1440x1080:rate=7.5:duration=0.4",
                    "-f", "lavfi", "-i", "sine=duration=0.66", *encode, "-c:a", "aac", str(clips["short"])], check=True)
    subprocess.run([*common, "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-frames:v", "1", *encode,
                    str(clips["single"])], check=True)
    subprocess.run([*common, "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=duration=2", *encode, "-c:a", "aac", str(clips["normal"])], check=True)
    clips["garbage"].write_bytes(bytes((i * 37 + 11) % 256 for i in range(4096)))
    return clips


@needs_pillow
@needs_ffmpeg
class ShortAndBrokenClipTests(TaggerTestCase):
    """One odd clip must never stop the others from being tagged."""

    @classmethod
    def setUpClass(cls):
        cls._fixture_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._fixture_tmp.cleanup)
        cls.fixtures = make_fixture_clips(pathlib.Path(cls._fixture_tmp.name))

    def put_clip(self, uuid: str, kind: str, **receipt_kwargs) -> None:
        self.add_clip(uuid, **receipt_kwargs)
        shutil.copy(self.fixtures[kind], self.root / "originals" / uuid / "clip.mov")

    def assert_three_real_jpegs(self, frames):
        from PIL import Image

        self.assertEqual([f.name for f in frames], ["f0.jpg", "f1.jpg", "f2.jpg"])
        for frame in frames:
            self.assertGreater(frame.stat().st_size, 0)
            with Image.open(frame) as image:
                image.load()
                self.assertEqual(image.format, "JPEG")

    def failed_marker(self, uuid: str) -> dict:
        return json.loads((self.root / "analysis" / "failed" / f"{uuid}.json").read_text())

    def assert_no_private_text(self, text: str) -> None:
        for private in (self._tmp.name, "clip.mov", "originals", "garbage", "ffmpeg", "ffprobe"):
            self.assertNotIn(private, text)

    def test_fixture_container_is_longer_than_its_video(self):
        facts = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=duration,nb_frames:format=duration", "-of", "json", str(self.fixtures["short"])],
            capture_output=True, text=True, check=True).stdout)
        self.assertEqual(facts["streams"][0]["nb_frames"], "3")
        self.assertGreater(float(facts["format"]["duration"]), float(facts["streams"][0]["duration"]) + 0.2)

    def test_a_clip_whose_video_is_shorter_than_its_container_still_yields_three_frames(self):
        self.put_clip(UUID_A, "short", width=1440, height=1080, duration=0.66)
        frames = tag_clips.extract(self.root, UUID_A, 640)
        self.assert_three_real_jpegs(frames)
        self.assertEqual(len({f.read_bytes() for f in frames}), 3)  # three different frames, not one repeated
        from PIL import Image

        with Image.open(frames[0]) as image:
            self.assertEqual(image.size, (640, 480))

    def test_a_one_frame_clip_yields_three_frames(self):
        self.put_clip(UUID_A, "single", width=320, height=180, duration=0.1)
        self.assert_three_real_jpegs(tag_clips.extract(self.root, UUID_A, 128))

    def test_a_receipt_duration_longer_than_the_video_does_not_matter(self):
        self.put_clip(UUID_A, "single", width=320, height=180, duration=5.0)
        self.assert_three_real_jpegs(tag_clips.extract(self.root, UUID_A, 128))

    def test_a_normal_clip_is_sampled_across_its_length_and_sized_as_before(self):
        self.put_clip(UUID_A, "normal", width=640, height=360, duration=2.0)
        frames = tag_clips.extract(self.root, UUID_A, 128)
        self.assert_three_real_jpegs(frames)
        self.assertEqual(len({f.read_bytes() for f in frames}), 3)
        from PIL import Image

        for frame in frames:
            with Image.open(frame) as image:
                self.assertEqual(image.size, (128, 72))
        features = tag_clips.local_features(frames, make_receipt(width=640, height=360, duration=2.0))
        self.assertEqual(features["orientation"], "landscape")

    def test_frame_indices_are_spread_over_the_available_frames(self):
        self.assertEqual(tag_clips.pick_frame_indices(100), [10, 50, 90])
        self.assertEqual(tag_clips.pick_frame_indices(3), [0, 1, 2])
        self.assertEqual(tag_clips.pick_frame_indices(2), [0, 1, 1])
        self.assertEqual(tag_clips.pick_frame_indices(1), [0, 0, 0])

    def test_extraction_stays_one_clip_when_the_frame_count_is_not_reported(self):
        # Matroska does not store nb_frames: ffprobe prints N/A and the count must be estimated.
        mkv = self.root / "originals" / UUID_A / "clip.mkv"
        self.add_clip(UUID_A, width=1440, height=1080, duration=0.66)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.fixtures["short"]), "-c", "copy", str(mkv)], check=True)
        (self.root / "originals" / UUID_A / ".done").write_text(json.dumps(
            {"video": {"name": "clip.mkv", "duration": 0.66, "width": 1440, "height": 1080}}))
        self.assert_three_real_jpegs(tag_clips.extract(self.root, UUID_A, 128))

    def test_an_undecodable_clip_raises_a_message_without_names_or_paths(self):
        self.put_clip(UUID_A, "garbage")
        with self.assertRaises(Exception) as caught:
            tag_clips.extract(self.root, UUID_A, 128)
        self.assert_no_private_text(str(caught.exception))
        self.assertFalse((self.root / "analysis" / "frames" / UUID_A).exists())

    def test_prepare_records_a_failed_marker_and_prepares_the_other_clips(self):
        self.put_clip(UUID_A, "normal", width=640, height=360, duration=2.0)
        self.put_clip(UUID_B, "garbage")
        self.put_clip(UUID_C, "short", width=1440, height=1080, duration=0.66)
        self.put_clip(UUID_D, "single", width=320, height=180, duration=0.1)
        self.assertEqual(self.run_main("prepare"), 0)
        self.assertIn("prepared 3 clips", self.output)
        self.assertIn("skipped 1 unusable clip(s)", self.output)
        self.assert_no_private_text(self.output)
        marker = self.failed_marker(UUID_B)
        self.assertEqual(set(marker), {"uuid", "error", "attempts"})
        self.assertEqual((marker["uuid"], marker["error"]), (UUID_B, "frame_extraction_failed"))
        self.assertIsInstance(marker["attempts"], int)
        self.assertGreaterEqual(marker["attempts"], 1)
        self.assert_no_private_text((self.root / "analysis" / "failed" / f"{UUID_B}.json").read_text())
        self.assertFalse((self.root / "analysis" / "frames" / UUID_B).exists())
        self.assertFalse((self.root / "analysis" / "features" / f"{UUID_B}.json").exists())
        for uuid in (UUID_A, UUID_C, UUID_D):
            self.assertEqual(len(list((self.root / "analysis" / "frames" / uuid).glob("f*.jpg"))), 3)
            self.assertTrue((self.root / "analysis" / "features" / f"{uuid}.json").exists())
            self.assertFalse((self.root / "analysis" / "failed" / f"{uuid}.json").exists())

    def test_ready_clips_skips_failed_clips_until_the_marker_is_deleted(self):
        self.put_clip(UUID_A, "normal", width=640, height=360, duration=2.0)
        self.put_clip(UUID_B, "garbage")
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A, UUID_B])
        self.assertEqual(self.run_main("prepare"), 0)
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A])
        (self.root / "analysis" / "failed" / f"{UUID_B}.json").unlink()
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A, UUID_B])

    def test_a_malformed_receipt_or_a_feature_failure_only_skips_that_clip(self):
        self.put_clip(UUID_A, "normal", width=640, height=360, duration=2.0)
        self.put_clip(UUID_B, "normal", width=640, height=360, duration=2.0)
        self.put_clip(UUID_C, "normal", width=640, height=360, duration=2.0)
        (self.root / "originals" / UUID_B / ".done").write_text("{not json")
        real = tag_clips.local_features
        broken = {"count": 0}

        def flaky(frames, receipt, *geometry):
            if frames[0].parent.name == UUID_C:
                broken["count"] += 1
                raise OSError("image file is truncated: /private/path/f0.jpg")
            return real(frames, receipt, *geometry)

        with mock.patch.object(tag_clips, "local_features", side_effect=flaky):
            self.assertEqual(self.run_main("prepare"), 0)
        self.assertEqual(broken["count"], 1)
        self.assertIn("prepared 1 clips", self.output)
        self.assertIn("skipped 2 unusable clip(s)", self.output)
        self.assert_no_private_text(self.output)
        for uuid in (UUID_B, UUID_C):
            self.assertEqual(self.failed_marker(uuid)["error"], "frame_extraction_failed")
            self.assert_no_private_text((self.root / "analysis" / "failed" / f"{uuid}.json").read_text())
            self.assertFalse((self.root / "analysis" / "frames" / uuid).exists())
        self.assertTrue((self.root / "analysis" / "features" / f"{UUID_A}.json").exists())

    @needs_sdk
    def test_run_tags_the_good_clips_around_a_broken_one_and_never_retries_it(self):
        self.put_clip(UUID_A, "normal", width=640, height=360, duration=2.0)
        self.put_clip(UUID_B, "garbage")
        self.put_clip(UUID_C, "short", width=1440, height=1080, duration=0.66)
        self.put_clip(UUID_D, "single", width=320, height=180, duration=0.1)
        client = StubClient([succeeded(uuid, json.dumps(GOOD_ANALYSIS)) for uuid in (UUID_A, UUID_C, UUID_D)])
        with mock.patch.object(tag_clips.time, "sleep"):
            self.assertEqual(self.run_main("run", "--confirm-upload", client=client), 0)
        batches = client.messages.batches
        self.assertEqual(len(batches.created), 1)
        self.assertEqual(sorted(r["custom_id"] for r in batches.created[0]), [UUID_A, UUID_C, UUID_D])
        for request in batches.created[0]:
            images = [part for part in request["params"]["messages"][0]["content"] if part["type"] == "image"]
            self.assertEqual(len(images), 3)
            self.assertTrue(all(part["source"]["data"] for part in images))
        self.assertIn("skipped 1 unusable clip(s)", self.output)
        self.assertIn("clips tagged: 3", self.output)
        self.assertIn("clips failed frame extraction: 1", self.output)
        self.assert_no_private_text(self.output)
        self.assertEqual(self.failed_marker(UUID_B)["uuid"], UUID_B)

        # The next run sends nothing, does not touch ffmpeg for the failed clip and keeps its marker.
        before = (self.root / "analysis" / "failed" / f"{UUID_B}.json").read_bytes()
        with mock.patch.object(subprocess, "run", wraps=subprocess.run) as spy:
            self.assertEqual(self.run_main("run", "--confirm-upload", client=client), 0)
        self.assertEqual([c.args[0][0] for c in spy.call_args_list if c.args[0][0] in ("ffmpeg", "ffprobe")], [])
        self.assertEqual(len(batches.created), 1)
        self.assertIn("nothing to submit", self.output)
        self.assertNotIn("skipped", self.output)
        self.assertEqual((self.root / "analysis" / "failed" / f"{UUID_B}.json").read_bytes(), before)

    def test_report_shows_how_many_clips_failed_with_or_without_tags(self):
        self.put_clip(UUID_B, "garbage")
        self.assertEqual(self.run_main("prepare"), 0)
        self.assertEqual(self.run_main("report"), 0)
        self.assertIn("no tags yet", self.output)
        self.assertIn("clips failed frame extraction: 1", self.output)
        self.assert_no_private_text(self.output)
        tags = self.root / "analysis" / "tags"
        tags.mkdir(parents=True, exist_ok=True)
        (tags / f"{UUID_A}.json").write_text(json.dumps(
            {"uuid": UUID_A, "analysis": GOOD_ANALYSIS, "error": None, "usd": 0.001, "needs_review": False}))
        self.assertEqual(self.run_main("report"), 0)
        self.assertIn("clips tagged: 1", self.output)
        self.assertIn("clips failed frame extraction: 1", self.output)

    def test_report_without_failures_says_zero(self):
        self.assertEqual(self.run_main("report"), 0)
        self.assertIn("clips failed frame extraction: 0", self.output)


class RequestBuildingTests(TaggerTestCase):
    @needs_sdk
    @needs_pillow
    def test_request_has_three_images_then_the_fixed_instruction_and_json_schema_output(self):
        import anthropic

        self.add_frames(UUID_A)
        schema = anthropic.transform_schema(tag_clips.clip_analysis_model())
        request = tag_clips.build_request(self.root, UUID_A, "claude-haiku-5-5", schema)
        self.assertEqual(request["custom_id"], UUID_A)
        params = request["params"]
        self.assertEqual(params["model"], "claude-haiku-5-5")
        self.assertEqual(params["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(params["output_config"]["format"]["schema"], schema)
        (message,) = params["messages"]
        self.assertEqual(message["role"], "user")
        kinds = [block["type"] for block in message["content"]]
        self.assertEqual(kinds, ["image", "image", "image", "text"])
        self.assertEqual(message["content"][-1]["text"], tag_clips.PROMPT)
        for index, block in enumerate(message["content"][:3]):
            self.assertEqual(block["source"]["media_type"], "image/jpeg")
            expected = (self.root / "analysis" / "frames" / UUID_A / f"f{index}.jpg").read_bytes()
            import base64

            self.assertEqual(base64.standard_b64decode(block["source"]["data"]), expected)

    @needs_sdk
    @needs_pillow
    def test_request_contains_no_file_names_or_paths_of_the_clip(self):
        import anthropic

        self.add_frames(UUID_A)
        schema = anthropic.transform_schema(tag_clips.clip_analysis_model())
        text = json.dumps(tag_clips.build_request(self.root, UUID_A, "claude-haiku-5-5", schema)["params"]["messages"])
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("originals", text)
        self.assertNotIn(UUID_A, text)  # the id is only the custom_id used to match results locally

    def test_missing_frames_fail_clearly(self):
        with self.assertRaises(SystemExit) as caught:
            tag_clips.build_request(self.root, UUID_A, "claude-haiku-5-5", {})
        self.assertIn("run prepare first", str(caught.exception))


@needs_sdk
@needs_pillow
class CollectTests(TaggerTestCase):
    def collect(self, entries, batch_id="msgbatch_test1"):
        self.write_batch(batch_id, uuids=[e.custom_id for e in entries])
        client = StubClient(entries)
        with mock.patch.object(tag_clips.time, "sleep"):
            self.run_main("collect", "--batch", batch_id, client=client)
        return client

    def test_success_refusal_and_invalid_json_are_recorded_and_errored_is_left_for_a_retry(self):
        for uuid in (UUID_A, UUID_B, UUID_C, UUID_D):
            self.add_frames(uuid)
            self.add_features(uuid)
        review = {**GOOD_ANALYSIS, "safety": {"verdict": "review", "categories": ["other"], "reason": "unsure"}}
        client = self.collect([
            succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)),
            succeeded(UUID_B, "I cannot help", stop_reason="refusal"),
            succeeded(UUID_C, "{not json"),
            errored(UUID_D, "errored"),
        ])
        good = self.tag(UUID_A)
        self.assertEqual(good["analysis"]["subjects"], ["sky", "tree"])  # duplicates removed, order kept
        self.assertEqual((good["error"], good["needs_review"], good["schema"], good["model"]),
                         (None, False, "clip-analysis/v2", "claude-haiku-5-5"))
        self.assertEqual(good["features"], {"luma": 0.5})
        self.assertAlmostEqual(good["usd"], 0.000125)  # (1000*0.10 + 300*0.50)/1e6 * 50% batch discount
        refusal = self.tag(UUID_B)
        self.assertEqual((refusal["analysis"], refusal["error"], refusal["needs_review"]), (None, "refusal", True))
        invalid = self.tag(UUID_C)
        self.assertEqual((invalid["analysis"], invalid["needs_review"]), (None, True))
        self.assertTrue(invalid["error"].startswith("invalid_output: "))
        self.assertNotIn("not json", json.dumps(invalid))
        self.assertFalse((self.root / "analysis" / "tags" / f"{UUID_D}.json").exists())  # transient: not final
        self.assertGreater(client.messages.batches.polls, 1)  # waited for the batch to end
        lines = [json.loads(line) for line in (self.root / "analysis" / "tags.jsonl").read_text().splitlines()]
        self.assertEqual([line["uuid"] for line in lines], [UUID_A, UUID_B, UUID_C])
        review_entry = succeeded(UUID_A, json.dumps(review))
        record = tag_clips.build_record(review_entry, {"model": "claude-haiku-5-5"}, "b", None)
        self.assertTrue(record["needs_review"])
        self.assertEqual(record["analysis"]["safety"]["verdict"], "review")

    def test_frames_of_tagged_clips_are_deleted_and_the_ledger_records_cost_and_transient_counts(self):
        for uuid in (UUID_A, UUID_B):
            self.add_frames(uuid)
        self.collect([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)), errored(UUID_B, "expired")])
        self.assertFalse((self.root / "analysis" / "frames" / UUID_A).exists())
        self.assertTrue((self.root / "analysis" / "frames" / UUID_B).exists())  # still needed for the retry
        (line,) = (self.root / "analysis" / "ledger.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(line), {"batch": "msgbatch_test1", "model": "claude-haiku-5-5", "ok": 1,
                                            "failed": 0, "transient": {"expired": 1}, "ignored": 0, "usd": 0.0001})
        self.assertIn("ok=1 failed=0 retry=1 ignored=0", self.output)

    def test_errored_expired_and_canceled_results_write_no_record_and_keep_the_clip_eligible(self):
        uuids = (UUID_A, UUID_B, UUID_C)
        for uuid in uuids:
            self.add_clip(uuid)
            self.add_frames(uuid)
            self.add_features(uuid)
        self.collect([errored(UUID_A, "errored"), errored(UUID_B, "expired"), errored(UUID_C, "canceled")])
        self.assertEqual(list((self.root / "analysis" / "tags").iterdir()), [])
        self.assertFalse((self.root / "analysis" / "tags.jsonl").exists())
        for uuid in uuids:
            self.assertEqual(len(list((self.root / "analysis" / "frames" / uuid).glob("f*.jpg"))), 3)
        ledger = json.loads((self.root / "analysis" / "ledger.jsonl").read_text())
        self.assertEqual((ledger["ok"], ledger["failed"], ledger["transient"]),
                         (0, 0, {"canceled": 1, "errored": 1, "expired": 1}))
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A, UUID_B, UUID_C])  # next run picks them up

    def test_refusals_and_invalid_output_still_produce_needs_review_records(self):
        for uuid in (UUID_A, UUID_B):
            self.add_frames(uuid)
        self.collect([succeeded(UUID_A, "no", stop_reason="refusal"), succeeded(UUID_B, "{broken")])
        for uuid in (UUID_A, UUID_B):
            self.assertTrue(self.tag(uuid)["needs_review"])
            self.assertFalse((self.root / "analysis" / "frames" / uuid).exists())
        ledger = json.loads((self.root / "analysis" / "ledger.jsonl").read_text())
        self.assertEqual((ledger["ok"], ledger["failed"], ledger["transient"]), (0, 2, {}))

    def test_results_for_clips_that_are_not_in_the_batch_are_ignored_and_counted(self):
        self.add_features(UUID_A)
        self.write_batch("msgbatch_test1", uuids=[UUID_A])
        client = StubClient([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)),
                             succeeded(UUID_B, json.dumps(GOOD_ANALYSIS)),  # well-formed but not ours
                             succeeded(UUID_C, json.dumps(GOOD_ANALYSIS))])
        with mock.patch.object(tag_clips.time, "sleep"):
            self.run_main("collect", "--batch", "msgbatch_test1", client=client)
        self.assertEqual(sorted(p.name for p in (self.root / "analysis" / "tags").iterdir()), [f"{UUID_A}.json"])
        ledger = json.loads((self.root / "analysis" / "ledger.jsonl").read_text())
        self.assertEqual((ledger["ok"], ledger["ignored"]), (1, 2))
        self.assertIn("ignored=2", self.output)

    def test_batch_ids_with_a_trailing_newline_are_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_main("collect", "--batch", "msgbatch_x\n", client=StubClient())
        self.assertIn("letters, digits and underscores", str(caught.exception))
        self.assertIsNone(tag_clips.UUID_RE.fullmatch(UUID_A + "\n"))

    def files_under(self, base: pathlib.Path) -> set[pathlib.Path]:
        return {p for p in base.rglob("*") if p.is_file()}

    def test_results_with_unexpected_ids_never_become_paths(self):
        # The batch record itself lists the hostile id, so only the id-format check stands in the way.
        base = self.root.parent
        before = self.files_under(base)
        self.collect([succeeded("../../escape", json.dumps(GOOD_ANALYSIS)),
                      succeeded("../escape", json.dumps(GOOD_ANALYSIS)),
                      succeeded("a/b", json.dumps(GOOD_ANALYSIS))])
        created = self.files_under(base) - before
        self.assertEqual(list((self.root / "analysis" / "tags").iterdir()), [])
        self.assertFalse((self.root / "escape.json").exists())  # `tags/../../escape.json` lands here
        self.assertFalse((self.root / "analysis" / "escape.json").exists())
        self.assertEqual([p for p in base.rglob("*escape*")], [])
        analysis = self.root / "analysis"
        self.assertEqual({p for p in created if analysis not in p.parents}, set())  # nothing outside analysis/
        self.assertEqual({p.name for p in created}, {"msgbatch_test1.json", "ledger.jsonl"})  # batch record, ledger
        self.assertFalse((analysis / "tags.jsonl").exists())

    def test_batch_ids_are_validated_and_must_be_known(self):
        with self.assertRaises(SystemExit):
            self.run_main("collect", "--batch", "../x", client=StubClient())
        with self.assertRaises(SystemExit) as caught:
            self.run_main("collect", "--batch", "msgbatch_unknown", client=StubClient())
        self.assertIn("Unknown batch", str(caught.exception))
        with self.assertRaises(SystemExit):
            self.run_main("collect", client=StubClient())

    def test_a_tagged_clip_is_not_prepared_again(self):
        self.add_clip(UUID_A)
        self.add_clip(UUID_B)
        self.collect([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS))])
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_B])


@needs_sdk
@needs_pillow
class FakeFfmpegTestCase(TaggerTestCase):
    """Two exported clips and a fake ffmpeg that writes small JPEG frames; git still runs for real."""

    def ffmpeg_calls(self) -> list:
        return [call for call in self.run_mock.call_args_list if call.args[0][0] == "ffmpeg"]

    def fake_ffmpeg(self, command, **kwargs):
        if pathlib.Path(command[0]).name == "git":
            return REAL_RUN(command, **kwargs)
        if command[0] == "ffprobe":  # a plausible 30-frame video stream
            facts = {"streams": [{"duration": "1.000000", "nb_frames": "30", "avg_frame_rate": "30/1"}],
                     "format": {"duration": "1.000000"}}
            return subprocess.CompletedProcess(command, 0, json.dumps(facts), "")
        assert command[0] == "ffmpeg", command
        save_frame(pathlib.Path(command[-1]), (len(command[-1]) * 7 % 255, 90, 160))
        return subprocess.CompletedProcess(command, 0, "", "")

    def setUp(self):
        super().setUp()
        self.run_mock = mock.patch.object(subprocess, "run", side_effect=self.fake_ffmpeg).start()
        mock.patch.object(tag_clips.shutil, "which",
                          side_effect=lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else REAL_WHICH(name)).start()
        self.addCleanup(mock.patch.stopall)
        self.add_clip(UUID_A)
        self.add_clip(UUID_B)


@needs_sdk
@needs_pillow
class SubmitAndConsentTests(FakeFfmpegTestCase):
    def test_submit_and_run_refuse_without_confirm_upload_before_doing_any_work(self):
        for command in ("submit", "run"):
            with mock.patch.object(tag_clips, "make_client") as make_client:
                with self.assertRaises(SystemExit) as caught:
                    self.run_main(command)
            self.assertIn("--confirm-upload", str(caught.exception))
            make_client.assert_not_called()
        self.assertEqual(self.ffmpeg_calls(), [])  # not even frames were extracted
        self.assertFalse((self.root / "analysis").exists())

    def test_dry_run_prepares_locally_prints_the_projection_and_uploads_nothing(self):
        with mock.patch.object(tag_clips, "make_client") as make_client:
            self.assertEqual(self.run_main("run", "--dry-run"), 0)
            self.assertEqual(self.run_main("submit", "--dry-run"), 0)
        make_client.assert_not_called()
        self.assertIn("2 clips -> claude-haiku-5-5: projected $", self.output)
        self.assertIn("uploads 3 frames/clip (long side 640px) plus a fixed instruction", self.output)
        self.assertEqual(len(list((self.root / "analysis" / "features").glob("*.json"))), 2)
        self.assertEqual(len(list((self.root / "analysis" / "frames" / UUID_A).glob("f*.jpg"))), 3)
        self.assertEqual(list((self.root / "analysis" / "batches").iterdir()), [])

    def test_prepare_never_uploads_and_needs_no_consent(self):
        with mock.patch.object(tag_clips, "make_client") as make_client:
            self.assertEqual(self.run_main("prepare", "--limit", "1"), 0)
        make_client.assert_not_called()
        self.assertIn("prepared 1 clips", self.output)

    def test_run_with_consent_submits_batches_collects_deletes_frames_and_reports(self):
        client = StubClient([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)),
                             succeeded(UUID_B, json.dumps({**GOOD_ANALYSIS, "subjects": ["fire"]}))])
        with mock.patch.object(tag_clips.time, "sleep"):
            self.assertEqual(self.run_main("run", "--confirm-upload", "--batch-size", "1", client=client), 0)
        batches = client.messages.batches
        self.assertEqual([len(requests) for requests in batches.created], [1, 1])
        self.assertEqual(sorted(r["custom_id"] for requests in batches.created for r in requests), [UUID_A, UUID_B])
        meta = json.loads((self.root / "analysis" / "batches" / "msgbatch_test1.json").read_text())
        self.assertEqual((meta["model"], meta["schema"], meta["frame_px"], len(meta["uuids"])),
                         ("claude-haiku-5-5", "clip-analysis/v2", 640, 1))
        for uuid in (UUID_A, UUID_B):
            self.assertFalse((self.root / "analysis" / "frames" / uuid).exists())
            self.assertIsNotNone(self.tag(uuid)["features"])
        self.assertIn("clips tagged: 2", self.output)
        self.assertIn("safety verdicts: {'clear': 2}", self.output)

    def test_nothing_ready_means_nothing_is_submitted(self):
        for uuid in (UUID_A, UUID_B):
            (self.root / "analysis" / "tags").mkdir(parents=True, exist_ok=True)
            (self.root / "analysis" / "tags" / f"{uuid}.json").write_text("{}")
        client = StubClient()
        self.assertEqual(self.run_main("submit", "--confirm-upload", client=client), 0)
        self.assertEqual(client.messages.batches.created, [])
        self.assertIn("nothing to submit", self.output)


@needs_sdk
@needs_pillow
class PendingBatchTests(FakeFfmpegTestCase):
    """Clips already uploaded in a batch that has not been collected must not be uploaded again."""

    def submit(self, client, *extra):
        with mock.patch.object(tag_clips.time, "sleep"):
            return self.run_main("submit", "--confirm-upload", *extra, client=client)

    def test_two_submits_before_collect_create_one_batch_not_two(self):
        client = StubClient()
        self.assertEqual(self.submit(client), 0)
        first_extractions = len(self.ffmpeg_calls())
        self.assertEqual(self.submit(client), 0)
        batches = client.messages.batches
        self.assertEqual(len(batches.created), 1)
        self.assertEqual(sorted(r["custom_id"] for r in batches.created[0]), [UUID_A, UUID_B])
        self.assertIn("nothing to submit", self.output)
        self.assertEqual(len(self.ffmpeg_calls()), first_extractions)  # nothing was re-extracted either

    def test_ready_clips_excludes_uuids_in_batches_without_a_ledger_line(self):
        self.write_batch("msgbatch_open", uuids=[UUID_A])
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_B])
        ledger = self.root / "analysis" / "ledger.jsonl"
        ledger.write_text(json.dumps({"batch": "msgbatch_other", "ok": 1}) + "\n")
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_B])  # another batch's line does not count
        ledger.write_text(json.dumps({"batch": "msgbatch_open", "ok": 1}) + "\n")
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A, UUID_B])  # collected: eligible again

    def test_a_corrupt_batch_record_stops_instead_of_risking_a_second_upload(self):
        (self.root / "analysis" / "batches").mkdir(parents=True)
        (self.root / "analysis" / "batches" / "msgbatch_bad.json").write_text("{not json")
        with self.assertRaises(SystemExit) as caught:
            tag_clips.ready_clips(self.root)
        self.assertIn("msgbatch_bad", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_collect_pending_collects_every_batch_without_a_ledger_line(self):
        self.write_batch("msgbatch_test1", uuids=[UUID_A])
        self.write_batch("msgbatch_test2", uuids=[UUID_B])
        self.write_batch("msgbatch_done", uuids=[UUID_C])
        (self.root / "analysis" / "ledger.jsonl").write_text(json.dumps({"batch": "msgbatch_done"}) + "\n")
        client = StubClient([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)), succeeded(UUID_B, json.dumps(GOOD_ANALYSIS))])
        retrieved = []
        real_retrieve = client.messages.batches.retrieve
        client.messages.batches.retrieve = lambda batch_id: (retrieved.append(batch_id), real_retrieve(batch_id))[1]
        with mock.patch.object(tag_clips.time, "sleep"):
            self.assertEqual(self.run_main("collect", "--pending", client=client), 0)
        self.assertEqual(sorted(set(retrieved)), ["msgbatch_test1", "msgbatch_test2"])
        ledger = [json.loads(line)["batch"] for line in (self.root / "analysis" / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(ledger, ["msgbatch_done", "msgbatch_test1", "msgbatch_test2"])
        self.assertEqual(tag_clips.pending_batches(self.root), [])

    def test_collect_pending_with_nothing_pending_is_not_an_error(self):
        client = StubClient()
        self.assertEqual(self.run_main("collect", "--pending", client=client), 0)
        self.assertIn("no pending batches", self.output)
        with self.assertRaises(SystemExit):
            self.run_main("collect", client=client)  # neither --batch nor --pending

    def test_run_collects_batches_left_pending_by_an_interrupted_earlier_run(self):
        client = StubClient([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)), succeeded(UUID_B, json.dumps(GOOD_ANALYSIS))])
        self.assertEqual(self.submit(client), 0)  # uploaded, then "Ctrl-C" before collecting
        with mock.patch.object(tag_clips.time, "sleep"):
            self.assertEqual(self.run_main("run", "--confirm-upload", client=client), 0)
        self.assertEqual(len(client.messages.batches.created), 1)  # no second upload
        self.assertEqual(self.tag(UUID_A)["analysis"]["setting"], "outdoor")
        self.assertIn("clips tagged: 2", self.output)

    def test_dry_run_never_collects_pending_batches(self):
        self.write_batch("msgbatch_test1", uuids=[UUID_A])
        with mock.patch.object(tag_clips, "make_client") as make_client:
            self.assertEqual(self.run_main("run", "--dry-run"), 0)
        make_client.assert_not_called()


@needs_sdk
@needs_pillow
class UploadSafetyTests(FakeFfmpegTestCase):
    def test_dry_run_with_confirm_upload_still_never_constructs_a_client(self):
        import anthropic

        for command in ("submit", "run"):
            with mock.patch.object(tag_clips, "make_client") as make_client, \
                    mock.patch.object(anthropic, "Anthropic") as sdk_client:
                self.assertEqual(self.run_main(command, "--dry-run", "--confirm-upload"), 0)
            make_client.assert_not_called()
            sdk_client.assert_not_called()
        self.assertIn("projected $", self.output)
        self.assertEqual(list((self.root / "analysis" / "batches").iterdir()), [])

    def test_batches_are_created_without_sdk_retries(self):
        client = StubClient()
        self.assertEqual(self.run_main("submit", "--confirm-upload", "--batch-size", "1", client=client), 0)
        self.assertEqual(len(client.messages.batches.created), 2)
        self.assertEqual(client.messages.batches.create_options, [{"max_retries": 0}, {"max_retries": 0}])

    def test_default_batch_size_is_small_enough_that_a_lost_upload_is_cheap(self):
        self.assertEqual(tag_clips.build_parser().parse_args(["submit", "--root", "x"]).batch_size, 200)
        self.assertEqual(tag_clips.DEFAULT_BATCH_SIZE, 200)

    def test_frame_size_is_capped(self):
        self.assertEqual(tag_clips.MAX_FRAME_PX, 1024)
        for value in ("1025", "4096"):
            with self.assertRaises(SystemExit) as caught:
                self.run_main("prepare", "--frame-px", value)
            self.assertIn("1024", str(caught.exception))
        self.assertEqual(self.ffmpeg_calls(), [])
        self.assertEqual(self.run_main("prepare", "--frame-px", "1024", "--limit", "1"), 0)


@needs_sdk
@needs_pillow
class PrepareGuardTests(FakeFfmpegTestCase):
    def test_stale_frames_are_never_reused(self):
        stale = self.root / "analysis" / "frames" / UUID_A
        for index in range(3):
            save_frame(stale / f"f{index}.jpg", (1, 2, 3), size=(500, 500))
        (stale / "leftover-partial.jpg").write_bytes(b"half a file")
        before = {path.name: path.read_bytes() for path in stale.glob("f*.jpg")}
        self.assertEqual(self.run_main("prepare", "--frame-px", "128", "--limit", "1"), 0)
        self.assertEqual(len(self.ffmpeg_calls()), 3)  # all three frames were extracted again
        self.assertFalse((stale / "leftover-partial.jpg").exists())
        for path in stale.glob("f*.jpg"):
            self.assertNotEqual(path.read_bytes(), before[path.name])

    def test_a_failed_extraction_does_not_leave_old_frames_behind(self):
        stale = self.root / "analysis" / "frames" / UUID_A
        save_frame(stale / "f2.jpg", (9, 9, 9))
        self.run_mock.side_effect = lambda command, **kwargs: (
            REAL_RUN(command, **kwargs) if pathlib.Path(command[0]).name == "git"
            else subprocess.CompletedProcess(command, 1, "", "boom"))
        self.assertEqual(self.run_main("prepare", "--limit", "1"), 0)  # the clip is skipped, the run goes on
        self.assertEqual(list(stale.glob("f*.jpg")), [])
        self.assertIn("skipped 1 unusable clip(s)", self.output)

    def test_prepare_without_pillow_fails_with_the_install_hint_before_extracting_anything(self):
        with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
            with self.assertRaises(SystemExit) as caught:
                self.run_main("prepare")
        self.assertIn('pip install -e ".[analysis]"', str(caught.exception))
        self.assertIn("Pillow", str(caught.exception))
        self.assertEqual(self.ffmpeg_calls(), [])
        self.assertFalse((self.root / "analysis" / "frames").exists() and any((self.root / "analysis" / "frames").iterdir()))
        for command in ("submit", "run"):
            with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
                with self.assertRaises(SystemExit):
                    self.run_main(command, "--confirm-upload", "--dry-run")
        self.assertEqual(self.ffmpeg_calls(), [])


@needs_pillow
class OsErrorTests(TaggerTestCase):
    def test_a_local_file_error_prints_the_type_and_no_path(self):
        self.add_clip(UUID_A)
        secret = str(self.root / "originals" / UUID_A / ".done")
        with mock.patch.object(tag_clips, "ready_clips", side_effect=PermissionError(13, "Permission denied", secret)):
            code = self.run_main("prepare")
        self.assertEqual(code, tag_clips.EXIT_IO_ERROR)
        self.assertIn("PermissionError", self.output)
        self.assertNotIn(self._tmp.name, self.output)
        self.assertNotIn("Traceback", self.output)

    def test_an_unreadable_receipt_is_reported_without_its_path(self):
        self.add_clip(UUID_A)
        with mock.patch.object(pathlib.Path, "read_text", side_effect=OSError(5, "Input/output error")):
            code = self.run_main("prepare")
        self.assertEqual(code, tag_clips.EXIT_IO_ERROR)
        self.assertNotIn(self._tmp.name, self.output)


@needs_sdk
class CredentialTests(unittest.TestCase):
    def test_standard_sdk_resolution_uses_the_environment_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": FAKE_KEY}):
            client = tag_clips.make_client()
        self.assertEqual(client.api_key, FAKE_KEY)
        self.assertEqual(client.max_retries, 3)

    def test_keychain_service_is_used_only_when_asked_and_the_key_is_never_printed(self):
        completed = subprocess.CompletedProcess(["security"], 0, FAKE_KEY + "\n", "")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-from-env"}):
            with mock.patch.object(subprocess, "run", return_value=completed) as run:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    client = tag_clips.make_client("my-service")
        self.assertEqual(client.api_key, FAKE_KEY)
        self.assertEqual(run.call_args.args[0], ["security", "find-generic-password", "-s", "my-service", "-w"])
        self.assertNotIn(FAKE_KEY, out.getvalue() + err.getvalue())

    def test_keychain_failure_message_never_contains_tool_output(self):
        failed = subprocess.CompletedProcess(["security"], 44, FAKE_KEY, f"could not find {FAKE_KEY}")
        with mock.patch.object(subprocess, "run", return_value=failed):
            with self.assertRaises(SystemExit) as caught:
                tag_clips.load_keychain_key("my-service")
        self.assertNotIn(FAKE_KEY, str(caught.exception))
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("security")):
            with self.assertRaises(SystemExit) as caught:
                tag_clips.load_keychain_key("my-service")
        self.assertIn("security", str(caught.exception))

    def test_submit_uses_the_keychain_service_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp).resolve() / "lp"
            (root / "originals" / UUID_A).mkdir(parents=True)
            (root / "originals" / UUID_A / ".done").write_text(json.dumps(make_receipt()))
            with mock.patch.object(tag_clips, "cmd_prepare", return_value=[UUID_A]), \
                    mock.patch.object(tag_clips, "make_client", return_value=StubClient()) as make_client, \
                    mock.patch.object(tag_clips, "build_request", return_value={}), \
                    contextlib.redirect_stdout(io.StringIO()):
                tag_clips.main(["submit", "--root", str(root), "--confirm-upload", "--keychain-service", "svc"])
            make_client.assert_called_once_with("svc")


@needs_pillow
class ReportTests(TaggerTestCase):
    def test_report_summarises_verdicts_subjects_cost_and_review_count(self):
        tags = self.root / "analysis" / "tags"
        tags.mkdir(parents=True)

        def record(uuid, analysis, error=None, usd=0.001, review=False):
            (tags / f"{uuid}.json").write_text(json.dumps(
                {"uuid": uuid, "analysis": analysis, "error": error, "usd": usd, "needs_review": review}))

        flagged = {**GOOD_ANALYSIS, "subjects": ["fire", "sky"],
                   "safety": {"verdict": "review", "categories": ["other"], "reason": "x"}}
        record(UUID_A, {**GOOD_ANALYSIS, "subjects": ["sky", "tree"]})
        record(UUID_B, flagged, review=True)
        record(UUID_C, None, error="refusal", usd=0.0, review=True)
        self.assertEqual(self.run_main("report"), 0)
        self.assertIn("clips tagged: 3  total cost ~$0.0020", self.output)
        self.assertIn("safety verdicts: {'clear': 1, 'review': 1, 'error': 1}", self.output)
        self.assertIn("('sky', 2)", self.output)
        self.assertIn("needs human review: 2", self.output)
        self.assertIn("sharing sensitivity: {'low': 2}", self.output)
        self.assertNotIn(GOOD_ANALYSIS["caption"], self.output)  # captions are private; the report never prints them

    def test_report_without_tags_says_so_and_creates_nothing(self):
        self.assertEqual(self.run_main("report"), 0)
        self.assertIn("no tags yet", self.output)
        self.assertFalse((self.root / "analysis").exists())


class SafetyPrivacySplitTests(unittest.TestCase):
    """Personal footage must not be flagged as unsafe: privacy sensitivity is its own field."""

    def test_prompt_separates_safety_from_privacy(self):
        prompt = tag_clips.PROMPT
        self.assertIn("Being private or personal is NOT a safety concern", prompt)
        self.assertIn("privacy.sharing_sensitivity", prompt)
        # The v1 wording that conflated the two (and flagged ~40% of ordinary clips) must not return.
        self.assertNotIn("something may be private, sensitive, or inappropriate for sharing", prompt)

    def test_sharing_levels_are_ordered_and_distinct_from_verdicts(self):
        self.assertEqual(tag_clips.SHARING_LEVELS, ("low", "moderate", "high"))
        self.assertFalse(set(tag_clips.SHARING_LEVELS) & set(tag_clips.VERDICTS))

    def test_schema_version_marks_the_split(self):
        self.assertEqual(tag_clips.SCHEMA_ID, "clip-analysis/v2")

    @needs_sdk
    def test_schema_requires_sharing_sensitivity_with_the_allowed_levels(self):
        model = tag_clips.clip_analysis_model()
        privacy = model.model_json_schema()["$defs"]["PrivacyFlags"]
        self.assertIn("sharing_sensitivity", privacy["required"])
        self.assertIn("sharing_note", privacy["required"])
        self.assertEqual(privacy["properties"]["sharing_sensitivity"]["enum"], list(tag_clips.SHARING_LEVELS))

    @needs_sdk
    def test_a_v1_style_record_without_sharing_fields_is_rejected(self):
        legacy = json.loads(json.dumps(GOOD_ANALYSIS))
        del legacy["privacy"]["sharing_sensitivity"], legacy["privacy"]["sharing_note"]
        with self.assertRaises(Exception):
            tag_clips.clip_analysis_model().model_validate(legacy)


class PrivateRootTests(TaggerTestCase):
    def test_root_inside_a_photos_library_package_is_refused(self):
        library = pathlib.Path(self._tmp.name) / "Photos Library.photoslibrary"
        library.mkdir()
        self.root = library / "analysis-root"
        with self.assertRaises(SystemExit):
            self.run_main("report")
        self.assertEqual(list(library.iterdir()), [])

    def test_root_inside_the_checkout_must_be_under_var(self):
        self.root = REPO_ROOT / "tagging-output"
        with self.assertRaises(SystemExit):
            self.run_main("report")
        self.assertFalse(self.root.exists())


# --- displayed orientation (issue #60) -------------------------------------------------------------------------

def rotated_facts(coded_width: int, coded_height: int, rotation: int | None) -> dict:
    """What ``ffprobe -show_streams -show_format -of json`` returns for one phone clip."""
    stream = {"codec_type": "video", "width": coded_width, "height": coded_height}
    if rotation is not None:
        stream["side_data_list"] = [{"side_data_type": "Display Matrix", "rotation": rotation}]
    return {"streams": [stream], "format": {"duration": "1.0"}}


def make_rotated_clip(path: pathlib.Path, rotation: int) -> None:
    """A real 64x48 coded clip with a display matrix (the two-step form FFmpeg 6.1 accepts)."""
    staging = path.with_name("staging.mov")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(staging)], check=True)
    option = ["-display_rotation:v:0", str(rotation)] if rotation else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", *option, "-i", str(staging), "-c", "copy", str(path)], check=True)
    staging.unlink()


class DisplayedGeometryFeatureTests(TaggerTestCase):
    def features(self, receipt, geometry=None):
        frames = []
        for index in range(3):
            frames.append(self.root / f"f{index}.jpg")
            save_frame(frames[-1], (20 * index, 90, 160))
        return tag_clips.local_features(frames, receipt, geometry)

    @needs_pillow
    def test_a_rotated_receipt_gives_the_displayed_size_and_keeps_the_coded_one(self):
        for rotation, orientation in ((0, "landscape"), (90, "portrait"), (-90, "portrait"), (180, "landscape"),
                                      (270, "portrait")):
            with self.subTest(rotation=rotation):
                features = self.features(make_receipt(width=1920, height=1080, rotation=rotation))
                shown = (1080, 1920) if orientation == "portrait" else (1920, 1080)
                self.assertEqual((features["width"], features["height"], features["orientation"]),
                                 (*shown, orientation))
                self.assertEqual((features["rotation"], features["coded_width"], features["coded_height"]),
                                 (rotation, 1920, 1080))

    @needs_pillow
    def test_features_keep_their_old_key_order_with_the_new_keys_after_orientation(self):
        keys = list(self.features(make_receipt(rotation=-90)))
        self.assertEqual(keys[keys.index("duration"):],
                         ["duration", "width", "height", "orientation", "rotation", "coded_width", "coded_height"])

    @needs_pillow
    def test_a_square_clip_stays_landscape(self):
        self.assertEqual(self.features(make_receipt(width=720, height=720))["orientation"], "landscape")

    @needs_pillow
    def test_a_legacy_receipt_without_rotation_cannot_be_featured_from_its_coded_size(self):
        legacy = make_receipt(width=1920, height=1080, rotation=None)
        self.assertNotIn("rotation", legacy["video"])
        with self.assertRaises(ValueError):
            self.features(legacy)
        features = self.features(legacy, geometry=video_geometry.geometry_from_stream(
            rotated_facts(1920, 1080, -90)["streams"][0]))
        self.assertEqual((features["orientation"], features["width"], features["height"]), ("portrait", 1080, 1920))

    def test_a_legacy_receipt_still_loads(self):
        self.add_clip(UUID_A, rotation=None)
        receipt = tag_clips.read_receipt(self.root, UUID_A)
        self.assertEqual(receipt["video"]["width"], 1080)
        self.assertIsNone(tag_clips.geometry_from_receipt(receipt))
        self.assertEqual(tag_clips.ready_clips(self.root), [UUID_A])

    def test_receipt_geometry_is_derived_from_the_coded_size_and_rotation(self):
        geometry = tag_clips.geometry_from_receipt(make_receipt(width=1920, height=1080, rotation=-90))
        self.assertEqual((geometry["display_width"], geometry["display_height"], geometry["orientation"]),
                         (1080, 1920, "portrait"))
        self.assertIsNone(tag_clips.geometry_from_receipt({}))
        self.assertIsNone(tag_clips.geometry_from_receipt({"video": {"rotation": 0}}))


class PrepareGeometryTests(TaggerTestCase):
    """``prepare_clip`` takes the displayed size from the receipt when it has ``rotation``, else from the video."""

    def setUp(self):
        super().setUp()
        for patcher in (mock.patch.object(tag_clips, "extract", return_value=[self.root / "f.jpg"] * 3),
                        mock.patch.object(tag_clips, "local_features",
                                          side_effect=lambda frames, receipt, geometry=None: {"geometry": geometry})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def prepared(self, uuid=UUID_A) -> dict:
        return json.loads((self.root / "analysis" / "features" / f"{uuid}.json").read_text())

    def test_a_legacy_receipt_makes_the_tagger_probe_the_original(self):
        self.add_clip(UUID_A, width=1920, height=1080, rotation=None)
        asked = []

        def fake(path):
            asked.append(path)
            return video_geometry.geometry_from_stream(rotated_facts(1920, 1080, -90)["streams"][0])

        with mock.patch.object(tag_clips, "probe_geometry", side_effect=fake):
            tag_clips.prepare_clip(self.root, UUID_A, 640)
        self.assertEqual(asked, [self.root / "originals" / UUID_A / "clip.mov"])
        geometry = self.prepared()["geometry"]
        self.assertEqual((geometry["orientation"], geometry["display_width"], geometry["display_height"]),
                         ("portrait", 1080, 1920))

    def test_a_receipt_with_rotation_needs_no_probe(self):
        self.add_clip(UUID_A, width=1920, height=1080, rotation=-90)
        with mock.patch.object(tag_clips, "probe_geometry") as probe:
            tag_clips.prepare_clip(self.root, UUID_A, 640)
        probe.assert_not_called()
        self.assertEqual(self.prepared()["geometry"]["orientation"], "portrait")

    def test_an_unreadable_probe_never_falls_back_to_the_coded_size(self):
        self.add_clip(UUID_A, width=1920, height=1080, rotation=None)
        with mock.patch.object(tag_clips, "probe_geometry", return_value=None):
            with self.assertRaises(tag_clips.ClipUnusable):
                tag_clips.prepare_clip(self.root, UUID_A, 640)
        self.assertFalse((self.root / "analysis" / "features" / f"{UUID_A}.json").exists())


@needs_pillow
@needs_ffmpeg
class RealRotatedPrepareTests(TaggerTestCase):
    def test_a_legacy_receipt_of_a_real_rotated_clip_is_tagged_portrait(self):
        for uuid, rotation, expected in ((UUID_A, -90, ("portrait", 48, 64)), (UUID_B, 0, ("landscape", 64, 48)),
                                         (UUID_C, 180, ("landscape", 64, 48)), (UUID_D, 270, ("portrait", 48, 64))):
            with self.subTest(rotation=rotation):
                self.add_clip(uuid, width=64, height=48, duration=0.5, rotation=None)
                make_rotated_clip(self.root / "originals" / uuid / "clip.mov", rotation)
                tag_clips.prepare_clip(self.root, uuid, 64)
                features = json.loads((self.root / "analysis" / "features" / f"{uuid}.json").read_text())
                self.assertEqual((features["orientation"], features["width"], features["height"]), expected)
                self.assertEqual((features["coded_width"], features["coded_height"]), (64, 48))
                self.assertEqual(features["rotation"] % 360, rotation % 360)


class RefreshLocalTestCase(TaggerTestCase):
    """A fake root of tagged clips whose features were computed from the CODED size."""

    def setUp(self):
        super().setUp()
        self.facts: dict[str, dict | None] = {}
        for patcher in (mock.patch.object(video_geometry, "run_ffprobe",
                                          side_effect=lambda path, timeout=120: self.facts.get(path.parent.name)),
                        mock.patch.object(tag_clips.shutil, "which",
                                          side_effect=lambda name: "/usr/bin/ffprobe" if name == "ffprobe"
                                          else REAL_WHICH(name))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def old_features(self) -> dict:
        return {"luma": 0.4321, "luma_spread": 0.0123, "saturation": 0.31, "hue": 0.6, "motion": 0.05,
                "palette": [{"hex": "#102030", "share": 0.5}], "duration": 1.8,
                "width": 1920, "height": 1080, "orientation": "landscape"}

    def add_tagged(self, uuid: str, rotation: int | None, coded=(1920, 1080), with_original=True,
                   probe=True, legacy_receipt=True, feature_file=True) -> None:
        self.add_clip(uuid, width=coded[0], height=coded[1], rotation=None if legacy_receipt else 0)
        if with_original:
            (self.root / "originals" / uuid / "clip.mov").write_bytes(b"placeholder, never decoded")
        if probe:
            self.facts[uuid] = rotated_facts(coded[0], coded[1], rotation)
        tags = self.root / "analysis" / "tags"
        tags.mkdir(parents=True, exist_ok=True)
        record = {"uuid": uuid, "schema": tag_clips.SCHEMA_ID, "model": "claude-haiku-5-5", "batch": "msgbatch_test1",
                  "analysis": GOOD_ANALYSIS, "error": None, "usd": 0.00123, "features": self.old_features(),
                  "needs_review": False}
        tag_clips.write_json(tags / f"{uuid}.json", record, indent=1)
        if feature_file:
            features = self.root / "analysis" / "features"
            features.mkdir(parents=True, exist_ok=True)
            tag_clips.write_json(features / f"{uuid}.json", self.old_features(), indent=1)

    def digest(self, uuid: str, kind="tags") -> str:
        return hashlib.sha256((self.root / "analysis" / kind / f"{uuid}.json").read_bytes()).hexdigest()

    def counts(self) -> dict:
        numbers = {"examined": r"examined (\d+)", "changed": r"changed (\d+)", "unchanged": r"unchanged (\d+)",
                   "missing": r"missing original\) (\d+)", "unreadable": r"unreadable\) (\d+)"}
        return {name: int(re.search(pattern, self.output).group(1)) for name, pattern in numbers.items()}

    def snapshot(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}


class RefreshLocalTests(RefreshLocalTestCase):
    def test_a_wrong_landscape_record_of_a_rotated_clip_becomes_portrait_and_nothing_else_changes(self):
        self.add_tagged(UUID_A, rotation=-90)
        original_tag, original_feature = self.tag(UUID_A), self.old_features()
        self.assertEqual(self.run_main("refresh-local"), 0, self.output)

        tag = self.tag(UUID_A)
        # Positive control: the refresh really changed the record. Only then do the "unchanged" checks mean anything.
        self.assertEqual(original_tag["features"]["orientation"], "landscape")
        self.assertEqual(tag["features"]["orientation"], "portrait")
        self.assertEqual((tag["features"]["width"], tag["features"]["height"]), (1080, 1920))
        self.assertEqual((tag["features"]["rotation"], tag["features"]["coded_width"], tag["features"]["coded_height"]),
                         (-90, 1920, 1080))

        self.assertEqual(list(tag), list(original_tag))  # key order of the record
        for key in original_tag:
            if key != "features":
                self.assertEqual(tag[key], original_tag[key], key)  # analysis, safety/privacy, error, usd, batch ...
        self.assertEqual(tag["analysis"]["safety"], GOOD_ANALYSIS["safety"])
        self.assertEqual(tag["analysis"]["privacy"], GOOD_ANALYSIS["privacy"])
        old_keys = list(original_feature)
        self.assertEqual(list(tag["features"]), old_keys + ["rotation", "coded_width", "coded_height"])
        for key in old_keys:
            if key not in ("width", "height", "orientation"):
                self.assertEqual(tag["features"][key], original_feature[key], key)  # luma, motion, palette ...
        self.assertEqual(json.loads((self.root / "analysis" / "features" / f"{UUID_A}.json").read_text()),
                         tag["features"])
        self.assertEqual(self.counts(), {"examined": 1, "changed": 1, "unchanged": 0, "missing": 0, "unreadable": 0})
        self.assertIn("orientation before: portrait 0, landscape 1", self.output)
        self.assertIn("orientation after: portrait 1, landscape 0", self.output)

    def test_the_files_are_written_the_way_the_tagger_writes_them(self):
        self.add_tagged(UUID_A, rotation=90)
        self.run_main("refresh-local")
        text = (self.root / "analysis" / "tags" / f"{UUID_A}.json").read_text()
        self.assertEqual(text, json.dumps(json.loads(text), indent=1))
        self.assertEqual(list((self.root / "analysis" / "tags").glob("*.tmp")), [])

    def test_a_clip_without_a_display_matrix_gets_rotation_zero_and_its_coded_orientation(self):
        self.add_tagged(UUID_A, rotation=None, coded=(1080, 1920))  # coded portrait, no matrix
        self.add_tagged(UUID_B, rotation=None)  # coded landscape, stored landscape: only the new keys are added
        self.run_main("refresh-local")
        features = self.tag(UUID_A)["features"]
        self.assertEqual((features["orientation"], features["rotation"], features["width"], features["height"]),
                         ("portrait", 0, 1080, 1920))
        features = self.tag(UUID_B)["features"]
        self.assertEqual((features["orientation"], features["rotation"], features["coded_width"]),
                         ("landscape", 0, 1920))

    def test_a_second_run_changes_nothing_and_leaves_the_files_byte_identical(self):
        self.add_tagged(UUID_A, rotation=-90)
        self.add_tagged(UUID_B, rotation=None)
        self.run_main("refresh-local")
        before = self.snapshot()
        self.assertEqual(self.run_main("refresh-local"), 0)
        self.assertEqual(self.counts(), {"examined": 2, "changed": 0, "unchanged": 2, "missing": 0, "unreadable": 0})
        self.assertEqual(self.snapshot(), before)  # includes sha256 of every tag and feature file

    def test_a_clip_that_is_already_right_is_not_rewritten(self):
        self.add_tagged(UUID_A, rotation=None)  # landscape stays landscape ...
        self.run_main("refresh-local")  # ... apart from the new keys, added once
        digests = (self.digest(UUID_A), self.digest(UUID_A, "features"))
        with mock.patch.object(tag_clips, "write_json") as write:
            self.run_main("refresh-local")
        write.assert_not_called()
        self.assertEqual((self.digest(UUID_A), self.digest(UUID_A, "features")), digests)

    def test_dry_run_computes_the_result_and_writes_nothing(self):
        self.add_tagged(UUID_A, rotation=-90)
        self.add_tagged(UUID_B, rotation=None)
        before = self.snapshot()
        self.assertEqual(self.run_main("refresh-local", "--dry-run"), 0, self.output)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("dry run: would change 2, unchanged 0", self.output)  # both lack the new keys; one flips
        self.assertIn("orientation before: portrait 0, landscape 2", self.output)
        self.assertIn("orientation after (dry run): portrait 1, landscape 1", self.output)

    def test_only_the_features_block_of_tag_and_features_files_is_touched(self):
        self.add_tagged(UUID_A, rotation=-90)
        analysis = self.root / "analysis"
        (analysis / "tags.jsonl").write_text(json.dumps({**self.tag(UUID_A)}) + "\n")
        (analysis / "ledger.jsonl").write_text(json.dumps({"batch": "msgbatch_test1", "usd": 0.1}) + "\n")
        (analysis / "tags-v1-pilot.json").write_text("{}")
        (analysis / "batches").mkdir()
        (analysis / "batches" / "msgbatch_test1.json").write_text(json.dumps({"uuids": [UUID_A]}))
        keep = {name: (self.root / name).read_bytes() for name in (
            "analysis/tags.jsonl", "analysis/ledger.jsonl", "analysis/tags-v1-pilot.json",
            "analysis/batches/msgbatch_test1.json", f"originals/{UUID_A}/.done", f"originals/{UUID_A}/clip.mov")}
        self.run_main("refresh-local")
        self.assertEqual(self.tag(UUID_A)["features"]["orientation"], "portrait")  # control: something did change
        for name, data in keep.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)
        self.assertEqual(json.loads((analysis / "tags.jsonl").read_text())["features"]["orientation"], "landscape")

    def test_a_missing_original_is_skipped_and_counted_and_its_record_is_left_alone(self):
        self.add_tagged(UUID_A, rotation=-90, with_original=False)
        self.add_tagged(UUID_B, rotation=-90)
        before = self.digest(UUID_A), self.digest(UUID_A, "features")
        self.run_main("refresh-local")
        self.assertEqual(self.counts(), {"examined": 2, "changed": 1, "unchanged": 0, "missing": 1, "unreadable": 0})
        self.assertEqual((self.digest(UUID_A), self.digest(UUID_A, "features")), before)
        self.assertEqual(self.tag(UUID_B)["features"]["orientation"], "portrait")

    def test_a_missing_or_malformed_receipt_counts_as_a_missing_original(self):
        self.add_tagged(UUID_A, rotation=-90)
        self.add_tagged(UUID_B, rotation=-90)
        (self.root / "originals" / UUID_A / ".done").unlink()
        (self.root / "originals" / UUID_B / ".done").write_text("{not json")
        self.run_main("refresh-local")
        self.assertEqual((self.counts()["missing"], self.counts()["changed"]), (2, 0))

    def test_an_unreadable_probe_is_skipped_and_counted_never_guessed(self):
        self.add_tagged(UUID_A, rotation=-90, probe=False)  # ffprobe fails
        self.add_tagged(UUID_B, rotation=-90)
        self.facts[UUID_B] = {"streams": [{"codec_type": "audio"}], "format": {}}  # no video size
        self.add_tagged(UUID_C, rotation=-90)
        before = self.digest(UUID_A), self.digest(UUID_B)
        self.run_main("refresh-local")
        self.assertEqual(self.counts(), {"examined": 3, "changed": 1, "unchanged": 0, "missing": 0, "unreadable": 2})
        self.assertEqual((self.digest(UUID_A), self.digest(UUID_B)), before)
        self.assertEqual(self.tag(UUID_A)["features"]["orientation"], "landscape")

    def test_failed_clips_and_records_without_features_are_ignored(self):
        self.add_tagged(UUID_A, rotation=-90)
        failed = self.root / "analysis" / "failed"
        failed.mkdir()
        (failed / f"{UUID_B}.json").write_text(json.dumps({"uuid": UUID_B, "error": "frame_extraction_failed"}))
        self.add_tagged(UUID_C, rotation=-90)
        record = self.tag(UUID_C)
        record["features"] = None
        tag_clips.write_json(self.root / "analysis" / "tags" / f"{UUID_C}.json", record, indent=1)
        stray = self.root / "analysis" / "tags" / "not-a-uuid.json"
        stray.write_text("{}")
        before = self.snapshot()
        self.run_main("refresh-local")
        self.assertEqual(self.counts()["examined"], 1)
        after = self.snapshot()
        self.assertEqual({k: v for k, v in after.items() if v != before[k]},
                         {f"analysis/tags/{UUID_A}.json": after[f"analysis/tags/{UUID_A}.json"],
                          f"analysis/features/{UUID_A}.json": after[f"analysis/features/{UUID_A}.json"]})

    def test_a_clip_without_a_features_file_is_still_corrected_in_its_record(self):
        self.add_tagged(UUID_A, rotation=-90, feature_file=False)
        self.run_main("refresh-local")
        self.assertEqual(self.tag(UUID_A)["features"]["orientation"], "portrait")
        self.assertFalse((self.root / "analysis" / "features" / f"{UUID_A}.json").exists())

    def test_an_unreadable_record_or_features_file_is_skipped_and_counted(self):
        self.add_tagged(UUID_A, rotation=-90)
        self.add_tagged(UUID_B, rotation=-90)
        (self.root / "analysis" / "tags" / f"{UUID_A}.json").write_text("{broken")
        (self.root / "analysis" / "features" / f"{UUID_B}.json").write_text("[1]")
        self.run_main("refresh-local")
        self.assertEqual(self.counts(), {"examined": 2, "changed": 0, "unchanged": 0, "missing": 0, "unreadable": 2})
        self.assertEqual(self.tag(UUID_B)["features"]["orientation"], "landscape")

    def test_output_is_counts_only(self):
        self.add_tagged(UUID_A, rotation=-90)
        self.add_tagged(UUID_B, rotation=-90, with_original=False)
        self.add_tagged(UUID_C, rotation=-90, probe=False)
        for argv in (("refresh-local", "--dry-run"), ("refresh-local",)):
            self.run_main(*argv)
            for text in (UUID_A, UUID_B, UUID_C, str(self.root), self._tmp.name, "clip.mov", "originals", "ffprobe",
                         "Traceback", GOOD_ANALYSIS["caption"]):
                self.assertNotIn(text, self.output)
            self.assertLessEqual(len(self.output.splitlines()), 6)

    def test_it_needs_no_pillow_no_sdk_no_key_and_no_frames(self):
        self.add_tagged(UUID_A, rotation=-90)
        with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None, "anthropic": None, "pydantic": None}), \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(tag_clips, "make_client", side_effect=AssertionError("API client")), \
                mock.patch.object(tag_clips, "extract", side_effect=AssertionError("frames")):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            self.assertEqual(self.run_main("refresh-local"), 0, self.output)
        self.assertEqual(self.tag(UUID_A)["features"]["orientation"], "portrait")
        self.assertFalse((self.root / "analysis" / "frames").exists())

    def test_without_ffprobe_it_stops_before_touching_anything(self):
        self.add_tagged(UUID_A, rotation=-90)
        before = self.snapshot()
        with mock.patch.object(tag_clips.shutil, "which",
                               side_effect=lambda name: None if name == "ffprobe" else REAL_WHICH(name)):
            with self.assertRaises(SystemExit) as caught:
                self.run_main("refresh-local")
        self.assertIn("ffprobe", str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_an_empty_root_reports_zero_and_creates_nothing(self):
        self.root.mkdir(parents=True)
        self.assertEqual(self.run_main("refresh-local"), 0)
        self.assertEqual(self.counts(), {"examined": 0, "changed": 0, "unchanged": 0, "missing": 0, "unreadable": 0})
        self.assertFalse((self.root / "analysis").exists())

    def test_a_local_file_error_prints_the_type_and_no_path(self):
        self.add_tagged(UUID_A, rotation=-90)
        with mock.patch.object(tag_clips, "write_json", side_effect=PermissionError(13, "denied", str(self.root))):
            code = self.run_main("refresh-local")
        self.assertEqual(code, tag_clips.EXIT_IO_ERROR)
        self.assertIn("PermissionError", self.output)
        self.assertNotIn(self._tmp.name, self.output)


class RefreshLocalGuardTests(RefreshLocalTestCase):
    def test_an_unguarded_root_inside_the_checkout_is_refused_and_nothing_is_created(self):
        self.root = REPO_ROOT / "tagging-output"
        with self.assertRaises(SystemExit):
            self.run_main("refresh-local")
        self.assertFalse(self.root.exists())

    def test_a_root_inside_a_photos_library_package_is_refused(self):
        library = pathlib.Path(self._tmp.name) / "Photos Library.photoslibrary"
        library.mkdir()
        self.root = library / "analysis-root"
        with self.assertRaises(SystemExit):
            self.run_main("refresh-local", "--dry-run")
        self.assertEqual(list(library.iterdir()), [])

    def test_the_command_is_accepted_by_the_parser_and_goes_through_resolve_private_root(self):
        self.assertEqual(tag_clips.build_parser().parse_args(["refresh-local", "--root", "x"]).command, "refresh-local")
        self.root.mkdir(parents=True)
        with mock.patch.object(tag_clips, "resolve_private_root", wraps=tag_clips.resolve_private_root) as guard:
            self.run_main("refresh-local")
        guard.assert_called_once()


@needs_ffmpeg
class RefreshLocalRealClipTests(RefreshLocalTestCase):
    """The same refresh against real clips with a display matrix, no mocked ffprobe."""

    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # use the real ffprobe and the real shutil.which

    def test_real_rotated_clips_are_corrected_from_their_display_matrix(self):
        cases = {UUID_A: (0, "landscape", 64, 48), UUID_B: (-90, "portrait", 48, 64), UUID_C: (90, "portrait", 48, 64),
                 UUID_D: (180, "landscape", 64, 48)}
        for uuid, (rotation, *_rest) in cases.items():
            self.add_tagged(uuid, rotation=rotation, coded=(64, 48), probe=False)
            make_rotated_clip(self.root / "originals" / uuid / "clip.mov", rotation)
        self.assertEqual(self.run_main("refresh-local", "--dry-run"), 0, self.output)
        self.assertEqual(self.tag(UUID_B)["features"]["orientation"], "landscape")  # dry run wrote nothing
        self.assertEqual(self.run_main("refresh-local"), 0, self.output)
        for uuid, (rotation, orientation, width, height) in cases.items():
            with self.subTest(rotation=rotation):
                features = self.tag(uuid)["features"]
                self.assertEqual((features["orientation"], features["width"], features["height"]),
                                 (orientation, width, height))
                self.assertEqual((features["coded_width"], features["coded_height"]), (64, 48))
                self.assertEqual(features["rotation"] % 360, rotation % 360)
        self.assertEqual(self.counts()["unreadable"], 0)
        self.assertEqual(self.run_main("refresh-local"), 0)
        self.assertEqual(self.counts()["changed"], 0)


if __name__ == "__main__":
    unittest.main()
