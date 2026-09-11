# SIMVLTANEA — STATUS

> Updated 2026-09-11 00:17 UTC — closeout audit (feat slice + config). Previous 2026-09-10 20:00 seamed slice field.

## Green gates (must pass on `main`)

| Gate | Command | Local (darwin, 2026-09-11) | CI (`ubuntu-latest`, `8b8dabb` `34545830164` in_progress) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** (17 subtests) | expected pass |
| Tests (plan) | `python3 -m unittest tests.test_browser_runtime.PlanTests -v` | **12 passed** | expected pass |
| Tests (full) | `pytest -q` / `unittest discover -s tests` | 73 + 12 plan ok; browser continuity needs Chromium (local Chrome present) | **FAILED** — `8b8dabb` `34545830164` in_progress, prior `7577a9c` `34544477784` `failure` 29× `Media failure: loop-*` at `tests/test_browser_runtime.py:185` despite `Generate runtime-proof fixtures` (`RENDERED state-2..6-draft` in log) |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` (0 untracked, 0 leaks) | passes when reached |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` **7**/16/43 | passes when reached |
| Edition status | `python3 tools/edition_status.py` | 7 editions `local-only` | passes when reached |
| CI | `.github/workflows/ci.yml` | local ok | **failure** — fixture gate added `.github/workflows/ci.yml:32` but `Media failure` persists — browser deps/codec, see closeout blocker #1 |

**Verdict:** trunk `main@8b8dabb` **is NOT green** per `BRANCHES.md:12` (`main` always releasable, required CI passes). Local lifecycle/edition gates pass, but browser runtime breaks CI consistently (also on 4 prior `main` runs). This closeout seals lane bookkeeping, not a green trunk.

## Trunk

- `main@8b8dabb` (local:remote 1:1 before this closeout, `0 0` 2026-09-11 00:17 UTC)
- Parent: `7577a9c` → `351a41b` → `fe54f80`
- Push authority: granted earlier — parity `0 0` verified, next closeout commit will be 1 ahead until pushed
- Branches: `main` + standing lanes `lane/verify` `lane/heal` `lane/expand` `lane/evolve` at `8b8dabb` (local + `origin`)
- Worktrees: single primary `8b8dabb [main]` (`git worktree list` =1)
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | healed — fixture gate added, local materialized | this wave |
| `lane/heal` | active — WAVE 1 governance shipped | prior |
| `lane/expand` | active — N=2 authored + slice field + `simvltanea-slice` edition | this wave |
| `lane/evolve` | dormant — audio v1.1 + N=7 parked as issues #2, #3 | — |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | parked — awaits operator `Post upstream closeout? y/N` |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | parked — spec approved, no code |
| #3 | N=7 authored layouts — experimental family parked | lane/evolve | parked — rejects 7 per `artifact001_layouts.py:32` |
| #4 | Parked intention: First Circle / photo-selector + Floating Points | lane/expand | parked — lineage neighbors |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | healing complete |

## Fixed this session (heal + expand + seamed slice + everything configurable)

- **CI attempt** `.github/workflows/ci.yml:32` — adds `Generate runtime-proof fixtures` (`make_runtime_fixture.py` + `make_artifact_001.py --draft`) before `Run Full Test Suite` — fixtures now generated (`RENDERED state-2..6-draft` in `gh run view 34544477784 --log`), but 29 `Media failure: loop-*` persists (browser decode, not missing files) — see blocker below.
- **N=2** `core/artifact001_layouts.py:17` `AUTHORED` adds 2: portrait `((0.04,0.03,0.92,0.44),(0.04,0.52,0.92,0.44))` landscape `((0.03,0.05,0.46,0.90),(0.51,0.05,0.46,0.90))`; `README.md:55` table 2..6; `core/make_artifact_001.py:54` 2..6; `tests/test_composition_model.py:20` set `{2,3,4,5,6}`.
- **Seamed slice field** `core/composition.py:18` `SEAM_MODES` + `validate_slice()` `:136` / `validate_seam()` `:151` + `slice_rect()` `:297` sha256 slice (`%1000` limit_denominator) + `seam_config()` `:316` + `resolve_at()` slice attach + `continuous()` `:401` split + `compile_segments()` `:416` `Panel.source_crop`/`Segment.seam`; `core/__init__.py:7` drop `LAYOUT_KEYS`.
- **Renderer** `core/render_triptych.py:91` `Panel.source_crop` `:118` `Segment.seam` + `_crop_prefix()` + crop in all `video_source_filters` branches + `render_segment()` `:1028` seam blur chain (boxblur strip at adjacency, feather/morph modes).
- **Browser** `core/browser_runtime.py:42` `_continues()` slice + `:85` canonicalize slice/seam → `plan.slice`/`plan.seam`; `core/browser_runtime.js:53` `applySlice()` overflow slice + `renderSeams()` backdrop-filter seam overlays.
- **Fixtures** `core/make_runtime_fixture.py:85` 2..7 + `state-slice.json` (N=2 feather) / `state-slice-3.json` (N=3 morph) previews; artifact draft 2..6 verified.
- **Edition** `editions.json:21` `simultaneous_field` adds `simvltanea-slice` + new video-ready edition with slice/seam settings and `docs/SEAMED_SLICE_FIELD.md`.
- **Lane branches** materialized locally + pushed to `origin` at `8b8dabb`.
- **Everything configurable** `feat(config)` — `core/render_triptych.py:43` Settings + `232` CLI `--slice-*`/`--seam-*`/`--config` + `340` manifest merge, `core/composition.py:507` state override, `tools/verify_editions.py:219,235` validators, `core/make_runtime_fixture.py:47` args, `core/artifact001_layouts.py:12` `_load_authored`/`core/layouts.json`, `examples/slice-seam-config.json:1`/`examples/layouts.json:1`, `docs/CONFIG.md:1` knob matrix.

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` 3× 320×320 synthetic (`.gitignore:1:samples/*`)
- `runtime-proof/` now 2..7 + slice variants + `preview-slice`/`preview-slice-3`; `artifact-001/media` 2..6 renders — all gitignored, regenerable via `make_*` scripts; CI now generates them.
- Proof render `runtime-proof/renders/slice-portrait-test.mp4` 360×640 yuv420p h264 single-segment with crop+seam (223K).

## Next waves / outstanding

- **Configurability** `feat(config)` — every slice/seam/N/layout knob now via state/edition/manifest/CLI (`--slice-*`/`--seam-*`/`--config`)/`core/layouts.json`/fixture args/browser plan (`docs/CONFIG.md:1`, `examples/slice-seam-config.json:1`, `examples/layouts.json:1`) — verified local; CI still red.
- **CI blocker** — 29 `Media failure: loop-*` persists despite fixture gate — next `fix(ci): browser deps` PR on `work/lane/verify/browser-deps`.
- **Upstream closeout** #1 parked — operator confirmation `Post upstream closeout? y/N` then `gh issue comment 8 --repo organvm/portvs --body-file docs/UPSTREAM_COORDINATION.md`.
- **Evolve** lane/evolve still parked: audio v1.1 (#2), N=7 (#3) — no code, spec only.
- **Layout validator** missing — `core/layouts.json` example has no `tools/verify_layouts.py` guard — follow-up `feat(verify): layouts.json`.
