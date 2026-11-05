"""Exercise the clip tagger with generated frames and a stub Batch API: no network, no real key.

Tests that need the optional ``analysis`` extra (anthropic, Pillow) are skipped with a message only
when that package is genuinely absent.
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tools.media import tag_clips
from tools.paths import REPO_ROOT

HAS_SDK = importlib.util.find_spec("anthropic") is not None and importlib.util.find_spec("pydantic") is not None
HAS_PIL = importlib.util.find_spec("PIL") is not None
needs_sdk = unittest.skipUnless(HAS_SDK, "anthropic SDK not installed (python3 -m pip install -e '.[analysis]')")
needs_pillow = unittest.skipUnless(HAS_PIL, "Pillow not installed (python3 -m pip install -e '.[analysis]')")
needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed (system prerequisite)")

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


def make_receipt(width=1080, height=1920, duration=1.8) -> dict:
    return {"video": {"name": "clip.mov", "duration": duration, "width": width, "height": height}}


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
        self.polls = 0

    def create(self, requests):
        self.created.append(list(requests))
        return SimpleNamespace(id=f"msgbatch_test{len(self.created)}")

    def retrieve(self, batch_id):
        self.polls += 1
        status = "in_progress" if self.polls == 1 else "ended"
        return SimpleNamespace(processing_status=status, request_counts="counts")

    def results(self, batch_id):
        return iter(self.entries)


class StubClient:
    def __init__(self, entries=()):
        self.messages = SimpleNamespace(batches=StubBatches(entries))


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
class RequestBuildingTests(TaggerTestCase):
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

    def test_success_refusal_invalid_json_and_errored_results_are_all_recorded(self):
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
        failed = self.tag(UUID_D)
        self.assertEqual((failed["analysis"], failed["error"], failed["usd"], failed["needs_review"]),
                         (None, "errored", 0.0, True))
        self.assertGreater(client.messages.batches.polls, 1)  # waited for the batch to end
        lines = [json.loads(line) for line in (self.root / "analysis" / "tags.jsonl").read_text().splitlines()]
        self.assertEqual([line["uuid"] for line in lines], [UUID_A, UUID_B, UUID_C, UUID_D])
        review_entry = succeeded(UUID_A, json.dumps(review))
        record = tag_clips.build_record(review_entry, {"model": "claude-haiku-5-5"}, "b", None)
        self.assertTrue(record["needs_review"])
        self.assertEqual(record["analysis"]["safety"]["verdict"], "review")

    def test_frames_are_deleted_for_every_result_and_the_ledger_records_cost(self):
        for uuid in (UUID_A, UUID_B):
            self.add_frames(uuid)
        self.collect([succeeded(UUID_A, json.dumps(GOOD_ANALYSIS)), errored(UUID_B, "expired")])
        for uuid in (UUID_A, UUID_B):
            self.assertFalse((self.root / "analysis" / "frames" / uuid).exists())
        (line,) = (self.root / "analysis" / "ledger.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(line), {"batch": "msgbatch_test1", "model": "claude-haiku-5-5", "ok": 1,
                                            "failed": 1, "usd": 0.0001})
        self.assertIn("ok=1 failed=1", self.output)

    def test_results_with_unexpected_ids_never_become_paths(self):
        self.collect([succeeded("../../escape", json.dumps(GOOD_ANALYSIS))])
        self.assertEqual(list((self.root / "analysis" / "tags").iterdir()), [])
        self.assertFalse((self.root.parent / "escape.json").exists())

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
class SubmitAndConsentTests(TaggerTestCase):
    def fake_ffmpeg(self, command, **kwargs):
        assert command[0] == "ffmpeg", command
        save_frame(pathlib.Path(command[-1]), (len(command[-1]) * 7 % 255, 90, 160))
        return subprocess.CompletedProcess(command, 0, "", "")

    def setUp(self):
        super().setUp()
        for patcher in (mock.patch.object(subprocess, "run", side_effect=self.fake_ffmpeg),
                        mock.patch.object(tag_clips.shutil, "which", return_value="/usr/bin/ffmpeg")):
            self.ffmpeg = patcher.start()
            self.addCleanup(patcher.stop)
        self.add_clip(UUID_A)
        self.add_clip(UUID_B)

    def test_submit_and_run_refuse_without_confirm_upload_before_doing_any_work(self):
        for command in ("submit", "run"):
            with mock.patch.object(tag_clips, "make_client") as make_client:
                with self.assertRaises(SystemExit) as caught:
                    self.run_main(command)
            self.assertIn("--confirm-upload", str(caught.exception))
            make_client.assert_not_called()
        self.ffmpeg.assert_not_called()  # not even frames were extracted
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


if __name__ == "__main__":
    unittest.main()
