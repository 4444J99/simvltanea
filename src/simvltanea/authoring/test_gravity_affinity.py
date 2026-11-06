"""Affinity: bounds, symmetry, graceful degradation, weights and cross-process reproducibility."""
import ast
import copy
import hashlib
import random
from fractions import Fraction
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from simvltanea.authoring import gravity_affinity as ga
from simvltanea.authoring.test_gravity_pool import make_pool, strip_tags

SRC = str(Path(__file__).resolve().parents[2])

CHILD = """
import hashlib, json
from simvltanea.authoring import gravity_affinity as ga
from simvltanea.authoring.test_gravity_pool import make_pool
pool = make_pool(40)
model = ga.build_affinity_model(pool)
ids = sorted(r["id"] for r in pool)
table = [[model.affinity(a, b) for b in ids] for a in ids]
print(hashlib.sha256(json.dumps(table).encode()).hexdigest())
"""


class AffinityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = make_pool(120)
        cls.model = ga.build_affinity_model(cls.pool)
        cls.ids = sorted(r["id"] for r in cls.pool)
        cls.truth = {r["id"]: set(r["_truth"]) for r in cls.pool}

    def test_integer_bounds_and_symmetry(self):
        for a in self.ids[:30]:
            for b in self.ids[:30]:
                value = self.model.affinity(a, b)
                self.assertIs(type(value), int)
                self.assertTrue(0 <= value <= ga.AFFINITY_SCALE)
                self.assertEqual(value, self.model.affinity(b, a))

    def test_default_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(ga.DEFAULT_WEIGHTS.values()), 1.0)
        self.assertEqual(set(ga.ALL_COMPONENTS), set(self.model.components(self.ids[0], self.ids[1])))

    def test_self_is_maximal(self):
        for a in self.ids[:20]:
            best = max(self.model.affinity(a, b) for b in self.ids if b != a)
            self.assertGreaterEqual(self.model.affinity(a, a), best)

    def test_same_theme_pairs_score_higher(self):
        same, other = [], []
        for i, a in enumerate(self.ids):
            for b in self.ids[i + 1:]:
                (same if self.truth[a] & self.truth[b] else other).append(self.model.affinity(a, b))
        self.assertGreater(sum(same) / len(same), sum(other) / len(other) + 100)

    def test_no_data_is_exactly_neutral(self):
        bare = [{"id": "x", "duration": 2}, {"id": "y", "duration": 2}]
        self.assertEqual(ga.build_affinity_model(bare).affinity("x", "y"), 500)

    def test_local_features_only_uses_local_components(self):
        model = ga.build_affinity_model(strip_tags(self.pool))
        components = model.components(self.ids[0], self.ids[1])
        for name in ("subjects", "keywords", "context", "mood"):
            self.assertIsNone(components[name])
        for name in ga.LOCAL_ONLY_COMPONENTS:
            self.assertIsNotNone(components[name])
        same, other = [], []
        for i, a in enumerate(self.ids):
            for b in self.ids[i + 1:]:
                (same if self.truth[a] & self.truth[b] else other).append(model.affinity(a, b))
        self.assertGreater(sum(same) / len(same), sum(other) / len(other) + 50)

    def test_features_only_clips_count_exactly_the_local_components_that_carry_default_weight(self):
        """DOC-8: of the components present for two features-only clips, those with a default weight are the
        LOCAL_ONLY_COMPONENTS; ``orientation`` is present too but weighs 0 by default (framing carries orientation)."""
        model = ga.build_affinity_model(strip_tags(self.pool))
        components = model.components(self.ids[0], self.ids[1])
        present = {name for name, value in components.items() if value is not None}
        self.assertEqual({n for n in present if ga.DEFAULT_WEIGHTS.get(n, 0) != 0}, set(ga.LOCAL_ONLY_COMPONENTS))
        self.assertIn("orientation", present)
        self.assertNotIn("orientation", ga.DEFAULT_WEIGHTS)
        self.assertEqual(present - set(ga.LOCAL_ONLY_COMPONENTS), {"orientation"})

    def test_the_float_operations_in_the_module_are_exactly_the_documented_ones(self):
        """DOC-10: + - * / sqrt, and the non-rounding abs/min/max, float %, floor division. Nothing else touches floats."""
        tree = ast.parse(Path(ga.__file__).read_text(encoding="utf-8"))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "math" for a in n.names}
        self.assertEqual(imported, {"isfinite", "sqrt"})
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(called & {"sum", "round", "pow", "exp", "log", "floor", "ceil", "fsum", "hypot", "atan2", "divmod"}, called)
        operators = {type(n.op).__name__ for n in ast.walk(tree) if isinstance(n, ast.BinOp)}
        self.assertLessEqual(operators, {"Add", "Sub", "Mult", "Div", "FloorDiv", "Mod", "Pow", "BitOr"})   # BitOr: ``X | None`` annotations
        for n in ast.walk(tree):                         # ** only between integer constants (COMPONENT_SCALE = 10 ** 12)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
                self.assertTrue(isinstance(n.left, ast.Constant) and isinstance(n.right, ast.Constant), ast.dump(n))
                self.assertTrue(isinstance(n.left.value, int) and isinstance(n.right.value, int))
        mods = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and not
                (isinstance(n.left, ast.Constant) and isinstance(n.left.value, str))]
        self.assertTrue(all(ast.unparse(n) == "hue % 1.0" for n in mods), [ast.unparse(n) for n in mods])
        text = (Path(__file__).resolve().parents[3] / "docs" / "architecture" / "GRAVITY.md").read_text(encoding="utf-8")
        self.assertNotIn("only `+ - * /` and `sqrt` touch floats", text)
        for name in ("`abs`", "`min`", "`max`", "`hue % 1.0`", "floor division by 1"):
            self.assertIn(name, text)

    def test_weights_are_validated_with_a_clear_error(self):
        """DP-4: NaN, inf, -inf, wrong types and out-of-range weights are refused, not 'cannot convert float NaN'."""
        pool = self.pool[:4]
        for bad in (float("nan"), float("inf"), float("-inf"), 2.0, -5.0, 1e30, "0.5", None, True, [0.5]):
            with self.subTest(weight=repr(bad)):
                with self.assertRaisesRegex(ValueError, r"weight 'tone' must be a finite number in -1\.0\.\.1\.0") as raised:
                    ga.build_affinity_model(pool, {"tone": bad})
                self.assertNotIn("cannot convert", str(raised.exception))
        with self.assertRaisesRegex(ValueError, "weights must be a mapping"):
            ga.build_affinity_model(pool, [("tone", 1.0)])
        with self.assertRaisesRegex(ValueError, "weight 'tone'"):
            ga.AffinityModel(profiles={}, subject_idf={}, keyword_idf={}, weights={"tone": float("nan")})
        for good in (-1.0, 0.0, 0.5, 1.0, 1, -1, 0):                               # the valid range is untouched
            ga.build_affinity_model(pool, {"tone": good})

    def test_mixed_tagged_and_untagged(self):
        tagged = next(r for r in self.pool if r["analysis"])
        untagged = next(r for r in self.pool if not r["analysis"])
        components = self.model.components(tagged["id"], untagged["id"])
        self.assertIsNone(components["subjects"])
        self.assertIsNotNone(components["color"])

    def test_missing_tags_inside_a_record_degrade_without_error(self):
        record = copy.deepcopy(self.pool[0])
        record["analysis"].pop("mood")
        record["analysis"]["subjects"] = []
        record["features"]["palette"] = [{"hex": "zz", "share": 1}]
        record["features"]["hue"] = float("nan")
        model = ga.build_affinity_model([record, self.pool[1]])
        self.assertTrue(0 <= model.affinity(record["id"], self.pool[1]["id"]) <= 1000)

    # DOC-3: GRAVITY.md says a component is missing when EITHER clip lacks its inputs and only components present for
    # both clips count. Each entry is the fields that carry one component: (section, field, usable value, malformed values).
    COMPONENT_FIELDS = {
        "subjects": (("analysis", "subjects", ["dog", "beach"], ["dog", 7, {"a": 1}, [None, 5, ""], [[]]]),),
        "keywords": (("analysis", "keywords", ["sand", "sea"], ["sand", 7, {"a": 1}, [None, 5, "  "], [[]]]),),
        "context": (("analysis", "setting", "indoor", [5, ["indoor"], "unclear", ""]),
                    ("analysis", "environment", "domestic", [5, ["x"], "unclear", ""]),
                    ("analysis", "time_of_day", "day", [5, ["x"], "unclear", ""])),
        "mood": (("analysis", "mood", ["calm"], ["calm", 7, ["nonsense"], [None]]),),
        "color": (("features", "hue", 0.3, ["red", None, float("nan"), -1]),
                  ("features", "saturation", 0.5, ["red", None, float("inf"), -1]),
                  ("features", "palette", [{"hex": "#ff0000", "share": 0.5}], ["red", 7, [{"hex": "zz", "share": 1}], [5]]),
                  ("analysis", "palette", ["red"], ["red", 7, ["not a colour"], [None]])),
        "tone": (("features", "luma", 0.5, ["x", None, float("nan"), -1]),
                 ("features", "saturation", 0.5, ["x", None, float("inf"), -1])),
        "motion": (("analysis", "motion_level", "moderate", [5, ["x"], "unclear", "frantic"]),
                   ("features", "motion", 0.05, ["x", None, float("nan"), -1])),
        "framing": (("features", "orientation", "portrait", [5, ["x"], "sideways"]),
                    ("analysis", "shot", "wide", [5, ["x"], "unclear", "huge"])),
        "environment": (("analysis", "environment", "urban", [5, ["x"], "unclear", ""]),),
        "shot": (("analysis", "shot", "wide", [5, ["x"], "unclear", "huge"]),),
        "orientation": (("features", "orientation", "portrait", [5, ["x"], "sideways"]),),
    }

    @staticmethod
    def two_tagged(edit_x, edit_y):
        """Two tagged clips that carry no component input at all unless an edit adds it."""
        def clip(name, edit):
            record = {"id": name, "duration": 2, "analysis": {"safety": {"verdict": "clear"}}, "features": {"fps": 24}}
            edit(record)
            return record
        return [clip("x", edit_x), clip("y", edit_y)]

    def test_every_component_follows_the_documented_missing_rule(self):
        self.assertEqual(set(self.COMPONENT_FIELDS), set(ga.ALL_COMPONENTS))
        nothing = lambda record: None
        for component, fields in self.COMPONENT_FIELDS.items():
            def present(record, fields=fields):
                for section, field, value, _ in fields:
                    record[section][field] = copy.deepcopy(value)

            def malformed(record, which, fields=fields):
                for section, field, _, bad in fields:
                    record[section][field] = copy.deepcopy(bad[which % len(bad)])
            cases = [("both present", present, present, True), ("one missing", present, nothing, False),
                     ("other one missing", nothing, present, False), ("both missing", nothing, nothing, False)]
            cases += [(f"malformed {i}", present, lambda r, i=i, m=malformed: m(r, i), False) for i in range(5)]
            cases += [(f"both malformed {i}", lambda r, i=i, m=malformed: m(r, i), lambda r, i=i, m=malformed: m(r, i), False)
                      for i in range(5)]
            for label, edit_x, edit_y, expected in cases:
                with self.subTest(component=component, case=label):
                    model = ga.build_affinity_model(self.two_tagged(edit_x, edit_y))
                    value = model.components("x", "y")[component]
                    self.assertEqual(value is not None, expected, value)
                    self.assertEqual(model.affinity("x", "y"), model.affinity_milli_uncached("x", "y"))   # fast path agrees

    def test_a_missing_field_never_lowers_affinity_like_a_mismatch(self):
        """The exact case of the finding: one tagged clip lacks subjects and keywords; they must not count as 0.0."""
        full = {"id": "x", "duration": 2, "analysis": {"subjects": ["dog", "beach"], "keywords": ["sand"],
                                                          "setting": "outdoor"}}
        bare = {"id": "y", "duration": 2, "analysis": {"setting": "outdoor"}}
        model = ga.build_affinity_model([full, bare])
        present = {k: v for k, v in model.components("x", "y").items() if v is not None}
        self.assertEqual(present, {"context": 1.0})
        neither = ga.build_affinity_model([{**full, "analysis": {"setting": "outdoor"}}, bare])
        self.assertEqual(model.affinity("x", "y"), neither.affinity("x", "y"))
        for malformed in ("dog", 7):
            odd = ga.build_affinity_model([full, {**bare, "analysis": {"setting": "outdoor", "subjects": malformed,
                                                                         "keywords": malformed}}])
            self.assertEqual(odd.affinity("x", "y"), model.affinity("x", "y"))

    def test_idf_downweights_common_terms(self):
        idf = self.model.subject_idf
        self.assertLess(idf["sky"], idf["insect"])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            ga.build_affinity_model([self.pool[0], self.pool[0]])

    def test_convenience_form_matches_model(self):
        a, b = self.pool[0], self.pool[1]
        self.assertAlmostEqual(ga.affinity(a, b, self.pool), self.model.affinity(a["id"], b["id"]) / 1000)

    def test_half_up_helpers(self):
        self.assertEqual([ga.quantize(v) for v in (0.0004, 0.0005, 0.0015, 1.0, 1.2, -0.2)], [0, 1, 2, 1000, 1000, 0])
        self.assertEqual([ga.round_half_up_div(n, 2) for n in (-3, -1, 1, 3)], [-1, 0, 1, 2])

    def test_reproducible_across_processes_and_hash_seeds(self):
        model = ga.build_affinity_model(make_pool(40))
        ids = sorted(r["id"] for r in make_pool(40))
        local = hashlib.sha256(json.dumps([[model.affinity(a, b) for b in ids] for a in ids]).encode()).hexdigest()
        for hash_seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=SRC)
            done = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, env=env, check=True)
            self.assertEqual(done.stdout.strip(), local, hash_seed)


class UnicodeStringSemanticsTests(unittest.TestCase):
    """DPP-1: the Python string behaviours GRAVITY.md lists in the port contract, pinned so the page cannot go stale."""

    @staticmethod
    def affinity(keywords_a, keywords_b):
        records = [{"id": "a", "analysis": {"keywords": keywords_a}}, {"id": "b", "analysis": {"keywords": keywords_b}}]
        return ga.build_affinity_model(records).affinity("a", "b")

    def test_strip_removes_exactly_the_isspace_characters_and_keeps_the_byte_order_mark(self):
        stripped = ["\t", "\n", "\x0b", "\x0c", "\r", "\x1c", "\x1d", "\x1e", "\x1f", " ", "\x85", "\xa0", "\u1680",
                    *(chr(c) for c in range(0x2000, 0x200B)), "\u2028", "\u2029", "\u202f", "\u205f", "\u3000"]
        for char in stripped:
            with self.subTest(char=hex(ord(char))):
                self.assertTrue(char.isspace())
                self.assertEqual(self.affinity([char + "bar"], ["bar"]), self.affinity(["bar"], ["bar"]))
        self.assertFalse("\ufeff".isspace())
        self.assertNotEqual(self.affinity(["\ufeffbar"], ["bar"]), self.affinity(["bar"], ["bar"]))

    def test_keywords_are_lower_cased_but_subjects_are_used_verbatim(self):
        self.assertEqual(self.affinity(["Bar"], ["bAR"]), self.affinity(["bar"], ["bar"]))
        subjects = lambda x, y: ga.build_affinity_model(
            [{"id": "a", "analysis": {"subjects": [x]}}, {"id": "b", "analysis": {"subjects": [y]}}]).affinity("a", "b")
        self.assertNotEqual(subjects("Bar", "bar"), subjects("bar", "bar"))
        self.assertNotEqual(subjects(" bar", "bar"), subjects("bar", "bar"))

    def test_nothing_is_unicode_normalised(self):
        composed, decomposed = "\u00e9", "e\u0301"
        self.assertNotEqual(composed, decomposed)
        self.assertNotEqual(self.affinity([composed], [decomposed]), self.affinity([composed], [composed]))

    def test_lower_and_casefold_differ_and_follow_unicode_tables(self):
        self.assertEqual(("\u00df".lower(), "\u00df".casefold()), ("\u00df", "ss"))
        self.assertEqual("\u0130".lower(), "i\u0307")

    def test_strings_sort_by_code_point_not_by_utf16_unit(self):
        astral, bmp_high = "\U0001f600", "\uff21"
        self.assertEqual(sorted([astral, bmp_high]), [bmp_high, astral])                      # code points: U+FF21 < U+1F600
        self.assertEqual(sorted([astral, bmp_high], key=lambda t: t.encode("utf-16-be")), [astral, bmp_high])
        self.assertEqual(tuple(sorted({astral, bmp_high})), (bmp_high, astral))
        profile = ga.clip_profile({"id": "x", "analysis": {"keywords": [astral, bmp_high]}})
        self.assertEqual(profile.keywords, (bmp_high.lower(), astral))

    def test_length_counts_code_points_not_utf16_units(self):
        text = "\U0001f600" * 3
        self.assertEqual((len(text), len(text.encode("utf-16-le")) // 2), (3, 6))


class SignedIntegerCombineTests(unittest.TestCase):
    """L4 and signed weights: the combination is integer arithmetic, so order cannot matter."""

    def test_exact_values(self):
        full = ga.COMPONENT_SCALE
        self.assertEqual(ga.combine_milli({}, {}), 500)
        self.assertEqual(ga.combine_milli({"color": None}, {"color": 1000}), 500)
        # (0.05*0.5 + 0.22*1) / (0.05 + 0.22) = 0.9074...; contrast of the same similarity: 0.0926...
        self.assertEqual(ga.combine_milli({"color": full}, {"color": 220}), 907)
        self.assertEqual(ga.combine_milli({"color": full}, {"color": -220}), 93)
        self.assertEqual(ga.combine_milli({"color": 0}, {"color": -220}), 907)
        self.assertEqual(ga.combine_milli({"color": full // 2}, {"color": 220}), 500)

    def test_result_is_independent_of_component_summation_order(self):
        rng = random.Random(7)
        names = list(ga.ALL_COMPONENTS)
        for _ in range(300):
            comps = {n: (None if rng.random() < 0.2 else rng.randrange(0, ga.COMPONENT_SCALE + 1)) for n in names}
            weights = {n: rng.randrange(-1000, 1001) for n in names}
            expected = ga.combine_milli(comps, weights)
            # reference: exact rational arithmetic, half-up
            num, den = Fraction(50 * 500, 1), Fraction(50)
            for n in names:
                if comps[n] is not None and weights[n]:
                    num += abs(weights[n]) * (Fraction(comps[n], ga.COMPONENT_SCALE) * 1000
                                              if weights[n] > 0 else 1000 - Fraction(comps[n], ga.COMPONENT_SCALE) * 1000)
                    den += abs(weights[n])
            self.assertEqual(expected, (2 * num + den) // (2 * den))      # exact half-up of the rational result
            for _ in range(5):
                order = names[:]
                rng.shuffle(order)
                self.assertEqual(ga.combine_milli({n: comps[n] for n in order}, {n: weights[n] for n in order}), expected)

    def test_affinity_module_never_uses_the_builtin_sum(self):
        # CPython 3.12+ compensates float sums inside sum(); a port could not match it bit for bit.
        tree = ast.parse(Path(ga.__file__).read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "sum"]
        self.assertEqual(calls, [])

    def test_negative_weight_rewards_contrast_and_mirrors_the_positive_one(self):
        pool = make_pool(60)
        plus = ga.build_affinity_model(pool, {"color": 1.0})
        minus = ga.build_affinity_model(pool, {"color": -1.0})
        ids = sorted(r["id"] for r in pool)
        for a, b in zip(ids, ids[1:]):
            self.assertIn(plus.affinity(a, b) + minus.affinity(a, b), (999, 1000, 1001))
        same, other = ids[0], ids[1]
        self.assertGreater(plus.affinity(same, same), 900)
        self.assertLess(minus.affinity(same, same), 100)

    def test_single_attribute_components_match_and_contrast(self):
        mk = lambda i, env, shot, orient: {"id": f"c{i}", "analysis": {"environment": env, "shot": shot, "subjects": ["x"]},  # noqa: E731
                                           "features": {"orientation": orient}}
        pool = [mk(1, "urban", "wide", "portrait"), mk(2, "urban", "close_up", "landscape"),
                mk(3, "nature", "wide", "portrait")]
        for name, same, different in (("environment", ("c1", "c2"), ("c1", "c3")), ("shot", ("c1", "c3"), ("c1", "c2")),
                                      ("orientation", ("c1", "c3"), ("c1", "c2"))):
            like = ga.build_affinity_model(pool, {name: 1.0})
            unlike = ga.build_affinity_model(pool, {name: -1.0})
            self.assertGreater(like.affinity(*same), like.affinity(*different), name)
            self.assertLess(unlike.affinity(*same), unlike.affinity(*different), name)

    def test_zero_weight_components_are_not_computed_and_unknown_names_are_rejected(self):
        pool = make_pool(20)
        only_color = ga.build_affinity_model(pool, {"color": 0.5})
        self.assertEqual(only_color._active, ["color"])

        def boom(*args, **kwargs):
            raise AssertionError("a zero-weight component was computed")
        table = {name: boom for name in ga._SIMILARITY if name != "color"}
        with mock.patch.object(ga, "sim_subjects", boom), mock.patch.object(ga, "sim_keywords", boom), \
                mock.patch.dict(ga._SIMILARITY, table):
            value = only_color.affinity(pool[0]["id"], pool[1]["id"])
        self.assertEqual(value, only_color.affinity(pool[0]["id"], pool[1]["id"]))
        with self.assertRaises(ValueError):
            ga.build_affinity_model(pool, {"nope": 1.0})

    def test_the_inlined_palette_distance_equals_the_redmean_reference_bit_for_bit(self):
        rng = random.Random(3)
        for _ in range(300):
            pa = [((rng.randrange(256), rng.randrange(256), rng.randrange(256)), rng.random() + 0.01) for _ in range(rng.randint(1, 5))]
            pb = [((rng.randrange(256), rng.randrange(256), rng.randrange(256)), rng.random() + 0.01) for _ in range(rng.randint(1, 5))]

            def directed(x, y):
                total = 0.0
                for _, s in x:
                    total += s
                acc = 0.0
                for rgb, share in x:
                    acc += share * min(ga._redmean(rgb, other) for other, _ in y)
                return acc / total
            reference = max(0.0, 1.0 - ((directed(pa, pb) + directed(pb, pa)) / 2.0) / ga._PALETTE_RANGE)
            self.assertEqual(ga._palette_similarity(pa, pb), reference)

    def test_the_sorted_merge_overlap_equals_the_dictionary_definition(self):
        rng = random.Random(4)
        vocab = [f"t{i:02d}" for i in range(12)]
        idf = {t: 1.0 + rng.random() for t in vocab[:9]}
        for _ in range(300):
            a = {t: rng.random() + 0.1 for t in rng.sample(vocab, rng.randint(0, 8))}
            b = {t: rng.random() + 0.1 for t in rng.sample(vocab, rng.randint(0, 8))}
            num = den = 0.0
            for term in sorted(set(a) | set(b)):
                wa, wb, w = a.get(term, 0.0), b.get(term, 0.0), idf.get(term, 1.0)
                num += min(wa, wb) * w
                den += max(wa, wb) * w
            expected = num / den if den > 0 else 0.0
            self.assertEqual(ga._ruzicka_sorted(tuple(sorted(a.items())), tuple(sorted(b.items())), idf), expected)

    def test_the_affinity_cache_is_bounded_and_does_not_change_results(self):
        pool = make_pool(40)
        small = ga.build_affinity_model(pool)
        small.cache_size = 25
        big = ga.build_affinity_model(pool)
        ids = sorted(r["id"] for r in pool)
        for a in ids:
            for b in ids:
                self.assertEqual(small.affinity(a, b), big.affinity(a, b))
                self.assertLessEqual(len(small._cache), 25)
        self.assertGreater(len(big._cache), 25)


class FastPathEquivalenceTests(unittest.TestCase):
    """The per-pool prepared path must return exactly what the plain per-pair functions return."""

    WEIGHT_SETS = {
        "defaults": None,
        "signed everything": {name: (0.9 if i % 2 else -0.7) * (1.0 - 0.05 * i) for i, name in enumerate(ga.ALL_COMPONENTS)},
        "contrast on environment, match on colour": {"color": 0.5, "tone": 0.3, "environment": -1.0},
        "shot only": {"shot": -1.0},
        "orientation and framing": {"orientation": 0.8, "framing": -0.4},
    }

    @staticmethod
    def corrupted(pool, seed=11):
        """Records with random keys dropped or replaced by wrong types: the paths must still agree."""
        rng = random.Random(seed)
        out = copy.deepcopy(pool)
        for record in out:
            for section in ("analysis", "features"):
                body = record.get(section)
                if not isinstance(body, dict):
                    continue
                for key in sorted(body):
                    roll = rng.random()
                    if roll < 0.08:
                        del body[key]
                    elif roll < 0.12:
                        body[key] = rng.choice(["x", 7, None, [], {}, [["bad"]], float("nan")])
        return out

    def assert_every_pair_agrees(self, pool, weights, label):
        model = ga.build_affinity_model(pool, weights)
        ids = sorted(r["id"] for r in pool)
        for i, a in enumerate(ids):
            for b in ids[i:]:
                reference = model.affinity_milli_uncached(a, b)
                self.assertEqual(model.affinity_milli_fast(a, b), reference, (label, a, b))
                self.assertEqual(model.affinity(a, b), reference, (label, a, b))
                self.assertEqual(model.affinity(b, a), reference, (label, a, b))

    def test_fast_cached_and_uncached_agree_on_every_pair_of_a_fixed_pool(self):
        pool = make_pool(60)
        for label, weights in self.WEIGHT_SETS.items():
            self.assert_every_pair_agrees(pool, weights, label)

    def test_they_agree_for_untagged_and_malformed_records(self):
        pool = make_pool(45)
        for label, variant in (("untagged", strip_tags(pool)), ("malformed", self.corrupted(pool))):
            for weights in (None, self.WEIGHT_SETS["signed everything"]):
                self.assert_every_pair_agrees(variant, weights, label)

    BAD_HEX = ("#-f0060", "#+f0060", "# f0060", "#-1-1-1", "#+f+f+f", "# 1 2 3", "#１２３４５６", "#٠٠١١٢٢",
               "##ff00ff", " #ff00ff", "#ff00ff ", "ff00ff\n", "#ff_00ff", "#0xff00", "#ff00f", "#ff00ff0", "", "#")
    GOOD_HEX = ("#ff00ff", "ff00ff", "#FF00ff", "#000000", "#AbCdEf")

    @classmethod
    def with_palette(cls, ident, entries):
        record = copy.deepcopy(next(r for r in make_pool(20) if r["analysis"]))
        record["id"] = ident
        record["analysis"]["palette"] = []                     # colour names, hue and saturation would otherwise
        record["features"].pop("hue", None)                    # supply the colour component on their own
        record["features"].pop("saturation", None)
        record["features"]["palette"] = entries
        return record

    def test_hex_colours_are_exactly_six_ascii_hex_digits_after_an_optional_hash(self):
        for bad in self.BAD_HEX:
            self.assertIsNone(ga._hex_rgb(bad), repr(bad))
        for good in self.GOOD_HEX:
            self.assertIsNotNone(ga._hex_rgb(good), repr(good))
        self.assertEqual(ga._hex_rgb("#aBc012"), (0xAB, 0xC0, 0x12))

    def test_a_malformed_hex_drops_the_palette_entry_and_both_paths_agree(self):
        good = {"hex": "#204060", "share": 0.5}
        records = [self.with_palette("ref", [good, {"hex": "#a0b0c0", "share": 0.5}])]
        for i, bad in enumerate(self.BAD_HEX):
            records.append(self.with_palette(f"bad-{i}", [{"hex": bad, "share": 0.5}, dict(good)]))
        for record in records[1:]:
            self.assertEqual(len(ga.clip_profile(record).palette), 1, record["id"])
        for weights in (None, {"color": 1.0}, self.WEIGHT_SETS["signed everything"]):
            self.assert_every_pair_agrees(records, weights, "malformed hex")

    def test_the_negative_index_case_no_longer_reads_the_wrong_table_entry(self):
        a = self.with_palette("a", [{"hex": "#-f0060", "share": 1.0}])
        b = self.with_palette("b", [{"hex": "#000000", "share": 1.0}])
        model = ga.build_affinity_model([a, b], {"color": 1.0})
        self.assertEqual(ga.clip_profile(a).palette, ())
        self.assertEqual(model.affinity_milli_fast("a", "b"), model.affinity_milli_uncached("a", "b"))
        self.assertEqual(model.affinity_milli_fast("a", "b"), 500)                    # the component is simply unavailable

    def test_a_palette_share_above_one_or_not_finite_is_malformed_and_dropped(self):
        for share in (1e308, 1.0000001, 2, float("inf"), float("nan"), -0.5, True, "0.5", None):
            entry = {"hex": "#102030", "share": share}
            record = self.with_palette("a", [entry, {"hex": "#203040", "share": 0.5}])
            self.assertEqual(len(ga.clip_profile(record).palette), 1, repr(share))
        self.assertEqual(len(ga.clip_profile(self.with_palette("a", [{"hex": "#102030", "share": 1}])).palette), 1)
        self.assertEqual(len(ga.clip_profile(self.with_palette("a", [{"hex": "#102030", "share": 0.0001}])).palette), 1)

    def test_overflowing_shares_give_the_same_result_as_an_absent_palette_on_both_paths(self):
        for share in (1e308, 1e300):
            a = self.with_palette("a", [{"hex": "#102030", "share": share}, {"hex": "#203040", "share": share}])
            b = self.with_palette("b", [{"hex": "#304050", "share": share}, {"hex": "#405060", "share": share}])
            model = ga.build_affinity_model([a, b], {"color": 1.0})
            self.assertEqual(model.affinity_milli_fast("a", "b"), model.affinity_milli_uncached("a", "b"))
            self.assertEqual(model.affinity_milli_uncached("a", "b"), 500)
            self.assertEqual(ga.clip_profile(a).palette, ())

    def test_random_hex_and_share_corpus_agrees_between_the_paths(self):
        rng = random.Random(23)
        digits = "0123456789abcdefABCDEF"
        junk = list(self.BAD_HEX) + ["#12345g", "#ffff", "#fffffff", "#" + "９" * 6]
        shares = [0.0, 0.2, 0.5, 1.0, 1.5, 1e308, -1, float("nan")]
        records = []
        for i in range(40):
            entries = []
            for _ in range(rng.randint(1, 5)):
                hexa = rng.choice(junk) if rng.random() < 0.35 else "#" + "".join(rng.choice(digits) for _ in range(6))
                entries.append({"hex": hexa, "share": rng.choice(shares) if rng.random() < 0.3 else rng.random() + 0.01})
            records.append(self.with_palette(f"r{i}", entries))
        for weights in (None, {"color": 1.0}):
            self.assert_every_pair_agrees(records, weights, "hex corpus")

    def test_a_tiny_memo_that_keeps_clearing_changes_nothing(self):
        pool = make_pool(40)
        tiny = ga.build_affinity_model(pool, self.WEIGHT_SETS["signed everything"])
        tiny.memo_limit = 1
        plain = ga.build_affinity_model(pool, self.WEIGHT_SETS["signed everything"])
        ids = sorted(r["id"] for r in pool)
        for a in ids:
            for b in ids:
                self.assertEqual(tiny.affinity_milli_fast(a, b), plain.affinity_milli_uncached(a, b))

    def test_the_prepared_palette_and_overlap_equal_their_references_bit_for_bit(self):
        rng = random.Random(5)

        def flat(palette):
            return tuple((r, g, b, share) for (r, g, b), share in palette)

        def share_total(palette):
            total = 0.0
            for _, share in palette:       # left to right, never the builtin sum
                total += share
            return total
        for _ in range(400):
            pa = tuple((tuple(rng.randrange(256) for _ in range(3)), rng.random() + 0.01) for _ in range(rng.randint(1, 5)))
            pb = tuple((tuple(rng.randrange(256) for _ in range(3)), rng.random() + 0.01) for _ in range(rng.randint(1, 5)))
            self.assertEqual(ga._palette_weighted(flat(pa), share_total(pa), flat(pb), share_total(pb)),
                             ga._palette_similarity(pa, pb))
        vocab = [f"t{i:02d}" for i in range(12)]
        idf = {t: 1.0 + rng.random() * 3 for t in vocab[:9]}

        def weigh(items):
            return tuple((t, w * idf.get(t, 1.0)) for t, w in items)
        for _ in range(400):
            a = tuple(sorted((t, rng.random() + 0.1) for t in rng.sample(vocab, rng.randint(0, 8))))
            b = tuple(sorted((t, rng.random() + 0.1) for t in rng.sample(vocab, rng.randint(0, 8))))
            self.assertEqual(ga._ruzicka_weighted(weigh(a), weigh(b)), ga._ruzicka_sorted(a, b, idf))

    def test_scheduling_is_identical_through_either_path(self):
        from simvltanea.authoring.test_play_support import cfg, digest, play
        config = cfg("magnetic")
        fast = digest(play(config, n=4, seconds=45, seed=3)["state"])
        original = ga.AffinityModel.affinity_milli_fast
        try:
            ga.AffinityModel.affinity_milli_fast = ga.AffinityModel.affinity_milli_uncached
            reference = digest(play(config, n=4, seconds=45, seed=3)["state"])
        finally:
            ga.AffinityModel.affinity_milli_fast = original
        self.assertEqual(fast, reference)


if __name__ == "__main__":
    unittest.main()
