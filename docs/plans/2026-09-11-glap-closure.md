# GLAP Closure — Full Implementation Plan (2026-09-11)

> Scope: close the 5 gaps from `docs/plans/2026-09-11-closeout.md:58-63` to `BRANCHES.md:12` green. No new invariants beyond slice/seam/layouts/CI. Lane governance `BRANCHES.md:12-16`.

## 0. Preflight

- Baseline `main@25aa34b` is 1:1 with `origin/main` after `git push origin main lane/*` (closeout #2). `git status --porcelain=v1 -uall` empty, `git worktree list` single primary. Branch protection `Branch not protected`.
- 5 gaps: 1 CI 29× `Media failure: loop-*` at `tests/test_browser_runtime.py:185` (`core/browser_runtime.js:163` decode), 2 lane PRs not opened, 3 1080p not proven, 4 upstream `organvm/portvs#8/#9` parked (`gh issue list` #1 OPEN), 5 `tools/verify_layouts.py` missing.
- Ordering: Wave 0 probe → Wave 1 CI deps (blocks green) ∥ Wave 2 validator → Wave 3 1080p (needs green) → Wave 4 PRs → Wave 5 upstream (gated).

## 1. Wave 0 — Probe & Pin (½ day)

- Verify `requirements-runtime-proof.txt:4` (`Pillow==12.3.0`, `playwright==1.57.0`) vs `ci.yml:29` unpinned drift.
- Local mirror: `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` vs `http`.
- Capture `ffmpeg -version`, `ffprobe -version`, `chromium --version` / `google-chrome --version`.

## 2. Wave 2 — `feat(verify): layouts.json guard` (parallel, no CI block)

**New `tools/verify_layouts.py` (~120 LOC):**
- Mirrors `core/composition.py:97-124` `rect_values`/`validate_layouts` + `core/artifact001_layouts.py:41-62` `_load_authored`.
- Inputs: `core/layouts.json` if exists else `examples/layouts.json` with `--examples`; `--strict` for CI when override present.
- Per-count `N` `1..32`, each orientation `portrait/landscape` length == N, rect `0<=x,y<=1`, `0<w,h<=1`, `x+w<=1`, `y+h<=1`, `fit contain|cover`, `focal 0..1`, non-overlap `not (x < a+c && a < x+w && y < b+d && b < y+h)`, set identity `len(seen)==len(loop_ids) && set(seen)==loop_ids`.
- CLI: `--examples`, `--layouts`, `--json`; exit `layouts ok` else `StateError`.

**Wire:** `.github/workflows/ci.yml:45` add `Verify Layouts` step after edition presets: `python3 tools/verify_layouts.py --examples` (strict if `core/layouts.json`). Link `docs/CONFIG.md:29` + `STATUS.md` gate row.

## 3. Wave 1 — `fix(ci): browser deps — yuv420p + chromium codec` (blocks green)

**Files:** `.github/workflows/ci.yml:21-30,32,37` + `core/composition.py:267` + `tests/test_browser_runtime.py:33,168`

- `ci.yml:21-24` add diagnostics `ffprobe -version; google-chrome --version || chromium --version`.
- `ci.yml:26-30` → `pip install -r requirements-runtime-proof.txt` (pins `playwright==1.57.0`) then `playwright install --with-deps chromium` with `set -e`.
- `ci.yml:32-35` keep fixture gate, add **ffprobe pix_fmt gate** before tests:
  ```bash
  for f in runtime-proof/media/*.mp4; do
    echo "== $f =="; ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,profile,width,height -of default=noprint_wrappers=1 "$f";
    ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt -of json "$f" | grep -q '"pix_fmt": "yuv420p"' || exit 1;
  done
  ```
- `ci.yml:37-39` wrap tests with `PORTVS_BROWSER_TRANSPORT=in-memory` + deterministic executable:
  ```bash
  export PLAYWRIGHT_CHROMIUM_PATH=$(python3 -c "from playwright.sync_api import sync_playwright; print(sync_playwright().start().chromium.executable_path)" 2>/dev/null || which google-chrome || which chromium)
  python3 -m unittest discover -s tests -v
  ```
  Dump `runtime-proof/evidence/browser-*.txt` on failure.
- `core/composition.py:267-278` add `pix_fmt` to `ffprobe -show_entries` and reject `h264 && pix_fmt!=yuv420p` mirroring `core/browser_runtime.py:122-127`.
- `tests/test_browser_runtime.py:33-57,168` fallback to `playwright.chromium.executable_path` when `which` fails.

Risk: Playwright bundle missing H.264 → fallback to `google-chrome-stable` (`libffmpeg.so`), or `mcr.microsoft.com/playwright:v1.57.0-jammy`.

Verify: `gh run view --log-failed` 0 `Media failure`, `gh run list --branch main` `success`.

## 4. Wave 3 — `feat(expand): full 1080p N-loop renders`

- Run locally (60 min, cap parallel per M5 16GB): `python3 core/make_artifact_001.py` (no `--draft`) → 12 renders `1080x1920/1920x1080` N=2..6 portrait+landscape, `artifact-001/evidence/renders.json` (currently 6× `state-3..6` only, missing `state-2` full).
- Also `python3 core/render_triptych.py --state runtime-proof/state-slice.json --orientation portrait --output runtime-proof/renders/slice-portrait-full.mp4 --width 1080 --height 1920` + landscape + `state-slice-3.json` both (seam `crop+boxblur+overlay` at 1080p).
- Gate `python3 tools/verify_runtime_renders.py --family artifact001` (`nb_frames 144` `r_frame_rate 24/1`) + `python3 tools/edition_status.py` `simvltanea-slice: ready`.
- CI keeps `--draft` for speed; full 1080p is PR evidence, not per-push.

## 5. Wave 4 — Lane PRs (after 1+2+3)

- `work/lane/verify/browser-deps → lane/verify → main` for CI heal.
- `work/lane/expand/full-renders → lane/expand → main` for N=2+slice+s seam 1080p.
- Each PR: linked issue + `how to verify` + evidence; `gh pr create --base main --head lane/*`.
- Merge via rebase (`BRANCHES.md:6` linear), delete working branches.

## 6. Wave 5 — Upstream `organvm/portvs#8/#9` (gated on `Post upstream closeout? y/N`)

- If `y`: `gh issue comment 8 --repo organvm/portvs --body-file docs/UPSTREAM_COORDINATION.md`, `gh pr comment 9 --repo organvm/portvs --body "Extraction to canonical: 4444J99/simvltanea @ $(git rev-parse main)"`, `gh issue close 1`.
- Else keep #1 parked (`docs/UPSTREAM_COORDINATION.md:30-53` provenance).

## 7. File Change Matrix

| Wave | File | Action |
| --- | --- | --- |
|1|`.github/workflows/ci.yml:21-40`|pin + diagnostics + pix_fmt gate + in-memory env|
|1|`core/composition.py:267`|add pix_fmt check|
|1|`tests/test_browser_runtime.py:33`|fallback executable|
|2|`tools/verify_layouts.py`|new ~120 LOC|
|2|`.github/workflows/ci.yml:45`|+ verify_layouts step|
|3|`artifact-001/evidence/renders.json`|regenerated 1080p (gitignored renders)|
|4|lane PRs|`gh pr create`|
|5|`docs/UPSTREAM_COORDINATION.md`|posted cross-org if authorized|

## 8. Verification (closeout definition)

- `git status --porcelain=v1 -uall` empty, `git rev-list --left-right --count origin/main...main → 0 0`
- `gh run list --branch main` latest `success`, 0 `Media failure`
- `python3 -m unittest discover -s tests -v` 0 failures both transports
- `python3 tools/verify_layouts.py` `layouts ok`
- `artifact-001/evidence/renders.json` 12×1080p `144 frames`
- `gh pr list` 2 merged, `gh issue list` 3 or 2 if #1 closed
- `STATUS.md:15` CI `success`

## 9. Risks

- Chromium H.264 codec absent → `google-chrome-stable` fallback or playwright container.
- ffmpeg 4.x pix_fmt ordering → lock `format=yuv420p` filter; gate catches.
- 1080p CI timeout → local-only full, CI stays draft.
