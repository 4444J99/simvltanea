"""Verify generic consumers share implementation and preserve distinct data identities."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from independent_loop_compositor import Composition, Layout, LoopState, Placement
from independent_loop_compositor.authoring import from_authoring_model
from independent_loop_compositor.browser import compile_plan
from tools.paths import REPO_ROOT


class FunctionalIdentityTests(unittest.TestCase):
    def test_public_objects_are_the_existing_implementation(self):
        for feature in ("authoring", "browser", "rendering"):
            current = importlib.import_module("independent_loop_compositor." + feature)
            legacy = importlib.import_module("simvltanea." + feature)
            for name in current.__all__:
                expected = legacy.render_triptych.render if name == "render" else getattr(legacy, name)
                with self.subTest(feature=feature, name=name):
                    self.assertIs(getattr(current, name), expected)

    def test_unrelated_compositions_do_not_inherit_artwork_identity(self):
        layouts = (
            Layout("stacked", "portrait", (Placement("first", 0, 0, 1, .5), Placement("second", 0, .5, 1, .5))),
            Layout("adjacent", "landscape", (Placement("first", 0, 0, .5, 1), Placement("second", .5, 0, .5, 1))),
        )
        results = []
        for identity in ("motion-study", "light-study"):
            loops = (LoopState("first", f"{identity}/camera-01.mp4", trim_out=3),
                     LoopState("second", f"{identity}/camera-02.mp4", trim_out=3, rate=1.25, offset=.25))
            model = Composition(identity, loops, layouts)
            model.validate()
            self.assertEqual(Composition.from_dict(json.loads(model.to_json())), model)
            mapping = {loop.source: dict(id=f"{identity}-{number}", path=loop.source,
                       kind="video", duration="3", sha256=str(number) * 64)
                       for number, loop in enumerate(loops, 1)}
            state = from_authoring_model(model, mapping, frames=12, fps=24)
            legacy = importlib.import_module("simvltanea.authoring")
            self.assertEqual(state, legacy.from_authoring_model(model, mapping, frames=12, fps=24))
            plan = compile_plan(state)
            self.assertEqual(len(plan["tracks"]), 2)
            self.assertEqual({s["path"] for s in plan["sources"]}, set(mapping))
            self.assertNotIn("simvltanea", model.to_json().lower())
            self.assertNotIn("simvltanea", json.dumps(plan).lower())
            times = [loop.media_time(1) for loop in model.loops]
            model.layout("portrait")
            model.layout("landscape")
            self.assertEqual(times, [loop.media_time(1) for loop in model.loops])
            results.append(plan)
        self.assertNotEqual(results[0]["state_sha256"], results[1]["state_sha256"])
        self.assertTrue({s["id"] for s in results[0]["sources"]}.isdisjoint(
            {s["id"] for s in results[1]["sources"]}))

    def test_old_and_new_cli_help_and_error_exit_codes(self):
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
        for action, legacy in (("preview", "simvltanea.browser_runtime"),
                               ("render", "simvltanea.render_triptych")):
            for arguments, expected in ((["--help"], 0), (["--unknown-argument"], 2)):
                old = subprocess.run([sys.executable, "-m", legacy, *arguments],
                                     cwd=REPO_ROOT, env=env, text=True, capture_output=True)
                new = subprocess.run([sys.executable, "-m", "independent_loop_compositor", action, *arguments],
                                     cwd=REPO_ROOT, env=env, text=True, capture_output=True)
                with self.subTest(action=action, arguments=arguments):
                    self.assertEqual(old.returncode, expected, old.stderr)
                    self.assertEqual(new.returncode, expected, new.stderr)
                    if expected == 0:
                        self.assertIn("--output", old.stdout)
                        self.assertIn("--output", new.stdout)

    def test_dispatch_restores_caller_arguments_on_failure(self):
        from independent_loop_compositor.cli import main
        original = sys.argv
        with patch("simvltanea.browser.browser_runtime.main", side_effect=RuntimeError("preview failure")):
            with self.assertRaisesRegex(RuntimeError, "preview failure"):
                main(["preview", "--state", "state.json"])
        self.assertIs(sys.argv, original)

    def test_descriptor_points_to_existing_authorities(self):
        manifest = json.loads((REPO_ROOT / "ace-manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["repository"]["github_id"], 1364497735)
        self.assertEqual(manifest["software"]["id"], "independent-loop-compositor")
        capabilities = {item["id"] for item in manifest["capabilities"]}
        artworks = {item["id"] for item in manifest["artworks"]}
        compositions = {item["id"] for item in manifest["compositions"]}
        for kind in ("capabilities", "modules", "source_media", "compositions", "artworks", "editions", "archives"):
            records = manifest[kind]
            self.assertEqual(len(records), len({item["id"] for item in records}))
            for record in records:
                if "path" in record:
                    path = (REPO_ROOT / record["path"]).resolve()
                    self.assertTrue(path.is_relative_to(REPO_ROOT))
                    self.assertTrue(path.exists())
                if "artwork_id" in record:
                    self.assertIn(record["artwork_id"], artworks)
                if "composition_id" in record:
                    self.assertIn(record["composition_id"], compositions)
                if "capability_ids" in record:
                    self.assertTrue(set(record["capability_ids"]) <= capabilities)
                if "json_pointer" in record:
                    data = json.loads(path.read_text())
                    for key in record["json_pointer"].strip("/").split("/"):
                        data = data[int(key)] if isinstance(data, list) else data[key]
                    self.assertIsInstance(data, dict)
                    if kind == "editions":
                        self.assertEqual(data["slug"], record["id"])
                    if kind == "compositions":
                        self.assertIn("arrangement_model_role", data)
        # A public software declaration must not newly inventory local media.
        self.assertEqual(manifest["source_media"], [])
