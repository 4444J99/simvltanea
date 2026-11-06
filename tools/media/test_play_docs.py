"""PLAY_MODES.md: the generated tables equal the code, and what the page cites exists and holds."""
import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from simvltanea.authoring import PRESETS, PlayError, describe_parameters
from simvltanea.authoring.gravity_affinity import ALL_COMPONENTS
from simvltanea.authoring.test_play_support import cfg, digest, play
from tools.media import play_docs
from tools.paths import REPO_ROOT

AUTHORING = REPO_ROOT / "src" / "simvltanea" / "authoring"


class GeneratedTablesTests(unittest.TestCase):
    def setUp(self):
        self.text = play_docs.DOC.read_text(encoding="utf-8")

    def test_the_document_matches_what_the_code_generates(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(play_docs.main([]), 0, out.getvalue())
        self.assertTrue(play_docs.render(self.text) == self.text, "generated blocks differ from the code")

    def test_a_drifted_table_is_detected_and_repaired_by_render(self):
        drifted = self.text.replace("| `relation.strength` | number -4 to 4 |", "| `relation.strength` | number -9 to 9 |")
        self.assertNotEqual(drifted, self.text)
        self.assertTrue(play_docs.render(drifted) == self.text, "render did not repair the drifted table")

    def test_every_parameter_and_every_preset_is_documented(self):
        for entry in describe_parameters():
            self.assertIn(f"`{entry['path']}`", self.text, entry["path"])
        for name in PRESETS:
            self.assertRegex(self.text, rf"\| `{name}` \|", name)

    def test_the_synchronized_note_and_the_ignored_settings_are_on_the_page(self):
        self.assertIn(play_docs.SYNCHRONIZED_NOTE, self.text)
        for key, where, names, why in play_docs.INERT_ROWS:
            self.assertIn(where, self.text, key)

    def test_the_page_says_the_output_is_a_private_artifact_and_matches_the_command(self):
        from tools.media import play_state
        flat = " ".join(self.text.split())
        self.assertIn("private artifact: never commit them, never share them", flat)
        self.assertIn("Photos", flat)
        self.assertIn("private artifact, never commit it and never share it", play_state.PRIVACY_NOTICE)

    def test_the_renderable_rule_and_the_loud_warning_are_documented_as_the_code_does_them(self):
        from tools.media import play_state
        flat = " ".join(self.text.split())
        for needle in ("is always judged against `composition.MAX_SEGMENTS`", "can only be LOWER", "NOT RENDERABLE OFFLINE",
                       "`limits.refuse_unrenderable` is false", "`over_configured_limit`"):
            self.assertIn(needle, flat)
        entry = next(p for p in describe_parameters() if p["path"] == "limits.max_render_segments")
        self.assertEqual((entry["default"], entry["max"]), (play_docs.LIMIT, play_docs.LIMIT))
        self.assertIn("NOT RENDERABLE OFFLINE", Path(play_state.__file__).read_text(encoding="utf-8"))

    def test_the_seed_text_rule_on_the_page_is_what_the_code_does(self):
        from simvltanea.authoring.play_config import seed_from_text
        flat = " ".join(self.text.split())
        self.assertIn("Seed text follows one rule on every path", flat)
        self.assertIn("`7` and `-7` are integers while `007`, `-0`, `+7` and `1.5` are strings", flat)
        for text in ("7", "-7"):
            self.assertEqual(seed_from_text(text), int(text))
        for text in ("007", "-0", "+7", "1.5"):
            self.assertEqual(seed_from_text(text), text)

    def test_the_record_round_trip_is_documented_with_its_test(self):
        flat = " ".join(self.text.split())
        for needle in ("### Replaying a record", "play-config/v1", "byte for byte from the same private root",
                       "the eligible pool differs from the one in the record"):
            self.assertIn(needle, flat)
        from tools.media import play_state
        self.assertEqual(play_state.RECORD_SCHEMA, "play-config/v1")

    def test_the_record_is_described_with_the_ids_it_really_holds(self):
        self.assertNotIn("holds no ids", self.text)
        self.assertIn("exclusion.exclude_ids", self.text.split("`<name>.play.json`", 1)[1].split("\n", 1)[0])

    def test_markers_appear_exactly_once_per_block(self):
        for name in play_docs.BLOCKS:
            self.assertEqual(self.text.count(f"<!-- BEGIN GENERATED: {name} -->"), 1, name)
            self.assertEqual(self.text.count(f"<!-- END GENERATED: {name} -->"), 1, name)

    def test_cited_tests_exist(self):
        cited = set(re.findall(r"`(test_[a-z0-9_]+)`", self.text))
        self.assertGreaterEqual(len(cited), 8)
        sources = "\n".join(p.read_text(encoding="utf-8")
                            for p in [*AUTHORING.glob("test_*.py"), *(REPO_ROOT / "tools" / "media").glob("test_*.py")])
        for name in sorted(cited):
            self.assertRegex(sources, rf"def {name}\(", name)

    PLAN = REPO_ROOT / "docs" / "plans" / "2026-11-05-gravity-selection.md"

    def pages(self):
        return {"PLAY_MODES": self.text, "GRAVITY": play_docs.GRAVITY_DOC.read_text(encoding="utf-8"),
                "plan": self.PLAN.read_text(encoding="utf-8")}

    def test_every_test_class_and_file_cited_on_any_page_exists_and_every_preset_named_is_real(self):
        """DOC-F5: the check covers GRAVITY.md and the plan, and test classes and files as well as test functions."""
        for name, text in self.pages().items():
            with self.subTest(page=name):
                self.assertGreaterEqual(len(play_docs.CITED_TEST.findall(text)), 2)
                self.assertEqual(play_docs.citation_problems(text), [])
                self.assertEqual(play_docs.preset_name_problems(text), [])

    def test_a_citation_of_a_test_that_does_not_exist_is_caught_on_every_page(self):
        for name, text in self.pages().items():
            first = play_docs.CITED_TEST.findall(text)[0]
            for old, new in ((first, "test_this_test_does_not_exist"), (first, "NoSuchTests"), (first, "test_no_such_file.py")):
                with self.subTest(page=name, cited=first, replaced_by=new):
                    mutated = text.replace(f"`{old}`", f"`{new}`")
                    self.assertEqual(play_docs.citation_problems(mutated), [f"cited test does not exist: {new}"])

    def test_a_wrong_preset_name_is_caught_on_every_page(self):
        for name, text in self.pages().items():
            with self.subTest(page=name):
                self.assertEqual(play_docs.preset_name_problems(text + "\n\nThe `no_such_mode` preset and mode `also_missing`.\n"),
                                 ["not a preset: also_missing", "not a preset: no_such_mode"])

    def test_the_hand_written_measured_figures_carry_a_label(self):
        """DOC-F4: a figure no guard regenerates says so, with the date it was measured."""
        label = re.compile(r"not regenerated by the drift guards")
        self.assertGreaterEqual(len(label.findall(self.text)), 5)
        for section in ("Cost and limits", "The renderer limit (L8)", "Pending owner decisions"):
            body = self.text.split(f"## {section}" if section != "The renderer limit (L8)" else f"### {section}", 1)[1]
            self.assertTrue(label.search(body), section)
        self.assertIn("measured on 2026-11-05", " ".join(self.text.split()))

    # What else, besides the preset's own name, counts as the same behaviour in a cited test's body.
    RELATED = {"oldest_meets_newest": ("converge", "diverge"), "newest_meets_oldest": ("converge", "diverge"),
               "round_clips": ("round",), "round_tags": ("round",),
               "calm_to_intense": ("calm_to_intense",), "dark_to_light": ("dark_to_light",), "rainbow": ("rainbow",)}

    def test_every_test_cited_for_an_owner_example_runs_that_examples_preset(self):
        """A real but unrelated test must not pass as evidence (DOC-6): the cited body names a preset of its row."""
        section = self.text.split("### The owner's examples", 1)[1].split("\n\n", 2)[1]
        sources = [p.read_text(encoding="utf-8") for p in AUTHORING.glob("test_*.py")]

        def body(name):
            for text in sources:
                found = re.search(rf"    def {name}\(.*?(?=\n    def |\nclass |\Z)", text, re.S)
                if found:
                    return found.group(0)
            raise AssertionError(name)

        checked = 0
        for row in section.splitlines()[2:]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            presets = set(re.findall(r"`([a-z_]+)`", cells[1])) - set(re.findall(r"`(test_[a-z0-9_]+)`", cells[1]))
            words = presets | {w for p in presets for w in self.RELATED.get(p, ())}
            for test in re.findall(r"`(test_[a-z0-9_]+)`", cells[2]):
                text = body(test) + " " + test
                self.assertTrue(any(re.search(rf"[\"'_ ]{w}[\"'_ ]", text) for w in words),
                                f"{test} never names {sorted(words)}")
                checked += 1
        self.assertGreaterEqual(checked, 8)

    def test_the_previews_and_the_render_command_the_page_documents_exist(self):
        """RP-1, RP-2 and DOC-F3: the page names the two working command-line previews and a render command with an
        explicit in-repository output; no page says there is no preview."""
        import importlib.util
        plan = (REPO_ROOT / "docs" / "plans" / "2026-11-05-gravity-selection.md").read_text(encoding="utf-8")
        for name, text in (("PLAY_MODES", self.text), ("plan", plan)):
            self.assertNotRegex(" ".join(text.split()), r"There is no command-line preview", name)
        flat = " ".join(self.text.replace("\\\n", " ").split())
        for command in ("python -m independent_loop_compositor preview --state <state> --output var/work/<name>",
                        "python -m simvltanea.browser.browser_runtime --state <state> --output var/work/<name>",
                        "python -m independent_loop_compositor render --state <root>/play-state.json "
                        "--orientation portrait --output var/work/play-portrait.mp4"):
            self.assertIn(command, flat)
        for module in ("independent_loop_compositor", "simvltanea.browser.browser_runtime"):
            self.assertIsNotNone(importlib.util.find_spec(module), module)

    def test_owner_examples_name_real_presets(self):
        section = self.text.split("### The owner's examples", 1)[1].split("\n\n", 2)[1]
        names = set(re.findall(r"`([a-z_]+)`", section)) - {n for n in re.findall(r"`(test_[a-z0-9_]+)`", section)}
        self.assertTrue(names)
        self.assertLessEqual(names, set(PRESETS))


class GravityDocTests(unittest.TestCase):
    """GRAVITY.md: every table that restates a code constant is generated, and the prose numbers are parsed and compared."""

    def setUp(self):
        self.text = play_docs.GRAVITY_DOC.read_text(encoding="utf-8")

    def test_the_gravity_page_matches_what_the_code_generates(self):
        self.assertTrue(play_docs.render_gravity(self.text) == self.text, "GRAVITY.md generated blocks differ from the code")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(play_docs.main([]), 0, out.getvalue())

    def test_the_sticky_guarantee_says_what_is_true_now_on_both_pages(self):
        """DOC-F1 and DOC-F2: sticky is deterministic and equals score-everything only inside the condition; it no longer
        reproduces the pre-play-mode output, and 5,000 restores score-everything only for a pool of at most 5,000."""
        modes = play_docs.DOC.read_text(encoding="utf-8")
        for name, text in (("GRAVITY", self.text), ("PLAY_MODES", modes)):
            flat = " ".join(text.split())
            self.assertNotRegex(flat, r"reproduces? the earlier (gravity )?output byte for byte", name)
            self.assertIn("limits.max_candidates", flat, name)
            self.assertIn("re-pinned", flat, name)
            self.assertIn("relation.independence", flat, name)
            self.assertRegex(flat, r"(does \*\*not\*\* reproduce|is \*\*no longer reproduced\*\*)", name)
            self.assertRegex(flat, r"only while the eligible pool has at most 5,000 clips", name)
            self.assertIn("test_sticky_and_schedule_gravity_match_the_pinned_digests", flat, name)
            self.assertIn("test_the_score_everything_equality_holds_while_every_free_pool_fits_in_max_candidates", flat, name)
        limit = next(p for p in describe_parameters() if p["path"] == "limits.max_candidates")
        self.assertEqual(limit["max"], 5000)                        # the 5,000 the pages quote is the parameter's maximum

    def test_the_port_contract_lists_pythons_string_semantics_and_names_the_test_that_pins_them(self):
        """DPP-1: stripping, case, normalisation, sort order, length and encoding are part of the JavaScript port contract."""
        import ast
        flat = " ".join(self.text.split())
        for needle in ("**Stripping.**", "**Case.**", "**Normalisation.**", "**Sort order.**", "**Length.**",
                       "**Encoding.**", "not** U+FEFF", "`String.prototype.trim()`", "code point", "UTF-16"):
            self.assertIn(needle, flat)
        tree = ast.parse((REPO_ROOT / "src/simvltanea/authoring/test_gravity_affinity.py").read_text(encoding="utf-8"))
        self.assertIn("UnicodeStringSemanticsTests", {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)})
        self.assertIn("`UnicodeStringSemanticsTests` in `test_gravity_affinity.py`", flat)

    def test_the_two_affinity_entry_points_are_described_with_their_real_return_types(self):
        """DOC-7: AffinityModel.affinity returns an int 0..1000, the module-level helper a float 0..1 and is not exported."""
        import simvltanea.authoring as authoring
        from simvltanea.authoring import gravity_affinity as ga
        a, b = {"id": "a"}, {"id": "b"}
        value = ga.affinity(a, b)
        self.assertIsInstance(value, float)
        self.assertTrue(0.0 <= value <= 1.0)
        milli = ga.build_affinity_model([a, b]).affinity("a", "b")
        self.assertIs(type(milli), int)
        self.assertEqual(value, milli / 1000)
        self.assertFalse(hasattr(authoring, "affinity"))
        flat = " ".join(self.text.split())
        self.assertIn("`AffinityModel.affinity(a_id, b_id)`", flat)
        self.assertIn("returns an **integer** from 0 to 1000", flat)
        self.assertIn("returns a **float** from 0 to 1", flat)
        self.assertIn("the helper is not", flat)

    def test_the_sign_rule_and_the_opposites_limit_are_documented_on_both_pages(self):
        """F6 and F7: two negatives cancel to attraction; `opposites` biases, it does not pick the least related clip."""
        modes = " ".join(play_docs.DOC.read_text(encoding="utf-8").split())
        gravity = " ".join(self.text.split())
        for text in (modes, gravity):
            self.assertIn("Two negatives", text.replace("two negatives", "Two negatives"))
            self.assertIn("environment", text)
            self.assertIn("does not pick the least related one", text)
        self.assertIn("cancel to attraction", gravity)
        self.assertIn("measured-opposites", self.text)

    def test_inert_table_lists_the_settings_the_review_named(self):
        """F8: independence and adjacency under follow, stagger when synchronized, the round-only and order-only settings."""
        rows = {key: names for key, _, names, _ in play_docs.INERT_ROWS}
        self.assertLessEqual({"relation.independence", "relation.adjacency"}, set(rows["follow"]))
        self.assertIn("timing.stagger", rows["stagger"])
        self.assertLessEqual({"path.voice", "path.delay_beats"}, set(rows["not_a_round"]))
        self.assertIn("path.direction", rows["meeting_shapes"])
        self.assertIn("path.wrap", rows["wrap_unused"])
        self.assertLessEqual({"order.axis", "path.window"}, set(rows["unordered"]) | set(rows["window_unused"]))
        for names in rows.values():
            for name in names:
                self.assertIn(f"`{name}`", self.modes_text())

    def modes_text(self):
        return play_docs.DOC.read_text(encoding="utf-8")

    def test_markers_appear_exactly_once_per_gravity_block(self):
        for name in play_docs.GRAVITY_BLOCKS:
            self.assertEqual(self.text.count(f"<!-- BEGIN GENERATED: {name} -->"), 1, name)
            self.assertEqual(self.text.count(f"<!-- END GENERATED: {name} -->"), 1, name)

    def test_the_draw_weight_includes_the_bit_scale(self):
        """DOC-4: the weight of a candidate is 2^(BITS_PER_UNIT * logit / T), not 2^(logit / T)."""
        from simvltanea.authoring.play_rng import BITS_PER_UNIT
        self.assertEqual(BITS_PER_UNIT, 8)
        self.assertIn(f"draw weight = 2^({BITS_PER_UNIT} * logit / temperature)", self.text)
        self.assertNotIn("integer softmax of (logit / temperature)", self.text)
        self.assertIn("about 256:1", self.text)

    def test_the_odds_the_page_states_are_what_the_draw_gives(self):
        """A logit gap of 1.0 at T=1 is 2^8 = 256:1 (the table weights round it to about 259:1)."""
        from simvltanea.authoring.play_rng import BITS_PER_UNIT, weighted_pick
        n16 = [16 * BITS_PER_UNIT, 0]
        draws = 1 << 14
        first = sum(weighted_pick(["a", "b"], n16, (i * (1 << 64)) // draws) == "a" for i in range(draws))
        odds = first / (draws - first)
        self.assertAlmostEqual(odds / 2 ** BITS_PER_UNIT, 1.0, delta=0.02)
        for gap, temperature in ((0.1, 1.0), (0.25, 0.5)):          # the worked examples in the odds table
            m = [round(16 * BITS_PER_UNIT * gap / temperature), 0]
            ones = sum(weighted_pick(["a", "b"], m, (i * (1 << 64)) // draws) == "a" for i in range(draws))
            self.assertAlmostEqual((ones / (draws - ones)) / 2 ** (BITS_PER_UNIT * gap / temperature), 1.0, delta=0.02)

    def test_every_constant_the_page_restates_is_generated_or_parsed(self):
        self.assertEqual(play_docs.prose_problems(self.text, play_docs.DOC.read_text(encoding="utf-8")), [])

    def test_a_deliberately_wrong_number_is_caught(self):
        """Each mutation changes one number in the page; the check (generated blocks or parsed prose) must fail."""
        modes = play_docs.DOC.read_text(encoding="utf-8")
        mutations = [
            ("| subjects | 0.22 |", "| subjects | 0.44 |"),
            ("| `magnetic` | 4 | 0.5 |", "| `magnetic` | 3 | 0.9 |"),
            ("(`gravity` in `GravityParams`) | -4 to 4 | 2.5 |", "(`gravity` in `GravityParams`) | -4 to 4 | 3.5 |"),
            ("P = 0.05", "P = 0.5"),
            ("2^(8 * logit / temperature)", "2^(2 * logit / temperature)"),
            ("steps of 10^-12", "steps of 10^-9"),
            ("`4/(4+rank)`", "`2/(2+rank)`"),
            ("1/16-bit steps", "1/32-bit steps"),
        ]
        for old, new in mutations:
            with self.subTest(old=old):
                self.assertIn(old, self.text)
                bad = self.text.replace(old, new)
                caught = play_docs.render_gravity(bad) != bad or bool(play_docs.prose_problems(bad, modes))
                self.assertTrue(caught, f"{old!r} -> {new!r} was not detected")

    def test_other_phrasings_of_the_same_constants_are_parsed_too(self):
        """DOC-F4: the hold floor, the spans-per-loop limit, the max_candidates default and the duration cap."""
        modes = play_docs.DOC.read_text(encoding="utf-8")
        for old, new in (("at least 0.25 s", "at least 2 s"), ("at most 1,024 spans per loop", "at most 4,096 spans per loop"),
                         ("Durations are capped at 600 s", "Durations are capped at 900 s")):
            with self.subTest(old=old):
                self.assertIn(old, modes)
                self.assertTrue(play_docs.prose_problems(self.text, modes.replace(old, new)))
        self.assertIn("(400 by default)", self.text)
        self.assertTrue(play_docs.prose_problems(self.text.replace("(400 by default)", "(800 by default)"), modes))
        self.assertTrue(play_docs.prose_problems(self.text, modes.replace("(400 by default)", "(800 by default)")))

    def test_modes_page_numbers_that_restate_code_are_parsed(self):
        modes = play_docs.DOC.read_text(encoding="utf-8")
        for old, new in (("at most 1,024 render segments", "at most 4,096 render segments"),
                         ("floor of 0.25 s", "floor of 2 s")):
            with self.subTest(old=old):
                self.assertIn(old, modes)
                self.assertTrue(play_docs.prose_problems(self.text, modes.replace(old, new)))


def round_of(base, voice, **extra):
    path = {"shape": "round", "base": base, "voice": voice, "delay_beats": 3, "beat_seconds": 2.0, **extra}
    order = {"axis": "captured_at"} if base in ("sequential", "converge", "diverge", "pingpong") else {"axis": "none"}
    return {"path": path, "order": order, "timing": {"synchronized": True, "hold_min": 4.0, "hold_max": 4.0}}


def with_timing(config, **timing):
    return {**config, "timing": {**config.get("timing", {}), **timing}}


def loops(config, n):
    """``config`` run with ``n`` loops (the key is read by ``outcome``, never passed on as a section)."""
    return {**config, "_n": n}


ROUND_BASES = ("sequential", "random", "playlist", "follow", "converge", "diverge", "pingpong")


def rounds(bases, voices=("clips", "tags")):
    return [round_of(b, v) for b in bases for v in voices]


def shaped(shape, window=0):
    order = {"axis": "captured_at"} if shape in ("sequential", "converge", "diverge", "pingpong") else {"axis": "none"}
    return {"path": {"shape": shape, "window": window}, "order": order}


# For each row of play_docs.INERT_ROWS: the configurations in which its settings do nothing, and contrasting
# configurations in which they do (so the check cannot pass just because the setting is never read).
INERT_CONFIGS = {
    "round_clips": ([round_of(b, "clips") for b in ("sequential", "random", "playlist", "follow", "converge", "pingpong")],
                    [round_of("sequential", "tags")]),
    "round_clips_unscored_base": ([round_of("random", "clips"), round_of("playlist", "clips")],
                                  [round_of("follow", "clips")]),
    "window_unused": ([shaped("random"), shaped("follow", 4), round_of("random", "tags"), round_of("playlist", "tags"),
                       round_of("follow", "clips"), round_of("random", "clips", window=4)],
                      [shaped("sequential", 0)]),
    "follow": ([shaped("follow"), round_of("follow", "clips")], [shaped("random"), round_of("follow", "tags")]),
    "window_zero": ([shaped(s) for s in ("sequential", "converge", "diverge", "pingpong", "playlist")]
                    + [round_of("sequential", "clips"), round_of("pingpong", "clips")],
                    [shaped("sequential", 4), shaped("playlist", 4)]
                    + [round_of(b, "tags") for b in ("sequential", "converge", "pingpong", "playlist")]),
    "stagger": ([with_timing(shaped(s), synchronized=True) for s in ("random", "sequential", "converge", "diverge", "pingpong", "playlist", "follow")]
                + [round_of("sequential", "clips"), round_of("random", "tags")],
                [shaped("random"), shaped("sequential"), shaped("follow")]),
    "not_a_round": ([shaped(s) for s in ("random", "sequential", "converge", "diverge", "pingpong", "playlist", "follow")],
                    [round_of("sequential", "clips"), round_of("sequential", "tags"), round_of("random", "tags")]),
    "unordered": ([shaped(s) for s in ("random", "playlist", "follow")],
                  [shaped("sequential"), shaped("pingpong"), shaped("converge"), shaped("diverge")]),
    "round_single_voice": (rounds(ROUND_BASES), [shaped("sequential"), shaped("pingpong"), shaped("converge")]),
    "round_unordered_base": (rounds(("random", "follow")), rounds(("sequential", "pingpong", "converge"), ("clips",))),
    "axis_none": (rounds(("random", "playlist", "follow")),
                  [{**round_of(b, v), "order": {"axis": "luma"}} for b in ("random", "playlist") for v in ("clips", "tags")]),
    "two_loops": ([loops(c, 2) for c in (shaped("random"), shaped("follow"), shaped("sequential", 4), shaped("playlist", 4),
                                         round_of("follow", "tags"))],
                  [shaped("random"), shaped("sequential", 4)]),
    "meeting_shapes": ([shaped("converge"), shaped("diverge"), *rounds(("converge", "diverge"))],
                       [shaped("sequential"), shaped("pingpong")]),
    "wrap_unused": ([shaped("converge"), shaped("pingpong"), *rounds(("converge", "pingpong"))],
                    [shaped("sequential"), shaped("diverge")]),
    "on_meet_unused": ([shaped("sequential"), shaped("pingpong"), shaped("diverge"),
                        *rounds(("sequential", "pingpong", "diverge"))], [shaped("converge")]),
    "ends_unused": ([shaped("sequential"), shaped("pingpong"), *rounds(("sequential", "pingpong"))],
                    [shaped("converge"), shaped("diverge")]),
    "playlist_cooldown": ([shaped("playlist", 0), shaped("playlist", 4), round_of("playlist", "clips")],
                          [shaped("sequential", 0), shaped("sequential", 4)]),
}
# Anchors only matter together with a pull, so both names change the pair.
ANCHORS = {"relation": {"anchors": ["clip-002", "clip-005", "clip-009"], "anchor_pull": 1.5}}
ALTERED = {
    "relation.anchors": ANCHORS, "relation.anchor_pull": ANCHORS,
    "timing.cooldown": {"timing": {"cooldown": 300.0}}, "timing.recency": {"timing": {"recency": 2.0}},
    "timing.recency_window": {"timing": {"recency_window": 10.0}}, "timing.novelty": {"timing": {"novelty": 2.0}},
    "relation.independence": {"relation": {"independence": 0.9}}, "relation.adjacency": {"relation": {"adjacency": 1.0}},
    "relation.strength": {"relation": {"strength": -1.0}}, "relation.temperature": {"relation": {"temperature": 3.0}},
    "relation.weights.*": {"relation": {"weights": {name: (-0.5 if i % 2 else 0.9) for i, name in enumerate(ALL_COMPONENTS)}}},
    "path.window": {"path": {"window": 4}},
    "timing.stagger": {"timing": {"stagger": 3.0}},
    "path.base": {"path": {"base": "random"}}, "path.voice": {"path": {"voice": "tags"}},
    "path.tag": {"path": {"tag": "environment"}}, "path.delay_beats": {"path": {"delay_beats": 5}},
    "path.beat_seconds": {"path": {"beat_seconds": 4.0}},
    "order.axis": {"order": {"axis": "luma"}}, "order.direction": {"order": {"direction": "descending"}},
    "order.missing": {"order": {"missing": "end"}},
    "path.step": {"path": {"step": 3}}, "path.direction": {"path": {"direction": "backward"}},
    "path.wrap": {"path": {"wrap": "stop"}}, "path.spread": {"path": {"spread": "together"}},
    "path.on_meet": {"path": {"on_meet": "restart"}}, "path.groups": {"path": {"groups": "halves"}},
    "path.first_end": {"path": {"first_end": "high"}},
}
# Every configuration runs at both scales: a roomy pool where no clip comes back, and a small pool over a long
# run where clips do come back, which is the only place a cooldown, a recency or a novelty term can show.
SCALES = (("roomy", 96, 120), ("recurring", 14, 300))


def with_setting(config, name):
    out = {section: dict(values) if isinstance(values, dict) else values for section, values in config.items()}
    for section, values in ALTERED[name].items():
        out[section] = {**out.get(section, {}), **values}
    return out


def outcome(overlay, scale, seed=1):
    """The state digest, or the refusal text: a setting that changes only the refusal still changed the outcome."""
    _, pool, seconds = scale
    n = overlay.get("_n", 3)
    overlay = {key: value for key, value in overlay.items() if key != "_n"}
    try:
        return digest(play(cfg("sticky", **overlay), n, seconds, seed, pool=pool)["state"])
    except PlayError as exc:
        return f"refused: {exc}"


def inert_violations(rows, configs):
    """(row, setting, shape, base, scale) for every listed setting that does change the state where a row says it cannot."""
    found = []
    for key, _, names, _ in rows:
        for overlay in configs[key][0]:
            for scale in SCALES:
                base = outcome(overlay, scale)
                assert not base.startswith("refused"), (key, overlay, base)
                for name in names:
                    if outcome(with_setting(overlay, name), scale) != base:
                        found.append((key, name, overlay["path"]["shape"], overlay["path"].get("base"), scale[0]))
    return found


class InertSettingsTests(unittest.TestCase):
    def test_every_row_has_a_check_and_names_real_settings(self):
        self.assertEqual({row[0] for row in play_docs.INERT_ROWS}, set(INERT_CONFIGS))
        for _, _, names, _ in play_docs.INERT_ROWS:
            for name in names:
                self.assertIn(name, ALTERED)

    def test_each_listed_setting_leaves_the_state_byte_identical_where_the_page_says_it_does_nothing(self):
        self.assertEqual(inert_violations(play_docs.INERT_ROWS, INERT_CONFIGS), [])

    def test_the_same_settings_do_change_the_state_in_the_contrasting_configuration(self):
        for key, where, names, _ in play_docs.INERT_ROWS:
            for name in names:
                with self.subTest(row=key, setting=name):
                    changed = [outcome(with_setting(o, name), scale) != outcome(o, scale)
                               for o in INERT_CONFIGS[key][1] for scale in SCALES]
                    self.assertTrue(any(changed), "the setting is inert in the control as well: the row proves nothing")

    def test_a_false_row_is_caught_for_cooldown_recency_and_novelty(self):
        """The check must be able to fail: claim each of these inert where it is read, and it must be reported."""
        sequential = [shaped("sequential", 4)]
        for name, overlays in (("timing.cooldown", [shaped("sequential", 0)]), ("timing.recency", sequential),
                               ("timing.novelty", sequential)):
            row = ("false_row", "a row that is wrong", (name,), "")
            with self.subTest(setting=name):
                found = inert_violations([row], {"false_row": (overlays, [])})
                self.assertTrue(found and found[0][1] == name, found)

    def test_a_false_cooldown_claim_for_the_window_zero_row_is_caught(self):
        rows = [(k, w, (*names, "timing.cooldown") if k == "window_zero" else names, why)
                for k, w, names, why in play_docs.INERT_ROWS]
        found = inert_violations(rows, INERT_CONFIGS)
        self.assertTrue(any(f[0] == "window_zero" and f[1] == "timing.cooldown" for f in found), found)

    def test_the_window_zero_row_does_not_claim_the_tags_voice_round(self):
        row = next(r for r in play_docs.INERT_ROWS if r[0] == "window_zero")
        self.assertIn("`voice` = `clips`", row[1])
        self.assertNotIn("timing.cooldown", row[2])
        for base in ("sequential", "playlist"):
            overlay = round_of(base, "tags")
            for name in row[2]:
                with self.subTest(base=base, setting=name):
                    changed = [outcome(with_setting(overlay, name), scale) != outcome(overlay, scale) for scale in SCALES]
                    self.assertTrue(any(changed))

    def test_the_cooldown_note_matches_the_playlist_behaviour(self):
        row = next(r for r in play_docs.INERT_ROWS if r[0] == "playlist_cooldown")
        self.assertEqual(row[2], ("timing.cooldown",))
        self.assertIn("`playlist`", row[1])
        window_zero = next(r for r in play_docs.INERT_ROWS if r[0] == "window_zero")
        self.assertIn("except under `playlist`", window_zero[3])
        for base in ("sequential", "converge", "diverge", "pingpong"):                       # the other shapes do read it
            self.assertTrue(any(outcome(with_setting(shaped(base, 0), "timing.cooldown"), scale)
                                != outcome(shaped(base, 0), scale) for scale in SCALES), base)


def starts_of(out, loop):
    """Seconds at which one loop shows another clip."""
    sched = out["schedule"]
    return [ch["frame"] / sched.fps for ch in sched.changes if ch["op"] == "show" and ch["loop"] == loop]


class SynchronizedNoteTests(unittest.TestCase):
    """What the page says ``timing.synchronized`` means, checked against generated states."""

    HOLD, DELAY, BEAT, SECONDS = 4.0, 3, 2.0, 60

    def make(self, base, voice, n, **timing):
        config = round_of(base, voice)
        config["timing"] = {**config["timing"], **timing}
        return play(cfg("sticky", **config), n, self.SECONDS, 5, pool=96)

    def test_a_round_offsets_loop_k_by_k_delays_on_the_beat_grid_for_both_voices(self):
        offset = self.DELAY * self.BEAT
        for voice in ("clips", "tags"):
            for n in (2, 3, 4):
                out = self.make("sequential", voice, n)
                for k, loop in enumerate(out["schedule"].loop_ids):
                    expected = [t for t in (self.HOLD * m + (k * offset) % self.HOLD for m in range(0, 100))
                                if 0 < t < self.SECONDS]
                    with self.subTest(voice=voice, n=n, loop=loop):
                        self.assertEqual(starts_of(out, loop), expected)
                        self.assertTrue(all(((t - k * offset) % self.HOLD) == 0 for t in starts_of(out, loop)))
        out = self.make("sequential", "clips", 3)            # the round never has all loops change together
        self.assertNotEqual(starts_of(out, "loop-1"), starts_of(out, "loop-2"))

    def test_the_clips_voice_plays_loop_zeros_clips_a_delay_later(self):
        offset = self.DELAY * self.BEAT
        out = self.make("sequential", "clips", 3)
        sched = out["schedule"]
        shown = {frame: snap for frame, snap in sched.timeline()}
        def clip_at(loop, second):
            frame = max(f for f in shown if f <= int(second * sched.fps))
            return shown[frame][loop]
        first, second, third = sched.loop_ids
        for t in range(int(offset * 2), self.SECONDS):
            self.assertEqual(clip_at(second, t), clip_at(first, t - offset), t)
            self.assertEqual(clip_at(third, t), clip_at(first, t - 2 * offset), t)

    def test_stagger_is_not_used_by_a_round_nor_by_the_synchronized_shapes(self):
        for voice in ("clips", "tags"):
            near, far = (self.make("sequential", voice, 3, stagger=s) for s in (0.5, 3.0))
            self.assertEqual(digest(near["state"]), digest(far["state"]), voice)
        def together(stagger):
            config = cfg("sticky", timing={"synchronized": True, "stagger": stagger, "hold_min": 4.0, "hold_max": 8.0})
            return play(config, 3, 60, 5, pool=96)
        near, far = together(0.5), together(3.0)
        self.assertEqual(digest(near["state"]), digest(far["state"]))
        loops = near["schedule"].loop_ids
        self.assertTrue(starts_of(near, loops[0]))
        for loop in loops[1:]:
            self.assertEqual(starts_of(near, loop), starts_of(near, loops[0]))     # all loops change on the same frame

    def test_a_round_requires_synchronized_true(self):
        config = round_of("sequential", "clips")
        config["timing"]["synchronized"] = False
        with self.assertRaises(PlayError):
            play(cfg("sticky", **config), 3, 30, 5, pool=96)


class DocumentedDurationTests(unittest.TestCase):
    """The segment table is only worth printing if the durations in it really stay under the limit."""

    def test_typical_durations_stay_within_the_limit_on_the_synthetic_pool(self):
        for n, seed in ((2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (7, 2)):
            seconds = play_docs.typical_duration(n)
            report = play(cfg("sticky"), n, seconds, seed, pool=120)["report"]
            self.assertLessEqual(report["render_segments"], play_docs.LIMIT, (n, seconds, seed))
            self.assertTrue(report["renderable"])

    def test_guaranteed_durations_stay_within_the_limit_with_the_shortest_documented_clips(self):
        for n, hold in ((7, 4.0), (4, 4.0), (7, 12.0)):
            seconds = play_docs.segment_durations(n, hold, 1.5)
            config = cfg("sticky", timing={"hold_min": hold, "hold_max": hold + 8})
            report = play(config, n, seconds, 3, pool=120)["report"]
            self.assertLessEqual(report["render_segments"], play_docs.LIMIT, (n, hold, seconds))

    def test_a_longer_duration_than_the_typical_one_can_exceed_it(self):
        report = play(cfg("sticky"), 7, 600, 1, pool=120)["report"]
        self.assertGreater(report["render_segments"], play_docs.LIMIT)
        self.assertLess(play_docs.typical_duration(7), 600)


if __name__ == "__main__":
    unittest.main()
