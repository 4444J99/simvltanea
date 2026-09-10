#!/usr/bin/env python3
"""Render a named edition's Story/Reel post pack, sync it, and verify the site."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PACKS = {
    "all": ("story-triptych", "reel-left", "reel-middle", "reel-right"),
    "reels": ("reel-left", "reel-middle", "reel-right"),
    "story": ("story-triptych",),
}
PROFILES: dict[str, dict[str, Any] | None] = {
    "draft": {
        "width": 540,
        "height": 960,
        "fps": 15,
        "crf": 34,
        "preset": "ultrafast",
        "max_videos": 5,
        "max_clip_seconds": 4,
    },
    "share": {
        "width": 720,
        "height": 1280,
        "fps": 24,
        "crf": 28,
        "preset": "veryfast",
        "max_videos": 12,
        "max_clip_seconds": 20,
    },
    "full": None,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a postable export pack for one edition: one Story plus three "
            "panel Reels by default, then sync public receipts and run the share gate."
        )
    )
    parser.add_argument("edition", help="Edition slug/name, for example ballerina or glitche.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="draft",
        help="Render profile. draft is small/fast, share is larger, full keeps edition settings.",
    )
    parser.add_argument(
        "--pack",
        choices=sorted(PACKS),
        default="all",
        help="Which configured exports to render. Defaults to all Story/Reels.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Override generated project path. Defaults to work/editions/<edition>/project.json.",
    )
    parser.add_argument("--limit", type=int, help="Source import limit if import is needed.")
    parser.add_argument("--skip-import", action="store_true", help="Reuse an existing staged edition project.")
    parser.add_argument("--keep-existing", action="store_true", help="Keep existing staged files when importing.")
    parser.add_argument(
        "--photos-export-missing",
        action="store_true",
        help="For Photos editions, ask Photos.app to export selected missing originals.",
    )
    parser.add_argument("--no-sync", action="store_true", help="Render only; skip flash-copy sync.")
    parser.add_argument("--no-verify", action="store_true", help="Skip verify_public_site.py after sync.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without writing or rendering.")
    return parser.parse_args()


def safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "edition"


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
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any], dry_run: bool) -> None:
    print(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], dry_run: bool) -> None:
    print(" ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def project_path_for(args: argparse.Namespace) -> Path:
    if args.project:
        path = args.project.expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    else:
        path = SCRIPT_DIR / "work" / "editions" / safe_slug(args.edition) / "project.json"
    require_inside(path, "project")
    return path


def build_command(args: argparse.Namespace, project_path: Path) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "build_edition.py"),
        args.edition,
        "--project",
        str(project_path),
    ]
    if args.skip_import or project_path.exists():
        command.append("--skip-import")
    if args.keep_existing:
        command.append("--keep-existing")
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.photos_export_missing:
        command.append("--photos-export-missing")
    if args.dry_run:
        command.append("--dry-run")
    return command


def apply_profile(
    project_path: Path,
    profile_name: str,
    pack_name: str,
    export_names: tuple[str, ...],
    dry_run: bool,
) -> None:
    project = load_json(project_path)
    exports = project.get("exports")
    if not isinstance(exports, list):
        raise SystemExit(f"{project_path}: exports must be a list.")

    profile = PROFILES[profile_name]
    seen: set[str] = set()
    for export in exports:
        if not isinstance(export, dict):
            continue
        name = str(export.get("name", ""))
        if name not in export_names:
            continue
        seen.add(name)
        if profile:
            export.update(profile)

    missing = set(export_names).difference(seen)
    if missing:
        raise SystemExit(f"{project_path}: missing configured export(s): {', '.join(sorted(missing))}")

    project["post_pack"] = {
        "profile": profile_name,
        "pack": pack_name,
        "exports": list(export_names),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "note": "Post-pack profiles change render settings for configured Story/Reel exports only.",
    }
    write_json(project_path, project, dry_run)


def print_profile_plan(
    project_path: Path,
    profile_name: str,
    pack_name: str,
    export_names: tuple[str, ...],
) -> None:
    profile = PROFILES[profile_name]
    print(
        "dry-run: would apply "
        f"{profile_name} profile to {project_path} for {pack_name} exports: "
        f"{', '.join(export_names)}"
    )
    if profile is None:
        print("dry-run: profile keeps configured render settings.")
    else:
        print(f"dry-run: profile settings {json.dumps(profile, sort_keys=True)}")


def export_command(project_path: Path, export_names: tuple[str, ...], dry_run: bool) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "export_project.py"),
        str(project_path),
        "--only",
        ",".join(export_names),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def sync_command(project_path: Path, edition_slug: str, dry_run: bool) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "sync_flash_copy.py"),
        str(project_path),
        "--manifest",
        str(SCRIPT_DIR / "work" / "editions" / edition_slug / "flash-copy.json"),
        "--site-manifest",
        str(SCRIPT_DIR / "site" / "editions" / edition_slug / "flash-copy.json"),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def site_index_command(dry_run: bool) -> list[str]:
    command = [sys.executable, str(SCRIPT_DIR / "build_site_index.py")]
    if dry_run:
        command.append("--dry-run")
    return command


def post_verify_command(project_path: Path) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / "verify_post_pack.py"), str(project_path)]


def site_verify_command() -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / "verify_public_site.py")]


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive when provided.")
    project_path = project_path_for(args)
    edition_slug = project_path.parent.name
    export_names = PACKS[args.pack]

    run(build_command(args, project_path), args.dry_run)
    if args.dry_run and not project_path.exists():
        print_profile_plan(project_path, args.profile, args.pack, export_names)
    else:
        apply_profile(project_path, args.profile, args.pack, export_names, args.dry_run)
    run(export_command(project_path, export_names, args.dry_run), args.dry_run)
    if not args.no_sync:
        run(sync_command(project_path, edition_slug, args.dry_run), args.dry_run)
        run(site_index_command(args.dry_run), args.dry_run)
    if not args.no_verify and not args.no_sync:
        run(post_verify_command(project_path), args.dry_run)
        run(site_verify_command(), args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
