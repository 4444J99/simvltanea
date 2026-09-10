#!/usr/bin/env python3
"""Build lightweight motion clips from still-heavy Photos albums."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from import_photos import (
    DEFAULT_EXCLUDE_FILE,
    DEFAULT_LIBRARY,
    DEFAULT_PHOTOS_EXPORT_WORK_DIR,
    DEFAULT_PROJECT,
    SCRIPT_DIR,
    UUID_RE,
    Asset,
    album_asset_pks,
    album_descendants,
    album_display_path,
    album_children,
    apple_time,
    date_filtered_assets,
    exclude_assets,
    export_original_from_photos,
    filter_assets_by_album,
    load_albums,
    load_excluded_uuids,
    load_project,
    match_albums,
    normalize_export_paths,
    prepare_output_dir,
    photos_db_path,
    relative_to_base,
    require_inside,
    safe_name,
    select_assets,
    sort_key,
    source_rank,
)


DEFAULT_LOCAL_PROJECT = SCRIPT_DIR / "work" / "project.photos-visual-local.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "samples" / "photos-visual-import"
DEFAULT_MODEL_OUTPUT_DIR = SCRIPT_DIR / "work" / "photos-visual-models"
IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
}
MOTION_MODES = {"alternate", "hold", "zoom-in", "zoom-out", "pan-left", "pan-right"}


@dataclass(frozen=True)
class VisualItem:
    asset: Asset
    source_path: Path | None
    destination_path: Path
    photos_export: bool
    duration: float


@dataclass(frozen=True)
class ModelItem:
    asset: Asset
    source_path: Path | None
    destination_path: Path
    photos_export: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import still Photos album material as generated lightweight MP4 "
            "motion clips for the triptych canon."
        )
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY,
        help="Path to a .photoslibrary package. Defaults to ~/Pictures/Photos Library.photoslibrary.",
    )
    parser.add_argument(
        "--source-project",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Base project manifest to copy settings from.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=DEFAULT_LOCAL_PROJECT,
        help="Generated local project manifest. Defaults to work/project.photos-visual-local.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for generated motion clips. Defaults to samples/photos-visual-import/.",
    )
    parser.add_argument(
        "--album",
        action="append",
        default=[],
        help="Import still assets from a Photos album or folder title/path. Can be repeated.",
    )
    parser.add_argument(
        "--album-match",
        choices=("exact", "contains"),
        default="exact",
        help="How --album should match Photos album titles or paths. Defaults to exact.",
    )
    parser.add_argument(
        "--model-album",
        action="append",
        default=[],
        help="Optional Photos album/path to stage as an arrangement model reference.",
    )
    parser.add_argument(
        "--model-album-match",
        choices=("exact", "contains"),
        default="exact",
        help="How --model-album should match Photos album titles or paths. Defaults to exact.",
    )
    parser.add_argument(
        "--model-output-dir",
        type=Path,
        default=DEFAULT_MODEL_OUTPUT_DIR,
        help="Ignored local directory for staged arrangement model stills.",
    )
    parser.add_argument(
        "--model-limit",
        type=int,
        default=3,
        help="Maximum arrangement model stills to stage. Defaults to 3.",
    )
    parser.add_argument(
        "--list-albums",
        action="store_true",
        help="List Photos albums/folders with visual still counts, then exit.",
    )
    parser.add_argument("--limit", type=int, default=24, help="Maximum stills to convert.")
    parser.add_argument(
        "--all-local",
        action="store_true",
        help="Convert every matching local still. This can be large and slow.",
    )
    parser.add_argument(
        "--order",
        choices=("recent", "oldest", "filename"),
        default="oldest",
        help="Order selected stills before conversion. Defaults to oldest.",
    )
    parser.add_argument("--start-date", help="Only select assets created on or after YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Only select assets created before or on YYYY-MM-DD.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many assets after filtering.")
    parser.add_argument("--random-seed", help="Shuffle filtered assets with a stable seed.")
    parser.add_argument(
        "--exclude-file",
        type=Path,
        default=DEFAULT_EXCLUDE_FILE,
        help="Text file of source UUIDs to exclude. Defaults to work/photos-exclude-uuids.txt.",
    )
    parser.add_argument(
        "--exclude-uuid",
        action="append",
        default=[],
        help="Source UUID to exclude for this import. Can be repeated.",
    )
    parser.add_argument(
        "--photos-export-missing",
        action="store_true",
        help="Ask Photos.app to export selected originals when local still files are absent.",
    )
    parser.add_argument(
        "--photos-export-work-dir",
        type=Path,
        default=DEFAULT_PHOTOS_EXPORT_WORK_DIR,
        help="Temporary directory for Photos.app exports. Defaults to work/photos-export/.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=3.2,
        help="Default generated clip duration. Defaults to 3.2 seconds.",
    )
    parser.add_argument(
        "--duration-pattern",
        help="Comma-separated generated durations, cycled per still, for imperfect cadence.",
    )
    parser.add_argument("--width", type=int, default=720, help="Generated clip width. Defaults to 720.")
    parser.add_argument("--height", type=int, default=1280, help="Generated clip height. Defaults to 1280.")
    parser.add_argument("--fps", type=int, default=12, help="Generated clip frame rate. Defaults to 12.")
    parser.add_argument("--crf", type=int, default=38, help="Generated clip x264 CRF. Defaults to 38.")
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="Generated clip x264 preset. Defaults to veryfast.",
    )
    parser.add_argument(
        "--motion",
        choices=sorted(MOTION_MODES),
        default="alternate",
        help="Motion treatment for stills. Defaults to alternate.",
    )
    parser.add_argument("--render", action="store_true", help="Run export_project.py after import.")
    parser.add_argument("--only", help="Comma-separated export names to render when --render is used.")
    parser.add_argument("--dry-run", action="store_true", help="Print import actions only.")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing generated clips instead of replacing the output directory.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.duration_seconds <= 0:
        raise SystemExit("--duration-seconds must be positive.")
    if args.limit <= 0 and not args.all_local:
        raise SystemExit("--limit must be positive unless --all-local is used.")
    if args.model_limit < 0:
        raise SystemExit("--model-limit must be greater than or equal to 0.")
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive.")
    if args.fps <= 0:
        raise SystemExit("--fps must be positive.")
    if not 0 <= args.crf <= 51:
        raise SystemExit("--crf must be between 0 and 51.")


def duration_pattern(value: str | None, fallback: float) -> list[float]:
    if not value:
        return [fallback]
    durations = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            duration = float(raw)
        except ValueError as error:
            raise SystemExit(f"Invalid duration value: {raw!r}") from error
        if duration <= 0:
            raise SystemExit("Duration pattern values must be positive.")
        durations.append(duration)
    return durations or [fallback]


def load_visual_assets(db_path: Path, order: str) -> list[Asset]:
    query = """
        select
            a.Z_PK,
            a.ZUUID,
            a.ZDATECREATED,
            a.ZADDEDDATE,
            0.0,
            coalesce(a.ZWIDTH, 0),
            coalesce(a.ZHEIGHT, 0),
            coalesce(a.ZFILENAME, ''),
            aa.ZORIGINALFILENAME,
            coalesce(a.ZPLAYBACKSTYLE, 0)
        from ZASSET a
        left join ZADDITIONALASSETATTRIBUTES aa on aa.ZASSET = a.Z_PK
        where coalesce(a.ZPLAYBACKSTYLE, 0) != 4
          and coalesce(a.ZTRASHEDSTATE, 0) = 0
          and coalesce(a.ZHIDDEN, 0) = 0
          and coalesce(a.ZVISIBILITYSTATE, 0) = 0
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query).fetchall()

    assets = [
        Asset(
            pk=int(row[0]),
            uuid=str(row[1]),
            created=row[2],
            added=row[3],
            duration=float(row[4]),
            width=int(row[5]),
            height=int(row[6]),
            filename=str(row[7]),
            original_filename=row[8],
            playback_style=int(row[9]),
        )
        for row in rows
        if row[1]
    ]
    return sorted(assets, key=lambda asset: sort_key(asset, order))


def album_visual_counts(db_path: Path) -> dict[int, int]:
    query = """
        select rel.Z_33ALBUMS, count(distinct a.Z_PK)
        from Z_33ASSETS rel
        join ZASSET a on a.Z_PK = rel.Z_3ASSETS
        where coalesce(a.ZPLAYBACKSTYLE, 0) != 4
          and coalesce(a.ZTRASHEDSTATE, 0) = 0
          and coalesce(a.ZHIDDEN, 0) = 0
          and coalesce(a.ZVISIBILITYSTATE, 0) = 0
        group by rel.Z_33ALBUMS
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query).fetchall()
    return {int(row[0]): int(row[1]) for row in rows}


def descendant_visual_counts(albums: list[Any], direct_counts: dict[int, int]) -> dict[int, int]:
    children_by_parent = album_children(albums)
    totals: dict[int, int] = {}
    for album in albums:
        pks = album_descendants(album.pk, children_by_parent)
        totals[album.pk] = sum(direct_counts.get(pk, 0) for pk in pks)
    return totals


def print_album_listing(
    db_path: Path,
    selectors: list[str],
    match_mode: str,
) -> None:
    albums = load_albums(db_path)
    albums_by_pk = {album.pk: album for album in albums}
    paths = {album.pk: album_display_path(album, albums_by_pk) for album in albums}
    direct_counts = album_visual_counts(db_path)
    totals = descendant_visual_counts(albums, direct_counts)
    selected_pks = None
    if selectors:
        selected_pks, _ = match_albums(albums, selectors, match_mode)

    print("visuals\tdirect\titems\tkind\tpath")
    for album in sorted(albums, key=lambda value: paths[value.pk].casefold()):
        if selected_pks is not None and album.pk not in selected_pks:
            continue
        total = totals.get(album.pk, 0)
        direct = direct_counts.get(album.pk, 0)
        if selected_pks is None and total == 0 and direct == 0:
            continue
        kind = "folder" if album.kind == 4000 else "album"
        print(f"{total}\t{direct}\t{album.cached_count}\t{kind}\t{paths[album.pk]}")


def image_file_index(library: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for root, _, files in os.walk(library):
        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            match = UUID_RE.match(path.stem)
            if match is None:
                continue
            index.setdefault(match.group(0).upper(), []).append(path)
    return index


def best_image_path(asset: Asset, indexed_files: dict[str, list[Path]]) -> Path | None:
    matches = indexed_files.get(asset.uuid.upper(), [])
    existing = [path for path in matches if path.exists() and path.is_file()]
    if not existing:
        return None
    return sorted(existing, key=source_rank)[0]


def staged_clip_name(index: int, asset: Asset) -> str:
    created = apple_time(asset.created) or "undated"
    base = safe_name(asset.original_filename or asset.filename or "still")
    stem = Path(base).stem[:64]
    return f"{index:03d}_{created}_{asset.uuid[:8]}_{stem}.mp4"


def staged_model_name(index: int, asset: Asset, source_path: Path | None) -> str:
    created = apple_time(asset.created) or "undated"
    base = safe_name(asset.original_filename or asset.filename or "model")
    stem = Path(base).stem[:64]
    suffix = source_path.suffix.lower() if source_path is not None else Path(base).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"
    return f"{index:03d}_{created}_{asset.uuid[:8]}_{stem}{suffix}"


def stage_visual_items(
    assets: list[Asset],
    indexed_files: dict[str, list[Path]],
    output_dir: Path,
    durations: list[float],
    limit: int | None,
    photos_export_missing: bool,
) -> tuple[list[VisualItem], int]:
    items: list[VisualItem] = []
    missing_local = 0
    for asset in assets:
        source_path = best_image_path(asset, indexed_files)
        if source_path is None:
            missing_local += 1
            if not photos_export_missing:
                continue
        duration = durations[len(items) % len(durations)]
        destination = output_dir / staged_clip_name(len(items) + 1, asset)
        items.append(
            VisualItem(
                asset=asset,
                source_path=source_path,
                destination_path=destination,
                photos_export=source_path is None,
                duration=duration,
            )
        )
        if limit is not None and len(items) >= limit:
            break
    return items, missing_local


def stage_model_items(
    db_path: Path,
    indexed_files: dict[str, list[Path]],
    selectors: list[str],
    match_mode: str,
    output_dir: Path,
    limit: int,
    photos_export_missing: bool,
) -> tuple[list[ModelItem], list[dict[str, Any]]]:
    if not selectors or limit == 0:
        return [], []
    assets = load_visual_assets(db_path, "oldest")
    assets, match_records = filter_assets_by_album(db_path, assets, selectors, match_mode)
    items: list[ModelItem] = []
    for asset in assets:
        source_path = best_image_path(asset, indexed_files)
        if source_path is None and not photos_export_missing:
            continue
        destination = output_dir / staged_model_name(len(items) + 1, asset, source_path)
        items.append(
            ModelItem(
                asset=asset,
                source_path=source_path,
                destination_path=destination,
                photos_export=source_path is None,
            )
        )
        if len(items) >= limit:
            break
    return items, match_records


def motion_for_index(mode: str, index: int) -> str:
    if mode != "alternate":
        return mode
    pattern = ("zoom-in", "pan-left", "zoom-out", "pan-right")
    return pattern[(index - 1) % len(pattern)]


def motion_filter(mode: str, width: int, height: int, fps: int, frames: int) -> str:
    work_width = width * 2
    work_height = height * 2
    base = (
        f"scale={work_width}:{work_height}:force_original_aspect_ratio=increase,"
        f"crop={work_width}:{work_height},setsar=1"
    )
    if mode == "hold":
        return f"{base},scale={width}:{height},fps={fps},format=yuv420p"

    if mode == "zoom-out":
        zoom = "max(1.08-0.0015*on,1)"
        x = "iw/2-(iw/zoom/2)"
    elif mode == "pan-left":
        zoom = "1.05"
        x = f"(iw-iw/zoom)*on/{max(frames - 1, 1)}"
    elif mode == "pan-right":
        zoom = "1.05"
        x = f"(iw-iw/zoom)*(1-on/{max(frames - 1, 1)})"
    else:
        zoom = "min(1+0.0015*on,1.08)"
        x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    return (
        f"{base},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        "format=yuv420p"
    )


def run_command(command: list[str], dry_run: bool) -> None:
    print(" ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def convert_with_sips(source_path: Path, converted_path: Path, dry_run: bool) -> bool:
    if shutil.which("sips") is None:
        return False
    command = ["sips", "-s", "format", "jpeg", str(source_path), "--out", str(converted_path)]
    print(" ".join(command), flush=True)
    if dry_run:
        return True
    completed = subprocess.run(command)
    return completed.returncode == 0 and converted_path.exists()


def render_motion_clip(
    source_path: Path,
    destination_path: Path,
    duration: float,
    mode: str,
    args: argparse.Namespace,
    dry_run: bool,
) -> None:
    frames = max(1, round(duration * args.fps))
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-loop",
        "1",
        "-i",
        str(source_path),
        "-frames:v",
        str(frames),
        "-vf",
        motion_filter(mode, args.width, args.height, args.fps, frames),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        args.preset,
        "-crf",
        str(args.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(args.fps),
        "-movflags",
        "+faststart",
        str(destination_path),
    ]
    print(" ".join(command), flush=True)
    if dry_run:
        return

    completed = subprocess.run(command)
    if completed.returncode == 0:
        return

    converted_path = destination_path.with_suffix(".source.jpg")
    if not convert_with_sips(source_path, converted_path, dry_run=False):
        raise subprocess.CalledProcessError(completed.returncode, command)
    retry = list(command)
    retry[retry.index(str(source_path))] = str(converted_path)
    print(" ".join(retry), flush=True)
    subprocess.run(retry, check=True)
    converted_path.unlink(missing_ok=True)


def source_for_item(
    asset: Asset,
    source_path: Path | None,
    photos_export: bool,
    photos_export_work_dir: Path,
) -> Path:
    if not photos_export:
        if source_path is None:
            raise SystemExit(f"Missing local image source for {asset.uuid}.")
        return source_path
    export_dir = photos_export_work_dir / asset.uuid
    exported_path = export_original_from_photos(asset, export_dir)
    if exported_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise SystemExit(f"Photos.app exported a non-image model/source for {asset.uuid}: {exported_path}")
    return exported_path


def generate_motion_clips(
    items: list[VisualItem],
    args: argparse.Namespace,
    photos_export_work_dir: Path,
) -> None:
    for index, item in enumerate(items, start=1):
        mode = motion_for_index(args.motion, index)
        if item.photos_export:
            print(f"photos-export+motion {item.asset.uuid} -> {item.destination_path}")
        else:
            print(f"motion {mode} {item.source_path} -> {item.destination_path}")
        if args.dry_run:
            continue
        source_path = source_for_item(
            item.asset,
            item.source_path,
            item.photos_export,
            photos_export_work_dir,
        )
        if item.destination_path.exists() or item.destination_path.is_symlink():
            item.destination_path.unlink()
        render_motion_clip(
            source_path=source_path,
            destination_path=item.destination_path,
            duration=item.duration,
            mode=mode,
            args=args,
            dry_run=False,
        )


def stage_models(
    items: list[ModelItem],
    output_dir: Path,
    photos_export_work_dir: Path,
    dry_run: bool,
) -> None:
    if not items:
        return
    print(f"stage arrangement model stills {output_dir}")
    if dry_run:
        return
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        source_path = source_for_item(
            item.asset,
            item.source_path,
            item.photos_export,
            photos_export_work_dir,
        )
        if item.destination_path.exists() or item.destination_path.is_symlink():
            item.destination_path.unlink()
        shutil.copy2(source_path, item.destination_path)


def model_records(items: list[ModelItem], local_base: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": relative_to_base(item.destination_path, local_base),
            "source": "photos_visual_model",
            "source_uuid": item.asset.uuid,
            "source_created": apple_time(item.asset.created),
            "width": item.asset.width,
            "height": item.asset.height,
            "original_filename": item.asset.original_filename or item.asset.filename,
        }
        for item in items
    ]


def write_local_project(
    base_project_path: Path,
    local_project_path: Path,
    output_dir: Path,
    items: list[VisualItem],
    model_items: list[ModelItem],
    library: Path,
    photos_export_missing: bool,
    selection: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    project = load_project(base_project_path)
    local_base = local_project_path.parent
    normalize_export_paths(project, local_base)
    project["input_dir"] = relative_to_base(output_dir, local_base)
    project["clips"] = [
        {
            "path": relative_to_base(item.destination_path, local_base),
            "enabled": True,
            "source": "photos_visual_motion",
            "source_uuid": item.asset.uuid,
            "source_created": apple_time(item.asset.created),
            "duration": item.duration,
            "width": args.width,
            "height": args.height,
            "original_filename": item.asset.original_filename or item.asset.filename,
            "motion": motion_for_index(args.motion, index),
        }
        for index, item in enumerate(items, start=1)
    ]
    visual_import = {
        "library": str(library.expanduser()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staged_count": len(items),
        "photos_export_missing": photos_export_missing,
        "selection": selection,
        "motion": {
            "mode": args.motion,
            "duration_seconds": args.duration_seconds,
            "duration_pattern": duration_pattern(args.duration_pattern, args.duration_seconds),
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
            "crf": args.crf,
            "preset": args.preset,
        },
        "arrangement_model_assets": model_records(model_items, local_base),
        "note": "Local opt-in Photos still import generated lossy motion clips without mutating Photos.",
    }
    project["visual_import"] = visual_import
    if model_items:
        composition = dict(project.get("composition", {}))
        composition["arrangement_model_assets"] = visual_import["arrangement_model_assets"]
        project["composition"] = composition

    prompts = list(project.get("prompts", []))
    prompts.append(
        {
            "date": datetime.now().date().isoformat(),
            "text": "Authorized opt-in Photos still-album ingestion as lightweight generated motion clips.",
        }
    )
    project["prompts"] = prompts

    landing = dict(project.get("landing_page", {}))
    landing["output_file"] = relative_to_base(SCRIPT_DIR / "site" / "index.html", local_base)
    project["landing_page"] = landing

    print(f"write local project {local_project_path}")
    if args.dry_run:
        return
    local_project_path.parent.mkdir(parents=True, exist_ok=True)
    local_project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")


def run_render(project_path: Path, only: str | None) -> None:
    command = [sys.executable, str(SCRIPT_DIR / "export_project.py"), str(project_path)]
    if only:
        command.extend(["--only", only])
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    validate_args(args)
    library = args.library.expanduser().resolve()
    output_dir = args.output_dir.expanduser()
    project_path = args.project.expanduser()
    source_project = args.source_project.expanduser()
    model_output_dir = args.model_output_dir.expanduser()
    photos_export_work_dir = args.photos_export_work_dir.expanduser()
    exclude_file = args.exclude_file.expanduser()
    limit = None if args.all_local else args.limit

    require_inside(output_dir, SCRIPT_DIR, "output-dir")
    require_inside(project_path, SCRIPT_DIR, "project")
    require_inside(model_output_dir, SCRIPT_DIR, "model-output-dir")
    require_inside(photos_export_work_dir, SCRIPT_DIR, "photos-export-work-dir")
    require_inside(exclude_file, SCRIPT_DIR, "exclude-file")
    db_path = photos_db_path(library)

    if args.list_albums:
        print(f"read Photos visual albums {db_path}")
        print_album_listing(db_path, args.album, args.album_match)
        return 0

    print(f"read Photos visual catalog {db_path}")
    assets = load_visual_assets(db_path, args.order)
    print(f"visual catalog matches after filters: {len(assets)}")
    assets, album_matches = filter_assets_by_album(db_path, assets, args.album, args.album_match)
    if args.album:
        print(f"visual catalog matches after album selection: {len(assets)}")
        for record in album_matches:
            print(
                "album match "
                f"{record['selector']!r} -> {record['matched_path']} "
                f"(descendants: {record['descendant_album_count']})"
            )
    assets = date_filtered_assets(assets, args.start_date, args.end_date)
    excluded_uuids = load_excluded_uuids(exclude_file, args.exclude_uuid)
    assets = exclude_assets(assets, excluded_uuids)
    assets = select_assets(assets, args.offset, args.random_seed)
    print(f"visual catalog matches after selection: {len(assets)}")
    if excluded_uuids:
        print(f"excluded source UUIDs: {len(excluded_uuids)}")

    print(f"index local still files under {library}")
    indexed_files = image_file_index(library)
    durations = duration_pattern(args.duration_pattern, args.duration_seconds)
    items, missing_local = stage_visual_items(
        assets,
        indexed_files,
        output_dir,
        durations,
        limit,
        photos_export_missing=args.photos_export_missing,
    )
    model_items, model_matches = stage_model_items(
        db_path=db_path,
        indexed_files=indexed_files,
        selectors=args.model_album,
        match_mode=args.model_album_match,
        output_dir=model_output_dir,
        limit=args.model_limit,
        photos_export_missing=args.photos_export_missing,
    )
    print(f"selected visual clips: {len(items)}")
    print(f"selected visual clips requiring Photos.app export: {sum(1 for item in items if item.photos_export)}")
    print(f"visual catalog matches without local still files before limit: {missing_local}")
    print(f"selected arrangement model stills: {len(model_items)}")
    if not items:
        raise SystemExit(
            "No local Photos stills matched the filters. "
            "Open Photos and download originals, lower filters, or pass --photos-export-missing."
        )

    prepare_output_dir(output_dir, args.keep_existing, args.dry_run)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    generate_motion_clips(items, args, photos_export_work_dir)
    stage_models(model_items, model_output_dir, photos_export_work_dir, args.dry_run)
    write_local_project(
        base_project_path=source_project,
        local_project_path=project_path,
        output_dir=output_dir,
        items=items,
        model_items=model_items,
        library=library,
        photos_export_missing=args.photos_export_missing,
        selection={
            "order": args.order,
            "limit": limit,
            "offset": args.offset,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "random_seed": args.random_seed,
            "album": args.album,
            "album_match": args.album_match,
            "album_matches": album_matches,
            "model_album": args.model_album,
            "model_album_match": args.model_album_match,
            "model_album_matches": model_matches,
            "exclude_file": str(exclude_file),
            "excluded_uuid_count": len(excluded_uuids),
        },
        args=args,
    )
    if args.render and not args.dry_run:
        run_render(project_path, args.only)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
