# Configuration — Everything is a knob

All seamed-slice behaviour is **state + edition + manifest + CLI + layout file + browser plan** configurable. No hard-coded secrets.

## Slice field — never full-frame

- **State file** (`runtime-proof/state-*.json`, `artifact-001/state-*.json`): `slice: {enabled: bool, width: "1/2", height: "2/3"}` — rational strings, `w*h<1` enforced `core/composition.py:129`.
- **Edition preset** (`editions.json:21` `simultaneous_field` → `settings.slice`): `editions.json` `simvltanea-slice` shows `{enabled:true, width:0.5, height:0.66}` validated by `tools/verify_editions.py:219` `validate_slice_config()` (float 0..1).
- **Project/manifest** (`examples/manifest.example.json`, `examples/project.example.json`): top-level `slice: {enabled,width,height}` merged by `core/render_triptych.py:340` `slice_cfg` and `core/composition.py:537` state override.
- **CLI** (`core/render_triptych.py:232` `parse_args()`): `--slice-enabled true|false`, `--slice-width 0.33`, `--slice-height 0.45`, `--config examples/slice-seam-config.json`. Overrides state even when `--state` is used (`core/composition.py:507` `render_from_args()` merges `slice_over` → `validate_state()`).
- **Fixture generator** (`core/make_runtime_fixture.py:132`): `--slice-width`, `--slice-height` (default 0.5/0.66). `prepare(slice_width, slice_height, ...)`.
- **Browser** (`core/browser_runtime.py:85` `compile_plan()` canonicalizes `slice_rect` to plan; `core/browser_runtime.js:53` `applySlice()` overflow-hidden scaled media).
- **Defaults** `core/composition.py:28` `DEFAULT_SLICE = {enabled:false, width:"1/2", height:"1/2"}` — disable by omitting `slice` for backward compat.

Deterministic random `slice_rect()` `core/composition.py:297` uses same `sha256-counter-v1` `core/composition.py:20` as bank selection, `%1000` discretization, `limit_denominator(1e9)` to stay in rational bounds. Vary `seed`, `period`, or `w/h` to change locations.

## Seam — blur/merge/morph

- **State**: `seam: {enabled, width: "1/28", mode: "feather", sigma: "1/180"}` — `width` 0..0.15, `sigma` 0..0.1, `mode` in `SEAM_MODES` `("blur","feather","morph")` `core/composition.py:25,147`.
- **Edition**: `settings.seam` validated by `tools/verify_editions.py:235` `validate_seam_config()`.
- **Project/manifest**: top-level `seam` merged in `core/render_triptych.py:341`.
- **CLI**: `--seam-enabled`, `--seam-width`, `--seam-mode`, `--seam-sigma`, `--config`.
- **Fixture**: `--seam-width`, `--seam-mode`, `--seam-sigma`.
- **Renderer**: `core/render_triptych.py:1028` adjacency detection + `crop+boxblur+overlay` strip, `seam_width` → pixel gutter (even), `seam_sigma*min(W,H)` → `boxblur` radius, mode `morph` vs `feather` vs `blur`. Configurable per segment via `Segment.seam`.
- **Browser**: `core/browser_runtime.js:53` `renderSeams()` — `backdrop-filter: blur(sigma)`, mode-aware opacity/mixBlendMode, seam width → CSS strip. All driven by `plan.seam`.

## N and geometry — minimum 2

- **Authored pairs** `core/artifact001_layouts.py:12` `AUTHORED` 2..6 (now 5 pairs). **Configurable**: copy `examples/layouts.json` → `core/layouts.json` (`_load_authored()` merges). Add any `N` with `portrait`/`landscape` rect arrays `[[x,y,w,h], ...]` in 0..1 (see `docs/SEAMED_SLICE_FIELD.md`).
- **Count CLI**: `python3 core/artifact001_layouts.py 2 --output ...`, `core/make_artifact_001.py` loop `2..6` (override via `build_artifact001(count)` call), `core/make_runtime_fixture.py` loop `2..7` (SEVEN stays experimental).
- **Canvas**: `width/height/fps` per manifest `canvas`, CLI `--width/--height`, edition `source.width/height/fps` and `settings.canvas`.

## Canvas, FPS, CRF, presets, audio — unchanged configurability

All existing `render_triptych.py` knobs (`--width`, `--height`, `--fps`, `--crf`, `--preset`, `--phrase`, `--timing`, `--audio-*`, `--tone*`, `--panel-order`) + manifest `canvas`/`render`/`audio`/`effects` remain; slice/seam added orthogonally via `--config` JSON.

## Examples

```bash
# 1) State override via CLI — any knob
python3 core/render_triptych.py --state runtime-proof/state-2.json --orientation portrait \
  --slice-enabled true --slice-width 0.33 --slice-height 0.5 \
  --seam-enabled true --seam-width 0.08 --seam-mode morph --seam-sigma 0.02 \
  --output runtime-proof/renders/custom.mp4 --width 360 --height 640 --preset ultrafast --crf 28

# 2) Via JSON config (all knobs)
cat examples/slice-seam-config.json | python3 core/make_runtime_fixture.py --slice-width 0.33 --seam-mode blur

# 3) Edition preset (text config over same engine)
# editions.json -> simvltanea-slice settings.{slice,seam}
python3 tools/verify_editions.py  # validates 7 editions
python3 tools/build_edition.py simvltanea-slice --render --draft

# 4) Layout override
cp examples/layouts.json core/layouts.json  # edit rects, then
python3 core/make_artifact_001.py --prepare-only && python3 core/make_runtime_fixture.py
```

See `docs/SEAMED_SLICE_FIELD.md` for invariant, `examples/slice-seam-config.json` for annotated knob file, `examples/layouts.json` for geometry.
