"""Exercise the private-root guard against real temporary Git repositories (no mocks of Git).

Every repository lives in a temporary directory, with global and system Git configuration disabled
and the author set through the environment, so nothing outside the sandbox is read or written.
"""
import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.media import private_root

HAS_GIT = shutil.which("git") is not None
needs_git = unittest.skipUnless(HAS_GIT, "git is not installed")


def git_environment(home: pathlib.Path) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    environment.update({
        "HOME": str(home), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return environment


class SandboxTestCase(unittest.TestCase):
    """A temporary directory that holds repositories and plain directories side by side."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = pathlib.Path(os.path.realpath(self._tmp.name))
        self.environment = git_environment(self.base)

    def git(self, cwd: pathlib.Path, *arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=cwd, env=self.environment, check=True, capture_output=True)

    def make_repository(self, name: str) -> pathlib.Path:
        """A repository with a tracked ``docs/`` folder and an ignored ``var/`` folder, like this one."""
        repo = self.base / name
        (repo / "docs").mkdir(parents=True)
        (repo / "var").mkdir()
        (repo / ".gitignore").write_text("/var/*\n!/var/.gitkeep\n")
        (repo / "docs" / "README.md").write_text("tracked\n")
        (repo / "var" / ".gitkeep").write_text("")
        self.git(repo, "init", "-q")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "initial")
        return repo

    def checkout_is(self, repo: pathlib.Path):
        """Make ``repo`` the checkout that 'runs the code', as REPO_ROOT does in production."""
        for name, value in (("REPO_ROOT", repo), ("VAR_DIR", repo / "var")):
            patcher = mock.patch.object(private_root, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def resolve(self, path) -> tuple[pathlib.Path, str]:
        """Run the guard with the sandbox environment; returns the result and what it wrote to stderr."""
        err = io.StringIO()
        with mock.patch.dict(os.environ, self.environment, clear=True), contextlib.redirect_stderr(err):
            return private_root.resolve_private_root(path), err.getvalue()

    def refused(self, path) -> str:
        with self.assertRaises(SystemExit) as caught:
            self.resolve(path)
        message = str(caught.exception)
        self.assertNotIn(str(self.base), message)  # names no path beyond what the user typed
        return message

    def case_sensitive_volume(self) -> bool:
        probe = self.base / "CaseProbe"
        probe.mkdir()
        return not (self.base / "caseprobe").exists()


@needs_git
class GitRuleTests(SandboxTestCase):
    def test_a_tracked_directory_of_the_checkout_is_refused(self):
        repo = self.make_repository("checkout")
        self.checkout_is(repo)
        self.assertIn("var/", self.refused(repo / "docs" / "live-photos"))
        self.assertIn("var/", self.refused(repo / "media-dump"))
        self.assertFalse((repo / "docs" / "live-photos").exists())

    def test_a_tracked_directory_of_any_other_repository_is_refused_by_git(self):
        self.checkout_is(self.make_repository("checkout"))
        other = self.make_repository("unrelated")
        message = self.refused(other / "docs" / "live-photos")
        self.assertIn("Git working tree", message)
        self.assertIn("not ignored", message)
        self.refused(other / "brand-new-untracked-folder")

    def test_an_ignored_directory_is_accepted_in_the_checkout_and_in_another_repository(self):
        repo = self.make_repository("checkout")
        self.checkout_is(repo)
        accepted, note = self.resolve(repo / "var" / "live-photos")
        self.assertEqual(accepted, repo / "var" / "live-photos")
        self.assertEqual(note, "")
        other = self.make_repository("unrelated")
        self.assertEqual(self.resolve(other / "var" / "deep" / "er")[0], other / "var" / "deep" / "er")
        self.assertFalse((repo / "var" / "live-photos").exists())  # validation creates nothing

    def test_a_root_outside_any_repository_is_accepted_silently(self):
        self.checkout_is(self.make_repository("checkout"))
        plain = self.base / "archive" / "live-photos"
        accepted, note = self.resolve(plain)
        self.assertEqual(accepted, plain)
        self.assertEqual(note, "")

    def test_a_path_inside_a_sibling_worktree_is_refused_when_another_worktree_runs_the_code(self):
        main = self.make_repository("main")
        sibling = self.base / "sibling"
        self.git(main, "worktree", "add", "-q", "-b", "other-branch", str(sibling))
        self.checkout_is(main)  # the code runs from `main`, which knows nothing about `sibling`
        self.assertIn("not ignored", self.refused(sibling / "docs" / "live-photos"))
        self.assertIn("not ignored", self.refused(sibling / "scratch"))
        self.assertEqual(self.resolve(sibling / "var" / "live-photos")[0], sibling / "var" / "live-photos")

    def test_the_guard_does_not_depend_on_which_worktree_runs_it(self):
        main = self.make_repository("main")
        sibling = self.base / "sibling"
        self.git(main, "worktree", "add", "-q", "-b", "other-branch", str(sibling))
        for running in (main, sibling):
            with self.subTest(running=running.name):
                with contextlib.ExitStack() as stack:
                    for name, value in (("REPO_ROOT", running), ("VAR_DIR", running / "var")):
                        stack.enter_context(mock.patch.object(private_root, name, value))
                    for repo in (main, sibling):
                        self.refused(repo / "docs" / "x")

    def test_a_symlink_into_a_tracked_directory_is_refused(self):
        repo = self.make_repository("checkout")
        self.checkout_is(repo)
        link = self.base / "innocent"
        link.symlink_to(repo / "docs", target_is_directory=True)
        self.refused(link / "live-photos")

    def test_git_environment_variables_cannot_redirect_the_check(self):
        repo = self.make_repository("checkout")
        self.checkout_is(repo)
        redirected = {**self.environment, "GIT_DIR": str(repo / ".git"), "GIT_WORK_TREE": str(repo)}
        plain = self.base / "archive" / "live-photos"
        with mock.patch.dict(os.environ, redirected, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(private_root.resolve_private_root(plain), plain)
            with self.assertRaises(SystemExit):
                private_root.resolve_private_root(self.make_repository("unrelated") / "docs" / "x")

    def test_a_root_inside_a_git_directory_is_refused(self):
        repo = self.make_repository("checkout")
        self.checkout_is(repo)
        self.refused(repo / ".git" / "live-photos")


class CaseInsensitiveTests(SandboxTestCase):
    def fold_variant(self, path: pathlib.Path) -> pathlib.Path:
        return pathlib.Path(str(path).upper())

    def test_a_case_variant_of_the_checkout_path_is_refused_without_git(self):
        repo = self.base / "Checkout"
        (repo / "docs").mkdir(parents=True)
        self.checkout_is(repo)
        with mock.patch.object(private_root.shutil, "which", return_value=None):
            for path in (repo / "docs" / "live-photos", repo / "tools" / "dump"):
                variant = self.fold_variant(path)
                self.assertNotEqual(str(variant), str(path))
                self.assertIn("var/", self.refused(variant))

    def test_a_case_variant_of_var_is_not_trusted_without_git(self):
        repo = self.base / "Checkout"
        (repo / "var").mkdir(parents=True)
        self.checkout_is(repo)
        with mock.patch.object(private_root.shutil, "which", return_value=None):
            self.refused(repo / "VAR" / "live-photos")  # only the exact var/ is known to be ignored

    @needs_git
    def test_a_case_variant_of_the_checkout_path_is_refused_with_git_on_a_case_insensitive_volume(self):
        repo = self.make_repository("Checkout")
        self.checkout_is(repo)
        if self.case_sensitive_volume():
            self.skipTest("the temporary directory is on a case-sensitive volume")
        variant = self.base / "CHECKOUT" / "docs" / "live-photos"
        self.assertTrue(variant.parent.exists())  # the variant really reaches the checkout
        self.refused(variant)

    @needs_git
    def test_a_case_variant_of_another_repository_is_refused_by_git_on_a_case_insensitive_volume(self):
        self.checkout_is(self.make_repository("Checkout"))
        other = self.make_repository("Unrelated")
        if self.case_sensitive_volume():
            self.skipTest("the temporary directory is on a case-sensitive volume")
        self.refused(self.base / "UNRELATED" / "docs" / "x")
        self.assertEqual(self.resolve(self.base / "UNRELATED" / "var" / "x")[0],
                         self.base / "UNRELATED" / "var" / "x")
        self.assertTrue(other.exists())


class GitUnavailableTests(SandboxTestCase):
    def test_without_git_the_checkout_comparison_still_applies_and_the_note_says_so(self):
        repo = self.base / "checkout"
        (repo / "var").mkdir(parents=True)
        (repo / "docs").mkdir()
        self.checkout_is(repo)
        plain = self.base / "archive" / "live-photos"
        with mock.patch.object(private_root.shutil, "which", return_value=None):
            accepted, note = self.resolve(plain)
            self.assertEqual(accepted, plain)
            self.assertIn("git is not available", note)
            self.assertEqual(self.resolve(repo / "var" / "x")[0], repo / "var" / "x")
            self.refused(repo / "docs" / "x")

    def test_a_git_that_cannot_be_executed_counts_as_unavailable(self):
        self.checkout_is(self.base / "checkout")
        with mock.patch.object(private_root.shutil, "which", return_value=str(self.base / "no-such-git")):
            accepted, note = self.resolve(self.base / "archive" / "x")
        self.assertIn("git is not available", note)
        self.assertEqual(accepted, self.base / "archive" / "x")


class ExistingRefusalTests(SandboxTestCase):
    def test_photos_library_packages_are_still_refused_first(self):
        library = self.base / "Photos Library.photoslibrary"
        library.mkdir()
        link = self.base / "link"
        link.symlink_to(library, target_is_directory=True)
        for path in (library / "x", link / "x", self.base / "Pictures.PhotosLibrary" / "x"):
            with self.assertRaises(SystemExit) as caught:
                self.resolve(path)
            self.assertIn("Photos library", str(caught.exception))
        self.assertEqual(list(library.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
