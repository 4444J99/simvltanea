#!/usr/bin/env python3
"""Build a lightweight metadata catalog for local Photos videos."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from import_photos import (
    DEFAULT_LIBRARY,
    SCRIPT_DIR,
    Asset,
    apple_time,
    best_source_path,
    load_assets,
    photos_db_path,
    require_inside,
    video_file_index,
)


DEFAULT_CATALOG = SCRIPT_DIR / "work" / "photos-catalog.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a metadata-only catalog of Photos videos. This does not copy, "
            "symlink, export, render, or mutate the Photos library."
        )
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY,
        help="Path to a .photoslibrary package. Defaults to ~/Pictures/Photos Library.photoslibrary.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Catalog JSON path. Defaults to work/photos-catalog.json.",
    )
    parser.add_argument(
        "--include-live-photos",
        action="store_true",
        help="Also include Live Photo motion clips.",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.1,
        help="Minimum video duration in seconds. Defaults to 0.1.",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=0.0,
        help="Maximum video duration in seconds. Use 0 for no cap. Defaults to 0.",
    )
    parser.add_argument(
        "--order",
        choices=("recent", "oldest", "filename"),
        default="oldest",
        help="Catalog order. Defaults to oldest.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit catalog rows for testing. Defaults to 0, meaning no limit.",
    )
    parser.add_argument(
        "--check-local",
        action="store_true",
        help="Walk the Photos package and mark whether each asset has a local source file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing JSON.")
    return parser.parse_args()


def orientation(asset: Asset) -> str:
    if asset.width <= 0 or asset.height <= 0:
        return "unknown"
    if asset.width > asset.height:
        return "landscape"
    if asset.height > asset.width:
        return "portrait"
    return "square"


def duration_bucket(seconds: float) -> str:
    if seconds < 3:
        return "under_3s"
    if seconds < 10:
        return "3_to_10s"
    if seconds < 30:
        return "10_to_30s"
    if seconds < 60:
        return "30_to_60s"
    return "over_60s"


def asset_record(asset: Asset, local_path: Path | None, checked_local: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "uuid": asset.uuid,
        "created": apple_time(asset.created),
        "added": apple_time(asset.added),
        "duration": asset.duration,
        "width": asset.width,
        "height": asset.height,
        "orientation": orientation(asset),
        "filename": asset.filename,
        "original_filename": asset.original_filename,
        "playback_style": asset.playback_style,
    }
    if checked_local:
        record["local_available"] = local_path is not None
        if local_path is not None:
            record["local_path"] = str(local_path)
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_year: Counter[str] = Counter()
    by_orientation: Counter[str] = Counter()
    by_duration: Counter[str] = Counter()
    earliest = None
    latest = None
    total_duration = 0.0
    local_available = 0

    for record in records:
        created = record.get("created") or "undated"
        year = created[:4] if created != "undated" else created
        by_year[year] += 1
        by_orientation[str(record.get("orientation", "unknown"))] += 1
        duration = float(record.get("duration") or 0)
        by_duration[duration_bucket(duration)] += 1
        total_duration += duration
        if record.get("local_available"):
            local_available += 1
        if created != "undated":
            earliest = created if earliest is None else min(earliest, created)
            latest = created if latest is None else max(latest, created)

    return {
        "total_assets": len(records),
        "total_duration_seconds": round(total_duration, 3),
        "earliest_created": earliest,
        "latest_created": latest,
        "local_available": local_available if any("local_available" in record for record in records) else None,
        "by_year": dict(sorted(by_year.items())),
        "by_orientation": dict(sorted(by_orientation.items())),
        "by_duration": dict(sorted(by_duration.items())),
    }


def build_catalog(args: argparse.Namespace) -> dict[str, Any]:
    library = args.library.expanduser().resolve()
    db_path = photos_db_path(library)
    print(f"read Photos catalog {db_path}")
    assets = load_assets(
        db_path=db_path,
        include_live_photos=args.include_live_photos,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        order=args.order,
    )
    if args.limit < 0:
        raise SystemExit("--limit must be greater than or equal to 0.")
    if args.limit:
        assets = assets[: args.limit]

    indexed_files = None
    if args.check_local:
        print(f"index local video files under {library}")
        indexed_files = video_file_index(library)

    records = []
    for asset in assets:
        local_path = best_source_path(asset, indexed_files) if indexed_files is not None else None
        records.append(asset_record(asset, local_path, checked_local=indexed_files is not None))

    summary = summarize(records)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library": str(library),
        "filters": {
            "include_live_photos": args.include_live_photos,
            "min_duration": args.min_duration,
            "max_duration": args.max_duration,
            "order": args.order,
            "limit": args.limit,
            "checked_local": args.check_local,
        },
        "summary": summary,
        "assets": records,
    }


def print_summary(catalog: dict[str, Any]) -> None:
    summary = catalog["summary"]
    print(f"assets: {summary['total_assets']}")
    print(f"duration seconds: {summary['total_duration_seconds']}")
    print(f"created range: {summary['earliest_created']}..{summary['latest_created']}")
    if summary["local_available"] is not None:
        print(f"local available: {summary['local_available']}")
    print(f"years: {len(summary['by_year'])}")


def main() -> int:
    args = parse_args()
    catalog_path = args.catalog.expanduser()
    require_inside(catalog_path, SCRIPT_DIR, "catalog")
    catalog = build_catalog(args)
    print_summary(catalog)
    print(f"write catalog {catalog_path}")
    if args.dry_run:
        return 0
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
