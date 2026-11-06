"""Displayed geometry of a video stream from ffprobe facts (stdlib only, no Pillow, no SDK).

A phone portrait clip is stored as a landscape-coded stream plus a display rotation of 90 or 270
degrees. The coded ``width``/``height`` therefore say nothing about how the clip appears. This module
reads the rotation the way ``src/independent_loop_compositor/proxy.py`` does (``ffprobe_json`` and
``stream_rotation``) and derives the displayed size and the orientation word that tag records use.

ffprobe's sign convention: ``-90`` is a clockwise display rotation (phone portrait), ``90`` is
counter-clockwise. Only ``abs(rotation) % 180`` matters for the displayed size.

The rotation is read from the stream's ``side_data_list`` (an item holding ``rotation``) first, then from
the legacy ``tags.rotate`` (whose sign is the opposite, as in proxy.py). A missing, non-numeric,
non-finite or not-a-multiple-of-90 rotation counts as 0. The ffprobe call asks for whole streams as JSON;
it does not use ``-show_entries ...stream_side_data``, whose output differs between FFmpeg versions.
"""

from __future__ import annotations

import json
import math
import pathlib
import subprocess

PORTRAIT, LANDSCAPE = "portrait", "landscape"
ORIENTATIONS = (PORTRAIT, LANDSCAPE)
ANGLE_TOLERANCE = 0.01  # degrees; ffprobe prints some matrices as 90.000000 or -90.0


def _angle(value) -> int | None:
    """``value`` as a whole multiple of 90 degrees, or None when it is not one."""
    if isinstance(value, bool):
        return None
    try:
        angle = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(angle):
        return None
    quarter_turns = round(angle / 90)
    if abs(angle - quarter_turns * 90) > ANGLE_TOLERANCE:
        return None
    return quarter_turns * 90


def stream_rotation(stream: dict) -> int:
    """Display rotation in degrees (ffprobe sign convention); 0 when absent or unusable."""
    if not isinstance(stream, dict):
        return 0
    side_data = stream.get("side_data_list")
    for item in side_data if isinstance(side_data, list) else []:
        if isinstance(item, dict) and "rotation" in item:
            return _angle(item["rotation"]) or 0
    tags = stream.get("tags")
    tag = tags.get("rotate") if isinstance(tags, dict) else None
    if tag in (None, ""):
        return 0
    angle = _angle(tag)
    return -angle if angle else 0  # the legacy tag counts the other way round


def display_size(width, height, rotation: int) -> tuple:
    """(width, height) as displayed: swapped when the rotation is a quarter turn."""
    return (height, width) if abs(rotation) % 180 == 90 else (width, height)


def orientation_for(width, height) -> str:
    """``portrait`` when the displayed height exceeds the width, otherwise ``landscape`` (square included)."""
    return PORTRAIT if (height or 0) > (width or 0) else LANDSCAPE


def _size(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def geometry_from_stream(stream: dict) -> dict | None:
    """Coded size, rotation, displayed size and orientation of a stream; None without a usable size."""
    if not isinstance(stream, dict):
        return None
    coded_width, coded_height = _size(stream.get("width")), _size(stream.get("height"))
    if coded_width is None or coded_height is None:
        return None
    rotation = stream_rotation(stream)
    width, height = display_size(coded_width, coded_height, rotation)
    return {"rotation": rotation, "coded_width": coded_width, "coded_height": coded_height,
            "display_width": width, "display_height": height, "orientation": orientation_for(width, height)}


def run_ffprobe(path: pathlib.Path, timeout: float = 120) -> dict | None:
    """The first video stream's ffprobe JSON (streams and format), or None when it cannot be read."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format", "-of", "json",
             str(path)],
            capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def first_stream(data: dict | None) -> dict:
    """The first stream of ffprobe JSON, or ``{}``."""
    streams = (data or {}).get("streams")
    if isinstance(streams, list) and streams and isinstance(streams[0], dict):
        return streams[0]
    return {}


def probe_geometry(path: pathlib.Path) -> dict | None:
    """``geometry_from_stream`` of a fresh ffprobe run on ``path``; None when unreadable."""
    return geometry_from_stream(first_stream(run_ffprobe(path)))
