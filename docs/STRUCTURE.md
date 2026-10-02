# Repository structure governance

`tools/verification/verify_repository_structure.py` is the executable structure
contract. Update it and this document together when the layout changes.

Run the contract from the repository root:

```bash
python3 -m tools.verification.verify_repository_structure
```

## Source and command boundaries

- `src/simvltanea/` is the installable engine and browser-runtime package.
- `tools/` contains operational commands grouped by workflow: `editions`,
  `media`, `publishing`, `preservation`, and `verification`.
- `tests/` mirrors product and governance behavior.
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

The approved root directories are `.github`, `archive`, `docs`, `evidence`,
`examples`, `fixtures`, `src`, `tests`, `tools`, and `var`; `.vscode` is
optional. Root configuration and governance files are enumerated by the
executable contract, including `pyproject.toml`.

Branch guidance and project status live in `docs/BRANCHES.md` and
`docs/STATUS.md`. Root files are reserved for project entry points, the edition
registry, and conventional tooling configuration such as `requirements.txt`.
Obsolete `core/` and `runtime-proof/` directories must not be recreated; runtime
proof output belongs in `var/proofs/`.

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
