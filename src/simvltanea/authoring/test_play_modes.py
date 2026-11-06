"""Presets as data, determinism, the relation rule (signed), limits, encoding validity and pinned gravity digests."""
import bisect
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simvltanea.authoring import composition as c
from simvltanea.authoring import gravity_scheduler as gs
from simvltanea.authoring import play_engine as pe
from simvltanea.authoring import play_presets as pp
from simvltanea.authoring.gravity_affinity import build_affinity_model
from simvltanea.authoring.play_config import PlayError
from simvltanea.authoring.play_encode import base_state_for, encode_state
from simvltanea.authoring.test_gravity_pool import make_pool
from simvltanea.authoring.test_play_support import FPS, cfg, differ, digest, mean_affinity, pair_stat, play, pool_of

SRC = str(Path(__file__).resolve().parents[2])

CHILD = """
import hashlib, json
from simvltanea.authoring import schedule_play, PRESETS
from simvltanea.authoring.composition import canonical_json
from simvltanea.authoring.test_gravity_pool import make_pool
pool = make_pool(60)
print(json.dumps({n: hashlib.sha256(canonical_json(schedule_play(pool, 3, c, 30, 24, "child")["state"]).encode()).hexdigest()
                  for n, c in sorted(PRESETS.items())}))
"""

# Digests of the gravity wrapper and of the sticky preset, pinned in full so that they stay deterministic. They are the
# CURRENT code's output, not a comparison with the older implementation: they were first the earlier (pre play-mode)
# implementation's output, and were RE-PINNED once, after the review
# tightened eligibility (a clip with no safety verdict, or with an error code, is now excluded): the synthetic pool
# contains such clips, so every digest changed by exactly those clips leaving the pool. On a pool without them
# the output is unchanged (checked on pools of 300 and 2,000 clips before the re-pin). They were re-pinned a second
# time, deliberately, by the fix to ``relation.independence`` (F2): the loop's own thread is now the clip it is showing
# (the one being replaced) instead of the clip two changes back, so every gravity-scored pick can differ. Only
# gravity-scored states changed; the golden cases above are exactly those.
# (pool size, n, GravityParams kwargs, seconds, seed)
GOLDEN = [
    ((60, 4, {"swap_interval": 15}, 45, "child-seed"), "c58a12539d2d3c8f459d0359b317980bcb025ef4d5edb830f287f4293c8ec1a9"),
    ((120, 5, {}, 120, 1), "8ca44a72cea1ddace983ded53b920c8baf26784a6dbcf905b16efc0326271330"),
    ((120, 3, {}, 60, 7), "68e07d66e263b9d0f6d7220ec55111a0b5fb3b3b4d7ed1a35e6fd664ffa7b78b"),
    ((120, 7, {"swap_interval": 20}, 90, 3), "365bd80a5fa00a7ca36484e65d178863fc88128d9c1217e8f824c0807dedd37b"),
    ((120, 4, {"anchor_pull": 1.0, "independence": 0.7, "gravity": 4, "temperature": 0.5}, 60, 11),
     "9f7c0ebe89bbabd41475ea7ea2852b10175ab5fbc35e9deac2f0f8e6ad5097fc"),
]


class GravityIsOnePlayModeTests(unittest.TestCase):
    def test_sticky_and_schedule_gravity_match_the_pinned_digests(self):
        for (size, n, kwargs, seconds, seed), expected in GOLDEN:
            with self.subTest(size=size, n=n, seed=seed):
                legacy = gs.schedule_gravity(make_pool(size), n, gs.GravityParams(**kwargs), seconds, seed=seed)
                self.assertEqual(digest(legacy["state"]), expected)
        # and through the new entry point with the sticky preset
        new = pe.schedule_play(make_pool(120), 5, pp.PRESETS["sticky"], 120, FPS, 1)
        self.assertEqual(digest(new["state"]), GOLDEN[1][1])

    def test_the_score_everything_equality_holds_while_every_free_pool_fits_in_max_candidates(self):
        """DP-3: the earlier code scored every free clip; the engine scores at most ``limits.max_candidates`` of them.

        Inside the condition (the eligible pool, which bounds every free pool, has at most max_candidates clips)
        the limit is never reached, so any limit at or above it gives the identical state. Above it the free pool is
        sampled and the state differs from the score-everything output (the output at max_candidates = 5000).
        """
        sticky = pp.PRESETS["sticky"]

        def run(size, limit, seed=5):
            config = {**sticky, "limits": {**sticky["limits"], "max_candidates": limit}}
            return play_state(config, size, seed)

        def play_state(config, size, seed):
            out = pe.schedule_play(make_pool(size), 3, config, 30, FPS, seed)
            return out["report"]["eligible"], digest(out["state"])

        eligible, everything = run(120, 5000)
        self.assertLessEqual(eligible, sticky["limits"]["max_candidates"])
        for limit in (eligible, 400, 1000):                       # at or above the eligible count: identical
            with self.subTest(limit=limit):
                self.assertEqual(run(120, limit), (eligible, everything))
        self.assertNotEqual(run(120, 8)[1], everything)           # a limit below the pool changes picks: sampling
        big, everything = run(600, 5000)
        self.assertGreater(big, sticky["limits"]["max_candidates"])
        self.assertNotEqual(run(600, sticky["limits"]["max_candidates"])[1], everything)

    def test_gravity_params_are_just_a_random_path_with_a_positive_strength(self):
        config = gs.GravityParams(gravity=3.0, temperature=0.7, cooldown=10.0).to_config()
        self.assertEqual((config["path"]["shape"], config["relation"]["strength"], config["relation"]["temperature"],
                          config["timing"]["cooldown"]), ("random", 3.0, 0.7, 10.0))
        self.assertEqual(gs.GravityParams.from_preset().to_config(), pp.PRESETS["sticky"])

    def test_schedule_gravity_validates_like_the_engine(self):
        for bad in ({"gravity": 5}, {"temperature": 0}, {"independence": -0.1}, {"hold_max": 1}, {"hold_min": 0.1},
                    {"untagged_policy": "maybe"}, {"max_sharing_sensitivity": "extreme"}, {"exclude_ids": "clip-001"},
                    {"exclude_privacy_flags": "readable_text"}, {"anchors": "a"}):
            with self.subTest(**bad), self.assertRaises(PlayError):
                gs.GravityParams(**bad)


class DeterminismTests(unittest.TestCase):
    def test_every_preset_is_deterministic_and_independent_of_pool_order(self):
        for name, config in pp.PRESETS.items():
            with self.subTest(preset=name):
                a = play(config, 3, 30, 5, pool=60)
                b = play(config, 3, 30, 5, pool=60, records=list(reversed(pool_of(60))))
                self.assertEqual(digest(a["state"]), digest(b["state"]))
                self.assertEqual(a["report"]["config_sha256"], b["report"]["config_sha256"])

    def test_the_seed_changes_every_preset(self):
        for name, config in pp.PRESETS.items():
            with self.subTest(preset=name):
                digests = {digest(play(config, 3, 30, seed, pool=60)["state"]) for seed in (1, 2, 3)}
                self.assertEqual(len(digests), 3)

    def test_the_seed_changes_the_schedule_of_every_random_mode(self):
        for name in ("random", "sticky", "opposites", "city_vs_nature", "near_vs_far", "drift", "magnetic", "round_tags"):
            with self.subTest(preset=name):
                shows = lambda seed: [(ch["frame"], ch.get("clip")) for ch in  # noqa: E731
                                      play(pp.PRESETS[name], 3, 60, seed, pool=60)["schedule"].changes]
                self.assertNotEqual(shows(1), shows(2))

    def test_byte_identical_across_processes_with_different_hash_seeds(self):
        pool = pool_of(60)
        expected = {n: digest(pe.schedule_play(list(pool), 3, conf, 30, FPS, "child")["state"])
                    for n, conf in sorted(pp.PRESETS.items())}
        for hash_seed in ("0", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=SRC)
            done = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, env=env, check=True)
            self.assertEqual(json.loads(done.stdout), expected, f"PYTHONHASHSEED={hash_seed}")

    def test_the_seed_argument_overrides_the_configured_seed_and_is_reported(self):
        config = cfg("sticky", seed="from-config")
        a = play(config, 3, 20, None, pool=60)
        self.assertEqual((a["state"]["seed"], a["report"]["seed"]), ("from-config", "from-config"))
        b = play(config, 3, 20, 9, pool=60)
        self.assertEqual((b["state"]["seed"], b["config"]["seed"]), (9, 9))


class SeedEffectTests(unittest.TestCase):
    """BEH-1: a different seed gives a different state for every preset, and a different composition for every preset
    that draws something at random. ``round_clips`` draws nothing (sequential base, window 0, fixed 4 s holds, a canon
    that starts at the oldest clip), so every seed shows the same clips at every frame."""

    SEEDS = (1, 2, 3, "abc")
    SEED_INERT = {"round_clips"}

    def runs(self, name, n=3, seconds=60):
        return [play(cfg(name), n, seconds, seed, pool=120) for seed in self.SEEDS]

    def test_the_states_always_differ_but_the_composition_differs_for_every_preset_except_round_clips(self):
        for name in sorted(pp.PRESETS):
            with self.subTest(preset=name):
                outs = self.runs(name)
                self.assertEqual(len({digest(o["state"]) for o in outs}), len(self.SEEDS), "state bytes carry the seed")
                timelines = {repr(o["schedule"].timeline()) for o in outs}
                if name in self.SEED_INERT:
                    self.assertEqual(len(timelines), 1, f"{name} was documented as seed-independent but now varies")
                else:
                    self.assertEqual(len(timelines), len(self.SEEDS), f"{name} shows the same clips for every seed")

    def test_round_clips_shows_the_same_clips_at_every_frame_for_every_seed_at_other_loop_counts(self):
        for n in (2, 5):
            with self.subTest(n=n):
                self.assertEqual(len({repr(o["schedule"].timeline()) for o in self.runs("round_clips", n, 120)}), 1)


class EventsAndBanksTests(unittest.TestCase):
    """DOC-F6: the page says a play state usually has events and multi-source banks (which the in-browser client compiler
    refuses), with one exception: a state with every loop pinned has neither."""

    def shape(self, config, n=2):
        state = play(config, n, 20, 1, pool=60)["state"]
        return len(state["events"]), [len(loop["bank"]) for loop in state["loops"]]

    def test_an_ordinary_state_has_events_and_multi_source_banks(self):
        events, banks = self.shape(cfg("sticky"))
        self.assertGreater(events, 0)
        self.assertTrue(all(size > 1 for size in banks), banks)

    def test_a_state_with_every_loop_pinned_has_no_events_and_one_source_per_bank(self):
        pins = [["loop-1", "clip-001"], ["loop-2", "clip-002"], ["loop-3", "clip-003"]]
        for n in (2, 3):
            with self.subTest(n=n):
                events, banks = self.shape(cfg("sticky", path={"pins": pins[:n]}), n)
                self.assertEqual((events, banks), (0, [1] * n))

    def test_a_state_with_only_some_loops_pinned_still_has_a_multi_source_bank(self):
        events, banks = self.shape(cfg("sticky", path={"pins": [["loop-1", "clip-001"]]}))
        self.assertEqual(banks[0], 1)
        self.assertGreater(banks[1], 1)


class EveryPresetIsAValidState(unittest.TestCase):
    def test_every_preset_yields_a_state_that_validates_round_trips_and_compiles(self):
        from simvltanea.browser import compile_plan
        for name, config in pp.PRESETS.items():
            with self.subTest(preset=name):
                out = play(config, 3, 16, 4, pool=60)
                state = out["state"]
                c.validate_state(state)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "state.json"
                    c.save_state(state, path)
                    self.assertEqual(c.load_state(path), state)
                plan = compile_plan(state)
                timeline = out["schedule"].timeline()
                starts = [f for f, _ in timeline]
                for track in plan["tracks"]:
                    spans = track["spans"]
                    for index, span in enumerate(spans):
                        end = spans[index + 1]["frame"] if index + 1 < len(spans) else state["frames"]
                        for frame in (span["frame"], (span["frame"] + end - 1) // 2, end - 1):
                            snap = timeline[bisect.bisect_right(starts, frame) - 1][1]
                            self.assertEqual(span["source"], snap[track["id"]], (track["id"], frame))

    def test_no_filler_no_duplicates_and_only_eligible_clips(self):
        for name, config in pp.PRESETS.items():
            with self.subTest(preset=name):
                out = play(config, 4, 60, 2, pool=80)
                eligible = set(out["model"].profiles)
                self.assertTrue({s["id"] for s in out["state"]["sources"]} <= eligible)
                self.assertFalse(out["state"]["allow_source_reuse"])
                for _, snap in out["schedule"].timeline():
                    self.assertEqual(len(set(snap.values())), 4)
                    self.assertTrue(set(snap.values()) <= eligible)
                hashes = {s["sha256"] for s in out["state"]["sources"]}
                self.assertEqual(len(hashes), len(out["state"]["sources"]))

    def test_fewer_eligible_clips_than_loops_is_an_explicit_failure_for_every_shape(self):
        few = [r for r in pool_of(120) if r["analysis"] and "captured_at" in r][:30]
        keep = pe.eligible_pool(few, cfg("sticky")["exclusion"])[0][:3]
        for shape in ("random", "sequential", "converge", "diverge", "pingpong", "playlist", "follow"):
            config = cfg("sticky", order={"axis": "captured_at"}, path={"shape": shape})
            with self.subTest(shape=shape), self.assertRaises(PlayError):
                play(config, 4, 30, 1, records=keep)
        with self.assertRaises(PlayError):
            play(pp.PRESETS["round_clips"], 4, 30, 1, records=keep)

    def test_a_pool_equal_to_the_loop_count_never_invents_filler(self):
        keep = pe.eligible_pool(list(pool_of(60)), cfg("sticky")["exclusion"])[0][:4]
        for name in ("random", "sticky", "opposites"):
            out = play(pp.PRESETS[name], 4, 40, 3, records=keep)
            self.assertEqual({s["id"] for s in out["state"]["sources"]}, {r["id"] for r in keep})


class RelationTests(unittest.TestCase):
    """Signed strength and signed weights through the same integer machinery."""

    def level(self, name, seeds=(1, 2), **kw):
        config = pp.PRESETS[name] if isinstance(name, str) else name
        return sum(mean_affinity(play(config, 4, 90, s, pool=120)) for s in seeds) / len(seeds)

    def test_positive_strength_raises_and_negative_lowers_on_screen_affinity_against_random(self):
        baseline = self.level("random")
        self.assertGreater(self.level("sticky"), baseline + 60)      # measured about +160
        self.assertLess(self.level("opposites"), baseline - 20)      # measured about -35 (-50 before the F2 fix)

    def test_strength_orders_the_modes_monotonically(self):
        levels = [self.level(cfg("sticky", relation={"strength": s})) for s in (-3.0, 0.0, 3.0)]
        self.assertTrue(levels[0] + 15 < levels[1] < levels[2] - 30, levels)       # about 340, 363, 572
        drift, sticky, magnetic = (self.level(n) for n in ("drift", "sticky", "magnetic"))
        random = self.level("random")
        self.assertTrue(random + 15 < drift < sticky < magnetic, (random, drift, sticky, magnetic))

    def test_city_against_nature_shows_different_environments_far_more_than_random(self):
        def different(name, attr):
            total = 0.0
            for seed in (1, 2, 3):
                out = play(pp.PRESETS[name], 4, 90, seed, pool=120)
                total += pair_stat(out, lambda a, b: differ(attr)(out["model"], a, b))
            return total / 3
        base, preset = different("random", "environment"), different("city_vs_nature", "environment")
        self.assertGreater(preset, base + 0.12)                       # measured 0.87 against 0.65
        self.assertGreater(preset, 0.8)
        # the other attribute is not pushed apart: the contrast is per component
        self.assertLess(different("city_vs_nature", "shot"), different("near_vs_far", "shot"))

    def test_near_against_far_shows_different_shot_sizes_more_than_random(self):
        def spread(name):
            total = 0.0
            for seed in (1, 2, 3):
                out = play(pp.PRESETS[name], 4, 90, seed, pool=120)
                total += pair_stat(out, lambda a, b: abs(out["model"].profiles[a].shot - out["model"].profiles[b].shot)
                                   if out["model"].profiles[a].shot is not None and out["model"].profiles[b].shot is not None else None)
            return total / 3
        self.assertGreater(spread("near_vs_far"), spread("random") + 0.12)

    def test_contrast_on_one_component_and_match_on_another(self):
        match_color = cfg("sticky", relation={"strength": 4.0, "temperature": 0.5, "weights": {
            "subjects": 0, "keywords": 0, "context": 0, "mood": 0, "color": 1.0, "tone": 0, "motion": 0, "framing": 0}})
        both = cfg("sticky", relation={"strength": 4.0, "temperature": 0.5, "weights": {
            "subjects": 0, "keywords": 0, "context": 0, "mood": 0, "color": 1.0, "tone": 0, "motion": 0, "framing": 0,
            "environment": -1.0}})
        def stat(config, which):
            out = play(config, 4, 90, 1, pool=120)
            full = build_affinity_model([r for r in pool_of(120) if r["id"] in out["model"].profiles], {"color": 1.0})
            if which == "color":
                return pair_stat(out, full.affinity)
            return pair_stat(out, lambda a, b: differ("environment")(out["model"], a, b))
        self.assertGreater(stat(both, "environment"), stat(match_color, "environment") + 0.1)
        self.assertGreater(stat(both, "color"), stat(cfg("random"), "color"))      # colour is still matched

    def test_a_negative_strength_with_a_negative_weight_cancels_to_attraction(self):
        """F6: opposites (negative strength) plus 'contrast environment' (negative weight) MATCHES on environment.

        With environment as the only weighted component and T=0.5, over seeds 1 to 3 (measured: share of on-screen
        pairs in the same environment): strength -2 / weight -1 gives 1.00, +2 / -1 gives 0.15, -2 / +1 gives 0.15,
        +2 / +1 gives 1.00 and neutral strength 0 / weight +1 gives 0.32. The signs multiply.
        """
        zero = {name: 0.0 for name in ("subjects", "keywords", "context", "mood", "color", "tone", "motion", "framing")}

        def same_environment(strength, weight):
            total = 0.0
            for seed in (1, 2, 3):
                config = cfg("sticky", relation={"strength": strength, "temperature": 0.5,
                                                 "weights": {**zero, "environment": weight}})
                out = play(config, 4, 90, seed, pool=120)
                total += 1 - pair_stat(out, lambda a, b: differ("environment")(out["model"], a, b))
            return total / 3
        cancelled, contrast_a, contrast_b, matched, neutral = (
            same_environment(-2.0, -1.0), same_environment(2.0, -1.0), same_environment(-2.0, 1.0),
            same_environment(2.0, 1.0), same_environment(0.0, 1.0))
        self.assertGreater(cancelled, 0.9)                                 # two negatives: the same environment again
        self.assertGreater(matched, 0.9)
        self.assertLess(contrast_a, neutral - 0.1)                         # exactly one negative: contrast
        self.assertLess(contrast_b, neutral - 0.1)
        self.assertAlmostEqual(cancelled, matched, delta=0.1)

    def test_anchor_pull_with_a_real_assertion(self):
        anchor = sorted(play(cfg("sticky"), 3, 10, 1, pool=120)["model"].profiles)[5]
        def pulled(strength_anchor):
            vals = []
            for seed in (1, 2):
                out = play(cfg("sticky", relation={"strength": 1.0, "anchors": [anchor], "anchor_pull": strength_anchor}),
                           4, 100, seed, pool=120)
                model = build_affinity_model([r for r in pool_of(120) if r["id"] in out["model"].profiles])
                vals.append(self.mean_to(out, model, anchor))
            return sum(vals) / len(vals)
        self.assertGreater(pulled(2.0), pulled(0.0) + 15)

    @staticmethod
    def mean_to(out, model, anchor):
        sched = out["schedule"]
        timeline = sched.timeline()
        total = acc = 0.0
        for index, (frame, snap) in enumerate(timeline):
            end = timeline[index + 1][0] if index + 1 < len(timeline) else sched.frames
            others = [clip for clip in snap.values() if clip != anchor]
            acc += (end - frame) * sum(model.affinity(clip, anchor) for clip in others) / len(others)
            total += end - frame
        return acc / total


class ScoreTermTests(unittest.TestCase):
    """Each term of the relation rule moves the score the right way (kills 'term ignored' mutations)."""

    @classmethod
    def setUpClass(cls):
        records = pe.eligible_pool(list(pool_of(120)), cfg("sticky")["exclusion"])[0]
        cls.model = build_affinity_model(records)
        cls.ids = sorted(r["id"] for r in records)
        cls.base = pe.base_state_for(3)
        cls.loops = [l["id"] for l in cls.base["loops"]]
        cls.adjacency = pe.adjacency_milli(cls.base["layouts"], cls.loops)

    def engine(self, **sections):
        config = cfg("sticky", **sections)
        return pe.Engine(self.model, self.ids, self.ids, self.loops, self.adjacency, config, 240, FPS, 1)

    def triple(self, anchor_loop="loop-1"):
        """(candidate, near-loop clip, far-loop clip) where the candidate relates to one clip only."""
        others = [l for l in self.loops if l != anchor_loop]
        near = max(others, key=lambda j: self.adjacency[(anchor_loop, j)])
        far = min(others, key=lambda j: self.adjacency[(anchor_loop, j)])
        self.assertGreater(self.adjacency[(anchor_loop, near)], self.adjacency[(anchor_loop, far)])
        for cand in self.ids:
            for x in self.ids:
                for y in self.ids:
                    if len({cand, x, y}) == 3 and self.model.affinity(cand, x) >= 700 and self.model.affinity(cand, y) <= 300:
                        return cand, near, far, x, y
        self.fail("no triple")

    def test_adjacency_weights_neighbours_more(self):
        cand, near, far, x, y = self.triple()
        scores = {}
        for adjacency in (0.0, 1.0):
            e = self.engine(relation={"adjacency": adjacency, "independence": 0.0})
            e.current = {near: x, far: y}
            scores[adjacency] = e.score_n16("loop-1", cand, 0)
            self.assertEqual(e.kappa[("loop-1", far)], 1000 + 3 * e.q["adjacency"] * e.adjacency[("loop-1", far)] // 1000)
        self.assertGreater(scores[1.0], scores[0.0])                  # related to the neighbour only

    def test_independence_shifts_attention_from_the_field_to_the_loops_own_thread(self):
        cand, near, far, x, y = self.triple()
        scores = {}
        for independence in (0.0, 1.0):
            e = self.engine(relation={"independence": independence})
            e.current = {near: y, far: y, "loop-1": x}                # the clip being replaced relates to cand
            scores[independence] = e.score_n16("loop-1", cand, 0)
        self.assertGreater(scores[1.0], scores[0.0])

    def chain(self):
        """(earlier, outgoing, follower, decoy): the follower relates only to the outgoing clip, the decoy only to the earlier."""
        for outgoing in self.ids:
            for follower in self.ids:
                if follower == outgoing or self.model.affinity(follower, outgoing) < 700:
                    continue
                for earlier in self.ids:
                    if earlier in (outgoing, follower) or self.model.affinity(follower, earlier) > 300:
                        continue
                    for decoy in self.ids:
                        if decoy not in (earlier, outgoing, follower) and self.model.affinity(decoy, earlier) >= 700 \
                                and self.model.affinity(decoy, outgoing) <= 300 and self.model.affinity(decoy, follower) <= 300:
                            return earlier, outgoing, follower, decoy
        self.fail("no chain")

    def test_full_independence_relates_the_pick_to_the_clip_being_replaced_not_the_one_before_it(self):
        # F2: the engine used the clip two changes back (it advanced "previous" only after the pick).
        earlier, outgoing, follower, decoy = self.chain()
        e = self.engine(relation={"independence": 1.0, "strength": 4.0, "temperature": 0.1, "anchor_pull": 0.0},
                        timing={"novelty": 0.0, "recency": 0.0, "cooldown": 0.0})
        e.show("loop-1", earlier, 0)
        e.show("loop-1", outgoing, 100)                                # the loop is now showing ``outgoing``
        picks = [e.pick_among("loop-1", 200, step, [follower, decoy]) for step in range(30)]
        self.assertEqual(set(picks), {follower})
        # With no independence and nothing else on screen the thread is ignored: the pick is not forced either way.
        free = self.engine(relation={"independence": 0.0, "strength": 4.0, "temperature": 0.1, "anchor_pull": 0.0},
                           timing={"novelty": 0.0, "recency": 0.0, "cooldown": 0.0})
        free.show("loop-1", earlier, 0)
        free.show("loop-1", outgoing, 100)
        self.assertEqual({free.pick_among("loop-1", 200, step, [follower, decoy]) for step in range(30)} - {follower, decoy}, set())

    def test_recency_penalises_a_clip_that_just_left_and_fades_over_the_window(self):
        e0, e1 = self.engine(timing={"recency": 0.0, "novelty": 0.0}), self.engine(timing={"recency": 2.0, "novelty": 0.0})
        cand = self.ids[0]
        for e in (e0, e1):
            e.last_left = {cand: 100}
        self.assertLess(e1.score_n16("loop-1", cand, 110), e0.score_n16("loop-1", cand, 110))
        recent, old = e1.score_n16("loop-1", cand, 110), e1.score_n16("loop-1", cand, 100 + e1.window_frames - 1)
        self.assertLess(recent, old)
        self.assertEqual(e1.score_n16("loop-1", cand, 100 + e1.window_frames), e0.score_n16("loop-1", cand, 100 + e1.window_frames))

    def test_novelty_penalises_over_shown_clips(self):
        e = self.engine(timing={"recency": 0.0, "novelty": 2.0})
        e.shows[self.ids[0]], e.shows[self.ids[1]], e.total_shows = 9, 0, 9
        self.assertLess(e.score_n16("loop-1", self.ids[0], 0), e.score_n16("loop-1", self.ids[1], 0))

    def test_the_sign_of_the_strength_flips_the_preference(self):
        cand, near, far, x, y = self.triple()
        up, down = self.engine(relation={"strength": 3.0}), self.engine(relation={"strength": -3.0})
        for e in (up, down):
            e.current = {near: x, far: x}
        liked, disliked = cand, self.most_unlike(x)
        self.assertGreater(up.score_n16("loop-1", liked, 0), up.score_n16("loop-1", disliked, 0))
        self.assertLess(down.score_n16("loop-1", liked, 0), down.score_n16("loop-1", disliked, 0))

    def most_unlike(self, clip):
        return min((c for c in self.ids if c != clip), key=lambda c: self.model.affinity(c, clip))

    def test_anchor_term_rewards_clips_related_to_the_anchor(self):
        anchor = self.ids[3]
        e = self.engine(relation={"anchors": [anchor], "anchor_pull": 2.0, "strength": 0.0},
                        timing={"recency": 0.0, "novelty": 0.0})
        close = max((c for c in self.ids if c != anchor), key=lambda c: self.model.affinity(c, anchor))
        far = self.most_unlike(anchor)
        self.assertGreater(e.score_n16("loop-1", close, 0), e.score_n16("loop-1", far, 0))


class CooldownTests(unittest.TestCase):
    def gaps(self, out):
        sched, last_left, shown = out["schedule"], {}, []
        cur = dict(sched.initial)
        gaps = []
        for ch in sched.changes:
            if ch["op"] != "show":
                continue
            left = cur[ch["loop"]]
            last_left[left] = ch["frame"]
            if ch["clip"] in last_left:
                gaps.append(ch["frame"] - last_left[ch["clip"]])
            cur[ch["loop"]] = ch["clip"]
        return gaps

    def test_random_honours_the_cooldown_with_a_small_pool(self):
        for seed in (1, 2, 3):
            out = play(pp.PRESETS["random"], 3, 300, seed, pool=30)
            gaps = self.gaps(out)
            self.assertGreater(len(gaps), 10)
            self.assertGreaterEqual(min(gaps), 30 * FPS, seed)

    def test_the_cooldown_value_is_what_is_enforced(self):
        out = play(cfg("random", timing={"cooldown": 60.0}), 3, 400, 2, pool=40)
        gaps = self.gaps(out)
        self.assertGreater(len(gaps), 5)
        self.assertGreaterEqual(min(gaps), 60 * FPS)
        loose = play(cfg("random", timing={"cooldown": 0.0}), 3, 400, 2, pool=40)
        self.assertLess(min(self.gaps(loose)), 30 * FPS)

    def test_cooldown_is_relaxed_rather_than_inventing_filler(self):
        keep = pe.eligible_pool(list(pool_of(60)), cfg("sticky")["exclusion"])[0][:6]
        out = play(pp.PRESETS["random"], 5, 120, 4, records=keep)
        self.assertLessEqual({s["id"] for s in out["state"]["sources"]}, {r["id"] for r in keep})
        self.assertTrue(all(g > 0 for g in self.gaps(out)))


class LimitsAndEncodingTests(unittest.TestCase):
    def test_estimated_events_over_budget_are_refused_before_anything_is_built(self):
        config = cfg("sticky", limits={"max_events": 100})
        built = []
        original = pe.build_schedule
        pe.build_schedule = lambda *args, **kwargs: built.append(1) or original(*args, **kwargs)
        try:
            with self.assertRaisesRegex(PlayError, "estimated .*max_events"):
                play(config, 7, 600, 1, pool=120)
        finally:
            pe.build_schedule = original
        self.assertEqual(built, [])                                    # refused before any scheduling work

    def test_estimated_work_over_budget_is_refused(self):
        with self.assertRaisesRegex(PlayError, "max_score_ops"):
            play(cfg("sticky", limits={"max_score_ops": 10_000}), 5, 120, 1, pool=120)

    def test_the_encoder_stops_at_the_event_budget_too(self):
        with self.assertRaisesRegex(PlayError, "max_events"):
            play(cfg("sticky", limits={"max_events": 100, "max_score_ops": 10 ** 9}, timing={"hold_min": 12.0, "hold_max": 12.0}),
                 2, 360, 1, pool=120)

    def test_a_round_that_is_under_the_budget_is_not_refused_at_half_of_it(self):
        # F1 / SSP-3: rerolls were counted twice, so the real limit was about half the configured one.
        out = play(cfg("round_clips"), 7, 540, 1, pool=120)
        total = out["report"]["encoding"]["total_events"]
        self.assertLessEqual(total, 150_000)
        self.assertGreater(total, 75_000)                              # more than the old effective limit

    def encode_with_limit(self, out, max_events):
        records = {r["id"]: r for r in pool_of(120)}
        return encode_state(out["schedule"], records, base_state_for(3), 1, max_events)

    def test_a_state_exactly_at_the_event_limit_passes_and_one_event_over_is_refused(self):
        out = play(cfg("sticky", timing={"hold_min": 3.0, "hold_max": 5.0}), 3, 120, 1)
        total = out["report"]["encoding"]["total_events"]
        self.assertGreater(total, 50)
        state, stats = self.encode_with_limit(out, total)
        self.assertEqual((len(state["events"]), stats["total_events"]), (total, total))
        with self.assertRaises(PlayError) as caught:
            self.encode_with_limit(out, total - 1)
        message = str(caught.exception)
        self.assertIn(f"limits.max_events={total - 1}", message)
        self.assertIn(f"{total} events", message)                    # names the real number the state needs
        self.assertNotIn(str(2 * total), message)
        for limit in (2 * total, total + 1):
            self.encode_with_limit(out, limit)

    def test_the_hold_floor_prevents_a_flood_of_events(self):
        with self.assertRaises(PlayError):
            cfg("sticky", timing={"hold_min": 0.01, "hold_max": 0.01, "stagger": 0})

    def test_candidates_are_capped_deterministically(self):
        seen = []
        original = pe.weighted_pick
        pe.weighted_pick = lambda items, n16, u: (seen.append(len(items)), original(items, n16, u))[1]
        try:
            config = cfg("sticky", limits={"max_candidates": 8})
            a = play(config, 3, 60, 1, pool=120)
            b = play(config, 3, 60, 1, pool=120)
        finally:
            pe.weighted_pick = original
        self.assertLessEqual(max(seen), 8)
        self.assertEqual(digest(a["state"]), digest(b["state"]))
        uncapped = play(cfg("sticky"), 3, 60, 1, pool=120)
        self.assertNotEqual(digest(a["state"]), digest(uncapped["state"]))
        # a cap above the pool changes nothing
        self.assertEqual(digest(play(cfg("sticky", limits={"max_candidates": 5000}), 3, 60, 1, pool=120)["state"]),
                         digest(uncapped["state"]))

    def test_base_state_events_and_trims_are_refused_not_dropped(self):
        base = pe.base_state_for(3)
        with_event = json.loads(json.dumps(base))
        with_event["events"] = [{"op": "hold", "frame": 5, "loop": "loop-1", "value": True}]
        with self.assertRaisesRegex(PlayError, "events"):
            pe.schedule_play(list(pool_of(60)), 3, cfg(), 20, FPS, 1, with_event)
        with_trim = json.loads(json.dumps(base))
        with_trim["loops"][0]["trim"] = ["0", "1"]
        with self.assertRaisesRegex(PlayError, "trims"):
            pe.schedule_play(list(pool_of(60)), 3, cfg(), 20, FPS, 1, with_trim)
        pe.schedule_play(list(pool_of(60)), 3, cfg(), 20, FPS, 1, json.loads(json.dumps(base)))

    def test_a_swap_interval_that_rounds_to_zero_frames_is_an_error(self):
        with self.assertRaisesRegex(PlayError, "shorter than one frame"):
            pe.schedule_play(list(pool_of(60)), 3, cfg("sticky", timing={"swap_interval": 0.25}), 20, 1, 1)

    def test_non_finite_and_invalid_durations_fail_clearly(self):
        for seconds in (float("inf"), float("nan"), -5, 0, 10 ** 9, True, "60"):
            with self.subTest(seconds=seconds), self.assertRaises(PlayError):
                pe.schedule_play(list(pool_of(60)), 3, cfg(), seconds, FPS, 1)

    def test_the_render_segment_estimate_equals_the_renderers_own_count(self):
        for name in ("sticky", "chronological", "round_clips", "oldest_meets_newest"):
            for n in (2, 3):
                with self.subTest(preset=name, n=n):
                    out = play(pp.PRESETS[name], n, 40, 3, pool=60)
                    with tempfile.TemporaryDirectory() as tmp:
                        for source in out["state"]["sources"]:         # empty stand-ins: only names are checked
                            target = Path(tmp) / source["path"]
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.touch()
                        for orientation, width, height in (("portrait", 360, 640), ("landscape", 640, 360)):
                            segments = c.compile_segments(out["state"], Path(tmp), orientation, width, height,
                                                          verify_media=False)
                            self.assertEqual(out["report"]["render_segments"], len(segments))

    def test_unrenderable_states_are_reported_and_can_be_refused(self):
        """SSP-2 / SSP-5: renderable is judged against the renderer's own limit (1,024), whatever the config says."""
        long_run = dict(n=7, seconds=300, seed=1, pool=120)
        out = play(cfg("sticky"), **long_run)
        self.assertGreater(out["report"]["render_segments"], c.MAX_SEGMENTS)
        self.assertFalse(out["report"]["renderable"])
        self.assertEqual(out["report"]["render_segment_limit"], c.MAX_SEGMENTS)
        with self.assertRaisesRegex(PlayError, rf"would need {out['report']['render_segments']} render segments; "
                                               rf"the offline renderer allows {c.MAX_SEGMENTS}"):
            play(cfg("sticky", limits={"refuse_unrenderable": True}), **long_run)
        self.assertTrue(play(cfg("sticky"), 2, 30, 1, pool=60)["report"]["renderable"])

    def test_a_lower_configured_limit_refuses_earlier_but_never_changes_what_the_renderer_allows(self):
        mid = dict(n=5, seconds=120, seed=1, pool=120)
        count = play(cfg("sticky"), **mid)["report"]["render_segments"]
        self.assertTrue(50 < count <= c.MAX_SEGMENTS)
        low = cfg("sticky", limits={"max_render_segments": 50})
        report = play(low, **mid)["report"]
        self.assertTrue(report["renderable"])                       # the renderer would take it ...
        self.assertEqual(report["render_segment_limit"], c.MAX_SEGMENTS)
        self.assertEqual(report["configured_render_segment_limit"], 50)
        self.assertTrue(report["over_configured_limit"])           # ... but the caller's own, lower limit is exceeded
        with self.assertRaisesRegex(PlayError, rf"would need {count} render segments; limits.max_render_segments allows 50"):
            play(cfg("sticky", limits={"max_render_segments": 50, "refuse_unrenderable": True}), **mid)

    def test_the_configured_limit_cannot_be_raised_above_the_renderers(self):
        for value in (c.MAX_SEGMENTS + 1, 5000, 1_000_000):
            with self.subTest(value=value), self.assertRaisesRegex(PlayError, "max_render_segments.*1024"):
                cfg("sticky", limits={"max_render_segments": value})
        for value in (1, 50, c.MAX_SEGMENTS):
            self.assertEqual(cfg("sticky", limits={"max_render_segments": value})["limits"]["max_render_segments"], value)
        long_run = dict(n=7, seconds=300, seed=1, pool=120)       # the SSP-5 reproduction: raising it used to flip the flag
        with self.assertRaises(PlayError):
            play(cfg("sticky", limits={"max_render_segments": 5000, "refuse_unrenderable": True}), **long_run)
        self.assertEqual(cfg("sticky")["limits"]["refuse_unrenderable"], False)    # default kept: long states still compile

    def test_an_absurd_duration_is_a_play_error_not_a_raw_overflow(self):
        """DP-5: 10**400 used to raise OverflowError from math.isfinite."""
        for bad in (10 ** 400, -10 ** 400, 10 ** 30, 10 ** 308, 1e300, float("inf"), float("-inf"), float("nan"), 0, -5,
                    True, "60", None):
            with self.subTest(duration=repr(bad)[:30]), self.assertRaises(PlayError):
                play(cfg("sticky"), 3, bad, 1, pool=60)
        self.assertTrue(play(cfg("sticky"), 3, 10 ** 1, 1, pool=60)["report"]["eligible"])

    def test_the_report_holds_counts_only(self):
        bad = {**pool_of(60)[0], "id": "zz-secret-id", "needs_review": True}
        out = play(cfg("sticky", exclusion={"exclude_ids": ["zz-secret-id2"]}), 3, 30, 1, records=[*pool_of(60), bad])
        text = json.dumps(out["report"])
        self.assertNotIn("zz-secret-id", text)
        self.assertNotIn('"exclude_ids"', text)                    # no list of ids; only the counts below
        self.assertEqual(out["report"]["unmatched_exclude_ids"], 1)
        self.assertTrue(all(not isinstance(v, (list, dict, str)) for k, v in out["report"].items()
                            if k.startswith("unmatched")))
        self.assertNotIn("params", out["report"])
        self.assertGreaterEqual(out["report"]["excluded_counts"]["safety"], 1)
        self.assertTrue(all(isinstance(v, int) for v in out["report"]["excluded_counts"].values()))


if __name__ == "__main__":
    unittest.main()
