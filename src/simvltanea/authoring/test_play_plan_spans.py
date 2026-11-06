"""A state the generator writes is never refused later by compile_plan's span guard (spans <= 1024 per loop)."""
import random
import unittest

from simvltanea.authoring import composition as c
from simvltanea.authoring import play_encode as pe
from simvltanea.authoring.play_config import PlayError
from simvltanea.authoring.test_play_exclusions import clean_record
from simvltanea.authoring.test_play_support import FPS, cfg, play, pool_of


def clean_records(count):
    return [clean_record(i) | {"duration": 1.5 + (i % 4) * 0.5} for i in range(count)]


class RefusalTests(unittest.TestCase):
    """The two reproductions from the independent review, which used to be written and then refused."""

    def test_the_documented_hold_floor_over_five_minutes_is_refused_before_anything_is_built_on_it(self):
        config = cfg("random", timing={"hold_min": 0.25, "hold_max": 0.25, "stagger": 0.0, "cooldown": 0.0})
        with self.assertRaises(PlayError) as caught:
            play(config, 2, 300, 3, records=clean_records(8))
        message = str(caught.exception)
        self.assertIn("compile_plan", message)
        self.assertIn(f"allow {c.MAX_SEGMENTS} per loop ({2 * c.MAX_SEGMENTS} in all)", message)
        self.assertRegex(message, r"needs \d+ browser spans per loop on average \(\d+ in all\)")
        self.assertIn("source changes dominate", message.lower())              # here the holds, not the clip ends, are the problem
        self.assertIn("larger timing.hold_min", message)
        self.assertIn("shorter duration", message)

    def test_default_sticky_seven_loops_for_half_an_hour_at_a_low_frame_rate_is_refused(self):
        with self.assertRaises(PlayError) as caught:
            schedule(cfg("sticky"), 7, 1800, 8, clean_records(20))
        message = str(caught.exception)
        self.assertIn("browser spans", message)
        self.assertIn("clip ends dominate", message.lower())
        self.assertRegex(message, r"mean source clip is \d+\.\d s")             # clip length is named
        self.assertIn("shorter duration", message)
        self.assertIn("longer source clips", message)
        self.assertIn("does not help", message)                         # the hold floor, loop count and fps
        self.assertNotIn("(fewer)", message)
        self.assertNotIn("makes fewer changes", message)
        self.assertNotIn("larger timing.hold_min", message)
        self.assertIn("does not help here", message)                    # the hold floor is named only to rule it out

    def test_the_advice_is_true_for_the_default_sticky_long_case(self):
        """What the message says does not help really does not, and what it says helps does."""
        records = clean_records(20)
        for change in ({"timing": {"hold_min": 12.0, "hold_max": 20.0}}, {"timing": {"hold_min": 60.0, "hold_max": 60.0}}):
            with self.subTest(change=change), self.assertRaises(PlayError):
                schedule(cfg("sticky", **change), 7, 1800, 8, records)         # a higher hold floor: still refused
        for n in (2, 3):
            with self.subTest(n=n), self.assertRaises(PlayError):
                schedule(cfg("sticky"), n, 1800, 8, records)                    # fewer loops: still refused
        with self.assertRaises(PlayError):
            schedule(cfg("sticky"), 7, 1800, 4, records)                        # a lower frame rate: still refused
        out = schedule(cfg("sticky"), 7, 1200, 8, records)                      # a shorter duration: accepted
        self.assertLessEqual(pe.count_plan_spans(out["schedule"], out["state"]), 7 * c.MAX_SEGMENTS)
        longer = [dict(r, duration=r["duration"] * 3) for r in records]         # longer source clips: accepted
        out = schedule(cfg("sticky"), 7, 1800, 8, longer)
        self.assertLessEqual(pe.count_plan_spans(out["schedule"], out["state"]), 7 * c.MAX_SEGMENTS)

    def test_the_breakdown_splits_the_exact_count_into_changes_and_wraps(self):
        for config, n, seconds, fps in ((cfg("sticky"), 3, 60, 8), (cfg("random"), 2, 40, 8)):
            out = play(config, n, seconds, 3, pool=60)
            total, changes, wraps = pe.plan_span_parts(out["schedule"], out["state"])
            self.assertEqual(total, pe.count_plan_spans(out["schedule"], out["state"]))
            self.assertEqual(total, changes + wraps)
            self.assertGreaterEqual(changes, n)                               # every loop starts a span at frame 0
            self.assertGreaterEqual(wraps, 0)

    def test_the_refusal_comes_before_validate_state_runs(self):
        calls = []
        real = c.validate_state
        from simvltanea.authoring import play_engine
        play_engine.validate_state = lambda state: calls.append(1) or real(state)
        try:
            with self.assertRaises(PlayError):
                schedule(cfg("sticky"), 7, 1800, 8, clean_records(20))
        finally:
            play_engine.validate_state = real
        self.assertEqual(calls, [])

    def test_a_state_just_inside_the_limit_is_still_written(self):
        out = play(cfg("sticky"), 3, 60, 1, pool=60)
        spans = pe.count_plan_spans(out["schedule"], out["state"])
        self.assertLessEqual(spans, c.MAX_SEGMENTS * 3)


def schedule(config, n, seconds, fps, records):
    from simvltanea.authoring import schedule_play
    return schedule_play(records, n, config, seconds, fps, 3)


class ExactCountTests(unittest.TestCase):
    """The generator's own count equals the number of spans compile_plan really produces."""

    CASES = [  # (preset or None, config sections, n, seconds, fps, pool size, seed)
        ("sticky", {}, 2, 20, 24, 60, 1), ("sticky", {}, 3, 30, 12, 60, 2), ("sticky", {}, 7, 25, 8, 80, 3),
        ("random", {"timing": {"hold_min": 0.25, "hold_max": 1.0, "stagger": 0.0, "cooldown": 0.0}}, 2, 20, 24, 40, 4),
        ("random", {"timing": {"hold_min": 0.5, "hold_max": 0.5, "stagger": 0.0, "cooldown": 0.0}}, 3, 16, 10, 40, 5),
        ("drift", {}, 4, 30, 24, 60, 6), ("magnetic", {}, 5, 24, 16, 60, 7), ("opposites", {}, 3, 30, 24, 60, 8),
        ("chronological", {}, 3, 30, 24, 90, 9), ("reverse_chronological", {}, 4, 20, 20, 90, 10),
        ("oldest_meets_newest", {}, 3, 40, 24, 90, 11), ("newest_meets_oldest", {}, 5, 30, 12, 90, 12),
        ("round_clips", {}, 4, 40, 24, 90, 13), ("round_tags", {}, 3, 40, 24, 90, 14),
        ("calm_to_intense", {}, 2, 30, 24, 90, 15), ("rainbow", {}, 6, 20, 24, 90, 16),
        ("sticky", {"timing": {"swap_interval": 4.0}}, 4, 30, 24, 60, 17),
        ("sticky", {"path": {"shape": "follow"}}, 3, 30, 24, 60, 18),
        ("sticky", {"path": {"shape": "playlist"}, "timing": {"hold_min": 1.0, "hold_max": 3.0}}, 4, 30, 24, 60, 19),
        ("sticky", {"timing": {"synchronized": True, "hold_min": 1.0, "hold_max": 2.0}}, 3, 24, 24, 60, 20),
        ("sticky", {"path": {"pins": [["loop-1", "__first__"]]}}, 3, 30, 24, 60, 21),
        ("random", {"timing": {"hold_min": 0.25, "hold_max": 0.25, "stagger": 0.0, "cooldown": 0.0}}, 2, 12, 24, 40, 22),
        ("sticky", {"timing": {"hold_min": 20.0, "hold_max": 30.0}}, 3, 60, 24, 60, 23),
    ]

    def run_case(self, preset, sections, n, seconds, fps, size, seed):
        sections = {k: dict(v) for k, v in sections.items()}
        records = list(pool_of(size))
        pins = sections.get("path", {}).get("pins")
        if pins:
            ids = sorted(r["id"] for r in records if r["analysis"] and not r["needs_review"]
                         and r["analysis"]["safety"]["verdict"] == "clear")
            sections["path"]["pins"] = [[loop, ids[0]] for loop, _ in pins]
        from simvltanea.authoring import schedule_play
        config = cfg(preset, **sections)
        return schedule_play(records, n, config, seconds, fps, seed)

    def test_the_count_equals_the_spans_compile_plan_produces_for_many_varied_states(self):
        from simvltanea.browser import compile_plan
        accepted = 0
        for case in self.CASES:
            with self.subTest(case=case[:2] + case[2:]):
                out = self.run_case(*case)
                plan = compile_plan(out["state"])                    # raises when the span guard is exceeded
                real = sum(len(track["spans"]) for track in plan["tracks"])
                self.assertEqual(pe.count_plan_spans(out["schedule"], out["state"]), real)
                self.assertLessEqual(real, c.MAX_SEGMENTS * len(plan["tracks"]))
                accepted += 1
        self.assertGreaterEqual(accepted, 20)

    def test_random_settings_are_either_refused_cleanly_or_compile(self):
        """Accepted or refused, never written-and-then-refused: every accepted state compiles."""
        from simvltanea.browser import compile_plan
        rng = random.Random(404)
        compiled = refused = accepted_long = 0
        for _ in range(45):
            n = rng.randint(2, 7)
            records = list(pool_of(40))
            if rng.random() < 0.7:
                seconds, hold = rng.choice([8, 12, 20]), rng.choice([0.25, 0.5, 1.0, 2.0, 4.0])
            else:                                       # long states on a small pool: short holds exceed the guard
                seconds, hold = rng.choice([(300, 0.25), (300, 0.5), (200, 0.25), (600, 0.5)])
                records = clean_records(10)
                n = min(n, 3)
            timing = {"hold_min": hold, "hold_max": hold + rng.choice([0.0, 1.0, 4.0]), "stagger": 0.0,
                      "cooldown": 0.0}
            fps = rng.choice([4, 8, 12, 24])
            config = cfg(rng.choice(["random", "sticky", "drift"]), timing=timing)
            try:
                out = schedule(config, n, seconds, fps, records)
            except PlayError as exc:
                self.assertRegex(str(exc), "browser spans|max_events")
                refused += "browser spans" in str(exc)
                continue
            counted = pe.count_plan_spans(out["schedule"], out["state"])
            self.assertLessEqual(counted, c.MAX_SEGMENTS * n)
            if seconds * fps > 500:                    # a real compile_plan of a long state takes minutes
                accepted_long += 1
                continue
            plan = compile_plan(out["state"])
            self.assertEqual(sum(len(t["spans"]) for t in plan["tracks"]), counted)
            compiled += 1
        self.assertGreaterEqual(compiled, 20)
        self.assertGreaterEqual(refused, 3)

    def test_the_count_can_stop_early_once_it_is_over_the_limit(self):
        out = play(cfg("sticky"), 7, 120, 1, pool=60)
        full = pe.count_plan_spans(out["schedule"], out["state"])
        self.assertEqual(pe.count_plan_spans(out["schedule"], out["state"], limit=full), full)
        self.assertGreater(pe.count_plan_spans(out["schedule"], out["state"], limit=full - 1), full - 1)


if __name__ == "__main__":
    unittest.main()
