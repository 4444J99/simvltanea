#!/usr/bin/env python3
"""Opt-in local Photos library importer for the triptych video canon incubator."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"
DEFAULT_PROJECT = SCRIPT_DIR / "project.example.json"
DEFAULT_LOCAL_PROJECT = SCRIPT_DIR / "work" / "project.photos-local.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "samples" / "photos-import"
DEFAULT_PHOTOS_EXPORT_WORK_DIR = SCRIPT_DIR / "work" / "photos-export"
DEFAULT_EXCLUDE_FILE = SCRIPT_DIR / "work" / "photos-exclude-uuids.txt"
VIDEO_EXTENSIONS = {".3gp", ".m4v", ".mov", ".mp4", ".mpeg", ".mpg"}
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)


@dataclass(frozen=True)
class Asset:
    pk: int
    uuid: str
    created: float | None
    added: float | None
    duration: float
    width: int
    height: int
    filename: str
    original_filename: str | None
    playback_style: int


@dataclass(frozen=True)
class Album:
    pk: int
    title: str
    parent_pk: int | None
    kind: int
    cached_count: int
    cached_videos_count: int


@dataclass(frozen=True)
class ImportItem:
    asset: Asset
    source_path: Path | None
    destination_path: Path
    photos_export: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import local video files from a macOS Photos library into samples/ "
            "and write a local project manifest."
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
        help="Generated local project manifest. Defaults to work/project.photos-local.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for staged Photos videos. Defaults to samples/photos-import/.",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "symlink"),
        default="symlink",
        help="Stage media by copying files or by creating symlinks. Defaults to symlink.",
    )
    parser.add_argument(
        "--album",
        action="append",
        default=[],
        help=(
            "Only import assets from a Photos album or folder title/path. "
            "Can be passed more than once. Folder matches include descendants."
        ),
    )
    parser.add_argument(
        "--album-match",
        choices=("exact", "contains"),
        default="exact",
        help="How --album should match Photos album titles or paths. Defaults to exact.",
    )
    parser.add_argument(
        "--list-albums",
        action="store_true",
        help="List Photos albums/folders with video counts, then exit without staging media.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum local assets to stage. Use --all-local to remove the limit.",
    )
    parser.add_argument(
        "--all-local",
        action="store_true",
        help="Stage every matching local Photos video. This can be large and slow.",
    )
    parser.add_argument(
        "--order",
        choices=("recent", "oldest", "filename"),
        default="oldest",
        help="Order staged clips before rendering. Defaults to oldest.",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.1,
        help="Minimum clip duration in seconds. Defaults to 0.1.",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=45.0,
        help="Maximum clip duration in seconds for the first local canon. Use 0 for no cap.",
    )
    parser.add_argument(
        "--start-date",
        help="Only select assets created on or after YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        help="Only select assets created before or on YYYY-MM-DD.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many assets after filtering and ordering. Useful for paging the library.",
    )
    parser.add_argument(
        "--random-seed",
        help="Shuffle filtered assets with a stable seed before applying --offset and --limit.",
    )
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
        help="Source UUID to exclude for this import. Can be passed more than once.",
    )
    parser.add_argument(
        "--include-live-photos",
        action="store_true",
        help="Also include Live Photo motion clips when their paired .mov files are local.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Run export_project.py after import.",
    )
    parser.add_argument(
        "--photos-export-missing",
        action="store_true",
        help=(
            "Use Photos.app to export selected originals when the catalog row has no "
            "local video file in the library package."
        ),
    )
    parser.add_argument(
        "--photos-export-work-dir",
        type=Path,
        default=DEFAULT_PHOTOS_EXPORT_WORK_DIR,
        help="Temporary directory for Photos.app exports. Defaults to work/photos-export/.",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated export names to render when --render is used.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print import actions only.")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing staged files instead of replacing the output directory.",
    )
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def require_inside(path: Path, parent: Path, label: str) -> None:
    if not path_inside(path, parent):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def photos_db_path(library: Path) -> Path:
    db_path = library.expanduser() / "database" / "Photos.sqlite"
    if not db_path.exists():
        raise SystemExit(
            f"Photos database not found: {db_path}\n"
            "Open Photos once, choose the correct --library path, or grant macOS file access."
        )
    return db_path


def apple_time(value: float | None) -> str | None:
    if value is None:
        return None
    return (APPLE_EPOCH + timedelta(seconds=float(value))).date().isoformat()


def parse_date_boundary(value: str | None, inclusive_end: bool = False) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise SystemExit(f"Invalid date {value!r}; use YYYY-MM-DD.") from error
    if inclusive_end:
        parsed = parsed + timedelta(days=1)
    return (parsed - APPLE_EPOCH).total_seconds()


def asset_created_value(asset: Asset) -> float | None:
    return asset.created if asset.created is not None else asset.added


def sort_key(asset: Asset, order: str) -> tuple[Any, ...]:
    if order == "filename":
        return (asset.original_filename or asset.filename, asset.uuid)
    value = asset_created_value(asset)
    if value is None:
        value = 0.0
    if order == "oldest":
        return (value, asset.uuid)
    return (-value, asset.uuid)


def date_filtered_assets(
    assets: list[Asset],
    start_date: str | None,
    end_date: str | None,
) -> list[Asset]:
    start = parse_date_boundary(start_date)
    end = parse_date_boundary(end_date, inclusive_end=True)
    if start is None and end is None:
        return assets

    filtered = []
    for asset in assets:
        value = asset_created_value(asset)
        if value is None:
            continue
        if start is not None and value < start:
            continue
        if end is not None and value >= end:
            continue
        filtered.append(asset)
    return filtered


def load_albums(db_path: Path) -> list[Album]:
    query = """
        select
            Z_PK,
            coalesce(ZTITLE, ''),
            ZPARENTFOLDER,
            coalesce(ZKIND, 0),
            coalesce(ZCACHEDCOUNT, 0),
            coalesce(ZCACHEDVIDEOSCOUNT, 0)
        from ZGENERICALBUM
        where coalesce(ZTRASHEDSTATE, 0) = 0
          and coalesce(ZCLOUDDELETESTATE, 0) = 0
        order by lower(coalesce(ZTITLE, '')), Z_PK
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query).fetchall()
    return [
        Album(
            pk=int(row[0]),
            title=str(row[1]),
            parent_pk=int(row[2]) if row[2] is not None else None,
            kind=int(row[3]),
            cached_count=int(row[4]),
            cached_videos_count=int(row[5]),
        )
        for row in rows
    ]


def album_display_path(album: Album, albums_by_pk: dict[int, Album]) -> str:
    titles = [album.title or f"untitled-{album.pk}"]
    seen = {album.pk}
    parent_pk = album.parent_pk
    while parent_pk is not None and parent_pk in albums_by_pk and parent_pk not in seen:
        parent = albums_by_pk[parent_pk]
        if parent.title:
            titles.append(parent.title)
        seen.add(parent.pk)
        parent_pk = parent.parent_pk
    return "/".join(reversed(titles))


def album_children(albums: list[Album]) -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for album in albums:
        if album.parent_pk is None:
            continue
        children.setdefault(album.parent_pk, []).append(album.pk)
    return children


def album_descendants(start_pk: int, children_by_parent: dict[int, list[int]]) -> set[int]:
    selected = {start_pk}
    stack = list(children_by_parent.get(start_pk, []))
    while stack:
        pk = stack.pop()
        if pk in selected:
            continue
        selected.add(pk)
        stack.extend(children_by_parent.get(pk, []))
    return selected


def match_albums(
    albums: list[Album],
    selectors: list[str],
    match_mode: str,
) -> tuple[set[int], list[dict[str, Any]]]:
    if not selectors:
        return set(), []

    albums_by_pk = {album.pk: album for album in albums}
    children_by_parent = album_children(albums)
    paths = {album.pk: album_display_path(album, albums_by_pk) for album in albums}
    matched_pks: set[int] = set()
    match_records: list[dict[str, Any]] = []

    for selector in selectors:
        needle = selector.strip()
        if not needle:
            continue
        folded = needle.casefold()
        matches = []
        for album in albums:
            title = album.title.casefold()
            path = paths[album.pk].casefold()
            if match_mode == "contains":
                matched = folded in title or folded in path
            else:
                matched = folded == title or folded == path
            if matched:
                matches.append(album)
        if not matches:
            available = sorted(paths.values(), key=str.casefold)[:12]
            raise SystemExit(
                f"No Photos album/folder matched {selector!r}. "
                "Run --list-albums to inspect names. First available paths: "
                + ", ".join(available)
            )
        for album in matches:
            pks = album_descendants(album.pk, children_by_parent)
            matched_pks.update(pks)
            match_records.append(
                {
                    "selector": selector,
                    "matched_title": album.title,
                    "matched_path": paths[album.pk],
                    "matched_pk": album.pk,
                    "descendant_album_count": len(pks) - 1,
                }
            )
    return matched_pks, match_records


def album_video_counts(
    db_path: Path,
    include_live_photos: bool,
    min_duration: float,
    max_duration: float,
) -> dict[int, int]:
    playback_styles = [4]
    if include_live_photos:
        playback_styles.append(3)
    placeholders = ",".join("?" for _ in playback_styles)
    query = f"""
        select rel.Z_33ALBUMS, count(distinct a.Z_PK)
        from Z_33ASSETS rel
        join ZASSET a on a.Z_PK = rel.Z_3ASSETS
        where a.ZPLAYBACKSTYLE in ({placeholders})
          and coalesce(a.ZTRASHEDSTATE, 0) = 0
          and coalesce(a.ZHIDDEN, 0) = 0
          and coalesce(a.ZVISIBILITYSTATE, 0) = 0
          and (
            a.ZPLAYBACKSTYLE = 3
            or (
              coalesce(a.ZDURATION, 0) >= ?
              and (? <= 0 or coalesce(a.ZDURATION, 0) <= ?)
            )
          )
        group by rel.Z_33ALBUMS
    """
    params = [*playback_styles, min_duration, max_duration, max_duration]
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query, params).fetchall()
    return {int(row[0]): int(row[1]) for row in rows}


def album_asset_pks(db_path: Path, album_pks: set[int]) -> set[int]:
    if not album_pks:
        return set()
    placeholders = ",".join("?" for _ in album_pks)
    query = f"""
        select distinct Z_3ASSETS
        from Z_33ASSETS
        where Z_33ALBUMS in ({placeholders})
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query, sorted(album_pks)).fetchall()
    return {int(row[0]) for row in rows}


def descendant_video_counts(albums: list[Album], direct_counts: dict[int, int]) -> dict[int, int]:
    children_by_parent = album_children(albums)
    totals: dict[int, int] = {}
    for album in albums:
        pks = album_descendants(album.pk, children_by_parent)
        totals[album.pk] = sum(direct_counts.get(pk, 0) for pk in pks)
    return totals


def print_album_listing(
    albums: list[Album],
    direct_counts: dict[int, int],
    selectors: list[str],
    match_mode: str,
) -> None:
    albums_by_pk = {album.pk: album for album in albums}
    paths = {album.pk: album_display_path(album, albums_by_pk) for album in albums}
    totals = descendant_video_counts(albums, direct_counts)
    selected_pks = None
    if selectors:
        selected_pks, _ = match_albums(albums, selectors, match_mode)

    print("videos\tdirect\titems\tkind\tpath")
    for album in sorted(albums, key=lambda value: paths[value.pk].casefold()):
        if selected_pks is not None and album.pk not in selected_pks:
            continue
        total = totals.get(album.pk, 0)
        direct = direct_counts.get(album.pk, 0)
        if selected_pks is None and total == 0 and direct == 0:
            continue
        kind = "folder" if album.kind == 4000 else "album"
        print(f"{total}\t{direct}\t{album.cached_count}\t{kind}\t{paths[album.pk]}")


def filter_assets_by_album(
    db_path: Path,
    assets: list[Asset],
    selectors: list[str],
    match_mode: str,
) -> tuple[list[Asset], list[dict[str, Any]]]:
    if not selectors:
        return assets, []
    albums = load_albums(db_path)
    album_pks, match_records = match_albums(albums, selectors, match_mode)
    asset_pks = album_asset_pks(db_path, album_pks)
    selected = [asset for asset in assets if asset.pk in asset_pks]
    return selected, match_records


def normalize_uuid(value: str) -> str:
    return value.strip().upper()


def load_excluded_uuids(exclude_file: Path, inline_uuids: list[str]) -> set[str]:
    excluded = {normalize_uuid(value) for value in inline_uuids if value.strip()}
    if exclude_file.exists():
        for line in exclude_file.read_text(encoding="utf-8").splitlines():
            value = line.split("#", 1)[0].strip()
            if value:
                excluded.add(normalize_uuid(value))
    return excluded


def exclude_assets(assets: list[Asset], excluded_uuids: set[str]) -> list[Asset]:
    if not excluded_uuids:
        return assets
    return [asset for asset in assets if normalize_uuid(asset.uuid) not in excluded_uuids]


def select_assets(
    assets: list[Asset],
    offset: int,
    random_seed: str | None,
) -> list[Asset]:
    if offset < 0:
        raise SystemExit("--offset must be greater than or equal to 0.")
    selected = list(assets)
    if random_seed is not None:
        random.Random(random_seed).shuffle(selected)
    if offset:
        selected = selected[offset:]
    return selected


def load_assets(
    db_path: Path,
    include_live_photos: bool,
    min_duration: float,
    max_duration: float,
    order: str,
) -> list[Asset]:
    playback_styles = [4]
    if include_live_photos:
        playback_styles.append(3)

    placeholders = ",".join("?" for _ in playback_styles)

    query = f"""
        select
            a.Z_PK,
            a.ZUUID,
            a.ZDATECREATED,
            a.ZADDEDDATE,
            coalesce(a.ZDURATION, 0),
            coalesce(a.ZWIDTH, 0),
            coalesce(a.ZHEIGHT, 0),
            coalesce(a.ZFILENAME, ''),
            aa.ZORIGINALFILENAME,
            a.ZPLAYBACKSTYLE
        from ZASSET a
        left join ZADDITIONALASSETATTRIBUTES aa on aa.ZASSET = a.Z_PK
        where a.ZPLAYBACKSTYLE in ({placeholders})
          and coalesce(a.ZTRASHEDSTATE, 0) = 0
          and coalesce(a.ZHIDDEN, 0) = 0
          and coalesce(a.ZVISIBILITYSTATE, 0) = 0
    """

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(query, playback_styles).fetchall()

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
    filtered = []
    for asset in assets:
        if asset.playback_style == 3:
            filtered.append(asset)
            continue
        if asset.duration < min_duration:
            continue
        if max_duration > 0 and asset.duration > max_duration:
            continue
        filtered.append(asset)
    return sorted(filtered, key=lambda asset: sort_key(asset, order))


def video_file_index(library: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for root, _, files in os.walk(library):
        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            match = UUID_RE.match(path.stem)
            if match is None:
                continue
            index.setdefault(match.group(0).upper(), []).append(path)
    return index


def source_rank(path: Path) -> tuple[int, int, int, str]:
    text = str(path)
    if "/originals/" in text or "/scopes/" in text and "/originals/" in text:
        class_rank = 0
    elif "/resources/renders/" in text:
        class_rank = 1
    else:
        class_rank = 2
    suffix_rank = 1 if "_" in path.stem else 0
    return (class_rank, suffix_rank, len(path.name), text)


def best_source_path(asset: Asset, indexed_files: dict[str, list[Path]]) -> Path | None:
    matches = indexed_files.get(asset.uuid.upper(), [])
    existing = [path for path in matches if path.exists() and path.is_file()]
    if not existing:
        return None
    return sorted(existing, key=source_rank)[0]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "clip"


def staged_name(index: int, asset: Asset, source_path: Path | None) -> str:
    created = apple_time(asset.created) or "undated"
    base = safe_name(asset.original_filename or asset.filename or (source_path.name if source_path else "clip"))
    stem = Path(base).stem[:64]
    suffix = source_path.suffix.lower() if source_path else Path(base).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        suffix = ".mov"
    return f"{index:03d}_{created}_{asset.uuid[:8]}_{stem}{suffix}"


def stage_items(
    assets: list[Asset],
    indexed_files: dict[str, list[Path]],
    output_dir: Path,
    limit: int | None,
    photos_export_missing: bool,
) -> tuple[list[ImportItem], int]:
    items: list[ImportItem] = []
    missing_local = 0
    for asset in assets:
        source_path = best_source_path(asset, indexed_files)
        if source_path is None:
            missing_local += 1
            if not photos_export_missing:
                continue
        destination = output_dir / staged_name(len(items) + 1, asset, source_path)
        items.append(
            ImportItem(
                asset=asset,
                source_path=source_path,
                destination_path=destination,
                photos_export=source_path is None,
            )
        )
        if limit is not None and len(items) >= limit:
            break
    return items, missing_local


def prepare_output_dir(output_dir: Path, keep_existing: bool, dry_run: bool) -> None:
    if dry_run:
        return
    if output_dir.exists() and not keep_existing:
        for child in output_dir.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)


def applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def export_original_from_photos(asset: Asset, export_dir: Path) -> Path:
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    photos_id = f"{asset.uuid}/L0/001"
    script_lines = [
        'tell application "Photos"',
        f'set targetItem to media item id "{applescript_string(photos_id)}"',
        (
            f'export {{targetItem}} to '
            f'(POSIX file "{applescript_string(str(export_dir))}") with using originals'
        ),
        "end tell",
    ]
    command: list[str] = ["osascript"]
    for line in script_lines:
        command.extend(["-e", line])
    subprocess.run(command, check=True)

    exported = sorted(path for path in export_dir.iterdir() if path.is_file())
    if not exported:
        raise SystemExit(f"Photos.app did not export an original for {asset.uuid}.")

    videos = [path for path in exported if path.suffix.lower() in VIDEO_EXTENSIONS]
    return videos[0] if videos else exported[0]


def stage_media(
    items: list[ImportItem],
    mode: str,
    dry_run: bool,
    photos_export_work_dir: Path,
) -> None:
    for item in items:
        if item.photos_export:
            print(f"photos-export {item.asset.uuid} -> {item.destination_path}")
        else:
            print(f"{mode} {item.source_path} -> {item.destination_path}")
        if dry_run:
            continue
        if item.destination_path.exists() or item.destination_path.is_symlink():
            item.destination_path.unlink()

        if item.photos_export:
            export_dir = photos_export_work_dir / item.asset.uuid
            exported_path = export_original_from_photos(item.asset, export_dir)
            shutil.move(str(exported_path), item.destination_path)
        elif mode == "copy":
            if item.source_path is None:
                raise SystemExit(f"Missing source path for {item.asset.uuid}.")
            shutil.copy2(item.source_path, item.destination_path)
        else:
            if item.source_path is None:
                raise SystemExit(f"Missing source path for {item.asset.uuid}.")
            os.symlink(item.source_path, item.destination_path)


def load_project(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Base project manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def relative_to_base(path: Path, base: Path) -> str:
    return os.path.relpath(path.absolute(), base.absolute())


def normalize_export_paths(project: dict[str, Any], local_base: Path) -> None:
    exports = project.get("exports")
    if not isinstance(exports, list):
        return
    for export in exports:
        if not isinstance(export, dict) or not export.get("output_file"):
            continue
        output_path = Path(str(export["output_file"]))
        target = output_path if output_path.is_absolute() else SCRIPT_DIR / output_path
        export["output_file"] = relative_to_base(target, local_base)


def write_local_project(
    base_project_path: Path,
    local_project_path: Path,
    output_dir: Path,
    items: list[ImportItem],
    mode: str,
    library: Path,
    photos_export_missing: bool,
    selection: dict[str, Any],
    dry_run: bool,
) -> None:
    project = load_project(base_project_path)
    local_base = local_project_path.parent
    normalize_export_paths(project, local_base)
    project["input_dir"] = relative_to_base(output_dir, local_base)
    project["clips"] = [
        {
            "path": relative_to_base(item.destination_path, local_base),
            "enabled": True,
            "source": "photos",
            "source_uuid": item.asset.uuid,
            "source_created": apple_time(item.asset.created),
            "duration": item.asset.duration,
            "width": item.asset.width,
            "height": item.asset.height,
            "original_filename": item.asset.original_filename or item.asset.filename,
        }
        for item in items
    ]
    project["photos_import"] = {
        "library": str(library.expanduser()),
        "mode": mode,
        "photos_export_missing": photos_export_missing,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staged_count": len(items),
        "selection": selection,
        "note": "Local opt-in Photos import generated by import_photos.py.",
    }
    prompts = list(project.get("prompts", []))
    prompts.append(
        {
            "date": datetime.now().date().isoformat(),
            "text": "Authorized opt-in Photos library ingestion for a living local canon surface.",
        }
    )
    project["prompts"] = prompts

    landing = dict(project.get("landing_page", {}))
    landing["output_file"] = relative_to_base(SCRIPT_DIR / "site" / "index.html", local_base)
    project["landing_page"] = landing

    print(f"write local project {local_project_path}")
    if dry_run:
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
    library = args.library.expanduser().resolve()
    output_dir = args.output_dir.expanduser()
    project_path = args.project.expanduser()
    source_project = args.source_project.expanduser()
    photos_export_work_dir = args.photos_export_work_dir.expanduser()
    exclude_file = args.exclude_file.expanduser()
    limit = None if args.all_local else args.limit

    require_inside(output_dir, SCRIPT_DIR, "output-dir")
    require_inside(project_path, SCRIPT_DIR, "project")
    require_inside(photos_export_work_dir, SCRIPT_DIR, "photos-export-work-dir")
    require_inside(exclude_file, SCRIPT_DIR, "exclude-file")
    db_path = photos_db_path(library)

    if args.list_albums:
        print(f"read Photos albums {db_path}")
        albums = load_albums(db_path)
        direct_counts = album_video_counts(
            db_path=db_path,
            include_live_photos=args.include_live_photos,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
        )
        print_album_listing(albums, direct_counts, args.album, args.album_match)
        return 0

    print(f"read Photos catalog {db_path}")
    assets = load_assets(
        db_path=db_path,
        include_live_photos=args.include_live_photos,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        order=args.order,
    )
    print(f"catalog matches after filters: {len(assets)}")
    assets, album_matches = filter_assets_by_album(db_path, assets, args.album, args.album_match)
    if args.album:
        print(f"catalog matches after album selection: {len(assets)}")
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
    print(f"catalog matches after selection: {len(assets)}")
    if excluded_uuids:
        print(f"excluded source UUIDs: {len(excluded_uuids)}")
    print(f"index local video files under {library}")
    indexed_files = video_file_index(library)
    items, missing_local = stage_items(
        assets,
        indexed_files,
        output_dir,
        limit,
        photos_export_missing=args.photos_export_missing,
    )
    print(f"selected clips: {len(items)}")
    print(f"selected clips requiring Photos.app export: {sum(1 for item in items if item.photos_export)}")
    print(f"catalog matches without local video files before limit: {missing_local}")
    if not items:
        raise SystemExit(
            "No local Photos videos matched the filters. "
            "Open Photos and download originals, lower filters, use --include-live-photos, "
            "or pass --photos-export-missing."
        )

    prepare_output_dir(output_dir, args.keep_existing, args.dry_run)
    stage_media(items, args.mode, args.dry_run, photos_export_work_dir)
    write_local_project(
        base_project_path=source_project,
        local_project_path=project_path,
        output_dir=output_dir,
        items=items,
        mode=args.mode,
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
            "exclude_file": str(exclude_file),
            "excluded_uuid_count": len(excluded_uuids),
            "min_duration": args.min_duration,
            "max_duration": args.max_duration,
            "include_live_photos": args.include_live_photos,
        },
        dry_run=args.dry_run,
    )
    if args.render and not args.dry_run:
        run_render(project_path, args.only)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
