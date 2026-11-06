# Layout Presets

Two layout families place exactly one cell per independent loop. **Strips** are
computed full-bleed partitions for any count from 1 through 12. **Authored**
engineering pairs (`build_artifact001`) exist for 2 through 7. A count outside the
selected family's range fails explicitly. It is never filled, duplicated or moved to
the other family. Strips and their zoom curve are engineering presets. They are not
artist-approved designs. The design and its evidence are in
[the full-bleed layout presets spec](../plans/2026-11-05-full-bleed-layout-presets.md).

## Strips geometry

For N loops with positive weights `w_0..w_{N-1}` (equal by default), the edges are
`e_0 = 0`, `e_k = (w_0 + … + w_{k-1}) / Σw` and `e_N = 1`, all exact `Fraction`s.

- `rows` (portrait default): cell k is `[0, e_k, 1, e_{k+1} - e_k]`, top to bottom.
- `columns` (landscape default): cell k is `[e_k, 0, e_{k+1} - e_k, 1]`, left to right.

Neighbours share an edge as the same rational. There is no gutter and no margin.
Strip k is bound to `loop-{k+1}`. The cell array is the draw order (back to front):
`order: forward` lists strips in direction order, `order: reverse` lists them
backwards. Rects are written in lowest terms, for example `["0", "1/5", "1", "1/5"]`.

## Zoom tied to N

Zoom is the state-wide `slice` with `width = height = s(N)`. Magnification over plain
cover is exactly `1/s`, whatever the cell or screen shape. The default curve is
`zoom(N) = max(min_zoom, 8 / N^(3/5))` with `min_zoom = 10/9`. Then
`s = 1/zoom` is rounded half up to a multiple of `1/quantum` (`quantum = 1000`). The
rounding is exact; no float decides it.

| N | zoom (curve) | `s` stored |
| --- | --- | --- |
| 1 | 8.00 | 1/8 |
| 2 | 5.28 | 189/1000 |
| 3 | 4.14 | 121/500 |
| 5 | 3.05 | 41/125 |
| 8 | 2.30 | 87/200 |
| 10 | 2.01 | 249/500 |
| 12 | 1.80 | 111/200 |

The minimum zoom keeps `s <= 9/10`, so no panel ever shows a full frame. An explicit
`zoom.table` entry (`"N": "s"`) replaces the curve for that N. It must be a multiple
of `1/quantum` and at most `1/min_zoom`.

## Choosing a preset

```python
from simvltanea.authoring import build_strips, strips_layouts, strips_slice

layouts = strips_layouts(5)          # {"portrait": {...}, "landscape": {...}}
zoom = strips_slice(5)               # {"enabled": true, "width": "41/125", "height": "41/125"}
state = build_strips(5)              # validated initial state skeleton
```

`preset` is `"strips"` (the built-in default), a preset object, or a file path:
`strips_layouts(5, Path("my-strips.json"))`. The name `"authored"` is refused here.
Use `build_artifact001(count)` for that family. `build_strips` names placeholder
media until you pass `sources=[...]`, one hashed source per loop.

## The preset format: `simvltanea.layout-preset/1`

The default preset is [`examples/layout-presets/strips.json`](../../examples/layout-presets/strips.json):

```json
{
  "format": "simvltanea.layout-preset/1",
  "name": "strips",
  "family": "strips",
  "counts": {"min": 1, "max": 12},
  "orientations": {
    "portrait": {"direction": "rows", "order": "forward"},
    "landscape": {"direction": "columns", "order": "forward"}
  },
  "weights": {"default": "equal", "by_count": {}},
  "fit": "cover",
  "focal": {"default": ["1/2", "1/2"], "by_index": {}},
  "full_bleed": true,
  "overlap_px": 2,
  "zoom": {"curve": "power", "z1": "8", "gamma": "3/5", "min_zoom": "10/9", "quantum": 1000, "table": {}},
  "style": {"corner_radius": "0", "lateral_jitter": "0"}
}
```

`format`, `name` and `family` are required. Every other key, including each key of a
nested object, may be omitted and takes the value shown. Rationals are integers or
strings such as `"3/5"`. JSON floats are refused.

| Key | Meaning and bounds |
| --- | --- |
| `name` | `[A-Za-z0-9_-]{1,80}`; layouts are named `{name}-{N}-{orientation}` |
| `family` | `strips` |
| `counts` | integers with `1 <= min <= max <= 12` |
| `orientations.*.direction` | `rows` or `columns` |
| `orientations.*.order` | `forward` or `reverse` |
| `weights.by_count` | `"N"` → N positive rationals; every edge `e_k` and size `w_k / Σw` must have a denominator of at most 10^9 |
| `fit` | `cover` (required by `full_bleed`) or `contain` |
| `focal.by_index` | `"k"` (0-based strip index) → focal pair in 0..1 |
| `overlap_px` | integer device pixels, 0..8 |
| `zoom.curve` | `power` |
| `zoom.z1` | rational in (0, 1000] |
| `zoom.gamma` | rational in 0..2 with denominator at most 100 |
| `zoom.min_zoom` | rational in (1, 1000] |
| `zoom.quantum` | integer in 2..1000000 |
| `style.corner_radius` | rational in 0..1/20 of the canvas minor dimension |
| `style.lateral_jitter` | rational in 0..1/20 of the canvas extent along the strip |

## What a state layout gains

Expanded strips layouts carry two optional layout keys and one optional cell key.
They are additions to schema v1; absent keys mean exactly the previous behaviour.

- `full_bleed: true` is a checked declaration. Every cell uses `fit: cover`, and the
  rect areas sum to exactly 1. With disjoint interiors inside the unit square, this
  proves the cells tile the canvas.
- `presentation` holds `overlap_px`, `corner_radius` and `lateral_jitter`, all three
  required. `overlap_px` is a raster bleed under the neighbour drawn later. Nominal
  rects stay disjoint.
- `lateral_offset` is a resolved per-cell rational in `[-J, J]`. It is present on
  every cell when `lateral_jitter` (J) is above 0, and absent otherwise. Offsets come
  from `sha256-counter-v1` over `[rng, name, N, orientation, "jitter", k]` and are
  quantised to 1/1000.

A single strip has no shared edge, so its expansion writes `overlap_px: 0` and
`corner_radius: "0"`.

## Your own file

Give files **by path**. Nothing is read from inside the package. If
`src/simvltanea/layouts.json` exists, importing `simvltanea.authoring` fails and names
that file.

- A preset file, as above.
- An explicit pair file:
  `{"format": "simvltanea.layout-pair/1", "count": N, "portrait": {...}, "landscape": {...}}`.
  Each orientation is a state layout object (`name`, `cells`, optional `full_bleed` and
  `presentation`).

```python
from simvltanea.authoring import load_layout_file
data = load_layout_file("my-layouts.json")  # validated; raises LayoutError
```

```bash
python -m tools.verification.verify_layouts --presets examples/layout-presets/strips.json
python -m tools.verification.verify_layouts --layouts my-layouts.json
python -m tools.verification.verify_layouts --examples
```

`--layouts` also reads the legacy count map of `examples/layouts.json` with the same
validator.

## Validation rules

`validate_layout_pair` is the single reference validator. State validation
(`validate_layouts`) and the guard both call it. Each failure raises a `LayoutError`
with a stable `code`. The message names the file, the count, the orientation and the
0-based cell index.

- Bounds: `0 <= x, y`, `w, h > 0`, `x + w <= 1`, `y + h <= 1` (`bounds`).
- Interiors are disjoint (`overlap`). The only drawn overlap permitted is the declared
  `overlap_px` bleed across shared edges.
- One cell per loop, the same loops in both orientations (`mapping`, `cell-count`).
- `fit` is `cover` or `contain` (`fit`); focal is in 0..1 (`focal`).
- `full_bleed: true`: every fit is `cover` (`full-bleed-fit`), and the areas sum to
  exactly 1 (`full-bleed-coverage`). A gap of 1/10^9 fails.
- `overlap_px` is an integer in 0..8 (`overlap-px`). A value above 0 needs at least one
  shared edge (`overlap-px-no-shared-edge`).
- `corner_radius` is in 0..1/20 (`corner-radius`). Only corners on a side shared with
  an earlier-drawn neighbour are rounded. Each such corner must have an earlier
  neighbour beneath it, and a radius above 0 needs a shared edge (`corner-rule`).
- `lateral_jitter` is in 0..1/20 (`lateral-jitter`); `|lateral_offset| <= J`
  (`lateral-offset`).
- Layouts declaring `full_bleed` or `presentation` have 1..12 cells (`count-range`).
- Unknown keys (`unknown-key`), missing keys (`missing-key`), wrong types
  (`wrong-type`), floats or invalid rationals (`rational`), malformed JSON or duplicate
  keys (`json`) and an unknown `format` (`format`) are errors.

`adjacency(cells)` lists exact shared edges in draw order. For N=3 portrait it returns
`[{"a":0,"b":1,"edge":"bottom","span":["0","1"]},{"a":1,"b":2,"edge":"bottom","span":["0","1"]}]`.

The conformance corpus is in `fixtures/layouts/`. `corpus.json` lists every valid file
and the error code each invalid file must produce.
