"""Shared helpers for the play-mode tests (contains no tests): schedules, statistics, ranks.

Everything works on the synthetic pool of ``test_gravity_pool``; nothing here is private data.
"""
from __future__ import annotations

import bisect
import copy
import contextlib
import hashlib
import signal
from functools import lru_cache
from typing import Any

from simvltanea.authoring import composition as c
from simvltanea.authoring.play_config import validate_config
from simvltanea.authoring.play_engine import schedule_play
from simvltanea.authoring.play_presets import PRESETS
from simvltanea.authoring.test_gravity_pool import make_pool

FPS = 24
PLAIN = {"novelty": 0.0, "recency": 0.0, "cooldown": 0.0}


@contextlib.contextmanager
def time_limit(seconds: int):
    """Fail instead of hanging: raise ``TimeoutError`` when the block runs longer than ``seconds`` (Unix main thread)."""
    def expired(signum, frame):
        raise TimeoutError(f"still running after {seconds} s")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@lru_cache(maxsize=None)
def pool_of(size: int = 120) -> tuple[dict[str, Any], ...]:
    return tuple(make_pool(size))


def cfg(base: str | None = "sticky", **sections: Any) -> dict[str, Any]:
    """A complete validated configuration: a preset (or the starting values) with sections overlaid."""
    return validate_config(sections, PRESETS[base] if base else None)


def ordered(shape: str, axis: str = "captured_at", plain: bool = True, **path: Any) -> dict[str, Any]:
    """An ordered play mode with no relation pull; ``path`` overrides path values."""
    return cfg("sticky", order={"axis": axis}, path={"shape": shape, **path}, relation={"strength": 0.0},
               timing=dict(PLAIN) if plain else {})


def play(config: dict[str, Any], n: int = 3, seconds: float = 60, seed: Any = 1, pool: int = 120,
         records: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    return schedule_play(list(records) if records is not None else list(pool_of(pool)), n, config, seconds, FPS, seed,
                         **extra)


def digest(state: dict[str, Any]) -> str:
    return hashlib.sha256(c.canonical_json(state).encode()).hexdigest()


def sequences(out: dict[str, Any]) -> dict[str, list[str]]:
    """Per loop, the clips shown in order: the initial clip, then every change."""
    sched = out["schedule"]
    seqs = {loop: [sched.initial[loop]] for loop in sched.loop_ids}
    for ch in sched.changes:
        if ch["op"] == "show":
            seqs[ch["loop"]].append(ch["clip"])
    return seqs


def rank_sequences(out: dict[str, Any]) -> dict[str, list[int]]:
    rank = {clip: i for i, clip in enumerate(out["order"])}
    return {loop: [rank[x] for x in seq] for loop, seq in sequences(out).items()}


def clip_at(out: dict[str, Any]):
    """A function (loop, frame) -> clip shown, from the schedule's timeline."""
    timeline = out["schedule"].timeline()
    starts = [frame for frame, _ in timeline]
    return lambda loop, frame: timeline[bisect.bisect_right(starts, frame) - 1][1][loop]


def pair_stat(out: dict[str, Any], pair_value) -> float:
    """Time-weighted mean of ``pair_value(clip_a, clip_b)`` over simultaneous on-screen pairs."""
    sched = out["schedule"]
    timeline = sched.timeline()
    loops = sched.loop_ids
    pairs = [(a, b) for i, a in enumerate(loops) for b in loops[i + 1:]]
    total = acc = 0.0
    for index, (frame, snap) in enumerate(timeline):
        end = timeline[index + 1][0] if index + 1 < len(timeline) else sched.frames
        values = [pair_value(snap[a], snap[b]) for a, b in pairs]
        values = [v for v in values if v is not None]
        if values:
            acc += (end - frame) * sum(values) / len(values)
            total += end - frame
    return acc / total


def mean_affinity(out: dict[str, Any]) -> float:
    """Mean on-screen affinity under the default component weights (milli, 0..1000)."""
    from simvltanea.authoring.gravity_affinity import build_affinity_model
    model = build_affinity_model([r for r in pool_of(120) if r["id"] in out["model"].profiles])
    return pair_stat(out, model.affinity)


def differ(attr: str):
    """pair_value: 1 when both clips have the tag and it differs, 0 when equal, None when unknown."""
    def value(model, a, b):
        x, y = getattr(model.profiles[a], attr), getattr(model.profiles[b], attr)
        return None if x is None or y is None else float(x != y)
    return value


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def deep(value: Any) -> Any:
    return copy.deepcopy(value)
