"""Exercise the Photos album exporter with fake osascript, ffprobe, route and ifconfig.

No Photos.app, no network and no real media: ``subprocess.run`` is replaced by FakeHost.
"""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from tools.media import export_photos_album as exporter
from tools.paths import REPO_ROOT

HOTSPOT_ROUTE = "   route to: default\n    gateway: 172.20.10.1\n  interface: en0\n"
LAN_ROUTE = "   route to: default\n    gateway: 192.168.1.1\n  interface: en0\n"
PRIVATE_NAME = "FullSizeRender"


def uid(n: int) -> str:
    return f"{n:08x}-0000-4000-8000-000000000000"


def pid(n: int) -> str:
    return f"{uid(n)}/L0/001"


def live_photo(tag: bytes) -> list[tuple[str, bytes]]:
    """What Photos writes for a typical Live Photo; the names are deliberately non-unique."""
    return [(f"{PRIVATE_NAME}.JPG", b"still-" + tag), (f"{PRIVATE_NAME}.MOV", b"movie-" + tag * 100)]


class FakeHost:
    """Replacement for ``subprocess.run`` covering osascript, ffprobe, route and ifconfig."""

    def __init__(self, assets=None, album_ids=None):
        self.assets = assets or {}
        self.album_ids = album_ids or []
        self.fail_times: dict[str, int] = {}
        self.fail_stderr = f"execution error: /Users/someone/Pictures/{PRIVATE_NAME}.MOV can't be exported. (-1712)"
        self.on_export = None
        self.route = LAN_ROUTE
        self.ifconfig = "en0: flags=8863<UP>\n\toptions=400\n"
        self.route_error: Exception | None = None
        self.calls: list[list[str]] = []
        self.exports: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, command, **kwargs):
        with self._lock:
            self.calls.append(list(command))
        name = pathlib.Path(command[0]).name
        if "osascript" in command:
            return self.osascript(command)
        if name == "ffprobe":
            return self.ffprobe(command)
        if name == "route":
            if self.route_error:
                raise self.route_error
            return subprocess.CompletedProcess(command, 0, self.route, "")
        if name == "ifconfig":
            return subprocess.CompletedProcess(command, 0, self.ifconfig, "")
        raise AssertionError(f"unexpected command {command[:2]}")

    def osascript(self, command):
        if "export {m}" not in " ".join(command):
            return subprocess.CompletedProcess(command, 0, "\n".join(self.album_ids) + "\nnoise line\n", "")
        photos_id, folder = command[-2], pathlib.Path(command[-1])
        with self._lock:
            self.exports.append(photos_id)
            remaining = self.fail_times.get(photos_id, 0)
            if remaining:
                self.fail_times[photos_id] = remaining - 1
        if self.on_export:
            self.on_export(photos_id)
        if remaining:
            return subprocess.CompletedProcess(command, 1, "", self.fail_stderr)
        for file_name, data in self.assets.get(photos_id, []):
            (folder / file_name).write_bytes(data)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    def ffprobe(self, command):
        data = pathlib.Path(command[-1]).read_bytes()
        if data.startswith(b"corrupt"):
            return subprocess.CompletedProcess(command, 1, "", "invalid data")
        facts = {"streams": [{"codec_name": "hevc", "width": 1080, "height": 1920, "r_frame_rate": "30/1"}],
                 "format": {"duration": "1.8"}}
        return subprocess.CompletedProcess(command, 0, json.dumps(facts), "")


class ExporterTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name).resolve() / "live-photos"
        self.host = FakeHost()
        for patcher in (mock.patch.object(subprocess, "run", self.host),
                        mock.patch.object(exporter, "preflight"),
                        mock.patch.object(os, "nice")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, *extra, platform="linux"):
        out = io.StringIO()
        with mock.patch.object(sys, "platform", platform), contextlib.redirect_stdout(out):
            code = exporter.main(["--root", str(self.root), "--workers", "1", *extra])
        self.output = out.getvalue()
        return code

    def seed(self, assets: dict[int, list[tuple[str, bytes]]]):
        self.host.assets = {pid(n): files for n, files in assets.items()}
        self.host.album_ids = [pid(n) for n in assets]

    def folder(self, n: int) -> pathlib.Path:
        return self.root / "originals" / uid(n)

    def names(self, n: int) -> set[str]:
        return {p.name for p in self.folder(n).iterdir()}

    def log_lines(self, name: str) -> list[dict]:
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class ScriptTests(unittest.TestCase):
    def test_export_script_runs_inside_a_long_timeout_block_and_takes_argv(self):
        command = exporter.osascript_command(exporter.export_script_lines(3600), pid(1), "/tmp/out")
        self.assertEqual(command[0], "osascript")
        self.assertEqual(command[-2:], [pid(1), "/tmp/out"])
        lines = [command[i + 1] for i, token in enumerate(command[:-2]) if token == "-e"]
        self.assertEqual(command[1::2][: len(lines)], ["-e"] * len(lines))
        script = "\n".join(lines)
        self.assertIn("with timeout of 3600 seconds", script)
        self.assertIn("with using originals", script)
        self.assertNotIn(pid(1), script)  # ids travel as argv, never interpolated into the script
        self.assertLess(script.index("with timeout of"), script.index('tell application "Photos"'))

    def test_timeout_and_launcher_are_applied(self):
        command = exporter.osascript_command(exporter.export_script_lines(900), "a", "b", launcher=("host", "run", "--"))
        self.assertEqual(command[:4], ["host", "run", "--", "osascript"])
        self.assertIn("with timeout of 900 seconds", command)

    def test_no_applescript_files_are_shipped(self):
        self.assertEqual(list((REPO_ROOT / "tools").rglob("*.applescript")), [])


class ExportLayoutTests(ExporterTestCase):
    def test_one_folder_per_uuid_even_when_original_names_collide(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.names(1), {f"{uid(1)}.jpg", f"{uid(1)}.mov", ".done"})
        self.assertEqual(self.names(2), {f"{uid(2)}.jpg", f"{uid(2)}.mov", ".done"})
        self.assertEqual((self.folder(1) / f"{uid(1)}.mov").read_bytes(), b"movie-" + b"a" * 100)
        self.assertEqual((self.folder(2) / f"{uid(2)}.mov").read_bytes(), b"movie-" + b"b" * 100)

    def test_primary_video_and_still_are_renamed_and_the_rest_become_extras(self):
        self.seed({1: [("IMG_0001.HEIC", b"still"), ("IMG_0001.MOV", b"movie-1"), ("IMG_0002.JPG", b"other-still"),
                       ("IMG_0002.MOV", b"movie-2"), ("IMG_0001.AAE", b"sidecar")]})
        self.assertEqual(self.run_main(), 0)
        # sorted order: IMG_0001.AAE(0) .HEIC(1) .MOV(2) IMG_0002.JPG(3) .MOV(4); first non-video is the AAE sidecar
        self.assertEqual(self.names(1), {f"{uid(1)}.aae", f"{uid(1)}.mov", f"{uid(1)}.extra1.heic",
                                         f"{uid(1)}.extra3.jpg", f"{uid(1)}.extra4.mov", ".done"})
        self.assertEqual((self.folder(1) / f"{uid(1)}.mov").read_bytes(), b"movie-1")

    def test_renaming_never_overwrites_a_file_whose_name_equals_another_final_name(self):
        lower = "ffffffff-0000-4000-8000-000000000000"
        photos_id = f"{lower}/L0/001"
        files = [("A.mov", b"movie-A"), ("B.jpg", b"still-B"), ("C.mov", b"movie-C"),
                 (f"{lower}.extra2.mov", b"movie-D")]
        self.host.assets = {photos_id: files}
        self.host.album_ids = [photos_id]
        self.assertEqual(self.run_main(), 0)
        folder = self.root / "originals" / lower
        contents = sorted(p.read_bytes() for p in folder.iterdir() if not p.name.startswith("."))
        self.assertEqual(contents, sorted(data for _, data in files))
        receipt = json.loads((folder / ".done").read_text())
        self.assertEqual(len(receipt["files"]), 4)
        self.assertEqual(len({entry["name"] for entry in receipt["files"]}), 4)

    def test_receipt_records_sizes_sha256_and_ffprobe_facts_but_no_original_names(self):
        self.seed({1: live_photo(b"a")})
        self.assertEqual(self.run_main(), 0)
        receipt = json.loads((self.folder(1) / ".done").read_text())
        self.assertEqual(receipt["uuid"], uid(1))
        self.assertEqual(receipt["photos_id"], pid(1))
        self.assertEqual(receipt["original_file_count"], 2)
        by_name = {entry["name"]: entry for entry in receipt["files"]}
        for name, entry in by_name.items():
            data = (self.folder(1) / name).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(entry["bytes"], len(data))
        self.assertEqual(receipt["video"]["name"], f"{uid(1)}.mov")
        self.assertEqual((receipt["video"]["codec"], receipt["video"]["width"], receipt["video"]["height"]),
                         ("hevc", 1080, 1920))
        self.assertAlmostEqual(receipt["video"]["duration"], 1.8)
        self.assertEqual(self.log_lines("export-manifest.jsonl"), [receipt])
        self.assertFalse((self.folder(1) / ".done.tmp").exists())

    def test_nothing_but_uuids_is_logged_or_recorded(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.host.fail_times[pid(2)] = 1
        self.run_main("--rounds", "1")
        everything = self.output + "".join(p.read_text() for p in self.root.glob("*.json*"))
        everything += (self.folder(1) / ".done").read_text()
        self.assertNotIn(PRIVATE_NAME, everything)
        self.assertNotIn("/Users/", everything)
        self.assertNotIn(str(self.root), everything)
        self.assertNotIn(str(self.root.parent), self.output)

    def test_missing_video_and_failed_probe_are_failures_that_name_nothing(self):
        self.seed({1: [(f"{PRIVATE_NAME}.JPG", b"still-only")], 2: [("x.MOV", b"corrupt!")]})
        self.assertEqual(self.run_main("--rounds", "1"), 1)
        details = {line["uuid"]: line["detail"] for line in self.log_lines("export-failures.jsonl")}
        self.assertEqual(details[uid(1)], "no paired video exported (1 files)")
        self.assertEqual(details[uid(2)], "exported video failed ffprobe")
        self.assertFalse((self.folder(1) / ".done").exists())
        self.assertFalse((self.folder(2) / ".done").exists())

    def test_malformed_ids_are_refused_before_touching_the_filesystem(self):
        settings = exporter.ExportSettings(root=self.root)
        status, _uuid, detail = exporter.export_one(settings, "../../etc/passwd/L0/001")
        self.assertEqual((status, detail), ("fail", "malformed Photos media item id"))
        self.assertFalse((self.root / "originals").exists())
        self.assertEqual(self.host.exports, [])


class ResumeAndRetryTests(ExporterTestCase):
    def test_resume_skips_finished_items_and_exports_the_rest(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.assertEqual(self.run_main("--limit", "1"), 0)
        self.assertEqual(self.host.exports, [pid(1)])
        before = (self.folder(1) / ".done").read_text()
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.host.exports, [pid(1), pid(2)])  # item 1 was not exported again
        self.assertEqual((self.folder(1) / ".done").read_text(), before)
        self.assertEqual(len(self.log_lines("export-manifest.jsonl")), 2)

    def test_interrupted_item_without_receipt_is_redone_from_scratch(self):
        self.seed({1: live_photo(b"a")})
        self.folder(1).mkdir(parents=True)
        (self.folder(1) / "stale-partial.MOV").write_bytes(b"partial")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.names(1), {f"{uid(1)}.jpg", f"{uid(1)}.mov", ".done"})

    def test_failed_items_are_retried_in_later_rounds(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.host.fail_times[pid(2)] = 2
        self.assertEqual(self.run_main("--rounds", "3"), 0)
        failures = self.log_lines("export-failures.jsonl")
        self.assertEqual([(f["uuid"], f["round"]) for f in failures], [(uid(2), 1), (uid(2), 2)])
        self.assertEqual(self.host.exports.count(pid(1)), 1)
        self.assertEqual(self.host.exports.count(pid(2)), 3)
        self.assertTrue((self.folder(2) / ".done").exists())

    def test_exhausted_rounds_exit_nonzero_and_log_a_path_free_error_code(self):
        self.seed({1: live_photo(b"a")})
        self.host.fail_times[pid(1)] = 5
        self.assertEqual(self.run_main("--rounds", "2"), 1)
        details = {f["detail"] for f in self.log_lines("export-failures.jsonl")}
        self.assertEqual(details, {"osascript exited 1 (AppleScript error -1712)"})
        self.assertIn("still failing: 1", self.output)

    def test_timeout_is_a_failure_not_a_crash(self):
        self.seed({1: live_photo(b"a")})
        real = self.host.osascript

        def slow_export(command):
            if "export {m}" in " ".join(command):
                raise subprocess.TimeoutExpired(command, 1)
            return real(command)

        self.host.osascript = slow_export
        self.assertEqual(self.run_main("--rounds", "1", "--timeout", "7"), 1)
        self.assertEqual([f["detail"] for f in self.log_lines("export-failures.jsonl")], ["timeout after 7s"])

    def test_offset_and_limit_select_a_window_of_the_album(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 6)})
        self.assertEqual(self.run_main("--offset", "1", "--limit", "2"), 0)
        self.assertEqual(self.host.exports, [pid(2), pid(3)])


class StopTests(ExporterTestCase):
    def test_stop_file_finishes_the_in_flight_item_and_skips_queued_ones(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 5)})
        self.host.on_export = lambda photos_id: (self.root / "STOP").write_text("") if photos_id == pid(2) else None
        self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.host.exports, [pid(1), pid(2)])
        self.assertTrue((self.folder(2) / ".done").exists())  # in-flight item completed
        self.assertFalse(self.folder(3).exists())
        self.assertFalse(self.folder(4).exists())
        self.assertIn("STOP file present", self.output)

    def test_items_already_queued_to_the_pool_honour_stop_per_item(self):
        self.seed({1: live_photo(b"a")})
        (self.root).mkdir(parents=True)
        (self.root / "STOP").write_text("")
        settings = exporter.ExportSettings(root=self.root)
        self.assertEqual(exporter.export_one(settings, pid(1)), ("stop", uid(1), ""))
        self.assertEqual(self.host.exports, [])
        self.assertFalse(self.folder(1).exists())

    def test_stop_never_discards_receipted_work_and_removal_resumes(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.host.on_export = lambda photos_id: (self.root / "STOP").write_text("")
        self.assertEqual(self.run_main(), 2)
        (self.root / "STOP").unlink()
        self.host.on_export = None
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.host.exports, [pid(1), pid(2)])


class MeteredLinkTests(ExporterTestCase):
    def test_hotspot_gateway_is_detected_on_macos_only(self):
        self.host.route = HOTSPOT_ROUTE
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertTrue(exporter.on_metered_link())
        with mock.patch.object(sys, "platform", "linux"):
            self.host.calls.clear()
            self.assertFalse(exporter.on_metered_link())
            self.assertEqual(self.host.calls, [])  # a true no-op elsewhere: nothing is executed

    def test_constrained_or_expensive_interface_flags_count_as_metered(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertFalse(exporter.on_metered_link())
            for flag in (" constrained", " expensive"):
                self.host.ifconfig = f"en0: flags=8863<UP>\n\toptions=400\n\tstatus: active{flag}\n"
                self.assertTrue(exporter.on_metered_link())

    def test_missing_route_tool_is_a_safe_no_op(self):
        self.host.route_error = FileNotFoundError("route")
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertFalse(exporter.on_metered_link())

    def test_hotspot_without_budget_or_wait_refuses_before_any_export(self):
        self.seed({1: live_photo(b"a")})
        self.host.route = HOTSPOT_ROUTE
        self.assertEqual(self.run_main(platform="darwin"), 3)
        self.assertIn("--wait", self.output)
        self.assertIn("--hotspot-budget-gb", self.output)
        self.assertEqual(self.host.exports, [])
        self.assertFalse(self.root.exists())

    def test_budget_allows_items_until_it_is_spent_then_defers_the_rest(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 4)})
        self.host.route = HOTSPOT_ROUTE
        # Each item is 113 bytes: a 200-byte budget admits two items (113 < 200), then blocks (226 >= 200).
        self.assertEqual(self.run_main("--hotspot-budget-gb", "0.0000002", platform="darwin"), 3)
        self.assertEqual(self.host.exports, [pid(1), pid(2)])
        self.assertIn("deferred by metered link: 1", self.output)
        self.assertFalse(self.folder(3).exists())

    def test_budget_is_not_spent_on_an_unmetered_network(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 4)})
        self.assertEqual(self.run_main("--hotspot-budget-gb", "0.0000002", platform="darwin"), 0)
        self.assertEqual(len(self.host.exports), 3)

    def test_wait_sleeps_until_a_real_network_returns_then_exports(self):
        self.seed({1: live_photo(b"a")})
        states = iter([True, True, True])  # startup check, then two blocked polls; unmetered afterwards
        sleeps = []
        with mock.patch.object(exporter.time, "sleep", sleeps.append):
            with mock.patch.object(exporter, "on_metered_link", side_effect=lambda: next(states, False)):
                self.assertEqual(self.run_main("--wait", platform="darwin"), 0)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(self.host.exports, [pid(1)])
        self.assertIn("waiting for a real network", self.output)
        self.assertEqual(self.output.count("waiting for a real network"), 1)

    def test_guard_blocks_without_wait_and_honours_stop_while_waiting(self):
        self.root.mkdir(parents=True)
        guard = exporter.MeterGuard(budget_bytes=0, wait=False, detector=lambda: True)
        self.assertEqual(guard.gate(self.root), "blocked")
        calls = []

        def stop_after_two(seconds):
            calls.append(seconds)
            if len(calls) == 2:
                (self.root / "STOP").write_text("")

        waiting = exporter.MeterGuard(budget_bytes=0, wait=True, poll_seconds=60, detector=lambda: True,
                                      sleep=stop_after_two)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(waiting.gate(self.root), "stop")
        self.assertEqual(calls, [60, 60])


class PrivateRootTests(ExporterTestCase):
    def test_root_inside_a_photos_library_package_is_refused_and_nothing_is_written(self):
        library = pathlib.Path(self._tmp.name) / "Photos Library.photoslibrary"
        library.mkdir()
        self.seed({1: live_photo(b"a")})
        for candidate in (library / "export", library / "a" / "b", library):
            self.root = candidate
            with self.assertRaises(SystemExit) as caught:
                self.run_main()
            self.assertIn("Photos library", str(caught.exception))
        self.assertEqual(list(library.iterdir()), [])
        self.assertEqual(self.host.calls, [])

    def test_photos_library_suffix_is_refused_case_insensitively_and_through_symlinks(self):
        library = pathlib.Path(self._tmp.name) / "Pictures.PhotosLibrary"
        library.mkdir()
        link = pathlib.Path(self._tmp.name) / "innocent-link"
        link.symlink_to(library, target_is_directory=True)
        for candidate in (library / "x", link / "x"):
            self.root = candidate
            with self.assertRaises(SystemExit):
                self.run_main()
        self.assertEqual(list(library.iterdir()), [])

    def test_root_may_live_outside_the_checkout_but_inside_it_only_under_var(self):
        outside = exporter.resolve_private_root(self.root)
        self.assertEqual(outside, self.root)
        self.assertFalse(self.root.exists())
        with self.assertRaises(SystemExit):
            exporter.resolve_private_root(REPO_ROOT / "media-dump")
        with self.assertRaises(SystemExit):
            exporter.resolve_private_root(REPO_ROOT / "docs" / "live-photos")
        inside_var = exporter.resolve_private_root(REPO_ROOT / "var" / "live-photos-test-root")
        self.assertEqual(inside_var, (REPO_ROOT / "var" / "live-photos-test-root").resolve())
        self.assertFalse(inside_var.exists())


class AlbumIdTests(ExporterTestCase):
    def test_ids_are_read_once_cached_and_filtered_to_valid_media_item_ids(self):
        self.host.album_ids = [pid(1), pid(2)]
        settings = exporter.ExportSettings(root=self.root)
        self.assertEqual(exporter.load_ids(settings, "My Album", False), [pid(1), pid(2)])
        self.assertEqual(json.loads((self.root / "album-ids.json").read_text()), [pid(1), pid(2)])
        script_call = next(c for c in self.host.calls if "osascript" in c)
        self.assertEqual(script_call[-1], "My Album")
        self.host.calls.clear()
        self.assertEqual(exporter.load_ids(settings, "My Album", False), [pid(1), pid(2)])
        self.assertEqual(self.host.calls, [])
        self.host.album_ids = [pid(3)]
        self.assertEqual(exporter.load_ids(settings, "My Album", True), [pid(3)])

    def test_empty_album_and_corrupt_cache_fail_clearly(self):
        settings = exporter.ExportSettings(root=self.root)
        with self.assertRaises(SystemExit):
            exporter.load_ids(settings, "Empty", False)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "album-ids.json").write_text(json.dumps(["../../etc"]))
        with self.assertRaises(SystemExit):
            exporter.load_ids(settings, "Any", False)


if __name__ == "__main__":
    unittest.main()
