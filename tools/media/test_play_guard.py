"""Path guard: no case-variant, alias, sibling-worktree or Photos-library bypass; safe atomic writes."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.media import play_guard as guard
from tools.paths import REPO_ROOT, WORK_DIR


def case_variant(path: Path) -> Path | None:
    """The same existing location spelled with different letter case, or None on a case-sensitive volume."""
    parts = list(path.parts)
    for index in range(len(parts) - 1, 0, -1):
        swapped = parts[index].swapcase()
        if swapped == parts[index]:
            continue
        candidate = Path(*parts[:index], swapped, *parts[index + 1:])
        if str(candidate) != str(path) and os.path.exists(candidate):
            try:
                if os.path.samestat(os.stat(candidate), os.stat(path)):
                    return candidate
            except OSError:
                pass
    return None


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class OutputGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.assertFalse(self.tmp.is_relative_to(REPO_ROOT.resolve()))

    def refused(self, path):
        existed = Path(path).exists()
        before = Path(path).read_bytes() if existed and Path(path).is_file() else None
        with self.assertRaises(SystemExit):
            guard.resolve_out(path)
        self.assertEqual(Path(path).exists(), existed)                  # nothing was created
        if before is not None:
            self.assertEqual(Path(path).read_bytes(), before)

    def test_work_area_and_plain_outside_locations_are_allowed(self):
        self.assertEqual(guard.resolve_out(WORK_DIR / "x.json"), (WORK_DIR / "x.json").resolve())
        self.assertEqual(guard.resolve_out(self.tmp / "x.json"), self.tmp / "x.json")
        self.assertEqual(guard.resolve_out(self.tmp / "not" / "yet" / "there.json"), self.tmp / "not" / "yet" / "there.json")

    def test_everything_else_in_the_checkout_is_refused(self):
        for inside in (REPO_ROOT / "x.json", REPO_ROOT / "docs" / "x.json", REPO_ROOT / "var" / "x.json",
                       REPO_ROOT / "var" / "site" / "x.json", WORK_DIR / ".." / "x.json", REPO_ROOT / "src" / "x.json",
                       REPO_ROOT / "ace-manifest.json"):
            with self.subTest(path=str(inside.relative_to(REPO_ROOT))):
                self.refused(inside)

    def test_the_file_name_must_be_a_visible_json_name(self):
        for name in ("x.txt", ".hidden.json", "x"):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                guard.resolve_out(self.tmp / name)

    def test_a_case_variant_of_the_checkout_path_cannot_write_into_it(self):
        variant = case_variant(REPO_ROOT)
        if variant is None:
            self.skipTest("this volume is case-sensitive: a case-variant path does not exist")
        for tail in ("docs/x.json", "ace-manifest.json", "var/x.json", "src/x.json"):
            with self.subTest(tail=tail):
                self.refused(variant / tail)
        self.assertEqual(guard.resolve_out(variant / "var" / "work" / "x.json").name, "x.json")   # the work area is still fine

    def test_an_alias_of_the_checkout_cannot_write_into_it(self):
        link = self.tmp / "alias"
        link.symlink_to(REPO_ROOT, target_is_directory=True)
        for tail in ("docs/x.json", "x.json", "var/x.json"):
            self.refused(link / tail)
        docs = self.tmp / "docs-link"
        docs.symlink_to(REPO_ROOT / "docs", target_is_directory=True)
        self.refused(docs / "x.json")

    def test_a_sibling_worktree_or_any_other_repository_is_refused(self):
        other = self.tmp / "other-worktree"
        (other / "docs").mkdir(parents=True)
        (other / ".git").write_text("gitdir: /nowhere\n")                  # a worktree marks itself with a .git file
        repo = self.tmp / "other-repo"
        (repo / ".git").mkdir(parents=True)
        for target in (other / "docs" / "x.json", other / "x.json", repo / "deep" / "er" / "x.json"):
            with self.subTest(path=target.name):
                self.refused(target)
        sibling = REPO_ROOT.parent / "simvltanea"
        if (sibling / ".git").exists() and not os.path.samestat(os.stat(sibling), os.stat(REPO_ROOT)):
            self.refused(sibling / "docs" / "x.json")
        # a plain directory beside them is fine
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(guard.resolve_out(plain / "x.json"), plain / "x.json")

    def test_only_this_checkouts_work_area_is_exempt_not_any_directory_named_work(self):
        # The exemption is an identity (samestat) match with this checkout's var/work, never a name match.
        repo = self.tmp / "other-repo"
        (repo / ".git").mkdir(parents=True)
        for rel in ("var/work", "docs/work", f"x/{WORK_DIR.name}", WORK_DIR.name):
            (repo / rel).mkdir(parents=True, exist_ok=True)
            for tail in ("state.json", "new/deep.json"):
                with self.subTest(path=f"{rel}/{tail}"):
                    self.refused(repo / rel / tail)
        self.assertEqual(guard.resolve_out(WORK_DIR / "x.json"), (WORK_DIR / "x.json").resolve())   # the real one still works

    def test_a_checkout_without_a_git_directory_is_still_refused_by_identity(self):
        """RS-5: a source export or copy of the checkout has no ``.git``, so only the identity clause
        (``_same(ancestor, REPO_ROOT)``) keeps ``--out`` out of docs/ and src/; var/work/ stays allowed."""
        checkout = self.tmp / "export"
        work = checkout / WORK_DIR.relative_to(REPO_ROOT)
        for directory in (work, checkout / "docs", checkout / "src"):
            directory.mkdir(parents=True)
        self.assertFalse(any(guard._has_git(ancestor) for ancestor in (checkout, *checkout.parents)),
                         "the temporary directory must not sit inside a Git working tree")
        with mock.patch.object(guard, "REPO_ROOT", checkout), mock.patch.object(guard, "WORK_DIR", work):
            for target in (checkout / "docs" / "x.json", checkout / "src" / "x.json", checkout / "x.json"):
                with self.subTest(path=str(target.relative_to(checkout))):
                    self.refused(target)
            self.assertEqual(guard.resolve_out(work / "x.json"), (work / "x.json").resolve())

    def test_a_directory_named_like_the_work_area_inside_this_checkout_is_refused_in_a_copy_of_the_layout(self):
        """The same case as above for THIS checkout, built in a temporary copy of its layout so that nothing is
        ever created in the real checkout (a crash or a concurrent run cannot leave a stray directory behind)."""
        checkout = self.tmp / "checkout"
        (checkout / ".git").mkdir(parents=True)
        work = checkout / WORK_DIR.relative_to(REPO_ROOT)
        lookalike = checkout / "docs" / WORK_DIR.name
        for directory in (work, lookalike):
            directory.mkdir(parents=True)
        real_docs = REPO_ROOT / "docs" / WORK_DIR.name
        existed = real_docs.exists()
        made = []
        real_mkdir = Path.mkdir

        def spy(path, *args, **kwargs):
            made.append(Path(path))
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(guard, "REPO_ROOT", checkout), mock.patch.object(guard, "WORK_DIR", work), \
                mock.patch.object(Path, "mkdir", spy):
            self.refused(lookalike / "state.json")
            self.refused(lookalike / "new" / "deep.json")
            self.assertEqual(guard.resolve_out(work / "x.json"), (work / "x.json").resolve())   # the copy's own work area
            self.assertEqual(guard.resolve_out(work / "new" / "x.json"), (work / "new" / "x.json").resolve())
        self.assertEqual(real_docs.exists(), existed)
        self.assertFalse([p for p in made if p.is_relative_to(REPO_ROOT)])    # nothing was made in the real checkout

    def test_a_spelling_that_resolves_outside_every_repository_is_still_refused_when_it_passes_through_one(self):
        # The lexical path is checked as well as the resolved one: a link INSIDE a repository that points OUT of it.
        repo = self.tmp / "repo"
        (repo / ".git").mkdir(parents=True)
        outside = self.tmp / "outside"
        outside.mkdir()
        (repo / "link-out").symlink_to(outside, target_is_directory=True)
        self.assertEqual(guard.resolve_out(outside / "state.json"), outside / "state.json")     # resolved form is fine
        self.refused(repo / "link-out" / "state.json")
        self.assertEqual(list(outside.iterdir()), [])

    def test_photos_library_packages_are_refused_in_any_case_and_through_links(self):
        for name in ("Lib.photoslibrary", "LIB.PHOTOSLIBRARY", "x.PhotosLibrary"):
            self.refused(self.tmp / name / "resources" / "x.json")
        package = self.tmp / "Real.photoslibrary"
        package.mkdir()
        link = self.tmp / "innocent"
        link.symlink_to(package, target_is_directory=True)
        self.refused(link / "x.json")
        self.assertEqual(list(package.iterdir()), [])

    def test_unicode_case_fold_aliases_of_the_library_suffix_are_refused(self):
        # U+017F (LATIN SMALL LETTER LONG S) folds to "s" under Unicode case folding, the rule the default macOS
        # volume applies: "X.photoſlibrary" opens "X.photoslibrary", but str.lower() leaves the character unchanged.
        for name in ("X.photoſlibrary", "X.PhotoſLibrary", "x.PHOTOſLIBRARY"):
            with self.subTest(name=name):
                self.assertTrue(guard._has_library_component(self.tmp / name / "inner"))
                self.refused(self.tmp / name / "resources" / "x.json")
                with self.assertRaises(SystemExit):
                    guard.resolve_root(self.tmp / name)

    def test_the_alias_really_reaches_the_library_on_a_volume_that_folds_unicode_case(self):
        library = self.tmp / "Real.photoslibrary"
        library.mkdir()
        (library / "marker").write_text("x")
        alias = self.tmp / "Real.photoſlibrary"
        if not (alias / "marker").exists():
            self.skipTest("this volume does not alias Unicode case folds")
        self.refused(alias / "resources" / "x.json")
        with self.assertRaises(SystemExit):
            guard.resolve_root(alias)
        self.assertEqual(sorted(entry.name for entry in library.iterdir()), ["marker"])


class RootGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def make_root(self, base: Path) -> Path:
        (base / "analysis" / "tags").mkdir(parents=True)
        return base

    def test_a_plain_directory_with_tags_is_a_valid_root(self):
        root = self.make_root(self.tmp / "private")
        self.assertEqual(guard.resolve_root(root), root)

    def test_missing_files_photos_libraries_and_the_checkout_are_refused(self):
        for bad in (self.tmp / "missing", self.tmp, REPO_ROOT, REPO_ROOT / "docs", self.tmp / "Library.photoslibrary" / "x",
                    self.tmp / "LIBRARY.PHOTOSLIBRARY"):
            with self.subTest(root=str(bad)), self.assertRaises(SystemExit):
                guard.resolve_root(bad)
        package = self.make_root(self.tmp / "Real.photoslibrary")
        link = self.tmp / "innocent"
        link.symlink_to(package, target_is_directory=True)
        with self.assertRaises(SystemExit):
            guard.resolve_root(link)

    def test_a_root_inside_a_git_working_tree_must_be_ignored_by_git(self):
        repo = self.tmp / "work-tree"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        (repo / ".gitignore").write_text("/ignored/\n")
        tracked = self.make_root(repo / "tracked")
        ignored = self.make_root(repo / "ignored")
        with self.assertRaises(SystemExit):
            guard.resolve_root(tracked)
        self.assertEqual(guard.resolve_root(ignored), ignored)

    def test_git_environment_variables_cannot_redirect_the_ignore_check(self):
        # XS-6: GIT_DIR/GIT_WORK_TREE pointing at a repository whose info/exclude is "*" made every path look ignored.
        checkout = self.tmp / "checkout"
        (checkout / "src").mkdir(parents=True)
        git("init", "-q", cwd=checkout)
        (checkout / "src" / "mod.py").write_text("tracked\n")
        evil = self.tmp / "evil.git"
        git("init", "-q", "--bare", str(evil), cwd=self.tmp)
        (evil / "info" / "exclude").write_text("*\n")
        tracked = self.make_root(checkout / "src" / "private")
        with self.assertRaises(SystemExit):
            guard.resolve_root(tracked)                                  # baseline: refused without the variables
        pair = {"GIT_DIR": str(evil), "GIT_WORK_TREE": str(checkout)}                  # the pair the finding used
        redirects = [pair, {"GIT_DIR": str(evil)}, {"GIT_COMMON_DIR": str(evil)}, {"GIT_INDEX_FILE": str(evil / "index")},
                     {"GIT_CEILING_DIRECTORIES": str(self.tmp)}, {"GIT_NAMESPACE": "x"},
                     {"GIT_CONFIG_PARAMETERS": "'core.excludesfile=/dev/null'", **pair}]
        for variables in redirects:
            with self.subTest(variables=sorted(variables)), mock.patch.dict(os.environ, variables):
                with self.assertRaises(SystemExit):
                    guard.resolve_root(tracked)
        ignored = self.make_root(checkout / "ignored-root")
        (checkout / ".gitignore").write_text("/ignored-root/\n")
        with mock.patch.dict(os.environ, pair):
            self.assertEqual(guard.resolve_root(ignored), ignored)         # a genuinely ignored root still passes

    def test_a_sibling_worktree_is_checked_the_same_way(self):
        repo = self.tmp / "main-tree"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        (repo / "f").write_text("x")
        git("-c", "user.email=a@b", "-c", "user.name=n", "add", "f", cwd=repo)
        git("-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "-m", "m", cwd=repo)
        sibling = self.tmp / "sibling-tree"
        git("worktree", "add", "-q", str(sibling), "-b", "side", cwd=repo)
        with self.assertRaises(SystemExit):
            guard.resolve_root(self.make_root(sibling / "analysis-holder"))
        (sibling / ".gitignore").write_text("/var/\n")
        self.assertEqual(guard.resolve_root(self.make_root(sibling / "var" / "root")), sibling / "var" / "root")

    def test_the_checkouts_own_ignored_var_area_is_allowed_and_a_case_variant_does_not_bypass_it(self):
        root = self.make_root(WORK_DIR / f"guard-root-{os.getpid()}")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(root)]))
        self.assertEqual(guard.resolve_root(root), root.resolve())
        variant = case_variant(REPO_ROOT)
        if variant is not None:
            with self.assertRaises(SystemExit):
                guard.resolve_root(variant / "docs")


class WriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def test_writes_atomically_and_privately(self):
        out = self.tmp / "sub" / "state.json"
        guard.write_private_file(out, b"hello", False)
        self.assertEqual(out.read_bytes(), b"hello")
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
        self.assertEqual([p.name for p in out.parent.iterdir()], ["state.json"])          # no temp file left

    def test_an_existing_file_is_kept_without_force_and_replaced_with_it(self):
        out = self.tmp / "state.json"
        out.write_bytes(b"old")
        with self.assertRaises(SystemExit):
            guard.write_private_file(out, b"new", False)
        self.assertEqual(out.read_bytes(), b"old")
        guard.write_private_file(out, b"new", True)
        self.assertEqual(out.read_bytes(), b"new")

    def test_a_planted_temp_name_symlink_is_never_followed(self):
        victim = self.tmp / "victim.json"
        victim.write_bytes(b"precious")
        for planted in (".state.json.tmp", ".state.json.abc123.tmp"):
            (self.tmp / planted).symlink_to(victim)
        out = self.tmp / "state.json"
        guard.write_private_file(out, b"payload", False)
        guard.write_private_file(out, b"payload2", True)
        self.assertEqual(victim.read_bytes(), b"precious")
        self.assertFalse(out.is_symlink())
        self.assertEqual(out.read_bytes(), b"payload2")
        self.assertTrue((self.tmp / ".state.json.tmp").is_symlink())                      # untouched

    def test_a_symlink_at_the_target_name_is_replaced_not_written_through(self):
        victim = self.tmp / "victim.json"
        victim.write_bytes(b"precious")
        out = self.tmp / "state.json"
        out.symlink_to(victim)
        with self.assertRaises(SystemExit):
            guard.write_private_file(out, b"x", False)
        guard.write_private_file(out, b"x", True)
        self.assertEqual(victim.read_bytes(), b"precious")
        self.assertFalse(out.is_symlink())
        dangling = self.tmp / "dangling.json"
        dangling.symlink_to(self.tmp / "nowhere")
        with self.assertRaises(SystemExit):
            guard.write_private_file(dangling, b"x", False)
        self.assertFalse((self.tmp / "nowhere").exists())

    def test_a_target_that_appears_during_the_write_is_not_overwritten(self):
        out = self.tmp / "state.json"
        real = os.link

        def racing(src, dst, *args, **kwargs):
            Path(dst).write_bytes(b"winner")
            return real(src, dst, *args, **kwargs)
        with mock.patch.object(guard.os, "link", racing), self.assertRaises(SystemExit):
            guard.write_private_file(out, b"loser", False)
        self.assertEqual(out.read_bytes(), b"winner")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["state.json"])


if __name__ == "__main__":
    unittest.main()
