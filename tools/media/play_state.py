#!/usr/bin/env python3
"""Generate a composition state for any play mode from private per-clip records.

How the clips play is configuration, not code: a saved mode (``--mode``), an optional JSON config
(``--config``), your own mode table (``--presets-file``) and single overrides
(``--set section.key=value``, repeatable). ``--list-modes`` names the modes and ``--describe``
prints every parameter with its range and effect.

The command reads, from a private directory you name (``--root``):

  analysis/tags/<id>.json          per-clip tag record (read generically)
  analysis/index/<id>.json         optional capture time written by ``index_clips`` (captured_at only)
  originals/<id>/.done             export receipt: video name, duration and sha256

Only opaque ids matching ``[A-Za-z0-9_-]{1,80}`` (Photos UUIDs fit) enter the pool. Tag text is
reduced to a whitelist of controlled vocabulary and numbers before scheduling, so captions,
sharing notes, safety reasons and error messages are never read into the pool or written to the
state. The command prints counts and digests only: no ids, no captions, no file names.

The state is written only under ``var/work/`` or to an explicit path outside every Git working
tree, next to a ``<state>.play.json`` sidecar holding the effective, fully resolved configuration,
the seed and digests of the eligible pool and of the configuration, so any run is reproducible. The
sidecar holds, besides digests and counts, the clip ids named in the configuration
(``exclusion.exclude_ids``, ``relation.anchors``, ``path.pins``) because reproducing the run needs
them; treat it like the configuration file. It never holds captions, tags or file names.

Media digests are the ones in the export receipts (written by the exporter after copying and hashing);
by default they are trusted. ``--verify-media`` checks each file's size and SHA-256 against its receipt.
A symlinked ``originals/`` or ``originals/<id>/`` is never followed to show a clip (only to read the receipt of
an excluded id, which can only hide more), and a linked ``analysis/``, ``analysis/tags/`` or ``analysis/index/`` is refused.
Source paths in the state are ``originals/<id>/<id><ext>``, relative to the state file, so write
the state beside ``originals/`` (``--out <root>/play-state.json``) to render it offline.

Run:  python3 -m tools.media.play_state --root /path/to/live-photos --mode chronological --n 5 --duration 120
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.media import play_guard
from tools.paths import WORK_DIR

from simvltanea.authoring import (
    DEFAULT_PRESET,
    PlayError,
    apply_set,
    composition,
    config_digest,
    config_to_json,
    descriptions,
    describe_parameters,
    get_preset,
    load_presets_file,
    merged_table,
    parse_captured_at,
    schedule_play,
    validate_config,
)
from simvltanea.authoring import play_config, play_pool

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")      # short plain tokens only
VIDEO_SUFFIXES = (".mov", ".mp4", ".m4v")
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_LIST_ITEMS = 32
MAX_FILE_BYTES = 1024 * 1024
HASH_CHUNK = 1024 * 1024
MAX_FLAG_TEXT = 40                      # a yes-or-no flag written as text is at most this long
MAX_SAFE_SEED = 2 ** 53 - 1             # the largest integer seed a JSON number carries exactly (as in validate_config)
INVALID_FLAG = None                     # what stays where a flag was present but not a bool, number or short string
INVALID_SECTION = None                  # what stays where a whole section was present but not an object
INVALID_RATING = "invalid"              # the same for the sharing rating, which is read as text
DEFAULT_OUT = WORK_DIR / "play-state.json"
DEFAULT_N, DEFAULT_DURATION, DEFAULT_FPS = 5, 120.0, 24
RECORD_SCHEMA = "play-config/v1"        # what the record written next to every state is labelled

# Whitelists: only short plain tokens and numbers survive; no free text is carried over.
# Subjects and keywords are model-chosen words (the tag schema does not constrain them); they are
# used only for overlap statistics and never reach the state, the sidecar or the output.
ANALYSIS_LISTS = ("subjects", "keywords", "palette", "mood")
ANALYSIS_SCALARS = ("setting", "environment", "time_of_day", "motion_level", "shot")
PEOPLE_KEYS = ("count", "faces_visible", "minors_apparent")
PRIVACY_KEYS = ("readable_text", "license_plate", "document_or_screen", "location_identifiable",
                "sharing_sensitivity")
FEATURE_NUMBERS = ("luma", "luma_spread", "saturation", "hue", "motion")


def _tokens(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:MAX_LIST_ITEMS] if isinstance(item, str) and TOKEN_RE.fullmatch(item)]


_DROP = object()


def _flag_value(value: Any, key: str) -> Any:
    """A bool, number or short string is kept as it is. Anything else that is PRESENT stays as an explicit
    invalid marker (a null for a flag, ``"invalid"`` for the rating; the exclusion rules fail closed on both),
    so a malformed flag is never read as "absent". Only ``count`` and ``faces_visible`` (statistics) and a null
    sharing rating (schema v1 style, meaning "unknown") are dropped."""
    if isinstance(value, (bool, int, float)) or (isinstance(value, str) and len(value) <= MAX_FLAG_TEXT):
        return value
    if key in ("count", "faces_visible") or (key == "sharing_sensitivity" and value is None):
        return _DROP
    return INVALID_RATING if key == "sharing_sensitivity" else INVALID_FLAG


def sanitize_analysis(analysis: Any) -> dict[str, Any] | None:
    """The whitelisted view of a tag analysis.

    ``None`` means the record had no analysis at all (an untagged clip). A record that HAD an analysis
    but nothing usable survives as ``{}``: it is never mistaken for an untagged clip.
    """
    if analysis is None:
        return None
    if not isinstance(analysis, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ANALYSIS_LISTS:
        if isinstance(analysis.get(key), list):
            out[key] = _tokens(analysis[key])
    for key in ANALYSIS_SCALARS:
        if isinstance(analysis.get(key), str) and TOKEN_RE.fullmatch(analysis[key]):
            out[key] = analysis[key]
    for section, keys in (("people", PEOPLE_KEYS), ("privacy", PRIVACY_KEYS)):
        source = analysis.get(section)
        if section in analysis and not isinstance(source, dict):
            out[section] = INVALID_SECTION                  # present but not an object: an explicit marker, never "absent"
        elif isinstance(source, dict):
            out[section] = {key: _flag_value(source[key], key) for key in keys if key in source}
            for key in [k for k, v in out[section].items() if v is _DROP]:
                del out[section][key]
    safety = analysis.get("safety")
    if isinstance(safety, dict):
        verdict = safety.get("verdict")
        out["safety"] = {"verdict": verdict if isinstance(verdict, str) and len(verdict) <= 40 else None,
                         "categories": _tokens(safety.get("categories"))}
    return out


def sanitize_features(features: Any) -> dict[str, Any] | None:
    if not isinstance(features, dict) or not features:
        return None
    out: dict[str, Any] = {key: features[key] for key in FEATURE_NUMBERS
                           if isinstance(features.get(key), (int, float)) and not isinstance(features.get(key), bool)}
    if features.get("orientation") in ("portrait", "landscape"):
        out["orientation"] = features["orientation"]
    palette = features.get("palette")
    if isinstance(palette, list):
        out["palette"] = [{"hex": e["hex"], "share": e["share"]} for e in palette[:MAX_LIST_ITEMS]
                          if isinstance(e, dict) and isinstance(e.get("hex"), str) and len(e["hex"]) <= 9
                          and isinstance(e.get("share"), (int, float)) and not isinstance(e.get("share"), bool)]
    return out or None


def read_json(path: Path, limit: int = MAX_RECORD_BYTES) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("unreadable")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_media(receipt: Any, clip_id: str, originals: Path, verify: bool = False) -> dict[str, Any]:
    """sha256, duration and relative path of the receipt's primary video, or raise ValueError.

    The digest is the one the exporter wrote into the receipt after copying and hashing the file; by
    default it is trusted, because hashing every media file is proportional to the whole corpus. With
    ``verify`` the file's size and SHA-256 must match the receipt, or the clip is refused.
    """
    if not isinstance(receipt, dict) or not isinstance(receipt.get("video"), dict):
        raise ValueError("no video")
    video = receipt["video"]
    name = video.get("name")
    suffix = Path(name).suffix.lower() if isinstance(name, str) else ""
    if suffix not in VIDEO_SUFFIXES:
        raise ValueError("no video")
    files = receipt.get("files")
    entry = next((e for e in (files if isinstance(files, list) else ())
                  if isinstance(e, dict) and e.get("name") == name), {})
    sha = entry.get("sha256")
    duration = video.get("duration")
    if not isinstance(sha, str) or isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("no digest or duration")
    media = originals / clip_id / f"{clip_id}{suffix}"      # exports are renamed to <id>.<ext>
    if media.is_symlink() or not media.is_file():
        raise ValueError("media missing")
    if verify:
        size = entry.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or media.stat().st_size != size \
                or file_sha256(media) != sha.strip().lower():
            raise ValueError("media does not match its receipt")
    return {"sha256": sha.lower(), "duration": duration, "path": f"originals/{clip_id}/{clip_id}{suffix}"}


def clip_receipt(root: Path, clip_id: str, verify: bool = False) -> dict[str, Any]:
    """The export receipt's media entry for one clip, or raise. Never follows a link: a symlinked
    ``originals/`` or ``originals/<id>/`` is refused before anything inside it is read."""
    originals = root / "originals"
    clip_dir = originals / clip_id
    if originals.is_symlink() or clip_dir.is_symlink() or not clip_dir.is_dir():
        raise ValueError("linked or missing clip directory")
    return receipt_media(read_json(clip_dir / ".done"), clip_id, originals, verify)


def originals_index(originals: Path) -> dict[str, list[str]]:
    """``originals/`` listed ONCE: casefolded name -> every name that folds to it (sorted).

    Ids are matched to directories by comparing ``casefold()`` of the listed names, never by asking the volume to
    resolve a differently spelled path, so the result is the same on a case-sensitive and on a case-insensitive
    volume. A case-sensitive volume may hold several names that fold alike; all are kept. An unreadable or missing
    ``originals/`` gives an empty index.
    """
    try:
        names = os.listdir(originals)
    except OSError:
        return {}
    index: dict[str, list[str]] = {}
    for name in sorted(names):
        index.setdefault(name.casefold(), []).append(name)
    return index


def clip_dir_names(originals: Path, clip_id: str, index: dict[str, list[str]] | None = None) -> list[str]:
    """The names under ``originals/`` that are ``clip_id`` up to letter case; none for an id that is not opaque.

    Pass a prebuilt ``index`` (``originals_index``) to avoid listing the directory again for every id.
    """
    if not ID_RE.fullmatch(clip_id):
        return []
    if index is None:
        index = originals_index(originals)
    return list(index.get(clip_id.casefold(), ()))


def receipt_digests(path: Path) -> set[str]:
    """Every normalised ``files[].sha256`` of the export receipt at ``path``, read leniently; empty if unusable.

    Only for the exclusion direction, where a digest can only be added to the hidden set. Unlike
    ``receipt_media`` it does not need the media file to exist, a numeric duration, a video suffix or a
    non-linked receipt; it keeps the size bound and never raises for a missing, oversized, malformed or
    unexpectedly shaped file.
    """
    try:
        if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
            return set()
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return set()
    files = receipt.get("files") if isinstance(receipt, dict) else None
    entries = (e for e in (files if isinstance(files, list) else ()) if isinstance(e, dict))
    return {sha for sha in (play_pool.norm_sha256(e.get("sha256")) for e in entries) if sha}


def excluded_receipts(root: Path, ids: list[str], index: dict | None = None) -> tuple[set[str], set[str]]:
    """(digests, lower-cased ids) of the excluded ids that exist under ``originals/``.

    A clip that was exported but never tagged still has bytes that must stay hidden, wherever else they
    were imported; and an id with a directory exists, so it is not a typo. An id is matched to its directory
    by letter-case-insensitive name (``originals_index``, one listing for the whole call). This is the
    exclusion direction only, so it fails closed: a link to the clip directory (or to ``originals/``) is read
    through, and the receipt is read leniently (``receipt_digests``): a missing or linked media file, a linked
    ``.done`` or a text duration still contribute every digest the receipt names. Showing media stays strict
    in ``clip_receipt``. A directory that resolves into a ``.photoslibrary`` package is never read: the run is
    refused, as for ``--root``.
    """
    digests: set[str] = set()
    known: set[str] = set()
    originals = root / "originals"
    if index is None:
        index = originals_index(originals)               # one listing for the whole call (or the caller's)
    for clip_id in ids:
        for name in clip_dir_names(originals, clip_id, index):
            clip_dir = originals / name
            try:
                if not clip_dir.is_dir():
                    continue
                if play_guard.has_library_component(clip_dir, Path(os.path.realpath(clip_dir))):
                    raise play_guard.GuardError("Refusing to read from inside a Photos library package.")
            except OSError:
                continue
            known.add(clip_id.casefold())
            digests |= receipt_digests(clip_dir / ".done")
    return digests, known


def captured_at_of(root: Path, clip_id: str) -> str | None:
    """The normalised capture time from ``analysis/index/<id>.json`` (the only key ever read), or None."""
    path = root / "analysis" / "index" / f"{clip_id}.json"
    try:
        record = read_json(path)
    except (OSError, ValueError, RecursionError):
        return None
    seconds = parse_captured_at(record.get("captured_at")) if isinstance(record, dict) else None
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def unusable_digests(root: Path, unusable: list[dict[str, Any]], exclusion: dict[str, Any]) -> set[str]:
    """Digests of tagged clips skipped for DISPLAY (unusable receipt) that would themselves be excluded.

    A clip that cannot be shown still has bytes that must stay hidden wherever else they were imported, but
    only when its own tag says it must not be shown: a clean clip with a broken receipt hides nothing. Reading
    is lenient and in the exclusion direction only (``excluded_receipts``), so it fails closed. A record that
    cannot even be judged counts as excluded.
    """
    if not unusable:
        return set()
    index = originals_index(root / "originals")           # one listing for all of them
    digests: set[str] = set()
    for record in unusable:
        try:
            reason = play_pool.exclusion_reason(record, exclusion)
        except Exception:
            reason = "malformed_record"
        if reason:
            digests |= excluded_receipts(root, [record["id"]], index)[0]
    return digests


def load_pool(root: Path, verify_media: bool = False,
              unusable: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], Counter]:
    """Build the scheduler pool from ``root``. Returns (records, counts of skipped reasons).

    ``verify_media`` checks every media file's size and SHA-256 against its receipt (slow: reads the corpus).
    A list passed as ``unusable`` receives the id, sanitised analysis and review flag of every tagged clip that
    was skipped because its receipt failed the display checks (``unusable_digests`` judges them later).

    One malformed record never stops a run: every record is handled on its own and counted.
    """
    skipped: Counter = Counter()
    pool = []
    tags = root / "analysis" / "tags"
    for path in sorted(tags.glob("*.json")):
        clip_id = path.stem
        if not ID_RE.fullmatch(clip_id):
            skipped["id_not_opaque"] += 1
            continue
        try:
            record = read_json(path)
        except (OSError, ValueError, RecursionError):
            skipped["unreadable_tag_record"] += 1
            continue
        try:
            if not isinstance(record, dict) or record.get("uuid", clip_id) != clip_id:
                skipped["tag_record_id_mismatch"] += 1
                continue
            try:
                media = clip_receipt(root, clip_id, verify_media)
            except (OSError, ValueError, RecursionError):
                skipped["no_usable_export_receipt"] += 1
                if unusable is not None:
                    unusable.append({"id": clip_id, "analysis": sanitize_analysis(record.get("analysis")),
                                     "needs_review": bool(record.get("needs_review") or record.get("error") is not None)})
                continue
            entry = {"id": clip_id, **media,
                     "analysis": sanitize_analysis(record.get("analysis")),
                     "features": sanitize_features(record.get("features")),
                     "needs_review": bool(record.get("needs_review") or record.get("error") is not None)}   # an error code is never read
            captured = captured_at_of(root, clip_id)
            if captured:
                entry["captured_at"] = captured
            pool.append(entry)
        except Exception:                                   # a malformed record is counted, never fatal
            skipped["malformed_record"] += 1
    return pool, skipped


PRIVACY_NOTICE = ("private: the state and its .play.json carry Photos-library clip ids and media paths; "
                  "this is a private artifact, never commit it and never share it")


def seed_value(text: str) -> int | str:
    """Seed text by the one rule of ``play_config.seed_from_text`` (``--seed``, ``--set seed=`` and config files)."""
    return play_config.seed_from_text(text)


def parse_pin(text: str) -> tuple[str, str]:
    loop, sep, clip = text.partition("=")
    if not sep or not ID_RE.fullmatch(loop) or not ID_RE.fullmatch(clip):
        raise argparse.ArgumentTypeError("--pin takes LOOP=ID using [A-Za-z0-9_-] only")
    return loop, clip


def opaque_id(text: str) -> str:
    if not ID_RE.fullmatch(text):
        raise argparse.ArgumentTypeError("ids must match [A-Za-z0-9_-]{1,80}")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a composition state for a play mode from private records.")
    parser.add_argument("--root", help="private directory holding analysis/tags and originals")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="state file; under var/work/ or outside every Git working tree (default var/work/play-state.json)")
    parser.add_argument("--force", action="store_true", help="replace existing output files")
    parser.add_argument("--list-modes", action="store_true", help="name every mode (built in and from --presets-file)")
    parser.add_argument("--describe", action="store_true", help="print every parameter with range, default and effect")
    parser.add_argument("--json", action="store_true", help="with --describe or --list-modes: machine-readable output")
    parser.add_argument("--mode", default=DEFAULT_PRESET, help=f"saved mode to start from (default {DEFAULT_PRESET})")
    parser.add_argument("--presets-file", help="JSON file of your own modes (add or override by name)")
    parser.add_argument("--config", help="JSON file laid over the mode (partial is fine), or a <name>.play.json record "
                        "written by an earlier run: its config, n, duration and fps replay that run")
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="SECTION.KEY=VALUE",
                        help="override one value, e.g. --set relation.strength=-2 (repeatable)")
    parser.add_argument("--seed", default=None, help="integer or string (default: the mode's seed, else 0)")
    parser.add_argument("--n", type=int, default=None, help=f"number of simultaneous loops (2..7; default the record's, else {DEFAULT_N})")
    parser.add_argument("--duration", type=float, default=None,
                        help=f"seconds of composition (at most 600 at 24 fps; default the record's, else {DEFAULT_DURATION:g})")
    parser.add_argument("--fps", type=int, default=None, help=f"frames per second (default the record's, else {DEFAULT_FPS})")
    parser.add_argument("--anchor", dest="anchors", action="append", type=opaque_id, default=[], metavar="ID",
                        help="add to relation.anchors; unless you set relation.anchor_pull (even to 0) it becomes 1.0, recorded in the sidecar")
    parser.add_argument("--pin", dest="pins", action="append", type=parse_pin, default=[], metavar="LOOP=ID",
                        help="add to path.pins: that loop never changes")
    parser.add_argument("--verify-media", action="store_true",
                        help="check each media file's size and SHA-256 against its export receipt and skip mismatches "
                             "(reads every file; by default the receipt is trusted)")
    parser.add_argument("--exclude-id", dest="exclude_ids", action="append", type=opaque_id, default=[], metavar="ID",
                        help="add to exclusion.exclude_ids")
    return parser


def read_small(path: str, what: str) -> str:
    file = Path(path).expanduser()
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
        raise SystemExit(f"{what} must be a regular JSON file under 1 MiB.")
    return file.read_text(encoding="utf-8")


def resolve_table(args: argparse.Namespace) -> dict[str, Any]:
    user = load_presets_file(read_small(args.presets_file, "--presets-file")) if args.presets_file else {}
    return merged_table(user)


def record_config(record: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """The inner config of a ``play-config/v1`` record, and the run it describes kept on ``args`` for the defaults.

    Only that schema is accepted; the record's n, duration and fps fill in what the command line leaves out, and
    ``--mode`` is moot because the record's config is complete.
    """
    if record.get("schema") != RECORD_SCHEMA:
        raise PlayError(f"--config: unknown record schema; this command reads {RECORD_SCHEMA!r}")
    inner = record.get("config")
    if not isinstance(inner, dict):
        raise PlayError(f"--config: a {RECORD_SCHEMA} record needs a 'config' object")
    args.record = record
    return inner


def apply_run_defaults(args: argparse.Namespace) -> None:
    """Fill n, duration and fps: the command line, else the replayed record, else the defaults."""
    record = getattr(args, "record", None) or {}
    for name, key, default in (("n", "n", DEFAULT_N), ("duration", "duration_seconds", DEFAULT_DURATION),
                               ("fps", "fps", DEFAULT_FPS)):
        if getattr(args, name) is None:
            setattr(args, name, record.get(key, default))


def config_from_args(args: argparse.Namespace, table: dict[str, Any]) -> dict[str, Any]:
    """mode -> --config -> --set -> shortcut flags -> --seed, validated as a whole."""
    base = get_preset(args.mode, table)
    raw: dict[str, Any] = {}
    if args.config:
        try:
            raw = json.loads(read_small(args.config, "--config"))
        except (ValueError, RecursionError):
            raise PlayError("--config is not valid JSON") from None
        if not isinstance(raw, dict):
            raise PlayError("--config must be a JSON object")
        if "schema" in raw:                                  # a record written by an earlier run: replay it
            raw = record_config(raw, args)
        raw = play_config.with_seed_text_rule(raw)                       # seed text follows the same rule as --seed and --set
    for assignment in args.sets:
        raw = apply_set(raw, assignment)
    cfg = validate_config(raw, base)
    extra: dict[str, Any] = {}
    if args.anchors:
        pull = cfg["relation"]["anchor_pull"]
        extra.setdefault("relation", {})["anchors"] = [*cfg["relation"]["anchors"], *args.anchors]
        if pull == 0 and "anchor_pull" not in raw.get("relation", {}):      # an explicit value, even 0, always wins
            extra["relation"]["anchor_pull"] = 1.0
    if args.pins:
        extra.setdefault("path", {})["pins"] = [*cfg["path"]["pins"], *map(list, args.pins)]
    if args.exclude_ids:
        extra.setdefault("exclusion", {})["exclude_ids"] = [*cfg["exclusion"]["exclude_ids"], *args.exclude_ids]
    if args.seed is not None:
        extra["seed"] = seed_value(args.seed)
    return validate_config(extra, cfg) if extra else cfg


def describe_text() -> str:
    lines = []
    for p in describe_parameters():
        if "min" in p:
            domain = f"number {p['min']}..{p['max']}" if p["type"] == "number" else f"integer {p['min']}..{p['max']}"
        elif "choices" in p:
            domain = " | ".join(p["choices"])
        else:
            domain = p["type"]
        lines.append(f"{p['path']}  [{domain}]  default {json.dumps(p['default'])}\n    {p['description']}")
    return "\n".join(lines)


def sidecar_for(out: Path) -> Path:
    return out.with_name(out.stem + ".play.json")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        table = resolve_table(args)
        if args.list_modes:
            names = descriptions(table)
            if args.json:
                print(json.dumps(names, indent=2, sort_keys=True))
            else:
                print("\n".join(f"{name}: {text}" for name, text in sorted(names.items())))
            return 0
        if args.describe:
            print(json.dumps(describe_parameters(), indent=2) if args.json else describe_text())
            return 0
        if not args.root:
            raise SystemExit("--root is required (or use --list-modes / --describe).")
        root, out = play_guard.resolve_root(args.root), play_guard.resolve_out(args.out)
        play_guard.check_analysis_dirs(root)
        side = sidecar_for(out)
        for target in (out, side):
            if target.exists() or target.is_symlink():
                if not args.force:
                    raise SystemExit("output already exists; pass --force to replace it.")
        cfg = config_from_args(args, table)
        apply_run_defaults(args)
        unusable: list[dict[str, Any]] = []
        pool, skipped = load_pool(root, args.verify_media, unusable)
        listed = cfg["exclusion"]["exclude_ids"]
        shas, receipted = excluded_receipts(root, listed)
        shas |= unusable_digests(root, unusable, cfg["exclusion"])
        known = {str(r["id"]).casefold() for r in pool} | receipted
        missing = len({i.casefold() for i in args.exclude_ids} - known)
        if missing:
            raise PlayError(f"{missing} --exclude-id value(s) match no clip in the pool (letter case is ignored); "
                            "nothing was written")
        result = schedule_play(pool, args.n, cfg, args.duration, fps=args.fps, extra_excluded_shas=shas,
                               extra_known_ids=receipted)
    except (PlayError, composition.StateError) as exc:
        raise SystemExit(f"play: {exc}") from None
    state, report, cfg = result["state"], result["report"], result["config"]
    ids_now = sorted(result["model"].profiles)
    ids_sha = hashlib.sha256("\n".join(ids_now).encode()).hexdigest()
    replayed = getattr(args, "record", None)
    text = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    digest = hashlib.sha256(composition.canonical_json(state).encode("utf-8")).hexdigest()
    ids = ids_now
    sidecar = {"schema": RECORD_SCHEMA, "config": cfg, "config_sha256": config_digest(cfg),
               "seed": cfg["seed"], "n": args.n, "duration_seconds": args.duration, "fps": args.fps,
               "eligible_pool": {"count": len(ids), "ids_sha256": ids_sha},
               "state_sha256": digest, "render_segments": report["render_segments"],
               "renderable": report["renderable"], "render_segment_limit": report["render_segment_limit"]}
    out, side = play_guard.resolve_out(out), play_guard.resolve_out(side)   # the folder may have changed since the start
    play_guard.write_private_file(out, text.encode("utf-8"), args.force)
    side = play_guard.resolve_out(side)                                      # and again right before the second write
    play_guard.write_private_file(side, config_to_json(sidecar).encode("utf-8"), args.force)
    print(f"pool: {len(pool)} usable records, {report['eligible']} eligible, "
          f"{sum(report['excluded_counts'].values())} excluded {report['excluded_counts']}, "
          f"{sum(skipped.values())} skipped {dict(sorted(skipped.items()))}")
    if report["order_dropped"]:
        print(f"order: {report['order_dropped']} clips lack a value on the order axis and are not shown")
    if report["unmatched_exclude_ids"]:
        near = report["unmatched_exclude_ids_near"]
        print(f"warning: {report['unmatched_exclude_ids']} exclude id(s) match no clip in the pool; those are NOT excluded"
              + (f" ({near} of them differ from a pool id by one character)" if near else ""), file=sys.stderr)
    if isinstance(replayed, dict) and isinstance(replayed.get("eligible_pool"), dict) \
            and replayed["eligible_pool"].get("ids_sha256") != ids_sha:
        print(f"warning: the eligible pool differs from the one in the record (it had "
              f"{replayed['eligible_pool'].get('count')} clips, now {len(ids)}), so the state is not a replay of it",
              file=sys.stderr)
    print(f"config: sha256={config_digest(cfg)} seed={json.dumps(cfg['seed'])}")
    print(f"state: n={args.n} frames={state['frames']} fps={state['fps']} "
          f"sources={len(state['sources'])} events={len(state['events'])} "
          f"render_segments={report['render_segments']} sha256={digest}")
    if not report["renderable"]:
        over = report["render_segments"] - report["render_segment_limit"]
        print(f"WARNING: NOT RENDERABLE OFFLINE: this state needs {report['render_segments']} render segments and the "
              f"offline renderer allows {report['render_segment_limit']} ({over} over); render_triptych will stop with "
              f"\"composition exceeds segment resource guard\". The state is still written and still compiles with "
              f"compile_plan (its separate limit is {composition.MAX_SEGMENTS} spans per loop, which this state "
              f"satisfies). Shorten --duration to render it, or pass --set limits.refuse_unrenderable=true to refuse "
              f"such states.", file=sys.stderr)
    elif report["over_configured_limit"]:
        print(f"warning: this state needs {report['render_segments']} render segments, over your "
              f"limits.max_render_segments={report['configured_render_segment_limit']}; the offline renderer itself "
              f"allows {report['render_segment_limit']}, so it can still be rendered.", file=sys.stderr)
    print(f"wrote {out}")
    print(f"wrote {side}")
    print(PRIVACY_NOTICE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
