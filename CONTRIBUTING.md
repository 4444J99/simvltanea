# Contributing to SIMVLTANEA

## Branching

Read `docs/BRANCHES.md` before creating branches.

- `main` is always releasable. No direct commits.
- Standing lanes (`lane/verify`, `lane/heal`, `lane/expand`, `lane/evolve`) persist.
- Implementation happens on short-lived `work/<lane>/<short-intent>` or `feat|fix|chore|docs|test/<short-intent>` branches, preferably in worktrees, then PRs back to the correct lane or to `main`.
- One intention per PR. Link the issue. Include how to verify.
- After merge, delete the working branch. Keep the lane.

## Verify before PR

```bash
set -o pipefail
# Filename and directory governance (install from https://ls-lint.org first)
ls-lint

# Markdown in committed branch changes against main
git diff --name-only --diff-filter=ACMR -z origin/main...HEAD -- '*.md' |
  xargs -0 -r npx --yes markdownlint-cli@0.45.0 \
    --config .markdownlint.json --ignore-path .markdownlintignore --

# Repository placement, required paths, and generated-output boundaries
python3 -m tools.verification.verify_repository_structure # must print "repository structure ok"

# Full suite (unit, ffmpeg render, browser runtime, continuity)
python3 -m pytest -q            # or: python3 -m unittest discover -s tests
python3 -m tools.verification.verify_local_lifecycle # must print "local lifecycle ok"
python3 -m tools.verification.verify_editions    # must print "edition presets ok"
python3 -m tools.editions.edition_status         # inspect edition readiness
```

CI (`.github/workflows/ci.yml`) runs naming and structure checks, linting for
changed Markdown, the full test suite (`unittest discover -s tests`), and the
local lifecycle gate.
The structure gate runs immediately after Python setup, before dependencies
are installed.

Markdown checks use Node.js 20 or newer and the pinned CLI shown above. CI lints
entire added, copied, renamed, or modified `.md` files against the PR base (or
the previous commit on a push). Unchanged documents retain their existing
formatting. `.markdownlint.json` keeps MD041 (top-level title) and MD047 (final
newline) enabled; `.markdownlintignore` excludes historical material, generated
lanes, and the vendor Mermaid instructions from CLI checks. Before committing,
check new or uncommitted Markdown by passing its paths directly to
`npx --yes markdownlint-cli@0.45.0 --config .markdownlint.json --ignore-path .markdownlintignore`.

See [repository structure governance](docs/STRUCTURE.md) for approved root
entries, required paths, and folder roles. When changing the layout, update the
named policy tables in `tools/verification/verify_repository_structure.py` and the documented
contract in the same PR. Keep new scripts under `tools/` or `core/`, according
to their role; root-level scripts require an explicit contract change.

## Generated lanes

These directories are gitignored and must never leak into a PR:

```text
var/samples/  var/renders/  var/site/  var/packages/  var/work/  var/proofs/
```

Only root `.gitkeep` placeholders in `samples`, `renders`, `site`, `packages`,
and `work`, plus the two Artifact 001 baseline inputs
(`fixtures/artifact-001/baseline-manifest.json` and
`fixtures/artifact-001/baseline/render_triptych.original.py`), are exceptions.
Visual-proof `media` and `renders` outputs must also remain local; approved
inspected PNG frames belong in `evidence/visual-proof/frames/`.
Ignored local outputs are allowed, but force-staged or committed outputs fail
both the structure and lifecycle checks. If your diff shows generated files,
run both verifiers and remove the unintended Git additions.

To regenerate synthetic proofs without committing blobs:

```bash
PYTHONPATH=src python3 -m simvltanea.make_artifact_001           # full family
PYTHONPATH=src python3 -m simvltanea.make_artifact_001 --draft   # fast 360p draft
python3 -m tools.preservation.generated_inventory --json         # inventory by lane
```

## Edition authoring

See `docs/EDITION_AUTHORING.md` for real-media ingestion (`var/samples/` → media tools → `editions.json` → edition tools → verification).

Every edition entry in `editions.json` must satisfy `tools.verification.verify_editions` (`schema triptych.editions.v1`). Run it before committing edition changes.

## Invariant

`N` independent loops + authored portrait/landscape layouts + independent rational clocks + simultaneous coexistence + presentation-only orientation changes + no filler (`README.md` Invariant). Authored engineering pairs currently cover N=2 through N=7; unsupported counts fail explicitly. See `docs/CANON.md`.

## Secrets

Never commit credentials, production data, or raw photo-library paths. The verifier rejects `FORBIDDEN_TEXT` tokens (`/Users/`, `.photoslibrary`, etc.) in `editions.json`.

## PR checklist

- [ ] Branch from correct lane (`docs/BRANCHES.md`)
- [ ] New files and directories pass `ls-lint`
- [ ] Added or edited Markdown passes `markdownlint-cli@0.45.0`
- [ ] `verify_repository_structure.py` prints `repository structure ok`
- [ ] Intentional layout changes update the structure policy and documentation in this PR
- [ ] Tests pass (`pytest -q`)
- [ ] `verify_local_lifecycle.py` prints `local lifecycle ok`
- [ ] `verify_editions.py` prints `edition presets ok` (if touching editions)
- [ ] No generated lane files in diff (`git status --porcelain`)
- [ ] Linked issue + `how to verify` steps in PR body
