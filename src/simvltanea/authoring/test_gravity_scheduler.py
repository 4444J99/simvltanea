"""Gravity scheduler: determinism, exclusions, stickiness, coverage, cooldown and engine validity."""
import bisect
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from simvltanea.authoring import composition as c
from simvltanea.authoring import gravity_scheduler as gs
from simvltanea.authoring.composition import ENGINE_VERSION, SCHEMA_VERSION
from simvltanea.authoring.gravity_affinity import build_affinity_model
from simvltanea.authoring.test_gravity_pool import make_pool

SRC = str(Path(__file__).resolve().parents[2])
FPS = 24
DEFAULT = gs.GravityParams()
BASELINE = replace(DEFAULT, gravity=0.0, novelty=0.0, recency=0.0, anchor_pull=0.0)   # same constraints, no pull

CHILD = """
import hashlib
from simvltanea.authoring import GravityParams, schedule_gravity
from simvltanea.authoring.composition import canonical_json
from simvltanea.authoring.test_gravity_pool import make_pool
out = schedule_gravity(make_pool(60), 4, GravityParams(swap_interval=15), 45, seed="child-seed")
print(hashlib.sha256(canonical_json(out["state"]).encode()).hexdigest())
"""


def digest(state):
    return hashlib.sha256(c.canonical_json(state).encode()).hexdigest()


def plan_only(pool, n, params, seconds, seed, model=None):
    """Schedule without encoding (fast path for statistics); same code as schedule_gravity."""
    eligible, _ = gs.eligible_pool(pool, params)
    model = model or build_affinity_model(eligible)
    base = gs.base_state_for(n)
    loops = [loop["id"] for loop in base["loops"]]
    adjacency = gs.adjacency_milli(base["layouts"], loops)
    schedule = gs.build_schedule(model, sorted(r["id"] for r in eligible), loops, adjacency, params,
                                 int(seconds * FPS), FPS, seed)
    return schedule, model


def same_theme_fraction(schedule, truth):
    """Time-weighted fraction of on-screen pairs that share a latent theme."""
    timeline = schedule.timeline()
    loops = schedule.loop_ids
    pairs = [(a, b) for i, a in enumerate(loops) for b in loops[i + 1:]]
    total = same = 0.0
    for index, (frame, snap) in enumerate(timeline):
        end = timeline[index + 1][0] if index + 1 < len(timeline) else schedule.frames
        span = end - frame
        same += span * sum(bool(truth[snap[a]] & truth[snap[b]]) for a, b in pairs) / len(pairs)
        total += span
    return same / total


def mean_affinity_to(schedule, model, anchor):
    timeline = schedule.timeline()
    total = acc = 0.0
    for index, (frame, snap) in enumerate(timeline):
        end = timeline[index + 1][0] if index + 1 < len(timeline) else schedule.frames
        span = end - frame
        others = [clip for clip in snap.values() if clip != anchor]
        acc += span * sum(model.affinity(clip, anchor) for clip in others) / len(others)
        total += span
    return acc / total


def showings(schedule):
    """[(clip, start_frame, end_frame)] for each continuous stay on screen."""
    open_, spans, previous = {}, [], set()
    for frame, snap in schedule.timeline():
        now = set(snap.values())
        for clip in sorted(previous - now):
            spans.append((clip, open_.pop(clip), frame))
        for clip in sorted(now - previous):
            open_[clip] = frame
        previous = now
    spans.extend((clip, start, schedule.frames) for clip, start in sorted(open_.items()))
    return spans


def repeat_gaps(schedule):
    by_clip = {}
    for clip, start, end in showings(schedule):
        by_clip.setdefault(clip, []).append((start, end))
    gaps = []
    for spans in by_clip.values():
        spans.sort()
        gaps += [second[0] - first[1] for first, second in zip(spans, spans[1:])]
    return gaps, by_clip


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = make_pool(120)
        cls.truth = {r["id"]: set(r["_truth"]) for r in cls.pool}
        cls.eligible, cls.excluded = gs.eligible_pool(cls.pool, DEFAULT)
        cls.model = build_affinity_model(cls.eligible)


class DeterminismTests(Base):
    def test_identical_inputs_give_identical_state_in_process(self):
        a = gs.schedule_gravity(self.pool, 4, DEFAULT, 60, seed=5)["state"]
        b = gs.schedule_gravity(copy.deepcopy(self.pool), 4, DEFAULT, 60, seed=5)["state"]
        self.assertEqual(c.canonical_json(a), c.canonical_json(b))

    def test_pool_order_does_not_matter(self):
        a = gs.schedule_gravity(self.pool, 3, DEFAULT, 60, seed=9)["state"]
        b = gs.schedule_gravity(list(reversed(self.pool)), 3, DEFAULT, 60, seed=9)["state"]
        self.assertEqual(c.canonical_json(a), c.canonical_json(b))

    def test_byte_identical_across_processes_with_different_hash_seeds(self):
        expected = digest(gs.schedule_gravity(make_pool(60), 4, gs.GravityParams(swap_interval=15), 45,
                                              seed="child-seed")["state"])
        for hash_seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=SRC)
            done = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, env=env, check=True)
            self.assertEqual(done.stdout.strip(), expected, f"PYTHONHASHSEED={hash_seed}")

    def test_seed_changes_the_state(self):
        digests = {digest(gs.schedule_gravity(self.pool, 4, DEFAULT, 45, seed=s)["state"]) for s in range(6)}
        self.assertEqual(len(digests), 6)
        self.assertNotEqual(digest(gs.schedule_gravity(self.pool, 4, DEFAULT, 45, seed=1)["state"]),
                            digest(gs.schedule_gravity(self.pool, 4, DEFAULT, 45, seed="1")["state"]))

    def test_schema_pick_mirrors_engine_choose_source(self):
        bank = ["clip-001", "clip-005", "clip-009", "clip-020"]
        for seed in (0, 7, "s"):
            for epoch in range(25):
                loop = {"id": "loop-2", "bank": bank, "epoch": epoch, "offset": "0", "rate": "1",
                        "period": gs.PERIOD, "held": False}
                self.assertEqual(c.choose_source({"seed": seed, "fps": FPS}, loop, 0),
                                 gs._schema_pick(seed, "loop-2", epoch, bank))

    def test_weighted_pick_is_an_integer_softmax(self):
        picks = [gs.weighted_pick(["a", "b"], [0, 16], gs.draw64(0, "t", i)) for i in range(3000)]
        self.assertAlmostEqual(picks.count("b") / 3000, 2 / 3, delta=0.03)   # 16 steps = 1 bit of odds


class EngineValidityTests(Base):
    def test_state_uses_existing_vocabulary_and_untouched_clocks(self):
        base = gs.base_state_for(5)
        out = gs.schedule_gravity(self.pool, 5, gs.GravityParams(swap_interval=10), 90, seed=4, base_state=base)
        state = out["state"]
        c.validate_state(state)
        self.assertEqual((state["schema_version"], state["engine_version"]), (SCHEMA_VERSION, ENGINE_VERSION))
        self.assertEqual(state["layouts"], base["layouts"])
        self.assertEqual([(l["id"], l["rate"], l["offset"], l["held"]) for l in state["loops"]],
                         [(l["id"], l["rate"], l["offset"], l["held"]) for l in base["loops"]])
        self.assertEqual({e["op"] for e in state["events"]}, {"reroll", "swap"})
        self.assertGreater(out["report"]["encoding"]["swap_events"], 0)

    def test_every_n_validates_with_no_filler_or_duplicates(self):
        for n in range(2, 8):
            with self.subTest(n=n):
                state = gs.schedule_gravity(self.pool, n, gs.GravityParams(swap_interval=20), 60, seed=n)["state"]
                c.validate_state(state)
                self.assertFalse(state["allow_source_reuse"])
                digests = {s["id"]: s["sha256"] for s in state["sources"]}
                self.assertEqual(len(set(digests.values())), len(digests))
                for frame in range(0, state["frames"], 7):
                    resolved = c.resolve_at(state, frame)["loops"]
                    self.assertEqual(len({x["source"] for x in resolved}), n)

    def test_save_load_round_trip(self):
        state = gs.schedule_gravity(self.pool, 3, gs.GravityParams(swap_interval=10), 40, seed=2)["state"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            c.save_state(state, path)
            self.assertEqual(c.load_state(path), state)

    def test_compile_plan_agrees_with_the_schedule_frame_by_frame(self):
        from simvltanea.browser import compile_plan
        for n, seconds, params in ((2, 30, replace(DEFAULT, swap_interval=8)), (3, 40, DEFAULT)):
            with self.subTest(n=n):
                out = gs.schedule_gravity(self.pool, n, params, seconds, seed=11)
                plan = compile_plan(out["state"])
                frames = out["state"]["frames"]
                per_frame = {}
                for track in plan["tracks"]:
                    seq, spans = [None] * frames, track["spans"]
                    for i, span in enumerate(spans):
                        end = spans[i + 1]["frame"] if i + 1 < len(spans) else frames
                        seq[span["frame"]:end] = [span["source"]] * (end - span["frame"])
                    per_frame[track["id"]] = seq
                timeline = out["schedule"].timeline()
                starts = [f for f, _ in timeline]
                mismatches = 0
                for f in range(frames):
                    snap = timeline[bisect.bisect_right(starts, f) - 1][1]
                    mismatches += any(per_frame[loop][f] != clip for loop, clip in snap.items())
                self.assertEqual(mismatches, 0)

    def test_invalid_arguments_fail_explicitly(self):
        for kwargs in ({"n": 1}, {"n": 8}, {"fps": 0}, {"fps": 61}, {"duration_seconds": 0},
                       {"duration_seconds": 601}, {"duration_seconds": float("nan")}):
            with self.subTest(**kwargs):
                args = dict(pool=self.pool, n=3, params=DEFAULT, duration_seconds=30, fps=FPS, seed=1)
                args.update(kwargs)
                with self.assertRaises(gs.GravityError):
                    gs.schedule_gravity(**args)
        for bad in ({"gravity": 5}, {"temperature": 0}, {"independence": -0.1}, {"hold_max": 1},
                    {"untagged_policy": "maybe"}, {"max_sharing_sensitivity": "extreme"}):
            with self.subTest(**bad), self.assertRaises(gs.GravityError):
                gs.GravityParams(**bad)

    def test_presets(self):
        self.assertEqual({k: (v["gravity"], v["temperature"]) for k, v in gs.GRAVITY_PRESETS.items()},
                         {"drift": (1.0, 1.0), "sticky": (2.5, 1.0), "magnetic": (4.0, 0.5)})
        self.assertEqual(gs.GravityParams.from_preset(), DEFAULT)
        with self.assertRaises(gs.GravityError):
            gs.GravityParams.from_preset("sticky-ish")


class SelectionRuleTests(Base):
    def test_too_few_eligible_clips_fail_explicitly(self):
        with self.assertRaises(gs.GravityError):
            gs.schedule_gravity(self.pool[:3], 4, replace(DEFAULT, require_safety_clear=False), 30, seed=1)
        # exclusions count against the pool: six clips, three excluded, four loops
        six = make_pool(40)[:6]
        params = replace(DEFAULT, exclude_ids=tuple(r["id"] for r in six[:3]), require_safety_clear=False)
        with self.assertRaises(gs.GravityError):
            gs.schedule_gravity(six, 4, params, 30, seed=1)

    def test_pool_equal_to_loops_never_invents_filler(self):
        tiny = [r for r in self.eligible][:4]
        out = gs.schedule_gravity(tiny, 4, replace(DEFAULT, swap_interval=5), 40, seed=3)
        used = {s["id"] for s in out["state"]["sources"]}
        self.assertEqual(used, {r["id"] for r in tiny})
        self.assertEqual({e["op"] for e in out["state"]["events"]} - {"swap"}, set())

    def test_excluded_clips_never_enter_banks_sources_or_events(self):
        out = gs.schedule_gravity(self.pool, 7, replace(DEFAULT, swap_interval=15), 240, seed=1)
        excluded = set(out["excluded"])
        self.assertEqual(set(self.excluded), excluded)
        reasons = set(out["excluded"].values())
        self.assertTrue({"safety", "privacy", "minors", "sharing_sensitivity"} <= reasons)
        state = out["state"]
        self.assertFalse({s["id"] for s in state["sources"]} & excluded)
        self.assertFalse({b for loop in state["loops"] for b in loop["bank"]} & excluded)
        shown = {clip for _, snap in out["schedule"].timeline() for clip in snap.values()}
        self.assertFalse(shown & excluded)
        text = json.dumps(state)
        self.assertFalse([cid for cid in excluded if f'"{cid}"' in text])

    def test_high_sharing_sensitivity_is_excluded_unless_raised(self):
        high = {r["id"] for r in self.pool if (r["analysis"] or {}).get("privacy", {}).get("sharing_sensitivity") == "high"
                and r["analysis"]["safety"]["verdict"] == "clear" and not r["needs_review"]}
        self.assertTrue(high)
        for level, expect_excluded in (("low", True), ("moderate", True), ("high", False)):
            eligible, excluded = gs.eligible_pool(self.pool, replace(DEFAULT, max_sharing_sensitivity=level))
            self.assertEqual(bool(high & set(excluded)), expect_excluded)
        _, excluded = gs.eligible_pool(self.pool, DEFAULT)
        self.assertTrue(all(excluded[cid] == "sharing_sensitivity" for cid in high
                            if not self.pool_record(cid)["analysis"]["privacy"].get("readable_text")
                            and not self.pool_record(cid)["analysis"]["people"]["minors_apparent"]))
        eligible, _ = gs.eligible_pool(self.pool, replace(DEFAULT, max_sharing_sensitivity="low"))
        ratings = {r["analysis"]["privacy"].get("sharing_sensitivity") for r in eligible if r["analysis"]}
        self.assertEqual(ratings - {None}, {"low"})

    def pool_record(self, cid):
        return next(r for r in self.pool if r["id"] == cid)

    def test_unknown_or_invalid_sensitivity_follows_policy_and_malformed_never_passes(self):
        record = copy.deepcopy(next(r for r in self.eligible if r["analysis"]))
        unknown = copy.deepcopy(record)
        unknown["id"], unknown["sha256"] = "unknown-1", hashlib.sha256(b"u").hexdigest()
        del unknown["analysis"]["privacy"]["sharing_sensitivity"]
        malformed = copy.deepcopy(unknown)
        malformed["id"], malformed["sha256"] = "malformed-1", hashlib.sha256(b"m").hexdigest()
        malformed["analysis"]["privacy"]["sharing_sensitivity"] = "very-private"
        upper = copy.deepcopy(unknown)
        upper["id"], upper["sha256"] = "upper-1", hashlib.sha256(b"x").hexdigest()
        upper["analysis"]["privacy"]["sharing_sensitivity"] = " HIGH "
        pool = [unknown, malformed, upper]
        _, allowed = gs.eligible_pool(pool, replace(DEFAULT, untagged_policy="allow"))
        self.assertEqual(allowed, {"malformed-1": "sharing_invalid", "upper-1": "sharing_sensitivity"})
        _, strict = gs.eligible_pool(pool, replace(DEFAULT, untagged_policy="exclude"))
        self.assertEqual(strict, {"unknown-1": "sharing_unknown", "malformed-1": "sharing_invalid",
                                  "upper-1": "sharing_sensitivity"})

    def test_untagged_clips_are_excluded_by_default_and_the_policy_decides_only_when_safety_is_not_required(self):
        untagged = {r["id"] for r in self.pool if not r["analysis"]}
        self.assertTrue(untagged)
        for policy in ("allow", "exclude"):
            kept, excluded = gs.eligible_pool(self.pool, replace(DEFAULT, untagged_policy=policy))
            self.assertFalse(untagged & {r["id"] for r in kept}, policy)
            self.assertTrue(all(excluded[cid] == "safety" for cid in untagged))      # the fixture carries an error code
        relaxed = replace(DEFAULT, require_safety_clear=False)
        allow, _ = gs.eligible_pool(self.pool, relaxed)
        strict, excluded = gs.eligible_pool(self.pool, replace(relaxed, untagged_policy="exclude"))
        self.assertTrue(untagged & {r["id"] for r in allow})
        self.assertFalse(untagged & {r["id"] for r in strict})
        self.assertTrue(all(excluded[cid] == "untagged" for cid in untagged))

    def test_each_exclusion_switch_is_independent(self):
        base_ids = {r["id"] for r in gs.eligible_pool(self.pool, DEFAULT)[0]}
        for change in ({"require_safety_clear": False}, {"exclude_privacy_flags": ()}, {"exclude_minors": False},
                       {"max_sharing_sensitivity": "high"}):
            with self.subTest(change=change):
                ids = {r["id"] for r in gs.eligible_pool(self.pool, replace(DEFAULT, **change))[0]}
                self.assertTrue(base_ids < ids)

    def test_duplicate_bytes_malformed_ids_and_bad_media_records(self):
        a = copy.deepcopy(self.eligible[0])
        b = {**copy.deepcopy(self.eligible[1]), "sha256": a["sha256"]}
        _, excluded = gs.eligible_pool([a, b], DEFAULT)
        self.assertEqual(excluded, {b["id"]: "duplicate_bytes"})
        for bad, reason in (({"sha256": "XYZ"}, "media_sha256"), ({"duration": 0}, "media_duration"),
                            ({"duration": "soon"}, "media_duration"), ({"duration": None}, "media_duration")):
            record = {**copy.deepcopy(self.eligible[2]), **bad}
            self.assertEqual(gs.eligible_pool([record], DEFAULT)[1], {record["id"]: reason})
        for bad_id in ("../x", "a b", "", "x" * 81):
            with self.assertRaises(gs.GravityError):
                gs.eligible_pool([{**self.eligible[0], "id": bad_id}], DEFAULT)
        with self.assertRaises(gs.GravityError):
            gs.eligible_pool([self.eligible[0], self.eligible[0]], DEFAULT)

    def test_pins_hold_for_the_whole_duration(self):
        pin = self.eligible[10]["id"]
        out = gs.schedule_gravity(self.pool, 4, replace(DEFAULT, pins=(("loop-1", pin),)), 120, seed=2)
        self.assertTrue(all(snap["loop-1"] == pin for _, snap in out["schedule"].timeline()))
        self.assertFalse(any(e.get("loop") == "loop-1" for e in out["state"]["events"] if e["op"] == "reroll"))
        self.assertIn(pin, out["state"]["loops"][0]["bank"])
        for bad in (self.excluded and next(iter(self.excluded)), "no-such-clip"):
            with self.assertRaises(gs.GravityError):
                gs.schedule_gravity(self.pool, 4, replace(DEFAULT, pins=(("loop-1", bad),)), 30, seed=2)
        with self.assertRaises(gs.GravityError):
            gs.schedule_gravity(self.pool, 4, replace(DEFAULT, pins=(("loop-9", pin),)), 30, seed=2)
        with self.assertRaises(gs.GravityError):
            gs.schedule_gravity(self.pool, 4, replace(DEFAULT, pins=(("loop-1", pin), ("loop-2", pin))), 30, seed=2)

    def test_anchor_pulls_the_field_toward_it(self):
        anchor = self.eligible[5]["id"]
        plain = replace(DEFAULT, gravity=1.0)
        pulled = replace(plain, anchors=(anchor,), anchor_pull=2.0)
        lifts = []
        for seed in range(1, 7):
            a, _ = plan_only(self.pool, 5, plain, 300, seed, self.model)
            b, _ = plan_only(self.pool, 5, pulled, 300, seed, self.model)
            lifts.append(mean_affinity_to(b, self.model, anchor) - mean_affinity_to(a, self.model, anchor))
        self.assertGreater(sum(lifts) / len(lifts), 15)   # milli-affinity; measured gain is several times this

    def test_anchors_must_exist_and_excluded_anchors_are_ignored(self):
        with self.assertRaises(gs.GravityError):
            gs.schedule_gravity(self.pool, 4, replace(DEFAULT, anchors=("nope",)), 30, seed=1)
        bad = next(iter(self.excluded))
        out = gs.schedule_gravity(self.pool, 4, replace(DEFAULT, anchors=(bad,), anchor_pull=2.0), 60, seed=1)
        self.assertEqual(out["report"]["ignored_anchors"], 1)
        self.assertNotIn(bad, {s["id"] for s in out["state"]["sources"]})


class StickinessTests(Base):
    def test_gravity_lifts_same_theme_pairs_over_the_zero_gravity_baseline_at_n5(self):
        seeds = range(1, 7)
        gravity = [same_theme_fraction(plan_only(self.pool, 5, DEFAULT, 300, s, self.model)[0], self.truth)
                   for s in seeds]
        baseline = [same_theme_fraction(plan_only(self.pool, 5, BASELINE, 300, s, self.model)[0], self.truth)
                    for s in seeds]
        lift = (sum(gravity) / len(gravity)) / (sum(baseline) / len(baseline))
        self.assertGreater(lift, 1.5)   # measured about 2.5 at N=5; the bound leaves room for sampling noise

    def test_presets_are_ordered_by_strength(self):
        def mean_fraction(params):
            return sum(same_theme_fraction(plan_only(self.pool, 5, params, 300, s, self.model)[0], self.truth)
                       for s in range(1, 5)) / 4
        drift, sticky, magnetic = (mean_fraction(gs.GravityParams.from_preset(name))
                                   for name in ("drift", "sticky", "magnetic"))
        baseline = mean_fraction(BASELINE)
        self.assertLess(baseline, drift)
        self.assertLess(drift, sticky)
        self.assertLess(sticky, magnetic)

    def test_higher_temperature_weakens_stickiness(self):
        def mean_fraction(temperature):
            params = replace(DEFAULT, temperature=temperature)
            return sum(same_theme_fraction(plan_only(self.pool, 5, params, 300, s, self.model)[0], self.truth)
                       for s in range(1, 5)) / 4
        self.assertGreater(mean_fraction(0.5), mean_fraction(4.0))

    def test_coverage_and_variety_are_kept(self):
        schedules = [plan_only(self.pool, 5, DEFAULT, 600, s, self.model)[0] for s in (1, 2, 3)]
        for schedule in schedules:
            _, by_clip = repeat_gaps(schedule)
            self.assertGreaterEqual(len(by_clip) / len(self.eligible), 0.9)   # measured about 0.996
        def on_screen(schedule, second):
            timeline = schedule.timeline()
            starts = [f for f, _ in timeline]
            return set(timeline[bisect.bisect_right(starts, second * FPS) - 1][1].values())
        similarity = []
        for second in range(60, 600, 60):
            a, b = on_screen(schedules[0], second), on_screen(schedules[1], second)
            similarity.append(len(a & b) / len(a | b))
        self.assertLess(sum(similarity) / len(similarity), 0.3)   # different seeds show different sets (measured about 0.03)

    def test_every_loop_keeps_changing(self):
        schedule, _ = plan_only(self.pool, 5, DEFAULT, 300, 1, self.model)
        changes = {}
        for ch in schedule.changes:
            if ch["op"] == "show":
                changes[ch["loop"]] = changes.get(ch["loop"], 0) + 1
        self.assertEqual(set(changes), set(schedule.loop_ids))
        self.assertTrue(all(count >= 300 / DEFAULT.hold_max * 0.8 for count in changes.values()))


class CooldownTests(Base):
    def test_no_immediate_repeats_and_hard_cooldown_by_default(self):
        cooldown = round(DEFAULT.cooldown * FPS)
        for n in (3, 5, 7):
            for seed in (1, 2):
                with self.subTest(n=n, seed=seed):
                    schedule, _ = plan_only(self.pool, n, DEFAULT, 300, seed, self.model)
                    gaps, _ = repeat_gaps(schedule)
                    self.assertTrue(gaps)
                    self.assertTrue(all(gap > 0 for gap in gaps))
                    self.assertGreaterEqual(min(gaps), cooldown)

    def test_cooldown_is_a_hard_rule_even_without_soft_penalties(self):
        params = replace(DEFAULT, recency=0.0, novelty=0.0, gravity=4.0, temperature=0.5, cooldown=60.0)
        schedule, _ = plan_only(self.pool, 3, params, 400, 3, self.model)
        gaps, _ = repeat_gaps(schedule)
        self.assertTrue(gaps)
        self.assertGreaterEqual(min(gaps), 60 * FPS)

    def test_cooldown_relaxes_instead_of_inventing_filler_in_a_small_pool(self):
        small = [r for r in self.eligible][:6]
        out = gs.schedule_gravity(small, 5, replace(DEFAULT, swap_interval=0), 120, seed=4)
        c.validate_state(out["state"])
        gaps, _ = repeat_gaps(out["schedule"])
        self.assertTrue(all(gap > 0 for gap in gaps))   # never the same clip twice at once, never a made-up clip
        self.assertLessEqual({s["id"] for s in out["state"]["sources"]}, {r["id"] for r in small})


if __name__ == "__main__":
    unittest.main()
