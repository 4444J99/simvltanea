# Repository structure governance

`tools/verify_repository_structure.py` is the executable structure contract.
Its named policy tables govern required paths, approved root entries, folder
roles, and generated-output boundaries. Update those tables and this document
in the same PR as an intentional layout change.

Run the contract from the repository root:

```bash
python3 tools/verify_repository_structure.py
```

Use `--root PATH` to check another Git repository, including a test fixture.
The command reports sorted, actionable violations and exits with `0` for a
passing contract, `1` for policy violations, or `2` for invocation or Git
failures. CI runs it immediately after Python setup, before dependency
installation; a failure blocks the build.

## Approved root entries and required paths

Approved root directories are `.github`, `archive`, `artifact-001`, `core`,
`docs`, `evidence`, `examples`, `packages`, `renders`, `samples`, `site`, `tests`,
`tools`, and `work`. These directories are required; `.vscode` is optional.
Other root entries, including new root-level scripts, require an explicit
contract update.

The following root files are approved and required:

```text
.gitignore                  .ls-lint.yml
.markdownlint.json          .markdownlintignore
BRANCHES.md                 CODEOWNERS
CONTRIBUTING.md             LICENSE
README.md                   SECURITY.md
STATUS.md                   editions.json
pytest.ini                  requirements-runtime-proof.txt
```

The contract also requires:

- `.github/workflows/ci.yml` and `core/__init__.py`.
- `README.md` in `core`, `tools`, `tests`, `examples`, `docs/historical`,
  `archive/chatgpt`, `archive/raw`, and `evidence/visual-proof`.
- `docs/plans/INDEX.md`, `archive/PROJECT_MANIFEST.md`, and
  `evidence/visual-proof/ledger.json`.
- The governance documents `docs/NAMING.md` and `docs/STRUCTURE.md`.
- `artifact-001/baseline-manifest.json` and
  `artifact-001/baseline/render_triptych.original.py`.
- `.gitkeep` at the root of each generated lane: `packages`, `renders`,
  `samples`, `site`, and `work`.

Required nested directories are `archive/chatgpt`, `archive/raw`, `docs/plans`,
`docs/historical`, `artifact-001/baseline`, `evidence/visual-proof`, and
`evidence/visual-proof/frames`. Archive category directories are allowed but
not individually required.

Required files must exist as regular files and must not be staged for deletion.
A remaining local copy does not satisfy a staged deletion. Directory presence
comes from Git-visible children rather than empty folders or local output.

## Folder roles

| Area | Allowed contents |
| --- | --- |
| `core` | Python, JavaScript, Markdown, and optional `core/layouts.json` |
| `tools` | Python utilities and Markdown documentation |
| `tests` | `test_*.py`, `__init__.py`, `conftest.py`, and Markdown |
| `examples` | JSON configurations and Markdown |
| `docs` | Markdown at the root; only `plans` and `historical` subdirectories |
| `docs/plans` | Markdown plans and the plans index; names also follow the naming policy |
| `docs/historical` | Historical files with unrestricted formats and preserved source names |
| `.github` | Root Markdown; direct workflow YAML and issue-template Markdown/YAML; Markdown descendants under `instructions` |
| `.vscode` | Optional JSON editor configuration directly within the directory |
| `archive` | The project manifest, raw intake documentation, and classified ChatGPT material |
| `evidence` | Visual-proof README, JSON ledger, and PNG files under `visual-proof/frames` |

Classified archival material belongs under `archive/chatgpt/` in `threads`,
`handoffs`, `receipts`, `research`, `evidence`, `logs`, `media`, `bundles`,
`sessions`, `prompts`, or `extracts`. `logs` remains optional. These categories
preserve arbitrary archival filenames and formats, including recovered code,
binary media, and bundles.

Git-visible raw intake is limited to `archive/raw/README.md`,
`archive/raw/.gitkeep`, and the existing legacy receipt
`archive/raw/PR9_review_proof_2026-09-06/README.md`. That exact receipt is an
exception, not a convention permitting new raw-intake folders. Historical
material also has an approved home in `docs/historical/`.

## Generated-output boundaries

Only the root `.gitkeep` may be Git-visible in each of `packages`, `renders`,
`samples`, `site`, and `work`; nested placeholders are not exceptions.
`runtime-proof/` must remain local. Within `artifact-001/`, only the two required
baseline inputs above may be Git-visible. Visual-proof `media` and `renders`
outputs must also remain local; inspected PNG frames in
`evidence/visual-proof/frames/` are approved evidence.

Finder `.DS_Store` files and Python `__pycache__` directories are prohibited
throughout the Git-visible inventory. Root `.venv` and `.pytest_cache` also
remain local-only.

The verifier inventories indexed files and nonignored untracked files using
NUL-delimited Git output. Ignored local builds are permitted. Force-staging or
committing an ignored output makes it Git-visible and causes the check to fail.
The inventory does not recursively scan local output directories. Staged
removals of optional paths are allowed.

## Complementary checks

- `ls-lint` enforces file and directory names using `.ls-lint.yml`; see
  [Naming policy](NAMING.md).
- `markdownlint-cli@0.45.0` checks added or edited Markdown in CI using
  `.markdownlint.json` and `.markdownlintignore`, including MD041 title and
  MD047 final-newline requirements. Both configuration files are required.
- `verify_repository_structure.py` enforces placement, required presence, and
  the repository's folder roles.
- `verify_local_lifecycle.py` shares the generated-path policy and checks for
  generated/local leaks and prohibited raw intake across indexed and
  nonignored untracked paths. It also provides optional pending-change and
  untracked-size limits.

These checks report violations without moving or deleting files. Structure
verification uses only Python's standard library and Git. Import boundaries,
module-to-test mappings, and arbitrary nesting or file-count limits are not
part of this contract.
