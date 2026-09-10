#!/usr/bin/env python3
"""List, hide, and show clips in a triptych project manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = SCRIPT_DIR / "work" / "project.photos-local.json"
DEFAULT_EXCLUDE_FILE = SCRIPT_DIR / "work" / "photos-exclude-uuids.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage clip visibility in a triptych project JSON file."
    )
    parser.add_argument(
        "action",
        choices=("list", "hide", "show", "only", "ban", "unban"),
        help=(
            "list clips, hide/show matching clips, make only matching clips visible, "
            "or ban/unban Photos UUIDs from future imports."
        ),
    )
    parser.add_argument("selectors", nargs="*", help="1-based indexes or text/UUID substrings.")
    parser.add_argument(
        "--project",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Project manifest to edit. Defaults to work/project.photos-local.json.",
    )
    parser.add_argument(
        "--exclude-file",
        type=Path,
        default=DEFAULT_EXCLUDE_FILE,
        help="Persistent Photos UUID exclude file. Defaults to work/photos-exclude-uuids.txt.",
    )
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def load_project(path: Path) -> dict[str, Any]:
    project_path = path.expanduser().resolve()
    if not path_inside(project_path, SCRIPT_DIR):
        raise SystemExit("project must stay inside the SIMVLTANEA repository root.")
    if not project_path.exists():
        raise SystemExit(f"Project manifest not found: {project_path}")
    return json.loads(project_path.read_text(encoding="utf-8"))


def require_inside(path: Path, parent: Path, label: str) -> None:
    if not path_inside(path.expanduser().resolve(), parent):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def save_project(project: dict[str, Any], path: Path) -> None:
    path.expanduser().resolve().write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")


def clips(project: dict[str, Any]) -> list[dict[str, Any]]:
    raw = project.get("clips")
    if not isinstance(raw, list):
        raise SystemExit("Project has no clips array to manage.")
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            normalized.append({"path": entry, "enabled": True})
        elif isinstance(entry, dict):
            normalized.append(entry)
    project["clips"] = normalized
    return normalized


def searchable_text(index: int, clip: dict[str, Any]) -> str:
    values = [
        str(index + 1),
        str(clip.get("path", "")),
        str(clip.get("source_uuid", "")),
        str(clip.get("source_created", "")),
        str(clip.get("original_filename", "")),
    ]
    return " ".join(values).lower()


def matching_indexes(all_clips: list[dict[str, Any]], selectors: list[str]) -> set[int]:
    if not selectors:
        raise SystemExit("Provide at least one selector.")

    matches: set[int] = set()
    for selector in selectors:
        selector_text = selector.strip().lower()
        if not selector_text:
            continue
        if selector_text.isdigit():
            index = int(selector_text) - 1
            if not 0 <= index < len(all_clips):
                raise SystemExit(f"Clip index out of range: {selector}")
            matches.add(index)
            continue
        for index, clip in enumerate(all_clips):
            if selector_text in searchable_text(index, clip):
                matches.add(index)

    if not matches:
        raise SystemExit("No clips matched the selector(s).")
    return matches


def print_clips(all_clips: list[dict[str, Any]]) -> None:
    for index, clip in enumerate(all_clips, start=1):
        enabled = bool(clip.get("enabled", True))
        marker = "on " if enabled else "off"
        date = clip.get("source_created") or "undated"
        uuid = str(clip.get("source_uuid", ""))[:8]
        name = clip.get("original_filename") or Path(str(clip.get("path", ""))).name
        print(f"{index:03d} {marker} {date} {uuid} {name}")


def read_excluded_uuids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    values = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip().upper()
        if value:
            values.add(value)
    return values


def write_excluded_uuids(path: Path, values: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(values)) + ("\n" if values else ""), encoding="utf-8")


def main() -> int:
    args = parse_args()
    project_path = args.project.expanduser().resolve()
    exclude_file = args.exclude_file.expanduser().resolve()
    require_inside(exclude_file, SCRIPT_DIR, "exclude-file")
    project = load_project(project_path)
    all_clips = clips(project)

    if args.action == "list":
        print_clips(all_clips)
        return 0

    indexes = matching_indexes(all_clips, args.selectors)
    if args.action in {"ban", "unban"}:
        uuids = {
            str(all_clips[index].get("source_uuid", "")).strip().upper()
            for index in indexes
            if all_clips[index].get("source_uuid")
        }
        if not uuids:
            raise SystemExit("Matched clips do not have Photos source UUIDs to ban.")
        excluded = read_excluded_uuids(exclude_file)
        if args.action == "ban":
            excluded.update(uuids)
        else:
            excluded.difference_update(uuids)
        write_excluded_uuids(exclude_file, excluded)
        print(f"{args.action} future import UUID(s): {', '.join(sorted(uuid[:8] for uuid in uuids))}")
        return 0

    if args.action == "only":
        for clip in all_clips:
            clip["enabled"] = False
        enabled = True
    else:
        enabled = args.action == "show"

    for index in indexes:
        all_clips[index]["enabled"] = enabled

    save_project(project, project_path)
    print(f"{args.action} matched clip(s): {', '.join(str(index + 1) for index in sorted(indexes))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
