#!/usr/bin/env python3
"""Verify rendered Story/Reel exports for a named edition post pack."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = SCRIPT_DIR / "work" / "editions" / "ballerina" / "project.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a post_pack recorded in work/editions/<slug>/project.json "
            "against public site exports and actual ffprobe media metadata."
        )
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Edition project JSON. Defaults to work/editions/ballerina/project.json.",
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=SCRIPT_DIR / "site",
        help="Generated static site directory. Defaults to site/.",
    )
    parser.add_argument(
        "--max-export-mb",
        type=float,
        default=64.0,
        help="Fail if one post-pack export exceeds this size. Defaults to 64 MB.",
    )
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def require_inside(path: Path, label: str) -> None:
    if not path_inside(path, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: cannot read JSON: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: JSON root must be an object")
    return data


def resolve_path(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return base / path


def public_ref(base_dir: Path, ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def mb(size_bytes: int) -> float:
    return size_bytes / (1024 * 1024)


def ffprobe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SystemExit("Required tool not found on PATH: ffprobe") from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"{path}: ffprobe failed: {error.stderr.strip()}") from error
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise SystemExit(f"{path}: no video stream found")
    stream = streams[0]
    if not isinstance(stream, dict):
        raise SystemExit(f"{path}: invalid ffprobe stream")
    return stream


def export_maps(project: dict[str, Any], receipt: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    project_exports = {
        str(export.get("name")): export
        for export in project.get("exports", [])
        if isinstance(export, dict) and export.get("name")
    }
    receipt_exports = {
        str(export.get("name")): export
        for export in receipt.get("exports", [])
        if isinstance(export, dict) and export.get("name")
    }
    return project_exports, receipt_exports


def validate_export(
    name: str,
    project_export: dict[str, Any],
    receipt_export: dict[str, Any],
    project_base: Path,
    receipt_dir: Path,
    site_dir: Path,
    max_export_mb: float,
    errors: list[str],
) -> dict[str, Any] | None:
    if receipt_export.get("exists") is not True:
        errors.append(f"{name}: public receipt does not mark export as existing")
        return None
    if receipt_export.get("published") is not True:
        errors.append(f"{name}: public receipt does not mark export as published")
    src = receipt_export.get("src")
    if not isinstance(src, str) or not src:
        errors.append(f"{name}: public receipt is missing src")
        return None

    public_path = public_ref(receipt_dir, src)
    if not path_inside(public_path, site_dir):
        errors.append(f"{name}: public src escapes site directory: {src}")
        return None
    if not public_path.exists():
        errors.append(f"{name}: public src does not exist: {src}")
        return None

    output_file = resolve_path(project_export.get("output_file"), project_base)
    if path_inside(output_file, SCRIPT_DIR) and output_file.exists():
        try:
            if public_path.stat().st_size != output_file.stat().st_size:
                errors.append(f"{name}: public export size differs from render output")
        except OSError:
            pass

    stream = ffprobe(public_path)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    expected_width = int(project_export.get("width") or 0)
    expected_height = int(project_export.get("height") or 0)
    if expected_width and width != expected_width:
        errors.append(f"{name}: width {width} != configured {expected_width}")
    if expected_height and height != expected_height:
        errors.append(f"{name}: height {height} != configured {expected_height}")
    if width <= 0 or height <= 0:
        errors.append(f"{name}: invalid media dimensions {width}x{height}")
    elif abs((width / height) - (9 / 16)) > 0.02:
        errors.append(f"{name}: expected near 9:16 media, got {width}x{height}")

    duration = float(stream.get("duration") or 0)
    if duration <= 0:
        errors.append(f"{name}: duration must be positive")

    size_bytes = public_path.stat().st_size
    if mb(size_bytes) > max_export_mb:
        errors.append(f"{name}: size {mb(size_bytes):.1f} MB exceeds {max_export_mb:.1f} MB")

    return {
        "name": name,
        "layout": receipt_export.get("layout"),
        "width": width,
        "height": height,
        "duration": round(duration, 2),
        "size_mb": round(mb(size_bytes), 2),
        "src": src,
    }


def main() -> int:
    args = parse_args()
    project_path = args.project.expanduser()
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path
    project_path = project_path.resolve()
    site_dir = args.site_dir.expanduser()
    if not site_dir.is_absolute():
        site_dir = SCRIPT_DIR / site_dir
    site_dir = site_dir.resolve()
    require_inside(project_path, "project")
    require_inside(site_dir, "site-dir")

    project = load_json(project_path)
    post_pack = project.get("post_pack")
    if not isinstance(post_pack, dict):
        raise SystemExit(f"{project_path}: missing post_pack metadata")
    export_names = post_pack.get("exports")
    if not isinstance(export_names, list) or not export_names:
        raise SystemExit(f"{project_path}: post_pack.exports must be a non-empty list")

    edition_slug = project_path.parent.name
    receipt_path = site_dir / "editions" / edition_slug / "flash-copy.json"
    receipt = load_json(receipt_path)
    if receipt.get("public") is not True:
        raise SystemExit(f"{receipt_path}: expected public flash-copy receipt")

    project_exports, receipt_exports = export_maps(project, receipt)
    errors: list[str] = []
    verified: list[dict[str, Any]] = []
    for raw_name in export_names:
        name = str(raw_name)
        project_export = project_exports.get(name)
        receipt_export = receipt_exports.get(name)
        if project_export is None:
            errors.append(f"{name}: missing project export")
            continue
        if receipt_export is None:
            errors.append(f"{name}: missing public receipt export")
            continue
        result = validate_export(
            name=name,
            project_export=project_export,
            receipt_export=receipt_export,
            project_base=project_path.parent,
            receipt_dir=receipt_path.parent,
            site_dir=site_dir,
            max_export_mb=args.max_export_mb,
            errors=errors,
        )
        if result is not None:
            verified.append(result)

    if errors:
        print("post pack verification failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"post pack ok: {edition_slug} ({post_pack.get('profile', 'unknown')} / {post_pack.get('pack', 'unknown')})")
    for item in verified:
        print(
            f"- {item['name']}: {item['width']}x{item['height']}, "
            f"{item['duration']}s, {item['size_mb']} MB, {item['src']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
