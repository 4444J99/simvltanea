"""Privacy gate for the playable lab: no dataset, real media or personal paths enter Git.

A lab dataset (``data/clips.json``, ``media/<id>.mp4``, ``still/<id>.jpg``) is private. Below the
lab subpackage those folder names are git-ignored (derived by ``sync_layout`` from the layout
contract) and rejected by the structure verifier even when force-added. The speech policy default
itself is asserted by ``tests/unit/speech.test.mjs`` and the e2e suite.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import PurePosixPath

from simvltanea.lab import APP_DIR, LAB_DIR
from simvltanea.paths import LAYOUT, REPO_ROOT
from tools.verification.verify_repository_structure import path_violation

LAB = LAB_DIR.relative_to(REPO_ROOT).as_posix()
DATASET_FOLDERS = ("data", "media", "still")
# Spelled in pieces so this file does not match its own scan.
PERSONAL_PATH_TOKENS = ("/" + "Volumes/", "/" + "Users/", "/" + "home/", "." + "photoslibrary")
APP_FILES = {"engine.js", "framing.js", "index.html", "lab.css", "layout.js", "main.js", "params.js", "player.js",
             "presets.js", "speech.js", "store.js", "ui.js"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, check=False)


def visible_lab_paths() -> list[str]:
    paths = set()
    for scope in ("--cached", "--others"):
        output = git("ls-files", "-z", scope, "--exclude-standard", "--", LAB, "docs/authoring/LAB.md").stdout
        paths |= {os.fsdecode(path) for path in output.split(b"\0") if path}
    return sorted(path for path in paths if (REPO_ROOT / path).is_file())


class LabPrivacyTests(unittest.TestCase):
    def test_the_contract_declares_the_lab_dataset_folders(self):
        self.assertEqual(sorted(LAYOUT.policy["private_dataset_directories"]["{package}/lab"]), sorted(DATASET_FOLDERS))

    def test_dataset_folders_below_the_lab_are_git_ignored(self):
        for folder in DATASET_FOLDERS:
            for path in (f"{LAB}/{folder}/clips.json", f"{LAB}/app/{folder}/x.mp4", f"{LAB}/lab-data/{folder}/x.jpg"):
                with self.subTest(path=path):
                    self.assertEqual(git("check-ignore", "-q", "--no-index", path).returncode, 0, path)
        for name in sorted(APP_FILES):
            with self.subTest(app=name):
                self.assertEqual(git("check-ignore", "-q", "--no-index", f"{LAB}/app/{name}").returncode, 1, name)

    def test_force_added_dataset_folders_are_structure_violations(self):
        for folder in DATASET_FOLDERS:
            for path in (f"{LAB}/{folder}/clips.json", f"{LAB}/app/{folder}/notes.md", f"{LAB}/tests/{folder}/x.py"):
                with self.subTest(path=path):
                    self.assertIsNotNone(path_violation(path))
        self.assertIsNone(path_violation(f"{LAB}/app/main.js"))
        self.assertIsNone(path_violation(f"{LAB}/tests/unit/engine.test.mjs"))

    def test_lab_scope_does_not_loosen_the_rest_of_src(self):
        for path in ("src/simvltanea/browser/page.html", "src/simvltanea/browser/style.css",
                     "src/simvltanea/authoring/check.mjs", f"{LAB}/app/clip.mp4", f"{LAB}/app/still.jpg",
                     f"{LAB}/clips.json"):
            with self.subTest(path=path):
                self.assertIsNotNone(path_violation(path))

    def test_no_dataset_folder_or_media_is_visible_in_git(self):
        for path in visible_lab_paths():
            with self.subTest(path=path):
                relative = PurePosixPath(path)
                self.assertFalse(set(relative.parts[:-1]) & set(DATASET_FOLDERS), path)
                self.assertNotIn(relative.suffix.lower(), {".mp4", ".mov", ".jpg", ".jpeg", ".heic", ".png", ".m4a"})
                self.assertNotEqual(relative.name, "clips.json")

    def test_no_personal_absolute_paths_in_lab_files(self):
        paths = visible_lab_paths()
        self.assertIn(f"{LAB}/app/main.js", paths)
        for path in paths:
            text = (REPO_ROOT / path).read_text(encoding="utf-8")
            for token in PERSONAL_PATH_TOKENS:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, text)

    def test_app_is_exactly_the_static_instrument(self):
        self.assertEqual({path.name for path in APP_DIR.iterdir() if path.is_file() and not path.name.startswith(".")}, APP_FILES)


if __name__ == "__main__":
    unittest.main()
