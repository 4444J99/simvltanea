"""Gravity: the compatibility entry point over the play-mode engine.

Gravity is one play mode among several (see docs/architecture/PLAY_MODES.md): the ``random`` path
shape with a positive relation strength. ``schedule_gravity`` keeps the earlier signature and is a
thin wrapper that maps ``GravityParams`` onto a play-mode configuration and calls
``play_engine.schedule_play``; with the ``sticky`` values it reproduces the earlier output byte for
byte. All determinism, exclusion and encoding rules live in the ``play_*`` modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .play_config import (PRIVACY_FLAGS, SHARING_LEVELS, UNTAGGED_POLICIES, PlayError, validate_config)
from .play_encode import PERIOD, Schedule, _schema_pick, base_state_for, encode_state  # noqa: F401
from .play_engine import adjacency_milli, build_schedule as _build_schedule, schedule_play  # noqa: F401
from .play_pool import eligible_pool as _eligible_pool
from .play_rng import GRAVITY_RNG, MANTISSA, draw64, weighted_pick  # noqa: F401

GravityError = PlayError
BITS_PER_UNIT = 8

# Named strengths; "sticky" is the default (measured about 2x same-theme pairs at N=5).
GRAVITY_PRESETS: dict[str, dict[str, float]] = {
    "drift": {"gravity": 1.0, "temperature": 1.0},
    "sticky": {"gravity": 2.5, "temperature": 1.0},
    "magnetic": {"gravity": 4.0, "temperature": 0.5},
}
DEFAULT_PRESET = "sticky"


@dataclass(frozen=True)
class GravityParams:
    gravity: float = 2.5            # -4..4   signed pull toward (or away from) clips related to what is on screen
    temperature: float = 1.0        # 0.1..4  divides every logit; high = more random
    independence: float = 0.25      # 0..1    0: attend to the whole field; 1: follow own loop's thread
    adjacency: float = 0.5          # 0..1    extra weight for spatial neighbours (both orientations)
    hold_min: float = 4.0           # seconds a clip stays on a loop, lower bound (at least 0.25)
    hold_max: float = 12.0          # seconds, upper bound (per-change draw, per-loop independent)
    stagger: float = 0.5            # seconds; no two loops change within this gap
    cooldown: float = 30.0          # seconds; hard minimum before a clip may return (auto-relaxed)
    recency: float = 0.6            # 0..2    soft penalty that decays over recency_window
    recency_window: float = 120.0   # seconds
    novelty: float = 0.6            # 0..2    coverage pressure against over-shown clips
    anchor_pull: float = 0.0        # 0..2    attraction toward anchors
    anchors: tuple[str, ...] = ()
    pins: tuple[tuple[str, str], ...] = ()      # (loop_id, clip_id): that loop never changes
    exclude_ids: tuple[str, ...] = ()
    require_safety_clear: bool = True
    exclude_privacy_flags: tuple[str, ...] = PRIVACY_FLAGS
    exclude_minors: bool = True
    max_sharing_sensitivity: str = "moderate"
    untagged_policy: str = "allow"
    swap_interval: float = 0.0      # seconds between spatial swap considerations; 0 = off

    def __post_init__(self) -> None:
        self.to_config()            # raises GravityError with a clear message when anything is invalid

    def to_config(self, weights: dict[str, float] | None = None) -> dict[str, Any]:
        relation: dict[str, Any] = {"strength": self.gravity, "temperature": self.temperature,
                                    "independence": self.independence, "adjacency": self.adjacency,
                                    "anchors": self.anchors, "anchor_pull": self.anchor_pull}
        if weights is not None:
            relation["weights"] = weights
        return validate_config({
            "path": {"shape": "random", "pins": self.pins},
            "relation": relation,
            "timing": {"hold_min": self.hold_min, "hold_max": self.hold_max, "stagger": self.stagger,
                       "cooldown": self.cooldown, "recency": self.recency, "recency_window": self.recency_window,
                       "novelty": self.novelty, "swap_interval": self.swap_interval},
            "exclusion": {"require_safety_clear": self.require_safety_clear,
                          "exclude_privacy_flags": self.exclude_privacy_flags, "exclude_minors": self.exclude_minors,
                          "max_sharing_sensitivity": self.max_sharing_sensitivity,
                          "untagged_policy": self.untagged_policy, "exclude_ids": self.exclude_ids}})

    @classmethod
    def from_preset(cls, name: str = DEFAULT_PRESET, **overrides: Any) -> "GravityParams":
        if name not in GRAVITY_PRESETS:
            raise GravityError(f"unknown preset {name!r}; choose from {sorted(GRAVITY_PRESETS)}")
        return cls(**{**GRAVITY_PRESETS[name], **overrides})


def eligible_pool(pool: list[dict[str, Any]], params: GravityParams) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (eligible records sorted by id, {excluded_id: reason}) for the exclusion settings of ``params``."""
    return _eligible_pool(pool, params.to_config()["exclusion"])


def schedule_gravity(pool: list[dict[str, Any]], n: int, params: GravityParams | None = None,
                     duration_seconds: float = 60, fps: int = 24, seed: Any = 0,
                     base_state: dict[str, Any] | None = None,
                     weights: dict[str, float] | None = None) -> dict[str, Any]:
    """(pool, N, params, duration, fps, seed) -> {state, schedule, model, adjacency, order, excluded, config, report}.

    A thin wrapper over ``schedule_play`` with the ``random`` path shape. ``params`` defaults to the
    "sticky" preset. The returned state has passed ``validate_state``. Fails with ``GravityError``
    (never with filler or duplicated clips) when fewer than ``n`` eligible clips exist.
    """
    params = params if params is not None else GravityParams.from_preset()
    return schedule_play(pool, n, params.to_config(weights), duration_seconds, fps, seed, base_state)


def build_schedule(model: Any, eligible: list[str], loop_ids: list[str], adjacency: dict[tuple[str, str], int],
                   params: GravityParams, frames: int, fps: int, seed: Any) -> Schedule:
    """Schedule only (no encoding), with the earlier signature; used by statistics and tests."""
    return _build_schedule(model, eligible, eligible, loop_ids, adjacency, params.to_config(), frames, fps, seed)
