#!/usr/bin/env python3
"""Create lightweight synthetic clips for the clean-clone inaugural demo.

The generated MP4s are engineering fixtures only. They are written beneath the
repository's ignored ``samples/`` lane and are not archival or artist-approved
media.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "samples" / "inaugural"
CLIP_COUNT = 3


def _inside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ValueError("fixture output must remain inside repository")
    return resolved


def build_commands(
    output_dir: Path, *, duration: float = 1.0, size: int = 160
) -> list[list[str]]:
    """Return deterministic FFmpeg commands for the three demo clips."""
    if duration <= 0:
        raise ValueError("duration must be positive")
    if size < 32:
        raise ValueError("size must be at least 32 pixels")
    output_dir = _inside_repo(output_dir)
    commands: list[list[str]] = []
    for index, hue in enumerate((0, 110, 220), start=1):
        target = output_dir / f"inaugural-{index:02d}.mp4"
        commands.append(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={size}x{size}:rate=24:duration={duration:g}",
                "-vf",
                f"hue=h={hue}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                str(target),
            ]
        )
    return commands


def generate(
    output_dir: Path = DEFAULT_OUTPUT, *, duration: float = 1.0, size: int = 160
) -> list[Path]:
    """Generate and return the three local inaugural fixture paths."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to generate inaugural fixtures")
    output_dir = _inside_repo(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = build_commands(output_dir, duration=duration, size=size)
    targets: list[Path] = []
    for command in commands:
        subprocess.run(command, check=True)
        target = Path(command[-1])
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"fixture generation produced no media: {target}")
        targets.append(target)
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--size", type=int, default=160)
    args = parser.parse_args()
    targets = generate(args.output_dir, duration=args.duration, size=args.size)
    relative = _inside_repo(args.output_dir).relative_to(REPO_ROOT)
    print(f"inaugural fixture ok: {len(targets)} clips at {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
