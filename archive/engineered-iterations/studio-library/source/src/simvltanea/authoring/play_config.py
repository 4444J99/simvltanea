"""Play-mode configuration: how a composition plays, as validated data.

A play mode is a plain JSON-serialisable dictionary with four dials and a few guard sections::

    order      what the clips are ordered by (axis, direction, missing)
    path       how each loop travels along that order (shape and its parameters)
    relation   how simultaneous loops relate to each other (signed strength and weights)
    timing     holds, stagger, synchronisation, cooldown, recency, novelty, swaps
    exclusion  safety, privacy, minors, sensitivity, explicit ids, untagged policy
    limits     work budgets (events, candidates, render segments)
    seed       integer or string

``PARAMETERS`` is the single table that drives validation, defaults and
``describe_parameters()``, so a UI can render controls without hard-coding anything.
Named presets live in ``play_presets``; they are complete configurations of this shape.
Nothing here depends on a preset: the defaults below are only the starting values.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from math import isfinite
from typing import Any, Mapping

from .composition import MAX_SEGMENTS
from .gravity_affinity import ALL_COMPONENTS, DEFAULT_WEIGHTS, WEIGHT_RANGE
from .play_rng import draw64


class PlayError(ValueError):
    """A configuration, pool or schedule request that cannot be honoured."""


CLIP_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")      # same rule as composition.ID
PRIVACY_FLAGS = ("readable_text", "license_plate", "document_or_screen", "location_identifiable")
SHARING_LEVELS = ("low", "moderate", "high")         # analysis.privacy.sharing_sensitivity (tag schema v2)
UNTAGGED_POLICIES = ("allow", "exclude")
ORDER_AXES = ("none", "captured_at", "luma", "luma_spread", "saturation", "hue", "motion", "duration",
              "motion_level", "shot", "time_of_day")
ORDER_DIRECTIONS = ("ascending", "descending")
ORDER_MISSING = ("exclude", "end", "random")
SHAPES = ("random", "sequential", "converge", "diverge", "pingpong", "round", "playlist", "follow")
VOICE_SHAPES = tuple(s for s in SHAPES if s != "round")
CURSOR_SHAPES = ("sequential", "converge", "diverge", "pingpong")
TAGS = ("shot", "time_of_day", "motion_level", "environment", "setting")
MIN_HOLD = 0.25                  # seconds: hard floor for any hold, beat or swap interval
MAX_SECONDS = 1_000_000.0
MAX_ID_LIST = 10_000      # most ids in one id_list parameter (anchors, exclude_ids)

SECTIONS = ("order", "path", "relation", "timing", "exclusion", "limits")


def _p(section: str, name: str, kind: str, default: Any, description: str, **extra: Any) -> dict[str, Any]:
    return {"section": section, "name": name, "type": kind, "default": default,
            "description": description, **extra}


PARAMETERS: list[dict[str, Any]] = [
    # ---- order
    _p("order", "axis", "enum", "none", "What the clips are ordered by: none, capture time, a numeric local "
       "feature, or a tag ordinal. Ignored by the random, playlist and follow shapes.", choices=list(ORDER_AXES)),
    _p("order", "direction", "enum", "ascending", "ascending puts the lowest value (oldest) first; descending "
       "reverses the order; ignored when the axis is none, which is a seeded shuffle. Ties always break by clip id.", choices=list(ORDER_DIRECTIONS)),
    _p("order", "missing", "enum", "exclude", "Clips without a value on the axis: exclude them, put them at the end "
       "(sorted by id), or insert them at seeded random positions.", choices=list(ORDER_MISSING)),
    # ---- path
    _p("path", "shape", "enum", "random", "How each loop travels along the order. random: uniform (or relation-"
       "weighted) over free clips. sequential: walk the order. converge: loops start at the two ends and move toward "
       "each other. diverge: start in the middle, move toward both ends. pingpong: sweep end to end and back. round: a "
       "canon (loop k plays loop 0's voice k*delay_beats beats later). playlist: shuffled deal that exhausts the pool "
       "before any repeat. follow: each loop walks from its previous clip to a related one.", choices=list(SHAPES)),
    _p("path", "direction", "enum", "forward", "sequential/pingpong: travel along the order (forward) or against it "
       "(backward).", choices=["forward", "backward"]),
    _p("path", "step", "integer", 1, "Positions advanced per change (sequential, pingpong, converge, diverge).",
       min=1, max=50),
    _p("path", "wrap", "enum", "wrap", "At the end of the order (sequential) or of the outward travel (diverge): wrap "
       "jumps back to the start, bounce reverses, stop leaves the loop on its last clip.",
       choices=["wrap", "bounce", "stop"]),
    _p("path", "spread", "enum", "even", "sequential/pingpong start positions: even = evenly spaced along the order, "
       "together = side by side at the start. Not read by a round (its single voice always starts together).", choices=["even", "together"]),
    _p("path", "on_meet", "enum", "bounce", "converge, when a loop reaches the meeting point: bounce = reverse and "
       "diverge back out, restart = jump back to its end, hold = that loop keeps its clip, stop = every loop freezes "
       "at the first meeting.", choices=["bounce", "restart", "hold", "stop"]),
    _p("path", "groups", "enum", "alternate", "converge/diverge: how loops split between the two ends. alternate = "
       "loops take the ends in turn; halves = the first half takes one end, the rest the other. Not read by a round "
       "(its single voice alternates between the ends).",
       choices=["alternate", "halves"]),
    _p("path", "first_end", "enum", "low", "converge/diverge: the end (low = oldest/first, high = newest/last) that "
       "loop 0 takes; with an odd loop count that end gets the extra loop.", choices=["low", "high"]),
    _p("path", "window", "integer", 0, "Cursor shapes and playlist: 0 = exactly the next clip; k = choose among the "
       "next k+1 clips with the relation rule (chronological but gravity-flavoured). Ignored by random and follow, "
       "and by a round whose base is random, playlist or follow.", min=0, max=100),
    _p("path", "base", "enum", "sequential", "round only: the path shape of the base voice that loop 0 follows.",
       choices=list(VOICE_SHAPES)),
    _p("path", "voice", "enum", "clips", "round only: clips = every loop plays the same clips, delayed (needs "
       "delay_beats*beat_seconds >= hold); tags = every loop plays the same sequence of tag values on different clips.",
       choices=["clips", "tags"]),
    _p("path", "tag", "enum", "shot", "round with voice=tags: which single-valued tag forms the voice.",
       choices=list(TAGS)),
    _p("path", "delay_beats", "integer", 2, "round: loop k starts the voice k*delay_beats beats after loop 0.",
       min=1, max=64),
    _p("path", "beat_seconds", "number", 2.0, "round: length of a beat in seconds; the hold must be a whole number of "
       "beats and every change lands on the beat grid.", min=MIN_HOLD, max=3600.0),
    _p("path", "pins", "pin_list", [], "[loop id, clip id] pairs: that loop never changes. One pin per loop."),
    # ---- relation
    _p("relation", "strength", "number", 2.5, "Signed pull between simultaneous loops: positive attracts related "
       "clips (gravity), 0 is neutral, negative repels (opposites). Only used where a choice is scored; see "
       "\"Settings that have no effect\" in PLAY_MODES.md.", min=-4.0, max=4.0),
    _p("relation", "temperature", "number", 1.0, "Divides every score; higher means more random.", min=0.1, max=4.0),
    _p("relation", "independence", "number", 0.25, "0 = attend to the whole field of other loops; 1 = each loop only "
       "relates to the clip it is showing when the pick is made (the one being replaced). Ignored by the follow shape "
       "(which always relates each loop that way) and wherever no choice is scored.", min=0.0, max=1.0),
    _p("relation", "adjacency", "number", 0.5, "Extra weight for spatially neighbouring cells (both orientations "
       "averaged). Ignored by the follow shape and wherever no choice is scored.", min=0.0, max=1.0),
    _p("relation", "anchors", "id_list", [], "Clip ids that attract the whole field. Anchors only attract: anchor_pull is 0 to 2 and never negative, so an anchor cannot repel. At most 10,000 ids."),
    _p("relation", "anchor_pull", "number", 0.0, "Strength of the anchor term; 0 turns anchors off.", min=0.0, max=2.0),
    # ---- timing
    _p("timing", "hold_min", "number", 4.0, "Shortest stay of a clip on a loop, seconds.", min=MIN_HOLD, max=3600.0),
    _p("timing", "hold_max", "number", 12.0, "Longest stay, seconds (>= hold_min); drawn per change.",
       min=MIN_HOLD, max=3600.0),
    _p("timing", "stagger", "number", 0.5, "Minimum seconds between any two loops' changes (not used when "
       "synchronized).", min=0.0, max=3600.0),
    _p("timing", "synchronized", "boolean", False, "All loops change together on the same frame (stagger is not used). "
       "A round requires true but is not simultaneous: loop k changes k * delay_beats beats after loop 0, every "
       "change on the shared beat grid, and the flag has no other effect there."),
    _p("timing", "cooldown", "number", 30.0, "Hard minimum seconds before a clip may return; relaxed only when no "
       "other clip is free. Not used by the playlist shape (at any window), nor by a round with voice clips (the canon "
       "replays each clip on purpose).",
       min=0.0, max=MAX_SECONDS),
    _p("timing", "recency", "number", 0.6, "Soft penalty for recently shown clips. Only used where a choice is "
       "scored; not by a round with voice clips, nor by cursor shapes and playlist with window 0.", min=0.0, max=2.0),
    _p("timing", "recency_window", "number", 120.0, "Seconds over which the recency penalty fades (unused wherever recency is).",
       min=MIN_HOLD, max=MAX_SECONDS),
    _p("timing", "novelty", "number", 0.6, "Pressure toward under-shown clips (coverage). Only used where a choice "
       "is scored; not by a round with voice clips, nor by cursor shapes and playlist with window 0.",
       min=0.0, max=2.0),
    _p("timing", "swap_interval", "number", 0.0, "Seconds between gravity-driven swaps of two loops' clips; 0 = off "
       "(otherwise at least 0.25). Not available for ordered shapes.", min=0.0, max=MAX_SECONDS, zero_or_min=MIN_HOLD),
    # ---- exclusion
    _p("exclusion", "require_safety_clear", "boolean", True, "Clips need safety verdict 'clear' and no pending "
       "review; a record the tagger refused (an error code or needs_review) is excluded too. A clip with no safety "
       "verdict at all (never tagged) is excluded under either untagged_policy."),
    _p("exclusion", "exclude_privacy_flags", "flag_list", sorted(PRIVACY_FLAGS), "Privacy flags that exclude a clip. "
       "A listed flag that is present but malformed (not a bool, number or short string) excludes the clip under "
       "either untagged_policy; a missing one follows untagged_policy.",
       choices=list(PRIVACY_FLAGS)),
    _p("exclusion", "exclude_minors", "boolean", True, "Exclude clips where a minor is apparent. A malformed "
       "minors flag excludes the clip under either untagged_policy; a missing one follows untagged_policy."),
    _p("exclusion", "max_sharing_sensitivity", "enum", "moderate", "Clips rated above this are excluded.",
       choices=list(SHARING_LEVELS)),
    _p("exclusion", "untagged_policy", "enum", "allow", "What is done with what is UNKNOWN about a clip that "
       "carries a clear safety verdict: a missing or null sharing rating, a missing privacy flag, a missing minors "
       "flag. allow keeps the clip, exclude drops it. It also decides never-tagged clips when require_safety_clear is "
       "off; with require_safety_clear on, a clip with no safety verdict is excluded under either value.",
       choices=list(UNTAGGED_POLICIES)),
    _p("exclusion", "exclude_ids", "id_list", [], "Clip ids that are never shown (letter case is ignored; "
       "byte-identical copies under other ids are excluded too). An id that matches no clip in the pool is counted "
       "and warned about, and is an error when given with --exclude-id. At most 10,000 ids."),
    # ---- limits
    _p("limits", "max_events", "integer", 150_000, "Refuse a request whose estimated event count exceeds this (the "
       "repository's validate_state grows super-linearly with events).", min=100, max=1_000_000),
    _p("limits", "max_candidates", "integer", 400, "At most this many candidates are scored per change; a larger "
       "free pool is sampled deterministically by a seeded draw.", min=8, max=5000),
    _p("limits", "max_score_ops", "integer", 30_000_000, "Refuse a request whose estimated scheduling work "
       "(changes x candidates x loops affinity lookups) exceeds this.", min=10_000, max=10_000_000_000),
    _p("limits", "max_render_segments", "integer", MAX_SEGMENTS, "Your own render-segment limit, which can only be "
       f"LOWER than the offline renderer's fixed limit of {MAX_SEGMENTS} (composition.MAX_SEGMENTS). Whether a state "
       "is renderable is always judged against the renderer's limit; this value only decides when "
       "refuse_unrenderable refuses and when the command warns that you are over your own limit.",
       min=1, max=MAX_SEGMENTS),
    _p("limits", "refuse_unrenderable", "boolean", False, "Refuse (instead of warn) a state that needs more render "
       "segments than max_render_segments (at most the renderer's limit). The default keeps long states: they are "
       "still written and still compile with compile_plan, but the offline renderer will not render them."),
]
SEED_PARAMETER = _p("", "seed", "seed", 0, "Integer (within +/-(2**53 - 1), so JSON keeps it exact) or string; "
                    "identical (pool, seed, config) give a byte-identical state.")

_INDEX = {(p["section"], p["name"]): p for p in PARAMETERS}
_SECTION_KEYS = {s: [p["name"] for p in PARAMETERS if p["section"] == s] for s in SECTIONS}
_SECTION_KEYS["relation"].append("weights")
_SECTION_KEYS["relation"].sort()


def default_weights() -> dict[str, float]:
    return {name: float(DEFAULT_WEIGHTS.get(name, 0.0)) for name in ALL_COMPONENTS}


def default_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {s: {p["name"]: copy.deepcopy(p["default"]) for p in PARAMETERS if p["section"] == s}
                           for s in SECTIONS}
    cfg["relation"]["weights"] = default_weights()
    cfg["seed"] = SEED_PARAMETER["default"]
    return cfg


def describe_parameters() -> list[dict[str, Any]]:
    """Machine-readable metadata for every configurable field (for UIs and docs)."""
    out = []
    for p in PARAMETERS:
        entry = {"path": f"{p['section']}.{p['name']}", **copy.deepcopy(p)}
        out.append(entry)
    for name in ALL_COMPONENTS:
        out.append({"path": f"relation.weights.{name}", "section": "relation", "name": f"weights.{name}",
                    "type": "number", "default": default_weights()[name], "min": WEIGHT_RANGE[0],
                    "max": WEIGHT_RANGE[1],
                    "description": f"Signed weight of the {name} component: positive matches it, negative "
                                   "contrasts it, 0 ignores it."})
    out.append({"path": "seed", **copy.deepcopy(SEED_PARAMETER)})
    return out


# ------------------------------------------------------------------ validation

def _number(value: Any, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlayError(f"{where} must be a number in {low}..{high}")
    try:
        number = float(value)
    except OverflowError:
        raise PlayError(f"{where} must be a number in {low}..{high}") from None
    if not isfinite(number) or not low <= number <= high:
        raise PlayError(f"{where} must be a number in {low}..{high}")
    return number


def _integer(value: Any, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise PlayError(f"{where} must be an integer in {low}..{high}")
    if isinstance(value, float) and (not isfinite(value) or not value.is_integer()):
        raise PlayError(f"{where} must be an integer in {low}..{high}")
    if not low <= value <= high:
        raise PlayError(f"{where} must be an integer in {low}..{high}")
    return int(value)


def _list(value: Any, where: str) -> list:
    if not isinstance(value, (list, tuple)):          # a bare string would be split into characters
        raise PlayError(f"{where} must be a list, not {type(value).__name__}")
    return list(value)


def _ident(value: Any, where: str) -> str:
    if not isinstance(value, str) or not CLIP_ID.fullmatch(value):
        raise PlayError(f"{where} must be an id matching [A-Za-z0-9_-]{{1,80}}")
    return value


def _validate_value(spec: Mapping[str, Any], value: Any) -> Any:
    where = f"{spec['section']}.{spec['name']}"
    kind = spec["type"]
    if kind == "number":
        number = _number(value, where, spec["min"], spec["max"])
        floor = spec.get("zero_or_min")
        if floor is not None and 0 < number < floor:
            raise PlayError(f"{where} must be 0 or at least {floor}")
        return number
    if kind == "integer":
        return _integer(value, where, spec["min"], spec["max"])
    if kind == "boolean":
        if type(value) is not bool:
            raise PlayError(f"{where} must be true or false")
        return value
    if kind == "enum":
        if not isinstance(value, str) or value not in spec["choices"]:
            raise PlayError(f"{where} must be one of {spec['choices']}")
        return value
    if kind == "id_list":
        items = _list(value, where)
        if len(items) > MAX_ID_LIST:
            raise PlayError(f"{where} may list at most {MAX_ID_LIST} ids, not {len(items)}")
        return sorted({_ident(v, f"{where} item") for v in items})
    if kind == "flag_list":
        items = _list(value, where)
        if not all(isinstance(v, str) and v in spec["choices"] for v in items):
            raise PlayError(f"{where} items must be among {spec['choices']}")
        return sorted(set(items))
    if kind == "pin_list":
        pins = []
        for item in _list(value, where):
            pair = _list(item, f"{where} item")
            if len(pair) != 2:
                raise PlayError(f"{where} items must be [loop id, clip id]")
            pins.append([_ident(pair[0], f"{where} loop"), _ident(pair[1], f"{where} clip")])
        if len({p[0] for p in pins}) != len(pins):
            raise PlayError(f"{where}: two pins for one loop")
        if len({p[1] for p in pins}) != len(pins):
            raise PlayError(f"{where}: one clip pinned to two loops")
        return sorted(pins)
    raise AssertionError(kind)


def _merge(base: dict[str, Any], raw: Mapping[str, Any], where: str = "") -> dict[str, Any]:
    """Overlay ``raw`` on ``base`` (both nested dicts), rejecting unknown keys."""
    out = copy.deepcopy(base)
    if not isinstance(raw, Mapping):
        raise PlayError(f"{where or 'config'} must be an object")
    for key, value in raw.items():
        if key == "seed" and not where:
            out["seed"] = value
        elif not where and key in SECTIONS:
            if not isinstance(value, Mapping):
                raise PlayError(f"{key} must be an object")
            allowed = _SECTION_KEYS[key]
            unknown = sorted(set(map(str, value)) - set(allowed))
            if unknown:
                raise PlayError(f"{key}: unknown keys {unknown}; allowed {allowed}")
            for name, item in value.items():
                if key == "relation" and name == "weights":
                    if not isinstance(item, Mapping):
                        raise PlayError("relation.weights must be an object")
                    bad = sorted(set(map(str, item)) - set(ALL_COMPONENTS))
                    if bad:
                        raise PlayError(f"relation.weights: unknown components {bad}; allowed {list(ALL_COMPONENTS)}")
                    out[key][name].update(item)
                else:
                    out[key][name] = item
        else:
            raise PlayError(f"unknown config key {key!r}; allowed {list(SECTIONS) + ['seed']}")
    return out


MAX_SAFE_SEED = 2 ** 53 - 1      # beyond this a JSON number is rounded by JavaScript's JSON.parse


_CANONICAL_INTEGER = re.compile(r"0|-?[1-9][0-9]*")       # ASCII digits only; no sign but '-', no leading zeros


def seed_from_text(text: str) -> int | str:
    """The one rule for seed TEXT (``--seed``, ``--set seed=``, config and presets files).

    Text that is exactly an integer written the canonical way (an optional '-', no leading zeros, ASCII digits)
    and that a JSON number carries exactly (|n| <= 2**53 - 1) becomes that integer; everything else stays text.
    So ``7`` and ``-7`` are integers, while ``007``, ``-0``, ``+7``, `` 7``, ``1.5`` and a 20-digit number stay
    strings, and the same text gives the same seed whichever way it is passed. ``str(int(text)) == text`` is
    the test: ``-0`` is not how the integer 0 is written.
    """
    if len(text) <= 17 and _CANONICAL_INTEGER.fullmatch(text) and abs(int(text)) <= MAX_SAFE_SEED:
        return int(text)
    return text


def with_seed_text_rule(raw: Any) -> Any:
    """``raw`` (a config read from text) with a string ``seed`` passed through :func:`seed_from_text`."""
    if isinstance(raw, dict) and isinstance(raw.get("seed"), str):
        return {**raw, "seed": seed_from_text(raw["seed"])}
    return raw


def check_seed(seed: Any) -> Any:
    """The seed itself, or PlayError. Integers must stay exactly representable as a JSON number, and the seed
    must be serialisable: a string holding a lone surrogate (an invalid byte in argv decodes to one) cannot be
    written as UTF-8, so ``draw64`` could not hash it."""
    if isinstance(seed, bool) or not isinstance(seed, (int, str)) or (isinstance(seed, str) and len(seed) > 200):
        raise PlayError("seed must be an integer or a string of at most 200 characters")
    if isinstance(seed, int) and abs(seed) > MAX_SAFE_SEED:
        raise PlayError(f"an integer seed must be within +/-{MAX_SAFE_SEED} (2**53 - 1) so it survives JSON "
                        "unchanged; pass larger values as a string")
    try:
        draw64(seed)
    except (UnicodeError, ValueError, RecursionError):
        raise PlayError("seed text cannot be encoded as UTF-8 (it holds a lone surrogate or an invalid byte); "
                        "use valid text") from None
    return seed


def validate_config(raw: Mapping[str, Any] | None = None, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Overlay ``raw`` on ``base`` (default: the starting values), validate everything, return the full dict."""
    merged = _merge(copy.deepcopy(dict(base)) if base is not None else default_config(), {} if raw is None else raw)
    out: dict[str, Any] = {}
    for section in SECTIONS:
        out[section] = {p["name"]: _validate_value(p, merged[section][p["name"]])
                        for p in PARAMETERS if p["section"] == section}
    out["relation"]["weights"] = {
        name: _number(merged["relation"]["weights"][name], f"relation.weights.{name}", *WEIGHT_RANGE)
        for name in ALL_COMPONENTS}
    out["relation"] = dict(sorted(out["relation"].items()))
    out["seed"] = check_seed(merged["seed"])
    _check_consistency(out)
    return out


# The base voices of a round that can stop moving: base -> (setting, values that halt it, what to use instead).
HALTING_BASES = {"sequential": ("wrap", ("stop",), "wrap or bounce"),
                 "converge": ("on_meet", ("stop", "hold"), "bounce or restart"),
                 "diverge": ("wrap", ("stop",), "wrap or bounce")}


def _check_consistency(cfg: Mapping[str, Any]) -> None:
    t, path, order = cfg["timing"], cfg["path"], cfg["order"]
    if t["hold_max"] < t["hold_min"]:
        raise PlayError("timing.hold_max must be at least timing.hold_min")
    shape = path["shape"]
    if shape in ("converge", "diverge", "pingpong") and order["axis"] == "none":
        raise PlayError(f"path.shape {shape} needs an order: set order.axis")
    if path["base"] in ("converge", "diverge", "pingpong") and shape == "round" and order["axis"] == "none":
        raise PlayError(f"path.base {path['base']} needs an order: set order.axis")
    if t["swap_interval"] > 0 and (shape in CURSOR_SHAPES or shape == "round"):
        raise PlayError("timing.swap_interval would break an ordered path; set it to 0 for this shape")
    if shape == "round":
        if not t["synchronized"]:
            raise PlayError("path.shape round requires timing.synchronized = true")
        if t["hold_min"] != t["hold_max"]:
            raise PlayError("path.shape round requires timing.hold_min == timing.hold_max (the voice step)")
        if cfg["path"]["pins"]:
            raise PlayError("path.shape round does not allow pins")
        beat, hold = path["beat_seconds"], t["hold_min"]
        if not _is_multiple(hold, beat):
            raise PlayError("round: timing.hold_min must be a whole number of path.beat_seconds")
        if path["base"] in HALTING_BASES:
            setting, halting, advice = HALTING_BASES[path["base"]]
            if path[setting] in halting:
                raise PlayError(f"round: path.{setting}={path[setting]} lets the base voice ({path['base']}) halt, and a "
                                f"round whose voice has halted cannot continue (it would depend on the duration); "
                                f"use path.{setting} = {advice}")
        if path["voice"] == "clips" and path["delay_beats"] * beat < hold:
            raise PlayError("round with voice=clips needs delay_beats * beat_seconds >= hold, otherwise the same "
                            "clip would be on two loops at once")


def _is_multiple(value: float, unit: float) -> bool:
    ratio = value / unit
    return abs(ratio - round(ratio)) < 1e-9 and round(ratio) >= 1


# ------------------------------------------------------------------ serialisation, digest, overrides

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def config_digest(cfg: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(cfg)).hexdigest()


def config_to_json(cfg: Mapping[str, Any]) -> str:
    return json.dumps(cfg, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def config_from_json(text: str, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError):
        raise PlayError("config is not valid JSON") from None
    return validate_config(with_seed_text_rule(raw), base)


def apply_set(raw: dict[str, Any], assignment: str) -> dict[str, Any]:
    """Return ``raw`` with ``section.key=value`` applied (value is JSON, else a bare string)."""
    target, sep, text = assignment.partition("=")
    if not sep or not target:
        raise PlayError("--set takes section.key=value")
    out = copy.deepcopy(raw)
    parts = target.split(".")
    if parts == ["seed"]:
        # seed text follows seed_from_text, not JSON: 007 and -0 stay text, 1e3 is not a float. A quoted JSON
        # string ('seed="abc"') is still read as that string.
        value: Any = text
        if text.startswith('"'):
            try:
                decoded = json.loads(text)
            except (ValueError, RecursionError):
                decoded = None
            value = decoded if isinstance(decoded, str) else text
        out["seed"] = seed_from_text(value)
        return out
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        value = text
    if len(parts) == 2 and parts[0] in SECTIONS:
        out.setdefault(parts[0], {})[parts[1]] = value
    elif len(parts) == 3 and parts[:2] == ["relation", "weights"]:
        out.setdefault("relation", {}).setdefault("weights", {})[parts[2]] = value
    else:
        raise PlayError(f"--set {target!r}: use section.key (sections: {list(SECTIONS)}), "
                        "relation.weights.<component> or seed")
    return out
