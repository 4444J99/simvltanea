# SIMVLTANEA — STATUS

> Updated 2026-09-11 20:45 UTC — glap closure (CI heal + layouts + 1080p). Previous 2026-09-11 00:17 feat slice+config.

## Green gates (must pass on `main`)

| Gate | Command | Local (darwin, 2026-09-11 20:45 UTC) | CI (`ubuntu-latest`, `ea337a8` pending) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** (17 subtests) | expected pass |
| Tests (plan) | `python3 -m unittest tests.test_browser_runtime.PlanTests -v` | **12 passed** | expected pass |
| Tests (full) | `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` | **3/4/5/6 continuity ok** (in-memory; `tests/test_browser_runtime.py:33` fallback to playwright bundle, `tests/test_browser_runtime.py:185` no `Media failure: loop-*`; http also ok via `Chrome.app`) | **pending** — fix at `.github/workflows/ci.yml:29,42,57` pins `requirements-runtime-proof.txt:4`, pix_fmt gate `yuv420p`, `in-memory` transport; prior `7577a9c` `34544477784` 29× failure now gated |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` (pending commits pre-push) | expected pass |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` **7**/16/43 | expected pass |
| Edition status | `python3 tools/edition_status.py` | 7 editions `local-only` | expected pass |
| Layouts | `python3 tools/verify_layouts.py --examples` | `layouts ok` counts `2,3` (`examples/layouts.json:1`) | wired `.github/workflows/ci.yml:60` |
| Media pix_fmt | `ffprobe -show_entries stream=pix_fmt` gate | **yuv420p** 7/7 `runtime-proof/media/*.mp4` (`core/composition.py:267` now rejects non-yuv420p) | `.github/workflows/ci.yml:42` gate |
| CI | `.github/workflows/ci.yml` | local ok | **pending verification** — `ea337a8` push will run `in_progress`; prior failures on `8b8dabb`/`7577a9c` deltas documented |

**Verdict:** trunk `main@ea337a8` **healing — pending CI.** Local gates 73+12 pass, layouts ok, pix_fmt yuv420p 7/7, `PORTVS_BROWSER_TRANSPORT=in-memory` 3/5/6 continuity verified, 1080p N=2..6 11 renders + 4 slice-full proven (see Fixtures). Requires `gh run list --branch main` `success` on `ea337a8` to flip to green per `BRANCHES.md:12`.

## Trunk

- `main@ea337a8` (local 3 ahead of `origin/main@25aa34b` before push; `e4c0257` plan + `99c573d` verify_layouts + `ea337a8` fix(ci))
- Parent: `e4c0257` → `99c573d` → `ea337a8` onto `25aa34b` → `8b8dabb` → `7577a9c`
- Push authority: granted — `Branch not protected` via `gh api repos/4444J99/simvltanea/branches/main/protection`
- Branches: `main@ea337a8` + standing lanes `lane/*` at `25aa34b` pre-sync (will fast-forward to `ea337a8` on push)
- Worktrees: single primary `ea337a8 [main]` (`git worktree list` =1)
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | **healed** — `fix(ci): browser deps` `ea337a8` `.github/workflows/ci.yml:29,42,57` + `core/composition.py:267` pix_fmt + `tests/test_browser_runtime.py:33` playwright fallback; `in-memory` + ffprobe yuv420p gate | next: PR `lane/verify → main` for CI heal |
| `lane/heal` | active — WAVE 1 governance shipped (`BRANCHES.md`, `CONTRIBUTING.md`) | prior |
| `lane/expand` | **healed** — N=2 authored + slice field + `simvltanea-slice` edition + **1080p full** `artifact-001/evidence/renders.json:1` 11× `1080x1920/1920x1080` 144f + `runtime-proof/renders/slice-*-full.mp4` 4× yuv420p | next: PR `lane/expand → main` for 1080p proof |
| `lane/evolve` | dormant — audio v1.1 + N=7 parked as issues #2, #3 | — |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | parked — awaits operator `Post upstream closeout? y/N` |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | parked — spec approved, no code |
| #3 | N=7 authored layouts — experimental family parked | lane/evolve | parked — rejects 7 per `artifact001_layouts.py:32` |
| #4 | Parked intention: First Circle / photo-selector + Floating Points | lane/expand | parked — lineage neighbors |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | healing complete |

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

## Next waves / outstanding

- **CI** — pending `ea337a8` run on `ubuntu-latest` with `in-memory` + pinned deps + pix_fmt gate; if green, flip `STATUS.md` CI to `success` per `BRANCHES.md:12`.
- **Lane PRs** — open `lane/verify → main` and `lane/expand → main` PRs after push to document heal/expand purpose per `BRANCHES.md:6` (labels `lane/verify`, `lane/expand`).
- **Upstream closeout** #1 parked — operator confirmation `Post upstream closeout? y/N` then `gh issue comment 8 --repo organvm/portvs --body-file docs/UPSTREAM_COORDINATION.md`.
- **Evolve** lane/evolve still parked: audio v1.1 (#2), N=7 (#3) — no code, spec only.
