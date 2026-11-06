"""Synthetic clip pool for the gravity tests (shared helper; contains no tests).

All data is invented: eight latent themes with overlapping vocabulary, bridge clips that
mix two themes, untagged clips, flagged clips and sharing-sensitivity ratings. Captions and
notes carry sentinel strings so tests can prove they never reach a state. The private
_truth field holds the latent themes for evaluation only; the scheduler never reads it.
"""
from __future__ import annotations

import colorsys
import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

# theme: subjects (core, optional), keywords, setting, env, times, moods, palette names,
#        hue (0..1), sat, luma, motion (feature units), motion levels, shots
THEMES: dict[str, dict[str, Any]] = {
    "beach": dict(core=["water", "waves", "sky"], opt=["sun", "person", "clouds", "reflection"],
                  kw=["beach", "sea", "sand", "summer", "shore", "horizon", "surf"], setting="outdoor",
                  env=["nature"], times=["day", "golden_hour"], moods=["calm", "serene", "joyful"],
                  pal=["blue", "teal", "white"], hue=0.55, sat=0.45, luma=0.62, motion=0.07,
                  levels=["moderate", "subtle"], shots=["wide", "medium"]),
    "forest": dict(core=["tree", "plant"], opt=["grass", "sky", "shadow", "light_effect"],
                   kw=["forest", "woods", "leaves", "path", "green", "hike", "moss"], setting="outdoor",
                   env=["nature"], times=["day"], moods=["calm", "serene"],
                   pal=["green", "brown"], hue=0.30, sat=0.40, luma=0.42, motion=0.03,
                   levels=["subtle", "still"], shots=["wide", "medium"]),
    "city_night": dict(core=["street", "building", "light_effect"], opt=["vehicle", "reflection", "crowd"],
                       kw=["city", "neon", "traffic", "night", "lights", "downtown", "rain"], setting="outdoor",
                       env=["urban", "transit"], times=["night", "dusk"], moods=["energetic", "eerie"],
                       pal=["purple", "orange", "black"], hue=0.80, sat=0.50, luma=0.22, motion=0.10,
                       levels=["moderate", "intense"], shots=["wide", "medium"]),
    "kitchen": dict(core=["person", "food", "interior"], opt=["face", "group", "hands", "drink"],
                    kw=["dinner", "table", "family", "cooking", "kitchen", "meal", "laughing"], setting="indoor",
                    env=["domestic"], times=["artificial_light", "night"], moods=["joyful", "intimate", "tender"],
                    pal=["orange", "brown", "yellow"], hue=0.08, sat=0.42, luma=0.45, motion=0.06,
                    levels=["moderate", "subtle"], shots=["medium", "close_up"]),
    "pets": dict(core=["pet", "animal"], opt=["interior", "hands", "grass", "face"],
                 kw=["dog", "cat", "puppy", "fur", "sofa", "playing", "cute"], setting="indoor",
                 env=["domestic"], times=["day", "artificial_light"], moods=["playful", "tender", "joyful"],
                 pal=["brown", "white", "gray"], hue=0.09, sat=0.22, luma=0.52, motion=0.08,
                 levels=["moderate", "intense"], shots=["close_up", "medium"]),
    "snow": dict(core=["snow", "mountain", "sky"], opt=["clouds", "tree", "person", "sun"],
                 kw=["winter", "snow", "cold", "peak", "ski", "white", "frost"], setting="outdoor",
                 env=["nature"], times=["day", "golden_hour"], moods=["serene", "calm", "melancholic"],
                 pal=["white", "blue", "gray"], hue=0.60, sat=0.12, luma=0.80, motion=0.03,
                 levels=["still", "subtle"], shots=["wide"]),
    "concert": dict(core=["crowd", "light_effect"], opt=["fireworks", "instrument", "person", "sky"],
                    kw=["concert", "music", "stage", "festival", "fireworks", "party", "dance"], setting="mixed",
                    env=["event"], times=["night", "artificial_light"], moods=["energetic", "chaotic", "joyful"],
                    pal=["purple", "pink", "black"], hue=0.88, sat=0.65, luma=0.25, motion=0.13,
                    levels=["intense", "moderate"], shots=["wide", "medium"]),
    "garden": dict(core=["flower", "plant"], opt=["insect", "grass", "sun", "hands"],
                   kw=["flowers", "garden", "bloom", "petals", "bee", "spring", "macro"], setting="outdoor",
                   env=["nature", "domestic"], times=["day", "golden_hour"], moods=["tender", "calm", "joyful"],
                   pal=["pink", "yellow", "green"], hue=0.95, sat=0.55, luma=0.55, motion=0.04,
                   levels=["subtle", "still"], shots=["close_up"]),
}
NOISE_KW = ["blur", "moment", "light", "afternoon", "window", "shadow", "quiet", "weekend", "slow", "bright"]
TIME_FOR = {"artificial_light": "artificial_light"}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _palette_hex(rng: random.Random, hue: float, sat: float, luma: float, n: int) -> list[dict[str, Any]]:
    shares = sorted((rng.random() + 0.2 for _ in range(n)), reverse=True)
    total = sum(shares)
    out = []
    for i, s in enumerate(shares):
        h = (hue + rng.gauss(0, 0.04 + 0.03 * i)) % 1.0
        l = _clamp(luma + rng.gauss(0, 0.12))
        sa = _clamp(sat + rng.gauss(0, 0.12))
        r, g, b = colorsys.hls_to_rgb(h, l, sa)
        out.append({"hex": "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)), "share": round(s / total, 3)})
    return out


def _mix(rng: random.Random, primary: dict, secondary: dict | None, key: str):
    src = secondary if (secondary is not None and rng.random() < 0.4) else primary
    return src[key]


def make_record(rng: random.Random, index: int, theme: str, second: str | None = None,
                tagged: bool = True) -> dict[str, Any]:
    t, s = THEMES[theme], (THEMES[second] if second else None)
    subjects = list(t["core"])
    rng.shuffle(subjects)
    subjects = subjects[: rng.randint(max(1, len(subjects) - 1), len(subjects))]
    subjects += rng.sample(t["opt"], rng.randint(0, 2))
    if s:
        subjects.insert(rng.randint(0, len(subjects)), rng.choice(s["core"]))
        subjects += rng.sample(s["opt"], 1)
    subjects = list(dict.fromkeys(subjects))[:8]
    keywords = rng.sample(t["kw"], rng.randint(2, 4)) + (rng.sample(s["kw"], 2) if s else [])
    if rng.random() < 0.5:
        keywords.append(rng.choice(NOISE_KW))
    keywords = list(dict.fromkeys(keywords))[:6]
    mood_src = _mix(rng, t, s, "moods")
    moods = rng.sample(mood_src, rng.randint(1, min(2, len(mood_src))))
    pal_src = _mix(rng, t, s, "pal")
    pal_names = rng.sample(pal_src, rng.randint(1, min(3, len(pal_src))))
    hue_base = t["hue"] if not s or rng.random() < 0.6 else s["hue"]
    hue = (hue_base + rng.gauss(0, 0.035)) % 1.0
    sat = _clamp(t["sat"] + rng.gauss(0, 0.07))
    luma = _clamp(t["luma"] + rng.gauss(0, 0.08))
    motion = _clamp(t["motion"] + rng.gauss(0, 0.02), 0.002, 0.3)
    orientation = "portrait" if rng.random() < 0.8 else "landscape"
    cid = f"clip-{index:03d}"
    analysis = {
        "subjects": subjects,
        "setting": t["setting"] if rng.random() < 0.9 else "unclear",
        "environment": rng.choice(_mix(rng, t, s, "env")),
        "time_of_day": rng.choice(_mix(rng, t, s, "times")),
        "camera": rng.choice(["locked", "handheld", "handheld", "pan"]),
        "motion_level": rng.choice(t["levels"]),
        "shot": rng.choice(t["shots"]),
        "palette": pal_names,
        "mood": moods,
        "caption": f"CAPTION-SENTINEL-{index:03d}",
        "keywords": keywords,
        "people": {"count": "0", "faces_visible": "face" in subjects, "minors_apparent": False},
        "privacy": {"readable_text": False, "license_plate": False, "document_or_screen": False,
                    "location_identifiable": False,
                    "sharing_sensitivity": rng.choice(["low", "low", "moderate"]),
                    "sharing_note": f"NOTE-SENTINEL-{index:03d}"},
        "safety": {"verdict": "clear", "categories": [], "reason": f"REASON-SENTINEL-{index:03d}"},
    }
    features = {
        "luma": round(luma, 4), "luma_spread": round(abs(rng.gauss(0, 0.03)), 4),
        "saturation": round(sat, 4), "hue": round(hue, 4), "motion": round(motion, 4),
        "palette": _palette_hex(rng, hue, sat, luma, 5),
        "duration": round(rng.uniform(1.6, 3.2), 3),
        "width": 1080 if orientation == "portrait" else 1920,
        "height": 1920 if orientation == "portrait" else 1080,
        "orientation": orientation,
    }
    return {
        "id": cid,
        "sha256": hashlib.sha256(f"synthetic:{cid}".encode()).hexdigest(),
        "duration": features["duration"],
        "analysis": analysis if tagged else None,
        "features": features,
        "needs_review": False,
        "error": None if tagged else "not_tagged",
        "_truth": [theme] + ([second] if second else []),
    }




def make_pool(size: int = 120, seed: int = 20260101) -> list[dict[str, Any]]:
    """About 8% untagged, 8% unsafe/private/minor/high-sensitivity, and a few unknown-sensitivity records."""
    rng = random.Random(seed)
    themes = sorted(THEMES)
    weights = [rng.uniform(0.6, 1.4) for _ in themes]       # uneven cluster sizes
    pool = []
    for i in range(1, size + 1):
        theme = rng.choices(themes, weights)[0]
        second = None
        if rng.random() < 0.15:                                # bridge clips
            second = rng.choice([x for x in themes if x != theme])
        tagged = rng.random() > 0.08
        record = make_record(rng, i, theme, second, tagged)
        roll = rng.random()
        if tagged and roll < 0.04:
            record["analysis"]["safety"]["verdict"] = "review"
            record["needs_review"] = True
        elif tagged and roll < 0.06:
            record["analysis"]["privacy"]["readable_text"] = True
        elif tagged and roll < 0.075:
            record["analysis"]["safety"]["verdict"] = "exclude"
            record["needs_review"] = True
        elif tagged and roll < 0.10:
            record["analysis"]["privacy"]["sharing_sensitivity"] = "high"
        elif tagged and roll < 0.12:
            record["analysis"]["people"]["minors_apparent"] = True
        elif tagged and roll < 0.14:
            del record["analysis"]["privacy"]["sharing_sensitivity"]   # schema v1 style: unknown
        pool.append(record)
    stamps = random.Random(seed + 1)                     # separate stream: the records above are unchanged
    for record in pool:
        if stamps.random() < 0.92:                       # a few clips carry no capture time
            seconds = stamps.randrange(0, 2 * 365 * 24 * 3600)
            record["captured_at"] = (datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()
    return pool


def strip_tags(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stranger view: only locally computed features remain."""
    out = []
    for r in pool:
        r2 = {k: v for k, v in r.items() if k not in ("analysis", "needs_review", "error")}
        r2["analysis"] = None
        out.append(r2)
    return out
