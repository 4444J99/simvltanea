# Seamed Slice Field — SIMVLTANEA

> N >= 1 under strips (1 to 12); authored pairs 2 to 7. Connecting sides blur/merge/morph;
> no source ever reveals full frame.

## Rule

- **N >= 1 under strips; authored 2..12.** The strips family (`src/simvltanea/authoring/layout_presets.py`)
  computes full-bleed rows (portrait) and columns (landscape) for N=1..12. The authored family
  (`src/simvltanea/authoring/artifact001_layouts.py` `AUTHORED`) has reviewed engineering pairs for
  N=2..12. A count outside the chosen family fails; it is never filled, duplicated or moved to the
  other family. Both are engineering geometries, not artist-approved designs.
- **Every panel is a deterministic random crop** of a larger source video: `slice: {enabled, width, height}` at `src/simvltanea/authoring/composition.py:297` `slice_rect()` using the same `sha256-counter-v1` `src/simvltanea/authoring/composition.py:20` RNG as `choose_source()`. Crop is `x = hash%1000/1000 * (1-w)`, `y = hash%1000/1000 * (1-h)`, `w/h` from `slice` config. Invariant `validate_slice()` `src/simvltanea/authoring/composition.py:136` enforces `0<w<1,0<h<1, w*h<1` so at least one dimension is cropped — full-frame reveal is rejected before encoding.
- **Opposing sides are paired**: video 1 is a random slice sequenced next to video 2 also a random slice cropped from opposing source — each added slice repeats same slice+seam process (`slice_rect` is per-loop per-period, so every `period` the slice location rerolls deterministically, never via wall clock).
- **Connecting sides blur/merge/morph**: `seam: {enabled, width, mode, sigma}` at `src/simvltanea/authoring/composition.py:316` `seam_config()`. Modes `blur|feather|morph` (`SEAM_MODES`). FFmpeg implementation `src/simvltanea/rendering/render_triptych.py:1030` `render_segment()` detects adjacency of `pixel_placements()` `src/simvltanea/authoring/composition.py:386` rects and adds a blurred strip `crop+boxblur+overlay` centered at the seam line. Width `width` is fraction of canvas (0..0.15) and `sigma` drives `boxblur` luma_radius. Browser mirrors with CSS `backdrop-filter: blur()` + `filter: blur()` `src/simvltanea/browser/browser.runtime.js:53` `renderSeams()`.
- **Phase independence preserved**: `continuous()` `src/simvltanea/authoring/composition.py:401` splits segments when `slice_rect` changes, so the N-loop rational clocks `src/simvltanea/authoring/composition.py:43` `local_time()` remain independent; `allow_source_reuse: false` `src/simvltanea/authoring/composition.py:330` still forbids duplicated IDs or hashed bytes.

## State shape (optional, backward-compatible)

```json
{
  "slice": {"enabled": true, "width": "1/2", "height": "2/3"},
  "seam": {"enabled": true, "width": "1/28", "mode": "feather", "sigma": "1/180"}
}
```

Omitted `slice`/`seam` disables feature (existing states unchanged). `validate_state()` accepts but validates counts when present.

## Compiler + Renderer

- `src/simvltanea/authoring/composition.py:283` `local_time()` handles optional `anchor` for slice cycles.
- `src/simvltanea/authoring/composition.py:297` `slice_rect()` pure SHA-256, limit_denominator 1e9.
- `src/simvltanea/authoring/composition.py:401` `continuous()` includes slice discontinuity.
- `src/simvltanea/authoring/composition.py:416` `compile_segments()` attaches `Panel.source_crop` and `Segment.seam`.
- `src/simvltanea/rendering/render_triptych.py:824` `_crop_prefix()` before `trim`, `_crop` applied also to `forward/reverse/pingpong` branches.
- `src/simvltanea/browser/browser_runtime.py:49` `compile_plan()` canonicalizes slice rects and seam, `_continues()` checks slice.
- `src/simvltanea/browser/browser.runtime.js:70` `applySlice()` overflow:hidden + scaled media offset, `renderSeams()` CSS seam overlays.
- Fixtures: `src/simvltanea/generators/make_runtime_fixture.py` generates `state-slice.json` (N=2 feather) and `state-slice-3.json` (N=3 morph), plus `state-strips-{1,5,8,12}.json` and their `-styled` variants on ramp clips; `src/simvltanea/generators/make_artifact_001.py` builds authored 2..7 and strips 1, 5, 8 and 12.
- Edition: `editions/registry.json:28` `simvltanea-slice` (video-ready, folder `samples/inaugural`, slice 1/2×0.66, seam 0.035 feather).

## Strips: zoom tied to N, drawn without gaps

Strips use the same state-wide `slice` as zoom: `width = height = s(N)`, so magnification over
plain cover is exactly `1/s` (`zoom(N) = 8 / N^(3/5)`, at least 10/9). The renderer crops the slice
window and then covers the cell; it never stretches. A layout with `presentation` is drawn by
`presentation_placements()` and `raster_geometry()` in `src/simvltanea/rendering/render_triptych.py`:

- **Bleed.** A side shared with a later-drawn strip grows by `2*ceil(overlap_px/2)` device pixels,
  clamped to half that strip, and only where later cells cover the whole bleed. The bleed is taken
  from the same fitted picture around the nominal window, and the later overlay hides it. Exports
  are therefore identical for every `overlap_px` (`test_bleed_is_hidden_and_never_changes_a_visible_pixel`).
- **Rounded corners.** Only the corners on a side shared with an earlier strip are rounded, by an
  anti-aliased alpha mask (`geq` + `alphamerge`) on the later overlay. The earlier strip's bleed grows
  by `ceil(radius)` beneath them, so no corner shows background. The bleed is capped at half of the
  thinnest later strip on that side, rounded down to an even number of pixels, so on a strip thinner
  than about `2*(overlap_px + radius)` the radius is reduced until `overlap_px + radius` fits under
  the cap. The radius is also reduced to what every earlier neighbour's granted bleed covers: a bleed
  dropped by the coverage guard backs no corner, and a cell with nothing to back its corners stays
  square. The earlier strip therefore always backs the whole cutout.
- **Lateral jitter.** The picture is fitted to the cell overscanned by `2*ceil(J*L/2)` pixels at both
  ends of the strip's long axis (`L` is the canvas extent along it) and slides by `lateral_offset*L`,
  rounded to even. A single strip slides along x in portrait and along y in landscape.

Layouts without `presentation` keep the historical filter graph byte for byte
(`test_legacy_filter_graphs_are_unchanged`).

## Verification

```bash
PYTHONPATH=src python3 -m simvltanea.make_runtime_fixture        # authored 2..7, slice variants, strips 1/5/8/12
PYTHONPATH=src python3 -m simvltanea.make_artifact_001 --draft   # authored 2..7 and strips draft renders 360p
python3 -m tools.verification.verify_editions            # 7 editions ok
python3 -m unittest discover -s tests       # 73+ non-browser; plan tests 12 ok
# browser continuity (requires Chromium + ffmpeg):
python3 -m unittest simvltanea.browser.test_browser_runtime -v
# full ffmpeg proof:
PYTHONPATH=src python3 -m simvltanea.render_triptych --state var/proofs/state-slice.json --orientation portrait --output var/proofs/renders/slice-portrait-test.mp4 --preset ultrafast --crf 28 --width 360 --height 640
```
