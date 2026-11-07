#!/usr/bin/env python3
"""Generate a SYNTHETIC dataset for the lab (stdlib + ffmpeg only).

Output (git-ignored, below var/): var/proofs/lab-fixtures/{data/clips.json, data/clips-large.json, media/*.mp4, still/*.jpg}
Run from the repository root:  PYTHONPATH=src python3 -m simvltanea.lab.make_fixtures [--force]
Serve the repository root and open  /src/simvltanea/lab/app/?data=/var/proofs/lab-fixtures/

No real media is ever read; every pixel and sample here is a test pattern or a sine tone.
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from simvltanea.lab import FIXTURES_DIR
from simvltanea.paths import require_in_var

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
OUT = str(require_in_var(FIXTURES_DIR, "lab fixtures"))
N_CLIPS = 24
N_LARGE = 6500

ENV_SUBJECTS = {
    "nature": ["tree", "sky", "river", "mountain", "sea", "flower", "dog"],
    "urban": ["street", "car", "building", "crowd", "bike", "window"],
    "domestic": ["kitchen", "cake", "sofa", "window", "dog", "child toy"],
    "workplace": ["desk", "laptop", "window", "meeting"],
    "transit": ["train", "bus", "road", "station", "car"],
    "event": ["crowd", "balloons", "cake", "stage"],
    "studio": ["lamp", "backdrop", "chair"],
}
SETTINGS = {"nature": "outdoor", "urban": "outdoor", "domestic": "indoor", "workplace": "indoor", "transit": "mixed", "event": "mixed", "studio": "indoor"}
TOD = ["day", "golden_hour", "dusk", "night", "artificial_light"]
CAMERA = ["locked", "handheld", "pan", "tilt", "zoom", "tracking"]
MOTION = ["still", "subtle", "moderate", "intense"]
SHOT = ["close_up", "medium", "wide"]
PALETTE = ["blue", "green", "red", "yellow", "orange", "grey", "white", "brown"]
MOOD = ["calm", "joyful", "tense", "nostalgic", "quiet", "energetic"]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def rand_date(rng):
    start = datetime(2012, 1, 1, tzinfo=timezone.utc)
    span = int((datetime(2022, 12, 31, tzinfo=timezone.utc) - start).total_seconds())
    return (start + timedelta(seconds=rng.randrange(span))).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_tags(rng, env=None):
    env = env or rng.choice(list(ENV_SUBJECTS))
    subjects = rng.sample(ENV_SUBJECTS[env], k=min(2, len(ENV_SUBJECTS[env])))
    return {
        "subjects": subjects,
        "setting": SETTINGS[env],
        "environment": env,
        "time_of_day": rng.choice(TOD),
        "camera": rng.choice(CAMERA),
        "motion_level": rng.choice(MOTION),
        "shot": rng.choice(SHOT),
        "palette": rng.sample(PALETTE, 2),
        "mood": rng.sample(MOOD, 1),
        "keywords": subjects + [rng.choice(ENV_SUBJECTS[env])],
        "people": {"count": rng.choice(["0", "0", "1", "2-3", "4+"]), "faces_visible": False, "minors_apparent": False},
        "privacy": {"readable_text": False, "license_plate": False, "document_or_screen": False,
                    "location_identifiable": False, "sharing_sensitivity": rng.choice(["low", "low", "moderate"])},
        "safety": {"verdict": "clear"},
    }


def make_features(rng):
    return {
        "luma": round(rng.random(), 3), "luma_spread": round(rng.random() * 0.3, 3), "saturation": round(rng.random(), 3),
        "hue": round(rng.random(), 3), "motion": round(rng.random() * 0.3, 3),
        "palette": [{"hex": "#%02x%02x%02x" % (rng.randrange(256), rng.randrange(256), rng.randrange(256)), "share": 0.4}],
    }


def volumedetect(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    return float(m.group(1)) if m else None


def grid8(video, dur):
    """features.grid8: 8x8 mean colours (row-major, rrggbb x 64 = 384 hex chars) of the middle frame of a SYNTHETIC clip."""
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % (dur / 2), "-i", video, "-frames:v", "1",
                        "-vf", "scale=8:8:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    if len(p.stdout) != 192:
        raise RuntimeError("grid8: expected 192 bytes, got %d" % len(p.stdout))
    return p.stdout.hex()


def make_audio_info(i):
    """clip.audio as a local speech screen would report it (synthetic, no transcript ever): about one clip in three has speech."""
    speech = i % 3 == 1
    flags = []
    if speech:
        flags = [["introduces_self"], ["possible_name"], ["number_sequence", "long_speech"]][(i // 3) % 3]
    return {"screened": True, "speech": speech, "words": (8 + (i * 7) % 33) if speech else 0, "flags": flags, "low_confidence": i % 8 == 5}


def make_clip(i, rng):
    cid = "fx-%02d-%s" % (i, "%08x" % rng.getrandbits(32))
    portrait = i % 3 != 0 or i % 2 == 0 and i > 12
    w, h = (540, 720) if portrait else (720, 540)
    dur = round(2.0 + (i % 5) * 0.4, 1)
    freq = 220 * (2 ** ((i * 5 % 24) / 12.0))                 # a different tone per clip
    vol_db = -42 + (i % 8) * 4 if i % 2 else -18 - (i % 4) * 3  # deliberately different levels (-42 .. -12 dB)
    video = os.path.join(OUT, "media", cid + ".mp4")
    still = os.path.join(OUT, "still", cid + ".jpg")
    has_audio = i != N_CLIPS - 1
    src = ("testsrc2=size=%dx%d:rate=24:duration=%s" % (w, h, dur)) if i % 2 == 0 else \
          ("gradients=size=%dx%d:rate=24:duration=%s:speed=0.05:seed=%d:nb_colors=4" % (w, h, dur, 100 + i))
    vf = "hue=h=%d,format=yuv420p" % ((i * 37) % 360)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src]
    if has_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=%.2f:sample_rate=44100:duration=%s" % (freq, dur),
                "-af", "volume=%gdB" % vol_db, "-c:a", "aac", "-b:a", "64k", "-ac", "1"]
    else:
        cmd += ["-an"]
    cmd += ["-vf", vf, "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-g", "24", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-shortest", video]
    run(cmd)
    scale = "scale=1280:-2:flags=lanczos" if not portrait else "scale=-2:1280:flags=lanczos"
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", video, "-ss", "0.8", "-frames:v", "1", "-vf", scale, "-q:v", "3", still])
    loud = volumedetect(video) if has_audio else None
    clip = {
        "id": cid, "video": "media/%s.mp4" % cid, "still": "still/%s.jpg" % cid, "duration": dur, "width": w, "height": h,
        "orientation": "portrait" if portrait else "landscape", "has_audio": has_audio,
        "loudness_db": round(loud, 1) if loud is not None else 0,
        "captured_at": rand_date(rng), "tags": make_tags(rng, list(ENV_SUBJECTS)[i % len(ENV_SUBJECTS)]), "features": make_features(rng),
        "audio": make_audio_info(i),
    }
    clip["features"]["grid8"] = grid8(video, dur)
    return clip


def degrade(clips):
    """Missing optional fields and a few privacy-sensitive records so filters are testable."""
    by = {c["id"]: c for c in clips}
    ids = [c["id"] for c in clips]
    del by[ids[20]]["tags"]                                        # no tags at all
    del by[ids[21]]["features"]; del by[ids[21]]["loudness_db"]  # no features, unknown loudness
    del by[ids[22]]["captured_at"]; del by[ids[22]]["tags"]["privacy"]; del by[ids[22]]["tags"]["safety"]
    del by[ids[23]]["loudness_db"]  # the clip without an audio track
    del by[ids[19]]["features"]["grid8"]                           # palette/hue/luma fallback only
    by[ids[18]]["features"]["grid8"] = by[ids[18]]["features"]["grid8"][:100]  # malformed grid8 (wrong length): ignored
    del by[ids[21]]["audio"]                                       # never screened: no audio record at all
    by[ids[22]]["audio"] = {"screened": False, "speech": False, "words": 0, "flags": [], "low_confidence": True}
    by[ids[5]]["tags"]["privacy"]["license_plate"] = True
    by[ids[9]]["tags"]["people"]["minors_apparent"] = True
    by[ids[14]]["tags"]["safety"] = {"verdict": "review"}
    by[ids[3]]["tags"]["privacy"]["sharing_sensitivity"] = "high"


def large(rng):
    out = []
    envs = list(ENV_SUBJECTS)
    for i in range(N_LARGE):
        portrait = rng.random() < 0.5
        c = {
            "id": "L%05d-%08x" % (i, rng.getrandbits(32)), "video": "media/L%05d.mp4" % i, "still": "still/L%05d.jpg" % i,
            "duration": round(1 + rng.random() * 5, 1), "width": 540 if portrait else 720, "height": 720 if portrait else 540,
            "orientation": "portrait" if portrait else "landscape", "has_audio": rng.random() < 0.9, "loudness_db": round(-55 + rng.random() * 30, 1),
            "captured_at": rand_date(rng), "tags": make_tags(rng, rng.choice(envs)), "features": make_features(rng),
            "audio": {"screened": i % 50 != 0, "speech": i % 3 == 0, "words": 0, "flags": ["possible_name"] if i % 17 == 0 else [], "low_confidence": False},
        }
        r = rng.random()
        if r < 0.02: del c["tags"]
        elif r < 0.04: del c["features"]
        elif r < 0.05: c["tags"]["safety"] = {"verdict": "review"}
        elif r < 0.06: c["tags"]["privacy"]["sharing_sensitivity"] = "high"
        out.append(c)
    return out


def main():
    force = "--force" in sys.argv
    if os.path.exists(os.path.join(OUT, "data", "clips.json")) and not force:
        print("fixtures already generated in %s (use --force to rebuild)" % OUT)
        return 0
    if not shutil.which(FFMPEG):
        print("ffmpeg not found (%s); install it or set FFMPEG" % FFMPEG, file=sys.stderr)
        return 2
    for d in ("data", "media", "still"):
        shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
        os.makedirs(os.path.join(OUT, d))
    rng = random.Random(20240601)
    clips = [make_clip(i, rng) for i in range(N_CLIPS)]
    degrade(clips)
    with open(os.path.join(OUT, "data", "clips.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "clips": clips}, f, indent=1)
    with open(os.path.join(OUT, "data", "clips-large.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "clips": large(random.Random(99))}, f, separators=(",", ":"))
    print("wrote %d clips (+%d metadata-only) to %s" % (N_CLIPS, N_LARGE, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
