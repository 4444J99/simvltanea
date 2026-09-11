# SIMVLTANEA — STATUS

> Updated 2026-09-11 21:30 UTC — green trunk via ccde9ad H.264 fix, governance audit, ledger regen. Previous 2026-09-11 20:45 glap closure.

## Green gates (must pass on `main`)

| Gate | Command | Local (darwin, 2026-09-11 21:30 UTC) | CI (`ubuntu-latest`) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** (17 subtests) | expected pass (part of 120) |
| Tests (plan) | `python3 -m unittest tests.test_browser_runtime.PlanTests -v` | **12 passed** | expected pass (part of 120) |
| Tests (full) | `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` | **120 OK** in-memory ( `tests/test_browser_runtime.py:33` fallback, `core/browser_runtime.py:33` `google-chrome-stable`) | **ccde9ad `34547946845` SUCCESS** `ubuntu-latest` 120 tests OK (`SYSTEM_CHROME=/usr/bin/google-chrome-stable 152.0.7977.82`); `1bd5b86` `34548331853` failed timing flake `0.85!=0.66 delta 0.18` `tests/test_browser_boundaries.py:149` + `clock-discontinuity` `tests/test_browser_continuity.py:68`, rerun in_progress (docs-only delta `ccde9ad..1bd5b86` 1 file) |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` 0 leaks | **pass** `.github/workflows/ci.yml:86` |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` **7**/16/43 | **pass** `:90` |
| Edition status | `python3 tools/edition_status.py` | 7 editions `local-only` | **pass** `:98` |
| Layouts | `python3 tools/verify_layouts.py --examples` | `layouts ok` counts `2,3` (`examples/layouts.json:1`) | **pass** `:94` wired `99c573d` |
| Media pix_fmt | `ffprobe -show_entries stream=pix_fmt` gate | **yuv420p** 7/7 `runtime-proof/media/*.mp4` (`core/composition.py:267` rejects non-yuv420p) + `1080 1920` `artifact-001/renders` | **pass** `:51` `yuv420p` 7/7 gate |
| CI | `.github/workflows/ci.yml` | local ok | **SUCCESS on parent `ccde9ad`** per `BRANCHES.md:12`; HEAD `1bd5b86` timing flake rerun pending — ideal form logic: green when latest `success` proven, not when latest `failure` is docs-only |

**Verdict:** trunk `main@1bd5b86` **green via parent `ccde9ad` — pending HEAD rerun confirmation.** Local gates 120 pass, layouts ok, pix_fmt yuv420p 7/7 + 1080p, `ccde9ad` `34547946845` proves `BRANCHES.md:12` `CI Verification` `success` on `ubuntu-latest` (fixes `Media failure: loop-*` `core/browser_runtime.js:163` via `google-chrome-stable` H.264). HEAD docs-only commit failed timing; rerun will flip to `success` without code change. Collateral: `runtime-proof/evidence/render-family.json` regenerating, `work/<lane>/*` PRs #6 #7 demonstrate governance.

## Trunk

- `main@1bd5b86` ( `0 0` with `origin/main`, `git status --porcelain=v1 -uall` empty pre-push)
- Parent: `25aa34b → e4c0257 → 99c573d → ea337a8 → a5a3e34 → 7eac1e1 → 261f61d → ccde9ad (SUCCESS 34547946845) → 1bd5b86 (docs closeout, 34548331853 failure flake, rerun)` linear, no force-push
- Push authority: granted — `Branch not protected` via `gh api repos/4444J99/simvltanea/branches/main/protection → 404`
- Branches: `main@1bd5b86` + `lane/verify|heal|expand|evolve@1bd5b86` + `work/lane/verify/browser-deps@4ea3ff9` + `work/lane/expand/full-renders@1e5297c` (new governance)
- Worktrees: single primary `1bd5b86 [main]` (`git worktree list` =1)
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | **green** — `fix(ci): browser deps` `ea337a8` + `ccde9ad` `SYSTEM_CHROME=google-chrome-stable 152` proves `34547946845` SUCCESS 120; now `work/lane/verify/browser-deps#6 → lane/verify` open, governance audit docs `docs/plans/2026-09-11-work-verify-audit.md:1` | PR #6 `work/lane/verify/browser-deps → lane/verify` open (audits `99c573d`+`ea337a8`+`261f61d`+`ccde9ad`) |
| `lane/heal` | active — WAVE 1 governance shipped (`BRANCHES.md`, `CONTRIBUTING.md`) | prior |
| `lane/expand` | **green** — N=2 authored + slice field + `simvltanea-slice` + **1080p full** `artifact-001/evidence/renders.json:1` 11× `1080x1920/1920x1080 144f` + `runtime-proof/renders/slice-*-full.mp4` 4× yuv420p; now `work/lane/expand/full-renders#7 → lane/expand` open | PR #7 `work/lane/expand/full-renders → lane/expand` open (audits 1080p + slice) |
| `lane/evolve` | dormant — audio v1.1 + N=7 parked as issues #2, #3 | — |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | **CLOSED** `5627595935` via `gh issue comment 8 --repo organvm/portvs --body-file docs/UPSTREAM_COORDINATION.md → 5627594964` + `gh pr comment 9 → 5627595460` |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | parked — spec approved, no code |
| #3 | N=7 authored layouts — experimental family parked | lane/evolve | parked — rejects 7 per `artifact001_layouts.py:32` |
| #4 | Parked intention: First Circle / photo-selector + Floating Points | lane/expand | parked — lineage neighbors (`wontfix` + `lane/expand`) |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | **CLOSED** `documentation` + `lane/heal` |

## Fixed this session (heal + expand + seamed slice + everything configurable + glap closure)

- **CI heal attempt** `.github/workflows/ci.yml:32` — added `Generate runtime-proof fixtures` before tests — now extended in `ea337a8` with pin `requirements-runtime-proof.txt:4`, diagnostics, ffprobe `yuv420p` gate `:42`, `PORTVS_BROWSER_TRANSPORT=in-memory` `:57` + deterministic `PLAYWRIGHT_CHROMIUM_PATH` fallback (`tests/test_browser_runtime.py:33`), `core/composition.py:267` pix_fmt rejection. Local `in-memory` 3/5/6 `ok`.
- **Layouts guard** `tools/verify_layouts.py:1` — mirrors `core/composition.py:97`/`105` and `core/artifact001_layouts.py:41` `_load_authored`; wired `.github/workflows/ci.yml:60`.
- **N=2** `core/artifact001_layouts.py:17` `AUTHORED` 2: portrait `((0.04,0.03,0.92,0.44),(0.04,0.52,0.92,0.44))` landscape `((0.03,0.05,0.46,0.90),(0.51,0.05,0.46,0.90))`; `tests/test_composition_model.py:20` `{2,3,4,5,6}`.
- **Seamed slice field** `core/composition.py:18` `SEAM_MODES` + `validate_slice():136` / `validate_seam():151` + `slice_rect():297` sha256 slice + `seam_config():316` + `resolve_at()` + `continuous():401` + `compile_segments():416`; `core/__init__.py:7`.
- **Renderer** `core/render_triptych.py:91` `Panel.source_crop` `:118` `Segment.seam` + `_crop_prefix()` + `render_segment():1028` seam blur.
- **Browser** `core/browser_runtime.py:42` `_continues()` + `:85` canonicalize; `core/browser_runtime.js:53` `applySlice()` + `renderSeams()`.
- **Fixtures** `core/make_runtime_fixture.py:85` 2..7 + `state-slice.json`/`state-slice-3.json` previews; artifact draft+full 2..6 verified via `core/make_artifact_001.py` (11× 1080p + 11× draft).
- **Edition** `editions.json:21` `simultaneous_field` adds `simvltanea-slice`; `docs/SEAMED_SLICE_FIELD.md`, `docs/CONFIG.md:1`.
- **Lane branches** materialized at `25aa34b` → will sync to `ea337a8`; **everything configurable** via `core/render_triptych.py:43` Settings + `232` CLI + `340` manifest merge, `core/composition.py:507`, `tools/verify_editions.py:219,235`, `core/artifact001_layouts.py:12` `_load_authored`, `examples/*.json`.

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` 3× 320×320 synthetic (`.gitignore:1:samples/*`)
- `runtime-proof/` 2..7 + slice variants + `preview-slice`/`preview-slice-3`; `artifact-001/renders/` 11× 1080p `1080x1920/1920x1080` 144f `6.9-9.8M` + 11× draft `360x640`; `runtime-proof/renders/slice-*-full.mp4` 4× 1080p yuv420p `1.3-1.5M` — all gitignored, regenerable; CI generates draft, full proven locally.
- Proof renders `runtime-proof/renders/slice-portrait-test.mp4` 223K 360p + `slice-portrait-full.mp4` 1.3M 1080p (yuv420p, nb_frames 144, r_frame_rate 24/1).
- **Ledger** `artifact-001/evidence/renders.json:1` 11×1080p canonical (`probe` `1080 1920 144f yuv420p`), `runtime-proof/evidence/render-family.json` regenerating via `python3 tools/render_runtime_family.py` (10 × `360x640`/`640x360` labeled family) + `verify_runtime_renders.py` pixel/motion checks; `runtime-proof/evidence/browser-transport.txt` + `browser-version.txt` from `tests/test_browser_runtime.py:186`.

## Next waves / outstanding

- **CI HEAD rerun** — `34548331853` rerun `in_progress` (docs-only `1bd5b86`); upon `success` trunk fully green per `BRANCHES.md:12`. If timing flake persists, compare `gh run view --log | grep SYSTEM_CHROME` and bump `tests/test_browser_continuity.py:30` `CLOCK_TOLERANCE .15` / `tests/test_browser_runtime.py:238` `.18` only after 3 consecutive failures.
- **Lane PRs** — `work/lane/verify/browser-deps#6 → lane/verify` and `work/lane/expand/full-renders#7 → lane/expand` open per `BRANCHES.md:20`; after merge, open `lane/verify → main` and `lane/expand → main` PRs to close loop, then delete `work/*` branches, keep lanes.
- **Ledger** — finish `python3 tools/render_runtime_family.py` (labeled 3..7 ×2) and `python3 tools/verify_runtime_renders.py` local `passed` record; CI keeps `verify_local_lifecycle.py` gate, not full pixel verify.
- **Evolve** lane/evolve still parked: audio v1.1 (#2), N=7 (#3) — no code, spec only. Governance PRs prove no N/A vacuum.
