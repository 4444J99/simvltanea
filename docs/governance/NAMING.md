# Naming record

| # | Candidate | Semantic rationale | Relation to TripTicks | Valid for N>3 | Collision / search | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | TripTicks | Historical title; play on triptych / TripTik | Origin name | No; names the three-panel construction | Unique on YouTube as ETCETER4 upload | Preserve as historical title only |
| 2 | Triptych Video Canon | Incubator descriptor | Implementation nickname | No; locks count at three | Collides with many triptych tools | Configuration / incubator path only |
| 3 | Polyptych | Classical N-panel altarpiece | Direct generalization of triptych | Yes | Synonym family the handoff forbids | Rejected |
| 4 | visual-composition-engine | Prior Portvs PR #11 extract target | Names shared tooling, not the work | Yes | Generic; never provisioned remotely | Recorded as superseded-pending |
| 5 | Parataxis | Side-by-side independent units | Formal, not historical | Yes | Literary-theory term | Strong alternate |
| 6 | Copraesentia | Co-presence of streams | Describes the experience | Yes | Rare; Latinate | Strong alternate |
| 7 | **SIMVLTANEA** | Simultaneous independent visual streams in one authored field | TripTicks is the first simultaneous instance | Yes; simultaneity is independent of count | Rare as a product/artwork name; ORGANVM orthography (V for U) | **Canonical** |

## Recommended canonical name

**SIMVLTANEA**

Repository: `4444J99/simvltanea`

Display title: SIMVLTANEA
Historical title: TripTicks
Configuration words: triptych, N-panel, portrait, landscape
Schema id already in code: `visual-form-composition/v1`

Historical artifacts are not renamed.

## Filesystem naming policy

New and actively maintained paths follow these conventions:

| Scope | Convention | Examples |
| --- | --- | --- |
| Directories | `kebab-case` | `artifact-001`, `visual-proof` |
| Python and JavaScript files | `snake_case` | `composition_model.py`, `browser_runtime.js` |
| Canonical documentation in `docs/` | `SCREAMING_SNAKE_CASE` | `AUDIO_ARCHITECTURE.md` |
| Plans in `docs/plans/` | date-prefixed `kebab-case` | `2026-09-11-final-closeout.md` |
| Conventional ecosystem files | tool-defined names | `README.md`, `LICENSE`, `.gitignore` |

Prefer single-word directory names for workflow groups and output lanes, such as
`media`, `verification`, and `proofs`. When multiple words are necessary, join
them with hyphens, never spaces. Runtime proof output uses `var/proofs/`.

The `config/lint/ls-lint.yml` is the executable policy. CI runs it on every push and
pull request. Contributors should run `ls-lint --config config/lint/ls-lint.yml` locally before opening a pull
request when they add or rename paths.

Historical and provenance-bearing material under `archive/`, `archive/incubation/`,
and `fixtures/artifact-001/baseline/` is excluded from linting. Those paths preserve
source identifiers and recovered names; do not rename them merely to satisfy an
active-repository convention. Generated and local-only lanes are also excluded
because repository cleanliness checks, rather than filename policy, govern them.
