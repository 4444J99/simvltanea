# Stewardship Plan — SIMVLTANEA (2026-09-10)

> Doctrine: Verify → Heal → Expand → Evolve. This plan executes waves 0–3 in a single session per operator authorization.

## Orientation

- **Purpose**: `README.md:1` configurable simultaneous video-loop compositions (N independent loops + paired portrait/landscape layouts + rational clocks + presentation-only orientation).
- **Done**: invariant holds, N=3..6 pairs verified, `visual-form-composition/v1` compiler/browser/FFmpeg green, Artifact 001 regenerable, 120 tests + lifecycle gate pass.
- **Green**: `pytest -q` 120/120 + `tools/verify_local_lifecycle.py` no leaks (+ edition gates after heal).

## Inventories (summary)

- **Branches**: `main@6e122da` only, linear 10 commits, no other refs (`git branch -a`), `work/` empty `.gitkeep`, no tags, no worktrees.
- **PRs**: 0 open/closed in `4444J99/simvltanea`; upstream `organvm/portvs#9`/`#7` are historical provenance.
- **Issues**: 0 open/closed before steward; 10 default labels, 0 milestones.
- **Hidden**: `TODO 0`, browser continuity gated on chromium, `.gitignore` lanes correctly excluded, 7-loop experimental, audio v1.1 spec parked.

## Verdict families

- F1 `verify/green-default` → needs-heal → prove 120 tests + lifecycle
- F2 `standing-branch-constitution` → active → write BRANCHES.md
- F3 `generated-lanes` → active → document regenerability
- F4 `upstream-closeout` → blocked → post comment or park issue #1
- V5 `audio-v1.1` → parked → issue #2 lane/evolve
- F6 `seven-loop` → parked → issue #3
- F7 `visual-proof` → active → make_artifact_001 idempotent
- F8 `edition-ingestion` → active → fix validator + fixture
- F9 `governance` → needs-heal → CONTRIBUTING/CODEOWNERS/SECURITY/templates/labels
- V10 `photo-selector` lineage → parked → issue #4

## Branch constitution

See `BRANCHES.md` — GitHub Flow with lanes `lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve`. No `develop`. Work branches `work/<lane>/<short-intent>` via worktrees adjacent to repo.

## Waves (executed)

- **Wave 0**: proved green (120/120 via `pytest -q` in 116s, `verify_local_lifecycle ok`, `verify_editions ok` after heal, `edition_status` 6 editions).
- **Wave 1**: `BRANCHES.md` + `CONTRIBUTING.md`/`CODEOWNERS`/`SECURITY.md`/templates + `lane/*` labels + parked upstream issue #1.
- **Wave 2**: hardened `tools/edition_status.py` + `verify_editions.py` (root path, folder alias, zero gain) + `editions.json` inaugural fix + synthetic `samples/inaugural` fixture + issues #2–#5.
- **Wave 3**: added CI edition gates + `STATUS.md` + this plan.

See `STATUS.md` for current green table.
