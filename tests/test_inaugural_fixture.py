"""Exercise the clean-clone synthetic inaugural fixture generator."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "make_inaugural_fixture.py"
SPEC = importlib.util.spec_from_file_location("make_inaugural_fixture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class InauguralFixtureTests(unittest.TestCase):
    def test_commands_are_bounded_silent_h264_sources(self):
        target = ROOT / "work" / "fixture-command-test"
        commands = MODULE.build_commands(target, duration=0.25, size=64)
        self.assertEqual(len(commands), 3)
        self.assertEqual(
            [Path(command[-1]).name for command in commands],
            ["inaugural-01.mp4", "inaugural-02.mp4", "inaugural-03.mp4"],
        )
        for command in commands:
            self.assertIn("-an", command)
            self.assertIn("libx264", command)
            self.assertIn("yuv420p", command)

    def test_generate_produces_decodable_video_only_mp4s(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as temp:
            targets = MODULE.generate(Path(temp), duration=0.125, size=64)
            self.assertEqual(len(targets), 3)
            for target in targets:
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=codec_type,codec_name,pix_fmt,width,height",
                        "-of",
                        "json",
                        str(target),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                probe = json.loads(result.stdout)
                self.assertEqual(
                    probe["streams"],
                    [
                        {
                            "codec_name": "h264",
                            "codec_type": "video",
                            "width": 64,
                            "height": 64,
                            "pix_fmt": "yuv420p",
                        }
                    ],
                )

    def test_output_cannot_escape_repository(self):
        with self.assertRaisesRegex(ValueError, "inside repository"):
            MODULE.build_commands(Path("/tmp/outside-simvltanea"))


if __name__ == "__main__":
    unittest.main()
