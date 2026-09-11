#!/usr/bin/env python3
"""Validate authored layout overrides without touching media.

Mirrors core/composition.py rect_values / validate_layouts and
core/artifact001_layouts.py _load_authored for the JSON override path.
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "tools" else SCRIPT_DIR
DEFAULT_CORE = REPO_ROOT / "core" / "layouts.json"
DEFAULT_EXAMPLE = REPO_ROOT / "examples" / "layouts.json"


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


def rational(value, where: str) -> Fraction:
    if type(value) not in (str, int, float):
        raise ValueError(f"{where} must be rational")
    try:
        result = Fraction(str(value))
    except Exception as exc:
        raise ValueError(f"{where}: invalid rational") from exc
    if abs(result) > 10**9 or result.denominator > 10**9:
        raise ValueError(f"{where}: out of bounds")
    return result


def validate_payload(data: dict, source: Path) -> list[str]:
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
        except Exception:
            errors.append(f"{source}: key {key!r} must be integer count")
            continue
        if not (1 <= count <= 32):
            errors.append(f"{source}: count {count} must be in 1..32")
            continue
        if not isinstance(value, dict):
            errors.append(f"{source}: count {count} must be an object with portrait/landscape")
            continue
        for orient in ("portrait", "landscape"):
            if orient not in value:
                errors.append(f"{source}: count {count} missing {orient}")
                continue
            rects = value[orient]
            if not isinstance(rects, list):
                errors.append(f"{source}: count {count} {orient} must be a list")
                continue
            if len(rects) != count:
                errors.append(f"{source}: count {count} {orient} has {len(rects)} rects, expected {count}")
            seen_boxes: list[tuple[Fraction, Fraction, Fraction, Fraction]] = []
            for idx, rect in enumerate(rects, start=1):
                label = f"{source}: count {count} {orient}[{idx}]"
                if not isinstance(rect, list) or len(rect) != 4:
                    errors.append(f"{label} must be [x,y,width,height]")
                    continue
                try:
                    x, y, w, h = (rational(v, label) for v in rect)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if not (x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1):
                    errors.append(f"{label} must have positive area inside unit canvas (0<=x,y,0<w,h,x+w<=1,y+h<=1) got [{x},{y},{w},{h}]")
                    continue
                # non-overlap with previous boxes
                for (a, b, c, d) in seen_boxes:
                    if x < a + c and a < x + w and y < b + d and b < y + h:
                        errors.append(f"{label} overlaps prior rect [{a},{b},{c},{d}] — overlapping/occluded panels are not supported")
                        break
                seen_boxes.append((x, y, w, h))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate authored layout JSON.")
    parser.add_argument("--layouts", type=Path, default=None, help="Path to core/layouts.json (defaults to core/layouts.json if present, else examples).")
    parser.add_argument("--examples", action="store_true", help="Validate examples/layouts.json instead of core/layouts.json.")
    parser.add_argument("--strict", action="store_true", help="Fail if target file is missing.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    if args.layouts is not None:
        target = resolve_inside(args.layouts, "layouts")
    elif args.examples:
        target = DEFAULT_EXAMPLE
    else:
        target = DEFAULT_CORE if DEFAULT_CORE.is_file() else DEFAULT_EXAMPLE

    if not target.is_file():
        if args.strict:
            msg = f"{target}: missing layout file"
            if args.json:
                print(json.dumps({"schema": "triptych.layout-verification.v1", "ok": False, "errors": [msg], "target": str(target)}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"schema": "triptych.layout-verification.v1", "ok": True, "errors": [], "target": str(target), "note": "no override file — defaults in artifact001_layouts.py _AUTHORED_DEFAULT"}, indent=2))
        else:
            print(f"layouts ok — no override file at {target} (defaults in artifact001_layouts.py)")
        return 0

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"{target}: cannot read JSON: {exc}"
        if args.json:
            print(json.dumps({"schema": "triptych.layout-verification.v1", "ok": False, "errors": [msg], "target": str(target)}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 1

    errors = validate_payload(data, target)
    if args.json:
        print(json.dumps({"schema": "triptych.layout-verification.v1", "ok": not errors, "errors": errors, "target": str(target)}, indent=2))
    elif errors:
        print("layout verification failed", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
    else:
        print("layouts ok")
        # Summary
        counts = [k for k in data.keys() if not k.startswith("_")]
        print(f"counts: {sorted(counts)}; file: {target.relative_to(REPO_ROOT) if path_inside(target, REPO_ROOT) else target}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
