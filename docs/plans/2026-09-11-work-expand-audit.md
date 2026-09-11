# Work Audit — lane/expand full-renders (2026-09-11)

> Branch: `work/lane/expand/full-renders` → `lane/expand` → `main`. Cut from `main@1bd5b86` per `BRANCHES.md:20`.

## Intent

Governance demonstration that `lane/expand` healed scope is replayed via proper `work/<lane>/*` PR flow. No functional change — audits already-shipped expansion on `main`:

- **N=2 authored** `core/artifact001_layouts.py:17` portrait `((0.04,0.03,0.92,0.44),(0.04,0.52,0.92,0.44))` landscape `((0.03,0.05,0.46,0.90),(0.51,0.05,0.46,0.90))` + `core/layouts.json` override via `_load_authored` `:41` (`tests/test_composition_model.py:20` `{2,3,4,5,6}`)
- **Seamed slice field** `core/composition.py:18` `SEAM_MODES` + `validate_slice():136` + `slice_rect():297` sha256 + `seam_config():316` + `core/render_triptych.py:1028` seam blur + `core/browser_runtime.js:53` `applySlice`
- **Everything configurable** via `core/render_triptych.py:43` Settings + `examples/*.json`
- **1080p full renders** proven locally: `artifact-001/evidence/renders.json:1` `11× 1080x1920/1920x1080 144f 6.9-9.8M` + `artifact-001/renders/` `11× draft 360x640` + `runtime-proof/renders/slice-*-full.mp4` `4× 1080p yuv420p 1.3M` (CI generates `--draft` for speed, full is local evidence, both gitignored per `.gitignore:27,20`)

## Evidence (verified against disk)

- `python3 core/make_artifact_001.py` idempotent: regenerates `11×1080p 144f` + `11× draft`; `ffprobe pix_fmt=yuv420p` `1080 1920` / `320 320` samples.
- `runtime-proof/renders/slice-portrait-full.mp4` `1.3M 1080 1920 yuv420p 144f 24/1` + `slice-portrait-test.mp4` `223K 360p`.
- `editions.json:21` `simultaneous_field` slice edition + `docs/SEAMED_SLICE_FIELD.md` + `docs/CONFIG.md`.
- `tools/verify_editions.py → 7/16/43`, `tools/edition_status.py → 7 local-only`, `tools/verify_local_lifecycle.py → ok 0 leaks`, `git check-ignore -v runtime-proof/` confirmed.

## How to verify

```bash
python3 core/make_runtime_fixture.py
python3 core/make_artifact_001.py --draft
python3 core/make_artifact_001.py  # full 1080p, see artifact-001/evidence/renders.json 11
ffprobe -show_entries stream=codec_name,pix_fmt,width,height -of default=noprint_wrappers=1 artifact-001/renders/state-2-portrait.mp4  # yuv420p 1080 1920
python3 tools/verify_editions.py  # 7/16/43
git check-ignore -v runtime-proof/ artifact-001/renders/state-2-portrait.mp4  # .gitignore:27,20
```

## Governance

- Lane `lane/expand` — complete already-stated scope, verified by `verify_editions` not merely sketched.
- Single intention, `work/<lane>/<short-intent>` per `BRANCHES.md:20`. Delete working branch after merge, keep lane.
- Closes gap 2: previously `0 0` with no PR after fast-forward. Parked intentions `#3` N=7, `#4` First Circle remain tracked.
