"""The ls-lint config checks file names inside src/ (issue #62), with a positive control."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from simvltanea.paths import REPO_ROOT

CONFIG = REPO_ROOT / "config" / "lint" / "ls-lint.yml"


def lint(names: list[str]) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "config" / "lint").mkdir(parents=True)
        shutil.copy(CONFIG, root / "config" / "lint" / "ls-lint.yml")
        for name in names:
            path = root / "src" / "simvltanea" / "authoring" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return subprocess.run(
            ["ls-lint", "--config", str(root / "config" / "lint" / "ls-lint.yml"), "--workdir", str(root)],
            capture_output=True, text=True, check=False)


@unittest.skipUnless(shutil.which("ls-lint"), "ls-lint is not installed")
class SrcNamingTests(unittest.TestCase):
    def test_good_names_pass(self):
        result = lint(["play_modes.py", "browser.runtime.js", "browser.studio.js", "README.md", "py.typed"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_camel_case_python_name_fails(self):
        result = lint(["PlayBad.py"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PlayBad.py", result.stdout + result.stderr)

    def test_spaced_name_fails(self):
        result = lint(["Bad Name.py"])
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
