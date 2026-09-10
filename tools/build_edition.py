#!/usr/bin/env python3
"""Build a named triptych edition from a small text preset."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EDITIONS = SCRIPT_DIR / "editions.example.json"
DEFAULT_SOURCE_PROJECT = SCRIPT_DIR / "project.example.json"
PROJECT_KEYS = {
    "title",
    "subtitle",
    "work_title",
    "family",
    "timing_mode",
    "phrase_seconds",
    "canvas",
    "render",
    "audio",
    "effects",
    "web_media",
    "landing_page",
    "control_presets",
    "exports",
    "visual_sketch",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local project from a named edition preset, then optionally "
            "render and sync its lightweight flash copy."
        )
    )
    parser.add_argument("edition", nargs="?", help="Edition name or slug to build.")
    parser.add_argument(
        "--editions",
        type=Path,
        default=DEFAULT_EDITIONS,
        help="Edition preset JSON. Defaults to editions.example.json.",
    )
    parser.add_argument("--list", action="store_true", help="List available edition presets.")
    parser.add_argument(
        "--project",
        type=Path,
        help="Override generated project path. Defaults to work/editions/<slug>/project.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override staged media path. Defaults to samples/editions/<slug>/.",
    )
    parser.add_argument("--render", action="store_true", help="Run export_project.py for the edition.")
    parser.add_argument("--sync", action="store_true", help="Run sync_flash_copy.py for the edition.")
    parser.add_argument("--sketch", action="store_true", help="Render the edition visual-arrangement sketch.")
    parser.add_argument("--draft", action="store_true", help="Render draft output when --render is used.")
    parser.add_argument(
        "--only",
        help="Comma-separated export names to render when --render is used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Override the edition source limit for this run.",
    )
    parser.add_argument(
        "--photos-export-missing",
        action="store_true",
        help="For Photos editions, ask Photos.app to export missing selected originals.",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Reuse an existing generated project, then reapply edition settings.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing staged files when importing source media.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without writing files.")
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


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-").lower()
    return cleaned or "edition"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any], dry_run: bool) -> None:
    require_inside(path, "project")
    print(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def edition_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    editions = payload.get("editions")
    if not isinstance(editions, list):
        raise SystemExit("editions file must contain an editions array.")
    return [edition for edition in editions if isinstance(edition, dict)]


def edition_slug(edition: dict[str, Any]) -> str:
    slug = edition.get("slug") or edition.get("name") or "edition"
    return safe_slug(str(slug))


def find_edition(payload: dict[str, Any], requested: str) -> dict[str, Any]:
    requested_slug = safe_slug(requested)
    matches = []
    for edition in edition_list(payload):
        names = {
            safe_slug(str(edition.get("name", ""))),
            edition_slug(edition),
        }
        aliases = edition.get("aliases", [])
        if isinstance(aliases, list):
            names.update(safe_slug(str(alias)) for alias in aliases)
        if requested_slug in names:
            matches.append(edition)
    if not matches:
        available = ", ".join(edition_slug(edition) for edition in edition_list(payload))
        raise SystemExit(f"Unknown edition {requested!r}. Available: {available}")
    if len(matches) > 1:
        raise SystemExit(f"Edition {requested!r} is ambiguous.")
    return matches[0]


def list_editions(payload: dict[str, Any]) -> None:
    print("slug\tsource\tmodel\tstatus\tnote")
    for edition in edition_list(payload):
        source = edition.get("source", {})
        source_type = source.get("type", "unknown") if isinstance(source, dict) else "unknown"
        composition = edition.get("composition", {})
        model = ""
        if isinstance(composition, dict):
            model = str(composition.get("arrangement_model_album", "") or "")
        note = edition.get("note", "")
        print(
            f"{edition_slug(edition)}\t{source_type}\t{model}\t"
            f"{edition.get('status', 'ready')}\t{note}"
        )


def relative_to_base(path: Path, base: Path) -> str:
    return os.path.relpath(path.absolute(), base.absolute())


def default_project_path(slug: str) -> Path:
    return SCRIPT_DIR / "work" / "editions" / slug / "project.json"


def default_output_dir(slug: str) -> Path:
    return SCRIPT_DIR / "samples" / "editions" / slug


def source_project_path(payload: dict[str, Any], edition: dict[str, Any]) -> Path:
    source_project = edition.get("source_project") or payload.get("default_source_project")
    if source_project is None:
        return DEFAULT_SOURCE_PROJECT
    path = Path(str(source_project)).expanduser()
    return path if path.is_absolute() else SCRIPT_DIR / path


def album_selectors(source: dict[str, Any]) -> list[str]:
    selectors = []
    album = source.get("album")
    if isinstance(album, str) and album.strip():
        selectors.append(album)
    albums = source.get("albums")
    if isinstance(albums, list):
        selectors.extend(str(value) for value in albums if str(value).strip())
    if not selectors:
        raise SystemExit("photos_album editions require source.album or source.albums.")
    return selectors


def string_option(command: list[str], flag: str, value: Any) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def csv_option(command: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        text = ",".join(str(item) for item in value)
    else:
        text = str(value)
    if text.strip():
        command.extend([flag, text])


def bool_flag(command: list[str], flag: str, value: Any) -> None:
    if value:
        command.append(flag)


def import_command(
    payload: dict[str, Any],
    edition: dict[str, Any],
    project_path: Path,
    output_dir: Path,
    keep_existing: bool,
    dry_run: bool,
) -> list[str]:
    source = edition.get("source", {})
    if not isinstance(source, dict):
        raise SystemExit("edition source must be an object.")
    source_type = source.get("type", "photos_album")
    source_project = source_project_path(payload, edition)

    if source_type == "photos_album":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "import_photos.py"),
            "--source-project",
            str(source_project),
            "--project",
            str(project_path),
            "--output-dir",
            str(output_dir),
            "--album-match",
            str(source.get("album_match", "exact")),
            "--mode",
            str(source.get("mode", "symlink")),
        ]
        for selector in album_selectors(source):
            command.extend(["--album", selector])
        for key, flag in (
            ("order", "--order"),
            ("limit", "--limit"),
            ("offset", "--offset"),
            ("min_duration", "--min-duration"),
            ("max_duration", "--max-duration"),
            ("start_date", "--start-date"),
            ("end_date", "--end-date"),
            ("random_seed", "--random-seed"),
        ):
            string_option(command, flag, source.get(key))
        bool_flag(command, "--include-live-photos", source.get("include_live_photos", True))
        bool_flag(command, "--photos-export-missing", source.get("photos_export_missing", False))
    elif source_type == "photos_visual_album":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "import_photos_visuals.py"),
            "--source-project",
            str(source_project),
            "--project",
            str(project_path),
            "--output-dir",
            str(output_dir),
            "--album-match",
            str(source.get("album_match", "exact")),
        ]
        for selector in album_selectors(source):
            command.extend(["--album", selector])

        composition = edition.get("composition", {})
        model_album = source.get("model_album")
        if model_album is None and isinstance(composition, dict):
            model_album = composition.get("arrangement_model_album")
        if isinstance(model_album, list):
            for selector in model_album:
                command.extend(["--model-album", str(selector)])
        elif model_album:
            command.extend(["--model-album", str(model_album)])

        command.extend(
            [
                "--model-album-match",
                str(source.get("model_album_match", source.get("album_match", "exact"))),
                "--model-output-dir",
                str(SCRIPT_DIR / "work" / "editions" / edition_slug(edition) / "models"),
            ]
        )
        for key, flag in (
            ("model_limit", "--model-limit"),
            ("order", "--order"),
            ("limit", "--limit"),
            ("offset", "--offset"),
            ("start_date", "--start-date"),
            ("end_date", "--end-date"),
            ("random_seed", "--random-seed"),
            ("duration_seconds", "--duration-seconds"),
            ("width", "--width"),
            ("height", "--height"),
            ("fps", "--fps"),
            ("crf", "--crf"),
            ("preset", "--preset"),
            ("motion", "--motion"),
        ):
            string_option(command, flag, source.get(key))
        csv_option(command, "--duration-pattern", source.get("duration_pattern"))
        bool_flag(command, "--photos-export-missing", source.get("photos_export_missing", False))
    elif source_type == "folder":
        source_dir = source.get("source_dir")
        if not source_dir:
            raise SystemExit("folder editions require source.source_dir.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "import_folder.py"),
            str(Path(str(source_dir)).expanduser()),
            "--source-project",
            str(source_project),
            "--project",
            str(project_path),
            "--output-dir",
            str(output_dir),
            "--mode",
            str(source.get("mode", "symlink")),
            "--order",
            str(source.get("order", "filename")),
        ]
        string_option(command, "--limit", source.get("limit"))
        bool_flag(command, "--recursive", source.get("recursive", False))
    else:
        raise SystemExit(f"Unsupported edition source type: {source_type}")

    if keep_existing:
        command.append("--keep-existing")
    if dry_run:
        command.append("--dry-run")
    return command


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def scoped_project_defaults(project: dict[str, Any], slug: str, project_base: Path) -> None:
    site_dir = SCRIPT_DIR / "site" / "editions" / slug
    export_dir = SCRIPT_DIR / "renders" / "editions" / slug

    landing = dict(project.get("landing_page", {}))
    landing["output_file"] = relative_to_base(site_dir / "index.html", project_base)
    project["landing_page"] = landing

    web_media = dict(project.get("web_media", {}))
    web_media["output_dir"] = relative_to_base(site_dir / "media", project_base)
    project["web_media"] = web_media

    exports = project.get("exports", [])
    if isinstance(exports, list):
        scoped_exports = []
        for export in exports:
            if not isinstance(export, dict):
                continue
            scoped = dict(export)
            name = str(scoped.get("name", scoped.get("layout", "export")))
            scoped["output_file"] = relative_to_base(export_dir / f"{safe_slug(name)}.mp4", project_base)
            scoped_exports.append(scoped)
        project["exports"] = scoped_exports


def scoped_visual_sketch(project: dict[str, Any], slug: str, project_base: Path) -> None:
    raw_sketch = project.get("visual_sketch")
    if raw_sketch is None:
        return
    sketch_dir = SCRIPT_DIR / "renders" / "editions" / slug

    def scoped_item(item: dict[str, Any], index: int) -> dict[str, Any]:
        scoped = dict(item)
        output_value = scoped.get("output_file")
        if output_value:
            output_path = Path(str(output_value)).expanduser()
            output_path = output_path if output_path.is_absolute() else SCRIPT_DIR / output_path
        else:
            suffix = "" if index == 1 else f"-{index}"
            output_path = sketch_dir / f"draft-visual-sketch{suffix}.mp4"
        require_inside(output_path, "visual_sketch output_file")
        scoped["output_file"] = relative_to_base(output_path, project_base)
        return scoped

    if isinstance(raw_sketch, dict):
        project["visual_sketch"] = scoped_item(raw_sketch, 1)
    elif isinstance(raw_sketch, list):
        project["visual_sketch"] = [
            scoped_item(item, index)
            for index, item in enumerate(raw_sketch, start=1)
            if isinstance(item, dict)
        ]


def prompt_text(prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt.strip()
    if isinstance(prompt, dict):
        return str(prompt.get("text", "")).strip()
    return ""


def append_unique_prompts(project: dict[str, Any], edition: dict[str, Any]) -> None:
    prompts = []
    seen = set()
    for prompt in project.get("prompts", []):
        text = prompt_text(prompt)
        if not text or text in seen:
            continue
        prompts.append(prompt)
        seen.add(text)

    for prompt in edition.get("prompts", []):
        text = prompt_text(prompt)
        if not text or text in seen:
            continue
        if isinstance(prompt, str):
            prompts.append({"date": date.today().isoformat(), "text": prompt})
        elif isinstance(prompt, dict):
            prompts.append(prompt)
        seen.add(text)
    project["prompts"] = prompts


def apply_edition_settings(project_path: Path, edition: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if not project_path.exists() and not dry_run:
        raise SystemExit(f"Generated project not found: {project_path}")
    project = {} if dry_run and not project_path.exists() else load_json(project_path)
    slug = edition_slug(edition)
    project_base = project_path.parent
    scoped_project_defaults(project, slug, project_base)

    project["edition"] = {
        "name": edition.get("name", slug),
        "slug": slug,
        "work_title": edition.get("work_title"),
        "family": edition.get("family"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": edition.get("source", {}),
        "composition": edition.get("composition", {}),
        "status": edition.get("status", "ready"),
        "note": edition.get("note"),
    }
    composition = edition.get("composition")
    if isinstance(composition, dict):
        existing_composition = project.get("composition", {})
        if not isinstance(existing_composition, dict):
            existing_composition = {}
        project["composition"] = deep_merge(composition, existing_composition)

    project_overrides = {
        key: value
        for key, value in edition.items()
        if key in PROJECT_KEYS and value is not None
    }
    settings = edition.get("settings")
    if isinstance(settings, dict):
        project_overrides = deep_merge(project_overrides, settings)
    project = deep_merge(project, project_overrides)
    scoped_visual_sketch(project, slug, project_base)

    append_unique_prompts(project, edition)

    write_json(project_path, project, dry_run)
    return project


def run_command(command: list[str], dry_run: bool) -> None:
    print(" ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def render_command(project_path: Path, draft: bool, only: str | None, dry_run: bool) -> list[str]:
    command = [sys.executable, str(SCRIPT_DIR / "export_project.py"), str(project_path)]
    if draft:
        command.append("--draft")
    if only:
        command.extend(["--only", only])
    if dry_run:
        command.append("--dry-run")
    return command


def sync_command(project_path: Path, slug: str, dry_run: bool) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "sync_flash_copy.py"),
        str(project_path),
        "--manifest",
        str(SCRIPT_DIR / "work" / "editions" / slug / "flash-copy.json"),
        "--site-manifest",
        str(SCRIPT_DIR / "site" / "editions" / slug / "flash-copy.json"),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def sketch_command(project_path: Path, slug: str, edition: dict[str, Any], dry_run: bool) -> list[str]:
    settings = edition.get("visual_sketch", {})
    if not isinstance(settings, dict):
        settings = {}
    output_value = settings.get("output_file")
    if output_value is None:
        output_path = SCRIPT_DIR / "renders" / "editions" / slug / "draft-visual-sketch.mp4"
    else:
        output_path = Path(str(output_value)).expanduser()
        if not output_path.is_absolute():
            output_path = SCRIPT_DIR / output_path
    require_inside(output_path, "visual_sketch output_file")
    command = [
        sys.executable,
        str(SCRIPT_DIR / "render_visual_sketch.py"),
        str(project_path),
        "--output",
        str(output_path),
    ]
    for key, flag in (
        ("style", "--style"),
        ("width", "--width"),
        ("height", "--height"),
        ("fps", "--fps"),
        ("duration", "--duration"),
        ("slices", "--slices"),
        ("source_count", "--source-count"),
        ("model_opacity", "--model-opacity"),
        ("model_fit", "--model-fit"),
        ("crf", "--crf"),
        ("preset", "--preset"),
        ("panel_order", "--panel-order"),
    ):
        string_option(command, flag, settings.get(key))
    if settings.get("no_model_underlay"):
        command.append("--no-model-underlay")
    if dry_run:
        command.append("--dry-run")
    return command


def apply_cli_overrides(edition: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    updated = copy.deepcopy(edition)
    source = updated.setdefault("source", {})
    if not isinstance(source, dict):
        raise SystemExit("edition source must be an object.")
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("--limit must be positive when provided.")
        source["limit"] = args.limit
    if args.photos_export_missing:
        source["photos_export_missing"] = True
    return updated


def main() -> int:
    args = parse_args()
    editions_path = args.editions.expanduser()
    payload = load_json(editions_path)

    if args.list:
        list_editions(payload)
        return 0
    if not args.edition:
        raise SystemExit("Pass an edition name, or use --list.")

    edition = apply_cli_overrides(find_edition(payload, args.edition), args)
    slug = edition_slug(edition)
    project_path = args.project.expanduser() if args.project else default_project_path(slug)
    output_dir = args.output_dir.expanduser() if args.output_dir else default_output_dir(slug)
    require_inside(project_path, "project")
    require_inside(output_dir, "output-dir")

    if not args.skip_import:
        run_command(
            import_command(
                payload=payload,
                edition=edition,
                project_path=project_path,
                output_dir=output_dir,
                keep_existing=args.keep_existing,
                dry_run=args.dry_run,
            ),
            dry_run=args.dry_run,
        )

    apply_edition_settings(project_path, edition, args.dry_run)

    if args.sketch:
        run_command(sketch_command(project_path, slug, edition, args.dry_run), args.dry_run)
    if args.render or args.draft:
        run_command(render_command(project_path, args.draft, args.only, args.dry_run), args.dry_run)
    if args.sync:
        run_command(sync_command(project_path, slug, args.dry_run), args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
