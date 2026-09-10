#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

from artifact001_layouts import AUTHORED, build_artifact001
from composition_model import Composition


class CompositionModelTests(unittest.TestCase):
    def test_acceptance_matrix_has_authored_pairs(self):
        self.assertEqual(set(AUTHORED), {3, 4, 5, 6})
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
            build_artifact001(7)


if __name__ == "__main__":
    unittest.main()
