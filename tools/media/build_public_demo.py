#!/usr/bin/env python3
"""Build a PUBLIC demo package (small proxies + manifest) from already-exported, already-tagged Live Photos clips.

The owner decided the library is public as the demo. This tool reads the private root (read-only, never written)
and writes a separate output directory:

  <out>/clips/<sha256-12 of the proxy bytes>.mp4   content-addressed; no original uuid or file name is public
  <out>/manifest.json                              schema "simvltanea.public-demo/1"

A clip is selected only when its ``analysis/tags/<uuid>.json`` passes every exclusion rule below. Each rule is a
named option with a safe default; unknown or missing facts exclude the clip.

  needs_review            tag record says a human must look                       (--exclude-needs-review)
  no_analysis             no usable analysis block (model error, refusal)         (always)
  unsafe                  safety verdict is not "clear", or categories listed,    (--exclude-unsafe)
                          or the safety block is missing/unknown
  document_or_screen      privacy flag is true or unknown                         (--exclude-document-or-screen)
  license_plate           privacy flag is true or unknown                         (--exclude-license-plate)
  location_identifiable   privacy flag is true or unknown                         (--exclude-location-identifiable)
  readable_text           privacy flag is true or unknown                         (--exclude-readable-text)
  missing_original        no original video on disk for the record                (always)

Audio: ``--audio keep`` (default; the owner decided people and their voices may be published) writes AAC 64k
mono; ``mute`` writes no audio stream at all.

Proxies are H.264 yuv420p, at most 480 px on the long side AFTER the display rotation (FFmpeg's default
autorotate applies it; no ``-autorotate`` option is used, so FFmpeg 6.1 works), +faststart, with global,
stream and chapter metadata dropped. Every output is re-probed with ffprobe and fails closed on any doubt.

Output is counts only: no uuid, caption, file name or path of an individual clip is ever printed.

Run:  python3 -m tools.media.build_public_demo --root /path/to/live-photos --out /path/outside/repo --dry-run
Exit codes: 0 ok, 2 bad arguments/ffmpeg missing, 3 verification failed (nothing published), 5 local file error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from tools.media import tag_clips
from tools.media.private_root import inside_photos_library, resolve_private_root
from tools.media.video_geometry import display_size, orientation_for, stream_rotation
from tools.paths import REPO_ROOT, VAR_DIR

SCHEMA = "simvltanea.public-demo/1"
MAX_LONG_SIDE = 480
CRF = 28
MAX_KEYWORDS = 5
ID_LENGTH = 12
KEYWORD_RE = re.compile(r"[a-z][a-z0-9 \-]{0,31}")  # a short plain word; anything else is dropped from the manifest
EXIT_VERIFY_FAILED = 3
EXIT_IO_ERROR = 5
FFMPEG_TIMEOUT = 600
HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
# What the mp4 muxer writes by itself under bitexact. Any other tag (creation_time, location, encoder, make, ...) fails.
ALLOWED_FORMAT_TAGS = frozenset({"major_brand", "minor_version", "compatible_brands"})
ALLOWED_STREAM_TAGS = {"handler_name": frozenset({"VideoHandler", "SoundHandler"}),
                       "language": frozenset({"und"}),
                       "vendor_id": frozenset({"[0][0][0][0]"}),
                       "encoder": frozenset({"Lavc libx264", "Lavc aac"})}  # bitexact form: names no version or host
FORBIDDEN_BYTES = (b"\xa9xyz", b"mdta", b"com.apple", b"creation", b"location")  # long markers only: short ones occur by chance in video data

# Exclusion reasons in the order they are tested; a clip is counted under the first that applies.
REASONS = ("unreadable_tags", "no_analysis", "needs_review", "unsafe", "document_or_screen", "license_plate",
           "location_identifiable", "readable_text", "missing_original")
PRIVACY_FLAGS = ("document_or_screen", "license_plate", "location_identifiable", "readable_text")


class Failure(Exception):
    """A clip or output that cannot be used. The message never holds names or paths."""


class VerificationError(Exception):
    """An output that did not pass stage-time verification. Fatal: the run publishes nothing."""


# -- selection -----------------------------------------------------------------

def load_record(path: pathlib.Path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def exclusion_reasons(record, options) -> list[str]:
    """Every reason (from ``REASONS``) that excludes this tag record; empty when it may be published."""
    if record is None:
        return ["unreadable_tags"]
    analysis = record.get("analysis")
    if not isinstance(analysis, dict):
        return ["no_analysis"]
    reasons = []
    if options.exclude_needs_review and record.get("needs_review") is not False:  # true, missing or odd => exclude
        reasons.append("needs_review")
    safety = analysis.get("safety")
    benign = (isinstance(safety, dict) and safety.get("verdict") == "clear"
              and isinstance(safety.get("categories"), list) and not safety["categories"])
    if options.exclude_unsafe and not benign:
        reasons.append("unsafe")
    privacy = analysis.get("privacy")
    for flag in PRIVACY_FLAGS:
        if not getattr(options, f"exclude_{flag}"):
            continue
        value = privacy.get(flag) if isinstance(privacy, dict) else None
        if value is not False:  # true, missing, null or any other value => exclude
            reasons.append(flag)
    return reasons


def original_path(root: pathlib.Path, uuid: str) -> pathlib.Path | None:
    candidates = []
    try:
        receipt = tag_clips.read_receipt(root, uuid)
        candidates.append(tag_clips.original_video(root, uuid, receipt))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    candidates.append(root / "originals" / uuid / f"{uuid}.mov")
    return next((path for path in candidates if path.is_file()), None)


def select(root: pathlib.Path, options) -> tuple[list[tuple[str, pathlib.Path, dict]], dict]:
    """(selected clips as (uuid, original, record), counts). Counts hold no identifiers."""
    counts = {"examined": 0, "selected": 0, "excluded": 0,
              "excluded_by_reason": {reason: 0 for reason in REASONS},
              "flag_hits": {reason: 0 for reason in REASONS}}
    selected = []
    for tag_path in sorted((root / "analysis" / "tags").glob("*.json")):
        uuid = tag_path.stem
        if not tag_clips.UUID_RE.fullmatch(uuid):
            continue
        counts["examined"] += 1
        record = load_record(tag_path)
        reasons = exclusion_reasons(record, options)
        original = original_path(root, uuid)
        if not reasons and original is None:
            reasons = ["missing_original"]
        if reasons:
            counts["excluded"] += 1
            counts["excluded_by_reason"][reasons[0]] += 1
            for reason in reasons:
                counts["flag_hits"][reason] += 1
            continue
        selected.append((uuid, original, record))
    if options.limit:
        selected = selected[: options.limit]
    counts["selected"] = len(selected)
    return selected, counts


# -- probing and encoding --------------------------------------------------------

def run_ffprobe(path: pathlib.Path) -> dict:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-show_chapters", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
        data = json.loads(proc.stdout or "{}") if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        data = None
    if not isinstance(data, dict):
        raise Failure("unreadable_media")
    return data


def positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def target_size(width: int, height: int) -> tuple[int, int]:
    """Even size with the long side at most ``MAX_LONG_SIDE`` (never upscaled), aspect kept."""
    scale = min(1.0, MAX_LONG_SIDE / max(width, height))
    return (max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2))


def plan_source(original: pathlib.Path) -> tuple[tuple[int, int], float]:
    """(output size, source duration) from the original; raises Failure for what must not be encoded."""
    data = run_ffprobe(original)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    if video is None:
        raise Failure("no_video")
    try:
        width, height = int(video["width"]), int(video["height"])
    except (KeyError, TypeError, ValueError):
        raise Failure("no_size") from None
    pix_fmt = str(video.get("pix_fmt") or "")
    if video.get("color_transfer") in HDR_TRANSFERS or re.search(r"(10|12|16)(le|be)?$", pix_fmt):
        raise Failure("hdr_or_high_bit_depth")  # tone mapping is out of scope; never publish a washed-out proxy
    aspect = str(video.get("sample_aspect_ratio") or "1:1")
    if aspect not in ("1:1", "0:1", "N/A"):
        raise Failure("non_square_pixels")
    width, height = display_size(width, height, stream_rotation(video))
    duration = (positive_float(video.get("duration")) or positive_float((data.get("format") or {}).get("duration")))
    if not duration:
        raise Failure("no_duration")
    return target_size(width, height), duration


def encode_command(original: pathlib.Path, destination: pathlib.Path, size: tuple[int, int], audio: str) -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(original),
               "-map", "0:v:0"]
    command += ["-an"] if audio == "mute" else ["-map", "0:a:0?"]
    command += ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
                "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1",
                "-vf", f"scale={size[0]}:{size[1]}:flags=lanczos:out_range=tv,format=yuv420p,setsar=1",
                "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-crf", str(CRF),
                "-maxrate", "1000k", "-bufsize", "2000k", "-pix_fmt", "yuv420p"]
    if audio == "keep":
        command += ["-c:a", "aac", "-b:a", "64k", "-ac", "1"]
    command += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
                "-movflags", "+faststart", "-f", "mp4", str(destination)]
    return command


def encode(original: pathlib.Path, destination: pathlib.Path, size: tuple[int, int], audio: str) -> None:
    try:
        proc = subprocess.run(encode_command(original, destination, size, audio), capture_output=True, text=True,
                              timeout=FFMPEG_TIMEOUT)
    except subprocess.SubprocessError:
        raise Failure("encode_timeout") from None
    if proc.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        raise Failure("encode_failed")  # stderr may hold paths: not echoed


def top_level_boxes(path: pathlib.Path) -> list[str]:
    boxes = []
    with path.open("rb") as handle:
        while True:
            header = handle.read(8)
            if len(header) < 8:
                return boxes
            size, kind = int.from_bytes(header[:4], "big"), header[4:8].decode("latin-1")
            offset = 8
            if size == 1:
                size, offset = int.from_bytes(handle.read(8), "big"), 16
            boxes.append(kind)
            if size == 0 or size < offset:
                return boxes
            handle.seek(size - offset, os.SEEK_CUR)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_output(path: pathlib.Path, audio: str) -> dict:
    """Re-probe a finished proxy and return its facts; raise VerificationError on any doubt (fail closed)."""
    try:
        data = run_ffprobe(path)
    except Failure:
        raise VerificationError("unreadable output") from None
    streams = data.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(videos) + len(audios) != len(streams):
        raise VerificationError("unexpected stream set")
    video = videos[0]
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise VerificationError("not h264 yuv420p")
    if audio == "mute" and audios:
        raise VerificationError("audio present under --audio mute")
    if audio == "keep" and (len(audios) > 1 or any(a.get("codec_name") != "aac" or a.get("channels") != 1
                                                   for a in audios)):
        raise VerificationError("audio is not a single aac mono stream")
    if data.get("chapters"):
        raise VerificationError("chapters present")
    for stream in streams:
        if stream.get("side_data_list"):
            raise VerificationError("stream side data present (rotation or other)")
        if stream_rotation(stream):
            raise VerificationError("rotation left in output")
        for key, value in (stream.get("tags") or {}).items():
            if value not in ALLOWED_STREAM_TAGS.get(key, ()):
                raise VerificationError("unexpected stream tag")
    for key in (data.get("format") or {}).get("tags") or {}:
        if key not in ALLOWED_FORMAT_TAGS:
            raise VerificationError("unexpected container tag")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if min(width, height) < 2 or max(width, height) > MAX_LONG_SIDE or width % 2 or height % 2:
        raise VerificationError("bad size")
    duration = positive_float(video.get("duration")) or positive_float((data.get("format") or {}).get("duration"))
    if not duration:
        raise VerificationError("no duration")
    boxes = top_level_boxes(path)
    if "moov" not in boxes or "mdat" not in boxes or boxes.index("moov") > boxes.index("mdat"):
        raise VerificationError("not faststart")
    blob = path.read_bytes()
    if any(marker in blob for marker in FORBIDDEN_BYTES):
        raise VerificationError("metadata marker in file bytes")
    if blob.count(b"ilst") != blob.count(b"\x00\x00\x00\x08ilst"):  # the muxer's empty ilst (8 bytes) is fine
        raise VerificationError("non-empty metadata item list")
    return {"width": width, "height": height, "orientation": orientation_for(width, height),
            "duration_seconds": round(duration, 3), "bytes": len(blob)}


# -- manifest ----------------------------------------------------------------------

def public_tags(analysis: dict) -> dict:
    """The only tag fields that reach the manifest: <=5 keywords, mood, shot, palette (controlled vocabularies)."""
    raw = analysis.get("keywords")
    keywords = [k for k in (raw[:MAX_KEYWORDS] if isinstance(raw, list) else [])
                if isinstance(k, str) and KEYWORD_RE.fullmatch(k)]
    mood = analysis.get("mood")
    palette = analysis.get("palette")
    shot = analysis.get("shot")
    return {"keywords": keywords,
            "mood": [m for m in mood if m in tag_clips.MOODS] if isinstance(mood, list) else [],
            "shot": shot if shot in tag_clips.SHOTS else None,
            "palette": [c for c in palette if c in tag_clips.COLORS] if isinstance(palette, list) else []}


def write_atomic(path: pathlib.Path, data: bytes) -> None:
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".partial")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(name, path)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


# -- driver --------------------------------------------------------------------------

def resolve_out(value: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    out = pathlib.Path(os.path.realpath(os.path.expanduser(value)))
    checkout, var_dir = pathlib.Path(os.path.realpath(REPO_ROOT)), pathlib.Path(os.path.realpath(VAR_DIR))
    inside = lambda path, parent: path == parent or parent in path.parents  # noqa: E731
    if inside(out, checkout) and not inside(out, var_dir):
        raise SystemExit("--out inside the checkout must stay under var/ (ignored by Git).")
    if inside(out, root) or inside(root, out):
        raise SystemExit("--out and --root must not contain one another: the private root is read-only input.")
    if inside_photos_library(out):
        raise SystemExit("Refusing to write inside a Photos library package.")
    return out


def build(args) -> int:
    root = resolve_private_root(args.root)
    out = resolve_out(args.out, root)
    selected, counts = select(root, args)
    summary = {"examined": counts["examined"], "selected": counts["selected"], "excluded": counts["excluded"],
               "excluded_by_reason": counts["excluded_by_reason"], "flag_hits_not_exclusive": counts["flag_hits"],
               "audio": args.audio}
    if args.dry_run:
        print(json.dumps({"dry_run": True, **summary}, indent=1))
        return 0
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg and ffprobe are required.", file=sys.stderr)
        return 2
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(dir=out, prefix=".work-"))
    entries, encoded, reused, failed = [], 0, 0, {}
    try:
        for _uuid, original, record in selected:
            temporary = work / "proxy.mp4"
            temporary.unlink(missing_ok=True)
            try:
                size, _duration = plan_source(original)
                encode(original, temporary, size, args.audio)
            except Failure as failure:
                failed[str(failure)] = failed.get(str(failure), 0) + 1
                continue
            clip_id = sha256_file(temporary)[:ID_LENGTH]
            final = clips_dir / f"{clip_id}.mp4"
            if final.exists():
                if sha256_file(final) != sha256_file(temporary):
                    raise VerificationError("id collision with different bytes")
                reused += 1
            else:
                os.replace(temporary, final)
                encoded += 1
            entries.append({"id": clip_id, "file": f"clips/{clip_id}.mp4", "_analysis": record["analysis"]})
        manifest_clips = {}
        for entry in entries:  # re-probe every output, new or pre-existing
            facts = verify_output(out / entry["file"], args.audio)
            if sha256_file(out / entry["file"])[:ID_LENGTH] != entry["id"]:
                raise VerificationError("content hash does not match id")
            manifest_clips[entry["id"]] = {"id": entry["id"], "file": entry["file"], **facts,
                                           "tags": public_tags(entry["_analysis"])}
    except VerificationError:
        shutil.rmtree(work, ignore_errors=True)
        print("VERIFICATION FAILED: no manifest written; do not publish this directory.", file=sys.stderr)
        return EXIT_VERIFY_FAILED
    finally:
        shutil.rmtree(work, ignore_errors=True)
    clips = [manifest_clips[key] for key in sorted(manifest_clips)]
    document = {"schema": SCHEMA, "clips": clips}
    write_atomic(out / "manifest.json", (json.dumps(document, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    listed = {f"{clip['id']}.mp4" for clip in clips}
    orphans = sum(1 for path in clips_dir.glob("*.mp4") if path.name not in listed)
    boomerang_count = 0
    if args.boomerang:
        for clip in clips:
            src = clips_dir / f"{clip['id']}.mp4"
            dst = clips_dir / f"{clip['id']}.boomerang.mp4"
            if not dst.exists():
                # reuse lab dataset helper if available
                try:
                    from tools.media.build_lab_dataset import build_boomerang
                    ok = build_boomerang(src, dst, args.audio == "keep")
                except Exception:
                    ok = False
                if ok:
                    boomerang_count += 1
            else:
                boomerang_count += 1
    print(json.dumps({**summary, "encoded_new": encoded, "reused_existing": reused, "failed_by_reason": failed,
                      "in_manifest": len(clips), "orphan_files_not_in_manifest": orphans,
                      "boomerang": boomerang_count if args.boomerang else 0}, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, required=True, help="private Live Photos root (read-only input)")
    parser.add_argument("--out", type=pathlib.Path, required=True,
                        help="public output directory (outside the checkout, or under var/)")
    parser.add_argument("--limit", type=int, default=0, help="publish at most N selected clips (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="print selection counts only; encode and write nothing")
    parser.add_argument("--audio", choices=("keep", "mute"), default="keep",
                        help="keep (default): AAC 64k mono; mute: no audio stream")
    parser.add_argument("--boomerang", action="store_true",
                        help="also build forward-reverse (boomerang) MP4s for each clip")
    toggle = argparse.BooleanOptionalAction
    parser.add_argument("--exclude-needs-review", action=toggle, default=True)
    parser.add_argument("--exclude-unsafe", action=toggle, default=True,
                        help="exclude unless safety is verdict clear with no categories")
    parser.add_argument("--exclude-document-or-screen", action=toggle, default=True)
    parser.add_argument("--exclude-license-plate", action=toggle, default=True)
    parser.add_argument("--exclude-location-identifiable", action=toggle, default=True)
    parser.add_argument("--exclude-readable-text", action=toggle, default=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 0:
        raise SystemExit("--limit must be >= 0.")
    try:
        return build(args)
    except OSError as exc:  # the message and filename can hold private paths: type only
        print(f"local file error ({type(exc).__name__}).", file=sys.stderr, flush=True)
        return EXIT_IO_ERROR


if __name__ == "__main__":
    sys.exit(main())
