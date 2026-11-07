"""Run the lab's Playwright suite (``tests/e2e/e2e_*.py``) in headless Chrome.

The suite is pytest-style (fixtures, parametrize). Its modules are named ``e2e_*.py`` so that
neither the repository's pytest collection nor unittest discovery runs it a second time; this
wrapper runs it in a pytest subprocess with ``-o python_files=e2e_*.py``. The suite serves the
repository root on 127.0.0.1 and plays synthetic clips that ``python -m simvltanea.lab.make_fixtures``
writes below ``var/proofs/lab-fixtures/`` (FFmpeg).

Like the other browser suites it needs an installed Chromium/Chrome (``PORTVS_BROWSER_EXECUTABLE``),
Python Playwright, pytest and FFmpeg, and fails rather than skips without them. Its parameter lists
are read from the app's ES modules with Node.js, so without ``node`` it skips with that reason.
Headless tests cannot hear: audio is verified through the Web Audio graph, not speakers.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest

from simvltanea.lab import LAB_DIR
from simvltanea.paths import REPO_ROOT

E2E_DIR = LAB_DIR / "tests" / "e2e"


@unittest.skipUnless(shutil.which("node"), "node is not installed; the lab's e2e suite reads its parameter "
                                            "registry and presets from the app's ES modules with Node.js")
class LabPlaywrightTests(unittest.TestCase):
    def test_playwright_suite_passes(self):
        from simvltanea.browser.test_browser_runtime import browser_executable

        env = dict(os.environ, PORTVS_BROWSER_EXECUTABLE=browser_executable(),
                   PYTHONPATH=os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT),
                                               *filter(None, [os.environ.get("PYTHONPATH")])]))
        # The repository's pytest settings (importlib mode, src on the path) apply; only the file pattern differs.
        command = [sys.executable, "-m", "pytest", str(E2E_DIR), "-q", "-rfE", "-p", "no:cacheprovider",
                   "-o", "python_files=e2e_*.py"]
        result = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False, timeout=3600)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output[-12000:])
        self.assertRegex(result.stdout, r"\d+ passed")


if __name__ == "__main__":
    unittest.main()
