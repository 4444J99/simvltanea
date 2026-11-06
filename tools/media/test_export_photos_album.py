"""Exercise the Photos album exporter with fake osascript, ffprobe, route and ifconfig.

No Photos.app, no network and no real media: ``subprocess.run`` is replaced by FakeHost.
"""
import contextlib
import errno
import fcntl
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from tools.media import export_photos_album as exporter
from tools.paths import REPO_ROOT

HOTSPOT_ROUTE = "   route to: default\n    gateway: 172.20.10.1\n  interface: en0\n"
LAN_ROUTE = "   route to: default\n    gateway: 192.168.1.1\n  interface: en0\n"
PRIVATE_NAME = "FullSizeRender"
REAL_RUN = subprocess.run  # the private-root guard runs the real git while osascript and friends are faked


def _sample(text: str) -> str:
    """Real ``ifconfig -v`` output is tab-indented; the constants below use four spaces for readability."""
    return re.sub(r"(?m)^    ", "\t", text)


def _with_address(sample: str, name: str, address: str) -> str:
    """A derived sample: the same real output under another interface name, plus one IPv4 address."""
    first, rest = sample.split("\n", 1)
    renamed = name + first[first.index(":"):]
    return f"{renamed}\n\tinet {address} netmask 0xffffff00 broadcast 192.0.2.255\n{rest}"


# Redacted output of `ifconfig -v <interface>` captured on macOS 26 (MAC addresses, IPv4 and IPv6
# addresses and Skywalk GUIDs replaced). Plain `ifconfig` (no -v) never prints the eflags/xflags lines.
# en8 is a phone's USB tether (EXPENSIVE); en0 is Wi-Fi on a hotspot (constrained, EXPENSIVE+CONSTRAINED);
# en10 is an active USB Ethernet adapter without an address; en4 is an inactive one; utun2 is a tunnel.

EN8_USB_TETHER = _sample("""\
en8: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500 index 22
    eflags=400048c0<ACCEPT_RTADV,TXSTART,ARPLL,EXPENSIVE,FASTLN_ON>
    xflags=4000000<INBAND_WAKE_PKT>
    options=400<CHANNEL_IO>
    ether 02:00:00:00:00:00
    inet6 fe80::1%IFACE prefixlen 64 secured scopeid 0x16
    inet 192.0.2.7 netmask 0xfffffff0 broadcast 192.0.2.255
    inet6 2001:db8::1 prefixlen 64 autoconf secured
    inet6 2001:db8::1 prefixlen 64 autoconf temporary
    netif: 00000000-0000-0000-0000-000000000000
    flowswitch: 00000000-0000-0000-0000-000000000000
    nd6 options=201<PERFORMNUD,DAD>
    media: autoselect <full-duplex>
    status: active
    max mtu: 1500
    generation id: 48
    type: USB Ethernet
    agent domain:Skywalk type:NetIf flags:0xa443 desc:"Userspace Networking"
    agent domain:Skywalk type:FlowSwitch flags:0x4483 desc:"Userspace Networking"
    link quality: 100 (good)
    state availability: 0 (true)
    scheduler: UNKNOWN
    link rate: 100.00 Mbps
    qosmarking enabled: yes mode: none
    low power mode: disabled
    multi layer packet logging (mpklog): disabled
    routermode4: disabled
    routermode6: disabled
""")

EN0_WIFI_CONSTRAINED = _sample("""\
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500 index 14 constrained
    eflags=442048d0<ADV_REPORT,ACCEPT_RTADV,TXSTART,ARPLL,EXPENSIVE,NOACKPRI,CHANNEL_DRV,FASTLN_ON>
    xflags=4000201<WOL,CONSTRAINED,INBAND_WAKE_PKT>
    options=6460<TSO4,TSO6,CHANNEL_IO,PARTIAL_CSUM,ZEROINVERT_CSUM>
    hwassist=703000<CSUM_PARTIAL,CSUM_ZERO_INVERT,MULTIPAGES,TSO_V4,TSO_V6>
    ether 02:00:00:00:00:00
    inet6 fe80::1%IFACE prefixlen 64 secured scopeid 0xe
    inet 192.0.2.7 netmask 0xfffffff0 broadcast 192.0.2.255
    inet6 2001:db8::1 prefixlen 64 autoconf secured
    inet6 2001:db8::1 prefixlen 64 autoconf temporary
    netif: 00000000-0000-0000-0000-000000000000
    flowswitch: 00000000-0000-0000-0000-000000000000
    nd6 options=201<PERFORMNUD,DAD>
    media: autoselect
    status: active
    max mtu: 1500
    generation id: 25
    type: Wi-Fi
    agent domain:Skywalk type:NetIf flags:0xa443 desc:"Userspace Networking"
    agent domain:WiFiManager type:CallInProgress flags:0x3d desc:"WiFi"
    agent domain:Skywalk type:FlowSwitch flags:0x4483 desc:"Userspace Networking"
    link quality: 100 (good)
    state availability: 0 (true)
    scheduler: FQ_CODEL (driver managed)
    uplink rate: 72.25 Mbps [eff] / 97.11 Mbps
    downlink rate: 72.25 Mbps [eff] / 97.11 Mbps [max]
    qosmarking enabled: yes mode: none
    low power mode: disabled
    multi layer packet logging (mpklog): disabled
    routermode4: disabled
    routermode6: disabled
""")

EN10_USB_ETHERNET = _sample("""\
en10: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500 index 23
    eflags=60000080<TXSTART,DIRECTLINK,FASTLN_ON>
    xflags=4002000<NOSHAPING,INBAND_WAKE_PKT>
    options=404<VLAN_MTU,CHANNEL_IO>
    hwassist=20000<VLAN_MTU>
    ether 02:00:00:00:00:00
    inet6 fe80::1%IFACE prefixlen 64 scopeid 0x17
    netif: 00000000-0000-0000-0000-000000000000
    flowswitch: 00000000-0000-0000-0000-000000000000
    nd6 options=201<PERFORMNUD,DAD>
    media: autoselect
    status: active
    max mtu: 16000
    generation id: 49
    type: USB Ethernet
    agent domain:Skywalk type:NetIf flags:0xa443 desc:"Userspace Networking"
    agent domain:Skywalk type:FlowSwitch flags:0x4483 desc:"Userspace Networking"
    link quality: 100 (good)
    state availability: 0 (true)
    scheduler: UNKNOWN
    qosmarking enabled: yes mode: none
    low power mode: disabled
    multi layer packet logging (mpklog): disabled
    routermode4: disabled
    routermode6: disabled
""")

EN4_INACTIVE = _sample("""\
en4: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500 index 7
    eflags=40000080<TXSTART,FASTLN_ON>
    xflags=4000000<INBAND_WAKE_PKT>
    options=400<CHANNEL_IO>
    ether 02:00:00:00:00:00
    netif: 00000000-0000-0000-0000-000000000000
    flowswitch: 00000000-0000-0000-0000-000000000000
    nd6 options=201<PERFORMNUD,DAD>
    media: none
    status: inactive
    max mtu: 16000
    generation id: 7
    type: USB Ethernet
    agent domain:Skywalk type:NetIf flags:0xa443 desc:"Userspace Networking"
    agent domain:Skywalk type:FlowSwitch flags:0x4483 desc:"Userspace Networking"
    link quality: -2 (off)
    state availability: 0 (true)
    scheduler: UNKNOWN
    qosmarking enabled: yes mode: none
    low power mode: disabled
    multi layer packet logging (mpklog): disabled
    routermode4: disabled
    routermode6: disabled
""")

UTUN2_TUNNEL = _sample("""\
utun2: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 2000 index 20
    eflags=2080<TXSTART,NOAUTOIPV6LL>
    xflags=4000004<NOAUTONX,INBAND_WAKE_PKT>
    inet6 fe80::1%IFACE prefixlen 64 scopeid 0x14
    nd6 options=201<PERFORMNUD,DAD>
    generation id: 28
    agent domain:ids501 type:clientchannel flags:0xc3 desc:"IDSNexusAgent ids501 : clientchannel"
    link quality: -1 (unknown)
    state availability: 0 (true)
    scheduler: FQ_CODEL
    qosmarking enabled: no mode: none
    low power mode: disabled
    multi layer packet logging (mpklog): disabled
    routermode4: disabled
    routermode6: disabled
""")

# Derived (not captured): an unmetered wired interface with an address, and the hotspot Wi-Fi with its
# flags removed, i.e. the same card on a normal network.
ETHERNET_UNMETERED = _with_address(EN10_USB_ETHERNET, "en5", "192.0.2.20")
WIFI_UNMETERED = (EN0_WIFI_CONSTRAINED.replace(" constrained", "").replace(",EXPENSIVE", "")
                  .replace(",CONSTRAINED", ""))
TUNNEL_ROUTE = "   route to: default\n    gateway: 192.0.2.99\n  interface: utun2\n"
EN8_ROUTE = "   route to: default\n    gateway: 192.0.2.1\n  interface: en8\n"
ETHERNET_ROUTE = "   route to: default\n    gateway: 192.0.2.1\n  interface: en5\n"


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
        self.interfaces = {"en0": WIFI_UNMETERED, "en5": ETHERNET_UNMETERED}  # name -> `ifconfig -v NAME`
        self.interface_list = "lo0 en0 en5 utun2"
        self.route_error: Exception | None = None
        self.stream_extra: dict = {}  # merged into the fake video stream (side data, tags, ...)
        self.calls: list[list[str]] = []
        self.exports: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, command, **kwargs):
        with self._lock:
            self.calls.append(list(command))
        name = pathlib.Path(command[0]).name
        if name == "git":
            return REAL_RUN(command, **kwargs)
        if "osascript" in command:
            return self.osascript(command)
        if name == "ffprobe":
            return self.ffprobe(command)
        if name == "route":
            if self.route_error:
                raise self.route_error
            return subprocess.CompletedProcess(command, 0, self.route, "")
        if name == "ifconfig":
            return self.ifconfig_output(command)
        raise AssertionError(f"unexpected command {command[:2]}")

    def ifconfig_output(self, command):
        arguments = command[1:]
        if arguments == ["-l"]:
            return subprocess.CompletedProcess(command, 0, self.interface_list + "\n", "")
        text = self.interfaces.get(arguments[-1])
        if text is None:
            return subprocess.CompletedProcess(command, 1, "", f"ifconfig: interface {arguments[-1]} does not exist")
        if "-v" not in arguments:  # plain ifconfig never prints the eflags/xflags lines
            text = "\n".join(line for line in text.splitlines() if not re.match(r"\s+[ex]flags=", line)) + "\n"
        return subprocess.CompletedProcess(command, 0, text, "")

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
        facts = {"streams": [{"codec_name": "hevc", "width": 1080, "height": 1920, "r_frame_rate": "30/1",
                              **self.stream_extra}],
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
        with mock.patch.object(sys, "platform", platform), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
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
        # sorted order: IMG_0001.AAE(0) .HEIC(1) .MOV(2) IMG_0002.JPG(3) .MOV(4). The primary still is the
        # first *image*, so the AAE sidecar that sorts before it never becomes <uuid>.aae.
        self.assertEqual(self.names(1), {f"{uid(1)}.heic", f"{uid(1)}.mov", f"{uid(1)}.extra0.aae",
                                         f"{uid(1)}.extra3.jpg", f"{uid(1)}.extra4.mov", ".done"})
        self.assertEqual((self.folder(1) / f"{uid(1)}.mov").read_bytes(), b"movie-1")
        self.assertEqual((self.folder(1) / f"{uid(1)}.heic").read_bytes(), b"still")

    def test_every_image_extension_can_be_the_primary_still_and_a_sidecar_alone_is_not(self):
        for extension in ("HEIC", "JPG", "JPEG", "PNG"):
            self.assertIn(f".{extension.lower()}", exporter.IMAGE_EXT)
        self.seed({1: [("A.AAE", b"sidecar"), ("A.MOV", b"movie")]})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.names(1), {f"{uid(1)}.extra0.aae", f"{uid(1)}.mov", ".done"})

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

    def test_receipt_keeps_the_coded_size_and_adds_rotation_and_the_displayed_size(self):
        # A phone portrait clip: landscape-coded 1920x1080 with a clockwise display rotation.
        self.host.stream_extra = {"width": 1920, "height": 1080,
                                  "side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]}
        self.seed({1: live_photo(b"a")})
        self.assertEqual(self.run_main(), 0)
        receipt = json.loads((self.folder(1) / ".done").read_text())
        video = receipt["video"]
        self.assertEqual(receipt["schema"], "live-photo-export/v1")
        self.assertEqual((video["width"], video["height"]), (1920, 1080))  # still the CODED size
        self.assertEqual((video["rotation"], video["display_width"], video["display_height"]), (-90, 1080, 1920))

    def test_receipt_without_a_display_matrix_records_rotation_zero_and_the_same_size(self):
        self.seed({1: live_photo(b"a")})
        self.assertEqual(self.run_main(), 0)
        video = json.loads((self.folder(1) / ".done").read_text())["video"]
        self.assertEqual((video["rotation"], video["display_width"], video["display_height"]), (0, 1080, 1920))

    def test_a_legacy_rotate_tag_and_a_malformed_rotation_are_read_the_safe_way(self):
        clip = pathlib.Path(self._tmp.name) / "clip.mov"
        clip.write_bytes(b"movie")
        for extra, rotation, shown in (({"tags": {"rotate": "90"}}, -90, (1920, 1080)),
                                       ({"tags": {"rotate": "ninety"}}, 0, (1080, 1920)),
                                       ({"side_data_list": [{"rotation": 45}]}, 0, (1080, 1920)),
                                       ({"side_data_list": [{"rotation": "nan"}]}, 0, (1080, 1920))):
            with self.subTest(extra=extra):
                self.host.stream_extra = extra
                video = exporter.probe(clip)
                self.assertEqual((video["rotation"], video["display_width"], video["display_height"]),
                                 (rotation, *shown))
                self.assertEqual((video["width"], video["height"]), (1080, 1920))  # always the coded size

    def test_probe_asks_for_streams_and_format_not_side_data_entries(self):
        self.seed({1: live_photo(b"a")})
        self.run_main()
        command = next(call for call in self.host.calls if call[0] == "ffprobe")
        self.assertEqual(command[1:-1], ["-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format",
                                         "-of", "json"])
        self.assertNotIn("-show_entries", command)

    def test_a_receipt_written_before_the_rotation_keys_still_loads_in_the_tagger_helpers(self):
        from tools.media import tag_clips

        folder = self.root / "originals" / uid(1)
        folder.mkdir(parents=True)
        legacy = {"schema": "live-photo-export/v1", "uuid": uid(1),
                  "video": {"name": f"{uid(1)}.mov", "codec": "hevc", "width": 1920, "height": 1080, "fps": "30/1",
                            "duration": 1.8}}
        (folder / ".done").write_text(json.dumps(legacy))
        self.assertEqual(tag_clips.read_receipt(self.root, uid(1)), legacy)
        self.assertIsNone(tag_clips.geometry_from_receipt(legacy))  # rotation unknown: the tagger probes the video
        self.assertEqual(exporter.RECEIPT_SCHEMA, "live-photo-export/v1")

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


class StopAfterTests(ExporterTestCase):
    def test_stop_after_creates_stop_once_n_items_are_in_the_manifest_and_a_rerun_resumes(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 6)})
        self.assertEqual(self.run_main("--stop-after", "2"), 2)
        self.assertEqual(self.host.exports, [pid(1), pid(2)])
        self.assertEqual(len(self.log_lines("export-manifest.jsonl")), 2)
        self.assertTrue((self.root / "STOP").exists())
        self.assertIn("STOP file present", self.output)
        (self.root / "STOP").unlink()
        self.assertEqual(self.run_main(), 0)  # without the option the run completes; receipts are untouched
        self.assertEqual(self.host.exports, [pid(n) for n in range(1, 6)])
        self.assertEqual(len(self.log_lines("export-manifest.jsonl")), 5)

    def test_stop_after_counts_earlier_work_and_zero_or_negative_values(self):
        self.seed({n: live_photo(bytes([96 + n])) for n in range(1, 4)})
        self.assertEqual(self.run_main("--limit", "2"), 0)
        self.assertEqual(self.run_main("--stop-after", "2"), 2)  # two receipts already exist: nothing new is exported
        self.assertEqual(self.host.exports, [pid(1), pid(2)])
        (self.root / "STOP").unlink()
        self.assertEqual(self.run_main("--stop-after", "0"), 0)
        self.assertFalse((self.root / "STOP").exists())
        with self.assertRaises(SystemExit):
            self.run_main("--stop-after", "-1")


class MeteredLinkTests(ExporterTestCase):
    def test_hotspot_gateway_is_detected_on_macos_only(self):
        self.host.route = HOTSPOT_ROUTE
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertTrue(exporter.on_metered_link())
        with mock.patch.object(sys, "platform", "linux"):
            self.host.calls.clear()
            self.assertFalse(exporter.on_metered_link())
            self.assertEqual(self.host.calls, [])  # a true no-op elsewhere: nothing is executed

    def metered(self, route, **interfaces):
        self.host.route = route
        self.host.interfaces.update(interfaces)
        with mock.patch.object(sys, "platform", "darwin"):
            return exporter.on_metered_link()

    def test_real_ifconfig_v_expensive_flag_is_detected_without_the_hotspot_gateway(self):
        self.assertTrue(self.metered(EN8_ROUTE, en8=EN8_USB_TETHER))  # eflags=<...EXPENSIVE...> only
        self.assertNotIn("constrained", EN8_USB_TETHER)  # nothing lowercase to fall back on
        self.assertIn(["ifconfig", "-v", "en8"], self.host.calls)  # plain ifconfig never prints the flag

    def test_real_wifi_constrained_sample_is_detected(self):
        self.assertTrue(self.metered(LAN_ROUTE, en0=EN0_WIFI_CONSTRAINED))
        only_xflags = EN0_WIFI_CONSTRAINED.replace(" constrained", "").replace(",EXPENSIVE", "")
        self.assertIn("xflags=4000201<WOL,CONSTRAINED", only_xflags)
        self.assertTrue(self.metered(LAN_ROUTE, en0=only_xflags))

    def test_lowercase_constrained_header_is_still_honoured(self):
        header_only = WIFI_UNMETERED.replace("mtu 1500 index 14", "mtu 1500 index 14 constrained")
        self.assertTrue(self.metered(LAN_ROUTE, en0=header_only))

    def test_unmetered_interfaces_are_not_flagged(self):
        self.assertFalse(self.metered(LAN_ROUTE, en0=WIFI_UNMETERED))
        self.assertFalse(self.metered(ETHERNET_ROUTE))
        self.assertNotIn("EXPENSIVE", WIFI_UNMETERED + ETHERNET_UNMETERED)

    def test_a_vpn_does_not_hide_a_hotspot_on_the_physical_interface(self):
        self.host.interface_list = "lo0 en4 en8 utun2"
        self.assertTrue(self.metered(TUNNEL_ROUTE, en8=EN8_USB_TETHER, en4=EN4_INACTIVE, utun2=UTUN2_TUNNEL))
        self.assertIn(["ifconfig", "-l"], self.host.calls)

    def test_a_vpn_over_a_normal_network_is_not_metered(self):
        self.host.interface_list = "lo0 en0 en4 en5 utun2"
        self.assertFalse(self.metered(TUNNEL_ROUTE, en0=WIFI_UNMETERED, en4=EN4_INACTIVE, utun2=UTUN2_TUNNEL))

    def test_inactive_or_unaddressed_interfaces_are_ignored_behind_a_tunnel(self):
        flagged_but_down = EN8_USB_TETHER.replace("status: active", "status: inactive")
        self.host.interface_list = "lo0 en8 utun2"
        self.assertFalse(self.metered(TUNNEL_ROUTE, en8=flagged_but_down, utun2=UTUN2_TUNNEL))

    def test_hotspot_subnet_address_behind_a_tunnel_is_metered(self):
        subnet = _with_address(EN10_USB_ETHERNET, "en8", "172.20.10.4")
        self.host.interface_list = "lo0 en8 utun2"
        self.assertTrue(self.metered(TUNNEL_ROUTE, en8=subnet, utun2=UTUN2_TUNNEL))

    def test_other_interfaces_are_not_inspected_when_the_default_route_is_not_a_tunnel(self):
        self.host.interface_list = "lo0 en5 en8"
        self.assertFalse(self.metered(ETHERNET_ROUTE, en8=EN8_USB_TETHER))  # the tether is up but not the route

    def test_tunnel_name_families_are_all_recognised(self):
        for tunnel in ("utun4", "ppp0", "ipsec1"):
            route = TUNNEL_ROUTE.replace("utun2", tunnel)
            self.host.interface_list = f"lo0 en8 {tunnel}"
            self.assertTrue(self.metered(route, en8=EN8_USB_TETHER, **{tunnel: UTUN2_TUNNEL}), tunnel)

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


class MeterGuardRecordTests(unittest.TestCase):
    def test_bytes_are_counted_only_while_the_detector_reports_a_metered_link(self):
        link = {"metered": False}
        guard = exporter.MeterGuard(budget_bytes=1000, detector=lambda: link["metered"])
        guard.record(400)
        self.assertEqual(guard.spent_bytes, 0)  # unmetered exports never spend the hotspot budget
        link["metered"] = True
        guard.record(300)
        self.assertEqual(guard.spent_bytes, 300)
        link["metered"] = False
        guard.record(200)
        self.assertEqual(guard.spent_bytes, 300)
        self.assertTrue(guard.allowed())

    def test_bytes_exported_on_a_real_network_do_not_block_a_later_hotspot_session(self):
        link = {"metered": False}
        guard = exporter.MeterGuard(budget_bytes=500, detector=lambda: link["metered"])
        guard.record(10_000)
        link["metered"] = True
        self.assertTrue(guard.allowed())  # the whole budget is still available


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


class FinishedItemRaceTests(ExporterTestCase):
    def test_an_item_finished_by_another_run_while_this_one_waited_is_not_deleted(self):
        self.seed({1: live_photo(b"a")})
        finished_by_a = exporter.ExportSettings(root=self.root)

        def other_run_finishes_the_item_during_the_wait(_seconds):
            self.assertEqual(exporter.export_one(finished_by_a, pid(1))[0], "ok")
            link["metered"] = False

        link = {"metered": True}
        waiting = exporter.MeterGuard(budget_bytes=0, wait=True, detector=lambda: link["metered"],
                                      sleep=other_run_finishes_the_item_during_the_wait)
        settings = exporter.ExportSettings(root=self.root, guard=waiting)
        with contextlib.redirect_stdout(io.StringIO()):
            status, _uuid, _detail = exporter.export_one(settings, pid(1))
        self.assertEqual(status, "skip")
        self.assertEqual(self.host.exports, [pid(1)])  # exported once, by the other run
        self.assertTrue((self.folder(1) / ".done").exists())
        self.assertEqual(len(self.log_lines("export-manifest.jsonl")), 1)

    def test_two_sequential_runs_do_not_touch_finished_output(self):
        self.seed({1: live_photo(b"a")})
        self.assertEqual(self.run_main(), 0)
        before = {p.name: p.read_bytes() for p in self.folder(1).iterdir()}
        manifest = (self.root / "export-manifest.jsonl").read_text()
        self.assertEqual(self.run_main(), 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.folder(1).iterdir()}, before)
        self.assertEqual((self.root / "export-manifest.jsonl").read_text(), manifest)
        self.assertEqual(self.host.exports, [pid(1)])


class ExportLockTests(ExporterTestCase):
    def test_a_held_lock_makes_a_second_run_refuse_with_a_distinct_exit_code(self):
        self.seed({1: live_photo(b"a")})
        self.root.mkdir(parents=True)
        with (self.root / ".export.lock").open("a+") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code = self.run_main()
        self.assertEqual(code, exporter.EXIT_LOCKED)
        self.assertNotIn(code, (0, 1, 2, 3))
        self.assertIn("another export is already running", self.output)
        self.assertEqual(self.host.exports, [])
        self.assertFalse((self.root / "originals").exists())
        self.assertFalse((self.root / "album-ids.json").exists())

    def test_the_lock_is_released_when_the_run_ends(self):
        self.seed({1: live_photo(b"a")})
        self.assertEqual(self.run_main(), 0)
        with (self.root / ".export.lock").open("a+") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)  # would raise if the first run still held it
        self.assertEqual(self.run_main(), 0)

    def test_a_lock_held_by_another_process_is_respected(self):
        self.seed({1: live_photo(b"a")})
        self.root.mkdir(parents=True)
        code = (
            "import fcntl, sys\n"
            "handle = open(sys.argv[1], 'a+')\n"
            "fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "print('held', flush=True)\n"
            "sys.stdin.readline()\n"
        )
        # Popen is not faked (only subprocess.run is), so this really is a second process.
        holder = subprocess.Popen([sys.executable, "-c", code, str(self.root / ".export.lock")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.stdin.close)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        self.assertEqual(self.run_main(), exporter.EXIT_LOCKED)
        self.assertEqual(self.host.exports, [])


class DuplicateIdTests(ExporterTestCase):
    def test_duplicate_ids_are_dropped_keeping_first_occurrence_order(self):
        self.root.mkdir(parents=True)
        (self.root / "album-ids.json").write_text(json.dumps([pid(2), pid(1), pid(2), pid(3), pid(1)]))
        settings = exporter.ExportSettings(root=self.root)
        self.assertEqual(exporter.load_ids(settings, "Any", False), [pid(2), pid(1), pid(3)])

    def test_duplicates_from_photos_are_dropped_before_the_cache_is_written(self):
        self.host.album_ids = [pid(1), pid(2), pid(1)]
        settings = exporter.ExportSettings(root=self.root)
        self.assertEqual(exporter.load_ids(settings, "Any", False), [pid(1), pid(2)])
        self.assertEqual(json.loads((self.root / "album-ids.json").read_text()), [pid(1), pid(2)])

    def test_a_duplicated_id_is_exported_once(self):
        self.seed({1: live_photo(b"a")})
        self.host.album_ids = [pid(1), pid(1)]
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.host.exports, [pid(1)])


class InterruptTests(ExporterTestCase):
    def run_interrupted(self, *extra):
        try:
            return self.run_main(*extra)
        except KeyboardInterrupt:
            self.fail("KeyboardInterrupt escaped main(); it must be handled and turned into an exit code")

    def fake_export(self, ran, delay=0.05):
        def export(settings, photos_id):
            ran.append(photos_id)
            if len(ran) == 1:
                raise KeyboardInterrupt  # what the main thread sees when the user presses Ctrl-C
            time.sleep(delay)
            return "ok", exporter.uuid_of(photos_id), ""
        return export

    def test_ctrl_c_cancels_queued_items_logs_one_line_and_exits_nonzero(self):
        total = 40
        self.host.album_ids = [pid(n) for n in range(1, total + 1)]
        ran: list[str] = []
        with mock.patch.object(exporter, "export_one", self.fake_export(ran)):
            code = self.run_interrupted()
        self.assertEqual(code, exporter.EXIT_INTERRUPTED)
        self.assertNotEqual(code, 0)
        self.assertLess(len(ran), total)  # queued items never started
        lines = [line for line in self.output.splitlines() if "cancelled" in line]
        self.assertEqual(len(lines), 1)
        cancelled = int(re.search(r"(\d+) queued item", lines[0]).group(1))
        self.assertEqual(cancelled + len(ran), total)  # every item either ran or was cancelled
        self.assertNotIn(str(self.root), self.output)

    def test_ctrl_c_stops_the_retry_rounds_and_a_rerun_resumes(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        ran: list[str] = []
        with mock.patch.object(exporter, "export_one", self.fake_export(ran, delay=0)):
            self.assertEqual(self.run_interrupted("--rounds", "3"), exporter.EXIT_INTERRUPTED)
        self.assertEqual(self.run_main(), 0)
        self.assertTrue((self.folder(1) / ".done").exists() and (self.folder(2) / ".done").exists())


class StrictnessTests(ExporterTestCase):
    def test_an_id_with_a_trailing_newline_is_malformed(self):
        settings = exporter.ExportSettings(root=self.root)
        status, _uuid, detail = exporter.export_one(settings, pid(1) + "\n")
        self.assertEqual((status, detail), ("fail", "malformed Photos media item id"))
        self.assertEqual(self.host.exports, [])
        self.assertIsNone(exporter.ID_RE.fullmatch(pid(1) + "\n"))

    def test_a_cached_id_with_a_trailing_newline_is_rejected(self):
        self.root.mkdir(parents=True)
        (self.root / "album-ids.json").write_text(json.dumps([pid(1) + "\n"]))
        with self.assertRaises(SystemExit):
            exporter.load_ids(exporter.ExportSettings(root=self.root), "Any", False)


class OsErrorTests(ExporterTestCase):
    def test_a_local_file_error_prints_the_type_and_no_path(self):
        secret = self._tmp.name + "/very-private-folder/receipt"
        failure = PermissionError(errno.EACCES, "Permission denied", secret)
        with mock.patch.object(exporter, "load_ids", side_effect=failure):
            code = self.run_main()
        self.assertEqual(code, exporter.EXIT_IO_ERROR)
        self.assertIn("PermissionError", self.output)
        self.assertNotIn("very-private-folder", self.output)
        self.assertNotIn(self._tmp.name, self.output)
        self.assertNotIn("Traceback", self.output)


class ExitCodeTests(ExporterTestCase):
    def test_stop_plus_remaining_failures_returns_one_not_two(self):
        self.seed({1: live_photo(b"a"), 2: live_photo(b"b")})
        self.host.fail_times[pid(1)] = 5
        self.host.on_export = lambda photos_id: (self.root / "STOP").write_text("") if photos_id == pid(1) else None
        self.assertEqual(self.run_main(), exporter.EXIT_FAILURES)
        self.assertIn("STOP file present", self.output)
        self.assertEqual(self.host.exports, [pid(1)])

    def test_exit_codes_are_distinct_and_documented(self):
        codes = (exporter.EXIT_FAILURES, exporter.EXIT_STOPPED, exporter.EXIT_METERED, exporter.EXIT_LOCKED,
                 exporter.EXIT_IO_ERROR, exporter.EXIT_INTERRUPTED)
        self.assertEqual(len(set(codes)), len(codes))
        for code in codes:
            self.assertIn(f"{code} ", exporter.__doc__)

    def test_a_case_variant_of_this_checkout_is_refused_when_it_reaches_the_checkout(self):
        variant = REPO_ROOT.parent / REPO_ROOT.name.upper() / "docs" / "live-photos"
        if not variant.parent.exists():
            self.skipTest("case-sensitive volume: the upper-case path is a different, nonexistent directory")
        for tool_root in (variant, REPO_ROOT.parent / REPO_ROOT.name.upper() / "tools" / "media" / "dump"):
            with self.assertRaises(SystemExit):
                exporter.resolve_private_root(tool_root)
        self.assertFalse((REPO_ROOT / "docs" / "live-photos").exists())


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
