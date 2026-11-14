# Configuration — Everything is a knob

All seamed-slice behaviour is **state + edition + manifest + CLI + layout file + browser plan** configurable. No hard-coded secrets.

## Slice field — never full-frame

- **State file** (`var/proofs/state-*.json`, `var/artifact-001/state-*.json`): `slice: {enabled: bool, width: "1/2", height: "2/3"}` — rational strings, `w*h<1` enforced `src/simvltanea/authoring/composition.py:129`.
- **Edition preset** (`editions/registry.json:21` `simultaneous_field` → `settings.slice`): `editions/registry.json` `simvltanea-slice` shows `{enabled:true, width:0.5, height:0.66}` validated by `tools/verification/verify_editions.py:219` `validate_slice_config()` (float 0..1).
- **Project/manifest** (`examples/manifest.example.json`, `examples/project.example.json`): top-level `slice: {enabled,width,height}` merged by `src/simvltanea/rendering/render_triptych.py:340` `slice_cfg` and `src/simvltanea/authoring/composition.py:537` state override.
- **CLI** (`src/simvltanea/rendering/render_triptych.py:232` `parse_args()`): `--slice-enabled true|false`, `--slice-width 0.33`, `--slice-height 0.45`, `--config examples/slice-seam-config.json`. Overrides state even when `--state` is used (`src/simvltanea/authoring/composition.py:507` `render_from_args()` merges `slice_over` → `validate_state()`).
- **Fixture generator** (`src/simvltanea/generators/make_runtime_fixture.py:132`): `--slice-width`, `--slice-height` (default 0.5/0.66). `prepare(slice_width, slice_height, ...)`.
- **Browser** (`src/simvltanea/browser/browser_runtime.py:85` `compile_plan()` canonicalizes `slice_rect` to plan; `src/simvltanea/browser/browser.runtime.js:53` `applySlice()` overflow-hidden scaled media).
- **Defaults** `src/simvltanea/authoring/composition.py:28` `DEFAULT_SLICE = {enabled:false, width:"1/2", height:"1/2"}` — disable by omitting `slice` for backward compat.

Deterministic random `slice_rect()` `src/simvltanea/authoring/composition.py:297` uses same `sha256-counter-v1` `src/simvltanea/authoring/composition.py:20` as bank selection, `%1000` discretization, `limit_denominator(1e9)` to stay in rational bounds. Vary `seed`, `period`, or `w/h` to change locations.

## Seam — blur/merge/morph

- **State**: `seam: {enabled, width: "1/28", mode: "feather", sigma: "1/180"}` — `width` 0..0.15, `sigma` 0..0.1, `mode` in `SEAM_MODES` `("blur","feather","morph")` `src/simvltanea/authoring/composition.py:25,147`.
- **Edition**: `settings.seam` validated by `tools/verification/verify_editions.py:235` `validate_seam_config()`.
- **Project/manifest**: top-level `seam` merged in `src/simvltanea/rendering/render_triptych.py:341`.
- **CLI**: `--seam-enabled`, `--seam-width`, `--seam-mode`, `--seam-sigma`, `--config`.
- **Fixture**: `--seam-width`, `--seam-mode`, `--seam-sigma`.
- **Renderer**: `src/simvltanea/rendering/render_triptych.py:1028` adjacency detection + `crop+boxblur+overlay` strip, `seam_width` → pixel gutter (even), `seam_sigma*min(W,H)` → `boxblur` radius, mode `morph` vs `feather` vs `blur`. Configurable per segment via `Segment.seam`.
- **Browser**: `src/simvltanea/browser/browser.runtime.js:53` `renderSeams()` — `backdrop-filter: blur(sigma)`, mode-aware opacity/mixBlendMode, seam width → CSS strip. All driven by `plan.seam`.

## N and geometry — strips 1 to 12, authored 2 to 7

- **Strips (default family)** `src/simvltanea/authoring/layout_presets.py`: full-bleed rows
  (portrait) and columns (landscape) for N=1..12, zoom tied to N through the state-wide `slice`.
  Choose them with `build_strips(count)`, `strips_layouts(count)` and `strips_slice(count)`; the
  preset is data (`examples/layout-presets/strips.json`). See [Layout presets](LAYOUT_PRESETS.md).
- **Authored pairs** `src/simvltanea/authoring/artifact001_layouts.py` `AUTHORED`: reviewed
  engineering pairs for N=2..12 through `build_artifact001(count)`. Other counts raise.
- **Your own layouts** are explicit files given by path: `load_layout_file(path)` reads a
  `simvltanea.layout-preset/1` or `simvltanea.layout-pair/1` file and validates it strictly.
  Nothing is read from inside the package; a `src/simvltanea/layouts.json` makes importing
  `simvltanea.authoring` fail.
- **Fixture generators**: `src/simvltanea/generators/make_artifact_001.py` and
  `src/simvltanea/generators/make_runtime_fixture.py` build the authored pairs for `2..7` and
  strips states for N=1, 5, 8 and 12, both orientations.
- **Canvas**: `width/height/fps` per manifest `canvas`, CLI `--width/--height`, edition `source.width/height/fps` and `settings.canvas`.

## Export length — the 1,024-segment cap

`render_triptych --state` (and `independent-loop-compositor render --state`) exports through FFmpeg
in segments. `compile_segments()` in `src/simvltanea/authoring/composition.py` starts a new segment
at every frame where, in the exported orientation, any loop wraps, changes source, re-rolls its
slice, is held or released, or where a move event changes the layout. Coinciding changes share one
segment. The renderer refuses more than `MAX_SEGMENTS = 1024` segments in one export. The cap is a
resource guard and stays fixed.

The cap counts every loop together. The browser's guard allows 1,024 spans times the loop count,
so a long piece that plays in the studio can still be refused on export. Many short loops make this more
likely. With the default selection period (the loop's length) a slice re-roll falls on the wrap and
adds no segment. An export needs at most roughly `1 + Σ seconds × rate / loop length` segments. For
example, the `make_artifact_001` strips state for twelve 3-second loops (rates 1 to 1.77) needs
3,058 segments for 600 seconds, and its first 4,808 frames (about 200 seconds) fit.

The refusal names the cap and the remedy. That state at 600 seconds prints:

```text
composition: composition needs 3058 render segments, over the renderer's cap of 1024 segments
(MAX_SEGMENTS); a new segment starts at every loop wrap, source change, slice re-roll and event.
Remedy: shorten the export to at most 4808 frames (200.333 s at 24 fps), use longer loops or fewer
loops. No panels were removed
```

(The message is one line; it is wrapped here.)

To export, shorten the piece to the frame count the message gives (the studio's `seconds`, or the
state's `frames`), use longer loops, or use fewer loops. No loop is dropped to make it fit.

## Canvas, FPS, CRF, presets, audio — unchanged configurability

All existing `render_triptych.py` knobs (`--width`, `--height`, `--fps`, `--crf`, `--preset`, `--phrase`, `--timing`, `--audio-*`, `--tone*`, `--panel-order`) + manifest `canvas`/`render`/`audio`/`effects` remain; slice/seam added orthogonally via `--config` JSON.

## Examples

```bash
# 1) State override via CLI — any knob
PYTHONPATH=src python3 -m simvltanea.render_triptych --state var/proofs/state-2.json --orientation portrait \
  --slice-enabled true --slice-width 0.33 --slice-height 0.5 \
  --seam-enabled true --seam-width 0.08 --seam-mode morph --seam-sigma 0.02 \
  --output var/proofs/renders/custom.mp4 --width 360 --height 640 --preset ultrafast --crf 28

# 2) Via JSON config (all knobs)
cat examples/slice-seam-config.json | PYTHONPATH=src python3 -m simvltanea.make_runtime_fixture --slice-width 0.33 --seam-mode blur

# 3) Edition preset (text config over same engine)
# editions/registry.json -> simvltanea-slice settings.{slice,seam}
python3 -m tools.verification.verify_editions  # validates 7 editions
python3 -m tools.editions.build_edition simvltanea-slice --render --draft

# 4) Your own layouts, validated by path (never copied into the package)
python3 -m tools.verification.verify_layouts --layouts my-layouts.json
python3 -m tools.verification.verify_layouts --presets examples/layout-presets/strips.json
```

See `docs/architecture/SEAMED_SLICE_FIELD.md` for invariant, `examples/slice-seam-config.json` for annotated knob file, `examples/layout-presets/strips.json` and `examples/layouts.json` for geometry.
