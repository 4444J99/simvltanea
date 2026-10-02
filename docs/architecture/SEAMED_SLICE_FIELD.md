# Seamed Slice Field — SIMVLTANEA

> Minimum 2 videos; connecting sides blur/merge/morph; no source ever reveals full frame.

## Rule

- **N >= 2** authored pairs exist for 2,3,4,5,6 via `src/simvltanea/authoring/artifact001_layouts.py:17` `AUTHORED`. 7 remains experimental `src/simvltanea/generators/make_runtime_fixture.py:25` `SEVEN`.
- **Every panel is a deterministic random crop** of a larger source video: `slice: {enabled, width, height}` at `src/simvltanea/authoring/composition.py:297` `slice_rect()` using the same `sha256-counter-v1` `src/simvltanea/authoring/composition.py:20` RNG as `choose_source()`. Crop is `x = hash%1000/1000 * (1-w)`, `y = hash%1000/1000 * (1-h)`, `w/h` from `slice` config. Invariant `validate_slice()` `src/simvltanea/authoring/composition.py:136` enforces `0<w<1,0<h<1, w*h<1` so at least one dimension is cropped — full-frame reveal is rejected before encoding.
- **Opposing sides are paired**: video 1 is a random slice sequenced next to video 2 also a random slice cropped from opposing source — each added slice repeats same slice+seam process (`slice_rect` is per-loop per-period, so every `period` the slice location rerolls deterministically, never via wall clock).
- **Connecting sides blur/merge/morph**: `seam: {enabled, width, mode, sigma}` at `src/simvltanea/authoring/composition.py:316` `seam_config()`. Modes `blur|feather|morph` (`SEAM_MODES`). FFmpeg implementation `src/simvltanea/rendering/render_triptych.py:1030` `render_segment()` detects adjacency of `pixel_placements()` `src/simvltanea/authoring/composition.py:386` rects and adds a blurred strip `crop+boxblur+overlay` centered at the seam line. Width `width` is fraction of canvas (0..0.15) and `sigma` drives `boxblur` luma_radius. Browser mirrors with CSS `backdrop-filter: blur()` + `filter: blur()` `src/simvltanea/browser/browser_runtime.js:53` `renderSeams()`.
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
- `src/simvltanea/browser/browser_runtime.js:70` `applySlice()` overflow:hidden + scaled media offset, `renderSeams()` CSS seam overlays.
- Fixtures: `src/simvltanea/generators/make_runtime_fixture.py:107` generates `state-slice.json` (N=2 feather) and `state-slice-3.json` (N=3 morph); `src/simvltanea/generators/make_artifact_001.py:54` now builds 2..6.
- Edition: `editions/registry.json:28` `simvltanea-slice` (video-ready, folder `samples/inaugural`, slice 1/2×0.66, seam 0.035 feather).

## Verification

```bash
PYTHONPATH=src python3 -m simvltanea.make_runtime_fixture        # regenerates 2..7 + slice variants
PYTHONPATH=src python3 -m simvltanea.make_artifact_001 --draft   # 2..6 draft renders 360p
python3 -m tools.verification.verify_editions            # 7 editions ok
python3 -m unittest discover -s tests       # 73+ non-browser; plan tests 12 ok
# browser continuity (requires Chromium + ffmpeg):
python3 -m unittest tests.browser.test_browser_runtime -v
# full ffmpeg proof:
PYTHONPATH=src python3 -m simvltanea.render_triptych --state var/proofs/state-slice.json --orientation portrait --output var/proofs/renders/slice-portrait-test.mp4 --preset ultrafast --crf 28 --width 360 --height 640
```
