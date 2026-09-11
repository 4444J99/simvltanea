#!/usr/bin/env python3
"""Validate source edition presets before importing, rendering, or syncing."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "tools" else SCRIPT_DIR
DEFAULT_EDITIONS = REPO_ROOT / "editions.json"
DEFAULT_SITE_DIR = REPO_ROOT / "site"
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
PANEL_NAMES = {"left", "middle", "right"}
SOURCE_TYPES = {"photos_album", "photos_visual_album", "folder"}
SURFACES = {"canon", "sketch"}
DIRECTIONS = {"forward", "reverse", "pingpong"}
START_MODES = {"oldest", "random"}
SKETCH_STYLES = {"slices", "score", "serial", "fracture", "signal"}
AUDIO_MODES = {"none", "panel", "mix"}
TONE_MODES = {"none", "normalize", "histeq"}
FORBIDDEN_TEXT = (
    "/Users/",
    ".photoslibrary",
    "Photos Library",
    "Photos.sqlite",
    "resources/derivatives",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate triptych edition source presets without touching media."
    )
    parser.add_argument("--editions", type=Path, default=DEFAULT_EDITIONS, help="Edition preset JSON.")
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Public site dir for gate checks.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
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
    # Also allow repo-root-relative paths like ../editions.json or absolute repo-root paths.
    if not path_inside(resolved, SCRIPT_DIR) and not path_inside(resolved, REPO_ROOT):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")
    return resolved


def safe_slug(value: Any) -> str:
    text = str(value or "edition").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(".-").lower()
    return cleaned or "edition"


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: cannot read JSON: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: JSON root must be an object")
    return data


def edition_list(payload: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    editions = payload.get("editions")
    if not isinstance(editions, list):
        errors.append("editions must be a list")
        return []
    return [edition for edition in editions if isinstance(edition, dict)]


def add(error_list: list[str], slug: str, message: str) -> None:
    error_list.append(f"{slug}: {message}")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_range(
    errors: list[str],
    slug: str,
    label: str,
    value: Any,
    minimum: float,
    maximum: float,
) -> None:
    if not is_number(value):
        add(errors, slug, f"{label} must be numeric")
        return
    number = float(value)
    if number < minimum or number > maximum:
        add(errors, slug, f"{label} {number:g} outside {minimum:g}..{maximum:g}")


def validate_positive_number(errors: list[str], slug: str, label: str, value: Any) -> None:
    if value is None:
        return
    if not is_number(value) or float(value) <= 0:
        add(errors, slug, f"{label} must be a positive number")


def validate_positive_int(errors: list[str], slug: str, label: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        add(errors, slug, f"{label} must be a positive integer")


def validate_public_text(errors: list[str], slug: str, value: Any, path: str) -> None:
    if isinstance(value, str):
        for needle in FORBIDDEN_TEXT:
            if needle in value:
                add(errors, slug, f"{path} contains private token {needle!r}")
    elif isinstance(value, dict):
        for key, child in value.items():
            validate_public_text(errors, slug, child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_public_text(errors, slug, child, f"{path}[{index}]")


def validate_source(errors: list[str], slug: str, source: Any) -> None:
    if not isinstance(source, dict):
        add(errors, slug, "source must be an object")
        return
    source_type = source.get("type", "photos_album")
    if source_type not in SOURCE_TYPES:
        add(errors, slug, f"source.type {source_type!r} is not supported")
    if source_type in {"photos_album", "photos_visual_album"}:
        album = source.get("album")
        albums = source.get("albums")
        if not (isinstance(album, str) and album.strip()) and not (
            isinstance(albums, list) and any(isinstance(item, str) and item.strip() for item in albums)
        ):
            add(errors, slug, "Photos source requires source.album or source.albums")
    if source_type == "folder":
        source_dir = source.get("source_dir") or source.get("folder")
        if not isinstance(source_dir, str) or not source_dir.strip():
            add(errors, slug, "folder source requires source.source_dir (or source.folder)")
    for key in ("limit", "offset", "model_limit", "width", "height", "fps"):
        validate_positive_int(errors, slug, f"source.{key}", source.get(key))
    for key in ("min_duration", "max_duration", "duration_seconds"):
        validate_positive_number(errors, slug, f"source.{key}", source.get(key))
    duration_pattern = source.get("duration_pattern")
    if duration_pattern is not None:
        if not isinstance(duration_pattern, list) or not duration_pattern:
            add(errors, slug, "source.duration_pattern must be a non-empty list")
        else:
            for index, value in enumerate(duration_pattern, start=1):
                validate_positive_number(errors, slug, f"source.duration_pattern[{index}]", value)


def validate_audio(errors: list[str], slug: str, settings: dict[str, Any]) -> None:
    audio = settings.get("audio")
    if audio is None:
        return
    if not isinstance(audio, dict):
        add(errors, slug, "settings.audio must be an object")
        return
    mode = audio.get("mode")
    if mode is not None and mode not in AUDIO_MODES:
        add(errors, slug, f"settings.audio.mode {mode!r} is invalid")
    panel = audio.get("panel")
    if panel is not None and panel not in PANEL_NAMES:
        add(errors, slug, f"settings.audio.panel {panel!r} is invalid")
    for key in ("gain", "fade_seconds"):
        val = audio.get(key)
        if val is not None:
            if not is_number(val) or float(val) < 0:
                add(errors, slug, f"settings.audio.{key} must be a non-negative number")
    panel_gains = audio.get("panel_gains")
    if panel_gains is not None:
        if not isinstance(panel_gains, dict):
            add(errors, slug, "settings.audio.panel_gains must be an object")
        else:
            for panel_name, value in panel_gains.items():
                if panel_name not in PANEL_NAMES:
                    add(errors, slug, f"settings.audio.panel_gains has unknown panel {panel_name!r}")
                    continue
                validate_range(errors, slug, f"settings.audio.panel_gains.{panel_name}", value, 0, 2)


def validate_effects(errors: list[str], slug: str, settings: dict[str, Any]) -> None:
    effects = settings.get("effects")
    if effects is None:
        return
    if not isinstance(effects, dict):
        add(errors, slug, "settings.effects must be an object")
        return
    direction = effects.get("direction")
    if direction is not None and direction not in DIRECTIONS:
        add(errors, slug, f"settings.effects.direction {direction!r} is invalid")
    tone = effects.get("tone")
    if tone is not None:
        if not isinstance(tone, dict):
            add(errors, slug, "settings.effects.tone must be an object")
        elif tone.get("mode") is not None and tone.get("mode") not in TONE_MODES:
            add(errors, slug, f"settings.effects.tone.mode {tone.get('mode')!r} is invalid")


def validate_slice_config(errors: list[str], slug: str, settings: dict[str, Any]) -> None:
    cfg = settings.get("slice")
    if cfg is None:
        return
    if not isinstance(cfg, dict):
        add(errors, slug, "settings.slice must be an object")
        return
    enabled = cfg.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        add(errors, slug, "settings.slice.enabled must be boolean")
    for key in ("width", "height"):
        val = cfg.get(key)
        if val is not None:
            if not is_number(val) or not (0 < float(val) < 1):
                add(errors, slug, f"settings.slice.{key} must be in (0,1)")
    w = cfg.get("width", 0.5)
    h = cfg.get("height", 0.66)
    if is_number(w) and is_number(h) and float(w) * float(h) >= 1 and cfg.get("enabled"):
        add(errors, slug, "settings.slice area must be <1")


def validate_seam_config(errors: list[str], slug: str, settings: dict[str, Any]) -> None:
    cfg = settings.get("seam")
    if cfg is None:
        return
    if not isinstance(cfg, dict):
        add(errors, slug, "settings.seam must be an object")
        return
    enabled = cfg.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        add(errors, slug, "settings.seam.enabled must be boolean")
    w = cfg.get("width")
    if w is not None:
        if not is_number(w) or not (0 < float(w) <= 0.15):
            add(errors, slug, "settings.seam.width must be in (0,0.15]")
    mode = cfg.get("mode")
    if mode is not None and mode not in ("blur", "feather", "morph"):
        add(errors, slug, f"settings.seam.mode {mode!r} invalid")
    sigma = cfg.get("sigma")
    if sigma is not None:
        if not is_number(sigma) or not (0 < float(sigma) <= 0.1):
            add(errors, slug, "settings.seam.sigma must be in (0,0.1]")


def normalize_panel_order(value: Any) -> list[str] | None:
    if isinstance(value, str):
        names = [name.strip() for name in value.split(",") if name.strip()]
    elif isinstance(value, list):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        return None
    if len(names) == 3 and set(names) == PANEL_NAMES:
        return names
    return None


def validate_control_presets(errors: list[str], slug: str, presets: Any) -> tuple[int, str | None]:
    if presets is None:
        return 0, None
    if not isinstance(presets, list):
        add(errors, slug, "control_presets must be a list")
        return 0, None
    seen: set[str] = set()
    default_ids: list[str] = []
    for index, preset in enumerate(presets, start=1):
        label = f"control_presets[{index}]"
        if not isinstance(preset, dict):
            add(errors, slug, f"{label} must be an object")
            continue
        preset_id = preset.get("id")
        if not isinstance(preset_id, str) or not SAFE_ID_RE.fullmatch(preset_id):
            add(errors, slug, f"{label}.id must be a safe lowercase id")
        elif preset_id in seen:
            add(errors, slug, f"duplicate control preset id {preset_id!r}")
        else:
            seen.add(preset_id)
        preset_label = preset.get("label")
        if not isinstance(preset_label, str) or not preset_label.strip():
            add(errors, slug, f"{label}.label must be a non-empty string")
        for key, allowed in (("surface", SURFACES), ("direction", DIRECTIONS), ("start", START_MODES)):
            if key in preset and preset[key] not in allowed:
                add(errors, slug, f"{label}.{key} {preset[key]!r} is invalid")
        panel_order = preset.get("panel_order", preset.get("panelOrder"))
        if panel_order is not None and normalize_panel_order(panel_order) is None:
            add(errors, slug, f"{label}.panel_order must contain left, middle, right once")
        for key in ("labels", "audio", "default"):
            if key in preset and not isinstance(preset[key], bool):
                add(errors, slug, f"{label}.{key} must be boolean")
        if preset.get("default") is True and isinstance(preset_id, str):
            default_ids.append(preset_id)
        if "volume" in preset:
            validate_range(errors, slug, f"{label}.volume", preset["volume"], 0, 1)
        panel_volumes = preset.get("panel_volumes", preset.get("panelVolumes"))
        if panel_volumes is not None:
            if not isinstance(panel_volumes, dict):
                add(errors, slug, f"{label}.panel_volumes must be an object")
            else:
                for panel_name, value in panel_volumes.items():
                    if panel_name not in PANEL_NAMES:
                        add(errors, slug, f"{label}.panel_volumes has unknown panel {panel_name!r}")
                        continue
                    validate_range(errors, slug, f"{label}.panel_volumes.{panel_name}", value, 0, 1.5)
    if len(default_ids) > 1:
        add(errors, slug, "only one control preset may be default")
    return len(seen), default_ids[0] if default_ids else None


def validate_visual_cell(errors: list[str], slug: str, label: str, cell: Any, source_count: int | None) -> None:
    if not isinstance(cell, dict):
        add(errors, slug, f"{label} must be an object")
        return
    for key in ("x", "y", "width", "height"):
        validate_range(errors, slug, f"{label}.{key}", cell.get(key), 0, 1)
    if is_number(cell.get("x")) and is_number(cell.get("width")) and float(cell["x"]) + float(cell["width"]) > 1.05:
        add(errors, slug, f"{label} extends beyond the right edge")
    if is_number(cell.get("y")) and is_number(cell.get("height")) and float(cell["y"]) + float(cell["height"]) > 1.05:
        add(errors, slug, f"{label} extends beyond the bottom edge")
    if "alpha" in cell:
        validate_range(errors, slug, f"{label}.alpha", cell["alpha"], 0, 1)
    source = cell.get("source")
    if source is not None:
        if not isinstance(source, int) or isinstance(source, bool) or source < 0:
            add(errors, slug, f"{label}.source must be a non-negative integer")
        elif source_count is not None and source >= source_count:
            add(errors, slug, f"{label}.source {source} must be below source_count {source_count}")


def visual_sketch_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def validate_visual_sketch(errors: list[str], slug: str, value: Any) -> tuple[str, int]:
    if value is None:
        return "none", 0
    if not isinstance(value, (dict, list)):
        add(errors, slug, "visual_sketch must be an object or list")
        return "invalid", 0
    map_summaries: list[str] = []
    total_cells = 0
    for sketch_index, sketch in enumerate(visual_sketch_items(value), start=1):
        prefix = f"visual_sketch[{sketch_index}]"
        style = sketch.get("style", "slices")
        if style not in SKETCH_STYLES:
            add(errors, slug, f"{prefix}.style {style!r} is invalid")
        output_file = sketch.get("output_file")
        if isinstance(output_file, str) and output_file:
            output_path = Path(output_file).expanduser()
            resolved = output_path if output_path.is_absolute() else (SCRIPT_DIR / output_path).resolve()
            if not path_inside(resolved, SCRIPT_DIR) and not path_inside(resolved, REPO_ROOT):
                add(errors, slug, f"{prefix}.output_file escapes incubator")
        for key in ("width", "height", "fps", "duration", "slices", "source_count"):
            validate_positive_number(errors, slug, f"{prefix}.{key}", sketch.get(key))
        source_count_value = sketch.get("source_count")
        source_count = int(source_count_value) if isinstance(source_count_value, int) and source_count_value > 0 else None
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
        if cell_key:
            if not isinstance(cells, list) or not cells:
                add(errors, slug, f"{prefix}.{cell_key} must be a non-empty list for {style} sketches")
            else:
                total_cells += len(cells)
                map_summaries.append(f"{style}/{len(cells)}")
                for cell_index, cell in enumerate(cells, start=1):
                    validate_visual_cell(errors, slug, f"{prefix}.{cell_key}[{cell_index}]", cell, source_count)
        else:
            map_summaries.append(str(style))
    return ",".join(map_summaries) if map_summaries else "none", total_cells


def public_receipt_exists(site_dir: Path, slug: str) -> bool:
    return (site_dir / "editions" / slug / "flash-copy.json").exists()


def validate_payload(payload: dict[str, Any], site_dir: Path) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.editions.v1":
        errors.append(f"schema must be triptych.editions.v1, got {payload.get('schema')!r}")

    family_payload = payload.get("edition_families")
    families = family_payload if isinstance(family_payload, dict) else {}
    if not families:
        errors.append("edition_families must be an object")

    editions = edition_list(payload, errors)
    records: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for edition in editions:
        slug = safe_slug(edition.get("slug") or edition.get("name"))
        if not SAFE_ID_RE.fullmatch(slug):
            add(errors, slug, "slug must be a safe lowercase id")
        if slug in seen_slugs:
            add(errors, slug, "duplicate edition slug")
        seen_slugs.add(slug)

        validate_public_text(errors, slug, edition, "edition")
        family = edition.get("family")
        if not isinstance(family, str) or not family:
            add(errors, slug, "family is required")
        elif family not in families:
            add(errors, slug, f"family {family!r} is not declared in edition_families")
        else:
            members = families.get(family, {}).get("members") if isinstance(families.get(family), dict) else None
            if isinstance(members, list) and slug not in members:
                add(errors, slug, f"family {family!r} does not list this edition as a member")

        source = edition.get("source")
        validate_source(errors, slug, source)
        composition = edition.get("composition")
        if not isinstance(composition, dict):
            add(errors, slug, "composition must be an object")
        else:
            if composition.get("family") and composition.get("family") != family:
                add(errors, slug, "composition.family must match edition family")
            if not isinstance(composition.get("panel_arrangement_role"), str):
                add(errors, slug, "composition.panel_arrangement_role is required")
            if family == "structural_recomposition" and not isinstance(
                composition.get("arrangement_model_role"), str
            ):
                add(errors, slug, "structural recomposition requires arrangement_model_role")

        settings = edition.get("settings", {})
        if settings is not None and not isinstance(settings, dict):
            add(errors, slug, "settings must be an object")
            settings = {}
        if isinstance(settings, dict):
            validate_audio(errors, slug, settings)
            validate_effects(errors, slug, settings)
            validate_slice_config(errors, slug, settings)
            validate_seam_config(errors, slug, settings)

        preset_count, default_preset = validate_control_presets(errors, slug, edition.get("control_presets"))
        visual_map, cell_count = validate_visual_sketch(errors, slug, edition.get("visual_sketch"))

        public_exists = public_receipt_exists(site_dir, slug)
        gated = slug == "porn" or edition.get("public") is False or edition.get("gated") is True
        if slug == "porn" and public_exists:
            add(errors, slug, "Porn Signal Damage is gated but has a public flash-copy receipt")
        if edition.get("public") is True and gated:
            add(errors, slug, "gated edition must not set public true")

        records.append(
            {
                "slug": slug,
                "family": family or "",
                "source": source.get("type", "unknown") if isinstance(source, dict) else "invalid",
                "presets": preset_count,
                "default_preset": default_preset,
                "visual_map": visual_map,
                "visual_cells": cell_count,
                "public_receipt": public_exists,
                "gated": gated,
            }
        )

    declared_members: set[str] = set()
    for family_name, family in families.items():
        if not isinstance(family, dict):
            errors.append(f"edition_families.{family_name} must be an object")
            continue
        members = family.get("members")
        if not isinstance(members, list):
            errors.append(f"edition_families.{family_name}.members must be a list")
            continue
        declared_members.update(str(member) for member in members)
    missing_declared = sorted(declared_members.difference(seen_slugs))
    for slug in missing_declared:
        errors.append(f"edition_families declares missing edition {slug!r}")

    return errors, records


def print_summary(records: list[dict[str, Any]]) -> None:
    total_presets = sum(record["presets"] for record in records)
    total_cells = sum(record["visual_cells"] for record in records)
    gated = ", ".join(record["slug"] for record in records if record["gated"]) or "none"
    print("edition presets ok")
    print(f"editions: {len(records)}; presets: {total_presets}; visual cells: {total_cells}; gated: {gated}")
    for record in records:
        default = record["default_preset"] or "none"
        public = "public" if record["public_receipt"] else "local-only"
        print(
            f"- {record['slug']}: {record['source']} / {record['family']} / "
            f"presets {record['presets']} default {default} / map {record['visual_map']} / {public}"
        )


def main() -> int:
    args = parse_args()
    editions_path = resolve_inside(args.editions, "editions")
    site_dir = resolve_inside(args.site_dir, "site-dir")
    payload = load_json(editions_path)
    errors, records = validate_payload(payload, site_dir)
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "triptych.edition-verification.v1",
                    "ok": not errors,
                    "errors": errors,
                    "editions": records,
                },
                indent=2,
            )
        )
    elif errors:
        print("edition preset verification failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print_summary(records)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
