#!/usr/bin/env python3
"""Resumable, parallel export of a Photos.app album's Live Photo originals (macOS).

Why this exists: with "Optimize Mac Storage" the originals live in iCloud, and each first
export blocks on a per-item download. Photos overlaps those downloads when several export
calls are in flight, so this runs N ``osascript`` exports concurrently, each into its own
``originals/<uuid>/`` folder. Original filenames collide across assets (FullSizeRender,
IMG_xxxx), so one folder per asset UUID keeps the mapping exact.

Layout under --root (private; never committed; may live outside the checkout):
  album-ids.json              Photos media item ids in album order
  originals/<uuid>/<uuid>.mov the paired motion clip
  originals/<uuid>/<uuid>.<still extension>
  originals/<uuid>/.done      JSON receipt (sizes, sha256, ffprobe facts)
  export-manifest.jsonl       one line per completed item
  export-failures.jsonl       one line per failed attempt
Create <root>/STOP to finish in-flight items and exit; remove it and re-run to resume.

Only UUIDs are logged or recorded: never names, captions or paths of personal media.

Exit codes: 0 all in-scope items exported, 1 failures remain after the retry rounds,
2 stopped by STOP, 3 refused or deferred by the metered-link rule.

Run:  python3 -m tools.media.export_photos_album --root /path/to/live-photos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from tools.media.private_root import resolve_private_root

VIDEO_EXT = {".mov", ".mp4", ".m4v"}
ID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}/L0/\d+$")
APPLESCRIPT_ERROR_RE = re.compile(r"\((-\d+)\)")
RECEIPT_SCHEMA = "live-photo-export/v1"
EXIT_FAILURES, EXIT_STOPPED, EXIT_METERED = 1, 2, 3

# AppleScript lives in Python strings (tools/ may only hold .py and .md) and is passed to
# `osascript -e`, one -e per line. The id and output folder arrive as argv, never interpolated.
IDS_TIMEOUT_SECONDS = 600
IDS_SCRIPT_LINES = (
    "on run argv",
    "set albumName to item 1 of argv",
    f"with timeout of {IDS_TIMEOUT_SECONDS} seconds",
    'tell application "Photos"',
    "set a to first album whose name is albumName",
    "set AppleScript's text item delimiters to linefeed",
    "set idList to (id of every media item of a) as text",
    'set AppleScript\'s text item delimiters to ""',
    "return idList",
    "end tell",
    "end timeout",
    "end run",
)


def export_script_lines(timeout: int) -> tuple[str, ...]:
    """AppleScript exporting one media item's unmodified originals.

    The default AppleEvent timeout (120 s) kills queued exports with error -1712 while Photos
    works through other concurrent downloads, so the call sits inside a long timeout block.
    """
    return (
        "on run argv",
        "set pid to item 1 of argv",
        "set outDir to item 2 of argv",
        f"with timeout of {int(timeout)} seconds",
        'tell application "Photos"',
        "set m to media item id pid",
        "export {m} to (POSIX file outDir) with using originals",
        "end tell",
        "end timeout",
        'return "ok"',
        "end run",
    )


def osascript_command(lines: tuple[str, ...], *args: str, launcher: tuple[str, ...] = ()) -> list[str]:
    command = [*launcher, "osascript"]
    for line in lines:
        command.extend(["-e", line])
    command.extend(args)
    return command


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: pathlib.Path) -> dict:
    """ffprobe facts for the first video stream, or ``{}`` when the file is unreadable."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {}
    return {
        "codec": stream.get("codec_name"), "width": stream.get("width"), "height": stream.get("height"),
        "fps": stream.get("r_frame_rate"), "duration": duration,
    }


# --- network awareness -------------------------------------------------------------------
# A first export pulls the original from iCloud (~4 MB per Live Photo, ~27 GB for 6,500 items).
# On an iPhone Personal Hotspot (gateway 172.20.10.x, interface flagged "constrained") that is
# slow, uses the owner's data plan, and starves every other job, so bulk export is refused there
# unless an explicit byte budget is given; --wait resumes once a real network is back.
HOTSPOT_GATEWAY_PREFIX = "172.20.10."


def on_metered_link() -> bool:
    """True on an iPhone hotspot or an interface macOS flags constrained/expensive.

    macOS only: on any other platform, or if route/ifconfig cannot be run, this is a safe
    no-op that reports an unmetered link.
    """
    if sys.platform != "darwin":
        return False
    try:
        route = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=10).stdout
        gateway = re.search(r"gateway:\s*(\S+)", route)
        iface = re.search(r"interface:\s*(\S+)", route)
        if gateway and gateway.group(1).startswith(HOTSPOT_GATEWAY_PREFIX):
            return True
        if iface:
            flags = subprocess.run(["ifconfig", iface.group(1)], capture_output=True, text=True, timeout=10).stdout
            return " constrained" in flags or " expensive" in flags
    except (OSError, subprocess.SubprocessError):
        return False
    return False


class MeterGuard:
    """Per-item gate implementing the metered-link rule, shared by all workers."""

    def __init__(self, budget_bytes: int = 0, wait: bool = False, poll_seconds: float = 60.0,
                 detector: Callable[[], bool] | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.budget_bytes = budget_bytes
        self.wait = wait
        self.poll_seconds = poll_seconds
        self.detector = detector or on_metered_link
        self.sleep = sleep or time.sleep
        self.spent_bytes = 0  # bytes exported while on a metered link
        self._lock = threading.Lock()
        self._announced = False

    def allowed(self) -> bool:
        with self._lock:
            return (not self.detector()) or self.spent_bytes < self.budget_bytes

    def gate(self, root: pathlib.Path) -> str:
        """Return 'go', 'stop' (STOP file), or 'blocked' (metered, no budget left, not waiting)."""
        while True:
            if (root / "STOP").exists():
                return "stop"
            if self.allowed():
                return "go"
            if not self.wait:
                return "blocked"
            if not self._announced:
                self._announced = True
                print("metered link (hotspot) and no byte budget left: waiting for a real network...", flush=True)
            self.sleep(self.poll_seconds)

    def record(self, size: int) -> None:
        with self._lock:
            if self.detector():
                self.spent_bytes += size


@dataclass
class ExportSettings:
    root: pathlib.Path
    timeout: int = 3600
    launcher: tuple[str, ...] = ()
    guard: MeterGuard = field(default_factory=MeterGuard)


_append_lock = threading.Lock()


def append(path: pathlib.Path, record: dict) -> None:
    with _append_lock, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def uuid_of(photos_id: str) -> str:
    return photos_id.split("/")[0]


def failure_detail(proc: subprocess.CompletedProcess) -> str:
    """A path-free summary of an osascript failure (stderr can contain file names)."""
    match = APPLESCRIPT_ERROR_RE.search(proc.stderr or "")
    return f"osascript exited {proc.returncode}" + (f" (AppleScript error {match.group(1)})" if match else "")


def rename_exported(folder: pathlib.Path, uuid: str,
                    files: list[pathlib.Path]) -> tuple[list[pathlib.Path], pathlib.Path]:
    """Rename to ``<uuid>.<ext>`` (primary video and still) and ``<uuid>.extraN.<ext>`` (the rest).

    Two phases through unique temporary names, so no original name can collide with a final one.
    Returns the renamed files and the primary video.
    """
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXT]
    primary_still = next((p for p in files if p.suffix.lower() not in VIDEO_EXT), None)
    staged: list[tuple[pathlib.Path, str, bool]] = []
    for index, path in enumerate(files):
        is_primary = path == videos[0] or path == primary_still
        stem = uuid if is_primary else f"{uuid}.extra{index}"
        temporary = folder / f".rename-{index}"
        path.rename(temporary)
        staged.append((temporary, f"{stem}{path.suffix.lower()}", path == videos[0]))
    renamed = []
    primary_video = None
    for temporary, final_name, is_primary_video in staged:
        target = folder / final_name
        temporary.rename(target)
        renamed.append(target)
        if is_primary_video:
            primary_video = target
    return renamed, primary_video


def export_one(settings: ExportSettings, photos_id: str) -> tuple[str, str, str]:
    """Export one media item. Returns ``(status, uuid, detail)``.

    Status is ok, skip (already receipted), stop, blocked, or fail. ``detail`` never contains
    anything beyond UUIDs and error codes.
    """
    uuid = uuid_of(photos_id)
    if not ID_RE.match(photos_id):
        return "fail", uuid[:8], "malformed Photos media item id"
    root = settings.root
    folder = root / "originals" / uuid
    if (folder / ".done").exists():
        return "skip", uuid, ""
    gate = settings.guard.gate(root)  # honours STOP and the metered-link rule per item
    if gate != "go":
        return gate, uuid, ""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    started = time.monotonic()
    command = osascript_command(export_script_lines(settings.timeout), photos_id, str(folder),
                                launcher=settings.launcher)
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=settings.timeout + 30)
    except subprocess.TimeoutExpired:
        return "fail", uuid, f"timeout after {settings.timeout}s"
    if proc.returncode != 0:
        return "fail", uuid, failure_detail(proc)
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
    if not any(p.suffix.lower() in VIDEO_EXT for p in files):
        return "fail", uuid, f"no paired video exported ({len(files)} files)"

    original_count = len(files)
    renamed, mov = rename_exported(folder, uuid, files)
    facts = probe(mov)
    if not facts.get("duration"):
        return "fail", uuid, "exported video failed ffprobe"

    receipt = {
        "schema": RECEIPT_SCHEMA, "uuid": uuid, "photos_id": photos_id, "original_file_count": original_count,
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in renamed],
        "video": {"name": mov.name, **facts}, "export_seconds": round(time.monotonic() - started, 1),
    }
    temporary = folder / ".done.tmp"
    temporary.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    temporary.replace(folder / ".done")  # the receipt is the resume marker: write it last, atomically
    append(root / "export-manifest.jsonl", receipt)
    settings.guard.record(sum(entry["bytes"] for entry in receipt["files"]))
    return "ok", uuid, ""


def load_ids(settings: ExportSettings, album: str, refresh: bool) -> list[str]:
    root = settings.root
    cache = root / "album-ids.json"
    if cache.exists() and not refresh:
        ids = json.loads(cache.read_text(encoding="utf-8"))
        if not isinstance(ids, list) or not all(isinstance(i, str) and ID_RE.match(i) for i in ids):
            raise SystemExit("album-ids.json is not a list of Photos media item ids; re-run with --refresh-ids.")
        return ids
    command = osascript_command(IDS_SCRIPT_LINES, album, launcher=settings.launcher)
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=IDS_TIMEOUT_SECONDS + 300)
    except subprocess.TimeoutExpired:
        raise SystemExit("could not read album ids: timed out") from None
    if proc.returncode != 0:
        raise SystemExit(f"could not read album ids ({failure_detail(proc)})")
    ids = [line.strip() for line in proc.stdout.splitlines() if ID_RE.match(line.strip())]
    if not ids:
        raise SystemExit("album returned no ids (check the exact album name and Photos automation permission)")
    root.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(ids), encoding="utf-8")
    return ids


def run_round(settings: ExportSettings, pending: list[str], workers: int, round_no: int) -> dict:
    """Export ``pending`` once. Returns counts plus the ids to retry and the ids deferred."""
    root = settings.root
    counts = {"ok": 0, "skip": 0, "fail": 0}
    failures: list[str] = []
    deferred: list[str] = []
    stopped = False
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for photos_id in pending:
            if (root / "STOP").exists():
                stopped = True
                break
            futures[pool.submit(export_one, settings, photos_id)] = photos_id
        for future in as_completed(futures):
            photos_id = futures[future]
            try:
                status, uuid, detail = future.result()
            except Exception as exc:  # noqa: BLE001 - record the type only (messages can hold paths)
                status, uuid, detail = "fail", uuid_of(photos_id), type(exc).__name__
            if status == "stop":
                stopped = True
                continue
            if status == "blocked":
                deferred.append(photos_id)
                continue
            counts[status] += 1
            if status == "fail":
                failures.append(photos_id)
                append(root / "export-failures.jsonl",
                       {"uuid": uuid, "photos_id": photos_id, "round": round_no, "detail": detail})
            total = sum(counts.values())
            if total % 25 == 0 or status == "fail":
                rate = counts["ok"] / max(time.monotonic() - started, 1)
                eta = ((len(pending) - total) / rate / 3600) if rate else float("inf")
                print(f"round {round_no}: ok={counts['ok']} skipped={counts['skip']} failed={counts['fail']} "
                      f"of {len(pending)} | {rate * 60:.1f}/min | ETA {eta:.1f} h", flush=True)
    return {**counts, "failures": failures, "deferred": deferred, "stopped": stopped}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, type=pathlib.Path,
                        help="private storage root (outside the checkout, or under var/)")
    parser.add_argument("--album", default="simvl-live", help="exact Photos album name")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    parser.add_argument("--timeout", type=int, default=3600, help="per-item seconds (AppleScript timeout block)")
    parser.add_argument("--refresh-ids", action="store_true", help="re-read album ids instead of album-ids.json")
    parser.add_argument("--rounds", type=int, default=3, help="retry rounds for failures")
    parser.add_argument("--hotspot-budget-gb", type=float, default=0.0,
                        help="GB allowed while on a metered link (phone hotspot). Default 0 = none.")
    parser.add_argument("--wait", action="store_true",
                        help="when blocked by the metered-link rule, sleep and resume on a real network")
    parser.add_argument("--launcher", default="",
                        help="optional command prefix that runs osascript with Photos automation permission "
                             "(for a host process that holds the macOS privacy grant)")
    return parser


def preflight(launcher: tuple[str, ...]) -> None:
    if not launcher and sys.platform != "darwin":
        raise SystemExit("export_photos_album needs macOS (osascript and Photos.app).")
    if shutil.which("ffprobe") is None:
        raise SystemExit("ffprobe is required to verify exported clips; install FFmpeg first.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("workers", "rounds"):
        if getattr(args, name) < 1:
            raise SystemExit(f"--{name} must be at least 1")
    if min(args.offset, args.limit, args.timeout) < 0 or args.timeout == 0:
        raise SystemExit("--offset and --limit must be >= 0 and --timeout must be positive")
    launcher = tuple(shlex.split(args.launcher))
    root = resolve_private_root(args.root)
    preflight(launcher)

    if hasattr(os, "nice"):
        os.nice(10)
    guard = MeterGuard(budget_bytes=int(args.hotspot_budget_gb * 1e9), wait=args.wait)
    if guard.detector() and guard.budget_bytes == 0 and not args.wait:
        print("This Mac is on a metered link (iPhone hotspot). A bulk export pulls ~4 MB per Live Photo "
              "from iCloud. Re-run with --wait (resume on a real network) or --hotspot-budget-gb N.", flush=True)
        return EXIT_METERED
    settings = ExportSettings(root=root, timeout=args.timeout, launcher=launcher, guard=guard)
    ids = load_ids(settings, args.album, args.refresh_ids)[args.offset:]
    if args.limit:
        ids = ids[: args.limit]
    print(f"{len(ids)} items in scope, workers={args.workers}", flush=True)

    pending, deferred, stopped = ids, [], False
    for round_no in range(1, args.rounds + 1):
        if not pending:
            break
        result = run_round(settings, pending, args.workers, round_no)
        pending, stopped = result["failures"], result["stopped"]
        deferred.extend(result["deferred"])
        if stopped:
            print("STOP file present: exiting", flush=True)
            break
    print(f"finished. still failing: {len(pending)}, deferred by metered link: {len(deferred)}", flush=True)
    if pending:
        return EXIT_FAILURES
    if stopped:
        return EXIT_STOPPED
    return EXIT_METERED if deferred else 0


if __name__ == "__main__":
    sys.exit(main())
