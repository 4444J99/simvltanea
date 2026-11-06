"""Turn phone clips into small, browser-playable H.264 proxies.

Every panel shows a cropped window onto its loop, so a short side of a few
hundred pixels is enough. Each clip is probed, encoded with rotation baked in,
constant frame rate, no audio and an explicit full-to-limited range conversion,
then probed again and rejected unless the result is exactly as promised.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

PROGRAM = "independent-loop-compositor proxy"
DOCTOR_HINT = "Run `independent-loop-compositor doctor` to check prerequisites."
VIDEO_SUFFIXES = (".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi")
DEFAULT_OUT = "proxies"
DEFAULT_SHORT_SIDE = 540
DEFAULT_CRF = 28
DEFAULT_FPS = "24"
ENCODER = "libx264"
PRESET = "medium"
PROFILE = "main"
OUTPUT_PIX_FMT = "yuv420p"
OUTPUT_COLOR = "bt709"
FRAME_RATE_TOLERANCE = 0.001  # relative
TIMESTAMP_TOLERANCE = 0.002  # seconds
VFR_TOLERANCE = 0.001  # relative difference between average and nominal rate
HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
WIDE_GAMUT = frozenset({"bt2020", "bt2020nc", "bt2020c"})
MATRIX_NAMES = {
    "bt709": "bt709",
    "smpte170m": "smpte170m",
    "bt470bg": "smpte170m",
    "fcc": "fcc",
    "smpte240m": "smpte240m",
}
_BIT_DEPTH_SUFFIX = re.compile(r"p(9|10|12|14|16)(?:le|be)?$")


class ClipError(Exception):
    """A clip that cannot or must not be converted; the message is one line."""


@dataclass
class Source:
    codec: str
    width: int
    height: int
    pix_fmt: str
    bit_depth: int
    color_range: str
    color_space: str
    color_primaries: str
    color_transfer: str
    rotation: int
    sample_aspect: Fraction
    avg_frame_rate: Fraction | None
    nominal_frame_rate: Fraction | None
    duration: float
    has_audio: bool
    stream_index: int

    @property
    def variable_rate(self) -> bool:
        if not self.avg_frame_rate or not self.nominal_frame_rate:
            return False
        difference = abs(self.avg_frame_rate - self.nominal_frame_rate) / self.nominal_frame_rate
        return float(difference) > VFR_TOLERANCE

    @property
    def displayed_size(self) -> tuple[int, int]:
        """Square-pixel display size; non-square pixels shrink one axis so no axis is upscaled."""
        width, height = Fraction(self.width), Fraction(self.height)
        if self.sample_aspect > 1:
            height /= self.sample_aspect
        elif 0 < self.sample_aspect < 1:
            width *= self.sample_aspect
        sizes = (max(1, round(width)), max(1, round(height)))
        return (sizes[1], sizes[0]) if self.rotation % 180 else sizes

    def summary(self) -> str:
        rate = "VFR" if self.variable_rate else "CFR"
        return f"{self.codec.upper()} {self.width}x{self.height} rot {self.rotation} {rate} {self.pix_fmt}"

    def report(self) -> dict[str, Any]:
        return {
            "codec": self.codec, "width": self.width, "height": self.height, "pix_fmt": self.pix_fmt,
            "bit_depth": self.bit_depth, "color_range": self.color_range or "unknown",
            "color_space": self.color_space or "unknown", "rotation": self.rotation,
            "avg_frame_rate": str(self.avg_frame_rate) if self.avg_frame_rate else None,
            "variable_frame_rate": self.variable_rate, "duration": round(self.duration, 6),
            "has_audio": self.has_audio,
        }


@dataclass
class Settings:
    short_side: int
    crf: int
    fps: Fraction

    def report(self) -> dict[str, Any]:
        return {
            "encoder": ENCODER, "codec": "h264", "profile": PROFILE, "preset": PRESET, "crf": self.crf,
            "fps": fraction_text(self.fps), "short_side": self.short_side, "pix_fmt": OUTPUT_PIX_FMT,
            "color_range": "tv", "colorspace": OUTPUT_COLOR, "color_primaries": OUTPUT_COLOR,
            "color_trc": OUTPUT_COLOR, "audio": "none", "faststart": True, "scaler": "lanczos",
        }


@dataclass
class Clip:
    path: Path
    output_name: str
    status: str = "pending"
    message: str = ""
    source: Source | None = None
    plan: dict[str, Any] = field(default_factory=dict)
    output_bytes: int | None = None
    sha256: str | None = None
    output_duration: float | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def input_bytes(self) -> int | None:
        try:
            return self.path.stat().st_size
        except OSError:
            return None


def fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def fps_label(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{float(value):.3f}".rstrip("0").rstrip(".")


def format_size(size: int | None) -> str:
    if size is None:
        return "? MB"
    if size >= 100_000:
        return f"{size / 1_000_000:.1f} MB"
    return f"{size / 1_000:.0f} KB"


def parse_rate(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "N/A"):
        return None
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def parse_clock(text: str) -> float | None:
    """Matroska stream DURATION tags look like 00:00:01.966000000."""
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", text.strip())
    if not match:
        return None
    hours, minutes, secs = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(secs)


# -- arguments -----------------------------------------------------------------

def _short_side(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text}") from None
    if value < 16 or value > 4320 or value % 2:
        raise argparse.ArgumentTypeError("must be an even number from 16 to 4320")
    return value


def _crf(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text}") from None
    if not 1 <= value <= 51:
        raise argparse.ArgumentTypeError("must be from 1 to 51 (lossless 0 needs a profile other than Main)")
    return value


def _fps(text: str) -> Fraction:
    try:
        value = Fraction(text).limit_denominator(1001)
    except (ValueError, ZeroDivisionError):
        raise argparse.ArgumentTypeError(f"not a frame rate: {text}") from None
    if not 1 <= value <= 120:
        raise argparse.ArgumentTypeError("must be from 1 to 120, for example 24 or 30000/1001")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Make small H.264 proxies of phone clips: rotation baked in, constant frame rate, "
            "no audio, limited-range BT.709, short side scaled down (never up)."),
        epilog="example:\n  independent-loop-compositor proxy phone-clips --out proxies --dry-run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", metavar="INPUT",
                        help="video file or directory (not recursive; "
                             + ", ".join(VIDEO_SUFFIXES) + ", any letter case)")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"output directory, created if missing (default: ./{DEFAULT_OUT})")
    parser.add_argument("--short-side", type=_short_side, default=DEFAULT_SHORT_SIDE,
                        help=f"target short side in pixels; smaller clips keep their size (default: {DEFAULT_SHORT_SIDE})")
    parser.add_argument("--crf", type=_crf, default=DEFAULT_CRF,
                        help=f"x264 constant rate factor, lower is better quality (default: {DEFAULT_CRF})")
    parser.add_argument("--fps", type=_fps, default=Fraction(DEFAULT_FPS),
                        help=f"constant output frame rate (default: {DEFAULT_FPS})")
    parser.add_argument("--dry-run", action="store_true", help="probe and print the plan without encoding")
    parser.add_argument("--force", action="store_true", help="replace existing proxies in --out")
    parser.add_argument("--json", action="store_true", help="print a machine-readable report to stdout")
    return parser


# -- inputs and outputs --------------------------------------------------------

def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_SUFFIXES and not path.name.startswith(".")


def collect_inputs(arguments: list[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for argument in arguments:
        path = Path(argument).expanduser()
        label = path.name or argument
        if path.is_dir():
            try:
                entries = sorted(path.iterdir(), key=lambda item: item.name)
            except OSError as error:
                raise SystemExit(f"cannot list directory {label}: {error.strerror or error}") from None
            candidates = [entry for entry in entries if entry.is_file() and is_video(entry)]
        elif path.is_file():
            if path.suffix.lower() not in VIDEO_SUFFIXES:
                raise SystemExit(f"{label}: not a supported video file (expected {', '.join(VIDEO_SUFFIXES)})")
            candidates = [path]
        elif path.exists():
            raise SystemExit(f"{label}: not a file or directory")
        else:
            raise SystemExit(f"input not found: {label}")
        for candidate in candidates:
            key = candidate.resolve()
            if key not in seen:
                seen.add(key)
                found.append(candidate)
    if not found:
        raise SystemExit(f"no video files found in the given inputs (looked for {', '.join(VIDEO_SUFFIXES)})")
    return found


def assign_output_names(paths: list[Path]) -> list[str]:
    """``<stem>.mp4``; later inputs with a taken stem get ``-2``, ``-3`` in input order."""
    used: set[str] = set()
    names = []
    for path in paths:
        candidate, number = f"{path.stem}.mp4", 2
        while candidate.casefold() in used:
            candidate, number = f"{path.stem}-{number}.mp4", number + 1
        used.add(candidate.casefold())
        names.append(candidate)
    return names


def _same_directory(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return first.resolve() == second.resolve()


def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path(".")


def prepare_output_directory(out: Path, inputs: list[Path], label: str, dry_run: bool) -> None:
    if out.exists() and not out.is_dir():
        raise SystemExit(f"--out {label} exists and is not a directory")
    target = out.resolve()
    for parent in {path.parent for path in inputs}:
        if _same_directory(out, parent) if out.exists() else target == parent.resolve():
            raise SystemExit(f"--out {label} contains input clips; choose a separate directory so proxies "
                             "are never written next to or over an input")
    if dry_run:
        base = _nearest_existing(out)
        if not os.access(base, os.W_OK | os.X_OK):
            raise SystemExit(f"--out {label} is not writable")
        return
    try:
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=out):
            pass
    except OSError as error:
        raise SystemExit(f"--out {label} is not writable: {error.strerror or error}") from None


# -- probing -------------------------------------------------------------------

def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} not found on PATH. {DOCTOR_HINT}")


_CONTEXT_PREFIX = re.compile(r"^(?:\[[^\]]*@ 0x[0-9a-f]+\]\s*)+")


def _cause_line(text: str) -> str:
    """FFmpeg's first diagnostic names the cause; later lines are consequences."""
    lines = [_CONTEXT_PREFIX.sub("", line.strip()) for line in (text or "").splitlines() if line.strip()]
    return lines[0] if lines else ""


def pixel_format_depths() -> dict[str, int]:
    """Maximum component bit depth per pixel format, from ``ffprobe -pix_fmts``."""
    completed = subprocess.run(["ffprobe", "-hide_banner", "-pix_fmts"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
    depths = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 5 and re.fullmatch(r"[\d-]+", parts[4]) and parts[0].startswith(("I", ".")):
            depths[parts[1]] = max(int(depth) for depth in parts[4].split("-"))
    return depths


def bit_depth(pix_fmt: str, depths: dict[str, int]) -> int:
    if pix_fmt in depths:
        return depths[pix_fmt]
    match = _BIT_DEPTH_SUFFIX.search(pix_fmt)
    if match:
        return int(match.group(1))
    return 10 if pix_fmt.startswith(("p01", "p21", "p41", "y21")) else 8


def ffprobe_json(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        detail = _cause_line(completed.stderr).replace(str(path), path.name)
        raise ClipError(f"not a readable video ({detail or f'ffprobe exit status {completed.returncode}'})")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise ClipError("ffprobe returned unreadable output") from None


def stream_rotation(stream: dict[str, Any]) -> float:
    for item in stream.get("side_data_list", []) or []:
        if "rotation" in item:
            return float(item["rotation"])
    tag = (stream.get("tags") or {}).get("rotate")
    return -float(tag) if tag not in (None, "") else 0.0


def has_display_matrix(stream: dict[str, Any]) -> bool:
    side_data = stream.get("side_data_list", []) or []
    return any(item.get("side_data_type") in ("Display Matrix", "DisplayMatrix") for item in side_data) or \
        "rotate" in (stream.get("tags") or {})


def video_duration(stream: dict[str, Any], container: dict[str, Any]) -> float:
    for value in (stream.get("duration"), parse_clock((stream.get("tags") or {}).get("DURATION", "")),
                  container.get("duration")):
        try:
            seconds = float(value) if value not in (None, "N/A") else 0.0
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return seconds
    raise ClipError("no positive duration")


def probe_source(path: Path, depths: dict[str, int]) -> Source:
    if not os.access(path, os.R_OK):
        raise ClipError("cannot read file: permission denied")
    data = ffprobe_json(path)
    streams = data.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"
             and not (stream.get("disposition") or {}).get("attached_pic")]
    if not video:
        raise ClipError("no video stream")
    stream = video[0]
    try:
        width, height = int(stream["width"]), int(stream["height"])
    except (KeyError, TypeError, ValueError):
        raise ClipError("video stream has no frame size") from None
    pix_fmt = stream.get("pix_fmt") or "unknown"
    try:
        aspect = Fraction(str(stream.get("sample_aspect_ratio", "1:1")).replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        aspect = Fraction(1)
    raw_rotation = stream_rotation(stream)
    if abs(raw_rotation - round(raw_rotation / 90) * 90) > 0.01:
        raise ClipError(f"refused: rotation {raw_rotation:g} is not a multiple of 90 degrees")
    rotation = int(round(raw_rotation))
    return Source(
        codec=stream.get("codec_name") or "unknown", width=width, height=height, pix_fmt=pix_fmt,
        bit_depth=bit_depth(pix_fmt, depths), color_range=stream.get("color_range") or "",
        color_space=stream.get("color_space") or "", color_primaries=stream.get("color_primaries") or "",
        color_transfer=stream.get("color_transfer") or "", rotation=rotation,
        sample_aspect=aspect if aspect > 0 else Fraction(1),
        avg_frame_rate=parse_rate(stream.get("avg_frame_rate")),
        nominal_frame_rate=parse_rate(stream.get("r_frame_rate")),
        duration=video_duration(stream, data.get("format", {})),
        has_audio=any(item.get("codec_type") == "audio" for item in streams),
        stream_index=int(stream.get("index", 0)),
    )


def refusal(source: Source) -> str | None:
    if source.bit_depth > 8:
        return (f"refused: {source.bit_depth}-bit input ({source.pix_fmt}); HDR/10-bit tone-mapping is "
                "out of scope, export an 8-bit SDR copy first")
    if source.color_transfer in HDR_TRANSFERS:
        return f"refused: HDR transfer {source.color_transfer}; tone-mapping is out of scope"
    if source.color_primaries in WIDE_GAMUT or source.color_space in WIDE_GAMUT:
        return "refused: BT.2020 wide-gamut input; gamut mapping is out of scope"
    return None


# -- planning and encoding ---------------------------------------------------

def even_floor(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def target_size(displayed: tuple[int, int], short_side: int) -> tuple[int, int]:
    """Scale the short side down to ``short_side`` keeping aspect; never upscale; even sizes."""
    width, height = displayed
    short = min(width, height)
    if short <= short_side:
        return even_floor(width), even_floor(height)
    scale = short_side / short
    if width <= height:
        return short_side, max(2, round(height * scale / 2) * 2)
    return max(2, round(width * scale / 2) * 2), short_side


def input_range(source: Source) -> str:
    if source.color_range == "pc" or source.pix_fmt.startswith("yuvj"):
        return "pc"
    if source.color_range == "tv":
        return "tv"
    return "pc" if source.pix_fmt.startswith(("rgb", "bgr", "gbr", "argb", "abgr", "rgba", "bgra")) else "tv"


def input_matrix(source: Source) -> str:
    """Tagged matrix when known; untagged HD is BT.709 and untagged SD is SMPTE 170M (BT.601)."""
    if source.color_space in MATRIX_NAMES:
        return MATRIX_NAMES[source.color_space]
    return "bt709" if source.width >= 1280 or source.height >= 720 else "smpte170m"


def filter_graph(source: Source, size: tuple[int, int], fps: Fraction) -> str:
    """Rotation is applied by FFmpeg's autorotate (on by default in every version) before this graph runs."""
    width, height = size
    return ",".join((
        f"fps={fraction_text(fps)}",
        f"scale=w={width}:h={height}:flags=lanczos+accurate_rnd+full_chroma_int"
        f":in_range={input_range(source)}:out_range=tv"
        f":in_color_matrix={input_matrix(source)}:out_color_matrix={OUTPUT_COLOR}",
        f"format={OUTPUT_PIX_FMT}",
        "setsar=1",
        f"setparams=range=tv:colorspace={OUTPUT_COLOR}:color_primaries={OUTPUT_COLOR}:color_trc={OUTPUT_COLOR}",
    ))


def encode_command(path: Path, destination: Path, source: Source, size: tuple[int, int],
                   settings: Settings) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(path),
        "-map", f"0:{source.stream_index}", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", filter_graph(source, size, settings.fps),
        "-t", f"{source.duration:.6f}", "-fps_mode", "cfr",
        "-c:v", ENCODER, "-preset", PRESET, "-profile:v", PROFILE, "-crf", str(settings.crf),
        "-pix_fmt", OUTPUT_PIX_FMT,
        "-color_range", "tv", "-colorspace", OUTPUT_COLOR, "-color_primaries", OUTPUT_COLOR,
        "-color_trc", OUTPUT_COLOR,
        "-movflags", "+faststart", "-f", "mp4", str(destination),
    ]


def top_level_boxes(path: Path) -> list[str]:
    boxes = []
    with path.open("rb") as handle:
        while True:
            header = handle.read(8)
            if len(header) < 8:
                return boxes
            size, kind = int.from_bytes(header[:4], "big"), header[4:8].decode("latin-1")
            if size == 1:
                size = int.from_bytes(handle.read(8), "big")
                offset = 16
            else:
                offset = 8
            boxes.append(kind)
            if size == 0:
                return boxes
            if size < offset:
                return boxes
            handle.seek(size - offset, os.SEEK_CUR)


def frame_times(path: Path) -> list[float]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    times = []
    for line in completed.stdout.splitlines():
        value = line.strip().rstrip(",")
        if value and value != "N/A":
            times.append(float(value))
    return sorted(times)


def validate_output(path: Path, source: Source, size: tuple[int, int], settings: Settings) -> tuple[list[str], float]:
    """Problems with an encoded proxy (empty when it is exactly as promised) and its duration."""
    try:
        data = ffprobe_json(path)
    except ClipError as error:
        return [str(error)], 0.0
    streams = data.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    problems = []
    if len(videos) != 1:
        return [f"expected one video stream, found {len(videos)}"], 0.0
    video = videos[0]
    if any(stream.get("codec_type") == "audio" for stream in streams):
        problems.append("audio stream present")
    expected = {"codec_name": "h264", "pix_fmt": OUTPUT_PIX_FMT, "color_range": "tv", "profile": "Main",
                "color_space": OUTPUT_COLOR, "color_primaries": OUTPUT_COLOR, "color_transfer": OUTPUT_COLOR}
    for key, wanted in expected.items():
        if video.get(key) != wanted:
            problems.append(f"{key} is {video.get(key)}, expected {wanted}")
    if has_display_matrix(video) or stream_rotation(video):
        problems.append("rotation metadata left in output")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if (width, height) != size:
        problems.append(f"size {width}x{height}, expected {size[0]}x{size[1]}")
    if min(width, height) > settings.short_side:
        problems.append(f"short side {min(width, height)} exceeds {settings.short_side}")
    if width % 2 or height % 2:
        problems.append(f"odd size {width}x{height}")
    for key in ("avg_frame_rate", "r_frame_rate"):
        rate = parse_rate(video.get(key))
        if rate is None or abs(float(rate / settings.fps) - 1) > FRAME_RATE_TOLERANCE:
            problems.append(f"{key} is {video.get(key)}, expected {fraction_text(settings.fps)}")
    times = frame_times(path)
    step = 1 / float(settings.fps)
    if len(times) < 1:
        problems.append("no video frames")
    elif any(abs((later - earlier) - step) > TIMESTAMP_TOLERANCE for earlier, later in zip(times, times[1:])):
        problems.append("frame timestamps are not constant-rate")
    try:
        duration = video_duration(video, data.get("format", {}))
    except ClipError:
        duration = 0.0
    if abs(duration - source.duration) > step + TIMESTAMP_TOLERANCE:
        problems.append(f"duration {duration:.3f}s differs from input {source.duration:.3f}s by more than one frame")
    boxes = top_level_boxes(path)
    if "moov" not in boxes or ("mdat" in boxes and boxes.index("moov") > boxes.index("mdat")):
        problems.append("moov atom is not before the media data (faststart)")
    return problems, duration


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert(clip: Clip, out: Path, settings: Settings, size: tuple[int, int], force: bool) -> None:
    source = clip.source
    assert source is not None
    final = out / clip.output_name
    handle, temporary_name = tempfile.mkstemp(dir=out, prefix=".", suffix=".partial.mp4")
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        completed = subprocess.run(encode_command(clip.path, temporary, source, size, settings),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            detail = _cause_line(completed.stderr).replace(str(clip.path), clip.name).replace(str(temporary), "output")
            raise ClipError(f"ffmpeg failed with exit status {completed.returncode}" + (f": {detail}" if detail else ""))
        problems, duration = validate_output(temporary, source, size, settings)
        if problems:
            raise ClipError("output failed validation: " + "; ".join(problems))
        if final.exists() and not force:
            raise ClipError(f"{clip.output_name} appeared in --out during encoding; not overwritten")
        os.replace(temporary, final)
    finally:
        temporary.unlink(missing_ok=True)
    clip.output_bytes = final.stat().st_size
    clip.sha256 = sha256_file(final)
    clip.output_duration = duration


# -- reporting -----------------------------------------------------------------

def clip_line(clip: Clip, dry_run: bool) -> str:
    assert clip.source is not None
    plan = clip.plan
    text = f"{clip.name}: {clip.source.summary()} -> {plan['width']}x{plan['height']} {plan['fps_label']}fps h264"
    if clip.output_name != f"{clip.path.stem}.mp4":
        text += f" as {clip.output_name}"
    if clip.status == "converted":
        return f"{text} {format_size(clip.output_bytes)} ({format_size(clip.input_bytes)})"
    if clip.status == "skipped":
        return f"{text} ({format_size(clip.input_bytes)}) skipped: {clip.message}"
    return f"{text} ({format_size(clip.input_bytes)})" + (" [dry run]" if dry_run else "")


def clip_report(clip: Clip, settings: Settings) -> dict[str, Any]:
    clip_settings = settings.report()
    for key in ("in_range", "in_color_matrix", "filter"):
        if key in clip.plan:
            clip_settings[key] = clip.plan[key]
    return {
        "input": clip.name, "output": clip.output_name, "status": clip.status,
        "message": clip.message or None,
        "settings": clip_settings,
        "source": clip.source.report() if clip.source else None,
        "width": clip.plan.get("width"), "height": clip.plan.get("height"),
        "input_bytes": clip.input_bytes, "output_bytes": clip.output_bytes, "sha256": clip.sha256,
        "input_duration": round(clip.source.duration, 6) if clip.source else None,
        "duration": round(clip.output_duration, 6) if clip.output_duration is not None else None,
    }


def summary(clips: list[Clip], dry_run: bool) -> dict[str, Any]:
    counts = {status: sum(1 for clip in clips if clip.status == status)
              for status in ("converted", "planned", "skipped", "failed")}
    converted = [clip for clip in clips if clip.status == "converted"]
    return {
        "clips": len(clips), **counts, "dry_run": dry_run,
        "input_bytes": sum(clip.input_bytes or 0 for clip in clips),
        "converted_input_bytes": sum(clip.input_bytes or 0 for clip in converted),
        "output_bytes": sum(clip.output_bytes or 0 for clip in converted),
        "failures": [clip.name for clip in clips if clip.status == "failed"],
    }


def summary_line(totals: dict[str, Any]) -> str:
    parts = [f"{totals['clips']} clip(s)"]
    if totals["dry_run"]:
        parts.append(f"{totals['planned']} planned")
    else:
        parts.append(f"{totals['converted']} converted")
    parts.append(f"{totals['skipped']} skipped")
    parts.append(f"{totals['failed']} failed")
    text = ", ".join(parts) + f"; input {format_size(totals['input_bytes'])}"
    if not totals["dry_run"]:
        text += (f", converted {format_size(totals['converted_input_bytes'])} -> "
                 f"{format_size(totals['output_bytes'])}")
    if totals["failures"]:
        text += "; failed: " + ", ".join(totals["failures"])
    return text


# -- command -------------------------------------------------------------------

def process(clip: Clip, out: Path, settings: Settings, depths: dict[str, int], dry_run: bool, force: bool) -> None:
    clip.source = probe_source(clip.path, depths)
    reason = refusal(clip.source)
    if reason:
        raise ClipError(reason)
    size = target_size(clip.source.displayed_size, settings.short_side)
    clip.plan = {
        "width": size[0], "height": size[1], "fps_label": fps_label(settings.fps),
        "in_range": input_range(clip.source), "in_color_matrix": input_matrix(clip.source),
        "filter": filter_graph(clip.source, size, settings.fps),
    }
    if dry_run:
        clip.status = "planned"
        return
    if (out / clip.output_name).exists() and not force:
        clip.status = "skipped"
        clip.message = f"{clip.output_name} already exists in --out (use --force to replace it)"
        return
    convert(clip, out, settings, size, force)
    clip.status = "converted"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings(short_side=args.short_side, crf=args.crf, fps=args.fps)
    require_tools()
    paths = collect_inputs(args.inputs)
    out = Path(args.out).expanduser()
    prepare_output_directory(out, paths, args.out, args.dry_run)
    depths = pixel_format_depths()
    clips = [Clip(path, name) for path, name in zip(paths, assign_output_names(paths))]
    for clip in clips:
        try:
            process(clip, out, settings, depths, args.dry_run, args.force)
        except ClipError as error:
            clip.status, clip.message = "failed", str(error)
            print(f"{clip.name}: {clip.message}", file=sys.stderr)
            continue
        if not args.json:
            print(clip_line(clip, args.dry_run), flush=True)
    totals = summary(clips, args.dry_run)
    if args.json:
        print(json.dumps({"settings": settings.report(), "summary": totals,
                          "clips": [clip_report(clip, settings) for clip in clips]}, indent=2))
    else:
        print(summary_line(totals))
    return 1 if totals["failed"] else 0
