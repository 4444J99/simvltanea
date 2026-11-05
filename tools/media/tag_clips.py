#!/usr/bin/env python3
"""Tag and safety-screen exported Live Photo clips with Claude vision (Anthropic Batch API, 50% price).

For each exported clip this sends THREE downscaled still frames (start / middle / end of the VIDEO stream, long side
--frame-px, JPEG) plus a fixed instruction to the Anthropic API, and stores a private per-clip
analysis. Nothing is sent unless you pass --confirm-upload. No names are requested or stored; the
model is told never to identify people. Local features (palette, luma, saturation, motion) are
computed on this machine and never uploaded.

Credentials use the SDK's standard resolution (ANTHROPIC_API_KEY). On macOS you may instead pass
--keychain-service NAME to read the key from a Keychain item. A key is never printed.

Layout under --root (private; never committed; may live outside the checkout):
  originals/<uuid>/.done                written by export_photos_album.py
  analysis/frames/<uuid>/f{0,1,2}.jpg   temporary; deleted once the clip is tagged
  analysis/features/<uuid>.json         local deterministic features (no API)
  analysis/failed/<uuid>.json           clip whose frames could not be made; never retried (delete to retry)
  analysis/batches/<batch>.json         which clips went into which batch
  analysis/tags/<uuid>.json             final per-clip record (analysis + safety + features + cost)
  analysis/tags.jsonl                   append-only copy of the above
  analysis/ledger.jsonl                 one line per collected batch with the cost estimate

Commands: prepare | submit | collect | run | report
`collect --pending` collects every batch that has no line in the ledger yet. `submit` and `run` never
send a clip that sits in such a batch, so re-running after an interrupted `run` cannot upload twice;
`run` also collects those pending batches. Exit codes: 0 ok, 5 a local file error (type only, no path).

Run:  python3 -m tools.media.tag_clips run --root /path/to/live-photos --dry-run
The model-facing pieces need the optional extra: python3 -m pip install -e ".[analysis]"
"""

import argparse
import base64
import functools
import json
import math
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Literal

from tools.media.private_root import resolve_private_root

SCHEMA_ID = "clip-analysis/v2"  # v2: privacy.sharing_sensitivity is separate from the safety verdict
UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")  # fullmatch only
BATCH_ID_RE = re.compile(r"[A-Za-z0-9_]+")  # fullmatch only
MAX_FRAME_PX = 1024  # frames are thumbnails; the cap keeps full-resolution images from being uploaded
DEFAULT_BATCH_SIZE = 200  # a smaller batch is a smaller upload that can be lost without being recorded
EXIT_IO_ERROR = 5
# $ per 1M tokens (input, output); batch pricing is 50% of these.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}
FRAME_FRACTIONS = (0.1, 0.5, 0.9)

# Controlled vocabularies. They are plain tuples so they can be used without the SDK; the
# pydantic schema built from them is created lazily by clip_analysis_model().
SUBJECTS = (
    "face", "person", "group", "child", "animal", "pet", "bird", "insect", "tree", "plant", "flower",
    "grass", "sky", "clouds", "sun", "water", "waves", "fire", "snow", "mountain", "building", "interior",
    "street", "vehicle", "food", "drink", "screen", "text", "document", "art", "instrument", "clothing",
    "hands", "crowd", "light_effect", "reflection", "shadow", "pattern", "fireworks",
)
COLORS = ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "brown", "black", "white", "gray", "gold")
MOODS = ("calm", "joyful", "tender", "energetic", "melancholic", "eerie", "playful", "serene", "chaotic", "intimate")
SAFETY_CATEGORIES = ("nudity", "sexual", "violence", "injury", "weapons", "drugs", "hate", "self_harm",
                     "minors_sensitive", "distress", "other")
SETTINGS = ("indoor", "outdoor", "mixed", "unclear")
ENVIRONMENTS = ("nature", "urban", "domestic", "workplace", "transit", "event", "studio", "unclear")
TIMES_OF_DAY = ("day", "golden_hour", "dusk", "night", "artificial_light", "unclear")
CAMERAS = ("locked", "handheld", "pan", "tilt", "zoom", "tracking", "unclear")
MOTION_LEVELS = ("still", "subtle", "moderate", "intense")
SHOTS = ("close_up", "medium", "wide")
VERDICTS = ("clear", "review", "exclude")
SHARING_LEVELS = ("low", "moderate", "high")

PROMPT = """These three frames (start, middle, end) come from one short looping video clip (a Live Photo) in a personal archive. Describe it for a generative video-composition system that picks loops which feel related to each other.

Rules:
- Use only the allowed vocabulary values. Prefer the most prominent subjects first.
- Describe people only as present or absent, how many, and whether faces are visible. Never identify, name, or guess who anyone is.
- Do not transcribe any readable text, numbers, or addresses; only flag that they are visible.
- Safety asks only: is there anything BAD in this clip? Ordinary personal and family footage is "clear": selfies, portraits, people sleeping or relaxing, everyday swimwear or a bare chest, tattoos, parties, fireworks and pyrotechnics, tools. Use "review" only if the frames may show: nudity or sexual content beyond ordinary swimwear, graphic violence or visible injury or blood, a weapon being brandished or used, illegal drugs or paraphernalia, hate symbols, self-harm, a child in a potentially sensitive context (undressed, bathing), or visible distress or a medical emergency. Use "exclude" only for clearly explicit or graphic material. List the matching categories (never "other" just because footage is personal).
- Being private or personal is NOT a safety concern. Record how private the moment is only in privacy.sharing_sensitivity (low = public-ish scenes; moderate = ordinary personal moments; high = intimate or vulnerable moments) with a short note.
- The caption must be one plain factual sentence."""

INSTALL_HINT = 'Install the optional analysis extra first: python3 -m pip install -e ".[analysis]"'


@functools.cache
def clip_analysis_model():
    """Build (once) and return the pydantic ``ClipAnalysis`` schema; needs the SDK's pydantic."""
    try:
        from pydantic import BaseModel, Field
    except ImportError:
        raise SystemExit(f"pydantic is not installed. {INSTALL_HINT}") from None

    class People(BaseModel):
        count: Literal["0", "1", "2-3", "4+"]
        faces_visible: bool
        minors_apparent: bool = Field(description="True if anyone appears to be a child. Used only to protect privacy.")

    class PrivacyFlags(BaseModel):
        readable_text: bool
        license_plate: bool
        document_or_screen: bool
        location_identifiable: bool
        sharing_sensitivity: Literal[SHARING_LEVELS] = Field(
            description="How private the moment is if it were ever shared. Separate from safety: a selfie or a "
                        "sleeping person is personal (moderate/high) but not unsafe.")
        sharing_note: str = Field(description="One short sentence; empty when low.")

    class Safety(BaseModel):
        verdict: Literal[VERDICTS]
        categories: list[Literal[SAFETY_CATEGORIES]]
        reason: str = Field(description="One short sentence; empty if clear.")

    class ClipAnalysis(BaseModel):
        subjects: list[Literal[SUBJECTS]] = Field(description="Up to 8, most prominent first.")
        setting: Literal[SETTINGS]
        environment: Literal[ENVIRONMENTS]
        time_of_day: Literal[TIMES_OF_DAY]
        camera: Literal[CAMERAS]
        motion_level: Literal[MOTION_LEVELS]
        shot: Literal[SHOTS]
        palette: list[Literal[COLORS]] = Field(description="Up to 3 dominant colors.")
        mood: list[Literal[MOODS]] = Field(description="Up to 2.")
        caption: str = Field(description="One factual sentence. Never name or identify any person.")
        keywords: list[str] = Field(description="Up to 6 lowercase nouns or adjectives.")
        people: People
        privacy: PrivacyFlags
        safety: Safety

    return ClipAnalysis


def import_anthropic():
    try:
        import anthropic
    except ImportError:
        raise SystemExit(f"The anthropic SDK is not installed. {INSTALL_HINT}") from None
    return anthropic


def load_keychain_key(service: str) -> str:
    """Read an API key from the macOS Keychain. The key and the tool's output are never printed."""
    try:
        proc = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise SystemExit("Could not run the macOS 'security' tool to read the Keychain item.") from None
    key = proc.stdout.strip()
    if proc.returncode != 0 or not key:
        raise SystemExit(f"No usable API key in Keychain item '{service}'.")
    return key


def make_client(keychain_service: str | None = None):
    """Anthropic client: standard SDK credential resolution, or an explicit Keychain item."""
    anthropic = import_anthropic()
    options = {"max_retries": 3, "timeout": 300.0}
    if keychain_service:
        options["api_key"] = load_keychain_key(keychain_service)
    return anthropic.Anthropic(**options)


def dirs(root: pathlib.Path, create: bool = True) -> dict[str, pathlib.Path]:
    base = root / "analysis"
    paths = {name: base / name for name in ("frames", "features", "batches", "tags", "failed")}
    if create:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
    paths["base"] = base
    return paths


def write_json(path: pathlib.Path, value: dict, **kwargs) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, **kwargs), encoding="utf-8")
    temporary.replace(path)


def ledger_batches(root: pathlib.Path) -> set[str]:
    """Batch ids that have a line in ``analysis/ledger.jsonl`` (collected). Unreadable lines are skipped."""
    ledger = root / "analysis" / "ledger.jsonl"
    done: set[str] = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["batch"])
            except (ValueError, KeyError, TypeError):
                continue
    return done


def pending_batches(root: pathlib.Path) -> list[str]:
    """Batch ids recorded under ``analysis/batches/`` that have no ledger line yet, in name order."""
    collected = ledger_batches(root)
    return [path.stem for path in sorted((root / "analysis" / "batches").glob("*.json"))
            if BATCH_ID_RE.fullmatch(path.stem) and path.stem not in collected]


def pending_uuids(root: pathlib.Path) -> set[str]:
    """Clips already uploaded in a batch that has not been collected."""
    uuids: set[str] = set()
    for batch_id in pending_batches(root):
        try:
            meta = json.loads((root / "analysis" / "batches" / f"{batch_id}.json").read_text(encoding="utf-8"))
            uuids.update(u for u in meta["uuids"] if isinstance(u, str))
        except (ValueError, KeyError, TypeError):
            raise SystemExit(f"Batch record {batch_id} is unreadable; fix or remove it before submitting "
                             "(its clips may already have been uploaded).") from None
    return uuids


def ready_clips(root: pathlib.Path) -> list[str]:
    """UUIDs with an export receipt, no final tag record, no failed marker and no upload waiting.

    A clip with a marker in ``analysis/failed/`` is never retried automatically; delete the marker to retry.
    """
    tags = root / "analysis" / "tags"
    failed = root / "analysis" / "failed"
    waiting = pending_uuids(root)
    return [receipt.parent.name for receipt in sorted((root / "originals").glob("*/.done"))
            if UUID_RE.fullmatch(receipt.parent.name) and receipt.parent.name not in waiting
            and not (tags / f"{receipt.parent.name}.json").exists()
            and not (failed / f"{receipt.parent.name}.json").exists()]


def read_receipt(root: pathlib.Path, uuid: str) -> dict:
    return json.loads((root / "originals" / uuid / ".done").read_text(encoding="utf-8"))


class ClipUnusable(Exception):
    """A clip whose frames or features cannot be produced. The message never holds names or paths."""

    def __init__(self, attempts: int = 0):
        super().__init__("frame_extraction_failed")
        self.attempts = attempts


def parse_frame_rate(text) -> float | None:
    """``"15/2"`` -> 7.5; ``"0/0"`` and anything unreadable -> None."""
    try:
        numerator, _, denominator = str(text).partition("/")
        rate = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def probe_video(mov: pathlib.Path) -> tuple[int | None, float | None]:
    """(frame count, duration in seconds) of the VIDEO stream; None for what ffprobe cannot tell.

    The container duration also covers audio, which can be longer than the picture, so it is only used
    when the stream has no duration of its own. ``nb_frames`` can be ``N/A``; then it is estimated from
    the duration and the average frame rate.
    """
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=duration,nb_frames,avg_frame_rate:format=duration", "-of", "json", str(mov)],
            capture_output=True, text=True)
        facts = json.loads(proc.stdout) if proc.returncode == 0 else {}
        stream = (facts.get("streams") or [{}])[0]
        container = facts.get("format") or {}
    except (OSError, ValueError, AttributeError, TypeError, IndexError):
        return None, None

    def positive_float(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    duration = positive_float(stream.get("duration")) or positive_float(container.get("duration"))
    try:
        count = int(stream["nb_frames"])
    except (KeyError, TypeError, ValueError):  # missing or "N/A"
        count = 0
    if count < 1:
        rate = parse_frame_rate(stream.get("avg_frame_rate"))
        count = max(1, round(duration * rate)) if duration and rate else 0
    return (count or None), duration


def pick_frame_indices(count: int) -> list[int]:
    """Frame numbers at about 10 / 50 / 90 % of ``count`` frames; a short clip repeats its nearest frames."""
    return [min(count - 1, int(count * fraction)) for fraction in FRAME_FRACTIONS]


def extract(root: pathlib.Path, uuid: str, px: int) -> list[pathlib.Path]:
    """Three downscaled JPEG frames (start / middle / end) of the clip's VIDEO stream via ffmpeg.

    Frames are chosen by index among the video's own frames, so a clip whose audio outlasts its picture
    cannot make a position fall off the end. A position that yields no image falls back to the last
    decodable frame, then to the nearest frame already written. Raises ``ClipUnusable`` (no names, no
    paths) when no frame can be produced at all.
    """
    d = dirs(root)
    receipt = read_receipt(root, uuid)
    mov = root / "originals" / uuid / pathlib.Path(receipt["video"]["name"]).name
    out_dir = d["frames"] / uuid
    shutil.rmtree(out_dir, ignore_errors=True)  # never reuse frames of another size or a partial earlier file
    out_dir.mkdir(parents=True)
    count, duration = probe_video(mov)
    scale = f"scale='if(gt(iw,ih),{px},-2)':'if(gt(iw,ih),-2,{px})'"
    attempts = 0

    def grab(out: pathlib.Path, before_input: list[str], video_filter: str, after_input: list[str]) -> bool:
        nonlocal attempts
        attempts += 1
        out.unlink(missing_ok=True)
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *before_input, "-i", str(mov), "-map", "0:v:0", *after_input,
             "-vf", video_filter, "-q:v", "4", str(out)],
            capture_output=True, text=True)
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return True
        out.unlink(missing_ok=True)
        return False

    if count:
        wanted = [(["-fps_mode", "passthrough", "-frames:v", "1"], f"select='eq(n,{k})',{scale}")
                  for k in pick_frame_indices(count)]
    else:  # no frame count: fall back to time positions inside the video (or the receipt's duration)
        span = duration or max(float(receipt["video"].get("duration") or 1.0), 0.2)
        wanted = [(["-frames:v", "1", "-ss", f"{span * fraction:.3f}"], scale) for fraction in FRAME_FRACTIONS]
    last_resort = ["-update", "1"]  # decodes every frame into one file: the last decodable frame is what stays
    frames: list[pathlib.Path | None] = []
    for index, (options, video_filter) in enumerate(wanted):
        out = out_dir / f"f{index}.jpg"
        got = (grab(out, [], video_filter, options)
               or grab(out, ["-sseof", "-0.2"], scale, ["-frames:v", "1"])
               or grab(out, [], scale, last_resort))
        frames.append(out if got else None)
    written = [i for i, frame in enumerate(frames) if frame is not None]
    if not written:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise ClipUnusable(attempts)
    for index, frame in enumerate(frames):
        if frame is None:  # reuse the nearest frame that exists
            nearest = min(written, key=lambda i: (abs(i - index), i))
            shutil.copyfile(out_dir / f"f{nearest}.jpg", out_dir / f"f{index}.jpg")
    return [out_dir / f"f{index}.jpg" for index in range(len(wanted))]


def local_features(frames: list[pathlib.Path], receipt: dict) -> dict:
    """Deterministic features that need no API (also usable client-side for any visitor's loops)."""
    from PIL import Image

    def pixels(image):  # Pillow 13 deprecates getdata() in favour of get_flattened_data()
        return list(image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata())

    def mean(values):
        return sum(values) / len(values)

    small = []
    for frame in frames:
        with Image.open(frame) as image:
            small.append(image.convert("RGB").resize((64, 64)))
    lumas = [pixels(image.convert("L")) for image in small]
    motion = mean([mean([abs(a - b) for a, b in zip(lumas[i], lumas[i + 1])]) / 255 for i in range(len(lumas) - 1)])
    hue_img, sat_img, _value_img = small[1].convert("HSV").split()
    hues, sats = pixels(hue_img), pixels(sat_img)
    x = sum(math.cos(h / 255 * 2 * math.pi) * s for h, s in zip(hues, sats))
    y = sum(math.sin(h / 255 * 2 * math.pi) * s for h, s in zip(hues, sats))
    with Image.open(frames[1]) as image:
        quant = image.convert("RGB").resize((96, 96)).quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    palette_bytes = quant.getpalette()[:15]
    colors = sorted(quant.getcolors(), reverse=True)
    palette = [{"hex": "#%02x%02x%02x" % tuple(palette_bytes[idx * 3: idx * 3 + 3]), "share": round(count / (96 * 96), 3)}
               for count, idx in colors]
    video = receipt["video"]
    frame_means = [mean(luma) for luma in lumas]
    return {
        "luma": round(mean(frame_means) / 255, 4),
        "luma_spread": round((max(frame_means) - min(frame_means)) / 255, 4),
        "saturation": round(mean(sats) / 255, 4),
        "hue": round((math.atan2(y, x) / (2 * math.pi)) % 1.0, 4),
        "motion": round(motion, 4),
        "palette": palette,
        "duration": video.get("duration"),
        "width": video.get("width"),
        "height": video.get("height"),
        "orientation": "portrait" if (video.get("height") or 0) > (video.get("width") or 0) else "landscape",
    }


def require_pillow() -> None:
    try:
        from PIL import Image  # noqa: F401 - only the import is checked
    except ImportError:
        raise SystemExit(f"Pillow is not installed. {INSTALL_HINT}") from None


def mark_failed(root: pathlib.Path, uuid: str, attempts: int) -> None:
    """Record that a clip is unusable: only the uuid, a fixed error code and the attempt count."""
    d = dirs(root)
    shutil.rmtree(d["frames"] / uuid, ignore_errors=True)
    (d["features"] / f"{uuid}.json").unlink(missing_ok=True)
    write_json(d["failed"] / f"{uuid}.json",
               {"uuid": uuid, "error": "frame_extraction_failed", "attempts": max(attempts, 1)}, indent=1)


def prepare_clip(root: pathlib.Path, uuid: str, px: int) -> None:
    """Frames and local features of one clip; raises ``ClipUnusable`` when they cannot be made.

    Only per-clip problems become ``ClipUnusable`` (an undecodable video, an unreadable frame, a malformed
    receipt). A file error while reading the receipt or running ffmpeg (OSError) still stops the run with
    exit code 5.
    """
    try:
        receipt = read_receipt(root, uuid)
        frames = extract(root, uuid, px)
    except (ValueError, KeyError, TypeError, AttributeError):  # a malformed receipt; OSError stays fatal
        raise ClipUnusable(0) from None
    try:
        features = local_features(frames, receipt)
    except (OSError, ValueError, ArithmeticError, IndexError, TypeError):  # Pillow cannot read a frame
        raise ClipUnusable(0) from None
    write_json(dirs(root)["features"] / f"{uuid}.json", features, indent=1)


def cmd_prepare(args) -> list[str]:
    require_pillow()  # before any frame is extracted: local features need it
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required to extract frames; install FFmpeg first.")
    dirs(args.root)
    todo = ready_clips(args.root)
    if args.limit:
        todo = todo[: args.limit]
    prepared = []
    for uuid in todo:
        try:
            prepare_clip(args.root, uuid, args.frame_px)
        except ClipUnusable as unusable:
            mark_failed(args.root, uuid, unusable.attempts)
            continue
        prepared.append(uuid)
    print(f"prepared {len(prepared)} clips (frames + local features)")
    if len(prepared) < len(todo):
        print(f"skipped {len(todo) - len(prepared)} unusable clip(s); see analysis/failed/ (delete a marker to retry)")
    return prepared


def estimate(model: str, n: int, px: int) -> float:
    price_in, price_out = PRICES[model]
    tokens_in = 3 * (px * px * 0.75 / 750) + 700
    return n * (tokens_in * price_in + 330 * price_out) / 1_000_000 * 0.5


def build_request(root: pathlib.Path, uuid: str, model: str, schema: dict):
    """One Batch API request: three frame images, then the fixed instruction, JSON-schema output."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    d = dirs(root, create=False)
    content = []
    for index in range(len(FRAME_FRACTIONS)):
        frame = d["frames"] / uuid / f"f{index}.jpg"
        if not frame.exists():
            raise SystemExit(f"Frame {index} for clip {uuid} is missing; run prepare first.")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.standard_b64encode(frame.read_bytes()).decode()}})
    content.append({"type": "text", "text": PROMPT})
    return Request(custom_id=uuid, params=MessageCreateParamsNonStreaming(
        model=model, max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}]))


def require_upload_consent(args) -> None:
    if not args.confirm_upload:
        raise SystemExit("Refusing to upload: pass --confirm-upload (the owner approves sending 3 downscaled "
                         "frames per clip plus a fixed instruction to the Anthropic API).")


def cmd_submit(args, uuids: list[str]) -> list[str]:
    if not uuids:
        print("nothing to submit")
        return []
    projected = estimate(args.model, len(uuids), args.frame_px)
    print(f"{len(uuids)} clips -> {args.model}: projected ${projected:.3f} (batch pricing), "
          f"uploads 3 frames/clip (long side {args.frame_px}px) plus a fixed instruction")
    if args.dry_run:
        return []
    require_upload_consent(args)
    anthropic = import_anthropic()
    schema = anthropic.transform_schema(clip_analysis_model())
    api = make_client(args.keychain_service)
    # No SDK retries for the upload: a retried multi-megabyte POST could create a billed batch that this
    # tool never records. A batch whose reply was lost shows up as pending in the Console instead.
    uploader = api.with_options(max_retries=0)
    batch_ids = []
    for start in range(0, len(uuids), args.batch_size):
        chunk = uuids[start: start + args.batch_size]
        batch = uploader.messages.batches.create(
            requests=[build_request(args.root, u, args.model, schema) for u in chunk])
        write_json(dirs(args.root)["batches"] / f"{batch.id}.json",
                   {"batch": batch.id, "model": args.model, "uuids": chunk, "schema": SCHEMA_ID, "frame_px": args.frame_px})
        print(f"submitted {batch.id} ({len(chunk)} clips)")
        batch_ids.append(batch.id)
    return batch_ids


def result_cost(usage, model: str) -> float:
    price_in, price_out = PRICES[model]
    cache_write = (getattr(usage, "cache_creation_input_tokens", 0) or 0) * price_in * 1.25
    cache_read = (getattr(usage, "cache_read_input_tokens", 0) or 0) * price_in * 0.1
    return round(((usage.input_tokens or 0) * price_in + cache_write + cache_read
                  + (usage.output_tokens or 0) * price_out) / 1_000_000 * 0.5, 6)


def build_record(entry, meta: dict, batch_id: str, features: dict | None) -> dict:
    """Turn one *succeeded* batch result into the per-clip record (analysis, refusal or invalid output).

    Results that did not succeed (errored, expired, canceled) are transient and get no record.
    """
    record = {"uuid": entry.custom_id, "schema": SCHEMA_ID, "model": meta["model"], "batch": batch_id,
              "analysis": None, "error": None, "usd": 0.0, "features": features}
    message = entry.result.message
    record["usd"] = result_cost(message.usage, meta["model"])
    text = next((block.text for block in message.content if block.type == "text"), "")
    if message.stop_reason == "refusal":
        record["error"] = "refusal"
    else:
        try:
            analysis = clip_analysis_model().model_validate_json(text).model_dump()
            analysis["subjects"] = list(dict.fromkeys(analysis["subjects"]))
            record["analysis"] = analysis
        except Exception as exc:  # noqa: BLE001 - the type is enough; never echo model text
            record["error"] = f"invalid_output: {type(exc).__name__}"
    record["needs_review"] = bool(record["error"] or record["analysis"]["safety"]["verdict"] != "clear")
    return record


def collect_batch(api, args, batch_id: str) -> None:
    if not BATCH_ID_RE.fullmatch(batch_id):
        raise SystemExit("Batch ids may contain only letters, digits and underscores.")
    d = dirs(args.root)
    meta_path = d["batches"] / f"{batch_id}.json"
    if not meta_path.exists():
        raise SystemExit(f"Unknown batch {batch_id}: no record under analysis/batches/.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = set(meta["uuids"])
    while True:
        batch = api.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"{batch_id}: {batch.processing_status} {batch.request_counts}", flush=True)
        time.sleep(args.poll)
    ok = failed = ignored = 0
    transient: dict[str, int] = {}
    usd = 0.0
    for entry in api.messages.batches.results(batch_id):
        uuid = entry.custom_id
        if not UUID_RE.fullmatch(uuid) or uuid not in expected:
            ignored += 1  # never build a path from an id this batch did not contain
            continue
        if entry.result.type != "succeeded":
            # errored / expired / canceled: transient. No record, frames stay, the clip stays eligible
            # (this batch gets its ledger line below, so it no longer counts as pending).
            transient[entry.result.type] = transient.get(entry.result.type, 0) + 1
            continue
        features_path = d["features"] / f"{uuid}.json"
        features = json.loads(features_path.read_text(encoding="utf-8")) if features_path.exists() else None
        record = build_record(entry, meta, batch_id, features)
        ok += record["analysis"] is not None
        failed += record["analysis"] is None
        usd += record["usd"]
        write_json(d["tags"] / f"{uuid}.json", record, indent=1)
        with (d["base"] / "tags.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        shutil.rmtree(d["frames"] / uuid, ignore_errors=True)  # derivative personal images: do not keep
    with (d["base"] / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"batch": batch_id, "model": meta["model"], "ok": ok, "failed": failed,
                                 "transient": dict(sorted(transient.items())), "ignored": ignored,
                                 "usd": round(usd, 4)}) + "\n")
    print(f"{batch_id}: ok={ok} failed={failed} retry={sum(transient.values())} ignored={ignored} "
          f"cost~${usd:.4f}")


def cmd_collect(args, batch_ids: list[str]) -> None:
    if args.pending:
        batch_ids = list(dict.fromkeys([*batch_ids, *pending_batches(args.root)]))
        if not batch_ids:
            print("no pending batches")
            return
    if not batch_ids:
        raise SystemExit("collect needs at least one --batch id or --pending.")
    api = make_client(args.keychain_service)
    for batch_id in batch_ids:
        collect_batch(api, args, batch_id)


def cmd_report(args) -> None:
    tag_dir = dirs(args.root, create=False)["tags"]
    tags = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(tag_dir.glob("*.json"))]
    failed = sum(1 for _ in dirs(args.root, create=False)["failed"].glob("*.json"))
    if not tags:
        print("no tags yet")
        print(f"clips failed frame extraction: {failed}")
        return
    verdicts: dict[str, int] = {}
    subjects: dict[str, int] = {}
    sensitivity: dict[str, int] = {}
    for tag in tags:
        analysis = tag["analysis"]
        verdict = analysis["safety"]["verdict"] if analysis else "error"
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        for subject in (analysis["subjects"][:3] if analysis else []):
            subjects[subject] = subjects.get(subject, 0) + 1
        level = (analysis or {}).get("privacy", {}).get("sharing_sensitivity")
        if level:
            sensitivity[level] = sensitivity.get(level, 0) + 1
    print(f"clips tagged: {len(tags)}  total cost ~${sum(t['usd'] for t in tags):.4f}")
    print("safety verdicts:", verdicts)
    print("sharing sensitivity:", sensitivity)
    print("top subjects:", sorted(subjects.items(), key=lambda kv: -kv[1])[:12])
    print(f"needs human review: {sum(1 for t in tags if t.get('needs_review'))}")
    print(f"clips failed frame extraction: {failed}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["prepare", "submit", "collect", "run", "report"])
    parser.add_argument("--root", type=pathlib.Path, required=True,
                        help="private storage root (outside the checkout, or under var/)")
    parser.add_argument("--model", default="claude-haiku-5-5", choices=sorted(PRICES))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--frame-px", type=int, default=640, help=f"long side of each frame, at most {MAX_FRAME_PX}")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help="clips per batch; kept small so a lost upload is cheap (uploads are not retried)")
    parser.add_argument("--poll", type=int, default=30)
    parser.add_argument("--batch", action="append", default=[], help="batch id(s) for collect")
    parser.add_argument("--pending", action="store_true",
                        help="collect: also collect every batch that has no ledger line yet")
    parser.add_argument("--keychain-service", default=None,
                        help="macOS Keychain item holding the API key (default: ANTHROPIC_API_KEY via the SDK)")
    parser.add_argument("--dry-run", action="store_true", help="prepare locally and print the projected cost; upload nothing")
    parser.add_argument("--confirm-upload", action="store_true",
                        help="REQUIRED to send frames to the API: 3 downscaled JPEG frames per clip + a fixed instruction")
    return parser


def run_command(args) -> int:
    args.root = resolve_private_root(args.root)
    uploads = args.command in ("submit", "run") and not args.dry_run
    if uploads:
        require_upload_consent(args)  # before any frame is extracted

    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "submit":
        cmd_submit(args, cmd_prepare(args))
    elif args.command == "collect":
        cmd_collect(args, args.batch)
    elif args.command == "run":
        cmd_submit(args, cmd_prepare(args))
        if not args.dry_run and pending_batches(args.root):  # new batches and any left by an earlier run
            args.pending = True
            cmd_collect(args, [])
            cmd_report(args)
    else:
        cmd_report(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if min(args.limit, args.poll) < 0 or min(args.frame_px, args.batch_size) < 1:
        raise SystemExit("--limit and --poll must be >= 0; --frame-px and --batch-size must be positive.")
    if args.frame_px > MAX_FRAME_PX:
        raise SystemExit(f"--frame-px is capped at {MAX_FRAME_PX}: frames are thumbnails, not full-resolution images.")
    try:
        return run_command(args)
    except OSError as exc:  # the message and filename can hold private paths: print the type only
        print(f"local file error ({type(exc).__name__}); check permissions and free space under --root.",
              file=sys.stderr, flush=True)
        return EXIT_IO_ERROR


if __name__ == "__main__":
    sys.exit(main())
