"""index_clips: container creation time only; location and every other tag never leave the file."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.media import index_clips
from tools.media import play_state as cli

LOCATION = "+12.3456-045.6789/"
FAKE_TAGS = ("location", "com.apple.quicktime.location.ISO6709", "make", "model", "title", "comment")


def make_mov(path: Path, **tags: str) -> None:
    metadata = [arg for key, value in tags.items() for arg in ("-metadata", f"{key}={value}")]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1:r=10", "-pix_fmt", "yuv420p",
                    "-movflags", "use_metadata_tags", *metadata, str(path)], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe are required")
class IndexClipsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "private"
        self.root.mkdir()
        fakes = {k: f"FAKE-{i}-{LOCATION}" for i, k in enumerate(FAKE_TAGS)}
        fakes["location"] = LOCATION
        self.clips = {
            "clip-utc": dict(creation_time="2024-03-01T12:00:00Z", **fakes),
            "clip-qt": dict(creation_time="2020-01-01T00:00:00Z", **{"com.apple.quicktime.creationdate": "2024-05-06T07:08:09+0200"}, **fakes),
            "clip-none": dict(**fakes),
            "clip-badtime": dict(creation_time="not a time", **fakes),
        }
        for clip, tags in self.clips.items():
            self.make_clip(clip, tags)
        # a clip whose media is not a video at all
        self.make_clip("clip-corrupt", {}, raw=b"this is not a movie")
        # an export without a receipt
        (self.root / "originals" / "clip-norcpt").mkdir(parents=True)

    def make_clip(self, clip, tags, raw=None):
        folder = self.root / "originals" / clip
        folder.mkdir(parents=True)
        media = folder / f"{clip}.mov"
        if raw is None:
            make_mov(media, **tags)
        else:
            media.write_bytes(raw)
        (folder / ".done").write_text(json.dumps({
            "files": [{"name": media.name, "sha256": "0" * 64}], "video": {"name": media.name, "duration": 1}}))

    def index(self, clip):
        return json.loads((self.root / "analysis" / "index" / f"{clip}.json").read_text())

    def run_cli(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = index_clips.main(["--root", str(self.root), *extra])
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_the_synthetic_clips_really_carry_the_location_tag(self):
        # Guards against a vacuous privacy test: the fixture must contain what must not leak.
        done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json",
                               str(self.root / "originals" / "clip-utc" / "clip-utc.mov")],
                              capture_output=True, text=True, check=True)
        self.assertIn(LOCATION, done.stdout)
        self.assertIn("com.apple.quicktime.location.ISO6709", done.stdout)

    def test_creation_time_is_written_normalised_and_nothing_else(self):
        stdout = self.run_cli()
        self.assertEqual(self.index("clip-utc"), {"uuid": "clip-utc", "captured_at": "2024-03-01T12:00:00+00:00"})
        # the QuickTime creation date (with its offset) wins over the container creation_time
        self.assertEqual(self.index("clip-qt"), {"uuid": "clip-qt", "captured_at": "2024-05-06T05:08:09+00:00"})
        self.assertEqual(self.index("clip-none"), {"uuid": "clip-none", "captured_at": None})
        self.assertEqual(self.index("clip-badtime"), {"uuid": "clip-badtime", "captured_at": None})
        self.assertFalse((self.root / "analysis" / "index" / "clip-corrupt.json").exists())
        self.assertFalse((self.root / "analysis" / "index" / "clip-norcpt.json").exists())
        self.assertEqual(stdout, "index: indexed=2, no_creation_time=2, no_usable_export_receipt=1, probe_failed=1\n")

    def test_location_and_every_other_tag_never_appear_in_any_output(self):
        stdout = self.run_cli()
        files = sorted((self.root / "analysis" / "index").glob("*.json"))
        self.assertEqual(len(files), 4)
        for path in files:
            text = path.read_text()
            self.assertEqual(set(json.loads(text)), {"uuid", "captured_at"})
            for needle in (LOCATION, "12.3456", "location", "FAKE-", "ISO6709", "make", "model", "title", "comment"):
                self.assertNotIn(needle, text)
        for needle in ("12.3456", "location", "FAKE-", "clip-", "2024"):
            self.assertNotIn(needle, stdout)
        self.assertEqual(sorted(p.name for p in (self.root / "analysis").iterdir()), ["index"])

    def test_the_probe_asks_for_exactly_two_tags_and_logs_nothing(self):
        commands = []
        real = subprocess.run

        def spy(cmd, *args, **kwargs):
            commands.append(cmd)
            return real(cmd, *args, **kwargs)
        with mock.patch.object(index_clips.subprocess, "run", spy):
            self.run_cli()
        self.assertGreaterEqual(len(commands), 4)
        for cmd in commands:
            self.assertEqual(cmd[0], "ffprobe")
            self.assertEqual(cmd[cmd.index("-show_entries") + 1], "format_tags=com.apple.quicktime.creationdate,creation_time")
            joined = " ".join(cmd)
            for forbidden in ("-show_format", "-show_streams", "-show_data", "stream_tags", "location", "ISO6709", "gps"):
                self.assertNotIn(forbidden, joined)

    def test_even_if_a_probe_returned_more_tags_only_the_two_are_read(self):
        rogue = json.dumps({"format": {"tags": {"creation_time": "2024-01-02T03:04:05Z", "location": LOCATION,
                                               "com.apple.quicktime.location.ISO6709": LOCATION}}})
        done = subprocess.CompletedProcess([], 0, stdout=rogue, stderr="")
        with mock.patch.object(index_clips.subprocess, "run", return_value=done):
            self.assertEqual(index_clips.captured_at(Path("x.mov")), "2024-01-02T03:04:05+00:00")
        done = subprocess.CompletedProcess([], 0, stdout=json.dumps({"format": {"tags": {"location": LOCATION}}}), stderr="")
        with mock.patch.object(index_clips.subprocess, "run", return_value=done):
            self.assertIsNone(index_clips.captured_at(Path("x.mov")))

    def test_existing_index_files_are_kept_unless_forced(self):
        self.run_cli()
        path = self.root / "analysis" / "index" / "clip-utc.json"
        path.write_text(json.dumps({"uuid": "clip-utc", "captured_at": "1999-01-01T00:00:00+00:00"}))
        self.assertEqual(self.run_cli(), "index: kept=4, no_usable_export_receipt=1, probe_failed=1\n")
        self.assertEqual(self.index("clip-utc")["captured_at"], "1999-01-01T00:00:00+00:00")
        self.run_cli("--force")
        self.assertEqual(self.index("clip-utc")["captured_at"], "2024-03-01T12:00:00+00:00")

    def test_a_planted_symlink_in_the_index_folder_is_not_followed(self):
        index = self.root / "analysis" / "index"
        index.mkdir(parents=True)
        victim = self.root.parent / "victim.json"
        victim.write_text("precious")
        (index / "clip-utc.json").symlink_to(victim)
        self.run_cli("--force")
        self.assertEqual(victim.read_text(), "precious")
        self.assertEqual(self.index("clip-utc")["captured_at"], "2024-03-01T12:00:00+00:00")

    def test_a_symlinked_clip_directory_is_skipped_and_never_probed(self):
        """RS-3: ``originals/<id>/`` that is a link (it could lead into a Photos library or another tree) is not followed."""
        other = self.root.parent / "other-tree" / "clip-linked"
        other.mkdir(parents=True)
        make_mov(other / "clip-linked.mov", creation_time="2001-01-02T00:00:00Z")
        (other / ".done").write_text(json.dumps({
            "files": [{"name": "clip-linked.mov", "sha256": "0" * 64}],
            "video": {"name": "clip-linked.mov", "duration": 1}}))
        before = index_clips.index_root(self.root, True)
        (self.root / "originals" / "clip-linked").symlink_to(other, target_is_directory=True)
        probed = []
        real = index_clips.captured_at

        def spy(media):
            probed.append(Path(media).name)
            return real(media)

        with mock.patch.object(index_clips, "captured_at", spy):
            after = index_clips.index_root(self.root, True)
        self.assertEqual(after, before)                                   # not indexed, not counted as anything
        self.assertNotIn("clip-linked.mov", probed)
        self.assertFalse((self.root / "analysis" / "index" / "clip-linked.json").exists())
        self.assertEqual(self.index("clip-utc")["captured_at"], "2024-03-01T12:00:00+00:00")

    def test_the_pool_merges_the_index_and_chronological_mode_orders_by_it(self):
        self.run_cli()
        (self.root / "analysis" / "tags").mkdir(parents=True)
        for clip in ("clip-utc", "clip-qt", "clip-none"):
            (self.root / "analysis" / "tags" / f"{clip}.json").write_text(json.dumps({"uuid": clip, "analysis": None}))
            (self.root / "originals" / clip / ".done").write_text(json.dumps({
                "files": [{"name": f"{clip}.mov", "sha256": clip.encode().hex().ljust(64, "0")[:64]}],
                "video": {"name": f"{clip}.mov", "duration": 1}}))
        pool, skipped = cli.load_pool(self.root)
        stamps = {r["id"]: r.get("captured_at") for r in pool}
        self.assertEqual(stamps, {"clip-none": None, "clip-qt": "2024-05-06T05:08:09+00:00",
                                  "clip-utc": "2024-03-01T12:00:00+00:00"})
        self.assertNotIn("captured_at", next(r for r in pool if r["id"] == "clip-none"))
        self.assertEqual(sum(skipped.values()), 0)

    def test_roots_are_guarded_like_every_other_command(self):
        with self.assertRaises(SystemExit):
            index_clips.main(["--root", str(self.root.parent / "missing")])
        with self.assertRaises(SystemExit):
            index_clips.main(["--root", str(self.root.parent / "Lib.photoslibrary")])


class IndexDestinationGuardTests(unittest.TestCase):
    """The index is written only into a real analysis/index/ directory inside the guarded root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name).resolve()
        self.root = tmp / "private"
        folder = self.root / "originals" / "clip-a"
        folder.mkdir(parents=True)
        (folder / "clip-a.mov").write_bytes(b"x")
        (folder / ".done").write_text(json.dumps({"files": [{"name": "clip-a.mov", "sha256": "0" * 64}],
                                                  "video": {"name": "clip-a.mov", "duration": 1}}))
        self.repo = tmp / "other-repo"                      # a second tree that looks like a Git working tree
        (self.repo / ".git").mkdir(parents=True)
        (self.repo / "data").mkdir()
        (self.repo / "data" / "clip-a.json").write_text("tracked")
        self.snapshot = self.listing(self.repo)
        patcher = mock.patch.object(index_clips, "captured_at", return_value="2024-03-01T12:00:00+00:00")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def listing(folder):
        return sorted((str(p.relative_to(folder)), p.read_text() if p.is_file() else None) for p in folder.rglob("*"))

    def refused(self, *, force):
        for flag in (force, not force):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, flag)
            self.assertEqual(self.listing(self.repo), self.snapshot)

    def test_a_clean_root_is_indexed(self):
        self.assertEqual(index_clips.index_root(self.root)["indexed"], 1)
        self.assertTrue((self.root / "analysis" / "index" / "clip-a.json").is_file())

    def test_a_symlinked_index_directory_into_another_tree_is_refused_with_and_without_force(self):
        (self.root / "analysis").mkdir()
        (self.root / "analysis" / "index").symlink_to(self.repo / "data", target_is_directory=True)
        self.refused(force=False)

    def test_a_symlinked_analysis_directory_is_refused(self):
        (self.root / "analysis").symlink_to(self.repo, target_is_directory=True)
        self.refused(force=True)

    def test_a_symlinked_originals_directory_is_refused(self):
        moved = self.root.parent / "moved"
        (self.root / "originals").rename(moved)
        (self.root / "originals").symlink_to(moved, target_is_directory=True)
        for flag in (False, True):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, flag)
        self.assertFalse((self.root / "analysis").exists())

    def test_an_index_that_is_not_a_real_directory_is_refused(self):
        (self.root / "analysis").mkdir()
        (self.root / "analysis" / "index").write_text("a file")
        with self.assertRaises(index_clips.play_guard.GuardError):
            index_clips.index_root(self.root)

    def test_an_index_directory_that_holds_a_git_directory_is_refused(self):
        (self.root / "analysis" / "index" / ".git").mkdir(parents=True)
        with self.assertRaises(index_clips.play_guard.GuardError):
            index_clips.index_root(self.root, True)
        self.assertFalse((self.root / "analysis" / "index" / "clip-a.json").exists())
        shutil.rmtree(self.root / "analysis" / "index" / ".git")
        (self.root / "analysis" / ".git").write_text("gitdir: elsewhere")               # a worktree-style file
        with self.assertRaises(index_clips.play_guard.GuardError):
            index_clips.index_root(self.root, True)

    def test_an_index_that_resolves_elsewhere_is_refused_even_when_the_link_check_is_bypassed(self):
        (self.root / "analysis").mkdir()
        (self.root / "analysis" / "index").symlink_to(self.repo / "data", target_is_directory=True)
        with mock.patch.object(index_clips.os.path, "islink", return_value=False):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, True)
        self.assertEqual(self.listing(self.repo), self.snapshot)


def git_here(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_SYSTEM": os.devnull})


class IndexEveryTargetIsGuardedTests(unittest.TestCase):
    """XS-2: every file index_clips writes passes through the same guard as ``--out``, not only the root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.root = self.tmp / "outside" / "root"                    # outside every Git tree
        for clip in ("clip-a", "clip-b", "clip-c"):
            folder = self.root / "originals" / clip
            folder.mkdir(parents=True)
            (folder / f"{clip}.mov").write_bytes(b"x")
            (folder / ".done").write_text(json.dumps({"files": [{"name": f"{clip}.mov", "sha256": "0" * 64}],
                                                      "video": {"name": f"{clip}.mov", "duration": 1}}))
        self.checkout = self.tmp / "checkout"                        # a real repository with a tracked source directory
        (self.checkout / "src" / "pkg").mkdir(parents=True)
        (self.checkout / "src" / "pkg" / "mod.py").write_text("tracked\n")
        git_here("init", "-q", cwd=self.checkout)
        git_here("add", "-A", cwd=self.checkout)
        git_here("-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "-m", "m", cwd=self.checkout)

    def status(self):
        done = subprocess.run(["git", "-C", str(self.checkout), "status", "--porcelain", "-uall"],
                              capture_output=True, text=True, check=True)
        return done.stdout

    def probe_that(self, action):
        """Run the index with ``captured_at`` calling ``action`` the first time it is asked (a mid-run change)."""
        calls = []

        def fake(media):
            if not calls:
                action()
            calls.append(media)
            return "2024-03-01T12:00:00+00:00"
        with mock.patch.object(index_clips, "captured_at", side_effect=fake):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, True)

    def test_a_symlinked_index_directory_into_a_tracked_directory_of_a_checkout_is_refused(self):
        (self.root / "analysis").mkdir()
        (self.root / "analysis" / "index").symlink_to(self.checkout / "src" / "pkg", target_is_directory=True)
        with mock.patch.object(index_clips, "captured_at", return_value="2024-03-01T12:00:00+00:00"):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, True)
        self.assertEqual(self.status(), "")

    def test_a_symlinked_analysis_directory_into_a_checkout_is_refused(self):
        (self.root / "analysis").symlink_to(self.checkout / "src", target_is_directory=True)
        with mock.patch.object(index_clips, "captured_at", return_value="2024-03-01T12:00:00+00:00"):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(self.root, True)
        self.assertEqual(self.status(), "")

    def test_an_index_directory_swapped_for_a_link_after_the_first_check_is_caught_at_the_write(self):
        index = self.root / "analysis" / "index"
        index_clips.index_root(self.root)                            # creates a real index directory first
        for leftover in index.iterdir():
            leftover.unlink()

        def swap():
            index.rmdir()
            index.symlink_to(self.checkout / "src" / "pkg", target_is_directory=True)
        self.probe_that(swap)
        self.assertEqual(self.status(), "")
        self.assertEqual(sorted(p.name for p in (self.checkout / "src" / "pkg").iterdir()), ["mod.py"])

    def test_an_analysis_directory_swapped_for_a_link_after_the_first_check_is_caught_at_the_write(self):
        analysis = self.root / "analysis"
        index_clips.index_root(self.root)
        shutil.rmtree(analysis)
        index_clips.index_root(self.root)
        shutil.rmtree(analysis / "index")

        def swap():
            shutil.rmtree(analysis)
            analysis.symlink_to(self.checkout / "src", target_is_directory=True)
        self.probe_that(swap)
        self.assertEqual(self.status(), "")
        self.assertFalse((self.checkout / "src" / "index").exists())

    def test_an_index_directory_swapped_for_a_link_into_a_photos_library_is_caught_at_the_write(self):
        library = self.tmp / "Real.photoslibrary" / "resources"
        library.mkdir(parents=True)
        index = self.root / "analysis" / "index"
        index_clips.index_root(self.root)
        for leftover in index.iterdir():
            leftover.unlink()

        def swap():
            index.rmdir()
            index.symlink_to(library, target_is_directory=True)
        self.probe_that(swap)
        self.assertEqual(list(library.iterdir()), [])

    def test_a_root_inside_an_ignored_directory_of_a_working_tree_is_not_written_to(self):
        repo = self.tmp / "other-tree"
        repo.mkdir()
        git_here("init", "-q", cwd=repo)
        (repo / ".gitignore").write_text("/ignored/\n")
        moved = repo / "ignored" / "root"
        shutil.copytree(self.root, moved)
        self.assertEqual(index_clips.play_guard.resolve_root(moved, require_tags=False), moved)   # the root guard accepts it
        with mock.patch.object(index_clips, "captured_at", return_value="2024-03-01T12:00:00+00:00"):
            with self.assertRaises(index_clips.play_guard.GuardError):
                index_clips.index_root(moved, True)
        self.assertFalse((moved / "analysis" / "index").exists())

    def test_the_guarded_target_is_the_one_written(self):
        with mock.patch.object(index_clips, "captured_at", return_value="2024-03-01T12:00:00+00:00"), \
                mock.patch.object(index_clips.play_guard, "resolve_out", wraps=index_clips.play_guard.resolve_out) as spy:
            self.assertEqual(index_clips.index_root(self.root, True)["indexed"], 3)
        guarded = {call.args[0].name for call in spy.call_args_list}
        self.assertTrue({"clip-a.json", "clip-b.json", "clip-c.json"} <= guarded)


if __name__ == "__main__":
    unittest.main()
