# Plan — Full-Bleed Layout Presets (2026-11-05)

> Doctrine: Verify → Heal → Expand → Evolve. Lane: `lane/evolve`, which requires a
> spec before code (`docs/governance/BRANCHES.md:16`). This document is that spec. It
> fixes the design decisions, the data format and the acceptance gate. It authorizes no
> implementation by itself, and it changes no code.

Owner intent (from a hand sketch and the owner's own words): a portrait canvas filled
edge to edge by full-width bands stacked top to bottom, touching, with no gutters, no
outer margin and slightly overlapping seams. "The videos should have no gaps between one
another and should be basically clipping one another; the videos need to be heavily
cropped." Later requirements: the user picks any panel count, including 1, 3, 8, 10 and
12. Zoom depends on the count: one panel is zoomed in until it cannot be recognised, and
each added panel zooms out a little. The field always fills the screen it is on.
Corner radius and lateral jitter are optional and off by default. Everything is
configurable.

## Decision

| # | Decision | Recommended default |
| --- | --- | --- |
| 1 | Add a second layout family, **strips**, beside the authored family. The authored family (`_AUTHORED_DEFAULT`, N=2..7) stays byte-for-byte unchanged. | Two families: `authored` and `strips` |
| 2 | Strips geometry is an exact rational partition of the unit square: rows in portrait, columns in landscape. Direction is configurable per orientation. | portrait `rows`, landscape `columns`, equal weights |
| 3 | Strips are generated as exact `Fraction`s and written straight into state layouts, never through the float `Placement` model. | Pure module `authoring/layout_presets.py` |
| 4 | The anti-hairline **overlap** is a raster-time bleed in **device pixels**, applied to a cell under the neighbour drawn after it. Nominal rects stay disjoint, so the schema-v1 non-overlap rule keeps holding. | `overlap_px: 2` (allowed 0..8) |
| 5 | Draw order is the existing contract: cell array order, back to front. | `order: forward` (later strips over earlier ones) |
| 6 | `full_bleed: true` is a checked declaration: the rects tile the unit square exactly and every cell uses `fit: cover`. | Always true for strips |
| 7 | **Zoom** is tied to N through the existing state-global `slice` with `width = height = s(N)`, so magnification over plain cover is exactly `1/s`. | `zoom(N) = 8 / N^(3/5)`, quantum 1/1000, minimum zoom 10/9 |
| 8 | The browser draws a slice the way the renderer does: crop, then cover. The current stretch (`objectFit: 'fill'`) is replaced. | Aspect-preserving (open question 2) |
| 9 | Slice scope stays **state-global**. | No per-loop slice |
| 10 | Strips support N=1..12. Authored stays 2..7. A count is never moved silently from one family to the other. | Engine-wide compiler subset 1..12 |
| 11 | Style parameters `corner_radius` and `lateral_jitter` live in the data and are rendered without exposing background. | Both `"0"` |
| 12 | Formats are versioned: `simvltanea.layout-preset/1` (presets), `simvltanea.layout-bundle/2` (bundle, opt-in). State additions are optional fields in schema v1, as `slice` and `seam` were. | Legacy bundle output unchanged by default |
| 13 | The ambient in-package override `src/simvltanea/layouts.json` is removed. User layouts are explicit files, validated strictly and failing loudly. | `--layouts FILE` / `load_layout_file(path)` |
| 14 | Strips become the default family for new compositions and the studio. `authored` stays selectable by name. | `family: strips`, N=5 |

## Current state

### Authored pairs — `src/simvltanea/authoring/artifact001_layouts.py`

- `p()` (`:11-12`) builds a float `Placement` with `z=0` and `fit="cover"`.
- `_AUTHORED_DEFAULT` (`:18-43`) holds hand-specified float rects for N=2..7, with
  gutters and outer margins. For example, N=5 portrait cell 1 is `(.04, .03, .92, .36)`,
  which canonicalises to x 1/25..24/25 and y 3/100..39/100.
- `_load_authored()` (`:45-66`) reads `Path(__file__).resolve().parents[1] / "layouts.json"`,
  that is `src/simvltanea/layouts.json`, **inside the package**. It swallows errors twice:
  `except Exception: continue` (`:62-63`) per key, and `except Exception: pass` (`:64-65`)
  for the whole file. `layout.toml:42` lists `{package}/layouts.json` in
  `source_file_exceptions`. `pyproject.toml:29-32` does not ship it as package data, but an
  editable install or a file dropped into `site-packages/simvltanea/` is read silently.
- `AUTHORED = _load_authored()` (`:68`). `build_artifact001(count)` (`:71-84`) raises
  `no reviewed engineering layout pair` for any count not in `AUTHORED` (`:72-73`). It
  derives clocks `rate = 1 + i*.07`, `offset = i*.31` (`:75`). The CLI restricts
  `choices=sorted(AUTHORED)` (`:91`).

I measured the override's behaviour in scratch. I copied the module into a throwaway
package and put each bad `layouts.json` next to it:

| Override content | Result |
| --- | --- |
| `{not json` | import succeeds, counts `[2..7]`, override silently ignored |
| key `"five"` | silently ignored |
| `"8"` with only `portrait` | silently ignored |
| `"3"` with overlapping, non-covering rects | **silently replaces authored N=3**; `build_artifact001(3)` succeeds; the overlap is caught only later in `validate_state` |
| `"2"` with one portrait rect | fails late in `Layout.validate` (`one-to-one mapping failed`) |

### Authoring model and adapter — `src/simvltanea/authoring/composition_model.py`, `composition.py`

- `Placement` (`composition_model.py:144-167`) has float `x, y, width, height`, `z: int = 0`,
  `fit` in `FIT_MODES = {"cover", "contain"}` (`:21`), `focal_x/focal_y = 0.5`. It checks
  bounds with a `1.000001` tolerance and does not check overlap. `Layout.validate`
  (`:175-187`) enforces a one-to-one loop mapping. `Composition.validate` (`:204-222`)
  requires at least one loop and both orientations.
- `from_authoring_model` (`composition.py:649-694`) rounds every float to nine decimals
  (`exact()`, `:664-665`). It writes cells sorted by `z` as back-to-front draw order,
  "not permission for overlap" (`:678-684`).
- Measured consequence for strips. Float strips cannot round-trip through the adapter:

  | N | Result of `from_authoring_model` on float strips `i/N` |
  | --- | --- |
  | 3 | accepted with a 1/1000000000 gap at one seam (`333333333/1000000000`) |
  | 5, 8 | exact (`1/5`, `1/8` are short decimals) |
  | 7 | **rejected**: `overlapping/occluded panels are not supported in schema v1` |
  | 12 | accepted with 1e-9 gaps at 4 seams |

- `rect_values` (`:196-201`) requires `0 <= x, y`, `w, h > 0`, `x+w <= 1`, `y+h <= 1`.
  `validate_layouts` (`:204-225`) has strict layout keys `{name, cells}` (`:207`) and strict
  cell keys `{loop, rect, fit, focal}` (`:212`). It requires `fit` in contain/cover (`:215`)
  and focal in 0..1 (`:216-217`). Its exact-rational interior-intersection test rejects
  overlap (`:219-222`); shared edges pass.
- `validate_state` allows 1..32 loops (`:299`). N=1 and N=12 are already valid states.
  I validated hand-written strip states for N=1, 3, 5, 8 and 12 with `load_state`.
- `validate_slice` (`:228-243`): `0 < width, height < 1`, and when enabled
  `w*h < 1` ("slice must not reveal full frame"). `slice_rect` (`:432-451`) picks a
  deterministic `sha256-counter-v1` window position per loop **per period** (it rerolls
  at each loop wrap). `resolve_at` attaches it as `slice_rect` (`:501-503`).
- `pixel_placements` (`:566-578`) snaps every edge independently with
  `edge(v) = 2*round(v*dim/2)` (`:568-569`). A shared rational edge therefore maps to the
  same even pixel for both neighbours, so offline exports cannot have hairlines.
- `amalgamate_viewports` (`composition_model.py:511-…`, 3..10 panels, float and
  `random.Random`) produces **source** crop windows (`SliceRect`), not canvas layouts. It is
  unrelated to strips and stays untouched.

### Layout bundle — `src/simvltanea/browser/layout_bundle.py` (branch `feat/web-client-compiler` @ `6fcc3b6`, not on `main`)

- `authored_layouts(count)` (`:19-32`) builds `build_artifact001(count)` and returns
  `from_authoring_model(...)['layouts']`. `authored_layout_bundle()` (`:35-37`) maps
  `str(count)` → `{portrait: {name, cells}, landscape: {name, cells}}` for
  `sorted(AUTHORED)`. The docstring (`:7`) notes that source JSON is not permitted under `src/`.
- Consumers index it as `bundle[String(sources.length)]` (`docs/authoring/BROWSER_COMPILER.md:48`
  on that branch).

### Client compiler — `src/simvltanea/browser/browser.compiler.js` (same branch)

- `MIN_LOOPS = 2, MAX_LOOPS = 7` (`:47`). There is a hard guard of 1..32 (`:208-209`), then
  `refuse(N < 2 || N > 7, "authored layouts cover N=2..7 … (no filler, no implicit duplication)")`
  (`:210-212`). `SUPPORTED_LOOP_COUNTS: [2,3,4,5,6,7]` (`:440`). Header comments
  `:11` and `:17`.
- `CELL_FIELDS = ['loop','rect','fit','focal']` (`:55`). `validateLayouts` (`:139-162`) mirrors
  Python, including the overlap refusal (`:157`).
- `validateToggle` refuses any **enabled** slice or seam: "slices and seams are compiled by
  Python only" (`:167-171`, used at `:245-249`). Today the client compiler cannot express
  zoom at all.
- `bindLayouts(pair, loopIds)` (`:396-412`) relabels a bundle pair onto caller loop IDs in
  portrait cell order and refuses a cell-count mismatch ("no filler, no duplication").

### Browser runtime — `src/simvltanea/browser/browser.runtime.js` (`main`)

- The stage is the viewport: `#stage{width:100%;height:100%}` (`browser_runtime.py:50-51`).
  `applyLayout` (`:408-440`) picks `landscape` when `width >= height` (`:412`). It positions
  every cell box in **percentages** (`left/top/width/height = v*100%`), sets
  `zIndex = cell index` and `overflow: hidden` (`:422-426`), and applies `objectFit = cell.fit`
  and `objectPosition = focal` (`:429-431`). A `ResizeObserver` re-runs it (`:441`).
- `applySlice` (`:205-272`): with a partial slice, the media becomes `position: absolute`,
  `width = 100/sw %`, `height = 100/sh %`, `objectFit: 'fill'` (`:266-271`). That stretches
  the slice region to the cell's aspect ratio. The offline renderer crops and then covers
  (`render_triptych.py:898-905` `_crop_prefix`, `:877-889` `force_original_aspect_ratio=increase`
  and a focal crop). **Browser and export disagree whenever a slice is enabled.**
- `validatePlan` (`:835-…`). In the layout loop (`:907-929`), cells must equal the loop count
  (`:914`), `fit` must be contain/cover with a 4-rect and a 2-focal (`:918-919`), geometry must
  be in bounds with `1e-12` tolerance (`:920-922`), and overlap is rejected (`:923-925`,
  "overlapping cells"). The loop guard is 1..32 (`:845`), and media is capped at 256 MiB
  (`:850-855`, `:961`).
- The shared-engine panel driver pans focal and slice positions in the browser only
  (`:343-406`). In this environment the engine was unavailable (no `time-moment-brief`
  checkout), so all measurements below have static focal points.

### Layout guard — `tools/verification/verify_layouts.py`, `examples/layouts.json`

- `DEFAULT_CORE = package/layouts.json`, `DEFAULT_EXAMPLE = examples/layouts.json` (`:19-20`).
  `validate_payload` (`:51-104`) checks count keys in 1..32 and `len(rects) == count`. It
  applies the `rect_values` bounds (`:95-97`) and rejects any interior intersection
  ("overlapping/occluded panels are not supported", `:98-103`). `--examples` (`:110`)
  validates the example file, and CI runs it (`.github/workflows/ci.yml:167`). Without
  `--strict`, a missing file prints "layouts ok" (`:122-134`).
- It **re-implements** the rules instead of importing them, and has no tests.
- `examples/layouts.json` overrides counts 2 and 3 with the authored values plus a
  `_comment`. `python -m tools.verification.verify_layouts --examples` → `layouts ok`,
  `counts: ['2', '3']` (run on this branch).

### Where N=2..7 is hard-coded

| Place | Reference | Change under this spec |
| --- | --- | --- |
| Compiler subset | `browser.compiler.js:11, :17, :47, :210-212, :440` (branch) | 1..12; family counts move to the bundle |
| Compiler tests | `test_browser_compiler.py:4, :304-305` (`one-loop`, `eight-loops` refused), `:514` (branch) | accept 1 and 8; refuse 13 |
| Compiler docs | `docs/authoring/BROWSER_COMPILER.md:78` (branch) | "N outside 1 to 12" |
| Studio cap | not present on any committed ref (`git ls-tree` over all local and `origin` branches finds no studio file) | the studio must read the counts from the bundle, never hard-code a cap |
| `build_artifact001` | `artifact001_layouts.py:72-73, :91` | **unchanged** (authored only, 2..7) |
| README | `README.md:71` ("2 through 7"), `:83-84` ("Counts without an authored pair still fail explicitly; eight loops are currently unsupported") | amended text below |
| Contributing | `.github/CONTRIBUTING.md:92` | same amendment |
| Seamed slice doc | `docs/architecture/SEAMED_SLICE_FIELD.md:3` ("Minimum 2 videos"), `:7` ("N >= 2", stale "2..6", "7 experimental") | "N >= 1 under strips; authored 2..7" |
| Config doc | `docs/authoring/CONFIG.md:30` (stale "2..6", "SEVEN stays experimental") | corrected |
| Tests (authored) | `test_composition_model.py:30` (`{2..7}`), `:95-97` and `test_composition_render.py:219` (`build_artifact001(8)` raises) | **unchanged**: the authored guard stays |
| Generators | `make_runtime_fixture.py:77`, `make_artifact_001.py:57` loop over `(2..7)` | add strips fixtures; authored loops unchanged |
| Engine guards | `composition.py:299`, `browser.runtime.js:845` (1..32) | unchanged (resource guard) |

## Design: the strips family

### Geometry

For N loops, weights `w_0..w_{N-1}` (positive rationals, default all 1) and
`W = Σ w_i`, the edges are `e_0 = 0`, `e_k = (w_0 + … + w_{k-1}) / W` as `Fraction`, and
`e_N = 1` exactly.

- `rows` (portrait default): cell k is `[0, e_k, 1, e_{k+1} - e_k]`, stacked top to bottom.
- `columns` (landscape default): cell k is `[e_k, 0, e_{k+1} - e_k, 1]`, left to right.

Adjacent cells share the edge `e_{k+1}` as the **same rational**. The union is the unit
square because `e_0 = 0` and `e_N = 1`, and there is no outer margin. N=1 is the single
cell `[0, 0, 1, 1]` in both orientations. Strip k is bound to loop k, the same convention
as `bindLayouts`. Rects are serialised with `str(Fraction)` in lowest terms.

### Always-fill semantics

- The canvas is the viewport (`#stage` 100%×100%), and layout fractions scale independently
  on each axis. No letterboxing happens at any aspect ratio, so a full-bleed tiling covers
  every viewport for any N. The runtime switches orientation at `width >= height`; a square
  viewport is landscape.
- Each cell is filled by `fit: cover` (and by the slice, which also covers). `contain`
  pads with black (`render_triptych.py:877-881`; CSS `object-fit: contain`), so
  `full_bleed: true` **requires** `fit: cover` on every cell.
- Rounding in the browser is the only remaining source of empty pixels, and the bleed
  below removes it (measured).
- Exports: `pixel_placements` maps `e_0 = 0` and `e_N = 1` to `0` and the full width or
  height. Shared edges coincide, so an export is always filled. Even-pixel snapping makes
  strip extents differ by up to 2 px (64/66 px at N=12 on 360×780, measured).

### Overlap ("clipping one another")

- Unit: **integer device pixels**, `overlap_px` in 0..8, default 2. A hairline is a
  rasterisation artefact of at most a few device pixels at *any* canvas size. A fraction
  of the canvas would be too small on a phone (1/1000 of 375 CSS px is 0.375 px) and
  needlessly large on a 4K export. A canvas fraction is also aspect-dependent in unit
  coordinates, so it could not be stored as one rational. The geometry stays
  resolution-independent; the bleed is a raster tolerance, like a hairline stroke.
- Rule: on each edge a cell shares with a neighbour drawn **later**, the cell's drawn box
  extends `overlap_px` device pixels underneath that neighbour, clamped to half the
  neighbour's pixel extent. The cell drawn on top keeps its exact nominal edge. The
  visible picture therefore equals the nominal partition, and the bleed is visible only
  where rounding would otherwise show the background.
- Browser: `height: calc(<h>% + <k/devicePixelRatio>px)` (or `width` for columns).
  Renderer: extend by `2*ceil(k/2)` px. This is fully hidden by the later overlay
  (`render_triptych.py:1098-1101` overlays in cell order), so exports stay pixel-identical.
- Effect on the visible crop: the media of the cell underneath is fitted to a box taller
  by `k` device px. Its window shifts by at most `k/2` device px, which is 1 CSS px at
  `overlap_px: 2` on a 1× screen. At N=12 on 375×812 that is ≤1.5% of the strip height
  and ≤0.4% of a 3:4 clip's height.
- Nominal rects stay disjoint, so `validate_layouts`, the compiler and `validatePlan` keep
  their non-overlap rule unchanged. The guard's wording is amended: *interiors of nominal
  rects must be disjoint; the only drawn overlap permitted is the declared `overlap_px`
  bleed across shared edges.*
- Draw order: the cell array order (back to front), as today. `order: forward` lists strips
  in direction order, so later strips cover earlier ones. `order: reverse` lists them
  backwards. Loop k always stays on strip k; only the array order changes.

Rejected alternative: baking the overlap into overlapping rational rects. That needs
relaxing three validators and the renderer, breaks the exact shared-edge and coverage
tests, and its pixel size would vary with the screen.

### Zoom tied to N

Zoom uses the existing state-global `slice` with `width = height = s(N)`. The renderer
crops the source to the window `s·SW × s·SH`, which has the source's aspect ratio, and
then covers the cell. The cover scale of the window is therefore exactly `1/s` times the
cover scale of the whole source. **Magnification over plain cover is `zoom = 1/s` on both
axes, independent of the cell's aspect ratio and the screen shape.** The slice invariant
`s*s < 1` (`validate_slice`) is the masking guarantee: no panel ever shows a full frame.

Curve (data, not code): `zoom(N) = max(min_zoom, z1 / N^gamma)` with `z1 = 8`,
`gamma = 3/5` and `min_zoom = 10/9`, so `s <= 9/10` and every `w, h < 1` holds. `s` is
rounded to `quantum = 1000` so the state keeps short rationals. The curve is resolved per
N when the preset is expanded, and the state stores only `slice`. Engines need no curve
code.

Recommended: no dependence on cell aspect or screen shape. Cover already adapts to
aspect, and a state-level value keeps previews and exports identical on every device.

Zoom table for a 3:4 source (540×720), portrait 375×812 rows, landscape 1280×720 columns.
"Visible" is the fraction of the clip's width × height that a cell shows under
crop-then-cover. "Stretch" is the aspect distortion the **current** browser fill mode
would apply.

| N | zoom (exact curve) | s stored | portrait cell px | visible, portrait | area | stretch today | landscape cell px | visible, landscape | area | stretch today |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8.00 | 1/8 | 375×812 | 0.077×0.125 | 1.0% | 1.62 | 1280×720 | 0.125×0.053 | 0.7% | 2.37 |
| 2 | 5.28 | 189/1000 | 375×406 | 0.189×0.153 | 2.9% | 1.23 | 640×720 | 0.189×0.159 | 3.0% | 1.19 |
| 3 | 4.14 | 121/500 | 375×270.7 | 0.242×0.131 | 3.2% | 1.85 | 426.7×720 | 0.191×0.242 | 4.6% | 1.27 |
| 5 | 3.05 | 41/125 | 375×162.4 | 0.328×0.107 | 3.5% | 3.08 | 256×720 | 0.155×0.328 | 5.1% | 2.11 |
| 8 | 2.30 | 87/200 | 375×101.5 | 0.435×0.088 | 3.8% | 4.93 | 160×720 | 0.129×0.435 | 5.6% | 3.38 |
| 10 | 2.01 | 249/500 | 375×81.2 | 0.498×0.081 | 4.0% | 6.16 | 128×720 | 0.118×0.498 | 5.9% | 4.22 |
| 12 | 1.80 | 111/200 | 375×67.7 | 0.555×0.075 | 4.2% | 7.39 | 106.7×720 | 0.110×0.555 | 6.1% | 5.06 |

Why this default: for N ≥ 2 each clip shows a nearly constant 3–6% of its frame, which
amounts to a per-clip privacy budget. Magnification still falls from 5.3× to 1.8×, so
each strip gets clearer while staying a thin band. That is the owner's "more clarity, but
more cropped". N=1 is the most masked case, at about 1% of the frame.

Alternatives:

- **Hyperbolic `z1/N` (gamma = 1).** One parameter that tracks strip area exactly.
  It reaches zoom 1 at N=8, so by N=10 the masking comes only from the strip shape.
- **Exponential `1 + (z1-1)·e^(-k(N-1))`.** Approaches the floor smoothly and never
  crosses it. The decay constant is harder to explain than an exponent.
- **Anchor table (linear interpolation).** The owner can write a value per N (1→8, 12→1.5).
  It is explicit and auditable, but it has no shape between anchors, and editing it means
  editing many numbers.
- **Visible-area target.** Solves for zoom so each clip shows a fixed fraction of its
  frame. That depends on the cell and source aspect, so every device would get a
  different state; rejected for parity.

The format allows an explicit table (`zoom.table`) that overrides the curve. The curve is
open question 1.

### Slice rendering parity and scope

- **Parity (required).** The browser must crop and then cover, as the renderer does. The
  media fits the slice window with `cover` semantics, positioned by the slice origin
  and the cell's focal point. The current `fill` stretch is measured at 1.6× (N=1) up to
  7.4× (N=12 portrait). That gets *worse* as N rises, the opposite of "more clarity". It is
  a documented behaviour change for existing slice previews (`state-slice.json`).
- **Scope: state-global (recommended, smallest).** The owner ties zoom to N, and every
  cell of a composition shares N. Global scope needs no change to `composition_model.py`
  or `validate_slice`. The bundle carries one `slice` per count. The compiler only has to
  lift its "enabled slice" refusal for this global slice and port `slice_rect`
  (`sha256Hex` and `canonicalJson` already exist in the compiler).
- **Per-loop (not recommended now).** It would add a `LoopState` slice field (and its
  `to_json`), a `slice` key in the strict loop fields of `validate_state` and the compiler
  `LOOP_FIELDS`, a `validate_slice` call per loop, and loop-level reads in `slice_rect`,
  `compile_plan` and `browser.runtime.js`. The bundle would need per-cell values, and
  state hashes would grow. It is worth doing only if unequal weights later need different
  zoom per strip.

### Style parameters

- `corner_radius` (rational, a fraction of the canvas minor dimension, 0..1/20, default
  `"0"`). Every corner of a full-span strip lies on the canvas boundary, so naive rounding
  exposes background and violates always-fill. Rule: round only the corners on an edge
  shared with an **earlier**-drawn neighbour. The earlier neighbour's bleed under that
  corner becomes `overlap_px + ceil(radius in device px)`, and all other corners stay
  square. The result looks like a stack of cards, and no corner shows background. CSS:
  per-corner `border-*-radius` on the cell box, which already has `overflow: hidden`.
  Renderer: an alpha mask on the later overlay. The validator rejects
  `corner_radius > 0` if any rounded corner would lack an earlier neighbour.
- `lateral_jitter` (rational, a fraction of the canvas extent *along* the strip, 0..1/20,
  default `"0"`). Each strip's picture slides sideways by `lateral_offset_k` in
  `[-J, J]`. That value comes from `sha256-counter-v1` over
  `[rng, preset name, N, orientation, "jitter", k]`, quantised to 1/1000, and is stored
  resolved per cell. Conceptually the strip extends past both canvas ends by at least J,
  is shifted, and the canvas clips it. For full-span strips that is pixel-identical to
  scaling the media by `1 + 2J` along the strip (overscan) and shifting it inside the
  unchanged cell. This spec chooses the second form so rects stay inside the unit square,
  and no gap can appear by construction. Overscan multiplies the zoom (×1.05 at J=1/40).
- Seam tests run with both parameters at their maxima as well as at 0.

### Parameters as data: `simvltanea.layout-preset/1`

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

`by_count` maps `"5"` to five positive rationals. `by_index` maps a strip index to a focal
pair. `zoom.table` maps `"N"` to an explicit `s`. Unknown keys and wrong types are errors.

Expanded state layouts (N=5) and the per-count slice. The state layout object gains
optional `full_bleed` and `presentation`, and the cell gains optional `lateral_offset`
(only when jitter is non-zero):

```json
{
  "slice": {"enabled": true, "width": "41/125", "height": "41/125"},
  "layouts": {
    "portrait": {
      "name": "strips-5-portrait", "full_bleed": true,
      "presentation": {"overlap_px": 2, "corner_radius": "0", "lateral_jitter": "0"},
      "cells": [
        {"loop": "loop-1", "rect": ["0", "0", "1", "1/5"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-2", "rect": ["0", "1/5", "1", "1/5"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-3", "rect": ["0", "2/5", "1", "1/5"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-4", "rect": ["0", "3/5", "1", "1/5"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-5", "rect": ["0", "4/5", "1", "1/5"], "fit": "cover", "focal": ["1/2", "1/2"]}
      ]
    },
    "landscape": {
      "name": "strips-5-landscape", "full_bleed": true,
      "presentation": {"overlap_px": 2, "corner_radius": "0", "lateral_jitter": "0"},
      "cells": [
        {"loop": "loop-1", "rect": ["0", "0", "1/5", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-2", "rect": ["1/5", "0", "1/5", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-3", "rect": ["2/5", "0", "1/5", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-4", "rect": ["3/5", "0", "1/5", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
        {"loop": "loop-5", "rect": ["4/5", "0", "1/5", "1"], "fit": "cover", "focal": ["1/2", "1/2"]}
      ]
    }
  }
}
```

N=3 (slice `121/500`):

```json
{
  "portrait": {
    "name": "strips-3-portrait", "full_bleed": true,
    "presentation": {"overlap_px": 2, "corner_radius": "0", "lateral_jitter": "0"},
    "cells": [
      {"loop": "loop-1", "rect": ["0", "0", "1", "1/3"], "fit": "cover", "focal": ["1/2", "1/2"]},
      {"loop": "loop-2", "rect": ["0", "1/3", "1", "1/3"], "fit": "cover", "focal": ["1/2", "1/2"]},
      {"loop": "loop-3", "rect": ["0", "2/3", "1", "1/3"], "fit": "cover", "focal": ["1/2", "1/2"]}
    ]
  },
  "landscape": {
    "name": "strips-3-landscape", "full_bleed": true,
    "presentation": {"overlap_px": 2, "corner_radius": "0", "lateral_jitter": "0"},
    "cells": [
      {"loop": "loop-1", "rect": ["0", "0", "1/3", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
      {"loop": "loop-2", "rect": ["1/3", "0", "1/3", "1"], "fit": "cover", "focal": ["1/2", "1/2"]},
      {"loop": "loop-3", "rect": ["2/3", "0", "1/3", "1"], "fit": "cover", "focal": ["1/2", "1/2"]}
    ]
  }
}
```

Absent `full_bleed`, `presentation` and `lateral_offset` mean exactly today's behaviour.
Existing states and their `state_sha256` values are unchanged, and older engines refuse
the new keys loudly through their strict key checks.

### Selection, validation, adjacency and the bundle

- **By name.** Built-ins are `strips` (default) and `authored`. Python:
  `strips_layouts(count, preset="strips") -> {"portrait", "landscape"}`,
  `strips_slice(count, preset)`, and `build_strips(count, preset)` returning a validated
  initial state skeleton. `build_artifact001` stays the authored entry point.
- **Own JSON.** Either a preset file (`layout-preset/1`) or an explicit pair file
  (`{"format": "simvltanea.layout-pair/1", "count": N, "portrait": {...}, "landscape": {...}}`),
  given **by path**: `load_layout_file(path)`, `--layouts FILE`, or a file input in the
  studio. Nothing is read from inside the package. If `src/simvltanea/layouts.json` exists,
  importing the authoring package raises an error that names the replacement. Its
  `layout.toml:42` exception is removed.
- **One validator.** Python `validate_layout_pair()` in `authoring/layout_presets.py` is the
  reference. `validate_layouts` calls it, and `verify_layouts` imports it through
  `simvltanea.authoring` (no third copy). The compiler mirrors it in JS. A shared
  conformance corpus (`fixtures/layouts/{valid,invalid}/*.json`, each invalid case naming
  its expected error code) runs against both. Every error is raised, never swallowed. The
  error names the file, count, orientation and cell index.
- **Checks:** bounds; disjoint interiors; one cell per loop; `fit` cover/contain; focal in 0..1.
  With `full_bleed: true`: every `fit` is `cover`, and `Σ w·h == 1` exactly. Together with
  disjoint interiors inside the square, that proves the closed union is the unit square.
  Also `overlap_px` is an integer in 0..8; `corner_radius` is in 0..1/20 with the corner
  rule; `lateral_jitter` is in 0..1/20 with `|lateral_offset| <= J`; and strip counts are
  in 1..12.
- **Adjacency (pure helper).** `adjacency(cells) -> [{"a": i, "b": j, "edge": "bottom", "span": [lo, hi]}]`.
  Cell `a`'s side `edge` coincides exactly (Fraction equality) with cell `b`'s opposite
  side over a positive-length `span`, and `i < j` is draw order. The Python and JS
  implementations emit identical canonical JSON. For N=3 portrait the result is
  `[{"a":0,"b":1,"edge":"bottom","span":["0","1"]},{"a":1,"b":2,"edge":"bottom","span":["0","1"]}]`.
  A play-mode scheduler reads real neighbours from it, and the bleed and corner rules use it.
- **Bundle.** `python -m simvltanea.browser.layout_bundle` with no flags keeps emitting the
  existing authored map byte for byte. `--format 2` emits:

```json
{
  "format": "simvltanea.layout-bundle/2",
  "default_family": "strips",
  "families": {
    "authored": {"counts": {"2": {"portrait": {}, "landscape": {}}}},
    "strips": {
      "preset": {"format": "simvltanea.layout-preset/1", "name": "strips"},
      "counts": {
        "5": {
          "portrait": {}, "landscape": {},
          "slice": {"enabled": true, "width": "41/125", "height": "41/125"},
          "adjacency": {"portrait": [], "landscape": []}
        }
      }
    }
  }
}
```

(The empty `{}` and `[]` stand for the full objects shown above. `authored.counts` keeps
2..7, and `strips.counts` holds 1..12.)

### N range

Strips are defined for every N ≥ 1. The supported range is **1..12**.

- 12 is the owner's largest stated count.
- At 375×812 a strip is then 67.7 px tall.
- Measured decode load rises sharply between 8 and 12: dropped frames go from 0.5% to
  4.6–8.9% on a desktop Apple M5.
- Phone hardware decoders are fewer (not measured here).
- The 256 MiB preview cap (`browser_runtime.py:41`, compiler `:46`) leaves 21.3 MiB per
  clip at N=12, about 60 s at 3 Mbit/s.
- I found no 512 MiB cap on any committed ref. If another lane adds one, the per-clip
  budget doubles. That does not change the ceiling, which is decode-bound.

The Python and runtime guard of 32 stays.

README amendment (replaces `README.md:71-84` wording; mirrored in `CONTRIBUTING.md:92`):
"Two layout families exist. **Strips** (default) are computed full-bleed partitions for
any count from 1 through 12. **Authored** engineering pairs exist for 2 through 7. Each
family places exactly one cell per independent loop. A count outside the selected
family's range fails explicitly and is never filled, duplicated or moved to the other
family: `build_artifact001(8)` still raises, and strips at 13 raise." The invariant
holds: every cell is a distinct loop (no filler), sources are never reused (no implicit
duplication), and no family substitutes for another. N=1 is a field of one loop, by the
owner's explicit choice.

### Seam tests required of the implementation

1. Exact shared edges: for every strip pair `(k, k+1)`, the end edge of k equals the start
   edge of k+1 as `Fraction` (N=1..12, both orientations, default and non-equal weights).
2. Coverage: with `full_bleed`, `Σ area == 1`, disjoint interiors and bounds hold.
   Negative cases: a 1/10^9 gap, a margin, `contain`.
3. Overlap bounds: `overlap_px` outside 0..8, a non-integer, or a value in a layout
   without shared edges is rejected.
4. Guard amendment: `verify_layouts` accepts declared bleed and still rejects any
   rect-interior overlap.
5. Adjacency: Python and JS give byte-identical JSON on the corpus.
6. Browser: in the real runtime, a screenshot at 375×812 @1/2/3×, 390×844 @1/2/3×,
   360×780 @1/2/3×, 1280×720 @1/2× and 1366×768 @1/2× for N=1, 5, 8 and 12 has **zero**
   background pixels, with jitter and radius at 0 and at their maxima. (Clips must contain
   no near-black pixels; the measured method is below.)
7. Parity: an export frame and a browser screenshot of the same state show the same
   source rows per strip within ±2%. This catches any return of the fill stretch.

### Beyond strips (named, not designed)

- `grid`: full-bleed rows × columns.
- `guillotine`: recursive splits; strips are depth 1, and it can express authored-like
  hierarchy without margins.

Both would reuse the same validator, adjacency and bleed.

### Defaults, compatibility, demo

New compositions and the studio default to `strips` at N=5, with a family switch and an N
picker for 1..12 that reads the counts from the bundle. Authored compositions, their
evidence frames and archived renders are untouched. The public demo should show strips
N=5 (portrait rows / landscape columns), state "engineering preset" in its caption, and
keep authored selectable. The README support table gains a family column.

## Measured evidence

Environment: macOS 26.7.2, Apple M5, Google Chrome 156.0.8078.80 headless through
Playwright 1.57.0, Pillow 13.0.0 and ffmpeg 9.0.2. The shared engine was unavailable, so
focal points were static. Clips were 12 synthetic H.264 yuv420p 540×720 24 fps files
from `ffmpeg lavfi`. Each frame was a ramp (R = row, G = column, B = 80 + 14·k per clip,
so the background is the only near-black colour) plus temporal noise. They were 3.5
Mbit/s, 4.0–8.1 s long, and 30 MB for all twelve. The states were hand-written with the
exact strip rects above, clocks `rate = 1 + 7k/100` and `offset = 31k/100`, 960 frames,
and `slice` from the recommended curve in the "zoom" cases. They were staged with
`build_preview` (with `SIMVLTANEA_ROOT` set to the scratch directory) and served by
`python -m http.server` on 127.0.0.1:8791. Each page was measured at 375×812, then resized
in place to 1280×720. All scratch files were in `$TMPDIR` and nothing was committed.

What the columns mean:

- "Gap": the largest measured `getBoundingClientRect` gap between neighbours.
- "Empty px": screenshot pixels with max channel < 40.
- "EFP misses": `elementFromPoint` on every CSS pixel that did not hit a cell.
- "Elem/cell": video element size over cell size on each axis.
- "Visible": the fraction of clip width × height shown (geometry from the measured
  boxes; pixel ramp readings agree within ±0.01 for cover and ±0.06 for zoom).
- "Clock": the largest `|media advance per second − rate|` over 2.0 s.
- "Model": the largest `|currentTime − resolve_at|`.
- "Dropped": cumulative `getVideoPlaybackQuality`.

Cell rects are shown rounded to 0.01 px; Chrome stores 1/64 px.

| Case | Viewport | Cell k rect (px) | Gap | Overlap | Empty px | EFP misses |
| --- | --- | --- | --- | --- | --- | --- |
| cover N=5 | 375×812 | [0, k·162.39, 375, 162.39] | 0.015625 | 0 | **750** | 0 / 304500 |
| cover N=5 | 1280×720 | [k·256, 0, 256, 720] | 0 | 0 | 0 | 0 / 921600 |
| cover N=8 | 375×812 | [0, k·101.5, 375, 101.5] | 0 | 0 | 0 | 0 / 304500 |
| cover N=8 | 1280×720 | [k·160, 0, 160, 720] | 0 | 0 | 0 | 0 / 921600 |
| cover N=12 | 375×812 | [0, k·67.66, 375, 67.66] | 0.015625 | 0 | 0 | 0 / 304500 |
| cover N=12 | 1280×720 | [k·106.66, 0, 106.66, 720] | 0.015625 | 0 | 0 | 0 / 921600 |
| zoom N=1 | 375×812 | [0, 0, 375, 812] | 0 | 0 | 0 | 0 / 304500 |
| zoom N=1 | 1280×720 | [0, 0, 1280, 720] | 0 | 0 | 0 | 0 / 921600 |
| zoom N=3 | 375×812 | [0, k·270.66, 375, 270.66] | 0.015625 | 0 | 0 | 0 / 304500 |
| zoom N=3 | 1280×720 | [k·426.66, 0, 426.66, 720] | 0.015625 | 0 | 0 | 0 / 921600 |
| zoom N=5 | 375×812 | [0, k·162.39, 375, 162.39] | 0.015625 | 0 | 0 | 0 / 304500 |
| zoom N=5 | 1280×720 | [k·256, 0, 256, 720] | 0 | 0 | 0 | 0 / 921600 |
| zoom N=8 | 375×812 | [0, k·101.5, 375, 101.5] | 0 | 0 | 0 | 0 / 304500 |
| zoom N=8 | 1280×720 | [k·160, 0, 160, 720] | 0 | 0 | 0 | 0 / 921600 |
| zoom N=12 | 375×812 | [0, k·67.66, 375, 67.66] | 0.015625 | 0 | 0 | 0 / 304500 |
| zoom N=12 | 1280×720 | [k·106.66, 0, 106.66, 720] | 0.015625 | 0 | 0 | 0 / 921600 |

| Case | Viewport | Elem/cell | Visible w×h | Stretch | Clock | Model (s) | Dropped |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cover N=5 | 375×812 | 1.0 | 1.000×0.325 | 1.0 | 0.009 | 0.017 | 2/649 (0.3%) |
| cover N=5 | 1280×720 | 1.0 | 0.474×1.000 | 1.0 | 0.005 | 0.022 | 5/1186 (0.4%) |
| cover N=8 | 375×812 | 1.0 | 1.000×0.203 | 1.0 | 0.011 | 0.042 | 6/1171 (0.5%) |
| cover N=8 | 1280×720 | 1.0 | 0.296×1.000 | 1.0 | 0.007 | 0.053 | 11/2194 (0.5%) |
| cover N=12 | 375×812 | 1.0 | 1.000×0.135 | 1.0 | 0.013 | 0.064 | 175/1995 (**8.8%**) |
| cover N=12 | 1280×720 | 1.0 | 0.198×1.000 | 1.0 | 0.008 | 0.051 | 186/3838 (**4.8%**) |
| zoom N=1 | 375×812 | 8.000 | 0.125×0.125 | 1.62 | 0.000 | 0.024 | 0/96 |
| zoom N=1 | 1280×720 | 8.000 | 0.125×0.125 | 2.37 | 0.000 | 0.011 | 0/192 |
| zoom N=3 | 375×812 | 4.132 | 0.242×0.242 | 1.85 | 0.008 | 0.024 | 3/360 (0.8%) |
| zoom N=3 | 1280×720 | 4.132 | 0.242×0.242 | 1.27 | 0.008 | 0.011 | 6/699 (0.9%) |
| zoom N=5 | 375×812 | 3.049 | 0.328×0.328 | 3.08 | 0.012 | 0.022 | 2/681 (0.3%) |
| zoom N=5 | 1280×720 | 3.049 | 0.328×0.328 | 2.11 | 0.005 | 0.030 | 5/1288 (0.4%) |
| zoom N=8 | 375×812 | 2.299 | 0.435×0.435 | 4.93 | 0.010 | 0.041 | 6/1223 (0.5%) |
| zoom N=8 | 1280×720 | 2.299 | 0.435×0.435 | 3.38 | 0.006 | 0.017 | 13/2417 (0.5%) |
| zoom N=12 | 375×812 | 1.802 | 0.555×0.555 | 7.39 | 0.013 | 0.038 | 186/2096 (**8.9%**) |
| zoom N=12 | 1280×720 | 1.802 | 0.555×0.555 | 5.06 | 0.000 | 0.034 | 199/4368 (**4.6%**) |

In every case all N loops played (0 paused, ≥30 frame callbacks in 2 s each) at their own
rates. Resizing kept the same media elements (`same media after resize: true`), and there
were no page errors.

"Zoom" rows show **today's** fill path. The element is exactly `1/s` of the cell on each
axis, the visible fraction is `s × s`, and the stretch matches the table in the design
section. Under the recommended crop-then-cover, the magnification would be the same
`1/s`, the stretch 1.0, and the visible fractions those of the zoom table.

Hairline probe. I counted background-coloured device-pixel lines in screenshots of the
running runtime. "Snap" re-positioned boxes at integer device-pixel edges. "Bleed"
extended each non-last cell by 1 device px. Matrix: three cases (cover N=5, cover N=12,
zoom N=12) × {375×812, 390×844, 360×780} @1/2/3× and {1280×720, 1366×768} @1/2×, which is
39 combinations.

| Case | Viewport @DPR | Today | Snap | Bleed 1 dp |
| --- | --- | --- | --- | --- |
| cover N=5 | 375×812 @1 | 2 lines / 750 px | 0 | 0 |
| cover N=5 | 375×812 @2 | 4 / 3000 | 0 | 0 |
| cover N=5 | 375×812 @3 | 6 / 6750 | **6 / 6750** | 0 |
| cover N=5 | 1366×768 @1, @2 | 1 / 768; 2 / 3072 | 0 | 0 |
| cover N=12 | 390×844 @1, @2 | 4 / 1560; 8 / 6240 | 0 | 0 |
| cover N=12 | 390×844 @3 | 12 / 14040 | **12 / 14040** | 0 |
| cover N=12 | 1366×768 @1, @2 | 2 / 1536; 4 / 6144 | 0 | 0 |
| zoom N=12 | 1366×768 @1, @2 | 2 / 1536; 4 / 6144 | 0 | 0 |
| all other 27 combinations | | 0 | 0 | 0 |

The percentage positioning leaves 1/64 px LayoutUnit gaps (for example, cell 2 ends at
324.78125 and cell 3 starts at 324.796875). Chrome paints them as full background lines:
12 of 39 combinations today. Device-pixel snapping fails at 3× because thirds of a pixel
are not representable in 1/64 units. A 1-device-px bleed removed every line. This is the
evidence for decision 4. The peer's "exactly zero gap" holds only for some viewports.

Offline renderer: `render_triptych --state` for cover N=12, zoom N=12 and zoom N=1 at
360×780 portrait and 1280×720 landscape (24 frames). All exited 0 with **0** empty pixels;
strip extents were 64/66 px and 106/108 px, summing to 780 and 1280.

What did not work at N=1 or N=12, plainly:

- Engine: the Python state validator, `build_preview` and the runtime accept both.
- Blocked elsewhere: the client compiler refuses both (`:210-212`). `build_artifact001`
  refuses both by design. Float strips through `from_authoring_model` fail at N=7 and
  leave gaps at N=3 and N=12.
- Visual: today's slice path stretches up to 7.4× at N=12.
- Load: N=12 drops 4.6–8.9% of frames on this desktop.

## Acceptance criteria

- [ ] `git diff main -- src/simvltanea/authoring/artifact001_layouts.py` shows no change
  inside `_AUTHORED_DEFAULT`, and `build_artifact001(n)` output for n=2..7 is byte-identical
  to `main` (compare `to_json()`).
- [ ] `build_artifact001(1)`, `(8)` and `(13)` still raise `no reviewed engineering layout pair`.
- [ ] `strips_layouts(n)` for n=1..12 passes `validate_state` in both orientations; n=0 and
  n=13 raise.
- [ ] Seam tests 1–5 pass in pytest; test 6 passes in the browser suite; test 7 passes in
  the render suite.
- [ ] A malformed `--layouts` file, a preset with an unknown key, and any
  `src/simvltanea/layouts.json` each fail with a message naming the file. `grep -n "except Exception" src/simvltanea/authoring/artifact001_layouts.py`
  finds nothing.
- [ ] `python -m tools.verification.verify_layouts --examples` → `layouts ok`. A new
  `--presets examples/layout-presets/strips.json` → ok. A corpus of invalid cases each
  fails with its expected code.
- [ ] `python -m simvltanea.browser.layout_bundle` output is byte-identical to the current
  authored bundle; `--format 2` matches the shape above.
- [ ] Compiler: `SUPPORTED_LOOP_COUNTS` is 1..12; `one-loop` and `eight-loops` compile;
  13 refuses. An enabled global slice compiles to the same plan as Python's `compile_plan`.
- [ ] Browser: a strips N=5 state with slice shows stretch 1.0 (element aspect equals the
  source aspect) and zero background pixels in the hairline matrix.
- [ ] README, CONTRIBUTING, SEAMED_SLICE_FIELD and CONFIG state the amended counts; no
  document claims strips are artist-approved.
- [ ] Full suite, `verify_local_lifecycle`, `verify_repository_structure`, `ls-lint` and
  markdownlint pass.

## Work breakdown

| Lane | Goal | Files | Verify | Size | Depends on |
| --- | --- | --- | --- | --- | --- |
| A — preset core | Strips expansion, zoom curve, validator, adjacency, strict layout files; remove the ambient override | new `src/simvltanea/authoring/layout_presets.py` and its tests; `composition.py` (`validate_layouts` optional keys); `artifact001_layouts.py` (override path only); `authoring/__init__.py`; `tools/verification/verify_layouts.py` (+ tests); `examples/layout-presets/strips.json`; `fixtures/layouts/`; `layout.toml:42`; `ci.yml:167` | seam tests 1–5, acceptance rows 1–6 | M | none |
| B — browser raster | Bleed, `full_bleed`, crop-then-cover slice, corner radius, jitter overscan in the runtime; pass-through in `compile_plan` | `browser.runtime.js`, `browser_runtime.py`, `test_browser_runtime.py`, `test_preview_staging.py` | seam test 6, hairline matrix, stretch 1.0 | M–L | A (schema) |
| C — compiler, bundle, studio | N=1..12, new layout fields, global slice compiled in JS, bundle v2, studio reads counts | `browser.compiler.js`, `layout_bundle.py`, `test_browser_compiler.py`, `docs/authoring/BROWSER_COMPILER.md` | compiler parity tests, bundle byte-identity | M | A; `feat/web-client-compiler` merged |
| D — renderer parity, fixtures, docs | Hidden bleed, jitter crop and corner mask in ffmpeg; strips fixtures; documentation and demo | `render_triptych.py`, `test_composition_render.py`, `make_runtime_fixture.py`, `make_artifact_001.py`, `README.md`, `.github/CONTRIBUTING.md`, `SEAMED_SLICE_FIELD.md`, `CONFIG.md`, `ace-manifest.json`, site publishing | seam test 7, render matrix, docs review | M | A, B |

Hotspots:

- `src/simvltanea/authoring/__init__.py` (A): new exports (`strips_layouts`,
  `strips_slice`, `build_strips`, `adjacency`, `validate_layout_pair`,
  `load_layout_file`). The feature boundary gate requires them.
- `layout.toml` (A): drop the `{package}/layouts.json` source exception (`:42`).
- `README.md` (D): the support statement and family table.
- `ace-manifest.json` (D): its capability text "paired authored layouts" (`:21`) gains the
  strips family.
- `docs/plans/INDEX.md`: only the lane that adds a plan.
- `pyproject.toml`: **not touched**. Presets ship as Python data and examples as JSON in
  `examples/`. Shipping JSON inside the package would need both `package-data` and a new
  `layout.toml` exception.
- `browser.runtime.js` is also changed on `feat/web-runtime-public-hardening` and the
  studio stack. Expect conflicts; land B after those.

## Non-claims

- The strips and the zoom curve are **engineering presets** chosen to match the owner's
  sketch and words. They are **not artist-approved final designs**, and they do not
  change the status of the authored pairs (`artifact001_layouts.py:2-5`).
- Nothing here reconstructs TripTicks or any historical work.
- Resource capacity: the only claim is the measurement above. It covers one desktop
  (Apple M5, headless Chrome 156) with synthetic 540×720 clips at 3.5 Mbit/s, where N=12
  dropped 4.6–8.9% of frames. **No claim is made about phones**, Safari/WebKit (hairline
  behaviour included) or real footage.
- The masking claim is limited to geometry: no cell shows more than `s × s` of a frame
  through the slice. It is not a privacy guarantee about content.

## Open questions for the owner

1. **Zoom curve.** Recommended: `zoom = 8 / N^(3/5)` (8× at 1, 4.1× at 3, 3.0× at 5,
   2.3× at 8, 1.8× at 12). It keeps each clip at roughly 3–6% of its frame for N ≥ 2 while
   clarity rises. Alternatives are `8/N` or an explicit table; all are data.
2. **"Distorted": literal stretch or just abstract?** Recommended: aspect-preserving
   crop-then-cover, which matches exports. Today's stretch grows to 7.4× at N=12, the
   opposite of "more clarity". A stretch factor could become an explicit style parameter
   later.
3. **Is 12 the ceiling?** Recommended: yes, 1..12. 13+ is refused until it is measured on
   the phones the work targets, because decode drops already reach 9% at 12 on a desktop.

## Amendments found in review and testing (2026-11-06)

These refine "Overlap" and "Style parameters"; the decision table stands. Each was found by
independent review of the browser and export lanes and is covered by a test that fails without it.

- **The corner radius is reduced where the bleed cannot back it.** The bleed under a rounded
  corner is capped at half of the thinnest later neighbour on that side, so the target
  `overlap_px + ceil(radius)` can be out of reach on a thin strip. Each cell's effective radius
  is limited so that `overlap_px` plus the radius fits under every earlier neighbour's granted
  bleed; a cell with nothing to back its corners stays square. Without the limit, N=12 on a
  360x360 canvas (30 px strips, configured radius 18 px) exposed the background in the export,
  and 800x800 at 2x showed 44 background pixels in the browser.
- **The bleed grows only where the later cells cover it.** A side grows only when the nominal
  boxes of all later-drawn cells cover the whole bleed strip, and a grown corner square must be
  covered too. This matters for non-strip layouts; strips are unaffected. Browser and export
  apply the same rule.
- **Jitter axis for cells that are not strips.** A cell spanning only the full width slides along
  x, only the full height along y, and a cell spanning both follows the orientation (x in
  portrait, y in landscape). Any other cell uses its longer side. Browser and export agree.
- **Measurement.** The hairline matrix includes the near-square canvases 360x360, 744x768 and
  800x800, where strips are thinnest relative to the radius.
