# SIMVLTANEA — STATUS

> Updated 2026-10-01 (America/New_York) — N=7 authored layouts shipped via PRs #14–15 and closeout PR #16. Repository governance now covers naming, structure, and changed Markdown with blocking CI gates. Standing lanes follow the verified `main` after closeout. Assigned-copy housekeeping issue #12 remains partial: live Git refs are remotely reconstructable, but unique local Git objects and ignored payload do not yet have independently restored encrypted custody, so the copy is retained.
>
> Historical receipts: CI Verification run `36953519356` passed all 174 pre-governance tests on the PR #16 closeout head. On 2026-09-11 22:00 UTC, green trunk, tolerance tuning, and lane synchronization were confirmed via `8fbdc46`.

## Green gates (must pass on `main`)

| Gate | Command | Local | CI (`ubuntu-latest`) |
| --- | --- | --- | --- |
| Tests (non-browser) | `pytest tests/model/test_authoring_contract.py tests/model/test_composition_model.py tests/render/test_composition_render.py tests/governance/test_review_proof.py -q` | **73 passed** (17 subtests) | **pass** (part of CI suite) |
| Tests (plan) | `python3 -m unittest tests.browser.test_browser_runtime.PlanTests -v` | **12 passed** | **pass** |
| Naming | `ls-lint` (v2.3.1) | **pass** | **required** `config/lint/ls-lint.yml` |
| Structure | `python3 -m tools.verification.verify_repository_structure` | **pass**; 20 Git-fixture tests | **required** before dependency installation |
| Changed Markdown | `markdownlint-cli@0.45.0` with repository config and ignore file | **pass** on added/edited Markdown | **required** on PR and push diffs; MD041 and MD047 enforced |
| Tests (full, in-memory) | `PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest discover -s tests -v` | 194 discovered; **153 passed** on Python 3.14; 41 native-browser methods require an installed browser | **required** full suite on Python 3.12 with Chrome |
| Lifecycle | `python3 -m tools.verification.verify_local_lifecycle` | `local lifecycle ok` 0 leaks | **pass** `.github/workflows/ci.yml` |
| Edition presets | `python3 -m tools.verification.verify_editions` | `edition presets ok` **7**/16/43 | **pass** |
| Edition status | `python3 -m tools.editions.edition_status` | 7 editions `local-only` | **pass** |
| Layouts | `python3 -m tools.verification.verify_layouts --examples` | `layouts ok` counts `2,3` | **pass** wired `99c573d` |
| Media pix_fmt | `ffprobe -show_entries stream=pix_fmt` gate | **yuv420p** 7/7 `var/proofs/media/*.mp4` + `var/artifact-001/renders` `13×` | **pass** `yuv420p` 7/7 gate |
| CI | `.github/workflows/ci.yml` | local non-browser and evidence gates pass | [CI Verification](https://github.com/4444J99/simvltanea/actions/workflows/ci.yml) must be green before merging |

**Release boundary:** N=2 through N=7 are supported. Governance changes land only after the complete CI workflow passes; standing lanes are then fast-forwarded to `main` and merged working branches removed. Assigned-copy retirement remains blocked by issue #12's external private-custody gate, separate from application and repository-governance health.

## Trunk

- `main` includes the N=7 closeout PR #16; repository governance follows the same PR-only, no-force-push boundary
- Lineage: `… → 8fbdc46 34600713288 SUCCESS` → `f4ede0e/c638a25` (Audio v1.1, PR #10) → `0324129` (archive provenance, PR #11) → `da426fc/cdcfed4` (inaugural fixture, `work/heal/inaugural-fixture-eval`)
- Merge authority: available; CI is a required contributor-policy gate even where GitHub branch protection is not configured
- Branches: `main` + `lane/verify|heal|expand|evolve` (all synchronized); no open work branches
- Worktrees: single primary `[main]`
- Tags: none

## Lanes (standing — per `docs/governance/BRANCHES.md`)

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

- **CI heal** `.github/workflows/ci.yml` — runtime-proof fixture generation, ffprobe `yuv420p` gate, `PORTVS_BROWSER_TRANSPORT=in-memory`, browser diagnostics, `CLOCK_TOLERANCE .20`, `requirements.txt` pin.
- **Layouts guard** `tools/verification/verify_layouts.py` — mirrors composition model guards; wired to CI.
- **N=2 authored layouts** `src/simvltanea/authoring/artifact001_layouts.py` — portrait + landscape panels; tests updated.
- **Seamed slice field** `src/simvltanea/authoring/composition.py` — `SEAM_MODES`, `validate_slice`, `validate_seam`, `slice_rect`, `seam_config`, `resolve_at`, `continuous`, `compile_segments`.
- **Renderer** `src/simvltanea/rendering/render_triptych.py` — `Panel.source_crop`, `Segment.seam`, `_crop_prefix`, `render_segment` seam blur.
- **Browser** `src/simvltanea/browser/browser_runtime.py` + `src/simvltanea/browser/browser_runtime.js` — `_continues`, canonicalize, `applySlice`, `renderSeams`.
- **Audio v1.1** (PR #10) `src/simvltanea/authoring/composition.py`, `src/simvltanea/authoring/composition_model.py`, `src/simvltanea/rendering/render_triptych.py`, `src/simvltanea/browser/browser_runtime.js/.py` — opt-in synchronized soundtrack + spatial loop mix; `docs/architecture/AUDIO_ARCHITECTURE.md`; tests `test_audio_editions`, `test_audio_model`, `test_audio_render`, `test_browser_audio`.
- **Archive provenance** (PR #11) `archive/PROJECT_MANIFEST.md` — corrected MEDA-002 checksum/stream/links; `tests/governance/test_archive_media_provenance.py` retained-artifact regressions.
- **Inaugural fixture generator** (`work/heal/inaugural-fixture-eval`) `tools/media/make_inaugural_fixture.py` + `tests/editions/test_inaugural_fixture.py` — synthetic clean-clone demo clips; boundary + decodability tests.
- **CI trigger cleanup** `.github/workflows/ci.yml` — removed stale `work/evolve/audio-*` push trigger.
- **N=7 authored layouts** (PRs #14–15) — promoted the evidenced portrait/landscape pair into the canonical N=2..7 family; unified fixture generation; extended Artifact 001; retained explicit N=8 rejection; repaired root-invoked evidence tools.
- **Repository governance** — `ls-lint/action@v2.3.1`, explicit naming rules, a standard-library Git-visible structure verifier, shared generated-output boundaries, 20 fixture tests, and changed-Markdown linting. Contributor/PR instructions, editor/assistant configuration, and portable documentation links are included; historical material and ignored local builds remain intact.

## Fixtures

- `var/samples/inaugural/inaugural-0{1..3}.mp4` 3× synthetic (gitignored, regenerable via `tools/media/make_inaugural_fixture.py`)
- `var/proofs/` 2..7 + slice variants; `var/artifact-001/renders/` 13× 1080p — all gitignored, regenerable via `src/simvltanea/generators/make_runtime_fixture.py` + `src/simvltanea/generators/make_artifact_001.py`
- **Ledger** `var/artifact-001/evidence/renders.json` 13×1080p canonical; `var/proofs/evidence/render-family.json` 10× family; N=7 portable pair byte-identical

## Outstanding / parked

- **Tags** — no tags yet; first `vX.Y.Z` tag to be created on next verified `main` release point.
- **Issue #12** assigned-copy retirement — live refs and current CI are verified; retain `/workspaces/simvltanea` until unique local Git objects and non-reproducible ignored payload have encrypted custody with an independent restore proof.
