"""The play_state command: configuration by data, private-root intake, whitelisting, output safety, determinism."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simvltanea.authoring import (PRESETS, composition, config_digest, describe_parameters, descriptions,
                                  schedule_play, validate_config)
from simvltanea.authoring.test_gravity_pool import make_pool
from simvltanea.authoring.test_play_support import time_limit
from tools.media import play_guard
from tools.media import play_state as cli
from tools.media.test_play_guard import case_variant
from tools.paths import REPO_ROOT, WORK_DIR

SENTINELS = ("CAPTION-SENTINEL", "NOTE-SENTINEL", "REASON-SENTINEL", "ERROR-SENTINEL")


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def add_clip(root: Path, clip: str, record: dict) -> None:
    write(root / "analysis" / "tags" / f"{clip}.json",
          {"uuid": clip, "schema": "clip-analysis/v2", "analysis": record["analysis"], "features": record["features"],
           "needs_review": record["needs_review"], "error": record["error"], "usd": 0.0, "model": "synthetic"})
    write(root / "originals" / clip / ".done",
          {"schema": "live-photo-export/v1", "uuid": clip, "photos_id": "PHOTOS-ID-SENTINEL",
           "files": [{"name": f"{clip}.mov", "bytes": 4, "sha256": record["sha256"]}],
           "video": {"name": f"{clip}.mov", "duration": record["duration"], "width": 1080, "height": 1920}})
    (root / "originals" / clip / f"{clip}.mov").write_bytes(b"\0\0\0\0")
    if record.get("captured_at"):
        write(root / "analysis" / "index" / f"{clip}.json", {"uuid": clip, "captured_at": record["captured_at"]})


def build_root(root: Path, size: int = 60) -> list[dict]:
    """A synthetic private root: tag records, export receipts, capture-time index and tiny placeholder media."""
    pool = make_pool(size)
    for record in pool:
        add_clip(root, record["id"], record)
    return pool


def clean_record(index: int, sha: str | None = None) -> dict:
    base = next(r for r in make_pool(60) if r["analysis"] and not r["needs_review"]
                and r["analysis"]["safety"]["verdict"] == "clear"
                and r["analysis"]["privacy"].get("sharing_sensitivity") == "low"
                and not r["analysis"]["people"]["minors_apparent"]
                and not any(r["analysis"]["privacy"][f] for f in ("readable_text", "license_plate",
                                                                   "document_or_screen", "location_identifiable")))
    record = json.loads(json.dumps(base))
    record["id"] = f"x-{index:03d}"
    record["sha256"] = sha or hashlib.sha256(f"x:{index}".encode()).hexdigest()
    record.pop("_truth", None)
    return record


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main([str(a) for a in argv])
    return code, out.getvalue()


def run_all(*argv: str) -> tuple[object, str, str]:
    """(exit code or SystemExit message, stdout, stderr) of one command line."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main([str(a) for a in argv])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    size = 60

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.assertFalse(self.tmp.is_relative_to(REPO_ROOT.resolve()))
        self.root = self.tmp / "private"
        self.pool = build_root(self.root, self.size)
        self.out = self.tmp / "state.json"
        self.side = self.tmp / "state.play.json"
        self.common = ("--root", self.root, "--out", self.out, "--n", "3", "--duration", "30", "--seed", "7")

    def load(self):
        return composition.load_state(self.out)

    def used(self, *extra, base=None):
        run(*(base or self.common), "--force", *extra)
        return {s["id"] for s in self.load()["sources"]}

    def sidecar(self):
        return json.loads(self.side.read_text(encoding="utf-8"))


class OutputTests(Base):
    def test_the_command_says_once_that_its_output_is_private(self):
        """XS-8: ids and media paths are Photos-uuid shaped by design; the command must say so on every run."""
        code, stdout = run(*self.common)
        self.assertEqual(code, 0)
        lines = [line for line in stdout.splitlines() if line.startswith("private:")]
        self.assertEqual(len(lines), 1, stdout)
        for word in ("private", "never commit", "never share"):
            self.assertIn(word, lines[0])
        self.assertEqual(stdout.splitlines()[-1], lines[0])                       # last line, after the paths it refers to
        failed, out, _ = run_all(*self.common, "--n", "99")                      # a refused run wrote nothing: no notice
        self.assertNotEqual(failed, 0)
        self.assertNotIn("private:", out)

    def test_writes_a_valid_state_and_prints_exactly_the_documented_counts(self):
        code, stdout = run(*self.common)
        self.assertEqual(code, 0)
        state, side = self.load(), self.sidecar()
        self.assertEqual((state["frames"], state["fps"], len(state["loops"])), (720, 24, 3))
        self.assertEqual({e["op"] for e in state["events"]} - {"reroll", "swap"}, set())
        for source in state["sources"]:
            self.assertEqual(source["path"], f"originals/{source['id']}/{source['id']}.mov")
        digest = hashlib.sha256(composition.canonical_json(state).encode()).hexdigest()
        pool, skipped = cli.load_pool(self.root)
        result = schedule_play(pool, 3, side["config"], 30, 24)
        report = result["report"]
        expected = (
            f"pool: {len(pool)} usable records, {report['eligible']} eligible, "
            f"{sum(report['excluded_counts'].values())} excluded {report['excluded_counts']}, 0 skipped {{}}\n"
            f"config: sha256={config_digest(side['config'])} seed=7\n"
            f"state: n=3 frames=720 fps=24 sources={len(state['sources'])} events={len(state['events'])} "
            f"render_segments={report['render_segments']} sha256={digest}\n"
            f"wrote {self.out}\nwrote {self.side}\n{cli.PRIVACY_NOTICE}\n")
        self.assertEqual(stdout, expected)                                       # the full output, not a prefix
        self.assertEqual(self.out.read_text(encoding="utf-8"),
                         json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        for needle in (*SENTINELS, "PHOTOS-ID-SENTINEL", "synthetic"):
            for text in (self.out.read_text(), self.side.read_text(), stdout):
                self.assertNotIn(needle, text)
        self.assertFalse([r["id"] for r in self.pool if r["id"] in stdout])

    def test_the_sidecar_makes_the_run_reproducible(self):
        run(*self.common, "--mode", "oldest_meets_newest", "--set", "relation.strength=1.5")
        first = self.out.read_bytes()
        side = self.sidecar()
        self.assertEqual(side["schema"], "play-config/v1")
        self.assertEqual(side["config"], validate_config(side["config"]))
        self.assertEqual(side["config"]["relation"]["strength"], 1.5)
        self.assertEqual(side["config"]["path"]["shape"], "converge")
        self.assertEqual((side["seed"], side["n"], side["duration_seconds"], side["fps"]), (7, 3, 30.0, 24))
        self.assertEqual(side["config_sha256"], config_digest(side["config"]))
        pool, _ = cli.load_pool(self.root)
        eligible = sorted(schedule_play(pool, 3, side["config"], 30, 24)["model"].profiles)
        self.assertEqual(side["eligible_pool"], {"count": len(eligible),
                                                 "ids_sha256": hashlib.sha256("\n".join(eligible).encode()).hexdigest()})
        self.assertEqual(side["state_sha256"], hashlib.sha256(composition.canonical_json(self.load()).encode()).hexdigest())
        self.assertNotIn("ids", json.dumps(side["eligible_pool"]).replace("ids_sha256", ""))
        # replaying from the saved configuration alone gives the same bytes
        cfg_file = self.tmp / "saved.json"
        cfg_file.write_text(json.dumps(side["config"]))
        again = self.tmp / "again.json"
        run("--root", self.root, "--out", again, "--n", "3", "--duration", "30", "--config", cfg_file)
        self.assertEqual(again.read_bytes(), first)

    def test_the_sidecars_only_clip_ids_are_the_ones_named_in_the_configuration(self):
        ids = [r["id"] for r in self.pool]
        victim, anchor, pinned = ids[3], ids[7], ids[11]
        code, stdout, stderr = run_all(*self.common, "--exclude-id", victim, "--anchor", anchor,
                                       "--pin", f"loop-1={pinned}", "--force")
        self.assertEqual(code, 0, stderr)
        text = self.side.read_text(encoding="utf-8")
        present = {clip for clip in ids if clip in text}
        self.assertEqual(present, {victim, anchor, pinned})
        side = json.loads(text)
        self.assertEqual(side["config"]["exclusion"]["exclude_ids"], [victim])
        self.assertEqual(side["config"]["relation"]["anchors"], [anchor])
        self.assertEqual(side["config"]["path"]["pins"], [["loop-1", pinned]])
        self.assertEqual(side["eligible_pool"]["count"] > 0 and sorted(side["eligible_pool"]), ["count", "ids_sha256"])
        for forbidden in ("CAPTION-SENTINEL", "PHOTOS-ID-SENTINEL", ".mov"):                 # no captions, no file names
            self.assertNotIn(forbidden, text)
        self.assertNotIn(victim, stdout + stderr)                                           # and the console stays id-free
        run(*self.common, "--force")
        plain = self.side.read_text(encoding="utf-8")
        self.assertEqual({clip for clip in ids if clip in plain}, set())                   # no ids at all without any config id

    def test_identical_inputs_give_identical_bytes_across_processes(self):
        run(*self.common)
        first = self.out.read_bytes()
        run(*self.common, "--force")
        self.assertEqual(self.out.read_bytes(), first)
        run(*self.common, "--force", "--seed", "8")
        self.assertNotEqual(self.out.read_bytes(), first)
        digests = set()
        for hash_seed in ("0", "12345"):
            other = self.tmp / f"child-{hash_seed}.json"
            env = dict(os.environ, PYTHONHASHSEED=hash_seed)
            args = list(self.common)
            args[args.index("--out") + 1] = other
            done = subprocess.run([sys.executable, "-m", "tools.media.play_state", *map(str, args)],
                                  capture_output=True, text=True, env=env, cwd=REPO_ROOT)
            self.assertEqual(done.returncode, 0, done.stderr)
            digests.add(hashlib.sha256(other.read_bytes()).hexdigest())
        self.assertEqual(digests, {hashlib.sha256(first).hexdigest()})

    def test_every_built_in_mode_runs_through_the_command(self):
        for name in sorted(PRESETS):
            with self.subTest(mode=name):
                code, _ = run(*self.common, "--force", "--mode", name, "--duration", "20")
                self.assertEqual(code, 0)
                composition.validate_state(self.load())
                self.assertEqual(self.sidecar()["config"], validate_config(PRESETS[name], PRESETS[name]) | {"seed": 7})


class ConfigurationTests(Base):
    def test_list_modes_and_describe_are_complete(self):
        code, text = run("--list-modes")
        self.assertEqual(code, 0)
        self.assertEqual(text, "".join(f"{n}: {d}\n" for n, d in sorted(descriptions().items())))
        _, as_json = run("--list-modes", "--json")
        self.assertEqual(json.loads(as_json), descriptions())
        _, described = run("--describe")
        for entry in describe_parameters():
            self.assertIn(entry["path"], described)
            self.assertIn(entry["description"], described)
        _, machine = run("--describe", "--json")
        self.assertEqual(json.loads(machine), describe_parameters())

    def test_a_presets_file_adds_and_overrides_modes_by_name(self):
        presets = self.tmp / "mine.json"
        presets.write_text(json.dumps({"mine": {"description": "d", "config": {"relation": {"strength": -1.0}}},
                                       "sticky": {"description": "x", "config": {"relation": {"strength": 0.5}}}}))
        _, listing = run("--list-modes", "--presets-file", presets)
        self.assertIn("mine: d\n", listing)
        run(*self.common, "--mode", "mine", "--presets-file", presets)
        self.assertEqual(self.sidecar()["config"]["relation"]["strength"], -1.0)
        run(*self.common, "--force", "--presets-file", presets)                      # default mode, overridden
        self.assertEqual(self.sidecar()["config"]["relation"]["strength"], 0.5)
        with self.assertRaises(SystemExit):
            run(*self.common, "--mode", "mine")                                       # not known without the file
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"x": {"config": {"relation": {"strength": 99}}}}))
        with self.assertRaises(SystemExit):
            run(*self.common, "--presets-file", bad)

    def test_precedence_is_mode_then_config_then_set_then_shortcuts(self):
        cfg_file = self.tmp / "c.json"
        cfg_file.write_text(json.dumps({"relation": {"strength": -2.0, "temperature": 2.0}, "timing": {"cooldown": 10}}))
        run(*self.common, "--mode", "magnetic", "--config", cfg_file, "--set", "relation.temperature=3",
            "--set", "relation.weights.color=-0.5", "--set", "seed=\"from-set\"")
        config = self.sidecar()["config"]
        self.assertEqual((config["relation"]["strength"], config["relation"]["temperature"], config["timing"]["cooldown"],
                          config["relation"]["weights"]["color"]), (-2.0, 3.0, 10.0, -0.5))
        self.assertEqual(config["seed"], 7)                                           # --seed beats everything
        self.assertEqual(config["timing"]["recency"], PRESETS["magnetic"]["timing"]["recency"])

    def test_bad_configuration_fails_with_a_message_and_writes_nothing(self):
        for extra in (("--set", "relation.strength=9"), ("--set", "nope"), ("--set", "path.shape=round"),
                      ("--mode", "no-such-mode"), ("--set", "exclusion.exclude_ids=\"clip-001\""),
                      ("--config", self.tmp / "missing.json")):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as raised:
                run(*self.common, *extra)
            self.assertFalse(self.out.exists())
            self.assertFalse(self.side.exists())
            self.assertNotIn("Traceback", str(raised.exception))
        for text in ("{", "[]", "3"):
            cfg_file = self.tmp / "broken.json"
            cfg_file.write_text(text)
            with self.assertRaises(SystemExit):
                run(*self.common, "--config", cfg_file)

    def test_shortcut_flags_extend_the_lists_and_the_anchor_rule_is_recorded(self):
        victim = sorted(self.used())[0]
        run(*self.common, "--force", "--exclude-id", victim, "--pin", f"loop-1={sorted(self.used())[1]}")
        config = self.sidecar()["config"]
        self.assertEqual(config["exclusion"]["exclude_ids"], [victim])
        self.assertEqual(config["path"]["pins"][0][0], "loop-1")
        with self.assertRaises(SystemExit):
            run(*self.common, "--force", "--pin", "loop-1=../../etc")

    def test_anchor_adds_a_pull_of_one_unless_set_and_actually_changes_the_run(self):
        anchor = sorted(self.used())[2]
        run(*self.common, "--force")
        plain = self.out.read_bytes()
        run(*self.common, "--force", "--anchor", anchor)
        config = self.sidecar()["config"]
        self.assertEqual((config["relation"]["anchors"], config["relation"]["anchor_pull"]), ([anchor], 1.0))
        self.assertNotEqual(self.out.read_bytes(), plain)
        # an explicit zero pull wins: the anchor is then inert and the state equals the plain run
        run(*self.common, "--force", "--anchor", anchor, "--set", "relation.anchor_pull=0")
        self.assertEqual(self.sidecar()["config"]["relation"]["anchor_pull"], 0.0)
        self.assertEqual(self.out.read_bytes(), plain)
        run(*self.common, "--force", "--anchor", anchor, "--set", "relation.anchor_pull=2")
        self.assertEqual(self.sidecar()["config"]["relation"]["anchor_pull"], 2.0)

    def test_chronological_modes_use_the_capture_time_index(self):
        run(*self.common, "--force", "--mode", "chronological", "--duration", "20")
        self.assertEqual(composition.load_state(self.out)["fps"], 24)
        for p in (self.root / "analysis" / "index").glob("*.json"):
            p.unlink()
        with self.assertRaises(SystemExit) as raised:
            run(*self.common, "--force", "--mode", "chronological")
        self.assertIn("captured_at", str(raised.exception))

    def test_seed_forms(self):
        self.assertEqual((cli.seed_value("12"), cli.seed_value("-3"), cli.seed_value("abc"), cli.seed_value("1.5")),
                         (12, -3, "abc", "1.5"))

    def test_a_state_regenerated_from_its_own_sidecar_is_byte_identical(self):
        """SSP-7: --config accepts the play-config/v1 record (its inner config, n, duration and fps)."""
        base = ("--root", self.root, "--out", self.out)
        code, _, stderr = run_all(*base, "--mode", "magnetic", "--n", "4", "--duration", "45", "--fps", "12",
                                  "--seed", "007", "--set", "relation.strength=-1", "--set", "timing.hold_min=5")
        self.assertEqual(code, 0, stderr)
        state, record = self.out.read_bytes(), self.side.read_bytes()
        self.assertEqual(json.loads(record)["schema"], "play-config/v1")
        self.out.unlink()
        code, stdout, stderr = run_all(*base, "--config", self.side, "--force")      # nothing else: not mode, n, seed
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.out.read_bytes(), state)
        self.assertEqual(self.side.read_bytes(), record)                              # the record reproduces itself too
        elsewhere = self.tmp / "again.json"
        copy = self.tmp / "copy.play.json"
        copy.write_bytes(record)
        code, _, stderr = run_all("--root", self.root, "--out", elsewhere, "--config", copy)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(elsewhere.read_bytes(), state)
        self.assertEqual(json.loads(elsewhere.with_name("again.play.json").read_bytes())["state_sha256"],
                         json.loads(record)["state_sha256"])

    def test_explicit_flags_beat_the_record_and_a_bad_record_is_refused(self):
        base = ("--root", self.root, "--out", self.out)
        run(*base, "--n", "4", "--duration", "30", "--seed", "3")
        record = self.sidecar()
        code, stdout, _ = run_all(*base, "--config", self.side, "--n", "3", "--force")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.load()["loops"]), 3)                                # --n beat the record's 4
        for label, bad in (("another schema", {**record, "schema": "play-config/v2"}),
                           ("no config", {k: v for k, v in record.items() if k != "config"}),
                           ("a config that is not an object", {**record, "config": [1]}),
                           ("an invalid config", {**record, "config": {**record["config"], "seed": "ab\udcff"}})):
            path = self.tmp / "bad.play.json"
            path.write_text(json.dumps(bad))
            before = self.out.read_bytes()
            code, _, _ = run_all(*base, "--config", path, "--force")
            with self.subTest(label):
                self.assertIsInstance(code, str)
                self.assertTrue(code.startswith("play:"), code)
                self.assertEqual(self.out.read_bytes(), before)                        # nothing was rewritten
        plain = self.tmp / "plain.json"                                                # a plain config still works
        plain.write_text(json.dumps({"relation": {"strength": 1.0}}))
        self.assertEqual(run_all(*base, "--config", plain, "--force")[0], 0)

    def test_a_changed_pool_is_reported_when_replaying_a_record(self):
        base = ("--root", self.root, "--out", self.out)
        run(*base, "--n", "3", "--duration", "30", "--seed", "3")
        code, _, stderr = run_all(*base, "--config", self.side, "--force")
        self.assertEqual((code, stderr), (0, ""))
        shown = self.load()["sources"][0]["id"]                                         # an eligible clip, then gone
        (self.root / "analysis" / "tags" / f"{shown}.json").unlink()
        code, _, stderr = run_all(*base, "--config", self.side, "--force")
        self.assertEqual(code, 0)
        self.assertIn("warning: the eligible pool differs from the one in the record", stderr)

    def test_seed_text_has_one_rule_on_every_path(self):
        """DP-6: --seed, --set seed= and a config file give the same seed for the same text."""
        config = self.tmp / "seed.json"
        for text, expected in (("007", "007"), ("-0", "-0"), ("7", 7), ("-7", -7), ("0", 0), ("+7", "+7"), ("1.5", "1.5"),
                               ("abc", "abc")):
            digests = {}
            for how, argv in (("--seed", ("--seed", text)), ("--set", ("--set", f"seed={text}")),
                              ("config", ("--config", config))):
                config.write_text(json.dumps({"seed": text}))
                base = self.common[:-2]
                code, stdout, stderr = run_all(*base, *argv, "--force")
                with self.subTest(text=text, path=how):
                    self.assertEqual(code, 0, stderr)
                    self.assertEqual(self.sidecar()["seed"], expected)
                    self.assertIs(type(self.sidecar()["seed"]), type(expected))
                    digests[how] = hashlib.sha256(self.out.read_bytes()).hexdigest()
            self.assertEqual(len(set(digests.values())), 1, (text, digests))
        states = {}
        for text in ("7", "007", "-0", "0", "-7"):
            run(*self.common[:-2], "--seed", text, "--force")
            states[text] = self.out.read_bytes()
        self.assertEqual(len({v for v in states.values()}), 5)                     # five different seeds, five states
        config.write_text(json.dumps({"seed": 7}))                                 # a JSON number is the same as "7"
        run(*self.common[:-2], "--config", config, "--force")
        self.assertEqual(self.out.read_bytes(), states["7"])

    def test_a_seed_that_cannot_be_encoded_is_a_clean_refusal_not_a_traceback(self):
        """DP-2: an invalid byte in argv decodes to a lone surrogate."""
        for argv in (("--seed", "ab\udcffcd"), ("--set", "seed=ab\udcffcd")):
            code, stdout, stderr = run_all(*self.common[:-2], *argv, "--force")
            with self.subTest(argv=argv[0]):
                self.assertIsInstance(code, str)
                self.assertIn("seed", code)
                self.assertIn("UTF-8", code)
                self.assertNotIn("udcff", code)
                self.assertEqual(stdout, "")
        config = self.tmp / "bad-seed.json"
        config.write_text('{"seed": "\\ud800"}')
        code, _, _ = run_all(*self.common[:-2], "--config", config, "--force")
        self.assertIn("UTF-8", str(code))

    def test_seeds_beyond_the_javascript_safe_range_stay_strings(self):
        safe = 2 ** 53 - 1
        from simvltanea.authoring import play_config, play_pool
        self.assertEqual(cli.MAX_SAFE_SEED, safe)                                  # the command's copies of two
        self.assertEqual(cli.MAX_SAFE_SEED, play_config.MAX_SAFE_SEED)             # engine constants cannot drift
        self.assertEqual(cli.MAX_FLAG_TEXT, play_pool.MAX_FLAG_TEXT)
        self.assertEqual((cli.seed_value(str(safe)), cli.seed_value(str(-safe))), (safe, -safe))
        for text in (str(safe + 1), str(-safe - 1), "123456789012345678", "999999999999999999"):
            self.assertEqual(cli.seed_value(text), text)
        code, _, stderr = run_all(*self.common[:-2], "--seed", "123456789012345678", "--force")
        self.assertEqual(code, 0, stderr)
        side = self.sidecar()
        self.assertEqual(side["seed"], "123456789012345678")                      # a string in both records
        self.assertIsInstance(json.loads(self.out.read_text())["seed"], str)


class ExclusionTests(Base):
    def flagged(self):
        return {r["id"] for r in self.pool if r["analysis"] and (r["needs_review"]
                or r["analysis"]["safety"]["verdict"] != "clear" or r["analysis"]["people"]["minors_apparent"]
                or r["analysis"]["privacy"]["readable_text"])}

    def test_exclusions_and_sharing_sensitivity_levels(self):
        high = {r["id"] for r in self.pool if r["analysis"] and r["analysis"]["privacy"].get("sharing_sensitivity") == "high"}
        self.assertTrue(high - self.flagged())
        for seed in ("1", "2", "3"):
            sources = self.used("--seed", seed, "--duration", "120", "--n", "7")
            self.assertFalse(sources & (high | self.flagged()))
        sources = self.used("--set", "exclusion.max_sharing_sensitivity=\"high\"", "--duration", "300", "--n", "7")
        self.assertTrue(sources & high)
        self.assertFalse(sources & self.flagged())

    def test_untagged_policy_exclude_drops_untagged_and_unknown_sensitivity(self):
        untagged = {r["id"] for r in self.pool if not r["analysis"]}
        unknown = {r["id"] for r in self.pool if r["analysis"] and "sharing_sensitivity" not in r["analysis"]["privacy"]}
        self.assertTrue(untagged and unknown)
        for seed in ("1", "2"):
            sources = self.used("--set", "exclusion.untagged_policy=\"exclude\"", "--seed", seed, "--duration", "120", "--n", "7")
            self.assertFalse(sources & (untagged | unknown))

    def test_the_tagger_refusal_and_invalid_output_records_are_never_shown(self):
        # the shapes tag_clips writes: analysis null, an error text, needs_review true
        refused = {}
        for i, error in enumerate(("refusal", "invalid_output: KeyError", "ERROR-SENTINEL free text")):
            record = {**clean_record(100 + i), "analysis": None, "needs_review": True, "error": error}
            add_clip(self.root, record["id"], record)
            refused[record["id"]] = record
        pool, skipped = cli.load_pool(self.root)
        self.assertEqual(sum(skipped.values()), 0)
        self.assertNotIn("ERROR-SENTINEL", json.dumps(pool))                          # free text never enters the pool
        for seed in ("1", "2", "3"):
            for policy in ("allow", "exclude"):
                sources = self.used("--seed", seed, "--duration", "90", "--n", "7",
                                    "--set", f"exclusion.untagged_policy=\"{policy}\"")
                self.assertFalse(sources & set(refused), (seed, policy))
        code, stdout = run(*self.common, "--force")
        self.assertIn("'safety'", stdout)
        self.assertNotIn("ERROR-SENTINEL", stdout + self.out.read_text() + self.side.read_text())

    def test_review_flag_on_a_clear_record_is_honoured_by_the_command(self):
        # A command that hard-codes needs_review=False would show this clip.
        record = {**clean_record(200), "needs_review": True}
        add_clip(self.root, record["id"], record)
        pool, _ = cli.load_pool(self.root)
        self.assertTrue(next(r for r in pool if r["id"] == record["id"])["needs_review"])
        for seed in range(1, 5):
            self.assertNotIn(record["id"], self.used("--seed", str(seed), "--duration", "90", "--n", "7"))

    def test_copies_of_excluded_media_are_excluded_by_sha256_for_both_policies(self):
        banned = hashlib.sha256(b"banned-bytes").hexdigest()
        original = clean_record(300, banned)
        original["analysis"]["privacy"]["sharing_sensitivity"] = "high"
        copy_ = clean_record(301, banned)
        other = clean_record(302, hashlib.sha256(b"fine").hexdigest())
        for record in (original, copy_, other):
            add_clip(self.root, record["id"], record)
        for policy in ("allow", "exclude"):
            for seed in range(1, 4):
                run(*self.common, "--force", "--seed", str(seed), "--n", "7", "--duration", "120",
                    "--set", f"exclusion.untagged_policy=\"{policy}\"")
                state = self.load()
                self.assertNotIn(banned, {s["sha256"] for s in state["sources"]})
                self.assertFalse({original["id"], copy_["id"]} & {s["id"] for s in state["sources"]})
        pool, _ = cli.load_pool(self.root)                                              # sanitised records, as scheduled
        self.assertEqual(schedule_play(pool, 3, validate_config({}), 20, 24, 1)["excluded"][copy_["id"]], "excluded_media")

    def test_a_tagged_record_that_sanitises_to_nothing_is_not_treated_as_untagged(self):
        junk = {}
        for i, analysis in enumerate(({"safety": "clear", "extra": 1}, "just a string", {"caption": "ERROR-SENTINEL"}, {})):
            record = {**clean_record(400 + i), "analysis": analysis}
            add_clip(self.root, record["id"], record)
            junk[record["id"]] = analysis
        pool, _ = cli.load_pool(self.root)
        self.assertTrue(all(r["analysis"] == {} or isinstance(r["analysis"], dict) for r in pool if r["id"] in junk))
        for r in pool:
            if r["id"] in junk:
                self.assertIsNotNone(r["analysis"])
        for seed in range(1, 4):
            self.assertFalse(self.used("--seed", str(seed), "--duration", "90", "--n", "7") & set(junk))

    def excluded_reason(self, record, **exclusion):
        """Add one record to the private root, read it back through the command's intake and ask the engine."""
        add_clip(self.root, record["id"], record)
        pool, skipped = cli.load_pool(self.root)
        self.assertEqual(sum(skipped.values()), 0)
        cfg = validate_config({"exclusion": exclusion})
        return schedule_play(pool, 3, cfg, 20, 24, 1)["excluded"].get(record["id"])

    def test_a_malformed_or_absent_flag_fails_closed_through_the_command_intake(self):
        junk = {"list": ["yes"], "dict": {"value": True}, "long": "x" * 41, "null": None}
        for name, value in junk.items():
            for key, section, word in (("license_plate", "privacy", "privacy"), ("minors_apparent", "people", "minors"),
                                       ("sharing_sensitivity", "privacy", "sharing")):
                if value is None and key == "sharing_sensitivity":
                    continue                                    # a null rating is "unknown" (schema v1), as before
                record = clean_record(500)
                record["analysis"][section][key] = value
                for policy in ("allow", "exclude"):
                    for limit in ("low", "moderate"):
                        with self.subTest(value=name, flag=key, policy=policy, limit=limit):
                            got = self.excluded_reason(record, untagged_policy=policy, max_sharing_sensitivity=limit)
                            self.assertEqual(got, f"{word}_invalid")
        for key, section, word in (("readable_text", "privacy", "privacy"), ("minors_apparent", "people", "minors")):
            record = clean_record(501)
            del record["analysis"][section][key]
            self.assertIsNone(self.excluded_reason(record, untagged_policy="allow"), key)
            self.assertEqual(self.excluded_reason(record, untagged_policy="exclude", max_sharing_sensitivity="low"),
                             f"{word}_unknown", key)

    def test_a_section_that_is_present_but_not_an_object_fails_closed_through_the_command_intake(self):
        for section, word in (("privacy", "privacy"), ("people", "minors")):
            for name, value in {"list": ["junk"], "string": "no", "number": 0, "null": None}.items():
                record = clean_record(510)
                record["analysis"][section] = value
                for policy in ("allow", "exclude"):
                    for limit in ("low", "moderate"):
                        with self.subTest(section=section, value=name, policy=policy, limit=limit):
                            got = self.excluded_reason(record, untagged_policy=policy, max_sharing_sensitivity=limit)
                            self.assertEqual(got, f"{word}_invalid")
        got = cli.sanitize_analysis({"privacy": ["x"], "people": 3})
        self.assertIn("privacy", got)
        self.assertIn("people", got)
        self.assertNotIn("privacy", cli.sanitize_analysis({"people": {}}))              # a missing section stays missing

    def test_sanitise_keeps_a_malformed_flag_as_an_explicit_marker_and_valid_values_as_they_are(self):
        raw = {"people": {"count": 2, "minors_apparent": ["x"], "faces_visible": 1},
               "privacy": {"license_plate": {"a": 1}, "readable_text": "x" * 41, "document_or_screen": False,
                           "location_identifiable": "no", "sharing_sensitivity": ["high"]}}
        got = cli.sanitize_analysis(raw)
        for section, key in (("people", "minors_apparent"), ("privacy", "license_plate"), ("privacy", "readable_text")):
            self.assertIn(key, got[section])                                    # present, never dropped
            self.assertEqual(got[section][key], cli.INVALID_FLAG)
        self.assertEqual(got["privacy"]["sharing_sensitivity"], cli.INVALID_RATING)
        self.assertNotIn("sharing_sensitivity", cli.sanitize_analysis({"privacy": {"sharing_sensitivity": None}})["privacy"])
        self.assertIs(got["privacy"]["document_or_screen"], False)
        self.assertEqual(got["privacy"]["location_identifiable"], "no")
        self.assertEqual(got["people"]["count"], 2)
        self.assertNotIn("license_plate", cli.sanitize_analysis({"privacy": {"readable_text": True}})["privacy"])

    def test_an_error_code_without_the_review_flag_keeps_a_clip_out_through_the_command(self):
        record = {**clean_record(502), "needs_review": False, "error": "refusal"}
        for policy in ("allow", "exclude"):
            self.assertEqual(self.excluded_reason(record, untagged_policy=policy), "safety")
        pool, _ = cli.load_pool(self.root)
        entry = next(r for r in pool if r["id"] == record["id"])
        self.assertTrue(entry["needs_review"])
        self.assertNotIn("refusal", json.dumps(pool))

    def test_a_falsy_but_non_null_error_code_still_keeps_a_clip_out_through_the_command(self):
        for code in ("", 0, False, []):
            record = {**clean_record(504), "needs_review": False, "error": code}
            for policy in ("allow", "exclude"):
                with self.subTest(error=code, policy=policy):
                    self.assertEqual(self.excluded_reason(record, untagged_policy=policy), "safety")
            pool, _ = cli.load_pool(self.root)
            self.assertTrue(next(r for r in pool if r["id"] == record["id"])["needs_review"])
        record = {**clean_record(504), "needs_review": False, "error": None}
        self.assertIsNone(self.excluded_reason(record))
        self.assertFalse(next(r for r in cli.load_pool(self.root)[0] if r["id"] == record["id"])["needs_review"])

    def test_a_clip_that_was_never_tagged_is_excluded_under_the_default_settings(self):
        record = {**clean_record(503), "analysis": None, "needs_review": False, "error": None}
        self.assertEqual(self.excluded_reason(record), "untagged")                        # the default untagged_policy is allow
        self.assertEqual(self.excluded_reason(record, untagged_policy="exclude"), "untagged")
        self.assertIsNone(self.excluded_reason(record, require_safety_clear=False))
        untagged = {r["id"] for r in self.pool if not r["analysis"]}
        self.assertTrue(untagged)
        for seed in ("1", "2", "3"):
            self.assertFalse(self.used("--seed", seed, "--duration", "120", "--n", "7") & (untagged | {record["id"]}))

    def test_the_report_carries_counts_by_reason_and_no_ids(self):
        _, stdout = run(*self.common, "--set", "exclusion.exclude_ids=[\"x-000\"]", "--exclude-id", self.pool[0]["id"])
        self.assertNotIn(self.pool[0]["id"], stdout)
        self.assertRegex(stdout, r"excluded \{('[a-z_]+': \d+(, )?)+\}")


class ExcludeIdCommandTests(Base):
    """An exclude id that matches nothing must be loud: an error for --exclude-id, a warning from a config file."""

    def upper_clip(self):
        record = {**clean_record(600), "id": "UPPER-CLIP-600"}
        add_clip(self.root, record["id"], record)
        return record

    def test_an_id_typed_in_another_letter_case_still_excludes(self):
        record = self.upper_clip()
        code, stdout, stderr = run_all(*self.common, "--force", "--exclude-id", record["id"].lower())
        self.assertEqual(code, 0, stderr)
        self.assertIn("'exclude_ids': 1", stdout)
        self.assertNotIn("match no clip", stderr)
        self.assertNotIn(record["id"].lower(), stdout + stderr)

    def test_an_unmatched_id_from_a_config_file_warns_on_stderr_and_still_runs(self):
        config = self.tmp / "exclude.json"
        config.write_text(json.dumps({"exclusion": {"exclude_ids": ["no-such-clip-777", self.pool[0]["id"]]}}))
        code, stdout, stderr = run_all(*self.common, "--force", "--config", config)
        self.assertEqual(code, 0, stderr)
        self.assertIn("warning: 1 exclude id(s) match no clip in the pool; those are NOT excluded", stderr)
        self.assertNotIn("no-such-clip-777", stdout + stderr)
        self.assertTrue(self.out.exists())

    def test_the_warning_counts_near_misses_without_naming_them(self):
        config = self.tmp / "exclude.json"
        typo = self.pool[0]["id"][:-1] + "Z"
        config.write_text(json.dumps({"exclusion": {"exclude_ids": [typo, "no-such-clip-777"]}}))
        code, _, stderr = run_all(*self.common, "--force", "--config", config)
        self.assertEqual(code, 0, stderr)
        self.assertIn("2 exclude id(s) match no clip in the pool", stderr)
        self.assertIn("1 of them differ from a pool id by one character", stderr)
        self.assertNotIn(typo, stderr)

    def test_an_unmatched_id_given_with_the_flag_is_an_error_that_writes_nothing(self):
        for ids in (("no-such-clip-777",), ("no-such-clip-777", "also-missing-1")):
            args = [x for i in ids for x in ("--exclude-id", i)]
            code, stdout, stderr = run_all(*self.common, *args)
            self.assertNotEqual(code, 0)
            self.assertIn(f"{len(ids)} --exclude-id value(s) match no clip in the pool", str(code))
            self.assertNotIn("no-such-clip-777", f"{code}{stdout}{stderr}")
            self.assertFalse(self.out.exists() or self.side.exists())

    def test_the_flag_still_accepts_a_matching_id_next_to_a_stale_config_id(self):
        config = self.tmp / "exclude.json"
        config.write_text(json.dumps({"exclusion": {"exclude_ids": ["stale-config-id"]}}))
        code, _, stderr = run_all(*self.common, "--force", "--config", config, "--exclude-id", self.pool[0]["id"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("warning: 1 exclude id(s)", stderr)

    def test_an_excluded_clip_without_a_tag_record_still_hides_its_byte_identical_copy(self):
        banned = hashlib.sha256(b"banned-untagged-bytes").hexdigest()
        original, copy_ = clean_record(610, banned), clean_record(611, banned)
        for record in (original, copy_):
            add_clip(self.root, record["id"], record)
        (self.root / "analysis" / "tags" / f"{original['id']}.json").unlink()
        code, stdout, stderr = run_all(*self.common, "--force", "--n", "3", "--exclude-id", original["id"])
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("match no clip", stderr)                      # it has a receipt: it exists
        self.assertIn("'excluded_media': 1", stdout)
        for seed in ("1", "2", "3"):
            self.assertFalse(self.used("--seed", seed, "--n", "7", "--duration", "120",
                                       "--exclude-id", original["id"]) & {original["id"], copy_["id"]})
        pool, _ = cli.load_pool(self.root)
        self.assertEqual(schedule_play(pool, 3, validate_config({}), 20, 24, 1,
                                       extra_excluded_shas={banned})["excluded"][copy_["id"]], "excluded_media")


class LinkedExcludedClipTests(Base):
    """Reading an excluded clip's receipt through a link can only add a digest to the hidden set (it fails closed);
    showing media through a link stays refused."""

    def linked_original(self, tagged: bool):
        """Clip A (symlinked directory) and B (a byte-identical copy under another id). Returns (a, b)."""
        sha = hashlib.sha256(b"linked-excluded-bytes").hexdigest()
        a, b = clean_record(620, sha), clean_record(621, sha)
        for record in (a, b):
            add_clip(self.root, record["id"], record)
        if not tagged:
            (self.root / "analysis" / "tags" / f"{a['id']}.json").unlink()
        elsewhere = self.tmp / "moved-away"
        elsewhere.mkdir()
        (self.root / "originals" / a["id"]).rename(elsewhere / a["id"])
        (self.root / "originals" / a["id"]).symlink_to(elsewhere / a["id"], target_is_directory=True)
        return a, b

    def test_the_copy_of_a_clip_behind_a_symlinked_directory_stays_hidden_and_the_id_is_known(self):
        for tagged in (True, False):
            with self.subTest(tagged=tagged):
                self.setUp()
                a, b = self.linked_original(tagged)
                config = self.tmp / "exclude.json"
                config.write_text(json.dumps({"exclusion": {"exclude_ids": [a["id"]]}}))
                seen = set()
                for seed in ("1", "2", "3", "4", "5"):
                    code, stdout, stderr = run_all(*self.common, "--force", "--n", "7", "--duration", "120",
                                                   "--seed", seed)
                    self.assertEqual(code, 0, stderr)
                    seen |= {s["id"] for s in self.load()["sources"]}
                self.assertIn(b["id"], seen)                              # control: without the exclusion the copy is shown
                for seed in ("1", "2", "3", "4", "5"):
                    code, stdout, stderr = run_all(*self.common, "--force", "--n", "7", "--duration", "120",
                                                   "--seed", seed, "--config", config)
                    self.assertEqual(code, 0, stderr)
                    self.assertNotIn("match no clip", stderr)
                    self.assertNotIn(a["id"], stdout + stderr)
                    self.assertFalse({s["id"] for s in self.load()["sources"]} & {a["id"], b["id"]}, seed)
                code, stdout, stderr = run_all(*self.common, "--force", "--exclude-id", a["id"])
                self.assertEqual(code, 0, f"{code}{stderr}")                 # the clip exists: not a "match no clip" error

    def test_the_excluded_clip_itself_is_still_never_shown_through_the_link(self):
        a, _ = self.linked_original(True)
        pool, skipped = cli.load_pool(self.root)
        self.assertNotIn(a["id"], {r["id"] for r in pool})
        self.assertEqual(skipped["no_usable_export_receipt"], 1)

    def test_excluded_receipts_reads_through_a_linked_directory_and_a_linked_originals_directory(self):
        a, _ = self.linked_original(True)
        digests, known = cli.excluded_receipts(self.root, [a["id"]])
        self.assertEqual(digests, {hashlib.sha256(b"linked-excluded-bytes").hexdigest()})
        self.assertEqual(known, {a["id"].casefold()})
        moved = self.tmp / "originals-moved"
        (self.root / "originals").rename(moved)
        (self.root / "originals").symlink_to(moved, target_is_directory=True)
        self.assertEqual(cli.excluded_receipts(self.root, [a["id"]]), (digests, known))


class UnsafeClipWithUnusableReceiptTests(Base):
    """An UNSAFE tagged clip whose receipt fails the display checks is skipped, but its bytes must still stay
    hidden wherever else they were imported (exclusion follows content). Only a clip that would itself be excluded
    contributes its digests: a clean clip with a broken receipt must not hide its clean copy."""

    BYTES = b"unsafe-unusable-bytes"

    def pair(self, a_analysis=None):
        sha = hashlib.sha256(self.BYTES).hexdigest()
        a, b = clean_record(640, sha), clean_record(641, sha)
        if a_analysis is not None:
            a = {**a, "analysis": a_analysis(a["analysis"])}
        for record in (a, b):
            add_clip(self.root, record["id"], record)
        return a, b

    def shown_over_seeds(self, *extra):
        shown = set()
        for seed in ("1", "2", "3"):
            code, _, stderr = run_all(*self.common, "--force", "--seed", seed, "--n", "7", "--duration", "120", *extra)
            self.assertEqual(code, 0, stderr)
            shown |= {s["id"] for s in self.load()["sources"]}
        return shown

    def break_media(self, a):
        (self.root / "originals" / a["id"] / f"{a['id']}.mov").unlink()

    def test_the_clean_copy_of_an_unsafe_clip_with_an_unusable_receipt_stays_hidden(self):
        unsafe = lambda analysis: {**analysis, "safety": {**analysis["safety"], "verdict": "flagged"}}
        for label, make_unsafe in (("verdict flagged", unsafe),
                                   ("minors apparent", lambda an: {**an, "people": {**an["people"], "minors_apparent": True}}),
                                   ("licence plate", lambda an: {**an, "privacy": {**an["privacy"], "license_plate": True}})):
            with self.subTest(label):
                self.setUp()
                a, b = self.pair(make_unsafe)
                control = self.shown_over_seeds()                    # control: a usable receipt already hides the copy
                self.assertFalse(control & {a["id"], b["id"]}, "control: the copy of an unsafe clip is hidden")
                self.setUp()
                a, b = self.pair(make_unsafe)
                self.break_media(a)
                shown = self.shown_over_seeds()
                self.assertNotIn(a["id"], shown)
                self.assertNotIn(b["id"], shown, "byte-identical copy of an unsafe clip leaked")

    def test_a_clean_clip_with_an_unusable_receipt_does_not_hide_its_clean_copy(self):
        a, b = self.pair()
        self.break_media(a)
        shown = self.shown_over_seeds()
        self.assertNotIn(a["id"], shown)                            # cannot be shown: its receipt is unusable
        self.assertIn(b["id"], shown)                               # but nothing says its bytes are unsafe

    def test_the_digest_collection_never_raises_on_odd_records(self):
        """A record with nothing usable must be handled on its own: counted, never fatal."""
        a, b = self.pair(lambda an: {**an, "safety": "not-a-dict"})
        self.break_media(a)
        (self.root / "originals" / a["id"] / ".done").write_text("not json", encoding="utf-8")
        shown = self.shown_over_seeds()
        self.assertNotIn(a["id"], shown)


class LenientExclusionReceiptTests(Base):
    """Exclusion follows content even when the excluded clip's receipt is unusable for DISPLAY: reading in this
    direction only adds a digest to the hidden set, so a missing or linked media file, a linked ``.done`` or a text
    duration must not drop the digest. Showing media stays strict."""

    BYTES = b"lenient-excluded-bytes"

    def pair(self):
        sha = hashlib.sha256(self.BYTES).hexdigest()
        a, b = clean_record(630, sha), clean_record(631, sha)
        for record in (a, b):
            add_clip(self.root, record["id"], record)
        return a, b

    def break_media_deleted(self, a):
        (self.root / "originals" / a["id"] / f"{a['id']}.mov").unlink()

    def break_media_symlink(self, a):
        media = self.root / "originals" / a["id"] / f"{a['id']}.mov"
        target = self.tmp / "elsewhere.mov"
        target.write_bytes(media.read_bytes())
        media.unlink()
        media.symlink_to(target)

    def break_done_symlink(self, a):
        done = self.root / "originals" / a["id"] / ".done"
        target = self.tmp / "elsewhere.done"
        target.write_bytes(done.read_bytes())
        done.unlink()
        done.symlink_to(target)

    def break_duration_text(self, a):
        done = self.root / "originals" / a["id"] / ".done"
        receipt = json.loads(done.read_text(encoding="utf-8"))
        receipt["video"]["duration"] = "2.0"
        done.write_text(json.dumps(receipt), encoding="utf-8")

    def test_the_byte_identical_copy_stays_hidden_whatever_is_wrong_with_the_excluded_receipt(self):
        for name in ("media_deleted", "media_symlink", "done_symlink", "duration_text"):
            with self.subTest(name):
                self.setUp()
                a, b = self.pair()
                getattr(self, f"break_{name}")(a)
                shown = set()
                for seed in ("1", "2", "3"):
                    shown |= self.used("--seed", seed, "--n", "7", "--duration", "120")
                self.assertIn(b["id"], shown)                              # control: not excluded, so the copy is shown
                for seed in ("1", "2", "3"):
                    code, stdout, stderr = run_all(*self.common, "--force", "--seed", seed, "--n", "7",
                                                   "--duration", "120", "--exclude-id", a["id"])
                    self.assertEqual(code, 0, stderr)
                    self.assertNotIn("match no clip", stderr)
                    self.assertFalse({s["id"] for s in self.load()["sources"]} & {a["id"], b["id"]}, (name, seed))

    def test_a_malformed_receipt_adds_no_digest_and_never_raises(self):
        a, _ = self.pair()
        done = self.root / "originals" / a["id"] / ".done"
        for text in ("not json", "[]", json.dumps({"files": "x"}),
                     json.dumps({"files": [1, {"sha256": 5}, {"sha256": "short"}]})):
            done.write_text(text, encoding="utf-8")
            self.assertEqual(cli.excluded_receipts(self.root, [a["id"]]), (set(), {a["id"].casefold()}), text)

    def test_every_digest_in_the_receipt_is_collected_in_its_normalised_form(self):
        a, _ = self.pair()
        other = hashlib.sha256(b"second-file").hexdigest()
        done = self.root / "originals" / a["id"] / ".done"
        receipt = json.loads(done.read_text(encoding="utf-8"))
        receipt["files"].append({"name": "x.heic", "sha256": f"  {other.upper()}\n"})
        done.write_text(json.dumps(receipt), encoding="utf-8")
        digests, _ = cli.excluded_receipts(self.root, [a["id"]])
        self.assertEqual(digests, {hashlib.sha256(self.BYTES).hexdigest(), other})

    def test_showing_media_stays_strict_for_the_same_receipts(self):
        for name in ("media_deleted", "media_symlink", "done_symlink", "duration_text"):
            with self.subTest(name):
                self.setUp()
                a, _ = self.pair()
                getattr(self, f"break_{name}")(a)
                pool, skipped = cli.load_pool(self.root)
                self.assertNotIn(a["id"], {r["id"] for r in pool})
                self.assertEqual(skipped["no_usable_export_receipt"], 1)

    def test_a_receipt_that_resolves_into_a_photos_library_package_is_refused_not_read(self):
        a, _ = self.pair()
        package = self.tmp / "Other.photoslibrary" / "originals"
        package.mkdir(parents=True)
        (self.root / "originals" / a["id"]).rename(package / a["id"])
        (self.root / "originals" / a["id"]).symlink_to(package / a["id"], target_is_directory=True)
        for ids in ([a["id"]], [a["id"].upper()]):
            with mock.patch.object(cli, "read_json", side_effect=AssertionError("read inside a package")):
                with self.assertRaises(play_guard.GuardError):
                    cli.excluded_receipts(self.root, ids)
        code, stdout, stderr = run_all(*self.common, "--force", "--exclude-id", a["id"])
        self.assertIn("Photos library", str(code))
        self.assertFalse(self.out.exists())

    def test_a_folded_library_name_is_refused_the_same_way(self):
        a, _ = self.pair()
        package = self.tmp / "Other.photo\u017flibrary" / "originals"
        package.mkdir(parents=True)
        (self.root / "originals" / a["id"]).rename(package / a["id"])
        (self.root / "originals" / a["id"]).symlink_to(package / a["id"], target_is_directory=True)
        with self.assertRaises(play_guard.GuardError):
            cli.excluded_receipts(self.root, [a["id"]])

    def test_originals_is_listed_once_per_run_however_many_ids_are_excluded(self):
        ids = [self.pool[i]["id"] for i in range(6)] + ["no-such-clip-1", "no-such-clip-2", "bad id"]
        listed = []
        real = os.listdir

        def spy(path="."):
            listed.append(os.fspath(path))
            return real(path)

        with mock.patch.object(cli.os, "listdir", spy):
            digests, known = cli.excluded_receipts(self.root, ids)
        self.assertEqual(sum(1 for p in listed if p == os.fspath(self.root / "originals")), 1, listed)
        self.assertEqual(known, {self.pool[i]["id"].casefold() for i in range(6)})
        self.assertEqual(len(digests), len({self.pool[i]["sha256"] for i in range(6)}))

    def test_an_id_matches_every_case_variant_directory_from_the_single_listing(self):
        a, _ = self.pair()
        sibling = self.root / "originals" / a["id"].upper()
        if sibling.exists():
            self.skipTest("this volume folds letter case")
        shutil.copytree(self.root / "originals" / a["id"], sibling)
        other = hashlib.sha256(b"upper-copy").hexdigest()
        receipt = json.loads((sibling / ".done").read_text(encoding="utf-8"))
        receipt["files"][0]["sha256"] = other
        (sibling / ".done").write_text(json.dumps(receipt), encoding="utf-8")
        digests, _ = cli.excluded_receipts(self.root, [a["id"]])
        self.assertEqual(digests, {hashlib.sha256(self.BYTES).hexdigest(), other})


class CaseResolutionTests(Base):
    """An id resolves to its ``originals/`` directory by comparing casefolded names against a listing, so the
    outcome never depends on the volume resolving a differently-cased path."""

    SHA = hashlib.sha256(b"upper-case-directory-bytes").hexdigest()

    def upper(self, tagged: bool = False):
        record = {**clean_record(630, self.SHA), "id": "UPPER-CLIP-630"}
        copy_ = clean_record(631, self.SHA)
        for r in (record, copy_):
            add_clip(self.root, r["id"], r)
        if not tagged:
            (self.root / "analysis" / "tags" / f"{record['id']}.json").unlink()
        return record, copy_

    def strict_volume(self):
        """read_json as a case-sensitive volume would see it: a path must spell the directory exactly as listed."""
        real = cli.read_json
        def read(path, *args):
            path = Path(path)
            if path.name == ".done" and path.parent.name not in os.listdir(path.parent.parent):
                raise ValueError("unreadable")                   # no such directory on a case-sensitive volume
            return real(path, *args)
        return mock.patch.object(cli, "read_json", read)

    def test_a_lower_case_id_finds_the_upper_case_directory_by_name_not_by_path(self):
        record, _ = self.upper()
        opened = []
        real = cli.receipt_digests
        def spy(path, *args):
            opened.append(Path(path))
            return real(path, *args)
        with mock.patch.object(cli, "receipt_digests", spy):
            digests, known = cli.excluded_receipts(self.root, [record["id"].lower()])
        self.assertEqual((digests, known), ({self.SHA}, {record["id"].casefold()}))
        self.assertEqual([p.parent.name for p in opened if p.name == ".done"], [record["id"]])   # the spelling on disk

    def test_the_resolution_holds_on_a_case_sensitive_volume(self):
        record, copy_ = self.upper()
        with self.strict_volume():
            self.assertEqual(cli.excluded_receipts(self.root, [record["id"].lower()]),
                             ({self.SHA}, {record["id"].casefold()}))
            self.assertEqual(cli.excluded_receipts(self.root, [record["id"].swapcase()]),
                             ({self.SHA}, {record["id"].casefold()}))
            config = self.tmp / "exclude.json"
            config.write_text(json.dumps({"exclusion": {"exclude_ids": [record["id"].lower()]}}))
            for seed in ("1", "2", "3"):
                code, stdout, stderr = run_all(*self.common, "--force", "--n", "7", "--duration", "120",
                                               "--seed", seed, "--config", config)
                self.assertEqual(code, 0, stderr)
                self.assertNotIn("match no clip", stderr)
                self.assertFalse({s["id"] for s in self.load()["sources"]} & {record["id"], copy_["id"]})
            for typed in (record["id"].lower(), "Upper-Clip-630"):
                code, _, stderr = run_all(*self.common, "--force", "--exclude-id", typed)
                self.assertEqual(code, 0, f"{code}{stderr}")

    def test_an_unknown_id_is_still_unknown(self):
        self.upper()
        self.assertEqual(cli.excluded_receipts(self.root, ["no-such-clip-632"]), (set(), set()))

    def test_ids_are_never_joined_into_a_path_unlisted(self):
        self.upper()
        for hostile in ("..", ".", "", "a/b"):
            self.assertEqual(cli.excluded_receipts(self.root, [hostile]), (set(), set()))


class LinkedAndVerifiedMediaTests(Base):
    """A symlinked originals/ or originals/<id>/ is never followed; --verify-media checks bytes against receipts."""

    def test_a_symlinked_media_file_is_skipped_and_counted_not_scheduled(self):
        """RS-2: the media file itself may not be a link (it could lead into a Photos library), with or without --verify-media."""
        victim = self.pool[0]["id"]
        media = self.root / "originals" / victim / f"{victim}.mov"
        elsewhere = self.tmp / "elsewhere" / media.name
        elsewhere.parent.mkdir(parents=True)
        media.rename(elsewhere)
        media.symlink_to(elsewhere)
        for verify in (False, True):
            with self.subTest(verify_media=verify):
                pool, skipped = cli.load_pool(self.root, verify)
                self.assertNotIn(victim, {r["id"] for r in pool})
                if not verify:                               # the placeholder media never matches a receipt when verified
                    self.assertEqual(skipped["no_usable_export_receipt"], 1)
                    self.assertEqual(len(pool), len(self.pool) - 1)
        self.assertNotIn(victim, self.used("--n", "3"))

    def other_tree(self, clip):
        """A second synthetic tree holding a full receipt and media for ``clip``; returns its originals/ dir."""
        other = self.tmp / "elsewhere"
        add_clip(other, clip, {**clean_record(1), "id": clip})
        return other / "originals"

    def test_a_symlinked_clip_directory_is_skipped_and_counted_not_read(self):
        victim = self.pool[0]["id"]
        target = self.other_tree(victim) / victim
        shutil.rmtree(self.root / "originals" / victim)
        (self.root / "originals" / victim).symlink_to(target, target_is_directory=True)
        pool, skipped = cli.load_pool(self.root)
        self.assertNotIn(victim, {r["id"] for r in pool})
        self.assertEqual(skipped["no_usable_export_receipt"], 1)
        self.assertEqual(len(pool), len(self.pool) - 1)

    def test_a_symlinked_originals_directory_skips_every_clip(self):
        target = self.tmp / "moved-originals"
        (self.root / "originals").rename(target)
        (self.root / "originals").symlink_to(target, target_is_directory=True)
        pool, skipped = cli.load_pool(self.root)
        self.assertEqual(pool, [])
        self.assertEqual(skipped["no_usable_export_receipt"], len(self.pool))

    def test_the_receipt_behind_a_symlinked_clip_directory_is_never_opened(self):
        victim = self.pool[1]["id"]
        target = self.other_tree(victim) / victim
        shutil.rmtree(self.root / "originals" / victim)
        (self.root / "originals" / victim).symlink_to(target, target_is_directory=True)
        opened = []
        real = cli.receipt_digests
        def spy(path, *args):
            opened.append(Path(path))
            return real(path, *args)
        with mock.patch.object(cli, "receipt_digests", spy):
            cli.load_pool(self.root)
        self.assertFalse([p for p in opened if p.parent.name == victim and p.name == ".done"])

    def verified(self, clip, payload=b"verified-bytes"):
        record = {**clean_record(700), "id": clip, "sha256": hashlib.sha256(payload).hexdigest()}
        add_clip(self.root, clip, record)
        media = self.root / "originals" / clip / f"{clip}.mov"
        media.write_bytes(payload)
        done = json.loads((self.root / "originals" / clip / ".done").read_text())
        done["files"][0]["bytes"] = len(payload)
        (self.root / "originals" / clip / ".done").write_text(json.dumps(done))
        return media

    def test_by_default_a_receipt_is_trusted_and_the_media_is_not_hashed(self):
        media = self.verified("trusted-clip")
        media.write_bytes(b"replaced-by-something-else-entirely")
        pool, skipped = cli.load_pool(self.root)
        self.assertIn("trusted-clip", {r["id"] for r in pool})
        self.assertEqual(sum(skipped.values()), 0)

    def test_verify_media_skips_size_and_digest_mismatches_and_keeps_honest_files(self):
        self.verified("honest-clip")
        self.verified("grown-clip").write_bytes(b"verified-bytes-and-more")
        self.verified("swapped-clip").write_bytes(b"verified-BYTES")                  # same size, other content
        self.verified("missing-clip").unlink()
        pool, skipped = cli.load_pool(self.root, verify_media=True)
        ids = {r["id"] for r in pool}
        self.assertIn("honest-clip", ids)
        self.assertFalse(ids & {"grown-clip", "swapped-clip", "missing-clip"})
        self.assertEqual(skipped["no_usable_export_receipt"], len(self.pool) + 3)       # the 60 fixtures carry fake digests

    def test_the_command_flag_enables_the_check(self):
        self.verified("honest-clip")
        self.verified("honest-clip-2", b"other verified bytes")
        code, stdout, stderr = run_all(*self.common, "--force", "--n", "2", "--verify-media")
        self.assertEqual(code, 0, stderr)
        self.assertIn("2 usable records", stdout)
        self.assertIn(f"{len(self.pool)} skipped {{'no_usable_export_receipt': {len(self.pool)}}}", stdout)


class RobustnessTests(Base):
    def test_unusable_records_are_skipped_counted_and_never_named(self):
        tags = self.root / "analysis" / "tags"
        write(tags / "has space.json", {"analysis": None})
        (tags / "broken-json.json").write_text("{", encoding="utf-8")
        write(tags / "mismatch-id.json", {"uuid": "someone-else", "analysis": None})
        write(tags / "no-receipt.json", {"uuid": "no-receipt", "analysis": None})
        write(tags / "no-media.json", {"uuid": "no-media", "analysis": None})
        write(self.root / "originals" / "no-media" / ".done",
              {"files": [{"name": "no-media.mov", "sha256": "0" * 64}], "video": {"name": "no-media.mov", "duration": 2}})
        write(self.tmp / "elsewhere.json", {"uuid": "linked", "analysis": None})
        (tags / "linked.json").symlink_to(self.tmp / "elsewhere.json")
        pool, skipped = cli.load_pool(self.root)
        self.assertEqual(len(pool), len(self.pool))
        self.assertEqual(dict(skipped), {"id_not_opaque": 1, "unreadable_tag_record": 2, "tag_record_id_mismatch": 1,
                                         "no_usable_export_receipt": 2})
        code, stdout = run(*self.common, "--force")
        self.assertEqual(code, 0)
        self.assertIn("6 skipped {'id_not_opaque': 1, 'no_usable_export_receipt': 2, "
                      "'tag_record_id_mismatch': 1, 'unreadable_tag_record': 2}", stdout)
        for name in ("has space", "broken-json", "mismatch-id", "no-receipt", "no-media", "linked"):
            self.assertNotIn(name, stdout)
            self.assertNotIn(name, self.out.read_text(encoding="utf-8"))

    def test_one_malformed_record_never_crashes_a_run(self):
        tags, originals = self.root / "analysis" / "tags", self.root / "originals"
        ok = clean_record(500)
        # categories is an int; a deeply nested file; receipt files is an int; analysis is a list; huge numbers
        add_clip(self.root, "m-categories", {**ok, "analysis": {**ok["analysis"], "safety": {"verdict": "clear", "categories": 5}}})
        (tags / "m-deep.json").write_text("[" * 200000 + "]" * 200000)
        add_clip(self.root, "m-files", ok)
        write(originals / "m-files" / ".done", {"files": 5, "video": {"name": "m-files.mov", "duration": 2}})
        add_clip(self.root, "m-list", {**ok, "analysis": [1, 2]})
        add_clip(self.root, "m-huge", {**ok, "features": {"luma": 10 ** 400, "hue": float("nan"), "palette": [None, 5]}})
        add_clip(self.root, "m-types", {**ok, "analysis": {"subjects": "text", "keywords": {"a": 1}, "setting": 5,
                                                            "people": "x", "privacy": [1], "safety": {"verdict": "clear"}}})
        pool, skipped = cli.load_pool(self.root)
        self.assertEqual(skipped["unreadable_tag_record"], 1)
        self.assertEqual(skipped["no_usable_export_receipt"], 1)
        code, stdout = run(*self.common, "--force", "--duration", "60", "--n", "7")
        self.assertEqual(code, 0)
        for name in ("m-categories", "m-deep", "m-files", "m-list", "m-huge", "m-types"):
            self.assertNotIn(name, stdout)

    def test_a_receipt_with_a_tiny_duration_is_excluded_and_counted_not_a_hang(self):
        # DP-1: 1e-9 s made the segment estimate loop once per wrap, about 10**10 times.
        add_clip(self.root, "tiny-clip", {**clean_record(501), "duration": 1e-9})
        with time_limit(60):
            code, stdout = run(*self.common, "--force", "--n", "3", "--duration", "30")
        self.assertEqual(code, 0)
        self.assertIn("'media_duration': 1", stdout)
        self.assertNotIn("tiny-clip", stdout)
        self.assertNotIn("tiny-clip", {s["id"] for s in self.load()["sources"]})

    def test_non_finite_and_invalid_durations_and_counts_are_clean_errors(self):
        for duration in ("inf", "nan", "-1", "0", "100000"):
            with self.subTest(duration=duration), self.assertRaises(SystemExit) as raised:
                run("--root", self.root, "--out", self.out, "--duration", duration)
            self.assertIn("play:", str(raised.exception))
            self.assertFalse(self.out.exists())
        for extra in (("--n", "1"), ("--n", "8"), ("--fps", "0"), ("--fps", "61")):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                run("--root", self.root, "--out", self.out, *extra)

    def test_a_budget_refusal_is_a_clean_error(self):
        with self.assertRaises(SystemExit) as raised:
            run(*self.common, "--set", "limits.max_events=100", "--n", "7", "--duration", "600")
        self.assertIn("max_events", str(raised.exception))

    LONG = ("--n", "7", "--duration", "300")           # about 1,200 render segments on the synthetic pool: over 1,024

    def test_a_long_state_warns_loudly_and_exactly_that_it_will_not_render(self):
        code, stdout, stderr = run_all(*self.common[:-6], "--n", "7", "--duration", "300", "--seed", "7")
        self.assertEqual(code, 0, stderr)
        segments = int(re.search(r"render_segments=(\d+)", stdout).group(1))
        self.assertGreater(segments, composition.MAX_SEGMENTS)
        warning = [line for line in stderr.splitlines() if line.startswith("WARNING")]
        self.assertEqual(len(warning), 1, stderr)
        for needle in ("NOT RENDERABLE", f"needs {segments} render segments", f"allows {composition.MAX_SEGMENTS}",
                       f"{segments - composition.MAX_SEGMENTS} over", "compile_plan", "limits.refuse_unrenderable=true"):
            self.assertIn(needle, warning[0])
        self.assertTrue(self.out.exists() and self.side.exists())        # default: still written (previews and compiles)
        self.assertFalse(self.sidecar()["renderable"])
        code, stdout, stderr = run_all(*self.common, "--force")           # a short state: no warning at all
        self.assertEqual((code, stderr), (0, ""))

    def test_the_configured_limit_can_only_be_lower_than_the_renderers(self):
        code, _, _ = run_all(*self.common, "--force", "--set", "limits.max_render_segments=5000")
        self.assertIn("max_render_segments", str(code))
        self.assertIn("1024", str(code))
        code, stdout, stderr = run_all(*self.common, "--force", "--set", "limits.max_render_segments=20")
        self.assertEqual(code, 0, stderr)                                         # a lower limit warns, it does not refuse
        self.assertIn("over your limits.max_render_segments=20", stderr)
        self.assertNotIn("NOT RENDERABLE", stderr)                                # the renderer itself would take it
        self.assertTrue(self.sidecar()["renderable"])
        with self.assertRaises(SystemExit):
            run(*self.common, "--force", "--set", "limits.max_render_segments=20", "--set", "limits.refuse_unrenderable=true")

    def test_refusing_unrenderable_states_refuses_the_long_run_and_writes_nothing(self):
        argv = (*self.common[:-6], "--n", "7", "--duration", "300", "--set", "limits.refuse_unrenderable=true",
                "--set", "limits.max_render_segments=5000")
        code, _, _ = run_all(*argv)
        self.assertIn("1024", str(code))                           # the old escape hatch (raise the limit) is closed
        argv = (*self.common[:-6], "--n", "7", "--duration", "300", "--set", "limits.refuse_unrenderable=true")
        code, stdout, _ = run_all(*argv)
        self.assertIn("the offline renderer allows 1024", str(code))
        self.assertFalse(self.out.exists() or self.side.exists())

    def test_states_the_preview_would_refuse_are_refused_with_nothing_written(self):
        # (1) the 0.25 s hold floor over five minutes, (2) default sticky, 7 loops, 30 minutes at 8 fps
        small = self.tmp / "small"
        build_root(small, 14)
        for argv, cause, advice in (
                (("--root", small, "--out", self.out, "--mode", "random", "--n", "2", "--duration", "300",
                  "--set", "timing.hold_min=0.25", "--set", "timing.hold_max=0.25", "--set", "timing.stagger=0",
                  "--set", "timing.cooldown=0"), "source changes dominate", "larger timing.hold_min"),
                (("--root", self.root, "--out", self.out, "--n", "7", "--fps", "8", "--duration", "1800"),
                 "clip ends dominate", "longer source clips")):
            code, stdout, stderr = run_all(*argv)
            self.assertIn("browser spans", str(code))
            self.assertIn(cause, str(code).lower())
            self.assertIn(advice, str(code))                       # the advice follows the counted cause
            self.assertIn("per loop", str(code))
            self.assertIn("shorter duration", str(code))
            if cause.startswith("clip"):
                self.assertNotIn("larger timing.hold_min", str(code))   # a hold floor does not help when clip ends dominate
            self.assertEqual(stdout, "")
            self.assertFalse(self.out.exists() or self.side.exists())
            self.assertEqual([p.name for p in self.tmp.glob(".*.tmp")], [])

    def test_too_few_eligible_clips_fail_without_filler(self):
        small = self.tmp / "small"
        build_root(small, 8)
        for tag in sorted((small / "analysis" / "tags").glob("*.json"))[3:]:
            tag.unlink()
        with self.assertRaises(SystemExit) as raised:
            run("--root", small, "--out", self.out, "--n", "5", "--duration", "30")
        self.assertIn("no filler", str(raised.exception))
        self.assertFalse(self.out.exists())

    def test_pool_records_carry_no_free_text(self):
        record = clean_record(600)
        record["analysis"]["subjects"] = ["tree", "Anna was here at 12 Main Street, a very long personal sentence indeed", "ok"]
        record["analysis"]["camera"] = "CAMERA-SENTINEL"
        add_clip(self.root, record["id"], record)
        pool, _ = cli.load_pool(self.root)
        text = json.dumps(pool)
        for needle in (*SENTINELS, "PHOTOS-ID-SENTINEL", "caption", "sharing_note", "reason", "CAMERA-SENTINEL", "Anna", "error"):
            self.assertNotIn(needle, text)
        mine = next(r for r in pool if r["id"] == record["id"])
        self.assertEqual(mine["analysis"]["subjects"], ["tree", "ok"])
        tagged = next(r for r in pool if r["analysis"])
        self.assertEqual(set(tagged["analysis"]["privacy"]) - {"sharing_sensitivity"},
                         {"readable_text", "license_plate", "document_or_screen", "location_identifiable"})
        self.assertEqual(tagged["analysis"]["safety"].keys(), {"verdict", "categories"})
        self.assertEqual(cli.sanitize_analysis(None), None)
        self.assertEqual(cli.sanitize_analysis({}), {})
        self.assertEqual(cli.sanitize_analysis("x"), {})
        self.assertEqual(cli.sanitize_features({"hue": True, "luma": 0.5, "palette": "x", "extra": 1}), {"luma": 0.5})


class LinkedAnalysisDirTests(Base):
    """analysis/, analysis/tags/ and analysis/index/ are real directories inside --root, as index_clips requires."""

    def swap_for_link(self, *parts: str) -> Path:
        """Move root/<parts> into a second synthetic tree and leave a real symlink in its place."""
        original = self.root.joinpath(*parts)
        moved = self.tmp / "second-tree" / "/".join(parts)
        moved.parent.mkdir(parents=True, exist_ok=True)
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
        return original

    def test_a_linked_tags_index_or_analysis_directory_is_refused_with_nothing_written(self):
        for parts in (("analysis", "tags"), ("analysis", "index"), ("analysis",)):
            with self.subTest(link="/".join(parts)):
                self.setUp()
                self.swap_for_link(*parts)
                before = sorted(p.name for p in self.tmp.iterdir())
                code, stdout, stderr = run_all(*self.common)
                self.assertNotEqual(code, 0)
                self.assertIn("real directories inside --root", str(code))
                self.assertEqual(stdout, "")
                self.assertFalse(self.out.exists() or self.side.exists())
                self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), before)

    def test_a_link_to_a_directory_inside_the_root_is_refused_too(self):
        (self.root / "analysis" / "tags").rename(self.root / "tags-real")
        (self.root / "analysis" / "tags").symlink_to(self.root / "tags-real", target_is_directory=True)
        code, _, _ = run_all(*self.common)
        self.assertIn("real directories inside --root", str(code))

    def test_real_directories_and_an_absent_index_are_accepted(self):
        shutil.rmtree(self.root / "analysis" / "index")
        code, _, stderr = run_all(*self.common)
        self.assertEqual(code, 0, stderr)

    def test_the_guard_function_names_what_is_wrong_without_the_path(self):
        self.swap_for_link("analysis", "tags")
        with self.assertRaises(play_guard.GuardError) as raised:
            play_guard.check_analysis_dirs(self.root)
        self.assertNotIn(str(self.tmp), str(raised.exception))


class PlacementTests(Base):
    def attempt(self, out):
        before = sorted(p.name for p in Path(out).parent.iterdir()) if Path(out).parent.exists() else None
        with self.assertRaises(SystemExit):
            run("--root", self.root, "--out", out, "--n", "3", "--duration", "20")
        if before is not None:
            self.assertEqual(sorted(p.name for p in Path(out).parent.iterdir()), before)     # nothing was written

    def test_output_is_confined_to_var_work_or_outside_every_working_tree(self):
        self.assertEqual(play_guard.resolve_out(cli.DEFAULT_OUT), cli.DEFAULT_OUT.resolve())
        self.assertEqual(cli.DEFAULT_OUT.parent, WORK_DIR)
        for inside in (REPO_ROOT / "docs" / "play.json", REPO_ROOT / "var" / "play.json"):
            self.attempt(inside)

    def test_case_variants_sibling_worktrees_and_photos_libraries_write_nothing(self):
        variant = case_variant(REPO_ROOT)
        if variant is not None:
            self.attempt(variant / "docs" / "play.json")
            self.assertFalse((REPO_ROOT / "docs" / "play.json").exists())
            self.assertFalse((REPO_ROOT / "docs" / "play.play.json").exists())
        worktree = self.tmp / "sibling-worktree"
        (worktree / "docs").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /nowhere\n")
        self.attempt(worktree / "docs" / "play.json")
        package = self.tmp / "Lib.photoslibrary" / "resources"
        package.mkdir(parents=True)
        self.attempt(package / "play.json")
        self.attempt(self.tmp / "LIB.PHOTOSLIBRARY" / "play.json")

    def test_existing_output_needs_force_for_the_state_and_for_the_sidecar(self):
        run(*self.common)
        state, side = self.out.read_bytes(), self.side.read_bytes()
        with self.assertRaises(SystemExit):
            run(*self.common)
        self.out.unlink()
        with self.assertRaises(SystemExit):
            run(*self.common)                                                         # only the sidecar exists
        self.assertFalse(self.out.exists())
        self.assertEqual(self.side.read_bytes(), side)
        run(*self.common, "--force")
        self.assertEqual(self.out.read_bytes(), state)

    def test_failed_runs_leave_nothing_behind(self):
        with self.assertRaises(SystemExit) as raised:
            run(*self.common[:-2], "--seed", "1", "--n", "7", "--exclude-id", self.pool[0]["id"],
                "--set", "exclusion.untagged_policy=\"exclude\"", "--pin", "loop-1=nope")
        self.assertIn("play:", str(raised.exception))
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["private"])

    def test_a_planted_temp_symlink_and_a_planted_output_symlink_are_not_followed(self):
        victim = self.tmp / "victim.txt"
        victim.write_text("precious")
        (self.tmp / ".state.json.tmp").symlink_to(victim)
        (self.tmp / ".state.play.json.tmp").symlink_to(victim)
        run(*self.common)
        self.assertEqual(victim.read_text(), "precious")
        self.out.unlink()
        self.out.symlink_to(victim)
        with self.assertRaises(SystemExit):
            run(*self.common)
        run(*self.common, "--force")
        self.assertEqual(victim.read_text(), "precious")
        self.assertFalse(self.out.is_symlink())

    def swap_parent_for_link(self, parent: Path, victim: Path) -> Path:
        """Move ``parent`` aside and leave a symlink to ``victim`` under its name (what an attacker does mid-run)."""
        moved = parent.with_name(parent.name + "-moved")
        parent.rename(moved)
        parent.symlink_to(victim, target_is_directory=True)
        return moved

    def victims(self):
        """Directories a swapped-in link must never reach: a tracked directory of another repository, a Photos package."""
        repo = self.tmp / "other-repo"
        (repo / "tracked").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True,
                       env={"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp), "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_CONFIG_SYSTEM": os.devnull})
        package = self.tmp / "Victim.photoslibrary" / "resources"
        package.mkdir(parents=True)
        return {"tracked directory of another repository": repo / "tracked", "Photos library package": package}

    def test_a_parent_directory_swapped_for_a_link_after_the_first_check_is_caught_before_the_state_is_written(self):
        """PR-2: ``--out`` is validated once at the start and written minutes later (after the pool is loaded and the
        schedule built); the destination is checked again immediately before each write."""
        for what, victim in self.victims().items():
            with self.subTest(victim=what):
                parent = self.tmp / f"outside-{len(what)}"
                parent.mkdir()
                out = parent / "state.json"
                real_load = cli.load_pool

                def load_then_swap(*args, **kwargs):
                    result = real_load(*args, **kwargs)
                    self.swap_parent_for_link(parent, victim)
                    return result

                with mock.patch.object(cli, "load_pool", load_then_swap):
                    code, stdout, stderr = run_all("--root", self.root, "--out", out, "--n", "3", "--duration", "30",
                                                   "--seed", "7")
                self.assertNotEqual(code, 0, stdout + stderr)
                self.assertTrue(str(code).startswith(("--out must stay", "Refusing to write")), code)
                self.assertEqual(sorted(p.name for p in victim.iterdir()), [], "nothing may reach the victim directory")
                self.assertEqual(list((parent.with_name(parent.name + "-moved")).iterdir()), [])
                self.assertNotIn("private:", stdout)                          # no success notice

    def test_the_record_path_is_checked_again_right_before_the_second_write(self):
        for what, victim in self.victims().items():
            with self.subTest(victim=what):
                parent = self.tmp / f"outside2-{len(what)}"
                parent.mkdir()
                out = parent / "state.json"
                real_write, writes = play_guard.write_private_file, []

                def write_then_swap(target, data, force):
                    real_write(target, data, force)
                    writes.append(Path(target).name)
                    if len(writes) == 1:                                       # the state is down; now swap the folder
                        self.swap_parent_for_link(parent, victim)

                with mock.patch.object(play_guard, "write_private_file", write_then_swap):
                    code, stdout, stderr = run_all("--root", self.root, "--out", out, "--n", "3", "--duration", "30",
                                                   "--seed", "7")
                self.assertNotEqual(code, 0, stdout + stderr)
                self.assertTrue(str(code).startswith(("--out must stay", "Refusing to write")), code)
                self.assertEqual(writes, ["state.json"])                       # the record was never written
                self.assertEqual(sorted(p.name for p in victim.iterdir()), [], "nothing may reach the victim directory")

    def test_an_unswapped_run_still_writes_both_files_through_the_resolved_paths(self):
        code, stdout, stderr = run_all(*self.common)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.out.is_file() and self.side.is_file())

    def test_root_rules(self):
        for bad in (self.tmp / "missing", self.tmp, REPO_ROOT / "docs", REPO_ROOT, self.tmp / "Library.photoslibrary" / "x"):
            with self.subTest(root=str(bad)), self.assertRaises(SystemExit):
                play_guard.resolve_root(str(bad))
        self.assertEqual(play_guard.resolve_root(str(self.root)), self.root)
        with self.assertRaises(SystemExit):
            run("--out", self.out)                                                    # --root is required
        self.assertEqual(run("--list-modes")[0], 0)                                   # ... except for the listings


if __name__ == "__main__":
    unittest.main()
