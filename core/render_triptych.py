#!/usr/bin/env python3
"""Render a three-panel canon from manually exported videos."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}
PANEL_NAMES = ("left", "middle", "right")
LAYOUTS = {
    "story": PANEL_NAMES,
    "left": ("left",),
    "middle": ("middle",),
    "right": ("right",),
}
TIMING_MODES = {"clip", "fixed"}
AUDIO_MODES = {"none", "panel", "mix"}
VIDEO_DIRECTIONS = {"forward", "reverse", "pingpong"}
TONE_MODES = {"none", "normalize", "histeq"}
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "core" else SCRIPT_DIR


@dataclass(frozen=True)
class Settings:
    input_dir: Path
    output_file: Path
    work_dir: Path
    timing_mode: str
    phrase_seconds: float
    width: int
    height: int
    fps: int
    crf: int
    preset: str
    max_videos: int | None
    max_clip_seconds: float | None
    dry_run: bool
    keep_work: bool
    layout: str
    clip_paths: tuple[Path, ...] | None
    audio_mode: str
    audio_panel: str
    audio_gain: float
    audio_panel_gains: dict[str, float]
    audio_fade_seconds: float
    video_direction: str
    tone_mode: str
    tone_strength: float
    tone_smoothing: int
    panel_order: tuple[str, str, str]
    media_fit: str = "cover"
    focal: tuple[float, float] = (0.5, 0.5)
    slice_enabled: bool = False
    slice_width: float = 0.5
    slice_height: float = 0.66
    seam_enabled: bool = False
    seam_width: float = 0.036
    seam_mode: str = "feather"
    seam_sigma: float = 0.005
    # Versioned audio is opt-in and rendered once against the composition clock.
    # Legacy --audio none/panel/mix continues to use the fields above unchanged.
    composition_audio: dict[str, Any] | None = None
    soundtrack_path: Path | None = None


@dataclass(frozen=True)
class Clip:
    index: int
    path: Path
    duration: float
    has_audio: bool


@dataclass(frozen=True)
class Interval:
    panel_name: str
    clip: Clip
    start: float
    end: float


@dataclass(frozen=True)
class Panel:
    name: str
    source_index: int | None
    source_path: Path | None
    source_offset: float
    source_duration: float | None
    source_has_audio: bool
    source_kind: str = "video"
    playback_rate: float = 1.0
    held: bool = False
    clocked: bool = False
    source_crop: tuple[float, float, float, float] | None = None
    audio_pan: float = 0.0
    audio_gain: float = 1.0
    source_audio_channels: int = 0


@dataclass(frozen=True)
class Placement:
    """Resolved presentation geometry; never owns a source or a clock."""

    name: str
    x: int
    y: int
    width: int
    height: int
    fit: str = "cover"
    focal: tuple[float, float] = (0.5, 0.5)


@dataclass(frozen=True)
class Segment:
    index: int
    start: float
    duration: float
    panels: tuple[Panel, ...]
    placements: tuple[Placement, ...] | None = None
    seam: dict | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a left-to-right triptych video canon from exported videos."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        help="Directory containing manually exported videos. Defaults to samples/.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional JSON settings file. Relative paths resolve from the manifest.",
    )
    parser.add_argument("--state", type=Path, help="Versioned independent-loop composition state.")
    parser.add_argument("--orientation", choices=("portrait", "landscape"),
                        help="Explicit layout orientation for --state exports.")
    parser.add_argument("--output", type=Path, help="Output .mp4 path.")
    parser.add_argument("--work-dir", type=Path, help="Temporary segment directory.")
    parser.add_argument(
        "--timing",
        choices=sorted(TIMING_MODES),
        help="clip uses filled rounds led by source durations; fixed uses --phrase for every entry.",
    )
    parser.add_argument("--phrase", type=float, help="Seconds per canon phrase.")
    parser.add_argument(
        "--layout",
        choices=sorted(LAYOUTS),
        help="story renders all three panels; left/middle/right render one panel as a reel.",
    )
    parser.add_argument(
        "--panel-order",
        help="Comma-separated story panel order, for example left,middle,right or middle,left,right.",
    )
    parser.add_argument("--width", type=int, help="Canvas width.")
    parser.add_argument("--height", type=int, help="Canvas height.")
    parser.add_argument("--fps", type=int, help="Output frame rate.")
    parser.add_argument("--crf", type=int, help="x264 quality. Lower is larger/better.")
    parser.add_argument("--preset", help="x264 preset, for example medium or slow.")
    parser.add_argument("--max-videos", type=int, help="Render only the first N videos.")
    parser.add_argument(
        "--max-clip-seconds",
        type=float,
        help="Cap each source clip duration for this render without changing source media.",
    )
    parser.add_argument(
        "--audio",
        choices=sorted(AUDIO_MODES),
        help="Audio mode: none, panel, or mix.",
    )
    parser.add_argument(
        "--audio-panel",
        choices=PANEL_NAMES,
        help="Panel to use when --audio panel is active.",
    )
    parser.add_argument("--audio-gain", type=float, help="Per-source audio gain.")
    parser.add_argument("--audio-left-gain", type=float, help="Additional gain for left-panel audio.")
    parser.add_argument("--audio-middle-gain", type=float, help="Additional gain for middle-panel audio.")
    parser.add_argument("--audio-right-gain", type=float, help="Additional gain for right-panel audio.")
    parser.add_argument("--audio-fade", type=float, help="Audio fade in/out seconds per segment.")
    parser.add_argument(
        "--direction",
        choices=sorted(VIDEO_DIRECTIONS),
        help="Playback direction effect for video and rendered audio: forward, reverse, or pingpong.",
    )
    parser.add_argument(
        "--tone",
        choices=sorted(TONE_MODES),
        help="Optional export-time brightness/color balance filter.",
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
    parser.add_argument("--dry-run", action="store_true", help="Print the schedule only.")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep temporary segment files under work/ after rendering.",
    )
    # Seamed slice field — all configurable
    parser.add_argument("--slice-enabled", choices=("true", "false"), help="Enable slice field (never full-frame).")
    parser.add_argument("--slice-width", type=float, help="Slice width fraction 0..1 (e.g. 0.5).")
    parser.add_argument("--slice-height", type=float, help="Slice height fraction 0..1 (e.g. 0.66).")
    parser.add_argument("--seam-enabled", choices=("true", "false"), help="Enable seam blur/merge/morph.")
    parser.add_argument("--seam-width", type=float, help="Seam width fraction 0..0.15.")
    parser.add_argument("--seam-mode", choices=("blur", "feather", "morph"), help="Seam mode.")
    parser.add_argument("--seam-sigma", type=float, help="Seam blur sigma fraction 0..0.1.")
    parser.add_argument("--config", type=Path, help="JSON config file for slice/seam/layout (overrides manifest).")
    return parser.parse_args()


def load_manifest(path: Path | None) -> tuple[dict[str, Any], Path]:
    if path is None:
        return {}, REPO_ROOT

    manifest_path = path.resolve()
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle), manifest_path.parent


def resolve_path(value: str | Path | None, base: Path, default: Path) -> Path:
    if value is None:
        return default

    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base / path


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolve_clip_paths(raw_clips: Any, base: Path) -> tuple[Path, ...] | None:
    if raw_clips is None:
        return None
    if not isinstance(raw_clips, list):
        raise SystemExit("manifest clips must be a list when provided.")

    clip_paths: list[Path] = []
    for entry in raw_clips:
        enabled = True
        raw_path: str | None
        if isinstance(entry, str):
            raw_path = entry
        elif isinstance(entry, dict):
            enabled = bool(entry.get("enabled", True))
            raw_path = entry.get("path")
        else:
            raise SystemExit("each clip entry must be a string or object with a path.")

        if not enabled:
            continue
        if not raw_path:
            raise SystemExit("clip entry is missing path.")

        path = Path(raw_path).expanduser()
        clip_paths.append(path if path.is_absolute() else base / path)

    return tuple(clip_paths)


def audio_panel_gains(audio: dict[str, Any], args: argparse.Namespace) -> dict[str, float]:
    raw_gains = audio.get("panel_gains", {})
    gains = {name: 1.0 for name in PANEL_NAMES}
    if isinstance(raw_gains, dict):
        for name in PANEL_NAMES:
            if raw_gains.get(name) is not None:
                gains[name] = float(raw_gains[name])

    overrides = {
        "left": args.audio_left_gain,
        "middle": args.audio_middle_gain,
        "right": args.audio_right_gain,
    }
    for name, value in overrides.items():
        if value is not None:
            gains[name] = float(value)
    return gains


def parse_panel_order(value: Any) -> tuple[str, str, str]:
    if value is None:
        return PANEL_NAMES
    if isinstance(value, str):
        names = [name.strip() for name in value.split(",") if name.strip()]
    elif isinstance(value, list):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        raise SystemExit("panel_order must be a list or comma-separated string.")
    if len(names) != 3 or set(names) != set(PANEL_NAMES):
        raise SystemExit("panel_order must contain left, middle, and right exactly once.")
    return (names[0], names[1], names[2])


def build_settings(args: argparse.Namespace) -> Settings:
    manifest, manifest_base = load_manifest(args.manifest)
    # Optional external JSON config (all knobs configurable)
    if getattr(args, "config", None):
        cfg_path = Path(args.config).expanduser()
        if cfg_path.is_file():
            try:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg_data, dict):
                    manifest = {**manifest, **cfg_data}
            except Exception as exc:
                raise SystemExit(f"config {cfg_path}: {exc}") from exc
    canvas = manifest.get("canvas", {})
    render = manifest.get("render", {})
    audio = manifest.get("audio", {})
    effects = manifest.get("effects", {})
    tone = effects.get("tone", {}) if isinstance(effects.get("tone"), dict) else {}
    slice_cfg = manifest.get("slice", {}) if isinstance(manifest.get("slice"), dict) else {}
    seam_cfg = manifest.get("seam", {}) if isinstance(manifest.get("seam"), dict) else {}
    panel_order_value = args.panel_order
    if panel_order_value is None:
        panel_order_value = manifest.get("panel_order")
    if panel_order_value is None and isinstance(canvas, dict):
        panel_order_value = canvas.get("panel_order")

    cli_base = Path.cwd()
    input_base = cli_base if args.input_dir is not None else manifest_base
    output_base = cli_base if args.output is not None else manifest_base
    work_base = cli_base if args.work_dir is not None else manifest_base

    input_value = args.input_dir if args.input_dir is not None else manifest.get("input_dir")
    output_value = args.output if args.output is not None else manifest.get("output_file")
    work_value = args.work_dir if args.work_dir is not None else manifest.get("work_dir")
    timing_mode = args.timing or manifest.get("timing_mode")
    if timing_mode is None:
        timing_mode = "fixed" if args.phrase is not None else "clip"

    output_default = REPO_ROOT / "renders" / "triptych-canon.mp4"
    work_default = REPO_ROOT / "work"

    settings = Settings(
        input_dir=resolve_path(input_value, input_base, REPO_ROOT / "samples"),
        output_file=resolve_path(output_value, output_base, output_default),
        work_dir=resolve_path(work_value, work_base, work_default),
        timing_mode=str(timing_mode),
        phrase_seconds=args.phrase
        if args.phrase is not None
        else float(manifest.get("phrase_seconds", 4.0)),
        width=args.width if args.width is not None else int(canvas.get("width", 1080)),
        height=args.height if args.height is not None else int(canvas.get("height", 1920)),
        fps=args.fps if args.fps is not None else int(canvas.get("fps", 30)),
        crf=args.crf if args.crf is not None else int(render.get("crf", 18)),
        preset=args.preset if args.preset is not None else str(render.get("preset", "medium")),
        max_videos=args.max_videos
        if args.max_videos is not None
        else manifest.get("max_videos"),
        max_clip_seconds=args.max_clip_seconds
        if args.max_clip_seconds is not None
        else manifest.get("max_clip_seconds"),
        dry_run=args.dry_run,
        keep_work=args.keep_work,
        layout=args.layout if args.layout is not None else str(manifest.get("layout", "story")),
        clip_paths=resolve_clip_paths(manifest.get("clips"), manifest_base),
        audio_mode=args.audio if args.audio is not None else str(audio.get("mode", "none")),
        audio_panel=args.audio_panel
        if args.audio_panel is not None
        else str(audio.get("panel", "left")),
        audio_gain=args.audio_gain
        if args.audio_gain is not None
        else float(audio.get("gain", 0.8)),
        audio_panel_gains=audio_panel_gains(audio, args),
        audio_fade_seconds=args.audio_fade
        if args.audio_fade is not None
        else float(audio.get("fade_seconds", 0.05)),
        video_direction=args.direction
        if args.direction is not None
        else str(effects.get("direction", "forward")),
        tone_mode=args.tone
        if args.tone is not None
        else str(tone.get("mode", effects.get("tone_mode", "none"))),
        tone_strength=args.tone_strength
        if args.tone_strength is not None
        else float(tone.get("strength", effects.get("tone_strength", 0.35))),
        tone_smoothing=args.tone_smoothing
        if args.tone_smoothing is not None
        else int(tone.get("smoothing", effects.get("tone_smoothing", 50))),
        panel_order=parse_panel_order(panel_order_value),
        slice_enabled=(args.slice_enabled == "true") if getattr(args, "slice_enabled", None) is not None else bool(slice_cfg.get("enabled", False)),
        slice_width=float(args.slice_width) if getattr(args, "slice_width", None) is not None else float(slice_cfg.get("width", 0.5)),
        slice_height=float(args.slice_height) if getattr(args, "slice_height", None) is not None else float(slice_cfg.get("height", 0.66)),
        seam_enabled=(args.seam_enabled == "true") if getattr(args, "seam_enabled", None) is not None else bool(seam_cfg.get("enabled", False)),
        seam_width=float(args.seam_width) if getattr(args, "seam_width", None) is not None else float(seam_cfg.get("width", 0.036)),
        seam_mode=str(args.seam_mode) if getattr(args, "seam_mode", None) is not None else str(seam_cfg.get("mode", "feather")),
        seam_sigma=float(args.seam_sigma) if getattr(args, "seam_sigma", None) is not None else float(seam_cfg.get("sigma", 0.005)),
    )

    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    if settings.timing_mode not in TIMING_MODES:
        raise SystemExit(f"timing_mode must be one of: {', '.join(sorted(TIMING_MODES))}")
    if settings.layout not in LAYOUTS:
        raise SystemExit(f"layout must be one of: {', '.join(sorted(LAYOUTS))}")
    if settings.audio_mode not in AUDIO_MODES:
        raise SystemExit(f"audio mode must be one of: {', '.join(sorted(AUDIO_MODES))}")
    if settings.video_direction not in VIDEO_DIRECTIONS:
        raise SystemExit(f"direction must be one of: {', '.join(sorted(VIDEO_DIRECTIONS))}")
    if settings.tone_mode not in TONE_MODES:
        raise SystemExit(f"tone mode must be one of: {', '.join(sorted(TONE_MODES))}")
    if settings.audio_panel not in PANEL_NAMES:
        raise SystemExit(f"audio_panel must be one of: {', '.join(PANEL_NAMES)}")
    if settings.audio_gain < 0:
        raise SystemExit("audio_gain must be greater than or equal to 0.")
    for panel_name, panel_gain in settings.audio_panel_gains.items():
        if panel_name not in PANEL_NAMES:
            raise SystemExit(f"unknown audio panel gain: {panel_name}")
        if panel_gain < 0:
            raise SystemExit(f"audio panel gain for {panel_name} must be greater than or equal to 0.")
    if settings.audio_fade_seconds < 0:
        raise SystemExit("audio_fade_seconds must be greater than or equal to 0.")
    if not 0 <= settings.tone_strength <= 1:
        raise SystemExit("tone_strength must be between 0 and 1.")
    if settings.tone_smoothing < 0:
        raise SystemExit("tone_smoothing must be greater than or equal to 0.")
    if settings.phrase_seconds <= 0:
        raise SystemExit("phrase_seconds must be greater than 0.")
    if settings.layout == "story" and settings.width % 3 != 0:
        raise SystemExit("story width must divide evenly into three panels.")
    if settings.width <= 0 or settings.height <= 0:
        raise SystemExit("width and height must be positive.")
    if settings.fps <= 0:
        raise SystemExit("fps must be positive.")
    if settings.max_videos is not None and int(settings.max_videos) <= 0:
        raise SystemExit("max_videos must be positive when provided.")
    if settings.max_clip_seconds is not None and float(settings.max_clip_seconds) <= 0:
        raise SystemExit("max_clip_seconds must be positive when provided.")
    if not path_inside(settings.output_file, REPO_ROOT):
        raise SystemExit("output_file must stay inside the SIMVLTANEA repository root.")
    if not path_inside(settings.work_dir, REPO_ROOT):
        raise SystemExit("work_dir must stay inside the SIMVLTANEA repository root.")
    # Slice/Seam configurability — every knob validated
    if not 0 < settings.slice_width < 1:
        raise SystemExit("slice_width must be in (0,1)")
    if not 0 < settings.slice_height < 1:
        raise SystemExit("slice_height must be in (0,1)")
    if settings.slice_enabled and settings.slice_width * settings.slice_height >= 1:
        raise SystemExit("slice area must be <1 (never full-frame)")
    if not 0 < settings.seam_width <= 0.15:
        raise SystemExit("seam_width must be in (0,0.15]")
    if settings.seam_mode not in ("blur", "feather", "morph"):
        raise SystemExit("seam_mode must be blur|feather|morph")
    if not 0 < settings.seam_sigma <= 0.1:
        raise SystemExit("seam_sigma must be in (0,0.1]")


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required tool not found on PATH: {name}")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def probe_duration(path: Path) -> float:
    require_tool("ffprobe")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    try:
        duration = float(completed.stdout.strip())
    except ValueError as error:
        raise SystemExit(f"Could not read duration for {path}") from error
    if duration <= 0:
        raise SystemExit(f"Video has no positive duration: {path}")
    return duration


def probe_has_audio(path: Path) -> bool:
    require_tool("ffprobe")
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
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return bool(completed.stdout.strip())


def probe_audio_channels(path: Path) -> int:
    """An absent source stream is silence, not recovered or synthesized audio."""
    require_tool("ffprobe")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    return int(streams[0].get("channels", 0)) if streams else 0


def collect_video_paths(settings: Settings) -> list[Path]:
    if settings.clip_paths is not None:
        video_paths = list(settings.clip_paths)
    else:
        if not settings.input_dir.exists():
            raise SystemExit(
                f"No input directory found: {settings.input_dir}\n"
                "Export videos manually and place them in samples/, or pass another input_dir."
            )
        if not settings.input_dir.is_dir():
            raise SystemExit(f"Input path is not a directory: {settings.input_dir}")

        video_paths = sorted(
            path
            for path in settings.input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        )

    if settings.max_videos is not None:
        video_paths = video_paths[: int(settings.max_videos)]

    missing = [path for path in video_paths if not path.exists()]
    if missing:
        missing_text = "\n".join(str(path) for path in missing)
        raise SystemExit(f"Clip path does not exist:\n{missing_text}")

    unsupported = [path for path in video_paths if path.suffix.lower() not in VIDEO_EXTENSIONS]
    if unsupported:
        supported = ", ".join(sorted(VIDEO_EXTENSIONS))
        unsupported_text = "\n".join(str(path) for path in unsupported)
        raise SystemExit(f"Unsupported clip extension. Supported: {supported}\n{unsupported_text}")

    if not video_paths:
        supported = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise SystemExit(f"No video files found. Supported: {supported}")

    return video_paths


def load_clips(settings: Settings) -> list[Clip]:
    video_paths = collect_video_paths(settings)
    clips: list[Clip] = []
    for index, path in enumerate(video_paths):
        duration = probe_duration(path) if settings.timing_mode == "clip" else settings.phrase_seconds
        if settings.max_clip_seconds is not None:
            duration = min(duration, float(settings.max_clip_seconds))
        has_audio = probe_has_audio(path) if settings.audio_mode != "none" else False
        clips.append(Clip(index=index, path=path, duration=duration, has_audio=has_audio))
    return clips


def blank_panel(name: str) -> Panel:
    return Panel(
        name=name,
        source_index=None,
        source_path=None,
        source_offset=0.0,
        source_duration=None,
        source_has_audio=False,
    )


def build_fixed_segments(clips: list[Clip], phrase_seconds: float) -> list[Segment]:
    segments: list[Segment] = []
    for phrase_index in range(len(clips) + 2):
        panels: list[Panel] = []
        for panel_index, panel_name in enumerate(PANEL_NAMES):
            source_index = phrase_index - panel_index
            if 0 <= source_index < len(clips):
                panels.append(
                    Panel(
                        name=panel_name,
                        source_index=source_index,
                        source_path=clips[source_index].path,
                        source_offset=panel_index * phrase_seconds,
                        source_duration=clips[source_index].duration,
                        source_has_audio=clips[source_index].has_audio,
                    )
                )
            else:
                panels.append(blank_panel(panel_name))

        segments.append(
            Segment(
                index=phrase_index,
                start=phrase_index * phrase_seconds,
                duration=phrase_seconds,
                panels=tuple(panels),
            )
        )
    return segments


def build_clip_intervals(clips: list[Clip]) -> list[Interval]:
    intervals: list[Interval] = []

    start = 0.0
    # Add two wraparound rounds so finite exports close with the last original
    # clip completing in the right panel while the filled triptych stays occupied.
    for round_index in range(len(clips) + 2):
        active: list[tuple[str, Clip]] = []
        for panel_index, panel_name in enumerate(PANEL_NAMES):
            entry_index = round_index - panel_index
            if entry_index < 0:
                continue
            active.append((panel_name, clips[entry_index % len(clips)]))

        if not active:
            continue

        duration = max(clip.duration for _, clip in active)
        end = start + duration
        intervals.extend(
            Interval(panel_name, clip, start, end) for panel_name, clip in active
        )
        start = end

    return intervals


def active_interval(intervals: list[Interval], panel_name: str, start: float) -> Interval | None:
    for interval in intervals:
        if interval.panel_name == panel_name and interval.start <= start < interval.end:
            return interval
    return None


def build_clip_segments(clips: list[Clip]) -> list[Segment]:
    intervals = build_clip_intervals(clips)
    breakpoints = sorted({point for interval in intervals for point in (interval.start, interval.end)})
    segments: list[Segment] = []

    for index, (start, end) in enumerate(zip(breakpoints, breakpoints[1:])):
        duration = end - start
        if duration <= 0:
            continue

        panels: list[Panel] = []
        for panel_name in PANEL_NAMES:
            interval = active_interval(intervals, panel_name, start)
            if interval is None:
                panels.append(blank_panel(panel_name))
            else:
                panels.append(
                    Panel(
                        name=panel_name,
                        source_index=interval.clip.index,
                        source_path=interval.clip.path,
                        source_offset=start - interval.start,
                        source_duration=interval.clip.duration,
                        source_has_audio=interval.clip.has_audio,
                    )
                )

        segments.append(Segment(index=index, start=start, duration=duration, panels=tuple(panels)))

    return segments


def build_segments(clips: list[Clip], settings: Settings) -> list[Segment]:
    if settings.timing_mode == "fixed":
        return build_fixed_segments(clips, settings.phrase_seconds)
    return build_clip_segments(clips)


def print_schedule(segments: list[Segment], settings: Settings) -> None:
    panel_order = ",".join(settings.panel_order)
    print(
        f"timing={settings.timing_mode} layout={settings.layout} "
        f"direction={settings.video_direction} panel_order={panel_order}"
    )
    for segment in segments:
        print(
            f"segment {segment.index:03d} "
            f"[{segment.start:.2f}s-{segment.end:.2f}s] "
            f"duration={segment.duration:.2f}s"
        )
        for panel in segment.panels:
            if panel.source_path is None:
                print(f"  {panel.name:<6} blank")
            else:
                print(
                    f"  {panel.name:<6} "
                    f"{panel.source_index:03d}:{panel.source_path.name} "
                    f"@ +{panel.source_offset:.2f}s"
                )


def panel_by_name(segment: Segment, name: str) -> Panel:
    for panel in segment.panels:
        if panel.name == name:
            return panel
    raise KeyError(name)


def layout_panel_names(settings: Settings) -> tuple[str, ...]:
    if settings.layout == "story":
        return settings.panel_order
    visible_index = PANEL_NAMES.index(settings.layout)
    return (settings.panel_order[visible_index],)


def selected_audio_panels(render_panels: list[Panel], settings: Settings) -> set[int]:
    if settings.audio_mode == "none":
        return set()
    if settings.audio_mode == "panel":
        if settings.layout in PANEL_NAMES and len(render_panels) == 1:
            return {0}
        return {
            index
            for index, panel in enumerate(render_panels)
            if panel.name == settings.audio_panel
        }
    return set(range(len(render_panels)))


def audio_sample_count(duration: float, multiplier: int = 1) -> int:
    return max(1, math.ceil(duration * 48000) * multiplier)


def audio_base_filters(panel: Panel, duration: float) -> list[str]:
    return [
        f"atrim=start={seconds(panel.source_offset)}:duration={seconds(duration)}",
        "asetpts=PTS-STARTPTS",
        "aresample=48000",
        "aformat=sample_rates=48000:channel_layouts=stereo",
    ]


def audio_postprocess_filters(panel: Panel, segment: Segment, settings: Settings) -> list[str]:
    fade = min(settings.audio_fade_seconds, segment.duration / 2)
    panel_gain = settings.audio_panel_gains.get(panel.name, 1.0)
    filters = [f"volume={settings.audio_gain * panel_gain}"]
    if fade > 0:
        filters.append(f"afade=t=in:st=0:d={seconds(fade)}")
        filters.append(
            f"afade=t=out:st={seconds(max(segment.duration - fade, 0))}:d={seconds(fade)}"
        )
    return filters


def audio_source_filters(
    input_index: int,
    panel: Panel,
    segment: Segment,
    settings: Settings,
    output_label: str,
) -> list[str]:
    input_label = f"[{input_index}:a]"
    if settings.video_direction == "forward":
        filters = audio_base_filters(panel, segment.duration)
        filters.extend(audio_postprocess_filters(panel, segment, settings))
        return [input_label + ",".join(filters) + output_label]

    source_duration = panel.source_duration or segment.duration
    if settings.video_direction == "reverse":
        filters = audio_base_filters(panel, source_duration)
        filters.extend(
            [
                "areverse",
                f"aloop=loop=-1:size={audio_sample_count(source_duration)}:start=0",
                f"atrim=duration={seconds(segment.duration)}",
                "asetpts=PTS-STARTPTS",
            ]
        )
        filters.extend(audio_postprocess_filters(panel, segment, settings))
        return [input_label + ",".join(filters) + output_label]

    forward_label = f"[a{input_index}forward]"
    reverse_base_label = f"[a{input_index}reversebase]"
    reverse_label = f"[a{input_index}reverse]"
    loop_label = f"[a{input_index}loop]"
    base_filters = audio_base_filters(panel, source_duration)
    postprocess_filters = audio_postprocess_filters(panel, segment, settings)
    return [
        input_label + ",".join(base_filters) + f",asplit=2{forward_label}{reverse_base_label}",
        f"{reverse_base_label}areverse{reverse_label}",
        (
            f"{forward_label}{reverse_label}"
            "concat=n=2:v=0:a=1,"
            f"aloop=loop=-1:size={audio_sample_count(source_duration, multiplier=2)}:start=0,"
            f"atrim=duration={seconds(segment.duration)},"
            "asetpts=PTS-STARTPTS"
            f"{loop_label}"
        ),
        f"{loop_label}" + ",".join(postprocess_filters) + output_label,
    ]


def silence_filter(segment: Segment) -> str:
    return (
        "anullsrc=r=48000:cl=stereo,"
        f"atrim=duration={seconds(segment.duration)},"
        "asetpts=PTS-STARTPTS[outa]"
    )


def finish_video_filter(
    input_label: str,
    panel_width: int,
    settings: Settings,
    output_label: str,
) -> str:
    tone_filters: list[str] = []
    if settings.tone_mode == "normalize":
        tone_filters.append(
            "normalize="
            f"smoothing={settings.tone_smoothing}:"
            "independence=0:"
            f"strength={settings.tone_strength}"
        )
    elif settings.tone_mode == "histeq":
        tone_filters.append("histeq")
    tone = "".join(f",{filter_name}" for filter_name in tone_filters)
    if settings.media_fit == "contain":
        geometry = (
            f"scale={panel_width}:{settings.height}:force_original_aspect_ratio=decrease,"
            f"pad={panel_width}:{settings.height}:(ow-iw)/2:(oh-ih)/2:black,"
        )
    else:
        crop = f"crop={panel_width}:{settings.height}"
        if settings.focal != (0.5, 0.5):
            crop += f":(in_w-out_w)*{settings.focal[0]}:(in_h-out_h)*{settings.focal[1]}"
        geometry = (
            f"scale={panel_width}:{settings.height}:force_original_aspect_ratio=increase,"
            f"{crop},"
        )
    return f"{input_label}{geometry}setsar=1{tone},format=yuv420p{output_label}"


def source_frame_count(panel: Panel, settings: Settings, multiplier: int = 1) -> int:
    duration = panel.source_duration or settings.phrase_seconds
    return max(1, math.ceil(duration * settings.fps) * multiplier)


def _crop_prefix(panel: Panel) -> str:
    if panel.source_crop is None:
        return ""
    cx, cy, cw, ch = panel.source_crop
    # crop before scale: w/h proportional to source, x/y offset proportional
    # FFmpeg requires crop dimensions to be integers; delegation to in_w/in_h handles it.
    # Use round-friendly expression and ensure even via later scale.
    return f"crop=w=in_w*{cw:.6f}:h=in_h*{ch:.6f}:x=in_w*{cx:.6f}:y=in_h*{cy:.6f},"


def video_source_filters(
    input_index: int,
    panel: Panel,
    segment: Segment,
    settings: Settings,
    panel_width: int,
    output_label: str,
) -> list[str]:
    input_label = f"[{input_index}:v]"
    crop = _crop_prefix(panel)
    if panel.clocked:
        # Model compilation splits on source changes, events and loop wraps.
        # Padding protects the final decoded frame at fractional source boundaries.
        # Crop (slice) is applied right after initial PTS so source never reveals full frame.
        chain = crop + f"trim=start={seconds(panel.source_offset)},setpts=PTS-STARTPTS,"
        if panel.held or panel.source_kind == "still":
            chain += f"fps={settings.fps},trim=end_frame=1,loop=loop=-1:size=1:start=0,"
        else:
            chain += f"setpts=PTS/{seconds(panel.playback_rate)},fps={settings.fps},"
            chain += f"tpad=stop_mode=clone:stop_duration={seconds(segment.duration)},"
        chain += f"trim=duration={seconds(segment.duration)},setpts=PTS-STARTPTS,"
        return [finish_video_filter(input_label + chain, panel_width, settings, output_label)]
    if settings.video_direction == "forward":
        return [
            finish_video_filter(
                (
                    f"{input_label}"
                    + crop
                    + f"trim=start={seconds(panel.source_offset)}:"
                    f"duration={seconds(segment.duration)},"
                    "setpts=PTS-STARTPTS,"
                    f"fps={settings.fps},"
                ),
                panel_width,
                settings,
                output_label,
            )
        ]

    source_duration = panel.source_duration or segment.duration
    if settings.video_direction == "reverse":
        frames = source_frame_count(panel, settings)
        return [
            finish_video_filter(
                (
                    f"{input_label}"
                    + crop
                    + f"trim=start={seconds(panel.source_offset)}:"
                    f"duration={seconds(source_duration)},"
                    "setpts=PTS-STARTPTS,"
                    f"fps={settings.fps},"
                    "reverse,"
                    f"loop=loop=-1:size={frames}:start=0,"
                    f"trim=duration={seconds(segment.duration)},"
                    "setpts=PTS-STARTPTS,"
                ),
                panel_width,
                settings,
                output_label,
            )
        ]

    forward_label = f"[v{input_index}forward]"
    reverse_base_label = f"[v{input_index}reversebase]"
    reverse_label = f"[v{input_index}reverse]"
    loop_label = f"[v{input_index}loop]"
    frames = source_frame_count(panel, settings, multiplier=2)
    return [
        (
            f"{input_label}"
            + crop
            + f"trim=start={seconds(panel.source_offset)}:"
            f"duration={seconds(source_duration)},"
            "setpts=PTS-STARTPTS,"
            f"fps={settings.fps},"
            f"split=2{forward_label}{reverse_base_label}"
        ),
        f"{reverse_base_label}reverse{reverse_label}",
        (
            f"{forward_label}{reverse_label}"
            "concat=n=2:v=1:a=0,"
            f"loop=loop=-1:size={frames}:start=0,"
            f"trim=duration={seconds(segment.duration)},"
            "setpts=PTS-STARTPTS"
            f"{loop_label}"
        ),
        finish_video_filter(loop_label, panel_width, settings, output_label),
    ]


def render_segment(
    segment_path: Path,
    segment: Segment,
    settings: Settings,
) -> None:
    placements = segment.placements
    if placements is None:
        # Compatibility adapter: legacy ordering, reels, sizes and schedules stay intact.
        names = layout_panel_names(settings)
        width = settings.width // 3 if settings.layout == "story" else settings.width
        placements = tuple(Placement(name, i * width, 0, width, settings.height)
                           for i, name in enumerate(names))
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    if segment.placements is not None:
        command += ["-filter_complex_threads", "1"]
    render_panels = [panel_by_name(segment, cell.name) for cell in placements]

    for panel, cell in zip(render_panels, placements):
        panel_width = cell.width
        if panel.source_path is None:
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    seconds(segment.duration),
                    "-i",
                    f"color=c=black:s={panel_width}x{cell.height}:r={settings.fps}",
                ]
            )
        elif panel.source_kind == "still":
            command.extend(["-loop", "1", "-framerate", str(settings.fps), "-i", str(panel.source_path)])
        else:
            command.extend(["-stream_loop", "-1", "-i", str(panel.source_path)])

    filters: list[str] = []
    for index, panel in enumerate(render_panels):
        cell = placements[index]
        cell_settings = replace(settings, height=cell.height, media_fit=cell.fit, focal=cell.focal)
        input_label = f"[{index}:v]"
        output_label = f"[v{index}]"
        if panel.source_path is None:
            filters.append(
                (
                    f"{input_label}"
                    f"trim=duration={seconds(segment.duration)},"
                    "setpts=PTS-STARTPTS,"
                    f"fps={settings.fps},format=yuv420p"
                    f"{output_label}"
                )
            )
        else:
            filters.extend(
                video_source_filters(
                    index,
                    panel,
                    segment,
                    cell_settings,
                    cell.width,
                    output_label,
                )
            )

    audio_labels: list[str] = []
    audio_panel_indexes = selected_audio_panels(render_panels, settings)
    if settings.audio_mode != "none":
        for index, panel in enumerate(render_panels):
            if index not in audio_panel_indexes:
                continue
            if panel.source_path is None or not panel.source_has_audio:
                continue
            output_label = f"[a{len(audio_labels)}]"
            filters.extend(audio_source_filters(index, panel, segment, settings, output_label))
            audio_labels.append(output_label)

        if not audio_labels:
            filters.append(silence_filter(segment))
        elif len(audio_labels) == 1:
            filters.append(f"{audio_labels[0]}anull[outa]")
        else:
            labels = "".join(audio_labels)
            filters.append(
                (
                    f"{labels}amix=inputs={len(audio_labels)}:"
                    "duration=longest:normalize=0,"
                    f"atrim=duration={seconds(segment.duration)},"
                    "asetpts=PTS-STARTPTS[outa]"
                )
            )

    if segment.placements is None:
        # Keep the historical graph unchanged, including legacy encoder behavior.
        if len(render_panels) == 1:
            filters.append("[v0]copy[outv]")
        else:
            labels = "".join(f"[v{index}]" for index in range(len(render_panels)))
            filters.append(f"{labels}hstack=inputs={len(render_panels)}[outv]")
    else:
        filters.append(f"color=c=black:s={settings.width}x{settings.height}:r={settings.fps}:"
                       f"d={seconds(segment.duration)}[canvas0]")
        for index, cell in enumerate(placements):
            target = "[outv]" if index == len(placements) - 1 else f"[canvas{index + 1}]"
            filters.append(f"[canvas{index}][v{index}]overlay=x={cell.x}:y={cell.y}:"
                           f"shortest=1{target}")
        final_video_label = "[outv]"
        # Seamed slice seam blur/merge/morph: optional blur strip bridging adjacent panels
        seam = getattr(segment, "seam", None)
        if seam is None:
            try:
                seam = segment.__dict__.get("seam")
            except Exception:
                seam = None
        if seam and seam.get("enabled"):
            from fractions import Fraction as _F
            _wfrac = float(_F(seam.get("width", "1/40")))
            seam_w = max(4, 2 * round(_wfrac * settings.width / 2))
            seam_w = seam_w if seam_w % 2 == 0 else seam_w + 1
            seam_h = max(4, 2 * round(_wfrac * settings.height / 2))
            seam_h = seam_h if seam_h % 2 == 0 else seam_h + 1
            try:
                sigma = float(_F(seam.get("sigma", "1/200")) * min(settings.width, settings.height))
            except Exception:
                sigma = 5.0
            radius = max(2, int(round(sigma)))
            # Detect vertical and horizontal adjacencies; seam width spans gap +/- seam_w/2
            seams: list[tuple[str, int, int]] = []  # (orient, pos, length)
            for i, a in enumerate(placements):
                for b in placements[i+1:]:
                    # vertical seam (side-by-side)
                    vert_overlap = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                    if vert_overlap > 0 and abs((a.x + a.width) - b.x) <= seam_w * 2:
                        x = (a.x + a.width + b.x) // 2
                        seams.append(("v", x, settings.height))
                    elif vert_overlap > 0 and abs((b.x + b.width) - a.x) <= seam_w * 2:
                        x = (b.x + b.width + a.x) // 2
                        seams.append(("v", x, settings.height))
                    # horizontal seam (stacked)
                    horiz_overlap = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                    if horiz_overlap > 0 and abs((a.y + a.height) - b.y) <= seam_h * 2:
                        y = (a.y + a.height + b.y) // 2
                        seams.append(("h", y, settings.width))
                    elif horiz_overlap > 0 and abs((b.y + b.height) - a.y) <= seam_h * 2:
                        y = (b.y + b.height + a.y) // 2
                        seams.append(("h", y, settings.width))
            # Fallback for N=2: seam at canvas mid if no adjacency found (gap case)
            if not seams and len(placements) == 2:
                a, b = placements[0], placements[1]
                if abs(a.x - b.x) < 5 and a.y != b.y:
                    y = (a.y + a.height + b.y) // 2
                    seams.append(("h", y, settings.width))
                elif abs(a.y - b.y) < 5 and a.x != b.x:
                    x = (a.x + a.width + b.x) // 2
                    seams.append(("v", x, settings.height))
            # Chain blur overlays
            current = "[outv]"
            for idx, (orient, pos, _length) in enumerate(seams):
                nxt = f"[outv_seam{idx+1}]"
                mid = f"[seam_mid{idx}]"
                base = f"[seam_base{idx}]"
                blur = f"[seam_blur{idx}]"
                crop = f"[seam_crop{idx}]"
                if orient == "v":
                    x = max(0, pos - seam_w // 2)
                    # mode morph uses tblend; blur/feather use boxblur
                    mode = seam.get("mode", "feather")
                    if mode == "morph":
                        filters.append(f"{current}split=2{base}{mid}")
                        filters.append(f"{mid}crop=w={seam_w}:h={settings.height}:x={x}:y=0,boxblur=luma_radius={radius}:chroma_radius={radius}:luma_power=1{blur}")
                        filters.append(f"{base}{blur}overlay=x={x}:y=0:shortest=1{nxt}")
                    else:
                        filters.append(f"{current}split=2{base}{crop}")
                        filters.append(f"{crop}crop=w={seam_w}:h={settings.height}:x={x}:y=0,boxblur=luma_radius={radius}:chroma_radius={radius}:luma_power=1{blur}")
                        filters.append(f"{base}{blur}overlay=x={x}:y=0:shortest=1{nxt}")
                else:
                    y = max(0, pos - seam_h // 2)
                    filters.append(f"{current}split=2{base}{crop}")
                    filters.append(f"{crop}crop=w={settings.width}:h={seam_h}:x=0:y={y},boxblur=luma_radius={radius}:chroma_radius={radius}:luma_power=1{blur}")
                    filters.append(f"{base}{blur}overlay=x=0:y={y}:shortest=1{nxt}")
                current = nxt
            if seams:
                final_video_label = current
    # Resolve final label: placements path may have updated final_video_label, else stay [outv]
    if segment.placements is None:
        command_label = "[outv]"
    else:
        command_label = final_video_label
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            command_label,
        ]
    )
    if settings.audio_mode != "none":
        command.extend(["-map", "[outa]"])
    else:
        command.append("-an")

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            settings.preset,
            "-crf",
            str(settings.crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(settings.fps),
        ]
    )
    if settings.audio_mode != "none":
        command.extend(["-c:a", "aac", "-b:a", "160k"])

    command.extend(
        [
            "-movflags",
            "+faststart",
            str(segment_path),
        ]
    )
    run(command)


def concat_escape(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def concat_segments(segment_paths: list[Path], output_file: Path, concat_file: Path) -> None:
    lines = ["ffconcat version 1.0"]
    lines.extend(f"file '{concat_escape(path.resolve())}'" for path in segment_paths)
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output_file),
    ]
    run(command)


@dataclass(frozen=True)
class AudioSpan:
    """One loop's continuous audio interval, independent of video segmentation."""

    start: float
    duration: float
    panel: Panel

    @property
    def end(self) -> float:
        return self.start + self.duration


def spatial_audio_spans(segments: list[Segment]) -> dict[str, list[AudioSpan]]:
    """Do not reset a sibling's samples/tempo because another loop changed."""
    tracks: dict[str, list[AudioSpan]] = {}
    for segment in segments:
        for panel in segment.panels:
            spans = tracks.setdefault(panel.name, [])
            previous = spans[-1] if spans else None
            same = previous is not None and all(
                getattr(previous.panel, key) == getattr(panel, key)
                for key in ("source_path", "source_kind", "source_has_audio", "held",
                            "playback_rate", "audio_pan", "audio_gain", "source_audio_channels")
            )
            if same:
                delta = 0 if panel.held or panel.source_kind == "still" else previous.duration * panel.playback_rate
                same = (math.isclose(previous.end, segment.start, abs_tol=1e-7)
                        and math.isclose(previous.panel.source_offset + delta,
                                         panel.source_offset, abs_tol=1e-7))
            if same:
                spans[-1] = replace(previous, duration=segment.end - previous.start)
            else:
                spans.append(AudioSpan(segment.start, segment.duration, panel))
    return tracks


def tempo_filters(rate: float) -> list[str]:
    """Match native video's default pitch-preserving playbackRate, including <0.5."""
    filters = []
    while rate < 0.5:
        filters.append("atempo=0.5")
        rate *= 2
    while rate > 2:
        filters.append("atempo=2")
        rate /= 2
    if not math.isclose(rate, 1):
        filters.append(f"atempo={rate:.12g}")
    return filters


def spatial_pan_filter(pan: float, channels: int) -> str:
    """Equal-power mono/stereo law used by Web Audio's StereoPannerNode."""
    if channels == 1:
        angle = (pan + 1) * math.pi / 4
        return f"pan=stereo|c0={math.cos(angle):.12g}*c0|c1={math.sin(angle):.12g}*c0"
    if pan <= 0:
        angle = (pan + 1) * math.pi / 2
        return ("aformat=channel_layouts=stereo,pan=stereo|"
                f"c0=c0+{math.cos(angle):.12g}*c1|c1={math.sin(angle):.12g}*c1")
    angle = pan * math.pi / 2
    return ("aformat=channel_layouts=stereo,pan=stereo|"
            f"c0={math.cos(angle):.12g}*c0|c1=c1+{math.sin(angle):.12g}*c0")


def render_composition_audio(segments: list[Segment], settings: Settings, output: Path) -> None:
    """Render exact-length PCM first; the final mux encodes AAC only once.

    All new audio behavior is reachable only with an explicit v1.1 config.
    Silent/still loop sources remain silent. Authored holds fade during the
    preceding 50ms and are silent at the hold boundary; release has no catch-up.
    """
    from fractions import Fraction
    config = settings.composition_audio
    if config is None or config["mode"] == "none":
        raise ValueError("composition audio requires an explicit audible mode")
    duration = segments[-1].end
    total_samples = round(duration * 48000)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
               "-filter_complex_threads", "1"]
    filters: list[str] = []
    if config["mode"] == "soundtrack":
        if settings.soundtrack_path is None:
            raise ValueError("soundtrack has no verified source")
        command += ["-i", str(settings.soundtrack_path)]
        track_samples = max(1, round(float(Fraction(config["duration"])) * 48000))
        chain = ["aresample=48000:first_pts=0"]
        if probe_audio_channels(settings.soundtrack_path) == 1:
            # A global mono master uses the browser's unity speaker upmix. Only
            # spatial mono sources use the panner's equal-power center gain.
            chain.append("pan=stereo|c0=c0|c1=c0")
        chain += ["aformat=sample_fmts=fltp:channel_layouts=stereo",
                 f"apad=whole_len={track_samples}", f"atrim=end_sample={track_samples}",
                 "asetpts=N/SR/TB"]
        if config["loop"]:
            chain += [f"aloop=loop=-1:size={track_samples}:start=0"]
        chain += [f"apad=whole_len={total_samples}", f"atrim=end_sample={total_samples}",
                  "asetpts=N/SR/TB"]
        fade_in = float(Fraction(config["fade_in_seconds"]))
        fade_out = float(Fraction(config["fade_out_seconds"]))
        fade_end = duration if config["loop"] else min(duration, track_samples / 48000)
        envelopes = ["1"]
        if fade_in > 0:
            envelopes.append(f"t/{fade_in:.12g}")
        if fade_out > 0:
            envelopes.append(f"max(0,({fade_end:.12g}-t)/{fade_out:.12g})")
        envelope = envelopes.pop()
        for other in envelopes:
            envelope = f"min({other},{envelope})"
        gain = float(Fraction(config["volume"]))
        expression = f"{gain:.12g}*({envelope})"
        chain.append(f"aeval=exprs='val(0)*{expression}|val(1)*{expression}':channel_layout=stereo")
        filters.append("[0:a:0]" + ",".join(chain) + "[outa]")
    elif config["mode"] == "spatial_loops":
        tracks = spatial_audio_spans(segments)
        # Each physical source is decoded once; asplit feeds independent clocks.
        uses: dict[Path, list[str]] = {}
        for track_index, spans in enumerate(tracks.values()):
            for span_index, span in enumerate(spans):
                panel = span.panel
                if (panel.source_has_audio and not panel.held and panel.source_kind == "video"
                        and panel.audio_gain > 0 and panel.source_path is not None):
                    uses.setdefault(panel.source_path, []).append(f"[src{track_index}_{span_index}]")
        for source_index, (path, labels) in enumerate(uses.items()):
            command += ["-i", str(path)]
            # Keep delayed audio aligned with source/video time before trimming.
            prefix = f"[{source_index}:a:0]aresample=48000:first_pts=0"
            if len(labels) > 1:
                filters.append(prefix + f",asplit={len(labels)}" + "".join(labels))
            else:
                filters.append(prefix + labels[0])
        outputs = []
        for track_index, spans in enumerate(tracks.values()):
            # Fade at the authored hold, even if a source wrap splits its last 50ms.
            holds = [span.start for i, span in enumerate(spans)
                     if span.panel.held and (i == 0 or not spans[i - 1].panel.held)]
            chunks = []
            for span_index, span in enumerate(spans):
                panel = span.panel
                label = f"[chunk{track_index}_{span_index}]"
                chunks.append(label)
                # Round absolute boundaries, not each duration, to avoid drift.
                count = round(span.end * 48000) - round(span.start * 48000)
                source_label = f"[src{track_index}_{span_index}]"
                if panel.source_path in uses and source_label in uses[panel.source_path]:
                    chain = [f"atrim=start={seconds(panel.source_offset)}:"
                             f"duration={seconds(span.duration * panel.playback_rate)}",
                             "asetpts=PTS-STARTPTS"]
                    if not math.isclose(panel.playback_rate, 1):
                        # Supply silence to flush the tempo filter's final analysis window.
                        chain += ["apad=pad_dur=0.1", *tempo_filters(panel.playback_rate)]
                    chain += [spatial_pan_filter(panel.audio_pan, panel.source_audio_channels),
                              f"volume={panel.audio_gain:.12g}", f"apad=whole_len={count}",
                              f"atrim=end_sample={count}", "asetpts=N/SR/TB"]
                    impending = next((at for at in holds if span.start < at
                                      and at - 0.05 < span.end), None)
                    if impending is not None:
                        remaining = impending - span.start
                        if remaining < 0.05:
                            chain.append(f"volume={remaining / 0.05:.12g}")
                        chain.append(f"afade=t=out:st={seconds(max(0, remaining - 0.05))}:"
                                     f"d={seconds(min(0.05, remaining))}")
                    filters.append(source_label + ",".join(chain) + label)
                else:
                    filters.append(f"anullsrc=r=48000:cl=stereo,atrim=end_sample={count},"
                                   f"asetpts=N/SR/TB{label}")
            track_label = f"[track{track_index}]"
            outputs.append(track_label)
            if len(chunks) == 1:
                filters.append(f"{chunks[0]}anull{track_label}")
            else:
                filters.append("".join(chunks) + f"concat=n={len(chunks)}:v=0:a=1{track_label}")
        if len(outputs) == 1:
            filters.append(f"{outputs[0]}anull[outa]")
        else:
            filters.append("".join(outputs) + f"amix=inputs={len(outputs)}:duration=longest:"
                           f"dropout_transition=0:normalize=0,atrim=end_sample={total_samples},"
                           "asetpts=N/SR/TB[outa]")
    else:
        raise ValueError(f"unsupported composition audio mode: {config['mode']}")
    graph_path = output.with_suffix(".ffgraph")
    graph_path.write_text(";\n".join(filters) + "\n", encoding="utf-8")
    command += ["-filter_complex_script", str(graph_path), "-map", "[outa]", "-vn",
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", str(output)]
    run(command)


def mux_composition_audio(video: Path, audio: Path, output: Path, duration: float) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", str(video),
         "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-t", seconds(duration), "-movflags", "+faststart",
         str(output)])


def render(segments: list[Segment], settings: Settings) -> None:
    require_tool("ffmpeg")
    settings.output_file.parent.mkdir(parents=True, exist_ok=True)
    settings.work_dir.mkdir(parents=True, exist_ok=True)

    session_dir = Path(
        tempfile.mkdtemp(prefix=f"{settings.output_file.stem}-", dir=settings.work_dir)
    )
    segment_paths: list[Path] = []

    try:
        audible = settings.composition_audio is not None and settings.composition_audio["mode"] != "none"
        visual_settings = replace(settings, audio_mode="none") if audible else settings
        for segment in segments:
            segment_path = session_dir / f"segment-{segment.index:03d}.mp4"
            print(f"rendering {segment_path.name}")
            render_segment(segment_path, segment, visual_settings)
            segment_paths.append(segment_path)

        concat_file = session_dir / "concat.ffconcat"
        video_output = session_dir / "visual-field.mp4" if audible else settings.output_file
        concat_segments(segment_paths, video_output, concat_file)
        if audible:
            audio_output = session_dir / "composition-audio.wav"
            render_composition_audio(segments, settings, audio_output)
            mux_composition_audio(video_output, audio_output, settings.output_file, segments[-1].end)
    finally:
        if settings.keep_work:
            print(f"kept work files: {session_dir}")
        else:
            shutil.rmtree(session_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    if args.state is not None:
        from composition import render_from_args
        return render_from_args(args)
    if args.orientation is not None:
        raise SystemExit("--orientation requires --state; legacy CLI is unchanged.")
    settings = build_settings(args)
    clips = load_clips(settings)
    segments = build_segments(clips, settings)

    print_schedule(segments, settings)
    if settings.dry_run:
        return 0

    render(segments, settings)
    print(f"wrote {settings.output_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
