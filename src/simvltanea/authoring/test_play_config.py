"""Play-mode configuration: validation, metadata consistency, presets as data, overrides, digests."""
import json
import unittest

from simvltanea.authoring import play_config as pc
from simvltanea.authoring import play_presets as pp
from simvltanea.authoring.gravity_affinity import ALL_COMPONENTS
from simvltanea.authoring.test_play_support import cfg


def leaf_paths(config):
    out = set()
    for section in pc.SECTIONS:
        for key, value in config[section].items():
            if key == "weights":
                out |= {f"{section}.weights.{name}" for name in value}
            else:
                out.add(f"{section}.{key}")
    return out | {"seed"}


class MetadataTests(unittest.TestCase):
    def test_metadata_covers_exactly_the_validated_fields(self):
        described = {p["path"] for p in pc.describe_parameters()}
        self.assertEqual(described, leaf_paths(pc.validate_config({})))
        self.assertEqual({f"relation.weights.{c}" for c in ALL_COMPONENTS}, {p for p in described if ".weights." in p})
        for p in pc.describe_parameters():
            self.assertTrue(p["description"].strip(), p["path"])
            self.assertIn(p["type"], {"number", "integer", "boolean", "enum", "id_list", "flag_list", "pin_list", "seed"})

    def test_defaults_in_metadata_equal_the_validated_defaults(self):
        defaults = pc.validate_config({})
        for p in pc.describe_parameters():
            parts = p["path"].split(".")
            value = defaults
            for part in parts:
                value = value[part]
            self.assertEqual(value, p["default"] if p["type"] != "number" else float(p["default"]), p["path"])

    def test_declared_ranges_are_exactly_what_the_validator_enforces(self):
        probed = 0
        for p in pc.describe_parameters():
            if p["type"] not in ("number", "integer"):
                continue
            section, name = p["section"], p["name"]
            extra = {}
            if p["path"] == "timing.hold_min":
                extra = {"hold_max": 3600.0}
            if p["path"] == "timing.hold_max":
                extra = {"hold_min": pc.MIN_HOLD}

            def attempt(value):
                if name.startswith("weights."):
                    raw = {section: {"weights": {name.split(".")[1]: value}}}
                else:
                    raw = {section: {name: value, **extra}}
                return pc.validate_config(raw)

            low, high = p["min"], p["max"]
            step = 1 if p["type"] == "integer" else 1e-6
            attempt(low), attempt(high)                                   # both bounds are accepted
            for bad in (low - step, high + step, float("nan"), float("inf"), True, "1", None):
                with self.subTest(path=p["path"], value=bad), self.assertRaises(pc.PlayError):
                    attempt(bad)
            probed += 1
        self.assertGreater(probed, 25)

    def test_declared_choices_are_exactly_what_the_validator_accepts(self):
        base = pp.PRESETS["round_clips"]
        for p in pc.describe_parameters():
            if p["type"] not in ("enum", "flag_list"):
                continue
            # wrap=stop and on_meet=stop/hold are valid choices of the ordered shapes; a round refuses them (its base
            # voice would halt), so these two settings are checked on a plain ordered path instead.
            where = {"order": {"axis": "captured_at"}, "path": {"shape": "diverge"}} if p["path"] in (
                "path.wrap", "path.on_meet") else {}
            start = pc.validate_config(where, pp.PRESETS["sticky"]) if where else base
            for choice in p["choices"]:
                value = choice if p["type"] == "enum" else [choice]
                pc.validate_config({p["section"]: {p["name"]: value}}, start)
            with self.subTest(path=p["path"]), self.assertRaises(pc.PlayError):
                pc.validate_config({p["section"]: {p["name"]: "nonsense" if p["type"] == "enum" else ["nonsense"]}}, base)

    def test_metadata_is_json_serialisable(self):
        json.dumps(pc.describe_parameters())


class SeedTextTests(unittest.TestCase):
    """DP-2 and DP-6: a seed that cannot be serialised is refused, and seed TEXT follows one rule everywhere."""

    CASES = (("007", "007"), ("-0", "-0"), ("7", 7), ("-7", -7), ("0", 0), ("+7", "+7"), (" 7", " 7"), ("1.5", "1.5"),
             ("1e3", "1e3"), ("abc", "abc"), ("", ""), ("٧", "٧"), ("1_0", "1_0"), ("-", "-"), ("00", "00"),
             (str(pc.MAX_SAFE_SEED), pc.MAX_SAFE_SEED), (str(-pc.MAX_SAFE_SEED), -pc.MAX_SAFE_SEED),
             (str(pc.MAX_SAFE_SEED + 1), str(pc.MAX_SAFE_SEED + 1)), ("9" * 5000, "9" * 5000))

    def test_the_rule_itself(self):
        for text, expected in self.CASES:
            with self.subTest(text=text[:20]):
                got = pc.seed_from_text(text)
                self.assertEqual(got, expected)
                self.assertIs(type(got), type(expected))

    def test_the_rule_is_applied_to_config_text_set_assignments_and_presets_files(self):
        for text, expected in self.CASES:
            if len(text) > 200 or text == "":
                continue
            with self.subTest(text=text[:20]):
                self.assertEqual(pc.config_from_json(json.dumps({"seed": text}))["seed"], expected)
                self.assertEqual(pc.config_from_json(json.dumps({"seed": text}))["seed"],
                                 pc.validate_config(pc.apply_set({}, f"seed={text}"))["seed"])
                self.assertEqual(pp.load_presets_file(json.dumps({"p": {"config": {"seed": text}}}))["p"]["config"]["seed"],
                                 text if isinstance(expected, str) else expected)
        self.assertEqual(pc.config_from_json('{"seed": 7}')["seed"], 7)            # a JSON number is already a number
        self.assertEqual(pc.config_from_json('{"seed": 7}')["seed"], pc.config_from_json('{"seed": "7"}')["seed"])
        self.assertNotEqual(pc.config_from_json('{"seed": "007"}')["seed"], pc.config_from_json('{"seed": 7}')["seed"])
        self.assertEqual(pc.apply_set({}, 'seed="abc"')["seed"], "abc")             # a quoted JSON string still works
        self.assertEqual(pc.validate_config({"seed": "7"})["seed"], "7")           # code that passes a str means a str

    def test_a_seed_that_cannot_be_serialised_is_refused_with_a_clear_message(self):
        for bad in ("ab\udcffcd", "\ud800", "x" * 3 + "\udfff"):
            with self.subTest(seed=ascii(bad)):
                with self.assertRaisesRegex(pc.PlayError, "seed.*(UTF-8|encode)") as raised:
                    pc.validate_config({"seed": bad})
                self.assertNotIn("udc", str(raised.exception))                        # the text is never echoed
                with self.assertRaises(pc.PlayError):
                    pc.config_from_json(json.dumps({"seed": bad}))
        self.assertEqual(pc.validate_config({"seed": "caf\u00e9 \U0001f600"})["seed"], "caf\u00e9 \U0001f600")
        for bad in (10 ** 5000, 2 ** 53, -2 ** 53):
            with self.assertRaises(pc.PlayError):
                pc.validate_config({"seed": bad})


class AnchorDescriptionTests(unittest.TestCase):
    def test_anchors_are_described_as_attracting_only_because_the_pull_cannot_be_negative(self):
        """DOC-5: anchor_pull is 0..2, so an anchor can never repel; the description must not say it can."""
        entries = {p["path"]: p for p in pc.describe_parameters()}
        self.assertEqual((entries["relation.anchor_pull"]["min"], entries["relation.anchor_pull"]["max"]), (0.0, 2.0))
        for negative in (-0.1, -1.0):
            with self.assertRaises(pc.PlayError):
                pc.validate_config({"relation": {"anchors": ["c1"], "anchor_pull": negative}})
        text = entries["relation.anchors"]["description"].lower()
        self.assertNotIn("or repel", text)                                  # the old claim: "attract (or repel, see anchor_pull)"
        self.assertIn("only attract", text)
        self.assertIn("cannot repel", text)


class ValidationTests(unittest.TestCase):
    def test_unknown_keys_are_rejected_everywhere(self):
        for raw in ({"nope": 1}, {"order": {"nope": 1}}, {"relation": {"weights": {"nope": 0.1}}},
                    {"order": 5}, {"relation": {"weights": 3}}, {"limits": {"nope": 1}}):
            with self.subTest(raw=raw), self.assertRaises(pc.PlayError):
                pc.validate_config(raw)

    def test_a_bare_string_never_stands_for_a_list(self):
        lists = [p for p in pc.PARAMETERS if p["type"] in ("id_list", "flag_list", "pin_list")]
        self.assertEqual(len(lists), 4)
        for p in lists:
            for bad in ("readable_text", "clip-001", "abc", {"a": 1}, 5):
                with self.subTest(path=f"{p['section']}.{p['name']}", value=bad), self.assertRaises(pc.PlayError):
                    pc.validate_config({p["section"]: {p["name"]: bad}})

    def test_list_elements_are_type_checked(self):
        for raw in ({"exclusion": {"exclude_ids": [1]}}, {"exclusion": {"exclude_ids": ["../x"]}},
                    {"exclusion": {"exclude_ids": [None]}}, {"relation": {"anchors": [["a"]]}},
                    {"exclusion": {"exclude_privacy_flags": ["readable_text", "made_up"]}},
                    {"exclusion": {"exclude_privacy_flags": [3]}},
                    {"path": {"pins": [["loop-1"]]}}, {"path": {"pins": ["loop-1=a"]}},
                    {"path": {"pins": [["loop-1", 7]]}}):
            with self.subTest(raw=raw), self.assertRaises(pc.PlayError):
                pc.validate_config(raw)

    def test_each_privacy_flag_is_known_and_kept(self):
        ok = pc.validate_config({"exclusion": {"exclude_privacy_flags": list(pc.PRIVACY_FLAGS)}})
        self.assertEqual(ok["exclusion"]["exclude_privacy_flags"], sorted(pc.PRIVACY_FLAGS))

    def test_two_pins_for_one_loop_and_one_clip_on_two_loops_are_rejected(self):
        with self.assertRaisesRegex(pc.PlayError, "two pins for one loop"):
            pc.validate_config({"path": {"pins": [["loop-1", "a"], ["loop-1", "b"]]}})
        with self.assertRaises(pc.PlayError):
            pc.validate_config({"path": {"pins": [["loop-1", "a"], ["loop-2", "a"]]}})
        pc.validate_config({"path": {"pins": [["loop-1", "a"], ["loop-2", "b"]]}})

    def test_holds_have_a_hard_floor_and_swaps_cannot_round_to_nothing(self):
        for bad in ({"hold_min": 0.1}, {"hold_min": 0.0}, {"hold_max": 0.1}, {"swap_interval": 0.1},
                    {"hold_min": 8.0, "hold_max": 4.0}):
            with self.subTest(bad=bad), self.assertRaises(pc.PlayError):
                pc.validate_config({"timing": bad})
        pc.validate_config({"timing": {"hold_min": 0.25, "hold_max": 0.25, "swap_interval": 0.25}})
        pc.validate_config({"timing": {"swap_interval": 0}})

    def test_shape_specific_requirements_fail_clearly(self):
        for raw, text in (({"path": {"shape": "converge"}}, "needs an order"),
                          ({"path": {"shape": "pingpong"}}, "needs an order"),
                          ({"path": {"shape": "sequential"}, "order": {"axis": "luma"},
                            "timing": {"swap_interval": 5}}, "swap_interval"),
                          ({"path": {"shape": "round"}}, "synchronized"),
                          ({"path": {"shape": "round"}, "timing": {"synchronized": True}}, "hold_min == "),
                          ({"path": {"shape": "round", "pins": [["loop-1", "a"]]},
                            "timing": {"synchronized": True, "hold_min": 4, "hold_max": 4}}, "pins"),
                          ({"path": {"shape": "round", "beat_seconds": 3.0, "delay_beats": 5},
                            "timing": {"synchronized": True, "hold_min": 4, "hold_max": 4}}, "whole number of")):
            with self.subTest(raw=raw), self.assertRaisesRegex(pc.PlayError, text):
                pc.validate_config(raw)

    def test_a_canon_of_clips_needs_the_delay_to_cover_the_hold(self):
        timing = {"synchronized": True, "hold_min": 6.0, "hold_max": 6.0}
        with self.assertRaisesRegex(pc.PlayError, "same clip would be on two loops"):
            pc.validate_config({"path": {"shape": "round", "voice": "clips", "delay_beats": 2, "beat_seconds": 2.0},
                                "timing": timing})
        pc.validate_config({"path": {"shape": "round", "voice": "clips", "delay_beats": 3, "beat_seconds": 2.0},
                            "timing": timing})
        # the tag voice has no duplication problem, so a short delay is fine
        pc.validate_config({"path": {"shape": "round", "voice": "tags", "delay_beats": 1, "beat_seconds": 2.0},
                            "timing": timing})

    ROUND = {"shape": "round", "voice": "clips", "delay_beats": 3, "beat_seconds": 2.0}
    ROUND_TIMING = {"synchronized": True, "hold_min": 4.0, "hold_max": 4.0}

    def test_a_round_whose_base_voice_can_halt_is_refused_naming_the_setting(self):
        # F5: these used to validate and then fail in schedule_play once the voice reached its end (long runs only).
        halting = [("sequential", {"wrap": "stop"}, "path.wrap"), ("converge", {"on_meet": "stop"}, "path.on_meet"),
                   ("converge", {"on_meet": "hold"}, "path.on_meet"), ("diverge", {"wrap": "stop"}, "path.wrap")]
        for voice in ("clips", "tags"):
            for base, extra, setting in halting:
                with self.subTest(voice=voice, base=base, extra=extra):
                    raw = {"path": {**self.ROUND, "voice": voice, "base": base, **extra}, "timing": self.ROUND_TIMING,
                           "order": {"axis": "captured_at"}}
                    with self.assertRaises(pc.PlayError) as caught:
                        pc.validate_config(raw)
                    self.assertIn(setting + "=", str(caught.exception))
                    self.assertIn(base, str(caught.exception))

    def test_a_round_over_a_base_voice_that_keeps_moving_is_accepted(self):
        keeps_moving = [("sequential", {"wrap": "wrap"}), ("sequential", {"wrap": "bounce"}),
                        ("converge", {"on_meet": "bounce"}), ("converge", {"on_meet": "restart"}),
                        ("diverge", {"wrap": "wrap"}), ("diverge", {"wrap": "bounce"}), ("pingpong", {"wrap": "stop"}),
                        ("pingpong", {}), ("random", {"wrap": "stop", "on_meet": "stop"}),
                        ("playlist", {"wrap": "stop"}), ("follow", {"on_meet": "hold"})]
        for base, extra in keeps_moving:
            with self.subTest(base=base, extra=extra):
                pc.validate_config({"path": {**self.ROUND, "base": base, **extra}, "timing": self.ROUND_TIMING,
                                    "order": {"axis": "captured_at"}})

    def test_the_halting_settings_stay_valid_outside_a_round(self):
        for shape, extra in (("sequential", {"wrap": "stop"}), ("converge", {"on_meet": "stop"}),
                             ("converge", {"on_meet": "hold"}), ("diverge", {"wrap": "stop"})):
            with self.subTest(shape=shape, extra=extra):
                pc.validate_config({"path": {"shape": shape, **extra}, "order": {"axis": "captured_at"}})

    def test_integer_seeds_beyond_the_javascript_safe_range_are_refused_but_strings_are_kept(self):
        limit = 2 ** 53 - 1
        for seed in (limit, -limit, 0):
            self.assertEqual(pc.validate_config({"seed": seed})["seed"], seed)
        for seed in (limit + 1, -limit - 1, 123456789012345678, 10 ** 30):
            with self.subTest(seed=seed), self.assertRaisesRegex(pc.PlayError, "string"):
                pc.validate_config({"seed": seed})
            self.assertEqual(pc.validate_config({"seed": str(seed)})["seed"], str(seed))

    def test_the_seed_given_to_the_scheduler_is_bounded_the_same_way(self):
        from simvltanea.authoring.test_play_support import play
        with self.assertRaisesRegex(pc.PlayError, "string"):
            play(cfg("sticky"), 2, 10, 2 ** 53, pool=30)

    def test_seed_forms(self):
        for seed in (0, -5, "abc", "x" * 200):
            self.assertEqual(pc.validate_config({"seed": seed})["seed"], seed)
        for seed in (True, 1.5, None, [1], "x" * 201):
            with self.subTest(seed=seed), self.assertRaises(pc.PlayError):
                pc.validate_config({"seed": seed})


class BooleanParameterTests(unittest.TestCase):
    """RS-4: a boolean is true or false and nothing else. Accepting 0 or 1 would let a tool that writes numbers switch the
    safety or minors exclusion off unnoticed (``--set exclusion.require_safety_clear=0`` parses to the integer 0)."""

    BOOLEANS = [p for p in pc.describe_parameters() if p["type"] == "boolean"]
    NOT_BOOLEAN = (0, 1, 0.0, 1.0, -1, 2, "false", "true", "0", "1", None, [], {})

    def test_the_boolean_parameters_include_the_two_safety_switches(self):
        paths = {p["path"] for p in self.BOOLEANS}
        self.assertLessEqual({"exclusion.require_safety_clear", "exclusion.exclude_minors", "timing.synchronized",
                              "limits.refuse_unrenderable"}, paths)

    def test_every_boolean_parameter_accepts_true_and_false(self):
        for p in self.BOOLEANS:
            section, name = p["path"].split(".")
            for value in (True, False):
                with self.subTest(parameter=p["path"], value=value):
                    self.assertIs(pc.validate_config({section: {name: value}})[section][name], value)

    def test_no_boolean_parameter_accepts_a_number_a_word_or_nothing(self):
        for p in self.BOOLEANS:
            section, name = p["path"].split(".")
            for value in self.NOT_BOOLEAN:
                with self.subTest(parameter=p["path"], value=repr(value)):
                    with self.assertRaises(pc.PlayError) as caught:
                        pc.validate_config({section: {name: value}})
                    self.assertIn("true or false", str(caught.exception))

    def test_the_set_option_route_refuses_zero_and_one_for_every_boolean_parameter(self):
        for p in self.BOOLEANS:
            for text in ("0", "1", "0.0", "yes"):
                with self.subTest(parameter=p["path"], text=text):
                    with self.assertRaises(pc.PlayError):
                        pc.validate_config(pc.apply_set({}, f"{p['path']}={text}"))
            for text, expected in (("true", True), ("false", False)):
                with self.subTest(parameter=p["path"], text=text):
                    section, name = p["path"].split(".")
                    self.assertIs(pc.validate_config(pc.apply_set({}, f"{p['path']}={text}"))[section][name], expected)


class IdListCapTests(unittest.TestCase):
    """Every id_list parameter is bounded: a 1 MiB configuration could otherwise carry about 25,000 ids."""

    PATHS = [(p["path"].split(".")[0], p["path"].split(".")[1]) for p in pc.describe_parameters() if p["type"] == "id_list"]

    def ids(self, count):
        return [f"clip-{i:06d}" for i in range(count)]

    def test_the_two_id_lists_are_the_ones_covered(self):
        self.assertEqual(sorted(self.PATHS), [("exclusion", "exclude_ids"), ("relation", "anchors")])

    def test_a_list_at_the_cap_is_accepted_and_one_over_is_refused_with_a_clear_error(self):
        for section, key in self.PATHS:
            with self.subTest(parameter=f"{section}.{key}"):
                accepted = pc.validate_config({section: {key: self.ids(pc.MAX_ID_LIST)}})
                self.assertEqual(len(accepted[section][key]), pc.MAX_ID_LIST)
                with self.assertRaises(pc.PlayError) as caught:
                    pc.validate_config({section: {key: self.ids(pc.MAX_ID_LIST + 1)}})
                message = str(caught.exception)
                self.assertIn(f"{section}.{key}", message)
                self.assertIn(str(pc.MAX_ID_LIST), message)

    def test_the_cap_counts_the_list_as_given_not_after_removing_duplicates(self):
        with self.assertRaises(pc.PlayError):
            pc.validate_config({"exclusion": {"exclude_ids": ["same-id"] * (pc.MAX_ID_LIST + 1)}})


class RoundTripTests(unittest.TestCase):
    def test_json_round_trip_and_digest_are_stable(self):
        config = cfg("city_vs_nature", seed="roundtrip")
        again = pc.config_from_json(pc.config_to_json(config))
        self.assertEqual(again, config)
        self.assertEqual(pc.config_digest(again), pc.config_digest(config))
        self.assertEqual(pc.config_to_json(again), pc.config_to_json(config))

    def test_digest_ignores_spelling_and_key_order_but_not_values(self):
        a = pc.validate_config({"relation": {"strength": 2, "adjacency": 0.5}, "timing": {"hold_min": 4}})
        b = pc.validate_config({"timing": {"hold_min": 4.0}, "relation": {"adjacency": 0.5, "strength": 2.0}})
        self.assertEqual(pc.config_digest(a), pc.config_digest(b))
        c = pc.validate_config({"relation": {"strength": 2.001}})
        self.assertNotEqual(pc.config_digest(a), pc.config_digest(c))
        self.assertNotEqual(pc.config_digest(a), pc.config_digest(pc.validate_config({"seed": 9})))

    def test_digest_is_a_pinned_value_for_the_starting_configuration(self):
        # Pins the starting values: changing any default changes this digest on purpose and visibly.
        self.assertEqual(pc.config_digest(pc.validate_config({})), pc.config_digest(pp.PRESETS["sticky"]))
        self.assertEqual(len(pc.config_digest(pc.validate_config({}))), 64)

    def test_invalid_json_is_a_clear_error(self):
        for text in ("{", "[]", '{"order": 3}'):
            with self.subTest(text=text), self.assertRaises(pc.PlayError):
                pc.config_from_json(text)


class OverrideTests(unittest.TestCase):
    def test_set_overrides_one_value_and_leaves_the_rest(self):
        base = pp.PRESETS["chronological"]
        raw = pc.apply_set({}, "relation.strength=-2")
        raw = pc.apply_set(raw, "relation.weights.color=-0.5")
        raw = pc.apply_set(raw, "path.shape=pingpong")
        raw = pc.apply_set(raw, "exclusion.exclude_ids=[\"a-1\",\"b-2\"]")
        raw = pc.apply_set(raw, "seed=42")
        merged = pc.validate_config(raw, base)
        self.assertEqual((merged["relation"]["strength"], merged["relation"]["weights"]["color"],
                          merged["path"]["shape"], merged["seed"]), (-2.0, -0.5, "pingpong", 42))
        self.assertEqual(merged["exclusion"]["exclude_ids"], ["a-1", "b-2"])
        self.assertEqual(merged["order"], base["order"])
        self.assertEqual(merged["timing"], base["timing"])
        self.assertEqual(merged["relation"]["weights"]["subjects"], base["relation"]["weights"]["subjects"])
        self.assertEqual(raw["seed"], 42)

    def test_set_rejects_malformed_assignments_and_bad_values(self):
        for bad in ("relation.strength", "=1", "strength=1", "relation.nope.x=1", "a.b.c.d=1", "nope.key=1"):
            with self.subTest(bad=bad), self.assertRaises(pc.PlayError):
                pc.apply_set({}, bad)
        with self.assertRaises(pc.PlayError):
            pc.validate_config(pc.apply_set({}, "relation.strength=9"))
        with self.assertRaises(pc.PlayError):
            pc.validate_config(pc.apply_set({}, "path.shape=sideways"))

    def test_set_does_not_mutate_its_input(self):
        raw = {"relation": {"strength": 1}}
        pc.apply_set(raw, "relation.strength=2")
        self.assertEqual(raw, {"relation": {"strength": 1}})


class PresetTableTests(unittest.TestCase):
    OWNER = {"random", "chronological", "reverse_chronological", "oldest_meets_newest", "newest_meets_oldest",
             "round_clips", "round_tags", "opposites", "city_vs_nature", "near_vs_far", "drift", "sticky",
             "magnetic", "calm_to_intense", "dark_to_light", "rainbow"}

    def test_the_required_presets_exist_and_each_is_complete_and_valid(self):
        self.assertEqual(set(pp.PRESETS), self.OWNER)
        shape = leaf_paths(pc.validate_config({}))
        for name, config in pp.PRESETS.items():
            self.assertEqual(leaf_paths(config), shape, name)
            self.assertEqual(pc.validate_config(config), config, name)      # already normalised and valid
            self.assertTrue(pp.descriptions()[name].strip(), name)

    def test_sticky_is_the_starting_values_and_presets_differ_only_by_data(self):
        self.assertEqual(pp.PRESETS["sticky"], pc.validate_config({}))
        self.assertEqual(pp.DEFAULT_PRESET, "sticky")
        digests = {pc.config_digest(c) for c in pp.PRESETS.values()}
        self.assertEqual(len(digests), len(pp.PRESETS))

    def test_users_add_and_override_presets_with_a_json_file(self):
        text = json.dumps({"mine": {"description": "my mode", "config": {"relation": {"strength": -1}, "seed": "s"}},
                           "sticky": {"description": "overridden", "config": {"relation": {"strength": 0.5}}}})
        user = pp.load_presets_file(text)
        table = pp.merged_table(user)
        self.assertEqual(set(table), set(pp.PRESET_TABLE) | {"mine"})
        self.assertEqual(pp.get_preset("mine", table)["relation"]["strength"], -1.0)
        self.assertEqual(pp.get_preset("sticky", table)["relation"]["strength"], 0.5)
        self.assertEqual(pp.get_preset("sticky")["relation"]["strength"], 2.5)      # built-ins untouched
        self.assertEqual(pp.descriptions(table)["sticky"], "overridden")

    def test_bad_user_presets_name_the_preset_and_fail(self):
        for text in ("[]", "{", json.dumps({"x": {"config": {"relation": {"strength": 99}}}}),
                     json.dumps({"x": {}}), json.dumps({"bad name!": {"config": {}}}),
                     json.dumps({"x": {"config": {"path": {"shape": "round"}}}})):
            with self.subTest(text=text), self.assertRaises(pc.PlayError):
                pp.load_presets_file(text)
        with self.assertRaisesRegex(pc.PlayError, "unknown mode"):
            pp.get_preset("nope")


if __name__ == "__main__":
    unittest.main()
