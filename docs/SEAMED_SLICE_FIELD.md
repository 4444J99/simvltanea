# Seamed Slice Field — SIMVLTANEA

> Minimum 2 videos; connecting sides blur/merge/morph; no source ever reveals full frame.

## Rule

- **N >= 2** authored pairs exist for 2,3,4,5,6 via `core/artifact001_layouts.py:17` `AUTHORED`. 7 remains experimental `core/make_runtime_fixture.py:25` `SEVEN`.
- **Every panel is a deterministic random crop** of a larger source video: `slice: {enabled, width, height}` at `core/composition.py:297` `slice_rect()` using the same `sha256-counter-v1` `core/composition.py:20` RNG as `choose_source()`. Crop is `x = hash%1000/1000 * (1-w)`, `y = hash%1000/1000 * (1-h)`, `w/h` from `slice` config. Invariant `validate_slice()` `core/composition.py:136` enforces `0<w<1,0<h<1, w*h<1` so at least one dimension is cropped — full-frame reveal is rejected before encoding.
- **Opposing sides are paired**: video 1 is a random slice sequenced next to video 2 also a random slice cropped from opposing source — each added slice repeats same slice+seam process (`slice_rect` is per-loop per-period, so every `period` the slice location rerolls deterministically, never via wall clock).
- **Connecting sides blur/merge/morph**: `seam: {enabled, width, mode, sigma}` at `core/composition.py:316` `seam_config()`. Modes `blur|feather|morph` (`SEAM_MODES`). FFmpeg implementation `core/render_triptych.py:1030` `render_segment()` detects adjacency of `pixel_placements()` `core/composition.py:386` rects and adds a blurred strip `crop+boxblur+overlay` centered at the seam line. Width `width` is fraction of canvas (0..0.15) and `sigma` drives `boxblur` luma_radius. Browser mirrors with CSS `backdrop-filter: blur()` + `filter: blur()` `core/browser_runtime.js:53` `renderSeams()`.
- **Phase independence preserved**: `continuous()` `core/composition.py:401` splits segments when `slice_rect` changes, so the N-loop rational clocks `core/composition.py:43` `local_time()` remain independent; `allow_source_reuse: false` `core/composition.py:330` still forbids duplicated IDs or hashed bytes.

## State shape (optional, backward-compatible)

```json
{
  "slice": {"enabled": true, "width": "1/2", "height": "2/3"},
  "seam": {"enabled": true, "width": "1/28", "mode": "feather", "sigma": "1/180"}
}
```

Omitted `slice`/`seam` disables feature (existing states unchanged). `validate_state()` accepts but validates counts when present.

## Compiler + Renderer

- `core/composition.py:283` `local_time()` handles optional `anchor` for slice cycles.
- `core/composition.py:297` `slice_rect()` pure SHA-256, limit_denominator 1e9.
- `core/composition.py:401` `continuous()` includes slice discontinuity.
- `core/composition.py:416` `compile_segments()` attaches `Panel.source_crop` and `Segment.seam`.
- `core/render_triptych.py:824` `_crop_prefix()` before `trim`, `_crop` applied also to `forward/reverse/pingpong` branches.
- `core/browser_runtime.py:49` `compile_plan()` canonicalizes slice rects and seam, `_continues()` checks slice.
- `core/browser_runtime.js:70` `applySlice()` overflow:hidden + scaled media offset, `renderSeams()` CSS seam overlays.
- Fixtures: `core/make_runtime_fixture.py:107` generates `state-slice.json` (N=2 feather) and `state-slice-3.json` (N=3 morph); `core/make_artifact_001.py:54` now builds 2..6.
- Edition: `editions.json:28` `simvltanea-slice` (video-ready, folder `samples/inaugural`, slice 1/2×0.66, seam 0.035 feather).

## Verification

```bash
python3 core/make_runtime_fixture.py        # regenerates 2..7 + slice variants
python3 core/make_artifact_001.py --draft   # 2..6 draft renders 360p
python3 tools/verify_editions.py            # 7 editions ok
python3 -m unittest discover -s tests       # 73+ non-browser; plan tests 12 ok
# browser continuity (requires Chromium + ffmpeg):
python3 -m unittest tests.test_browser_runtime -v
# full ffmpeg proof:
python3 core/render_triptych.py --state runtime-proof/state-slice.json --orientation portrait --output runtime-proof/renders/slice-portrait-test.mp4 --preset ultrafast --crf 28 --width 360 --height 640
```
