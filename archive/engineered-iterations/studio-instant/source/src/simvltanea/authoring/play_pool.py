"""Eligibility: which records may ever be shown. Everything downstream is built from the survivors.

An excluded clip never reaches the affinity model, an order, a bank, a source or an event.
Exclusion also follows content: the sha256 of every record excluded for ANY reason is collected,
and every other record carrying one of those digests is excluded too (the same media imported
twice under two ids), with a reason that does not name the other record. No free text from a tag
record (captions, notes, reasons, error messages) is ever read.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Iterable, Mapping

from .play_config import CLIP_ID, SHARING_LEVELS, PlayError

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_DURATION = 1_000_000          # seconds; anything longer is not a clip
MIN_CLIP_SECONDS = Fraction(1, 24)  # one frame at 24 fps: anything shorter is not a usable clip
MIN_CLIP_TOLERANCE = Fraction(1, 10 ** 6)   # a decimal receipt rounds (0.041667 for one frame); allow that much slack
MAX_FLAG_TEXT = 40                # a yes-or-no flag written as text is at most this long
NEAR_MISS_CHECKS = 200            # at most this many unmatched ids are compared with the pool for the near-miss count


def _section(analysis: dict[str, Any], key: str) -> dict[str, Any]:
    value = analysis.get(key)
    return value if isinstance(value, dict) else {}


def _norm_sha(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if SHA256.fullmatch(text) else None


norm_sha256 = _norm_sha          # the one normalisation of a digest (tools/media reads receipts with it)


def media_problem(record: dict[str, Any]) -> str | None:
    """Why a record cannot be encoded as a source (it is then excluded, never guessed)."""
    sha = record.get("sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        return "media_sha256"
    try:
        duration = record["duration"]
        if isinstance(duration, bool) or not isinstance(duration, (int, float, str)):
            return "media_duration"
        text = str(duration)
        rough = Decimal(text)                    # cheap range test first: Fraction("1e999999999") would build a huge integer
        if not rough.is_finite() or not Decimal("0.04") <= rough <= MAX_DURATION:
            return "media_duration"
        seconds = Fraction(text)
        if not MIN_CLIP_SECONDS * (1 - MIN_CLIP_TOLERANCE) <= seconds <= MAX_DURATION:
            return "media_duration"
    except (KeyError, ValueError, ZeroDivisionError, OverflowError, InvalidOperation):
        return "media_duration"
    path = record.get("path")
    if path is not None and not isinstance(path, str):
        return "media_path"
    return None


_ABSENT = object()


def _section_invalid(analysis: dict[str, Any], key: str) -> bool:
    """True when the section is PRESENT but is not an object (intake leaves a null in its place)."""
    return key in analysis and not isinstance(analysis[key], dict)


def _flag_state(section: Any, key: str) -> str:
    """``absent`` / ``invalid`` / ``set`` / ``clear`` for one yes-or-no flag of a tag section.

    A flag that is present but is not a bool, a number or a short string (intake leaves a null in its
    place) is ``invalid``: it is never read as permission. A flag that is missing is ``absent``.
    """
    value = section.get(key, _ABSENT) if isinstance(section, dict) else _ABSENT
    if value is _ABSENT:
        return "absent"
    if not isinstance(value, (bool, int, float, str)):
        return "invalid"
    if isinstance(value, str) and len(value) > MAX_FLAG_TEXT:
        return "invalid"
    return "set" if value else "clear"


def exclusion_reason(record: dict[str, Any], exclusion: Mapping[str, Any]) -> str | None:
    """The first reason this record alone is not allowed, or None.

    A record with no safety verdict at all (untagged) is excluded whenever ``require_safety_clear`` is on.
    ``untagged_policy`` then decides only what is *unknown* about a record that does carry a clear verdict
    (the sharing rating, a privacy flag, the minors flag), and untagged clips when the requirement is off.
    A value that is present but malformed is excluded under every policy.
    """
    policy = exclusion["untagged_policy"]
    strict = exclusion["require_safety_clear"]
    if strict and (record.get("needs_review") or record.get("error") is not None):
        return "safety"              # before the untagged branch: a refused or unparsed record is never shown
    analysis = record.get("analysis")
    if analysis is None:
        return "untagged" if strict or policy == "exclude" else None
    if not isinstance(analysis, dict) or not analysis:
        # A tag record existed but nothing usable survived: not "untagged", and never silently allowed.
        if strict:
            return "safety"
        return "untagged" if policy == "exclude" else None
    if strict and _section(analysis, "safety").get("verdict") != "clear":
        return "safety"
    if _section_invalid(analysis, "privacy"):
        return "privacy_invalid"             # a malformed section is never read as "no flags set"
    privacy = _section(analysis, "privacy")
    states = {flag: _flag_state(privacy, flag) for flag in exclusion["exclude_privacy_flags"]}
    if "invalid" in states.values():
        return "privacy_invalid"
    if "set" in states.values():
        return "privacy"
    if exclusion["exclude_minors"] and _section_invalid(analysis, "people"):
        return "minors_invalid"
    minors = _flag_state(analysis.get("people"), "minors_apparent") if exclusion["exclude_minors"] else "clear"
    if minors == "invalid":
        return "minors_invalid"
    if minors == "set":
        return "minors"
    if policy == "exclude":
        if "absent" in states.values():
            return "privacy_unknown"         # nothing says whether this flag applies
        if minors == "absent":
            return "minors_unknown"
    level = privacy.get("sharing_sensitivity")
    if level is None or level == "":
        # Tag schema v1 or an incomplete record: sensitivity is unknown, so the untagged policy decides.
        return "sharing_unknown" if policy == "exclude" else None
    level = level.strip().lower() if isinstance(level, str) else None
    if level not in SHARING_LEVELS:
        return "sharing_invalid"           # a malformed rating is never read as permission
    if SHARING_LEVELS.index(level) > SHARING_LEVELS.index(exclusion["max_sharing_sensitivity"]):
        return "sharing_sensitivity"
    return None


def unmatched_exclude_ids(exclude_ids: Iterable[str], known_ids: Iterable[str]) -> tuple[int, int]:
    """(how many ids match no known clip, how many of those are one edit away from a known id).

    Ids compare case-insensitively. Counts only: the ids themselves are never returned or named.
    """
    known = {str(i).casefold() for i in known_ids}
    missing = sorted({i.casefold() for i in exclude_ids} - known)
    by_length: dict[int, list[str]] = {}
    for clip in known:
        by_length.setdefault(len(clip), []).append(clip)
    near = sum(1 for m in missing[:NEAR_MISS_CHECKS]
               if any(_one_edit(m, k) for length in (len(m) - 1, len(m), len(m) + 1) for k in by_length.get(length, ())))
    return len(missing), near


def _one_edit(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` differ by exactly one substitution, insertion or deletion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def eligible_pool(pool: list[dict[str, Any]], exclusion: Mapping[str, Any],
                  extra_excluded_shas: Iterable[Any] = ()) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (eligible records sorted by id, {excluded_id: reason}). ``exclusion`` is the config's section.

    ``extra_excluded_shas`` are digests of media that must stay hidden although no record of the pool
    carries them (for example the receipt of an excluded id whose tag record is missing).
    """
    ids = []
    for record in pool:
        if not isinstance(record, dict) or "id" not in record:
            raise PlayError("every pool record must be an object with an id")
        ids.append(str(record["id"]))
    for cid in ids:
        if not CLIP_ID.fullmatch(cid):
            raise PlayError("clip ids must match [A-Za-z0-9_-]{1,80}")
    if len(set(ids)) != len(ids):
        raise PlayError("duplicate clip id in pool")
    skip_ids = {i.casefold() for i in exclusion["exclude_ids"]}
    excluded: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    excluded_shas: set[str] = {sha for sha in map(_norm_sha, extra_excluded_shas) if sha}
    for record in sorted(pool, key=lambda r: str(r["id"])):
        cid = str(record["id"])
        try:
            reason = "exclude_ids" if cid.casefold() in skip_ids else (exclusion_reason(record, exclusion) or media_problem(record))
        except Exception:                      # one malformed record must never stop a run
            reason = "malformed_record"
        if reason:
            excluded[cid] = reason
            try:
                sha = _norm_sha(record.get("sha256"))
            except Exception:
                sha = None
            if sha:
                excluded_shas.add(sha)
        else:
            candidates.append(record)
    keep, seen = [], set()
    for record in candidates:
        cid = str(record["id"])
        if record["sha256"] in excluded_shas:
            excluded[cid] = "excluded_media"
        elif record["sha256"] in seen:
            excluded[cid] = "duplicate_bytes"
        else:
            seen.add(record["sha256"])
            keep.append(record)
    return keep, excluded
