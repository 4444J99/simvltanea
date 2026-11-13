"""Schedule -> schema-1 composition state, plus the budgets that keep it renderable and validatable.

The state uses only the existing vocabulary and engine version:
  * loop.bank   = the ordered set of clips that loop will ever be rerolled onto;
  * loop.epoch  = the initial epoch whose sha256 pick is the scheduled first clip;
  * loop.period = larger than the loop's whole local timeline, so source changes happen only
                  through events;
  * "reroll"    events (one or more at the same frame) advance the epoch until
                  ``composition.choose_source`` lands on the scheduled clip;
  * "swap"      events exchange two loops' clips (spatial gravity), clocks untouched.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterable

from .artifact001_layouts import build_artifact001
from .composition import RNG as SCHEMA_RNG, canonical_json, from_authoring_model
from .play_config import PlayError

PERIOD = "1000000"


@dataclass
class Schedule:
    frames: int
    fps: int
    loop_ids: list[str]
    initial: dict[str, str]
    changes: list[dict[str, Any]] = field(default_factory=list)   # {"frame","op":"show"|"swap",...} in apply order

    def timeline(self) -> list[tuple[int, dict[str, str]]]:
        """[(frame, {loop: clip})] snapshots at every change, starting at 0."""
        cur = dict(self.initial)
        out = [(0, dict(cur))]
        for ch in self.changes:
            if ch["op"] == "show":
                cur[ch["loop"]] = ch["clip"]
            else:
                cur[ch["a"]], cur[ch["b"]] = cur[ch["b"]], cur[ch["a"]]
            if out[-1][0] == ch["frame"]:
                out[-1] = (ch["frame"], dict(cur))
            else:
                out.append((ch["frame"], dict(cur)))
        return out


def base_state_for(n: int) -> dict[str, Any]:
    """Authored N-loop layouts and independent clocks, with placeholder sources."""
    authored = build_artifact001(n)
    dummy = {loop.source: dict(id=f"placeholder-{i}", path=f"media/placeholder-{i}.mp4",
                               sha256=hashlib.sha256(f"placeholder-{i}".encode()).hexdigest(),
                               kind="video", duration="3") for i, loop in enumerate(authored.loops)}
    return from_authoring_model(authored, dummy)


def check_base_state(base: dict[str, Any], n: int) -> list[str]:
    """Loop ids of an acceptable base state. Events and trims are refused, not silently dropped."""
    if base.get("events"):
        raise PlayError("base_state events (hold, move, ...) are not preserved by play modes; "
                        "pass a base state without events")
    if any("trim" in loop for loop in base["loops"]):
        raise PlayError("base_state loop trims are not preserved by play modes; pass loops without trim")
    loop_ids = [loop["id"] for loop in base["loops"]]
    if len(loop_ids) != n:
        raise PlayError("base_state loop count differs from n")
    return loop_ids


def _schema_pick(seed: Any, loop_id: str, epoch: int, bank: list[str]) -> str:
    """Exact mirror of composition.choose_source at cycle 0 (checked against the engine in tests)."""
    payload = [SCHEMA_RNG, seed, loop_id, epoch, 0, bank]
    value = int.from_bytes(hashlib.sha256(canonical_json(payload).encode("utf-8")).digest(), "big")
    return bank[value % len(bank)]


def encode_state(schedule: Schedule, records: dict[str, dict[str, Any]], base_state: dict[str, Any],
                 seed: Any, max_events: int | None = None) -> tuple[dict[str, Any], dict[str, int]]:
    """Encode a Schedule using only existing ops. Returns (state, encoding stats)."""
    state = copy.deepcopy(base_state)
    loop_ids = schedule.loop_ids
    banks: dict[str, set[str]] = {l: {schedule.initial[l]} for l in loop_ids}
    for ch in schedule.changes:
        if ch["op"] == "show":
            banks[ch["loop"]].add(ch["clip"])
    bank_lists = {l: sorted(b) for l, b in banks.items()}
    used = sorted(set().union(*banks.values()))
    state["sources"] = [dict(id=c, path=records[c].get("path") or f"media/{c}.mp4", sha256=records[c]["sha256"],
                             kind="video", duration=str(Fraction(str(records[c]["duration"])))) for c in used]
    state["seed"] = seed
    state["frames"] = schedule.frames
    state["fps"] = schedule.fps
    state["allow_source_reuse"] = False
    epochs: dict[str, int] = {}
    for loop in state["loops"]:
        lid = loop["id"]
        loop["bank"] = bank_lists[lid]
        loop["period"] = PERIOD
        e = 0
        while _schema_pick(seed, lid, e, bank_lists[lid]) != schedule.initial[lid]:
            e += 1
        loop["epoch"] = epochs[lid] = e
        # The loop must never cross a selection cycle by local time alone.
        horizon = Fraction(loop["offset"]) + Fraction(schedule.frames, schedule.fps) * Fraction(loop["rate"])
        if horizon >= Fraction(PERIOD):
            raise PlayError("composition longer than selection period")
    events, rerolls = [], 0
    for ch in schedule.changes:
        if ch["op"] == "swap":
            events.append(dict(op="swap", frame=ch["frame"], a=ch["a"], b=ch["b"]))
            continue
        lid, k = ch["loop"], 0
        while True:
            k += 1
            if _schema_pick(seed, lid, epochs[lid] + k, bank_lists[lid]) == ch["clip"]:
                break
        epochs[lid] += k
        rerolls += k
        # ``events`` already holds every earlier reroll, so the total after this change is len(events) + k.
        if max_events is not None and len(events) + k > max_events:
            raise PlayError(f"the state would need at least {len(events) + k} events, more than "
                            f"limits.max_events={max_events}")
        events.extend(dict(op="reroll", frame=ch["frame"], loop=lid) for _ in range(k))
    state["events"] = events
    stats = {"clip_changes": sum(ch["op"] == "show" for ch in schedule.changes),
             "swap_events": sum(ch["op"] == "swap" for ch in schedule.changes),
             "reroll_events": rerolls, "total_events": len(events),
             "mean_bank_size": round(sum(len(b) for b in bank_lists.values()) / len(bank_lists), 2),
             "max_epoch": max(epochs.values()) if epochs else 0}
    return state, stats


def estimate_events(n: int, frames: int, hold_frames_mean: float, pool: int, swaps: int = 0) -> int:
    """Expected event count before anything is built: changes x (bank size ~ changes per loop)."""
    per_loop = max(1, int(frames / max(1.0, hold_frames_mean)) + 1)
    bank = max(1, min(pool, per_loop + 1))
    return n * per_loop * bank + swaps


def wrap_frames(start: int, end: int, offset: Fraction, d: Fraction, rate: Fraction, fps: int) -> Iterable[int]:
    """Frames in ``(start, end)`` at which a loop's local clock passes a multiple of the clip length ``d``.

    The clock is ``offset + frame * rate / fps``; frame ``f`` is a wrap when it is the first frame whose time
    reaches ``d * j`` for some whole ``j``, that is ``f = ceil((d * j - offset) * fps / rate)``. The work is
    bounded by the span, never by how short the clip is: when the clip is no longer than one frame
    (``d * fps / rate <= 1``) consecutive wraps are at most a frame apart, so every frame of the span is a
    wrap and the range is returned without iterating; otherwise there are fewer wraps than frames.
    """
    if end - start <= 1:
        return ()
    if d * fps <= rate:
        return range(start + 1, end)
    found = []
    j = int((offset + Fraction(start) * rate / fps) // d) + 1
    while True:
        wrap = -((offset - d * j) * fps // rate)              # ceil((d*j - offset) * fps / rate)
        if wrap >= end:
            return found
        if wrap > start:
            found.append(int(wrap))
        j += 1


def estimate_render_segments(schedule: Schedule, state: dict[str, Any]) -> int:
    """Segments the renderer will need for this state (``composition.compile_segments``).

    A new segment starts at frame 0, whenever any loop changes its source, and whenever a loop's
    source wraps from its end back to its start. Layouts are constant and trims absent here, so
    nothing else breaks continuity. Exact (Fractions); a test compares it with the renderer's own count.
    """
    durations = {s["id"]: Fraction(s["duration"]) for s in state["sources"]}
    fps = schedule.fps
    loops = {loop["id"]: loop for loop in state["loops"]}
    starts: set[int] = {0}
    spans: dict[str, list[list[Any]]] = {l: [[0, schedule.initial[l]]] for l in schedule.loop_ids}
    current = dict(schedule.initial)
    for ch in schedule.changes:
        if ch["op"] == "show":
            changed = {ch["loop"]: ch["clip"]}
        else:
            changed = {ch["a"]: current[ch["b"]], ch["b"]: current[ch["a"]]}
        for loop, clip in changed.items():
            if clip != current[loop]:
                spans[loop].append([ch["frame"], clip])
                starts.add(ch["frame"])
        current.update(changed)
    for lid, loop_spans in spans.items():
        loop = loops[lid]
        if loop["held"]:
            continue
        rate, offset = Fraction(loop["rate"]), Fraction(loop["offset"])
        for index, (start, clip) in enumerate(loop_spans):
            end = loop_spans[index + 1][0] if index + 1 < len(loop_spans) else schedule.frames
            starts.update(wrap_frames(start, end, offset, durations[clip], rate, fps))
    return len(starts)


def _walk_plan_spans(schedule: Schedule, state: dict[str, Any], limit: int | None) -> tuple[int, int]:
    """(total spans, spans that start at a source change), summed over the loops. See ``count_plan_spans``.

    With a ``limit`` the walk stops once the total exceeds it; both numbers are then partial.
    """
    durations = {s["id"]: Fraction(s["duration"]) for s in state["sources"]}
    fps = schedule.fps
    loops = {loop["id"]: loop for loop in state["loops"]}
    timeline = schedule.timeline()
    spans: dict[str, list[tuple[int, str]]] = {l: [(0, timeline[0][1][l])] for l in schedule.loop_ids}
    for (_, before), (frame, after) in zip(timeline, timeline[1:]):
        for lid in schedule.loop_ids:
            if after[lid] != before[lid]:
                spans[lid].append((frame, after[lid]))
    total = changes = 0
    for lid, loop_spans in spans.items():
        starts = {frame for frame, _ in loop_spans}
        changes += len(starts)
        if not loops[lid]["held"]:
            rate, offset = Fraction(loops[lid]["rate"]), Fraction(loops[lid]["offset"])
            for index, (start, clip) in enumerate(loop_spans):
                end = loop_spans[index + 1][0] if index + 1 < len(loop_spans) else schedule.frames
                starts.update(wrap_frames(start, end, offset, durations[clip], rate, fps))
                if limit is not None and total + len(starts) > limit:
                    return total + len(starts), changes
        total += len(starts)
        if limit is not None and total > limit:
            return total, changes
    return total, changes


def count_plan_spans(schedule: Schedule, state: dict[str, Any], limit: int | None = None) -> int:
    """Exact number of spans ``compile_plan`` produces, summed over the loops (Fractions, no frame loop).

    A loop starts a span at frame 0, at every frame where the clip it shows changes (a change that a
    later change on the same frame cancels is not a change), and at every frame where its local clock
    wraps past the end of its current clip. ``compile_plan`` refuses a state with more than
    ``composition.MAX_SEGMENTS`` spans per loop; a test compares this count with the real plan.
    Counting stops as soon as the total exceeds ``limit`` (and returns a number above it), so a state far
    over the limit is refused in bounded time.
    """
    return _walk_plan_spans(schedule, state, limit)[0]


def plan_span_parts(schedule: Schedule, state: dict[str, Any]) -> tuple[int, int, int]:
    """(total, spans from source changes, spans from clip-end wraps), exact and without a limit.

    A span that is both a change and a wrap frame counts as a change, so the parts add up to the total.
    The work is bounded by the loop count times the frame count, so it is safe to call on a refused state.
    """
    total, changes = _walk_plan_spans(schedule, state, None)
    return total, changes, total - changes


def render_segment_bound(rates: Any, seconds: float, hold_min: float, clip_min: float, fps: int = 24,
                         swap_interval: float = 0.0) -> int:
    """Upper bound on the render segments of any state this engine can generate, from settings alone.

    ``compile_segments`` starts a segment at frame 0, at every frame where a loop changes source, and
    wherever a loop's local clock wraps past the end of its current clip. For each loop (``rates``
    holds the loops' playback rates):

      * changes are at least ``hold_min`` (in whole frames) apart, so there are at most
        ``(frames - 1) // hold_frames + 1`` of them and one more span than there are changes;
      * inside a span of source time ``D`` a clip of length ``>= clip_min`` wraps at most
        ``D / clip_min + 1`` times, and the spans add up to ``seconds * rate``.

    Hence ``1 + sum(2 * changes + 1 + seconds * rate / clip_min)`` plus, when swaps are on, one frame
    and two spans per swap. It is deliberately pessimistic (it assumes every clip is as short as
    ``clip_min`` and ignores coinciding frames); the exact count is ``estimate_render_segments``.
    """
    frames = max(1, int(seconds * fps + 0.5))
    hold_frames = max(1, int(hold_min * fps + 0.5))
    changes = (frames - 1) // hold_frames + 1
    total = Fraction(1)
    for rate in rates:
        total += 2 * changes + 1 + Fraction(str(seconds)) * Fraction(str(rate)) / Fraction(str(clip_min))
    if swap_interval > 0:
        swaps = int(seconds / swap_interval) + 1
        total += 3 * swaps
    return -int(-total // 1)


def render_segment_estimate(rates: Any, seconds: float, hold_mean: float, clip_mean: float) -> int:
    """Expected render segments: one per change plus one per wrap, summed over loops (an estimate, not a bound).

    ``1 + seconds * sum(rate / clip_mean + 1 / hold_mean)``. On the synthetic pools it lands within about
    6 percent of the exact count, usually above it.
    """
    total = Fraction(1)
    for rate in rates:
        total += Fraction(str(seconds)) * (Fraction(str(rate)) / Fraction(str(clip_mean)) + 1 / Fraction(str(hold_mean)))
    return -int(-total // 1)
