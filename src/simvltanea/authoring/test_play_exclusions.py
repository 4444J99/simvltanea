"""Exclusion is absolute: by record, by content (sha256), for every malformed shape, under every policy."""
import copy
import hashlib
import random
import unittest

from simvltanea.authoring import gravity_affinity as ga
from simvltanea.authoring import play_pool as pool_rules
from simvltanea.authoring.play_config import PlayError, validate_config
from simvltanea.authoring.test_play_support import cfg, pool_of, play

POLICIES = ("allow", "exclude")


def exclusion(**changes):
    return {**validate_config({})["exclusion"], **changes}


def clean_record(index: int, sha: str | None = None) -> dict:
    """A tagged, safe, low-sensitivity record with its own id and media digest."""
    base = next(r for r in pool_of(120) if r["analysis"] and not r["needs_review"]
                and r["analysis"]["safety"]["verdict"] == "clear"
                and r["analysis"]["privacy"].get("sharing_sensitivity") == "low"
                and not r["analysis"]["people"]["minors_apparent"]
                and not any(r["analysis"]["privacy"][f] for f in pool_rules_flags()))
    record = copy.deepcopy(base)
    record["id"] = f"rec-{index:03d}"
    record["sha256"] = sha or hashlib.sha256(f"rec:{index}".encode()).hexdigest()
    return record


def pool_rules_flags():
    return ("readable_text", "license_plate", "document_or_screen", "location_identifiable")


def reasons(records, **changes):
    return pool_rules.eligible_pool(records, exclusion(**changes))[1]


class RefusedRecordTests(unittest.TestCase):
    """B1: a record the tagger refused is excluded whenever safety clearance is required."""

    SHAPES = {"refusal": {"analysis": None, "error": "refusal", "needs_review": True},
              "invalid_output": {"analysis": None, "error": "invalid_output: KeyError", "needs_review": True}}

    def test_the_tagger_refusal_and_invalid_output_shapes_are_excluded_before_the_untagged_branch(self):
        for name, shape in self.SHAPES.items():
            record = {**clean_record(1), **shape}
            for policy in POLICIES:
                with self.subTest(shape=name, policy=policy):
                    self.assertEqual(reasons([record], untagged_policy=policy), {record["id"]: "safety"})

    def test_a_record_without_any_safety_verdict_is_excluded_by_default_under_both_policies(self):
        # Deliberate tightening: require_safety_clear means a verdict must exist, not only "not bad".
        for error in (None, "not_tagged"):
            record = {**clean_record(1), "analysis": None, "needs_review": False, "error": error}
            for policy in POLICIES:
                with self.subTest(error=error, policy=policy):
                    expected = {record["id"]: "safety"} if error else {record["id"]: "untagged"}
                    self.assertEqual(reasons([record], untagged_policy=policy), expected)

    def test_untagged_policy_decides_untagged_clips_only_when_the_safety_requirement_is_off(self):
        record = {**clean_record(1), "analysis": None, "needs_review": False, "error": None}
        self.assertEqual(reasons([record], require_safety_clear=False), {})
        self.assertEqual(reasons([record], require_safety_clear=False, untagged_policy="exclude"),
                         {record["id"]: "untagged"})

    def test_untagged_policy_still_decides_unknown_rating_for_a_clip_with_a_clear_verdict(self):
        record = clean_record(1)
        del record["analysis"]["privacy"]["sharing_sensitivity"]
        self.assertEqual(reasons([record]), {})
        self.assertEqual(reasons([record], untagged_policy="exclude"), {record["id"]: "sharing_unknown"})

    def test_an_error_code_alone_marks_a_record_as_needing_review(self):
        # No needs_review key at all: the presence of an error is enough (its text is never read).
        for analysis in (None, clean_record(1)["analysis"]):
            record = {k: v for k, v in clean_record(1).items() if k != "needs_review"}
            record.update(analysis=analysis, error="refusal")
            for policy in POLICIES:
                with self.subTest(analysis=bool(analysis), policy=policy):
                    self.assertEqual(reasons([record], untagged_policy=policy), {record["id"]: "safety"})
        record = {k: v for k, v in clean_record(1).items() if k != "needs_review"}
        self.assertEqual(reasons([{**record, "error": None}]), {})
        for code in ("", 0, False, [], {}):                 # any non-null error is an error, however falsy (text never read)
            for policy in POLICIES:
                with self.subTest(error=code, policy=policy):
                    self.assertEqual(reasons([{**record, "error": code}], untagged_policy=policy),
                                     {record["id"]: "safety"})
        self.assertEqual(reasons([{**record, "error": "x"}], require_safety_clear=False), {})
        self.assertEqual(reasons([{**record, "error": 0}], require_safety_clear=False), {})

    def test_refused_records_never_reach_a_schedule(self):
        refused = [{**clean_record(i), **self.SHAPES["refusal"]} for i in range(100, 104)]
        out = play(cfg(), 3, 60, 1, records=[*pool_of(60), *refused])
        shown = {clip for _, snap in out["schedule"].timeline() for clip in snap.values()}
        self.assertFalse(shown & {r["id"] for r in refused})
        self.assertEqual({r["id"] for r in refused} & set(out["model"].profiles), set())

    def test_the_review_flag_alone_excludes_a_tagged_clear_clip(self):
        # Removing the needs_review check must make this fail (the synthetic pool never had a clear+review clip).
        for flag in (True, 1, "yes", ["x"]):
            record = {**clean_record(1), "needs_review": flag}
            self.assertEqual(reasons([record]), {record["id"]: "safety"}, flag)
        for flag in (False, None, 0, ""):
            record = {**clean_record(1), "needs_review": flag}
            self.assertEqual(reasons([record]), {}, flag)
        record = {**clean_record(1), "needs_review": True}
        self.assertEqual(reasons([record], require_safety_clear=False), {})


class MalformedSectionTests(unittest.TestCase):
    """A privacy or people section that is present but not an object is invalid, never read as absent."""

    JUNK = {"list": ["junk"], "empty list": [], "string": "no", "number": 0, "bool": False, "null": None}

    def test_a_present_section_that_is_not_an_object_is_excluded_under_both_policies_and_every_limit(self):
        for section, reason in (("privacy", "privacy_invalid"), ("people", "minors_invalid")):
            for name, value in self.JUNK.items():
                record = clean_record(1)
                record["analysis"][section] = value
                for policy in POLICIES:
                    for limit in ("low", "moderate", "high"):
                        with self.subTest(section=section, value=name, policy=policy, limit=limit):
                            self.assertEqual(reasons([record], untagged_policy=policy, max_sharing_sensitivity=limit),
                                             {record["id"]: reason})

    def test_an_absent_section_is_still_governed_by_the_untagged_policy(self):
        for section, reason in (("privacy", "privacy_unknown"), ("people", "minors_unknown")):
            record = clean_record(1)
            del record["analysis"][section]
            self.assertEqual(reasons([record], untagged_policy="exclude"), {record["id"]: reason}, section)
            if section == "people":
                self.assertEqual(reasons([record], untagged_policy="allow"), {}, section)

    def test_the_people_section_is_ignored_when_minors_are_not_screened(self):
        record = clean_record(1)
        record["analysis"]["people"] = ["junk"]
        self.assertEqual(reasons([record], exclude_minors=False), {})


class SanitisedToNothingTests(unittest.TestCase):
    """M5: a record that had an analysis but nothing usable is not an untagged clip."""

    def test_present_but_unusable_analysis_is_excluded_when_safety_is_required(self):
        for analysis in ({}, "not a dict", 5, [], [1]):
            record = {**clean_record(1), "analysis": analysis}
            for policy in POLICIES:
                with self.subTest(analysis=analysis, policy=policy):
                    self.assertEqual(reasons([record], untagged_policy=policy), {record["id"]: "safety"})

    def test_without_the_safety_requirement_it_follows_the_untagged_policy(self):
        record = {**clean_record(1), "analysis": {}}
        self.assertEqual(reasons([record], require_safety_clear=False), {})
        self.assertEqual(reasons([record], require_safety_clear=False, untagged_policy="exclude"),
                         {record["id"]: "untagged"})


class PrivacyAndSafetyTests(unittest.TestCase):
    def test_every_privacy_flag_excludes_on_its_own(self):
        # Checking only the first flag must make this fail.
        for flag in pool_rules_flags():
            record = clean_record(1)
            record["analysis"]["privacy"][flag] = True
            self.assertEqual(reasons([record]), {record["id"]: "privacy"}, flag)

    def test_only_the_configured_flags_exclude(self):
        record = clean_record(1)
        record["analysis"]["privacy"]["license_plate"] = True
        self.assertEqual(reasons([record], exclude_privacy_flags=["readable_text"]), {})
        self.assertEqual(reasons([record], exclude_privacy_flags=["license_plate"]), {record["id"]: "privacy"})
        self.assertEqual(reasons([record], exclude_privacy_flags=[]), {})

    def test_minors_and_sensitivity(self):
        record = clean_record(1)
        record["analysis"]["people"]["minors_apparent"] = True
        self.assertEqual(reasons([record]), {record["id"]: "minors"})
        self.assertEqual(reasons([record], exclude_minors=False), {})
        record = clean_record(2)
        record["analysis"]["privacy"]["sharing_sensitivity"] = "high"
        self.assertEqual(reasons([record]), {record["id"]: "sharing_sensitivity"})
        self.assertEqual(reasons([record], max_sharing_sensitivity="high"), {})

    def test_verdict_and_rating_variants_never_pass_as_permission(self):
        for verdict in ("Clear", "clear ", " clear", "CLEAR", "review", "exclude", 1, True, None, ["clear"], {"x": 1}, ""):
            record = clean_record(1)
            record["analysis"]["safety"]["verdict"] = verdict
            self.assertEqual(reasons([record]), {record["id"]: "safety"}, repr(verdict))
        for rating in ("HIGH", " high ", "\thigh\n", "высокий", "ｈｉｇｈ", 5, False, ["high"], {}, "very-private"):
            record = clean_record(2)
            record["analysis"]["privacy"]["sharing_sensitivity"] = rating
            self.assertIn(reasons([record]).get(record["id"]), {"sharing_sensitivity", "sharing_invalid"}, repr(rating))
        for flag in ("true", "false", 1):
            record = clean_record(3)
            record["analysis"]["privacy"]["readable_text"] = flag
            self.assertEqual(reasons([record]), {record["id"]: "privacy"}, repr(flag))
        for flag in (["x"], {"a": 1}):
            record = clean_record(3)
            record["analysis"]["privacy"]["readable_text"] = flag
            self.assertEqual(reasons([record]), {record["id"]: "privacy_invalid"}, repr(flag))

    def test_malformed_sections_never_crash_and_are_never_permission(self):
        for section in ("privacy", "people", "safety"):
            for junk in (None, "x", 5, [], [1]):
                record = clean_record(1)
                record["analysis"][section] = junk
                for policy in POLICIES:
                    got = reasons([record], untagged_policy=policy).get(record["id"])
                    if section == "safety":
                        self.assertEqual(got, "safety")
                    else:
                        self.assertEqual(got, "minors_invalid" if section == "people" else "privacy_invalid")


class FailClosedFlagTests(unittest.TestCase):
    """A privacy flag or the minors flag that is absent or malformed is never read as permission."""

    BAD = {"list": ["yes"], "dict": {"value": True}, "long string": "x" * 41, "null": None}

    def record_with(self, section, key, **value):
        record = clean_record(1)
        if value:
            record["analysis"][section][key] = value["value"]
        else:
            del record["analysis"][section][key]
        return record

    def test_a_malformed_flag_is_always_excluded_under_both_policies_and_every_sensitivity_limit(self):
        for flag in (*pool_rules_flags(), "minors_apparent"):
            section = "people" if flag == "minors_apparent" else "privacy"
            word = "minors" if flag == "minors_apparent" else "privacy"
            for name, bad in self.BAD.items():
                record = self.record_with(section, flag, value=bad)
                for policy in POLICIES:
                    for limit in ("low", "moderate", "high"):
                        with self.subTest(flag=flag, value=name, policy=policy, limit=limit):
                            got = reasons([record], untagged_policy=policy, max_sharing_sensitivity=limit)
                            self.assertEqual(got, {record["id"]: f"{word}_invalid"})

    def test_an_absent_flag_follows_the_untagged_policy_like_an_absent_sharing_rating(self):
        for flag in (*pool_rules_flags(), "minors_apparent"):
            section = "people" if flag == "minors_apparent" else "privacy"
            word = "minors" if flag == "minors_apparent" else "privacy"
            record = self.record_with(section, flag)
            for limit in ("low", "moderate"):
                with self.subTest(flag=flag, limit=limit):
                    self.assertEqual(reasons([record], untagged_policy="allow", max_sharing_sensitivity=limit), {})
                    self.assertEqual(reasons([record], untagged_policy="exclude", max_sharing_sensitivity=limit),
                                     {record["id"]: f"{word}_unknown"})

    def test_an_absent_privacy_section_or_absent_people_section_follows_the_policy(self):
        for section, word in (("privacy", "privacy"), ("people", "minors")):
            record = clean_record(1)
            del record["analysis"][section]
            self.assertEqual(reasons([record]), {}, section)
            self.assertEqual(reasons([record], untagged_policy="exclude"), {record["id"]: f"{word}_unknown"}, section)

    def test_flags_that_are_switched_off_are_not_demanded(self):
        record = clean_record(1)
        del record["analysis"]["privacy"]["license_plate"]
        record["analysis"]["privacy"]["readable_text"] = ["x"]
        got = reasons([record], untagged_policy="exclude", exclude_privacy_flags=["document_or_screen"])
        self.assertEqual(got, {})
        record = clean_record(2)
        del record["analysis"]["people"]["minors_apparent"]
        self.assertEqual(reasons([record], untagged_policy="exclude", exclude_minors=False), {})

    def test_present_valid_flags_behave_as_before(self):
        record = clean_record(1)
        for policy in POLICIES:
            self.assertEqual(reasons([record], untagged_policy=policy), {})
        record["analysis"]["privacy"]["license_plate"] = 0
        record["analysis"]["people"]["minors_apparent"] = False
        for policy in POLICIES:
            self.assertEqual(reasons([record], untagged_policy=policy), {})

    def test_a_malformed_sharing_rating_is_always_excluded_too(self):
        for name, bad in self.BAD.items():
            record = self.record_with("privacy", "sharing_sensitivity", value=bad) if bad is not None else None
            if record is None:
                continue
            for policy in POLICIES:
                self.assertEqual(reasons([record], untagged_policy=policy), {record["id"]: "sharing_invalid"}, name)


class ContentExclusionTests(unittest.TestCase):
    """B2: bytes follow the exclusion. Everything sharing a digest with an excluded record is excluded."""

    def excluded_variants(self):
        sha = lambda tag: hashlib.sha256(tag.encode()).hexdigest()   # noqa: E731
        out = {}
        for key in ("safety", "privacy", "minors", "sensitivity", "exclude_id", "review", "bad_duration", "untagged"):
            record = clean_record(len(out) + 1, sha(key))
            if key == "safety":
                record["analysis"]["safety"]["verdict"] = "exclude"
            elif key == "privacy":
                record["analysis"]["privacy"]["document_or_screen"] = True
            elif key == "minors":
                record["analysis"]["people"]["minors_apparent"] = True
            elif key == "sensitivity":
                record["analysis"]["privacy"]["sharing_sensitivity"] = "high"
            elif key == "review":
                record["needs_review"] = True
            elif key == "bad_duration":
                record["duration"] = 0
            elif key == "untagged":
                record["analysis"] = None
            out[key] = record
        return out

    def test_a_copy_of_an_excluded_clip_is_excluded_under_both_policies(self):
        for policy in POLICIES:
            for key, original in self.excluded_variants().items():
                copy_ = clean_record(900, original["sha256"])
                records = [original, copy_]
                changes = {"untagged_policy": policy, "exclude_ids": [original["id"]] if key == "exclude_id" else []}
                if key == "untagged":
                    changes["untagged_policy"] = "exclude"
                with self.subTest(policy=policy, reason=key):
                    keep, excluded = pool_rules.eligible_pool(records, exclusion(**changes))
                    self.assertEqual({r["sha256"] for r in keep} & {original["sha256"]}, set())
                    self.assertEqual(excluded[copy_["id"]], "excluded_media")
                    self.assertNotIn(original["id"], excluded[copy_["id"]])

    def test_the_digest_comparison_is_case_and_whitespace_insensitive_for_the_excluded_side(self):
        original = self.excluded_variants()["safety"]
        original["sha256"] = "  " + original["sha256"].upper() + " "
        twin = clean_record(901, original["sha256"].strip().lower())
        self.assertEqual(reasons([original, twin])[twin["id"]], "excluded_media")

    def test_a_schedule_never_shows_media_whose_digest_belongs_to_an_excluded_clip(self):
        bad = self.excluded_variants()
        del bad["untagged"]                  # untagged clips are allowed under the default policy
        copies = [clean_record(300 + i, r["sha256"]) for i, r in enumerate(bad.values())]
        records = [*pool_of(60), *bad.values(), *copies]
        out = play(cfg(exclusion={"exclude_ids": [bad["exclude_id"]["id"]]}), 5, 120, 2, records=records)
        banned = {r["sha256"] for r in bad.values()}
        state = out["state"]
        self.assertFalse({s["sha256"] for s in state["sources"]} & banned)
        shown = {clip for _, snap in out["schedule"].timeline() for clip in snap.values()}
        self.assertFalse({r["id"] for r in copies} & shown)
        self.assertEqual(out["report"]["excluded_counts"].get("excluded_media"), len(copies))

    def test_duplicates_among_kept_clips_keep_exactly_one(self):
        a, b, c = (clean_record(i, hashlib.sha256(b"same").hexdigest()) for i in (1, 2, 3))
        keep, excluded = pool_rules.eligible_pool([c, a, b], exclusion())
        self.assertEqual([r["id"] for r in keep], [a["id"]])
        self.assertEqual(excluded, {b["id"]: "duplicate_bytes", c["id"]: "duplicate_bytes"})

    def test_an_excluded_anchor_pulls_nothing_and_its_copy_is_excluded(self):
        anchor = self.excluded_variants()["safety"]
        copy_ = clean_record(902, anchor["sha256"])
        records = [*pool_of(60), anchor, copy_]
        out = play(cfg(relation={"anchors": [anchor["id"]], "anchor_pull": 2.0}), 4, 60, 1, records=records)
        self.assertEqual(out["report"]["ignored_anchors"], 1)
        self.assertNotIn(copy_["id"], out["model"].profiles)
        self.assertNotIn(anchor["id"], out["model"].profiles)


class ExcludeIdTests(unittest.TestCase):
    """An exclude id matches case-insensitively, a miss is counted (never listed), and bytes follow it."""

    def test_the_match_ignores_letter_case_in_both_directions(self):
        upper = {**clean_record(1), "id": "4F2A9C1E-ABCD-4000-8000-00000000BEEF"}
        lower = {**clean_record(2), "id": "aaaaaaaa-abcd-4000-8000-000000000001"}
        for typed in (upper["id"].lower(), upper["id"], upper["id"].title()):
            self.assertEqual(reasons([upper, lower], exclude_ids=[typed]), {upper["id"]: "exclude_ids"}, typed)
        self.assertEqual(reasons([upper, lower], exclude_ids=[lower["id"].upper()]), {lower["id"]: "exclude_ids"})

    def test_unmatched_ids_are_counted_with_the_near_misses_and_never_named(self):
        records = [*pool_of(60)]
        real = records[3]["id"]
        typo = real[:-1] + ("0" if real[-1] != "0" else "1")
        config = cfg("sticky", exclusion={"exclude_ids": [real.lower(), typo, "no-such-clip-anywhere-1"]})
        out = play(config, 3, 30, 1, records=records)
        self.assertEqual(out["report"]["unmatched_exclude_ids"], 2)
        self.assertEqual(out["report"]["unmatched_exclude_ids_near"], 1)
        self.assertNotIn(typo, repr(out["report"]))
        none = play(cfg("sticky", exclusion={"exclude_ids": [real]}), 3, 30, 1, records=records)["report"]
        self.assertEqual((none["unmatched_exclude_ids"], none["unmatched_exclude_ids_near"]), (0, 0))

    def test_an_id_of_a_clip_that_is_excluded_for_another_reason_still_matches(self):
        bad = {**clean_record(1), "needs_review": True}
        out = play(cfg("sticky", exclusion={"exclude_ids": [bad["id"]]}), 3, 30, 1, records=[*pool_of(60), bad])
        self.assertEqual(out["report"]["unmatched_exclude_ids"], 0)

    def test_known_ids_outside_the_pool_count_as_matched(self):
        out = play(cfg("sticky", exclusion={"exclude_ids": ["no-tag-record-clip"]}), 3, 30, 1,
                   pool=60, extra_known_ids=["No-Tag-Record-Clip"])
        self.assertEqual(out["report"]["unmatched_exclude_ids"], 0)

    def test_extra_digests_hide_a_copy_even_when_the_excluded_clip_is_not_in_the_pool(self):
        original = clean_record(1)
        twin = clean_record(2, original["sha256"])
        other = clean_record(3)
        for extra in ({original["sha256"]}, {"  " + original["sha256"].upper() + " "}):
            keep, excluded = pool_rules.eligible_pool([twin, other], exclusion(), extra_excluded_shas=extra)
            self.assertEqual([r["id"] for r in keep], [other["id"]])
            self.assertEqual(excluded, {twin["id"]: "excluded_media"})
        keep, excluded = pool_rules.eligible_pool([twin, other], exclusion(), extra_excluded_shas={"nonsense", 5, None})
        self.assertEqual(len(keep), 2)
        self.assertEqual(excluded, {})


class MalformedRecordTests(unittest.TestCase):
    def test_wrong_types_never_crash_and_are_excluded_with_a_generic_reason(self):
        good = clean_record(1)
        bad = []
        for field, value in (("sha256", 123), ("sha256", None), ("sha256", "short"), ("duration", [1]), ("duration", "x"),
                             ("duration", True), ("duration", float("nan")), ("path", 5), ("duration", 10 ** 400)):
            record = {**clean_record(len(bad) + 2), field: value}
            bad.append(record)
        keep, excluded = pool_rules.eligible_pool([good, *bad], exclusion())
        self.assertEqual([r["id"] for r in keep], [good["id"]])
        self.assertEqual(set(excluded), {r["id"] for r in bad})

    def test_a_record_that_raises_while_being_classified_is_excluded_not_fatal(self):
        class Boom(dict):
            def get(self, *args):
                raise RuntimeError("boom")
        record = {**clean_record(2), "analysis": Boom(a=1)}
        keep, excluded = pool_rules.eligible_pool([clean_record(1), record], exclusion())
        self.assertEqual(excluded, {record["id"]: "malformed_record"})
        self.assertEqual(len(keep), 1)

    def test_bad_ids_and_duplicate_ids_are_explicit_errors(self):
        for bad_id in ("../x", "a b", "", "x" * 81, "é"):
            with self.assertRaises(PlayError):
                pool_rules.eligible_pool([{**clean_record(1), "id": bad_id}], exclusion())
        with self.assertRaises(PlayError):
            pool_rules.eligible_pool([clean_record(1), clean_record(1)], exclusion())
        with self.assertRaises(PlayError):
            pool_rules.eligible_pool([5], exclusion())


class MalformedFieldFuzzTests(unittest.TestCase):
    """L5: malformed fields drop their component; they never raise."""

    JUNK = (None, 1, -1, 2.5, "x", "", [], [1, [2]], ["a", 1, None, ["b"]], {"a": 1}, {}, True, 10 ** 400,
            float("nan"), float("inf"), "#zzzzzz", [{"hex": 5, "share": "a"}, {"hex": "#fff", "share": None}])

    def test_random_malformed_records_never_raise_and_stay_in_range(self):
        rng = random.Random(5)
        analysis_keys = ("subjects", "keywords", "mood", "palette", "setting", "environment", "time_of_day",
                         "motion_level", "shot", "people", "privacy", "safety")
        feature_keys = ("luma", "saturation", "hue", "motion", "palette", "orientation")
        records = []
        for i in range(400):
            analysis = {k: rng.choice(self.JUNK) for k in rng.sample(analysis_keys, rng.randint(0, 6))}
            features = {k: rng.choice(self.JUNK) for k in rng.sample(feature_keys, rng.randint(0, 4))}
            records.append({"id": f"f-{i}", "analysis": rng.choice([analysis, None, {}, "x", 5]),
                            "features": rng.choice([features, None, [], "x"])})
        profiles = [ga.clip_profile(r) for r in records]
        model = ga.AffinityModel(profiles={p.id: p for p in profiles}, subject_idf={}, keyword_idf={},
                                 weights={name: 0.1 for name in ga.ALL_COMPONENTS})
        for a, b in zip(profiles, profiles[1:]):
            self.assertTrue(0 <= model.affinity(a.id, b.id) <= 1000)

    def test_every_documented_field_drops_alone(self):
        for key in ("subjects", "keywords", "mood", "palette"):
            for junk in (5, "x", {"a": 1}, True):
                profile = ga.clip_profile({"id": "a", "analysis": {key: junk, "setting": "indoor"}})
                self.assertEqual(profile.setting, "indoor")


if __name__ == "__main__":
    unittest.main()
