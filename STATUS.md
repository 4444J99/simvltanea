# SIMVLTANEA — STATUS

> Generated 2026-09-10 — steward wave 0–3 complete. This file tracks the living state of the trunk and lanes, not a marketing roadmap.

## Green gates (must pass on `main`)

| Gate | Command | Result (2026-09-10) |
| --- | --- | --- |
| Tests | `python3 -m pytest -q` / `python3 -m unittest discover -s tests` | **120 passed, 26 subtests passed** |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` (8 untracked governance files pending, 0 leaks) |
| Editions | `python3 tools/verify_editions.py` | `edition presets ok` — 6 editions, 16 presets, 43 cells |
| Edition status | `python3 tools/edition_status.py` | 6 editions, all `local-only` (0 public receipts — expected on clean clone) |
| CI | `.github/workflows/ci.yml` (`ubuntu-latest`, Python 3.12, ffmpeg, pillow, playwright chromium) | `test` job runs 120 tests + lifecycle + edition gates |

## Trunk

- `main@6e122da` → steward commit `6e122da..HEAD` heals edition tooling + governance
- Branches: `main` only (plus standing lanes defined in `BRANCHES.md`, created on demand)
- Worktrees: single primary (`git worktree list` = 1)
- Tags: none yet

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
- Governance: `BRANCHES.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `SECURITY.md`, PR/issue templates, lane labels

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` — 3× 2s synthetic 320×320 clips (gitignored via `samples/*`) — demo for `simvltanea-inaugural` folder source without leaking heavy media. Regenerable.
- `runtime-proof/` experimental 7-study stays unchanged (on-demand via `core/make_runtime_fixture.py`)

## Next waves

- **Wave 3 (done in this session partially)**: edition fixture ready, CI now checks browser + edition gates
- **Wave 4 (evolve, deferred)**: Audio v1.1 implementation requires `work/evolve/audio-v1.1` spike only after lane creation + schema v1.1 issue; N=7 only with artist-approved geometry
- **Risk if abandoned**: none imminent — trunk is green and mergeable; parked issues keep intentions without inventing scope
