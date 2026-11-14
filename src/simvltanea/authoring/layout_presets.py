"""Full-bleed layout presets: the strips family, its zoom curve and the layout validator.

Strips are exact rational partitions of the unit square, written straight into state
layouts as ``Fraction`` strings (never through the float ``Placement`` model). Zoom is
the state-wide ``slice`` with ``width = height = s(N)``, so magnification over plain
cover is exactly ``1/s``. Presets are data (``simvltanea.layout-preset/1``); explicit
pairs use ``simvltanea.layout-pair/1``. Both are read only from paths the caller names.

``validate_layout_pair`` is the single reference validator: ``validate_layouts`` in
``composition.py`` and ``tools.verification.verify_layouts`` both call it. Every error is
a ``LayoutError`` carrying a stable ``code``; nothing is swallowed.

Strips and the zoom curve are engineering presets, not artist-approved designs.
See ``docs/plans/2026-11-05-full-bleed-layout-presets.md``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from simvltanea.authoring.composition import (
    ENGINE_VERSION,
    ID,
    ORIENTATIONS,
    RNG,
    SCHEMA_VERSION,
    StateError,
    canonical_json,
    rational,
    validate_slice,
    validate_state,
)

PRESET_FORMAT = "simvltanea.layout-preset/1"
PAIR_FORMAT = "simvltanea.layout-pair/1"
FAMILY_STRIPS = "strips"
FAMILY_AUTHORED = "authored"
STRIPS_MIN_COUNT = 1
STRIPS_MAX_COUNT = 12
PAIR_MAX_COUNT = 32  # the engine-wide resource guard of validate_state
OVERLAP_PX_MAX = 8
STYLE_MAX = Fraction(1, 20)
JITTER_QUANTUM = 1000
DIRECTIONS = ("rows", "columns")
ORDERS = ("forward", "reverse")
ZOOM_CURVES = ("power",)
ZOOM_MAX = Fraction(1000)
GAMMA_MAX = Fraction(2)
GAMMA_DENOMINATOR_MAX = 100
QUANTUM_MAX = 10**6
SIDES = ("top", "bottom", "left", "right")
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}

LAYOUT_FIELDS = {"name", "cells", "full_bleed", "presentation"}
CELL_FIELDS = {"loop", "rect", "fit", "focal", "lateral_offset"}
PRESENTATION_FIELDS = {"overlap_px", "corner_radius", "lateral_jitter"}
PRESET_FIELDS = {"format", "name", "family", "counts", "orientations", "weights", "fit", "focal",
                 "full_bleed", "overlap_px", "zoom", "style"}
PAIR_FIELDS = {"format", "count", "portrait", "landscape"}

# The default preset, as data. ``examples/layout-presets/strips.json`` is this object.
DEFAULT_STRIPS_PRESET: dict[str, Any] = {
    "format": PRESET_FORMAT,
    "name": "strips",
    "family": FAMILY_STRIPS,
    "counts": {"min": 1, "max": 12},
    "orientations": {
        "portrait": {"direction": "rows", "order": "forward"},
        "landscape": {"direction": "columns", "order": "forward"},
    },
    "weights": {"default": "equal", "by_count": {}},
    "fit": "cover",
    "focal": {"default": ["1/2", "1/2"], "by_index": {}},
    "full_bleed": True,
    "overlap_px": 2,
    "zoom": {"curve": "power", "z1": "8", "gamma": "3/5", "min_zoom": "10/9", "quantum": 1000, "table": {}},
    "style": {"corner_radius": "0", "lateral_jitter": "0"},
}
BUILTIN_PRESETS: dict[str, dict[str, Any]] = {"strips": DEFAULT_STRIPS_PRESET}

# Error codes shared with the conformance corpus (fixtures/layouts/corpus.json).
ERROR_CODES = frozenset({
    "json", "format", "wrong-type", "unknown-key", "missing-key", "rational", "count-range",
    "cell-count", "loop-id", "mapping", "fit", "focal", "bounds", "overlap", "full-bleed-fit",
    "full-bleed-coverage", "overlap-px", "overlap-px-no-shared-edge", "corner-radius",
    "corner-rule", "lateral-jitter", "lateral-offset", "counts", "orientation", "weights", "zoom",
    "preset",
})


class LayoutError(StateError):
    """An invalid layout, pair file or preset. ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Where:
    """Error location. Without a file or count (state validation), the legacy
    messages of ``validate_layouts`` are emitted unchanged; new checks always say where."""

    source: str | None = None
    count: int | None = None
    orientation: str | None = None
    cell: int | None = None

    @property
    def file_context(self) -> bool:
        return self.source is not None or self.count is not None

    def at(self, **changes: Any) -> "_Where":
        return replace(self, **changes)

    def prefix(self, legacy: bool = False) -> str:
        if legacy and not self.file_context:
            return ""
        parts = []
        if self.source is not None:
            parts.append(self.source)
        if self.count is not None:
            parts.append(f"count {self.count}")
        if self.orientation is not None:
            parts.append(self.orientation)
        if self.cell is not None:
            parts.append(f"cell {self.cell}")
        return ", ".join(parts) + ": " if parts else ""


def _fail(where: _Where, code: str, message: str, legacy: bool = False):
    raise LayoutError(code, where.prefix(legacy) + message)


def _require(condition: Any, where: _Where, code: str, message: str, legacy: bool = False) -> None:
    if not condition:
        _fail(where, code, message, legacy)


def _keys(value: Any, allowed: set[str], required: set[str], label: str, where: _Where,
          legacy: bool = False) -> None:
    _require(isinstance(value, dict), where, "wrong-type", f"{label} must be an object", legacy)
    _require(not (value.keys() - allowed), where, "unknown-key",
             f"{label}: unsupported fields {sorted(value.keys() - allowed)}", legacy)
    _require(not (required - value.keys()), where, "missing-key",
             f"{label}: missing fields {sorted(required - value.keys())}", legacy)


def _rational(value: Any, label: str, where: _Where, code: str = "rational", legacy: bool = False) -> Fraction:
    try:
        return rational(value, label)
    except StateError as exc:
        raise LayoutError(code, where.prefix(legacy) + str(exc)) from exc


def _integer(value: Any, low: int, high: int, label: str, where: _Where, code: str) -> int:
    _require(type(value) is int and low <= value <= high, where, code,
             f"{label} must be an integer in {low}..{high}")
    return value


def _rect(rect: Any, where: _Where) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    # Same rules and messages as composition.rect_values, with error codes.
    _require(isinstance(rect, list) and len(rect) == 4, where, "wrong-type",
             "rect must be [x,y,width,height]", legacy=True)
    x, y, w, h = (_rational(item, "rect", where, legacy=True) for item in rect)
    _require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1, where, "bounds",
             "rect must have positive area inside the unit canvas", legacy=True)
    return x, y, w, h


def _shared_edges(boxes: list[tuple[Fraction, ...]]) -> list[dict[str, Any]]:
    result = []
    for i, (x, y, w, h) in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            a, b, c, d = boxes[j]
            horizontal = (max(x, a), min(x + w, a + c))
            vertical = (max(y, b), min(y + h, b + d))
            for edge, touches, (lo, hi) in (("bottom", y + h == b, horizontal), ("top", y == b + d, horizontal),
                                            ("right", x + w == a, vertical), ("left", x == a + c, vertical)):
                if touches and lo < hi:
                    result.append({"a": i, "b": j, "edge": edge, "span": [str(lo), str(hi)]})
    return result


def adjacency(cells: list) -> list[dict[str, Any]]:
    """Exact shared edges between cells, in draw order.

    Each entry says that side ``edge`` of cell ``a`` coincides (``Fraction`` equality)
    with the opposite side of cell ``b`` over the positive-length ``span``; ``a < b``.
    """
    where = _Where()
    if not isinstance(cells, list):
        _fail(where, "wrong-type", "cells must be an array")
    boxes = []
    for index, cell in enumerate(cells):
        _require(isinstance(cell, dict) and "rect" in cell, where.at(cell=index), "wrong-type",
                 "cell must be an object with a rect")
        boxes.append(_rect(cell["rect"], where.at(cell=index)))
    return _shared_edges(boxes)


def _corner_rule(boxes: list[tuple[Fraction, ...]], edges: list[dict[str, Any]], radius: Fraction,
                 where: _Where) -> None:
    # Only corners on a side shared with an earlier-drawn neighbour are rounded; each such
    # corner must have that earlier neighbour's bleed beneath its whole cutout. Along the side
    # the earlier spans must run without a gap from the corner for corner_radius (a fraction
    # of the minor dimension, so at most that fraction of the side's axis) or to the far corner.
    _require(edges, where, "corner-rule",
             "presentation.corner_radius > 0 requires cells that share an edge; no corner can be rounded")
    spans: dict[tuple[int, str], list[tuple[Fraction, Fraction]]] = {}
    for edge in edges:
        side = OPPOSITE[edge["edge"]]
        spans.setdefault((edge["b"], side), []).append(tuple(Fraction(v) for v in edge["span"]))
    for (index, side), covered in sorted(spans.items()):
        x, y, w, h = boxes[index]
        low, high = (x, x + w) if side in ("top", "bottom") else (y, y + h)
        for corner, inward in ((low, True), (high, False)):
            reach, grew = corner, True
            while grew:
                grew = False
                for a, b in covered:
                    if (a <= reach < b) if inward else (a < reach <= b):
                        reach, grew = (b if inward else a), True
            run = abs(reach - corner)
            _require(run > 0, where.at(cell=index), "corner-rule",
                     f"rounded {side} corner at {corner} has no earlier-drawn neighbour beneath it")
            _require(run >= min(radius, high - low), where.at(cell=index), "corner-rule",
                     f"rounded {side} corner at {corner} has earlier-drawn neighbours beneath only {run} "
                     f"from it, less than corner_radius {radius}")


def _validate_layout(layout: Any, loop_ids: set[str] | None, where: _Where) -> list[str]:
    label = "layout" if where.file_context else where.orientation
    _keys(layout, LAYOUT_FIELDS, {"name", "cells"}, label, where, legacy=True)
    _require(isinstance(layout["name"], str) and bool(layout["name"]), where, "wrong-type",
             "layout name is required", legacy=True)
    _require(isinstance(layout["cells"], list), where, "wrong-type", "cells must be an array", legacy=True)
    # Count before geometry: the pairwise overlap loop is quadratic in len(cells). State validation
    # (loop_ids) needs exactly one cell per loop, so a longer array is refused with the same mapping error.
    _require(loop_ids is None or len(layout["cells"]) == len(loop_ids), where, "mapping",
             "each orientation must map every loop exactly once", legacy=True)
    _require(loop_ids is not None or where.count is None or len(layout["cells"]) == where.count, where,
             "cell-count", f"has {len(layout['cells'])} cells, expected {where.count}")
    seen: list[str] = []
    boxes: list[tuple[Fraction, ...]] = []
    for index, cell in enumerate(layout["cells"]):
        at = where.at(cell=index)
        _keys(cell, CELL_FIELDS, {"loop", "rect", "fit", "focal"}, "cell", at, legacy=True)
        _require(isinstance(cell["loop"], str) and bool(ID.fullmatch(cell["loop"])), at, "loop-id",
                 "cell.loop: invalid ID", legacy=True)
        seen.append(cell["loop"])
        _require(cell["fit"] in ("contain", "cover"), at, "fit", "only contain/cover fit is implemented", legacy=True)
        _require(isinstance(cell["focal"], list) and len(cell["focal"]) == 2, at, "focal",
                 "focal needs two coordinates", legacy=True)
        _require(all(0 <= _rational(v, "focal", at, "focal", legacy=True) <= 1 for v in cell["focal"]), at,
                 "focal", "focal must be in 0..1", legacy=True)
        box = _rect(cell["rect"], at)
        x, y, w, h = box
        for a, b, c, d in boxes:
            _require(not (x < a + c and a < x + w and y < b + d and b < y + h), at, "overlap",
                     "overlapping/occluded panels are not supported in schema v1", legacy=True)
        boxes.append(box)
    if loop_ids is not None:
        _require(len(seen) == len(loop_ids) and set(seen) == loop_ids, where, "mapping",
                 "each orientation must map every loop exactly once", legacy=True)
    else:
        _require(len(set(seen)) == len(seen), where, "mapping", "each loop must appear in exactly one cell")

    cells = layout["cells"]
    if "full_bleed" in layout or "presentation" in layout:
        _require(STRIPS_MIN_COUNT <= len(cells) <= STRIPS_MAX_COUNT, where, "count-range",
                 f"full_bleed and presentation are supported for {STRIPS_MIN_COUNT}..{STRIPS_MAX_COUNT} cells, "
                 f"not {len(cells)}")
    if "full_bleed" in layout:
        _require(type(layout["full_bleed"]) is bool, where, "wrong-type", "full_bleed must be boolean")
    if layout.get("full_bleed") is True:
        for index, cell in enumerate(cells):
            _require(cell["fit"] == "cover", where.at(cell=index), "full-bleed-fit",
                     "full_bleed requires fit cover on every cell (contain exposes background)")
        area = sum(w * h for _, _, w, h in boxes)
        _require(area == 1, where, "full-bleed-coverage",
                 f"full_bleed requires the rects to tile the unit square exactly; they cover {area}")
    edges = _shared_edges(boxes)
    jitter = Fraction(0)
    if "presentation" in layout:
        presentation = layout["presentation"]
        _keys(presentation, PRESENTATION_FIELDS, PRESENTATION_FIELDS, "presentation", where)
        overlap = _integer(presentation["overlap_px"], 0, OVERLAP_PX_MAX, "presentation.overlap_px (device pixels)",
                           where, "overlap-px")
        _require(overlap == 0 or edges, where, "overlap-px-no-shared-edge",
                 "presentation.overlap_px > 0 is a bleed across shared edges; this layout has no shared edge")
        radius = _rational(presentation["corner_radius"], "presentation.corner_radius", where, "corner-radius")
        _require(0 <= radius <= STYLE_MAX, where, "corner-radius",
                 "presentation.corner_radius must be in 0..1/20 of the canvas minor dimension")
        if radius:
            _corner_rule(boxes, edges, radius, where)
        jitter = _rational(presentation["lateral_jitter"], "presentation.lateral_jitter", where, "lateral-jitter")
        _require(0 <= jitter <= STYLE_MAX, where, "lateral-jitter",
                 "presentation.lateral_jitter must be in 0..1/20 of the canvas extent along the strip")
    for index, cell in enumerate(cells):
        at = where.at(cell=index)
        if not jitter:
            _require("lateral_offset" not in cell, at, "lateral-offset",
                     "lateral_offset requires presentation.lateral_jitter > 0")
            continue
        _require("lateral_offset" in cell, at, "lateral-offset",
                 "presentation.lateral_jitter > 0 requires a resolved lateral_offset on every cell")
        offset = _rational(cell["lateral_offset"], "lateral_offset", at, "lateral-offset")
        _require(abs(offset) <= jitter, at, "lateral-offset",
                 f"|lateral_offset| must not exceed lateral_jitter {jitter}, got {offset}")
    return seen


def validate_layout_pair(pair: Any, loop_ids: set[str] | None = None, *, source: str | os.PathLike | None = None,
                         count: int | None = None) -> None:
    """Validate a portrait/landscape layout pair; raise ``LayoutError`` on the first problem.

    With ``loop_ids`` (state validation) every orientation must map exactly those loops.
    Without them (layout files) each orientation needs ``count`` distinct loops and both
    orientations must map the same loops. ``source`` and ``count`` name the location in
    every message, together with the orientation and the 0-based cell index.
    """
    where = _Where(source=None if source is None else str(source), count=count)
    _keys(pair, set(ORIENTATIONS), set(ORIENTATIONS), "layouts", where, legacy=True)
    mapped = {orientation: _validate_layout(layout, loop_ids, where.at(orientation=orientation))
              for orientation, layout in pair.items()}
    if loop_ids is None:
        _require(set(mapped["portrait"]) == set(mapped["landscape"]), where, "mapping",
                 "portrait and landscape must map the same loops")


# ---------------------------------------------------------------- presets

@dataclass(frozen=True)
class _Preset:
    name: str
    count_min: int
    count_max: int
    orientations: dict[str, tuple[str, str]]
    weights: dict[int, tuple[Fraction, ...]]
    fit: str
    focal: tuple[Fraction, Fraction]
    focal_by_index: dict[int, tuple[Fraction, Fraction]]
    full_bleed: bool
    overlap_px: int
    z1: Fraction
    gamma: Fraction
    min_zoom: Fraction
    quantum: int
    table: dict[int, Fraction]
    corner_radius: Fraction
    lateral_jitter: Fraction
    source: str | None


def _section(raw: Mapping, key: str, fields: set[str], where: _Where) -> dict[str, Any]:
    default = DEFAULT_STRIPS_PRESET[key]
    if key not in raw:
        return dict(default)
    _keys(raw[key], fields, set(), key, where)
    return {**default, **raw[key]}


def _count_key(key: Any, low: int, high: int, label: str, where: _Where, code: str) -> int:
    # The length check comes first: int() raises a plain ValueError for digit strings over 4300 characters,
    # and every valid key has at most len(str(high)) digits.
    _require(isinstance(key, str) and key.isascii() and key.isdigit() and len(key) <= len(str(high))
             and str(int(key)) == key and low <= int(key) <= high, where, code,
             f"{label} key {str(key)[:40]!r} must be an integer string in {low}..{high}")
    return int(key)


def _focal_pair(value: Any, label: str, where: _Where) -> tuple[Fraction, Fraction]:
    _require(isinstance(value, list) and len(value) == 2, where, "focal", f"{label} needs two coordinates")
    pair = tuple(_rational(v, label, where, "focal") for v in value)
    _require(all(0 <= v <= 1 for v in pair), where, "focal", f"{label} must be in 0..1")
    return pair  # type: ignore[return-value]


def _resolve_preset(raw: Any, source: str | None = None) -> _Preset:
    where = _Where(source=source)
    _keys(raw, PRESET_FIELDS, {"format", "name", "family"}, "preset", where)
    _require(raw["format"] == PRESET_FORMAT, where, "format", f"format must be {PRESET_FORMAT!r}, got {raw['format']!r}")
    name = raw["name"]
    _require(isinstance(name, str) and bool(ID.fullmatch(name)), where, "preset",
             "name must match [A-Za-z0-9_-]{1,80}")
    _require(raw["family"] == FAMILY_STRIPS, where, "preset",
             f"family must be {FAMILY_STRIPS!r} (the authored family is build_artifact001), got {raw['family']!r}")

    counts = _section(raw, "counts", {"min", "max"}, where)
    low = _integer(counts["min"], STRIPS_MIN_COUNT, STRIPS_MAX_COUNT, "counts.min", where, "counts")
    high = _integer(counts["max"], STRIPS_MIN_COUNT, STRIPS_MAX_COUNT, "counts.max", where, "counts")
    _require(low <= high, where, "counts", "counts.min must not exceed counts.max")

    orientations_raw = _section(raw, "orientations", set(ORIENTATIONS), where)
    orientations = {}
    for orientation in ORIENTATIONS:
        default = DEFAULT_STRIPS_PRESET["orientations"][orientation]
        value = orientations_raw[orientation]
        _keys(value, {"direction", "order"}, set(), f"orientations.{orientation}", where)
        value = {**default, **value}
        _require(value["direction"] in DIRECTIONS, where, "orientation",
                 f"orientations.{orientation}.direction must be one of {list(DIRECTIONS)}")
        _require(value["order"] in ORDERS, where, "orientation",
                 f"orientations.{orientation}.order must be one of {list(ORDERS)}")
        orientations[orientation] = (value["direction"], value["order"])

    weights_raw = _section(raw, "weights", {"default", "by_count"}, where)
    _require(weights_raw["default"] == "equal", where, "weights", "weights.default must be 'equal'")
    _require(isinstance(weights_raw["by_count"], dict), where, "wrong-type", "weights.by_count must be an object")
    weights = {}
    for key, value in weights_raw["by_count"].items():
        count = _count_key(key, low, high, "weights.by_count", where, "weights")
        _require(isinstance(value, list) and len(value) == count, where.at(count=count), "weights",
                 f"weights.by_count needs exactly {count} weights")
        parsed = tuple(_rational(v, "weights.by_count", where.at(count=count), "weights") for v in value)
        _require(all(v > 0 for v in parsed), where.at(count=count), "weights", "weights must be positive")
        total = sum(parsed)
        edges = [sum(parsed[:k], Fraction(0)) / total for k in range(count + 1)]
        _require(all(v.denominator <= 10**9 for v in edges + [w / total for w in parsed]),
                 where.at(count=count), "weights",
                 "weights.by_count must give strip edges and sizes with denominators of at most 10**9")
        weights[count] = parsed

    fit = raw.get("fit", DEFAULT_STRIPS_PRESET["fit"])
    _require(fit in ("cover", "contain"), where, "fit", "fit must be 'cover' or 'contain'")
    full_bleed = raw.get("full_bleed", DEFAULT_STRIPS_PRESET["full_bleed"])
    _require(type(full_bleed) is bool, where, "wrong-type", "full_bleed must be boolean")
    _require(not full_bleed or fit == "cover", where, "full-bleed-fit",
             "full_bleed requires fit 'cover' (contain exposes background)")

    focal_raw = _section(raw, "focal", {"default", "by_index"}, where)
    focal = _focal_pair(focal_raw["default"], "focal.default", where)
    _require(isinstance(focal_raw["by_index"], dict), where, "wrong-type", "focal.by_index must be an object")
    focal_by_index = {_count_key(k, 0, high - 1, "focal.by_index", where, "focal"):
                      _focal_pair(v, f"focal.by_index.{k}", where) for k, v in focal_raw["by_index"].items()}

    overlap = _integer(raw.get("overlap_px", DEFAULT_STRIPS_PRESET["overlap_px"]), 0, OVERLAP_PX_MAX,
                       "overlap_px (device pixels)", where, "overlap-px")

    zoom = _section(raw, "zoom", {"curve", "z1", "gamma", "min_zoom", "quantum", "table"}, where)
    _require(zoom["curve"] in ZOOM_CURVES, where, "zoom", f"zoom.curve must be one of {list(ZOOM_CURVES)}")
    z1 = _rational(zoom["z1"], "zoom.z1", where, "zoom")
    _require(0 < z1 <= ZOOM_MAX, where, "zoom", "zoom.z1 must be in (0, 1000]")
    gamma = _rational(zoom["gamma"], "zoom.gamma", where, "zoom")
    _require(0 <= gamma <= GAMMA_MAX and gamma.denominator <= GAMMA_DENOMINATOR_MAX, where, "zoom",
             "zoom.gamma must be in 0..2 with a denominator of at most 100")
    min_zoom = _rational(zoom["min_zoom"], "zoom.min_zoom", where, "zoom")
    _require(1 < min_zoom <= ZOOM_MAX, where, "zoom",
             "zoom.min_zoom must be in (1, 1000] so no panel ever shows a full frame")
    quantum = _integer(zoom["quantum"], 2, QUANTUM_MAX, "zoom.quantum", where, "zoom")
    _require(isinstance(zoom["table"], dict), where, "wrong-type", "zoom.table must be an object")
    table = {}
    largest = Fraction(math.floor(quantum / min_zoom), quantum)
    for key, value in zoom["table"].items():
        count = _count_key(key, low, high, "zoom.table", where, "zoom")
        size = _rational(value, f"zoom.table.{key}", where, "zoom")
        _require(0 < size <= largest and (size * quantum).denominator == 1, where.at(count=count), "zoom",
                 f"zoom.table.{key} must be a multiple of 1/{quantum} in (0, {largest}] (minimum zoom {min_zoom})")
        table[count] = size

    style = _section(raw, "style", {"corner_radius", "lateral_jitter"}, where)
    radius = _rational(style["corner_radius"], "style.corner_radius", where, "corner-radius")
    _require(0 <= radius <= STYLE_MAX, where, "corner-radius", "style.corner_radius must be in 0..1/20")
    jitter = _rational(style["lateral_jitter"], "style.lateral_jitter", where, "lateral-jitter")
    _require(0 <= jitter <= STYLE_MAX, where, "lateral-jitter", "style.lateral_jitter must be in 0..1/20")
    return _Preset(name, low, high, orientations, weights, fit, focal, focal_by_index, full_bleed, overlap,
                   z1, gamma, min_zoom, quantum, table, radius, jitter, source)


def _checked_preset(raw: Any, source: str | None = None) -> _Preset:
    """Resolve a preset and expand every count it advertises, as a preset file is."""
    preset = _resolve_preset(raw, source)
    for count in range(preset.count_min, preset.count_max + 1):
        _expand(preset, count)
        _slice_size(preset, count)
    return preset


def _preset(preset: Any) -> _Preset:
    if isinstance(preset, str):
        if preset == FAMILY_AUTHORED:
            raise LayoutError("preset", "preset 'authored' is the authored family (N=2..12); use build_artifact001")
        if preset not in BUILTIN_PRESETS:
            raise LayoutError("preset", f"unknown preset {preset!r}; built-ins are {sorted(BUILTIN_PRESETS)} "
                                        "(pass your own file by path)")
        return _resolve_preset(BUILTIN_PRESETS[preset])
    if isinstance(preset, os.PathLike):
        path = Path(preset)
        data = load_layout_file(path)
        if data["format"] != PRESET_FORMAT:
            raise LayoutError("format", f"{path}: expected a {PRESET_FORMAT} file, got {data['format']}")
        return _resolve_preset(data, str(path))
    if isinstance(preset, Mapping):
        return _checked_preset(dict(preset))
    raise LayoutError("preset", "preset must be a built-in name, a preset object or a file path")


def _check_count(preset: _Preset, count: Any) -> int:
    where = _Where(source=preset.source)
    _require(type(count) is int, where, "count-range", f"count must be an integer, not {type(count).__name__}")
    _require(preset.count_min <= count <= preset.count_max, where, "count-range",
             f"strips preset {preset.name!r} supports N={preset.count_min}..{preset.count_max}; count {count} is "
             "refused (no filler, no duplication, never moved to another family)")
    return count


def _round_half_up_root(target: Fraction, root: int, estimate: float) -> int:
    """Exact floor(x + 1/2) for x >= 0 with x**root == target."""
    def fits(k: int) -> bool:  # k <= x + 1/2
        return k == 0 or Fraction(2 * k - 1, 2) ** root <= target
    k = max(0, math.floor(estimate + 0.5))
    while not fits(k):
        k -= 1
    while fits(k + 1):
        k += 1
    return k


def _slice_size(preset: _Preset, count: int) -> Fraction:
    if count in preset.table:
        return preset.table[count]
    # zoom(N) = max(min_zoom, z1 / N**gamma); s = 1/zoom, rounded half up to 1/quantum, exactly.
    p, q = preset.gamma.numerator, preset.gamma.denominator
    target = (Fraction(preset.quantum) / preset.z1) ** q * Fraction(count) ** p
    estimate = preset.quantum * count ** float(preset.gamma) / float(preset.z1)
    steps = _round_half_up_root(target, q, estimate)
    steps = min(steps, math.floor(preset.quantum / preset.min_zoom))
    _require(steps >= 1, _Where(source=preset.source, count=count), "zoom",
             f"zoom rounds to an empty slice at quantum 1/{preset.quantum}")
    return Fraction(steps, preset.quantum)


def _lateral_offset(name: str, count: int, orientation: str, index: int, jitter: Fraction) -> Fraction:
    steps = math.floor(jitter * JITTER_QUANTUM)
    if not steps:
        return Fraction(0)
    payload = [RNG, name, count, orientation, "jitter", index]
    value = int.from_bytes(hashlib.sha256(canonical_json(payload).encode("utf-8")).digest()[:8], "big")
    return Fraction(value % (2 * steps + 1) - steps, JITTER_QUANTUM)


def _expand(preset: _Preset, count: int) -> dict[str, Any]:
    weights = preset.weights.get(count, (Fraction(1),) * count)
    total = sum(weights)
    edges = [Fraction(0)]
    for weight in weights:
        edges.append(edges[-1] + weight / total)
    layouts = {}
    for orientation in ORIENTATIONS:
        direction, order = preset.orientations[orientation]
        cells = []
        for k in range(count):
            start, size = edges[k], edges[k + 1] - edges[k]
            rect = (0, start, 1, size) if direction == "rows" else (start, 0, size, 1)
            cell: dict[str, Any] = {
                "loop": f"loop-{k + 1}", "rect": [str(Fraction(v)) for v in rect], "fit": preset.fit,
                "focal": [str(v) for v in preset.focal_by_index.get(k, preset.focal)],
            }
            if preset.lateral_jitter:
                cell["lateral_offset"] = str(_lateral_offset(preset.name, count, orientation, k,
                                                             preset.lateral_jitter))
            cells.append(cell)
        if order == "reverse":
            cells.reverse()
        # Bleed and rounded corners need a shared edge; a single strip has none.
        shared = count > 1
        layouts[orientation] = {
            "name": f"{preset.name}-{count}-{orientation}",
            "full_bleed": preset.full_bleed,
            "presentation": {
                "overlap_px": preset.overlap_px if shared else 0,
                "corner_radius": str(preset.corner_radius if shared else Fraction(0)),
                "lateral_jitter": str(preset.lateral_jitter),
            },
            "cells": cells,
        }
    validate_layout_pair(layouts, {f"loop-{k + 1}" for k in range(count)}, source=preset.source, count=count)
    return layouts


def strips_layouts(count: int, preset: Any = "strips") -> dict[str, Any]:
    """Return ``{"portrait": layout, "landscape": layout}`` for ``count`` strips (1..12).

    ``preset`` is a built-in name, a ``simvltanea.layout-preset/1`` object or a file path.
    Strip k is bound to ``loop-{k+1}``; the array order is the draw order (back to front).
    """
    resolved = _preset(preset)
    return _expand(resolved, _check_count(resolved, count))


def strips_slice(count: int, preset: Any = "strips") -> dict[str, Any]:
    """Return the state-wide slice for ``count`` strips: ``width = height = s(N)``, zoom ``1/s``."""
    resolved = _preset(preset)
    size = str(_slice_size(resolved, _check_count(resolved, count)))
    value = {"enabled": True, "width": size, "height": size}
    validate_slice(value)
    return value


def build_strips(count: int, preset: Any = "strips", *, sources: list[dict] | None = None,
                 frames: int = 144, fps: int = 24) -> dict[str, Any]:
    """Return a validated initial state skeleton for ``count`` strips.

    Without ``sources`` the state names placeholder media ``fixtures/loop-{k}.mp4`` whose
    digests are labelled placeholders, so any media binding fails its hash check until
    real sources are supplied. Clocks follow Artifact 001: ``rate = 1 + 7k/100``,
    ``offset = 31k/100``.
    """
    resolved = _preset(preset)
    count = _check_count(resolved, count)
    if sources is None:
        sources = [dict(id=f"source-{k + 1}", path=f"fixtures/loop-{k + 1}.mp4",
                        sha256=hashlib.sha256(f"simvltanea strips skeleton placeholder loop-{k + 1}".encode()).hexdigest(),
                        kind="video", duration="8") for k in range(count)]
    _require(isinstance(sources, list) and len(sources) == count, _Where(count=count), "cell-count",
             f"build_strips needs exactly {count} sources, one per loop (no filler, no duplication)")
    _require(all(isinstance(item, dict) and {"id", "duration"} <= item.keys() for item in sources),
             _Where(count=count), "wrong-type", "each source must be a source object with id and duration")
    loops = [dict(id=f"loop-{k + 1}", bank=[sources[k]["id"]], offset=str(Fraction(31 * k, 100)),
                  rate=str(1 + Fraction(7 * k, 100)), period=sources[k]["duration"], epoch=0, held=False)
             for k in range(count)]
    state = dict(schema_version=SCHEMA_VERSION, engine_version=ENGINE_VERSION, rng=RNG, seed=444499, fps=fps,
                 frames=frames, allow_source_reuse=False, sources=copy.deepcopy(sources), loops=loops,
                 layouts=_expand(resolved, count), events=[],
                 audio={"mode": "none", "routing": None, "generative": None},
                 slice={"enabled": True, "width": str(_slice_size(resolved, count)),
                        "height": str(_slice_size(resolved, count))})
    validate_state(state)
    return state


# ---------------------------------------------------------------- files

def _read_json(path: Path) -> Any:
    where = _Where(source=str(path))

    def unique(pairs: list) -> dict:
        result = {}
        for key, value in pairs:
            _require(key not in result, where, "json", f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(name: str) -> None:
        _fail(where, "json", f"non-finite number {name} is not allowed")

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LayoutError("json", f"{path}: cannot read layout file: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=constant)
    except json.JSONDecodeError as exc:
        raise LayoutError("json", f"{path}: malformed JSON: {exc}") from exc
    except LayoutError:
        raise
    except ValueError as exc:
        raise LayoutError("json", f"{path}: invalid JSON value: {exc}") from exc


def load_layout_file(path: str | os.PathLike) -> dict[str, Any]:
    """Read and strictly validate a layout file given by path; return its JSON object.

    Accepts ``simvltanea.layout-preset/1`` (every count of the preset is expanded and
    validated) and ``simvltanea.layout-pair/1``. Errors name the file and, where known,
    the count, orientation and 0-based cell index.
    """
    path = Path(path)
    where = _Where(source=str(path))
    data = _read_json(path)
    _require(isinstance(data, dict), where, "wrong-type", "layout file must be a JSON object")
    kind = data.get("format")
    if kind == PRESET_FORMAT:
        _checked_preset(data, str(path))
    elif kind == PAIR_FORMAT:
        _keys(data, PAIR_FIELDS, PAIR_FIELDS, "pair", where)
        count = _integer(data["count"], 1, PAIR_MAX_COUNT, "count", where, "count-range")
        validate_layout_pair({o: data[o] for o in ORIENTATIONS}, source=str(path), count=count)
    else:
        _fail(where, "format", f"format must be {PRESET_FORMAT!r} or {PAIR_FORMAT!r}, got {kind!r}")
    return data
