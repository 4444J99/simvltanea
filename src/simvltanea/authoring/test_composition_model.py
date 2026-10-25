#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


from simvltanea.authoring.artifact001_layouts import AUTHORED, build_artifact001
from simvltanea.authoring.composition_model import (
    Composition,
    SliceRect,
    AmalgamatedPanel,
    amalgamate_viewports,
    color_subject_affinity,
    select_neighbor_sequence,
    LoopState,
    AMALGAMATED_MANIFEST_SCHEMA,
    MAX_AMALGAMATED_DECODERS,
    export_amalgamated_manifest,
    verify_amalgamated_manifest,
)


class CompositionModelTests(unittest.TestCase):
    def test_acceptance_matrix_has_authored_pairs(self):
        self.assertEqual(set(AUTHORED), {2, 3, 4, 5, 6, 7})
        for count in AUTHORED:
            comp = build_artifact001(count)
            self.assertEqual(len(comp.loops), count)
            self.assertEqual({l.orientation for l in comp.layouts}, {"portrait", "landscape"})
            for layout in comp.layouts:
                self.assertEqual({p.loop_id for p in layout.placements}, set(comp.loop_ids))
                self.assertEqual(len(layout.placements), count)

    def test_orientation_selection_does_not_mutate_time(self):
        comp = build_artifact001(6)
        before = [loop.media_time(12.5) for loop in comp.loops]
        comp.layout("portrait")
        comp.layout("landscape")
        comp.layout("portrait")
        after = [loop.media_time(12.5) for loop in comp.loops]
        self.assertEqual(before, after)

    def test_add_loop_does_not_reset_survivors(self):
        a = build_artifact001(5)
        b = build_artifact001(6)
        self.assertEqual([x.media_time(9) for x in a.loops], [x.media_time(9) for x in b.loops[:5]])

    def test_serialization_round_trip(self):
        comp = build_artifact001(4)
        replay = Composition.from_dict(json.loads(comp.to_json()))
        self.assertEqual(comp, replay)

    def test_seeded_selection_is_evaluation_order_independent(self):
        comp = build_artifact001(5)
        bank = ("a.mp4", "b.mp4", "c.mp4", "d.mp4")
        forward = {loop.id: comp.choose_source(loop.id, bank) for loop in comp.loops}
        reverse = {loop.id: comp.choose_source(loop.id, bank) for loop in reversed(comp.loops)}
        self.assertEqual(forward, reverse)

    def test_hold_release_preserves_other_loop_clocks(self):
        comp = build_artifact001(3)
        untouched = comp.loops[1].media_time(7)
        held = comp.apply({"type": "hold", "loop_id": "loop-1"}, 3)
        self.assertEqual(held.loops[0].media_time(8), held.loops[0].media_time(3))
        self.assertEqual(held.loops[1].media_time(7), untouched)
        released = held.apply({"type": "release", "loop_id": "loop-1"}, 8)
        self.assertAlmostEqual(released.loops[0].media_time(8), held.loops[0].media_time(3))

    def test_reroll_only_advances_target(self):
        comp = build_artifact001(4)
        updated = comp.apply({"type": "reroll", "loop_id": "loop-3"}, 2)
        self.assertEqual(updated.loops[2].reroll_index, 1)
        self.assertEqual([l.reroll_index for l in updated.loops[:2] + updated.loops[3:]], [0, 0, 0])

    def test_swap_exchanges_sources_not_clocks(self):
        comp = build_artifact001(3)
        times = [l.media_time(5) for l in comp.loops]
        swapped = comp.apply({"type": "swap", "a": "loop-1", "b": "loop-2"}, 5)
        self.assertEqual(swapped.loops[0].source, comp.loops[1].source)
        self.assertEqual(swapped.loops[1].source, comp.loops[0].source)
        self.assertEqual([l.media_time(5) for l in swapped.loops], times)

    def test_move_changes_one_orientation_only(self):
        comp = build_artifact001(3)
        old_landscape = comp.layout("landscape")
        moved = comp.apply({"type": "move", "orientation": "portrait", "loop_id": "loop-2", "geometry": {"x": .05}}, 1)
        self.assertEqual(moved.layout("landscape"), old_landscape)
        self.assertEqual(moved.layout("portrait").placements[1].x, .05)

    def test_unsupported_count_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "no reviewed engineering layout pair"):
            build_artifact001(8)

    def test_amalgamate_viewports_valid_counts_and_invariants(self):
        for count in range(3, 11):
            viewports = amalgamate_viewports(count, seed=42)
            self.assertEqual(len(viewports), count)
            # Invariant: no panel displays full frame
            for rect in viewports:
                self.assertIsInstance(rect, SliceRect)
                self.assertFalse(rect.is_full_frame, f"Count {count} produced full-frame viewport {rect}")
                self.assertFalse(rect.x == 0.0 and rect.y == 0.0 and rect.width == 1.0 and rect.height == 1.0)
                self.assertGreaterEqual(rect.x, 0.0)
                self.assertGreaterEqual(rect.y, 0.0)
                self.assertLessEqual(rect.x + rect.width, 1.000001)
                self.assertLessEqual(rect.y + rect.height, 1.000001)
                self.assertGreater(rect.width, 0.0)
                self.assertGreater(rect.height, 0.0)

            # Check coverage spans from x=0 to x+w=1 across the amalgamated ribbon
            min_x = min(r.x for r in viewports)
            max_right = max(r.x + r.width for r in viewports)
            self.assertAlmostEqual(min_x, 0.0, places=4)
            self.assertAlmostEqual(max_right, 1.0, places=4)

    def test_amalgamate_viewports_invalid_counts_raise_value_error(self):
        for bad_count in (0, 1, 2, 11, 12, -5):
            with self.assertRaises(ValueError):
                amalgamate_viewports(bad_count)

    def test_amalgamate_viewports_modes_and_seeding(self):
        v_ribbon = amalgamate_viewports(4, seed=10, mode="ribbon")
        v_vert = amalgamate_viewports(4, seed=10, mode="vertical")
        v_grid = amalgamate_viewports(4, seed=10, mode="grid")
        self.assertEqual(len(v_ribbon), 4)
        self.assertEqual(len(v_vert), 4)
        self.assertEqual(len(v_grid), 4)

        # Seeding determinism: identical seed -> identical rects
        v_ribbon2 = amalgamate_viewports(4, seed=10, mode="ribbon")
        self.assertEqual(v_ribbon, v_ribbon2)

        # Different seed -> different rects
        v_diff = amalgamate_viewports(4, seed=999, mode="ribbon")
        self.assertNotEqual(v_ribbon, v_diff)

        with self.assertRaises(ValueError):
            amalgamate_viewports(4, mode="invalid_mode")

    def test_color_subject_affinity(self):
        clip1 = {"id": "c1", "color_profile": "#FF0000", "subject_tags": ["red", "warm", "circle"]}
        clip2 = {"id": "c2", "color_profile": "#EE0000", "subject_tags": ["red", "warm", "square"]}
        clip3 = {"id": "c3", "color_profile": "#0000FF", "subject_tags": ["blue", "cold", "triangle"]}

        # Self-affinity is 1.0
        self.assertAlmostEqual(color_subject_affinity(clip1, clip1), 1.0, places=4)

        # Near color and overlapping tags -> high affinity
        aff_12 = color_subject_affinity(clip1, clip2)
        # Distant color and disjoint tags -> lower affinity
        aff_13 = color_subject_affinity(clip1, clip3)
        self.assertGreater(aff_12, aff_13)
        self.assertGreaterEqual(aff_13, 0.0)
        self.assertLessEqual(aff_12, 1.0)

        # HSL and RGB tuple formats
        hsl_clip = {"id": "hsl", "color_profile": {"hue": 0, "saturation": 1.0, "luminance": 0.5}}
        rgb_clip = {"id": "rgb", "color_profile": (1.0, 0.0, 0.0)}
        self.assertGreater(color_subject_affinity(hsl_clip, rgb_clip), 0.9)

        # Fallback for clips without metadata
        plain_a = {"id": "plain_a"}
        plain_b = {"id": "plain_b"}
        aff_fallback = color_subject_affinity(plain_a, plain_b)
        self.assertIsInstance(aff_fallback, float)
        self.assertTrue(0.0 <= aff_fallback <= 1.0)

    def test_select_neighbor_sequence(self):
        candidates = [
            {"id": "red_1", "color_profile": "#FF0000", "subject_tags": ["ruby", "fire"]},
            {"id": "red_2", "color_profile": "#E00000", "subject_tags": ["ruby", "flame"]},
            {"id": "orange", "color_profile": "#FFA500", "subject_tags": ["fire", "sun"]},
            {"id": "blue_1", "color_profile": "#0000FF", "subject_tags": ["ocean", "water"]},
            {"id": "blue_2", "color_profile": "#0020EE", "subject_tags": ["ocean", "ice"]},
            {"id": "green_1", "color_profile": "#00FF00", "subject_tags": ["leaf", "forest"]},
        ]

        seq = select_neighbor_sequence(candidates, panel_count=5, seed=0)
        self.assertEqual(len(seq), 5)

        # Check pairing of clip and viewport
        for panel in seq:
            self.assertIsInstance(panel, AmalgamatedPanel)
            self.assertIn("id", panel.clip)
            self.assertIsInstance(panel.viewport, SliceRect)
            self.assertFalse(panel.viewport.is_full_frame)
            # Tuple unpacking
            clip, vp = panel
            self.assertEqual(clip, panel.clip)
            self.assertEqual(vp, panel.viewport)
            # Property and dict access
            self.assertEqual(panel.slice_rect, panel.viewport)
            self.assertEqual(panel["viewport"], panel.viewport)
            self.assertEqual(panel["clip"], panel.clip)

        # No duplicate clips in sequence
        selected_ids = [p.clip["id"] for p in seq]
        self.assertEqual(len(selected_ids), len(set(selected_ids)))

        # Insufficient candidates raises ValueError
        with self.assertRaises(ValueError):
            select_neighbor_sequence(candidates[:2], panel_count=3)

        # Invalid panel_count raises ValueError
        with self.assertRaises(ValueError):
            select_neighbor_sequence(candidates, panel_count=2)
        with self.assertRaises(ValueError):
            select_neighbor_sequence(candidates, panel_count=11)


class AmalgamatedManifestTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"id": f"clip_{i:02d}", "color": [0.1 * (i % 10), 0.2, 0.5], "tags": [f"theme_{i % 3}"]}
            for i in range(12)
        ]

    def test_export_and_verify_amalgamated_manifest(self):
        for panel_count in (3, 6, 8, 10):
            manifest = export_amalgamated_manifest(
                panel_count=panel_count,
                media_candidates=self.candidates,
                seed=42,
            )
            self.assertEqual(manifest["schema"], AMALGAMATED_MANIFEST_SCHEMA)
            self.assertEqual(manifest["panel_count"], panel_count)
            self.assertEqual(manifest["preview_mode"], "bounded_preview")
            self.assertLessEqual(manifest["active_decoders"], MAX_AMALGAMATED_DECODERS)
            if panel_count <= 6:
                self.assertEqual(manifest["active_decoders"], panel_count)
            else:
                self.assertEqual(manifest["active_decoders"], 6)

            self.assertEqual(len(manifest["panels"]), panel_count)
            for p in manifest["panels"]:
                rect = SliceRect(**p["viewport"])
                self.assertFalse(rect.is_full_frame)

            ok, errors = verify_amalgamated_manifest(manifest)
            self.assertTrue(ok, f"Verification failed for count {panel_count}: {errors}")
            self.assertEqual(errors, [])

    def test_export_rejects_out_of_bounds(self):
        with self.assertRaises(ValueError):
            export_amalgamated_manifest(panel_count=2, media_candidates=self.candidates)
        with self.assertRaises(ValueError):
            export_amalgamated_manifest(panel_count=11, media_candidates=self.candidates)
        with self.assertRaises(ValueError):
            export_amalgamated_manifest(panel_count=5, media_candidates=self.candidates[:4])

    def test_verify_detects_tampering_or_digest_mismatch(self):
        manifest = export_amalgamated_manifest(panel_count=4, media_candidates=self.candidates, seed=123)
        tampered = json.loads(json.dumps(manifest))
        tampered["preview_mode"] = "tampered_preview"
        ok, errors = verify_amalgamated_manifest(tampered)
        self.assertFalse(ok)
        self.assertTrue(any("digest mismatch" in e.lower() for e in errors))

    def test_verify_detects_full_frame_violation(self):
        manifest = export_amalgamated_manifest(panel_count=3, media_candidates=self.candidates, seed=1)
        manifest["panels"][0]["viewport"] = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        payload = {k: v for k, v in manifest.items() if k != "digest"}
        manifest["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        ok, errors = verify_amalgamated_manifest(manifest)
        self.assertFalse(ok)
        self.assertTrue(any("full frame" in e.lower() for e in errors))

    def test_verify_detects_decoder_cap_violation(self):
        manifest = export_amalgamated_manifest(panel_count=4, media_candidates=self.candidates, seed=1)
        manifest["active_decoders"] = 7
        payload = {k: v for k, v in manifest.items() if k != "digest"}
        manifest["digest"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        ok, errors = verify_amalgamated_manifest(manifest)
        self.assertFalse(ok)
        self.assertTrue(any("active_decoders" in e.lower() for e in errors))


class ReviewIdentityTests(unittest.TestCase):
    def test_unset_loop_extensions_preserve_historical_snapshot(self):
        comp=build_artifact001(3)
        for loop in comp.to_dict()['loops']:
            self.assertNotIn('color_profile',loop)
            self.assertNotIn('subject_tags',loop)

    def test_color_profile_json_roundtrip(self):
        from dataclasses import replace
        comp=build_artifact001(3)
        comp=replace(comp,loops=(replace(comp.loops[0],color_profile=(.1,.2,.3)),)+comp.loops[1:])
        self.assertEqual(comp,Composition.from_dict(json.loads(comp.to_json())))

    def test_neighbor_selection_rejects_unidentified_candidates(self):
        from simvltanea.authoring.composition_model import _extract_clip_features
        for value in ({'color':'red'},object()):
            with self.assertRaisesRegex(ValueError,'stable'):
                _extract_clip_features(value)


class CustodyParityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        tools_verify = Path(__file__).resolve().parents[3] / "tools" / "verification" / "verify_custody_parity.py"
        spec = importlib.util.spec_from_file_location("verify_custody_parity", tools_verify)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.evaluate = staticmethod(module.evaluate_custody_parity)

    def test_eligible_retirement_when_parity_and_receipt_verified(self):
        assigned = {
            "path": "simvltanea",
            "head_sha": "abcd1234abcd1234abcd1234abcd1234abcd1234",
            "dirty_files": 0,
            "unpushed_commits": 0,
        }
        receipt = {
            "verified": True,
            "missing_blobs": 0,
            "head_sha": "abcd1234abcd1234abcd1234abcd1234abcd1234",
        }
        candidates = [
            {
                "path": "duplicates/simvltanea-bak",
                "head_sha": "abcd1234abcd1234abcd1234abcd1234abcd1234",
                "dirty_files": 0,
                "untracked_media_count": 0,
            }
        ]
        res = self.evaluate(assigned, candidates, receipt)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["eligible_count"], 1)
        self.assertEqual(res["blocked_count"], 0)
        self.assertTrue(res["duplicates"][0]["eligible_for_retirement"])
        self.assertEqual(res["duplicates"][0]["blocking_reasons"], [])

    def test_blocked_when_duplicate_head_mismatch(self):
        assigned = {
            "path": "simvltanea",
            "head_sha": "1111222233334444555566667777888899990000",
            "dirty_files": 0,
            "unpushed_commits": 0,
        }
        receipt = {
            "verified": True,
            "missing_blobs": 0,
            "head_sha": "1111222233334444555566667777888899990000",
        }
        candidates = [
            {
                "path": "duplicates/simvltanea-stale",
                "head_sha": "9999888877776666555544443333222211110000",
                "dirty_files": 0,
                "untracked_media_count": 0,
            }
        ]
        res = self.evaluate(assigned, candidates, receipt)
        self.assertEqual(res["status"], "GATED")
        self.assertFalse(res["duplicates"][0]["eligible_for_retirement"])
        self.assertTrue(any("does not match canonical HEAD" in r for r in res["duplicates"][0]["blocking_reasons"]))

    def test_blocked_when_duplicate_has_dirty_or_untracked_files(self):
        assigned = {
            "path": "simvltanea",
            "head_sha": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
            "dirty_files": 0,
            "unpushed_commits": 0,
        }
        receipt = {
            "verified": True,
            "missing_blobs": 0,
            "head_sha": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
        }
        candidates = [
            {
                "path": "duplicates/dirty-cand",
                "head_sha": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
                "dirty_files": 2,
                "untracked_media_count": 0,
            },
            {
                "path": "duplicates/untracked-media-cand",
                "head_sha": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
                "dirty_files": 0,
                "untracked_media_count": 5,
            },
        ]
        res = self.evaluate(assigned, candidates, receipt)
        self.assertEqual(res["status"], "GATED")
        self.assertEqual(res["blocked_count"], 2)
        self.assertFalse(res["duplicates"][0]["eligible_for_retirement"])
        self.assertTrue(any("dirty files" in r for r in res["duplicates"][0]["blocking_reasons"]))
        self.assertFalse(res["duplicates"][1]["eligible_for_retirement"])
        self.assertTrue(any("untracked media" in r for r in res["duplicates"][1]["blocking_reasons"]))

    def test_blocked_when_canonical_lacks_clean_parity_or_receipt_unverified(self):
        assigned_dirty = {
            "path": "simvltanea",
            "head_sha": "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
            "dirty_files": 1,
            "unpushed_commits": 0,
        }
        receipt_missing = {
            "verified": False,
            "missing_blobs": 3,
            "head_sha": "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
        }
        candidates = [
            {
                "path": "duplicates/cand-a",
                "head_sha": "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
                "dirty_files": 0,
                "untracked_media_count": 0,
            }
        ]
        res = self.evaluate(assigned_dirty, candidates, receipt_missing)
        self.assertEqual(res["status"], "GATED")
        self.assertFalse(res["canonical_assigned"]["clean_parity"])
        self.assertFalse(res["custody_receipt"]["valid"])
        self.assertFalse(res["duplicates"][0]["eligible_for_retirement"])
        reasons = res["duplicates"][0]["blocking_reasons"]
        self.assertTrue(any("Canonical repository copy lacks clean parity" in r for r in reasons))
        self.assertTrue(any("Custody receipt is unverified" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
