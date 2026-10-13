# Naming record

The October 13, 2026 identity contract supersedes the earlier use of SIMVLTANEA
as both software and artwork. The artwork remains **SIMVLTANEA**; the software
is **Independent Loop Compositor** (`independent-loop-compositor`). The canonical
public Python API is `independent_loop_compositor`.

`simvltanea` remains the compatible distribution name, implementation namespace,
and existing repository slug. These are explicit compatibility addresses, not
titles inherited by future compositions. TripTicks remains the historical title
of the 2017 three-panel instantiation. Historical decisions and original files
remain in Git history and retained archives.

See [identity migration](IDENTITY_MIGRATION.md) and the typed root
[`ace-manifest.json`](../../ace-manifest.json). No repository relocation,
media rename, source re-registration, or change of accepted external engine
hashes is necessary for this migration.

## Filesystem naming policy

New and actively maintained paths follow these conventions:

| Scope | Convention | Examples |
| --- | --- | --- |
| Directories outside Python source | `kebab-case` | `artifact-001`, `visual-proof` |
| Python package directories under `src/` | `snake_case` | `independent_loop_compositor` |
| Python files | `snake_case` with underscore roles | `composition_model.py`, `test_audio_model.py` |
| JavaScript feature assets | `name.role.js` | `browser.runtime.js`, `browser.continuity.js` |
| Canonical documentation in `docs/` | `SCREAMING_SNAKE_CASE` | `AUDIO_ARCHITECTURE.md` |
| Dated provenance reports | `SCREAMING_SNAKE_CASE_YYYY-MM-DD` | `PHOTOS_PREVIEW_2026-10-02.md` |
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

## File roles

Python modules use importable snake_case role names (`composition_model.py`,
`browser_runtime.py`, `test_composition_model.py`). Dots in a Python basename
change import semantics, so Python role suffixes use underscores. Feature API
files use the ecosystem name `__init__.py`; feature guides use `README.md`.
JavaScript assets may use dot role suffixes such as `browser.runtime.js`.
