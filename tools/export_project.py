#!/usr/bin/env python3
"""Text-driven export runner for the triptych video canon incubator."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = SCRIPT_DIR / "project.example.json"
DEFAULT_EXPORTS = [
    {
        "name": "story-triptych",
        "layout": "story",
        "output_file": "renders/story-triptych.mp4",
        "width": 1080,
        "height": 1920,
    },
    {
        "name": "reel-left",
        "layout": "left",
        "output_file": "renders/reel-left.mp4",
        "width": 1080,
        "height": 1920,
    },
    {
        "name": "reel-middle",
        "layout": "middle",
        "output_file": "renders/reel-middle.mp4",
        "width": 1080,
        "height": 1920,
    },
    {
        "name": "reel-right",
        "layout": "right",
        "output_file": "renders/reel-right.mp4",
        "width": 1080,
        "height": 1920,
    },
]
PANEL_NAMES = ("left", "middle", "right")
AUDIO_MODES = ("none", "panel", "mix")
VIDEO_DIRECTIONS = ("forward", "reverse", "pingpong")
TONE_MODES = ("none", "normalize", "histeq")
DEFAULT_AUDIO_PROXY_LIMIT = 72


def normalize_panel_order(value: Any) -> list[str]:
    if value is None:
        return list(PANEL_NAMES)
    if isinstance(value, str):
        names = [name.strip() for name in value.split(",") if name.strip()]
    elif isinstance(value, list):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        return list(PANEL_NAMES)
    return names if len(names) == 3 and set(names) == set(PANEL_NAMES) else list(PANEL_NAMES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render configured triptych story/reel exports and landing page."
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Project JSON manifest. Defaults to project.example.json.",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated export names to render, for example story-triptych,reel-left.",
    )
    parser.add_argument(
        "--add-prompt",
        action="append",
        help="Append a text prompt to the project before exporting.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands only.")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Render a lightweight draft: story only by default, lower resolution, fewer clips.",
    )
    parser.add_argument(
        "--draft-videos",
        type=int,
        default=5,
        help="Maximum videos in --draft mode. Defaults to 5.",
    )
    parser.add_argument("--audio", choices=AUDIO_MODES, help="Override project audio mode.")
    parser.add_argument("--audio-panel", choices=PANEL_NAMES, help="Panel for --audio panel.")
    parser.add_argument("--audio-gain", type=float, help="Override per-source audio gain.")
    parser.add_argument("--audio-left-gain", type=float, help="Additional gain for left-panel audio.")
    parser.add_argument("--audio-middle-gain", type=float, help="Additional gain for middle-panel audio.")
    parser.add_argument("--audio-right-gain", type=float, help="Additional gain for right-panel audio.")
    parser.add_argument("--audio-fade", type=float, help="Override audio fade seconds.")
    parser.add_argument(
        "--direction",
        choices=VIDEO_DIRECTIONS,
        help="Override video playback direction effect.",
    )
    parser.add_argument(
        "--tone",
        choices=TONE_MODES,
        help="Override export-time brightness/color balance filter.",
    )
    parser.add_argument(
        "--tone-strength",
        type=float,
        help="Strength for --tone normalize, from 0 to 1.",
    )
    parser.add_argument(
        "--tone-smoothing",
        type=int,
        help="Temporal smoothing frames for --tone normalize.",
    )
    parser.add_argument("--keep-work", action="store_true", help="Keep renderer temp files.")
    parser.add_argument("--skip-render", action="store_true", help="Only build the landing page.")
    parser.add_argument("--landing-only", action="store_true", help="Alias for --skip-render.")
    parser.add_argument("--no-landing", action="store_true", help="Do not build site/index.html.")
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def lexical_path_inside(path: Path, parent: Path) -> bool:
    try:
        path.absolute().relative_to(parent.absolute())
    except ValueError:
        return False
    return True


def resolve_path(value: str | Path | None, base: Path, default: Path) -> Path:
    if value is None:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base / path


def load_project(project_path: Path) -> tuple[dict[str, Any], Path]:
    path = project_path.resolve()
    if not path.exists():
        raise SystemExit(f"Project manifest not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        project = json.load(handle)
    return project, path


def save_project(project: dict[str, Any], project_path: Path) -> None:
    project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")


def append_prompts(project: dict[str, Any], project_path: Path, prompts: list[str]) -> None:
    if not prompts:
        return

    history = list(project.get("prompts", []))
    for prompt in prompts:
        history.append({"date": date.today().isoformat(), "text": prompt})
    project["prompts"] = history
    save_project(project, project_path)
    print(f"appended {len(prompts)} prompt(s) to {project_path}")


def export_definitions(project: dict[str, Any], include_disabled: bool = False) -> list[dict[str, Any]]:
    raw_exports = project.get("exports", DEFAULT_EXPORTS)
    if not isinstance(raw_exports, list):
        raise SystemExit("project exports must be a list.")
    return [
        dict(export)
        for export in raw_exports
        if include_disabled or export.get("enabled", True)
    ]


def visual_sketch_definitions(project: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sketches = project.get("visual_sketch")
    if raw_sketches is None:
        return []
    if isinstance(raw_sketches, dict):
        raw_items = [raw_sketches]
    elif isinstance(raw_sketches, list):
        raw_items = raw_sketches
    else:
        return []

    sketches = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        output_file = item.get("output_file")
        if not output_file:
            continue
        sketches.append(
            {
                "name": item.get("name", "visual-sketch" if index == 1 else f"visual-sketch-{index}"),
                "layout": item.get("layout", "visual-sketch"),
                "output_file": output_file,
            }
        )
    return sketches


def public_text(value: Any, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def public_album_label(value: Any) -> str | None:
    text = public_text(value, limit=120)
    if text is None:
        return None
    return text.split("/")[-1] or text


def public_language(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels = []
    for item in value:
        label = public_text(item, limit=48)
        if label:
            labels.append(label)
        if len(labels) >= 6:
            break
    return labels


def first_visual_sketch_config(project: dict[str, Any]) -> dict[str, Any]:
    raw_sketches = project.get("visual_sketch")
    if isinstance(raw_sketches, dict) and raw_sketches.get("enabled", True) is not False:
        return raw_sketches
    if isinstance(raw_sketches, list):
        for item in raw_sketches:
            if isinstance(item, dict) and item.get("enabled", True) is not False:
                return item
    return {}


def arrangement_score(project: dict[str, Any]) -> dict[str, Any]:
    edition = project.get("edition")
    if not isinstance(edition, dict):
        edition = {}
    composition = project.get("composition")
    if not isinstance(composition, dict):
        composition = edition.get("composition")
    if not isinstance(composition, dict):
        composition = {}

    sketch = first_visual_sketch_config(project)
    style = public_text(sketch.get("style"), limit=40) if sketch else None
    cell_key = None
    cell_count = 0
    if isinstance(sketch.get("score_cells"), list):
        cell_key = "score_cells"
        cell_count = len(sketch["score_cells"])
    elif isinstance(sketch.get("fracture_cells"), list):
        cell_key = "fracture_cells"
        cell_count = len(sketch["fracture_cells"])
    elif isinstance(sketch.get("signal_cells"), list):
        cell_key = "signal_cells"
        cell_count = len(sketch["signal_cells"])

    material = public_album_label(composition.get("material_album"))
    model = public_album_label(composition.get("arrangement_model_album"))
    family = public_text(project.get("family") or edition.get("family"), limit=80)
    work_title = public_text(project.get("work_title") or edition.get("work_title"), limit=120)
    if cell_count and style:
        preview_label = f"{style} / {cell_count} cells"
    elif style:
        preview_label = style
    elif family:
        preview_label = family
    else:
        preview_label = None

    score: dict[str, Any] = {
        "work_title": work_title,
        "family": family,
        "material": material,
        "model": model,
        "style": style,
        "cell_key": cell_key,
        "cell_count": cell_count or None,
        "model_fit": public_text(sketch.get("model_fit"), limit=40) if sketch else None,
        "panel_role": public_text(composition.get("panel_arrangement_role"), limit=260),
        "model_role": public_text(composition.get("arrangement_model_role"), limit=260),
        "observation": public_text(composition.get("arrangement_model_observation"), limit=260),
        "language": public_language(composition.get("language")),
        "preview_label": preview_label,
    }
    return {key: value for key, value in score.items() if value not in (None, "", [])}


def safe_id(value: Any, fallback: str) -> str:
    text = public_text(value, limit=80) or fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip(".-").lower()
    return cleaned or fallback


def bounded_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return min(maximum, max(minimum, number))


def bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "show"}:
            return True
        if normalized in {"0", "false", "no", "off", "hide"}:
            return False
    return None


def raw_control_presets(project: dict[str, Any]) -> list[Any]:
    raw = project.get("control_presets")
    if raw is None:
        landing = project.get("landing_page", {})
        if isinstance(landing, dict):
            raw = landing.get("control_presets")
    return raw if isinstance(raw, list) else []


def control_presets(project: dict[str, Any]) -> list[dict[str, Any]]:
    presets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_control_presets(project), start=1):
        if not isinstance(raw, dict):
            continue
        preset_id = safe_id(raw.get("id") or raw.get("name") or raw.get("label"), f"preset-{index}")
        if preset_id in seen:
            continue
        seen.add(preset_id)
        preset: dict[str, Any] = {
            "id": preset_id,
            "label": public_text(raw.get("label") or raw.get("name"), limit=80) or preset_id,
        }
        note = public_text(raw.get("note"), limit=180)
        if note:
            preset["note"] = note
        surface = public_text(raw.get("surface"), limit=32)
        if surface in {"canon", "sketch"}:
            preset["surface"] = surface
        direction = public_text(raw.get("direction"), limit=32)
        if direction in VIDEO_DIRECTIONS:
            preset["direction"] = direction
        start = public_text(raw.get("start"), limit=32)
        if start in {"oldest", "random"}:
            preset["start"] = start
        if raw.get("panel_order") is not None:
            preset["panelOrder"] = normalize_panel_order(raw.get("panel_order"))
        for key in ("labels", "audio", "default"):
            parsed = bool_value(raw.get(key))
            if parsed is not None:
                preset[key] = parsed
        if raw.get("volume") is not None:
            preset["volume"] = bounded_float(raw.get("volume"), 0.35, 0, 1)
        panel_volumes = raw.get("panel_volumes")
        if isinstance(panel_volumes, dict):
            preset["panelVolumes"] = {
                panel: bounded_float(panel_volumes.get(panel), 1, 0, 1.5)
                for panel in PANEL_NAMES
                if panel_volumes.get(panel) is not None
            }
        presets.append(preset)
    return presets


def selected_exports(exports: list[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    if not only:
        return exports

    names = {name.strip() for name in only.split(",") if name.strip()}
    selected = [export for export in exports if export.get("name") in names]
    missing = names.difference({export.get("name") for export in selected})
    if missing:
        raise SystemExit(f"Unknown export name(s): {', '.join(sorted(missing))}")
    return selected


def draft_exports(exports: list[dict[str, Any]], draft_videos: int) -> list[dict[str, Any]]:
    selected = exports
    if not selected:
        return []
    if len(selected) == len(DEFAULT_EXPORTS):
        selected = [export for export in selected if export.get("layout", "story") == "story"]
        if not selected:
            selected = [exports[0]]

    drafts = []
    for export in selected:
        name = f"draft-{export.get('name', export.get('layout', 'story'))}"
        original_output = Path(str(export.get("output_file", f"renders/{export.get('name', 'story')}.mp4")))
        draft = dict(export)
        draft.update(
            {
                "name": name,
                "output_file": str(original_output.with_name(f"{name}.mp4")),
                "width": 540 if export.get("layout", "story") == "story" else 540,
                "height": 960,
                "fps": 15,
                "crf": 30,
                "preset": "ultrafast",
                "max_videos": draft_videos,
            }
        )
        drafts.append(draft)
    return drafts


def render_command(
    project_path: Path,
    project_base: Path,
    project: dict[str, Any],
    export: dict[str, Any],
    dry_run: bool,
    keep_work: bool,
) -> list[str]:
    canvas = project.get("canvas", {})
    render = project.get("render", {})
    audio = dict(project.get("audio", {}))
    audio.update(export.get("audio", {}))
    require_legacy_audio(audio)
    effects = dict(project.get("effects", {}))
    effects.update(export.get("effects", {}))
    output_default = SCRIPT_DIR / "renders" / f"{export['name']}.mp4"
    output_file = resolve_path(export.get("output_file"), project_base, output_default)

    command = [
        sys.executable,
        str(SCRIPT_DIR / "render_triptych.py"),
        "--manifest",
        str(project_path),
        "--layout",
        str(export.get("layout", "story")),
        "--output",
        str(output_file),
        "--width",
        str(export.get("width", canvas.get("width", 1080))),
        "--height",
        str(export.get("height", canvas.get("height", 1920))),
        "--fps",
        str(export.get("fps", canvas.get("fps", 30))),
        "--crf",
        str(export.get("crf", render.get("crf", 18))),
        "--preset",
        str(export.get("preset", render.get("preset", "medium"))),
    ]

    if "timing_mode" in export:
        command.extend(["--timing", str(export["timing_mode"])])
    if "phrase_seconds" in export:
        command.extend(["--phrase", str(export["phrase_seconds"])])
    if "max_videos" in export:
        command.extend(["--max-videos", str(export["max_videos"])])
    if "max_clip_seconds" in export:
        command.extend(["--max-clip-seconds", str(export["max_clip_seconds"])])
    if audio.get("mode"):
        command.extend(["--audio", str(audio["mode"])])
    if audio.get("panel"):
        command.extend(["--audio-panel", str(audio["panel"])])
    if "gain" in audio:
        command.extend(["--audio-gain", str(audio["gain"])])
    panel_gains = audio.get("panel_gains", {})
    if isinstance(panel_gains, dict):
        for panel_name in PANEL_NAMES:
            if panel_gains.get(panel_name) is not None:
                command.extend([f"--audio-{panel_name}-gain", str(panel_gains[panel_name])])
    if "fade_seconds" in audio:
        command.extend(["--audio-fade", str(audio["fade_seconds"])])
    if effects.get("direction"):
        command.extend(["--direction", str(effects["direction"])])
    tone = effects.get("tone", {}) if isinstance(effects.get("tone"), dict) else {}
    tone_mode = tone.get("mode", effects.get("tone_mode"))
    if tone_mode:
        command.extend(["--tone", str(tone_mode)])
    tone_strength = tone.get("strength", effects.get("tone_strength"))
    if tone_strength is not None:
        command.extend(["--tone-strength", str(tone_strength)])
    tone_smoothing = tone.get("smoothing", effects.get("tone_smoothing"))
    if tone_smoothing is not None:
        command.extend(["--tone-smoothing", str(tone_smoothing)])
    panel_order = normalize_panel_order(
        export.get("panel_order", project.get("panel_order", canvas.get("panel_order")))
    )
    if panel_order != list(PANEL_NAMES):
        command.extend(["--panel-order", ",".join(panel_order)])
    if dry_run:
        command.append("--dry-run")
    if keep_work:
        command.append("--keep-work")
    return command


def run_exports(
    project_path: Path,
    project: dict[str, Any],
    exports: list[dict[str, Any]],
    dry_run: bool,
    keep_work: bool,
) -> None:
    project_base = project_path.parent
    for export in exports:
        command = render_command(project_path, project_base, project, export, dry_run, keep_work)
        print(" ".join(command), flush=True)
        if not dry_run:
            subprocess.run(command, check=True)


def apply_audio_overrides(project: dict[str, Any], args: argparse.Namespace) -> None:
    overrides: dict[str, Any] = {}
    if args.audio is not None:
        overrides["mode"] = args.audio
    if args.audio_panel is not None:
        overrides["panel"] = args.audio_panel
    if args.audio_gain is not None:
        if args.audio_gain < 0:
            raise SystemExit("--audio-gain must be greater than or equal to 0.")
        overrides["gain"] = args.audio_gain
    panel_gain_overrides = {
        "left": args.audio_left_gain,
        "middle": args.audio_middle_gain,
        "right": args.audio_right_gain,
    }
    panel_gains = {
        name: value
        for name, value in panel_gain_overrides.items()
        if value is not None
    }
    for panel_name, panel_gain in panel_gains.items():
        if panel_gain < 0:
            raise SystemExit(f"--audio-{panel_name}-gain must be greater than or equal to 0.")
    if panel_gains:
        merged_panel_gains = dict(project.get("audio", {}).get("panel_gains", {}))
        merged_panel_gains.update(panel_gains)
        overrides["panel_gains"] = merged_panel_gains
    if args.audio_fade is not None:
        if args.audio_fade < 0:
            raise SystemExit("--audio-fade must be greater than or equal to 0.")
        overrides["fade_seconds"] = args.audio_fade
    if not overrides:
        return

    audio = dict(project.get("audio", {}))
    audio.update(overrides)
    project["audio"] = audio


def apply_effect_overrides(project: dict[str, Any], args: argparse.Namespace) -> None:
    if args.direction is None and args.tone is None and args.tone_strength is None and args.tone_smoothing is None:
        return
    effects = dict(project.get("effects", {}))
    if args.direction is not None:
        effects["direction"] = args.direction
    if args.tone is not None or args.tone_strength is not None or args.tone_smoothing is not None:
        tone = dict(effects.get("tone", {})) if isinstance(effects.get("tone"), dict) else {}
        if args.tone is not None:
            tone["mode"] = args.tone
        if args.tone_strength is not None:
            if not 0 <= args.tone_strength <= 1:
                raise SystemExit("--tone-strength must be between 0 and 1.")
            tone["strength"] = args.tone_strength
        if args.tone_smoothing is not None:
            if args.tone_smoothing < 0:
                raise SystemExit("--tone-smoothing must be greater than or equal to 0.")
            tone["smoothing"] = args.tone_smoothing
        effects["tone"] = tone
    project["effects"] = effects


def project_clip_entries(project: dict[str, Any], project_base: Path) -> list[dict[str, Any]]:
    clips = project.get("clips")
    if isinstance(clips, list) and clips:
        entries: list[dict[str, Any]] = []
        for clip in clips:
            enabled = True
            raw_path: str | None
            metadata: dict[str, Any] = {}
            if isinstance(clip, str):
                raw_path = clip
            elif isinstance(clip, dict):
                enabled = bool(clip.get("enabled", True))
                raw_path = clip.get("path")
                metadata = {
                    key: clip.get(key)
                    for key in (
                        "duration",
                        "source_created",
                        "source_uuid",
                        "original_filename",
                        "width",
                        "height",
                    )
                    if clip.get(key) is not None
                }
            else:
                continue
            if not enabled or not raw_path:
                continue
            path = Path(raw_path).expanduser()
            resolved = path if path.is_absolute() else project_base / path
            entries.append({"path": resolved, **metadata})
        return entries

    input_dir = resolve_path(project.get("input_dir"), project_base, SCRIPT_DIR / "samples")
    if not input_dir.exists() or not input_dir.is_dir():
        return []
    return [{"path": path} for path in sorted(path for path in input_dir.iterdir() if path.is_file())]


def project_clip_paths(project: dict[str, Any], project_base: Path) -> list[Path]:
    return [entry["path"] for entry in project_clip_entries(project, project_base)]


def relative_media(path: Path, site_dir: Path) -> str | None:
    if not path_inside(path, SCRIPT_DIR):
        if not (path.is_symlink() and lexical_path_inside(path, SCRIPT_DIR)):
            return None
        return os.path.relpath(path.absolute(), site_dir.absolute())
    return os.path.relpath(path.resolve(), site_dir.resolve())


def site_export_artifact_path(output_file: Path, site_dir: Path) -> Path | None:
    try:
        resolved = output_file.resolve()
    except OSError:
        resolved = output_file.absolute()
    if not path_inside(resolved, SCRIPT_DIR):
        return None
    return site_dir / "exports" / output_file.name


def export_media_src(output_file: Path, site_dir: Path) -> str | None:
    artifact = site_export_artifact_path(output_file, site_dir)
    if artifact is not None and artifact.exists():
        return relative_media(artifact, site_dir)
    return relative_media(output_file, site_dir)


def safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return cleaned[:72] or "clip"


def command_text(command: list[str]) -> str:
    return " ".join(command)


def fresh_enough(source: Path, output: Path) -> bool:
    if not output.exists():
        return False
    try:
        return output.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def probe_audio_stream(path: Path) -> bool:
    if shutil.which("ffprobe") is None:
        return False
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    return completed.returncode == 0 and bool(completed.stdout.strip())


def web_media_settings(project: dict[str, Any]) -> dict[str, Any]:
    landing = project.get("landing_page", {})
    settings: dict[str, Any] = {
        "enabled": True,
        "output_dir": None,
        "proxy_limit": DEFAULT_AUDIO_PROXY_LIMIT,
        "video_height": 540,
        "fps": 15,
        "crf": 36,
        "preset": "veryfast",
        "audio_bitrate": "48k",
        "audio_sample_rate": 48000,
        "audio_channels": 1,
    }
    if isinstance(project.get("web_media"), dict):
        settings.update(project["web_media"])
    if isinstance(landing.get("web_media"), dict):
        settings.update(landing["web_media"])
    return settings


def proxy_key(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12]
    return f"{safe_stem(path.stem)}-{digest}"


def run_proxy_command(command: list[str], dry_run: bool) -> bool:
    print(command_text(command), flush=True)
    if dry_run:
        return True
    completed = subprocess.run(command)
    return completed.returncode == 0


def build_source_media_proxies(
    project: dict[str, Any],
    project_path: Path,
    site_dir: Path,
    dry_run: bool,
) -> dict[str, dict[str, Any]]:
    settings = web_media_settings(project)
    if not settings.get("enabled", True):
        return {}
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found; landing page will reference source media directly.")
        return {}

    output_value = settings.get("output_dir")
    output_base = project_path.parent if output_value is not None else site_dir
    output_dir = resolve_path(output_value, output_base, site_dir / "media")
    if not path_inside(output_dir, SCRIPT_DIR):
        raise SystemExit("web_media output_dir must stay inside the SIMVLTANEA repository root.")
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    video_height = max(120, int(settings.get("video_height", 540)))
    fps = max(1, int(settings.get("fps", 15)))
    crf = min(51, max(0, int(settings.get("crf", 36))))
    preset = str(settings.get("preset", "veryfast"))
    audio_bitrate = str(settings.get("audio_bitrate", "48k"))
    audio_sample_rate = max(8000, int(settings.get("audio_sample_rate", 48000)))
    audio_channels = max(1, int(settings.get("audio_channels", 1)))
    proxy_limit = int(settings.get("proxy_limit", DEFAULT_AUDIO_PROXY_LIMIT))
    entries = project_clip_entries(project, project_path.parent)
    if proxy_limit > 0:
        entries = entries[:proxy_limit]

    proxies: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries, start=1):
        source = entry["path"]
        if not source.exists():
            continue
        key = proxy_key(source)
        video_out = output_dir / f"{index:03d}-{key}.mp4"
        audio_out = output_dir / f"{index:03d}-{key}.m4a"

        if not fresh_enough(source, video_out):
            video_filter = f"scale=-2:{video_height},fps={fps},format=yuv420p"
            video_command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-movflags",
                "+faststart",
                str(video_out),
            ]
            if not run_proxy_command(video_command, dry_run):
                print(f"warning: could not create video proxy for {source.name}")

        has_audio = probe_audio_stream(source)
        if has_audio and not fresh_enough(source, audio_out):
            if audio_channels == 1:
                audio_filter_options = ["-af", "pan=mono|c0=0.5*c0+0.5*c1"]
            else:
                audio_filter_options = ["-ac", str(audio_channels)]
            audio_command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                *audio_filter_options,
                "-ar",
                str(audio_sample_rate),
                "-c:a",
                "aac",
                "-b:a",
                audio_bitrate,
                "-movflags",
                "+faststart",
                str(audio_out),
            ]
            if not run_proxy_command(audio_command, dry_run):
                print(f"warning: could not create audio proxy for {source.name}")

        video_src = relative_media(video_out, site_dir) if video_out.exists() else None
        audio_src = relative_media(audio_out, site_dir) if has_audio and audio_out.exists() else None
        proxies[str(source)] = {
            "video_src": video_src,
            "audio_src": audio_src,
            "has_audio": has_audio,
            "proxy": bool(video_src),
        }
    return proxies


def landing_payload(
    project: dict[str, Any],
    project_path: Path,
    exports: list[dict[str, Any]],
    site_dir: Path,
    media_proxies: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project_base = project_path.parent
    media_proxies = media_proxies or {}
    source_videos = []
    for entry in project_clip_entries(project, project_base):
        path = entry["path"]
        proxy = media_proxies.get(str(path), {})
        source_src = relative_media(path, site_dir)
        src = proxy.get("video_src") or source_src
        if src is not None:
            source_videos.append(
                {
                    "name": path.name,
                    "src": src,
                    "audioSrc": proxy.get("audio_src"),
                    "proxy": bool(proxy.get("proxy")),
                    "hasAudio": bool(proxy.get("has_audio")),
                    "duration": entry.get("duration"),
                    "created": entry.get("source_created"),
                    "originalFilename": entry.get("original_filename"),
                    "width": entry.get("width"),
                    "height": entry.get("height"),
                }
            )

    export_videos = []
    for export in exports:
        output_file = resolve_path(
            export.get("output_file"),
            project_base,
            SCRIPT_DIR / "renders" / f"{export['name']}.mp4",
        )
        artifact_file = site_export_artifact_path(output_file, site_dir)
        exists = output_file.exists() or bool(artifact_file and artifact_file.exists())
        src = export_media_src(output_file, site_dir)
        if src is not None and exists:
            export_videos.append(
                {
                    "name": export.get("name", output_file.stem),
                    "layout": export.get("layout", "story"),
                    "src": src,
                    "exists": exists,
                }
            )

    for sketch in visual_sketch_definitions(project):
        output_file = resolve_path(
            sketch.get("output_file"),
            project_base,
            SCRIPT_DIR / "renders" / f"{sketch['name']}.mp4",
        )
        artifact_file = site_export_artifact_path(output_file, site_dir)
        exists = output_file.exists() or bool(artifact_file and artifact_file.exists())
        src = export_media_src(output_file, site_dir)
        if src is not None and exists:
            export_videos.append(
                {
                    "name": sketch.get("name", output_file.stem),
                    "layout": sketch.get("layout", "visual-sketch"),
                    "src": src,
                    "exists": exists,
                }
            )

    return {
        "title": project.get("title", "Triptych Video Canon"),
        "subtitle": project.get("subtitle", "A three-panel canon for moving image fragments."),
        "originalReference": project.get("original_reference"),
        "timingMode": project.get("timing_mode", "clip"),
        "panelOrder": normalize_panel_order(
            project.get("panel_order", project.get("canvas", {}).get("panel_order"))
        ),
        "effects": project.get("effects", {}),
        "audio": project.get("audio", {}),
        "webMedia": web_media_settings(project),
        "canvas": project.get("canvas", {}),
        "render": project.get("render", {}),
        "arrangementScore": arrangement_score(project),
        "controlPresets": control_presets(project),
        "prompts": project.get("prompts", []),
        "sourceVideos": source_videos,
        "exports": export_videos,
    }


def build_landing_page(
    project: dict[str, Any],
    project_path: Path,
    exports: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    landing = project.get("landing_page", {})
    output_file = resolve_path(
        landing.get("output_file"),
        project_path.parent,
        SCRIPT_DIR / "site" / "index.html",
    )
    if not path_inside(output_file, SCRIPT_DIR):
        raise SystemExit("landing_page output_file must stay inside the SIMVLTANEA repository root.")

    site_dir = output_file.parent
    media_proxies = build_source_media_proxies(project, project_path, site_dir, dry_run)
    payload = landing_payload(project, project_path, exports, site_dir, media_proxies)
    page = landing_html(payload)
    print(f"write landing page {output_file}")
    if dry_run:
        return
    site_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(page, encoding="utf-8")


def landing_html_legacy(payload: dict[str, Any]) -> str:
    title = html.escape(str(payload["title"]))
    subtitle = html.escape(str(payload["subtitle"]))
    data = json.dumps(payload).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #f7f4ed;
      --ink: #161615;
      --muted: #69645b;
      --line: #c9c1b2;
      --accent: #9f2f24;
      --steel: #3e6670;
      --olive: #6e7048;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 45vw) 1fr;
    }}
    .stage {{
      min-height: 100vh;
      padding: 20px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 14px;
      background: #11100f;
      color: #f6f1e8;
    }}
    .bar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      border-bottom: 1px solid rgba(246, 241, 232, 0.22);
      padding-bottom: 12px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: clamp(24px, 4vw, 48px); line-height: 0.96; font-weight: 720; }}
    .mode {{ color: #d8cdbd; font-size: 13px; text-transform: uppercase; letter-spacing: 0; }}
    .triptych {{
      align-self: center;
      justify-self: center;
      width: min(100%, 46vh);
      aspect-ratio: 9 / 16;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      border: 1px solid rgba(246, 241, 232, 0.32);
      background: #050505;
      overflow: hidden;
    }}
    .panel {{
      position: relative;
      min-width: 0;
      border-left: 1px solid rgba(246, 241, 232, 0.18);
      background: #070707;
    }}
    .panel:first-child {{ border-left: 0; }}
    .panel video {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .panel span {{
      position: absolute;
      left: 8px;
      bottom: 8px;
      right: 8px;
      color: #f6f1e8;
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    button, a.export {{
      border: 1px solid currentColor;
      background: transparent;
      color: inherit;
      min-height: 36px;
      padding: 7px 10px;
      font: inherit;
      text-decoration: none;
      cursor: pointer;
    }}
    button:hover, a.export:hover {{ background: rgba(246, 241, 232, 0.12); }}
    .workspace {{
      min-height: 100vh;
      padding: 24px;
      display: grid;
      align-content: start;
      gap: 24px;
    }}
    .summary {{
      display: grid;
      gap: 8px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}
    .summary p {{ color: var(--muted); max-width: 68ch; line-height: 1.45; }}
    .columns {{
      display: grid;
      grid-template-columns: repeat(2, minmax(240px, 1fr));
      gap: 20px;
    }}
    .lane {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: 0; }}
    textarea {{
      width: 100%;
      min-height: 110px;
      resize: vertical;
      border: 1px solid var(--line);
      background: #fffdf8;
      color: var(--ink);
      padding: 10px;
      font: inherit;
    }}
    .workspace button {{ color: var(--ink); }}
    ol, ul {{
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .clip {{
      display: grid;
      grid-template-columns: 1fr auto auto;
      align-items: center;
      gap: 8px;
      border-top: 1px solid var(--line);
      padding: 8px 0;
      color: var(--ink);
    }}
    .clip-name {{
      overflow-wrap: anywhere;
      color: var(--muted);
      font-size: 13px;
    }}
    .exports {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .exports a {{
      color: var(--accent);
      border-color: var(--accent);
    }}
    @media (max-width: 860px) {{
      main {{ grid-template-columns: 1fr; }}
      .stage {{ min-height: 72vh; }}
      .workspace {{ min-height: auto; }}
      .columns {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="stage">
      <div class="bar">
        <h1>{title}</h1>
        <div class="mode" id="mode"></div>
      </div>
      <div class="triptych" aria-label="Triptych preview">
        <div class="panel" data-panel="0"><video muted playsinline loop></video><span></span></div>
        <div class="panel" data-panel="1"><video muted playsinline loop></video><span></span></div>
        <div class="panel" data-panel="2"><video muted playsinline loop></video><span></span></div>
      </div>
      <div class="controls">
        <button type="button" id="shuffle">New Canon</button>
        <button type="button" id="play">Play</button>
        <button type="button" id="pause">Pause</button>
      </div>
    </section>
    <section class="workspace">
      <div class="summary">
        <h2>Surface</h2>
        <p>{subtitle}</p>
        <div class="exports" id="exports"></div>
      </div>
      <div class="columns">
        <div class="lane">
          <h2>Prompt Stack</h2>
          <ol id="prompts"></ol>
          <textarea id="promptText" placeholder="Add the next direction"></textarea>
          <button type="button" id="addPrompt">Add Prompt</button>
        </div>
        <div class="lane">
          <h2>Clip Order</h2>
          <div id="clips"></div>
        </div>
      </div>
    </section>
  </main>
  <script id="canon-data" type="application/json">{data}</script>
  <script>
    const data = JSON.parse(document.getElementById("canon-data").textContent);
    const saved = JSON.parse(localStorage.getItem("triptych-canon-state") || "{{}}");
    const state = {{
      clips: saved.clips || data.sourceVideos || [],
      prompts: saved.prompts || data.prompts || []
    }};

    const panels = Array.from(document.querySelectorAll(".panel"));
    const promptList = document.getElementById("prompts");
    const clipList = document.getElementById("clips");
    const exportsNode = document.getElementById("exports");
    document.getElementById("mode").textContent = data.timingMode + " timing";

    function persist() {{
      localStorage.setItem("triptych-canon-state", JSON.stringify(state));
    }}

    function rotateIndex(base, offset) {{
      if (!state.clips.length) return -1;
      return (base + offset) % state.clips.length;
    }}

    function setPanels(base = Math.floor(Math.random() * Math.max(state.clips.length, 1))) {{
      panels.forEach((panel, panelIndex) => {{
        const video = panel.querySelector("video");
        const label = panel.querySelector("span");
        const clipIndex = rotateIndex(base, panelIndex);
        if (clipIndex < 0) {{
          video.removeAttribute("src");
          label.textContent = "No clips yet";
          return;
        }}
        const clip = state.clips[clipIndex];
        video.src = clip.src;
        video.load();
        video.play().catch(() => {{}});
        label.textContent = clip.name;
      }});
    }}

    function renderPrompts() {{
      promptList.innerHTML = "";
      state.prompts.forEach((prompt) => {{
        const item = document.createElement("li");
        item.textContent = typeof prompt === "string" ? prompt : prompt.text;
        promptList.appendChild(item);
      }});
    }}

    function moveClip(index, direction) {{
      const next = index + direction;
      if (next < 0 || next >= state.clips.length) return;
      const [clip] = state.clips.splice(index, 1);
      state.clips.splice(next, 0, clip);
      persist();
      renderClips();
      setPanels(0);
    }}

    function renderClips() {{
      clipList.innerHTML = "";
      if (!state.clips.length) {{
        clipList.textContent = "No local clip paths were embedded in this page.";
        return;
      }}
      state.clips.forEach((clip, index) => {{
        const row = document.createElement("div");
        row.className = "clip";
        const name = document.createElement("div");
        name.className = "clip-name";
        name.textContent = clip.name;
        const up = document.createElement("button");
        up.type = "button";
        up.textContent = "Up";
        up.addEventListener("click", () => moveClip(index, -1));
        const down = document.createElement("button");
        down.type = "button";
        down.textContent = "Down";
        down.addEventListener("click", () => moveClip(index, 1));
        row.append(name, up, down);
        clipList.appendChild(row);
      }});
    }}

    function renderExports() {{
      exportsNode.innerHTML = "";
      data.exports.forEach((entry) => {{
        if (!entry.exists) return;
        const link = document.createElement("a");
        link.className = "export";
        link.href = entry.src;
        link.textContent = entry.name;
        exportsNode.appendChild(link);
      }});
    }}

    document.getElementById("shuffle").addEventListener("click", () => setPanels());
    document.getElementById("play").addEventListener("click", () => {{
      panels.forEach((panel) => panel.querySelector("video").play().catch(() => {{}}));
    }});
    document.getElementById("pause").addEventListener("click", () => {{
      panels.forEach((panel) => panel.querySelector("video").pause());
    }});
    document.getElementById("addPrompt").addEventListener("click", () => {{
      const text = document.getElementById("promptText").value.trim();
      if (!text) return;
      state.prompts.push({{ date: new Date().toISOString().slice(0, 10), text }});
      document.getElementById("promptText").value = "";
      persist();
      renderPrompts();
    }});

    renderPresetOptions();
    renderPrompts();
    renderClips();
    renderExports();
    setPanels(0);
    window.setInterval(() => setPanels(), 12000);
  </script>
</body>
</html>
"""


def landing_html(payload: dict[str, Any]) -> str:
    title = html.escape(str(payload["title"]))
    data = json.dumps(payload).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --black: #030303;
      --ink: #f7f1e8;
      --muted: #b9b0a2;
      --paper: #f4efe6;
      --paper-ink: #161615;
      --paper-muted: #625c52;
      --line: rgba(247, 241, 232, 0.2);
      --paper-line: #cfc5b7;
      --accent: #c45038;
      --steel: #5e8a94;
    }}
    * {{ box-sizing: border-box; }}
    html {{ background: var(--black); }}
    body {{
      margin: 0;
      min-height: 100vh;
      min-height: 100svh;
      overflow: hidden;
      background: var(--black);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    button, input, select, textarea {{ font: inherit; }}
    button, a.export {{
      border: 1px solid currentColor;
      background: transparent;
      color: inherit;
      min-height: 40px;
      padding: 8px 12px;
      text-decoration: none;
      cursor: pointer;
    }}
    button:hover, a.export:hover {{ background: rgba(247, 241, 232, 0.12); }}
    button:focus-visible, a:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible {{
      outline: 2px solid var(--steel);
      outline-offset: 2px;
    }}
    h1, h2, p {{ margin: 0; }}
    .surface {{
      position: fixed;
      inset: 0;
      display: grid;
      place-items: stretch;
      background: var(--black);
    }}
    .triptych {{
      position: relative;
      width: 100vw;
      height: 100vh;
      height: 100svh;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      background: #000;
      overflow: hidden;
    }}
    .panel {{
      position: relative;
      min-width: 0;
      overflow: hidden;
      background: #030303;
      border-left: 1px solid rgba(247, 241, 232, 0.16);
    }}
    .panel:first-child {{ border-left: 0; }}
    .panel video {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      background: #030303;
    }}
    .sketch-preview {{
      position: absolute;
      inset: 0;
      z-index: 2;
      display: none;
      width: 100%;
      height: 100%;
      object-fit: cover;
      background: #030303;
    }}
    .surface.is-sketch .panel {{
      visibility: hidden;
    }}
    .surface.is-sketch .sketch-preview {{
      display: block;
    }}
    .panel.is-empty video {{ opacity: 0; }}
    .panel-meta {{
      position: absolute;
      left: 10px;
      right: 10px;
      bottom: 10px;
      min-height: 22px;
      color: var(--ink);
      font-size: 12px;
      line-height: 1.2;
      overflow-wrap: anywhere;
      opacity: 0;
      transition: opacity 160ms ease;
      text-shadow: 0 1px 6px rgba(0, 0, 0, 0.8);
      pointer-events: none;
    }}
    .surface.show-labels .panel-meta {{ opacity: 1; }}
    .chrome {{
      position: fixed;
      inset: 14px 14px auto 14px;
      z-index: 3;
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 16px;
      pointer-events: none;
      opacity: 0.18;
      transition: opacity 160ms ease;
    }}
    .surface:hover .chrome,
    .surface.controls-visible .chrome,
    body.settings-open .chrome {{
      opacity: 1;
    }}
    .mark,
    .chrome-actions {{ pointer-events: auto; }}
    .mark {{
      display: grid;
      gap: 4px;
      max-width: min(440px, 54vw);
      padding: 10px 12px;
      background: rgba(3, 3, 3, 0.46);
      border: 1px solid rgba(247, 241, 232, 0.16);
      backdrop-filter: blur(14px);
    }}
    h1 {{
      font-size: 15px;
      line-height: 1;
      font-weight: 680;
    }}
    .status {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .chrome-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: end;
    }}
    .chrome button {{
      min-width: 56px;
      height: 42px;
      padding: 0 11px;
      border-color: rgba(247, 241, 232, 0.55);
      background: rgba(3, 3, 3, 0.44);
      backdrop-filter: blur(14px);
      color: var(--ink);
    }}
    .scrim {{
      position: fixed;
      inset: 0;
      z-index: 4;
      background: rgba(0, 0, 0, 0.46);
      opacity: 0;
      pointer-events: none;
      transition: opacity 160ms ease;
    }}
    body.settings-open .scrim {{
      opacity: 1;
      pointer-events: auto;
    }}
    .settings {{
      position: fixed;
      z-index: 5;
      top: 0;
      right: 0;
      bottom: 0;
      width: min(440px, 100vw);
      display: grid;
      grid-template-rows: auto 1fr;
      background: var(--paper);
      color: var(--paper-ink);
      border-left: 1px solid var(--paper-line);
      transform: translateX(100%);
      transition: transform 180ms ease;
      box-shadow: -18px 0 42px rgba(0, 0, 0, 0.32);
    }}
    body.settings-open .settings {{ transform: translateX(0); }}
    .settings-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 62px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--paper-line);
    }}
    .settings-head h2 {{
      font-size: 16px;
      line-height: 1;
    }}
    .settings-body {{
      overflow: auto;
      padding: 0 14px 20px;
    }}
    details {{
      border-bottom: 1px solid var(--paper-line);
      padding: 13px 0;
    }}
    summary {{
      cursor: pointer;
      font-weight: 650;
      list-style-position: inside;
    }}
    .stack {{
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }}
    .exports {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .exports a {{
      color: #9f2f24;
      border-color: #9f2f24;
    }}
    textarea {{
      width: 100%;
      min-height: 106px;
      resize: vertical;
      border: 1px solid var(--paper-line);
      background: #fffdf8;
      color: var(--paper-ink);
      padding: 10px;
    }}
    .settings button {{
      color: var(--paper-ink);
      border-color: var(--paper-ink);
      min-height: 36px;
      padding: 7px 10px;
    }}
    ol {{
      margin: 0;
      padding-left: 22px;
      color: var(--paper-muted);
      line-height: 1.42;
    }}
    .clip-list {{
      display: grid;
      gap: 0;
    }}
    .clip {{
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      align-items: center;
      gap: 7px;
      min-height: 46px;
      padding: 7px 0;
      border-top: 1px solid var(--paper-line);
    }}
    .clip:first-child {{ border-top: 0; }}
    .clip.is-hidden {{ opacity: 0.48; }}
    .clip-name {{
      min-width: 0;
      color: var(--paper-muted);
      font-size: 12px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .mini-row {{
      display: grid;
      grid-template-columns: 86px 1fr;
      align-items: center;
      gap: 10px;
      color: var(--paper-muted);
      font-size: 13px;
    }}
    .mini-row input[type="range"],
    .mini-row select {{
      width: 100%;
    }}
    .arrange-board {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .arrange-slot {{
      display: grid;
      gap: 6px;
      align-content: start;
      min-width: 0;
      min-height: 96px;
      padding: 8px;
      border: 1px solid var(--paper-line);
      background: #fffdf8;
    }}
    .arrange-slot strong,
    .arrange-slot span {{
      display: block;
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .arrange-slot strong {{
      font-size: 13px;
      line-height: 1.1;
    }}
    .arrange-slot span {{
      color: var(--paper-muted);
      font-size: 11px;
      line-height: 1.1;
    }}
    .arrange-actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 5px;
      margin-top: 2px;
    }}
    .settings .arrange-actions button {{
      min-width: 0;
      min-height: 30px;
      padding: 4px 6px;
    }}
    .share-url {{
      width: 100%;
      min-width: 0;
      border: 1px solid var(--paper-line);
      background: #fffdf8;
      color: var(--paper-muted);
      padding: 8px;
      font-size: 12px;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      color: var(--paper-muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .score-card {{
      display: grid;
      gap: 8px;
      border: 1px solid var(--paper-line);
      background: #fffdf8;
      padding: 10px;
      color: var(--paper-muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .score-card strong {{
      display: block;
      color: var(--paper-ink);
      font-size: 14px;
      line-height: 1.2;
    }}
    .score-card dl {{
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 6px 10px;
      margin: 0;
    }}
    .score-card dt {{
      color: var(--paper-ink);
    }}
    .score-card dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    .empty {{
      color: var(--paper-muted);
      font-size: 13px;
    }}
    @media (max-aspect-ratio: 3 / 4) {{
      .surface {{ place-items: center; }}
      .triptych {{
        width: min(100vw, calc(100svh * 9 / 16));
        height: min(100svh, calc(100vw * 16 / 9));
      }}
      .mark {{ max-width: calc(100vw - 28px); }}
    }}
    @media (max-width: 700px) {{
      .chrome {{ inset: 10px 10px auto 10px; }}
      .mark {{ display: none; }}
      .chrome-actions {{ width: 100%; }}
      .chrome button {{
        min-width: 0;
        flex: 1 1 0;
      }}
      .settings {{ width: 100vw; }}
      .clip {{ grid-template-columns: 1fr auto auto; }}
      .clip button[data-action="hide"] {{ grid-column: 2 / 4; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .chrome,
      .panel-meta,
      .scrim,
      .settings {{
        transition: none;
      }}
    }}
  </style>
</head>
<body>
  <main class="surface" id="surface">
    <section class="triptych" aria-label="Triptych canon preview">
      <div class="panel is-empty" data-panel="0"><video muted playsinline loop></video><span class="panel-meta"></span></div>
      <div class="panel is-empty" data-panel="1"><video muted playsinline loop></video><span class="panel-meta"></span></div>
      <div class="panel is-empty" data-panel="2"><video muted playsinline loop></video><span class="panel-meta"></span></div>
      <video class="sketch-preview" id="sketchPreview" muted playsinline loop></video>
    </section>
    <div class="chrome" aria-label="Preview controls">
      <div class="mark">
        <h1>{title}</h1>
        <p class="status" id="status"></p>
      </div>
      <div class="chrome-actions">
        <button type="button" id="playToggle">Pause</button>
        <button type="button" id="restart">Restart</button>
        <button type="button" id="fullscreen">Full</button>
        <button type="button" id="settingsOpen">Settings</button>
      </div>
    </div>
  </main>
  <div class="scrim" id="scrim"></div>
  <aside class="settings" id="settings" aria-hidden="true">
    <div class="settings-head">
      <h2>Settings</h2>
      <button type="button" id="settingsClose">Close</button>
    </div>
    <div class="settings-body">
      <details open>
        <summary>Preview</summary>
        <div class="stack">
          <div class="mini-row">
            <span>Preset</span>
            <select id="presetMode"></select>
          </div>
          <div class="mini-row">
            <span>Labels</span>
            <button type="button" id="labelsToggle">Show</button>
          </div>
          <div class="mini-row">
            <span>Audio</span>
            <button type="button" id="audioToggle">Off</button>
          </div>
          <div class="mini-row">
            <span>Surface</span>
            <select id="surfaceMode">
              <option value="canon">Canon</option>
              <option value="sketch">Sketch</option>
            </select>
          </div>
          <div class="mini-row">
            <span>Volume</span>
            <input type="range" id="volume" min="0" max="1" value="0.35" step="0.01">
          </div>
          <div class="mini-row">
            <span>Left Vol</span>
            <input type="range" id="leftVolume" min="0" max="1.5" value="1" step="0.01">
          </div>
          <div class="mini-row">
            <span>Mid Vol</span>
            <input type="range" id="middleVolume" min="0" max="1.5" value="1" step="0.01">
          </div>
          <div class="mini-row">
            <span>Right Vol</span>
            <input type="range" id="rightVolume" min="0" max="1.5" value="1" step="0.01">
          </div>
          <div class="mini-row">
            <span>Start</span>
            <select id="startMode">
              <option value="oldest">Oldest</option>
              <option value="random">Random</option>
            </select>
          </div>
          <div class="mini-row">
            <span>Direction</span>
            <select id="directionMode">
              <option value="forward">Forward</option>
              <option value="reverse">Reverse</option>
              <option value="pingpong">Ping-pong</option>
            </select>
          </div>
          <div class="mini-row">
            <span>Panels</span>
            <select id="panelOrderMode">
              <option value="left,middle,right">Left / Middle / Right</option>
              <option value="left,right,middle">Left / Right / Middle</option>
              <option value="middle,left,right">Middle / Left / Right</option>
              <option value="middle,right,left">Middle / Right / Left</option>
              <option value="right,left,middle">Right / Left / Middle</option>
              <option value="right,middle,left">Right / Middle / Left</option>
            </select>
          </div>
          <div class="arrange-board" id="arrangeBoard" aria-label="Panel arrangement"></div>
          <div class="mini-row">
            <span>Link</span>
            <button type="button" id="writeLink">Write URL</button>
          </div>
          <input class="share-url" id="shareUrl" readonly aria-label="Share URL">
          <div class="meta-grid" id="previewMeta"></div>
        </div>
      </details>
      <details>
        <summary>Prompts</summary>
        <div class="stack">
          <ol id="prompts"></ol>
          <textarea id="promptText" placeholder="Add direction"></textarea>
          <button type="button" id="addPrompt">Add Prompt</button>
        </div>
      </details>
      <details>
        <summary>Score</summary>
        <div class="stack">
          <div class="score-card" id="scoreCard"></div>
        </div>
      </details>
      <details>
        <summary>Clips</summary>
        <div class="stack">
          <div class="exports">
            <button type="button" id="useAll">Use All</button>
            <button type="button" id="resetOrder">Reset Order</button>
          </div>
          <div class="clip-list" id="clips"></div>
        </div>
      </details>
      <details>
        <summary>Exports</summary>
        <div class="stack">
          <div class="exports" id="exports"></div>
        </div>
      </details>
    </div>
  </aside>
  <script id="canon-data" type="application/json">{data}</script>
  <script>
    const data = JSON.parse(document.getElementById("canon-data").textContent);
    const storageKey = "triptych-canon-state-v2";
    const arrangementScore = data.arrangementScore || {{}};
    const controlPresets = Array.isArray(data.controlPresets) ? data.controlPresets : [];

    function savedState() {{
      try {{
        return JSON.parse(localStorage.getItem(storageKey) || "{{}}") || {{}};
      }} catch (error) {{
        return {{}};
      }}
    }}

    const saved = savedState();
    const urlParams = new URLSearchParams(window.location.search);

    function normalizeClip(clip, index) {{
      return {{
        ...clip,
        id: clip.src || clip.name || String(index),
        hidden: Boolean(clip.hidden),
      }};
    }}

    function defaultPanelVolumes() {{
      const gains = data.audio && data.audio.panel_gains ? data.audio.panel_gains : {{}};
      return {{
        left: Number.isFinite(Number(gains.left)) ? Number(gains.left) : 1,
        middle: Number.isFinite(Number(gains.middle)) ? Number(gains.middle) : 1,
        right: Number.isFinite(Number(gains.right)) ? Number(gains.right) : 1,
      }};
    }}

    function normalizePanelOrder(value) {{
      const names = Array.isArray(value)
        ? value
        : String(value || "left,middle,right").split(",");
      const alias = {{
        c: "middle",
        center: "middle",
        l: "left",
        left: "left",
        m: "middle",
        mid: "middle",
        middle: "middle",
        r: "right",
        right: "right",
      }};
      let cleaned = names
        .map((name) => alias[String(name).trim().toLowerCase()] || String(name).trim())
        .filter(Boolean);
      if (cleaned.length === 1 && /^[lmr]{{3}}$/i.test(cleaned[0])) {{
        cleaned = cleaned[0].toLowerCase().split("").map((name) => alias[name]);
      }}
      const allowed = ["left", "middle", "right"];
      if (cleaned.length !== 3) return allowed;
      if (!allowed.every((name) => cleaned.includes(name))) return allowed;
      return cleaned;
    }}

    function firstParam(names) {{
      for (const name of names) {{
        if (urlParams.has(name)) return urlParams.get(name);
      }}
      return null;
    }}

    function flagParam(names, fallback) {{
      const value = firstParam(names);
      if (value === null) return fallback;
      const normalized = String(value).trim().toLowerCase();
      if (["1", "true", "yes", "on", "show"].includes(normalized)) return true;
      if (["0", "false", "no", "off", "hide"].includes(normalized)) return false;
      return fallback;
    }}

    function numberParam(names, fallback, min, max) {{
      const value = firstParam(names);
      if (value === null) return fallback;
      const number = Number(value);
      if (!Number.isFinite(number)) return fallback;
      return Math.min(max, Math.max(min, number));
    }}

    function finiteNumber(value, fallback) {{
      const number = Number(value);
      return Number.isFinite(number) ? number : fallback;
    }}

    function choiceParam(names, allowed, fallback) {{
      const value = firstParam(names);
      if (value === null) return fallback;
      const normalized = String(value).trim().toLowerCase();
      if (allowed.includes(normalized)) return normalized;
      return fallback;
    }}

    function surfaceParam(fallback, hasSketch) {{
      let value = choiceParam(["surface", "view", "mode"], ["canon", "sketch", "visual", "visual-sketch"], fallback);
      if (value === "visual" || value === "visual-sketch") value = "sketch";
      return value === "sketch" && hasSketch ? "sketch" : "canon";
    }}

    function presetById(id) {{
      if (!id) return null;
      const normalized = String(id).trim().toLowerCase();
      return controlPresets.find((preset) => String(preset.id || "").toLowerCase() === normalized) || null;
    }}

    function defaultPreset() {{
      return controlPresets.find((preset) => preset.default) || controlPresets[0] || null;
    }}

    function presetValue(preset, key, fallback) {{
      return preset && Object.prototype.hasOwnProperty.call(preset, key) ? preset[key] : fallback;
    }}

    const originalClips = (data.sourceVideos || []).map(normalizeClip);
    const defaultPanelOrder = normalizePanelOrder(data.panelOrder);
    const sketchExport = (data.exports || []).find((entry) => entry.layout === "visual-sketch" && entry.exists && entry.src);
    const savedHasValues = Object.keys(saved).length > 0;
    const urlPreset = presetById(firstParam(["preset"]));
    const basePreset = urlPreset || (!savedHasValues ? defaultPreset() : null);
    const defaultAudio = urlPreset
      ? Boolean(presetValue(urlPreset, "audio", data.audio && data.audio.mode && data.audio.mode !== "none"))
      : Object.prototype.hasOwnProperty.call(saved, "audio")
      ? Boolean(saved.audio)
      : Boolean(presetValue(basePreset, "audio", data.audio && data.audio.mode && data.audio.mode !== "none"));
    const savedPanelVolumes = saved.panelVolumes && typeof saved.panelVolumes === "object"
      ? saved.panelVolumes
      : defaultPanelVolumes();
    const presetPanelVolumes = basePreset && basePreset.panelVolumes && typeof basePreset.panelVolumes === "object"
      ? basePreset.panelVolumes
      : null;
    const savedSurface = saved.surfaceMode === "sketch" && sketchExport ? "sketch" : "canon";
    const state = {{
      presetId: urlPreset ? urlPreset.id : saved.presetId || (basePreset ? basePreset.id : ""),
      clips: Array.isArray(saved.clips) && saved.clips.length ? saved.clips.map(normalizeClip) : originalClips.map((clip) => ({{ ...clip }})),
      prompts: saved.prompts || data.prompts || [],
      labels: flagParam(["labels"], Boolean(presetValue(basePreset, "labels", saved.labels))),
      audio: flagParam(["audio"], defaultAudio),
      volume: numberParam(["volume", "vol"], Number.isFinite(Number(presetValue(basePreset, "volume", saved.volume))) ? Number(presetValue(basePreset, "volume", saved.volume)) : 0.35, 0, 1),
      panelVolumes: {{
        left: numberParam(["left", "leftVolume", "leftVol"], finiteNumber(presetPanelVolumes ? presetPanelVolumes.left : savedPanelVolumes.left, 1), 0, 1.5),
        middle: numberParam(["middle", "middleVolume", "middleVol", "mid", "midVol"], finiteNumber(presetPanelVolumes ? presetPanelVolumes.middle : savedPanelVolumes.middle, 1), 0, 1.5),
        right: numberParam(["right", "rightVolume", "rightVol"], finiteNumber(presetPanelVolumes ? presetPanelVolumes.right : savedPanelVolumes.right, 1), 0, 1.5),
      }},
      startMode: choiceParam(["start"], ["oldest", "random"], presetValue(basePreset, "start", saved.startMode || "oldest")),
      direction: choiceParam(["direction", "dir"], ["forward", "reverse", "pingpong"], presetValue(basePreset, "direction", saved.direction || (data.effects && data.effects.direction) || "forward")),
      panelOrder: normalizePanelOrder(firstParam(["order", "panels", "panelOrder"]) || presetValue(basePreset, "panelOrder", saved.panelOrder || defaultPanelOrder)),
      surfaceMode: surfaceParam(presetValue(basePreset, "surface", savedSurface), Boolean(sketchExport)),
      running: true,
    }};

    const surface = document.getElementById("surface");
    const panels = Array.from(document.querySelectorAll(".panel"));
    const promptList = document.getElementById("prompts");
    const clipList = document.getElementById("clips");
    const exportsNode = document.getElementById("exports");
    const statusNode = document.getElementById("status");
    const previewMeta = document.getElementById("previewMeta");
    const scoreCard = document.getElementById("scoreCard");
    const playToggle = document.getElementById("playToggle");
    const labelsToggle = document.getElementById("labelsToggle");
    const audioToggle = document.getElementById("audioToggle");
    const presetMode = document.getElementById("presetMode");
    const surfaceMode = document.getElementById("surfaceMode");
    const volumeInput = document.getElementById("volume");
    const sketchPreview = document.getElementById("sketchPreview");
    const panelVolumeInputs = {{
      left: document.getElementById("leftVolume"),
      middle: document.getElementById("middleVolume"),
      right: document.getElementById("rightVolume"),
    }};
    const startMode = document.getElementById("startMode");
    const directionMode = document.getElementById("directionMode");
    const panelOrderMode = document.getElementById("panelOrderMode");
    const arrangeBoard = document.getElementById("arrangeBoard");
    const shareUrl = document.getElementById("shareUrl");
    const panelIndexByName = {{
      left: 0,
      middle: 1,
      right: 2,
    }};

    let voices = [null, null, null];
    let nextClipIndex = 0;
    let roundStartedAt = 0;
    let roundDuration = 0;
    let timer = null;
    let effectFrame = null;
    let pauseStartedAt = 0;
    let controlsTimer = null;
    let audioContext = null;
    let audioGeneration = 0;
    let activeAudioNodes = [];
    let audioWarning = "";
    const decodedAudio = new Map();
    const directedAudio = new Map();

    function persist() {{
      localStorage.setItem(storageKey, JSON.stringify({{
        clips: state.clips,
        prompts: state.prompts,
        labels: state.labels,
        audio: state.audio,
        volume: state.volume,
        panelVolumes: state.panelVolumes,
        presetId: state.presetId,
        startMode: state.startMode,
        direction: state.direction,
        panelOrder: state.panelOrder,
        surfaceMode: state.surfaceMode,
      }}));
    }}

    function enabledClips() {{
      return state.clips.filter((clip) => !clip.hidden);
    }}

    function clipDuration(clip) {{
      const duration = Number(clip.duration);
      return Number.isFinite(duration) && duration > 0 ? Math.max(duration, 0.75) : 4;
    }}

    function clipLabel(clip) {{
      const date = clip.created ? clip.created + " " : "";
      const name = clip.originalFilename || clip.name || "clip";
      return date + name;
    }}

    function formatSeconds(value) {{
      const seconds = Math.max(0, Math.round(Number(value) || 0));
      const minutes = Math.floor(seconds / 60);
      const rest = String(seconds % 60).padStart(2, "0");
      return minutes + ":" + rest;
    }}

    function directionLabel() {{
      if (state.direction === "reverse") return "reverse";
      if (state.direction === "pingpong") return "ping-pong";
      return "forward";
    }}

    function panelOrderLabel() {{
      return state.panelOrder.join(" / ");
    }}

    function previewAudioActive() {{
      return state.audio;
    }}

    function audioStatus() {{
      if (!state.audio) return "preview off";
      if (audioWarning) return audioWarning;
      if (!voices.some((voice) => voice && voice.clip.audioSrc)) return "no audio proxies";
      if (audioContext && audioContext.state === "suspended") return "tap to unlock";
      return "preview on";
    }}

    function surfaceLabel() {{
      return state.surfaceMode === "sketch" ? "visual sketch" : "canon";
    }}

    function panelName(index) {{
      return ["left", "middle", "right"][index] || "left";
    }}

    function panelDisplayName(name) {{
      const names = {{
        left: "Left",
        middle: "Middle",
        right: "Right",
      }};
      return names[name] || name;
    }}

    function panelVoice(index) {{
      const sourceName = state.panelOrder[index] || panelName(index);
      return voices[panelIndexByName[sourceName] ?? index];
    }}

    function markCustomPreset() {{
      state.presetId = "";
    }}

    function renderPresetOptions() {{
      presetMode.innerHTML = "";
      const custom = document.createElement("option");
      custom.value = "";
      custom.textContent = "Custom";
      presetMode.appendChild(custom);
      controlPresets.forEach((preset) => {{
        const option = document.createElement("option");
        option.value = preset.id;
        option.textContent = preset.label || preset.id;
        presetMode.appendChild(option);
      }});
      presetMode.disabled = !controlPresets.length;
    }}

    function applyPreset(presetId) {{
      const preset = presetById(presetId);
      if (!preset) return;
      state.presetId = preset.id;
      if (Object.prototype.hasOwnProperty.call(preset, "labels")) state.labels = Boolean(preset.labels);
      if (Object.prototype.hasOwnProperty.call(preset, "audio")) state.audio = Boolean(preset.audio);
      if (Object.prototype.hasOwnProperty.call(preset, "volume")) state.volume = Math.min(1, Math.max(0, Number(preset.volume) || 0));
      if (preset.panelVolumes && typeof preset.panelVolumes === "object") {{
        ["left", "middle", "right"].forEach((name) => {{
          if (Object.prototype.hasOwnProperty.call(preset.panelVolumes, name)) {{
            state.panelVolumes[name] = Math.min(1.5, Math.max(0, Number(preset.panelVolumes[name]) || 0));
          }}
        }});
      }}
      if (preset.start === "oldest" || preset.start === "random") state.startMode = preset.start;
      if (["forward", "reverse", "pingpong"].includes(preset.direction)) state.direction = preset.direction;
      if (preset.panelOrder) state.panelOrder = normalizePanelOrder(preset.panelOrder);
      if (preset.surface) state.surfaceMode = surfaceParam(preset.surface, Boolean(sketchExport));
      persist();
      resetCanon();
    }}

    function setPanelOrder(nextOrder, custom = true) {{
      if (custom) markCustomPreset();
      state.panelOrder = normalizePanelOrder(nextOrder);
      persist();
      paintAllPanels();
      scheduleEffectLoop();
      scheduleRoundAudio();
    }}

    function movePanelOrder(index, delta) {{
      const target = index + delta;
      if (target < 0 || target >= state.panelOrder.length) return;
      const nextOrder = state.panelOrder.slice();
      const held = nextOrder[index];
      nextOrder[index] = nextOrder[target];
      nextOrder[target] = held;
      setPanelOrder(nextOrder);
    }}

    function renderArrangeBoard() {{
      arrangeBoard.innerHTML = "";
      state.panelOrder.forEach((name, index) => {{
        const slot = document.createElement("div");
        slot.className = "arrange-slot";
        slot.dataset.slot = String(index);

        const position = document.createElement("span");
        position.textContent = "Column " + String(index + 1);

        const label = document.createElement("strong");
        label.textContent = panelDisplayName(name);

        const actions = document.createElement("div");
        actions.className = "arrange-actions";
        [-1, 1].forEach((delta) => {{
          const button = document.createElement("button");
          button.type = "button";
          button.innerHTML = delta < 0 ? "&larr;" : "&rarr;";
          button.disabled = index + delta < 0 || index + delta >= state.panelOrder.length;
          button.setAttribute(
            "aria-label",
            "Move " + panelDisplayName(name) + (delta < 0 ? " left" : " right")
          );
          button.addEventListener("click", () => movePanelOrder(index, delta));
          actions.appendChild(button);
        }});

        slot.append(position, label, actions);
        arrangeBoard.appendChild(slot);
      }});
    }}

    function compactPanelOrder(order) {{
      const shortNames = {{
        left: "l",
        middle: "m",
        right: "r",
      }};
      return order.map((name) => shortNames[name] || name).join("");
    }}

    function formattedNumber(value) {{
      return String(Math.round(Number(value) * 100) / 100);
    }}

    function currentShareUrl() {{
      const url = new URL(window.location.href);
      if (state.presetId) {{
        url.searchParams.set("preset", state.presetId);
      }} else {{
        url.searchParams.delete("preset");
      }}
      url.searchParams.set("surface", state.surfaceMode);
      url.searchParams.set("dir", state.direction);
      url.searchParams.set("order", compactPanelOrder(state.panelOrder));
      url.searchParams.set("start", state.startMode);
      url.searchParams.set("labels", state.labels ? "1" : "0");
      url.searchParams.set("audio", state.audio ? "1" : "0");
      url.searchParams.set("vol", formattedNumber(state.volume));
      url.searchParams.set("left", formattedNumber(state.panelVolumes.left ?? 1));
      url.searchParams.set("middle", formattedNumber(state.panelVolumes.middle ?? 1));
      url.searchParams.set("right", formattedNumber(state.panelVolumes.right ?? 1));
      return url;
    }}

    async function writeShareUrl() {{
      const url = currentShareUrl();
      window.history.replaceState(null, "", url);
      shareUrl.value = url.toString();
      shareUrl.select();
      if (navigator.clipboard && window.isSecureContext) {{
        try {{
          await navigator.clipboard.writeText(shareUrl.value);
        }} catch (error) {{}}
      }}
    }}

    function panelGain(index) {{
      const panelVolume = Number(state.panelVolumes[panelName(index)]);
      const gain = Number.isFinite(panelVolume) ? panelVolume : 1;
      return Math.max(0, state.volume * gain);
    }}

    function ensureAudioContext() {{
      if (audioContext) return audioContext;
      const ContextClass = window.AudioContext || window.webkitAudioContext;
      if (!ContextClass) {{
        audioWarning = "WebAudio unavailable";
        return null;
      }}
      audioContext = new ContextClass();
      return audioContext;
    }}

    function reverseBuffer(buffer) {{
      const context = ensureAudioContext();
      if (!context) return null;
      const reversed = context.createBuffer(buffer.numberOfChannels, buffer.length, buffer.sampleRate);
      for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {{
        const input = buffer.getChannelData(channel);
        const output = reversed.getChannelData(channel);
        for (let index = 0; index < input.length; index += 1) {{
          output[index] = input[input.length - 1 - index];
        }}
      }}
      return reversed;
    }}

    function pingpongBuffer(buffer) {{
      const context = ensureAudioContext();
      if (!context) return null;
      const doubled = context.createBuffer(buffer.numberOfChannels, buffer.length * 2, buffer.sampleRate);
      for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {{
        const input = buffer.getChannelData(channel);
        const output = doubled.getChannelData(channel);
        for (let index = 0; index < input.length; index += 1) {{
          output[index] = input[index];
          output[input.length + index] = input[input.length - 1 - index];
        }}
      }}
      return doubled;
    }}

    async function loadAudioBuffer(clip) {{
      if (!clip.audioSrc) throw new Error("clip has no audio proxy");
      if (decodedAudio.has(clip.audioSrc)) return decodedAudio.get(clip.audioSrc);
      const context = ensureAudioContext();
      if (!context) throw new Error("WebAudio unavailable");
      const response = await fetch(clip.audioSrc);
      if (!response.ok) throw new Error("audio proxy fetch failed");
      const arrayBuffer = await response.arrayBuffer();
      const buffer = await context.decodeAudioData(arrayBuffer);
      decodedAudio.set(clip.audioSrc, buffer);
      return buffer;
    }}

    async function directionalAudioBuffer(clip) {{
      const base = await loadAudioBuffer(clip);
      if (state.direction === "forward") return base;
      const key = clip.audioSrc + "::" + state.direction;
      if (directedAudio.has(key)) return directedAudio.get(key);
      const buffer = state.direction === "reverse" ? reverseBuffer(base) : pingpongBuffer(base);
      if (!buffer) throw new Error("could not build direction buffer");
      directedAudio.set(key, buffer);
      return buffer;
    }}

    function roundElapsedSeconds() {{
      if (!roundDuration) return 0;
      return Math.min(roundDuration, Math.max(0, (performance.now() - roundStartedAt) / 1000));
    }}

    function roundRemainingSeconds() {{
      return Math.max(0, roundDuration - roundElapsedSeconds());
    }}

    function stopAudioNodes() {{
      audioGeneration += 1;
      activeAudioNodes.forEach((node) => {{
        try {{ node.source.stop(); }} catch (error) {{}}
        try {{ node.source.disconnect(); }} catch (error) {{}}
        try {{ node.gain.disconnect(); }} catch (error) {{}}
      }});
      activeAudioNodes = [];
    }}

    function updateActiveAudioGains() {{
      if (!audioContext) return;
      activeAudioNodes.forEach((node) => {{
        const nextGain = panelGain(node.panelIndex);
        try {{
          node.gain.gain.setTargetAtTime(nextGain, audioContext.currentTime, 0.015);
        }} catch (error) {{
          node.gain.gain.value = nextGain;
        }}
      }});
    }}

    async function scheduleVoiceAudio(index, voice, token) {{
      try {{
        const context = ensureAudioContext();
        if (!context) return;
        const buffer = await directionalAudioBuffer(voice.clip);
        if (token !== audioGeneration || !state.running || !state.audio || panelVoice(index) !== voice) return;
        const remaining = roundRemainingSeconds();
        if (remaining <= 0.04 || buffer.duration <= 0) return;
        const source = context.createBufferSource();
        const gain = context.createGain();
        const offset = roundElapsedSeconds() % buffer.duration;
        const startAt = context.currentTime + 0.02;
        gain.gain.value = panelGain(index);
        source.buffer = buffer;
        source.loop = true;
        source.connect(gain).connect(context.destination);
        source.start(startAt, offset, remaining);
        source.stop(startAt + remaining + 0.04);
        source.onended = () => {{
          activeAudioNodes = activeAudioNodes.filter((node) => node.source !== source);
          try {{ source.disconnect(); }} catch (error) {{}}
          try {{ gain.disconnect(); }} catch (error) {{}}
        }};
        activeAudioNodes.push({{ source, gain, panelIndex: index }});
      }} catch (error) {{
        audioWarning = "audio proxy decode failed";
        updateStatus();
      }}
    }}

    function scheduleRoundAudio() {{
      stopAudioNodes();
      if (!state.audio || !state.running || !roundDuration) {{
        updateStatus();
        return;
      }}
      const context = ensureAudioContext();
      if (!context) {{
        updateStatus();
        return;
      }}
      context.resume().catch(() => {{}});
      audioWarning = "";
      const token = audioGeneration;
      panels.forEach((_, index) => {{
        const voice = panelVoice(index);
        if (voice && voice.clip.audioSrc) {{
          scheduleVoiceAudio(index, voice, token);
        }}
      }});
      updateStatus();
    }}

    function newVoice(clip) {{
      return {{
        clip,
        duration: clipDuration(clip),
        startedAt: performance.now(),
      }};
    }}

    function currentRoundDuration() {{
      return voices.reduce((longest, voice) => {{
        return voice ? Math.max(longest, voice.duration) : longest;
      }}, 0);
    }}

    function clearPanel(index) {{
      const panel = panels[index];
      const video = panel.querySelector("video");
      panel.classList.add("is-empty");
      panel.querySelector(".panel-meta").textContent = "";
      video.pause();
      video.removeAttribute("src");
      delete video.dataset.src;
      video.load();
    }}

    function applyAudio(video, index) {{
      video.muted = true;
      video.volume = 0;
    }}

    function paintSketchSurface() {{
      if (!sketchExport) {{
        state.surfaceMode = "canon";
        return;
      }}
      if (sketchPreview.dataset.src !== sketchExport.src) {{
        sketchPreview.dataset.src = sketchExport.src;
        sketchPreview.src = sketchExport.src;
        sketchPreview.load();
      }}
      sketchPreview.muted = true;
      sketchPreview.volume = 0;
      if (state.running) {{
        sketchPreview.play().catch(() => {{}});
      }} else {{
        sketchPreview.pause();
      }}
    }}

    function manualPlaybackTime(voice, video, now) {{
      const realDuration = Number(video.duration);
      const duration = Number.isFinite(realDuration) && realDuration > 0
        ? realDuration
        : voice.duration;
      const safeDuration = Math.max(duration, 0.1);
      const elapsed = Math.max(0, (now - voice.startedAt) / 1000);
      if (state.direction === "reverse") {{
        const phase = elapsed % safeDuration;
        return Math.max(0.02, safeDuration - phase - 0.02);
      }}
      const cycle = safeDuration * 2;
      const pingPhase = elapsed % cycle;
      if (pingPhase <= safeDuration) {{
        return Math.min(Math.max(pingPhase, 0.02), safeDuration - 0.02);
      }}
      return Math.min(Math.max(cycle - pingPhase, 0.02), safeDuration - 0.02);
    }}

    function syncPanelTime(index, now) {{
      if (state.direction === "forward") return;
      const voice = panelVoice(index);
      if (!voice) return;
      const video = panels[index].querySelector("video");
      if (!video.duration || video.readyState === 0) return;
      const target = manualPlaybackTime(voice, video, now);
      if (Math.abs(video.currentTime - target) > 0.08) {{
        video.currentTime = target;
      }}
    }}

    function stopEffectLoop() {{
      if (effectFrame !== null) {{
        window.cancelAnimationFrame(effectFrame);
        effectFrame = null;
      }}
    }}

    function syncEffectPlayback() {{
      effectFrame = null;
      if (!state.running || state.direction === "forward") return;
      const now = performance.now();
      panels.forEach((panel, index) => {{
        const video = panel.querySelector("video");
        video.pause();
        syncPanelTime(index, now);
      }});
      effectFrame = window.requestAnimationFrame(syncEffectPlayback);
    }}

    function scheduleEffectLoop() {{
      stopEffectLoop();
      if (state.running && state.direction !== "forward") {{
        effectFrame = window.requestAnimationFrame(syncEffectPlayback);
      }}
    }}

    function paintPanel(index) {{
      const panel = panels[index];
      const video = panel.querySelector("video");
      const meta = panel.querySelector(".panel-meta");
      const voice = panelVoice(index);
      if (!voice) {{
        clearPanel(index);
        return;
      }}
      panel.classList.remove("is-empty");
      if (video.dataset.src !== voice.clip.src) {{
        video.dataset.src = voice.clip.src;
        video.src = voice.clip.src;
        video.currentTime = 0;
        video.load();
        video.addEventListener("loadedmetadata", () => syncPanelTime(index, performance.now()), {{ once: true }});
      }} else {{
        try {{
          if (state.direction === "forward") video.currentTime = 0;
        }} catch (error) {{}}
      }}
      video.loop = state.direction === "forward";
      video.playbackRate = 1;
      applyAudio(video, index);
      meta.textContent = clipLabel(voice.clip);
      if (state.running) {{
        if (state.direction === "forward") {{
          video.play().catch(() => {{}});
        }} else {{
          video.pause();
          syncPanelTime(index, performance.now());
        }}
      }}
    }}

    function paintAllPanels() {{
      panels.forEach((_, index) => paintPanel(index));
      surface.classList.toggle("is-sketch", state.surfaceMode === "sketch");
      if (state.surfaceMode === "sketch") {{
        paintSketchSurface();
      }} else {{
        sketchPreview.pause();
      }}
      surface.classList.toggle("show-labels", state.labels);
      labelsToggle.textContent = state.labels ? "Hide" : "Show";
      audioToggle.textContent = state.audio ? "On" : "Off";
      volumeInput.value = String(state.volume);
      Object.entries(panelVolumeInputs).forEach(([panelName, input]) => {{
        input.value = String(state.panelVolumes[panelName] ?? 1);
      }});
      startMode.value = state.startMode;
      directionMode.value = state.direction;
      panelOrderMode.value = state.panelOrder.join(",");
      presetMode.value = state.presetId && presetById(state.presetId) ? state.presetId : "";
      renderArrangeBoard();
      surfaceMode.value = state.surfaceMode;
      surfaceMode.disabled = !sketchExport;
      playToggle.textContent = state.running ? "Pause" : "Play";
      updateStatus();
    }}

    function beginRound() {{
      roundStartedAt = performance.now();
      roundDuration = currentRoundDuration();
      voices.forEach((voice) => {{
        if (voice) voice.startedAt = roundStartedAt;
      }});
      paintAllPanels();
      scheduleEffectLoop();
      scheduleRoundAudio();
      scheduleNext();
    }}

    function stepCanon() {{
      const clips = enabledClips();
      if (!clips.length) {{
        voices = [null, null, null];
        roundDuration = 0;
        stopEffectLoop();
        stopAudioNodes();
        paintAllPanels();
        return;
      }}
      const nextLeft = newVoice(clips[nextClipIndex % clips.length]);
      nextClipIndex += 1;
      voices = [
        nextLeft,
        voices[0] ? newVoice(voices[0].clip) : null,
        voices[1] ? newVoice(voices[1].clip) : null,
      ];
      beginRound();
    }}

    function nextDelay() {{
      const now = performance.now();
      const remaining = roundDuration * 1000 - (now - roundStartedAt);
      if (!Number.isFinite(remaining)) return 300;
      return Math.max(80, remaining + 20);
    }}

    function scheduleNext() {{
      window.clearTimeout(timer);
      if (!state.running) return;
      timer = window.setTimeout(stepCanon, nextDelay());
    }}

    function resetCanon() {{
      window.clearTimeout(timer);
      stopEffectLoop();
      stopAudioNodes();
      voices = [null, null, null];
      const clips = enabledClips();
      if (state.startMode === "random" && clips.length) {{
        nextClipIndex = Math.floor(Math.random() * clips.length);
      }} else {{
        nextClipIndex = 0;
      }}
      if (!clips.length) {{
        roundDuration = 0;
        paintAllPanels();
        return;
      }}
      voices[0] = newVoice(clips[nextClipIndex % clips.length]);
      nextClipIndex += 1;
      beginRound();
    }}

    function setRunning(nextRunning) {{
      if (state.running === nextRunning) return;
      state.running = nextRunning;
      if (state.running) {{
        const pausedFor = performance.now() - pauseStartedAt;
        roundStartedAt += pausedFor;
        voices.forEach((voice) => {{
          if (voice) voice.startedAt += pausedFor;
        }});
        if (state.direction === "forward") {{
          panels.forEach((panel) => panel.querySelector("video").play().catch(() => {{}}));
        }} else {{
          scheduleEffectLoop();
        }}
        if (state.surfaceMode === "sketch") {{
          sketchPreview.play().catch(() => {{}});
        }}
        scheduleRoundAudio();
        scheduleNext();
      }} else {{
        pauseStartedAt = performance.now();
        window.clearTimeout(timer);
        stopEffectLoop();
        stopAudioNodes();
        panels.forEach((panel) => panel.querySelector("video").pause());
        sketchPreview.pause();
      }}
      paintAllPanels();
    }}

    function moveClip(index, direction) {{
      const next = index + direction;
      if (next < 0 || next >= state.clips.length) return;
      const [clip] = state.clips.splice(index, 1);
      state.clips.splice(next, 0, clip);
      persist();
      renderClips();
      resetCanon();
    }}

    function toggleClip(index) {{
      state.clips[index].hidden = !state.clips[index].hidden;
      persist();
      renderClips();
      resetCanon();
    }}

    function renderClips() {{
      clipList.innerHTML = "";
      if (!state.clips.length) {{
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No clips.";
        clipList.appendChild(empty);
        return;
      }}
      state.clips.forEach((clip, index) => {{
        const row = document.createElement("div");
        row.className = "clip";
        row.classList.toggle("is-hidden", Boolean(clip.hidden));
        const name = document.createElement("div");
        name.className = "clip-name";
        name.textContent = clipLabel(clip) + " " + formatSeconds(clipDuration(clip));
        const up = document.createElement("button");
        up.type = "button";
        up.textContent = "Up";
        up.addEventListener("click", () => moveClip(index, -1));
        const down = document.createElement("button");
        down.type = "button";
        down.textContent = "Down";
        down.addEventListener("click", () => moveClip(index, 1));
        const hide = document.createElement("button");
        hide.type = "button";
        hide.dataset.action = "hide";
        hide.textContent = clip.hidden ? "Show" : "Hide";
        hide.addEventListener("click", () => toggleClip(index));
        row.append(name, up, down, hide);
        clipList.appendChild(row);
      }});
    }}

    function renderPrompts() {{
      promptList.innerHTML = "";
      state.prompts.forEach((prompt) => {{
        const item = document.createElement("li");
        item.textContent = typeof prompt === "string" ? prompt : prompt.text;
        promptList.appendChild(item);
      }});
    }}

    function renderExports() {{
      exportsNode.innerHTML = "";
      data.exports.forEach((entry) => {{
        if (!entry.exists) return;
        const link = document.createElement("a");
        link.className = "export";
        link.href = entry.src;
        link.textContent = entry.name;
        exportsNode.appendChild(link);
      }});
      if (!exportsNode.children.length) {{
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No rendered exports.";
        exportsNode.appendChild(empty);
      }}
    }}

    function scoreValue(key, fallback = "") {{
      const value = arrangementScore[key];
      return typeof value === "string" && value.trim() ? value.trim() : fallback;
    }}

    function renderScoreCard() {{
      scoreCard.innerHTML = "";
      const title = scoreValue("work_title", data.title || "Triptych Video Canon");
      const heading = document.createElement("strong");
      heading.textContent = title;
      scoreCard.appendChild(heading);

      const rows = [];
      const preview = scoreValue("preview_label");
      if (preview) rows.push(["Map", preview]);
      const material = scoreValue("material");
      if (material) rows.push(["Material", material]);
      const model = scoreValue("model");
      if (model) rows.push(["Model", model]);
      const role = scoreValue("panel_role") || scoreValue("model_role");
      if (role) rows.push(["Role", role]);
      const observation = scoreValue("observation");
      if (observation) rows.push(["Read", observation]);
      const language = Array.isArray(arrangementScore.language) ? arrangementScore.language.join(", ") : "";
      if (language) rows.push(["Terms", language]);
      const modelFit = scoreValue("model_fit");
      if (modelFit) rows.push(["Fit", modelFit]);

      if (!rows.length) {{
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No authored arrangement score metadata for this edition.";
        scoreCard.appendChild(empty);
        return;
      }}

      const list = document.createElement("dl");
      rows.forEach(([key, value]) => {{
        const dt = document.createElement("dt");
        const dd = document.createElement("dd");
        dt.textContent = key;
        dd.textContent = value;
        list.append(dt, dd);
      }});
      scoreCard.appendChild(list);
    }}

    function updateStatus() {{
      const clips = enabledClips();
      const active = voices
        .map((voice, index) => voice ? ["left", "middle", "right"][index] + ": " + (voice.clip.originalFilename || voice.clip.name) : null)
        .filter(Boolean)
        .join(" / ");
      statusNode.textContent = active || (clips.length ? data.timingMode + " timing" : "No clips");
      previewMeta.innerHTML = "";
      const rows = [
        ["Timing", data.timingMode || "clip"],
      ["Surface", surfaceLabel()],
      ["Effect", directionLabel()],
      ["Panels", panelOrderLabel()],
      ["Score", scoreValue("preview_label", "edition")],
      ["Round", roundDuration ? formatSeconds(roundDuration) + " hold" : "not started"],
      ["Clips", String(clips.length) + " visible"],
      ["Audio", audioStatus()],
      ];
      rows.forEach(([key, value]) => {{
        const k = document.createElement("span");
        const v = document.createElement("span");
        k.textContent = key;
        v.textContent = value;
        previewMeta.append(k, v);
      }});
    }}

    function openSettings() {{
      document.body.classList.add("settings-open");
      document.getElementById("settings").setAttribute("aria-hidden", "false");
    }}

    function closeSettings() {{
      document.body.classList.remove("settings-open");
      document.getElementById("settings").setAttribute("aria-hidden", "true");
    }}

    function showControlsBriefly() {{
      surface.classList.add("controls-visible");
      window.clearTimeout(controlsTimer);
      controlsTimer = window.setTimeout(() => surface.classList.remove("controls-visible"), 1600);
    }}

    document.getElementById("playToggle").addEventListener("click", () => setRunning(!state.running));
    document.getElementById("restart").addEventListener("click", resetCanon);
    document.getElementById("settingsOpen").addEventListener("click", openSettings);
    document.getElementById("settingsClose").addEventListener("click", closeSettings);
    document.getElementById("scrim").addEventListener("click", closeSettings);
    document.getElementById("fullscreen").addEventListener("click", () => {{
      if (document.fullscreenElement) {{
        document.exitFullscreen().catch(() => {{}});
      }} else {{
        document.documentElement.requestFullscreen().catch(() => {{}});
      }}
    }});
    document.getElementById("writeLink").addEventListener("click", () => {{
      writeShareUrl();
    }});
    presetMode.addEventListener("change", () => {{
      if (!presetMode.value) {{
        markCustomPreset();
        persist();
        paintAllPanels();
        return;
      }}
      applyPreset(presetMode.value);
    }});
    labelsToggle.addEventListener("click", () => {{
      markCustomPreset();
      state.labels = !state.labels;
      persist();
      paintAllPanels();
    }});
    audioToggle.addEventListener("click", () => {{
      markCustomPreset();
      state.audio = !state.audio;
      if (state.audio) {{
        ensureAudioContext();
        scheduleRoundAudio();
      }} else {{
        stopAudioNodes();
      }}
      persist();
      paintAllPanels();
    }});
    volumeInput.addEventListener("input", () => {{
      markCustomPreset();
      state.volume = Number(volumeInput.value);
      updateActiveAudioGains();
      persist();
      updateStatus();
    }});
    Object.entries(panelVolumeInputs).forEach(([panelName, input]) => {{
      input.addEventListener("input", () => {{
        markCustomPreset();
        state.panelVolumes[panelName] = Number(input.value);
        updateActiveAudioGains();
        persist();
        updateStatus();
      }});
    }});
    startMode.addEventListener("change", () => {{
      markCustomPreset();
      state.startMode = startMode.value;
      persist();
      resetCanon();
    }});
    directionMode.addEventListener("change", () => {{
      markCustomPreset();
      state.direction = directionMode.value;
      persist();
      paintAllPanels();
      scheduleEffectLoop();
      scheduleRoundAudio();
    }});
    surfaceMode.addEventListener("change", () => {{
      markCustomPreset();
      state.surfaceMode = surfaceMode.value === "sketch" && sketchExport ? "sketch" : "canon";
      persist();
      paintAllPanels();
    }});
    panelOrderMode.addEventListener("change", () => {{
      setPanelOrder(panelOrderMode.value);
    }});
    document.getElementById("useAll").addEventListener("click", () => {{
      state.clips.forEach((clip) => {{
        clip.hidden = false;
      }});
      persist();
      renderClips();
      resetCanon();
    }});
    document.getElementById("resetOrder").addEventListener("click", () => {{
      state.clips = originalClips.map((clip) => ({{ ...clip }}));
      persist();
      renderClips();
      resetCanon();
    }});
    document.getElementById("addPrompt").addEventListener("click", () => {{
      const text = document.getElementById("promptText").value.trim();
      if (!text) return;
      state.prompts.push({{ date: new Date().toISOString().slice(0, 10), text }});
      document.getElementById("promptText").value = "";
      persist();
      renderPrompts();
    }});
    window.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") closeSettings();
      if (event.key === " ") {{
        event.preventDefault();
        setRunning(!state.running);
      }}
    }});
    ["pointermove", "pointerdown", "keydown"].forEach((eventName) => {{
      window.addEventListener(eventName, showControlsBriefly, {{ passive: true }});
    }});

    renderPrompts();
    renderClips();
    renderExports();
    renderScoreCard();
    paintAllPanels();
    resetCanon();
    showControlsBriefly();
  </script>
</body>
</html>
"""


def require_legacy_audio(audio: dict[str, Any]) -> None:
    """Keep edition metadata from implying a v1.1-capable historical player."""
    if audio.get("mode") in ("soundtrack", "spatial_loops"):
        raise SystemExit(
            "Audio v1.1 requires a hashed composition state: use "
            "core/render_triptych.py --state STATE --orientation portrait|landscape "
            "or core/browser_runtime.py; this historical project exporter uses none/panel/mix."
        )


def main() -> int:
    args = parse_args()
    if args.draft_videos <= 0:
        raise SystemExit("--draft-videos must be positive.")
    project, project_path = load_project(args.project)
    apply_audio_overrides(project, args)
    require_legacy_audio(project.get("audio", {}))
    apply_effect_overrides(project, args)
    append_prompts(project, project_path, args.add_prompt or [])
    exports = selected_exports(
        export_definitions(project, include_disabled=bool(args.only)),
        args.only,
    )
    for export in exports:
        require_legacy_audio(export.get("audio", {}))
    if args.draft:
        exports = draft_exports(exports, args.draft_videos)

    skip_render = args.skip_render or args.landing_only
    if not skip_render:
        run_exports(project_path, project, exports, args.dry_run, args.keep_work)
    if not args.no_landing:
        build_landing_page(project, project_path, exports, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
