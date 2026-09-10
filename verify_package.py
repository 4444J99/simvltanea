#!/usr/bin/env python3
"""Verify a generated triptych public-site package manifest and media gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PACKAGE_DIR = SCRIPT_DIR / "packages" / "triptych-video-canon-site"
MANIFEST_NAME = "package-manifest.json"
SCHEMA = "triptych.public-site-package.v1"
FORBIDDEN_PACKAGE_PARTS = {"work", "samples", "renders", "packages", "__pycache__"}
PUBLIC_PACKAGE_READY = "public-package-ready"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute a generated package's file hashes and optionally rerun "
            "verify_public_site.py against the package tree."
        )
    )
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=DEFAULT_PACKAGE_DIR,
        help="Generated package directory. Defaults to packages/triptych-video-canon-site/.",
    )
    parser.add_argument(
        "--no-public-site-verify",
        action="store_true",
        help="Only verify the package manifest and checksums.",
    )
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolved_path(path: Path, base: Path = SCRIPT_DIR) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (base / expanded).resolve()


def require_inside(path: Path, label: str) -> None:
    if not path_inside(path, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == MANIFEST_NAME:
            continue
        relative = path.relative_to(root).as_posix()
        records.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def tree_size(records: list[dict[str, Any]]) -> int:
    return sum(int(record["size_bytes"]) for record in records)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: cannot read package manifest: {error}") from error
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: manifest root must be an object")
    if payload.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: unexpected schema {payload.get('schema')!r}")
    return payload


def manifest_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_records = payload.get("files")
    if not isinstance(raw_records, list):
        raise SystemExit("package manifest files must be a list")
    records: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            raise SystemExit(f"package manifest files[{index}] must be an object")
        raw_path = record.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise SystemExit(f"package manifest files[{index}] missing path")
        rel = Path(raw_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"package manifest path must stay relative: {raw_path}")
        if raw_path in records:
            raise SystemExit(f"package manifest duplicates path: {raw_path}")
        size = record.get("size_bytes")
        checksum = record.get("sha256")
        if not isinstance(size, int) or size < 0:
            raise SystemExit(f"package manifest has invalid size for {raw_path}")
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise SystemExit(f"package manifest has invalid sha256 for {raw_path}")
        records[raw_path] = record
    return records


def verify_records(payload: dict[str, Any], package_dir: Path) -> list[dict[str, Any]]:
    actual_records = file_records(package_dir)
    actual_by_path = {record["path"]: record for record in actual_records}
    expected_by_path = manifest_records(payload)
    errors: list[str] = []

    if len(actual_records) != payload.get("file_count"):
        errors.append(
            f"file_count mismatch: manifest {payload.get('file_count')!r}, actual {len(actual_records)}"
        )
    actual_size = tree_size(actual_records)
    if actual_size != payload.get("size_bytes"):
        errors.append(f"size_bytes mismatch: manifest {payload.get('size_bytes')!r}, actual {actual_size}")

    missing = sorted(set(expected_by_path) - set(actual_by_path))
    extra = sorted(set(actual_by_path) - set(expected_by_path))
    for path in missing:
        errors.append(f"missing file: {path}")
    for path in extra:
        errors.append(f"extra file not in manifest: {path}")

    for path in sorted(set(expected_by_path) & set(actual_by_path)):
        expected = expected_by_path[path]
        actual = actual_by_path[path]
        if actual["size_bytes"] != expected["size_bytes"]:
            errors.append(
                f"size mismatch {path}: manifest {expected['size_bytes']}, actual {actual['size_bytes']}"
            )
        if actual["sha256"] != expected["sha256"]:
            errors.append(f"sha256 mismatch {path}")

    if errors:
        raise SystemExit("package verification failed:\n- " + "\n- ".join(errors))
    return actual_records


def verify_no_private_lanes(records: list[dict[str, Any]]) -> None:
    offenders: list[str] = []
    for record in records:
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            continue
        parts = set(Path(raw_path).parts)
        if parts & FORBIDDEN_PACKAGE_PARTS:
            offenders.append(raw_path)
    if offenders:
        raise SystemExit(
            "package contains private/generated source lanes:\n- " + "\n- ".join(sorted(offenders))
        )


def verify_custody(payload: dict[str, Any]) -> None:
    custody = payload.get("custody")
    if not isinstance(custody, dict):
        raise SystemExit("package manifest missing custody")
    required = {
        "tier": "public_derivative",
        "promotion_state": PUBLIC_PACKAGE_READY,
        "public_export_gate": PUBLIC_PACKAGE_READY,
        "source_boundary": "copied from sanitized site/ only",
    }
    for key, expected in required.items():
        if custody.get(key) != expected:
            raise SystemExit(f"package manifest custody.{key} must be {expected!r}")
    forbidden_lanes = custody.get("forbidden_lanes")
    if not isinstance(forbidden_lanes, list) or not {"work/", "samples/", "renders/"}.issubset(
        set(forbidden_lanes)
    ):
        raise SystemExit("package manifest custody.forbidden_lanes must include work/, samples/, renders/")


def verify_edition_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("edition_summary")
    if not isinstance(summary, dict):
        raise SystemExit("package manifest missing edition_summary")
    editions = summary.get("editions")
    if not isinstance(editions, list):
        raise SystemExit("package manifest edition_summary.editions must be a list")
    required_totals = (
        "edition_count",
        "clips",
        "video_proxies",
        "audio_proxies",
        "published_post_exports",
        "visual_sketches",
    )
    for key in required_totals:
        value = summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise SystemExit(f"package manifest edition_summary.{key} must be a non-negative integer")
    if summary["edition_count"] != len(editions):
        raise SystemExit(
            f"package manifest edition_count mismatch: {summary['edition_count']} vs {len(editions)}"
        )

    slugs: set[str] = set()
    for index, edition in enumerate(editions):
        if not isinstance(edition, dict):
            raise SystemExit(f"package manifest edition_summary.editions[{index}] must be an object")
        slug = edition.get("slug")
        if not isinstance(slug, str) or not slug:
            raise SystemExit(f"package manifest edition_summary.editions[{index}] missing slug")
        if slug in slugs:
            raise SystemExit(f"package manifest edition_summary duplicates edition slug: {slug}")
        slugs.add(slug)
        for key in ("title", "work_title", "family"):
            if not isinstance(edition.get(key), str) or not edition.get(key):
                raise SystemExit(f"package manifest edition_summary.{slug}.{key} must be present")
        if edition.get("custody_tier") != "public_derivative":
            raise SystemExit(f"package manifest edition_summary.{slug}.custody_tier must be public_derivative")
        if edition.get("promotion_state") != PUBLIC_PACKAGE_READY:
            raise SystemExit(
                f"package manifest edition_summary.{slug}.promotion_state must be {PUBLIC_PACKAGE_READY}"
            )
        if edition.get("public_export_gate") != PUBLIC_PACKAGE_READY:
            raise SystemExit(
                f"package manifest edition_summary.{slug}.public_export_gate must be {PUBLIC_PACKAGE_READY}"
            )
        for key in ("clips", "video_proxies", "audio_proxies", "published_post_exports", "visual_sketches"):
            value = edition.get(key)
            if not isinstance(value, int) or value < 0:
                raise SystemExit(f"package manifest edition_summary.{slug}.{key} must be a non-negative integer")
        if (edition.get("published_post_exports") or 0) + (edition.get("visual_sketches") or 0) <= 0:
            raise SystemExit(f"package manifest edition_summary.{slug} has no public exports")
        presets = edition.get("control_presets")
        if not isinstance(presets, list) or not all(isinstance(item, str) and item for item in presets):
            raise SystemExit(f"package manifest edition_summary.{slug}.control_presets must be a string list")
        score = edition.get("arrangement_score")
        if not isinstance(score, dict):
            raise SystemExit(f"package manifest edition_summary.{slug}.arrangement_score must be an object")
    return summary


def summarize_edition_manifest(payload: dict[str, Any]) -> str:
    summary = payload.get("edition_summary")
    if not isinstance(summary, dict):
        return "edition summary: missing"
    editions = summary.get("edition_count")
    posts = summary.get("published_post_exports")
    sketches = summary.get("visual_sketches")
    clips = summary.get("clips")
    return f"edition summary: {editions} editions; {clips} clips; {posts} posts; {sketches} sketches"


def run_public_site_verify(package_dir: Path) -> None:
    command = [sys.executable, str(SCRIPT_DIR / "verify_public_site.py"), "--site-dir", str(package_dir)]
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    package_dir = resolved_path(args.package_dir)
    require_inside(package_dir, "package-dir")
    if not package_dir.exists():
        raise SystemExit(f"package directory does not exist: {package_dir}")
    manifest_path = package_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise SystemExit(f"package manifest does not exist: {manifest_path}")

    payload = load_manifest(manifest_path)
    records = verify_records(payload, package_dir)
    verify_no_private_lanes(records)
    verify_custody(payload)
    verify_edition_summary(payload)
    if not args.no_public_site_verify:
        run_public_site_verify(package_dir)

    size_mb = tree_size(records) / (1024 * 1024)
    print(f"package ok: {package_dir.relative_to(SCRIPT_DIR)} ({len(records)} files, {size_mb:.1f} MB)")
    print(summarize_edition_manifest(payload))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
