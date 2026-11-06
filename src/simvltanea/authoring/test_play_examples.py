"""The owner's examples, each as a preset, with evidence that it behaves as described."""
import statistics
import unittest

from simvltanea.authoring import play_order as po
from simvltanea.authoring.play_presets import PRESETS
from simvltanea.authoring.test_play_support import (FPS, clip_at, play, pool_of, rank_sequences, sequences,
                                                    spearman)


def feature(out, clip, name):
    record = next(r for r in pool_of(120) if r["id"] == clip)
    if name == "captured_at":
        return po.parse_captured_at(record["captured_at"])
    return record["features"][name]


def time_series(out, loop, name):
    """(frames, values) of the clips a loop shows, in order."""
    sched = out["schedule"]
    frames = [0] + [ch["frame"] for ch in sched.changes if ch["op"] == "show" and ch["loop"] == loop]
    return frames, [feature(out, clip, name) for clip in sequences(out)[loop]]


class OwnerExampleTests(unittest.TestCase):
    def test_totally_random_has_no_order_and_covers_the_pool(self):
        out = play(PRESETS["random"], 3, 300, 1, pool=60)
        for loop in out["schedule"].loop_ids:
            frames, values = time_series(out, loop, "luma")
            self.assertLess(abs(spearman(frames, values)), 0.3)
        seen = {c for seq in sequences(out).values() for c in seq}
        self.assertGreater(len(seen) / len(out["model"].profiles), 0.8)

    def test_chronological_runs_oldest_to_newest_and_reverse_runs_the_other_way(self):
        for name, sign in (("chronological", 1), ("reverse_chronological", -1)):
            out = play(PRESETS[name], 3, 25, 1, pool=120)
            for loop in out["schedule"].loop_ids:
                frames, values = time_series(out, loop, "captured_at")
                self.assertGreater(sign * spearman(frames, values), 0.99, (name, loop))
                self.assertTrue(all(sign * (b - a) > 0 for a, b in zip(values, values[1:])), (name, loop))

    def test_oldest_meets_newest_in_the_middle(self):
        # Long enough (600 s) for the two loops to travel to the middle, meet there and bounce back out.
        out = play(PRESETS["oldest_meets_newest"], 2, 600, 1, pool=120)
        ranks = rank_sequences(out)
        low, high = ranks["loop-1"], ranks["loop-2"]
        size = len(out["order"])
        self.assertEqual((low[0], high[0]), (0, size - 1))                 # one loop starts at each end
        low_turn, high_turn = low.index(max(low)), high.index(min(high))
        self.assertTrue(all(b > a for a, b in zip(low[:low_turn], low[1:low_turn + 1])))      # forward in time ...
        self.assertTrue(all(b < a for a, b in zip(high[:high_turn], high[1:high_turn + 1])))  # ... and backward
        self.assertLess(low[-1], max(low))                                 # both loops really turned round ...
        self.assertGreater(high[-1], min(high))                            # ... and are on the way out again
        low_front, high_front = self.fronts(out)
        gap = min(h - l for l, h in zip(low_front, high_front))
        self.assertLessEqual(gap, 4)                                       # they came within a few clips of each other
        self.assertLessEqual(abs((max(low) + min(high)) / 2 - size / 2), 3)       # near the middle of the order
        newest_first = play(PRESETS["newest_meets_oldest"], 3, 10, 1, pool=120)
        self.assertEqual(feature(newest_first, newest_first["schedule"].initial["loop-1"], "captured_at"),
                         max(feature(newest_first, c, "captured_at") for c in newest_first["order"]))

    @staticmethod
    def fronts(out):
        """(per snapshot the highest rank shown by a loop that started in the low half, the lowest rank of the others)."""
        rank = {clip: i for i, clip in enumerate(out["order"])}
        timeline = out["schedule"].timeline()
        size = len(rank)
        start = timeline[0][1]
        low = [l for l in start if rank[start[l]] < size / 2]
        high = [l for l in start if l not in low]
        return ([max(rank[snap[l]] for l in low) for _, snap in timeline],
                [min(rank[snap[l]] for l in high) for _, snap in timeline])

    def test_the_two_fronts_meet_in_the_middle_for_every_loop_count_odd_or_even(self):
        # The preset's own random holds (4 to 12 s), long enough (600 s on 96 clips) to reach the middle. Measured over
        # seeds 1 to 8 (the run is deterministic): the median smallest gap between the fronts is at most 4 ranks for
        # every N (2: 3, 3: 2, 4: 4, 5: 1.5, 7: 1 for oldest_meets_newest; 2, 3.5, 3, 3, 1 for newest_meets_oldest) and
        # the turn is exactly at the middle (offset 0) in all 80 runs, so those are the bounds.
        for name in ("oldest_meets_newest", "newest_meets_oldest"):
            for n in (2, 3, 4, 5, 7):
                gaps, turns = [], []
                for seed in range(1, 9):
                    out = play(PRESETS[name], n, 600, seed, pool=96)
                    low_front, high_front = self.fronts(out)
                    size = len(out["order"])
                    gaps.append(min(h - l for l, h in zip(low_front, high_front)))
                    turns.append((max(low_front) + min(high_front)) / 2 - size / 2)
                    ranks = rank_sequences(out)
                    start = out["schedule"].initial
                    low_loops = [l for l in start if out["order"].index(start[l]) < size / 2]
                    self.assertGreater(max(low_front), size // 4, (name, n, seed))          # they did travel
                    self.assertTrue(any(b < a for l in low_loops for a, b in zip(ranks[l], ranks[l][1:])), (name, n, seed))
                    self.assertTrue(any(b > a for l in ranks if l not in low_loops
                                        for a, b in zip(ranks[l], ranks[l][1:])), (name, n, seed))
                with self.subTest(preset=name, n=n):
                    self.assertLessEqual(statistics.median(gaps), 4, gaps)         # fronts come within a few ranks
                    self.assertEqual(statistics.median(turns), 0, turns)            # and the turn is at the middle

    def test_a_round_of_clips_is_an_exact_canon(self):
        out = play(PRESETS["round_clips"], 4, 100, 1, pool=120)
        at, shift = clip_at(out), 3 * 2 * FPS
        for k, loop in enumerate(out["schedule"].loop_ids):
            for frame in range(k * shift, out["schedule"].frames, 5):
                self.assertEqual(at(loop, frame), at("loop-1", frame - k * shift))

    def test_a_round_of_tags_repeats_the_shot_sequence_on_different_clips(self):
        out = play(PRESETS["round_tags"], 3, 100, 1, pool=120)
        at, shift = clip_at(out), 3 * 2 * FPS
        shots = {r: out["model"].profiles[r].shot for r in out["model"].profiles}
        different = total = 0
        for k, loop in enumerate(out["schedule"].loop_ids):
            for frame in range(k * shift, out["schedule"].frames, 7):
                a, b = at(loop, frame), at("loop-1", frame - k * shift)
                self.assertEqual(shots[a], shots[b])
                if k:
                    total += 1
                    different += a != b
        self.assertGreater(different / total, 0.5)

    def test_calm_to_intense_dark_to_light_and_rainbow_follow_their_axes(self):
        for name, axis in (("calm_to_intense", "motion"), ("dark_to_light", "luma"), ("rainbow", "hue")):
            out = play(PRESETS[name], 2, 100, 1, pool=120)
            frames, values = time_series(out, "loop-1", axis)
            self.assertGreater(len(values), 8)
            self.assertGreater(spearman(frames, values), 0.85, name)


if __name__ == "__main__":
    unittest.main()
