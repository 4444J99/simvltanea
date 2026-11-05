"""Run the installed command as a subprocess: version, doctor, and friendly failures."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from independent_loop_compositor import doctor
from independent_loop_compositor.version import get_version
from simvltanea.authoring import build_artifact001, from_authoring_model, save_state
from tools.paths import REPO_ROOT

PROGRAM = "independent-loop-compositor"
DEBUG = "SIMVLTANEA_DEBUG"
COMMAND_LINE_MARKERS = ("-filter_complex", "-movflags", "-hide_banner")


def make_state(workspace: Path, real_media: bool) -> Path:
    """A two-loop state; with real_media the clips exist so FFmpeg can render them."""
    (workspace / "media").mkdir(parents=True, exist_ok=True)
    sources = []
    for index in range(2):
        clip = workspace / "media" / f"loop-{index + 1}.mp4"
        if real_media:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 "testsrc2=s=160x160:r=24:d=3", "-vf", f"hue=h={index * 90}", "-c:v", "libx264",
                 "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", str(clip)], check=True)
            digest = hashlib.sha256(clip.read_bytes()).hexdigest()
        else:
            digest = hashlib.sha256(f"placeholder-{index}".encode()).hexdigest()
        sources.append(dict(id=f"media-{index + 1}", path=f"media/loop-{index + 1}.mp4",
                            sha256=digest, kind="video", duration="3"))
    state = from_authoring_model(
        build_artifact001(2), {f"fixtures/loop-{i + 1}.mp4": sources[i] for i in range(2)})
    path = workspace / ("state.json" if real_media else "state-unrendered.json")
    save_state(state, path)
    return path


class CommandLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._directory.cleanup)
        cls.workspace = Path(cls._directory.name).resolve()
        cls.empty_path = cls.workspace / "empty-bin"
        cls.empty_path.mkdir()
        cls.unrendered_state = make_state(cls.workspace / "bare", real_media=False)
        cls.has_ffmpeg = all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe"))
        cls.state = make_state(cls.workspace / "real", real_media=True) if cls.has_ffmpeg else None

    def run_cli(self, *arguments, path=None, debug=False, extra_env=None):
        env = {key: value for key, value in os.environ.items() if key != DEBUG}
        env.update(PYTHONPATH=str(REPO_ROOT / "src"), SIMVLTANEA_ROOT=str(self.workspace))
        if path is not None:
            env["PATH"] = str(path)
        if debug:
            env[DEBUG] = "1"
        env.update(extra_env or {})
        return subprocess.run([sys.executable, "-m", "independent_loop_compositor", *arguments],
                              cwd=self.workspace, env=env, text=True, capture_output=True, timeout=300)

    def assertFriendly(self, result, *fragments):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(result.stderr.startswith(f"{PROGRAM}: error: "), result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)

    def test_version_reports_distribution_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{PROGRAM} {get_version()}")
        self.assertRegex(result.stdout.strip(), rf"^{PROGRAM} \d+\.\d+\.\d+")

    def test_version_prefers_installed_metadata(self):
        site = self.workspace / "fake-site"
        info = site / "simvltanea-9.8.7.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text("Metadata-Version: 2.1\nName: simvltanea\nVersion: 9.8.7\n")
        result = self.run_cli("--version", extra_env={
            "PYTHONPATH": os.pathsep.join([str(site), str(REPO_ROOT / "src")])})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{PROGRAM} 9.8.7")

    def test_top_level_help_lists_subcommands_and_an_example(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("preview", "render", "doctor"):
            self.assertRegex(result.stdout, rf"(?m)^\s+{command}\s+\S")
        self.assertIn("example:", result.stdout)
        self.assertIn("--version", result.stdout)

    def test_render_help_has_correct_title_and_default_directory(self):
        result = self.run_cli("render", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = " ".join(result.stdout.split())
        self.assertNotIn("Render a left-to-right triptych video canon", text)
        self.assertIn("Defaults to var/samples/", text)
        self.assertNotIn("Defaults to samples/", text)

    def test_doctor_without_ffmpeg_fails_cleanly(self):
        result = self.run_cli("doctor", path=self.empty_path)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        for tool in ("ffmpeg", "ffprobe"):
            self.assertTrue(any(line.startswith("FAIL") and tool in line for line in lines), result.stdout)
        self.assertIn("fix: install FFmpeg, for example `brew install ffmpeg`", result.stdout)
        self.assertTrue(any(line.startswith("ok") and "python" in line for line in lines), result.stdout)
        self.assertTrue(all(line.isascii() for line in lines))

    def test_doctor_json_without_ffmpeg(self):
        result = self.run_cli("doctor", "--json", path=self.empty_path)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        status = {check["id"]: check["status"] for check in report["checks"]}
        self.assertEqual([status[key] for key in ("ffmpeg", "ffprobe", "encoder-libx264", "encoder-aac")],
                         ["fail"] * 4)
        self.assertIn(status["shared-engine"], ("ok", "info"))

    def test_doctor_json_on_this_machine_is_valid(self):
        result = self.run_cli("doctor", "--json")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if report["ok"] else 1, result.stderr)
        self.assertEqual(report["version"], get_version())
        self.assertEqual({check["id"] for check in report["checks"]},
                         {"python", "ffmpeg", "ffprobe", "encoder-libx264", "encoder-aac",
                          "workspace", "shared-engine"})
        for check in report["checks"]:
            self.assertIn(check["status"], ("ok", "fail", "info"))
            self.assertEqual(check["required"], check["id"] != "shared-engine")
        if self.has_ffmpeg:
            self.assertTrue(report["ok"], report)

    def test_doctor_text_report_on_this_machine(self):
        result = self.run_cli("doctor")
        self.assertIn(f"{PROGRAM} {get_version()} doctor", result.stdout)
        self.assertEqual(result.returncode, 0 if "all required checks passed" in result.stdout else 1)
        self.assertIn("workspace writable", result.stdout)

    def test_doctor_reports_unusable_workspace(self):
        blocked = self.workspace / "blocked"
        blocked.mkdir()
        (blocked / "var").write_text("not a directory", encoding="utf-8")
        result = self.run_cli("doctor", "--json", extra_env={"SIMVLTANEA_ROOT": str(blocked)})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        checks = {check["id"]: check for check in json.loads(result.stdout)["checks"]}
        self.assertEqual(checks["workspace"]["status"], "fail")
        self.assertIn("not a directory", checks["workspace"]["detail"])
        self.assertTrue(checks["workspace"]["remedy"])

    def test_encoder_parser_reads_ffmpeg_listing(self):
        listing = (" V....D libx264              libx264 H.264\n"
                   " A....D aac                  AAC (Advanced Audio Coding)\n"
                   " ------\n"
                   " S..... srt                  SubRip subtitle\n")
        self.assertEqual(doctor.listed_encoders(listing), {"libx264", "aac", "srt"})

    def test_preview_with_missing_state_is_one_line(self):
        result = self.run_cli("preview", "--state", "missing.json", "--output", "var/preview")
        self.assertFriendly(result, "cannot read state")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_preview_with_output_outside_workspace_is_friendly(self):
        outside = self.workspace.parent / "outside-generated-storage"
        result = self.run_cli("preview", "--state", str(self.unrendered_state), "--output", str(outside))
        self.assertFriendly(result)
        self.assertFalse(outside.exists())

    def test_debug_variable_restores_traceback(self):
        result = self.run_cli("preview", "--state", "missing.json", "--output", "var/preview", debug=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Traceback", result.stderr)
        self.assertIn("StateError", result.stderr)

    def test_render_missing_config_is_an_error_in_both_modes(self):
        state_mode = self.run_cli("render", "--state", str(self.unrendered_state), "--orientation",
                                  "landscape", "--dry-run", "--config", "does-not-exist.json")
        self.assertFriendly(state_mode, "does-not-exist.json")
        legacy = self.run_cli("render", "--dry-run", "--config", "does-not-exist.json")
        self.assertFriendly(legacy, "does-not-exist.json")

    def test_render_invalid_config_is_an_error_in_both_modes(self):
        broken = self.workspace / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        for arguments in (("--state", str(self.unrendered_state), "--orientation", "landscape"), ()):
            with self.subTest(arguments=arguments):
                result = self.run_cli("render", *arguments, "--dry-run", "--config", str(broken))
                self.assertFriendly(result, "broken.json", "invalid JSON")
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_render_without_config_keeps_default_behaviour(self):
        samples = self.workspace / "var" / "samples"
        samples.mkdir(parents=True, exist_ok=True)
        result = self.run_cli("render", "--dry-run")
        self.assertFriendly(result, "No video files found")
        self.assertNotIn("config", result.stderr)

    def test_render_config_that_is_not_an_object_is_an_error(self):
        listing = self.workspace / "list.json"
        listing.write_text("[1, 2]", encoding="utf-8")
        result = self.run_cli("render", "--dry-run", "--config", str(listing))
        self.assertFriendly(result, "top level must be a JSON object")

    def test_missing_ffmpeg_points_at_doctor(self):
        self.assertTrue(self.has_ffmpeg, "ffmpeg and ffprobe are system prerequisites for this suite")
        for arguments in (("render", "--state", str(self.state), "--orientation", "landscape", "--dry-run"),
                          ("preview", "--state", str(self.state), "--output", "var/preview")):
            with self.subTest(command=arguments[0]):
                result = self.run_cli(*arguments, path=self.empty_path)
                self.assertFriendly(result, "ffprobe", f"{PROGRAM} doctor")

    def test_failed_ffmpeg_shows_its_own_diagnostics_not_the_command(self):
        self.assertTrue(self.has_ffmpeg, "ffmpeg and ffprobe are system prerequisites for this suite")
        result = self.run_cli("render", "--state", str(self.state), "--orientation", "landscape",
                              "--width", "320", "--height", "180", "--preset", "bogus",
                              "--output", str(self.workspace / "var" / "failed.mp4"))
        self.assertFriendly(result, "ffmpeg failed with exit status", "bogus")
        for marker in COMMAND_LINE_MARKERS:
            self.assertNotIn(marker, result.stderr)
        self.assertLess(len(result.stderr), 1500)

    def test_successful_render_still_works(self):
        self.assertTrue(self.has_ffmpeg, "ffmpeg and ffprobe are system prerequisites for this suite")
        output = self.workspace / "var" / "ok.mp4"
        result = self.run_cli("render", "--state", str(self.state), "--orientation", "landscape",
                              "--width", "320", "--height", "180", "--preset", "ultrafast",
                              "--output", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file() and output.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
