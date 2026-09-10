# Branch constitution — SIMVLTANEA

Default branch: `main`
Policy: GitHub Flow on top of a small set of standing program lanes.
Worktrees: one worktree per active working branch. Do not pile unrelated WIP onto a lane.
History: linear, no force-push to `main`. All changes via PR. Preserve history (rebase-then-merge); squash only if the repo already squashes and the PR description preserves intention.

## Standing branches (always exist)

| Branch | Purpose | Merge into | Green means |
| --- | --- | --- | --- |
| `main` | Production-true trunk. Always releasable. No direct work commits. | tags / releases | required CI (`CI Verification` on `ubuntu-latest`: 120 tests + `tools/verify_local_lifecycle.py` no leaks) passes; `visual-form-composition/v1` invariants hold |
| `lane/verify` | Proof: tests, contracts, CI, reproducibility, visual proof regen | `main` | verification suite strictly stronger or equal; `python3 core/make_artifact_001.py` idempotent; browser continuity probe green |
| `lane/heal` | Repair of known broken or rotting behavior, docs/governance debt that blocks shipping | `main` | previously failing paths pass; governance updated |
| `lane/expand` | Complete already-stated scope: edition coverage N=3..6, ingestion factories, remaining jurisdictions/features | `main` | new coverage verified (`tools/verify_editions.py`, `tools/edition_status.py`), not merely sketched |
| `lane/evolve` | Structural improvement implied by current purpose (e.g., Audio v1.1, authored N=7) | `main` | behavior preserved except documented changes; spec PR precedes code |

Dormant lanes stay listed here until explicitly retired by a PR updating this file. A lane with no work for a long time is marked "dormant" — not deleted.

## Working branches (temporary)

Pattern: `work/<lane>/<short-intent>` preferred
Also allowed: `feat|fix|chore|docs|test|hotfix/<short-intent>`

Rules:
- Cut from the lane you are advancing, or from `main` if the change is trunk-ready.
- One intention per branch. Lifetime measured in days, not months.
- Merge by PR with linked issue, `how to verify` steps, and evidence. Delete working branch after merge. Keep the lane.
- If blocked, park with a comment `Parked intention: …` and keep the branch; do not erase.
- Never `fix-stuff`, `wip`, `temp`, `asdf`.

## Hotfix

`hotfix/<short-intent>` from `main` → PR to `main` → back-port (merge or cherry-pick) to any living lanes that diverged.

## Release

`release/*` only if versioned artifacts ship and a freeze line is needed. Otherwise `main` is the release line; tag `vX.Y.Z` on green `main`. No tags currently; first tag will be created on verified `main`.

## Worktree map

One worktree per active working branch. The `work/` directory itself is a gitignored lane cache (see `.gitignore:work/*`), not a worktree container.

```bash
# Example: create lane worktrees adjacent to the repo
git worktree add ../simvltanea-wt-verify lane/verify
git worktree add ../simvltanea-wt-heal   lane/heal
git worktree add ../simvltanea-wt-expand lane/expand
git worktree list
```

Do not create worktrees inside `work/` — that directory is ignored and disposable.

## What must never live on `main`

Generated lanes (`samples/`, `renders/`, `site/`, `packages/`, `work/`, `artifact-001/media`, `runtime-proof/`, `evidence/visual-proof/media/`), secrets/credentials/production data, large MP4s, `.DS_Store`, `__pycache__`. Gated by `tools/verify_local_lifecycle.py` (`GENERATED_LANES`). Exceptions: tracked placeholders (`*/.gitkeep`) and `artifact-001/baseline/` provenance files.

## Labels

Lane labels mirror this constitution: `lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve`, plus `amalgamated-into:#N` for family successors. Default GitHub labels (`bug`, `enhancement`, `documentation`, etc.) remain.

## Retirement

A standing lane is retired only when its purpose is complete or absorbed, via a PR updating this file. Branches are never deleted as a substitute for thinking. See `docs/RECOVERY.md` for provenance of retired intentions.
