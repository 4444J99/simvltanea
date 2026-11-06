"""Public demo builder: selection filter, metadata stripping, audio rule, manifest allow-list, idempotence.

Everything runs on a fake private root with synthetic lavfi clips. Tests that need FFmpeg skip cleanly when
``ffmpeg``/``ffprobe`` are absent. No real media, no network.
"""
import contextlib
import copy
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import types
import unittest
import uuid as uuidlib

from tools.media import build_public_demo as demo

needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                                   "ffmpeg/ffprobe not installed (system prerequisite)")

CAPTION = "A secret caption about a named person"
SECRET_PLACE = "+12.3456+045.6789"


def options(**overrides):
    base = dict(limit=0, exclude_needs_review=True, exclude_unsafe=True, exclude_document_or_screen=True,
                exclude_license_plate=True, exclude_location_identifiable=True, exclude_readable_text=True)
    return types.SimpleNamespace(**{**base, **overrides})


def analysis(**overrides):
    value = {"subjects": ["person"], "setting": "indoor", "mood": ["calm", "joyful"], "shot": "wide",
             "palette": ["red", "blue"], "caption": CAPTION, "keywords": ["one", "two", "three", "four", "five", "six"],
             "people": {"count": "1", "faces_visible": True, "minors_apparent": False},
             "privacy": {"readable_text": False, "license_plate": False, "document_or_screen": False,
                         "location_identifiable": False, "sharing_sensitivity": "moderate", "sharing_note": "private"},
             "safety": {"verdict": "clear", "categories": [], "reason": ""}}
    value.update(overrides)
    return value


def record(**overrides):
    value = {"uuid": "x", "analysis": analysis(), "needs_review": False, "error": None,
             "features": {"width": 1, "height": 1}}
    value.update(overrides)
    return value


def make_clip(path: pathlib.Path, size="320x180", rotation=0, audio=True, secret_metadata=True) -> None:
    """A short mov carrying GPS/creation-time/handler metadata, optionally a display rotation and audio."""
    staging = path.with_name("staging.mov")
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=15:duration=0.6"]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.6"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-c:a", "aac"]
    if secret_metadata:
        command += ["-metadata", f"location={SECRET_PLACE}/", "-metadata", "creation_time=2020-02-02T02:02:02Z",
                    "-metadata", "com.apple.quicktime.make=SecretPhone", "-metadata:s:v:0", "handler_name=SecretName"]
    subprocess.run([*command, str(staging)], check=True)
    command = ["ffmpeg", "-v", "error", "-y"]
    if rotation:
        command += ["-display_rotation:v:0", str(rotation)]  # input option, FFmpeg 6.1 and later
    subprocess.run([*command, "-i", str(staging), "-c", "copy", str(path)], check=True)
    staging.unlink()


class FakeRoot:
    def __init__(self, folder: pathlib.Path):
        self.root = folder / "private"
        (self.root / "analysis" / "tags").mkdir(parents=True)
        (self.root / "originals").mkdir()
        self.ids = []

    def add(self, rec=None, clip=True, **clip_args) -> str:
        name = str(uuidlib.uuid4()).upper()
        (self.root / "originals" / name).mkdir()
        if clip is True:
            make_clip(self.root / "originals" / name / f"{name}.mov", **clip_args)
        elif clip == "stub":
            (self.root / "originals" / name / f"{name}.mov").write_bytes(b"stub")
        (self.root / "analysis" / "tags" / f"{name}.json").write_text(
            json.dumps(rec if rec is not None else record()), encoding="utf-8")
        self.ids.append(name)
        return name

    def digest(self) -> str:
        sha = hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            sha.update(str(path.relative_to(self.root)).encode())
            if path.is_file():
                sha.update(path.read_bytes())
        return sha.hexdigest()


def run(root: pathlib.Path, out: pathlib.Path, *extra: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = demo.main(["--root", str(root), "--out", str(out), *extra])
    return code, stdout.getvalue(), stderr.getvalue()


class ExclusionRuleTests(unittest.TestCase):
    def reasons(self, rec, **opt):
        return demo.exclusion_reasons(rec, options(**opt))

    def test_a_clean_record_is_selected(self):
        self.assertEqual(self.reasons(record()), [])

    def test_each_rule_excludes_by_its_own_name(self):
        cases = {
            "needs_review": record(needs_review=True),
            "document_or_screen": record(analysis=analysis(privacy={**analysis()["privacy"], "document_or_screen": True})),
            "license_plate": record(analysis=analysis(privacy={**analysis()["privacy"], "license_plate": True})),
            "location_identifiable": record(analysis=analysis(
                privacy={**analysis()["privacy"], "location_identifiable": True})),
            "readable_text": record(analysis=analysis(privacy={**analysis()["privacy"], "readable_text": True})),
            "unsafe": record(analysis=analysis(safety={"verdict": "review", "categories": [], "reason": ""})),
            "no_analysis": record(analysis=None, error="refusal", needs_review=True),
            "unreadable_tags": None,
        }
        for name, rec in cases.items():
            self.assertEqual(self.reasons(rec)[0], name, name)

    def test_unknown_or_missing_facts_exclude(self):
        def without(path):
            rec = copy.deepcopy(record())
            target = rec["analysis"]
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            return rec
        for path, name in ((("safety",), "unsafe"), (("safety", "verdict"), "unsafe"),
                           (("safety", "categories"), "unsafe"), (("privacy", "license_plate"), "license_plate"),
                           (("privacy",), "document_or_screen")):
            self.assertIn(name, self.reasons(without(path)), path)
        no_flag = copy.deepcopy(record())
        del no_flag["needs_review"]
        self.assertIn("needs_review", self.reasons(no_flag))
        self.assertIn("unsafe", self.reasons(record(analysis=analysis(
            safety={"verdict": "clear", "categories": ["other"], "reason": ""}))))
        self.assertIn("unsafe", self.reasons(record(analysis=analysis(
            safety={"verdict": "maybe", "categories": [], "reason": ""}))))

    def test_every_rule_is_a_named_option_that_can_be_relaxed(self):
        text = record(analysis=analysis(privacy={**analysis()["privacy"], "readable_text": True}))
        self.assertEqual(self.reasons(text), ["readable_text"])
        self.assertEqual(self.reasons(text, exclude_readable_text=False), [])
        self.assertEqual(self.reasons(record(needs_review=True), exclude_needs_review=False), [])
        parsed = demo.build_parser().parse_args(["--root", "r", "--out", "o"])
        self.assertTrue(all(getattr(parsed, f"exclude_{name}") for name in
                            ("needs_review", "unsafe", "document_or_screen", "license_plate",
                             "location_identifiable", "readable_text")))
        self.assertEqual(parsed.audio, "keep")


class SelectionCountTests(unittest.TestCase):
    def test_counts_by_reason_need_no_ffmpeg_and_the_limit_applies_to_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeRoot(pathlib.Path(folder))
            for _ in range(3):
                fake.add(clip="stub")
            fake.add(record(needs_review=True), clip="stub")
            fake.add(record(analysis=None), clip="stub")
            fake.add(clip=False)  # tagged, but its original video is gone
            selected, counts = demo.select(fake.root, options())
            self.assertEqual((counts["examined"], counts["selected"], counts["excluded"]), (6, 3, 3))
            self.assertEqual(counts["excluded_by_reason"]["needs_review"], 1)
            self.assertEqual(counts["excluded_by_reason"]["no_analysis"], 1)
            self.assertEqual(counts["excluded_by_reason"]["missing_original"], 1)
            self.assertEqual(sum(counts["excluded_by_reason"].values()), counts["excluded"])
            _, limited = demo.select(fake.root, options(limit=2))
            self.assertEqual(limited["selected"], 2)

    def test_dry_run_prints_counts_only_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeRoot(pathlib.Path(folder))
            for _ in range(2):
                fake.add(clip="stub")
            before, out = fake.digest(), pathlib.Path(folder) / "public"
            code, stdout, _ = run(fake.root, out, "--dry-run")
            self.assertEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(stdout)["selected"], 2)
            self.assertEqual(fake.digest(), before)
            for name in fake.ids:
                self.assertNotIn(name, stdout)
            self.assertNotIn(CAPTION, stdout)

    def test_output_directory_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeRoot(pathlib.Path(folder))
            with self.assertRaises(SystemExit):
                demo.resolve_out(fake.root / "public", fake.root)
            with self.assertRaises(SystemExit):
                demo.resolve_out(demo.REPO_ROOT / "docs" / "public", fake.root.resolve())
            self.assertEqual(demo.resolve_out(pathlib.Path(folder) / "public", fake.root.resolve()).name, "public")


@needs_ffmpeg
class BuildTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = pathlib.Path(self._folder.name)
        self.fake = FakeRoot(self.folder)
        self.out = self.folder / "public"

    def probe(self, path):
        return demo.run_ffprobe(path)

    def test_portrait_clip_is_rotated_shrunk_stripped_and_muted_with_mute(self):
        self.fake.add(rotation=90, size="640x360")  # coded landscape, displayed portrait 360x640
        before = self.fake.digest()
        code, stdout, _ = run(self.fake.root, self.out, "--audio", "mute")
        self.assertEqual(code, 0, stdout)
        self.assertEqual(self.fake.digest(), before, "the private root must stay untouched")
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(manifest["schema"], "simvltanea.public-demo/1")
        (clip,) = manifest["clips"]
        self.assertEqual((clip["width"], clip["height"], clip["orientation"]), (270, 480, "portrait"))
        data = self.probe(self.out / clip["file"])
        self.assertEqual([s["codec_type"] for s in data["streams"]], ["video"])  # no audio stream under mute
        self.assertFalse(data["streams"][0].get("side_data_list"))
        self.assertEqual(set(data["format"].get("tags", {})) - demo.ALLOWED_FORMAT_TAGS, set())
        raw = (self.out / clip["file"]).read_bytes()
        for secret in (SECRET_PLACE, "SecretPhone", "SecretName", "2020-02-02"):
            self.assertNotIn(secret.encode(), raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest()[:12], clip["id"])
        self.assertEqual(clip["file"], f"clips/{clip['id']}.mp4")
        self.assertEqual(clip["bytes"], len(raw))
        self.assertGreater(clip["duration_seconds"], 0.3)

    def test_manifest_holds_only_the_allow_listed_fields(self):
        name = self.fake.add()
        self.assertEqual(run(self.fake.root, self.out)[0], 0)
        text = (self.out / "manifest.json").read_text()
        manifest = json.loads(text)
        (clip,) = manifest["clips"]
        self.assertEqual(set(clip), {"id", "file", "width", "height", "orientation", "duration_seconds", "bytes", "tags"})
        self.assertEqual(set(clip["tags"]), {"keywords", "mood", "shot", "palette"})
        self.assertEqual(clip["tags"]["keywords"], ["one", "two", "three", "four", "five"])  # first five only
        self.assertEqual((clip["tags"]["mood"], clip["tags"]["shot"], clip["tags"]["palette"]),
                         (["calm", "joyful"], "wide", ["red", "blue"]))
        for secret in (name, name.lower(), CAPTION, "sharing_note", "caption", "people", "setting", "subjects",
                       "private", SECRET_PLACE):
            self.assertNotIn(secret, text)
        self.assertEqual({p.name for p in (self.out / "clips").iterdir()}, {f"{clip['id']}.mp4"})

    def test_audio_defaults_to_one_aac_mono_stream_and_metadata_is_still_stripped(self):
        self.fake.add()
        self.assertEqual(run(self.fake.root, self.out)[0], 0)  # no --audio: the default is keep
        (clip,) = json.loads((self.out / "manifest.json").read_text())["clips"]
        audio = [s for s in self.probe(self.out / clip["file"])["streams"] if s["codec_type"] == "audio"]
        self.assertEqual([(s["codec_name"], s["channels"]) for s in audio], [("aac", 1)])
        raw = (self.out / clip["file"]).read_bytes()
        for secret in (SECRET_PLACE, "SecretPhone", "SecretName", "2020-02-02"):
            self.assertNotIn(secret.encode(), raw)
        self.assertEqual(set(self.probe(self.out / clip["file"])["format"].get("tags", {}))
                         - demo.ALLOWED_FORMAT_TAGS, set())

    def test_rerun_is_idempotent_and_orphans_are_reported(self):
        self.fake.add()
        self.fake.add(size="1280x720")
        self.assertEqual(run(self.fake.root, self.out)[0], 0)
        first = (self.out / "manifest.json").read_bytes()
        code, stdout, _ = run(self.fake.root, self.out)
        report = json.loads(stdout)
        self.assertEqual((code, report["encoded_new"], report["reused_existing"]), (0, 0, 2))
        self.assertEqual((self.out / "manifest.json").read_bytes(), first)
        sizes = {(c["width"], c["height"]) for c in json.loads(first)["clips"]}
        self.assertEqual(sizes, {(320, 180), (480, 270)})  # small kept, large shrunk to 480 long side, never upscaled
        code, stdout, _ = run(self.fake.root, self.out, "--limit", "1")
        self.assertEqual(json.loads(stdout)["orphan_files_not_in_manifest"], 1)

    def test_excluded_clips_never_reach_the_output(self):
        self.fake.add(record(needs_review=True))
        self.fake.add(record(analysis=analysis(privacy={**analysis()["privacy"], "readable_text": True})))
        kept = self.fake.add()
        code, stdout, _ = run(self.fake.root, self.out)
        report = json.loads(stdout)
        self.assertEqual((code, report["examined"], report["selected"], report["in_manifest"]), (0, 3, 1, 1))
        self.assertNotIn(kept, stdout)
        _, relaxed, _ = run(self.fake.root, self.out, "--dry-run", "--no-exclude-readable-text")
        self.assertEqual(json.loads(relaxed)["selected"], 2)

    def test_an_undecodable_original_is_counted_and_skipped_without_a_path(self):
        self.fake.add(clip="stub")
        self.fake.add()
        code, stdout, stderr = run(self.fake.root, self.out)
        report = json.loads(stdout)
        self.assertEqual((code, report["in_manifest"], sum(report["failed_by_reason"].values())), (0, 1, 1))
        self.assertNotIn(str(self.fake.root), stdout + stderr)

    def test_verification_fails_closed_on_metadata_audio_and_rotation(self):
        source = self.folder / "src.mov"
        make_clip(source, rotation=90)
        tagged = self.folder / "tagged.mp4"  # what a careless encode would give: metadata kept, audio kept, rotated
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-c:v", "libx264", "-c:a", "aac",
                        "-movflags", "+faststart", str(tagged)], check=True)
        with self.assertRaises(demo.VerificationError):
            demo.verify_output(tagged, "keep")
        stripped = self.folder / "stripped.mp4"
        size, _ = demo.plan_source(source)
        demo.encode(source, stripped, size, "keep")
        self.assertEqual(demo.verify_output(stripped, "keep")["orientation"], "portrait")
        with self.assertRaises(demo.VerificationError):  # audio present although the rule says mute
            demo.verify_output(stripped, "mute")
        garbage = self.folder / "garbage.mp4"
        garbage.write_bytes(b"not a video")
        with self.assertRaises(demo.VerificationError):
            demo.verify_output(garbage, "mute")

    def test_a_verification_failure_publishes_no_manifest(self):
        self.fake.add()
        original = demo.verify_output
        def refuse(*_args, **_kwargs):
            raise demo.VerificationError("forced")
        demo.verify_output = refuse
        try:
            code, _, stderr = run(self.fake.root, self.out)
        finally:
            demo.verify_output = original
        self.assertEqual(code, demo.EXIT_VERIFY_FAILED)
        self.assertFalse((self.out / "manifest.json").exists())
        self.assertIn("VERIFICATION FAILED", stderr)


if __name__ == "__main__":
    unittest.main()
