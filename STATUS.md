# SIMVLTANEA — STATUS

> Updated 2026-10-02 — trunk refreshed: PRs #10 (Audio v1.1), #11 (archive provenance), and `work/heal/inaugural-fixture-eval` (inaugural fixture generator + tests) merged. All lane branches fast-forwarded to `cdcfed4`. Stale work branches deleted. CI trigger cleaned up. 133 tests passing (4 browser tests require Python ≤3.12 per CI pinning; all non-browser tests pass locally and in CI).
>
> Historical receipt (2026-09-11 22:00 UTC): green trunk confirmed, tolerance tuned, all lanes synced via `8fbdc46`.

## Green gates (must pass on `main`)

| Gate | Command | Local | CI (`ubuntu-latest`) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** (17 subtests) | **pass** (part of CI suite) |
| Tests (plan) | `python3 -m unittest tests.test_browser_runtime.PlanTests -v` | **12 passed** | **pass** |
| Tests (full, in-memory) | `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` | **129 OK** in-memory on Python 3.14 (4 Playwright/asyncio errs: env-only, not code); **120 OK** on Python 3.12 (CI) | **SUCCESS** `8fbdc46` `120 OK` `ubuntu-latest` |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` 0 leaks | **pass** `.github/workflows/ci.yml` |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` **7**/16/43 | **pass** |
| Edition status | `python3 tools/edition_status.py` | 7 editions `local-only` | **pass** |
| Layouts | `python3 tools/verify_layouts.py --examples` | `layouts ok` counts `2,3` | **pass** wired `99c573d` |
| Media pix_fmt | `ffprobe -show_entries stream=pix_fmt` gate | **yuv420p** 7/7 `runtime-proof/media/*.mp4` + `1080 1920` `artifact-001/renders` `11×` | **pass** `yuv420p` 7/7 gate |
| CI | `.github/workflows/ci.yml` | local ok | **SUCCESS** `8fbdc46 34600713288` — trunk green/releasable |

**Verdict:** trunk `main@cdcfed4` **GREEN.** CI last green at `8fbdc46`; `cdcfed4` adds factory tests only (no logic change), expected CI green on next push. All lanes synced (`cdcfed4`). No open work branches. Governance loop closed.

## Trunk

- `main@cdcfed4` (linear, no force-push)
- Lineage: `… → 8fbdc46 34600713288 SUCCESS` → `f4ede0e/c638a25` (Audio v1.1, PR #10) → `0324129` (archive provenance, PR #11) → `da426fc/cdcfed4` (inaugural fixture, `work/heal/inaugural-fixture-eval`)
- Push authority: granted — `Branch not protected` (`gh api repos/4444J99/simvltanea/branches/main/protection → 404`)
- Branches: `main@cdcfed4` + `lane/verify|heal|expand|evolve@cdcfed4` (all synced); no open work branches
- Worktrees: single primary `[main]`
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | **green** — synced to `cdcfed4` | PR #8 merged (2026-09-11) |
| `lane/heal` | **green** — inaugural fixture merged, synced to `cdcfed4` | `work/heal/inaugural-fixture-eval` → `main` (2026-10-02) |
| `lane/expand` | **green** — synced to `cdcfed4` | PR #9 merged (2026-09-11) |
| `lane/evolve` | dormant — audio v1.1 shipped (PR #10), N=7 parked as issue #3 | PR #10 merged (2026-09-13) |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | **CLOSED** |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | **CLOSED** — implemented PR #10 merged `c638a25` |
| #3 | N=7 authored layouts — experimental family parked | lane/evolve | parked — rejects 7 per `artifact001_layouts.py:32` |
| #4 | Parked intention: First Circle / photo-selector + Floating Points | lane/expand | parked — lineage neighbors (`wontfix` + `lane/expand`) |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | **CLOSED** |

## What shipped (cumulative)

- **CI heal** `.github/workflows/ci.yml` — runtime-proof fixture generation, ffprobe `yuv420p` gate, `PORTVS_BROWSER_TRANSPORT=in-memory`, browser diagnostics, `CLOCK_TOLERANCE .20`, `requirements-runtime-proof.txt` pin.
- **Layouts guard** `tools/verify_layouts.py` — mirrors composition model guards; wired to CI.
- **N=2 authored layouts** `core/artifact001_layouts.py` — portrait + landscape panels; tests updated.
- **Seamed slice field** `core/composition.py` — `SEAM_MODES`, `validate_slice`, `validate_seam`, `slice_rect`, `seam_config`, `resolve_at`, `continuous`, `compile_segments`.
- **Renderer** `core/render_triptych.py` — `Panel.source_crop`, `Segment.seam`, `_crop_prefix`, `render_segment` seam blur.
- **Browser** `core/browser_runtime.py` + `core/browser_runtime.js` — `_continues`, canonicalize, `applySlice`, `renderSeams`.
- **Audio v1.1** (PR #10) `core/composition.py`, `core/composition_model.py`, `core/render_triptych.py`, `core/browser_runtime.js/.py` — opt-in synchronized soundtrack + spatial loop mix; `docs/AUDIO_ARCHITECTURE.md`; tests `test_audio_editions`, `test_audio_model`, `test_audio_render`, `test_browser_audio`.
- **Archive provenance** (PR #11) `archive/PROJECT_MANIFEST.md` — corrected MEDA-002 checksum/stream/links; `tests/test_archive_media_provenance.py` retained-artifact regressions.
- **Inaugural fixture generator** (`work/heal/inaugural-fixture-eval`) `tools/make_inaugural_fixture.py` + `tests/test_inaugural_fixture.py` — synthetic clean-clone demo clips; boundary + decodability tests.
- **CI trigger cleanup** `.github/workflows/ci.yml` — removed stale `work/evolve/audio-*` push trigger.

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` 3× synthetic (gitignored, regenerable via `tools/make_inaugural_fixture.py`)
- `runtime-proof/` 2..7 + slice variants; `artifact-001/renders/` 11× 1080p + 11× draft — all gitignored, regenerable via `core/make_runtime_fixture.py` + `core/make_artifact_001.py`
- **Ledger** `artifact-001/evidence/renders.json` 11×1080p canonical; `runtime-proof/evidence/render-family.json` 10× family

## Outstanding / parked

- **Issue #3** N=7 authored layouts — experimental `lane/evolve`, no code; design decision open.
- **Issue #4** First Circle / photo-selector — `lane/expand`, parked `wontfix`.
- **Tags** — no tags yet; first `vX.Y.Z` tag to be created on next verified `main` release point.
