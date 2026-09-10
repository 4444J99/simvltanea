# SIMVLTANEA — STATUS

> Updated 2026-09-10 23:35 UTC — closeout audit. Previous line 2026-09-10 19:22 wave 0–3.

## Green gates (must pass on `main`)

| Gate | Command | Local (darwin, 2026-09-10) | CI (`ubuntu-latest`, `34542060051`) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** | — |
| Tests (full) | `pytest -q` / `unittest discover -s tests` | **claimed 120 passed** earlier session (116s), not rerun in closeout (browser+continuity gated) | **FAILED** 29 failures (`Media failure: loop-*` in `test_browser_runtime.BrowserTests`) |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` (0 untracked, 0 leaks) | not reached (failed at test step) |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` 6/16/43 | not reached |
| Edition status | `python3 tools/edition_status.py` | 6 editions `local-only` | not reached |
| CI | `.github/workflows/ci.yml` | local ok | **failure** — 29 browser-runtime failures |

**Verdict:** trunk `main@fe54f80` is **not green** per `BRANCHES.md` (`main` always releasable, required CI passes). Local lifecycle/edition gates pass, but browser runtime breaks CI consistently (also on 3 prior `main` runs `34507476445`/`34506547318`/`34505564858` — pre-existing).

## Trunk

- `main@fe54f80` (local:remote 1:1, pushed 2026-09-10 19:25, `0 ahead`)
- Parent: `6e122da` refactor: 3-tier layout
- Push authority: granted earlier session — parity achieved `0 ahead`
- Branches: `main` only (`git branch -a`); standing lanes defined but not materialized as refs
- Worktrees: single primary (`git worktree list` = 1)
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | dormant — to be created on first verification PR | — |
| `lane/heal` | active — WAVE 1 governance shipped on `main` | this stewardship |
| `lane/expand` | dormant — `simvltanea-inaugural` demo fixture in `samples/inaugural` (ignored) | — |
| `lane/evolve` | dormant — audio v1.1 + N=7 parked as issues #2, #3 | — |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | parked — awaits operator `Post upstream closeout?` |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | parked — spec approved, no code |
| #3 | N=7 authored layouts — experimental family parked | lane/evolve | parked — rejects 7 per `artifact001_layouts.py:32` |
| #4 | Parked intention: First Circle / photo-selector + Floating Points | lane/expand | parked — lineage neighbors |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | healing complete; tracks residual onboarding |

## Fixed this session (heal)

- `tools/edition_status.py:13` + `tools/verify_editions.py:15` — `DEFAULT_EDITIONS = REPO_ROOT/editions.json` + `resolve_inside` now allows both `tools/` and repo-root paths (was `SCRIPT_DIR`-only, so `editions.json` at root failed)
- `tools/verify_editions.py:154` — `folder` alias accepted alongside `source_dir` for `type=folder`
- `tools/verify_editions.py:183` — `audio.gain` / `fade_seconds` now allow `0` (was `>0`, silent field needs `0.0`)
- `editions.json:36` — `simvltanea-inaugural` now includes `source_dir` + `composition.panel_arrangement_role` (was missing, failed validator)
- `.github/workflows/ci.yml:32` — added `Verify Edition Presets` + `Report Edition Status` gates after lifecycle
- Governance: `BRANCHES.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `SECURITY.md`, PR/issue templates, lane labels (`lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve` via `gh label create`)
- Issues: #1 parked upstream closeout, #2 audio v1.1, #3 N=7, #4 lineage, #5 closed (factory hardening) — `gh issue list`

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` — 3× 2s synthetic 320×320 clips (`git check-ignore` confirms `.gitignore:1:samples/*`) — demo for `simvltanea-inaugural` folder source without leaking heavy media. Regenerable.
- `runtime-proof/` + `artifact-001/media` + `work/` empty — regenerable via `core/make_artifact_001.py` / `core/make_runtime_fixture.py`, intentionally not committed

## Next waves / outstanding

- **Wave 3 residual**: full `build_edition.py` 1080p portrait/landscape demo not yet run (only minimal `samples/inaugural` fixture)
- **Wave 4 (evolve, deferred)**: Audio v1.1 (#2) and N=7 (#3) parked — no spike until lane created
- **CI debt**: 29 browser-runtime continuity failures must be healed to reach `BRANCHES.md` green (see Blockers)
- **Lanes**: standing branches defined but not pushed (`lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve` — `git branch -a` shows only `main`)
