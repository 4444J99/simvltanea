#!/usr/bin/env python3
"""Verify that the generated triptych site is safe and coherent to share."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".txt"}
FORBIDDEN_TEXT = (
    "/Users/",
    ".photoslibrary",
    "Photos Library",
    "Photos.sqlite",
    "resources/derivatives",
    "absolute_path",
    "resolved_path",
    "source_uuid",
    "sourceUuid",
    "sourceSrc",
    "source_src",
    "symlink_target",
)
FORBIDDEN_PUBLIC_KEYS = {
    "absolute_path",
    "outside_incubator_source",
    "resolved_path",
    "source",
    "source_src",
    "source_uuid",
    "symlink_target",
}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
PANEL_NAMES = {"left", "middle", "right"}
SURFACES = {"canon", "sketch"}
DIRECTIONS = {"forward", "reverse", "pingpong"}
START_MODES = {"oldest", "random"}
LIVING_ROTATION_PROFILES = (
    ("studio-review", "Studio Review", "0.35", "0.75"),
    ("gallery-slow", "Gallery Slow", "0.20", "0.50"),
    ("post-spark", "Post Spark", "0.45", "1.00"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate generated public triptych site files before sharing or hosting. "
            "Checks privacy tokens, public receipts, media references, exports, and size."
        )
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=DEFAULT_SITE_DIR,
        help="Generated static site directory. Defaults to site/.",
    )
    parser.add_argument(
        "--max-site-mb",
        type=float,
        default=128.0,
        help="Fail if the public site exceeds this size. Defaults to 128 MB.",
    )
    parser.add_argument(
        "--max-edition-mb",
        type=float,
        default=32.0,
        help="Fail if one edition directory exceeds this size. Defaults to 32 MB.",
    )
    parser.add_argument(
        "--max-visual-sketch-mb",
        type=float,
        default=16.0,
        help="Fail if one public visual-sketch export exceeds this size. Defaults to 16 MB.",
    )
    parser.add_argument(
        "--max-visual-sketch-seconds",
        type=float,
        default=120.0,
        help="Fail if one public visual-sketch export exceeds this duration. Defaults to 120 seconds.",
    )
    parser.add_argument(
        "--max-published-export-mb",
        type=float,
        default=64.0,
        help="Fail if one published Story/Reel export exceeds this size. Defaults to 64 MB.",
    )
    parser.add_argument(
        "--max-published-export-seconds",
        type=float,
        default=600.0,
        help="Fail if one published Story/Reel export exceeds this duration. Defaults to 600 seconds.",
    )
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def site_path(raw_path: Path, site_dir: Path) -> Path:
    path = raw_path.expanduser()
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def public_ref(base_dir: Path, ref: str) -> Path | None:
    if not ref or ref.startswith(("http://", "https://", "data:", "javascript:")):
        return None
    path = Path(ref)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{path}: cannot read JSON: {error}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{path}: JSON root must be an object")
        return None
    return data


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def tree_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += file_size(item)
    return total


def mb(value: int) -> float:
    return value / (1024 * 1024)


def scan_text_files(site_dir: Path, errors: list[str]) -> None:
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: expected UTF-8 text")
            continue
        except OSError as error:
            errors.append(f"{path}: cannot read text: {error}")
            continue
        for needle in FORBIDDEN_TEXT:
            if needle in text:
                errors.append(f"{path}: contains private token {needle!r}")


def walk_forbidden_keys(value: Any, path: str, errors: list[str], receipt_path: Path) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in FORBIDDEN_PUBLIC_KEYS:
                errors.append(f"{receipt_path}: public receipt contains private key {child_path}")
            walk_forbidden_keys(child, child_path, errors, receipt_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_forbidden_keys(child, f"{path}[{index}]", errors, receipt_path)


def resolve_landing_path(receipt: dict[str, Any], receipt_dir: Path, site_dir: Path) -> Path | None:
    raw_landing = receipt.get("landing_page")
    if not isinstance(raw_landing, str) or not raw_landing:
        return None
    candidates = [
        (SCRIPT_DIR / raw_landing).resolve(),
        (site_dir / raw_landing).resolve(),
        (receipt_dir / raw_landing).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def media_ref_path(
    receipt_path: Path,
    receipt_dir: Path,
    site_dir: Path,
    ref: Any,
    label: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(ref, str) or not ref:
        errors.append(f"{receipt_path}: missing {label}")
        return None
    target = public_ref(receipt_dir, ref)
    if target is None:
        errors.append(f"{receipt_path}: invalid {label} {ref!r}")
        return None
    if not path_inside(target, site_dir):
        errors.append(f"{receipt_path}: {label} escapes site dir: {ref}")
        return None
    if not target.exists():
        errors.append(f"{receipt_path}: {label} does not exist: {ref}")
        return None
    return target


def validate_media_ref(
    receipt_path: Path,
    receipt_dir: Path,
    site_dir: Path,
    ref: Any,
    label: str,
    errors: list[str],
) -> bool:
    return media_ref_path(receipt_path, receipt_dir, site_dir, ref, label, errors) is not None


def validate_number_range(
    receipt_path: Path,
    value: Any,
    label: str,
    minimum: float,
    maximum: float,
    errors: list[str],
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{receipt_path}: {label} must be a number")
        return
    number = float(value)
    if number < minimum or number > maximum:
        errors.append(f"{receipt_path}: {label} {number:g} outside {minimum:g}..{maximum:g}")


def validate_control_presets(receipt_path: Path, receipt: dict[str, Any], errors: list[str]) -> None:
    presets = receipt.get("control_presets", [])
    if not isinstance(presets, list):
        errors.append(f"{receipt_path}: control_presets must be a list")
        return

    seen: set[str] = set()
    default_count = 0
    for index, preset in enumerate(presets, start=1):
        label = f"control_presets[{index}]"
        if not isinstance(preset, dict):
            errors.append(f"{receipt_path}: {label} must be an object")
            continue

        preset_id = preset.get("id")
        if not isinstance(preset_id, str) or not SAFE_ID_RE.fullmatch(preset_id):
            errors.append(f"{receipt_path}: {label}.id must be a safe lowercase id")
        elif preset_id in seen:
            errors.append(f"{receipt_path}: duplicate preset id {preset_id!r}")
        else:
            seen.add(preset_id)

        preset_label = preset.get("label")
        if not isinstance(preset_label, str) or not preset_label.strip():
            errors.append(f"{receipt_path}: {label}.label must be a non-empty string")

        note = preset.get("note")
        if note is not None and not isinstance(note, str):
            errors.append(f"{receipt_path}: {label}.note must be a string")

        surface = preset.get("surface")
        if surface is not None and surface not in SURFACES:
            errors.append(f"{receipt_path}: {label}.surface must be canon or sketch")

        direction = preset.get("direction")
        if direction is not None and direction not in DIRECTIONS:
            errors.append(f"{receipt_path}: {label}.direction is invalid")

        start = preset.get("start")
        if start is not None and start not in START_MODES:
            errors.append(f"{receipt_path}: {label}.start is invalid")

        panel_order = preset.get("panelOrder")
        if panel_order is not None:
            if (
                not isinstance(panel_order, list)
                or len(panel_order) != 3
                or set(panel_order) != PANEL_NAMES
                or any(not isinstance(name, str) for name in panel_order)
            ):
                errors.append(f"{receipt_path}: {label}.panelOrder must contain left, middle, right once")

        for key in ("labels", "audio", "default"):
            if key in preset and not isinstance(preset[key], bool):
                errors.append(f"{receipt_path}: {label}.{key} must be boolean")
        if preset.get("default") is True:
            default_count += 1

        if "volume" in preset:
            validate_number_range(receipt_path, preset["volume"], f"{label}.volume", 0, 1, errors)

        panel_volumes = preset.get("panelVolumes")
        if panel_volumes is not None:
            if not isinstance(panel_volumes, dict):
                errors.append(f"{receipt_path}: {label}.panelVolumes must be an object")
            else:
                for panel, value in panel_volumes.items():
                    if panel not in PANEL_NAMES:
                        errors.append(f"{receipt_path}: {label}.panelVolumes has unknown panel {panel!r}")
                        continue
                    validate_number_range(
                        receipt_path,
                        value,
                        f"{label}.panelVolumes.{panel}",
                        0,
                        1.5,
                        errors,
                    )

    if default_count > 1:
        errors.append(f"{receipt_path}: only one control preset may be default")


def ffprobe_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        errors.append(f"{label}: ffprobe is required to verify visual-sketch media")
        return None
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        errors.append(f"{label}: ffprobe failed: {detail}")
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        errors.append(f"{label}: ffprobe returned invalid JSON: {error}")
        return None
    return data if isinstance(data, dict) else None


def numeric_field(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def validate_video_export_media(
    receipt_path: Path,
    target: Path,
    label: str,
    max_mb: float,
    max_seconds: float,
    errors: list[str],
) -> None:
    size_mb = mb(file_size(target))
    if size_mb > max_mb:
        errors.append(f"{receipt_path}: {label} size {size_mb:.1f} MB exceeds {max_mb:.1f} MB")

    data = ffprobe_json(target, f"{receipt_path}: {label}", errors)
    if data is None:
        return

    streams = data.get("streams", [])
    video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    if not video_streams:
        errors.append(f"{receipt_path}: {label} has no video stream")
        return
    stream = video_streams[0]
    width = stream.get("width")
    height = stream.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        errors.append(f"{receipt_path}: {label} has invalid dimensions {width!r}x{height!r}")
    else:
        ratio = width / height
        expected = 9 / 16
        if abs(ratio - expected) > 0.035:
            errors.append(f"{receipt_path}: {label} is not 9:16 video ({width}x{height})")

    format_info = data.get("format", {})
    duration = numeric_field(format_info.get("duration")) if isinstance(format_info, dict) else None
    if duration is None or duration <= 0:
        errors.append(f"{receipt_path}: {label} has invalid duration {duration!r}")
    elif duration > max_seconds:
        errors.append(f"{receipt_path}: {label} duration {duration:.1f}s exceeds {max_seconds:.1f}s")


def public_media_facts(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    data = ffprobe_json(path, label, errors)
    if data is None:
        return None
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
        "size_bytes": int(reported_size) if reported_size is not None else file_size(path),
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


def validate_manifest_media_facts(
    manifest_path: Path,
    media: Any,
    target: Path,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(media, dict):
        errors.append(f"{manifest_path}: {label}.media must be an object")
        return
    actual = public_media_facts(target, f"{manifest_path}: {label}", errors)
    if actual is None:
        return
    required_keys = ("size_bytes", "duration_seconds", "width", "height", "has_video", "has_audio")
    for key in required_keys:
        if media.get(key) != actual.get(key):
            errors.append(f"{manifest_path}: {label}.media.{key} must be {actual.get(key)!r}")
    if "video_codec" in actual and media.get("video_codec") != actual["video_codec"]:
        errors.append(f"{manifest_path}: {label}.media.video_codec must be {actual['video_codec']!r}")
    if "aspect_ratio" in actual:
        ratio = media.get("aspect_ratio")
        if not isinstance(ratio, (int, float)) or abs(float(ratio) - float(actual["aspect_ratio"])) > 0.000001:
            errors.append(f"{manifest_path}: {label}.media.aspect_ratio must be {actual['aspect_ratio']!r}")


POSTABLE_LAYOUTS = {"story", "left", "middle", "right"}
PUBLIC_MANIFEST_SCHEMA = "triptych.public-release-manifest.v1"
PLAYBACK_CONTRACT_SCHEMA = "triptych.playback-contract.v1"
COMPOSITION_ATLAS_SCHEMA = "triptych.composition-atlas.v1"
RHYTHM_MAP_SCHEMA = "triptych.rhythm-map.v1"
SOUND_MAP_SCHEMA = "triptych.sound-map.v1"
RELEASE_MATRIX_SCHEMA = "triptych.release-matrix.v1"
EXHIBIT_CUE_SHEET_SCHEMA = "triptych.exhibit-cue-sheet.v1"
CURATORIAL_SCORE_SCHEMA = "triptych.curatorial-score.v1"
LIVING_LOOP_SCHEMA = "triptych.living-loop.v1"


def validate_receipt(
    receipt_path: Path,
    site_dir: Path,
    errors: list[str],
    max_visual_sketch_mb: float,
    max_visual_sketch_seconds: float,
    max_published_export_mb: float,
    max_published_export_seconds: float,
) -> dict[str, Any] | None:
    receipt = load_json(receipt_path, errors)
    if receipt is None:
        return None

    receipt_dir = receipt_path.parent
    if receipt.get("schema") != "triptych.flash-copy.v1":
        errors.append(f"{receipt_path}: unexpected schema {receipt.get('schema')!r}")
    if receipt.get("public") is not True:
        errors.append(f"{receipt_path}: public must be true")
    walk_forbidden_keys(receipt, "", errors, receipt_path)

    landing = resolve_landing_path(receipt, receipt_dir, site_dir)
    if landing is None:
        errors.append(f"{receipt_path}: missing landing_page")
    elif not path_inside(landing, site_dir):
        errors.append(f"{receipt_path}: landing_page escapes site dir")
    elif not landing.exists():
        errors.append(f"{receipt_path}: landing_page does not exist: {receipt.get('landing_page')}")

    clips = receipt.get("clips", [])
    if not isinstance(clips, list):
        errors.append(f"{receipt_path}: clips must be a list")
        clips = []

    counts = receipt.get("counts", {})
    if not isinstance(counts, dict):
        errors.append(f"{receipt_path}: counts must be an object")
        counts = {}

    manifest_count = counts.get("manifest_clips")
    if isinstance(manifest_count, int) and manifest_count != len(clips):
        errors.append(f"{receipt_path}: manifest_clips {manifest_count} != clips {len(clips)}")

    video_proxy_count = 0
    audio_proxy_count = 0
    for index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            errors.append(f"{receipt_path}: clip {index} must be an object")
            continue
        media = clip.get("media")
        if not isinstance(media, dict):
            errors.append(f"{receipt_path}: clip {index} media must be an object")
            continue
        video_src = media.get("video_src")
        audio_src = media.get("audio_src")
        if media.get("proxy") is True:
            if validate_media_ref(receipt_path, receipt_dir, site_dir, video_src, f"clip {index} video_src", errors):
                video_proxy_count += 1
        elif video_src:
            validate_media_ref(receipt_path, receipt_dir, site_dir, video_src, f"clip {index} video_src", errors)
        if audio_src:
            if validate_media_ref(receipt_path, receipt_dir, site_dir, audio_src, f"clip {index} audio_src", errors):
                audio_proxy_count += 1

    if isinstance(counts.get("video_proxies"), int) and counts["video_proxies"] != video_proxy_count:
        errors.append(f"{receipt_path}: video_proxies {counts['video_proxies']} != verified {video_proxy_count}")
    if isinstance(counts.get("audio_proxies"), int) and counts["audio_proxies"] != audio_proxy_count:
        errors.append(f"{receipt_path}: audio_proxies {counts['audio_proxies']} != verified {audio_proxy_count}")

    validate_control_presets(receipt_path, receipt, errors)

    exports = receipt.get("exports", [])
    if not isinstance(exports, list):
        errors.append(f"{receipt_path}: exports must be a list")
        exports = []
    for index, export in enumerate(exports, start=1):
        if not isinstance(export, dict):
            errors.append(f"{receipt_path}: export {index} must be an object")
            continue
        exists = export.get("exists") is True
        src = export.get("src")
        if exists:
            target = media_ref_path(receipt_path, receipt_dir, site_dir, src, f"export {index} src", errors)
            if target is not None and export.get("layout") == "visual-sketch":
                validate_video_export_media(
                    receipt_path,
                    target,
                    f"export {index} visual-sketch",
                    max_visual_sketch_mb,
                    max_visual_sketch_seconds,
                    errors,
                )
            elif target is not None and export.get("published") is True and export.get("layout") in POSTABLE_LAYOUTS:
                validate_video_export_media(
                    receipt_path,
                    target,
                    f"export {index} {export.get('layout')}",
                    max_published_export_mb,
                    max_published_export_seconds,
                    errors,
                )
        elif src:
            errors.append(f"{receipt_path}: export {index} is missing but still exposes src {src!r}")
        if export.get("published") is True and not exists:
            errors.append(f"{receipt_path}: export {index} is published but exists is not true")

    return receipt


def validate_index(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    index = site_dir / "index.html"
    if not index.exists():
        errors.append(f"{index}: missing root site index")
        return
    try:
        text = index.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{index}: cannot read: {error}")
        return
    if "release-board.html" not in text:
        errors.append(f"{index}: missing link to release-board.html")
    if "public-manifest.json" not in text:
        errors.append(f"{index}: missing link to public-manifest.json")
    if "release-copy.md" not in text:
        errors.append(f"{index}: missing link to release-copy.md")
    if "platform-plan.md" not in text:
        errors.append(f"{index}: missing link to platform-plan.md")
    if "release-queue.md" not in text:
        errors.append(f"{index}: missing link to release-queue.md")
    if "release-player.html" not in text:
        errors.append(f"{index}: missing link to release-player.html")
    if "player-presets.md" not in text:
        errors.append(f"{index}: missing link to player-presets.md")
    if "exhibit-loop.md" not in text:
        errors.append(f"{index}: missing link to exhibit-loop.md")
    if "exhibit-programs.json" not in text:
        errors.append(f"{index}: missing link to exhibit-programs.json")
    if "exhibit-cue-sheet.md" not in text:
        errors.append(f"{index}: missing link to exhibit-cue-sheet.md")
    if "exhibit-cue-sheet.json" not in text:
        errors.append(f"{index}: missing link to exhibit-cue-sheet.json")
    if "curatorial-score.md" not in text:
        errors.append(f"{index}: missing link to curatorial-score.md")
    if "curatorial-score.json" not in text:
        errors.append(f"{index}: missing link to curatorial-score.json")
    if "living-loop.md" not in text:
        errors.append(f"{index}: missing link to living-loop.md")
    if "living-loop.json" not in text:
        errors.append(f"{index}: missing link to living-loop.json")
    if "playback-contract.json" not in text:
        errors.append(f"{index}: missing link to playback-contract.json")
    if "composition-atlas.md" not in text:
        errors.append(f"{index}: missing link to composition-atlas.md")
    if "composition-atlas.json" not in text:
        errors.append(f"{index}: missing link to composition-atlas.json")
    if "rhythm-map.md" not in text:
        errors.append(f"{index}: missing link to rhythm-map.md")
    if "rhythm-map.json" not in text:
        errors.append(f"{index}: missing link to rhythm-map.json")
    if "sound-map.md" not in text:
        errors.append(f"{index}: missing link to sound-map.md")
    if "sound-map.json" not in text:
        errors.append(f"{index}: missing link to sound-map.json")
    if "release-matrix.md" not in text:
        errors.append(f"{index}: missing link to release-matrix.md")
    if "release-matrix.json" not in text:
        errors.append(f"{index}: missing link to release-matrix.json")
    for slug, receipt in receipts.items():
        expected = f"editions/{slug}/index.html"
        if expected not in text:
            errors.append(f"{index}: missing link to {expected}")
        for preset in receipt.get("control_presets", []):
            if not isinstance(preset, dict):
                continue
            preset_id = preset.get("id")
            if not isinstance(preset_id, str) or not SAFE_ID_RE.fullmatch(preset_id):
                continue
            expected_preset = f"{expected}?preset={preset_id}"
            if expected_preset not in text:
                errors.append(f"{index}: missing preset link to {expected_preset}")
        post_pack = receipt.get("post_pack")
        if not isinstance(post_pack, dict):
            continue
        post_exports = post_pack.get("exports")
        if not isinstance(post_exports, list):
            continue
        exports = {
            str(export.get("name")): export
            for export in receipt.get("exports", [])
            if isinstance(export, dict)
        }
        for export_name in post_exports:
            export = exports.get(str(export_name))
            if not export or export.get("exists") is not True:
                continue
            src = export.get("src")
            if isinstance(src, str) and src:
                expected_export = f"editions/{slug}/{src}"
                if expected_export not in text:
                    errors.append(f"{index}: missing post-pack export link to {expected_export}")


def expected_release_hrefs(receipts: dict[str, dict[str, Any]]) -> list[str]:
    hrefs: list[str] = []
    for slug, receipt in receipts.items():
        for export in published_post_exports(receipt):
            hrefs.append(f"editions/{slug}/{export['src']}")
        for export in visual_sketch_exports(receipt):
            hrefs.append(f"editions/{slug}/{export['src']}")
    return sorted(hrefs)


def validate_release_board(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    board = site_dir / "release-board.html"
    if not board.exists():
        errors.append(f"{board}: missing release board")
        return
    try:
        text = board.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{board}: cannot read: {error}")
        return
    if "index.html" not in text:
        errors.append(f"{board}: missing link to index.html")
    if "public-manifest.json" not in text:
        errors.append(f"{board}: missing link to public-manifest.json")
    if "release-copy.md" not in text:
        errors.append(f"{board}: missing link to release-copy.md")
    if "platform-plan.md" not in text:
        errors.append(f"{board}: missing link to platform-plan.md")
    if "release-queue.md" not in text:
        errors.append(f"{board}: missing link to release-queue.md")
    if "release-player.html" not in text:
        errors.append(f"{board}: missing link to release-player.html")
    if "player-presets.md" not in text:
        errors.append(f"{board}: missing link to player-presets.md")
    if "exhibit-loop.md" not in text:
        errors.append(f"{board}: missing link to exhibit-loop.md")
    if "exhibit-programs.json" not in text:
        errors.append(f"{board}: missing link to exhibit-programs.json")
    if "exhibit-cue-sheet.md" not in text:
        errors.append(f"{board}: missing link to exhibit-cue-sheet.md")
    if "exhibit-cue-sheet.json" not in text:
        errors.append(f"{board}: missing link to exhibit-cue-sheet.json")
    if "curatorial-score.md" not in text:
        errors.append(f"{board}: missing link to curatorial-score.md")
    if "curatorial-score.json" not in text:
        errors.append(f"{board}: missing link to curatorial-score.json")
    if "living-loop.md" not in text:
        errors.append(f"{board}: missing link to living-loop.md")
    if "living-loop.json" not in text:
        errors.append(f"{board}: missing link to living-loop.json")
    if "playback-contract.json" not in text:
        errors.append(f"{board}: missing link to playback-contract.json")
    if "composition-atlas.md" not in text:
        errors.append(f"{board}: missing link to composition-atlas.md")
    if "composition-atlas.json" not in text:
        errors.append(f"{board}: missing link to composition-atlas.json")
    if "rhythm-map.md" not in text:
        errors.append(f"{board}: missing link to rhythm-map.md")
    if "rhythm-map.json" not in text:
        errors.append(f"{board}: missing link to rhythm-map.json")
    if "sound-map.md" not in text:
        errors.append(f"{board}: missing link to sound-map.md")
    if "sound-map.json" not in text:
        errors.append(f"{board}: missing link to sound-map.json")
    if "release-matrix.md" not in text:
        errors.append(f"{board}: missing link to release-matrix.md")
    if "release-matrix.json" not in text:
        errors.append(f"{board}: missing link to release-matrix.json")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{board}: missing release media link to {href}")


def validate_release_copy(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    copy_path = site_dir / "release-copy.md"
    if not copy_path.exists():
        errors.append(f"{copy_path}: missing release copy deck")
        return
    try:
        text = copy_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{copy_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-board.html",
        "release-player.html",
        "player-presets.md",
        "release-queue.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "public-manifest.json",
    ):
        if required not in text:
            errors.append(f"{copy_path}: missing link to {required}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{copy_path}: missing release media link to {href}")


def validate_platform_plan(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    plan_path = site_dir / "platform-plan.md"
    if not plan_path.exists():
        errors.append(f"{plan_path}: missing platform plan")
        return
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{plan_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-board.html",
        "release-player.html",
        "player-presets.md",
        "release-queue.md",
        "release-copy.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "public-manifest.json",
    ):
        if required not in text:
            errors.append(f"{plan_path}: missing link to {required}")
    for required in ("Instagram Story", "Instagram Reel", "YouTube Shorts", "GitHub/portfolio", "Product/shop gate"):
        if required not in text:
            errors.append(f"{plan_path}: missing platform/gate marker {required!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{plan_path}: missing release media link to {href}")


def validate_release_queue(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    queue_path = site_dir / "release-queue.md"
    if not queue_path.exists():
        errors.append(f"{queue_path}: missing release queue")
        return
    try:
        text = queue_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{queue_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-board.html",
        "release-player.html",
        "player-presets.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "public-manifest.json",
    ):
        if required not in text:
            errors.append(f"{queue_path}: missing link to {required}")
    for required in ("## Queue", "Instagram Story", "Instagram Reel", "YouTube Shorts", "GitHub/portfolio", "Product/shop gate"):
        if required not in text:
            errors.append(f"{queue_path}: missing queue/platform marker {required!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{queue_path}: missing release media link to {href}")


def validate_release_player(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    player_path = site_dir / "release-player.html"
    if not player_path.exists():
        errors.append(f"{player_path}: missing release player")
        return
    try:
        text = player_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{player_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-board.html",
        "player-presets.md",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "public-manifest.json",
    ):
        if required not in text:
            errors.append(f"{player_path}: missing link to {required}")
    for required in (
        "release-player-data",
        "triptych.release-player.v1",
        "triptych.exhibit-programs.v1",
        "URLSearchParams",
        "data-mode",
        "edition",
        "family",
        "program",
        "programList",
        "applyProgramParams",
        "autoplay",
        "muted",
        "volume",
        "rate",
        "seed",
        "boundedNumber",
        "seededRandomFactory",
        "randomValue",
        "playbackRate",
        "kiosk",
        "data-kiosk",
        "data-fit",
        "contain",
        "Random",
        "Sequential",
    ):
        if required not in text:
            errors.append(f"{player_path}: missing player marker {required!r}")
    match = re.search(
        r'<script id="release-player-data" type="application/json">(.*?)</script>',
        text,
        flags=re.DOTALL,
    )
    if not match:
        errors.append(f"{player_path}: missing release-player-data JSON")
        return
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        errors.append(f"{player_path}: release-player-data is invalid JSON: {error}")
        return
    if not isinstance(data, dict) or data.get("schema") != "triptych.release-player.v1":
        errors.append(f"{player_path}: release-player-data schema is invalid")
        return
    validate_player_presets(player_path, data.get("presets"), site_dir, receipts, "release-player-data.presets", errors)
    if data.get("program_schema") != "triptych.exhibit-programs.v1":
        errors.append(f"{player_path}: release-player-data.program_schema is invalid")
    validate_player_programs(
        player_path,
        data.get("programs"),
        site_dir,
        receipts,
        "release-player-data.programs",
        errors,
    )
    items = data.get("items")
    if not isinstance(items, list):
        errors.append(f"{player_path}: release-player-data.items must be a list")
        return
    expected_hrefs = expected_release_hrefs(receipts)
    if len(items) != len(expected_hrefs):
        errors.append(f"{player_path}: player item count must be {len(expected_hrefs)}")
    actual_hrefs: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"{player_path}: player items[{index}] must be an object")
            continue
        if item.get("position") != index:
            errors.append(f"{player_path}: player items[{index}].position must be {index}")
        for key in ("edition", "work_title", "family", "kind", "name", "label", "phase", "href", "facts"):
            if not isinstance(item.get(key), str) or not item.get(key):
                errors.append(f"{player_path}: player items[{index}].{key} must be a non-empty string")
        targets = item.get("targets")
        if not isinstance(targets, list) or not targets or not all(isinstance(target, str) and target for target in targets):
            errors.append(f"{player_path}: player items[{index}].targets must be a non-empty string list")
        href = item.get("href")
        if isinstance(href, str):
            actual_hrefs.append(href)
        href_path(site_dir, href, f"{player_path}: player items[{index}].href", errors)
    if sorted(actual_hrefs) != expected_hrefs:
        errors.append(f"{player_path}: player hrefs do not match public receipt exports")


def validate_player_presets_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    presets_path = site_dir / "player-presets.md"
    if not presets_path.exists():
        errors.append(f"{presets_path}: missing player presets")
        return
    try:
        text = presets_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{presets_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-player.html",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "public-manifest.json",
        "Playback Controls",
        "volume=0..1",
        "rate=0.25..2",
        "seed=<text>",
        "## Presets",
        "Operating Gates",
    ):
        if required not in text:
            errors.append(f"{presets_path}: missing preset-doc marker {required!r}")
    for href in expected_player_preset_hrefs(receipts):
        if href not in text:
            errors.append(f"{presets_path}: missing player preset link to {href}")


def expected_exhibit_loop_hrefs(receipts: dict[str, dict[str, Any]]) -> list[str]:
    hrefs = [
        f"release-player.html?{urlencode({'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}",
    ]
    families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    for family in families:
        hrefs.append(
            f"release-player.html?{urlencode({'family': family, 'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}"
        )
    for slug in sorted(receipts):
        hrefs.append(
            f"release-player.html?{urlencode({'edition': slug, 'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}"
        )
    return sorted(hrefs)


def validate_exhibit_loop(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    exhibit_path = site_dir / "exhibit-loop.md"
    if not exhibit_path.exists():
        errors.append(f"{exhibit_path}: missing exhibit loop")
        return
    try:
        text = exhibit_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{exhibit_path}: cannot read: {error}")
        return
    for required in (
        "index.html",
        "release-player.html",
        "player-presets.md",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "public-manifest.json",
        "# Triptych Exhibit Loop",
        "## Operating Gates",
        "## Package Snapshot",
        "## Kiosk Programs",
        "## Edition Programs",
        "digital-frame/gallery",
        "verify_package.py",
        "product/shop",
    ):
        if required not in text:
            errors.append(f"{exhibit_path}: missing exhibit marker {required!r}")
    families = {
        str(receipt.get("family"))
        for receipt in receipts.values()
        if isinstance(receipt.get("family"), str) and receipt.get("family")
    }
    if families and "## Family Programs" not in text:
        errors.append(f"{exhibit_path}: missing family programs section")
    for slug in sorted(receipts):
        page = f"editions/{slug}/index.html"
        if page not in text:
            errors.append(f"{exhibit_path}: missing edition page link to {page}")
    for href in expected_exhibit_loop_hrefs(receipts):
        if href not in text:
            errors.append(f"{exhibit_path}: missing kiosk player link to {href}")
        href_path(site_dir, href, f"{exhibit_path}: kiosk href {href}", errors)


def public_release_count(receipt: dict[str, Any]) -> int:
    return len(published_post_exports(receipt)) + len(visual_sketch_exports(receipt))


def expected_program_items(
    receipts: dict[str, dict[str, Any]], *, edition: str = "", family: str = ""
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    position = 0
    for slug in sorted(receipts):
        receipt = receipts[slug]
        receipt_family = str(receipt.get("family") or "")
        for export in [*published_post_exports(receipt), *visual_sketch_exports(receipt)]:
            position += 1
            if edition and slug != edition:
                continue
            if family and receipt_family != family:
                continue
            items.append(
                {
                    "position": position,
                    "edition": slug,
                    "family": receipt_family,
                    "href": f"editions/{slug}/{export['src']}",
                }
            )
    return items


def expected_exhibit_programs(receipts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    expected: dict[str, dict[str, Any]] = {
        "all-kiosk-random-muted": {
            "scope": "all",
            "href": f"release-player.html?{urlencode({'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}",
            "edition_slugs": sorted(receipts),
            "families": families,
            "item_count": sum(public_release_count(receipt) for receipt in receipts.values()),
            "items": expected_program_items(receipts),
        }
    }
    for family in families:
        slugs = sorted(
            slug
            for slug, receipt in receipts.items()
            if isinstance(receipt.get("family"), str) and receipt.get("family") == family
        )
        expected[f"family-{family}-kiosk-random-muted"] = {
            "scope": "family",
            "family": family,
            "href": f"release-player.html?{urlencode({'family': family, 'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}",
            "edition_slugs": slugs,
            "families": [family],
            "item_count": sum(public_release_count(receipts[slug]) for slug in slugs),
            "items": expected_program_items(receipts, family=family),
        }
    for slug, receipt in sorted(receipts.items()):
        family = str(receipt.get("family") or "")
        expected[f"edition-{slug}-kiosk-random-muted"] = {
            "scope": "edition",
            "edition": slug,
            "family": family,
            "href": f"release-player.html?{urlencode({'edition': slug, 'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}",
            "edition_slugs": [slug],
            "families": [family] if family else [],
            "item_count": public_release_count(receipt),
            "items": expected_program_items(receipts, edition=slug),
        }
    return expected


def validate_player_programs(
    source_path: Path,
    programs: Any,
    site_dir: Path,
    receipts: dict[str, dict[str, Any]],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(programs, list):
        errors.append(f"{source_path}: {label} must be a list")
        return
    expected = expected_exhibit_programs(receipts)
    actual_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, program in enumerate(programs, start=1):
        if not isinstance(program, dict):
            errors.append(f"{source_path}: {label}[{index}] must be an object")
            continue
        program_id = program.get("id")
        if not isinstance(program_id, str) or not SAFE_ID_RE.fullmatch(program_id):
            errors.append(f"{source_path}: {label}[{index}].id must be a safe id")
            continue
        if program_id in seen_ids:
            errors.append(f"{source_path}: {label} duplicate id {program_id!r}")
        seen_ids.add(program_id)
        actual_ids.append(program_id)
        spec = expected.get(program_id)
        if spec is None:
            errors.append(f"{source_path}: {label}[{index}] unexpected id {program_id!r}")
            continue
        if not isinstance(program.get("label"), str) or not program.get("label"):
            errors.append(f"{source_path}: {label}[{index}].label must be a non-empty string")
        if program.get("scope") != spec["scope"]:
            errors.append(f"{source_path}: {program_id}.scope must be {spec['scope']}")
        for optional_key in ("edition", "family"):
            if optional_key in spec and program.get(optional_key) != spec[optional_key]:
                errors.append(f"{source_path}: {program_id}.{optional_key} must be {spec[optional_key]}")
        if program.get("mode") != "random":
            errors.append(f"{source_path}: {program_id}.mode must be random")
        for boolean_key in ("muted", "autoplay", "kiosk"):
            if program.get(boolean_key) is not True:
                errors.append(f"{source_path}: {program_id}.{boolean_key} must be true")
        if program.get("href") != spec["href"]:
            errors.append(f"{source_path}: {program_id}.href must be {spec['href']}")
        href_path(site_dir, program.get("href"), f"{source_path}: {program_id}.href", errors)
        if sorted(program.get("edition_slugs") or []) != spec["edition_slugs"]:
            errors.append(f"{source_path}: {program_id}.edition_slugs mismatch")
        if sorted(program.get("families") or []) != spec["families"]:
            errors.append(f"{source_path}: {program_id}.families mismatch")
        if program.get("item_count") != spec["item_count"]:
            errors.append(f"{source_path}: {program_id}.item_count must be {spec['item_count']}")
        items = program.get("items")
        expected_items = spec["items"]
        if not isinstance(items, list):
            errors.append(f"{source_path}: {program_id}.items must be a list")
        else:
            if len(items) != len(expected_items):
                errors.append(f"{source_path}: {program_id}.items length must be {len(expected_items)}")
            actual_hrefs: list[str] = []
            for item_index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    errors.append(f"{source_path}: {program_id}.items[{item_index}] must be an object")
                    continue
                expected_item = expected_items[item_index - 1] if item_index <= len(expected_items) else None
                for key in ("work_title", "kind", "name", "label", "phase", "href", "facts"):
                    if not isinstance(item.get(key), str) or not item.get(key):
                        errors.append(f"{source_path}: {program_id}.items[{item_index}].{key} must be a non-empty string")
                targets = item.get("targets")
                if not isinstance(targets, list) or not targets or not all(isinstance(target, str) and target for target in targets):
                    errors.append(f"{source_path}: {program_id}.items[{item_index}].targets must be a non-empty string list")
                href = item.get("href")
                if isinstance(href, str):
                    actual_hrefs.append(href)
                href_path(site_dir, href, f"{source_path}: {program_id}.items[{item_index}].href", errors)
                if expected_item is None:
                    continue
                for key in ("position", "edition", "family", "href"):
                    if item.get(key) != expected_item[key]:
                        errors.append(
                            f"{source_path}: {program_id}.items[{item_index}].{key} must be {expected_item[key]!r}"
                        )
            expected_hrefs = [item["href"] for item in expected_items]
            if actual_hrefs != expected_hrefs:
                errors.append(f"{source_path}: {program_id}.items href order mismatch")
        if not isinstance(program.get("use"), str) or not program.get("use"):
            errors.append(f"{source_path}: {program_id}.use must be a non-empty string")
    if sorted(actual_ids) != sorted(expected):
        errors.append(f"{source_path}: {label} ids do not match expected exhibit programs")


def validate_exhibit_programs(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    programs_path = site_dir / "exhibit-programs.json"
    if not programs_path.exists():
        errors.append(f"{programs_path}: missing exhibit programs")
        return
    data = load_json(programs_path, errors)
    if data is None:
        return
    if data.get("schema") != "triptych.exhibit-programs.v1":
        errors.append(f"{programs_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("release_player", "release-player.html"),
        ("exhibit_loop", "exhibit-loop.md"),
        ("public_manifest", "public-manifest.json"),
        ("playback_contract", "playback-contract.json"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{programs_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{programs_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public flash-copy receipts":
        errors.append(f"{programs_path}: derived_from must describe sanitized public receipts")
    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{programs_path}: operating_gates must be a non-empty string list")
    programs = data.get("programs")
    if not isinstance(programs, list):
        errors.append(f"{programs_path}: programs must be a list")
        return
    expected = expected_exhibit_programs(receipts)
    if data.get("program_count") != len(expected):
        errors.append(f"{programs_path}: program_count must be {len(expected)}")
    if len(programs) != len(expected):
        errors.append(f"{programs_path}: programs length must be {len(expected)}")
    validate_player_programs(programs_path, programs, site_dir, receipts, "programs", errors)


def validate_exhibit_cue_sheet(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    cue_path = site_dir / "exhibit-cue-sheet.json"
    if not cue_path.exists():
        errors.append(f"{cue_path}: missing exhibit cue sheet")
        return
    data = load_json(cue_path, errors)
    if data is None:
        return
    if data.get("schema") != EXHIBIT_CUE_SHEET_SCHEMA:
        errors.append(f"{cue_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("exhibit_programs", "exhibit-programs.json"),
        ("release_player", "release-player.html"),
        ("rhythm_map", "rhythm-map.json"),
        ("sound_map", "sound-map.json"),
        ("playback_contract", "playback-contract.json"),
        ("exhibit_cue_sheet_doc", "exhibit-cue-sheet.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{cue_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{cue_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public exhibit programs and media facts":
        errors.append(f"{cue_path}: derived_from must describe sanitized public exhibit programs and media facts")

    expected = expected_exhibit_programs(receipts)
    programs_path = site_dir / "exhibit-programs.json"
    programs_data = load_json(programs_path, errors) if programs_path.exists() else None
    source_programs = programs_data.get("programs") if isinstance(programs_data, dict) else []
    source_by_id = {
        program["id"]: program
        for program in source_programs
        if isinstance(program, dict) and isinstance(program.get("id"), str)
    }

    rhythm_path = site_dir / "rhythm-map.json"
    rhythm_data = load_json(rhythm_path, errors) if rhythm_path.exists() else None
    rhythm_items = rhythm_data.get("items") if isinstance(rhythm_data, dict) else []
    rhythm_by_href = {
        item["href"]: item
        for item in rhythm_items
        if isinstance(item, dict) and isinstance(item.get("href"), str)
    }

    if data.get("program_count") != len(expected):
        errors.append(f"{cue_path}: program_count must be {len(expected)}")
    if data.get("total_public_items") != len(rhythm_by_href):
        errors.append(f"{cue_path}: total_public_items must be {len(rhythm_by_href)}")

    programs = data.get("programs")
    if not isinstance(programs, list):
        errors.append(f"{cue_path}: programs must be a list")
        return
    if len(programs) != len(expected):
        errors.append(f"{cue_path}: programs length must be {len(expected)}")
    actual_ids: list[str] = []
    for index, program in enumerate(programs, start=1):
        if not isinstance(program, dict):
            errors.append(f"{cue_path}: programs[{index}] must be an object")
            continue
        program_id = program.get("id")
        if not isinstance(program_id, str) or not SAFE_ID_RE.fullmatch(program_id):
            errors.append(f"{cue_path}: programs[{index}].id must be a safe id")
            continue
        actual_ids.append(program_id)
        spec = expected.get(program_id)
        source = source_by_id.get(program_id)
        if spec is None:
            errors.append(f"{cue_path}: programs[{index}] unexpected id {program_id!r}")
            continue
        if not isinstance(source, dict):
            errors.append(f"{cue_path}: {program_id} must exist in exhibit-programs.json")
            source = {}
        for key in ("label", "scope", "href", "mode", "use"):
            expected_value = source.get(key)
            if program.get(key) != expected_value:
                errors.append(f"{cue_path}: {program_id}.{key} must match exhibit-programs.json")
        for key in ("edition", "family", "edition_slugs", "families"):
            if key in source and program.get(key) != source.get(key):
                errors.append(f"{cue_path}: {program_id}.{key} must match exhibit-programs.json")
        for boolean_key in ("muted", "autoplay", "kiosk"):
            if program.get(boolean_key) is not True:
                errors.append(f"{cue_path}: {program_id}.{boolean_key} must be true")
        href_path(site_dir, program.get("href"), f"{cue_path}: {program_id}.href", errors)

        source_items = source.get("items") if isinstance(source.get("items"), list) else spec["items"]
        items = program.get("items")
        if not isinstance(items, list):
            errors.append(f"{cue_path}: {program_id}.items must be a list")
            continue
        if program.get("item_count") != len(source_items):
            errors.append(f"{cue_path}: {program_id}.item_count must be {len(source_items)}")
        if len(items) != len(source_items):
            errors.append(f"{cue_path}: {program_id}.items length must be {len(source_items)}")
        durations: list[float] = []
        audio_count = 0
        actual_hrefs: list[str] = []
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"{cue_path}: {program_id}.items[{item_index}] must be an object")
                continue
            if item.get("position") != item_index:
                errors.append(f"{cue_path}: {program_id}.items[{item_index}].position must be {item_index}")
            source_item = source_items[item_index - 1] if item_index <= len(source_items) else None
            if isinstance(source_item, dict):
                if item.get("queue_position") != source_item.get("position"):
                    errors.append(f"{cue_path}: {program_id}.items[{item_index}].queue_position must match exhibit program")
                for key in ("edition", "work_title", "family", "kind", "label", "phase", "href"):
                    if item.get(key) != source_item.get(key):
                        errors.append(f"{cue_path}: {program_id}.items[{item_index}].{key} must match exhibit program")
            for key in ("edition", "work_title", "family", "kind", "label", "phase", "href"):
                if not isinstance(item.get(key), str) or not item.get(key):
                    errors.append(f"{cue_path}: {program_id}.items[{item_index}].{key} must be a non-empty string")
            href = item.get("href")
            if isinstance(href, str):
                actual_hrefs.append(href)
            href_path(site_dir, href, f"{cue_path}: {program_id}.items[{item_index}].href", errors)
            rhythm = rhythm_by_href.get(href)
            if rhythm is None:
                errors.append(f"{cue_path}: {program_id}.items[{item_index}].href must exist in rhythm-map.json")
                continue
            expected_duration = rhythm.get("duration_seconds")
            if item.get("duration_seconds") != expected_duration:
                errors.append(f"{cue_path}: {program_id}.items[{item_index}].duration_seconds must match rhythm map")
            duration = numeric_duration(item.get("duration_seconds"))
            if duration is not None:
                durations.append(duration)
            if item.get("has_audio") != (rhythm.get("has_audio") is True):
                errors.append(f"{cue_path}: {program_id}.items[{item_index}].has_audio must match rhythm map")
            if item.get("has_audio") is True:
                audio_count += 1
        expected_hrefs = [source_item["href"] for source_item in source_items if isinstance(source_item, dict)]
        if actual_hrefs != expected_hrefs:
            errors.append(f"{cue_path}: {program_id}.items href order mismatch")
        total = round(sum(durations), 3)
        if program.get("total_duration_seconds") != total:
            errors.append(f"{cue_path}: {program_id}.total_duration_seconds must be {total}")
        if program.get("audio_item_count") != audio_count:
            errors.append(f"{cue_path}: {program_id}.audio_item_count must be {audio_count}")
        if program.get("silent_item_count") != len(items) - audio_count:
            errors.append(f"{cue_path}: {program_id}.silent_item_count must be {len(items) - audio_count}")
    if sorted(actual_ids) != sorted(expected):
        errors.append(f"{cue_path}: program ids must match exhibit-programs.json")

    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{cue_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public exhibit programs", "local player URLs", "No source library", "digital-frame/gallery"):
            if marker not in gate_text:
                errors.append(f"{cue_path}: operating_gates must include {marker!r}")


def validate_exhibit_cue_sheet_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "exhibit-cue-sheet.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing exhibit cue sheet doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Exhibit Cue Sheet",
        "exhibit-cue-sheet.json",
        "exhibit-programs.json",
        "release-player.html",
        "rhythm-map.json",
        "sound-map.json",
        "playback-contract.json",
        "public-manifest.json",
        "## Snapshot",
        "## Operating Gates",
        "## Programs",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing cue-sheet marker {required!r}")
    for program_id, spec in expected_exhibit_programs(receipts).items():
        for required in (program_id, spec["href"]):
            if required and required not in text:
                errors.append(f"{doc_path}: missing exhibit program marker {required!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{doc_path}: missing public cue item link to {href}")


def validate_curatorial_score(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    score_path = site_dir / "curatorial-score.json"
    if not score_path.exists():
        errors.append(f"{score_path}: missing curatorial score")
        return
    data = load_json(score_path, errors)
    if data is None:
        return
    if data.get("schema") != CURATORIAL_SCORE_SCHEMA:
        errors.append(f"{score_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("public_manifest", "public-manifest.json"),
        ("release_player", "release-player.html"),
        ("composition_atlas", "composition-atlas.json"),
        ("rhythm_map", "rhythm-map.json"),
        ("sound_map", "sound-map.json"),
        ("release_matrix", "release-matrix.json"),
        ("exhibit_cue_sheet", "exhibit-cue-sheet.json"),
        ("curatorial_score_doc", "curatorial-score.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{score_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{score_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public composition, rhythm, sound, release, and program facts":
        errors.append(f"{score_path}: derived_from must describe sanitized public facts")

    atlas_path = site_dir / "composition-atlas.json"
    atlas_data = load_json(atlas_path, errors) if atlas_path.exists() else None
    atlas_editions = atlas_data.get("editions") if isinstance(atlas_data, dict) else []
    atlas_by_slug = {
        edition["slug"]: edition
        for edition in atlas_editions
        if isinstance(edition, dict) and isinstance(edition.get("slug"), str)
    }

    rhythm_path = site_dir / "rhythm-map.json"
    rhythm_data = load_json(rhythm_path, errors) if rhythm_path.exists() else None
    rhythm_items = rhythm_data.get("items") if isinstance(rhythm_data, dict) else []
    rhythm_by_edition: dict[str, list[dict[str, Any]]] = {}
    for item in rhythm_items:
        if isinstance(item, dict) and isinstance(item.get("edition"), str):
            rhythm_by_edition.setdefault(item["edition"], []).append(item)

    expected_programs = expected_exhibit_programs(receipts)
    expected_families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    expected_hrefs = expected_release_hrefs(receipts)
    audio_count = sum(1 for item in rhythm_items if isinstance(item, dict) and item.get("has_audio") is True)
    durations = [
        float(item["duration_seconds"])
        for item in rhythm_items
        if isinstance(item, dict) and numeric_duration(item.get("duration_seconds")) is not None
    ]
    if data.get("edition_count") != len(receipts):
        errors.append(f"{score_path}: edition_count must be {len(receipts)}")
    if data.get("family_count") != len(expected_families):
        errors.append(f"{score_path}: family_count must be {len(expected_families)}")
    if data.get("item_count") != len(expected_hrefs):
        errors.append(f"{score_path}: item_count must be {len(expected_hrefs)}")
    if data.get("total_duration_seconds") != round(sum(durations), 3):
        errors.append(f"{score_path}: total_duration_seconds must match rhythm map")
    if data.get("audio_item_count") != audio_count:
        errors.append(f"{score_path}: audio_item_count must be {audio_count}")
    if data.get("silent_item_count") != len(expected_hrefs) - audio_count:
        errors.append(f"{score_path}: silent_item_count must be {len(expected_hrefs) - audio_count}")

    editions = data.get("editions")
    if not isinstance(editions, list):
        errors.append(f"{score_path}: editions must be a list")
        editions = []
    by_slug: dict[str, dict[str, Any]] = {}
    for index, edition in enumerate(editions, start=1):
        if not isinstance(edition, dict):
            errors.append(f"{score_path}: editions[{index}] must be an object")
            continue
        slug = edition.get("slug")
        if not isinstance(slug, str) or slug not in receipts:
            errors.append(f"{score_path}: editions[{index}].slug must match a public receipt")
            continue
        if slug in by_slug:
            errors.append(f"{score_path}: duplicate edition slug {slug!r}")
        by_slug[slug] = edition
        receipt = receipts[slug]
        if edition.get("work_title") != str(receipt.get("work_title") or receipt.get("title") or slug):
            errors.append(f"{score_path}: {slug}.work_title must match public receipt")
        if edition.get("family") != str(receipt.get("family") or ""):
            errors.append(f"{score_path}: {slug}.family must match public receipt")
        expected_page = f"editions/{slug}/index.html"
        if edition.get("page") != expected_page:
            errors.append(f"{score_path}: {slug}.page must be {expected_page}")
        href_path(site_dir, edition.get("page"), f"{score_path}: {slug}.page", errors)
        expected_player = f"release-player.html?{urlencode({'edition': slug})}"
        if edition.get("player") != expected_player:
            errors.append(f"{score_path}: {slug}.player must be {expected_player}")
        href_path(site_dir, edition.get("player"), f"{score_path}: {slug}.player", errors)
        expected_program_id = f"edition-{slug}-kiosk-random-muted"
        expected_program_url = f"release-player.html?{urlencode({'program': expected_program_id})}"
        if edition.get("program") != expected_program_id:
            errors.append(f"{score_path}: {slug}.program must be {expected_program_id}")
        if edition.get("program_url") != expected_program_url:
            errors.append(f"{score_path}: {slug}.program_url must be {expected_program_url}")
        href_path(site_dir, edition.get("program_url"), f"{score_path}: {slug}.program_url", errors)
        expected_program = expected_programs.get(expected_program_id, {})
        if edition.get("kiosk_url") != expected_program.get("href"):
            errors.append(f"{score_path}: {slug}.kiosk_url must match exhibit program href")
        href_path(site_dir, edition.get("kiosk_url"), f"{score_path}: {slug}.kiosk_url", errors)
        if not isinstance(edition.get("curatorial_note"), str) or str(edition.get("work_title")) not in str(edition.get("curatorial_note")):
            errors.append(f"{score_path}: {slug}.curatorial_note must include the work title")

        expected_items = rhythm_by_edition.get(slug, [])
        expected_durations = [
            float(item["duration_seconds"])
            for item in expected_items
            if numeric_duration(item.get("duration_seconds")) is not None
        ]
        expected_audio = sum(1 for item in expected_items if item.get("has_audio") is True)
        if edition.get("item_count") != len(expected_items):
            errors.append(f"{score_path}: {slug}.item_count must be {len(expected_items)}")
        if edition.get("total_duration_seconds") != round(sum(expected_durations), 3):
            errors.append(f"{score_path}: {slug}.total_duration_seconds must match rhythm map")
        if edition.get("audio_item_count") != expected_audio:
            errors.append(f"{score_path}: {slug}.audio_item_count must be {expected_audio}")
        if edition.get("silent_item_count") != len(expected_items) - expected_audio:
            errors.append(f"{score_path}: {slug}.silent_item_count must be {len(expected_items) - expected_audio}")
        expected_targets = sorted(
            {target for item in expected_items for target in item.get("targets", []) if isinstance(target, str)}
        )
        if edition.get("targets") != expected_targets:
            errors.append(f"{score_path}: {slug}.targets must match rhythm/release targets")

        atlas_edition = atlas_by_slug.get(slug, {})
        composition = edition.get("composition")
        atlas_composition = atlas_edition.get("composition") if isinstance(atlas_edition.get("composition"), dict) else {}
        if not isinstance(composition, dict) or not composition:
            errors.append(f"{score_path}: {slug}.composition must be a non-empty object")
            composition = {}
        for key in ("style", "material", "preview_label", "panel_role", "language"):
            if key in atlas_composition and composition.get(key) != atlas_composition.get(key):
                errors.append(f"{score_path}: {slug}.composition.{key} must match composition atlas")
        sketch = edition.get("visual_sketch")
        atlas_sketch = atlas_edition.get("visual_sketch") if isinstance(atlas_edition.get("visual_sketch"), dict) else None
        if atlas_sketch is None:
            if sketch is not None:
                errors.append(f"{score_path}: {slug}.visual_sketch must be null when atlas has none")
        elif not isinstance(sketch, dict) or sketch.get("href") != atlas_sketch.get("href"):
            errors.append(f"{score_path}: {slug}.visual_sketch must match composition atlas")
        elif sketch.get("href"):
            href_path(site_dir, sketch["href"], f"{score_path}: {slug}.visual_sketch.href", errors)

        items = edition.get("items")
        if not isinstance(items, list):
            errors.append(f"{score_path}: {slug}.items must be a list")
            continue
        if len(items) != len(expected_items):
            errors.append(f"{score_path}: {slug}.items length must be {len(expected_items)}")
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"{score_path}: {slug}.items[{item_index}] must be an object")
                continue
            expected_item = expected_items[item_index - 1] if item_index <= len(expected_items) else None
            if expected_item is None:
                continue
            for key in ("position", "kind", "label", "phase", "href", "duration_seconds", "has_audio", "targets"):
                if item.get(key) != expected_item.get(key):
                    errors.append(f"{score_path}: {slug}.items[{item_index}].{key} must match rhythm map")
            href_path(site_dir, item.get("href"), f"{score_path}: {slug}.items[{item_index}].href", errors)
    if set(by_slug) != set(receipts):
        errors.append(f"{score_path}: editions must cover all public receipts")

    families = data.get("families")
    if not isinstance(families, list):
        errors.append(f"{score_path}: families must be a list")
        families = []
    family_by_id = {
        family.get("family"): family
        for family in families
        if isinstance(family, dict) and isinstance(family.get("family"), str)
    }
    if sorted(family_by_id) != expected_families:
        errors.append(f"{score_path}: families must cover public families")
    for family_id in expected_families:
        row = family_by_id.get(family_id)
        if not isinstance(row, dict):
            continue
        slugs = sorted(slug for slug, receipt in receipts.items() if receipt.get("family") == family_id)
        expected_program_id = f"family-{family_id}-kiosk-random-muted"
        expected_program_url = f"release-player.html?{urlencode({'program': expected_program_id})}"
        if row.get("program") != expected_program_id:
            errors.append(f"{score_path}: families.{family_id}.program must be {expected_program_id}")
        if row.get("program_url") != expected_program_url:
            errors.append(f"{score_path}: families.{family_id}.program_url must be {expected_program_url}")
        href_path(site_dir, row.get("program_url"), f"{score_path}: families.{family_id}.program_url", errors)
        if sorted(row.get("edition_slugs") or []) != slugs:
            errors.append(f"{score_path}: families.{family_id}.edition_slugs must match receipts")
        family_editions = [by_slug[slug] for slug in slugs if slug in by_slug]
        if row.get("edition_count") != len(family_editions):
            errors.append(f"{score_path}: families.{family_id}.edition_count must be {len(family_editions)}")
        if row.get("item_count") != sum(int(edition.get("item_count") or 0) for edition in family_editions):
            errors.append(f"{score_path}: families.{family_id}.item_count must match editions")
        expected_total = round(sum(float(edition.get("total_duration_seconds") or 0) for edition in family_editions), 3)
        if row.get("total_duration_seconds") != expected_total:
            errors.append(f"{score_path}: families.{family_id}.total_duration_seconds must match editions")
        if row.get("audio_item_count") != sum(int(edition.get("audio_item_count") or 0) for edition in family_editions):
            errors.append(f"{score_path}: families.{family_id}.audio_item_count must match editions")
        if row.get("silent_item_count") != sum(int(edition.get("silent_item_count") or 0) for edition in family_editions):
            errors.append(f"{score_path}: families.{family_id}.silent_item_count must match editions")

    product_gate = data.get("product_shop_gate")
    if not isinstance(product_gate, dict) or product_gate.get("status") != "deferred":
        errors.append(f"{score_path}: product_shop_gate.status must be deferred")
    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{score_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public composition", "local to the public static package", "public curatorial score", "Product/shop use stays deferred", "No source library"):
            if marker not in gate_text:
                errors.append(f"{score_path}: operating_gates must include {marker!r}")


def validate_curatorial_score_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "curatorial-score.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing curatorial score doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Curatorial Score",
        "index.html",
        "release-player.html",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "curatorial-score.json",
        "public-manifest.json",
        "## Snapshot",
        "## Operating Gates",
        "## Families",
        "## Editions",
        "Product/shop gate: deferred",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing curatorial-score marker {required!r}")
    for slug, receipt in receipts.items():
        work_title = str(receipt.get("work_title") or receipt.get("title") or slug)
        for required in (
            slug,
            work_title,
            f"editions/{slug}/index.html",
            f"release-player.html?{urlencode({'edition': slug})}",
            f"release-player.html?{urlencode({'program': f'edition-{slug}-kiosk-random-muted'})}",
        ):
            if required and required not in text:
                errors.append(f"{doc_path}: missing public edition marker {required!r}")
    for program_id, spec in expected_exhibit_programs(receipts).items():
        if program_id.startswith("family-") and program_id not in text:
            errors.append(f"{doc_path}: missing family program marker {program_id!r}")
        href = spec.get("href")
        if isinstance(href, str) and spec.get("scope") == "edition" and href not in text:
            errors.append(f"{doc_path}: missing edition kiosk href {href!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{doc_path}: missing public item link to {href}")


def expected_living_review_url(program: dict[str, Any], seed: str) -> str:
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
    return f"release-player.html?{urlencode(params)}"


def validate_living_loop(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    loop_path = site_dir / "living-loop.json"
    if not loop_path.exists():
        errors.append(f"{loop_path}: missing living loop")
        return
    data = load_json(loop_path, errors)
    if data is None:
        return
    if data.get("schema") != LIVING_LOOP_SCHEMA:
        errors.append(f"{loop_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("release_player", "release-player.html"),
        ("exhibit_programs", "exhibit-programs.json"),
        ("exhibit_cue_sheet", "exhibit-cue-sheet.json"),
        ("curatorial_score", "curatorial-score.json"),
        ("playback_contract", "playback-contract.json"),
        ("living_loop_doc", "living-loop.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{loop_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{loop_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public exhibit programs and curatorial score":
        errors.append(f"{loop_path}: derived_from must describe sanitized public programs and score")

    cue_path = site_dir / "exhibit-cue-sheet.json"
    cue_data = load_json(cue_path, errors) if cue_path.exists() else None
    cue_programs = cue_data.get("programs") if isinstance(cue_data, dict) else []
    cue_by_id = {
        program["id"]: program
        for program in cue_programs
        if isinstance(program, dict) and isinstance(program.get("id"), str)
    }
    score_path = site_dir / "curatorial-score.json"
    score_data = load_json(score_path, errors) if score_path.exists() else None
    if isinstance(cue_data, dict):
        if data.get("program_count") != cue_data.get("program_count"):
            errors.append(f"{loop_path}: program_count must match exhibit cue sheet")
    if isinstance(score_data, dict):
        for key in ("edition_count", "family_count", "item_count", "total_duration_seconds"):
            if data.get(key) != score_data.get(key):
                errors.append(f"{loop_path}: {key} must match curatorial score")

    expected_programs = list(expected_exhibit_programs(receipts).keys())
    slots = data.get("slots")
    if not isinstance(slots, list):
        errors.append(f"{loop_path}: slots must be a list")
        slots = []
    if data.get("slot_count") != len(expected_programs):
        errors.append(f"{loop_path}: slot_count must be {len(expected_programs)}")
    if len(slots) != len(expected_programs):
        errors.append(f"{loop_path}: slots length must be {len(expected_programs)}")
    if data.get("default_seed") != "living-01-all-kiosk-random-muted":
        errors.append(f"{loop_path}: default_seed is invalid")
    expected_default = f"release-player.html?{urlencode({'program': 'all-kiosk-random-muted', 'seed': 'living-01-all-kiosk-random-muted'})}"
    if data.get("default_url") != expected_default:
        errors.append(f"{loop_path}: default_url must be {expected_default}")
    href_path(site_dir, data.get("default_url"), f"{loop_path}: default_url", errors)

    policy = data.get("seed_policy")
    if not isinstance(policy, dict):
        errors.append(f"{loop_path}: seed_policy must be an object")
    else:
        if policy.get("media_generation") != "none":
            errors.append(f"{loop_path}: seed_policy.media_generation must be none")
        if "seed changes random playback order only" not in str(policy.get("effect") or ""):
            errors.append(f"{loop_path}: seed_policy.effect must describe playback-order-only seed behavior")

    actual_programs: list[str] = []
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            errors.append(f"{loop_path}: slots[{index}] must be an object")
            continue
        expected_program = expected_programs[index - 1] if index <= len(expected_programs) else ""
        program = slot.get("program")
        if program != expected_program:
            errors.append(f"{loop_path}: slots[{index}].program must be {expected_program}")
        if isinstance(program, str):
            actual_programs.append(program)
        cue_program = cue_by_id.get(str(program), {})
        seed = f"living-{index:02d}-{expected_program}"
        expected_slot_id = f"slot-{index:02d}-{expected_program}"
        if slot.get("slot") != index:
            errors.append(f"{loop_path}: slots[{index}].slot must be {index}")
        if slot.get("slot_id") != expected_slot_id:
            errors.append(f"{loop_path}: slots[{index}].slot_id must be {expected_slot_id}")
        if not isinstance(slot.get("slot_id"), str) or not SAFE_ID_RE.fullmatch(str(slot.get("slot_id"))):
            errors.append(f"{loop_path}: slots[{index}].slot_id must be a safe id")
        if slot.get("seed") != seed:
            errors.append(f"{loop_path}: slots[{index}].seed must be {seed}")
        expected_program_url = f"release-player.html?{urlencode({'program': expected_program})}"
        if slot.get("program_url") != expected_program_url:
            errors.append(f"{loop_path}: slots[{index}].program_url must be {expected_program_url}")
        href_path(site_dir, slot.get("program_url"), f"{loop_path}: slots[{index}].program_url", errors)
        expected_seeded = f"release-player.html?{urlencode({'program': expected_program, 'seed': seed})}"
        if slot.get("seeded_kiosk_url") != expected_seeded:
            errors.append(f"{loop_path}: slots[{index}].seeded_kiosk_url must be {expected_seeded}")
        href_path(site_dir, slot.get("seeded_kiosk_url"), f"{loop_path}: slots[{index}].seeded_kiosk_url", errors)
        expected_review = expected_living_review_url(cue_program, seed)
        if slot.get("quiet_review_url") != expected_review:
            errors.append(f"{loop_path}: slots[{index}].quiet_review_url must be {expected_review}")
        href_path(site_dir, slot.get("quiet_review_url"), f"{loop_path}: slots[{index}].quiet_review_url", errors)
        for key in ("label", "scope"):
            if slot.get(key) != cue_program.get(key):
                errors.append(f"{loop_path}: slots[{index}].{key} must match exhibit cue sheet")
        for key in ("item_count", "total_duration_seconds", "audio_item_count", "silent_item_count"):
            if slot.get(key) != cue_program.get(key):
                errors.append(f"{loop_path}: slots[{index}].{key} must match exhibit cue sheet")
        for key in ("edition", "family", "edition_slugs", "families"):
            if key in cue_program and slot.get(key) != cue_program.get(key):
                errors.append(f"{loop_path}: slots[{index}].{key} must match exhibit cue sheet")
        if "no media regeneration" not in str(slot.get("refresh_note") or ""):
            errors.append(f"{loop_path}: slots[{index}].refresh_note must mention no media regeneration")
    if actual_programs != expected_programs:
        errors.append(f"{loop_path}: slots must follow exhibit program order")

    rotations = data.get("rotation_sets")
    if not isinstance(rotations, list):
        errors.append(f"{loop_path}: rotation_sets must be a list")
        rotations = []
    if len(rotations) != len(LIVING_ROTATION_PROFILES):
        errors.append(f"{loop_path}: rotation_sets length must be {len(LIVING_ROTATION_PROFILES)}")
    for rotation_index, profile in enumerate(LIVING_ROTATION_PROFILES):
        if rotation_index >= len(rotations) or not isinstance(rotations[rotation_index], dict):
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}] must be an object")
            continue
        rotation = rotations[rotation_index]
        profile_id, label, volume, rate = profile
        if rotation.get("id") != profile_id:
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].id must be {profile_id}")
        if rotation.get("label") != label:
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].label must be {label}")
        if rotation.get("volume") != volume:
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].volume must be {volume}")
        if rotation.get("rate") != rate:
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].rate must be {rate}")
        if rotation.get("media_generation") != "none":
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].media_generation must be none")
        if not isinstance(rotation.get("note"), str) or not rotation.get("note"):
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].note must be a non-empty string")
        rotation_slots = rotation.get("slots")
        if not isinstance(rotation_slots, list):
            errors.append(f"{loop_path}: rotation_sets[{rotation_index}].slots must be a list")
            rotation_slots = []
        if len(rotation_slots) != len(expected_programs):
            errors.append(
                f"{loop_path}: rotation_sets[{rotation_index}].slots length must be {len(expected_programs)}"
            )
        for slot_index, entry in enumerate(rotation_slots, start=1):
            if not isinstance(entry, dict):
                errors.append(f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}] must be an object")
                continue
            expected_program = expected_programs[slot_index - 1] if slot_index <= len(expected_programs) else ""
            seed = f"{profile_id}-{slot_index:02d}-{expected_program}"
            expected_href = f"release-player.html?{urlencode({'program': expected_program, 'mode': 'random', 'muted': '0', 'volume': volume, 'rate': rate, 'seed': seed})}"
            if entry.get("slot") != slot_index:
                errors.append(f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}].slot must be {slot_index}")
            if entry.get("program") != expected_program:
                errors.append(
                    f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}].program must be {expected_program}"
                )
            if entry.get("seed") != seed:
                errors.append(f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}].seed must be {seed}")
            if entry.get("href") != expected_href:
                errors.append(f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}].href must be {expected_href}")
            href_path(site_dir, entry.get("href"), f"{loop_path}: rotation_sets[{rotation_index}].slots[{slot_index}].href", errors)

    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{loop_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in (
            "sanitized public exhibit programs",
            "local player URLs",
            "no media generation",
            "Rotation sets",
            "No source library",
            "living loop",
        ):
            if marker not in gate_text:
                errors.append(f"{loop_path}: operating_gates must include {marker!r}")


def validate_living_loop_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "living-loop.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing living loop doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Living Loop",
        "release-player.html",
        "exhibit-programs.json",
        "exhibit-cue-sheet.json",
        "curatorial-score.json",
        "playback-contract.json",
        "living-loop.json",
        "public-manifest.json",
        "## Snapshot",
        "## Operating Gates",
        "## Rotation Sets",
        "## Slots",
        "seed changes random playback order only",
        "Media generation: none",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing living-loop marker {required!r}")
    for profile_id, label, volume, rate in LIVING_ROTATION_PROFILES:
        for required in (profile_id, label, f"Volume: {volume}", f"Rate: {rate}"):
            if required not in text:
                errors.append(f"{doc_path}: missing living rotation marker {required!r}")
    for index, program_id in enumerate(expected_exhibit_programs(receipts), start=1):
        seed = f"living-{index:02d}-{program_id}"
        for required in (
            program_id,
            seed,
            f"release-player.html?{urlencode({'program': program_id, 'seed': seed})}",
        ):
            if required not in text:
                errors.append(f"{doc_path}: missing living slot marker {required!r}")
        for profile_id, _label, volume, rate in LIVING_ROTATION_PROFILES:
            rotation_seed = f"{profile_id}-{index:02d}-{program_id}"
            rotation_href = f"release-player.html?{urlencode({'program': program_id, 'mode': 'random', 'muted': '0', 'volume': volume, 'rate': rate, 'seed': rotation_seed})}"
            for required in (rotation_seed, rotation_href):
                if required not in text:
                    errors.append(f"{doc_path}: missing living rotation slot marker {required!r}")


def validate_playback_contract(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    contract_path = site_dir / "playback-contract.json"
    if not contract_path.exists():
        errors.append(f"{contract_path}: missing playback contract")
        return
    data = load_json(contract_path, errors)
    if data is None:
        return
    if data.get("schema") != PLAYBACK_CONTRACT_SCHEMA:
        errors.append(f"{contract_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("release_player", "release-player.html"),
        ("public_manifest", "public-manifest.json"),
        ("exhibit_programs", "exhibit-programs.json"),
        ("player_presets", "player-presets.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{contract_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{contract_path}: {key}", errors)

    params = data.get("allowed_params")
    if not isinstance(params, list):
        errors.append(f"{contract_path}: allowed_params must be a list")
        params = []
    by_name: dict[str, dict[str, Any]] = {}
    for index, param in enumerate(params, start=1):
        if not isinstance(param, dict):
            errors.append(f"{contract_path}: allowed_params[{index}] must be an object")
            continue
        name = param.get("name")
        if not isinstance(name, str) or not SAFE_ID_RE.fullmatch(name):
            errors.append(f"{contract_path}: allowed_params[{index}].name must be a safe id")
            continue
        if name in by_name:
            errors.append(f"{contract_path}: duplicate allowed param {name!r}")
            continue
        by_name[name] = param
        if not isinstance(param.get("type"), str) or not param.get("type"):
            errors.append(f"{contract_path}: allowed_params[{index}].type must be a non-empty string")
        if not isinstance(param.get("effect"), str) or not param.get("effect"):
            errors.append(f"{contract_path}: allowed_params[{index}].effect must be a non-empty string")

    expected_names = {
        "program",
        "edition",
        "family",
        "mode",
        "seed",
        "start",
        "muted",
        "autoplay",
        "kiosk",
        "fit",
        "volume",
        "rate",
    }
    if set(by_name) != expected_names:
        errors.append(f"{contract_path}: allowed_params must be {sorted(expected_names)}")

    expected_editions = sorted(receipts)
    expected_families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    expected_programs = expected_exhibit_programs(receipts)
    expected_checks = {
        "edition": ("enum", expected_editions),
        "family": ("enum", expected_families),
        "mode": ("enum", ["sequential", "random"]),
        "fit": ("enum", ["cover", "contain"]),
    }
    for name, (expected_type, expected_values) in expected_checks.items():
        param = by_name.get(name)
        if not param:
            continue
        if param.get("type") != expected_type:
            errors.append(f"{contract_path}: {name}.type must be {expected_type}")
        if param.get("values") != expected_values:
            errors.append(f"{contract_path}: {name}.values must be {expected_values}")
    for name in ("muted", "autoplay", "kiosk"):
        param = by_name.get(name)
        if not param:
            continue
        if param.get("type") != "boolean":
            errors.append(f"{contract_path}: {name}.type must be boolean")
        if param.get("true_values") != ["1", "true", "yes"]:
            errors.append(f"{contract_path}: {name}.true_values must be ['1', 'true', 'yes']")
    if by_name.get("program", {}).get("type") != "id":
        errors.append(f"{contract_path}: program.type must be id")
    if "exhibit-programs.json" not in str(by_name.get("program", {}).get("source") or ""):
        errors.append(f"{contract_path}: program.source must cite exhibit-programs.json")
    if by_name.get("seed", {}).get("type") != "text":
        errors.append(f"{contract_path}: seed.type must be text")
    if by_name.get("start", {}).get("type") != "integer" or by_name.get("start", {}).get("min") != 1:
        errors.append(f"{contract_path}: start must be an integer with min 1")
    for name, minimum, maximum in (("volume", 0, 1), ("rate", 0.25, 2)):
        param = by_name.get(name)
        if not param:
            continue
        if param.get("type") != "number":
            errors.append(f"{contract_path}: {name}.type must be number")
        if param.get("min") != minimum or param.get("max") != maximum:
            errors.append(f"{contract_path}: {name} bounds must be {minimum}..{maximum}")

    examples = data.get("examples")
    if not isinstance(examples, list) or len(examples) < 3:
        errors.append(f"{contract_path}: examples must include at least three URLs")
        examples = []
    example_hrefs: list[str] = []
    for index, example in enumerate(examples, start=1):
        if not isinstance(example, dict):
            errors.append(f"{contract_path}: examples[{index}] must be an object")
            continue
        if not isinstance(example.get("label"), str) or not example.get("label"):
            errors.append(f"{contract_path}: examples[{index}].label must be a non-empty string")
        href = example.get("href")
        if isinstance(href, str):
            example_hrefs.append(href)
        href_path(site_dir, href, f"{contract_path}: examples[{index}].href", errors)
    if not any("seed=" in href for href in example_hrefs):
        errors.append(f"{contract_path}: examples must include a seeded random URL")
    if not any("volume=0.35" in href and "rate=0.75" in href for href in example_hrefs):
        errors.append(f"{contract_path}: examples must include bounded volume/rate URL")

    counts = data.get("counts")
    if not isinstance(counts, dict):
        errors.append(f"{contract_path}: counts must be an object")
        counts = {}
    expected_counts = {
        "editions": len(expected_editions),
        "families": len(expected_families),
        "presets": len(expected_player_preset_hrefs(receipts)),
        "programs": len(expected_programs),
    }
    for key, expected_value in expected_counts.items():
        if counts.get(key) != expected_value:
            errors.append(f"{contract_path}: counts.{key} must be {expected_value}")

    gates = data.get("gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{contract_path}: gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("Static browser controls only", "sanitized public flash-copy", "No private Photos paths"):
            if marker not in gate_text:
                errors.append(f"{contract_path}: gates must include {marker!r}")


def validate_composition_atlas(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    atlas_path = site_dir / "composition-atlas.json"
    if not atlas_path.exists():
        errors.append(f"{atlas_path}: missing composition atlas")
        return
    data = load_json(atlas_path, errors)
    if data is None:
        return
    if data.get("schema") != COMPOSITION_ATLAS_SCHEMA:
        errors.append(f"{atlas_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("public_manifest", "public-manifest.json"),
        ("release_player", "release-player.html"),
        ("exhibit_programs", "exhibit-programs.json"),
        ("playback_contract", "playback-contract.json"),
        ("composition_atlas_doc", "composition-atlas.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{atlas_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{atlas_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public flash-copy receipts":
        errors.append(f"{atlas_path}: derived_from must describe sanitized public receipts")

    families = data.get("families")
    if not isinstance(families, list):
        errors.append(f"{atlas_path}: families must be a list")
        families = []
    editions = data.get("editions")
    if not isinstance(editions, list):
        errors.append(f"{atlas_path}: editions must be a list")
        editions = []
    expected_families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    if data.get("edition_count") != len(receipts):
        errors.append(f"{atlas_path}: edition_count must be {len(receipts)}")
    if data.get("family_count") != len(expected_families):
        errors.append(f"{atlas_path}: family_count must be {len(expected_families)}")
    if len(editions) != len(receipts):
        errors.append(f"{atlas_path}: editions length must be {len(receipts)}")
    if len(families) != len(expected_families):
        errors.append(f"{atlas_path}: families length must be {len(expected_families)}")

    family_ids: set[str] = set()
    for index, family in enumerate(families, start=1):
        if not isinstance(family, dict):
            errors.append(f"{atlas_path}: families[{index}] must be an object")
            continue
        family_id = family.get("family")
        if not isinstance(family_id, str) or family_id not in expected_families:
            errors.append(f"{atlas_path}: families[{index}].family must match a public family")
            continue
        family_ids.add(family_id)
        expected_slugs = sorted(
            slug
            for slug, receipt in receipts.items()
            if receipt.get("family") == family_id
        )
        if sorted(family.get("edition_slugs") or []) != expected_slugs:
            errors.append(f"{atlas_path}: families[{index}].edition_slugs must match public receipts")
        program = family.get("program")
        expected_program = f"release-player.html?program=family-{family_id}-kiosk-random-muted"
        if program != expected_program:
            errors.append(f"{atlas_path}: families[{index}].program must be {expected_program}")
        href_path(site_dir, program, f"{atlas_path}: families[{index}].program", errors)
        style_counts = family.get("style_counts")
        if not isinstance(style_counts, dict) or not style_counts:
            errors.append(f"{atlas_path}: families[{index}].style_counts must be a non-empty object")
    if family_ids != set(expected_families):
        errors.append(f"{atlas_path}: families must cover all public families")

    seen_slugs: set[str] = set()
    for index, edition in enumerate(editions, start=1):
        if not isinstance(edition, dict):
            errors.append(f"{atlas_path}: editions[{index}] must be an object")
            continue
        slug = edition.get("slug")
        if not isinstance(slug, str) or slug not in receipts:
            errors.append(f"{atlas_path}: editions[{index}].slug must match a public receipt")
            continue
        if slug in seen_slugs:
            errors.append(f"{atlas_path}: duplicate edition slug {slug!r}")
        seen_slugs.add(slug)
        receipt = receipts[slug]
        for key in ("title", "work_title", "family"):
            if edition.get(key) != receipt.get(key):
                errors.append(f"{atlas_path}: editions[{index}].{key} must match public receipt")
        page = f"editions/{slug}/index.html"
        if edition.get("page") != page:
            errors.append(f"{atlas_path}: editions[{index}].page must be {page}")
        href_path(site_dir, edition.get("page"), f"{atlas_path}: editions[{index}].page", errors)
        expected_player = f"release-player.html?{urlencode({'edition': slug})}"
        if edition.get("player") != expected_player:
            errors.append(f"{atlas_path}: editions[{index}].player must be {expected_player}")
        href_path(site_dir, edition.get("player"), f"{atlas_path}: editions[{index}].player", errors)
        composition = edition.get("composition")
        if not isinstance(composition, dict) or not composition:
            errors.append(f"{atlas_path}: editions[{index}].composition must be a non-empty object")
            composition = {}
        for key in ("work_title", "family", "style", "material", "panel_role", "preview_label"):
            if not isinstance(composition.get(key), str) or not composition.get(key):
                errors.append(f"{atlas_path}: editions[{index}].composition.{key} must be a non-empty string")
        language = composition.get("language")
        if not isinstance(language, list) or not language or not all(isinstance(item, str) and item for item in language):
            errors.append(f"{atlas_path}: editions[{index}].composition.language must be a non-empty string list")
        if "cell_count" in composition and (not isinstance(composition["cell_count"], int) or isinstance(composition["cell_count"], bool)):
            errors.append(f"{atlas_path}: editions[{index}].composition.cell_count must be an integer")
        counts = edition.get("counts")
        if not isinstance(counts, dict):
            errors.append(f"{atlas_path}: editions[{index}].counts must be an object")
            counts = {}
        receipt_counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
        if counts.get("clips") != int(receipt_counts.get("visible_clips") or receipt_counts.get("manifest_clips") or 0):
            errors.append(f"{atlas_path}: editions[{index}].counts.clips must match public receipt")
        sketch = edition.get("visual_sketch")
        if sketch is not None:
            if not isinstance(sketch, dict):
                errors.append(f"{atlas_path}: editions[{index}].visual_sketch must be an object")
            else:
                href_path(site_dir, sketch.get("href"), f"{atlas_path}: editions[{index}].visual_sketch.href", errors)
        post_exports = edition.get("post_exports")
        if not isinstance(post_exports, list):
            errors.append(f"{atlas_path}: editions[{index}].post_exports must be a list")
            post_exports = []
        for export_index, export in enumerate(post_exports, start=1):
            if not isinstance(export, dict):
                errors.append(f"{atlas_path}: editions[{index}].post_exports[{export_index}] must be an object")
                continue
            href_path(
                site_dir,
                export.get("href"),
                f"{atlas_path}: editions[{index}].post_exports[{export_index}].href",
                errors,
            )
    if seen_slugs != set(receipts):
        errors.append(f"{atlas_path}: editions must cover all public receipts")

    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{atlas_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public flash-copy", "No source library", "public composition index"):
            if marker not in gate_text:
                errors.append(f"{atlas_path}: operating_gates must include {marker!r}")


def validate_composition_atlas_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "composition-atlas.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing composition atlas doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Composition Atlas",
        "index.html",
        "release-player.html",
        "player-presets.md",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "public-manifest.json",
        "composition-atlas.json",
        "rhythm-map.md",
        "rhythm-map.json",
        "sound-map.md",
        "sound-map.json",
        "release-matrix.md",
        "release-matrix.json",
        "## Families",
        "## Editions",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing atlas-doc marker {required!r}")
    for slug, receipt in receipts.items():
        for required in (
            slug,
            str(receipt.get("work_title") or ""),
            f"editions/{slug}/index.html",
            f"release-player.html?{urlencode({'edition': slug})}",
        ):
            if required and required not in text:
                errors.append(f"{doc_path}: missing public edition marker {required!r}")


def numeric_duration(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value < 0:
        return None
    return round(float(value), 3)


def rhythm_group_summary(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        value = item.get(key)
        if isinstance(value, str) and value:
            grouped.setdefault(value, []).append(item)
    summary: dict[str, dict[str, Any]] = {}
    for value, group_items in grouped.items():
        durations = [
            float(item["duration_seconds"])
            for item in group_items
            if numeric_duration(item.get("duration_seconds")) is not None
        ]
        summary[value] = {
            key: value,
            "item_count": len(group_items),
            "audio_items": sum(1 for item in group_items if item.get("has_audio") is True),
            "total_duration_seconds": round(sum(durations), 3),
            "min_duration_seconds": round(min(durations), 3) if durations else None,
            "max_duration_seconds": round(max(durations), 3) if durations else None,
        }
    return summary


def validate_rhythm_summary_rows(
    source_path: Path,
    rows: Any,
    expected: dict[str, dict[str, Any]],
    key: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(rows, list):
        errors.append(f"{source_path}: {label} must be a list")
        return
    actual: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"{source_path}: {label}[{index}] must be an object")
            continue
        value = row.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{source_path}: {label}[{index}].{key} must be a non-empty string")
            continue
        actual[value] = row
    if set(actual) != set(expected):
        errors.append(f"{source_path}: {label} keys must match rhythm items")
        return
    for value, expected_row in expected.items():
        row = actual[value]
        for field, expected_value in expected_row.items():
            if row.get(field) != expected_value:
                errors.append(f"{source_path}: {label}.{value}.{field} must be {expected_value}")


def validate_rhythm_map(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    rhythm_path = site_dir / "rhythm-map.json"
    if not rhythm_path.exists():
        errors.append(f"{rhythm_path}: missing rhythm map")
        return
    data = load_json(rhythm_path, errors)
    if data is None:
        return
    if data.get("schema") != RHYTHM_MAP_SCHEMA:
        errors.append(f"{rhythm_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("public_manifest", "public-manifest.json"),
        ("release_player", "release-player.html"),
        ("exhibit_programs", "exhibit-programs.json"),
        ("playback_contract", "playback-contract.json"),
        ("composition_atlas", "composition-atlas.json"),
        ("rhythm_map_doc", "rhythm-map.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{rhythm_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{rhythm_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public media facts":
        errors.append(f"{rhythm_path}: derived_from must describe sanitized public media facts")
    items = data.get("items")
    if not isinstance(items, list):
        errors.append(f"{rhythm_path}: items must be a list")
        return
    expected_hrefs = expected_release_hrefs(receipts)
    if data.get("item_count") != len(expected_hrefs):
        errors.append(f"{rhythm_path}: item_count must be {len(expected_hrefs)}")
    if len(items) != len(expected_hrefs):
        errors.append(f"{rhythm_path}: items length must be {len(expected_hrefs)}")

    actual_hrefs: list[str] = []
    durations: list[float] = []
    audio_count = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"{rhythm_path}: items[{index}] must be an object")
            continue
        if item.get("position") != index:
            errors.append(f"{rhythm_path}: items[{index}].position must be {index}")
        edition = item.get("edition")
        if not isinstance(edition, str) or edition not in receipts:
            errors.append(f"{rhythm_path}: items[{index}].edition must match a public receipt")
            receipt = {}
        else:
            receipt = receipts[edition]
            if item.get("family") != receipt.get("family"):
                errors.append(f"{rhythm_path}: items[{index}].family must match receipt family")
            if item.get("work_title") != receipt.get("work_title"):
                errors.append(f"{rhythm_path}: items[{index}].work_title must match receipt work_title")
        for key in ("kind", "label", "phase", "href"):
            if not isinstance(item.get(key), str) or not item.get(key):
                errors.append(f"{rhythm_path}: items[{index}].{key} must be a non-empty string")
        href = item.get("href")
        if isinstance(href, str):
            actual_hrefs.append(href)
        href_path(site_dir, href, f"{rhythm_path}: items[{index}].href", errors)
        duration = numeric_duration(item.get("duration_seconds"))
        if duration is None:
            errors.append(f"{rhythm_path}: items[{index}].duration_seconds must be a non-negative number")
        else:
            durations.append(duration)
        if not isinstance(item.get("has_audio"), bool):
            errors.append(f"{rhythm_path}: items[{index}].has_audio must be boolean")
        elif item.get("has_audio") is True:
            audio_count += 1
        if not isinstance(item.get("size_bytes"), int) or isinstance(item.get("size_bytes"), bool) or item.get("size_bytes") < 0:
            errors.append(f"{rhythm_path}: items[{index}].size_bytes must be a non-negative integer")
        targets = item.get("targets")
        if not isinstance(targets, list) or not targets or not all(isinstance(target, str) and target for target in targets):
            errors.append(f"{rhythm_path}: items[{index}].targets must be a non-empty string list")
    if sorted(actual_hrefs) != expected_hrefs:
        errors.append(f"{rhythm_path}: item hrefs must match public release hrefs")
    if data.get("audio_item_count") != audio_count:
        errors.append(f"{rhythm_path}: audio_item_count must be {audio_count}")
    total = round(sum(durations), 3)
    if data.get("total_duration_seconds") != total:
        errors.append(f"{rhythm_path}: total_duration_seconds must be {total}")
    if durations:
        if data.get("min_duration_seconds") != round(min(durations), 3):
            errors.append(f"{rhythm_path}: min_duration_seconds must match item durations")
        if data.get("max_duration_seconds") != round(max(durations), 3):
            errors.append(f"{rhythm_path}: max_duration_seconds must match item durations")
    validate_rhythm_summary_rows(rhythm_path, data.get("families"), rhythm_group_summary(items, "family"), "family", "families", errors)
    validate_rhythm_summary_rows(rhythm_path, data.get("editions"), rhythm_group_summary(items, "edition"), "edition", "editions", errors)
    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{rhythm_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public media facts", "not private source clips", "public cadence score"):
            if marker not in gate_text:
                errors.append(f"{rhythm_path}: operating_gates must include {marker!r}")


def validate_rhythm_map_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "rhythm-map.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing rhythm map doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Rhythm Map",
        "index.html",
        "release-player.html",
        "player-presets.md",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "composition-atlas.json",
        "public-manifest.json",
        "rhythm-map.json",
        "## Cadence Snapshot",
        "## Families",
        "## Editions",
        "## Queue",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing rhythm-doc marker {required!r}")
    for slug, receipt in receipts.items():
        for required in (slug, str(receipt.get("work_title") or "")):
            if required and required not in text:
                errors.append(f"{doc_path}: missing public rhythm marker {required!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{doc_path}: missing rhythm item link to {href}")


def sound_group_summary_expected(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        value = item.get(key)
        if isinstance(value, str) and value:
            grouped.setdefault(value, []).append(item)
    summary: dict[str, dict[str, Any]] = {}
    for value, group_items in grouped.items():
        audio_items = [item for item in group_items if item.get("has_audio") is True]
        silent_items = [item for item in group_items if item.get("has_audio") is not True]
        audio_durations = [
            float(item["duration_seconds"])
            for item in audio_items
            if numeric_duration(item.get("duration_seconds")) is not None
        ]
        silent_durations = [
            float(item["duration_seconds"])
            for item in silent_items
            if numeric_duration(item.get("duration_seconds")) is not None
        ]
        summary[value] = {
            key: value,
            "item_count": len(group_items),
            "audio_items": len(audio_items),
            "silent_items": len(silent_items),
            "audio_duration_seconds": round(sum(audio_durations), 3),
            "silent_duration_seconds": round(sum(silent_durations), 3),
        }
    return summary


def validate_sound_summary_rows(
    source_path: Path,
    rows: Any,
    expected: dict[str, dict[str, Any]],
    key: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(rows, list):
        errors.append(f"{source_path}: {label} must be a list")
        return
    actual: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"{source_path}: {label}[{index}] must be an object")
            continue
        value = row.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{source_path}: {label}[{index}].{key} must be a non-empty string")
            continue
        actual[value] = row
    if set(actual) != set(expected):
        errors.append(f"{source_path}: {label} keys must match sound items")
        return
    for value, expected_row in expected.items():
        row = actual[value]
        for field, expected_value in expected_row.items():
            if row.get(field) != expected_value:
                errors.append(f"{source_path}: {label}.{value}.{field} must be {expected_value}")


def validate_sound_map(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    sound_path = site_dir / "sound-map.json"
    if not sound_path.exists():
        errors.append(f"{sound_path}: missing sound map")
        return
    data = load_json(sound_path, errors)
    if data is None:
        return
    if data.get("schema") != SOUND_MAP_SCHEMA:
        errors.append(f"{sound_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("public_manifest", "public-manifest.json"),
        ("release_player", "release-player.html"),
        ("playback_contract", "playback-contract.json"),
        ("rhythm_map", "rhythm-map.json"),
        ("sound_map_doc", "sound-map.md"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{sound_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{sound_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public media facts":
        errors.append(f"{sound_path}: derived_from must describe sanitized public media facts")
    controls = data.get("controls")
    if not isinstance(controls, dict):
        errors.append(f"{sound_path}: controls must be an object")
        controls = {}
    if controls.get("browser_only") != ["muted", "volume", "rate"]:
        errors.append(f"{sound_path}: controls.browser_only must be ['muted', 'volume', 'rate']")
    for key in ("quiet_review", "muted_kiosk", "seeded_audio_review"):
        href_path(site_dir, controls.get(key), f"{sound_path}: controls.{key}", errors)
    if "volume=0.35" not in str(controls.get("quiet_review") or "") or "rate=0.75" not in str(controls.get("quiet_review") or ""):
        errors.append(f"{sound_path}: controls.quiet_review must include bounded volume/rate")
    if "muted=1" not in str(controls.get("muted_kiosk") or ""):
        errors.append(f"{sound_path}: controls.muted_kiosk must be muted")
    if "seed=sound-map" not in str(controls.get("seeded_audio_review") or ""):
        errors.append(f"{sound_path}: controls.seeded_audio_review must include seed=sound-map")

    items = data.get("items")
    if not isinstance(items, list):
        errors.append(f"{sound_path}: items must be a list")
        return
    expected_hrefs = expected_release_hrefs(receipts)
    if data.get("item_count") != len(expected_hrefs):
        errors.append(f"{sound_path}: item_count must be {len(expected_hrefs)}")
    if len(items) != len(expected_hrefs):
        errors.append(f"{sound_path}: items length must be {len(expected_hrefs)}")
    actual_hrefs: list[str] = []
    audio_count = 0
    silent_count = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"{sound_path}: items[{index}] must be an object")
            continue
        if item.get("position") != index:
            errors.append(f"{sound_path}: items[{index}].position must be {index}")
        edition = item.get("edition")
        if not isinstance(edition, str) or edition not in receipts:
            errors.append(f"{sound_path}: items[{index}].edition must match a public receipt")
            receipt = {}
        else:
            receipt = receipts[edition]
            if item.get("family") != receipt.get("family"):
                errors.append(f"{sound_path}: items[{index}].family must match receipt family")
            if item.get("work_title") != receipt.get("work_title"):
                errors.append(f"{sound_path}: items[{index}].work_title must match receipt work_title")
        for key in ("kind", "label", "phase", "href", "sound_role", "playback_note"):
            if not isinstance(item.get(key), str) or not item.get(key):
                errors.append(f"{sound_path}: items[{index}].{key} must be a non-empty string")
        href = item.get("href")
        if isinstance(href, str):
            actual_hrefs.append(href)
        href_path(site_dir, href, f"{sound_path}: items[{index}].href", errors)
        if numeric_duration(item.get("duration_seconds")) is None:
            errors.append(f"{sound_path}: items[{index}].duration_seconds must be a non-negative number")
        if not isinstance(item.get("has_audio"), bool):
            errors.append(f"{sound_path}: items[{index}].has_audio must be boolean")
        elif item.get("has_audio") is True:
            audio_count += 1
            if item.get("sound_role") != "audio-bearing post export":
                errors.append(f"{sound_path}: items[{index}].sound_role must describe audio-bearing export")
        else:
            silent_count += 1
            if item.get("sound_role") != "silent visual sketch":
                errors.append(f"{sound_path}: items[{index}].sound_role must describe silent sketch")
        if "no source audio mutation" not in str(item.get("playback_note") or ""):
            errors.append(f"{sound_path}: items[{index}].playback_note must keep source audio immutable")
    if sorted(actual_hrefs) != expected_hrefs:
        errors.append(f"{sound_path}: item hrefs must match public release hrefs")
    if data.get("audio_item_count") != audio_count:
        errors.append(f"{sound_path}: audio_item_count must be {audio_count}")
    if data.get("silent_item_count") != silent_count:
        errors.append(f"{sound_path}: silent_item_count must be {silent_count}")
    validate_sound_summary_rows(sound_path, data.get("families"), sound_group_summary_expected(items, "family"), "family", "families", errors)
    validate_sound_summary_rows(sound_path, data.get("editions"), sound_group_summary_expected(items, "edition"), "edition", "editions", errors)
    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{sound_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public media facts", "not private source clips", "do not mutate source media"):
            if marker not in gate_text:
                errors.append(f"{sound_path}: operating_gates must include {marker!r}")


def validate_sound_map_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "sound-map.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing sound map doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Sound Map",
        "index.html",
        "release-player.html",
        "player-presets.md",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "exhibit-loop.md",
        "exhibit-programs.json",
        "exhibit-cue-sheet.md",
        "exhibit-cue-sheet.json",
        "curatorial-score.md",
        "curatorial-score.json",
        "living-loop.md",
        "living-loop.json",
        "playback-contract.json",
        "composition-atlas.md",
        "rhythm-map.md",
        "public-manifest.json",
        "sound-map.json",
        "## Sound Snapshot",
        "## Families",
        "## Editions",
        "## Queue",
        "Quiet review",
        "Muted kiosk",
        "Seeded audio review",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing sound-doc marker {required!r}")
    for slug, receipt in receipts.items():
        for required in (slug, str(receipt.get("work_title") or "")):
            if required and required not in text:
                errors.append(f"{doc_path}: missing public sound marker {required!r}")
    for href in expected_release_hrefs(receipts):
        if href not in text:
            errors.append(f"{doc_path}: missing sound item link to {href}")


def expected_release_matrix_items(
    receipts: dict[str, dict[str, Any]],
    audio_by_href: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    items = []
    position = 0
    for slug in sorted(receipts):
        receipt = receipts[slug]
        work_title = str(receipt.get("work_title") or receipt.get("title") or slug)
        family = str(receipt.get("family") or "")
        exports = receipt.get("exports")
        if not isinstance(exports, list):
            continue
        for export in exports:
            if not isinstance(export, dict) or export.get("exists") is not True:
                continue
            layout = export.get("layout")
            if layout not in POSTABLE_LAYOUTS and layout != "visual-sketch":
                continue
            published = export.get("published") is True
            if layout in POSTABLE_LAYOUTS and not published:
                continue
            href = export.get("src")
            if not isinstance(href, str) or not href:
                continue
            position += 1
            if layout == "visual-sketch":
                kind = "Sketch"
                label = "Visual sketch"
                targets = ["GitHub/portfolio context", "process post"]
            elif layout == "story":
                kind = "Post"
                label = "Story"
                targets = ["Instagram Story", "YouTube Shorts draft", "portfolio teaser"]
            else:
                kind = "Post"
                label = f"{str(layout).title()} Reel"
                targets = ["Instagram Reel", "YouTube Shorts draft", "panel excerpt"]
            public_href = f"editions/{slug}/{href}"
            items.append(
                {
                    "position": position,
                    "edition": slug,
                    "work_title": work_title,
                    "family": family,
                    "kind": kind,
                    "label": label,
                    "href": public_href,
                    "targets": targets,
                    "has_audio": bool((audio_by_href or {}).get(public_href)),
                }
            )
    return items


def validate_release_matrix(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    matrix_path = site_dir / "release-matrix.json"
    if not matrix_path.exists():
        errors.append(f"{matrix_path}: missing release matrix")
        return
    data = load_json(matrix_path, errors)
    if data is None:
        return
    if data.get("schema") != RELEASE_MATRIX_SCHEMA:
        errors.append(f"{matrix_path}: unexpected schema {data.get('schema')!r}")
    for key, expected_href in (
        ("entrypoint", "index.html"),
        ("public_manifest", "public-manifest.json"),
        ("release_board", "release-board.html"),
        ("release_queue", "release-queue.md"),
        ("platform_plan", "platform-plan.md"),
        ("release_copy", "release-copy.md"),
        ("release_player", "release-player.html"),
    ):
        if data.get(key) != expected_href:
            errors.append(f"{matrix_path}: {key} must be {expected_href}")
        href_path(site_dir, expected_href, f"{matrix_path}: {key}", errors)
    if data.get("derived_from") != "sanitized public release queue":
        errors.append(f"{matrix_path}: derived_from must describe sanitized public release queue")
    audio_by_href: dict[str, bool] = {}
    sound_path = site_dir / "sound-map.json"
    if sound_path.exists():
        sound_data = load_json(sound_path, errors)
        if isinstance(sound_data, dict):
            sound_items = sound_data.get("items")
            if isinstance(sound_items, list):
                for item in sound_items:
                    if isinstance(item, dict) and isinstance(item.get("href"), str):
                        audio_by_href[item["href"]] = item.get("has_audio") is True
    expected_items = expected_release_matrix_items(receipts, audio_by_href)
    expected_hrefs = sorted(item["href"] for item in expected_items)
    if data.get("item_count") != len(expected_items):
        errors.append(f"{matrix_path}: item_count must be {len(expected_items)}")
    expected_editions = sorted({item["edition"] for item in expected_items})
    expected_targets = sorted({target for item in expected_items for target in item["targets"]})
    if data.get("edition_count") != len(expected_editions):
        errors.append(f"{matrix_path}: edition_count must be {len(expected_editions)}")
    if data.get("target_count") != len(expected_targets):
        errors.append(f"{matrix_path}: target_count must be {len(expected_targets)}")
    matrix_items_by_href = {item["href"]: item for item in expected_items}

    editions = data.get("editions")
    if not isinstance(editions, list):
        errors.append(f"{matrix_path}: editions must be a list")
        editions = []
    if sorted(row.get("edition") for row in editions if isinstance(row, dict)) != expected_editions:
        errors.append(f"{matrix_path}: editions must cover public editions")
    seen_hrefs: list[str] = []
    for index, row in enumerate(editions, start=1):
        if not isinstance(row, dict):
            errors.append(f"{matrix_path}: editions[{index}] must be an object")
            continue
        edition = row.get("edition")
        if not isinstance(edition, str) or edition not in receipts:
            errors.append(f"{matrix_path}: editions[{index}].edition must match a public receipt")
            continue
        edition_items = [item for item in expected_items if item["edition"] == edition]
        if row.get("work_title") != (edition_items[0]["work_title"] if edition_items else receipts[edition].get("work_title")):
            errors.append(f"{matrix_path}: editions[{index}].work_title must match public release data")
        if row.get("family") != str(receipts[edition].get("family") or ""):
            errors.append(f"{matrix_path}: editions[{index}].family must match receipt family")
        if row.get("item_count") != len(edition_items):
            errors.append(f"{matrix_path}: editions[{index}].item_count must be {len(edition_items)}")
        if row.get("audio_items") != sum(1 for item in edition_items if item["has_audio"] is True):
            errors.append(f"{matrix_path}: editions[{index}].audio_items does not match public media facts")
        expected_target_counts: dict[str, int] = {}
        for item in edition_items:
            for target in item["targets"]:
                expected_target_counts[target] = expected_target_counts.get(target, 0) + 1
        if row.get("targets") != dict(sorted(expected_target_counts.items())):
            errors.append(f"{matrix_path}: editions[{index}].targets must match expected target counts")
        items = row.get("items")
        if not isinstance(items, list):
            errors.append(f"{matrix_path}: editions[{index}].items must be a list")
            continue
        if len(items) != len(edition_items):
            errors.append(f"{matrix_path}: editions[{index}].items length must be {len(edition_items)}")
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"{matrix_path}: editions[{index}].items[{item_index}] must be an object")
                continue
            href = item.get("href")
            if isinstance(href, str):
                seen_hrefs.append(href)
            expected = matrix_items_by_href.get(href)
            if expected is None:
                errors.append(f"{matrix_path}: editions[{index}].items[{item_index}].href is not a public release href")
                continue
            for key in ("position", "label", "kind", "targets"):
                if item.get(key) != expected.get(key):
                    errors.append(f"{matrix_path}: editions[{index}].items[{item_index}].{key} must match release queue")
            href_path(site_dir, href, f"{matrix_path}: editions[{index}].items[{item_index}].href", errors)

    targets = data.get("targets")
    if not isinstance(targets, list):
        errors.append(f"{matrix_path}: targets must be a list")
        targets = []
    if sorted(row.get("target") for row in targets if isinstance(row, dict)) != expected_targets:
        errors.append(f"{matrix_path}: targets must cover expected platform targets")
    for index, row in enumerate(targets, start=1):
        if not isinstance(row, dict):
            errors.append(f"{matrix_path}: targets[{index}] must be an object")
            continue
        target = row.get("target")
        if not isinstance(target, str) or target not in expected_targets:
            errors.append(f"{matrix_path}: targets[{index}].target must match an expected target")
            continue
        target_items = [item for item in expected_items if target in item["targets"]]
        if row.get("item_count") != len(target_items):
            errors.append(f"{matrix_path}: targets[{index}].item_count must be {len(target_items)}")
        if sorted(row.get("edition_slugs") or []) != sorted({item["edition"] for item in target_items}):
            errors.append(f"{matrix_path}: targets[{index}].edition_slugs must match expected editions")
        items = row.get("items")
        if not isinstance(items, list):
            errors.append(f"{matrix_path}: targets[{index}].items must be a list")
            continue
        if len(items) != len(target_items):
            errors.append(f"{matrix_path}: targets[{index}].items length must be {len(target_items)}")
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"{matrix_path}: targets[{index}].items[{item_index}] must be an object")
                continue
            href = item.get("href")
            expected = matrix_items_by_href.get(href)
            if expected is None or target not in expected["targets"]:
                errors.append(f"{matrix_path}: targets[{index}].items[{item_index}].href must belong to target {target}")
                continue
            href_path(site_dir, href, f"{matrix_path}: targets[{index}].items[{item_index}].href", errors)
    if sorted(seen_hrefs) != expected_hrefs:
        errors.append(f"{matrix_path}: edition item hrefs must match public release hrefs")

    product_gate = data.get("product_shop_gate")
    if not isinstance(product_gate, dict) or product_gate.get("status") != "deferred":
        errors.append(f"{matrix_path}: product_shop_gate.status must be deferred")
    gates = data.get("operating_gates")
    if not isinstance(gates, list) or not gates or not all(isinstance(gate, str) and gate for gate in gates):
        errors.append(f"{matrix_path}: operating_gates must be a non-empty string list")
    else:
        gate_text = "\n".join(gates)
        for marker in ("sanitized public release queue", "local to the public static package", "Product/shop use stays deferred"):
            if marker not in gate_text:
                errors.append(f"{matrix_path}: operating_gates must include {marker!r}")


def validate_release_matrix_doc(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    doc_path = site_dir / "release-matrix.md"
    if not doc_path.exists():
        errors.append(f"{doc_path}: missing release matrix doc")
        return
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{doc_path}: cannot read: {error}")
        return
    for required in (
        "# Triptych Release Matrix",
        "index.html",
        "release-board.html",
        "release-queue.md",
        "release-copy.md",
        "platform-plan.md",
        "release-player.html",
        "public-manifest.json",
        "release-matrix.json",
        "## Snapshot",
        "## Targets",
        "## Editions",
        "Product/shop gate: deferred",
    ):
        if required not in text:
            errors.append(f"{doc_path}: missing release-matrix marker {required!r}")
    for item in expected_release_matrix_items(receipts):
        for required in (item["edition"], item["work_title"], item["href"]):
            if required and required not in text:
                errors.append(f"{doc_path}: missing release matrix item marker {required!r}")


def href_path(site_dir: Path, href: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(href, str) or not href:
        errors.append(f"{label}: missing href")
        return None
    if href.startswith(("http://", "https://", "data:", "javascript:")):
        errors.append(f"{label}: href must be a local site path")
        return None
    href_without_fragment = href.split("#", 1)[0]
    href_without_query = href_without_fragment.split("?", 1)[0]
    path = Path(href_without_query)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{label}: href escapes site dir: {href}")
        return None
    target = (site_dir / path).resolve()
    if not path_inside(target, site_dir):
        errors.append(f"{label}: href escapes site dir: {href}")
        return None
    if not target.exists():
        errors.append(f"{label}: href does not exist: {href}")
        return None
    return target


def published_post_exports(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    exports = receipt.get("exports")
    if not isinstance(exports, list):
        return []
    return [
        export
        for export in exports
        if isinstance(export, dict)
        and export.get("layout") in POSTABLE_LAYOUTS
        and export.get("exists") is True
        and export.get("published") is True
        and isinstance(export.get("src"), str)
        and export.get("src")
    ]


def visual_sketch_exports(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    exports = receipt.get("exports")
    if not isinstance(exports, list):
        return []
    return [
        export
        for export in exports
        if isinstance(export, dict)
        and export.get("layout") == "visual-sketch"
        and export.get("exists") is True
        and isinstance(export.get("src"), str)
        and export.get("src")
    ]


def expected_preset_hrefs(slug: str, receipt: dict[str, Any]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for preset in receipt.get("control_presets", []):
        if not isinstance(preset, dict):
            continue
        preset_id = preset.get("id")
        if isinstance(preset_id, str) and SAFE_ID_RE.fullmatch(preset_id):
            expected[preset_id] = f"editions/{slug}/index.html?{urlencode({'preset': preset_id})}"
    return expected


def expected_player_preset_hrefs(receipts: dict[str, dict[str, Any]]) -> list[str]:
    hrefs = [
        "release-player.html",
        f"release-player.html?{urlencode({'mode': 'random', 'muted': '1'})}",
        f"release-player.html?{urlencode({'mode': 'random', 'muted': '1', 'autoplay': '1', 'kiosk': '1'})}",
    ]
    for slug in sorted(receipts):
        hrefs.append(f"release-player.html?{urlencode({'edition': slug})}")
    families = sorted(
        {
            str(receipt.get("family"))
            for receipt in receipts.values()
            if isinstance(receipt.get("family"), str) and receipt.get("family")
        }
    )
    for family in families:
        hrefs.append(f"release-player.html?{urlencode({'family': family, 'mode': 'random', 'muted': '1'})}")
    return sorted(hrefs)


def validate_player_presets(
    source_path: Path,
    presets: Any,
    site_dir: Path,
    receipts: dict[str, dict[str, Any]],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(presets, list):
        errors.append(f"{source_path}: {label} must be a list")
        return
    expected_hrefs = expected_player_preset_hrefs(receipts)
    actual_hrefs: list[str] = []
    seen_ids: set[str] = set()
    families = {
        str(receipt.get("family"))
        for receipt in receipts.values()
        if isinstance(receipt.get("family"), str) and receipt.get("family")
    }
    for index, preset in enumerate(presets, start=1):
        if not isinstance(preset, dict):
            errors.append(f"{source_path}: {label}[{index}] must be an object")
            continue
        preset_id = preset.get("id")
        if not isinstance(preset_id, str) or not SAFE_ID_RE.fullmatch(preset_id):
            errors.append(f"{source_path}: {label}[{index}].id must be a safe id")
        elif preset_id in seen_ids:
            errors.append(f"{source_path}: {label} duplicate id {preset_id!r}")
        else:
            seen_ids.add(preset_id)
        if not isinstance(preset.get("label"), str) or not preset.get("label"):
            errors.append(f"{source_path}: {label}[{index}].label must be a non-empty string")
        scope = preset.get("scope")
        if scope not in {"all", "edition", "family"}:
            errors.append(f"{source_path}: {label}[{index}].scope must be all, edition, or family")
        if scope == "edition" and preset.get("edition") not in receipts:
            errors.append(f"{source_path}: {label}[{index}].edition must match a public receipt")
        if scope == "family" and preset.get("family") not in families:
            errors.append(f"{source_path}: {label}[{index}].family must match a public family")
        mode = preset.get("mode")
        if mode not in {"sequential", "random"}:
            errors.append(f"{source_path}: {label}[{index}].mode must be sequential or random")
        if "muted" in preset and not isinstance(preset["muted"], bool):
            errors.append(f"{source_path}: {label}[{index}].muted must be boolean")
        if "autoplay" in preset and not isinstance(preset["autoplay"], bool):
            errors.append(f"{source_path}: {label}[{index}].autoplay must be boolean")
        if "kiosk" in preset and not isinstance(preset["kiosk"], bool):
            errors.append(f"{source_path}: {label}[{index}].kiosk must be boolean")
        href = preset.get("href")
        if isinstance(href, str):
            actual_hrefs.append(href)
        href_path(site_dir, href, f"{source_path}: {label}[{index}].href", errors)
    if sorted(actual_hrefs) != expected_hrefs:
        errors.append(f"{source_path}: {label} hrefs do not match expected public player presets")


def validate_manifest_release_queue(
    manifest_path: Path,
    site_dir: Path,
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    queue = manifest.get("release_queue")
    if not isinstance(queue, list):
        errors.append(f"{manifest_path}: release_queue must be a list")
        return

    expected_hrefs = expected_release_hrefs(receipts)
    if len(queue) != len(expected_hrefs):
        errors.append(f"{manifest_path}: release_queue length must be {len(expected_hrefs)}")

    actual_hrefs: list[str] = []
    for index, item in enumerate(queue, start=1):
        if not isinstance(item, dict):
            errors.append(f"{manifest_path}: release_queue[{index}] must be an object")
            continue
        if item.get("position") != index:
            errors.append(f"{manifest_path}: release_queue[{index}].position must be {index}")
        edition = item.get("edition")
        if not isinstance(edition, str) or edition not in receipts:
            errors.append(f"{manifest_path}: release_queue[{index}].edition must match a public receipt")
        for key in ("work_title", "family", "kind", "name", "label", "phase", "href"):
            if not isinstance(item.get(key), str) or not item.get(key):
                errors.append(f"{manifest_path}: release_queue[{index}].{key} must be a non-empty string")
        targets = item.get("targets")
        if not isinstance(targets, list) or not targets or not all(isinstance(target, str) and target for target in targets):
            errors.append(f"{manifest_path}: release_queue[{index}].targets must be a non-empty string list")
        href = item.get("href")
        if isinstance(href, str):
            actual_hrefs.append(href)
        target = href_path(site_dir, href, f"{manifest_path}: release_queue[{index}].href", errors)
        if target is not None:
            validate_manifest_media_facts(
                manifest_path,
                item.get("media"),
                target,
                f"release_queue[{index}]",
                errors,
            )

    if sorted(actual_hrefs) != expected_hrefs:
        errors.append(f"{manifest_path}: release_queue hrefs do not match public receipt exports")


def validate_public_manifest(site_dir: Path, receipts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    manifest_path = site_dir / "public-manifest.json"
    if not manifest_path.exists():
        errors.append(f"{manifest_path}: missing public release manifest")
        return
    manifest = load_json(manifest_path, errors)
    if manifest is None:
        return
    if manifest.get("schema") != PUBLIC_MANIFEST_SCHEMA:
        errors.append(f"{manifest_path}: unexpected schema {manifest.get('schema')!r}")
    if manifest.get("entrypoint") != "index.html":
        errors.append(f"{manifest_path}: entrypoint must be index.html")
    href_path(site_dir, "index.html", f"{manifest_path}: entrypoint", errors)
    if manifest.get("release_player") != "release-player.html":
        errors.append(f"{manifest_path}: release_player must be release-player.html")
    href_path(site_dir, "release-player.html", f"{manifest_path}: release_player", errors)
    if manifest.get("exhibit_loop") != "exhibit-loop.md":
        errors.append(f"{manifest_path}: exhibit_loop must be exhibit-loop.md")
    href_path(site_dir, "exhibit-loop.md", f"{manifest_path}: exhibit_loop", errors)
    if manifest.get("exhibit_programs") != "exhibit-programs.json":
        errors.append(f"{manifest_path}: exhibit_programs must be exhibit-programs.json")
    href_path(site_dir, "exhibit-programs.json", f"{manifest_path}: exhibit_programs", errors)
    if manifest.get("exhibit_cue_sheet") != "exhibit-cue-sheet.json":
        errors.append(f"{manifest_path}: exhibit_cue_sheet must be exhibit-cue-sheet.json")
    href_path(site_dir, "exhibit-cue-sheet.json", f"{manifest_path}: exhibit_cue_sheet", errors)
    if manifest.get("exhibit_cue_sheet_doc") != "exhibit-cue-sheet.md":
        errors.append(f"{manifest_path}: exhibit_cue_sheet_doc must be exhibit-cue-sheet.md")
    href_path(site_dir, "exhibit-cue-sheet.md", f"{manifest_path}: exhibit_cue_sheet_doc", errors)
    if manifest.get("curatorial_score") != "curatorial-score.json":
        errors.append(f"{manifest_path}: curatorial_score must be curatorial-score.json")
    href_path(site_dir, "curatorial-score.json", f"{manifest_path}: curatorial_score", errors)
    if manifest.get("curatorial_score_doc") != "curatorial-score.md":
        errors.append(f"{manifest_path}: curatorial_score_doc must be curatorial-score.md")
    href_path(site_dir, "curatorial-score.md", f"{manifest_path}: curatorial_score_doc", errors)
    if manifest.get("living_loop") != "living-loop.json":
        errors.append(f"{manifest_path}: living_loop must be living-loop.json")
    href_path(site_dir, "living-loop.json", f"{manifest_path}: living_loop", errors)
    if manifest.get("living_loop_doc") != "living-loop.md":
        errors.append(f"{manifest_path}: living_loop_doc must be living-loop.md")
    href_path(site_dir, "living-loop.md", f"{manifest_path}: living_loop_doc", errors)
    if manifest.get("playback_contract") != "playback-contract.json":
        errors.append(f"{manifest_path}: playback_contract must be playback-contract.json")
    href_path(site_dir, "playback-contract.json", f"{manifest_path}: playback_contract", errors)
    if manifest.get("composition_atlas") != "composition-atlas.json":
        errors.append(f"{manifest_path}: composition_atlas must be composition-atlas.json")
    href_path(site_dir, "composition-atlas.json", f"{manifest_path}: composition_atlas", errors)
    if manifest.get("composition_atlas_doc") != "composition-atlas.md":
        errors.append(f"{manifest_path}: composition_atlas_doc must be composition-atlas.md")
    href_path(site_dir, "composition-atlas.md", f"{manifest_path}: composition_atlas_doc", errors)
    if manifest.get("rhythm_map") != "rhythm-map.json":
        errors.append(f"{manifest_path}: rhythm_map must be rhythm-map.json")
    href_path(site_dir, "rhythm-map.json", f"{manifest_path}: rhythm_map", errors)
    if manifest.get("rhythm_map_doc") != "rhythm-map.md":
        errors.append(f"{manifest_path}: rhythm_map_doc must be rhythm-map.md")
    href_path(site_dir, "rhythm-map.md", f"{manifest_path}: rhythm_map_doc", errors)
    if manifest.get("sound_map") != "sound-map.json":
        errors.append(f"{manifest_path}: sound_map must be sound-map.json")
    href_path(site_dir, "sound-map.json", f"{manifest_path}: sound_map", errors)
    if manifest.get("sound_map_doc") != "sound-map.md":
        errors.append(f"{manifest_path}: sound_map_doc must be sound-map.md")
    href_path(site_dir, "sound-map.md", f"{manifest_path}: sound_map_doc", errors)
    if manifest.get("release_matrix") != "release-matrix.json":
        errors.append(f"{manifest_path}: release_matrix must be release-matrix.json")
    href_path(site_dir, "release-matrix.json", f"{manifest_path}: release_matrix", errors)
    if manifest.get("release_matrix_doc") != "release-matrix.md":
        errors.append(f"{manifest_path}: release_matrix_doc must be release-matrix.md")
    href_path(site_dir, "release-matrix.md", f"{manifest_path}: release_matrix_doc", errors)
    validate_player_presets(
        manifest_path,
        manifest.get("player_presets"),
        site_dir,
        receipts,
        "player_presets",
        errors,
    )

    editions = manifest.get("editions")
    if not isinstance(editions, list):
        errors.append(f"{manifest_path}: editions must be a list")
        editions = []
    if manifest.get("edition_count") != len(editions):
        errors.append(f"{manifest_path}: edition_count must equal editions length")

    by_slug: dict[str, dict[str, Any]] = {}
    for index, edition in enumerate(editions, start=1):
        if not isinstance(edition, dict):
            errors.append(f"{manifest_path}: editions[{index}] must be an object")
            continue
        slug = edition.get("slug")
        if not isinstance(slug, str) or not SAFE_ID_RE.fullmatch(slug):
            errors.append(f"{manifest_path}: editions[{index}].slug must be a safe id")
            continue
        if slug in by_slug:
            errors.append(f"{manifest_path}: duplicate edition slug {slug!r}")
        by_slug[slug] = edition

    if set(by_slug) != set(receipts):
        missing = sorted(set(receipts) - set(by_slug))
        extra = sorted(set(by_slug) - set(receipts))
        if missing:
            errors.append(f"{manifest_path}: missing editions {', '.join(missing)}")
        if extra:
            errors.append(f"{manifest_path}: extra editions {', '.join(extra)}")

    validate_manifest_release_queue(manifest_path, site_dir, manifest, receipts, errors)

    expected_totals = {
        "clips": 0,
        "video_proxies": 0,
        "audio_proxies": 0,
        "post_exports": 0,
        "visual_sketches": 0,
    }
    expected_families: set[str] = set()

    for slug, receipt in receipts.items():
        edition = by_slug.get(slug)
        counts = receipt.get("counts", {}) if isinstance(receipt.get("counts"), dict) else {}
        post_exports = published_post_exports(receipt)
        sketches = visual_sketch_exports(receipt)
        expected_counts = {
            "clips": int(counts.get("manifest_clips") or 0),
            "video_proxies": int(counts.get("video_proxies") or 0),
            "audio_proxies": int(counts.get("audio_proxies") or 0),
            "exports": int(counts.get("exports") or 0),
            "post_exports": len(post_exports),
            "visual_sketches": len(sketches),
        }
        for key in ("clips", "video_proxies", "audio_proxies", "post_exports", "visual_sketches"):
            expected_totals[key] += expected_counts[key]
        family = receipt.get("family")
        if isinstance(family, str) and family:
            expected_families.add(family)
        if edition is None:
            continue

        expected_page = f"editions/{slug}/index.html"
        if edition.get("page") != expected_page:
            errors.append(f"{manifest_path}: {slug}.page must be {expected_page}")
        href_path(site_dir, edition.get("page"), f"{manifest_path}: {slug}.page", errors)
        if edition.get("preview_src") is not None:
            href_path(site_dir, edition.get("preview_src"), f"{manifest_path}: {slug}.preview_src", errors)

        for key in ("title", "work_title", "family"):
            value = edition.get(key)
            expected = str(receipt.get(key) or "")
            if not isinstance(value, str) or value != expected:
                errors.append(f"{manifest_path}: {slug}.{key} must match public receipt")

        manifest_counts = edition.get("counts")
        if not isinstance(manifest_counts, dict):
            errors.append(f"{manifest_path}: {slug}.counts must be an object")
        else:
            for key, expected in expected_counts.items():
                if manifest_counts.get(key) != expected:
                    errors.append(f"{manifest_path}: {slug}.counts.{key} must be {expected}")

        preset_hrefs = expected_preset_hrefs(slug, receipt)
        manifest_presets = edition.get("control_presets")
        if not isinstance(manifest_presets, list):
            errors.append(f"{manifest_path}: {slug}.control_presets must be a list")
            manifest_presets = []
        manifest_preset_hrefs: dict[str, str] = {}
        for preset in manifest_presets:
            if not isinstance(preset, dict):
                errors.append(f"{manifest_path}: {slug}.control_presets item must be an object")
                continue
            preset_id = preset.get("id")
            href = preset.get("href")
            if isinstance(preset_id, str):
                manifest_preset_hrefs[preset_id] = str(href)
                href_path(site_dir, href, f"{manifest_path}: {slug}.preset.{preset_id}", errors)
        if manifest_preset_hrefs != preset_hrefs:
            errors.append(f"{manifest_path}: {slug}.control_presets hrefs do not match receipt presets")

        expected_post_hrefs = sorted(f"editions/{slug}/{export['src']}" for export in post_exports)
        manifest_posts = edition.get("post_exports")
        if not isinstance(manifest_posts, list):
            errors.append(f"{manifest_path}: {slug}.post_exports must be a list")
            manifest_posts = []
        manifest_post_hrefs: list[str] = []
        for export in manifest_posts:
            if not isinstance(export, dict):
                errors.append(f"{manifest_path}: {slug}.post_exports item must be an object")
                continue
            href = export.get("href")
            if isinstance(href, str):
                manifest_post_hrefs.append(href)
            target = href_path(site_dir, href, f"{manifest_path}: {slug}.post_export", errors)
            if target is not None:
                validate_manifest_media_facts(
                    manifest_path,
                    export.get("media"),
                    target,
                    f"{slug}.post_exports.{export.get('name', 'export')}",
                    errors,
                )
        if sorted(manifest_post_hrefs) != expected_post_hrefs:
            errors.append(f"{manifest_path}: {slug}.post_exports do not match published receipt exports")

        visual_sketch = edition.get("visual_sketch")
        if sketches:
            expected_sketch = f"editions/{slug}/{sketches[0]['src']}"
            if not isinstance(visual_sketch, dict):
                errors.append(f"{manifest_path}: {slug}.visual_sketch must be present")
            elif visual_sketch.get("href") != expected_sketch:
                errors.append(f"{manifest_path}: {slug}.visual_sketch href must be {expected_sketch}")
            elif visual_sketch.get("href"):
                target = href_path(site_dir, visual_sketch["href"], f"{manifest_path}: {slug}.visual_sketch", errors)
                if target is not None:
                    validate_manifest_media_facts(
                        manifest_path,
                        visual_sketch.get("media"),
                        target,
                        f"{slug}.visual_sketch",
                        errors,
                    )
        elif visual_sketch is not None:
            errors.append(f"{manifest_path}: {slug}.visual_sketch must be null when no sketch exists")

    totals = manifest.get("totals")
    if not isinstance(totals, dict):
        errors.append(f"{manifest_path}: totals must be an object")
    else:
        for key, expected in expected_totals.items():
            if totals.get(key) != expected:
                errors.append(f"{manifest_path}: totals.{key} must be {expected}")
    families = manifest.get("families")
    if families != sorted(expected_families):
        errors.append(f"{manifest_path}: families must match public receipts")


def validate_size(site_dir: Path, max_site_mb: float, max_edition_mb: float, errors: list[str]) -> tuple[int, dict[str, int]]:
    site_bytes = tree_size(site_dir)
    if mb(site_bytes) > max_site_mb:
        errors.append(f"{site_dir}: site size {mb(site_bytes):.1f} MB exceeds {max_site_mb:.1f} MB")

    edition_sizes: dict[str, int] = {}
    editions_dir = site_dir / "editions"
    if editions_dir.exists():
        for edition_dir in sorted(path for path in editions_dir.iterdir() if path.is_dir()):
            size = tree_size(edition_dir)
            edition_sizes[edition_dir.name] = size
            if mb(size) > max_edition_mb:
                errors.append(
                    f"{edition_dir}: edition size {mb(size):.1f} MB exceeds {max_edition_mb:.1f} MB"
                )
    return site_bytes, edition_sizes


def main() -> int:
    args = parse_args()
    site_dir = site_path(args.site_dir, DEFAULT_SITE_DIR).resolve()
    errors: list[str] = []

    if not path_inside(site_dir, SCRIPT_DIR):
        raise SystemExit("site-dir must stay inside the SIMVLTANEA repository root.")
    if not site_dir.exists():
        raise SystemExit(f"site directory does not exist: {site_dir}")

    scan_text_files(site_dir, errors)

    receipt_paths = sorted((site_dir / "editions").glob("*/flash-copy.json"))
    if not receipt_paths:
        errors.append(f"{site_dir / 'editions'}: no edition flash-copy receipts found")

    receipts: dict[str, dict[str, Any]] = {}
    total_clips = 0
    total_video_proxies = 0
    total_audio_proxies = 0
    total_visual_sketch_exports = 0
    total_published_post_exports = 0
    for receipt_path in receipt_paths:
        receipt = validate_receipt(
            receipt_path,
            site_dir,
            errors,
            args.max_visual_sketch_mb,
            args.max_visual_sketch_seconds,
            args.max_published_export_mb,
            args.max_published_export_seconds,
        )
        if receipt is None:
            continue
        receipts[receipt_path.parent.name] = receipt
        counts = receipt.get("counts", {})
        if isinstance(counts, dict):
            total_clips += int(counts.get("manifest_clips") or 0)
            total_video_proxies += int(counts.get("video_proxies") or 0)
            total_audio_proxies += int(counts.get("audio_proxies") or 0)
        exports = receipt.get("exports", [])
        if isinstance(exports, list):
            total_visual_sketch_exports += sum(
                1
                for export in exports
                if isinstance(export, dict)
                and export.get("layout") == "visual-sketch"
                and export.get("exists") is True
            )
            total_published_post_exports += sum(
                1
                for export in exports
                if isinstance(export, dict)
                and export.get("layout") in POSTABLE_LAYOUTS
                and export.get("exists") is True
                and export.get("published") is True
            )

    validate_index(site_dir, receipts, errors)
    validate_release_board(site_dir, receipts, errors)
    validate_release_copy(site_dir, receipts, errors)
    validate_platform_plan(site_dir, receipts, errors)
    validate_release_queue(site_dir, receipts, errors)
    validate_release_player(site_dir, receipts, errors)
    validate_player_presets_doc(site_dir, receipts, errors)
    validate_exhibit_loop(site_dir, receipts, errors)
    validate_exhibit_programs(site_dir, receipts, errors)
    validate_playback_contract(site_dir, receipts, errors)
    validate_composition_atlas(site_dir, receipts, errors)
    validate_composition_atlas_doc(site_dir, receipts, errors)
    validate_rhythm_map(site_dir, receipts, errors)
    validate_rhythm_map_doc(site_dir, receipts, errors)
    validate_sound_map(site_dir, receipts, errors)
    validate_sound_map_doc(site_dir, receipts, errors)
    validate_exhibit_cue_sheet(site_dir, receipts, errors)
    validate_exhibit_cue_sheet_doc(site_dir, receipts, errors)
    validate_curatorial_score(site_dir, receipts, errors)
    validate_curatorial_score_doc(site_dir, receipts, errors)
    validate_living_loop(site_dir, receipts, errors)
    validate_living_loop_doc(site_dir, receipts, errors)
    validate_release_matrix(site_dir, receipts, errors)
    validate_release_matrix_doc(site_dir, receipts, errors)
    validate_public_manifest(site_dir, receipts, errors)
    site_bytes, edition_sizes = validate_size(site_dir, args.max_site_mb, args.max_edition_mb, errors)

    if errors:
        print("public site verification failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("public site ok")
    print(f"site: {site_dir.relative_to(SCRIPT_DIR)} ({mb(site_bytes):.1f} MB)")
    slugs = sorted(receipts)
    print(f"editions: {len(slugs)} ({', '.join(slugs)})")
    print(f"clips: {total_clips}; video proxies: {total_video_proxies}; audio proxies: {total_audio_proxies}")
    print(f"published posts: {total_published_post_exports}; visual sketches: {total_visual_sketch_exports}")
    for slug, size in edition_sizes.items():
        print(f"- {slug}: {mb(size):.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
