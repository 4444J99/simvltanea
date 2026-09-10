#!/usr/bin/env python3
"""Build a sanitized static index for published triptych editions."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_OUTPUT = DEFAULT_SITE_DIR / "index.html"
DEFAULT_PUBLIC_MANIFEST = DEFAULT_SITE_DIR / "public-manifest.json"
DEFAULT_RELEASE_BOARD = DEFAULT_SITE_DIR / "release-board.html"
DEFAULT_RELEASE_COPY = DEFAULT_SITE_DIR / "release-copy.md"
DEFAULT_PLATFORM_PLAN = DEFAULT_SITE_DIR / "platform-plan.md"
DEFAULT_RELEASE_QUEUE = DEFAULT_SITE_DIR / "release-queue.md"
DEFAULT_RELEASE_PLAYER = DEFAULT_SITE_DIR / "release-player.html"
DEFAULT_PLAYER_PRESETS = DEFAULT_SITE_DIR / "player-presets.md"
DEFAULT_EXHIBIT_LOOP = DEFAULT_SITE_DIR / "exhibit-loop.md"
DEFAULT_EXHIBIT_PROGRAMS = DEFAULT_SITE_DIR / "exhibit-programs.json"
DEFAULT_PLAYBACK_CONTRACT = DEFAULT_SITE_DIR / "playback-contract.json"
DEFAULT_COMPOSITION_ATLAS = DEFAULT_SITE_DIR / "composition-atlas.json"
DEFAULT_COMPOSITION_ATLAS_DOC = DEFAULT_SITE_DIR / "composition-atlas.md"
DEFAULT_RHYTHM_MAP = DEFAULT_SITE_DIR / "rhythm-map.json"
DEFAULT_RHYTHM_MAP_DOC = DEFAULT_SITE_DIR / "rhythm-map.md"
DEFAULT_SOUND_MAP = DEFAULT_SITE_DIR / "sound-map.json"
DEFAULT_SOUND_MAP_DOC = DEFAULT_SITE_DIR / "sound-map.md"
DEFAULT_RELEASE_MATRIX = DEFAULT_SITE_DIR / "release-matrix.json"
DEFAULT_RELEASE_MATRIX_DOC = DEFAULT_SITE_DIR / "release-matrix.md"
DEFAULT_EXHIBIT_CUE_SHEET = DEFAULT_SITE_DIR / "exhibit-cue-sheet.json"
DEFAULT_EXHIBIT_CUE_SHEET_DOC = DEFAULT_SITE_DIR / "exhibit-cue-sheet.md"
DEFAULT_CURATORIAL_SCORE = DEFAULT_SITE_DIR / "curatorial-score.json"
DEFAULT_CURATORIAL_SCORE_DOC = DEFAULT_SITE_DIR / "curatorial-score.md"
DEFAULT_LIVING_LOOP = DEFAULT_SITE_DIR / "living-loop.json"
DEFAULT_LIVING_LOOP_DOC = DEFAULT_SITE_DIR / "living-loop.md"

LIVING_ROTATION_PROFILES = (
    {
        "id": "studio-review",
        "label": "Studio Review",
        "volume": "0.35",
        "rate": "0.75",
        "note": "Quiet review pass with audible clips kept present but restrained.",
    },
    {
        "id": "gallery-slow",
        "label": "Gallery Slow",
        "volume": "0.20",
        "rate": "0.50",
        "note": "Slow digital-frame pass for watching the public loops as moving stills.",
    },
    {
        "id": "post-spark",
        "label": "Post Spark",
        "volume": "0.45",
        "rate": "1.00",
        "note": "Brighter posting-review pass for finding Story/Reel excerpts.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a public index from site/editions/*/flash-copy.json receipts."
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=DEFAULT_SITE_DIR,
        help="Static site directory. Defaults to site/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Index HTML path. Defaults to site/index.html.",
    )
    parser.add_argument(
        "--public-manifest",
        type=Path,
        default=DEFAULT_PUBLIC_MANIFEST,
        help="Public release manifest path. Defaults to site/public-manifest.json.",
    )
    parser.add_argument(
        "--release-board",
        type=Path,
        default=DEFAULT_RELEASE_BOARD,
        help="Human release-board HTML path. Defaults to site/release-board.html.",
    )
    parser.add_argument(
        "--release-copy",
        type=Path,
        default=DEFAULT_RELEASE_COPY,
        help="Public release-copy markdown path. Defaults to site/release-copy.md.",
    )
    parser.add_argument(
        "--platform-plan",
        type=Path,
        default=DEFAULT_PLATFORM_PLAN,
        help="Public platform-plan markdown path. Defaults to site/platform-plan.md.",
    )
    parser.add_argument(
        "--release-queue",
        type=Path,
        default=DEFAULT_RELEASE_QUEUE,
        help="Public release-queue markdown path. Defaults to site/release-queue.md.",
    )
    parser.add_argument(
        "--release-player",
        type=Path,
        default=DEFAULT_RELEASE_PLAYER,
        help="Public release-player HTML path. Defaults to site/release-player.html.",
    )
    parser.add_argument(
        "--player-presets",
        type=Path,
        default=DEFAULT_PLAYER_PRESETS,
        help="Public player-presets markdown path. Defaults to site/player-presets.md.",
    )
    parser.add_argument(
        "--exhibit-loop",
        type=Path,
        default=DEFAULT_EXHIBIT_LOOP,
        help="Public exhibit-loop markdown path. Defaults to site/exhibit-loop.md.",
    )
    parser.add_argument(
        "--exhibit-programs",
        type=Path,
        default=DEFAULT_EXHIBIT_PROGRAMS,
        help="Public exhibit-programs JSON path. Defaults to site/exhibit-programs.json.",
    )
    parser.add_argument(
        "--playback-contract",
        type=Path,
        default=DEFAULT_PLAYBACK_CONTRACT,
        help="Public playback-contract JSON path. Defaults to site/playback-contract.json.",
    )
    parser.add_argument(
        "--composition-atlas",
        type=Path,
        default=DEFAULT_COMPOSITION_ATLAS,
        help="Public composition-atlas JSON path. Defaults to site/composition-atlas.json.",
    )
    parser.add_argument(
        "--composition-atlas-doc",
        type=Path,
        default=DEFAULT_COMPOSITION_ATLAS_DOC,
        help="Public composition-atlas markdown path. Defaults to site/composition-atlas.md.",
    )
    parser.add_argument(
        "--rhythm-map",
        type=Path,
        default=DEFAULT_RHYTHM_MAP,
        help="Public rhythm-map JSON path. Defaults to site/rhythm-map.json.",
    )
    parser.add_argument(
        "--rhythm-map-doc",
        type=Path,
        default=DEFAULT_RHYTHM_MAP_DOC,
        help="Public rhythm-map markdown path. Defaults to site/rhythm-map.md.",
    )
    parser.add_argument(
        "--sound-map",
        type=Path,
        default=DEFAULT_SOUND_MAP,
        help="Public sound-map JSON path. Defaults to site/sound-map.json.",
    )
    parser.add_argument(
        "--sound-map-doc",
        type=Path,
        default=DEFAULT_SOUND_MAP_DOC,
        help="Public sound-map markdown path. Defaults to site/sound-map.md.",
    )
    parser.add_argument(
        "--release-matrix",
        type=Path,
        default=DEFAULT_RELEASE_MATRIX,
        help="Public release-matrix JSON path. Defaults to site/release-matrix.json.",
    )
    parser.add_argument(
        "--release-matrix-doc",
        type=Path,
        default=DEFAULT_RELEASE_MATRIX_DOC,
        help="Public release-matrix markdown path. Defaults to site/release-matrix.md.",
    )
    parser.add_argument(
        "--exhibit-cue-sheet",
        type=Path,
        default=DEFAULT_EXHIBIT_CUE_SHEET,
        help="Public exhibit cue-sheet JSON path. Defaults to site/exhibit-cue-sheet.json.",
    )
    parser.add_argument(
        "--exhibit-cue-sheet-doc",
        type=Path,
        default=DEFAULT_EXHIBIT_CUE_SHEET_DOC,
        help="Public exhibit cue-sheet markdown path. Defaults to site/exhibit-cue-sheet.md.",
    )
    parser.add_argument(
        "--curatorial-score",
        type=Path,
        default=DEFAULT_CURATORIAL_SCORE,
        help="Public curatorial-score JSON path. Defaults to site/curatorial-score.json.",
    )
    parser.add_argument(
        "--curatorial-score-doc",
        type=Path,
        default=DEFAULT_CURATORIAL_SCORE_DOC,
        help="Public curatorial-score markdown path. Defaults to site/curatorial-score.md.",
    )
    parser.add_argument(
        "--living-loop",
        type=Path,
        default=DEFAULT_LIVING_LOOP,
        help="Public living-loop JSON path. Defaults to site/living-loop.json.",
    )
    parser.add_argument(
        "--living-loop-doc",
        type=Path,
        default=DEFAULT_LIVING_LOOP_DOC,
        help="Public living-loop markdown path. Defaults to site/living-loop.md.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print output path without writing.")
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


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("public") is True else None


def relative_href(path: Path, output_dir: Path) -> str:
    return os.path.relpath(path.absolute(), output_dir.absolute()).replace(os.sep, "/")


def first_proxy_src(data: dict[str, Any], edition_dir: Path, output_dir: Path) -> str | None:
    for clip in data.get("clips", []):
        if not isinstance(clip, dict):
            continue
        media = clip.get("media", {})
        if not isinstance(media, dict):
            continue
        video_src = media.get("video_src")
        if not isinstance(video_src, str) or not video_src:
            continue
        path = (edition_dir / video_src).resolve()
        if path.exists() and path_inside(path, SCRIPT_DIR):
            return relative_href(path, output_dir)
    return None


def public_export_href(
    export: dict[str, Any],
    edition_dir: Path,
    output_dir: Path,
) -> str | None:
    if not export.get("exists"):
        return None
    src = export.get("src")
    if not isinstance(src, str) or not src:
        return None
    path = (edition_dir / src).resolve()
    if path.exists() and path_inside(path, SCRIPT_DIR):
        return relative_href(path, output_dir)
    return None


def public_export_path(export: dict[str, Any], edition_dir: Path) -> Path | None:
    if not export.get("exists"):
        return None
    src = export.get("src")
    if not isinstance(src, str) or not src:
        return None
    path = (edition_dir / src).resolve()
    if path.exists() and path_inside(path, SCRIPT_DIR):
        return path
    return None


def existing_export(data: dict[str, Any], edition_dir: Path, output_dir: Path, layout: str) -> str | None:
    for export in data.get("exports", []):
        if not isinstance(export, dict):
            continue
        if export.get("layout") != layout:
            continue
        href = public_export_href(export, edition_dir, output_dir)
        if href:
            return href
    return None


def existing_export_media(data: dict[str, Any], edition_dir: Path, layout: str) -> dict[str, Any] | None:
    for export in data.get("exports", []):
        if not isinstance(export, dict):
            continue
        if export.get("layout") != layout:
            continue
        path = public_export_path(export, edition_dir)
        if path:
            return media_facts(path)
    return None


def ffprobe_json(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SystemExit("ffprobe is required to write public media facts.") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise SystemExit(f"ffprobe failed for {path}: {detail}") from error
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"ffprobe returned invalid JSON for {path}: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"ffprobe returned non-object JSON for {path}")
    return data


def numeric_field(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def media_facts(path: Path) -> dict[str, Any]:
    data = ffprobe_json(path)
    streams = data.get("streams", [])
    video_streams = [
        stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    width = None
    height = None
    video_codec = None
    if video_streams:
        first_video = video_streams[0]
        width = first_video.get("width") if isinstance(first_video.get("width"), int) else None
        height = first_video.get("height") if isinstance(first_video.get("height"), int) else None
        video_codec = first_video.get("codec_name") if isinstance(first_video.get("codec_name"), str) else None
    format_info = data.get("format", {})
    duration = numeric_field(format_info.get("duration")) if isinstance(format_info, dict) else None
    reported_size = numeric_field(format_info.get("size")) if isinstance(format_info, dict) else None
    facts: dict[str, Any] = {
        "size_bytes": int(reported_size) if reported_size is not None else path.stat().st_size,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "width": width,
        "height": height,
        "has_video": bool(video_streams),
        "has_audio": bool(audio_streams),
    }
    if video_codec:
        facts["video_codec"] = video_codec
    if width and height:
        facts["aspect_ratio"] = round(width / height, 6)
    return facts


def post_export_records(data: dict[str, Any], edition_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    names = {
        "story-triptych": "Story",
        "reel-left": "Left Reel",
        "reel-middle": "Middle Reel",
        "reel-right": "Right Reel",
    }
    records: list[dict[str, Any]] = []
    for export in data.get("exports", []):
        if not isinstance(export, dict):
            continue
        name = str(export.get("name", ""))
        if name not in names:
            continue
        href = public_export_href(export, edition_dir, output_dir)
        path = public_export_path(export, edition_dir)
        if href and path:
            records.append({"name": name, "label": names[name], "href": href, "media": media_facts(path)})
    return records


def control_preset_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for preset in data.get("control_presets", []):
        if not isinstance(preset, dict):
            continue
        preset_id = preset.get("id")
        if not isinstance(preset_id, str) or not preset_id or preset_id in seen:
            continue
        seen.add(preset_id)
        label = preset.get("label")
        records.append(
            {
                "id": preset_id,
                "label": str(label or preset_id),
                "default": preset.get("default") is True,
            }
        )
    return records


def export_kind(name: str, layout: str | None) -> str:
    if layout == "story" or name == "story-triptych":
        return "story"
    if layout in {"left", "middle", "right"} or name.startswith("reel-"):
        return "reel"
    if layout == "visual-sketch":
        return "visual-sketch"
    return "export"


def edition_record(receipt_path: Path, output_dir: Path) -> dict[str, Any] | None:
    data = load_json(receipt_path)
    if data is None:
        return None
    edition_dir = receipt_path.parent
    slug = edition_dir.name
    counts = data.get("counts", {}) if isinstance(data.get("counts"), dict) else {}
    page_path = edition_dir / "index.html"
    if not page_path.exists():
        return None
    post_pack = data.get("post_pack")
    if not isinstance(post_pack, dict):
        post_pack = None
    arrangement_score = data.get("arrangement_score")
    if not isinstance(arrangement_score, dict):
        arrangement_score = {}
    return {
        "slug": slug,
        "title": str(data.get("title") or slug),
        "work_title": str(data.get("work_title") or data.get("title") or slug),
        "family": str(data.get("family") or ""),
        "arrangement_score": arrangement_score,
        "href": relative_href(page_path, output_dir),
        "preview_src": first_proxy_src(data, edition_dir, output_dir),
        "sketch_href": existing_export(data, edition_dir, output_dir, "visual-sketch"),
        "sketch_media": existing_export_media(data, edition_dir, "visual-sketch"),
        "post_pack": post_pack,
        "post_exports": post_export_records(data, edition_dir, output_dir),
        "control_presets": control_preset_records(data),
        "clips": int(counts.get("visible_clips") or counts.get("manifest_clips") or 0),
        "video_proxies": int(counts.get("video_proxies") or 0),
        "audio_proxies": int(counts.get("audio_proxies") or 0),
        "exports": int(counts.get("exports") or 0),
    }


def collect_editions(site_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    editions_dir = site_dir / "editions"
    if not editions_dir.exists():
        return []
    records = []
    for receipt_path in sorted(editions_dir.glob("*/flash-copy.json")):
        record = edition_record(receipt_path, output_dir)
        if record is not None:
            records.append(record)
    return sorted(records, key=lambda item: item["slug"])


def metric(label: str, value: int) -> str:
    return (
        '<span class="metric">'
        f"<strong>{html.escape(str(value))}</strong>"
        f"<small>{html.escape(label)}</small>"
        "</span>"
    )


def human_bytes(size: Any) -> str:
    if not isinstance(size, int) or size < 0:
        return "unknown"
    units = ["B", "KB", "MB", "GB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def human_duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "unknown"
    total = max(0, float(seconds))
    minutes = int(total // 60)
    remainder = total - minutes * 60
    if minutes:
        return f"{minutes}:{remainder:04.1f}"
    return f"{remainder:.1f}s"


def preset_href(href: str, preset_id: str) -> str:
    separator = "&" if "?" in href else "?"
    return f"{href}{separator}{urlencode({'preset': preset_id})}"


def media_fact_line(media: Any) -> str:
    if not isinstance(media, dict):
        return "media facts pending"
    width = media.get("width")
    height = media.get("height")
    dimensions = f"{width}x{height}" if isinstance(width, int) and isinstance(height, int) else "unknown"
    duration = human_duration(media.get("duration_seconds"))
    size = human_bytes(media.get("size_bytes"))
    audio = "audio" if media.get("has_audio") is True else "silent"
    return f"{duration} / {dimensions} / {size} / {audio}"


def markdown_text(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("\n", " ").strip()
    for char in "\\`*_{}[]<>#|":
        text = text.replace(char, "")
    return " ".join(text.split())


def score_label(record: dict[str, Any]) -> str:
    arrangement = record.get("arrangement_score")
    if isinstance(arrangement, dict):
        label = arrangement.get("preview_label") or arrangement.get("style") or arrangement.get("family")
        if isinstance(label, str) and label:
            return label
    return str(record.get("family") or "triptych")


def caption_starter(record: dict[str, Any], item: dict[str, Any], kind_label: str) -> str:
    title = markdown_text(record.get("work_title") or record.get("title") or record.get("slug"))
    score = markdown_text(score_label(record))
    label = markdown_text(item.get("label") or item.get("name") or kind_label)
    if str(record.get("family")) == "signal_damage":
        body = "compression, reversal, and signal damage become the surface"
    else:
        body = "fragments pass across the triptych as a canon"
    return f"{title} / {label}. {score}: {body}."


def hashtag_line(record: dict[str, Any]) -> str:
    tags = ["#triptych", "#videoart", "#canon"]
    family = str(record.get("family") or "")
    if family == "signal_damage":
        tags.extend(["#signal", "#glitch"])
    elif family == "structural_recomposition":
        tags.extend(["#recomposition", "#collage"])
    return " ".join(tags)


def release_item_card(record: dict[str, Any], item: dict[str, Any], kind_label: str) -> str:
    href = html.escape(str(item.get("href") or ""))
    label = html.escape(str(item.get("label") or item.get("name") or kind_label))
    title = html.escape(str(record.get("work_title") or record.get("title") or record.get("slug")))
    slug = html.escape(str(record.get("slug") or "edition"))
    family = html.escape(str(record.get("family") or "edition"))
    facts = html.escape(media_fact_line(item.get("media")))
    return f"""
      <article class="release-item">
        <video src="{href}" controls preload="metadata" playsinline></video>
        <div class="release-copy">
          <p class="slug">{slug} / {family}</p>
          <h2>{title}</h2>
          <p class="kind">{html.escape(kind_label)} / {label}</p>
          <p class="facts">{facts}</p>
          <a class="button" href="{href}">Open media</a>
        </div>
      </article>
    """


def release_items(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for item in record.get("post_exports") or []:
        if isinstance(item, dict):
            items.append(("Post", item))
    if record.get("sketch_href"):
        items.append(
            (
                "Sketch",
                {
                    "name": "visual-sketch",
                    "label": "Visual sketch",
                    "href": record["sketch_href"],
                    "media": record.get("sketch_media"),
                },
            )
        )
    return items


def release_phase(item: dict[str, Any], kind: str) -> str:
    name = str(item.get("name") or "")
    if name == "story-triptych":
        return "story anchor"
    if name == "reel-left":
        return "panel reel left"
    if name == "reel-middle":
        return "panel reel middle"
    if name == "reel-right":
        return "panel reel right"
    if kind == "Sketch" or name == "visual-sketch":
        return "process sketch"
    return "public media"


def release_sequence(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for record in records:
        for kind, item in release_items(record):
            sequence.append(
                {
                    "record": record,
                    "kind": kind,
                    "item": item,
                    "phase": release_phase(item, kind),
                }
            )
    return sequence


def player_query(**params: str) -> str:
    clean = {key: value for key, value in params.items() if value}
    if not clean:
        return "release-player.html"
    return f"release-player.html?{urlencode(clean)}"


def playback_contract(records: list[dict[str, Any]]) -> dict[str, Any]:
    slugs = sorted(str(record.get("slug") or "") for record in records if record.get("slug"))
    families = sorted({str(record.get("family") or "") for record in records if record.get("family")})
    programs = exhibit_programs_manifest(records)["programs"]
    return {
        "schema": "triptych.playback-contract.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "release_player": "release-player.html",
        "public_manifest": "public-manifest.json",
        "exhibit_programs": "exhibit-programs.json",
        "player_presets": "player-presets.md",
        "allowed_params": [
            {
                "name": "program",
                "type": "id",
                "source": "exhibit-programs.json programs[].id",
                "effect": "loads a verified all-work, family, or edition program",
            },
            {
                "name": "edition",
                "type": "enum",
                "values": slugs,
                "effect": "filters the queue to one public edition",
            },
            {
                "name": "family",
                "type": "enum",
                "values": families,
                "effect": "filters the queue to one public edition family",
            },
            {
                "name": "mode",
                "type": "enum",
                "values": ["sequential", "random"],
                "default": "sequential",
                "effect": "sets queue traversal order",
            },
            {
                "name": "seed",
                "type": "text",
                "effect": "makes random playback reproducible without generating media",
            },
            {
                "name": "start",
                "type": "integer",
                "min": 1,
                "effect": "sets the initial 1-based queue position",
            },
            {
                "name": "muted",
                "type": "boolean",
                "true_values": ["1", "true", "yes"],
                "effect": "starts browser playback muted",
            },
            {
                "name": "autoplay",
                "type": "boolean",
                "true_values": ["1", "true", "yes"],
                "effect": "requests browser autoplay",
            },
            {
                "name": "kiosk",
                "type": "boolean",
                "true_values": ["1", "true", "yes"],
                "effect": "hides chrome for digital-frame or gallery playback",
            },
            {
                "name": "fit",
                "type": "enum",
                "values": ["cover", "contain"],
                "default": "cover",
                "effect": "sets video object-fit",
            },
            {
                "name": "volume",
                "type": "number",
                "min": 0,
                "max": 1,
                "default": 1,
                "effect": "sets browser playback volume only",
            },
            {
                "name": "rate",
                "type": "number",
                "min": 0.25,
                "max": 2,
                "default": 1,
                "effect": "sets browser playback rate only",
            },
        ],
        "examples": [
            {
                "label": "quiet slow kiosk",
                "href": player_query(mode="random", muted="0", volume="0.35", rate="0.75", autoplay="1", kiosk="1"),
            },
            {
                "label": "seeded all-work kiosk",
                "href": player_query(mode="random", muted="1", autoplay="1", kiosk="1", seed="ballerina-whole"),
            },
            {
                "label": "structural recomposition review",
                "href": player_query(family="structural_recomposition", mode="random", muted="1", seed="structural-recomposition"),
            },
        ],
        "counts": {
            "editions": len(slugs),
            "families": len(families),
            "presets": len(player_presets(records)),
            "programs": len(programs),
        },
        "gates": [
            "Static browser controls only; no source media mutation.",
            "Generated only from sanitized public flash-copy receipts.",
            "No private Photos paths, work receipts, samples, or render-cache paths.",
            "Package verification must pass before hosting or transfer.",
        ],
    }


def sanitized_arrangement_score(record: dict[str, Any]) -> dict[str, Any]:
    score = record.get("arrangement_score")
    if not isinstance(score, dict):
        return {}
    allowed = (
        "work_title",
        "family",
        "style",
        "material",
        "model",
        "model_fit",
        "model_role",
        "panel_role",
        "observation",
        "preview_label",
        "cell_count",
        "cell_key",
        "language",
    )
    clean: dict[str, Any] = {}
    for key in allowed:
        value = score.get(key)
        if isinstance(value, str) and value:
            clean[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) and item for item in value):
            clean[key] = value
    return clean


def composition_atlas(records: list[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, list[dict[str, Any]]] = {}
    editions: list[dict[str, Any]] = []
    for record in records:
        family = str(record.get("family") or "")
        if family:
            families.setdefault(family, []).append(record)
        post_exports = [
            {
                "name": str(export.get("name") or ""),
                "label": str(export.get("label") or export.get("name") or ""),
                "href": str(export.get("href") or ""),
            }
            for export in record.get("post_exports", [])
            if isinstance(export, dict) and export.get("href")
        ]
        sketch = None
        if record.get("sketch_href"):
            sketch = {
                "label": "Visual sketch",
                "href": str(record.get("sketch_href") or ""),
                "media": record.get("sketch_media"),
            }
        editions.append(
            {
                "slug": str(record.get("slug") or ""),
                "title": str(record.get("title") or record.get("slug") or ""),
                "work_title": str(record.get("work_title") or record.get("title") or record.get("slug") or ""),
                "family": family,
                "page": str(record.get("href") or ""),
                "player": player_query(edition=str(record.get("slug") or "")),
                "preview_src": record.get("preview_src") if isinstance(record.get("preview_src"), str) else None,
                "composition": sanitized_arrangement_score(record),
                "counts": {
                    "clips": int(record.get("clips") or 0),
                    "video_proxies": int(record.get("video_proxies") or 0),
                    "audio_proxies": int(record.get("audio_proxies") or 0),
                    "post_exports": len(post_exports),
                    "visual_sketches": 1 if sketch else 0,
                },
                "visual_sketch": sketch,
                "post_exports": post_exports,
            }
        )

    family_rows = []
    for family, family_records in sorted(families.items()):
        style_counts: dict[str, int] = {}
        for record in family_records:
            composition = sanitized_arrangement_score(record)
            style = str(composition.get("style") or "unspecified")
            style_counts[style] = style_counts.get(style, 0) + 1
        family_rows.append(
            {
                "family": family,
                "label": family.replace("_", " "),
                "edition_slugs": [str(record.get("slug") or "") for record in family_records if record.get("slug")],
                "work_titles": [
                    str(record.get("work_title") or record.get("title") or record.get("slug") or "")
                    for record in family_records
                ],
                "style_counts": dict(sorted(style_counts.items())),
                "program": f"release-player.html?program=family-{family}-kiosk-random-muted",
            }
        )

    return {
        "schema": "triptych.composition-atlas.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public flash-copy receipts",
        "entrypoint": "index.html",
        "public_manifest": "public-manifest.json",
        "release_player": "release-player.html",
        "exhibit_programs": "exhibit-programs.json",
        "playback_contract": "playback-contract.json",
        "composition_atlas_doc": "composition-atlas.md",
        "edition_count": len(editions),
        "family_count": len(family_rows),
        "families": family_rows,
        "editions": editions,
        "operating_gates": [
            "Generated only from sanitized public flash-copy receipts.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
            "Use as a public composition index, not as an ingestion or source-media manifest.",
        ],
    }


def composition_atlas_markdown(records: list[dict[str, Any]]) -> str:
    atlas = composition_atlas(records)
    lines = [
        "# Triptych Composition Atlas",
        "",
        "Generated from sanitized public edition receipts. This names the album-shaped composition logic without exposing Photos, work receipts, samples, or render-cache paths.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "- Machine atlas: composition-atlas.json",
        "",
        "## Families",
        "",
    ]
    for family in atlas["families"]:
        lines.extend(
            [
                f"### {markdown_text(family['label'])}",
                "",
                f"- Editions: {', '.join(markdown_text(slug) for slug in family['edition_slugs'])}",
                f"- Program: {markdown_text(family['program'])}",
                f"- Styles: {', '.join(f'{markdown_text(style)} ({count})' for style, count in family['style_counts'].items())}",
                "",
            ]
        )
    lines.extend(["## Editions", ""])
    for edition in atlas["editions"]:
        composition = edition.get("composition") if isinstance(edition.get("composition"), dict) else {}
        language = composition.get("language") if isinstance(composition.get("language"), list) else []
        lines.extend(
            [
                f"### {markdown_text(edition['work_title'])}",
                "",
                f"- Edition: {markdown_text(edition['slug'])}",
                f"- Family: {markdown_text(edition['family']).replace('_', ' ')}",
                f"- Page: {markdown_text(edition['page'])}",
                f"- Player: {markdown_text(edition['player'])}",
                f"- Style: {markdown_text(composition.get('style') or 'unspecified')}",
                f"- Material: {markdown_text(composition.get('material') or 'public edition material')}",
                f"- Score: {markdown_text(composition.get('preview_label') or 'none')}",
            ]
        )
        if composition.get("model"):
            lines.append(f"- Model: {markdown_text(composition.get('model'))}")
        if composition.get("model_role"):
            lines.append(f"- Model role: {markdown_text(composition.get('model_role'))}")
        if composition.get("panel_role"):
            lines.append(f"- Panel role: {markdown_text(composition.get('panel_role'))}")
        if composition.get("observation"):
            lines.append(f"- Observation: {markdown_text(composition.get('observation'))}")
        if language:
            lines.append(f"- Language: {', '.join(markdown_text(item) for item in language)}")
        sketch = edition.get("visual_sketch") if isinstance(edition.get("visual_sketch"), dict) else None
        if sketch:
            lines.append(f"- Visual sketch: {markdown_text(sketch.get('href'))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def media_duration(media: Any) -> float | None:
    if not isinstance(media, dict):
        return None
    value = media.get("duration_seconds")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value < 0:
        return None
    return round(float(value), 3)


def rhythm_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for position, entry in enumerate(release_sequence(records), start=1):
        record = entry["record"]
        item = entry["item"]
        kind = str(entry["kind"])
        media = item.get("media") if isinstance(item.get("media"), dict) else {}
        duration = media_duration(media)
        items.append(
            {
                "position": position,
                "edition": str(record.get("slug") or ""),
                "work_title": str(record.get("work_title") or record.get("title") or record.get("slug") or ""),
                "family": str(record.get("family") or ""),
                "kind": kind,
                "label": str(item.get("label") or item.get("name") or kind),
                "phase": str(entry.get("phase") or ""),
                "href": str(item.get("href") or ""),
                "duration_seconds": duration,
                "has_audio": bool(media.get("has_audio")) if isinstance(media, dict) else False,
                "size_bytes": int(media.get("size_bytes") or 0) if isinstance(media, dict) else 0,
                "targets": platform_targets(item, kind),
            }
        )
    return items


def rhythm_summary(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        group_key = str(item.get(key) or "")
        if not group_key:
            continue
        grouped.setdefault(group_key, []).append(item)
    rows: list[dict[str, Any]] = []
    for group_key, group_items in sorted(grouped.items()):
        durations = [
            float(item["duration_seconds"])
            for item in group_items
            if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
        ]
        rows.append(
            {
                key: group_key,
                "item_count": len(group_items),
                "audio_items": sum(1 for item in group_items if item.get("has_audio") is True),
                "total_duration_seconds": round(sum(durations), 3),
                "min_duration_seconds": round(min(durations), 3) if durations else None,
                "max_duration_seconds": round(max(durations), 3) if durations else None,
            }
        )
    return rows


def rhythm_map(records: list[dict[str, Any]]) -> dict[str, Any]:
    items = rhythm_items(records)
    durations = [
        float(item["duration_seconds"])
        for item in items
        if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
    ]
    return {
        "schema": "triptych.rhythm-map.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public media facts",
        "entrypoint": "index.html",
        "public_manifest": "public-manifest.json",
        "release_player": "release-player.html",
        "exhibit_programs": "exhibit-programs.json",
        "playback_contract": "playback-contract.json",
        "composition_atlas": "composition-atlas.json",
        "rhythm_map_doc": "rhythm-map.md",
        "item_count": len(items),
        "audio_item_count": sum(1 for item in items if item.get("has_audio") is True),
        "total_duration_seconds": round(sum(durations), 3),
        "min_duration_seconds": round(min(durations), 3) if durations else None,
        "max_duration_seconds": round(max(durations), 3) if durations else None,
        "families": rhythm_summary(items, "family"),
        "editions": rhythm_summary(items, "edition"),
        "items": items,
        "operating_gates": [
            "Generated only from sanitized public media facts.",
            "Durations describe public Story/Reel/sketch exports, not private source clips.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
            "Use as a public cadence score for player/program planning.",
        ],
    }


def rhythm_map_markdown(records: list[dict[str, Any]]) -> str:
    rhythm = rhythm_map(records)
    lines = [
        "# Triptych Rhythm Map",
        "",
        "Generated from sanitized public media facts. This is a public cadence score for the current Story/Reel/sketch outputs, not a private source-media ledger.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "- Machine rhythm map: rhythm-map.json",
        "",
        "## Cadence Snapshot",
        "",
        f"- Public items: {rhythm['item_count']}",
        f"- Audio-bearing items: {rhythm['audio_item_count']}",
        f"- Total public runtime: {rhythm['total_duration_seconds']} seconds",
        f"- Duration range: {rhythm['min_duration_seconds']} to {rhythm['max_duration_seconds']} seconds",
        "",
        "## Families",
        "",
    ]
    for family in rhythm["families"]:
        lines.extend(
            [
                f"### {markdown_text(family['family']).replace('_', ' ')}",
                "",
                f"- Items: {family['item_count']}",
                f"- Audio items: {family['audio_items']}",
                f"- Total runtime: {family['total_duration_seconds']} seconds",
                f"- Duration range: {family['min_duration_seconds']} to {family['max_duration_seconds']} seconds",
                "",
            ]
        )
    lines.extend(["## Editions", ""])
    for edition in rhythm["editions"]:
        lines.extend(
            [
                f"### {markdown_text(edition['edition'])}",
                "",
                f"- Items: {edition['item_count']}",
                f"- Audio items: {edition['audio_items']}",
                f"- Total runtime: {edition['total_duration_seconds']} seconds",
                f"- Duration range: {edition['min_duration_seconds']} to {edition['max_duration_seconds']} seconds",
                "",
            ]
        )
    lines.extend(["## Queue", ""])
    for item in rhythm["items"]:
        duration = item.get("duration_seconds")
        duration_text = f"{duration} seconds" if duration is not None else "unknown duration"
        audio = "audio" if item.get("has_audio") else "silent"
        lines.extend(
            [
                f"{item['position']}. {markdown_text(item['work_title'])} / {markdown_text(item['label'])}",
                f"   - Edition: {markdown_text(item['edition'])}",
                f"   - Family: {markdown_text(item['family']).replace('_', ' ')}",
                f"   - Phase: {markdown_text(item['phase'])}",
                f"   - Duration: {duration_text} / {audio}",
                f"   - URL: {markdown_text(item['href'])}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def sound_group_summary(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        group_key = str(item.get(key) or "")
        if not group_key:
            continue
        grouped.setdefault(group_key, []).append(item)
    rows: list[dict[str, Any]] = []
    for group_key, group_items in sorted(grouped.items()):
        audio_items = [item for item in group_items if item.get("has_audio") is True]
        silent_items = [item for item in group_items if item.get("has_audio") is not True]
        audio_durations = [
            float(item["duration_seconds"])
            for item in audio_items
            if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
        ]
        silent_durations = [
            float(item["duration_seconds"])
            for item in silent_items
            if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
        ]
        rows.append(
            {
                key: group_key,
                "item_count": len(group_items),
                "audio_items": len(audio_items),
                "silent_items": len(silent_items),
                "audio_duration_seconds": round(sum(audio_durations), 3),
                "silent_duration_seconds": round(sum(silent_durations), 3),
            }
        )
    return rows


def sound_map(records: list[dict[str, Any]]) -> dict[str, Any]:
    rhythm = rhythm_items(records)
    items = []
    for item in rhythm:
        has_audio = item.get("has_audio") is True
        items.append(
            {
                "position": item["position"],
                "edition": item["edition"],
                "work_title": item["work_title"],
                "family": item["family"],
                "kind": item["kind"],
                "label": item["label"],
                "phase": item["phase"],
                "href": item["href"],
                "duration_seconds": item["duration_seconds"],
                "has_audio": has_audio,
                "sound_role": "audio-bearing post export" if has_audio else "silent visual sketch",
                "playback_note": "browser volume/rate/mute controls only; no source audio mutation",
            }
        )
    audio_items = [item for item in items if item["has_audio"] is True]
    silent_items = [item for item in items if item["has_audio"] is not True]
    return {
        "schema": "triptych.sound-map.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public media facts",
        "entrypoint": "index.html",
        "public_manifest": "public-manifest.json",
        "release_player": "release-player.html",
        "playback_contract": "playback-contract.json",
        "rhythm_map": "rhythm-map.json",
        "sound_map_doc": "sound-map.md",
        "item_count": len(items),
        "audio_item_count": len(audio_items),
        "silent_item_count": len(silent_items),
        "families": sound_group_summary(items, "family"),
        "editions": sound_group_summary(items, "edition"),
        "controls": {
            "browser_only": ["muted", "volume", "rate"],
            "quiet_review": player_query(mode="random", muted="0", volume="0.35", rate="0.75"),
            "muted_kiosk": player_query(mode="random", muted="1", autoplay="1", kiosk="1"),
            "seeded_audio_review": player_query(mode="random", muted="0", volume="0.5", seed="sound-map"),
        },
        "items": items,
        "operating_gates": [
            "Generated only from sanitized public media facts.",
            "Sound roles describe public Story/Reel/sketch exports, not private source clips.",
            "Browser mute, volume, and rate controls do not mutate source media or rendered post packs.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
        ],
    }


def sound_map_markdown(records: list[dict[str, Any]]) -> str:
    sound = sound_map(records)
    lines = [
        "# Triptych Sound Map",
        "",
        "Generated from sanitized public media facts. This is a public audio/silence map for the current Story/Reel/sketch outputs, not a source-audio ledger.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Rhythm map: rhythm-map.md",
        "- Public manifest: public-manifest.json",
        "- Machine sound map: sound-map.json",
        "",
        "## Sound Snapshot",
        "",
        f"- Public items: {sound['item_count']}",
        f"- Audio-bearing items: {sound['audio_item_count']}",
        f"- Silent items: {sound['silent_item_count']}",
        f"- Quiet review: {sound['controls']['quiet_review']}",
        f"- Muted kiosk: {sound['controls']['muted_kiosk']}",
        f"- Seeded audio review: {sound['controls']['seeded_audio_review']}",
        "",
        "## Families",
        "",
    ]
    for family in sound["families"]:
        lines.extend(
            [
                f"### {markdown_text(family['family']).replace('_', ' ')}",
                "",
                f"- Items: {family['item_count']}",
                f"- Audio items: {family['audio_items']}",
                f"- Silent items: {family['silent_items']}",
                f"- Audio runtime: {family['audio_duration_seconds']} seconds",
                f"- Silent runtime: {family['silent_duration_seconds']} seconds",
                "",
            ]
        )
    lines.extend(["## Editions", ""])
    for edition in sound["editions"]:
        lines.extend(
            [
                f"### {markdown_text(edition['edition'])}",
                "",
                f"- Items: {edition['item_count']}",
                f"- Audio items: {edition['audio_items']}",
                f"- Silent items: {edition['silent_items']}",
                f"- Audio runtime: {edition['audio_duration_seconds']} seconds",
                f"- Silent runtime: {edition['silent_duration_seconds']} seconds",
                "",
            ]
        )
    lines.extend(["## Queue", ""])
    for item in sound["items"]:
        audio = "audio" if item["has_audio"] else "silent"
        lines.extend(
            [
                f"{item['position']}. {markdown_text(item['work_title'])} / {markdown_text(item['label'])}",
                f"   - Edition: {markdown_text(item['edition'])}",
                f"   - Family: {markdown_text(item['family']).replace('_', ' ')}",
                f"   - Sound: {audio} / {markdown_text(item['sound_role'])}",
                f"   - Duration: {item['duration_seconds']} seconds",
                f"   - URL: {markdown_text(item['href'])}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def release_matrix_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for item in rhythm_items(records):
        targets = item.get("targets") if isinstance(item.get("targets"), list) else []
        items.append(
            {
                "position": item["position"],
                "edition": item["edition"],
                "work_title": item["work_title"],
                "family": item["family"],
                "kind": item["kind"],
                "label": item["label"],
                "phase": item["phase"],
                "href": item["href"],
                "targets": [str(target) for target in targets if isinstance(target, str) and target],
                "duration_seconds": item["duration_seconds"],
                "has_audio": item["has_audio"],
            }
        )
    return items


def release_matrix(records: list[dict[str, Any]]) -> dict[str, Any]:
    items = release_matrix_items(records)
    by_edition: dict[str, list[dict[str, Any]]] = {}
    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_edition.setdefault(item["edition"], []).append(item)
        for target in item["targets"]:
            by_target.setdefault(target, []).append(item)
    editions = []
    for edition, edition_items in sorted(by_edition.items()):
        target_counts: dict[str, int] = {}
        for item in edition_items:
            for target in item["targets"]:
                target_counts[target] = target_counts.get(target, 0) + 1
        editions.append(
            {
                "edition": edition,
                "work_title": edition_items[0]["work_title"] if edition_items else edition,
                "family": edition_items[0]["family"] if edition_items else "",
                "item_count": len(edition_items),
                "audio_items": sum(1 for item in edition_items if item["has_audio"] is True),
                "targets": dict(sorted(target_counts.items())),
                "items": [
                    {
                        "position": item["position"],
                        "label": item["label"],
                        "kind": item["kind"],
                        "href": item["href"],
                        "targets": item["targets"],
                    }
                    for item in edition_items
                ],
            }
        )
    targets = []
    for target, target_items in sorted(by_target.items()):
        targets.append(
            {
                "target": target,
                "item_count": len(target_items),
                "edition_slugs": sorted({item["edition"] for item in target_items}),
                "items": [
                    {
                        "position": item["position"],
                        "edition": item["edition"],
                        "label": item["label"],
                        "kind": item["kind"],
                        "href": item["href"],
                    }
                    for item in target_items
                ],
            }
        )
    return {
        "schema": "triptych.release-matrix.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public release queue",
        "entrypoint": "index.html",
        "public_manifest": "public-manifest.json",
        "release_board": "release-board.html",
        "release_queue": "release-queue.md",
        "platform_plan": "platform-plan.md",
        "release_copy": "release-copy.md",
        "release_player": "release-player.html",
        "item_count": len(items),
        "edition_count": len(editions),
        "target_count": len(targets),
        "editions": editions,
        "targets": targets,
        "product_shop_gate": {
            "status": "deferred",
            "reason": "No product object has been selected; use this matrix for creative/posting review before merchandise decisions.",
        },
        "operating_gates": [
            "Generated only from sanitized public release queue data.",
            "Every href must be local to the public static package.",
            "Product/shop use stays deferred until a product object is explicitly selected.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
        ],
    }


def release_matrix_markdown(records: list[dict[str, Any]]) -> str:
    matrix = release_matrix(records)
    lines = [
        "# Triptych Release Matrix",
        "",
        "Generated from the sanitized public release queue. This groups public outputs by edition and platform target without exposing source media lanes.",
        "",
        "- Edition index: index.html",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Release player: release-player.html",
        "- Public manifest: public-manifest.json",
        "- Machine release matrix: release-matrix.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "",
        "## Snapshot",
        "",
        f"- Public items: {matrix['item_count']}",
        f"- Editions: {matrix['edition_count']}",
        f"- Platform targets: {matrix['target_count']}",
        f"- Product/shop gate: {matrix['product_shop_gate']['status']}",
        "",
        "## Targets",
        "",
    ]
    for target in matrix["targets"]:
        lines.extend(
            [
                f"### {markdown_text(target['target'])}",
                "",
                f"- Items: {target['item_count']}",
                f"- Editions: {', '.join(markdown_text(slug) for slug in target['edition_slugs'])}",
                "",
            ]
        )
        for item in target["items"]:
            lines.append(
                f"- {item['position']}. {markdown_text(item['edition'])} / {markdown_text(item['label'])}: {markdown_text(item['href'])}"
            )
        lines.append("")
    lines.extend(["## Editions", ""])
    for edition in matrix["editions"]:
        lines.extend(
            [
                f"### {markdown_text(edition['work_title'])}",
                "",
                f"- Edition: {markdown_text(edition['edition'])}",
                f"- Family: {markdown_text(edition['family']).replace('_', ' ')}",
                f"- Items: {edition['item_count']}",
                f"- Audio items: {edition['audio_items']}",
                f"- Targets: {', '.join(f'{markdown_text(target)} ({count})' for target, count in edition['targets'].items())}",
                "",
            ]
        )
        for item in edition["items"]:
            lines.append(
                f"- {item['position']}. {markdown_text(item['label'])}: {markdown_text(item['href'])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def exhibit_cue_item(item: dict[str, Any], position: int, rhythm_by_href: dict[str, dict[str, Any]]) -> dict[str, Any]:
    href = str(item.get("href") or "")
    rhythm = rhythm_by_href.get(href, {})
    duration = rhythm.get("duration_seconds")
    has_audio = rhythm.get("has_audio") is True
    return {
        "position": position,
        "queue_position": item.get("position"),
        "edition": str(item.get("edition") or ""),
        "work_title": str(item.get("work_title") or ""),
        "family": str(item.get("family") or ""),
        "kind": str(item.get("kind") or ""),
        "label": str(item.get("label") or ""),
        "phase": str(item.get("phase") or ""),
        "href": href,
        "duration_seconds": duration if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
        "has_audio": has_audio,
    }


def exhibit_cue_sheet(records: list[dict[str, Any]]) -> dict[str, Any]:
    programs = exhibit_programs_manifest(records)["programs"]
    rhythm = {item["href"]: item for item in rhythm_items(records) if item.get("href")}
    cue_programs: list[dict[str, Any]] = []
    for program in programs:
        program_items = program.get("items") if isinstance(program.get("items"), list) else []
        items = [
            exhibit_cue_item(item, position, rhythm)
            for position, item in enumerate(program_items, start=1)
            if isinstance(item, dict)
        ]
        durations = [
            float(item["duration_seconds"])
            for item in items
            if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
        ]
        cue: dict[str, Any] = {
            "id": program.get("id"),
            "label": program.get("label"),
            "scope": program.get("scope"),
            "href": program.get("href"),
            "item_count": len(items),
            "total_duration_seconds": round(sum(durations), 3),
            "audio_item_count": sum(1 for item in items if item.get("has_audio") is True),
            "silent_item_count": sum(1 for item in items if item.get("has_audio") is not True),
            "mode": program.get("mode"),
            "muted": program.get("muted") is True,
            "autoplay": program.get("autoplay") is True,
            "kiosk": program.get("kiosk") is True,
            "use": program.get("use"),
            "items": items,
        }
        for key in ("edition", "family", "edition_slugs", "families"):
            if key in program:
                cue[key] = program[key]
        cue_programs.append(cue)
    return {
        "schema": "triptych.exhibit-cue-sheet.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public exhibit programs and media facts",
        "entrypoint": "index.html",
        "exhibit_programs": "exhibit-programs.json",
        "release_player": "release-player.html",
        "rhythm_map": "rhythm-map.json",
        "sound_map": "sound-map.json",
        "playback_contract": "playback-contract.json",
        "exhibit_cue_sheet_doc": "exhibit-cue-sheet.md",
        "program_count": len(cue_programs),
        "total_public_items": len(rhythm),
        "programs": cue_programs,
        "operating_gates": [
            "Generated only from sanitized public exhibit programs and media facts.",
            "Use only local player URLs.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
            "Use as a digital-frame/gallery cue sheet, not as an ingestion manifest.",
        ],
    }


def exhibit_cue_sheet_markdown(records: list[dict[str, Any]]) -> str:
    cue = exhibit_cue_sheet(records)
    lines = [
        "# Triptych Exhibit Cue Sheet",
        "",
        "Generated from sanitized public exhibit programs and media facts. This is a public gallery/digital-frame cue sheet, not a private Photos, source, sample, or render-cache ledger.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Playback contract: playback-contract.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Snapshot",
        "",
        f"- Programs: {cue['program_count']}",
        f"- Public items: {cue['total_public_items']}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in cue["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    lines.extend(["", "## Programs", ""])
    for program in cue["programs"]:
        lines.extend(
            [
                f"### {markdown_text(program['label'])}",
                "",
                f"- Program: {program['id']}",
                f"- Scope: {markdown_text(program['scope'])}",
                f"- URL: {program['href']}",
                f"- Items: {program['item_count']}",
                f"- Runtime: {program['total_duration_seconds']} seconds",
                f"- Audio items: {program['audio_item_count']}",
                f"- Silent items: {program['silent_item_count']}",
                f"- Use: {markdown_text(program.get('use'))}",
                "",
            ]
        )
        for item in program["items"]:
            duration = item.get("duration_seconds")
            duration_text = f"{duration} seconds" if duration is not None else "unknown duration"
            audio = "audio" if item.get("has_audio") else "silent"
            lines.append(
                f"- {item['position']}. {markdown_text(item['edition'])} / {markdown_text(item['label'])}: {duration_text} / {audio} / {item['href']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def curatorial_note(work_title: str, family: str, composition: dict[str, Any]) -> str:
    score = str(composition.get("preview_label") or composition.get("style") or family or "triptych")
    if family == "signal_damage":
        return f"{work_title} treats compression, reversal, and signal damage as the visible surface; {score} is the public score."
    if family == "structural_recomposition":
        return f"{work_title} treats still-to-motion fragments as structural recomposition; {score} is the public score."
    return f"{work_title} is a public triptych program; {score} is the current score."


def curatorial_score(records: list[dict[str, Any]]) -> dict[str, Any]:
    atlas = composition_atlas(records)
    rhythm = rhythm_items(records)
    cue = exhibit_cue_sheet(records)
    atlas_by_slug = {
        edition["slug"]: edition
        for edition in atlas.get("editions", [])
        if isinstance(edition, dict) and isinstance(edition.get("slug"), str)
    }
    cue_by_id = {
        program["id"]: program
        for program in cue.get("programs", [])
        if isinstance(program, dict) and isinstance(program.get("id"), str)
    }
    rhythm_by_edition: dict[str, list[dict[str, Any]]] = {}
    for item in rhythm:
        edition = str(item.get("edition") or "")
        if edition:
            rhythm_by_edition.setdefault(edition, []).append(item)

    editions: list[dict[str, Any]] = []
    for record in records:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        atlas_edition = atlas_by_slug.get(slug, {})
        composition = atlas_edition.get("composition") if isinstance(atlas_edition.get("composition"), dict) else {}
        items = rhythm_by_edition.get(slug, [])
        durations = [
            float(item["duration_seconds"])
            for item in items
            if isinstance(item.get("duration_seconds"), (int, float)) and not isinstance(item.get("duration_seconds"), bool)
        ]
        audio_count = sum(1 for item in items if item.get("has_audio") is True)
        targets = sorted({target for item in items for target in item.get("targets", []) if isinstance(target, str) and target})
        program_id = f"edition-{slug}-kiosk-random-muted"
        program = cue_by_id.get(program_id, {})
        work_title = str(record.get("work_title") or record.get("title") or slug)
        family = str(record.get("family") or "")
        editions.append(
            {
                "slug": slug,
                "work_title": work_title,
                "family": family,
                "page": str(record.get("href") or ""),
                "player": player_query(edition=slug),
                "program": program_id,
                "program_url": player_query(program=program_id),
                "kiosk_url": str(program.get("href") or player_query(edition=slug, mode="random", muted="1", autoplay="1", kiosk="1")),
                "composition": {
                    key: composition.get(key)
                    for key in (
                        "style",
                        "material",
                        "preview_label",
                        "model",
                        "model_role",
                        "panel_role",
                        "observation",
                        "language",
                    )
                    if key in composition
                },
                "curatorial_note": curatorial_note(work_title, family, composition),
                "item_count": len(items),
                "total_duration_seconds": round(sum(durations), 3),
                "audio_item_count": audio_count,
                "silent_item_count": len(items) - audio_count,
                "targets": targets,
                "visual_sketch": atlas_edition.get("visual_sketch") if isinstance(atlas_edition.get("visual_sketch"), dict) else None,
                "items": [
                    {
                        "position": item.get("position"),
                        "kind": item.get("kind"),
                        "label": item.get("label"),
                        "phase": item.get("phase"),
                        "href": item.get("href"),
                        "duration_seconds": item.get("duration_seconds"),
                        "has_audio": item.get("has_audio") is True,
                        "targets": item.get("targets") if isinstance(item.get("targets"), list) else [],
                    }
                    for item in items
                ],
            }
        )

    families: list[dict[str, Any]] = []
    for family in sorted({edition["family"] for edition in editions if edition["family"]}):
        family_editions = [edition for edition in editions if edition["family"] == family]
        families.append(
            {
                "family": family,
                "label": family.replace("_", " "),
                "program": f"family-{family}-kiosk-random-muted",
                "program_url": player_query(program=f"family-{family}-kiosk-random-muted"),
                "edition_slugs": [edition["slug"] for edition in family_editions],
                "work_titles": [edition["work_title"] for edition in family_editions],
                "edition_count": len(family_editions),
                "item_count": sum(int(edition["item_count"]) for edition in family_editions),
                "total_duration_seconds": round(sum(float(edition["total_duration_seconds"]) for edition in family_editions), 3),
                "audio_item_count": sum(int(edition["audio_item_count"]) for edition in family_editions),
                "silent_item_count": sum(int(edition["silent_item_count"]) for edition in family_editions),
            }
        )

    durations = [float(edition["total_duration_seconds"]) for edition in editions]
    return {
        "schema": "triptych.curatorial-score.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public composition, rhythm, sound, release, and program facts",
        "entrypoint": "index.html",
        "public_manifest": "public-manifest.json",
        "release_player": "release-player.html",
        "composition_atlas": "composition-atlas.json",
        "rhythm_map": "rhythm-map.json",
        "sound_map": "sound-map.json",
        "release_matrix": "release-matrix.json",
        "exhibit_cue_sheet": "exhibit-cue-sheet.json",
        "curatorial_score_doc": "curatorial-score.md",
        "edition_count": len(editions),
        "family_count": len(families),
        "item_count": sum(int(edition["item_count"]) for edition in editions),
        "total_duration_seconds": round(sum(durations), 3),
        "audio_item_count": sum(int(edition["audio_item_count"]) for edition in editions),
        "silent_item_count": sum(int(edition["silent_item_count"]) for edition in editions),
        "families": families,
        "editions": editions,
        "product_shop_gate": {
            "status": "deferred",
            "reason": "Curatorial fit can be reviewed now; product objects remain unselected.",
        },
        "operating_gates": [
            "Generated only from sanitized public composition, rhythm, sound, release, and program facts.",
            "Every href must be local to the public static package.",
            "Use as a public curatorial score for gallery, portfolio, posting, and product review.",
            "Product/shop use stays deferred until a concrete product object is selected.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
        ],
    }


def curatorial_score_markdown(records: list[dict[str, Any]]) -> str:
    score = curatorial_score(records)
    lines = [
        "# Triptych Curatorial Score",
        "",
        "Generated from sanitized public composition, rhythm, sound, release, and program facts. This names the public works without exposing source albums, work receipts, samples, render caches, or local Photos paths.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Snapshot",
        "",
        f"- Editions: {score['edition_count']}",
        f"- Families: {score['family_count']}",
        f"- Public items: {score['item_count']}",
        f"- Total runtime: {score['total_duration_seconds']} seconds",
        f"- Audio items: {score['audio_item_count']}",
        f"- Silent items: {score['silent_item_count']}",
        f"- Product/shop gate: {score['product_shop_gate']['status']}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in score["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    lines.extend(["", "## Families", ""])
    for family in score["families"]:
        lines.extend(
            [
                f"### {markdown_text(family['label'])}",
                "",
                f"- Program: {family['program']}",
                f"- Program URL: {family['program_url']}",
                f"- Editions: {', '.join(family['edition_slugs'])}",
                f"- Runtime: {family['total_duration_seconds']} seconds",
                f"- Audio items: {family['audio_item_count']}",
                f"- Silent items: {family['silent_item_count']}",
                "",
            ]
        )
    lines.extend(["## Editions", ""])
    for edition in score["editions"]:
        composition = edition.get("composition") if isinstance(edition.get("composition"), dict) else {}
        language = composition.get("language") if isinstance(composition.get("language"), list) else []
        lines.extend(
            [
                f"### {markdown_text(edition['work_title'])}",
                "",
                f"- Edition: {edition['slug']}",
                f"- Family: {edition['family']}",
                f"- Page: {edition['page']}",
                f"- Player: {edition['player']}",
                f"- Program: {edition['program']}",
                f"- Program URL: {edition['program_url']}",
                f"- Kiosk URL: {edition['kiosk_url']}",
                f"- Runtime: {edition['total_duration_seconds']} seconds",
                f"- Audio items: {edition['audio_item_count']}",
                f"- Silent items: {edition['silent_item_count']}",
                f"- Targets: {', '.join(edition['targets'])}",
                f"- Note: {markdown_text(edition['curatorial_note'])}",
                f"- Style: {markdown_text(composition.get('style') or 'unspecified')}",
                f"- Material: {markdown_text(composition.get('material') or 'public edition material')}",
                f"- Score: {markdown_text(composition.get('preview_label') or 'none')}",
            ]
        )
        if composition.get("model"):
            lines.append(f"- Model: {markdown_text(composition.get('model'))}")
        if composition.get("panel_role"):
            lines.append(f"- Panel role: {markdown_text(composition.get('panel_role'))}")
        if language:
            lines.append(f"- Language: {', '.join(markdown_text(item) for item in language)}")
        sketch = edition.get("visual_sketch") if isinstance(edition.get("visual_sketch"), dict) else None
        if sketch:
            lines.append(f"- Visual sketch: {sketch.get('href')}")
        lines.append("")
        for item in edition["items"]:
            audio = "audio" if item["has_audio"] else "silent"
            lines.append(
                f"- {item['position']}. {markdown_text(item['label'])}: {item['duration_seconds']} seconds / {audio} / {item['href']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def program_review_url(program: dict[str, Any], seed: str) -> str:
    params: dict[str, str] = {
        "mode": "random",
        "muted": "0",
        "volume": "0.35",
        "rate": "0.75",
        "seed": seed,
    }
    if program.get("scope") == "edition" and isinstance(program.get("edition"), str):
        params = {"edition": program["edition"], **params}
    elif program.get("scope") == "family" and isinstance(program.get("family"), str):
        params = {"family": program["family"], **params}
    return player_query(**params)


def living_rotation_sets(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rotations: list[dict[str, Any]] = []
    for profile in LIVING_ROTATION_PROFILES:
        rotation_slots: list[dict[str, Any]] = []
        for slot in slots:
            seed = f"{profile['id']}-{slot['slot']:02d}-{slot['program']}"
            rotation_slots.append(
                {
                    "slot": slot["slot"],
                    "program": slot["program"],
                    "seed": seed,
                    "href": player_query(
                        program=slot["program"],
                        mode="random",
                        muted="0",
                        volume=profile["volume"],
                        rate=profile["rate"],
                        seed=seed,
                    ),
                }
            )
        rotations.append(
            {
                "id": profile["id"],
                "label": profile["label"],
                "volume": profile["volume"],
                "rate": profile["rate"],
                "note": profile["note"],
                "media_generation": "none",
                "slots": rotation_slots,
            }
        )
    return rotations


def living_loop(records: list[dict[str, Any]]) -> dict[str, Any]:
    cue = exhibit_cue_sheet(records)
    score = curatorial_score(records)
    slots: list[dict[str, Any]] = []
    for index, program in enumerate(cue.get("programs", []), start=1):
        if not isinstance(program, dict) or not isinstance(program.get("id"), str):
            continue
        program_id = program["id"]
        seed = f"living-{index:02d}-{program_id}"
        slot: dict[str, Any] = {
            "slot": index,
            "slot_id": f"slot-{index:02d}-{program_id}",
            "program": program_id,
            "label": str(program.get("label") or program_id),
            "scope": str(program.get("scope") or ""),
            "seed": seed,
            "program_url": player_query(program=program_id),
            "seeded_kiosk_url": player_query(program=program_id, seed=seed),
            "quiet_review_url": program_review_url(program, seed),
            "item_count": program.get("item_count"),
            "total_duration_seconds": program.get("total_duration_seconds"),
            "audio_item_count": program.get("audio_item_count"),
            "silent_item_count": program.get("silent_item_count"),
            "refresh_note": "Change only the seed or slot URL; no media regeneration is required.",
        }
        for key in ("edition", "family", "edition_slugs", "families"):
            if key in program:
                slot[key] = program[key]
        slots.append(slot)
    return {
        "schema": "triptych.living-loop.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public exhibit programs and curatorial score",
        "entrypoint": "index.html",
        "release_player": "release-player.html",
        "exhibit_programs": "exhibit-programs.json",
        "exhibit_cue_sheet": "exhibit-cue-sheet.json",
        "curatorial_score": "curatorial-score.json",
        "playback_contract": "playback-contract.json",
        "living_loop_doc": "living-loop.md",
        "program_count": cue.get("program_count"),
        "slot_count": len(slots),
        "edition_count": score.get("edition_count"),
        "family_count": score.get("family_count"),
        "item_count": score.get("item_count"),
        "total_duration_seconds": score.get("total_duration_seconds"),
        "default_seed": "living-01-all-kiosk-random-muted",
        "default_url": player_query(program="all-kiosk-random-muted", seed="living-01-all-kiosk-random-muted"),
        "seed_policy": {
            "mode": "static deterministic URLs",
            "effect": "seed changes random playback order only",
            "media_generation": "none",
            "hosted_surface": "rotate slot URLs or seed text to make the loop feel newly arranged",
        },
        "slots": slots,
        "rotation_sets": living_rotation_sets(slots),
        "operating_gates": [
            "Generated only from sanitized public exhibit programs and curatorial score facts.",
            "Use only local player URLs with seed text.",
            "Seed changes affect browser playback order only; no media generation occurs.",
            "Rotation sets are text-addressable URL recipes only.",
            "No source library, work receipt, sample, render-cache, or local Photos paths.",
            "Use as a lightweight hosted/digital-frame living loop contract.",
        ],
    }


def living_loop_markdown(records: list[dict[str, Any]]) -> str:
    loop = living_loop(records)
    lines = [
        "# Triptych Living Loop",
        "",
        "Generated from sanitized public exhibit programs and curatorial score facts. This is the lightweight hosted-loop contract: rotate seeded player URLs to keep the surface alive without regenerating media or touching source libraries.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Snapshot",
        "",
        f"- Programs: {loop['program_count']}",
        f"- Slots: {loop['slot_count']}",
        f"- Editions: {loop['edition_count']}",
        f"- Families: {loop['family_count']}",
        f"- Public items: {loop['item_count']}",
        f"- Total runtime: {loop['total_duration_seconds']} seconds",
        f"- Default URL: {loop['default_url']}",
        f"- Seed policy: {loop['seed_policy']['effect']}",
        f"- Media generation: {loop['seed_policy']['media_generation']}",
        f"- Rotation sets: {len(loop['rotation_sets'])}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in loop["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    lines.extend(["", "## Rotation Sets", ""])
    for rotation in loop["rotation_sets"]:
        lines.extend(
            [
                f"### {markdown_text(rotation['label'])}",
                "",
                f"- ID: {rotation['id']}",
                f"- Volume: {rotation['volume']}",
                f"- Rate: {rotation['rate']}",
                f"- Media generation: {rotation['media_generation']}",
                f"- Note: {markdown_text(rotation['note'])}",
                "",
            ]
        )
        for entry in rotation["slots"]:
            lines.append(
                f"- Slot {entry['slot']:02d}: {entry['program']} / {entry['seed']} / {entry['href']}"
            )
        lines.append("")
    lines.extend(["", "## Slots", ""])
    for slot in loop["slots"]:
        lines.extend(
            [
                f"### {slot['slot']:02d}. {markdown_text(slot['label'])}",
                "",
                f"- Slot: {slot['slot_id']}",
                f"- Program: {slot['program']}",
                f"- Scope: {markdown_text(slot['scope'])}",
                f"- Seed: {slot['seed']}",
                f"- Program URL: {slot['program_url']}",
                f"- Seeded kiosk URL: {slot['seeded_kiosk_url']}",
                f"- Quiet review URL: {slot['quiet_review_url']}",
                f"- Items: {slot['item_count']}",
                f"- Runtime: {slot['total_duration_seconds']} seconds",
                f"- Audio items: {slot['audio_item_count']}",
                f"- Silent items: {slot['silent_item_count']}",
                f"- Refresh: {markdown_text(slot['refresh_note'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def player_presets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    presets: list[dict[str, Any]] = [
        {
            "id": "all",
            "label": "All releases",
            "scope": "all",
            "mode": "sequential",
            "href": player_query(),
        },
        {
            "id": "all-random-muted",
            "label": "All random muted",
            "scope": "all",
            "mode": "random",
            "muted": True,
            "href": player_query(mode="random", muted="1"),
        },
        {
            "id": "kiosk-random-muted",
            "label": "Kiosk random muted",
            "scope": "all",
            "mode": "random",
            "muted": True,
            "autoplay": True,
            "kiosk": True,
            "href": player_query(mode="random", muted="1", autoplay="1", kiosk="1"),
        },
    ]

    for record in records:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        presets.append(
            {
                "id": f"edition-{slug}",
                "label": str(record.get("work_title") or record.get("title") or slug),
                "scope": "edition",
                "edition": slug,
                "mode": "sequential",
                "href": player_query(edition=slug),
            }
        )

    families = sorted({str(record.get("family") or "") for record in records if record.get("family")})
    for family in families:
        presets.append(
            {
                "id": f"family-{family}",
                "label": family.replace("_", " "),
                "scope": "family",
                "family": family,
                "mode": "random",
                "muted": True,
                "href": player_query(family=family, mode="random", muted="1"),
            }
        )

    return presets


def player_presets_markdown(records: list[dict[str, Any]]) -> str:
    presets = player_presets(records)
    lines = [
        "# Triptych Player Presets",
        "",
        "Generated from sanitized public release data. These URLs address the static release player without exposing source albums, work receipts, samples, or local Photos paths.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Operating Gates",
        "",
        "- Use only local player URLs listed below.",
        "- Treat muted random family loops as review modes.",
        "- Use the kiosk preset for chromeless digital-frame/gallery playback.",
        "- Add bounded `volume=0..1` and `rate=0.25..2` query parameters for quiet or slowed playback.",
        "- Add `seed=<text>` to random URLs when a loop should feel alive but remain reproducible.",
        "- Keep product/shop use deferred until a product object is explicitly chosen.",
        "",
        "## Playback Controls",
        "",
        f"- Quiet slow kiosk example: {player_query(mode='random', muted='0', volume='0.35', rate='0.75', autoplay='1', kiosk='1')}",
        f"- Seeded kiosk example: {player_query(mode='random', muted='1', autoplay='1', kiosk='1', seed='ballerina-whole')}",
        "",
        "## Presets",
        "",
    ]
    for preset in presets:
        label = markdown_text(preset.get("label"))
        href = str(preset.get("href") or "")
        scope = markdown_text(preset.get("scope"))
        mode = markdown_text(preset.get("mode"))
        details = []
        if preset.get("edition"):
            details.append(f"edition {markdown_text(preset.get('edition'))}")
        if preset.get("family"):
            details.append(f"family {markdown_text(preset.get('family'))}")
        if preset.get("muted"):
            details.append("muted")
        detail_text = ", ".join(details) if details else "all public releases"
        lines.extend(
            [
                f"### {label}",
                "",
                f"- URL: {href}",
                f"- Scope: {scope}",
                f"- Mode: {mode}",
                f"- Detail: {detail_text}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def release_copy_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Triptych Release Copy",
        "",
        "Generated from sanitized public release data. Source libraries, work receipts, and local media paths are intentionally absent.",
        "",
        "- Edition index: index.html",
        "- Release board: release-board.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release queue: release-queue.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "",
    ]
    for record in records:
        title = markdown_text(record.get("work_title") or record.get("title") or record.get("slug"))
        slug = markdown_text(record.get("slug"))
        family = markdown_text(record.get("family"))
        lines.extend([f"## {title}", "", f"- Edition: {slug}", f"- Family: {family}", f"- Page: {record.get('href')}", ""])
        for kind, item in release_items(record):
            label = markdown_text(item.get("label") or item.get("name") or kind)
            href = str(item.get("href") or "")
            facts = media_fact_line(item.get("media"))
            lines.extend(
                [
                    f"### {kind}: {label}",
                    "",
                    f"- Media: {href}",
                    f"- Facts: {facts}",
                    f"- Caption starter: {caption_starter(record, item, kind)}",
                    f"- Tags: {hashtag_line(record)}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def platform_targets(item: dict[str, Any], kind: str) -> list[str]:
    name = str(item.get("name") or "")
    if kind == "Sketch":
        return ["GitHub/portfolio context", "process post"]
    if name == "story-triptych":
        return ["Instagram Story", "YouTube Shorts draft", "portfolio teaser"]
    if name.startswith("reel-"):
        return ["Instagram Reel", "YouTube Shorts draft", "panel excerpt"]
    return ["portfolio teaser"]


def platform_plan_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Triptych Platform Plan",
        "",
        "Generated from sanitized public release data. It maps public outputs to posting surfaces without selecting a permanent product owner.",
        "",
        "- Edition index: index.html",
        "- Release board: release-board.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Operating Gates",
        "",
        "- Post only public Story/Reel/sketch outputs listed below.",
        "- Keep source albums, work receipts, samples, and local Photos paths out of public captions.",
        "- Treat product/shop use as a later review gate until a product object is chosen.",
        "",
    ]
    for record in records:
        title = markdown_text(record.get("work_title") or record.get("title") or record.get("slug"))
        slug = markdown_text(record.get("slug"))
        lines.extend([f"## {title}", "", f"- Edition: {slug}", f"- Page: {record.get('href')}", ""])
        for kind, item in release_items(record):
            label = markdown_text(item.get("label") or item.get("name") or kind)
            href = str(item.get("href") or "")
            targets = ", ".join(platform_targets(item, kind))
            facts = media_fact_line(item.get("media"))
            shop_state = "defer product/shop use until explicit product review"
            lines.extend(
                [
                    f"### {kind}: {label}",
                    "",
                    f"- Media: {href}",
                    f"- Targets: {targets}",
                    f"- Facts: {facts}",
                    f"- Product/shop gate: {shop_state}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def release_queue_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Triptych Release Queue",
        "",
        "Generated from sanitized public release data. This is an ordered posting queue, not a calendar; dates stay outside the package until posting is actually scheduled.",
        "",
        "- Edition index: index.html",
        "- Release board: release-board.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit loop: exhibit-loop.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Release matrix: release-matrix.md",
        "- Release matrix JSON: release-matrix.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Operating Gates",
        "",
        "- Post from public media links only.",
        "- Keep source albums, local Photos paths, work receipts, samples, and private notes out of captions.",
        "- Product/shop gate: defer mugs, shirts, prints, and other product uses until the exact product object is reviewed.",
        "",
        "## Queue",
        "",
    ]
    for index, entry in enumerate(release_sequence(records), start=1):
        record = entry["record"]
        item = entry["item"]
        kind = str(entry["kind"])
        phase = markdown_text(entry["phase"])
        title = markdown_text(record.get("work_title") or record.get("title") or record.get("slug"))
        slug = markdown_text(record.get("slug"))
        family = markdown_text(record.get("family"))
        label = markdown_text(item.get("label") or item.get("name") or kind)
        href = str(item.get("href") or "")
        targets = ", ".join(platform_targets(item, kind))
        facts = media_fact_line(item.get("media"))
        lines.extend(
            [
                f"### {index:02d}. {title} / {label}",
                "",
                f"- Edition: {slug}",
                f"- Family: {family}",
                f"- Phase: {phase}",
                f"- Media: {href}",
                f"- Targets: {targets}",
                f"- Facts: {facts}",
                "- Caption deck: release-copy.md",
                "- Board card: release-board.html",
                "- Product/shop gate: defer until explicit product review",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def exhibit_loop_markdown(records: list[dict[str, Any]]) -> str:
    total_clips = sum(int(record.get("clips") or 0) for record in records)
    total_posts = sum(len(record.get("post_exports", [])) for record in records)
    total_sketches = sum(1 for record in records if record.get("sketch_href"))
    families = sorted({str(record.get("family") or "") for record in records if record.get("family")})
    family_names = ", ".join(markdown_text(family).replace("_", " ") for family in families) or "none"
    lines = [
        "# Triptych Exhibit Loop",
        "",
        "Generated from sanitized public release data. This is the lightweight gallery/digital-frame handoff for the verified static package, not a private Photos or render receipt.",
        "",
        "- Edition index: index.html",
        "- Release player: release-player.html",
        "- Player presets: player-presets.md",
        "- Release board: release-board.html",
        "- Release queue: release-queue.md",
        "- Release copy: release-copy.md",
        "- Platform plan: platform-plan.md",
        "- Exhibit programs: exhibit-programs.json",
        "- Exhibit cue sheet: exhibit-cue-sheet.md",
        "- Exhibit cue sheet JSON: exhibit-cue-sheet.json",
        "- Curatorial score: curatorial-score.md",
        "- Curatorial score JSON: curatorial-score.json",
        "- Living loop: living-loop.md",
        "- Living loop JSON: living-loop.json",
        "- Playback contract: playback-contract.json",
        "- Composition atlas: composition-atlas.md",
        "- Composition atlas JSON: composition-atlas.json",
        "- Rhythm map: rhythm-map.md",
        "- Rhythm map JSON: rhythm-map.json",
        "- Sound map: sound-map.md",
        "- Sound map JSON: sound-map.json",
        "- Public manifest: public-manifest.json",
        "",
        "## Operating Gates",
        "",
        "- Open only local player URLs listed below.",
        "- Use kiosk URLs for chromeless digital-frame/gallery loops.",
        "- Keep source albums, work receipts, samples, renders, and local Photos paths out of public hosting packages.",
        "- Rebuild with `python3 build_site_index.py`, package with `python3 package_public_site.py`, and verify transfers with `python3 verify_package.py`.",
        "- Keep product/shop use deferred until a concrete product object is reviewed.",
        "",
        "## Package Snapshot",
        "",
        f"- Public editions: {len(records)}",
        f"- Public clips: {total_clips}",
        f"- Published Story/Reel posts: {total_posts}",
        f"- Visual sketches: {total_sketches}",
        f"- Families: {family_names}",
        "",
        "## Kiosk Programs",
        "",
        "### Full Corpus Shuffle",
        "",
        "- Program: all-kiosk-random-muted",
        "- Program URL: release-player.html?program=all-kiosk-random-muted",
        f"- URL: {player_query(mode='random', muted='1', autoplay='1', kiosk='1')}",
        "- Use: unattended all-release gallery loop.",
        "- Audio: muted by default; unmute only after room/context review.",
        "",
    ]
    if families:
        lines.extend(["## Family Programs", ""])
    for family in families:
        family_records = [record for record in records if record.get("family") == family]
        family_label = markdown_text(family).replace("_", " ")
        titles = ", ".join(
            markdown_text(record.get("work_title") or record.get("title") or record.get("slug"))
            for record in family_records
        )
        lines.extend(
            [
                f"### {family_label}",
                "",
                f"- Program: family-{family}-kiosk-random-muted",
                f"- Program URL: release-player.html?program=family-{family}-kiosk-random-muted",
                f"- URL: {player_query(family=family, mode='random', muted='1', autoplay='1', kiosk='1')}",
                f"- Editions: {titles}",
                "- Use: family-specific gallery loop.",
                "",
            ]
        )
    lines.extend(["## Edition Programs", ""])
    for record in records:
        slug = str(record.get("slug") or "")
        title = markdown_text(record.get("work_title") or record.get("title") or slug)
        family = markdown_text(record.get("family") or "edition").replace("_", " ")
        page = str(record.get("href") or "")
        preset_links = [
            preset_href(page, str(preset.get("id") or ""))
            for preset in record.get("control_presets", [])
            if isinstance(preset, dict) and preset.get("id")
        ]
        lines.extend(
            [
                f"### {title}",
                "",
                f"- Edition: {markdown_text(slug)}",
                f"- Family: {family}",
                f"- Page: {page}",
                f"- Program: edition-{slug}-kiosk-random-muted",
                f"- Program URL: release-player.html?program=edition-{slug}-kiosk-random-muted",
                f"- Kiosk URL: {player_query(edition=slug, mode='random', muted='1', autoplay='1', kiosk='1')}",
                f"- Public presets: {', '.join(preset_links) if preset_links else 'none'}",
                "- Use: single-work loop for review, installation, or posting context.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def program_item_count(records: list[dict[str, Any]], *, edition: str = "", family: str = "") -> int:
    count = 0
    for entry in release_sequence(records):
        record = entry["record"]
        if edition and record.get("slug") != edition:
            continue
        if family and record.get("family") != family:
            continue
        count += 1
    return count


def program_playlist_items(records: list[dict[str, Any]], *, edition: str = "", family: str = "") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for position, entry in enumerate(release_sequence(records), start=1):
        record = entry["record"]
        if edition and record.get("slug") != edition:
            continue
        if family and record.get("family") != family:
            continue
        items.append(player_item(entry, position))
    return items


def exhibit_programs_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    families = sorted({str(record.get("family") or "") for record in records if record.get("family")})
    editions = [str(record.get("slug") or "") for record in records if record.get("slug")]
    programs: list[dict[str, Any]] = [
        {
            "id": "all-kiosk-random-muted",
            "label": "All public releases kiosk shuffle",
            "scope": "all",
            "mode": "random",
            "muted": True,
            "autoplay": True,
            "kiosk": True,
            "href": player_query(mode="random", muted="1", autoplay="1", kiosk="1"),
            "edition_slugs": editions,
            "families": families,
            "item_count": program_item_count(records),
            "items": program_playlist_items(records),
            "use": "unattended all-release gallery loop",
        }
    ]
    for family in families:
        family_records = [record for record in records if record.get("family") == family]
        programs.append(
            {
                "id": f"family-{family}-kiosk-random-muted",
                "label": f"{family.replace('_', ' ')} kiosk shuffle",
                "scope": "family",
                "family": family,
                "mode": "random",
                "muted": True,
                "autoplay": True,
                "kiosk": True,
                "href": player_query(family=family, mode="random", muted="1", autoplay="1", kiosk="1"),
                "edition_slugs": [str(record.get("slug") or "") for record in family_records if record.get("slug")],
                "families": [family],
                "item_count": program_item_count(records, family=family),
                "items": program_playlist_items(records, family=family),
                "use": "family-specific gallery loop",
            }
        )
    for record in records:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        family = str(record.get("family") or "")
        programs.append(
            {
                "id": f"edition-{slug}-kiosk-random-muted",
                "label": f"{record.get('work_title') or record.get('title') or slug} kiosk shuffle",
                "scope": "edition",
                "edition": slug,
                "family": family,
                "mode": "random",
                "muted": True,
                "autoplay": True,
                "kiosk": True,
                "href": player_query(edition=slug, mode="random", muted="1", autoplay="1", kiosk="1"),
                "edition_slugs": [slug],
                "families": [family] if family else [],
                "item_count": program_item_count(records, edition=slug),
                "items": program_playlist_items(records, edition=slug),
                "use": "single-work loop for review, installation, or posting context",
            }
        )
    return {
        "schema": "triptych.exhibit-programs.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "derived_from": "sanitized public flash-copy receipts",
        "entrypoint": "index.html",
        "release_player": "release-player.html",
        "exhibit_loop": "exhibit-loop.md",
        "public_manifest": "public-manifest.json",
        "playback_contract": "playback-contract.json",
        "program_count": len(programs),
        "programs": programs,
        "operating_gates": [
            "Use only local player URLs.",
            "Keep source albums, work receipts, samples, renders, and local Photos paths out of public hosting packages.",
            "Use muted kiosk programs as the default for unattended gallery playback.",
            "Run verify_public_site.py before sharing and verify_package.py after package transfer.",
        ],
    }


def public_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    editions: list[dict[str, Any]] = []
    total_clips = 0
    total_video_proxies = 0
    total_audio_proxies = 0
    total_post_exports = 0
    total_visual_sketches = 0
    families: set[str] = set()

    for record in records:
        post_exports = [
            {
                "name": export["name"],
                "label": export["label"],
                "kind": export_kind(str(export["name"]), None),
                "href": export["href"],
                "media": export.get("media"),
            }
            for export in record.get("post_exports", [])
        ]
        control_presets = [
            {
                "id": preset["id"],
                "label": preset["label"],
                "default": preset.get("default") is True,
                "href": preset_href(record["href"], preset["id"]),
            }
            for preset in record.get("control_presets", [])
        ]
        sketch = None
        if record.get("sketch_href"):
            sketch = {
                "name": "visual-sketch",
                "label": "Visual sketch",
                "kind": "visual-sketch",
                "href": record["sketch_href"],
                "media": record.get("sketch_media"),
            }
            total_visual_sketches += 1
        family = str(record.get("family") or "")
        if family:
            families.add(family)
        total_clips += int(record["clips"])
        total_video_proxies += int(record["video_proxies"])
        total_audio_proxies += int(record["audio_proxies"])
        total_post_exports += len(post_exports)
        editions.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "work_title": record["work_title"],
                "family": family,
                "page": record["href"],
                "preview_src": record.get("preview_src"),
                "arrangement_score": record.get("arrangement_score", {}),
                "counts": {
                    "clips": int(record["clips"]),
                    "video_proxies": int(record["video_proxies"]),
                    "audio_proxies": int(record["audio_proxies"]),
                    "exports": int(record["exports"]),
                    "post_exports": len(post_exports),
                    "visual_sketches": 1 if sketch else 0,
                },
                "control_presets": control_presets,
                "post_pack": record.get("post_pack"),
                "post_exports": post_exports,
                "visual_sketch": sketch,
            }
        )

    queue = []
    for position, entry in enumerate(release_sequence(records), start=1):
        record = entry["record"]
        item = entry["item"]
        kind = str(entry["kind"])
        queue.append(
            {
                "position": position,
                "edition": record["slug"],
                "work_title": record["work_title"],
                "family": record.get("family") or "",
                "kind": kind,
                "name": str(item.get("name") or ""),
                "label": str(item.get("label") or item.get("name") or kind),
                "phase": entry["phase"],
                "href": str(item.get("href") or ""),
                "targets": platform_targets(item, kind),
                "media": item.get("media"),
            }
        )

    return {
        "schema": "triptych.public-release-manifest.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "entrypoint": "index.html",
        "release_player": "release-player.html",
        "exhibit_loop": "exhibit-loop.md",
        "exhibit_programs": "exhibit-programs.json",
        "playback_contract": "playback-contract.json",
        "composition_atlas": "composition-atlas.json",
        "composition_atlas_doc": "composition-atlas.md",
        "rhythm_map": "rhythm-map.json",
        "rhythm_map_doc": "rhythm-map.md",
        "sound_map": "sound-map.json",
        "sound_map_doc": "sound-map.md",
        "release_matrix": "release-matrix.json",
        "release_matrix_doc": "release-matrix.md",
        "exhibit_cue_sheet": "exhibit-cue-sheet.json",
        "exhibit_cue_sheet_doc": "exhibit-cue-sheet.md",
        "curatorial_score": "curatorial-score.json",
        "curatorial_score_doc": "curatorial-score.md",
        "living_loop": "living-loop.json",
        "living_loop_doc": "living-loop.md",
        "player_presets": player_presets(records),
        "release_queue": queue,
        "edition_count": len(editions),
        "families": sorted(families),
        "totals": {
            "clips": total_clips,
            "video_proxies": total_video_proxies,
            "audio_proxies": total_audio_proxies,
            "post_exports": total_post_exports,
            "visual_sketches": total_visual_sketches,
        },
        "editions": editions,
        "notes": [
            "Generated only from sanitized public flash-copy receipts.",
            "Source libraries, work receipts, samples, and local render paths are intentionally absent.",
        ],
    }


def edition_card(record: dict[str, Any]) -> str:
    title = html.escape(record["title"])
    slug = html.escape(record["slug"])
    family = html.escape(record.get("family") or "edition")
    href = html.escape(record["href"])
    arrangement = record.get("arrangement_score") if isinstance(record.get("arrangement_score"), dict) else {}
    preview = ""
    if record.get("preview_src"):
        src = html.escape(record["preview_src"])
        preview = f'<video src="{src}" muted playsinline autoplay loop></video>'
    else:
        preview = '<div class="empty-preview"></div>'

    sketch = ""
    if record.get("sketch_href"):
        sketch = f'<a class="chip" href="{html.escape(record["sketch_href"])}">Visual sketch</a>'

    post_pack = ""
    if isinstance(record.get("post_pack"), dict):
        profile = html.escape(str(record["post_pack"].get("profile", "pack")))
        pack = html.escape(str(record["post_pack"].get("pack", "exports")))
        post_pack = f'<p class="post-pack">Post pack: {profile} / {pack}</p>'

    post_links = ""
    post_exports = record.get("post_exports") or []
    if post_exports:
        links = []
        for export in post_exports:
            links.append(
                f'<a class="chip post-chip" href="{html.escape(export["href"])}">'
                f'{html.escape(export["label"])}</a>'
            )
        post_links = '<div class="post-links">' + "".join(links) + "</div>"

    preset_links = ""
    control_presets = record.get("control_presets") or []
    if control_presets:
        links = []
        for preset in control_presets:
            preset_id = str(preset.get("id", ""))
            if not preset_id:
                continue
            label = html.escape(str(preset.get("label") or preset_id))
            preset_url = html.escape(preset_href(record["href"], preset_id))
            classes = "chip preset-chip"
            if preset.get("default") is True:
                classes += " is-default"
            links.append(f'<a class="{classes}" href="{preset_url}">{label}</a>')
        if links:
            preset_links = '<div class="preset-links">' + "".join(links) + "</div>"

    metrics = "".join(
        [
            metric("clips", record["clips"]),
            metric("video proxies", record["video_proxies"]),
            metric("audio proxies", record["audio_proxies"]),
        ]
    )
    score_line = ""
    score_label = arrangement.get("preview_label") or arrangement.get("family")
    if isinstance(score_label, str) and score_label:
        score_line = f'<p class="score-line">Score: {html.escape(score_label)}</p>'
    return f"""
      <article class="edition">
        <a class="preview" href="{href}" aria-label="Open {title}">
          {preview}
        </a>
        <div class="edition-body">
          <div>
            <p class="slug">{slug} / {family}</p>
            <h2>{title}</h2>
          </div>
          <div class="metrics">{metrics}</div>
          {score_line}
          {post_pack}
          <div class="links">
            <a class="button" href="{href}">Open edition</a>
            {sketch}
          </div>
          {preset_links}
          {post_links}
        </div>
      </article>
    """


def index_html(records: list[dict[str, Any]]) -> str:
    data = json.dumps(
        {
            "schema": "triptych.site-index.v1",
            "editions": [
                {
                    key: record[key]
                    for key in (
                        "slug",
                        "title",
                        "work_title",
                        "family",
                        "href",
                        "clips",
                        "video_proxies",
                        "audio_proxies",
                        "control_presets",
                    )
                }
                | {
                    "arrangement_score": record.get("arrangement_score", {}),
                    "post_pack": record.get("post_pack"),
                    "post_exports": record.get("post_exports", []),
                }
                for record in records
            ],
        }
    ).replace("</", "<\\/")
    cards = "\n".join(edition_card(record) for record in records)
    empty = ""
    if not records:
        empty = '<p class="empty">No public edition receipts found yet.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Video Canon</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070706;
      --panel: #11100e;
      --ink: #f6f1e8;
      --muted: #b8afa2;
      --line: rgba(246, 241, 232, 0.16);
      --rust: #c35d45;
      --blue: #7092a0;
      --green: #7d8c68;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1180px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 24px 0 34px;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      gap: 18px;
      min-height: 22vh;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{
      font-size: 28px;
      line-height: 1;
      font-weight: 720;
    }}
    .lede {{
      max-width: 66ch;
      color: var(--muted);
      margin-top: 8px;
      line-height: 1.42;
    }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .count {{
      display: grid;
      place-items: center;
      width: 70px;
      height: 70px;
      border: 1px solid var(--line);
      background: #0c0c0b;
    }}
    .count strong {{ font-size: 24px; }}
    .count small {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      padding-top: 18px;
    }}
    .edition {{
      min-width: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      border: 1px solid var(--line);
      background: var(--panel);
    }}
    .preview {{
      display: block;
      aspect-ratio: 9 / 16;
      background: #020202;
      overflow: hidden;
    }}
    .preview video,
    .empty-preview {{
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }}
    .empty-preview {{
      background:
        linear-gradient(90deg, rgba(195, 93, 69, 0.28), transparent 34%),
        linear-gradient(180deg, rgba(112, 146, 160, 0.24), transparent 42%),
        #030303;
    }}
    .edition-body {{
      display: grid;
      gap: 12px;
      padding: 12px;
    }}
    .slug {{
      color: var(--blue);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    h2 {{
      margin-top: 4px;
      font-size: 18px;
      line-height: 1.12;
      font-weight: 680;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}
    .metric {{
      display: grid;
      gap: 2px;
      border-top: 1px solid var(--line);
      padding-top: 8px;
    }}
    .metric strong {{ font-size: 18px; }}
    .metric small {{ color: var(--muted); font-size: 11px; }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .post-pack {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.3;
    }}
    .score-line {{
      color: var(--green);
      font-size: 12px;
      line-height: 1.3;
    }}
    .post-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding-top: 2px;
    }}
    .preset-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding-top: 2px;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .button,
    .chip {{
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid currentColor;
      padding: 7px 10px;
    }}
    .button {{ color: var(--rust); }}
    .chip {{ color: var(--green); }}
    .post-chip {{ color: var(--blue); }}
    .preset-chip {{ color: var(--ink); border-color: var(--line); }}
    .preset-chip.is-default {{ color: var(--rust); }}
    .empty {{
      color: var(--muted);
      padding-top: 20px;
    }}
    @media (max-width: 680px) {{
      main {{ width: min(100vw - 18px, 520px); padding-top: 12px; }}
      header {{ grid-template-columns: 1fr; min-height: auto; }}
      .count {{ width: 100%; height: 48px; grid-auto-flow: column; gap: 8px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Video Canon</h1>
        <p class="lede">A lightweight index of generated canon editions, visual sketches, and disposable web proxies. Source libraries stay private; these pages use only selected public flash-copy receipts.</p>
        <nav class="nav" aria-label="Release surfaces">
          <a class="chip" href="release-board.html">Release board</a>
          <a class="chip" href="release-player.html">Release player</a>
          <a class="chip" href="player-presets.md">Player presets</a>
          <a class="chip" href="release-queue.md">Release queue</a>
          <a class="chip" href="exhibit-loop.md">Exhibit loop</a>
          <a class="chip" href="exhibit-programs.json">Exhibit programs</a>
          <a class="chip" href="exhibit-cue-sheet.md">Exhibit cue sheet</a>
          <a class="chip" href="exhibit-cue-sheet.json">Cue JSON</a>
          <a class="chip" href="curatorial-score.md">Curatorial score</a>
          <a class="chip" href="curatorial-score.json">Score JSON</a>
          <a class="chip" href="living-loop.md">Living loop</a>
          <a class="chip" href="living-loop.json">Loop JSON</a>
          <a class="chip" href="platform-plan.md">Platform plan</a>
          <a class="chip" href="playback-contract.json">Playback contract</a>
          <a class="chip" href="composition-atlas.md">Composition atlas</a>
          <a class="chip" href="composition-atlas.json">Atlas JSON</a>
          <a class="chip" href="rhythm-map.md">Rhythm map</a>
          <a class="chip" href="rhythm-map.json">Rhythm JSON</a>
          <a class="chip" href="sound-map.md">Sound map</a>
          <a class="chip" href="sound-map.json">Sound JSON</a>
          <a class="chip" href="release-matrix.md">Release matrix</a>
          <a class="chip" href="release-matrix.json">Matrix JSON</a>
          <a class="chip" href="public-manifest.json">Public manifest</a>
          <a class="chip" href="release-copy.md">Release copy</a>
        </nav>
      </div>
      <div class="count"><strong>{len(records)}</strong><small>editions</small></div>
    </header>
    <section class="grid" aria-label="Published editions">
      {cards}
    </section>
    {empty}
  </main>
  <script id="site-index-data" type="application/json">{data}</script>
</body>
</html>
"""


def release_board_html(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        for kind, item in release_items(record):
            cards.append(release_item_card(record, item, kind))
    release_count = len(cards)
    empty = ""
    if not cards:
        empty = '<p class="empty">No public post exports or visual sketches found yet.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Release Board</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070706;
      --panel: #11100e;
      --ink: #f6f1e8;
      --muted: #b8afa2;
      --line: rgba(246, 241, 232, 0.16);
      --rust: #c35d45;
      --blue: #7092a0;
      --green: #7d8c68;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1240px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 24px 0 34px;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1; }}
    .lede {{
      max-width: 68ch;
      color: var(--muted);
      margin-top: 8px;
      line-height: 1.42;
    }}
    .count {{
      display: grid;
      place-items: center;
      width: 78px;
      height: 70px;
      border: 1px solid var(--line);
      background: #0c0c0b;
    }}
    .count strong {{ font-size: 24px; }}
    .count small {{ color: var(--muted); }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      padding-top: 18px;
    }}
    .release-item {{
      min-width: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      border: 1px solid var(--line);
      background: var(--panel);
    }}
    video {{
      width: 100%;
      aspect-ratio: 9 / 16;
      display: block;
      object-fit: cover;
      background: #020202;
    }}
    .release-copy {{
      display: grid;
      gap: 9px;
      padding: 12px;
    }}
    .slug {{
      color: var(--blue);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 17px;
      line-height: 1.14;
      font-weight: 680;
    }}
    .kind {{ color: var(--green); font-size: 12px; }}
    .facts {{ color: var(--muted); font-size: 12px; line-height: 1.35; }}
    a {{ color: inherit; text-decoration: none; }}
    .button,
    .chip {{
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid currentColor;
      padding: 7px 10px;
    }}
    .button {{ color: var(--rust); width: max-content; }}
    .chip {{ color: var(--green); }}
    .empty {{
      color: var(--muted);
      padding-top: 20px;
    }}
    @media (max-width: 680px) {{
      main {{ width: min(100vw - 18px, 520px); padding-top: 12px; }}
      header {{ grid-template-columns: 1fr; }}
      .count {{ width: 100%; height: 48px; grid-auto-flow: column; gap: 8px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Release Board</h1>
        <p class="lede">A generated board of public Story, Reel, and visual-sketch outputs. Every card is drawn from the sanitized public manifest and can be reverified before posting or transfer.</p>
        <nav class="nav" aria-label="Release surfaces">
          <a class="chip" href="index.html">Edition index</a>
          <a class="chip" href="release-player.html">Release player</a>
          <a class="chip" href="player-presets.md">Player presets</a>
          <a class="chip" href="release-queue.md">Release queue</a>
          <a class="chip" href="exhibit-loop.md">Exhibit loop</a>
          <a class="chip" href="exhibit-programs.json">Exhibit programs</a>
          <a class="chip" href="exhibit-cue-sheet.md">Exhibit cue sheet</a>
          <a class="chip" href="exhibit-cue-sheet.json">Cue JSON</a>
          <a class="chip" href="curatorial-score.md">Curatorial score</a>
          <a class="chip" href="curatorial-score.json">Score JSON</a>
          <a class="chip" href="living-loop.md">Living loop</a>
          <a class="chip" href="living-loop.json">Loop JSON</a>
          <a class="chip" href="platform-plan.md">Platform plan</a>
          <a class="chip" href="playback-contract.json">Playback contract</a>
          <a class="chip" href="composition-atlas.md">Composition atlas</a>
          <a class="chip" href="composition-atlas.json">Atlas JSON</a>
          <a class="chip" href="rhythm-map.md">Rhythm map</a>
          <a class="chip" href="rhythm-map.json">Rhythm JSON</a>
          <a class="chip" href="sound-map.md">Sound map</a>
          <a class="chip" href="sound-map.json">Sound JSON</a>
          <a class="chip" href="release-matrix.md">Release matrix</a>
          <a class="chip" href="release-matrix.json">Matrix JSON</a>
          <a class="chip" href="public-manifest.json">Public manifest</a>
          <a class="chip" href="release-copy.md">Release copy</a>
        </nav>
      </div>
      <div class="count"><strong>{release_count}</strong><small>items</small></div>
    </header>
    <section class="grid" aria-label="Public release media">
      {"".join(cards)}
    </section>
    {empty}
  </main>
</body>
</html>
"""


def player_item(entry: dict[str, Any], position: int) -> dict[str, Any]:
    record = entry["record"]
    item = entry["item"]
    kind = str(entry["kind"])
    return {
        "position": position,
        "edition": str(record.get("slug") or ""),
        "work_title": str(record.get("work_title") or record.get("title") or record.get("slug")),
        "family": str(record.get("family") or ""),
        "kind": kind,
        "name": str(item.get("name") or ""),
        "label": str(item.get("label") or item.get("name") or kind),
        "phase": str(entry["phase"]),
        "href": str(item.get("href") or ""),
        "targets": platform_targets(item, kind),
        "facts": media_fact_line(item.get("media")),
    }


def release_player_html(records: list[dict[str, Any]]) -> str:
    items = [player_item(entry, index) for index, entry in enumerate(release_sequence(records), start=1)]
    presets = player_presets(records)
    programs = exhibit_programs_manifest(records)["programs"]
    payload = json.dumps(
        {
            "schema": "triptych.release-player.v1",
            "items": items,
            "presets": presets,
            "program_schema": "triptych.exhibit-programs.v1",
            "programs": programs,
        }
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Release Player</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070706;
      --panel: #11100e;
      --ink: #f6f1e8;
      --muted: #b8afa2;
      --line: rgba(246, 241, 232, 0.16);
      --rust: #c35d45;
      --blue: #7092a0;
      --green: #7d8c68;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 1fr) minmax(260px, 380px);
      gap: 16px;
      padding: 14px;
    }}
    .stage {{
      min-width: 0;
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }}
    .frame {{
      width: min(100%, calc((100vh - 96px) * 9 / 16));
      max-height: calc(100vh - 96px);
      aspect-ratio: 9 / 16;
      justify-self: center;
      background: #020202;
      border: 1px solid var(--line);
      overflow: hidden;
    }}
    video {{
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
      background: #020202;
    }}
    main[data-kiosk="true"] {{
      grid-template-columns: 1fr;
      gap: 0;
      padding: 0;
    }}
    main[data-kiosk="true"] .stage {{
      min-height: 100vh;
      grid-template-rows: 1fr;
      gap: 0;
    }}
    main[data-kiosk="true"] .frame {{
      width: min(100vw, calc(100vh * 9 / 16));
      max-height: 100vh;
      border: 0;
    }}
    main[data-kiosk="true"] .controls,
    main[data-kiosk="true"] aside {{
      display: none;
    }}
    main[data-fit="contain"] video {{
      object-fit: contain;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
    }}
    button,
    .chip {{
      min-height: 36px;
      border: 1px solid currentColor;
      border-radius: 0;
      background: transparent;
      color: var(--ink);
      padding: 7px 10px;
      font: inherit;
      text-decoration: none;
      cursor: pointer;
    }}
    button.is-active {{ color: var(--rust); }}
    .chip {{ color: var(--green); }}
    aside {{
      min-width: 0;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      gap: 12px;
      border-left: 1px solid var(--line);
      padding-left: 16px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{
      font-size: 24px;
      line-height: 1.04;
      font-weight: 720;
    }}
    .meta,
    .facts {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.36;
    }}
    .meta {{ color: var(--blue); text-transform: uppercase; }}
    .queue {{
      min-height: 0;
      overflow: auto;
      display: grid;
      align-content: start;
      gap: 6px;
      padding-right: 4px;
    }}
    .presets,
    .programs {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .queue button {{
      width: 100%;
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 8px;
      text-align: left;
      color: var(--muted);
      border-color: var(--line);
    }}
    .queue button.is-current {{
      color: var(--ink);
      border-color: var(--rust);
    }}
    .queue strong,
    .queue span {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    @media (max-width: 760px) {{
      main {{
        min-height: 100vh;
        grid-template-columns: 1fr;
        grid-template-rows: auto auto;
        padding: 10px;
      }}
      .frame {{
        width: min(100%, 420px);
        max-height: 68vh;
      }}
      aside {{
        border-left: 0;
        border-top: 1px solid var(--line);
        padding-left: 0;
        padding-top: 12px;
      }}
      .queue {{ max-height: 28vh; }}
    }}
  </style>
</head>
<body>
  <main data-mode="sequential">
    <section class="stage" aria-label="Public release player">
      <div class="frame">
        <video id="player" controls playsinline preload="metadata"></video>
      </div>
      <div class="controls" aria-label="Player controls">
        <button type="button" id="prevButton">Prev</button>
        <button type="button" id="playButton">Play</button>
        <button type="button" id="nextButton">Next</button>
        <button type="button" id="modeButton">Random</button>
        <a class="chip" id="openMedia" href="#">Open media</a>
      </div>
    </section>
    <aside>
      <div>
        <p class="meta" id="nowMeta">release player</p>
        <h1 id="nowTitle">Triptych Release Player</h1>
      </div>
      <p class="facts" id="nowFacts">public queue</p>
      <div class="programs" id="programList" aria-label="Exhibit programs"></div>
      <div class="presets" id="presetList" aria-label="Player presets"></div>
      <div class="queue" id="queueList" aria-label="Release queue"></div>
      <nav aria-label="Release surfaces">
        <a class="chip" href="index.html">Edition index</a>
        <a class="chip" href="release-board.html">Release board</a>
        <a class="chip" href="player-presets.md">Player presets</a>
        <a class="chip" href="release-queue.md">Release queue</a>
        <a class="chip" href="exhibit-loop.md">Exhibit loop</a>
        <a class="chip" href="exhibit-programs.json">Exhibit programs</a>
        <a class="chip" href="exhibit-cue-sheet.md">Exhibit cue sheet</a>
        <a class="chip" href="exhibit-cue-sheet.json">Cue JSON</a>
        <a class="chip" href="curatorial-score.md">Curatorial score</a>
        <a class="chip" href="curatorial-score.json">Score JSON</a>
        <a class="chip" href="living-loop.md">Living loop</a>
        <a class="chip" href="living-loop.json">Loop JSON</a>
        <a class="chip" href="release-copy.md">Release copy</a>
        <a class="chip" href="platform-plan.md">Platform plan</a>
        <a class="chip" href="playback-contract.json">Playback contract</a>
        <a class="chip" href="composition-atlas.md">Composition atlas</a>
        <a class="chip" href="composition-atlas.json">Atlas JSON</a>
        <a class="chip" href="rhythm-map.md">Rhythm map</a>
        <a class="chip" href="rhythm-map.json">Rhythm JSON</a>
        <a class="chip" href="sound-map.md">Sound map</a>
        <a class="chip" href="sound-map.json">Sound JSON</a>
        <a class="chip" href="release-matrix.md">Release matrix</a>
        <a class="chip" href="release-matrix.json">Matrix JSON</a>
        <a class="chip" href="public-manifest.json">Public manifest</a>
      </nav>
    </aside>
  </main>
  <script id="release-player-data" type="application/json">{payload}</script>
  <script>
    const payload = JSON.parse(document.getElementById("release-player-data").textContent);
    const allItems = Array.isArray(payload.items) ? payload.items : [];
    const presets = Array.isArray(payload.presets) ? payload.presets : [];
    const programs = Array.isArray(payload.programs) ? payload.programs : [];
    const params = new URLSearchParams(window.location.search);
    applyProgramParams();
    const main = document.querySelector("main");
    const player = document.getElementById("player");
    const queueList = document.getElementById("queueList");
    const presetList = document.getElementById("presetList");
    const programList = document.getElementById("programList");
    const nowMeta = document.getElementById("nowMeta");
    const nowTitle = document.getElementById("nowTitle");
    const nowFacts = document.getElementById("nowFacts");
    const openMedia = document.getElementById("openMedia");
    const playButton = document.getElementById("playButton");
    const prevButton = document.getElementById("prevButton");
    const nextButton = document.getElementById("nextButton");
    const modeButton = document.getElementById("modeButton");
    let queue = filteredItems();
    let currentIndex = 0;
    let randomMode = params.get("mode") === "random";
    const seededRandom = seededRandomFactory(params.get("seed") || "");

    function displayNumber(value) {{
      return String(value).padStart(2, "0");
    }}

    function truthyParam(value) {{
      return value === "1" || value === "true" || value === "yes";
    }}

    function playerFit() {{
      return params.get("fit") === "contain" ? "contain" : "cover";
    }}

    function boundedNumber(value, fallback, min, max) {{
      const parsed = Number(value);
      if (!Number.isFinite(parsed)) return fallback;
      return Math.min(max, Math.max(min, parsed));
    }}

    function seededRandomFactory(seedText) {{
      if (!seedText) return null;
      let state = 2166136261;
      for (let index = 0; index < seedText.length; index += 1) {{
        state ^= seedText.charCodeAt(index);
        state = Math.imul(state, 16777619);
      }}
      return () => {{
        state = Math.imul(state ^ (state >>> 15), 2246822507);
        state = Math.imul(state ^ (state >>> 13), 3266489909);
        state = (state ^ (state >>> 16)) >>> 0;
        return state / 4294967296;
      }};
    }}

    function randomValue() {{
      return seededRandom ? seededRandom() : Math.random();
    }}

    function programById(id) {{
      return programs.find((program) => program && program.id === id);
    }}

    function applyProgramParams() {{
      const program = programById(params.get("program"));
      if (!program || typeof program.href !== "string") return;
      const query = program.href.split("?")[1] || "";
      const programParams = new URLSearchParams(query);
      ["edition", "family", "mode", "muted", "autoplay", "kiosk", "fit", "volume", "rate", "seed"].forEach((key) => {{
        if (programParams.has(key)) params.set(key, programParams.get(key));
      }});
    }}

    function filteredItems() {{
      const edition = params.get("edition");
      const family = params.get("family");
      return allItems.filter((item) => {{
        if (edition && item.edition !== edition) return false;
        if (family && item.family !== family) return false;
        return true;
      }});
    }}

    function startIndex() {{
      const raw = Number(params.get("start") || "1");
      if (!Number.isFinite(raw) || raw < 1) return 0;
      return Math.min(queue.length - 1, Math.floor(raw) - 1);
    }}

    function filterLabel() {{
      const program = programById(params.get("program"));
      if (program) return `program ${{program.label || program.id}}`;
      const edition = params.get("edition");
      const family = params.get("family");
      if (edition) return `edition ${{edition}}`;
      if (family) return `family ${{family.replaceAll("_", " ")}}`;
      return "all releases";
    }}

    function nextIndex() {{
      if (!queue.length) return 0;
      if (!randomMode || queue.length === 1) return (currentIndex + 1) % queue.length;
      let candidate = currentIndex;
      let attempts = 0;
      while (candidate === currentIndex && attempts < 8) {{
        candidate = Math.floor(randomValue() * queue.length);
        attempts += 1;
      }}
      return candidate === currentIndex ? (currentIndex + 1) % queue.length : candidate;
    }}

    function renderPresets() {{
      presetList.replaceChildren();
      presets.forEach((preset) => {{
        const link = document.createElement("a");
        link.className = "chip";
        link.href = preset.href;
        link.textContent = preset.label;
        presetList.append(link);
      }});
    }}

    function renderPrograms() {{
      programList.replaceChildren();
      programs.forEach((program) => {{
        const link = document.createElement("a");
        link.className = "chip";
        link.href = `release-player.html?program=${{encodeURIComponent(program.id)}}`;
        link.textContent = program.label;
        if (Number.isFinite(Number(program.item_count))) {{
          link.title = `${{program.item_count}} public items`;
        }}
        programList.append(link);
      }});
    }}

    function renderQueue() {{
      queueList.replaceChildren();
      queue.forEach((item, index) => {{
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.index = String(index);
        const number = document.createElement("strong");
        number.textContent = displayNumber(item.position || index + 1);
        const label = document.createElement("span");
        label.textContent = `${{item.work_title}} / ${{item.label}}`;
        button.append(number, label);
        button.addEventListener("click", () => loadItem(index, true));
        queueList.append(button);
      }});
    }}

    function markQueue() {{
      queueList.querySelectorAll("button").forEach((button) => {{
        button.classList.toggle("is-current", Number(button.dataset.index) === currentIndex);
      }});
    }}

    function loadItem(index, shouldPlay) {{
      if (!queue.length) {{
        player.removeAttribute("src");
        nowMeta.textContent = "no public media";
        nowTitle.textContent = "No matching release items";
        nowFacts.textContent = filterLabel();
        openMedia.removeAttribute("href");
        return;
      }}
      currentIndex = (index + queue.length) % queue.length;
      const item = queue[currentIndex];
      player.src = item.href;
      nowMeta.textContent = `${{displayNumber(currentIndex + 1)}} of ${{queue.length}} / ${{filterLabel()}} / ${{item.phase}}`;
      nowTitle.textContent = item.work_title;
      nowFacts.textContent = `${{item.facts}} / ${{item.targets.join(", ")}}`;
      openMedia.href = item.href;
      markQueue();
      if (shouldPlay) {{
        player.play().catch(() => {{}});
      }}
    }}

    function syncPlayLabel() {{
      playButton.textContent = player.paused ? "Play" : "Pause";
    }}

    prevButton.addEventListener("click", () => loadItem(currentIndex - 1, true));
    nextButton.addEventListener("click", () => loadItem(nextIndex(), true));
    playButton.addEventListener("click", () => {{
      if (player.paused) {{
        player.play().catch(() => {{}});
      }} else {{
        player.pause();
      }}
    }});
    modeButton.addEventListener("click", () => {{
      randomMode = !randomMode;
      main.dataset.mode = randomMode ? "random" : "sequential";
      modeButton.classList.toggle("is-active", randomMode);
      modeButton.textContent = randomMode ? "Sequential" : "Random";
    }});
    player.addEventListener("play", syncPlayLabel);
    player.addEventListener("pause", syncPlayLabel);
    player.addEventListener("ended", () => loadItem(nextIndex(), true));

    player.muted = truthyParam(params.get("muted"));
    player.volume = boundedNumber(params.get("volume"), 1, 0, 1);
    player.playbackRate = boundedNumber(params.get("rate"), 1, 0.25, 2);
    main.dataset.mode = randomMode ? "random" : "sequential";
    const kioskMode = truthyParam(params.get("kiosk"));
    main.dataset.kiosk = kioskMode ? "true" : "false";
    main.dataset.fit = playerFit();
    player.controls = !kioskMode;
    modeButton.classList.toggle("is-active", randomMode);
    modeButton.textContent = randomMode ? "Sequential" : "Random";
    renderPrograms();
    renderPresets();
    renderQueue();
    currentIndex = startIndex();
    loadItem(currentIndex, truthyParam(params.get("autoplay")));
    syncPlayLabel();
  </script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    site_dir = args.site_dir.expanduser()
    output = args.output.expanduser()
    public_manifest_path = args.public_manifest.expanduser()
    release_board_path = args.release_board.expanduser()
    release_copy_path = args.release_copy.expanduser()
    platform_plan_path = args.platform_plan.expanduser()
    release_queue_path = args.release_queue.expanduser()
    release_player_path = args.release_player.expanduser()
    player_presets_path = args.player_presets.expanduser()
    exhibit_loop_path = args.exhibit_loop.expanduser()
    exhibit_programs_path = args.exhibit_programs.expanduser()
    playback_contract_path = args.playback_contract.expanduser()
    composition_atlas_path = args.composition_atlas.expanduser()
    composition_atlas_doc_path = args.composition_atlas_doc.expanduser()
    rhythm_map_path = args.rhythm_map.expanduser()
    rhythm_map_doc_path = args.rhythm_map_doc.expanduser()
    sound_map_path = args.sound_map.expanduser()
    sound_map_doc_path = args.sound_map_doc.expanduser()
    release_matrix_path = args.release_matrix.expanduser()
    release_matrix_doc_path = args.release_matrix_doc.expanduser()
    exhibit_cue_sheet_path = args.exhibit_cue_sheet.expanduser()
    exhibit_cue_sheet_doc_path = args.exhibit_cue_sheet_doc.expanduser()
    curatorial_score_path = args.curatorial_score.expanduser()
    curatorial_score_doc_path = args.curatorial_score_doc.expanduser()
    living_loop_path = args.living_loop.expanduser()
    living_loop_doc_path = args.living_loop_doc.expanduser()
    require_inside(site_dir, "site-dir")
    require_inside(output, "output")
    require_inside(public_manifest_path, "public-manifest")
    require_inside(release_board_path, "release-board")
    require_inside(release_copy_path, "release-copy")
    require_inside(platform_plan_path, "platform-plan")
    require_inside(release_queue_path, "release-queue")
    require_inside(release_player_path, "release-player")
    require_inside(player_presets_path, "player-presets")
    require_inside(exhibit_loop_path, "exhibit-loop")
    require_inside(exhibit_programs_path, "exhibit-programs")
    require_inside(playback_contract_path, "playback-contract")
    require_inside(composition_atlas_path, "composition-atlas")
    require_inside(composition_atlas_doc_path, "composition-atlas-doc")
    require_inside(rhythm_map_path, "rhythm-map")
    require_inside(rhythm_map_doc_path, "rhythm-map-doc")
    require_inside(sound_map_path, "sound-map")
    require_inside(sound_map_doc_path, "sound-map-doc")
    require_inside(release_matrix_path, "release-matrix")
    require_inside(release_matrix_doc_path, "release-matrix-doc")
    require_inside(exhibit_cue_sheet_path, "exhibit-cue-sheet")
    require_inside(exhibit_cue_sheet_doc_path, "exhibit-cue-sheet-doc")
    require_inside(curatorial_score_path, "curatorial-score")
    require_inside(curatorial_score_doc_path, "curatorial-score-doc")
    require_inside(living_loop_path, "living-loop")
    require_inside(living_loop_doc_path, "living-loop-doc")
    output_dir = output.parent
    records = collect_editions(site_dir, output_dir)
    release_count = sum(len(release_items(record)) for record in records)
    print(f"write site index {output} ({len(records)} editions)")
    print(f"write public manifest {public_manifest_path} ({len(records)} editions)")
    print(f"write release board {release_board_path} ({release_count} items)")
    print(f"write release copy {release_copy_path} ({release_count} items)")
    print(f"write platform plan {platform_plan_path} ({release_count} items)")
    print(f"write release queue {release_queue_path} ({release_count} items)")
    print(f"write release player {release_player_path} ({release_count} items)")
    print(f"write player presets {player_presets_path} ({len(player_presets(records))} presets)")
    print(f"write exhibit loop {exhibit_loop_path} ({len(records)} editions)")
    print(f"write exhibit programs {exhibit_programs_path} ({len(exhibit_programs_manifest(records)['programs'])} programs)")
    print(f"write playback contract {playback_contract_path} ({len(playback_contract(records)['allowed_params'])} params)")
    print(f"write composition atlas {composition_atlas_path} ({len(composition_atlas(records)['editions'])} editions)")
    print(f"write composition atlas doc {composition_atlas_doc_path} ({len(composition_atlas(records)['families'])} families)")
    print(f"write rhythm map {rhythm_map_path} ({len(rhythm_map(records)['items'])} items)")
    print(f"write rhythm map doc {rhythm_map_doc_path} ({len(rhythm_map(records)['families'])} families)")
    print(f"write sound map {sound_map_path} ({sound_map(records)['audio_item_count']} audio items)")
    print(f"write sound map doc {sound_map_doc_path} ({sound_map(records)['silent_item_count']} silent items)")
    print(f"write release matrix {release_matrix_path} ({release_matrix(records)['target_count']} targets)")
    print(f"write release matrix doc {release_matrix_doc_path} ({release_matrix(records)['edition_count']} editions)")
    print(f"write exhibit cue sheet {exhibit_cue_sheet_path} ({exhibit_cue_sheet(records)['program_count']} programs)")
    print(f"write exhibit cue sheet doc {exhibit_cue_sheet_doc_path} ({exhibit_cue_sheet(records)['total_public_items']} public items)")
    print(f"write curatorial score {curatorial_score_path} ({curatorial_score(records)['edition_count']} editions)")
    print(f"write curatorial score doc {curatorial_score_doc_path} ({curatorial_score(records)['item_count']} public items)")
    print(f"write living loop {living_loop_path} ({living_loop(records)['slot_count']} slots)")
    print(f"write living loop doc {living_loop_doc_path} ({living_loop(records)['item_count']} public items)")
    if args.dry_run:
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(index_html(records), encoding="utf-8")
    public_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    public_manifest_path.write_text(
        json.dumps(public_manifest(records), indent=2) + "\n",
        encoding="utf-8",
    )
    release_board_path.parent.mkdir(parents=True, exist_ok=True)
    release_board_path.write_text(release_board_html(records), encoding="utf-8")
    release_copy_path.parent.mkdir(parents=True, exist_ok=True)
    release_copy_path.write_text(release_copy_markdown(records), encoding="utf-8")
    platform_plan_path.parent.mkdir(parents=True, exist_ok=True)
    platform_plan_path.write_text(platform_plan_markdown(records), encoding="utf-8")
    release_queue_path.parent.mkdir(parents=True, exist_ok=True)
    release_queue_path.write_text(release_queue_markdown(records), encoding="utf-8")
    release_player_path.parent.mkdir(parents=True, exist_ok=True)
    release_player_path.write_text(release_player_html(records), encoding="utf-8")
    player_presets_path.parent.mkdir(parents=True, exist_ok=True)
    player_presets_path.write_text(player_presets_markdown(records), encoding="utf-8")
    exhibit_loop_path.parent.mkdir(parents=True, exist_ok=True)
    exhibit_loop_path.write_text(exhibit_loop_markdown(records), encoding="utf-8")
    exhibit_programs_path.parent.mkdir(parents=True, exist_ok=True)
    exhibit_programs_path.write_text(
        json.dumps(exhibit_programs_manifest(records), indent=2) + "\n",
        encoding="utf-8",
    )
    playback_contract_path.parent.mkdir(parents=True, exist_ok=True)
    playback_contract_path.write_text(
        json.dumps(playback_contract(records), indent=2) + "\n",
        encoding="utf-8",
    )
    composition_atlas_path.parent.mkdir(parents=True, exist_ok=True)
    composition_atlas_path.write_text(
        json.dumps(composition_atlas(records), indent=2) + "\n",
        encoding="utf-8",
    )
    composition_atlas_doc_path.parent.mkdir(parents=True, exist_ok=True)
    composition_atlas_doc_path.write_text(composition_atlas_markdown(records), encoding="utf-8")
    rhythm_map_path.parent.mkdir(parents=True, exist_ok=True)
    rhythm_map_path.write_text(
        json.dumps(rhythm_map(records), indent=2) + "\n",
        encoding="utf-8",
    )
    rhythm_map_doc_path.parent.mkdir(parents=True, exist_ok=True)
    rhythm_map_doc_path.write_text(rhythm_map_markdown(records), encoding="utf-8")
    sound_map_path.parent.mkdir(parents=True, exist_ok=True)
    sound_map_path.write_text(
        json.dumps(sound_map(records), indent=2) + "\n",
        encoding="utf-8",
    )
    sound_map_doc_path.parent.mkdir(parents=True, exist_ok=True)
    sound_map_doc_path.write_text(sound_map_markdown(records), encoding="utf-8")
    release_matrix_path.parent.mkdir(parents=True, exist_ok=True)
    release_matrix_path.write_text(
        json.dumps(release_matrix(records), indent=2) + "\n",
        encoding="utf-8",
    )
    release_matrix_doc_path.parent.mkdir(parents=True, exist_ok=True)
    release_matrix_doc_path.write_text(release_matrix_markdown(records), encoding="utf-8")
    exhibit_cue_sheet_path.parent.mkdir(parents=True, exist_ok=True)
    exhibit_cue_sheet_path.write_text(
        json.dumps(exhibit_cue_sheet(records), indent=2) + "\n",
        encoding="utf-8",
    )
    exhibit_cue_sheet_doc_path.parent.mkdir(parents=True, exist_ok=True)
    exhibit_cue_sheet_doc_path.write_text(exhibit_cue_sheet_markdown(records), encoding="utf-8")
    curatorial_score_path.parent.mkdir(parents=True, exist_ok=True)
    curatorial_score_path.write_text(
        json.dumps(curatorial_score(records), indent=2) + "\n",
        encoding="utf-8",
    )
    curatorial_score_doc_path.parent.mkdir(parents=True, exist_ok=True)
    curatorial_score_doc_path.write_text(curatorial_score_markdown(records), encoding="utf-8")
    living_loop_path.parent.mkdir(parents=True, exist_ok=True)
    living_loop_path.write_text(
        json.dumps(living_loop(records), indent=2) + "\n",
        encoding="utf-8",
    )
    living_loop_doc_path.parent.mkdir(parents=True, exist_ok=True)
    living_loop_doc_path.write_text(living_loop_markdown(records), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
