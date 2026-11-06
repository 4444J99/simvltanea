#!/usr/bin/env python3
"""Regenerate the measured tables of docs/architecture/GRAVITY.md from the repository's synthetic pool.

Everything is deterministic: the pool is ``test_gravity_pool.make_pool(120)`` (eight latent themes, seed 20260101),
each setting runs for 600 s at 24 fps over seeds 1 to 10, and the statistics come from the helpers ``plan_only``,
``same_theme_fraction`` and ``repeat_gaps`` of ``test_gravity_scheduler.py``. No media, no tags of a person: the pool
is made up. The blocks sit between ``<!-- BEGIN GENERATED: measured-... -->`` markers in GRAVITY.md.

Run:  python3 -m tools.media.measure_gravity            (print the tables)
      python3 -m tools.media.measure_gravity --check    (exit 1 when GRAVITY.md differs from a fresh measurement)
      python3 -m tools.media.measure_gravity --write    (rewrite the measured blocks in place)

A full run takes well under a minute. Changing the pool generator, the affinity, the engine or the default
settings changes these numbers: run ``--write`` and read the diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from dataclasses import replace
from pathlib import Path

from tools.paths import REPO_ROOT

from simvltanea.authoring import (AFFINITY_SCALE, PRESET_TABLE, PRESETS, GravityParams, base_state_for,
                                  build_affinity_model, play_config, play_engine, test_gravity_pool,
                                  test_gravity_scheduler)

make_pool = test_gravity_pool.make_pool
BASELINE, DEFAULT, FPS = test_gravity_scheduler.BASELINE, test_gravity_scheduler.DEFAULT, test_gravity_scheduler.FPS
gs, plan_only = test_gravity_scheduler.gs, test_gravity_scheduler.plan_only
repeat_gaps, same_theme_fraction = test_gravity_scheduler.repeat_gaps, test_gravity_scheduler.same_theme_fraction
validate_config = play_config.validate_config

DOC = REPO_ROOT / "docs" / "architecture" / "GRAVITY.md"
POOL_SIZE = 120
SECONDS = 600
SEEDS = tuple(range(1, 11))
LOOP_COUNTS = (2, 3, 4, 5, 6, 7)
STICKINESS = (            # (label, params); the first row is the same scheduler with gravity, novelty and recency at 0
    ("gravity 0", BASELINE),
    ("gravity 1.0, temperature 1 (drift)", GravityParams.from_preset("drift")),
    ("gravity 2.5, temperature 1 (sticky)", GravityParams.from_preset("sticky")),
    ("gravity 4, temperature 1", replace(DEFAULT, gravity=4.0, temperature=1.0)),
    ("gravity 4, temperature 0.5 (magnetic)", GravityParams.from_preset("magnetic")),
)
INDEPENDENCE = (0.0, 0.25, 0.75, 1.0)
PRESET_NAMES = ("drift", "sticky", "magnetic")
RATIO_LOOPS = 5                  # the loop count the preset ratios and the stickiness table are quoted at


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def mean_pair_affinity(schedule, model) -> float:
    """Time-weighted mean affinity (0 to 1) over the pairs of loops that are on screen together."""
    timeline = schedule.timeline()
    loops = schedule.loop_ids
    pairs = [(a, b) for i, a in enumerate(loops) for b in loops[i + 1:]]
    total = acc = 0.0
    for index, (frame, snap) in enumerate(timeline):
        end = timeline[index + 1][0] if index + 1 < len(timeline) else schedule.frames
        acc += (end - frame) * sum(model.affinity(snap[a], snap[b]) for a, b in pairs) / len(pairs)
        total += end - frame
    return acc / total / AFFINITY_SCALE


class Measurer:
    def __init__(self) -> None:
        self.pool = make_pool(POOL_SIZE)
        self.truth = {r["id"]: set(r["_truth"]) for r in self.pool}
        self.eligible, _ = gs.eligible_pool(self.pool, DEFAULT)
        self.model = build_affinity_model(self.eligible)
        self.cache: dict = {}

    @property
    def pool_digest(self) -> str:
        text = json.dumps(self.pool, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def run(self, params: GravityParams, n: int) -> dict:
        key = (params, n)
        if key not in self.cache:
            same, affinity, coverage, gaps = [], [], [], []
            for seed in SEEDS:
                schedule, _ = plan_only(self.pool, n, params, SECONDS, seed, self.model)
                same.append(same_theme_fraction(schedule, self.truth))
                affinity.append(mean_pair_affinity(schedule, self.model))
                seed_gaps, by_clip = repeat_gaps(schedule)
                coverage.append(len(by_clip) / len(self.eligible))
                gaps += seed_gaps
            self.cache[key] = {"same": statistics.fmean(same), "affinity": statistics.fmean(affinity),
                               "coverage": statistics.fmean(coverage),
                               "gap": statistics.median(gaps) / FPS if gaps else float("nan")}
        return self.cache[key]


def _f3(value: float) -> str:
    return f"{value:.3f}".lstrip("0") if value < 1 else f"{value:.3f}"


def _f2(value: float) -> str:
    return f"{value:.2f}".lstrip("0") if value < 1 else f"{value:.2f}"


def by_loops_block(m: Measurer) -> str:
    rows = ["| N | Mean affinity on screen (gravity / baseline) | Same-theme pairs (gravity / baseline) | Times | "
            "Coverage (g / b) | Median repeat gap, s (g / b) |", "| --- | --- | --- | --- | --- | --- |"]
    for n in LOOP_COUNTS:
        g, b = m.run(DEFAULT, n), m.run(BASELINE, n)
        rows.append(f"| {n} | {_f3(g['affinity'])} / {_f3(b['affinity'])} | {_f3(g['same'])} / {_f3(b['same'])} | "
                    f"{g['same'] / b['same']:.2f} | {_f3(g['coverage'])} / {_f3(b['coverage'])} | "
                    f"{g['gap']:.0f} / {b['gap']:.0f} |")
    return "\n".join(rows)


def stickiness_block(m: Measurer) -> str:
    rows = ["| Setting | Same-theme | Coverage |", "| --- | --- | --- |"]
    for label, params in STICKINESS:
        r = m.run(params, RATIO_LOOPS)
        rows.append(f"| {label} | {_f2(r['same'])} | {_f2(r['coverage'])} |")
    return "\n".join(rows)


def independence_block(m: Measurer) -> str:
    cells = [f"{_f3(m.run(replace(DEFAULT, independence=x), RATIO_LOOPS)['same'])} at {x:g}" for x in INDEPENDENCE]
    return f"Independence at N={RATIO_LOOPS}, same-theme fraction: " + ", ".join(cells) + "."


def preset_ratios(m: Measurer) -> dict[str, float]:
    base = m.run(BASELINE, RATIO_LOOPS)["same"]
    return {name: m.run(GravityParams.from_preset(name), RATIO_LOOPS)["same"] / base for name in PRESET_NAMES}


def presets_block(m: Measurer) -> str:
    rows = [f"| Preset | Same-theme pairs against the zero-gravity baseline, N={RATIO_LOOPS} |", "| --- | --- |"]
    rows += [f"| `{name}` | {ratio:.1f} times |" for name, ratio in preset_ratios(m).items()]
    return "\n".join(rows)


OPPOSITE_SETTINGS = (       # (label, configuration)
    ("`random` (no pull)", PRESETS["random"]),
    ("`sticky` (strength 2.5)", PRESETS["sticky"]),
    ("`opposites` (strength -2.5, temperature 1)", PRESETS["opposites"]),
    ("strength -4, temperature 0.1", validate_config({"relation": {"strength": -4.0, "temperature": 0.1}},
                                                     PRESETS["opposites"])),
    ("strength -4, temperature 0.1, independence 0, novelty 0, recency 0",
     validate_config({"relation": {"strength": -4.0, "temperature": 0.1, "independence": 0.0},
                      "timing": {"novelty": 0.0, "recency": 0.0}}, PRESETS["opposites"])),
)


def pick_ranks(m: Measurer, config: dict, n: int = RATIO_LOOPS) -> tuple[float, float, int]:
    """(mean percentile, share of least-related picks, picks) for the choices a configuration makes.

    At every choice the candidates are ranked by the engine's own field, the neighbour-weighted mean affinity to the
    clips on the other loops (``play_engine.field_milli``). The percentile is the share of the other candidates the pick is MORE related
    than (ties count half): 0 is the least related candidate, 1 the most, 0.5 is what a blind pick scores.
    """
    base = base_state_for(n)
    loops = [loop["id"] for loop in base["loops"]]
    adjacency = play_engine.adjacency_milli(base["layouts"], loops)
    ids = sorted(r["id"] for r in m.eligible)
    ranks: list[float] = []
    least = 0
    original = play_engine.Engine.pick_among

    def spy(self, loop, frame, step, cands):
        nonlocal least
        pick = original(self, loop, frame, step, cands)
        others = [clip for other, clip in self.current.items() if other != loop]
        if others and len(cands) > 1:
            field = {c: play_engine.field_milli(loop, c, self.current, self.kappa, m.model.affinity) for c in cands}
            lower = sum(field[c] < field[pick] for c in cands)
            tied = sum(field[c] == field[pick] for c in cands) - 1
            ranks.append((lower + tied / 2) / (len(cands) - 1))
            least += field[pick] == min(field.values())
        return pick

    play_engine.Engine.pick_among = spy
    try:
        for seed in SEEDS:
            play_engine.build_schedule(m.model, ids, ids, loops, adjacency, config, SECONDS * FPS, FPS, seed)
    finally:
        play_engine.Engine.pick_among = original
    return statistics.fmean(ranks), least / len(ranks), len(ranks)


def opposites_block(m: Measurer) -> str:
    rows = [f"| Setting (N={RATIO_LOOPS}) | Mean percentile of the pick (0 = least related candidate) | "
            "Picks that are the least related candidate |", "| --- | --- | --- |"]
    for label, config in OPPOSITE_SETTINGS:
        mean, share, _ = pick_ranks(m, config)
        rows.append(f"| {label} | {mean:.2f} | {share:.1%} |")
    return "\n".join(rows)


def header_block(m: Measurer) -> str:
    return (f"Pool: `make_pool({POOL_SIZE})`, digest `{m.pool_digest}`, {len(m.eligible)} eligible clips, eight latent "
            f"themes. {SECONDS} s at {FPS} fps, seeds {SEEDS[0]} to {SEEDS[-1]}, default settings except as listed. "
            "Regenerate with `python3 -m tools.media.measure_gravity --write`.")


BLOCKS = {"measured-header": header_block, "measured-by-loops": by_loops_block,
          "measured-stickiness": stickiness_block, "measured-independence": independence_block,
          "measured-presets": presets_block, "measured-opposites": opposites_block}


def render(text: str, m: Measurer) -> str:
    for name, build in BLOCKS.items():
        pattern = re.compile(rf"(<!-- BEGIN GENERATED: {name} -->\n)(.*?)(<!-- END GENERATED: {name} -->)", re.S)
        if len(pattern.findall(text)) != 1:
            raise ValueError(f"{DOC.name} needs exactly one generated block named {name!r}")
        body = build(m)
        text = pattern.sub(lambda mo, body=body: mo.group(1) + body + "\n" + mo.group(3), text)
    return text


def preset_claim_problems(m: Measurer) -> list[str]:
    """The 'about X times uniform' of each gravity preset description must equal the measured ratio, rounded to 0.1."""
    out = []
    for name, ratio in preset_ratios(m).items():
        claims = re.findall(r"about ([\d.]+) times uniform", PRESET_TABLE[name]["description"])
        if not claims:
            continue
        if any(abs(float(c) - ratio) > 0.05 for c in claims):
            out.append(f"preset {name}: description says {claims}, measured {ratio:.2f}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="rewrite the measured blocks of GRAVITY.md in place")
    group.add_argument("--check", action="store_true", help="exit 1 when GRAVITY.md differs from a fresh measurement")
    args = parser.parse_args(argv)
    m = Measurer()
    if not (args.write or args.check):
        for name, build in BLOCKS.items():
            print(f"## {name}\n{build(m)}\n")
        return 0
    current = DOC.read_text(encoding="utf-8")
    fresh = render(current, m)
    if args.write:
        if fresh != current:
            DOC.write_text(fresh, encoding="utf-8")
        print(f"{_shown(DOC)} measured blocks written")
        return 0
    problems = preset_claim_problems(m)
    if fresh != current:
        problems.append(f"{_shown(DOC)} measured tables are out of date; run python3 -m tools.media.measure_gravity --write")
    for problem in problems:
        print(problem)
    if not problems:
        print(f"{_shown(DOC)} measured tables match a fresh measurement")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
