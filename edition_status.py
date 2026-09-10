#!/usr/bin/env python3
"""Summarize local/public status for configured triptych editions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EDITIONS = SCRIPT_DIR / "editions.example.json"
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_PACKAGE_DIR = SCRIPT_DIR / "packages" / "triptych-video-canon-site"
PUBLIC_MANIFEST_SCHEMA = "triptych.public-release-manifest.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read edition presets plus local/public receipts and print a compact "
            "status table without exposing private source media paths."
        )
    )
    parser.add_argument("--editions", type=Path, default=DEFAULT_EDITIONS, help="Edition preset JSON.")
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Public site directory.")
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=DEFAULT_PACKAGE_DIR,
        help="Generated package directory to inspect if present.",
    )
    parser.add_argument("--edition", help="Limit the report to one edition slug/name.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolve_inside(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    resolved = expanded.resolve() if expanded.is_absolute() else (SCRIPT_DIR / expanded).resolve()
    if not path_inside(resolved, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")
    return resolved


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-").lower()
    return cleaned or "edition"


def edition_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    editions = payload.get("editions")
    if not isinstance(editions, list):
        raise SystemExit("editions file must contain an editions array.")
    return [edition for edition in editions if isinstance(edition, dict)]


def edition_slug(edition: dict[str, Any]) -> str:
    return safe_slug(str(edition.get("slug") or edition.get("name") or "edition"))


def matches_edition(edition: dict[str, Any], requested: str | None) -> bool:
    if requested is None:
        return True
    requested_slug = safe_slug(requested)
    names = {edition_slug(edition), safe_slug(str(edition.get("name", "")))}
    aliases = edition.get("aliases", [])
    if isinstance(aliases, list):
        names.update(safe_slug(str(alias)) for alias in aliases)
    return requested_slug in names


def resolve_project_output(project_base: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path).expanduser()
    resolved = path if path.is_absolute() else (project_base / path).resolve()
    return resolved if path_inside(resolved, SCRIPT_DIR) else None


def visual_sketch_state(project: dict[str, Any] | None, project_base: Path) -> str:
    if project is None:
        return "none"
    raw_sketches = project.get("visual_sketch")
    if raw_sketches is None:
        return "none"
    sketches = raw_sketches if isinstance(raw_sketches, list) else [raw_sketches]
    existing = 0
    configured = 0
    for sketch in sketches:
        if not isinstance(sketch, dict):
            continue
        configured += 1
        output = resolve_project_output(project_base, sketch.get("output_file"))
        if output and output.exists():
            existing += 1
    if configured == 0:
        return "none"
    return f"{existing}/{configured}"


def public_exports_state(receipt: dict[str, Any] | None) -> str:
    if receipt is None:
        return "none"
    exports = receipt.get("exports")
    if not isinstance(exports, list) or not exports:
        return "0/0"
    existing = sum(1 for export in exports if isinstance(export, dict) and export.get("exists") is True)
    published = sum(1 for export in exports if isinstance(export, dict) and export.get("published") is True)
    return f"{existing}/{len(exports)} ({published} pub)"


def receipt_counts(receipt: dict[str, Any] | None) -> dict[str, int]:
    counts = receipt.get("counts", {}) if isinstance(receipt, dict) else {}
    if not isinstance(counts, dict):
        return {}
    return {str(key): int(value) for key, value in counts.items() if isinstance(value, int)}


def post_pack_state(receipt: dict[str, Any] | None, project: dict[str, Any] | None) -> str:
    post_pack = receipt.get("post_pack") if isinstance(receipt, dict) else None
    if not isinstance(post_pack, dict) and isinstance(project, dict):
        post_pack = project.get("post_pack")
    if not isinstance(post_pack, dict):
        return "none"
    profile = post_pack.get("profile", "?")
    pack = post_pack.get("pack", "?")
    exports = post_pack.get("exports", [])
    export_count = len(exports) if isinstance(exports, list) else 0
    return f"{profile}/{pack}/{export_count}"


def model_state(edition: dict[str, Any], project: dict[str, Any] | None) -> str:
    composition = edition.get("composition", {})
    model_album = ""
    if isinstance(composition, dict):
        model_album = str(composition.get("arrangement_model_album") or "")
    if not model_album:
        return "none"
    asset_count = 0
    if isinstance(project, dict):
        project_composition = project.get("composition", {})
        assets = project_composition.get("arrangement_model_assets", []) if isinstance(project_composition, dict) else []
        if isinstance(assets, list):
            asset_count = len(assets)
    return f"{model_album} ({asset_count})"


def control_preset_state(edition: dict[str, Any], receipt: dict[str, Any] | None) -> str:
    source_presets = edition.get("control_presets", [])
    source_count = len(source_presets) if isinstance(source_presets, list) else 0
    public_presets = receipt.get("control_presets", []) if isinstance(receipt, dict) else []
    public_count = len(public_presets) if isinstance(public_presets, list) else 0
    default_id = "none"
    for preset in source_presets if isinstance(source_presets, list) else []:
        if isinstance(preset, dict) and preset.get("default") is True:
            default_id = str(preset.get("id") or "default")
            break
    return f"{source_count}/{public_count} {default_id}"


def visual_map_state(edition: dict[str, Any]) -> str:
    raw_sketches = edition.get("visual_sketch")
    if raw_sketches is None:
        return "none"
    sketches = raw_sketches if isinstance(raw_sketches, list) else [raw_sketches]
    parts: list[str] = []
    for sketch in sketches:
        if not isinstance(sketch, dict):
            continue
        style = str(sketch.get("style", "slices"))
        cell_key = (
            "score_cells"
            if style == "score"
            else "fracture_cells"
            if style == "fracture"
            else "signal_cells"
            if style == "signal"
            else ""
        )
        cells = sketch.get(cell_key) if cell_key else None
        if isinstance(cells, list):
            parts.append(f"{style}/{len(cells)}")
        else:
            parts.append(style)
    return ",".join(parts) if parts else "none"


def public_manifest_summary(root: Path) -> dict[str, Any]:
    manifest = load_json(root / "public-manifest.json")
    if not isinstance(manifest, dict):
        return {
            "exists": False,
            "schema_ok": False,
            "edition_count": 0,
            "post_exports": 0,
            "visual_sketches": 0,
        }
    totals = manifest.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    return {
        "exists": True,
        "schema_ok": manifest.get("schema") == PUBLIC_MANIFEST_SCHEMA,
        "edition_count": int(manifest.get("edition_count") or 0)
        if isinstance(manifest.get("edition_count"), int)
        else 0,
        "post_exports": int(totals.get("post_exports") or 0)
        if isinstance(totals.get("post_exports"), int)
        else 0,
        "visual_sketches": int(totals.get("visual_sketches") or 0)
        if isinstance(totals.get("visual_sketches"), int)
        else 0,
        "families": manifest.get("families", []) if isinstance(manifest.get("families"), list) else [],
    }


def release_manifest_state(site_dir: Path, package_dir: Path) -> dict[str, Any]:
    return {
        "site": public_manifest_summary(site_dir),
        "package": public_manifest_summary(package_dir),
    }


def release_manifest_line(state: dict[str, Any]) -> str:
    parts: list[str] = []
    for label in ("site", "package"):
        summary = state.get(label, {})
        exists = "yes" if summary.get("exists") and summary.get("schema_ok") else "no"
        parts.append(
            f"{label} {exists}/{summary.get('edition_count', 0)} "
            f"posts {summary.get('post_exports', 0)} sketches {summary.get('visual_sketches', 0)}"
        )
    return "release manifest: " + "; ".join(parts)


def build_record(
    edition: dict[str, Any],
    site_dir: Path,
    package_dir: Path,
) -> dict[str, Any]:
    slug = edition_slug(edition)
    source = edition.get("source", {})
    source_type = source.get("type", "unknown") if isinstance(source, dict) else "unknown"
    source_album = source.get("album", "") if isinstance(source, dict) else ""
    project_path = SCRIPT_DIR / "work" / "editions" / slug / "project.json"
    project = load_json(project_path)
    public_receipt = load_json(site_dir / "editions" / slug / "flash-copy.json")
    package_receipt = load_json(package_dir / "editions" / slug / "flash-copy.json")
    public_counts = receipt_counts(public_receipt)
    project_clips = len(project.get("clips", [])) if isinstance(project, dict) and isinstance(project.get("clips"), list) else 0
    package_counts = receipt_counts(package_receipt)
    return {
        "slug": slug,
        "preset_status": edition.get("status", "ready"),
        "source_type": source_type,
        "source_album": source_album,
        "model": model_state(edition, project),
        "project_exists": project is not None,
        "project_clips": project_clips,
        "public_synced": public_receipt is not None,
        "public_clips": public_counts.get("manifest_clips", 0),
        "public_exports": public_exports_state(public_receipt),
        "post_pack": post_pack_state(public_receipt, project),
        "sketch": visual_sketch_state(project, project_path.parent),
        "presets": control_preset_state(edition, public_receipt),
        "visual_map": visual_map_state(edition),
        "package_synced": package_receipt is not None,
        "package_clips": package_counts.get("manifest_clips", 0),
        "note": str(edition.get("note", "")),
    }


def yes(value: bool) -> str:
    return "yes" if value else "no"


def print_table(records: list[dict[str, Any]]) -> None:
    headers = [
        "slug",
        "source",
        "project",
        "public",
        "package",
        "exports",
        "post_pack",
        "sketch",
        "presets",
        "map",
        "model",
    ]
    rows = []
    for record in records:
        rows.append(
            [
                record["slug"],
                record["source_type"],
                f"{yes(record['project_exists'])}/{record['project_clips']}",
                f"{yes(record['public_synced'])}/{record['public_clips']}",
                f"{yes(record['package_synced'])}/{record['package_clips']}",
                record["public_exports"],
                record["post_pack"],
                record["sketch"],
                record["presets"],
                record["visual_map"],
                record["model"],
            ]
        )
    widths = [
        max(len(str(value)) for value in [header] + [row[index] for row in rows])
        for index, header in enumerate(headers)
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def main() -> int:
    args = parse_args()
    editions_path = resolve_inside(args.editions, "editions")
    site_dir = resolve_inside(args.site_dir, "site-dir")
    package_dir = resolve_inside(args.package_dir, "package-dir")
    payload = load_json(editions_path)
    if payload is None:
        raise SystemExit(f"editions file does not exist: {editions_path}")
    records = [
        build_record(edition, site_dir, package_dir)
        for edition in edition_list(payload)
        if matches_edition(edition, args.edition)
    ]
    if args.edition and not records:
        raise SystemExit(f"edition not found: {args.edition}")
    manifest_state = release_manifest_state(site_dir, package_dir)
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "triptych.edition-status.v1",
                    "release_manifest": manifest_state,
                    "editions": records,
                },
                indent=2,
            )
        )
    else:
        print(release_manifest_line(manifest_state))
        print_table(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
