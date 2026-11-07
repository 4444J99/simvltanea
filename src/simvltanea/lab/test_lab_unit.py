"""Run the lab's Node unit tests and guard its generated configuration reference.

``tests/unit/*.test.mjs`` are plain ``node --test`` files with no dependencies (engine, layout,
framing, speech, params, presets). The configuration reference in ``docs/authoring/LAB.md`` is
generated from ``app/params.js`` by ``scripts/gen_config_reference.mjs``; these tests fail when the
committed table is stale and prove that regenerating it reproduces the committed bytes.

Every test here needs Node.js. Without ``node`` on PATH they skip with that reason; CI installs Node.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from simvltanea.lab import LAB_DIR
from simvltanea.paths import REPO_ROOT, WORK_DIR

NODE = shutil.which("node")
UNIT_TESTS = sorted((LAB_DIR / "tests" / "unit").glob("*.test.mjs"))
GENERATOR = LAB_DIR / "scripts" / "gen_config_reference.mjs"
LAB_DOC = REPO_ROOT / "docs" / "authoring" / "LAB.md"
SKIP_REASON = "node is not installed; the lab's unit tests and config reference generator run on Node.js"


def node(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, *args], cwd=LAB_DIR, capture_output=True, text=True, encoding="utf-8",
                          check=False, timeout=600)


def tail(result: subprocess.CompletedProcess, limit: int = 6000) -> str:
    return (result.stdout + result.stderr)[-limit:]


@unittest.skipUnless(NODE, SKIP_REASON)
class LabUnitTests(unittest.TestCase):
    def test_unit_test_files_are_present(self):
        names = {path.name for path in UNIT_TESTS}
        self.assertEqual(names, {f"{name}.test.mjs" for name in
                                 ("engine", "framing", "layout", "params", "presets", "speech")})

    def test_node_unit_suite_passes(self):
        # Explicit files rather than a folder argument: older Node releases treat arguments as globs.
        result = node("--test", "--test-reporter=tap", *(str(path) for path in UNIT_TESTS))
        self.assertEqual(result.returncode, 0, tail(result))
        self.assertRegex(result.stdout, r"(?m)^# fail 0$")
        self.assertRegex(result.stdout, r"(?m)^# pass [1-9]\d*$")


@unittest.skipUnless(NODE, SKIP_REASON)
class ConfigReferenceTests(unittest.TestCase):
    def test_committed_reference_is_current(self):
        result = node(str(GENERATOR), "--check")
        self.assertEqual(result.returncode, 0, tail(result))
        self.assertIn("up to date", result.stdout)

    def test_stale_reference_fails_and_regeneration_reproduces_the_committed_doc(self):
        committed = LAB_DOC.read_text(encoding="utf-8")
        row = next(line for line in committed.splitlines() if line.startswith("| `audio.speech_policy` |"))
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lab-config-reference-", dir=WORK_DIR) as scratch:
            copy = Path(scratch) / "LAB.md"
            copy.write_text(committed.replace(row, row.replace("| mute |", "| play |")), encoding="utf-8", newline="")
            stale = node(str(GENERATOR), "--check", "--doc", str(copy))
            self.assertEqual(stale.returncode, 1, tail(stale))
            self.assertIn("stale", stale.stderr)
            written = node(str(GENERATOR), "--doc", str(copy))
            self.assertEqual(written.returncode, 0, tail(written))
            self.assertEqual(copy.read_bytes(), LAB_DOC.read_bytes())


if __name__ == "__main__":
    unittest.main()
