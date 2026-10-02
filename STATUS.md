# SIMVLTANEA — STATUS

> Updated 2026-10-02 — N=7 authored layouts shipped via PRs #14–15; final closeout PR #16 merged; trunk and all standing lanes are synchronized. CI Verification run `36953519356` passed all 174 tests on the closeout head. Issue #4 closed under its existing `wontfix` boundary. Assigned-copy housekeeping issue #12 remains partial: live Git refs are remotely reconstructable, but unique local Git objects and ignored payload do not yet have independently restored encrypted custody, so the copy is retained.
>
> Historical receipt (2026-09-11 22:00 UTC): green trunk confirmed, tolerance tuned, all lanes synced via `8fbdc46`.

## Green gates (must pass on `main`)

| Gate | Command | Local | CI (`ubuntu-latest`) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/test_authoring_contract.py tests/test_composition_model.py tests/test_composition_render.py tests/test_review_proof.py -q` | **73 passed** (17 subtests) | **pass** (part of CI suite) |
| Tests (plan) | `python3 -m unittest tests.test_browser_runtime.PlanTests -v` | **12 passed** | **pass** |
| Tests (full, in-memory) | `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` | **133 passed** + 67 subtests on Python 3.14 outside native-browser setup; native browser requires the CI environment | **174 OK** on Python 3.12 CI |
| Lifecycle | `python3 tools/verify_local_lifecycle.py` | `local lifecycle ok` 0 leaks | **pass** `.github/workflows/ci.yml` |
| Edition presets | `python3 tools/verify_editions.py` | `edition presets ok` **7**/16/43 | **pass** |
| Edition status | `python3 tools/edition_status.py` | 7 editions `local-only` | **pass** |
| Layouts | `python3 tools/verify_layouts.py --examples` | `layouts ok` counts `2,3` | **pass** wired `99c573d` |
| Media pix_fmt | `ffprobe -show_entries stream=pix_fmt` gate | **yuv420p** 7/7 `runtime-proof/media/*.mp4` + `artifact-001/renders` `13×` | **pass** `yuv420p` 7/7 gate |
| CI | `.github/workflows/ci.yml` | local non-browser and evidence gates pass | **SUCCESS** `cc48a5d 36953519356` — PR #16 closeout tree green/releasable |

**Verdict:** trunk through PR #16 is **GREEN.** N=2 through N=7 are supported, all standing lanes are synced, and no remote work branches remain. Product/governance work is closed. Assigned-copy retirement remains blocked only by issue #12's external private-custody gate, not by application health.

## Trunk

- `main` includes final closeout PR #16 (linear, no force-push)
- Lineage: `… → 8fbdc46 34600713288 SUCCESS` → `f4ede0e/c638a25` (Audio v1.1, PR #10) → `0324129` (archive provenance, PR #11) → `da426fc/cdcfed4` (inaugural fixture, `work/heal/inaugural-fixture-eval`)
- Push authority: granted — `Branch not protected` (`gh api repos/4444J99/simvltanea/branches/main/protection → 404`)
- Branches: `main` + `lane/verify|heal|expand|evolve` (all synchronized); no open work branches
- Worktrees: single primary `[main]`
- Tags: none

## Lanes (standing — per `BRANCHES.md`)

| Lane | State | Last PR |
| --- | --- | --- |
| `lane/verify` | **green** — synced to current `main` | PR #8 merged (2026-09-11) |
| `lane/heal` | **green** — synced to current `main` | PR #13 merged (2026-10-02) |
| `lane/expand` | **green** — synced to current `main`; lineage-neighbor scope closed `wontfix` | PR #9 merged (2026-09-11) |
| `lane/evolve` | **green** — synced to current `main`; Audio v1.1 and authored N=7 shipped | PR #15 merged (2026-10-02) |

## Issues (living intentions)

| # | Title | Lane | Status |
| --- | --- | --- | --- |
| #1 | Parked intention: upstream Portvs Issue #8 / PR #9 closeout | lane/heal | **CLOSED** |
| #2 | Audio v1.1 — Synchronized Soundtrack + Spatial Loop Mix | lane/evolve | **CLOSED** — implemented PR #10 merged `c638a25` |
| #3 | N=7 authored layouts | lane/evolve | **CLOSED** — spec PR #14 + implementation PR #15 merged |
| #4 | First Circle / photo-selector + Floating Points | lane/expand | **CLOSED / NOT PLANNED** — preserved lineage neighbors outside this repository's product boundary |
| #5 | Factory hardening: verify_editions / edition_status path & lifecycle docs | lane/heal | **CLOSED** |
| #12 | Assigned-copy Git parity, custody, and retirement | housekeeping | **OPEN / PARTIAL** — remote refs and clean-clone reconstruction pass; encrypted archive + independent restore not established, copy retained |

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
- **N=7 authored layouts** (PRs #14–15) — promoted the evidenced portrait/landscape pair into the canonical N=2..7 family; unified fixture generation; extended Artifact 001; retained explicit N=8 rejection; repaired root-invoked evidence tools.

## Fixtures

- `samples/inaugural/inaugural-0{1..3}.mp4` 3× synthetic (gitignored, regenerable via `tools/make_inaugural_fixture.py`)
- `runtime-proof/` 2..7 + slice variants; `artifact-001/renders/` 13× 1080p — all gitignored, regenerable via `core/make_runtime_fixture.py` + `core/make_artifact_001.py`
- **Ledger** `artifact-001/evidence/renders.json` 13×1080p canonical; `runtime-proof/evidence/render-family.json` 10× family; N=7 portable pair byte-identical

## Outstanding / parked

- **Tags** — no tags yet; first `vX.Y.Z` tag to be created on next verified `main` release point.
- **Issue #12** assigned-copy retirement — live refs and current CI are verified; retain `/workspaces/simvltanea` until unique local Git objects and non-reproducible ignored payload have encrypted custody with an independent restore proof.
