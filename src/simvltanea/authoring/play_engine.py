"""The play-mode scheduler: (pool, N, configuration, duration, fps, seed) -> composition state.

Pure: it reads no clock, no environment and no global RNG. Candidate selection is an integer
softmax over signed relation scores (see ``gravity_affinity`` for the affinity and
``play_rng`` for the draws), so identical inputs give byte-identical states in any process.

How the four dials combine at every change of a loop:
  1. ``path`` proposes candidates: every free clip (random, follow), the next clips along the
     order (sequential, converge, diverge, pingpong; ``window`` widens the choice), the next
     cards of a shared shuffled deck (playlist), or the clip its voice dictates (round);
  2. ``relation`` scores the candidates against what is on screen (signed strength, signed
     component weights), with novelty and recency pressure;
  3. ``timing`` decides when each loop changes;
  4. ``order`` only decides the sequence the path walks.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Callable, Iterable, Mapping

from .composition import MAX_FRAMES, MAX_SEGMENTS, validate_state
from .gravity_affinity import AffinityModel, build_affinity_model, round_half_up_div, weight_milli
from .play_config import CURSOR_SHAPES, PlayError, check_seed, config_digest, validate_config
from .play_encode import (Schedule, base_state_for, check_base_state, count_plan_spans, encode_state, plan_span_parts,
                          estimate_events, estimate_render_segments)
from .play_order import build_order
from .play_paths import Walker, advance, generate_voice, make_walkers
from .play_pool import eligible_pool, unmatched_exclude_ids
from .play_rng import BITS_PER_UNIT, draw64, sample_indices, shuffled, weighted_pick

_RELATION_KEYS = ("strength", "temperature", "independence", "adjacency", "recency", "novelty", "anchor_pull")


def adjacency_milli(layouts: dict[str, Any], loop_ids: list[str], gap: Fraction = Fraction(6, 100)) -> dict[tuple[str, str], int]:
    """Edge-sharing neighbours averaged over BOTH orientations (orientation is presentation-only,
    so selection must not depend on which layout is showing). Value in 0..1000."""
    out = {(a, b): 0 for a in loop_ids for b in loop_ids if a != b}
    for orientation in ("portrait", "landscape"):
        rects = {cell["loop"]: [Fraction(v) for v in cell["rect"]] for cell in layouts[orientation]["cells"]}
        for a in loop_ids:
            ax, ay, aw, ah = rects[a]
            for b in loop_ids:
                if a == b:
                    continue
                bx, by, bw, bh = rects[b]
                overlap_y = min(ay + ah, by + bh) - max(ay, by)
                overlap_x = min(ax + aw, bx + bw) - max(ax, bx)
                horiz = overlap_y > 0 and (0 <= bx - (ax + aw) <= gap or 0 <= ax - (bx + bw) <= gap)
                vert = overlap_x > 0 and (0 <= by - (ay + ah) <= gap or 0 <= ay - (by + bh) <= gap)
                if horiz or vert:
                    out[(a, b)] += 500
    return out


def field_milli(loop: str, cand: str, current: Mapping[str, str], kappa: Mapping[tuple[str, str], int],
                affinity: Callable[[str, str], int]) -> int:
    """Neighbour-weighted mean affinity of ``cand`` to the clips on the other loops (0 when alone)."""
    num = den = 0
    for j, clip in current.items():
        if j != loop:
            weight = kappa[(loop, j)]
            num += weight * affinity(cand, clip)
            den += weight
    return round_half_up_div(num, den) if den else 0


def _milli(value: float) -> int:
    magnitude = int((abs(value) * 1000 + 0.5) // 1)
    return -magnitude if value < 0 else magnitude


class Engine:
    def __init__(self, model: AffinityModel, eligible: list[str], seq: list[str], loop_ids: list[str],
                 adjacency: dict[tuple[str, str], int], cfg: Mapping[str, Any], frames: int, fps: int, seed: Any):
        self.model, self.eligible, self.seq, self.loop_ids = model, eligible, seq, loop_ids
        self.cfg, self.frames, self.fps, self.seed = cfg, frames, fps, seed
        rel, timing, path = cfg["relation"], cfg["timing"], cfg["path"]
        self.q = {k: _milli((rel if k in rel else timing)[k]) for k in _RELATION_KEYS}
        self.shape = path["shape"]
        self.max_cands = cfg["limits"]["max_candidates"]
        self.pins = {loop: clip for loop, clip in path["pins"]}
        if set(self.pins) - set(loop_ids):
            raise PlayError("pin references an absent loop")
        pinned = set(self.pins.values())
        if not pinned <= set(eligible):
            raise PlayError("pinned clips must be eligible")
        self.anchors = [a for a in rel["anchors"] if a in model.profiles]
        sec = lambda s: max(0, int((s * fps + 0.5) // 1))  # noqa: E731
        self.sec = sec
        self.hold_lo, self.hold_hi = max(1, sec(timing["hold_min"])), max(1, sec(timing["hold_max"]))
        self.stagger, self.cooldown = sec(timing["stagger"]), sec(timing["cooldown"])
        self.window_frames = max(1, sec(timing["recency_window"]))
        self.swap_every = sec(timing["swap_interval"])
        if timing["swap_interval"] > 0 and self.swap_every == 0:
            raise PlayError("timing.swap_interval is shorter than one frame at this fps")
        self.kappa = {k: 1000 + 3 * self.q["adjacency"] * v // 1000 for k, v in adjacency.items()}
        self.adjacency = adjacency
        self.relation_active = (self.q["strength"] != 0 or (self.q["anchor_pull"] != 0 and bool(self.anchors))
                                or self.q["novelty"] != 0 or self.q["recency"] != 0)
        self.current: dict[str, str] = {}
        self.shows = {c: 0 for c in eligible}
        self.last_left: dict[str, int] = {}
        self.total_shows = 0
        self.schedule = Schedule(frames=frames, fps=fps, loop_ids=list(loop_ids), initial={})
        self.walkers: dict[str, Walker] = {}
        self.halted: set[str] = set()
        self.frozen = False
        self.deck: list[str] = []
        self.decks_dealt = 0
        self.window = path["window"]
        self.step = path["step"]

    # ---------------------------------------------------------------- scoring
    def score_n16(self, loop: str, cand: str, frame: int) -> int:
        q, aff = self.q, self.model.affinity
        logit = 0
        if q["strength"] != 0:
            if self.shape == "follow":                       # each loop only relates to its own previous clip
                grav = aff(cand, self.current[loop]) if loop in self.current else 0
            else:
                fld = field_milli(loop, cand, self.current, self.kappa, aff)
                # the loop's own thread is the clip it is showing now, the one this pick replaces (GRAVITY.md)
                thread = aff(cand, self.current[loop]) if loop in self.current else fld
                grav = round_half_up_div((1000 - q["independence"]) * fld + q["independence"] * thread, 1000)
            logit += q["strength"] * grav
        if q["anchor_pull"] != 0 and self.anchors:
            logit += q["anchor_pull"] * max((aff(cand, a) for a in self.anchors if a != cand), default=0)
        if q["novelty"] != 0 and self.total_shows:
            cov = min(1000, round_half_up_div(500 * self.shows[cand] * len(self.eligible), max(1, self.total_shows)))
            logit -= q["novelty"] * cov
        if q["recency"] != 0 and cand in self.last_left and frame - self.last_left[cand] < self.window_frames:
            rec = round_half_up_div(1000 * (self.window_frames - (frame - self.last_left[cand])), self.window_frames)
            logit -= q["recency"] * rec
        return round_half_up_div(16 * BITS_PER_UNIT * logit, 1000 * q["temperature"])

    def pick_among(self, loop: str, frame: int, step: Any, cands: list[str]) -> str:
        if len(cands) > self.max_cands:                      # bounded work: seeded, deterministic sample
            idx = sample_indices(draw64(self.seed, "cand", loop, step), len(cands), self.max_cands)
            cands = [cands[i] for i in idx]
        if len(cands) == 1:
            return cands[0]
        n16 = [self.score_n16(loop, c, frame) for c in cands] if self.relation_active else [0] * len(cands)
        return weighted_pick(cands, n16, draw64(self.seed, "pick", loop, step))

    def thread_pick(self, cands: list[str], previous: str | None, i: int) -> str:
        """Voice step: relation to the voice's own previous clip only (signed strength)."""
        if len(cands) > self.max_cands:
            idx = sample_indices(draw64(self.seed, "vcand", i), len(cands), self.max_cands)
            cands = [cands[j] for j in idx]
        if self.q["strength"] == 0 or previous is None:
            n16 = [0] * len(cands)
        else:
            n16 = [round_half_up_div(16 * BITS_PER_UNIT * self.q["strength"] * self.model.affinity(c, previous),
                                     1000 * self.q["temperature"]) for c in cands]
        return weighted_pick(cands, n16, draw64(self.seed, "vpick", i))

    # ---------------------------------------------------------------- state
    def show(self, loop: str, clip: str, frame: int) -> None:
        if loop in self.current:
            self.last_left[self.current[loop]] = frame
        self.current[loop] = clip
        self.shows[clip] += 1
        self.total_shows += 1

    def _cooled(self, clip: str, frame: int) -> bool:
        return clip not in self.last_left or frame - self.last_left[clip] >= self.cooldown

    def free(self, frame: int) -> list[str]:
        busy = set(self.current.values())
        cands = [c for c in self.eligible if c not in busy]
        cool = [c for c in cands if self._cooled(c, frame)]
        return cool or cands                                 # relax cooldown rather than invent filler

    # ---------------------------------------------------------------- shape: choosers
    def choose(self, loop: str, frame: int, step: Any) -> str | None:
        shape = self.shape
        if shape in ("random", "follow"):
            cands = self.free(frame)
            return self.pick_among(loop, frame, step, cands) if cands else None
        if shape == "playlist":
            return self._deal(loop, frame, step)
        return self._walk(loop, frame, step)

    def _deal(self, loop: str, frame: int, step: Any) -> str | None:
        busy = set(self.current.values())
        if not self.deck:
            shuf = shuffled(self.eligible, self.seed, "deck", self.decks_dealt)
            self.decks_dealt += 1
            self.deck = [c for c in shuf if c not in busy] + [c for c in shuf if c in busy]
        free = [c for c in self.deck if c not in busy][: self.window + 1]
        if not free:
            return None
        clip = free[0] if len(free) == 1 else self.pick_among(loop, frame, step, free)
        self.deck.remove(clip)
        return clip

    def _walk(self, loop: str, frame: int, step: Any, initial: bool = False) -> str | None:
        w0 = self.walkers[loop]
        busy = set(self.current.values())
        size = len(self.seq)
        found: list[tuple[str, Walker]] = []
        last = w0
        for relaxed in (False, True):
            found, probe, guard = [], w0, 0
            while len(found) < (1 if initial else self.window + 1) and guard < 2 * size + 2:
                probe = advance(probe, 0 if (initial and guard == 0) else self.step)
                guard += 1
                if probe.halted:
                    break
                clip = self.seq[probe.pos]
                if clip not in busy and (relaxed or self._cooled(clip, frame)):
                    found.append((clip, probe))
            last = probe
            if found:
                break
        if not found:
            if last.halted:
                self.halted.add(loop)
                self.frozen = self.frozen or last.frozen
            return None
        chosen = found[0][0] if len(found) == 1 else self.pick_among(loop, frame, step, [c for c, _ in found])
        self.walkers[loop] = next(w for c, w in found if c == chosen)
        return chosen

    # ---------------------------------------------------------------- initial placement
    def place_initial(self) -> None:
        for loop, clip in sorted(self.pins.items()):
            self.show(loop, clip, 0)
        movable = [l for l in self.loop_ids if l not in self.pins]
        if self.shape in CURSOR_SHAPES:
            walkers = make_walkers(self.shape, self.cfg["path"], len(self.seq), len(self.loop_ids))
            self.walkers = {l: walkers[i] for i, l in enumerate(self.loop_ids)}
            for loop in movable:
                clip = self._walk(loop, 0, ["init"], initial=True)
                if clip is None:
                    raise PlayError("the order leaves no free clip for a loop's starting position")
                self.show(loop, clip, 0)
        else:
            for loop in sorted(movable, key=lambda l: draw64(self.seed, "order", l)):
                self.show(loop, self.choose(loop, 0, ["init"]), 0)
        self.schedule.initial = dict(self.current)

    # ---------------------------------------------------------------- main loop
    def run(self) -> Schedule:
        self.place_initial()
        sched, frames, seed = self.schedule, self.frames, self.seed
        sync = self.cfg["timing"]["synchronized"]
        span = self.hold_hi - self.hold_lo + 1
        taken: list[int] = []

        def reserve(frame: int) -> int:
            if sync:
                return frame
            moved = True
            while moved:
                moved = False
                for t in taken:
                    if abs(frame - t) < max(1, self.stagger):
                        frame = t + max(1, self.stagger)
                        moved = True
            taken.append(frame)
            return frame

        def dwell(loop: str, n: int) -> int:
            if sync:
                return self.hold_lo + draw64(seed, "shold", n) % span
            return self.hold_lo + draw64(seed, "hold", loop, n) % span

        movable = [l for l in self.loop_ids if l not in self.pins]
        upcoming: dict[str, int] = {}
        for loop in movable:
            upcoming[loop] = dwell(loop, 0) if sync else reserve(1 + draw64(seed, "phase", loop) % self.hold_hi)
        swap_step = 0
        every = self.swap_every
        next_swap = reserve(every + draw64(seed, "swap-phase") % max(1, every)) if every else None
        counters = {l: 0 for l in self.loop_ids}
        while True:
            loop = min(upcoming, key=lambda l: (upcoming[l], l)) if upcoming and not self.frozen else None
            frame = upcoming[loop] if loop else None
            if next_swap is not None and (frame is None or next_swap < frame) and next_swap < frames:
                self._swap(next_swap, swap_step, movable)
                swap_step += 1
                next_swap = reserve(next_swap + every)
                continue
            if frame is None or frame >= frames:
                break
            counters[loop] += 1
            clip = self.choose(loop, frame, [counters[loop]])
            if clip is not None:
                self.show(loop, clip, frame)
                sched.changes.append({"frame": frame, "op": "show", "loop": loop, "clip": clip})
            if loop in self.halted:
                del upcoming[loop]
                continue
            upcoming[loop] = reserve(frame + dwell(loop, counters[loop]))
        return sched

    def _swap(self, frame: int, step: int, movable: list[str]) -> None:
        """Spatial gravity: maybe exchange two loops' clips so related (or contrasting) clips sit side by side."""
        aff, q, adj, cur = self.model.affinity, self.q, self.adjacency, self.current
        options: list[tuple[str, str] | None] = [None]
        gains = [0]
        for i, a in enumerate(movable):
            for b in movable[i + 1:]:
                delta = 0
                for j in self.loop_ids:
                    if j in (a, b):
                        continue
                    delta += adj[(a, j)] * (aff(cur[b], cur[j]) - aff(cur[a], cur[j]))
                    delta += adj[(b, j)] * (aff(cur[a], cur[j]) - aff(cur[b], cur[j]))
                options.append((a, b))
                gains.append(round_half_up_div(16 * BITS_PER_UNIT * q["strength"] * delta, 1000 * 1000 * q["temperature"]))
        labels = ["none"] + [f"{a}|{b}" for a, b in options[1:]]
        pick = weighted_pick(labels, gains, draw64(self.seed, "swap", step))
        if pick != "none":
            a, b = pick.split("|")
            cur[a], cur[b] = cur[b], cur[a]
            self.schedule.changes.append({"frame": frame, "op": "swap", "a": a, "b": b})

    # ---------------------------------------------------------------- round (canon)
    def run_round(self) -> Schedule:
        path, loops = self.cfg["path"], self.loop_ids
        n, frames = len(loops), self.frames
        hold, beat = self.hold_lo, max(1, self.sec(path["beat_seconds"]))
        if hold % beat:
            raise PlayError("round: the hold is not a whole number of beats at this fps; adjust beat_seconds or fps")
        delay = path["delay_beats"] * beat
        if path["voice"] == "clips" and delay < hold:
            raise PlayError("round with voice=clips needs delay_beats * beat_seconds >= hold, otherwise the same "
                            "clip would be on two loops at once")
        pre = -(-(n - 1) * delay // hold)                    # voice steps loop 0 is ahead of the last loop
        steps = pre + frames // hold + 2
        tag = path["tag"]
        if path["voice"] == "clips":
            if len(self.seq) < pre + 2:
                raise PlayError("the order holds too few clips for this canon without repeating a clip on two loops")
            voice = generate_voice(path["base"], self.seq, path, self.seed, steps, pre + 1, self.thread_pick)
            values = voice
            by_value: dict[Any, list[str]] = {}
        else:
            by_value = {}
            for clip in self.seq:
                value = getattr(self.model.profiles[clip], tag)
                if value is not None:
                    by_value.setdefault(value, []).append(clip)
            usable = {v for v, clips in by_value.items() if len(clips) >= n + 1}
            vseq = [c for c in self.seq if getattr(self.model.profiles[c], tag) in usable]
            if len(vseq) < 2:
                raise PlayError(f"round with voice=tags needs a {tag} value shared by at least {n + 1} clips")
            voice = generate_voice(path["base"], vseq, path, self.seed, steps, 0, self.thread_pick)
            values = [getattr(self.model.profiles[c], tag) for c in voice]

        def index(k: int, t: int) -> int:
            return (t - k * delay) // hold + pre

        def clip_for(k: int, t: int) -> str:
            i = index(k, t)
            if path["voice"] == "clips":
                return values[i]
            cands = by_value[values[i]]
            busy = set(self.current.values())
            free = [c for c in cands if c not in busy]
            cool = [c for c in free if self._cooled(c, t)]
            return self.pick_among(loops[k], t, ["round", t], cool or free)

        for k, loop in enumerate(loops):
            self.show(loop, clip_for(k, 0), 0)
        self.schedule.initial = dict(self.current)
        events = []
        for k in range(n):
            first = (k * delay) % hold or hold
            events += [(t, k) for t in range(first, frames, hold)]
        for t, k in sorted(events):
            clip = clip_for(k, t)
            self.show(loops[k], clip, t)
            self.schedule.changes.append({"frame": t, "op": "show", "loop": loops[k], "clip": clip})
        if path["voice"] == "clips":
            for frame, snap in self.schedule.timeline():
                if len(set(snap.values())) != n:
                    raise PlayError("the voice repeats a clip while another loop still shows it; use a longer "
                                    "order, a larger delay or another base shape")
        return self.schedule


# ---------------------------------------------------------------------- public entry point

def build_schedule(model: AffinityModel, eligible: list[str], seq: list[str], loop_ids: list[str],
                   adjacency: dict[tuple[str, str], int], cfg: Mapping[str, Any], frames: int, fps: int,
                   seed: Any) -> Schedule:
    if len(eligible) < len(loop_ids):
        raise PlayError(f"need {len(loop_ids)} eligible distinct clips, have {len(eligible)}; no filler is created")
    engine = Engine(model, eligible, seq, loop_ids, adjacency, cfg, frames, fps, seed)
    if cfg["path"]["shape"] == "round":
        return engine.run_round()
    return engine.run()


def schedule_play(pool: list[dict[str, Any]], n: int, config: Mapping[str, Any] | None = None,
                  duration_seconds: float = 60, fps: int = 24, seed: Any = None,
                  base_state: dict[str, Any] | None = None, extra_excluded_shas: Iterable[Any] = (),
                  extra_known_ids: Iterable[str] = ()) -> dict[str, Any]:
    """Pure entry point. Returns ``{state, schedule, model, adjacency, order, excluded, config, report}``.

    ``config`` is a (possibly partial) play-mode dictionary; it is validated and completed.
    ``seed`` overrides ``config["seed"]`` when given. The state has passed ``validate_state``.
    ``excluded`` maps ids to reasons for in-process use only; ``report`` holds counts only and
    is safe to store or print. ``extra_excluded_shas`` hides media whose record is not in the pool (the
    receipt of an excluded id that has no tag record); ``extra_known_ids`` names clips that exist outside
    the pool, so an exclude id naming one is not reported as unmatched.
    """
    cfg = validate_config(config or {})
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, (int, str)):
            raise PlayError("seed must be an integer or a string")
        cfg["seed"] = check_seed(seed)
    seed = cfg["seed"]
    if not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= 7:
        raise PlayError("authored layouts exist for N = 2..7")
    if type(fps) is not int or not 1 <= fps <= 60:
        raise PlayError("fps must be an integer in 1..60")
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
        raise PlayError("duration_seconds must be a finite number")
    # Python ints can be enormous, so compare before any float conversion (math.isfinite(10**400) overflows).
    # NaN and the infinities fail both comparisons too. MAX_FRAMES seconds is far above any duration that fits at 1 fps.
    if not -MAX_FRAMES <= duration_seconds <= MAX_FRAMES:
        raise PlayError(f"duration_seconds must be a finite number of seconds, at most {MAX_FRAMES}")
    frames = int((duration_seconds * fps + 0.5) // 1)
    if not 1 <= frames <= MAX_FRAMES:
        raise PlayError(f"duration must give 1..{MAX_FRAMES} frames at {fps} fps")
    known = {str(r["id"]) for r in pool if isinstance(r, dict) and "id" in r}
    if any(a not in known for a in cfg["relation"]["anchors"]):
        raise PlayError("anchor is not in the pool")
    eligible, excluded = eligible_pool(pool, cfg["exclusion"], extra_excluded_shas)
    unmatched, unmatched_near = unmatched_exclude_ids(cfg["exclusion"]["exclude_ids"], [*known, *extra_known_ids])
    records = {str(r["id"]): r for r in eligible}
    shape = cfg["path"]["shape"]
    if shape in CURSOR_SHAPES or shape == "round":
        seq, dropped = build_order(eligible, cfg["order"], seed)
        if len(seq) < n:
            raise PlayError(f"need {n} clips with a value on order.axis={cfg['order']['axis']}, have {len(seq)}; "
                            "add the data (captured_at comes from tools.media.index_clips) or set order.missing")
    else:
        seq, dropped = sorted(records), 0
    base = base_state if base_state is not None else base_state_for(n)
    loop_ids = check_base_state(base, n)
    limits = cfg["limits"]
    _budget(cfg, n, frames, fps, len(eligible))
    model = build_affinity_model(eligible, {k: v for k, v in cfg["relation"]["weights"].items()})
    adjacency = adjacency_milli(base["layouts"], loop_ids)
    ids = sorted(records)
    schedule = build_schedule(model, ids, seq if shape in CURSOR_SHAPES or shape == "round" else ids, loop_ids,
                              adjacency, cfg, frames, fps, seed)
    state, stats = encode_state(schedule, records, base, seed, limits["max_events"])
    span_limit = MAX_SEGMENTS * len(loop_ids)
    spans = count_plan_spans(schedule, state, span_limit)
    if spans > span_limit:
        raise PlayError(_span_refusal(schedule, state, len(loop_ids)))
    validate_state(state)
    segments = estimate_render_segments(schedule, state)
    configured = limits["max_render_segments"]               # never above MAX_SEGMENTS (validated)
    if limits["refuse_unrenderable"] and segments > configured:
        if configured >= MAX_SEGMENTS:
            raise PlayError(f"the state would need {segments} render segments; the offline renderer allows {MAX_SEGMENTS}")
        raise PlayError(f"the state would need {segments} render segments; limits.max_render_segments allows "
                        f"{configured} (the offline renderer allows {MAX_SEGMENTS})")
    reasons: dict[str, int] = {}
    for reason in excluded.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    report = {"eligible": len(eligible), "excluded_counts": dict(sorted(reasons.items())),
              "order_dropped": dropped, "encoding": stats,
              "unmatched_exclude_ids": unmatched, "unmatched_exclude_ids_near": unmatched_near,
              "ignored_anchors": sum(1 for a in cfg["relation"]["anchors"] if a in excluded),
              "render_segments": segments, "render_segment_limit": MAX_SEGMENTS,
              "renderable": segments <= MAX_SEGMENTS,
              "configured_render_segment_limit": configured, "over_configured_limit": segments > configured,
              "config_sha256": config_digest(cfg), "seed": seed}
    return {"state": state, "schedule": schedule, "model": model, "adjacency": adjacency, "order": seq,
            "excluded": excluded, "config": cfg, "report": report}


def _span_refusal(schedule: Schedule, state: dict[str, Any], loops: int) -> str:
    """The refusal for a state over compile_plan's span limit, saying what really would bring it under.

    Spans come from two things: a loop changing its clip (the holds) and a loop's clock running past the end
    of its clip (the clip length, which repeats every ``clip length / rate`` seconds whatever the holds are).
    Which one dominates is counted exactly from this very state, and only a hold floor that addresses the
    dominating cause is suggested. The loop count and the frame rate never help: the limit grows with the
    loops and spans follow seconds.
    """
    total, changes, wraps = plan_span_parts(schedule, state)
    allowed = MAX_SEGMENTS * loops
    lengths = [float(Fraction(s["duration"])) for s in state["sources"]]
    mean = sum(lengths) / len(lengths) if lengths else 0.0
    head = (f"the state needs {-(-total // loops)} browser spans per loop on average ({total} in all) but "
            f"compile_plan's span guard would allow {MAX_SEGMENTS} per loop ({allowed} in all)")
    if changes >= wraps:
        why = (f"Source changes dominate ({changes} of {total} spans), so a larger timing.hold_min (fewer changes) "
               "or a shorter duration helps")
    else:
        why = (f"Clip ends dominate ({wraps} of {total} spans are a loop reaching the end of its clip; the mean "
               f"source clip is {mean:.1f} s), so a shorter duration or longer source clips help; raising the hold "
               f"floor (timing.hold_min) only removes some of the {changes} change spans and does not help here")
    return (f"{head}. {why}. Fewer loops or a lower fps do not help: the limit grows with the loop count and "
            "spans follow seconds, not frames. Nothing was written")


def _budget(cfg: Mapping[str, Any], n: int, frames: int, fps: int, pool: int) -> None:
    """Refuse a request whose estimated size or work exceeds the configured limits, before building."""
    timing, limits = cfg["timing"], cfg["limits"]
    if cfg["path"]["shape"] == "round":
        mean_hold = max(1, int((timing["hold_min"] * fps + 0.5) // 1))
    else:
        lo = max(1, int((timing["hold_min"] * fps + 0.5) // 1))
        hi = max(1, int((timing["hold_max"] * fps + 0.5) // 1))
        mean_hold = (lo + hi) / 2
    estimate = estimate_events(n, frames, mean_hold, pool)
    if estimate > limits["max_events"]:
        raise PlayError(f"estimated {estimate} events exceeds limits.max_events={limits['max_events']}; "
                        "shorten the duration, lengthen the holds or lower the loop count")
    changes = n * (int(frames / mean_hold) + 1)
    ops = changes * min(pool, limits["max_candidates"]) * n
    if ops > limits["max_score_ops"]:
        raise PlayError(f"estimated scheduling work {ops} exceeds limits.max_score_ops={limits['max_score_ops']}")
