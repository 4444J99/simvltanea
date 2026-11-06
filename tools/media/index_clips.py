#!/usr/bin/env python3
"""Write the capture time of each exported clip to ``analysis/index/<id>.json``.

For every export receipt (``originals/<id>/.done``) this reads ONLY the container creation time
with ``ffprobe``, asking for exactly two tags (``creation_time`` and
``com.apple.quicktime.creationdate``) and nothing else, and writes::

    {"uuid": "<id>", "captured_at": "2024-03-01T12:00:00+00:00" | null}

Location, GPS and every other metadata tag are never requested, parsed, logged or written: the
``ffprobe`` command line names the two tags, so other tags are not even printed by the tool.
The output is an ISO 8601 UTC time (normalised from whichever tag was present, preferring the
QuickTime creation date) or null. Existing index files are kept unless ``--force``.
Counts are printed; ids and times are not.

Run:  python3 -m tools.media.index_clips --root /path/to/live-photos
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.media import play_guard
from tools.media.play_state import ID_RE, read_json, receipt_media

from simvltanea.authoring import parse_captured_at

TAGS = ("com.apple.quicktime.creationdate", "creation_time")      # in order of preference
PROBE_TIMEOUT = 30


def probe_command(media: Path) -> list[str]:
    return ["ffprobe", "-v", "error", "-show_entries", "format_tags=" + ",".join(TAGS),
            "-of", "json", str(media)]


def captured_at(media: Path) -> str | None:
    """Normalised UTC capture time from the container, or None. Raises OSError/ValueError on probe failure."""
    done = subprocess.run(probe_command(media), capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    if done.returncode != 0:
        raise ValueError("probe failed")
    tags = json.loads(done.stdout or "{}").get("format", {}).get("tags", {})
    if not isinstance(tags, dict):
        return None
    lowered = {str(k).lower(): v for k, v in tags.items() if str(k).lower() in TAGS}
    for name in TAGS:
        value = lowered.get(name)
        if isinstance(value, str):
            value = value.split(";")[0]          # some muxers join a repeated tag with ';'
        seconds = parse_captured_at(value)
        if seconds is not None:
            try:
                return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return None
    return None


def checked_index_dir(root: Path) -> Path:
    """``root/analysis/index`` as a real directory inside ``root`` that is not a Git working tree, or raise.

    The index is written with replacement, so it must never be a link to somewhere else, a file, a
    directory that resolves elsewhere or one that holds ``.git`` (another repository's tracked files
    would be overwritten). The same rule ``play_state`` applies to its output; ``index_root`` additionally sends
    every file it writes through ``play_guard.resolve_out``, so a link planted after this check is caught too.
    """
    analysis = root / "analysis"
    index = analysis / "index"
    for part in (analysis, index):
        if os.path.islink(part) or (os.path.lexists(part) and not part.is_dir()):
            raise play_guard.GuardError("analysis/index must be a real directory inside --root.")
    play_guard.resolve_out(index / "index.json")          # same destination rule as --out, before anything is created
    index.mkdir(parents=True, exist_ok=True)
    if not Path(os.path.realpath(index)).is_relative_to(root.resolve()):
        raise play_guard.GuardError("analysis/index must be a real directory inside --root.")
    if play_guard._has_git(index) or play_guard._has_git(analysis):
        raise play_guard.GuardError("analysis/index must not be inside a Git working tree.")
    return index


def index_root(root: Path, force: bool = False) -> Counter:
    counts: Counter = Counter()
    originals = root / "originals"
    if not originals.is_dir():
        raise SystemExit("--root has no originals directory.")
    if originals.is_symlink():
        raise play_guard.GuardError("originals must be a real directory inside --root.")
    index = checked_index_dir(root)
    for clip_dir in sorted(originals.iterdir()):
        clip_id = clip_dir.name
        if not ID_RE.fullmatch(clip_id) or not clip_dir.is_dir() or clip_dir.is_symlink():
            continue
        target = play_guard.resolve_out(index / f"{clip_id}.json")
        if (target.exists() or target.is_symlink()) and not force:
            counts["kept"] += 1
            continue
        try:
            media = root / receipt_media(read_json(clip_dir / ".done"), clip_id, originals)["path"]
        except (OSError, ValueError, RecursionError):
            counts["no_usable_export_receipt"] += 1
            continue
        try:
            when = captured_at(media)
        except (OSError, ValueError, subprocess.SubprocessError):
            counts["probe_failed"] += 1
            continue
        target = play_guard.resolve_out(index / f"{clip_id}.json")      # again at the write: nothing changed since the probe
        play_guard.write_private_file(target, (json.dumps({"uuid": clip_id, "captured_at": when}) + "\n").encode(), True)
        counts["indexed" if when else "no_creation_time"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index the capture time of exported clips (creation time only).")
    parser.add_argument("--root", required=True, help="private directory holding originals/")
    parser.add_argument("--force", action="store_true", help="re-read clips that already have an index file")
    args = parser.parse_args(argv)
    root = play_guard.resolve_root(args.root, require_tags=False)
    try:
        counts = index_root(root, args.force)
    except FileNotFoundError:
        raise SystemExit("ffprobe was not found; install FFmpeg.") from None
    print("index: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else "index: nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
