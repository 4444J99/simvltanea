"""Named play modes: saved configurations, nothing more.

``PRESET_TABLE`` lists, per name, a description and the values that differ from the starting
values of ``play_config`` (which are exactly the ``sticky`` preset). ``PRESETS`` holds every preset
resolved to a complete, validated configuration. A user adds or overrides presets with a JSON
file (``load_presets_file``) shaped ``{"name": {"description": "...", "config": {...partial...}}}``
and selects them by name; any single value can be overridden afterwards with ``apply_set``.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from .play_config import PlayError, validate_config, with_seed_text_rule

_NEUTRAL = {"strength": 0.0}          # no relation pull at all
_PLAIN = {"novelty": 0.0, "recency": 0.0, "cooldown": 0.0}     # ordered presets: the order is the rule
_CHRONO = {"order": {"axis": "captured_at"}, "relation": _NEUTRAL, "timing": _PLAIN}

PRESET_TABLE: dict[str, dict[str, Any]] = {
    "random": {
        "description": "Totally random: uniform over free clips, no immediate repeat, cooldown honoured.",
        "config": {"relation": _NEUTRAL, "timing": {"novelty": 0.0, "recency": 0.0}}},
    "chronological": {
        "description": "Oldest to newest by capture time; loops start evenly spaced along the timeline and wrap.",
        "config": {**_CHRONO, "path": {"shape": "sequential"}}},
    "reverse_chronological": {
        "description": "Newest to oldest by capture time.",
        "config": {**_CHRONO, "order": {"axis": "captured_at", "direction": "descending"},
                   "path": {"shape": "sequential"}}},
    "oldest_meets_newest": {
        "description": "Loops alternate between the oldest and newest ends and move toward each other, meet at the "
                       "middle of the order (for any loop count), then bounce back out.",
        "config": {**_CHRONO, "path": {"shape": "converge", "first_end": "low", "on_meet": "bounce"}}},
    "newest_meets_oldest": {
        "description": "The same, with loop 0 starting at the newest end (an odd loop count gives that end the "
                       "extra loop).",
        "config": {**_CHRONO, "path": {"shape": "converge", "first_end": "high", "on_meet": "bounce"}}},
    "round_clips": {
        "description": "A round (canon) in time: loop 0 walks the timeline and each later loop plays the same clips "
                       "3 beats (6 s) after the one before. Nothing in it is random, so every seed shows the same clips.",
        "config": {**_CHRONO, "path": {"shape": "round", "base": "sequential", "voice": "clips", "delay_beats": 3,
                                        "beat_seconds": 2.0},
                   "timing": {**_PLAIN, "synchronized": True, "hold_min": 4.0, "hold_max": 4.0}}},
    "round_tags": {
        "description": "A round of tags: every loop plays the same sequence of shot sizes, each loop on different "
                       "clips of that size.",
        "config": {"path": {"shape": "round", "base": "random", "voice": "tags", "tag": "shot", "delay_beats": 3,
                            "beat_seconds": 2.0},
                   "relation": {"strength": 1.0},
                   "timing": {**_PLAIN, "synchronized": True, "hold_min": 4.0, "hold_max": 4.0}}},
    "opposites": {
        "description": "Repel: clips unlike what is already on screen are favoured (negative strength). It tilts the "
                       "odds toward unlike clips; it does not choose the least related one (see GRAVITY.md).",
        "config": {"relation": {"strength": -2.5}}},
    "city_vs_nature": {
        "description": "Match colour and tone but contrast environment: urban beside nature.",
        "config": {"relation": {"strength": 4.0, "temperature": 0.5, "weights": {
            "subjects": 0.0, "keywords": 0.0, "context": 0.0, "mood": 0.0, "color": 0.5, "tone": 0.3,
            "motion": 0.0, "framing": 0.0, "environment": -1.0}}}},
    "near_vs_far": {
        "description": "Contrast shot size: close-ups beside wide shots, everything else neutral.",
        "config": {"relation": {"strength": 4.0, "temperature": 0.5, "weights": {
            "subjects": 0.0, "keywords": 0.0, "context": 0.0, "mood": 0.0, "color": 0.0, "tone": 0.0,
            "motion": 0.0, "framing": 0.0, "shot": -1.0}}}},
    "drift": {
        "description": "Mild gravity: related clips are slightly favoured (about 1.3 times uniform at N=5).",
        "config": {"relation": {"strength": 1.0}}},
    "sticky": {
        "description": "Gravity: related clips tend to appear together (about 2.5 times uniform at N=5). The "
                       "starting values of every setting.",
        "config": {}},
    "magnetic": {
        "description": "Strong gravity: tight clusters of related clips (about 4.8 times uniform at N=5).",
        "config": {"relation": {"strength": 4.0, "temperature": 0.5}}},
    "calm_to_intense": {
        "description": "Ordered by measured motion, calm to intense and back (bounce), gravity-flavoured over a "
                       "window of 5 clips.",
        "config": {"order": {"axis": "motion"}, "relation": {"strength": 1.0}, "timing": _PLAIN,
                   "path": {"shape": "sequential", "wrap": "bounce", "spread": "together", "window": 4}}},
    "dark_to_light": {
        "description": "Ordered by luma, dark to light, loops side by side, gravity-flavoured over 5 clips.",
        "config": {"order": {"axis": "luma"}, "relation": {"strength": 1.0}, "timing": _PLAIN,
                   "path": {"shape": "sequential", "spread": "together", "window": 4}}},
    "rainbow": {
        "description": "Ordered by hue around the colour wheel, loops side by side, wrapping.",
        "config": {"order": {"axis": "hue"}, "relation": _NEUTRAL, "timing": _PLAIN,
                   "path": {"shape": "sequential", "spread": "together", "window": 2}}},
}


def resolve_table(table: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for name, entry in table.items():
        if not isinstance(name, str) or not name or len(name) > 60 or not name.replace("_", "").replace("-", "").isalnum():
            raise PlayError("preset names use letters, digits, '_' and '-' (at most 60)")
        if not isinstance(entry, Mapping) or not isinstance(entry.get("config"), Mapping):
            raise PlayError(f"preset {name!r} needs a 'config' object")
        if not isinstance(entry.get("description", ""), str):
            raise PlayError(f"preset {name!r}: description must be a string")
        try:
            out[name] = validate_config(entry["config"])
        except PlayError as exc:
            raise PlayError(f"preset {name!r}: {exc}") from None
    return out


PRESETS: dict[str, dict[str, Any]] = resolve_table(PRESET_TABLE)
DEFAULT_PRESET = "sticky"       # pending owner decision; sticky reproduces the earlier gravity behaviour


def descriptions(table: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, str]:
    return {name: entry.get("description", "") for name, entry in (table or PRESET_TABLE).items()}


def load_presets_file(text: str) -> dict[str, dict[str, Any]]:
    """Parse a user presets file into a table (same shape as ``PRESET_TABLE``); raises PlayError."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise PlayError("presets file is not valid JSON") from None
    if not isinstance(data, dict):
        raise PlayError("presets file must be an object of name -> {description, config}")
    data = {name: ({**entry, "config": with_seed_text_rule(entry["config"])}      # seed text: one rule everywhere
                   if isinstance(entry, dict) and isinstance(entry.get("config"), dict) else entry)
            for name, entry in data.items()}
    resolve_table(data)          # validate now so errors name the preset
    return data


def merged_table(user: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Built-in presets with user presets added or overriding by name."""
    out = {name: copy.deepcopy(entry) for name, entry in PRESET_TABLE.items()}
    for name, entry in (user or {}).items():
        out[name] = copy.deepcopy(dict(entry))
    return out


def get_preset(name: str, table: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    resolved = resolve_table(table) if table is not None else PRESETS
    if name not in resolved:
        raise PlayError(f"unknown mode {name!r}; choose from {sorted(resolved)}")
    return copy.deepcopy(resolved[name])
