"""Exercise repository governance against real Git indexes and worktrees."""
import tests  # shared discovery bootstrap

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / "tools" / "verification"))

import verify_local_lifecycle as lifecycle
import verify_repository_structure as structure


GENERATED_OUTPUTS = (
    "var/packages/release.zip",
    "var/renders/review.mp4",
    "var/samples/source.mp4",
    "var/site/index.html",
    "var/work/session.json",
    "var/proofs/receipt.json",
    "var/artifact-001/baseline/unapproved.py",
    "var/artifact-001/output/render.mp4",
    "evidence/visual-proof/media/source.mp4",
    "evidence/visual-proof/renders/review.mp4",
)

FIXTURE_IGNORE_RULES = """\
var/*
!var/.gitkeep
evidence/visual-proof/media/
evidence/visual-proof/renders/
archive/raw/*
!archive/raw/README.md
!archive/raw/.gitkeep
__pycache__/
.DS_Store
"""


class RepositoryStructureTests(unittest.TestCase):
    def setUp(self):
        # User-global excludes and Git configuration must not affect fixtures.
        environment = patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="simvltanea-structure-")
        self.addCleanup(self.temp.cleanup)
        self.root = self.make_fixture("repo")

    @staticmethod
    def git(root, *args):
        result = subprocess.run(
            [
                "git", "-C", str(root),
                "-c", "user.name=Structure Tests",
                "-c", "user.email=structure-tests@example.invalid",
                *args,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout

    @staticmethod
    def write(root, path, content=b""):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def make_fixture(self, name):
        root = Path(self.temp.name) / name
        root.mkdir()
        self.git(root, "init", "--quiet", "--initial-branch=main")
        self.git(root, "config", "core.excludesFile", os.devnull)
        for path in structure.REQUIRED_FILES:
            self.write(root, path)
        self.write(root, ".gitignore", FIXTURE_IGNORE_RULES.encode())
        # Categories can retain arbitrary archival formats and placeholders.
        for category in (
            "threads", "handoffs", "receipts", "research", "evidence",
            "media", "bundles", "sessions", "prompts", "extracts",
        ):
            self.write(root, f"archive/chatgpt/{category}/.gitkeep")
        self.write(root, "archive/incubation/README.md")
        self.write(root, "evidence/visual-proof/frames/fixture.png", b"\x89PNG\r\n")
        self.git(root, "add", "--all", "--force")
        self.git(root, "commit", "--quiet", "-m", "Required repository layout")
        return root

    def assert_violation(self, root, path):
        violations = structure.verify_structure(root)
        self.assertIn(path, [entry[0] for entry in violations], violations)
        self.assertEqual(violations, sorted(violations))
        self.assertTrue(all(message for _, message in violations))
        return violations

    def lifecycle_result(self, root, *args):
        output = io.StringIO()
        with patch.object(lifecycle, "ROOT", root), patch.object(lifecycle, "REPO", root):
            with redirect_stdout(output), redirect_stderr(output):
                result = lifecycle.main(list(args))
        return result, output.getvalue()

    def test_fixture_satisfies_the_contract(self):
        self.assertEqual(structure.verify_structure(self.root), [])
        self.assertEqual(self.lifecycle_result(self.root)[0], 0)

    def test_current_repository_layout_satisfies_the_contract(self):
        # Validate the complete working tree without modifying the developer's
        # real index; this also handles structural refactors made as renames.
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index"
            environment = {**os.environ, "GIT_INDEX_FILE": str(index)}
            subprocess.run(
                ["git", "-C", str(ROOT), "read-tree", "HEAD"],
                env=environment, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(ROOT), "add", "-A"],
                env=environment, check=True, capture_output=True,
            )
            with patch.dict(os.environ, {"GIT_INDEX_FILE": str(index)}):
                self.assertEqual(structure.verify_structure(ROOT), [])

    def test_allowed_optional_files_and_archival_formats(self):
        paths = (
            ".vscode/settings.json",
            ".github/copilot-instructions.md",
            ".github/instructions/python.instructions.md",
            ".github/ISSUE_TEMPLATE/bug_report.md",
            ".github/ISSUE_TEMPLATE/config.yml",
            "src/simvltanea/layouts.json",
            "tests/__init__.py",
            "tests/conftest.py",
            "tests/test_fixture.py",
            "docs/plans/2026-10-02-fixture.md",
            "archive/incubation/retained-output.json",
            "archive/chatgpt/logs/Original Log.TXT",
            "archive/chatgpt/media/Original Study.MP4",
            "archive/chatgpt/bundles/Legacy Script.py",
            "archive/raw/PR9_review_proof_2026-09-06/README.md",
            "evidence/visual-proof/frames/review.png",
        )
        for path in paths:
            self.write(self.root, path)
        self.git(self.root, "add", "--all", "--force")
        self.assertEqual(structure.verify_structure(self.root), [])

    def test_unknown_root_entries_and_misplaced_content_are_rejected(self):
        paths = (
            "root_script.py",
            "unapproved/README.md",
            "src/simvltanea/config.json",
            "tools/config.json",
            "examples/script.py",
            "docs/receipt.json",
            "docs/unapproved/README.md",
            ".github/unapproved/settings.json",
            ".vscode/script.py",
            "archive/loose-note.md",
            "archive/chatgpt/unapproved/receipt.md",
            "evidence/unapproved/receipt.json",
            "evidence/visual-proof/frames/uninspected.mp4",
        )
        for path in paths:
            self.write(self.root, path)
        violations = structure.verify_structure(self.root)
        reported = {path for path, _ in violations}
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(path, reported, violations)
        self.assertEqual(violations, sorted(violations))

    def test_test_module_names_are_enforced(self):
        for path in ("tests/helper.py", "tests/fixture_test.py", "tests/nested/helper.py"):
            self.write(self.root, path)
            self.assert_violation(self.root, path)

    def test_required_files_cannot_be_deleted_or_removed_from_the_index(self):
        for operation in ("unstaged", "staged", "index-only"):
            with self.subTest(operation=operation):
                root = self.make_fixture(f"required-{operation}")
                if operation == "unstaged":
                    (root / "README.md").unlink()
                elif operation == "staged":
                    self.git(root, "rm", "README.md")
                else:
                    self.git(root, "rm", "--cached", "README.md")
                    self.assertTrue((root / "README.md").is_file())
                self.assert_violation(root, "README.md")

    def test_required_file_rename_fails_even_with_a_surviving_local_copy(self):
        content = b"Repository fixture overview.\n"
        self.write(self.root, "README.md", content)
        self.git(self.root, "add", "README.md")
        self.git(self.root, "commit", "--quiet", "-m", "Nonempty required README")
        self.git(self.root, "mv", "README.md", "docs/relocated-readme.md")
        self.write(self.root, "README.md", content)
        self.assertIn(
            b"R100\tREADME.md\tdocs/relocated-readme.md",
            self.git(self.root, "diff", "--cached", "--name-status", "-M"),
        )
        violations = self.assert_violation(self.root, "README.md")
        self.assertTrue(
            any(path == "README.md" and "staged for deletion" in message
                for path, message in violations),
            violations,
        )

    def test_required_paths_must_be_regular_files(self):
        for kind in ("directory", "symlink"):
            with self.subTest(kind=kind):
                root = self.make_fixture(f"regular-{kind}")
                readme = root / "README.md"
                readme.unlink()
                if kind == "directory":
                    readme.mkdir()
                else:
                    readme.symlink_to("src/simvltanea/README.md")
                    self.assertTrue(readme.is_file())
                self.assert_violation(root, "README.md")

    def test_missing_required_directory_is_not_satisfied_by_an_empty_directory(self):
        self.git(self.root, "rm", "-r", "evidence/visual-proof/frames")
        (self.root / "evidence/visual-proof/frames").mkdir()
        self.assert_violation(self.root, "evidence/visual-proof/frames")

    def test_required_parent_replaced_by_file_returns_a_policy_violation(self):
        (self.root / "src").rename(Path(self.temp.name) / "saved-src")
        self.write(self.root, "src", b"wrong path type\n")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = structure.main(["--root", str(self.root)])
        self.assertEqual(result, 1, output.getvalue())
        self.assertIn("src", output.getvalue())
        self.assert_violation(self.root, "src")

    def test_generated_outputs_fail_in_every_git_visible_state(self):
        for state in ("untracked", "staged", "committed"):
            with self.subTest(state=state):
                root = self.make_fixture(f"generated-{state}")
                if state == "untracked":
                    self.write(root, ".gitignore")
                for path in GENERATED_OUTPUTS:
                    self.write(root, path, b"generated\n")
                if state != "untracked":
                    self.git(root, "add", "--force", "--", *GENERATED_OUTPUTS)
                if state == "committed":
                    self.git(root, "commit", "--quiet", "-m", "Forced generated outputs")
                reported = {path for path, _ in structure.verify_structure(root)}
                for path in GENERATED_OUTPUTS:
                    self.assertIn(path, reported)
                result, output = self.lifecycle_result(root)
                self.assertEqual(result, 1, output)
                for path in GENERATED_OUTPUTS:
                    self.assertIn(path, output)

    def test_generated_path_predicate_preserves_only_exact_baseline_inputs(self):
        for path in GENERATED_OUTPUTS:
            with self.subTest(path=path):
                self.assertTrue(structure.is_generated_path(path))
        for path in (
            "var/.gitkeep",
            "fixtures/artifact-001/baseline-manifest.json",
            "fixtures/artifact-001/baseline/render_triptych.original.py",
            "evidence/visual-proof/ledger.json",
            "evidence/visual-proof/frames/review.png",
            "src/simvltanea/generated_inventory.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(structure.is_generated_path(path))

    def test_ignored_local_outputs_do_not_fail_either_gate(self):
        for path in GENERATED_OUTPUTS:
            self.write(self.root, path, b"local output\n")
        self.assertEqual(structure.verify_structure(self.root), [])
        self.assertEqual(self.lifecycle_result(self.root)[0], 0)

    def test_nested_generated_placeholders_and_raw_intake_are_rejected(self):
        paths = (
            "var/nested/.gitkeep",
            "archive/raw/new-drop/README.md",
            "archive/raw/PR9_review_proof_2026-09-06/extra.json",
        )
        for path in paths:
            self.write(self.root, path)
        self.git(self.root, "add", "--force", "--", *paths)
        for path in paths:
            self.assert_violation(self.root, path)

    def test_staged_removal_of_optional_file_passes(self):
        self.write(self.root, "src/simvltanea/optional.py")
        self.git(self.root, "add", "src/simvltanea/optional.py")
        self.git(self.root, "commit", "--quiet", "-m", "Optional module")
        self.git(self.root, "rm", "src/simvltanea/optional.py")
        self.assertEqual(structure.verify_structure(self.root), [])
        self.assertEqual(self.lifecycle_result(self.root)[0], 0)

    def test_staged_removal_of_generated_file_stops_the_leak(self):
        path = "var/renders/forced.mp4"
        self.write(self.root, path)
        self.git(self.root, "add", "--force", path)
        self.git(self.root, "commit", "--quiet", "-m", "Generated leak fixture")
        self.git(self.root, "rm", path)
        self.assertEqual(structure.verify_structure(self.root), [])
        self.assertEqual(self.lifecycle_result(self.root)[0], 0)

    def test_nul_inventory_preserves_spaces_and_newlines(self):
        tracked = "archive/chatgpt/media/original frame\nversion.mp4"
        untracked = "archive/chatgpt/media/another frame\nversion.mp4"
        self.write(self.root, tracked)
        self.git(self.root, "add", "--", tracked)
        self.write(self.root, untracked)
        self.assertIn(tracked, structure.git_paths(self.root, "ls-files", "--cached", "-z"))
        self.assertIn(
            untracked,
            structure.git_paths(self.root, "ls-files", "--others", "--exclude-standard", "-z"),
        )
        self.assertEqual(structure.verify_structure(self.root), [])
        bad_path = "unknown root\nfile.txt"
        self.write(self.root, bad_path)
        self.assert_violation(self.root, bad_path)

    def test_lifecycle_detects_force_staged_local_metadata_and_python_caches(self):
        paths = ("src/simvltanea/.DS_Store", "src/simvltanea/__pycache__/composition.cpython-314.pyc")
        for path in paths:
            self.write(self.root, path)
        self.git(self.root, "add", "--force", "--", *paths)
        result, output = self.lifecycle_result(self.root)
        self.assertEqual(result, 1, output)
        for path in paths:
            self.assertIn(path, output)

    def test_cli_exit_status_and_actionable_diagnostics(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = structure.main(["--root", str(self.root)])
        self.assertEqual(result, 0, output.getvalue())
        self.write(self.root, "root_script.py")
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = structure.main(["--root", str(self.root)])
        self.assertEqual(result, 1, output.getvalue())
        self.assertIn("root_script.py", output.getvalue())
        outside_git = Path(self.temp.name) / "outside-git"
        outside_git.mkdir()
        for invalid in (outside_git, outside_git / "missing"):
            with self.subTest(root=invalid):
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    result = structure.main(["--root", str(invalid)])
                self.assertEqual(result, 2, output.getvalue())
                self.assertTrue(output.getvalue().strip())
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/verification/verify_repository_structure.py"), "--unknown"],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)

    def test_linked_git_worktree_is_supported(self):
        worktree = Path(self.temp.name) / "linked-worktree"
        self.git(self.root, "worktree", "add", "--quiet", "-b", "linked", str(worktree))
        self.assertTrue((worktree / ".git").is_file())
        self.assertEqual(structure.verify_structure(worktree), [])
        self.assertEqual(self.lifecycle_result(worktree)[0], 0)


if __name__ == "__main__":
    unittest.main()
