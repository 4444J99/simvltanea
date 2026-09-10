# Plan — Seamed Slice Field (2026-09-10)

> Doctrine: Verify → Heal → Expand → Evolve. Implements user prompt: minimum 2 videos, connecting sides blur/merge/morph via seamed slice field (never full-frame reveal).

## Objective

- N=2..6 authored pairs (formerly 3..6)
- Every panel is a deterministic random cropped slice of a larger source (one source never reveals full self)
- Opposing video slice sequenced next to other; each added slice repeats same slice+seam rule
- Connecting sides blur/feather/morph via configurable seam

## Waves executed

### Wave 0 — Verify/Heal: CI + branches

- `.github/workflows/ci.yml:32` inserts `Generate runtime-proof fixtures` (`python3 core/make_runtime_fixture.py` + `make_artifact_001.py --draft`) before test step — fixes 29 browser `Media failure: loop-*` (missing `runtime-proof/media`).
- Materialized lanes `lane/verify` `lane/heal` `lane/expand` `lane/evolve` as refs (previously only declared in `BRANCHES.md:9`).

### Wave 1 — Layouts: N=2

- `core/artifact001_layouts.py:17` `AUTHORED` adds 2: portrait `((0.04,0.03,0.92,0.44),(0.04,0.52,0.92,0.44))` landscape `((0.03,0.05,0.46,0.90),(0.51,0.05,0.46,0.90))`.
- `README.md:55` table updated 2..6.
- `core/make_artifact_001.py:54` loop 2..6; control fixture fixed to use `state-3` not `state-2`.
- `tests/test_composition_model.py:20` acceptance set updated to `{2,3,4,5,6}`.

### Wave 2 — Composition model: slice + seam

- `core/composition.py:18` `SEAM_MODES`, `DEFAULT_SLICE/SEAM`; `validate_slice()` `:136` enforces `0<w,h<1` and `w*h<1` (area<1) and `validate_seam()` `:151`.
- `validate_state()` `:176` optional `slice`/`seam` fields, backward compatible.
- `local_time()` `:283` tolerates missing `anchor` for slice domain.
- `slice_rect()` `:297` deterministic `sha256-counter-v1` with distinct domain `"slice"`, `%1000` discretization and `limit_denominator`.
- `seam_config()` `:316`, `resolve_at()` `:327` attaches `slice_rect` per loop, `continuous()` `:401` splits on slice change, `compile_segments()` `:416` attaches `Panel.source_crop` + `Segment.seam`.
- `core/__init__.py:7` removal of phantom `LAYOUT_KEYS` import.

### Wave 3 — Renderer

- `core/render_triptych.py:91` `Panel.source_crop`, `118` `Segment.seam`.
- `_crop_prefix()` `:824` inserted before `trim` in clocked and `forward/reverse/pingpong` branches.
- `render_segment()` `:1028` seam blur: adjacency detection via `pixel_placements`, `crop+boxblur+overlay` strip centered at seam line, supports `feather|blur|morph`, even-width gutter, sigma-driven radius.

### Wave 4 — Browser preview

- `core/browser_runtime.py:42` `_continues()` includes `slice_rect`; `compile_plan()` `:85` canonicalizes slice/seam, emits `plan.slice`/`plan.seam`.
- `core/browser_runtime.js:53` `applySlice()` (overflow:hidden scaled media), `renderSeams()` (CSS `backdrop-filter: blur` seam overlays per layout, mode-aware).

### Wave 5 — Fixtures / Edition / Docs

- `core/make_runtime_fixture.py:85` loop 2..7, adds `state-slice.json` (N=2 feather 1/28 sigma 1/180) and `state-slice-3.json` (N=3 morph) + previews.
- `editions.json:21` `simultaneous_field.members` adds `simvltanea-slice`; new edition `simvltanea-slice` folder edition with slice/seam settings and `composition.panel_arrangement_role` documenting rule.
- `docs/SEAMED_SLICE_FIELD.md` feature spec; `STATUS.md` updated green table.

## Verification

- `pytest tests/test_authoring_contract … -q` 73 passed
- `python3 -m unittest tests.test_browser_runtime.PlanTests -v` 12 passed
- `python3 tools/verify_editions.py` 7 editions ok
- `python3 core/make_runtime_fixture.py` generates 2..7 + slice variants without out-of-bounds
- `python3 core/make_artifact_001.py --draft` 11 renders (2..6 + still-controls)
- Seam render proof `runtime-proof/renders/slice-portrait-test.mp4` 360×640 yuv420p h264 223K single-segment with crop+seam

## Remaining

- Wave 3 upstream closeout `organvm/portvs#8` parked awaiting operator `Post upstream closeout? y/N` -> `gh issue comment 8 --repo organvm/portvs --body-file docs/UPSTREAM_COORDINATION.md`
- Audio v1.1 (issue #2) and N=7 (issue #3) still parked per `BRANCHES.md:15` lane/evolve.
