#!/usr/bin/env python3
"""Build a content-addressed atom map for triptych media.

The default mode writes small JSON/Markdown receipts under work/. It reads media
bytes to compute hashes and chunk identities, but it does not duplicate the
media. Use --write-chunks only when intentionally materializing a local chunk
store. New receipt paths are required; existing files are never overwritten.
"""

from __future__ import annotations
from tools.paths import resolve_references, LAYOUT
from tools.preservation.media_chunks import (
    IntegrityError, MAX_ATOMS, MAX_CHUNKS, MAX_CHUNK_BYTES, MAX_MANIFEST_BYTES,
    checked_path, fingerprint, integer,
    materialize, new_output, regular_reader,
)

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.paths import REPO_ROOT, VAR_DIR, EXAMPLES_DIR, WORK_DIR


ROOT = VAR_DIR
DEFAULT_OUTPUT = WORK_DIR / "media-atoms.json"
DEFAULT_SUMMARY = WORK_DIR / "media-atoms.md"
DEFAULT_CHUNK_DIR = WORK_DIR / "atom-chunks"
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024

MEDIA_SUFFIXES = {
    ".aac",
    ".aiff",
    ".flac",
    ".heic",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".wav",
    ".webm",
}

LANE_POLICIES: dict[str, dict[str, Any]] = {
    "samples": {
        "role": "staged selected source",
        "privacy": "private",
        "disposable": False,
        "decode": "keep or restage from Photos/Finder source before regenerating public media",
    },
    "renders": {
        "role": "generated render cache",
        "privacy": "public-safe after review",
        "disposable": True,
        "decode": "regenerate from project manifests and staged sources",
    },
    "site": {
        "role": "generated public site",
        "privacy": "public after verify_public_site.py",
        "disposable": True,
        "decode": "regenerate with build_site_index.py and package_public_site.py",
    },
    "packages": {
        "role": "generated hostable package",
        "privacy": "public after verify_package.py",
        "disposable": True,
        "decode": "regenerate from site/ with package_public_site.py",
    },
    "work": {
        "role": "private receipts and local control plane",
        "privacy": "private",
        "disposable": False,
        "decode": "preserve as receipts; do not publish",
    },
}


@dataclass
class Chunk:
    index: int
    offset: int
    bytes: int
    sha256: str


@dataclass
class Atom:
    id: str
    path: str
    lane: str
    role: str
    privacy: str
    disposable: bool
    bytes: int
    modified: str
    sha256: str
    media: bool
    chunks: list[Chunk]
    ffprobe: dict[str, Any] | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def parse_lanes(value: str) -> list[str]:
    lanes = [lane.strip() for lane in value.split(",") if lane.strip()]
    unknown = [lane for lane in lanes if lane not in LANE_POLICIES]
    if unknown:
        raise SystemExit(f"unknown lane(s): {', '.join(unknown)}")
    return lanes


def iter_files(lanes: list[str], *, exclude: tuple[Path, ...] = ()) -> Iterable[Path]:
    for lane in lanes:
        root = LAYOUT.path(lane)
        if root.is_symlink():
            raise IntegrityError("symlinked input lane")
        if not root.exists():
            continue
        checked_path(root, ROOT)
        def excluded(path: Path) -> bool:
            return any(path == item or path.is_relative_to(item) for item in exclude)
        def traversal_error(error):
            raise error
        for current_root, dirs, files in os.walk(root, followlinks=False, onerror=traversal_error):
            kept = []
            for name in sorted(dirs):
                path = Path(current_root) / name
                if excluded(path):
                    continue
                if path.is_symlink():
                    raise IntegrityError("symlinked input directory")
                if name not in {"__pycache__", ".git"} and not name.startswith("."):
                    kept.append(name)
            dirs[:] = kept
            for name in sorted(files):
                path = Path(current_root) / name
                if excluded(path) or name in {".gitkeep", ".DS_Store"}:
                    continue
                if path.is_symlink() or not path.is_file():
                    raise IntegrityError("non-regular input file")
                yield path


def is_media(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_SUFFIXES


def materialize_chunk(chunk_dir: Path, digest: str, data: bytes) -> str:
    target = materialize(chunk_dir, digest, data, ROOT)
    return target.relative_to(ROOT).as_posix()


def hash_file(
    path: Path,
    *,
    chunk_bytes: int,
    write_chunks: bool,
    chunk_dir: Path,
) -> tuple[str, list[Chunk]]:
    integer(chunk_bytes, "chunk byte bound", minimum=1, maximum=MAX_CHUNK_BYTES)
    path = checked_path(path, ROOT)
    checked_path(chunk_dir, ROOT)
    file_hash = hashlib.sha256()
    chunks: list[Chunk] = []
    offset = 0
    index = 0
    with regular_reader(path) as handle:
        if (os.fstat(handle.fileno()).st_size + chunk_bytes - 1) // chunk_bytes > MAX_CHUNKS:
            raise IntegrityError("source exceeds the supported chunk-count bound")
        while True:
            data = handle.read(chunk_bytes)
            if not data:
                break
            if index >= MAX_CHUNKS:
                raise IntegrityError("source exceeds the supported chunk-count bound")
            digest = hashlib.sha256(data).hexdigest()
            if write_chunks:
                materialize_chunk(chunk_dir, digest, data)
            file_hash.update(data)
            chunks.append(Chunk(index=index, offset=offset, bytes=len(data), sha256=digest))
            offset += len(data)
            index += 1
    return file_hash.hexdigest(), chunks


def ffprobe(path: Path) -> dict[str, Any] | None:
    if shutil.which("ffprobe") is None or not is_media(path):
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip() or "ffprobe failed"}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return {"error": f"ffprobe JSON parse failed: {error}"}

    streams = data.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    first_video = video_streams[0] if video_streams else {}
    fmt = data.get("format", {})
    return {
        "duration_seconds": _float_or_none(fmt.get("duration")),
        "bit_rate": _int_or_none(fmt.get("bit_rate")),
        "video_streams": len(video_streams),
        "audio_streams": len(audio_streams),
        "video_codec": first_video.get("codec_name"),
        "width": first_video.get("width"),
        "height": first_video.get("height"),
    }


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def atom_for_path(
    path: Path,
    *,
    chunk_bytes: int,
    write_chunks: bool,
    chunk_dir: Path,
    no_ffprobe: bool,
) -> Atom:
    lane = next(role for role in LANE_POLICIES if path.resolve().is_relative_to(LAYOUT.path(role)))
    policy = LANE_POLICIES[lane]
    stat = path.stat(follow_symlinks=False)
    digest, chunks = hash_file(
        path,
        chunk_bytes=chunk_bytes,
        write_chunks=write_chunks,
        chunk_dir=chunk_dir,
    )
    probe = None if no_ffprobe else ffprobe(path)
    if fingerprint(stat) != fingerprint(path.stat(follow_symlinks=False)):
        raise IntegrityError("source changed while being inventoried")
    if sum(chunk.bytes for chunk in chunks) != stat.st_size:
        raise IntegrityError("source size differs from hashed bytes")
    return Atom(
        id=f"sha256:{digest}",
        path=repo_rel(path),
        lane=lane,
        role=policy["role"],
        privacy=policy["privacy"],
        disposable=bool(policy["disposable"]),
        bytes=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        sha256=digest,
        media=is_media(path),
        chunks=chunks,
        ffprobe=probe,
    )


def load_project_recipes() -> list[dict[str, Any]]:
    project_paths = [EXAMPLES_DIR / "project.example.json"]
    work_root = WORK_DIR
    if work_root.exists():
        project_paths.extend(sorted(work_root.glob("project*.json")))
        project_paths.extend(sorted(work_root.glob("editions/*/project.json")))

    recipes: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in project_paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            data = resolve_references(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        exports = data.get("exports") if isinstance(data.get("exports"), list) else []
        output_files = [
            item.get("output_file")
            for item in exports
            if isinstance(item, dict) and isinstance(item.get("output_file"), str)
        ]
        recipes.append(
            {
                "project": path.relative_to(REPO_ROOT).as_posix(),
                "title": data.get("title"),
                "input_dir": data.get("input_dir"),
                "timing_mode": data.get("timing_mode"),
                "render": data.get("render"),
                "canvas": data.get("canvas"),
                "outputs": output_files,
                "regenerate": f"python3 -m tools.editions.export_project {path.relative_to(REPO_ROOT).as_posix()}",
            }
        )
    return recipes


def summarize(atoms: list[Atom], recipes: list[dict[str, Any]], *, chunk_bytes: int) -> str:
    by_lane: dict[str, dict[str, int]] = {}
    for atom in atoms:
        lane = by_lane.setdefault(atom.lane, {"files": 0, "bytes": 0, "chunks": 0})
        lane["files"] += 1
        lane["bytes"] += atom.bytes
        lane["chunks"] += len(atom.chunks)

    lines = [
        "# Triptych Media Atoms",
        "",
        f"Generated: {utc_now()}",
        f"Chunk size: {human_bytes(chunk_bytes)}",
        "",
        "## Lane Summary",
        "",
        "| Lane | Files | Size | Chunks | Policy |",
        "|---|---:|---:|---:|---|",
    ]
    for lane_name in sorted(by_lane):
        totals = by_lane[lane_name]
        policy = LANE_POLICIES[lane_name]
        disposable = "regenerable" if policy["disposable"] else "preserve/restage"
        lines.append(
            f"| {lane_name} | {totals['files']} | {human_bytes(totals['bytes'])} | "
            f"{totals['chunks']} | {disposable}; {policy['privacy']} |"
        )

    lines.extend(
        [
            "",
            "## Decode Model",
            "",
            "- Source atoms in `samples/` are private selected media. Keep them or restage them from the original library before deleting local copies.",
            "- Generated atoms in `renders/`, `site/`, and `packages/` are reconstructable from recipes and verification gates.",
            "- Chunk hashes let a future sync layer verify which bytes are already present before copying or rebuilding anything.",
            "- The manifest is the small object; media bytes only become matter when a file or chunk is actually required.",
            "",
            "## Recipes",
            "",
        ]
    )
    for recipe in recipes:
        title = recipe.get("title") or recipe["project"]
        lines.append(f"- `{recipe['project']}`: {title}")
        lines.append(f"  - regenerate: `{recipe['regenerate']}`")
        if recipe.get("outputs"):
            lines.append(f"  - outputs: {len(recipe['outputs'])}")
    return "\n".join(lines) + "\n"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    lanes = parse_lanes(args.lanes)
    integer(args.chunk_bytes, "chunk byte bound", minimum=1, maximum=MAX_CHUNK_BYTES)
    args.output = checked_path(args.output, ROOT)
    args.summary = checked_path(args.summary, ROOT)
    args.chunk_dir = checked_path(args.chunk_dir, ROOT)
    if args.output == args.summary or any(p.is_relative_to(args.chunk_dir) for p in (args.output, args.summary)):
        raise IntegrityError("receipt and chunk-store destinations overlap")
    if any(LAYOUT.path(lane).is_relative_to(args.chunk_dir) for lane in lanes):
        raise IntegrityError("chunk store cannot contain an entire selected input lane")
    if args.limit is not None:
        integer(args.limit, "file limit")
    paths = []
    for path in iter_files(lanes, exclude=(args.output, args.summary, args.chunk_dir)):
        if len(paths) >= MAX_ATOMS:
            raise IntegrityError("selection exceeds the supported atom-count bound")
        paths.append(path)
    paths.sort(key=repo_rel)
    if args.limit is not None:
        paths = paths[: args.limit]

    atoms = [
        atom_for_path(
            path,
            chunk_bytes=args.chunk_bytes,
            write_chunks=args.write_chunks,
            chunk_dir=args.chunk_dir,
            no_ffprobe=args.no_ffprobe,
        )
        for path in paths
    ]
    recipes = load_project_recipes()
    total_bytes = sum(atom.bytes for atom in atoms)
    payload = {
        "schema": "triptych.media-atoms.v1",
        "root": str(ROOT),
        "generated_at": utc_now(),
        "selection_complete": args.limit is None,
        "chunk_bytes": args.chunk_bytes,
        "copy_strategy": "manifest-only" if not args.write_chunks else "materialized-local-chunks",
        "lanes": {lane: LANE_POLICIES[lane] for lane in lanes},
        "totals": {
            "files": len(atoms),
            "bytes": total_bytes,
            "human_size": human_bytes(total_bytes),
            "chunks": sum(len(atom.chunks) for atom in atoms),
            "media_files": sum(1 for atom in atoms if atom.media),
            "disposable_bytes": sum(atom.bytes for atom in atoms if atom.disposable),
            "source_bytes": sum(atom.bytes for atom in atoms if not atom.disposable),
        },
        "recipes": recipes,
        "atoms": [asdict(atom) for atom in atoms],
    }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lanes",
        default="samples,renders,site,packages",
        help="comma-separated lanes to atomize (default: samples,renders,site,packages)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    parser.add_argument("--chunk-dir", type=Path, default=DEFAULT_CHUNK_DIR)
    parser.add_argument("--limit", type=int, default=None, help="limit file count for smoke tests")
    parser.add_argument("--no-ffprobe", action="store_true", help="skip media probing")
    parser.add_argument(
        "--write-chunks",
        action="store_true",
        help="materialize a local chunk store under --chunk-dir; duplicates media bytes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payload = build_payload(args)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    summary = args.summary if args.summary.is_absolute() else ROOT / args.summary
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise IntegrityError("manifest exceeds the supported size bound; use smaller selections")
    with new_output(output) as destination:
        destination.write(encoded)
    text = summarize(
            [
                Atom(
                    id=item["id"],
                    path=item["path"],
                    lane=item["lane"],
                    role=item["role"],
                    privacy=item["privacy"],
                    disposable=item["disposable"],
                    bytes=item["bytes"],
                    modified=item["modified"],
                    sha256=item["sha256"],
                    media=item["media"],
                    chunks=[Chunk(**chunk) for chunk in item["chunks"]],
                    ffprobe=item.get("ffprobe"),
                )
                for item in payload["atoms"]
            ],
            payload["recipes"],
            chunk_bytes=args.chunk_bytes,
        )
    with new_output(summary) as destination:
        destination.write(text.encode())
    print(f"media atoms: {payload['totals']['files']} files, {payload['totals']['human_size']}")
    print(f"wrote {output.relative_to(ROOT)}")
    print(f"wrote {summary.relative_to(ROOT)}")
    if args.write_chunks:
        print(f"wrote chunks under {args.chunk_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
