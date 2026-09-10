#!/usr/bin/env python3
"""Build a lightweight flash-copy receipt for a selected triptych edition."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import export_project
import build_site_index


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PHOTOS_PROJECT = SCRIPT_DIR / "work" / "project.photos-local.json"
DEFAULT_FOLDER_PROJECT = SCRIPT_DIR / "work" / "project.folder-local.json"
DEFAULT_PROJECT = SCRIPT_DIR / "project.example.json"
DEFAULT_WORK_MANIFEST = SCRIPT_DIR / "work" / "flash-copy.json"
DEFAULT_SITE_MANIFEST = SCRIPT_DIR / "site" / "flash-copy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate disposable web proxies plus private/public manifests for "
            "the currently selected triptych source set."
        )
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        help=(
            "Project manifest to sync. Defaults to work/project.photos-local.json "
            "when present, then work/project.folder-local.json, then project.example.json."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_WORK_MANIFEST,
        help="Private local flash-copy receipt. Defaults to work/flash-copy.json.",
    )
    parser.add_argument(
        "--site-manifest",
        type=Path,
        default=DEFAULT_SITE_MANIFEST,
        help="Public/proxy-centered receipt. Defaults to site/flash-copy.json.",
    )
    parser.add_argument(
        "--no-site-manifest",
        action="store_true",
        help="Skip writing the public/proxy-centered site manifest.",
    )
    parser.add_argument(
        "--no-landing",
        action="store_true",
        help="Skip rebuilding site/index.html after the flash copy is synced.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip rebuilding the public multi-edition site index.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print work without writing files.")
    return parser.parse_args()


def default_project_path() -> Path:
    for candidate in (DEFAULT_PHOTOS_PROJECT, DEFAULT_FOLDER_PROJECT, DEFAULT_PROJECT):
        if candidate.exists():
            return candidate
    return DEFAULT_PROJECT


def require_inside(path: Path, label: str) -> None:
    if not export_project.path_inside(path, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def relative_to_base(path: Path, base: Path = SCRIPT_DIR) -> str:
    return os.path.relpath(path.absolute(), base.absolute())


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def landing_output_path(project: dict[str, Any], project_path: Path) -> Path:
    landing = project.get("landing_page", {})
    if not isinstance(landing, dict):
        landing = {}
    output = export_project.resolve_path(
        landing.get("output_file"),
        project_path.parent,
        SCRIPT_DIR / "site" / "index.html",
    )
    require_inside(output, "landing_page output_file")
    return output


def source_file_info(path: Path, project_base: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "staged_path": relative_to_base(path, project_base),
        "staged_path_from_incubator": relative_to_base(path),
        "absolute_path": str(path.absolute()),
    }
    try:
        resolved = path.resolve()
        info["resolved_path"] = str(resolved)
    except OSError:
        resolved = path.absolute()
    try:
        stat = path.stat()
        info["size_bytes"] = stat.st_size
        info["mtime"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        info["missing"] = True
    if path.is_symlink():
        try:
            info["symlink_target"] = os.readlink(path)
        except OSError:
            pass
    if resolved != path.absolute():
        info["outside_incubator_source"] = not export_project.path_inside(resolved, SCRIPT_DIR)
    return info


def raw_clip_counts(project: dict[str, Any], project_path: Path) -> dict[str, int]:
    clips = project.get("clips")
    if isinstance(clips, list):
        total = len([clip for clip in clips if isinstance(clip, (str, dict))])
        visible = len(export_project.project_clip_entries(project, project_path.parent))
        disabled = max(0, total - visible)
        return {"project_clips": total, "visible_clips": visible, "hidden_clips": disabled}

    visible = len(export_project.project_clip_entries(project, project_path.parent))
    return {"project_clips": visible, "visible_clips": visible, "hidden_clips": 0}


def clip_display_name(entry: dict[str, Any], source: Path) -> str:
    original = entry.get("original_filename")
    if isinstance(original, str) and original.strip():
        return original
    return source.name


def proxy_media_for(
    source: Path,
    proxy: dict[str, Any],
    site_dir: Path,
    public: bool,
) -> dict[str, Any]:
    source_src = export_project.relative_media(source, site_dir)
    video_src = proxy.get("video_src")
    if not public and video_src is None:
        video_src = source_src
    media = {
        "video_src": video_src,
        "audio_src": proxy.get("audio_src"),
        "has_audio": bool(proxy.get("has_audio")),
        "proxy": bool(proxy.get("proxy")),
    }
    if not public:
        media["source_src"] = source_src
    return media


def clip_receipts(
    project: dict[str, Any],
    project_path: Path,
    site_dir: Path,
    media_proxies: dict[str, dict[str, Any]],
    public: bool,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for index, entry in enumerate(
        export_project.project_clip_entries(project, project_path.parent),
        start=1,
    ):
        source = entry["path"]
        proxy = media_proxies.get(str(source), {})
        receipt: dict[str, Any] = {
            "index": index,
            "name": source.name,
            "display_name": clip_display_name(entry, source),
            "created": entry.get("source_created"),
            "duration": entry.get("duration"),
            "width": entry.get("width"),
            "height": entry.get("height"),
            "media": proxy_media_for(source, proxy, site_dir, public),
        }
        if not public:
            receipt["source_uuid"] = entry.get("source_uuid")
            receipt["original_filename"] = entry.get("original_filename")
            receipt["source"] = source_file_info(source, project_path.parent)
        receipts.append({key: value for key, value in receipt.items() if value is not None})
    return receipts


def export_receipts(
    exports: list[dict[str, Any]],
    project_path: Path,
    site_dir: Path,
    public: bool,
) -> list[dict[str, Any]]:
    receipts = []
    for export in exports:
        name = export.get("name", export.get("layout", "story"))
        output_file = export_project.resolve_path(
            export.get("output_file"),
            project_path.parent,
            SCRIPT_DIR / "renders" / f"{name}.mp4",
        )
        artifact_path = export_project.site_export_artifact_path(output_file, site_dir)
        published = bool(artifact_path is not None and artifact_path.exists())
        exists = output_file.exists() or published
        src = export_project.export_media_src(output_file, site_dir)
        receipt: dict[str, Any] = {
            "name": name,
            "layout": export.get("layout", "story"),
            "exists": exists,
        }
        if src is not None and (exists or not public):
            receipt["src"] = src
        if published:
            receipt["published"] = True
        if not public:
            receipt["output_file"] = relative_to_base(output_file, project_path.parent)
            receipt["output_file_from_incubator"] = relative_to_base(output_file)
            if artifact_path is not None:
                receipt["published_file_from_incubator"] = relative_to_base(artifact_path)
        receipts.append(receipt)
    return receipts


def flash_manifest(
    project: dict[str, Any],
    project_path: Path,
    exports: list[dict[str, Any]],
    site_dir: Path,
    media_proxies: dict[str, dict[str, Any]],
    public: bool,
) -> dict[str, Any]:
    clips = clip_receipts(project, project_path, site_dir, media_proxies, public)
    counts = raw_clip_counts(project, project_path)
    counts.update(
        {
            "manifest_clips": len(clips),
            "video_proxies": sum(
                1 for clip in clips if clip["media"].get("proxy") and clip["media"].get("video_src")
            ),
            "audio_proxies": sum(1 for clip in clips if clip["media"].get("audio_src")),
            "exports": len(exports),
        }
    )
    manifest: dict[str, Any] = {
        "schema": "triptych.flash-copy.v1",
        "generated_at": iso_now(),
        "public": public,
        "title": project.get("title", "Triptych Video Canon"),
        "work_title": project.get("work_title") or project.get("edition", {}).get("work_title"),
        "family": project.get("family") or project.get("edition", {}).get("family"),
        "source_project": relative_to_base(project_path),
        "landing_page": relative_to_base(site_dir / "index.html"),
        "counts": counts,
        "settings": {
            "timing_mode": project.get("timing_mode", "clip"),
            "canvas": project.get("canvas", {}),
            "render": project.get("render", {}),
            "audio": project.get("audio", {}),
            "effects": project.get("effects", {}),
            "web_media": export_project.web_media_settings(project),
        },
        "arrangement_score": export_project.arrangement_score(project),
        "control_presets": export_project.control_presets(project),
        "clips": clips,
        "exports": export_receipts(exports, project_path, site_dir, public),
        "notes": [
            "Flash copies are disposable proxy media plus metadata for the selected edition.",
            "Original media remains the source of record and is not mutated by this command.",
            "A public flash copy should include site/index.html, site/flash-copy.json, selected renders, and site/media proxies, not the private Photos library.",
        ],
    }
    if isinstance(project.get("post_pack"), dict):
        manifest["post_pack"] = project["post_pack"]
    if not public:
        manifest["private_notes"] = [
            "This local receipt may include absolute source paths and Photos source UUIDs.",
            "Keep work/ ignored unless intentionally promoting a sanitized edition.",
        ]
    return manifest


def write_json(path: Path, payload: dict[str, Any], dry_run: bool) -> None:
    require_inside(path, str(path))
    print(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def publish_export_artifacts(
    exports: list[dict[str, Any]],
    project_path: Path,
    site_dir: Path,
    dry_run: bool,
) -> None:
    artifact_dir = site_dir / "exports"
    require_inside(artifact_dir, "export artifact dir")
    for export in exports:
        name = export.get("name", export.get("layout", "story"))
        output_file = export_project.resolve_path(
            export.get("output_file"),
            project_path.parent,
            SCRIPT_DIR / "renders" / f"{name}.mp4",
        )
        if not output_file.exists():
            continue
        artifact_path = export_project.site_export_artifact_path(output_file, site_dir)
        if artifact_path is None:
            continue
        require_inside(artifact_path, "export artifact")
        fresh = False
        if artifact_path.exists():
            try:
                fresh = artifact_path.stat().st_mtime >= output_file.stat().st_mtime
            except OSError:
                fresh = False
        if fresh:
            continue
        print(f"publish export {output_file} -> {artifact_path}")
        if dry_run:
            continue
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_file, artifact_path)


def write_site_index(dry_run: bool) -> None:
    output = SCRIPT_DIR / "site" / "index.html"
    records = build_site_index.collect_editions(SCRIPT_DIR / "site", output.parent)
    print(f"write site index {output} ({len(records)} editions)")
    if dry_run:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_site_index.index_html(records), encoding="utf-8")


def main() -> int:
    args = parse_args()
    project_arg = args.project.expanduser() if args.project else default_project_path()
    project, project_path = export_project.load_project(project_arg)
    render_exports = export_project.export_definitions(project)
    receipt_exports = render_exports + export_project.visual_sketch_definitions(project)
    landing_output = landing_output_path(project, project_path)
    site_dir = landing_output.parent

    work_manifest = args.manifest.expanduser()
    site_manifest = args.site_manifest.expanduser()
    require_inside(work_manifest, "manifest")
    if not args.no_site_manifest:
        require_inside(site_manifest, "site-manifest")

    print(f"sync flash copy from {project_path}")
    media_proxies = export_project.build_source_media_proxies(
        project,
        project_path,
        site_dir,
        args.dry_run,
    )
    publish_export_artifacts(receipt_exports, project_path, site_dir, args.dry_run)

    write_json(
        work_manifest,
        flash_manifest(project, project_path, receipt_exports, site_dir, media_proxies, public=False),
        args.dry_run,
    )
    if not args.no_site_manifest:
        write_json(
            site_manifest,
            flash_manifest(project, project_path, receipt_exports, site_dir, media_proxies, public=True),
            args.dry_run,
        )

    if not args.no_landing:
        export_project.build_landing_page(project, project_path, render_exports, args.dry_run)
    root_index = (SCRIPT_DIR / "site" / "index.html").resolve()
    if not args.no_index and landing_output.resolve() != root_index:
        write_site_index(args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
