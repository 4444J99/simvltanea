"""Path mechanics: cursors that travel along an order, and the single-voice generators used by ``round``.

A *walker* is one position on the order with a direction, a zone it may use and the action taken at
the zone's edge. Everything is integer arithmetic over positions; no randomness lives here except
the seeded draws passed in by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .play_config import PlayError
from .play_rng import draw64, shuffled

# Edge actions: wrap (jump to the opposite end), bounce (reverse), restart (jump back to the start),
# halt (this loop keeps its clip), freeze (every loop stops changing).


@dataclass(frozen=True)
class Walker:
    pos: int
    dir: int
    lo: int
    hi: int
    start: int
    start_dir: int
    edge: str
    halted: bool = False
    frozen: bool = False


def advance(w: Walker, steps: int) -> Walker:
    """Move ``steps`` positions, applying the edge action whenever the zone ends."""
    for _ in range(steps):
        if w.halted:
            return w
        q = w.pos + w.dir
        if w.lo <= q <= w.hi:
            w = replace(w, pos=q)
        elif w.lo == w.hi:
            return replace(w, halted=True, frozen=(w.edge == "freeze"))
        elif w.edge == "wrap":
            w = replace(w, pos=w.lo if w.dir > 0 else w.hi)
        elif w.edge == "bounce":
            w = replace(w, dir=-w.dir, pos=w.pos - w.dir)
        elif w.edge == "restart":
            w = replace(w, pos=w.start, dir=w.start_dir)
        else:
            return replace(w, halted=True, frozen=(w.edge == "freeze"))
    return w


def _ends(path: Mapping[str, Any], loops: int) -> list[str]:
    """Which end ('low' or 'high') each loop index takes."""
    first = path["first_end"]
    other = "high" if first == "low" else "low"
    if path["groups"] == "alternate":
        return [first if i % 2 == 0 else other for i in range(loops)]
    head = (loops + 1) // 2
    return [first if i < head else other for i in range(loops)]


def make_walkers(shape: str, path: Mapping[str, Any], size: int, loops: int) -> list[Walker]:
    """One walker per loop index (0..loops-1) over an order of ``size`` clips."""
    if size < loops:
        raise PlayError("the order holds fewer clips than loops")
    step_dir = 1 if path["direction"] == "forward" else -1
    if shape in ("sequential", "pingpong"):
        edge = "bounce" if shape == "pingpong" else path["wrap"]
        edge = {"stop": "halt"}.get(edge, edge)
        out = []
        for i in range(loops):
            base = i * size // loops if path["spread"] == "even" else i
            pos = base if step_dir > 0 else size - 1 - base
            out.append(Walker(pos, step_dir, 0, size - 1, pos, step_dir, edge))
        return out
    ends = _ends(path, loops)
    low_count = ends.count("low")
    # low zone [0, mid-1], high zone [mid, size-1]. converge turns at the true middle of the order (ceil(size/2)),
    # whatever the loop count, so the two fronts meet there; diverge keeps the zones proportional to the
    # loops each end starts (each loop then has about the same room to travel).
    mid = -(-size // 2) if shape == "converge" else -(-size * low_count // loops)
    # Each zone must hold the walkers that start in it: with first_end=high and as many clips as an odd number of
    # loops, the high end has one more loop than half the order, so the middle moves one place (nothing else
    # moves, because every clip is on screen already).
    mid = min(max(mid, low_count), size - (loops - low_count))
    seen = {"low": 0, "high": 0}
    out = []
    for end in ends:
        j = seen[end]
        seen[end] += 1
        if shape == "converge":
            edge = {"bounce": "bounce", "restart": "restart", "hold": "halt", "stop": "freeze"}[path["on_meet"]]
            pos, d = (j, 1) if end == "low" else (size - 1 - j, -1)
        else:                                            # diverge
            edge = {"wrap": "restart", "bounce": "bounce", "stop": "halt"}[path["wrap"]]
            pos, d = (mid - 1 - j, -1) if end == "low" else (mid + j, 1)
        lo, hi = (0, mid - 1) if end == "low" else (mid, size - 1)
        out.append(Walker(pos, d, lo, hi, pos, d, edge))
    return out


# ------------------------------------------------------------------ voices (single path for the canon)

def voice_walkers(shape: str, path: Mapping[str, Any], size: int) -> list[Walker]:
    """Walkers a single voice alternates between (one for linear shapes, two for converge/diverge)."""
    if shape in ("converge", "diverge"):
        return make_walkers(shape, {**path, "groups": "alternate"}, size, 2)
    return make_walkers(shape, {**path, "spread": "together"}, size, 1)


def generate_voice(shape: str, seq: list[str], path: Mapping[str, Any], seed: Any, length: int,
                   recent: int, pick: Callable[[list[str], str | None, int], str]) -> list[str]:
    """``length`` clip ids of one voice over the order ``seq``.

    ``recent`` is the number of immediately preceding voice steps whose clips are not offered again
    (the canon uses it so a clip is never on two loops at once). ``pick(cands, previous, i)`` chooses
    among at most a window of candidates; it must be deterministic.
    """
    size = len(seq)
    window = path["window"]
    out: list[str] = []
    if shape == "random":
        for i in range(length):
            avoid = set(out[-recent:]) if recent else set()
            cand = None
            for attempt in range(64):
                c = seq[draw64(seed, "voice", i, attempt) % size]
                if c not in avoid:
                    cand = c
                    break
            if cand is None:
                free = [c for c in seq if c not in avoid]
                if not free:
                    raise PlayError("the voice needs more distinct clips than the order holds")
                cand = free[draw64(seed, "voice", i, "scan") % len(free)]
            out.append(cand)
        return out
    if shape == "follow":
        for i in range(length):
            avoid = set(out[-recent:]) if recent else set()
            cands = [c for c in seq if c not in avoid]
            if not cands:
                raise PlayError("the voice needs more distinct clips than the order holds")
            out.append(pick(cands, out[-1] if out else None, i))
        return out
    if shape == "playlist":
        deck: list[str] = []
        deals = 0
        while len(out) < length:
            if not deck:
                avoid = set(out[-recent:]) if recent else set(out[-1:])
                shuf = shuffled(seq, seed, "voice-deck", deals)
                deck = [c for c in shuf if c not in avoid] + [c for c in shuf if c in avoid]
                deals += 1
            out.append(deck.pop(0))
        return out
    walkers = voice_walkers(shape, path, size)
    started: set[int] = set()
    for i in range(length):
        idx = i % len(walkers)
        w = walkers[idx]
        avoid = set(out[-recent:]) if recent else set()
        found: list[tuple[str, Walker]] = []
        if idx not in started and seq[w.pos] not in avoid:
            found.append((seq[w.pos], w))            # a walker's first clip is its start clip
        started.add(idx)
        probe, guard = w, 0
        while len(found) < window + 1 and guard < 2 * size + 2:
            probe = advance(probe, path["step"])
            guard += 1
            if probe.halted:
                break
            if seq[probe.pos] not in avoid:
                found.append((seq[probe.pos], probe))
        if not found:                                # a halted voice stays on its clip
            out.append(out[-1] if out else seq[w.pos])
            walkers[idx] = probe
            continue
        clip = found[0][0] if len(found) == 1 else pick([c for c, _ in found], out[-1] if out else None, i)
        walkers[idx] = next(state for c, state in found if c == clip)
        out.append(clip)
    return out
