# Contributing to SIMVLTANEA

## Branching

Read `BRANCHES.md` before creating branches.

- `main` is always releasable. No direct commits.
- Standing lanes (`lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve`) persist.
- Implementation happens on short-lived `work/<lane>/<short-intent>` or `feat|fix|chore|docs|test/<short-intent>` branches, preferably in worktrees, then PRs back to the correct lane or to `main`.
- One intention per PR. Link the issue. Include how to verify.
- After merge, delete the working branch. Keep the lane.

## Verify before PR

```bash
# Full suite (120 tests across unit, ffmpeg render, browser runtime, continuity)
python3 -m pytest -q            # or: python3 -m unittest discover -s tests
python3 tools/verify_local_lifecycle.py          # must print "local lifecycle ok"
python3 tools/verify_editions.py                 # must print "edition presets ok"
python3 tools/edition_status.py                  # inspect edition readiness
```

CI (` .github/workflows/ci.yml`) runs the same two gates: `unittest discover -s tests` + `verify_local_lifecycle.py`.

## Generated lanes

These directories are gitignored and must never leak into a PR:

```
samples/  renders/  site/  packages/  work/  artifact-001/media  runtime-proof/
```

Only `*/.gitkeep` placeholders and `artifact-001/baseline/` provenance are tracked. If your diff shows generated files, stop and run `tools/verify_local_lifecycle.py`.

To regenerate synthetic proofs without committing blobs:

```bash
python3 core/make_artifact_001.py           # full 8-state family
python3 core/make_artifact_001.py --draft   # fast 360p draft
python3 tools/generated_inventory.py --json # inventory by lane
```

## Edition authoring

See `docs/EDITION_AUTHORING.md` for real-media ingestion (`samples/` → `atomize_media.py` → `editions.json` → `build_edition.py` → `verify_editions.py`).

Every edition entry in `editions.json` must satisfy `tools/verify_editions.py` (`schema triptych.editions.v1`). Run it before committing edition changes.

## Invariant

`N` independent loops + authored portrait/landscape layouts + independent rational clocks + simultaneous coexistence + presentation-only orientation changes + no filler (`README.md` Invariant). `N=7` is experimental only — `core/artifact001_layouts.py` rejects 7. See `docs/CANON.md`.

## Secrets

Never commit credentials, production data, or raw photo-library paths. The verifier rejects `FORBIDDEN_TEXT` tokens (`/Users/`, `.photoslibrary`, etc.) in `editions.json`.

## PR checklist

- [ ] Branch from correct lane (`BRANCHES.md`)
- [ ] Tests pass (`pytest -q`, 120/120)
- [ ] `verify_local_lifecycle.py` prints `local lifecycle ok`
- [ ] `verify_editions.py` prints `edition presets ok` (if touching editions)
- [ ] No generated lane files in diff (`git status --porcelain`)
- [ ] Linked issue + `how to verify` steps in PR body
