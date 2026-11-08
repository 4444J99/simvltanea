"""Affinity between two clip records: how related two clips are, as an integer 0..1000.

Input record shape (generic tag record; every key but ``id`` is optional):

    {"id": str, "duration": float|str, "sha256": str?,
     "analysis": ClipAnalysis dict | None,   # tag fields; absent for untagged clips
     "features": local_features dict | None, # locally computed, browser-computable
     "needs_review": bool?, "error": str?}

Only the tag vocabulary and the numeric feature fields are read. Free text such as a
caption is never read here. Components whose inputs are missing on either clip are
skipped and the rest are renormalised, so untagged clips still get a defined affinity.

Portability contract (for a byte-identical JavaScript port):
  * the float operations are + - * / and sqrt (correctly rounded in IEEE-754, in both CPython and
    every JS engine) and operations that never round: abs, min, max, comparisons, the float
    remainder ``hue % 1.0`` (hue is non-negative, so Python and JS ``%`` are the same exact fmod) and
    floor division by 1 (the exact floor of a double, used for half-up quantisation); no
    exp/log/pow/atan2/cbrt, and never the builtin ``sum`` (CPython 3.12+ uses compensated
    summation there): float sums are plain left-to-right loops over sorted lists, so their order
    is fixed;
  * every component value is quantized to an integer (10**-12 steps, explicit half-up)
    BEFORE the components are combined, and the combination is pure integer
    arithmetic, so it does not depend on the order in which components are added;
  * the final value is an integer in 0..1000 ("milli-affinity"), half-up rounded;
  * Python's Unicode string semantics are part of the contract (docs/architecture/GRAVITY.md, "Reproducibility"):
    keywords go through ``str.strip()`` (which strips U+001C-U+001F and U+0085 but not U+FEFF, the reverse of
    ``String.prototype.trim()``) and ``str.lower()`` (the interpreter's Unicode tables); nothing is Unicode-normalised;
    every sort of strings is by code point, not by UTF-16 code unit; ``len`` counts code points.

Weights are signed. A positive weight rewards similarity in that component, a negative
weight rewards contrast (its score is ``1 - similarity``); the magnitude is the weight.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from math import isfinite, sqrt
from typing import Any, Iterable, Mapping

AFFINITY_SCALE = 1000  # quantized affinity is an int in 0..AFFINITY_SCALE

# Named components and their default weights (sum to 1.0 when all are present).
DEFAULT_WEIGHTS: dict[str, float] = {
    "subjects": 0.22,   # IDF-weighted, prominence-weighted overlap of analysis.subjects
    "keywords": 0.10,   # IDF-weighted overlap of analysis.keywords
    "context": 0.14,    # setting / environment / time_of_day agreement
    "mood": 0.10,       # valence-arousal proximity of analysis.mood
    "color": 0.16,      # circular hue (saturation-gated) + palette distance
    "tone": 0.10,       # luma and saturation closeness
    "motion": 0.10,     # motion_level ordinal and/or measured frame-difference motion
    "framing": 0.08,    # source orientation and shot-size compatibility
}
# Evidence shrinkage: a pseudo-component of this weight with value 0.5 is always
# added, so a pair that shares only one weak component cannot reach 0 or 1.
PRIOR_WEIGHT = 0.05
PRIOR_VALUE = 0.5
# A subject listed at position ``rank`` (0 = most prominent) weighs PROMINENCE_RANK / (PROMINENCE_RANK + rank).
PROMINENCE_RANK = 4.0

# Components a caller may weight. The first eight are the defaults above; the last three
# are single-attribute views (also inside context / framing) that default to weight 0 so a
# user can match on one attribute while contrasting on another (city against nature).
EXTRA_COMPONENTS = ("environment", "shot", "orientation")
ALL_COMPONENTS = tuple(DEFAULT_WEIGHTS) + EXTRA_COMPONENTS
COMPONENT_SCALE = 10 ** 12      # component values are integers 0..COMPONENT_SCALE
WEIGHT_SCALE = 1000             # weights are integers in milli-units
WEIGHT_RANGE = (-1.0, 1.0)
DEFAULT_CACHE_SIZE = 150_000    # affinity pairs kept (LRU)
DEFAULT_MEMO_SIZE = 200_000     # categorical-combination pairs kept per component (cleared when full)
_DEN_UNIT = COMPONENT_SCALE // AFFINITY_SCALE

LOCAL_ONLY_COMPONENTS = ("color", "tone", "motion", "framing")

_MOTION_LEVEL = {"still": 0, "subtle": 1, "moderate": 2, "intense": 3}
_SHOT = {"close_up": 0, "medium": 1, "wide": 2}
_TIME = {"day": 0, "golden_hour": 1, "dusk": 2, "night": 3}
_SETTING = {("indoor", "mixed"): 0.5, ("mixed", "outdoor"): 0.5}
_ENVIRONMENT = {("domestic", "workplace"): 0.3, ("studio", "workplace"): 0.3,
                ("transit", "urban"): 0.5, ("event", "urban"): 0.3, ("domestic", "studio"): 0.2}
# Valence, arousal in [-1, 1].
_MOOD_VA = {
    "calm": (0.5, -0.6), "serene": (0.6, -0.7), "tender": (0.7, -0.3), "intimate": (0.6, -0.2),
    "joyful": (0.9, 0.6), "playful": (0.7, 0.5), "energetic": (0.5, 0.9), "chaotic": (-0.3, 0.9),
    "eerie": (-0.5, 0.2), "melancholic": (-0.6, -0.4),
}
_MOOD_RADIUS = 1.6
# Representative sRGB for the tag palette vocabulary.
_COLOR_RGB = {
    "red": (200, 40, 40), "orange": (230, 130, 40), "yellow": (235, 210, 60), "green": (60, 150, 70),
    "teal": (40, 150, 150), "blue": (50, 90, 200), "purple": (120, 60, 170), "pink": (230, 130, 170),
    "brown": (120, 80, 50), "black": (15, 15, 15), "white": (240, 240, 240), "gray": (128, 128, 128),
    "gold": (210, 170, 60),
}
_PALETTE_RANGE = 220.0   # redmean distance at which palette similarity reaches 0
_LUMA_SIGMA = 0.15
_SAT_SIGMA = 0.12
_MOTION_FULL = 0.12      # features.motion at/above this counts as "maximal"
_HUE_SAT_REF = 0.30      # geometric-mean saturation at which hue is fully trusted


def round_half_up_div(num: int, den: int) -> int:
    """floor(num/den + 1/2) for integers, den > 0 (JS port: BigInt, floor not trunc)."""
    return (2 * num + den) // (2 * den)


def quantize(value: float) -> int:
    """Half-up quantization of a float in [0,1] to 0..AFFINITY_SCALE."""
    q = int((value * AFFINITY_SCALE + 0.5) // 1)
    return max(0, min(AFFINITY_SCALE, q))


def quantize_component(value: float) -> int:
    """Half-up quantization of a component similarity in [0,1] to 0..COMPONENT_SCALE."""
    q = int((value * COMPONENT_SCALE + 0.5) // 1)
    return max(0, min(COMPONENT_SCALE, q))


def weight_milli(weight: float) -> int:
    """Signed weight to integer milli-units, half-up on the magnitude."""
    magnitude = int((abs(weight) * WEIGHT_SCALE + 0.5) // 1)
    return -magnitude if weight < 0 else magnitude


def combine_milli(components: Mapping[str, int | None], weights: Mapping[str, int]) -> int:
    """Milli-affinity from quantized components and signed milli weights, in integers only.

    ``A = (P*500 + sum |w_k| * c_k) / (P + sum |w_k|)`` where ``c_k`` is the similarity for a
    positive weight and ``1 - similarity`` for a negative one, and ``P`` is the 0.05 prior.
    Addition of integers is exact, so the result does not depend on iteration order.
    """
    prior = weight_milli(PRIOR_WEIGHT)
    num = prior * (COMPONENT_SCALE // 2)
    den = prior
    for name in components:
        value, w = components[name], weights.get(name, 0)
        if value is None or w == 0:
            continue
        num += abs(w) * (value if w > 0 else COMPONENT_SCALE - value)
        den += abs(w)
    return max(0, min(AFFINITY_SCALE, round_half_up_div(num, den * (COMPONENT_SCALE // AFFINITY_SCALE))))


@dataclass(frozen=True)
class ClipProfile:
    """Normalized view of one record; every field may be missing (None / empty)."""
    id: str
    tagged: bool
    subjects: tuple[tuple[str, float], ...] = ()   # (term, prominence weight), sorted by term
    keywords: tuple[str, ...] = ()                  # sorted, deduplicated
    keyword_items: tuple[tuple[str, float], ...] = ()   # the same as (word, 1.0) pairs, for the overlap merge
    setting: str | None = None
    environment: str | None = None
    time_of_day: str | None = None
    moods: tuple[str, ...] = ()
    palette_names: tuple[str, ...] = ()
    motion_level: int | None = None
    shot: int | None = None
    hue: float | None = None
    saturation: float | None = None
    luma: float | None = None
    motion: float | None = None
    palette: tuple[tuple[tuple[int, int, int], float], ...] = ()  # ((r,g,b), share)
    orientation: str | None = None


# Exactly six ASCII hex digits after an optional '#': no sign, space, underscore, other digit script or
# second '#'. A port can copy this rule as /^#?[0-9a-fA-F]{6}$/ (int(,16) and parseInt disagree on all of those).
_HEX_COLOUR = re.compile(r"#?([0-9a-fA-F]{6})")


def _hex_rgb(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    m = _HEX_COLOUR.fullmatch(value)
    if m is None:
        return None
    s = m.group(1)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _seq(value: Any) -> tuple:
    """A list/tuple field, or nothing: a malformed (non-sequence) value drops its component."""
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def _known(value: Any) -> str | None:
    return value if isinstance(value, str) and value and value != "unclear" else None


def _finite01(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not isfinite(number) or number < 0:
        return None
    return number


def clip_profile(record: dict[str, Any]) -> ClipProfile:
    analysis = record.get("analysis")
    feats = record.get("features")
    analysis = analysis if isinstance(analysis, dict) and analysis else None
    feats = feats if isinstance(feats, dict) and feats else None
    kwargs: dict[str, Any] = {}
    if analysis:
        seen: dict[str, float] = {}
        for i, term in enumerate(_seq(analysis.get("subjects"))):
            if isinstance(term, str) and term and term not in seen:
                seen[term] = PROMINENCE_RANK / (PROMINENCE_RANK + i)      # most prominent first; rational decay
        kwargs["subjects"] = tuple(sorted(seen.items()))
        words = {w.strip().lower() for w in _seq(analysis.get("keywords")) if isinstance(w, str) and w.strip()}
        kwargs["keywords"] = tuple(sorted(words))
        kwargs["keyword_items"] = tuple((w, 1.0) for w in kwargs["keywords"])
        kwargs["setting"] = _known(analysis.get("setting"))
        kwargs["environment"] = _known(analysis.get("environment"))
        kwargs["time_of_day"] = _known(analysis.get("time_of_day"))
        kwargs["moods"] = tuple(sorted({m for m in _seq(analysis.get("mood")) if isinstance(m, str) and m in _MOOD_VA}))
        kwargs["palette_names"] = tuple(sorted({p for p in _seq(analysis.get("palette")) if isinstance(p, str) and p in _COLOR_RGB}))
        kwargs["motion_level"] = _MOTION_LEVEL.get(_known(analysis.get("motion_level")))
        kwargs["shot"] = _SHOT.get(_known(analysis.get("shot")))
    if feats:
        hue = _finite01(feats.get("hue"))
        kwargs["hue"] = None if hue is None else hue % 1.0
        kwargs["saturation"] = _finite01(feats.get("saturation"))
        kwargs["luma"] = _finite01(feats.get("luma"))
        kwargs["motion"] = _finite01(feats.get("motion"))
        pal = []
        for entry in _seq(feats.get("palette")):
            rgb = _hex_rgb(entry.get("hex", "")) if isinstance(entry, dict) else None
            share = _finite01(entry.get("share")) if isinstance(entry, dict) else None
            if rgb is not None and share and share <= 1.0:      # a share is a fraction; larger is malformed
                pal.append((rgb, share))
        kwargs["palette"] = tuple(sorted(pal))
        o = feats.get("orientation")
        kwargs["orientation"] = o if o in ("portrait", "landscape") else None
    return ClipProfile(id=str(record["id"]), tagged=bool(analysis), **kwargs)


# --- component similarities: each returns a float in [0,1] or None (unavailable) ---

def _ruzicka_sorted(a: tuple, b: tuple, idf: Mapping[str, float]) -> float:
    """Same value as the dictionary form: a two-pointer merge of term-sorted (term, weight) tuples.

    Terms present on one side contribute min = 0 to the numerator, which changes nothing, so only
    the denominator needs them; terms are visited in the same sorted order, so float sums are unchanged.
    """
    num = den = 0.0
    i = j = 0
    la, lb = len(a), len(b)
    while i < la and j < lb:
        ta, wa = a[i]
        tb, wb = b[j]
        if ta == tb:
            w = idf.get(ta, 1.0)
            num += min(wa, wb) * w
            den += max(wa, wb) * w
            i += 1
            j += 1
        elif ta < tb:
            den += wa * idf.get(ta, 1.0)
            i += 1
        else:
            den += wb * idf.get(tb, 1.0)
            j += 1
    while i < la:
        den += a[i][1] * idf.get(a[i][0], 1.0)
        i += 1
    while j < lb:
        den += b[j][1] * idf.get(b[j][0], 1.0)
        j += 1
    return num / den if den > 0 else 0.0


def _redmean(p: tuple[int, int, int], q: tuple[int, int, int]) -> float:
    rbar = (p[0] + q[0]) / 2.0
    dr, dg, db = p[0] - q[0], p[1] - q[1], p[2] - q[2]
    return sqrt((2.0 + rbar / 256.0) * dr * dr + 4.0 * dg * dg + (2.0 + (255.0 - rbar) / 256.0) * db * db)


def _palette_similarity(pa, pb) -> float:
    # One redmean matrix serves both directions (the distance is symmetric, bit for bit), so each
    # pair of colours is measured once. The expression is _redmean's, inlined; sums keep the order
    # of the directed form they replace.
    rows = []
    for (p0, p1, p2), _ in pa:
        row = []
        for (q0, q1, q2), _ in pb:
            rbar = (p0 + q0) / 2.0
            dr, dg, db = p0 - q0, p1 - q1, p2 - q2
            row.append(sqrt((2.0 + rbar / 256.0) * dr * dr + 4.0 * dg * dg + (2.0 + (255.0 - rbar) / 256.0) * db * db))
        rows.append(row)
    total_a = 0.0
    acc_a = 0.0
    for (_, share), row in zip(pa, rows):
        total_a += share
        acc_a += share * min(row)
    total_b = 0.0
    acc_b = 0.0
    for j, (_, share) in enumerate(pb):
        total_b += share
        acc_b += share * min([row[j] for row in rows])
    d = (acc_a / total_a + acc_b / total_b) / 2.0
    return max(0.0, 1.0 - d / _PALETTE_RANGE)


_MISSING = object()


class _Prep:
    """Per-clip data for ``AffinityModel.affinity_milli_fast``, computed once per pool."""
    __slots__ = ("profile", "ctx", "mood", "env", "shot_id", "orient", "framing", "names", "subjects",
                 "keywords", "has_hue", "palette", "palette_total", "motion_scaled", "hue", "sat", "luma", "level",
                 "has_names")

    def __init__(self, profile: ClipProfile) -> None:
        self.profile = profile


def _ruzicka_weighted(a: tuple, b: tuple) -> float:
    """``_ruzicka_sorted`` on terms whose weights already include the IDF factor.

    ``min(wa, wb) * w`` equals ``min(wa * w, wb * w)`` bit for bit (rounding is monotone and w > 0),
    and likewise for max, so this returns exactly the same float with no dictionary lookups.
    """
    num = den = 0.0
    i = j = 0
    la, lb = len(a), len(b)
    while i < la and j < lb:
        ta, wa = a[i]
        tb, wb = b[j]
        if ta == tb:
            if wa < wb:
                num += wa
                den += wb
            else:
                num += wb
                den += wa
            i += 1
            j += 1
        elif ta < tb:
            den += wa
            i += 1
        else:
            den += wb
            j += 1
    while i < la:
        den += a[i][1]
        i += 1
    while j < lb:
        den += b[j][1]
        j += 1
    return num / den if den > 0 else 0.0


# The two redmean coefficients depend only on s = r1 + r2 (rbar = s / 2.0, exact), so they are tabulated
# with the very expressions _redmean evaluates.
_REDMEAN_RED = tuple(2.0 + (s / 2.0) / 256.0 for s in range(511))
_REDMEAN_BLUE = tuple(2.0 + (255.0 - s / 2.0) / 256.0 for s in range(511))


def _palette_weighted(pa: tuple, total_a: float, pb: tuple, total_b: float) -> float:
    """``_palette_similarity`` on palettes flattened to (r, g, b, share) with the share totals known.

    The squared redmean expression is the one inside ``_redmean`` (same operations, same order, with
    its two coefficients read from tables); ``sqrt`` is applied once to each row and column minimum
    instead of to every cell (sqrt is monotone, so min(sqrt(x)) == sqrt(min(x))).
    """
    red, blue = _REDMEAN_RED, _REDMEAN_BLUE
    inf = float("inf")
    column_min = [inf] * len(pb)
    acc_a = 0.0
    for p0, p1, p2, share in pa:
        row_min = inf
        j = 0
        for q0, q1, q2, _ in pb:
            s = p0 + q0
            dr, dg, db = p0 - q0, p1 - q1, p2 - q2
            x = red[s] * dr * dr + 4.0 * dg * dg + blue[s] * db * db
            if x < row_min:
                row_min = x
            if x < column_min[j]:
                column_min[j] = x
            j += 1
        acc_a += share * sqrt(row_min)
    acc_b = 0.0
    j = 0
    for _, _, _, share in pb:
        acc_b += share * sqrt(column_min[j])
        j += 1
    d = (acc_a / total_a + acc_b / total_b) / 2.0
    return max(0.0, 1.0 - d / _PALETTE_RANGE)


def _kernel(delta: float, sigma: float) -> float:
    z = delta / sigma
    return 1.0 / (1.0 + z * z)   # Cauchy kernel: no exp, portable


def _mean(values: Iterable[float | None]) -> float | None:
    total, count = 0.0, 0
    for v in values:          # plain left-to-right addition (never the compensated builtin sum)
        if v is not None:
            total += v
            count += 1
    return total / count if count else None


def sim_subjects(a: ClipProfile, b: ClipProfile, idf: dict[str, float]) -> float | None:
    if not (a.subjects and b.subjects):          # missing when EITHER clip lacks it (GRAVITY.md)
        return None
    return _ruzicka_sorted(a.subjects, b.subjects, idf)


def sim_keywords(a: ClipProfile, b: ClipProfile, idf: dict[str, float]) -> float | None:
    if not (a.keywords and b.keywords):
        return None
    return _ruzicka_sorted(a.keyword_items, b.keyword_items, idf)


def sim_context(a: ClipProfile, b: ClipProfile) -> float | None:
    parts = []
    if a.setting and b.setting:
        key = tuple(sorted((a.setting, b.setting)))
        parts.append(1.0 if a.setting == b.setting else _SETTING.get(key, 0.0))
    if a.environment and b.environment:
        key = tuple(sorted((a.environment, b.environment)))
        parts.append(1.0 if a.environment == b.environment else _ENVIRONMENT.get(key, 0.0))
    if a.time_of_day and b.time_of_day:
        ta, tb = _TIME.get(a.time_of_day), _TIME.get(b.time_of_day)
        if a.time_of_day == b.time_of_day:
            parts.append(1.0)
        elif ta is not None and tb is not None:
            parts.append(1.0 - abs(ta - tb) / 3.0)
        else:  # artificial_light against a natural time
            other = tb if ta is None else ta
            parts.append(0.5 if other == _TIME["night"] else 0.25)
    return _mean(parts)


def sim_mood(a: ClipProfile, b: ClipProfile) -> float | None:
    if not (a.moods and b.moods):
        return None
    def directed(x, y) -> float:
        acc = 0.0
        for m in x:
            va = _MOOD_VA[m]
            best = 0.0
            for n in y:
                vb = _MOOD_VA[n]
                dx, dy = va[0] - vb[0], va[1] - vb[1]
                best = max(best, max(0.0, 1.0 - sqrt(dx * dx + dy * dy) / _MOOD_RADIUS))
            acc += best
        return acc / len(x)
    return (directed(a.moods, b.moods) + directed(b.moods, a.moods)) / 2.0


def sim_color(a: ClipProfile, b: ClipProfile) -> float | None:
    parts = []
    if a.hue is not None and b.hue is not None and a.saturation is not None and b.saturation is not None:
        d = abs(a.hue - b.hue)
        d = min(d, 1.0 - d) * 2.0                        # circular, 0..1
        trust = min(1.0, sqrt(a.saturation * b.saturation) / _HUE_SAT_REF)
        parts.append(1.0 - trust * d)
    if a.palette and b.palette:
        parts.append(_palette_similarity(a.palette, b.palette))
    if a.palette_names and b.palette_names:
        parts.append(_palette_similarity([(_COLOR_RGB[n], 1.0) for n in a.palette_names],
                                         [(_COLOR_RGB[n], 1.0) for n in b.palette_names]))
    return _mean(parts)


def sim_tone(a: ClipProfile, b: ClipProfile) -> float | None:
    parts = []
    if a.luma is not None and b.luma is not None:
        parts.append(_kernel(a.luma - b.luma, _LUMA_SIGMA))
    if a.saturation is not None and b.saturation is not None:
        parts.append(_kernel(a.saturation - b.saturation, _SAT_SIGMA))
    return _mean(parts)


def sim_motion(a: ClipProfile, b: ClipProfile) -> float | None:
    parts = []
    if a.motion_level is not None and b.motion_level is not None:
        parts.append(1.0 - abs(a.motion_level - b.motion_level) / 3.0)
    if a.motion is not None and b.motion is not None:
        ma, mb = min(1.0, a.motion / _MOTION_FULL), min(1.0, b.motion / _MOTION_FULL)
        parts.append(1.0 - abs(ma - mb))
    return _mean(parts)


def sim_framing(a: ClipProfile, b: ClipProfile) -> float | None:
    parts = []
    if a.orientation and b.orientation:
        parts.append(1.0 if a.orientation == b.orientation else 0.4)
    if a.shot is not None and b.shot is not None:
        parts.append(1.0 - abs(a.shot - b.shot) / 2.0)
    return _mean(parts)


def sim_environment(a: ClipProfile, b: ClipProfile) -> float | None:
    if not (a.environment and b.environment):
        return None
    key = tuple(sorted((a.environment, b.environment)))
    return 1.0 if a.environment == b.environment else _ENVIRONMENT.get(key, 0.0)


def sim_shot(a: ClipProfile, b: ClipProfile) -> float | None:
    if a.shot is None or b.shot is None:
        return None
    return 1.0 - abs(a.shot - b.shot) / 2.0


def sim_orientation(a: ClipProfile, b: ClipProfile) -> float | None:
    if not (a.orientation and b.orientation):
        return None
    return 1.0 if a.orientation == b.orientation else 0.0


_SIMILARITY = {"context": sim_context, "mood": sim_mood, "color": sim_color, "tone": sim_tone, "motion": sim_motion,
               "framing": sim_framing, "environment": sim_environment, "shot": sim_shot, "orientation": sim_orientation}


@dataclass
class AffinityModel:
    """Pool-aware affinity: IDF tables come from the pool the scheduler sees.

    ``weights`` maps component name to a signed float in [-1, 1]; names left out weigh 0.
    """
    profiles: dict[str, ClipProfile]
    subject_idf: dict[str, float]
    keyword_idf: dict[str, float]
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    cache_size: int = DEFAULT_CACHE_SIZE
    memo_limit: int = DEFAULT_MEMO_SIZE
    _cache: "OrderedDict[tuple[str, str], int]" = field(default_factory=OrderedDict, repr=False)
    _plan: Any = field(default=None, repr=False)
    _prep: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.weights, Mapping):
            raise ValueError("affinity weights must be a mapping of component name to a number")
        for name, weight in self.weights.items():
            # a NaN fails the range test as well, and no float conversion happens (a huge int cannot overflow here)
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) \
                    or not WEIGHT_RANGE[0] <= weight <= WEIGHT_RANGE[1]:
                raise ValueError(f"affinity weight {name!r} must be a finite number in "
                                 f"{WEIGHT_RANGE[0]}..{WEIGHT_RANGE[1]}, not {weight!r}")
        unknown = sorted(set(self.weights) - set(ALL_COMPONENTS))
        if unknown:
            raise ValueError(f"unknown affinity components: {unknown}")
        self.weights_milli = {k: weight_milli(v) for k, v in sorted(self.weights.items())}
        self._active = [name for name, w in self.weights_milli.items() if w != 0]      # zero weights are never computed

    def components(self, a_id: str, b_id: str, names: Iterable[str] | None = None) -> dict[str, float | None]:
        a, b = self.profiles[a_id], self.profiles[b_id]
        out: dict[str, float | None] = {}
        for name in (ALL_COMPONENTS if names is None else names):
            if name == "subjects":
                out[name] = sim_subjects(a, b, self.subject_idf)
            elif name == "keywords":
                out[name] = sim_keywords(a, b, self.keyword_idf)
            else:
                out[name] = _SIMILARITY[name](a, b)
        return out

    def affinity_milli_uncached(self, a_id: str, b_id: str) -> int:
        """Reference path: the plain component functions, one pair, nothing shared between pairs.

        ``affinity`` uses ``affinity_milli_fast`` instead; a test asserts the two agree on every pair.
        """
        a, b = self.profiles[a_id], self.profiles[b_id]
        quantized: dict[str, int | None] = {}
        for name in self._active:
            if name == "subjects":
                value = sim_subjects(a, b, self.subject_idf)
            elif name == "keywords":
                value = sim_keywords(a, b, self.keyword_idf)
            else:
                value = _SIMILARITY[name](a, b)
            quantized[name] = None if value is None else quantize_component(value)
        return combine_milli(quantized, self.weights_milli)

    def affinity_milli_fast(self, a_id: str, b_id: str) -> int:
        """Same integer as ``affinity_milli_uncached``, computed from per-clip data prepared once.

        Per pool (lazily, on first use): every clip's terms already multiplied by their IDF weight,
        its palette with the share total, and its categorical tags interned. Per pair: categorical
        components (context, mood, environment, shot, orientation, framing, palette names) come
        from a memo keyed by the two interned tag combinations (a pure function of them, computed
        by the reference functions on the first miss); only the continuous ones are evaluated.
        Components are still quantised one by one and combined in integers, as in ``combine_milli``.
        """
        plan = self._plan
        if plan is None:
            plan = self._plan = self._build_plan()
        prep = self._prep
        pa, pb = prep[a_id], prep[b_id]
        num = self._prior_num
        den = self._prior_den
        for function, weight in plan:
            q = function(pa, pb)
            if q >= 0:
                if weight > 0:
                    num += weight * q
                    den += weight
                else:
                    num += -weight * (COMPONENT_SCALE - q)
                    den -= weight
        value = (2 * num + den * _DEN_UNIT) // (2 * den * _DEN_UNIT)
        return 0 if value < 0 else AFFINITY_SCALE if value > AFFINITY_SCALE else value

    # --- per-pool preparation for the fast path ---------------------------------------------
    def _build_plan(self) -> list[tuple[Any, int]]:
        profiles = self.profiles
        interned: dict[str, dict[Any, int]] = {}

        def intern(kind: str, key: Any) -> int:
            table = interned.setdefault(kind, {})
            return table.setdefault(key, len(table))

        prepared: dict[str, _Prep] = {}
        for clip_id, p in profiles.items():
            item = _Prep(p)
            item.ctx = intern("ctx", (p.setting, p.environment, p.time_of_day))
            item.mood = intern("mood", p.moods)
            item.env = intern("env", p.environment)
            item.shot_id = intern("shot", p.shot)
            item.orient = intern("orient", p.orientation)
            item.framing = intern("framing", (p.orientation, p.shot))
            item.names = intern("names", p.palette_names)
            item.subjects = tuple((t, w * self.subject_idf.get(t, 1.0)) for t, w in p.subjects)
            item.keywords = tuple((t, 1.0 * self.keyword_idf.get(t, 1.0)) for t in p.keywords)
            item.has_hue = p.hue is not None and p.saturation is not None
            item.hue, item.sat, item.luma, item.level = p.hue, p.saturation, p.luma, p.motion_level
            item.has_names = bool(p.palette_names)
            item.palette = tuple((r, g, b, share) for (r, g, b), share in p.palette)
            total = 0.0
            for _, _, _, share in item.palette:      # left to right, as _palette_similarity does
                total += share
            item.palette_total = total
            item.motion_scaled = None if p.motion is None else min(1.0, p.motion / _MOTION_FULL)
            prepared[clip_id] = item
        self._prep = prepared
        memo_limit = self.memo_limit

        def memoised(kind: str, field_name: str, compute) -> Any:
            memo: dict[tuple[int, int], int] = {}

            def component(x: "_Prep", y: "_Prep") -> int:
                key = (getattr(x, field_name), getattr(y, field_name))
                hit = memo.get(key)
                if hit is None:
                    value = compute(x.profile, y.profile)
                    hit = -1 if value is None else quantize_component(value)
                    if len(memo) >= memo_limit:
                        memo.clear()
                    memo[key] = hit
                return hit
            return component

        names_memo: dict[tuple[int, int], float | None] = {}
        names_limit = memo_limit

        def names_similarity(x: "_Prep", y: "_Prep") -> float | None:
            key = (x.names, y.names)
            value = names_memo.get(key, _MISSING)
            if value is not _MISSING:
                return value
            if x.has_names and y.has_names:
                value = _palette_similarity([(_COLOR_RGB[n], 1.0) for n in x.profile.palette_names],
                                            [(_COLOR_RGB[n], 1.0) for n in y.profile.palette_names])
            else:
                value = None
            if len(names_memo) >= names_limit:
                names_memo.clear()
            names_memo[key] = value
            return value

        def subjects(x: "_Prep", y: "_Prep") -> int:
            if not (x.subjects and y.subjects):
                return -1
            value = _ruzicka_weighted(x.subjects, y.subjects)
            q = int((value * COMPONENT_SCALE + 0.5) // 1)
            return 0 if q < 0 else COMPONENT_SCALE if q > COMPONENT_SCALE else q


        def keywords(x: "_Prep", y: "_Prep") -> int:
            if not (x.keywords and y.keywords):
                return -1
            value = _ruzicka_weighted(x.keywords, y.keywords)
            q = int((value * COMPONENT_SCALE + 0.5) // 1)
            return 0 if q < 0 else COMPONENT_SCALE if q > COMPONENT_SCALE else q


        def color(x: "_Prep", y: "_Prep") -> int:
            # sim_color with the same parts in the same order; _mean's left-to-right sum is kept.
            total = 0.0
            count = 0
            if x.has_hue and y.has_hue:
                d = abs(x.hue - y.hue)
                d = min(d, 1.0 - d) * 2.0
                trust = min(1.0, sqrt(x.sat * y.sat) / _HUE_SAT_REF)
                total += 1.0 - trust * d
                count += 1
            if x.palette and y.palette:
                total += _palette_weighted(x.palette, x.palette_total, y.palette, y.palette_total)
                count += 1
            names = names_similarity(x, y)
            if names is not None:
                total += names
                count += 1
            if not count:
                return -1
            value = total / count
            q = int((value * COMPONENT_SCALE + 0.5) // 1)
            return 0 if q < 0 else COMPONENT_SCALE if q > COMPONENT_SCALE else q

        def tone(x: "_Prep", y: "_Prep") -> int:
            total = 0.0
            count = 0
            if x.luma is not None and y.luma is not None:
                z = (x.luma - y.luma) / _LUMA_SIGMA
                total += 1.0 / (1.0 + z * z)
                count += 1
            if x.sat is not None and y.sat is not None:
                z = (x.sat - y.sat) / _SAT_SIGMA
                total += 1.0 / (1.0 + z * z)
                count += 1
            if not count:
                return -1
            value = total / count
            q = int((value * COMPONENT_SCALE + 0.5) // 1)
            return 0 if q < 0 else COMPONENT_SCALE if q > COMPONENT_SCALE else q

        def motion(x: "_Prep", y: "_Prep") -> int:
            total = 0.0
            count = 0
            if x.level is not None and y.level is not None:
                total += 1.0 - abs(x.level - y.level) / 3.0
                count += 1
            if x.motion_scaled is not None and y.motion_scaled is not None:
                total += 1.0 - abs(x.motion_scaled - y.motion_scaled)
                count += 1
            if not count:
                return -1
            value = total / count
            q = int((value * COMPONENT_SCALE + 0.5) // 1)
            return 0 if q < 0 else COMPONENT_SCALE if q > COMPONENT_SCALE else q

        builders = {
            "subjects": subjects, "keywords": keywords, "color": color, "tone": tone, "motion": motion,
            "context": memoised("context", "ctx", sim_context), "mood": memoised("mood", "mood", sim_mood),
            "framing": memoised("framing", "framing", sim_framing),
            "environment": memoised("environment", "env", sim_environment),
            "shot": memoised("shot", "shot_id", sim_shot),
            "orientation": memoised("orientation", "orient", sim_orientation),
        }
        prior = weight_milli(PRIOR_WEIGHT)
        self._prior_num = prior * (COMPONENT_SCALE // 2)
        self._prior_den = prior
        return [(builders[name], self.weights_milli[name]) for name in self._active]

    def affinity(self, a_id: str, b_id: str) -> int:
        """Symmetric milli-affinity in 0..1000 (bounded LRU cache)."""
        key = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
        cache = self._cache
        hit = cache.get(key)
        if hit is None:
            hit = self.affinity_milli_fast(*key)
            cache[key] = hit
            if len(cache) > self.cache_size:
                cache.popitem(last=False)
        else:
            cache.move_to_end(key)
        return hit


def _idf(documents: list[Iterable[str]]) -> dict[str, float]:
    """Square-root smoothed IDF: sqrt((1+M)/(1+df)); monotone like log-IDF, portable."""
    m = len(documents)
    df: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    return {t: sqrt((1.0 + m) / (1.0 + n)) for t, n in sorted(df.items())}


def build_affinity_model(records: list[dict[str, Any]], weights: Mapping[str, float] | None = None) -> AffinityModel:
    if weights is not None and not isinstance(weights, Mapping):
        raise ValueError("affinity weights must be a mapping of component name to a number")
    profiles = {}
    for record in records:
        prof = clip_profile(record)
        if prof.id in profiles:
            raise ValueError(f"duplicate clip id: {prof.id}")
        profiles[prof.id] = prof
    tagged = [p for p in profiles.values() if p.tagged]
    return AffinityModel(
        profiles=profiles,
        subject_idf=_idf([[t for t, _ in p.subjects] for p in tagged]),
        keyword_idf=_idf([p.keywords for p in tagged]),
        weights=dict(DEFAULT_WEIGHTS if weights is None else weights),
    )


def affinity(a: dict[str, Any], b: dict[str, Any], pool: list[dict[str, Any]] | None = None) -> float:
    """Convenience form affinity(a, b) in [0,1]; IDF from `pool` if given, else from {a, b}."""
    model = build_affinity_model(pool if pool is not None else [a, b])
    return model.affinity(str(a["id"]), str(b["id"])) / AFFINITY_SCALE
