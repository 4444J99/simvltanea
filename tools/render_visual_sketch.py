#!/usr/bin/env python3
"""Render a lightweight visual-arrangement sketch from an edition project."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = SCRIPT_DIR / "work" / "editions" / "ballerina" / "project.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "renders" / "editions" / "ballerina" / "draft-visual-sketch.mp4"
VIDEO_EXTENSIONS = {".3gp", ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}
IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
PANEL_NAMES = ("left", "middle", "right")
SKETCH_STYLES = {"fracture", "score", "serial", "signal", "slices"}
MODEL_FITS = {"contain", "cover", "triptych"}
DEFAULT_SCORE_CELLS = [
    {"x": 0.03, "y": 0.00, "width": 0.17, "height": 0.50, "alpha": 0.58},
    {"x": 0.17, "y": 0.00, "width": 0.12, "height": 0.45, "alpha": 0.80},
    {"x": 0.35, "y": 0.00, "width": 0.13, "height": 0.46, "alpha": 0.70},
    {"x": 0.48, "y": 0.03, "width": 0.16, "height": 0.43, "alpha": 0.48},
    {"x": 0.69, "y": 0.00, "width": 0.12, "height": 0.52, "alpha": 0.78},
    {"x": 0.82, "y": 0.00, "width": 0.14, "height": 0.58, "alpha": 0.62},
    {"x": 0.07, "y": 0.36, "width": 0.20, "height": 0.32, "alpha": 0.44},
    {"x": 0.30, "y": 0.26, "width": 0.18, "height": 0.38, "alpha": 0.66},
    {"x": 0.52, "y": 0.28, "width": 0.17, "height": 0.39, "alpha": 0.72},
    {"x": 0.72, "y": 0.32, "width": 0.20, "height": 0.36, "alpha": 0.50},
    {"x": 0.03, "y": 0.55, "width": 0.15, "height": 0.37, "alpha": 0.70},
    {"x": 0.21, "y": 0.56, "width": 0.13, "height": 0.38, "alpha": 0.52},
    {"x": 0.38, "y": 0.54, "width": 0.19, "height": 0.42, "alpha": 0.76},
    {"x": 0.58, "y": 0.55, "width": 0.13, "height": 0.41, "alpha": 0.62},
    {"x": 0.76, "y": 0.53, "width": 0.18, "height": 0.39, "alpha": 0.78},
]
DEFAULT_SIGNAL_CELLS = [
    {"x": 0.00, "y": 0.00, "width": 0.34, "height": 0.24, "alpha": 0.88, "source": 0},
    {"x": 0.29, "y": 0.02, "width": 0.42, "height": 0.18, "alpha": 0.72, "source": 1},
    {"x": 0.66, "y": 0.00, "width": 0.33, "height": 0.28, "alpha": 0.92, "source": 2},
    {"x": 0.08, "y": 0.22, "width": 0.24, "height": 0.56, "alpha": 0.58, "source": 3},
    {"x": 0.31, "y": 0.26, "width": 0.39, "height": 0.38, "alpha": 0.86, "source": 4},
    {"x": 0.63, "y": 0.20, "width": 0.31, "height": 0.50, "alpha": 0.66, "source": 5},
    {"x": 0.00, "y": 0.66, "width": 0.44, "height": 0.24, "alpha": 0.78, "source": 6},
    {"x": 0.38, "y": 0.62, "width": 0.30, "height": 0.32, "alpha": 0.52, "source": 7},
    {"x": 0.67, "y": 0.68, "width": 0.32, "height": 0.28, "alpha": 0.84, "source": 8},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a quick visual-arrangement sketch from selected clips. "
            "This is for visual-album drafts like ballerina whole -> ballerina danse "
            "or serial portrait albums like noonlight."
        )
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Project JSON to read. Defaults to work/editions/ballerina/project.json.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output MP4 path.")
    parser.add_argument("--width", type=int, default=1080, help="Canvas width. Defaults to 1080.")
    parser.add_argument("--height", type=int, default=1920, help="Canvas height. Defaults to 1920.")
    parser.add_argument("--fps", type=int, default=12, help="Output frame rate. Defaults to 12.")
    parser.add_argument("--duration", type=float, default=12.0, help="Draft duration in seconds.")
    parser.add_argument(
        "--style",
        choices=sorted(SKETCH_STYLES),
        default="slices",
        help=(
            "Sketch grammar: slices for collage, score for model-guided recomposition, "
            "serial for portrait sequences, fracture for collision grids, "
            "signal for damaged feedback/compression maps."
        ),
    )
    parser.add_argument("--slices", type=int, default=11, help="Number of vertical slices.")
    parser.add_argument("--source-count", type=int, default=9, help="Maximum project clips to use.")
    parser.add_argument(
        "--model-opacity",
        type=float,
        default=0.34,
        help="Opacity for a staged arrangement-model still under slice sketches.",
    )
    parser.add_argument(
        "--no-model-underlay",
        action="store_true",
        help="Disable staged arrangement-model still underlay.",
    )
    parser.add_argument(
        "--model-fit",
        choices=sorted(MODEL_FITS),
        default="contain",
        help=(
            "How a staged arrangement-model still enters slice sketches: "
            "contain keeps the whole still visible, cover fills the canvas, "
            "triptych maps the still's thirds into the visible panel order."
        ),
    )
    parser.add_argument("--crf", type=int, default=39, help="x264 CRF. Defaults to 39.")
    parser.add_argument("--preset", default="veryfast", help="x264 preset. Defaults to veryfast.")
    parser.add_argument(
        "--panel-order",
        help="Visible panel order for dividing the canvas, for example middle,left,right.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print ffmpeg command only.")
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
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


def load_project(path: Path) -> tuple[dict[str, Any], Path]:
    project_path = path.expanduser().resolve()
    if not project_path.exists():
        raise SystemExit(f"Project manifest not found: {project_path}")
    return json.loads(project_path.read_text(encoding="utf-8")), project_path.parent


def normalize_panel_order(value: Any) -> tuple[str, str, str]:
    if value is None:
        return PANEL_NAMES
    if isinstance(value, str):
        names = [name.strip() for name in value.split(",") if name.strip()]
    elif isinstance(value, list):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        names = []
    if len(names) != 3 or set(names) != set(PANEL_NAMES):
        raise SystemExit("panel order must contain left, middle, and right exactly once.")
    return (names[0], names[1], names[2])


def active_visual_sketch_config(project: dict[str, Any], project_base: Path, output: Path) -> dict[str, Any]:
    raw_sketches = project.get("visual_sketch")
    if isinstance(raw_sketches, dict):
        return raw_sketches
    if not isinstance(raw_sketches, list):
        return {}

    resolved_output = output.expanduser()
    if not resolved_output.is_absolute():
        resolved_output = Path.cwd() / resolved_output
    for sketch in raw_sketches:
        if not isinstance(sketch, dict):
            continue
        raw_output = sketch.get("output_file")
        if not raw_output:
            continue
        sketch_output = Path(str(raw_output)).expanduser()
        if not sketch_output.is_absolute():
            sketch_output = project_base / sketch_output
        if sketch_output.resolve() == resolved_output.resolve():
            return sketch
    for sketch in raw_sketches:
        if isinstance(sketch, dict):
            return sketch
    return {}


def number_from_cell(cell: dict[str, Any], keys: tuple[str, ...], default: float | None, label: str) -> float:
    value: Any = None
    for key in keys:
        if key in cell:
            value = cell[key]
            break
    if value is None:
        if default is None:
            raise SystemExit(f"{label} is required.")
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SystemExit(f"{label} must be a number.") from error


def normalize_cell(raw_cell: Any, index: int, key: str, default_alpha: float = 1.0) -> dict[str, Any]:
    if isinstance(raw_cell, dict):
        cell = raw_cell
        x = number_from_cell(cell, ("x", "left"), None, f"{key}[{index}].x")
        y = number_from_cell(cell, ("y", "top"), None, f"{key}[{index}].y")
        width = number_from_cell(cell, ("width", "w"), None, f"{key}[{index}].width")
        height = number_from_cell(cell, ("height", "h"), None, f"{key}[{index}].height")
        alpha = number_from_cell(cell, ("alpha", "opacity"), default_alpha, f"{key}[{index}].alpha")
        source_value = cell.get("source", cell.get("source_index", index))
    elif isinstance(raw_cell, list) and len(raw_cell) >= 4:
        x = float(raw_cell[0])
        y = float(raw_cell[1])
        width = float(raw_cell[2])
        height = float(raw_cell[3])
        alpha = float(raw_cell[4]) if len(raw_cell) >= 5 else default_alpha
        source_value = raw_cell[5] if len(raw_cell) >= 6 else index
    else:
        raise SystemExit(f"{key}[{index}] must be an object or [x, y, width, height, alpha?, source?].")

    if not 0 <= x <= 1:
        raise SystemExit(f"{key}[{index}].x must be between 0 and 1.")
    if not 0 <= y <= 1:
        raise SystemExit(f"{key}[{index}].y must be between 0 and 1.")
    if width <= 0 or width > 1:
        raise SystemExit(f"{key}[{index}].width must be greater than 0 and no more than 1.")
    if height <= 0 or height > 1:
        raise SystemExit(f"{key}[{index}].height must be greater than 0 and no more than 1.")
    if x + width > 1.08:
        raise SystemExit(f"{key}[{index}] extends too far past the right edge.")
    if y + height > 1.08:
        raise SystemExit(f"{key}[{index}] extends too far past the bottom edge.")
    if not 0 <= alpha <= 1:
        raise SystemExit(f"{key}[{index}].alpha must be between 0 and 1.")
    try:
        source_index = int(source_value)
    except (TypeError, ValueError) as error:
        raise SystemExit(f"{key}[{index}].source must be an integer clip index.") from error
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "alpha": alpha,
        "source": max(0, source_index),
    }


def configured_cells(
    sketch_config: dict[str, Any],
    key: str,
    default_cells: list[dict[str, Any]] | None = None,
    requested_count: int | None = None,
    default_alpha: float = 1.0,
) -> list[dict[str, Any]]:
    raw_cells = sketch_config.get(key)
    if raw_cells is None:
        cells = [dict(cell) for cell in (default_cells or [])]
    else:
        if not isinstance(raw_cells, list):
            raise SystemExit(f"{key} must be an array of cell objects.")
        cells = [
            normalize_cell(raw_cell, index, key, default_alpha=default_alpha)
            for index, raw_cell in enumerate(raw_cells)
        ]
    if not cells:
        return []
    if requested_count is not None and requested_count > 0:
        cells = cells[:requested_count]
    return cells


def project_clips(project: dict[str, Any], base: Path) -> list[Path]:
    raw_clips = project.get("clips", [])
    clips: list[Path] = []
    if isinstance(raw_clips, list):
        for clip in raw_clips:
            if isinstance(clip, str):
                raw_path = clip
                enabled = True
            elif isinstance(clip, dict):
                raw_path = clip.get("path")
                enabled = bool(clip.get("enabled", True))
            else:
                continue
            if not enabled or not raw_path:
                continue
            path = Path(str(raw_path)).expanduser()
            resolved = path if path.is_absolute() else base / path
            if resolved.suffix.lower() in VIDEO_EXTENSIONS:
                clips.append(resolved)
    if clips:
        return clips

    input_dir = resolve_path(project.get("input_dir"), base, SCRIPT_DIR / "samples")
    if not input_dir.exists():
        return []
    return sorted(path for path in input_dir.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)


def model_underlay_path(project: dict[str, Any], base: Path) -> Path | None:
    composition = project.get("composition", {})
    if not isinstance(composition, dict):
        return None
    raw_assets = composition.get("arrangement_model_assets", [])
    if not isinstance(raw_assets, list):
        return None
    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue
        raw_path = asset.get("path")
        if not raw_path:
            continue
        path = Path(str(raw_path)).expanduser()
        resolved = path if path.is_absolute() else base / path
        if resolved.exists() and resolved.suffix.lower() in IMAGE_EXTENSIONS:
            return resolved
    return None


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required tool not found on PATH: {name}")


def seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def slice_layout(width: int, slice_count: int) -> list[tuple[int, int]]:
    slice_width = max(24, math.ceil(width / max(slice_count * 0.68, 1)))
    if slice_count == 1:
        return [(0, width)]
    max_x = max(0, width - slice_width)
    return [
        (round(index * max_x / (slice_count - 1)), slice_width)
        for index in range(slice_count)
    ]


def slice_filter(
    input_index: int,
    slice_index: int,
    x: int,
    slice_width: int,
    args: argparse.Namespace,
) -> str:
    max_source_x = max(0, args.width - slice_width)
    source_shift = (slice_index * 83) % (max_source_x + 1)
    alpha = 0.56 if slice_index % 3 else 0.82
    tone = "hue=s=0," if slice_index % 2 else ""
    return (
        f"[{input_index}:v]"
        f"scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
        f"crop={args.width}:{args.height},"
        f"crop={slice_width}:{args.height}:{source_shift}:0,"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"{tone}format=rgba,colorchannelmixer=aa={alpha}"
        f"[s{slice_index}]"
    )


def overlay_chain(
    slice_positions: list[tuple[int, int]],
    args: argparse.Namespace,
    base_ready: bool = False,
) -> list[str]:
    filters = []
    if not base_ready:
        filters.append(f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[base]")
    previous = "base"
    for index, (x, _) in enumerate(slice_positions):
        output = f"mix{index}"
        filters.append(f"[{previous}][s{index}]overlay=x={x}:y=0:shortest=1[{output}]")
        previous = output

    panel_width = args.width // 3
    band_one = round(args.height * 0.27)
    band_two = round(args.height * 0.55)
    band_height = max(24, round(args.height * 0.11))
    filters.append(
        f"[{previous}]"
        f"drawbox=x={panel_width}:y=0:w=2:h=ih:color=white@0.22:t=fill,"
        f"drawbox=x={panel_width * 2}:y=0:w=2:h=ih:color=white@0.22:t=fill,"
        f"drawbox=x=0:y={band_one}:w=iw:h={band_height}:color=white@0.07:t=fill,"
        f"drawbox=x=0:y={band_two}:w=iw:h={band_height}:color=black@0.18:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def model_underlay_filters(
    input_index: int,
    panel_order: tuple[str, str, str],
    args: argparse.Namespace,
) -> list[str]:
    alpha = min(1, max(0, args.model_opacity))
    if args.model_fit == "triptych":
        panel_width = args.width // 3
        filters = [f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[canvas]"]
        panel_labels = []
        for visible_index, panel_name in enumerate(panel_order):
            model_index = PANEL_NAMES.index(panel_name)
            crop_x = "0" if model_index == 0 else "iw/3" if model_index == 1 else "iw*2/3"
            label = f"[modelpanel{visible_index}]"
            filters.append(
                f"[{input_index}:v]"
                f"crop=iw/3:ih:{crop_x}:0,"
                f"scale={panel_width}:{args.height}:force_original_aspect_ratio=increase,"
                f"crop={panel_width}:{args.height},"
                f"fps={args.fps},trim=duration={seconds(args.duration)},"
                "setpts=PTS-STARTPTS,"
                f"hue=s=0,eq=contrast=1.12:brightness=-0.02,format=rgba,colorchannelmixer=aa={alpha}"
                f"{label}"
            )
            panel_labels.append(label)
        filters.append("".join(panel_labels) + "hstack=inputs=3[model]")
        filters.append("[canvas][model]overlay=x=0:y=0:shortest=1[base]")
        return filters

    if args.model_fit == "cover":
        placement = (
            f"scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
            f"crop={args.width}:{args.height},"
        )
    else:
        placement = (
            f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,"
            f"pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2:black,"
        )
    return [
        f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[canvas]",
        f"[{input_index}:v]"
        f"{placement}"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"hue=s=0,eq=contrast=1.12:brightness=-0.02,format=rgba,colorchannelmixer=aa={alpha}"
        "[model]",
        "[canvas][model]overlay=x=0:y=0:shortest=1[base]",
    ]


def serial_input_sources(clips: list[Path], panel_order: tuple[str, str, str], args: argparse.Namespace) -> list[Path]:
    selected = clips[: max(1, min(args.source_count, len(clips)))]
    voice_index = {"left": 0, "middle": 1, "right": 2}
    sources: list[Path] = []
    for panel_name in panel_order:
        base_index = voice_index[panel_name] % len(selected)
        if len(selected) > 3:
            ghost_index = (base_index + 3) % len(selected)
        elif len(selected) > 1:
            ghost_index = (base_index + 1) % len(selected)
        else:
            ghost_index = base_index
        sources.extend([selected[base_index], selected[ghost_index]])
    return sources


def fracture_input_sources(clips: list[Path], panel_order: tuple[str, str, str], args: argparse.Namespace) -> list[Path]:
    selected = clips[: max(1, min(args.source_count, len(clips)))]
    voice_index = {"left": 0, "middle": 1, "right": 2}
    sources: list[Path] = []
    for panel_name in panel_order:
        base_index = voice_index[panel_name] % len(selected)
        for row in range(3):
            sources.append(selected[(base_index + row * 3) % len(selected)])
    return sources


def default_score_cell_specs(count: int) -> list[dict[str, Any]]:
    requested = max(1, count)
    if requested <= len(DEFAULT_SCORE_CELLS):
        return [dict(cell) for cell in DEFAULT_SCORE_CELLS[:requested]]
    specs = [dict(cell) for cell in DEFAULT_SCORE_CELLS]
    while len(specs) < requested:
        cell = DEFAULT_SCORE_CELLS[len(specs) % len(DEFAULT_SCORE_CELLS)]
        drift = 0.025 * (len(specs) // len(DEFAULT_SCORE_CELLS) + 1)
        specs.append(
            {
                **cell,
                "x": min(0.86, float(cell["x"]) + drift),
                "alpha": max(0.36, float(cell["alpha"]) - 0.12),
            }
        )
    return specs


def score_cell_specs(count: int, sketch_config: dict[str, Any]) -> list[dict[str, Any]]:
    return configured_cells(
        sketch_config,
        "score_cells",
        default_cells=default_score_cell_specs(count),
        requested_count=count,
        default_alpha=0.66,
    )


def fracture_cell_specs(sketch_config: dict[str, Any]) -> list[dict[str, Any]]:
    return configured_cells(sketch_config, "fracture_cells", default_alpha=1.0)


def signal_cell_specs(sketch_config: dict[str, Any]) -> list[dict[str, Any]]:
    return configured_cells(
        sketch_config,
        "signal_cells",
        default_cells=DEFAULT_SIGNAL_CELLS,
        default_alpha=0.78,
    )


def map_cell_rect(
    spec: dict[str, Any],
    panel_order: tuple[str, str, str],
    args: argparse.Namespace,
) -> tuple[int, int, int, int, float]:
    x_frac = float(spec["x"])
    y_frac = float(spec["y"])
    width_frac = float(spec["width"])
    height_frac = float(spec["height"])
    alpha = float(spec["alpha"])
    panel_width = args.width // 3
    internal_index = max(0, min(2, int(x_frac * 3)))
    local_x = (x_frac - (internal_index / 3)) * 3
    panel_name = PANEL_NAMES[internal_index]
    visible_index = panel_order.index(panel_name)
    x = round(visible_index * panel_width + local_x * panel_width)
    y = round(y_frac * args.height)
    width = max(24, round(width_frac * args.width))
    height = max(24, round(height_frac * args.height))
    return x, y, width, height, alpha


def cell_input_sources(clips: list[Path], args: argparse.Namespace, cells: list[dict[str, Any]]) -> list[Path]:
    selected = clips[: max(1, min(args.source_count, len(clips)))]
    return [selected[int(cell.get("source", index)) % len(selected)] for index, cell in enumerate(cells)]


def serial_clip_filter(
    input_index: int,
    panel_width: int,
    args: argparse.Namespace,
    output_label: str,
    ghost: bool = False,
) -> str:
    tone = "hue=s=0,eq=brightness=0.035:saturation=0.72," if ghost else "eq=brightness=0.018:saturation=0.92,"
    alpha = "colorchannelmixer=aa=0.24" if ghost else "colorchannelmixer=aa=1"
    return (
        f"[{input_index}:v]"
        f"scale={panel_width}:{args.height}:force_original_aspect_ratio=increase,"
        f"crop={panel_width}:{args.height},"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"{tone}format=rgba,{alpha}"
        f"{output_label}"
    )


def serial_filters(panel_order: tuple[str, str, str], args: argparse.Namespace) -> list[str]:
    panel_width = args.width // 3
    filters: list[str] = []
    panel_labels = []
    for index, panel_name in enumerate(panel_order):
        base_input = index * 2
        ghost_input = base_input + 1
        base_label = f"[serial{index}base]"
        ghost_label = f"[serial{index}ghost]"
        panel_label = f"[serial{index}]"
        offset = round((index - 1) * panel_width * 0.035)
        filters.append(serial_clip_filter(base_input, panel_width, args, base_label))
        filters.append(serial_clip_filter(ghost_input, panel_width, args, ghost_label, ghost=True))
        filters.append(
            f"{base_label}{ghost_label}"
            f"overlay=x={offset}:y=0:shortest=1,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.05:t=fill,"
            "drawbox=x=0:y=0:w=2:h=ih:color=white@0.20:t=fill,"
            "drawbox=x=iw-2:y=0:w=2:h=ih:color=black@0.18:t=fill,"
            f"format=yuv420p{panel_label}"
        )
        panel_labels.append(panel_label)

    glare_height = max(32, round(args.height * 0.18))
    lower_band = round(args.height * 0.63)
    filters.append(
        "".join(panel_labels)
        +
        "hstack=inputs=3,"
        f"drawbox=x=0:y=0:w=iw:h={glare_height}:color=white@0.08:t=fill,"
        f"drawbox=x=0:y={lower_band}:w=iw:h={max(18, round(args.height * 0.04))}:color=black@0.10:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def fracture_clip_filter(
    input_index: int,
    tile_width: int,
    tile_height: int,
    args: argparse.Namespace,
    output_label: str,
) -> str:
    contrast = 1.08 + (input_index % 3) * 0.11
    saturation = 0.58 if input_index % 2 else 0.92
    brightness = -0.025 if input_index % 4 == 0 else 0.018
    line_y = max(0, min(tile_height - 5, round(tile_height * (0.18 + (input_index % 5) * 0.14))))
    line_height = max(5, round(tile_height * 0.024))
    line_color = "white@0.16" if input_index % 2 else "black@0.18"
    return (
        f"[{input_index}:v]"
        f"scale={tile_width + 42}:{tile_height + 42}:force_original_aspect_ratio=increase,"
        f"crop={tile_width}:{tile_height},"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"eq=contrast={contrast:.3f}:brightness={brightness:.3f}:saturation={saturation:.3f},"
        f"drawbox=x=0:y={line_y}:w=iw:h={line_height}:color={line_color}:t=fill,"
        "format=yuv420p"
        f"{output_label}"
    )


def fracture_filters(args: argparse.Namespace) -> list[str]:
    if args.height % 3:
        raise SystemExit("--height must divide evenly into three rows for fracture sketches.")
    tile_width = args.width // 3
    tile_height = args.height // 3
    filters: list[str] = []
    labels = []
    for index in range(9):
        label = f"[fracture{index}]"
        filters.append(fracture_clip_filter(index, tile_width, tile_height, args, label))
        labels.append(label)

    layout = []
    for column in range(3):
        for row in range(3):
            layout.append(f"{column * tile_width}_{row * tile_height}")

    first_band_y = round(args.height * 0.31)
    second_band_y = round(args.height * 0.67)
    vertical_slip_x = round(args.width * 0.47)
    filters.append(
        "".join(labels)
        + f"xstack=inputs=9:layout={'|'.join(layout)}:fill=black,"
        f"drawbox=x={tile_width}:y=0:w=2:h=ih:color=white@0.22:t=fill,"
        f"drawbox=x={tile_width * 2}:y=0:w=2:h=ih:color=white@0.22:t=fill,"
        f"drawbox=x=0:y={tile_height}:w=iw:h=2:color=white@0.12:t=fill,"
        f"drawbox=x=0:y={tile_height * 2}:w=iw:h=2:color=black@0.18:t=fill,"
        f"drawbox=x=0:y={first_band_y}:w=iw:h={max(10, round(args.height * 0.022))}:color=white@0.11:t=fill,"
        f"drawbox=x=0:y={second_band_y}:w=iw:h={max(14, round(args.height * 0.035))}:color=black@0.20:t=fill,"
        f"drawbox=x={vertical_slip_x}:y=0:w={max(8, round(args.width * 0.024))}:h=ih:color=black@0.16:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def fracture_cell_filter(
    input_index: int,
    cell_index: int,
    width: int,
    height: int,
    alpha: float,
    args: argparse.Namespace,
) -> str:
    contrast = 1.16 + (cell_index % 4) * 0.12
    saturation = 0.48 if cell_index % 2 else 1.05
    brightness = -0.04 if cell_index % 3 == 0 else 0.02
    line_y = max(0, min(height - 5, round(height * (0.16 + (cell_index % 5) * 0.15))))
    line_height = max(4, round(height * 0.032))
    line_color = "white@0.20" if cell_index % 2 else "black@0.24"
    skew_crop = 70
    x_offset = (cell_index * 23) % (skew_crop + 1)
    y_offset = (cell_index * 31) % (skew_crop + 1)
    return (
        f"[{input_index}:v]"
        f"scale={width + skew_crop}:{height + skew_crop}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:{x_offset}:{y_offset},"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"eq=contrast={contrast:.3f}:brightness={brightness:.3f}:saturation={saturation:.3f},"
        f"drawbox=x=0:y={line_y}:w=iw:h={line_height}:color={line_color}:t=fill,"
        f"format=rgba,colorchannelmixer=aa={alpha}"
        f"[fracturecell{cell_index}]"
    )


def fracture_cell_filters(
    cells: list[dict[str, Any]],
    panel_order: tuple[str, str, str],
    args: argparse.Namespace,
) -> list[str]:
    filters: list[str] = [
        f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[base]"
    ]
    rects = [map_cell_rect(spec, panel_order, args) for spec in cells]
    for index, (_, _, width, height, alpha) in enumerate(rects):
        filters.append(fracture_cell_filter(index, index, width, height, alpha, args))

    previous = "base"
    for index, (x, y, _, _, _) in enumerate(rects):
        output = f"fracturemix{index}"
        filters.append(f"[{previous}][fracturecell{index}]overlay=x={x}:y={y}:shortest=1[{output}]")
        previous = output

    panel_width = args.width // 3
    filters.append(
        f"[{previous}]"
        f"drawbox=x={panel_width}:y=0:w=2:h=ih:color=white@0.22:t=fill,"
        f"drawbox=x={panel_width * 2}:y=0:w=2:h=ih:color=white@0.18:t=fill,"
        f"drawbox=x=0:y={round(args.height * 0.30)}:w=iw:h={max(8, round(args.height * 0.018))}:color=white@0.13:t=fill,"
        f"drawbox=x=0:y={round(args.height * 0.62)}:w=iw:h={max(12, round(args.height * 0.030))}:color=black@0.24:t=fill,"
        f"drawbox=x={round(args.width * 0.44)}:y=0:w={max(7, round(args.width * 0.018))}:h=ih:color=black@0.18:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def signal_cell_filter(
    input_index: int,
    cell_index: int,
    width: int,
    height: int,
    alpha: float,
    args: argparse.Namespace,
) -> str:
    crop_pad = 96
    x_offset = (cell_index * 41) % (crop_pad + 1)
    y_offset = (cell_index * 29) % (crop_pad + 1)
    contrast = 1.34 + (cell_index % 4) * 0.18
    saturation = 1.45 + (cell_index % 3) * 0.34
    brightness = -0.055 if cell_index % 2 else 0.026
    tear_y = max(0, min(height - 4, round(height * (0.13 + (cell_index % 6) * 0.13))))
    tear_height = max(4, round(height * (0.018 + (cell_index % 3) * 0.010)))
    tear_color = "white@0.24" if cell_index % 2 else "black@0.28"
    phase_shift = max(2, round(width * (0.018 + (cell_index % 4) * 0.012)))
    return (
        f"[{input_index}:v]"
        f"scale={width + crop_pad}:{height + crop_pad}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:{x_offset}:{y_offset},"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"eq=contrast={contrast:.3f}:brightness={brightness:.3f}:saturation={saturation:.3f},"
        f"drawbox=x=0:y={tear_y}:w=iw:h={tear_height}:color={tear_color}:t=fill,"
        f"drawbox=x={phase_shift}:y=0:w={max(2, phase_shift // 2)}:h=ih:color=white@0.06:t=fill,"
        f"format=rgba,colorchannelmixer=aa={alpha}"
        f"[signalcell{cell_index}]"
    )


def signal_filters(
    cells: list[dict[str, Any]],
    panel_order: tuple[str, str, str],
    args: argparse.Namespace,
) -> list[str]:
    filters: list[str] = [
        f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[base]"
    ]
    rects = [map_cell_rect(spec, panel_order, args) for spec in cells]
    for index, (_, _, width, height, alpha) in enumerate(rects):
        filters.append(signal_cell_filter(index, index, width, height, alpha, args))

    previous = "base"
    for index, (x, y, _, _, _) in enumerate(rects):
        output = f"signalmix{index}"
        x_slip = x + ((index % 3) - 1) * max(2, round(args.width * 0.006))
        filters.append(f"[{previous}][signalcell{index}]overlay=x={x_slip}:y={y}:shortest=1[{output}]")
        previous = output

    panel_width = args.width // 3
    filters.append(
        f"[{previous}]"
        f"drawbox=x={panel_width}:y=0:w=2:h=ih:color=white@0.18:t=fill,"
        f"drawbox=x={panel_width * 2}:y=0:w=2:h=ih:color=black@0.24:t=fill,"
        f"drawbox=x=0:y={round(args.height * 0.18)}:w=iw:h={max(5, round(args.height * 0.012))}:color=white@0.16:t=fill,"
        f"drawbox=x=0:y={round(args.height * 0.42)}:w=iw:h={max(7, round(args.height * 0.016))}:color=black@0.28:t=fill,"
        f"drawbox=x=0:y={round(args.height * 0.76)}:w=iw:h={max(6, round(args.height * 0.014))}:color=white@0.13:t=fill,"
        f"drawbox=x={round(args.width * 0.54)}:y=0:w={max(6, round(args.width * 0.016))}:h=ih:color=white@0.07:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def score_clip_filter(
    input_index: int,
    cell_index: int,
    width: int,
    height: int,
    alpha: float,
    args: argparse.Namespace,
) -> str:
    crop_pad = 64
    offset = (cell_index * 17) % (crop_pad + 1)
    contrast = 1.04 + (cell_index % 4) * 0.07
    brightness = -0.025 if cell_index % 3 == 0 else 0.012
    saturation = 0.38 if cell_index % 2 else 0.95
    tone = f"eq=contrast={contrast:.3f}:brightness={brightness:.3f}:saturation={saturation:.3f},"
    if cell_index % 3 == 1:
        tone = "hue=s=0," + tone
    return (
        f"[{input_index}:v]"
        f"scale={width + crop_pad}:{height + crop_pad}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:{offset}:{crop_pad - offset},"
        f"fps={args.fps},trim=duration={seconds(args.duration)},"
        "setpts=PTS-STARTPTS,"
        f"{tone}format=rgba,colorchannelmixer=aa={alpha}"
        f"[score{cell_index}]"
    )


def score_filters(
    panel_order: tuple[str, str, str],
    args: argparse.Namespace,
    cells: list[dict[str, Any]],
    base_ready: bool = False,
) -> list[str]:
    filters: list[str] = []
    if not base_ready:
        filters.append(f"color=c=black:s={args.width}x{args.height}:r={args.fps}:d={seconds(args.duration)}[base]")
    rects = [map_cell_rect(spec, panel_order, args) for spec in cells]
    for index, (_, _, width, height, alpha) in enumerate(rects):
        filters.append(score_clip_filter(index, index, width, height, alpha, args))

    previous = "base"
    for index, (x, y, _, _, _) in enumerate(rects):
        output = f"scoremix{index}"
        filters.append(f"[{previous}][score{index}]overlay=x={x}:y={y}:shortest=1[{output}]")
        previous = output

    panel_width = args.width // 3
    band_one = round(args.height * 0.31)
    band_two = round(args.height * 0.56)
    band_three = round(args.height * 0.80)
    filters.append(
        f"[{previous}]"
        f"drawbox=x={panel_width}:y=0:w=2:h=ih:color=white@0.24:t=fill,"
        f"drawbox=x={panel_width * 2}:y=0:w=2:h=ih:color=white@0.24:t=fill,"
        f"drawbox=x=0:y={band_one}:w=iw:h={max(18, round(args.height * 0.035))}:color=black@0.15:t=fill,"
        f"drawbox=x=0:y={band_two}:w=iw:h={max(20, round(args.height * 0.045))}:color=white@0.08:t=fill,"
        f"drawbox=x=0:y={band_three}:w=iw:h={max(14, round(args.height * 0.028))}:color=black@0.18:t=fill,"
        "format=yuv420p[outv]"
    )
    return filters


def build_command(project: dict[str, Any], project_base: Path, args: argparse.Namespace) -> list[str]:
    if args.width % 3 != 0:
        raise SystemExit("--width must divide evenly into three panels.")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        raise SystemExit("--width, --height, and --fps must be positive.")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive.")
    if args.slices <= 0:
        raise SystemExit("--slices must be positive.")
    if args.source_count <= 0:
        raise SystemExit("--source-count must be positive.")
    if args.style not in SKETCH_STYLES:
        raise SystemExit(f"--style must be one of: {', '.join(sorted(SKETCH_STYLES))}")
    if args.model_fit not in MODEL_FITS:
        raise SystemExit(f"--model-fit must be one of: {', '.join(sorted(MODEL_FITS))}")
    if not 0 <= args.crf <= 51:
        raise SystemExit("--crf must be between 0 and 51.")
    if not 0 <= args.model_opacity <= 1:
        raise SystemExit("--model-opacity must be between 0 and 1.")

    output = args.output.expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    if not path_inside(output, SCRIPT_DIR):
        raise SystemExit("output must stay inside the SIMVLTANEA repository root.")
    sketch_config = active_visual_sketch_config(project, project_base, output)

    panel_value = args.panel_order
    if panel_value is None:
        panel_value = project.get("panel_order", project.get("canvas", {}).get("panel_order"))
    panel_order = normalize_panel_order(panel_value)

    clips = [path for path in project_clips(project, project_base) if path.exists()]
    if not clips:
        raise SystemExit("No usable video clips found in project.")
    clips = clips[: args.source_count]

    score_cells: list[dict[str, Any]] = []
    fracture_cells: list[dict[str, Any]] = []
    signal_cells: list[dict[str, Any]] = []
    if args.style == "serial":
        input_sources = serial_input_sources(clips, panel_order, args)
    elif args.style == "fracture":
        fracture_cells = fracture_cell_specs(sketch_config)
        input_sources = (
            cell_input_sources(clips, args, fracture_cells)
            if fracture_cells
            else fracture_input_sources(clips, panel_order, args)
        )
    elif args.style == "score":
        score_cells = score_cell_specs(args.slices, sketch_config)
        input_sources = cell_input_sources(clips, args, score_cells)
    elif args.style == "signal":
        signal_cells = signal_cell_specs(sketch_config)
        input_sources = cell_input_sources(clips, args, signal_cells)
    else:
        input_sources = [clips[index % len(clips)] for index in range(args.slices)]

    underlay_path = None
    if args.style in {"score", "slices"} and not args.no_model_underlay:
        underlay_path = model_underlay_path(project, project_base)
    underlay_index = len(input_sources) if underlay_path is not None else None

    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    for source in input_sources:
        command.extend(["-stream_loop", "-1", "-t", seconds(args.duration), "-i", str(source)])
    if underlay_path is not None:
        command.extend(["-loop", "1", "-t", seconds(args.duration), "-i", str(underlay_path)])

    if args.style == "serial":
        filters = serial_filters(panel_order, args)
    elif args.style == "fracture":
        filters = fracture_cell_filters(fracture_cells, panel_order, args) if fracture_cells else fracture_filters(args)
    elif args.style == "score":
        filters = model_underlay_filters(underlay_index, panel_order, args) if underlay_index is not None else []
        filters.extend(score_filters(panel_order, args, score_cells, base_ready=underlay_index is not None))
    elif args.style == "signal":
        filters = signal_filters(signal_cells, panel_order, args)
    else:
        slice_positions = slice_layout(args.width, args.slices)
        filters = model_underlay_filters(underlay_index, panel_order, args) if underlay_index is not None else []
        filters.extend(
            [
                slice_filter(
                    input_index=index,
                    slice_index=index,
                    x=x,
                    slice_width=slice_width,
                    args=args,
                )
                for index, (x, slice_width) in enumerate(slice_positions)
            ]
        )
        filters.extend(overlay_chain(slice_positions, args, base_ready=underlay_index is not None))

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outv]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(args.fps),
            "-metadata",
            f"comment=style:{args.style};panel_order:{','.join(panel_order)}",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return command


def main() -> int:
    args = parse_args()
    require_tool("ffmpeg")
    project, project_base = load_project(args.project)
    command = build_command(project, project_base, args)
    print(" ".join(command), flush=True)
    if args.dry_run:
        return 0
    output = Path(command[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
