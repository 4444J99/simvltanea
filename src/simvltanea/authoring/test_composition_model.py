#!/usr/bin/env python3
from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()


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
