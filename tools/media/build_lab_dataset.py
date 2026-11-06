#!/usr/bin/env python3
"""Build the playable lab's PRIVATE dataset from exported, v2-tagged, safety-clear Live Photo clips (local, incremental).

A clip is built only when its tag record (<root>/analysis/tags/<uuid>.json) is ``clip-analysis/v2``, analysed, free of
errors, not flagged for review, has ``privacy.sharing_sensitivity`` and a safety verdict of ``clear``.

Output under --dest (private; never git; serve it only to the owner, e.g. as /lab-data/):
  media/<id>.mp4   the validated proxy chain of ``independent_loop_compositor.proxy`` (full to limited range AND the
                   smpte170m to bt709 matrix, rotation baked in, constant 24 fps, 540 px short side), H.264 CRF 27,
                   faststart, and the clip's AUDIO KEPT (AAC mono 64 kb/s) so every panel can play its own sound
  still/<id>.jpg   the real still, long side 1280 (needs ``sips``, macOS only; see below)
  data/clips.json  {"version": 1, "clips": [...]}: id, video, still, duration, width, height, orientation (all of the
                   DISPLAYED clip), has_audio, loudness_db, audio, captured_at, tags, features (incl. grid8)

``id`` is one opaque string: the first 20 hex digits of HMAC-SHA256(<salt>, <Photos uuid>). The salt is a random
secret kept in <root>/analysis/lab-id-salt (mode 0600), so the id is stable for a clip across re-runs and cannot be
turned back into the uuid. clips.json, media/<id>.mp4 and still/<id>.jpg all use it; no uuid appears in any file name
or value. Files in media/ and still/ that no longer belong to a built clip are removed.

``captured_at`` is the original container's creation time and nothing else: NEVER a location. No captions, notes or
reasons are written.

``audio`` is ALWAYS present: {"screened": false} when the clip has no record from screen_audio.py (the lab mutes such
clips by default), otherwise the derived fields only (speech, words, flags, low_confidence), never a transcript.

Stills: converting HEIC to JPEG uses ``sips``. Where it is missing (Linux, CI) one line says that stills were skipped,
clips.json carries an empty ``still`` for those clips (the lab falls back to the video) and the exit code stays 0.

Run:  python3 -m tools.media.build_lab_dataset --root /path/to/live-photos --dest /path/to/lab-data
--root falls back to $SIMVLTANEA_LIVE_PHOTOS_ROOT and --dest to $SIMVLTANEA_LAB_DATA_DIR; there is no default path.
Needs ffmpeg and ffprobe. Exit codes: 0 done, 2 a tool or option is missing (one line, no traceback).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
from fractions import Fraction

from tools.media.private_root import resolve_private_root
from tools.media.tag_clips import SCHEMA_ID
from tools.media.video_geometry import geometry_from_stream, run_ffprobe

ROOT_ENV = "SIMVLTANEA_LIVE_PHOTOS_ROOT"
DEST_ENV = "SIMVLTANEA_LAB_DATA_DIR"
EXIT_MISSING = 2
UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")  # fullmatch only
OPAQUE_ID_RE = re.compile(r"[0-9a-f]{20}")  # fullmatch only
SALT_FILE = ("analysis", "lab-id-salt")
SHORT_SIDE = 540
CRF = 27
PRESET = "veryfast"
FPS = Fraction(24)
STILL_LONG_SIDE = 1280
STILL_EXT = (".heic", ".jpg", ".jpeg", ".png")
TAG_KEYS = ("subjects", "setting", "environment", "time_of_day", "camera", "motion_level", "shot", "palette",
            "mood", "keywords")
FEATURE_KEYS = ("luma", "luma_spread", "saturation", "hue", "motion", "palette")
STILLS_SKIPPED = ("stills skipped: sips not found (macOS only), so still/<id>.jpg was not written; "
                  "clips.json has an empty still for those clips and the lab falls back to the video")


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True)


def proxy_module():
    """The validated proxy recipe (PR #47); imported on use so ``--help`` needs nothing installed."""
    from independent_loop_compositor import proxy
    return proxy


def opaque_ids(root: pathlib.Path):
    """A function mapping a Photos uuid to its stable opaque id, creating the private salt on first use."""
    path = root.joinpath(*SALT_FILE)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(secrets.token_hex(32))
        try:
            os.link(temporary, path)  # never replace a salt another run created meanwhile
        except FileExistsError:
            pass
        temporary.unlink()
    key = bytes.fromhex(path.read_text().strip())
    return lambda uuid: hmac.new(key, uuid.lower().encode(), hashlib.sha256).hexdigest()[:20]


def probe_summary(path: pathlib.Path) -> dict | None:
    """Duration, audio presence, container creation time and displayed geometry; None when unreadable."""
    data = run_ffprobe(path)
    if data is None:
        return None
    full = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
                "-of", "csv=p=0", str(path)])
    streams = (data.get("streams") or [])
    geometry = geometry_from_stream(streams[0]) if streams else None
    fmt = data.get("format") or {}
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {"geometry": geometry, "audio": "audio" in full.stdout, "duration": duration,
            "creation": (fmt.get("tags") or {}).get("creation_time")}


def mean_volume(path: pathlib.Path):
    out = run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "volumedetect",
               "-f", "null", "-"]).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            try:
                return round(float(line.split("mean_volume:")[1].split()[0]), 1)
            except ValueError:
                return None
    return None


def color_grid(path: pathlib.Path, duration: float) -> str | None:
    """8x8 mean-colour map of the middle frame as 64 'rrggbb' triples (384 hex chars): a tiny local summary the crop
    deriver uses to choose windows that blend with their neighbours. Derived from the built clip; no AI, no upload."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(duration, 0.2) / 2:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", "scale=8:8:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    return result.stdout.hex() if result.returncode == 0 and len(result.stdout) == 192 else None


def transcode(source: pathlib.Path, target: pathlib.Path) -> bool:
    """Encode ``source`` with the proxy chain plus audio. FFmpeg autorotates by default (no option needed, so the
    command stays valid on FFmpeg 6.1 and 9)."""
    proxy = proxy_module()
    try:
        facts = proxy.probe_source(source, proxy.pixel_format_depths())
    except proxy.ClipError:
        return False
    if proxy.refusal(facts):
        return False
    size = proxy.target_size(facts.displayed_size, SHORT_SIDE)
    partial = target.with_name(target.name + ".partial.mp4")
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
        "-map", f"0:{facts.stream_index}", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-vf", proxy.filter_graph(facts, size, FPS),
        "-t", f"{facts.duration:.6f}", "-fps_mode", "cfr",
        "-c:v", proxy.ENCODER, "-preset", PRESET, "-profile:v", proxy.PROFILE, "-crf", str(CRF),
        "-pix_fmt", proxy.OUTPUT_PIX_FMT,
        "-color_range", "tv", "-colorspace", proxy.OUTPUT_COLOR, "-color_primaries", proxy.OUTPUT_COLOR,
        "-color_trc", proxy.OUTPUT_COLOR,
        "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "44100",
        "-movflags", "+faststart", "-f", "mp4", str(partial),
    ]
    if run(command).returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        return False
    os.replace(partial, target)
    return True


def convert_still(source: pathlib.Path, target: pathlib.Path) -> bool:
    partial = target.with_name(target.name + ".partial.jpg")
    result = run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", str(STILL_LONG_SIDE),
                  str(source), "--out", str(partial)])
    if result.returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        return False
    os.replace(partial, target)
    return True


def audio_screen(root: pathlib.Path, uuid: str) -> dict:
    """Derived fields only from screen_audio.py, never the transcript; ``{"screened": false}`` without a record."""
    try:
        record = json.loads((root / "analysis" / "audio" / f"{uuid}.json").read_text())
    except (OSError, ValueError):
        return {"screened": False}
    if not isinstance(record, dict) or record.get("screened") is not True:
        return {"screened": False}
    return {"screened": True, "speech": bool(record.get("speech")), "words": int(record.get("words") or 0),
            "flags": [f for f in record.get("flags") or [] if isinstance(f, str)],
            "low_confidence": bool(record.get("low_confidence"))}


def eligible(record) -> dict | None:
    """The analysis of a v2, error-free, clear, review-free tag record; None for anything else."""
    if not isinstance(record, dict) or record.get("schema") != SCHEMA_ID or record.get("error") \
            or record.get("needs_review"):
        return None
    analysis = record.get("analysis")
    if not isinstance(analysis, dict) or not isinstance(analysis.get("safety"), dict) \
            or not isinstance(analysis.get("privacy"), dict):
        return None
    if analysis["safety"].get("verdict") != "clear" or "sharing_sensitivity" not in analysis["privacy"]:
        return None
    return analysis


def write_json(path: pathlib.Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")))
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, default=os.environ.get(ROOT_ENV) or None,
                        help=f"private storage root (outside the checkout, or under var/); default ${ROOT_ENV}")
    parser.add_argument("--dest", type=pathlib.Path, default=os.environ.get(DEST_ENV) or None,
                        help=f"lab dataset directory (private); default ${DEST_ENV}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for value, label, env in ((args.root, "--root", ROOT_ENV), (args.dest, "--dest", DEST_ENV)):
        if value is None:
            print(f"no {label} given and ${env} is not set", file=sys.stderr)
            return EXIT_MISSING
    root, dest = resolve_private_root(args.root), resolve_private_root(args.dest)
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            print(f"{tool} not found on PATH", file=sys.stderr)
            return EXIT_MISSING
    try:
        proxy_module()
    except ImportError:
        print("independent_loop_compositor is not importable; install the repository (pip install -e .)",
              file=sys.stderr)
        return EXIT_MISSING
    can_still = shutil.which("sips") is not None
    for sub in ("media", "still", "data"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    make_id = opaque_ids(root)
    clips, skipped, without_still = [], 0, 0
    seen_ids: set[str] = set()
    for tag_file in sorted((root / "analysis" / "tags").glob("*.json")):
        try:
            record = json.loads(tag_file.read_text())
        except (OSError, ValueError):
            skipped += 1
            continue
        analysis = eligible(record)
        uuid = record.get("uuid") if isinstance(record, dict) else None
        if analysis is None or not isinstance(uuid, str) or not UUID_RE.fullmatch(uuid) or tag_file.stem != uuid:
            skipped += 1
            continue
        clip_id = make_id(uuid)
        folder = root / "originals" / uuid
        mov = folder / f"{uuid}.mov"
        still_source = next((p for p in sorted(folder.glob(f"{uuid}.*")) if p.suffix.lower() in STILL_EXT), None)
        if clip_id in seen_ids or not mov.exists() or still_source is None:
            skipped += 1
            continue
        mp4, jpg = dest / "media" / f"{clip_id}.mp4", dest / "still" / f"{clip_id}.jpg"
        if not mp4.exists() and not transcode(mov, mp4):
            skipped += 1
            continue
        if not jpg.exists() and can_still:
            convert_still(still_source, jpg)
        if not jpg.exists():
            without_still += 1
        built = probe_summary(mp4)
        original = probe_summary(mov)
        if built is None or built["geometry"] is None or original is None:
            mp4.unlink(missing_ok=True)
            skipped += 1
            continue
        seen_ids.add(clip_id)
        geometry = built["geometry"]
        features = record.get("features") or {}
        clips.append({
            "id": clip_id,
            "video": f"media/{clip_id}.mp4",
            "still": f"still/{clip_id}.jpg" if jpg.exists() else "",
            "duration": round(built["duration"], 3),
            "width": geometry["display_width"], "height": geometry["display_height"],
            "orientation": geometry["orientation"],
            "has_audio": built["audio"],
            "loudness_db": mean_volume(mp4) if built["audio"] else None,
            "audio": audio_screen(root, uuid),
            "captured_at": original["creation"],
            "tags": {**{k: analysis.get(k) for k in TAG_KEYS},
                     "people": analysis.get("people"),
                     "privacy": {k: v for k, v in analysis["privacy"].items() if k != "sharing_note"},
                     "safety": {"verdict": analysis["safety"]["verdict"]}},
            "features": {**{k: features.get(k) for k in FEATURE_KEYS},
                         "grid8": color_grid(mp4, built["duration"])},
        })
    for sub, suffix in (("media", ".mp4"), ("still", ".jpg")):
        for path in (dest / sub).iterdir():
            if path.suffix == suffix and OPAQUE_ID_RE.fullmatch(path.stem) and path.stem not in seen_ids:
                path.unlink()
    write_json(dest / "data" / "clips.json", {"version": 1, "clips": clips})
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"lab dataset: {len(clips)} clips, {skipped} skipped, {size / 1e6:.1f} MB")
    if not can_still and without_still:
        print(STILLS_SKIPPED)
    elif without_still:
        print(f"{without_still} clip(s) have no still: the conversion failed; the lab falls back to the video")
    return 0


if __name__ == "__main__":
    sys.exit(main())
