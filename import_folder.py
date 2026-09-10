#!/usr/bin/env python3
"""Stage videos from a chosen filesystem folder into a triptych project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = SCRIPT_DIR / "project.example.json"
DEFAULT_LOCAL_PROJECT = SCRIPT_DIR / "work" / "project.folder-local.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "samples" / "folder-import"
VIDEO_EXTENSIONS = {".3gp", ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage a folder of selected videos and write a local project manifest."
    )
    parser.add_argument("source_dir", type=Path, help="Folder containing chosen videos.")
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
        help="Generated local project manifest. Defaults to work/project.folder-local.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for staged videos. Defaults to samples/folder-import/.",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "symlink"),
        default="symlink",
        help="Stage media by copying files or by creating symlinks. Defaults to symlink.",
    )
    parser.add_argument(
        "--order",
        choices=("filename", "oldest", "recent"),
        default="filename",
        help="Order staged clips before rendering. Defaults to filename.",
    )
    parser.add_argument("--limit", type=int, help="Maximum videos to stage.")
    parser.add_argument("--recursive", action="store_true", help="Search source folder recursively.")
    parser.add_argument("--render", action="store_true", help="Run export_project.py after import.")
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


def safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "clip"


def collect_videos(source_dir: Path, recursive: bool) -> list[Path]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Source folder not found: {source_dir}")
    iterator = source_dir.rglob("*") if recursive else source_dir.iterdir()
    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def sort_key(path: Path, order: str) -> tuple[Any, ...]:
    stat = path.stat()
    if order == "oldest":
        return (stat.st_mtime, path.name.lower())
    if order == "recent":
        return (-stat.st_mtime, path.name.lower())
    return (path.name.lower(), stat.st_mtime)


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


def load_project(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Base project manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def staged_path(output_dir: Path, index: int, source_path: Path) -> Path:
    return output_dir / f"{index:03d}_{safe_name(source_path.name)}"


def stage_media(
    videos: list[Path],
    output_dir: Path,
    mode: str,
    dry_run: bool,
    local_base: Path,
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for index, source_path in enumerate(videos, start=1):
        destination = staged_path(output_dir, index, source_path)
        print(f"{mode} {source_path} -> {destination}")
        if not dry_run:
            if destination.exists() or destination.is_symlink():
                destination.unlink()
            if mode == "copy":
                shutil.copy2(source_path, destination)
            else:
                os.symlink(source_path.resolve(), destination)
        clips.append(
            {
                "path": relative_to_base(destination, local_base),
                "enabled": True,
                "source": "folder",
                "source_created": datetime.fromtimestamp(
                    source_path.stat().st_mtime, tz=timezone.utc
                ).date().isoformat(),
                "original_filename": source_path.name,
            }
        )
    return clips


def write_local_project(
    base_project_path: Path,
    local_project_path: Path,
    output_dir: Path,
    source_dir: Path,
    clips: list[dict[str, Any]],
    mode: str,
    dry_run: bool,
) -> None:
    project = load_project(base_project_path)
    local_base = local_project_path.parent
    normalize_export_paths(project, local_base)
    project["input_dir"] = relative_to_base(output_dir, local_base)
    project["clips"] = clips
    project["folder_import"] = {
        "source_dir": str(source_dir),
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staged_count": len(clips),
        "note": "Local folder import generated by import_folder.py.",
    }

    prompts = list(project.get("prompts", []))
    prompts.append(
        {
            "date": datetime.now().date().isoformat(),
            "text": "Use a selected local folder of videos as a deliberate canon source.",
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
    source_dir = args.source_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser()
    project_path = args.project.expanduser()
    source_project = args.source_project.expanduser()

    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive when provided.")
    require_inside(output_dir, SCRIPT_DIR, "output-dir")
    require_inside(project_path, SCRIPT_DIR, "project")

    videos = collect_videos(source_dir, args.recursive)
    videos = sorted(videos, key=lambda path: sort_key(path, args.order))
    if args.limit is not None:
        videos = videos[: args.limit]
    if not videos:
        supported = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise SystemExit(f"No supported videos found. Supported: {supported}")

    print(f"selected videos: {len(videos)}")
    prepare_output_dir(output_dir, args.keep_existing, args.dry_run)
    clips = stage_media(videos, output_dir, args.mode, args.dry_run, project_path.parent)
    write_local_project(
        base_project_path=source_project,
        local_project_path=project_path,
        output_dir=output_dir,
        source_dir=source_dir,
        clips=clips,
        mode=args.mode,
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
