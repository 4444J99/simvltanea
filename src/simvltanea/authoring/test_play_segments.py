"""Renderer limit (L8): the segment estimate, the bound from settings alone, and the guard that uses them."""
import copy
import random
import unittest
from fractions import Fraction

from simvltanea.authoring.play_config import PlayError
from simvltanea.authoring.play_encode import (base_state_for, count_plan_spans, estimate_render_segments,
                                              render_segment_bound, render_segment_estimate, wrap_frames)
from simvltanea.authoring.play_pool import MIN_CLIP_SECONDS, media_problem
from simvltanea.authoring.test_play_support import cfg, play, pool_of, time_limit

FPS = 24


def rates(n):
    return [Fraction(loop["rate"]) for loop in base_state_for(n)["loops"]]


class SegmentBoundTests(unittest.TestCase):
    def test_a_hand_computed_case(self):
        # one loop at rate 1, 10 s at 24 fps, holds of 4 s: at most (239 // 96) + 1 = 3 changes,
        # so 1 + (2 * 3 + 1 + 10 / 2) = 13 segments for clips of at least 2 s.
        self.assertEqual(render_segment_bound([1], 10, 4, 2), 13)
        self.assertEqual(render_segment_estimate([1], 10, 8, 2), 8)         # 1 + 10 * (1/2 + 1/8) = 7.25 -> 8
        self.assertEqual(render_segment_bound([1], 10, 4, 2, swap_interval=5), 13 + 3 * 3)

    def test_the_bound_is_never_below_the_exact_count_the_engine_reports(self):
        shortest = min(r["duration"] for r in pool_of(120))
        checked = 0
        for mode in ("sticky", "random", "chronological", "oldest_meets_newest", "opposites", "round_clips"):
            for n in (2, 4, 7):
                for hold in (4.0, 12.0):
                    if mode == "round_clips":
                        if hold != 4.0:
                            continue
                        timing = {"hold_min": hold, "hold_max": hold}
                    else:
                        timing = {"hold_min": hold, "hold_max": hold + 8}
                    for seed in (1, 2):
                        config = cfg(mode, timing=timing, limits={"refuse_unrenderable": False})
                        out = play(config, n, 90, seed, pool=120)
                        bound = render_segment_bound(rates(n), 90, hold, shortest, FPS)
                        self.assertLessEqual(out["report"]["render_segments"], bound, (mode, n, hold, seed))
                        checked += 1
        self.assertEqual(checked, 5 * 3 * 2 * 2 + 3 * 1 * 2)       # round_clips runs for hold 4 only

    def test_the_bound_covers_swaps(self):
        shortest = min(r["duration"] for r in pool_of(120))
        config = cfg("sticky", timing={"swap_interval": 3.0})
        out = play(config, 4, 90, 1, pool=120)
        self.assertGreater(out["report"]["encoding"]["swap_events"], 0)
        self.assertLessEqual(out["report"]["render_segments"],
                             render_segment_bound(rates(4), 90, 4.0, shortest, FPS, swap_interval=3.0))

    def test_the_estimate_tracks_the_exact_count_for_default_holds(self):
        mean_clip = sum(r["duration"] for r in pool_of(120)) / 120
        for n in (3, 5, 7):
            exact = [play(cfg("sticky"), n, 240, seed)["report"]["render_segments"] for seed in (1, 2, 3)]
            estimate = render_segment_estimate(rates(n), 240, 8.0, mean_clip)
            for value in exact:
                self.assertLess(abs(value - estimate) / estimate, 0.15, (n, value, estimate))


class RefusalTests(unittest.TestCase):
    def test_a_long_state_is_reported_unrenderable_and_refused_when_asked(self):
        long_run = dict(n=7, seconds=600, seed=1, pool=120)
        report = play(cfg("sticky"), **long_run)["report"]
        self.assertFalse(report["renderable"])
        self.assertGreater(report["render_segments"], report["render_segment_limit"])
        with self.assertRaisesRegex(PlayError, "render segments"):
            play(cfg("sticky", limits={"refuse_unrenderable": True}), **long_run)

    def test_a_short_state_is_renderable_by_the_same_count(self):
        report = play(cfg("sticky"), 3, 12, 1, pool=120)["report"]
        self.assertTrue(report["renderable"])
        self.assertLessEqual(report["render_segments"], report["render_segment_limit"])


if __name__ == "__main__":
    unittest.main()


def reference_wraps(start, end, offset, d, rate, fps):
    """The frames a loop's clock wraps, found by testing every frame (slow and obviously right)."""
    local = lambda frame: offset + Fraction(frame) * rate / fps
    return [f for f in range(start + 1, end) if local(f) // d > local(f - 1) // d]


class TinyClipTests(unittest.TestCase):
    """DP-1: a clip of a tiny positive duration must neither hang the scheduler nor be shown."""

    def test_the_floor_is_one_frame_at_24_fps_and_excludes_anything_shorter(self):
        self.assertEqual(MIN_CLIP_SECONDS, Fraction(1, 24))
        base = {"sha256": "a" * 64}
        for duration in (1 / 24, 0.041667, 0.05, 1, 2):
            self.assertIsNone(media_problem({**base, "duration": duration}), duration)
        for duration in (1e-9, 0.04, 1 / 25, 1e-300, "1e-9", "1e-400", "0.04", 0, -1, float("nan"), float("inf")):
            self.assertEqual(media_problem({**base, "duration": duration}), "media_duration", duration)
        with time_limit(10):                                                # must not build a 10**999999999 integer
            for duration in ("1e999999999", "1e-999999999", "-1e999999999", "nan", "Infinity", "0x10", ""):
                self.assertEqual(media_problem({**base, "duration": duration}), "media_duration", duration)

    def test_a_receipt_with_a_tiny_duration_is_skipped_quickly_and_counted(self):
        pool = [copy.deepcopy(r) for r in pool_of(120)]
        victim = next(r for r in pool if r["analysis"] and not r["needs_review"] and not r["error"])
        victim["duration"] = 1e-9
        with time_limit(10):
            out = play(cfg("sticky"), 3, 60, 1, records=pool)
        self.assertEqual(out["report"]["excluded_counts"].get("media_duration"), 1)
        self.assertNotIn(victim["id"], {s["id"] for s in out["state"]["sources"]})

    def test_the_wrap_walk_is_bounded_by_the_span_not_by_the_clip_length(self):
        out = play(cfg("sticky"), 3, 30, 1, pool=120)
        state = copy.deepcopy(out["state"])
        for source in state["sources"]:
            source["duration"] = "1/1000000000"
        with time_limit(10):
            segments = estimate_render_segments(out["schedule"], state)
            spans = count_plan_spans(out["schedule"], state)
        self.assertEqual(segments, out["schedule"].frames)                  # a wrap on every frame
        self.assertGreaterEqual(spans, out["schedule"].frames * len(state["loops"]))

    def test_the_analytic_walk_agrees_with_testing_every_frame(self):
        rng = random.Random(9)
        for _ in range(400):
            fps = rng.choice([8, 24, 30, 60])
            rate = Fraction(rng.choice(["1/2", "3/4", "1", "5/4", "3", "1/7"]))
            offset = Fraction(rng.randint(0, 50), rng.choice([1, 3, 7]))
            d = Fraction(rng.randint(1, 4000), rng.choice([100, 1000]))
            start = rng.randint(0, 60)
            end = start + rng.randint(0, 120)
            self.assertEqual(sorted(set(wrap_frames(start, end, offset, d, rate, fps))),
                             reference_wraps(start, end, offset, d, rate, fps), (fps, rate, offset, d, start, end))
        self.assertEqual(len(list(wrap_frames(0, 500, Fraction(0), Fraction(1, 10 ** 9), Fraction(1), 24))), 499)
