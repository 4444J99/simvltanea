"""Exercise the audio screen with synthesized audio and a stand-in ``whisper-cli``: no model, no network, no Photos."""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.media import screen_audio

needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                                   "ffmpeg and ffprobe not installed (system prerequisite)")
REAL_RUN = subprocess.run
REAL_WHICH = shutil.which

UUID_A = "aaaaaaaa-0000-4000-8000-000000000001"
UUID_B = "bbbbbbbb-0000-4000-8000-000000000002"
SECRET = "Hello, my name is Zelda Quux and my number is 0123456789."


def ffmpeg(*arguments: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *arguments],
                   check=True, capture_output=True)


def make_clip(path: pathlib.Path, audio: str | None) -> None:
    """A 1 s 64x64 clip; ``audio`` is an FFmpeg lavfi source (sine, silence, noise) or None for no audio stream."""
    arguments = ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=24:duration=1"]
    if audio:
        arguments += ["-f", "lavfi", "-i", audio, "-c:a", "aac", "-shortest"]
    ffmpeg(*arguments, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))


class AnalyseTests(unittest.TestCase):
    def test_filler_only_output_is_no_speech_with_low_confidence(self):
        for text in ("Thank you.", "you", "Thanks for watching!", "Okay. So", "[BLANK_AUDIO] Thank you."):
            with self.subTest(text=text):
                result = screen_audio.analyse(text)
                self.assertFalse(result["speech"])
                self.assertTrue(result["low_confidence"])
                self.assertEqual((result["words"], result["flags"]), (0, []))

    def test_empty_and_annotation_only_output_is_silence_without_low_confidence(self):
        for text in ("", "  \n", "[BLANK_AUDIO]", "(upbeat music)", "*laughs*"):
            with self.subTest(text=text):
                result = screen_audio.analyse(text)
                self.assertEqual((result["speech"], result["low_confidence"], result["words"]), (False, False, 0))

    def test_ordinary_speech_has_no_flags(self):
        result = screen_audio.analyse("we went down to the water and then walked back home")
        self.assertEqual(result, {"speech": True, "words": 11, "flags": [], "low_confidence": False})

    def test_each_flag_on_a_fixed_string(self):
        cases = {
            "number_sequence": ["call me on 07700900123 later", "the code is 1 2 3 4 5 6 7 8 9",
                                "it is nine eight seven six five four three"],
            "email_like": ["write to anna@example.com soon", "mail me at anna dot smith at example dot com okay"],
            "introduces_self": ["hi my name is sam and this is the garden", "they call me Bobby here"],
            "possible_name": ["we saw Marcus near the shop", "i think it was Priya yesterday"],
            "long_speech": [" ".join(["word"] * 30)],
        }
        for flag, texts in cases.items():
            for text in texts:
                with self.subTest(flag=flag, text=text):
                    self.assertIn(flag, screen_audio.analyse(text)["flags"])

    def test_flags_are_not_raised_by_unrelated_text(self):
        self.assertEqual(screen_audio.analyse("This is nice. The garden is quiet. But we left")["flags"], [])
        self.assertNotIn("long_speech", screen_audio.analyse(" ".join(["word"] * 29))["flags"])
        self.assertNotIn("number_sequence", screen_audio.analyse("one two three four five")["flags"])


class ScreenCase(unittest.TestCase):
    """A private root with two tagged clips, a stand-in model file and a stand-in whisper-cli."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name).resolve()
        self.root = base / "live-photos"
        self.model = base / "model.bin"
        self.model.write_bytes(b"not a real model")
        self.transcript = SECRET
        self.whisper_calls = 0
        self.whisper_fails = False
        self.have_whisper = True
        for patcher in (mock.patch.object(subprocess, "run", self.fake_run),
                        mock.patch.object(shutil, "which", self.fake_which)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_which(self, name, *args, **kwargs):
        if name == "whisper-cli":
            return "/stub/whisper-cli" if self.have_whisper else None
        return REAL_WHICH(name, *args, **kwargs)

    def fake_run(self, command, **kwargs):
        if command[0] != "whisper-cli":
            return REAL_RUN(command, **kwargs)
        self.whisper_calls += 1
        if self.whisper_fails:
            return subprocess.CompletedProcess(command, 1, "", "boom")
        pathlib.Path(command[command.index("-of") + 1] + ".txt").write_text(self.transcript)
        return subprocess.CompletedProcess(command, 0, "", "")

    def add_clip(self, uuid: str, audio: str | None) -> None:
        folder = self.root / "originals" / uuid
        folder.mkdir(parents=True, exist_ok=True)
        make_clip(folder / f"{uuid}.mov", audio)
        tags = self.root / "analysis" / "tags"
        tags.mkdir(parents=True, exist_ok=True)
        (tags / f"{uuid}.json").write_text(json.dumps({"uuid": uuid}))

    def run_main(self, *extra, root=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = screen_audio.main(["--root", str(root or self.root), "--model", str(self.model), *extra])
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        return code

    def record(self, uuid: str) -> dict:
        return json.loads((self.root / "analysis" / "audio" / f"{uuid}.json").read_text())


@needs_ffmpeg
class ScreenRunTests(ScreenCase):
    def test_speech_clip_gets_derived_fields_a_private_transcript_and_nothing_is_printed(self):
        self.add_clip(UUID_A, "sine=frequency=440:duration=1")
        self.assertEqual(self.run_main(), 0)
        record = self.record(UUID_A)
        self.assertEqual({k: record[k] for k in ("screened", "has_audio", "speech", "low_confidence")},
                         {"screened": True, "has_audio": True, "speech": True, "low_confidence": False})
        self.assertEqual(sorted(record), ["flags", "has_audio", "low_confidence", "screened", "speech", "words"])
        self.assertIn("introduces_self", record["flags"])
        self.assertIn("number_sequence", record["flags"])
        audio_dir = self.root / "analysis" / "audio"
        transcript = audio_dir / f"{UUID_A}.txt"
        self.assertEqual(transcript.read_text(), SECRET)
        for path in (transcript, audio_dir / f"{UUID_A}.json"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600, path.name)
        self.assertEqual(audio_dir.stat().st_mode & 0o777, 0o700)
        for needle in ("Zelda", "Quux", "0123456789", UUID_A):
            self.assertNotIn(needle, self.stdout + self.stderr)
            self.assertNotIn(needle, json.dumps(record))
        self.assertIn("1 clips screened this run | speech 1", self.stdout)
        self.assertEqual(list(audio_dir.glob("*.tmp")), [])

    def test_whisper_filler_on_a_silent_track_is_no_speech_and_low_confidence(self):
        self.add_clip(UUID_A, "anullsrc=r=16000:cl=mono")
        self.transcript = "Thank you."
        self.assertEqual(self.run_main(), 0)
        record = self.record(UUID_A)
        self.assertEqual((record["speech"], record["low_confidence"], record["words"], record["flags"]),
                         (False, True, 0, []))

    def test_a_noise_burst_is_screened_like_any_other_audio(self):
        self.add_clip(UUID_A, "anoisesrc=d=1:a=0.2")
        self.transcript = "[BLANK_AUDIO]"
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.record(UUID_A)["speech"], self.whisper_calls), (False, 1))

    def test_a_clip_without_an_audio_stream_is_marked_and_never_transcribed(self):
        self.add_clip(UUID_A, None)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.record(UUID_A), {"screened": True, "has_audio": False, "speech": False, "words": 0,
                                               "flags": [], "low_confidence": False})
        self.assertEqual(self.whisper_calls, 0)
        self.assertFalse((self.root / "analysis" / "audio" / f"{UUID_A}.txt").exists())
        self.assertIn("no audio 1", self.stdout)

    def test_screened_clips_are_skipped_until_force_and_limit_bounds_a_run(self):
        self.add_clip(UUID_A, "sine=frequency=440:duration=1")
        self.add_clip(UUID_B, "sine=frequency=880:duration=1")
        self.assertEqual(self.run_main("--limit", "1"), 0)
        self.assertEqual(self.whisper_calls, 1)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.whisper_calls, 2)  # only the clip the first run left over
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.whisper_calls, 2)
        self.assertIn("0 clips screened this run", self.stdout)
        self.assertEqual(self.run_main("--force"), 0)
        self.assertEqual(self.whisper_calls, 4)

    def test_a_failed_whisper_run_leaves_no_marker_and_is_retried(self):
        self.add_clip(UUID_A, "sine=frequency=440:duration=1")
        self.whisper_fails = True
        self.assertEqual(self.run_main(), 0)
        self.assertIn("failed 1", self.stdout)
        self.assertFalse((self.root / "analysis" / "audio" / f"{UUID_A}.json").exists())
        self.whisper_fails = False
        self.assertEqual(self.run_main(), 0)
        self.assertTrue(self.record(UUID_A)["speech"])

    def test_tag_files_that_are_not_uuids_or_have_no_original_are_ignored(self):
        self.add_clip(UUID_A, None)
        (self.root / "analysis" / "tags" / "notes.json").write_text("{}")
        (self.root / "analysis" / "tags" / f"{UUID_B}.json").write_text("{}")  # no original exported
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(sorted(p.name for p in (self.root / "analysis" / "audio").iterdir()), [f"{UUID_A}.json"])


class ScreenPrerequisiteTests(ScreenCase):
    def assert_one_line_failure(self, code, fragment):
        self.assertEqual(code, screen_audio.EXIT_MISSING)
        self.assertEqual(self.stdout, "")
        self.assertEqual(len(self.stderr.strip().splitlines()), 1, self.stderr)
        self.assertIn(fragment, self.stderr)
        self.assertNotIn("Traceback", self.stderr)

    def test_missing_whisper_cli_ffmpeg_and_ffprobe_are_one_clear_line(self):
        self.have_whisper = False
        self.assert_one_line_failure(self.run_main(), "whisper-cli not found")
        self.have_whisper = True
        for tool in ("ffmpeg", "ffprobe"):
            with self.subTest(tool=tool), mock.patch.object(
                    shutil, "which", lambda name, *a, _t=tool, **k: None if name == _t else REAL_WHICH(name, *a, **k)):
                self.assert_one_line_failure(self.run_main(), f"{tool} not found")

    def test_missing_model_file_or_option_is_one_clear_line(self):
        self.model.unlink()
        self.assert_one_line_failure(self.run_main(), "speech model file not found")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            os.environ.pop(screen_audio.MODEL_ENV, None)
            code = screen_audio.main(["--root", str(self.root)])
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.assert_one_line_failure(code, "no speech model given")

    def test_missing_root_is_one_clear_line_and_the_environment_is_a_fallback(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            os.environ.pop(screen_audio.ROOT_ENV, None)
            code = screen_audio.main([])
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        self.assert_one_line_failure(code, "--root")
        with mock.patch.dict(os.environ, {screen_audio.ROOT_ENV: str(self.root),
                                          screen_audio.MODEL_ENV: str(self.model)}):
            args = screen_audio.build_parser().parse_args([])
        self.assertEqual((args.root, args.model), (self.root, self.model))

    def test_help_needs_nothing_installed(self):
        completed = REAL_RUN([sys.executable, "-m", "tools.media.screen_audio", "--help"], capture_output=True,
                             text=True, env={"PATH": "/nonexistent", "PYTHONPATH": os.pathsep.join(sys.path)},
                             cwd=pathlib.Path(__file__).resolve().parents[2])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--root", completed.stdout)

    def test_root_inside_a_photos_library_package_is_refused_in_any_case(self):
        base = pathlib.Path(self._tmp.name)
        for name in ("Photos Library.photoslibrary", "Pictures.PhotosLibrary"):
            library = base / name
            library.mkdir()
            for candidate in (library, library / "export"):
                with self.subTest(root=str(candidate.relative_to(base))), self.assertRaises(SystemExit) as caught:
                    self.run_main(root=candidate)
                self.assertIn("Photos library", str(caught.exception))
            self.assertEqual(list(library.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
