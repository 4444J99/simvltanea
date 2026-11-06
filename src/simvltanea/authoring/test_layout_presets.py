#!/usr/bin/env python3
"""Strips presets: seam tests 1-3, zoom table, strict files, authored byte identity."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path

from simvltanea.authoring import (
    LayoutError,
    adjacency,
    build_artifact001,
    build_strips,
    load_layout_file,
    strips_layouts,
    strips_slice,
    validate_layout_pair,
)
from simvltanea.authoring import artifact001_layouts, composition as c
from simvltanea.authoring.layout_presets import DEFAULT_STRIPS_PRESET, ERROR_CODES

REPO = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parents[1]
EXAMPLE_PRESET = REPO / "examples" / "layout-presets" / "strips.json"
CORPUS = REPO / "fixtures" / "layouts"
COUNTS = range(1, 13)
STYLE_ZERO = {"corner_radius": "0", "lateral_jitter": "0"}
STYLE_MAX = {"corner_radius": "1/20", "lateral_jitter": "1/20"}

# Spec zoom table: N -> (zoom of the exact curve to 2 decimals, stored s).
ZOOM_TABLE = {1: ("8.00", "1/8"), 2: ("5.28", "189/1000"), 3: ("4.14", "121/500"), 5: ("3.05", "41/125"),
              8: ("2.30", "87/200"), 10: ("2.01", "249/500"), 12: ("1.80", "111/200")}

# SHA-256 of build_artifact001(n).to_json(), taken from the code before this change.
AUTHORED_DIGESTS = {
    2: "9e2fa13a9e6572cf1dae086ea66bd4b7d11f0b94a4e649ba94388e5aff5521fa",
    3: "904c19dea2939388464492039b01210298cba7b5c68094c2f413cdae0524257b",
    4: "8b52a934778ff7ecb9cfec5a07fd361ffeb0710f9a62624ef8bcb8e726c7e8a4",
    5: "204414780d9de66f983cac2b603bbbdcf0acca49dc22b99d2fa2f79a4ab49e81",
    6: "9577f7260601afae94927f8ec0c832b6d92d50a97cd9a0b5b210627097081322",
    7: "88aac6693d0bf70f3a1393df78a864ca173182ea311d1a816ecf1c444fc602c2",
}
# SHA-256 of canonical_json(from_authoring_model(build_artifact001(n), sources())), also from before.
AUTHORED_STATE_DIGESTS = {
    2: "c177d1e3282ae0ceb6b7bce729aad61b24ece1e2b6cb598bdfc4881f513b3193",
    3: "d131213b31fc2c6a9d00985edeae613ac0425fe8cfa49033869f7c2776ed35d4",
    4: "b3c749c0a73c5f31107464fb52d6aba30aabef9fc4460ae09431eb7426846087",
    5: "305f8a6c606bdef4a90bc02f6db77e3df477b4b30fe2717dc8df96d1b390e498",
    6: "62743ffa6a6c0243dcfaed48b2dcaa709114a2a476a88f024d3b66dd5565484f",
    7: "3d399b93ce39b61bf74bb4db0e2648e05b0a5d69bb83476599c73b42c2fd45f9",
}


def sources(count):
    return {f"fixtures/loop-{i + 1}.mp4": dict(id=f"source-{i + 1}", path=f"media/source-{i + 1}.mp4",
                                                sha256=f"{i + 1:064x}", kind="video", duration="8")
            for i in range(count)}


def preset(**changes):
    value = copy.deepcopy(DEFAULT_STRIPS_PRESET)
    value.update(copy.deepcopy(changes))
    return value


def weighted(style=STYLE_ZERO):
    # Non-equal weights for every count, mixing integers and rationals.
    by_count = {str(n): [str(Fraction(k + 1, 1 + k % 3)) for k in range(n)] for n in COUNTS}
    return preset(weights={"default": "equal", "by_count": by_count}, style=style)


def boxes_by_loop(layout):
    cells = sorted(layout["cells"], key=lambda cell: int(cell["loop"].split("-")[1]))
    return [tuple(Fraction(v) for v in cell["rect"]) for cell in cells]


def raises_code(test, code, function, *args, **kwargs):
    with test.assertRaises(LayoutError) as caught:
        function(*args, **kwargs)
    test.assertEqual(caught.exception.code, code, str(caught.exception))
    return str(caught.exception)


class SeamGeometryTests(unittest.TestCase):
    variants = {"default": preset(), "weighted": weighted(), "default-style-max": preset(style=STYLE_MAX),
                "weighted-style-max": weighted(STYLE_MAX)}

    def test_seam_1_exact_shared_edges(self):
        for label, value in self.variants.items():
            for n in COUNTS:
                weights = [Fraction(w) for w in value["weights"]["by_count"].get(str(n), ["1"] * n)]
                expected = [sum(weights[:k], Fraction(0)) / sum(weights) for k in range(n + 1)]
                layouts = strips_layouts(n, value)
                for orientation, layout in layouts.items():
                    with self.subTest(variant=label, n=n, orientation=orientation):
                        rows = orientation == "portrait"
                        boxes = boxes_by_loop(layout)
                        starts = [y if rows else x for x, y, w, h in boxes]
                        ends = [(y + h) if rows else (x + w) for x, y, w, h in boxes]
                        for k in range(n - 1):
                            self.assertIsInstance(ends[k], Fraction)
                            self.assertEqual(ends[k], starts[k + 1])
                        self.assertEqual(starts, expected[:-1])
                        self.assertEqual(ends, expected[1:])
                        self.assertEqual(starts[0], 0)
                        self.assertEqual(ends[-1], 1)
                        for x, y, w, h in boxes:  # full span across the other axis, no margin
                            self.assertEqual((x, w) if rows else (y, h), (0, 1))
                        for cell in layout["cells"]:  # serialized in lowest terms
                            self.assertEqual(cell["rect"], [str(Fraction(v)) for v in cell["rect"]])

    def test_seam_2_coverage(self):
        for label, value in self.variants.items():
            for n in COUNTS:
                layouts = strips_layouts(n, value)
                validate_layout_pair(layouts, {f"loop-{k + 1}" for k in range(n)})
                for orientation, layout in layouts.items():
                    with self.subTest(variant=label, n=n, orientation=orientation):
                        self.assertIs(layout["full_bleed"], True)
                        boxes = boxes_by_loop(layout)
                        self.assertEqual(sum(w * h for _, _, w, h in boxes), 1)
                        for x, y, w, h in boxes:
                            self.assertTrue(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1)
                        for i, (x, y, w, h) in enumerate(boxes):
                            for a, b, cw, ch in boxes[i + 1:]:
                                self.assertFalse(x < a + cw and a < x + w and y < b + ch and b < y + h)
                        self.assertTrue(all(cell["fit"] == "cover" for cell in layout["cells"]))

    def test_seam_2_negative_cases(self):
        def broken(n, mutate):
            layouts = strips_layouts(n)
            mutate(layouts)
            return layouts
        loops = {f"loop-{k + 1}" for k in range(5)}

        def gap(layouts):  # 1/10^9 gap at the first seam
            layouts["portrait"]["cells"][0]["rect"][3] = str(Fraction(1, 5) - Fraction(1, 10**9))
        message = raises_code(self, "full-bleed-coverage", validate_layout_pair, broken(5, gap), loops)
        self.assertIn("999999999/1000000000", message)

        def margin(layouts):
            for k, cell in enumerate(layouts["landscape"]["cells"]):
                cell["rect"] = [str(Fraction(k, 5) + Fraction(1, 100)), "1/100", "9/50", "49/50"]
        raises_code(self, "full-bleed-coverage", validate_layout_pair, broken(5, margin), loops)
        raises_code(self, "full-bleed-fit", validate_layout_pair,
                    broken(5, lambda l: l["portrait"]["cells"][2].__setitem__("fit", "contain")), loops)
        raises_code(self, "full-bleed-fit", strips_layouts, 5, preset(fit="contain"))
        # Without the declarations, the same margin layout is an ordinary valid layout.
        undeclared = broken(5, margin)
        undeclared["landscape"]["full_bleed"] = False
        raises_code(self, "overlap-px-no-shared-edge", validate_layout_pair, undeclared, loops)
        del undeclared["landscape"]["presentation"]
        validate_layout_pair(undeclared, loops)

    def test_seam_3_overlap_bounds(self):
        loops = {f"loop-{k + 1}" for k in range(3)}
        for value in range(0, 9):
            layouts = strips_layouts(3)
            layouts["portrait"]["presentation"]["overlap_px"] = value
            validate_layout_pair(layouts, loops)
        for value in (-1, 9, 2.5, 2.0, "2", True, None):
            with self.subTest(overlap_px=value):
                layouts = strips_layouts(3)
                layouts["portrait"]["presentation"]["overlap_px"] = value
                raises_code(self, "overlap-px", validate_layout_pair, layouts, loops)
                raises_code(self, "overlap-px", strips_layouts, 3, preset(overlap_px=value))
        single = strips_layouts(1)
        self.assertEqual(single["portrait"]["presentation"]["overlap_px"], 0)
        single["portrait"]["presentation"]["overlap_px"] = 2
        raises_code(self, "overlap-px-no-shared-edge", validate_layout_pair, single, {"loop-1"})
        apart = strips_layouts(2)
        apart["portrait"]["cells"][0]["rect"] = ["0", "0", "1", "2/5"]
        apart["portrait"]["full_bleed"] = False
        raises_code(self, "overlap-px-no-shared-edge", validate_layout_pair, apart, {"loop-1", "loop-2"})

    def test_reverse_order_keeps_loop_on_strip(self):
        value = preset(orientations={"portrait": {"order": "reverse"}, "landscape": {"direction": "rows"}})
        layouts = strips_layouts(4, value)
        portrait = layouts["portrait"]["cells"]
        self.assertEqual([cell["loop"] for cell in portrait], ["loop-4", "loop-3", "loop-2", "loop-1"])
        self.assertEqual(portrait[0]["rect"], ["0", "3/4", "1", "1/4"])
        self.assertEqual(layouts["landscape"]["cells"][1]["rect"], ["0", "1/4", "1", "1/4"])
        self.assertEqual({e["edge"] for e in adjacency(portrait)}, {"top"})

    def test_style_parameters(self):
        layouts = strips_layouts(12, preset(style=STYLE_MAX, overlap_px=8))
        for orientation, layout in layouts.items():
            self.assertEqual(layout["presentation"], {"overlap_px": 8, "corner_radius": "1/20",
                                                      "lateral_jitter": "1/20"})
            offsets = [Fraction(cell["lateral_offset"]) for cell in layout["cells"]]
            self.assertTrue(all(abs(v) <= Fraction(1, 20) and (v * 1000).denominator == 1 for v in offsets))
            self.assertGreater(len(set(offsets)), 1)
        self.assertEqual(layouts, strips_layouts(12, preset(style=STYLE_MAX, overlap_px=8)))  # deterministic
        self.assertNotIn("lateral_offset", strips_layouts(12)["portrait"]["cells"][0])
        single = strips_layouts(1, preset(style=STYLE_MAX))["portrait"]
        self.assertEqual(single["presentation"], {"overlap_px": 0, "corner_radius": "0", "lateral_jitter": "1/20"})
        raises_code(self, "corner-radius", strips_layouts, 3, preset(style={"corner_radius": "1/19"}))
        raises_code(self, "lateral-jitter", strips_layouts, 3, preset(style={"lateral_jitter": "-1/100"}))
        loops = {f"loop-{k + 1}" for k in range(3)}
        bad = strips_layouts(3, preset(style=STYLE_MAX))
        bad["portrait"]["cells"][1]["lateral_offset"] = "51/1000"
        raises_code(self, "lateral-offset", validate_layout_pair, bad, loops)
        missing = strips_layouts(3, preset(style=STYLE_MAX))
        del missing["landscape"]["cells"][0]["lateral_offset"]
        raises_code(self, "lateral-offset", validate_layout_pair, missing, loops)

    def test_corner_rule(self):
        loops = {"loop-1", "loop-2", "loop-3"}
        # loop-2 spans the bottom half; only loop-1 (left half) is drawn before it, so the
        # top-right corner of loop-2 would round with nothing beneath it.
        layouts = strips_layouts(3)
        layouts["portrait"]["cells"] = [
            {"loop": "loop-1", "rect": ["0", "0", "1/2", "1/2"], "fit": "cover", "focal": ["1/2", "1/2"]},
            {"loop": "loop-2", "rect": ["0", "1/2", "1", "1/2"], "fit": "cover", "focal": ["1/2", "1/2"]},
            {"loop": "loop-3", "rect": ["1/2", "0", "1/2", "1/2"], "fit": "cover", "focal": ["1/2", "1/2"]},
        ]
        validate_layout_pair(layouts, loops)
        layouts["portrait"]["presentation"]["corner_radius"] = "1/40"
        message = raises_code(self, "corner-rule", validate_layout_pair, layouts, loops)
        self.assertIn("cell 1", message)
        # Drawing both upper cells first gives every rounded corner an earlier neighbour.
        cells = layouts["portrait"]["cells"]
        cells[1], cells[2] = cells[2], cells[1]
        validate_layout_pair(layouts, loops)

    def test_corner_rule_needs_earlier_spans_along_the_whole_radius(self):
        loops = {f"loop-{k + 1}" for k in range(5)}

        def pair(edge):
            # Two thin upper cells at the corners, then the wide bottom cell, then the upper filling.
            layouts = strips_layouts(5, preset(style={"corner_radius": "1/20", "lateral_jitter": "0"}))
            rects = [["0", "0", edge, "1/2"], [str(1 - Fraction(edge)), "0", edge, "1/2"], ["0", "1/2", "1", "1/2"],
                     [edge, "0", "1/50", "1/2"], [str(Fraction(edge) + Fraction(1, 50)), "0",
                                                  str(1 - 2 * Fraction(edge) - Fraction(1, 50)), "1/2"]]
            for cell, rect in zip(layouts["portrait"]["cells"], rects):
                cell["rect"] = rect
            return layouts

        # A 1/100 corner cell backs the wide cell's rounded corner for 1/100 of the width, not the 1/20
        # radius: the rest of the cutout would show the canvas behind the depth-only bleed.
        message = raises_code(self, "corner-rule", validate_layout_pair, pair("1/100"), loops)
        self.assertIn("cell 2", message)
        self.assertIn("rounded top corner at 0 has earlier-drawn neighbours beneath only 1/100 from it, "
                      "less than corner_radius 1/20", message)
        # Exactly the radius is enough; so is a whole side shorter than the radius (cell 3's 1/50 bottom).
        validate_layout_pair(pair("1/20"), loops)


class ZoomTests(unittest.TestCase):
    def test_zoom_table(self):
        for n, (zoom, stored) in ZOOM_TABLE.items():
            with self.subTest(n=n):
                self.assertEqual(strips_slice(n), {"enabled": True, "width": stored, "height": stored})
                self.assertEqual(f"{8 / n ** 0.6:.2f}", zoom)
                s = Fraction(stored)
                self.assertLess(abs(1 / s / (8 / n ** 0.6) - 1), 0.005)  # quantum error only

    def test_curve_is_exact_and_masking(self):
        getcontext().prec = 60
        previous = Fraction(0)
        for n in COUNTS:
            s = Fraction(strips_slice(n)["width"])
            exact = Decimal(1000) * Decimal(n) ** (Decimal(3) / Decimal(5)) / Decimal(8)
            self.assertEqual(s, Fraction(int((exact + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR")), 1000))
            self.assertTrue(0 < s <= Fraction(9, 10) and s * s < 1)
            self.assertGreaterEqual(s, previous)  # zoom falls as N rises
            previous = s

    def test_minimum_zoom_and_table(self):
        flat = preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "z1": "1"})
        self.assertEqual({strips_slice(n, flat)["width"] for n in COUNTS}, {"9/10"})
        table = preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "table": {"5": "1/2"}})
        self.assertEqual(strips_slice(5, table)["width"], "1/2")
        self.assertEqual(strips_slice(6, table), strips_slice(6))
        raises_code(self, "zoom", strips_slice, 5, preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "table": {"5": "19/20"}}))
        raises_code(self, "zoom", strips_slice, 5, preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "min_zoom": "1"}))
        raises_code(self, "zoom", strips_slice, 5, preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "curve": "linear"}))

    def test_preset_object_validates_every_count(self):
        # A preset object is checked like a preset file: every count it advertises must expand.
        coarse = preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "quantum": 2})
        for function in (strips_slice, strips_layouts, build_strips):
            with self.subTest(function=function.__name__):
                raises_code(self, "zoom", function, 5, coarse)
        narrowed = preset(counts={"min": 5, "max": 12}, zoom={**DEFAULT_STRIPS_PRESET["zoom"], "quantum": 2})
        self.assertEqual(strips_slice(5, narrowed)["width"], "1/2")


class SelectionTests(unittest.TestCase):
    def test_spec_examples(self):
        presentation = {"overlap_px": 2, "corner_radius": "0", "lateral_jitter": "0"}
        for n in (3, 5):
            unit = f"1/{n}"
            expected = {}
            for orientation in ("portrait", "landscape"):
                cells = []
                for k in range(n):
                    start = str(Fraction(k, n))
                    rect = ["0", start, "1", unit] if orientation == "portrait" else [start, "0", unit, "1"]
                    cells.append({"loop": f"loop-{k + 1}", "rect": rect, "fit": "cover", "focal": ["1/2", "1/2"]})
                expected[orientation] = {"name": f"strips-{n}-{orientation}", "full_bleed": True,
                                         "presentation": presentation, "cells": cells}
            self.assertEqual(json.dumps(strips_layouts(n)), json.dumps(expected))
        self.assertEqual(strips_slice(5), {"enabled": True, "width": "41/125", "height": "41/125"})
        self.assertEqual(strips_slice(3)["width"], "121/500")

    def test_states_validate_for_every_supported_count(self):
        for n in COUNTS:
            with self.subTest(n=n):
                state = build_strips(n)
                c.validate_state(state)
                self.assertEqual(state["layouts"], strips_layouts(n))
                self.assertEqual(state["slice"], strips_slice(n))
                for orientation, (w, h) in (("portrait", (360, 780)), ("landscape", (1280, 720))):
                    layout = c.presentation_at(state, 0, w, h)["layout"]
                    self.assertEqual(layout["name"], f"strips-{n}-{orientation}")
                    placed = c.pixel_placements(layout, w, h)
                    self.assertEqual(sum(p.width * p.height for p in placed), w * h)
                portable = json.loads(json.dumps(state))
                self.assertEqual(portable, state)

    def test_counts_outside_range_are_refused(self):
        for n in (0, 13, -1, 32):
            with self.subTest(n=n):
                for function in (strips_layouts, strips_slice, build_strips):
                    message = raises_code(self, "count-range", function, n)
                    self.assertIn("N=1..12", message)
        for n in (True, 5.0, "5"):
            raises_code(self, "count-range", strips_layouts, n)
        raises_code(self, "preset", strips_layouts, 5, "authored")
        raises_code(self, "preset", strips_layouts, 5, "grid")

    def test_move_event_cannot_break_declared_full_bleed(self):
        state = build_strips(3)
        state["events"] = [dict(op="move", frame=10, loop="loop-1", orientation="portrait",
                                rect=["0", "0", "1", "1/4"])]
        with self.assertRaisesRegex(c.StateError, "full_bleed"):
            c.validate_state(state)

    def test_build_strips_binds_given_sources(self):
        given = list(sources(3).values())
        state = build_strips(3, sources=given)
        self.assertEqual(state["sources"], given)
        self.assertEqual([loop["bank"] for loop in state["loops"]], [["source-1"], ["source-2"], ["source-3"]])
        self.assertEqual([loop["rate"] for loop in state["loops"]], ["1", "107/100", "57/50"])
        raises_code(self, "cell-count", build_strips, 3, sources=given[:2])
        raises_code(self, "wrong-type", build_strips, 3, sources=[{"path": "x.mp4"}] * 3)

    def test_adjacency(self):
        portrait = strips_layouts(3)["portrait"]["cells"]
        self.assertEqual(c.canonical_json(adjacency(portrait)),
                         '[{"a":0,"b":1,"edge":"bottom","span":["0","1"]},'
                         '{"a":1,"b":2,"edge":"bottom","span":["0","1"]}]')
        self.assertEqual(adjacency(strips_layouts(1)["portrait"]["cells"]), [])
        self.assertEqual([e["edge"] for e in adjacency(strips_layouts(3)["landscape"]["cells"])], ["right", "right"])
        grid = [{"rect": r} for r in (["0", "0", "1/2", "1/2"], ["1/2", "0", "1/2", "1/2"],
                                     ["0", "1/2", "1/2", "1/2"], ["1/2", "1/2", "1/2", "1/2"])]
        self.assertEqual([(e["a"], e["b"], e["edge"], e["span"]) for e in adjacency(grid)],
                         [(0, 1, "right", ["0", "1/2"]), (0, 2, "bottom", ["0", "1/2"]),
                          (1, 3, "bottom", ["1/2", "1"]), (2, 3, "right", ["1/2", "1"])])
        corner_only = [{"rect": ["0", "0", "1/2", "1/2"]}, {"rect": ["1/2", "1/2", "1/2", "1/2"]}]
        self.assertEqual(adjacency(corner_only), [])


class AuthoredRegressionTests(unittest.TestCase):
    def test_authored_output_is_byte_identical(self):
        self.assertEqual(sorted(artifact001_layouts.AUTHORED), [2, 3, 4, 5, 6, 7])
        self.assertEqual(artifact001_layouts.AUTHORED, artifact001_layouts._AUTHORED_DEFAULT)
        for n, digest in AUTHORED_DIGESTS.items():
            self.assertEqual(hashlib.sha256(build_artifact001(n).to_json().encode()).hexdigest(), digest, n)
        for n, digest in AUTHORED_STATE_DIGESTS.items():
            state = c.from_authoring_model(build_artifact001(n), sources(n))
            self.assertEqual(hashlib.sha256(c.canonical_json(state).encode()).hexdigest(), digest, n)

    def test_authored_guard_is_unchanged(self):
        for n in (1, 8, 13):
            with self.assertRaisesRegex(ValueError, "no reviewed engineering layout pair"):
                build_artifact001(n)

    def test_no_swallowed_errors(self):
        text = (PACKAGE / "authoring" / "artifact001_layouts.py").read_text()
        self.assertNotIn("except Exception", text)
        self.assertNotIn("layouts.json\").read", text)

    def test_legacy_layout_messages_are_unchanged(self):
        base = c.from_authoring_model(build_artifact001(3), sources(3))
        portrait = lambda s: s["layouts"]["portrait"]
        cases = {
            "layouts: unsupported fields ['square']": lambda s: s["layouts"].__setitem__("square", {}),
            "layouts: missing fields ['landscape']": lambda s: s["layouts"].pop("landscape"),
            "portrait must be an object": lambda s: s["layouts"].__setitem__("portrait", []),
            "portrait: unsupported fields ['z']": lambda s: portrait(s).__setitem__("z", 1),
            "portrait: unsupported fields ['fullbleed']": lambda s: portrait(s).__setitem__("fullbleed", True),
            "portrait: missing fields ['name']": lambda s: portrait(s).pop("name"),
            "layout name is required": lambda s: portrait(s).__setitem__("name", ""),
            "cells must be an array": lambda s: portrait(s).__setitem__("cells", {}),
            "cell: unsupported fields ['z']": lambda s: portrait(s)["cells"][1].__setitem__("z", 0),
            "cell: missing fields ['focal']": lambda s: portrait(s)["cells"][1].pop("focal"),
            "cell.loop: invalid ID": lambda s: portrait(s)["cells"][1].__setitem__("loop", "bad id"),
            "only contain/cover fit is implemented": lambda s: portrait(s)["cells"][1].__setitem__("fit", "fill"),
            "focal needs two coordinates": lambda s: portrait(s)["cells"][1].__setitem__("focal", ["1/2"]),
            "focal must be in 0..1": lambda s: portrait(s)["cells"][1].__setitem__("focal", ["3/2", "0"]),
            "focal must be an integer or rational string, not a float":
                lambda s: portrait(s)["cells"][1].__setitem__("focal", [0.5, "0"]),
            "rect must be [x,y,width,height]": lambda s: portrait(s)["cells"][1].__setitem__("rect", ["0", "0", "1"]),
            "rect must be an integer or rational string, not a float":
                lambda s: portrait(s)["cells"][1].__setitem__("rect", [0.1, "0", "1/2", "1/2"]),
            "rect: invalid rational": lambda s: portrait(s)["cells"][1].__setitem__("rect", ["x", "0", "1/2", "1/2"]),
            "rect must have positive area inside the unit canvas":
                lambda s: portrait(s)["cells"][1].__setitem__("rect", ["0", "0", "2", "1/2"]),
            "overlapping/occluded panels are not supported in schema v1":
                lambda s: portrait(s)["cells"][1].__setitem__("rect", ["0", "0", "1/2", "1/2"]),
            "each orientation must map every loop exactly once": lambda s: portrait(s)["cells"].pop(),
        }
        for message, mutate in cases.items():
            with self.subTest(message=message):
                state = copy.deepcopy(base)
                mutate(state)
                with self.assertRaises(c.StateError) as caught:
                    c.validate_state(state)
                self.assertEqual(str(caught.exception), message)


class StrictFileTests(unittest.TestCase):
    def test_example_preset_is_the_default(self):
        self.assertEqual(json.loads(EXAMPLE_PRESET.read_text()), DEFAULT_STRIPS_PRESET)
        self.assertEqual(load_layout_file(EXAMPLE_PRESET), DEFAULT_STRIPS_PRESET)
        self.assertEqual(strips_layouts(7, EXAMPLE_PRESET), strips_layouts(7))

    def test_conformance_corpus(self):
        manifest = json.loads((CORPUS / "corpus.json").read_text())
        self.assertEqual(manifest["format"], "simvltanea.layout-corpus/1")
        listed = set(manifest["valid"]) | set(manifest["invalid"])
        present = {path.relative_to(CORPUS).as_posix() for path in CORPUS.glob("*/*.json")}
        self.assertEqual(listed, present)
        self.assertTrue(manifest["valid"] and manifest["invalid"])
        self.assertLessEqual(set(manifest["invalid"].values()), ERROR_CODES)
        for name in manifest["valid"]:
            with self.subTest(valid=name):
                load_layout_file(CORPUS / name)
        for name, code in manifest["invalid"].items():
            with self.subTest(invalid=name):
                message = raises_code(self, code, load_layout_file, CORPUS / name)
                self.assertTrue(message.startswith(str(CORPUS / name)), message)

    def test_pair_cell_count_is_checked_before_geometry(self):
        # The pairwise overlap loop is quadratic, so a wrong count must be refused before any geometry.
        cell = {"loop": "loop-1", "rect": ["0", "0", "1", "1"], "fit": "cover", "focal": ["1/2", "1/2"]}
        two = [cell, {**cell, "loop": "loop-2"}]
        layout = lambda name: {"name": name, "cells": two}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "count.json"
            path.write_text(json.dumps({"format": "simvltanea.layout-pair/1", "count": 1,
                                        "portrait": layout("p"), "landscape": layout("l")}))
            message = raises_code(self, "cell-count", load_layout_file, path)
            self.assertIn("count 1, portrait: has 2 cells, expected 1", message)

    def test_state_validation_refuses_a_wrong_cell_count_before_geometry(self):
        # 200 identical, overlapping cells for two loops: the count is compared with the loops first, so the
        # error is the mapping error, not the overlap error the quadratic loop would raise (and takes no time).
        cell = {"loop": "loop-1", "rect": ["0", "0", "1", "1"], "fit": "cover", "focal": ["1/2", "1/2"]}
        cells = [{**cell, "loop": f"loop-{index % 2 + 1}"} for index in range(200)]
        pair = {"portrait": {"name": "p", "cells": cells}, "landscape": {"name": "l", "cells": cells}}
        message = raises_code(self, "mapping", validate_layout_pair, pair, {"loop-1", "loop-2"})
        self.assertIn("each orientation must map every loop exactly once", message)

    def test_oversized_count_keys_are_coded_errors_with_a_bounded_message(self):
        # int() raises a plain ValueError for digit strings over 4300 characters on Python 3.12.
        huge = "1" * 5000
        cases = (
            ("weights", preset(weights={"default": "equal", "by_count": {huge: ["1", "1"]}})),
            ("focal", preset(focal={**DEFAULT_STRIPS_PRESET["focal"], "by_index": {huge: ["1/2", "1/2"]}})),
            ("zoom", preset(zoom={**DEFAULT_STRIPS_PRESET["zoom"], "table": {huge: "1/2"}})),
        )
        for code, value in cases:
            with self.subTest(code=code):
                message = raises_code(self, code, strips_slice, 2, value)
                self.assertLess(len(message), 400, len(message))

    def test_weights_outside_state_rationals_are_refused_at_parse(self):
        for weights in (["1", "1/1000000000"], ["1000000000", "1"]):
            with self.subTest(weights=weights):
                message = raises_code(self, "weights", strips_layouts, 2,
                                      preset(weights={"default": "equal", "by_count": {"2": weights}}))
                self.assertIn("count 2", message)
        # The largest legal neighbour is still accepted.
        strips_layouts(2, preset(weights={"default": "equal", "by_count": {"2": ["999999999", "1"]}}))

    def test_oversized_integer_is_a_coded_json_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.json"
            path.write_text('{"format": "simvltanea.layout-pair/1", "count": ' + "1" * 5000 + "}")
            message = raises_code(self, "json", load_layout_file, path)
            self.assertTrue(message.startswith(str(path)), message)
            path.write_text('{"a": 1, "a": 2}')
            self.assertIn("duplicate JSON key", raises_code(self, "json", load_layout_file, path))

    def test_errors_name_file_count_orientation_and_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mine.json"
            path.write_text('{"format": "simvltanea.layout-pair/1", "count": 2,')
            message = raises_code(self, "json", load_layout_file, path)
            self.assertIn(str(path), message)
            path.write_text(json.dumps(preset(gutter="1/100")))
            message = raises_code(self, "unknown-key", load_layout_file, path)
            self.assertIn(str(path), message)
            self.assertIn("gutter", message)
            pair = {"format": "simvltanea.layout-pair/1", "count": 3, **strips_layouts(3)}
            pair["landscape"]["cells"][2]["focal"] = ["1/2", "2"]
            path.write_text(json.dumps(pair))
            message = raises_code(self, "focal", load_layout_file, path)
            self.assertEqual(message, f"{path}, count 3, landscape, cell 2: focal must be in 0..1")
            path.write_text(json.dumps(preset(weights={"default": "equal", "by_count": {"4": ["1", 2, 0.5, "1"]}})))
            message = raises_code(self, "weights", load_layout_file, path)
            self.assertIn(f"{path}, count 4:", message)
            path.write_text(json.dumps(preset(weights={"default": "equal", "by_count": {"13": ["1"] * 13}})))
            raises_code(self, "weights", load_layout_file, path)
            missing = Path(tmp) / "absent.json"
            self.assertIn(str(missing), raises_code(self, "json", load_layout_file, missing))
            raises_code(self, "json", strips_layouts, 3, missing)

    def test_ambient_override_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "layouts.json"
            artifact001_layouts.refuse_ambient_override(target)
            target.write_text("{}")
            with self.assertRaises(artifact001_layouts.AmbientLayoutOverrideError) as caught:
                artifact001_layouts.refuse_ambient_override(target)
            self.assertIn(str(target), str(caught.exception))
            self.assertIn("load_layout_file(path)", str(caught.exception))
            # A real import of a package copy with the file present fails, naming the file.
            copy_root = Path(tmp) / "src"
            shutil.copytree(PACKAGE, copy_root / "simvltanea",
                            ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
            ambient = copy_root / "simvltanea" / "layouts.json"
            ambient.write_text('{"3": {"portrait": [[0, 0, 1, 1]], "landscape": [[0, 0, 1, 1]]}}')
            env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
            env["PYTHONPATH"] = str(copy_root)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run([sys.executable, "-c", "import simvltanea.authoring"], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=120)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AmbientLayoutOverrideError", result.stderr)
            self.assertIn(str(ambient.resolve()), result.stderr)
            ambient.unlink()
            result = subprocess.run([sys.executable, "-c", "import simvltanea.authoring as a; print(sorted(a.AUTHORED))"],
                                    cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "[2, 3, 4, 5, 6, 7]")


if __name__ == "__main__":
    unittest.main()
