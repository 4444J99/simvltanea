# Repository structure governance

`src/simvltanea/layout.toml` declares physical path roles and placement policy.
`tools/verification/verify_repository_structure.py` executes that contract.
See [configurable layout](LAYOUT.md) for role references and relocation steps.

Run the contract from the repository root:

```bash
python3 -m tools.verification.verify_repository_structure
```

## Source and command boundaries

- `src/simvltanea/` is the installable engine and browser-runtime package.
- `tools/` contains operational commands grouped by workflow: `editions`,
  `media`, `publishing`, `preservation`, and `verification`.
- Tests and feature guides live beside their owning source; `tests/` preserves
  the historical unittest discovery entry point.
- `examples/` contains safe configuration templates.
- `fixtures/` contains small, tracked regression inputs. Artifact 001's pinned
  baseline is under `fixtures/artifact-001/`.
- `docs/`, `archive/`, and `evidence/` remain separate because active guidance,
  historical records, and reviewed evidence have different lifecycles.

## Generated-output boundary

All generated or private local output belongs below `var/`:

```text
var/
├── artifact-001/
├── packages/
├── proofs/
├── renders/
├── samples/
├── site/
└── work/
```

Only `var/.gitkeep` is Git-visible. Everything else below `var/` is ignored and
regenerable. Commands resolve these paths through `simvltanea.paths`; they must
not create parallel output trees relative to their own script directories.

Reviewed visual evidence remains under `evidence/visual-proof/`. Its generated
`media/` and `renders/` children stay local, while the ledger and inspected PNG
frames may be tracked.

## Approved root

The root files are `README.md`, `LICENSE`, `pyproject.toml`, and `.gitignore`.
Python packaging, the `verification` optional dependencies, and pytest settings
share `pyproject.toml`. Install with `python3 -m pip install -e ".[verification]"`.

GitHub governance lives in `.github/`; lint configuration lives in `config/lint/`.
Run naming checks with `ls-lint --config config/lint/ls-lint.yml`.
Production declarations live in `editions/registry.json`; examples remain separate.

Active docs are grouped into `architecture/`, `authoring/`, `governance/`,
`provenance/`, `plans/`, and `continuations/`. Retained incubation records live in
`archive/incubation/`, with their original contents preserved.

Engine implementations are grouped into `authoring/`, `browser/`, `rendering/`,
and `generators/`. Root package modules retain compatibility with existing
imports and CLI commands. Browser JavaScript is distributed with its subpackage.
Feature APIs use ordinary imports with explicit `__all__` declarations.

Feature tests live directly in `authoring/`, `browser/`, `rendering/`,
`tools/editions/`, and `tools/verification/`. Pytest uses importlib mode with qualified test imports. Both pytest and the historical
`python3 -m unittest discover -s tests` command discover these suites.

Cross-feature imports use explicit exports in feature `__init__.py` files.
Run `python3 -m tools.verification.verify_feature_boundaries` to enforce this
barrier. Python does not provide runtime access control; this AST gate enforces
static imports in active source and tools, while feature tests may inspect internals.

Approved root directories are `.github`, `config`, `editions`, `archive`, `docs`,
`evidence`, `examples`, `fixtures`, `src`, `tests`, `tools`, and `var`;
`.vscode` is optional. Obsolete `core/` and `runtime-proof/` trees must not be
recreated; generated runtime proofs belong in `var/proofs/`.

The verifier inventories indexed files and nonignored untracked files with
NUL-delimited Git output. It reports violations without moving or deleting
files. CI runs the structure contract before dependency installation.

## Complementary checks

- `ls-lint` enforces file and directory names.
- Markdown lint checks changed documentation.
- `tools.verification.verify_local_lifecycle` rejects generated-output leaks,
  Python caches, and local metadata.
- Unit tests exercise required paths, linked worktrees, staged removals,
  arbitrary filenames, and every generated-output visibility state.

Continuation handoffs live in `docs/continuations/`. Markdown guides follow the
normal documentation rules; JSON receipts require an explicit
`documentation_file_exceptions` entry in the layout contract.
