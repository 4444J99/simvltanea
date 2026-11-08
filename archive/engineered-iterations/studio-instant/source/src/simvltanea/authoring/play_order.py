"""Ordering of the eligible clips: what the clips are ordered by, and where unknowns go."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from math import isfinite
from typing import Any, Mapping

from .play_config import PlayError
from .play_rng import draw64, shuffled

_ORDINALS = {
    "motion_level": {"still": 0, "subtle": 1, "moderate": 2, "intense": 3},
    "shot": {"close_up": 0, "medium": 1, "wide": 2},
    "time_of_day": {"day": 0, "golden_hour": 1, "dusk": 2, "night": 3},   # artificial_light has no place on it
}
_FEATURES = ("luma", "luma_spread", "saturation", "hue", "motion")


def parse_captured_at(value: Any) -> int | None:
    """ISO 8601 text to whole epoch seconds (UTC; a missing offset is read as UTC), else None."""
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        return None
    text = value.strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00") if text.endswith("Z") else text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return int(moment.timestamp())
    except (ValueError, OverflowError, OSError):
        return None


def _number(value: Any) -> Fraction | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return Fraction(value) if isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def axis_value(record: Mapping[str, Any], axis: str) -> Fraction | int | None:
    """The record's value on ``axis`` or None when it has none. Free text is never read."""
    if axis == "captured_at":
        return parse_captured_at(record.get("captured_at"))
    if axis in _ORDINALS:
        analysis = record.get("analysis")
        tag = analysis.get(axis) if isinstance(analysis, dict) else None
        return _ORDINALS[axis].get(tag) if isinstance(tag, str) else None
    if axis == "duration":
        features = record.get("features")
        value = _number(features.get("duration")) if isinstance(features, dict) else None
        if value is None:
            raw = record.get("duration")
            try:
                value = _number(raw) if not isinstance(raw, str) else Fraction(raw)
            except (ValueError, ZeroDivisionError):
                value = None
        return value
    if axis in _FEATURES:
        features = record.get("features")
        return _number(features.get(axis)) if isinstance(features, dict) else None
    raise PlayError(f"unknown order axis {axis!r}")


def build_order(records: list[dict[str, Any]], order: Mapping[str, Any], seed: Any) -> tuple[list[str], int]:
    """(clip ids in play order, number of clips dropped for lacking the axis).

    axis none: a seeded shuffle (a fixed permutation). Otherwise ascending or descending by
    value with ties broken by clip id (ascending in both directions); clips lacking the value are
    dropped (exclude), appended sorted by id (end) or inserted at seeded positions (random).
    """
    ids = sorted(str(r["id"]) for r in records)
    axis = order["axis"]
    if axis == "none":
        return shuffled(ids, seed, "order-none"), 0
    known, missing = [], []
    for record in records:
        value = axis_value(record, axis)
        (known if value is not None else missing).append((value, str(record["id"])))
    sign = 1 if order["direction"] == "ascending" else -1
    seq = [cid for _, cid in sorted(known, key=lambda kv: (sign * kv[0], kv[1]))]
    missing_ids = sorted(cid for _, cid in missing)
    policy = order["missing"]
    if policy == "end":
        seq += missing_ids
    elif policy == "random":
        for cid in missing_ids:
            seq.insert(draw64(seed, "missing", cid) % (len(seq) + 1), cid)
    return seq, (len(missing_ids) if policy == "exclude" else 0)
