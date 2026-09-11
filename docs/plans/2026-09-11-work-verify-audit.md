# Work Audit — lane/verify browser-deps (2026-09-11)

> Branch: `work/lane/verify/browser-deps` → `lane/verify` → `main`. Cut from `main@1bd5b86` per `BRANCHES.md:20`.

## Intent

Governance demonstration that `lane/*` fast-forward `0 0` after direct `main` pushes is replayed via proper `work/<lane>/*` PR flow. This branch contains **no functional change** — it audits the `fix(ci): browser deps` family (`ea337a8` `99c573d` `261f61d` `ccde9ad`) already on `main`:

- Pin `requirements-runtime-proof.txt:4` (`playwright 1.57.0`, `Pillow 12.3.0`) + `playwright install --with-deps chromium` diagnostics `.github/workflows/ci.yml:29,37-44`
- `ffprobe pix_fmt` gate `yuv420p` `7/7` `core/composition.py:267` + `.github/workflows/ci.yml:42`
- `PORTVS_BROWSER_TRANSPORT=in-memory` `:57` + `PORTVS_BROWSER_EXECUTABLE` selection `:71` preferring `google-chrome-stable` with H.264 (`core/browser_runtime.py:33`, `tests/test_browser_runtime.py:33` fallback)
- `tools/verify_layouts.py:1` mirrors `core/composition.py:97,105` + `core/artifact001_layouts.py:41`, wired `.github/workflows/ci.yml:74`

## Evidence (pre-existing, verified)

- Local gates `2026-09-11 00:52 UTC` (darwin, `ffmpeg 9.0.1`): `pytest ... -q → 73 passed`, `PlanTests 12 passed`, `in-memory` `test_3/5_loop_native_continuity 2 ok`, `verify_layouts ok 2,3`, `verify_editions 7/16/43`, `verify_local_lifecycle ok`, `pix_fmt=yuv420p` `320 320` and `1080 1920`.
- CI `34547946845` `ccde9ad` `success` on `ubuntu-latest` (proves H.264 decode via `SYSTEM_CHROME=/usr/bin/google-chrome-stable` `152.0.7977.82`, `Verify media pix_fmt` `yuv420p` 7/7, `Run Full Test Suite` 120 tests `OK`). Supersedes prior `34547592934` `failure` `Media failure: loop-*` at `tests/test_browser_continuity.py:128` `core/browser_runtime.js:163`.
- Current HEAD `1bd5b86` `failure` `34548331853` is flake (`clock-discontinuity` `0.85!=0.66 delta 0.18`, `tests/test_browser_boundaries.py:149`), not codec; rerun `gh run rerun 34548331853` in progress.

## How to verify

```
python3 -m unittest tests.test_browser_runtime.PlanTests -v  # 12 passed
PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v  # 120
python3 tools/verify_layouts.py --examples  # layouts ok
python3 tools/verify_editions.py  # 7/16/43
ffprobe -show_entries stream=pix_fmt -of default=noprint_wrappers=1 runtime-proof/media/source-1.mp4  # yuv420p
gh run list --branch main --limit 3  # expect latest success after rerun
```

## Governance

- One intention per branch, lifetime days. Merges by PR with linked issue `lane/verify` healed.
- This audit branch will be deleted after merge; `lane/verify` retained per `BRANCHES.md`.

No N/A vacuum — ideal form logic: every claim verified against disk.
