#!/usr/bin/env python3
"""Validate layout files without touching media.

Geometry rules are not re-implemented here: every layout is checked by
``simvltanea.authoring.validate_layout_pair``, the single reference validator.
Interiors of nominal rects must be disjoint; the only drawn overlap permitted is
the declared ``presentation.overlap_px`` bleed across shared edges.

Accepted inputs: ``simvltanea.layout-preset/1`` and ``simvltanea.layout-pair/1``
files (by path), and the legacy count map of ``examples/layouts.json``.
Nothing is read from inside the package.
"""
from __future__ import annotations
from tools.paths import resolve_references

import argparse
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

from tools.paths import REPO_ROOT, LAYOUT, EXAMPLES_DIR
from simvltanea.authoring import LayoutError, load_layout_file, validate_layout_pair

SCRIPT_DIR = Path(__file__).resolve().parent
AMBIENT_OVERRIDE = LAYOUT.path("package") / "layouts.json"
DEFAULT_EXAMPLE = EXAMPLES_DIR / "layouts.json"
PRESET_FORMAT = "simvltanea.layout-preset/1"
SCHEMA = "triptych.layout-verification.v1"


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolve_inside(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    resolved = expanded.resolve() if expanded.is_absolute() else (REPO_ROOT / expanded).resolve()
    if not path_inside(resolved, REPO_ROOT):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")
    return resolved


def legacy_value(value):
    """Legacy count maps spell rects as JSON decimals; read finite floats by their decimal text."""
    if type(value) is float and math.isfinite(value):
        return str(Fraction(str(value)))
    return value


def validate_payload(data: dict, source: Path) -> list[str]:
    """Validate a legacy count map ({"N": {"portrait": [[x,y,w,h], ...], ...}}); one error per count."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{source}: root must be an object"]

    # Allow _comment or similar underscore keys as metadata
    counts = {k: v for k, v in data.items() if not k.startswith("_")}
    if not counts:
        errors.append(f"{source}: no layout counts found")
        return errors

    for key, value in counts.items():
        try:
            count = int(key)
        except ValueError:
            errors.append(f"{source}: key {key!r} must be integer count")
            continue
        if not (1 <= count <= 32):
            errors.append(f"{source}: count {count} must be in 1..32")
            continue
        if not isinstance(value, dict):
            errors.append(f"{source}: count {count} must be an object with portrait/landscape")
            continue
        pair = {}
        for orient in ("portrait", "landscape"):
            if orient not in value:
                errors.append(f"{source}: count {count} missing {orient}")
                continue
            rects = value[orient]
            if not isinstance(rects, list):
                errors.append(f"{source}: count {count} {orient} must be a list")
                continue
            pair[orient] = {"name": f"legacy-{count}-{orient}", "cells": [
                {"loop": f"loop-{index + 1}", "fit": "cover", "focal": ["1/2", "1/2"],
                 "rect": [legacy_value(v) for v in rect] if isinstance(rect, list) else rect}
                for index, rect in enumerate(rects)]}
        if len(pair) != 2:
            continue
        try:
            validate_layout_pair(pair, source=source, count=count)
        except LayoutError as exc:
            errors.append(f"{exc} [{exc.code}]")
    return errors


def validate_file(target: Path, presets_only: bool = False) -> tuple[list[str], str]:
    """Validate one file; return (errors, summary)."""
    try:
        data = resolve_references(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target}: cannot read JSON: {exc}"], ""
    if presets_only and not (isinstance(data, dict) and data.get("format") == PRESET_FORMAT):
        found = data.get("format") if isinstance(data, dict) else type(data).__name__
        return [f"{target}: --presets expects a {PRESET_FORMAT} file, got {found!r} [format]"], ""
    if isinstance(data, dict) and "format" in data:
        try:
            loaded = load_layout_file(target)
        except LayoutError as exc:
            return [f"{exc} [{exc.code}]"], ""
        if loaded["format"] == PRESET_FORMAT:
            counts = {"min": 1, "max": 12, **loaded.get("counts", {})}
            return [], f"preset {loaded['name']}: counts {counts['min']}..{counts['max']}"
        return [], f"pair: count {loaded['count']}"
    errors = validate_payload(data, target)
    counts = sorted(k for k in data if not k.startswith("_")) if isinstance(data, dict) else []
    return errors, f"counts: {counts}"


def report(args, target: Path, errors: list[str], summary: str = "", note: str | None = None) -> int:
    if args.json:
        payload = {"schema": SCHEMA, "ok": not errors, "errors": errors, "target": str(target)}
        if note:
            payload["note"] = note
        print(json.dumps(payload, indent=2))
    elif errors:
        print("layout verification failed", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
    elif note:
        print(f"layouts ok — {note}")
    else:
        print("layouts ok")
        shown = target.relative_to(REPO_ROOT) if path_inside(target, REPO_ROOT) else target
        print(f"{summary}; file: {shown}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate layout files (presets, pairs, legacy count maps).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--layouts", type=Path, default=None,
                       help="Validate FILE: a simvltanea.layout-preset/1 or layout-pair/1 file, or a legacy count map.")
    group.add_argument("--presets", type=Path, default=None,
                       help="Validate FILE as a simvltanea.layout-preset/1 preset (every count is expanded).")
    group.add_argument("--examples", action="store_true", help="Validate examples/layouts.json (the default).")
    parser.add_argument("--strict", action="store_true", help="Fail if target file is missing.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    if AMBIENT_OVERRIDE.exists():
        # The removed in-package override must not linger unnoticed; importing the package refuses it too.
        message = (f"{AMBIENT_OVERRIDE}: the in-package layout override was removed and is never read; "
                   "delete it and pass layouts as explicit files (--layouts FILE, load_layout_file(path))")
        return report(args, AMBIENT_OVERRIDE, [message])

    if args.layouts is not None:
        target = resolve_inside(args.layouts, "layouts")
    elif args.presets is not None:
        target = resolve_inside(args.presets, "presets")
    else:
        target = DEFAULT_EXAMPLE

    if not target.is_file():
        if args.strict or args.layouts is not None or args.presets is not None:
            return report(args, target, [f"{target}: missing layout file"])
        return report(args, target, [], note=f"no example file at {target} (defaults in artifact001_layouts.py)")

    errors, summary = validate_file(target, presets_only=args.presets is not None)
    return report(args, target, errors, summary)


if __name__ == "__main__":
    raise SystemExit(main())
