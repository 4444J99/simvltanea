"""Order and path shapes: every walk, meet behaviour, canon and deal, on a small synthetic pool."""
import unittest

from simvltanea.authoring import play_order as po
from simvltanea.authoring.play_config import PlayError
from simvltanea.authoring.test_play_exclusions import clean_record
from simvltanea.authoring.test_play_support import (FPS, PLAIN, cfg, clip_at, ordered, play, pool_of, rank_sequences,
                                                    sequences, spearman)

HOLD = {"hold_min": 4.0, "hold_max": 4.0}          # equal holds: loops never catch up with each other


def steady(shape, **path):
    config = ordered(shape, **path)
    config["timing"].update(HOLD)
    return config


def diffs(seq, size):
    return [(b - a) % size for a, b in zip(seq, seq[1:])]


class OrderTests(unittest.TestCase):
    def records(self):
        return [dict(r) for r in pool_of(120)]

    def test_captured_at_orders_by_parsed_time_in_both_directions(self):
        records = [r for r in self.records() if "captured_at" in r]
        asc, dropped = po.build_order(records, {"axis": "captured_at", "direction": "ascending", "missing": "exclude"}, 1)
        times = {r["id"]: po.parse_captured_at(r["captured_at"]) for r in records}
        self.assertEqual([times[i] for i in asc], sorted(times.values()))
        self.assertEqual(dropped, 0)
        desc, _ = po.build_order(records, {"axis": "captured_at", "direction": "descending", "missing": "exclude"}, 1)
        self.assertEqual([times[i] for i in desc], sorted(times.values(), reverse=True))

    def test_ties_break_by_clip_id_in_both_directions(self):
        records = [{"id": cid, "captured_at": "2024-01-01T00:00:00Z"} for cid in ("b", "d", "a", "c")]
        for direction in ("ascending", "descending"):
            seq, _ = po.build_order(records, {"axis": "captured_at", "direction": direction, "missing": "exclude"}, 0)
            self.assertEqual(seq, ["a", "b", "c", "d"])

    def test_timestamp_spellings(self):
        z = po.parse_captured_at("2024-03-01T12:00:00Z")
        self.assertEqual(z, po.parse_captured_at("2024-03-01T12:00:00+00:00"))
        self.assertEqual(z, po.parse_captured_at("2024-03-01T12:00:00"))                    # naive is read as UTC
        self.assertEqual(z - 3600, po.parse_captured_at("2024-03-01T12:00:00+01:00"))
        for bad in (None, 5, "", "yesterday", "2024-13-45", [], "9" * 80):
            self.assertIsNone(po.parse_captured_at(bad))

    def test_numeric_feature_and_tag_ordinal_axes(self):
        records = self.records()
        luma, _ = po.build_order(records, {"axis": "luma", "direction": "ascending", "missing": "exclude"}, 0)
        values = {r["id"]: r["features"]["luma"] for r in records}
        self.assertEqual([values[i] for i in luma], sorted(values.values()))
        shot, _ = po.build_order(records, {"axis": "shot", "direction": "ascending", "missing": "exclude"}, 0)
        ordinal = {"close_up": 0, "medium": 1, "wide": 2}
        tags = {r["id"]: ordinal.get((r["analysis"] or {}).get("shot")) for r in records}
        known = [tags[i] for i in shot]
        self.assertEqual(known, sorted(known))
        self.assertNotIn(None, known)
        self.assertEqual(len(shot), sum(v is not None for v in tags.values()))
        self.assertEqual(po.axis_value({"id": "x", "analysis": {"time_of_day": "artificial_light"}}, "time_of_day"), None)
        self.assertEqual(po.axis_value({"id": "x", "analysis": {"motion_level": "intense"}}, "motion_level"), 3)
        self.assertEqual(po.axis_value({"id": "x", "duration": "2.5"}, "duration"), po.axis_value({"id": "y", "duration": 2.5}, "duration"))
        for axis in ("luma", "hue", "motion", "duration", "shot", "captured_at"):
            self.assertIsNone(po.axis_value({"id": "x", "analysis": "junk", "features": [1], "duration": [2],
                                             "captured_at": 7}, axis))
        with self.assertRaises(PlayError):
            po.axis_value({"id": "x"}, "luminosity")

    def test_missing_policies(self):
        records = [{"id": f"k{i}", "captured_at": f"2024-01-0{i}T00:00:00Z"} for i in (1, 2, 3)] + [{"id": "m2"}, {"id": "m1"}]
        order = lambda missing, seed=0: po.build_order(records, {"axis": "captured_at", "direction": "ascending",  # noqa: E731
                                                                  "missing": missing}, seed)
        self.assertEqual(order("exclude"), (["k1", "k2", "k3"], 2))
        self.assertEqual(order("end"), (["k1", "k2", "k3", "m1", "m2"], 0))
        random_a, _ = order("random", 1)
        self.assertEqual(sorted(random_a), ["k1", "k2", "k3", "m1", "m2"])
        self.assertEqual([x for x in random_a if x.startswith("k")], ["k1", "k2", "k3"])
        self.assertEqual(order("random", 1)[0], random_a)
        placements = {tuple(order("random", seed)[0]) for seed in range(12)}
        self.assertGreater(len(placements), 3)

    def test_no_axis_is_a_seeded_permutation_independent_of_pool_order(self):
        records = self.records()
        order = {"axis": "none", "direction": "ascending", "missing": "exclude"}
        a, _ = po.build_order(records, order, 5)
        b, _ = po.build_order(list(reversed(records)), order, 5)
        self.assertEqual(a, b)
        self.assertNotEqual(a, po.build_order(records, order, 6)[0])
        self.assertEqual(sorted(a), sorted(r["id"] for r in records))

    def test_too_few_clips_on_the_axis_fail_explicitly(self):
        with self.assertRaisesRegex(PlayError, "need 3 clips with a value"):
            play(ordered("sequential", axis="captured_at"), 3, 30, 1,
                 records=[{**r, "captured_at": None} for r in pool_of(60)])


class SequentialTests(unittest.TestCase):
    def test_forward_walk_visits_the_order_one_clip_at_a_time(self):
        out = play(steady("sequential"), 2, 90, 1, pool=60)
        size = len(out["order"])
        for loop, ranks in rank_sequences(out).items():
            self.assertGreater(len(ranks), 15)
            self.assertEqual(set(diffs(ranks, size)), {1}, loop)

    def test_step_and_backward_direction(self):
        out = play(steady("sequential", step=3), 2, 90, 1, pool=60)
        size = len(out["order"])
        for ranks in rank_sequences(out).values():
            self.assertEqual(set(diffs(ranks, size)), {3})
        out = play(steady("sequential", direction="backward"), 2, 90, 1, pool=60)
        for ranks in rank_sequences(out).values():
            self.assertEqual(set(diffs(ranks, size)), {size - 1})

    def test_loops_start_evenly_spaced_or_together(self):
        out = play(steady("sequential", spread="even"), 3, 10, 1, pool=60)
        size = len(out["order"])
        starts = sorted(rank_sequences(out)[l][0] for l in out["schedule"].loop_ids)
        self.assertEqual(starts, [0, size // 3, 2 * size // 3])
        out = play(steady("sequential", spread="together"), 3, 10, 1, pool=60)
        self.assertEqual(sorted(rank_sequences(out)[l][0] for l in out["schedule"].loop_ids), [0, 1, 2])

    def test_wrap_returns_to_the_start(self):
        out = play(steady("sequential", wrap="wrap"), 2, 160, 1, pool=40)
        size = len(out["order"])
        for ranks in rank_sequences(out).values():
            self.assertIn(0, ranks[1:])                      # came back to the oldest clip
            self.assertEqual(set(diffs(ranks, size)), {1})

    def test_bounce_reverses_at_the_end(self):
        out = play(steady("sequential", wrap="bounce"), 2, 220, 1, pool=40)
        size = len(out["order"])
        for ranks in rank_sequences(out).values():
            steps = [b - a for a, b in zip(ranks, ranks[1:])]
            self.assertTrue({1, -1} <= set(steps) <= {1, -1, 2, -2})     # 2: passing a loop coming the other way
            self.assertEqual(max(ranks), size - 1)
            self.assertEqual(min(ranks), 0)
            self.assertTrue(all(0 <= r < size for r in ranks))

    def test_stop_leaves_each_loop_on_its_last_clip(self):
        out = play(steady("sequential", wrap="stop"), 2, 300, 1, pool=40)
        size = len(out["order"])
        for loop, ranks in rank_sequences(out).items():
            self.assertTrue(all(b > a for a, b in zip(ranks, ranks[1:])), loop)       # strictly forward
            self.assertGreaterEqual(ranks[-1], size - 3)
        last = max(ch["frame"] for ch in out["schedule"].changes)
        self.assertLess(last, out["schedule"].frames - 10 * FPS)                      # nothing changes at the end

    def test_the_cursor_skips_a_clip_that_is_on_another_loop(self):
        # Loops walking the same order with different holds meet; the one behind passes, never duplicates.
        config = ordered("sequential", spread="together")
        config["timing"].update({"hold_min": 2.0, "hold_max": 9.0})
        out = play(config, 3, 120, 3, pool=60)
        for _, snap in out["schedule"].timeline():
            self.assertEqual(len(set(snap.values())), 3)

    def test_pingpong_sweeps_end_to_end_and_back(self):
        out = play(steady("pingpong"), 2, 260, 2, pool=40)
        size = len(out["order"])
        for ranks in rank_sequences(out).values():
            steps = [b - a for a, b in zip(ranks, ranks[1:])]
            self.assertTrue({1, -1} <= set(steps) <= {1, -1, 2, -2})
            self.assertEqual((min(ranks), max(ranks)), (0, size - 1))
            turns = sum(1 for a, b in zip(steps, steps[1:]) if a != b)
            self.assertGreaterEqual(turns, 2)

    def test_chronological_time_and_position_are_rank_correlated(self):
        out = play(steady("sequential", spread="together"), 3, 25, 1, pool=120)
        ranks = rank_sequences(out)
        frames = [ch["frame"] for ch in out["schedule"].changes]
        positions = [r[-1] for r in ranks.values()]
        self.assertGreater(spearman(list(range(len(ranks["loop-1"]))), ranks["loop-1"]), 0.99)
        self.assertEqual(len(positions), 3)
        self.assertEqual(frames, sorted(frames))


class ConvergeTests(unittest.TestCase):
    def gaps(self, out, low=("loop-1",), high=("loop-2",)):
        """Distance between the high group's lowest rank and the low group's highest rank at each change."""
        ranks = {l: r for l, r in rank_sequences(out).items()}
        sched = out["schedule"]
        rank = {c: i for i, c in enumerate(out["order"])}
        cur = {l: rank[sched.initial[l]] for l in sched.loop_ids}
        gaps = [(0, min(cur[h] for h in high) - max(cur[l] for l in low))]
        for ch in sched.changes:
            cur[ch["loop"]] = rank[ch["clip"]]
            gaps.append((ch["frame"], min(cur[h] for h in high) - max(cur[l] for l in low)))
        return gaps, ranks

    def run_meet(self, on_meet, n=2, seconds=240):
        return play(steady("converge", on_meet=on_meet), n, seconds, 1, pool=40)

    def test_loops_start_at_the_two_ends_and_close_in(self):
        out = self.run_meet("hold")
        size = len(out["order"])
        gaps, ranks = self.gaps(out)
        self.assertEqual(sorted(r[0] for r in ranks.values()), [0, size - 1])
        values = [g for _, g in gaps]
        self.assertGreater(values[0], size - 3)
        self.assertLessEqual(min(values), 2)
        # approach: the gap never grows while converging
        first_meet = values.index(min(values))
        self.assertTrue(all(b <= a for a, b in zip(values[:first_meet + 1], values[1:first_meet + 1])))

    def test_bounce_diverges_back_out_after_meeting(self):
        out = self.run_meet("bounce")
        size = len(out["order"])
        values = [g for _, g in self.gaps(out)[0]]
        at = values.index(min(values))
        self.assertLessEqual(values[at], 2)
        self.assertGreater(max(values[at:]), size - 6)           # went back out toward the ends
        reversals = sum(1 for a, b, c in zip(values, values[1:], values[2:]) if (b - a) * (c - b) < 0)
        self.assertGreaterEqual(reversals, 2)

    def test_restart_jumps_back_to_the_ends(self):
        out = self.run_meet("restart")
        size = len(out["order"])
        values = [g for _, g in self.gaps(out)[0]]
        jumps = [b - a for a, b in zip(values, values[1:])]
        self.assertGreater(max(jumps), size // 4)                # a restart is a jump, not a walk
        self.assertEqual(sorted(self.gaps(out)[1]["loop-1"])[0], 0)

    def last_changes(self, out):
        last = {}
        for ch in out["schedule"].changes:
            last[ch["loop"]] = ch["frame"]
        return last

    def uneven(self, on_meet, seed):
        config = steady("converge", on_meet=on_meet)
        config["timing"].update({"hold_min": 2.0, "hold_max": 9.0})
        return play(config, 3, 400, seed, pool=40)

    def test_hold_keeps_each_loop_on_the_clip_where_it_met(self):
        spreads = []
        for seed in range(1, 6):
            out = self.uneven("hold", seed)
            last = self.last_changes(out)
            self.assertLess(max(last.values()), out["schedule"].frames * 0.7)         # everything came to rest
            self.assertEqual(set(last), set(out["schedule"].loop_ids))
            final = {l: r[-1] for l, r in rank_sequences(out).items()}
            self.assertLessEqual(max(final.values()) - min(final.values()), 4)       # they met
            spreads.append(max(last.values()) - min(last.values()))
        self.assertGreater(max(spreads), 9 * FPS)       # loops arrive at their own pace and do not wait

    def test_stop_freezes_every_loop_at_the_first_meeting(self):
        for seed in range(1, 6):
            out = self.uneven("stop", seed)
            last = self.last_changes(out)
            self.assertLess(max(last.values()), out["schedule"].frames * 0.7)
            # nobody was left waiting: each loop's final change is within one hold of the freeze
            self.assertLessEqual(max(last.values()) - min(last.values()), 9 * FPS)
            self.assertEqual(set(last), set(out["schedule"].loop_ids))

    def test_groups_and_first_end(self):
        for groups, expected in (("alternate", {"loop-1": "low", "loop-2": "high", "loop-3": "low", "loop-4": "high"}),
                                 ("halves", {"loop-1": "low", "loop-2": "low", "loop-3": "high", "loop-4": "high"})):
            out = play(steady("converge", groups=groups), 4, 10, 1, pool=40)
            size = len(out["order"])
            for loop, end in expected.items():
                first = rank_sequences(out)[loop][0]
                self.assertEqual(first < size // 2, end == "low", (groups, loop))
        out = play(steady("converge", first_end="high"), 3, 10, 1, pool=40)
        size = len(out["order"])
        self.assertGreater(rank_sequences(out)["loop-1"][0], size // 2)
        self.assertEqual(sum(r[0] > size // 2 for r in rank_sequences(out).values()), 2)    # odd loop count: extra at that end

    def test_oldest_and_newest_ends_follow_the_order_direction(self):
        out = play(steady("converge", first_end="low"), 2, 10, 1, pool=40)
        stamps = {r["id"]: po.parse_captured_at(r["captured_at"]) for r in pool_of(40) if "captured_at" in r}
        first = out["schedule"].initial["loop-1"]
        second = out["schedule"].initial["loop-2"]
        self.assertEqual(stamps[first], min(stamps[c] for c in out["order"]))
        self.assertEqual(stamps[second], max(stamps[c] for c in out["order"]))


class StartingZoneTests(unittest.TestCase):
    """Every walker of converge and diverge starts inside the zone it will walk, for every order size and loop count."""

    def test_every_walker_starts_inside_its_zone_whatever_the_order_size_loop_count_and_end(self):
        from simvltanea.authoring.play_paths import make_walkers
        for shape in ("converge", "diverge"):
            for first_end in ("low", "high"):
                for groups in ("alternate", "halves"):
                    path = steady(shape, first_end=first_end, groups=groups)["path"]
                    for n in range(2, 8):
                        for size in range(n, n + 12):
                            walkers = make_walkers(shape, path, size, n)
                            for index, w in enumerate(walkers):
                                with self.subTest(shape=shape, first_end=first_end, groups=groups, n=n, size=size,
                                                  loop=index):
                                    self.assertTrue(w.lo <= w.pos <= w.hi, (w.pos, w.lo, w.hi))
                                    self.assertEqual((w.pos, w.dir), (w.start, w.start_dir))
                            self.assertEqual(len({w.pos for w in walkers}), n, "two loops start on the same clip")

    def test_with_as_many_clips_as_loops_every_clip_is_shown_from_the_start_for_both_ends(self):
        for first_end in ("low", "high"):
            for n in (3, 5, 7):
                records = [clean_record(i) | {"captured_at": f"2024-01-{i + 1:02d}T00:00:00+00:00"} for i in range(n)]
                out = play(steady("converge", first_end=first_end), n, 10, 1, records=records)
                self.assertEqual(len(set(out["schedule"].initial.values())), n, (first_end, n))


class DivergeTests(unittest.TestCase):
    def test_starts_in_the_middle_and_moves_to_both_ends(self):
        out = play(steady("diverge", wrap="stop"), 2, 300, 1, pool=40)
        size = len(out["order"])
        ranks = rank_sequences(out)
        for r in ranks.values():
            self.assertLessEqual(abs(r[0] - size // 2), 2)
        self.assertEqual(min(ranks["loop-1"][-1], ranks["loop-2"][-1]), 0)
        self.assertEqual(max(ranks["loop-1"][-1], ranks["loop-2"][-1]), size - 1)
        first_gap = abs(ranks["loop-1"][0] - ranks["loop-2"][0])
        self.assertLessEqual(first_gap, 2)

    def test_bounce_returns_to_the_middle_and_wrap_restarts_there(self):
        out = play(steady("diverge", wrap="bounce"), 2, 400, 1, pool=40)
        size = len(out["order"])
        for r in rank_sequences(out).values():
            steps = [b - a for a, b in zip(r, r[1:])]
            self.assertTrue({1, -1} <= set(steps) <= {1, -1, 2, -2})
        out = play(steady("diverge", wrap="wrap"), 2, 400, 1, pool=40)
        for r in rank_sequences(out).values():
            jumps = [abs(b - a) for a, b in zip(r, r[1:])]
            self.assertGreater(max(jumps), size // 4)               # restarted in the middle


class RoundTests(unittest.TestCase):
    def canon(self, voice, base, tag="shot", n=4, seconds=80, delay=3, pool=120, **extra):
        config = cfg("sticky", order={"axis": "captured_at"},
                     path={"shape": "round", "base": base, "voice": voice, "tag": tag, "delay_beats": delay,
                           "beat_seconds": 2.0, **extra},
                     relation={"strength": 0.0}, timing={**PLAIN, "synchronized": True, "hold_min": 4.0, "hold_max": 4.0})
        return play(config, n, seconds, 3, pool=pool), 3 * 2.0

    def assert_exact_canon(self, out, delay_seconds, key=lambda clip: clip):
        at = clip_at(out)
        shift = round(delay_seconds * FPS)
        loops = out["schedule"].loop_ids
        checked = 0
        for k, loop in enumerate(loops):
            for frame in range(k * shift, out["schedule"].frames):
                self.assertEqual(key(at(loop, frame)), key(at(loops[0], frame - k * shift)), (loop, frame))
                checked += 1
        self.assertGreater(checked, 2000)

    def test_loop_k_plays_loop_0s_clips_exactly_k_delays_later_for_every_base_shape(self):
        for base in ("sequential", "random", "playlist", "follow", "converge", "diverge", "pingpong"):
            with self.subTest(base=base):
                out, delay = self.canon("clips", base, wrap="bounce")
                self.assert_exact_canon(out, delay)
                for _, snap in out["schedule"].timeline():
                    self.assertEqual(len(set(snap.values())), 4)       # never the same clip on two loops

    def test_the_voice_really_is_a_walk_not_a_constant(self):
        out, _ = self.canon("clips", "sequential")
        seq = rank_sequences(out)["loop-1"]
        self.assertGreater(len(set(seq)), 15)
        self.assertEqual(set(diffs(seq, len(out["order"]))), {1})

    def test_tag_voice_repeats_the_tag_sequence_on_different_clips(self):
        for tag in ("shot", "time_of_day", "motion_level", "environment"):
            with self.subTest(tag=tag):
                out, delay = self.canon("tags", "random", tag=tag, n=3)
                profiles = out["model"].profiles
                self.assert_exact_canon(out, delay, key=lambda clip: getattr(profiles[clip], tag))
                at = clip_at(out)
                shift = round(delay * FPS)
                same_clip = total = 0
                for frame in range(2 * shift, out["schedule"].frames, FPS):
                    total += 1
                    same_clip += at("loop-3", frame) == at("loop-1", frame - 2 * shift)
                self.assertLess(same_clip / total, 0.5)           # different clips carrying the same tag value
                for _, snap in out["schedule"].timeline():
                    self.assertEqual(len(set(snap.values())), 3)

    def test_a_delay_shorter_than_the_hold_is_a_clear_error_for_clip_voices(self):
        with self.assertRaisesRegex(PlayError, "same clip would be on two loops"):
            self.canon("clips", "sequential", delay=1)
        out, _ = self.canon("tags", "random", delay=1, n=3)       # tags: no duplication problem
        self.assertEqual(len(out["schedule"].loop_ids), 3)

    def test_a_voice_that_must_repeat_a_clip_on_two_loops_is_an_error_not_a_duplicate(self):
        # A halting base is refused at validation (F5); an order too short for the loops is still caught when the
        # schedule is built.
        with self.assertRaisesRegex(PlayError, "path.wrap=stop"):
            self.canon("clips", "sequential", n=4, wrap="stop", seconds=300, pool=40)
        with self.assertRaisesRegex(PlayError, "too few clips for this canon"):
            self.canon("clips", "sequential", n=4, seconds=300, pool=9)

    def test_every_change_lands_on_the_beat_grid(self):
        out, _ = self.canon("clips", "sequential", n=3)
        beat = round(2.0 * FPS)
        self.assertTrue(all(ch["frame"] % beat == 0 for ch in out["schedule"].changes))

    def test_beat_must_divide_the_hold_at_this_frame_rate(self):
        config = cfg("round_clips", path={"beat_seconds": 1.0, "delay_beats": 5}, timing={"hold_min": 4.0, "hold_max": 4.0})
        play(config, 3, 30, 1, pool=120)
        config = cfg("round_clips", path={"beat_seconds": 1.3, "delay_beats": 5}, timing={"hold_min": 3.9, "hold_max": 3.9})
        with self.assertRaises(PlayError):
            play(config, 3, 30, 1, pool=120)


class PlaylistTests(unittest.TestCase):
    def test_every_clip_is_dealt_once_before_any_clip_repeats(self):
        config = cfg("sticky", path={"shape": "playlist"}, relation={"strength": 0.0}, timing=dict(PLAIN))
        out = play(config, 4, 260, 1, pool=30)
        eligible = sorted(out["model"].profiles)
        sched = out["schedule"]
        draws = [sched.initial[l] for l in sorted(sched.loop_ids, key=lambda l: sched.initial[l])]
        # initial draws come in seeded order; what matters is that they belong to deck one
        draws += [ch["clip"] for ch in sched.changes if ch["op"] == "show"]
        size = len(eligible)
        self.assertGreater(len(draws), 4 * size)                   # several decks
        for start in range(0, len(draws) - size + 1, size):
            self.assertEqual(sorted(draws[start:start + size]), eligible, start)

    def test_window_lets_the_relation_choose_among_the_next_cards(self):
        config = cfg("sticky", path={"shape": "playlist", "window": 5}, timing=dict(PLAIN))
        out = play(config, 3, 120, 1, pool=60)
        self.assertGreater(len(out["schedule"].changes), 20)


class FollowTests(unittest.TestCase):
    def thread_affinity(self, out):
        model = out["model"]
        from simvltanea.authoring.gravity_affinity import build_affinity_model
        full = build_affinity_model([r for r in pool_of(120) if r["id"] in model.profiles])
        vals = []
        for seq in sequences(out).values():
            vals += [full.affinity(a, b) for a, b in zip(seq, seq[1:])]
        return sum(vals) / len(vals)

    def test_each_loop_walks_to_related_clips_and_negative_strength_walks_away(self):
        mean = lambda strength: sum(self.thread_affinity(play(cfg("sticky", path={"shape": "follow"}, relation={  # noqa: E731
            "strength": strength, "independence": 1.0}, timing=dict(PLAIN)), 3, 150, s, pool=120)) for s in (1, 2)) / 2
        near, neutral, far = mean(3.0), mean(0.0), mean(-3.0)
        self.assertGreater(near, neutral + 40)
        self.assertLess(far, neutral - 40)


class WindowTests(unittest.TestCase):
    def mean_jump(self, window, strength=0.0):
        config = steady("sequential", spread="even", window=window)
        config["relation"]["strength"] = strength
        out = play(config, 2, 200, 1, pool=120)
        size = len(out["order"])
        jumps = []
        for seq in rank_sequences(out).values():
            jumps += [(b - a) % size for a, b in zip(seq, seq[1:])]
        return sum(jumps) / len(jumps), jumps

    def test_window_widens_the_choice_from_exactly_the_next_clip(self):
        zero, jumps = self.mean_jump(0)
        self.assertEqual(set(jumps), {1})
        means = [self.mean_jump(w)[0] for w in (0, 2, 8, 30)]
        self.assertTrue(all(b > a for a, b in zip(means, means[1:])), means)
        self.assertGreater(means[-1], 5)

    def test_chronological_but_gravity_flavoured_is_window_plus_strength(self):
        from simvltanea.authoring.test_play_support import mean_affinity
        def level(strength):
            config = steady("sequential", spread="together", window=10)
            config["relation"]["strength"] = strength
            return sum(mean_affinity(play(config, 3, 200, s, pool=120)) for s in (1, 2)) / 2
        self.assertGreater(level(4.0), level(0.0) + 20)


if __name__ == "__main__":
    unittest.main()
