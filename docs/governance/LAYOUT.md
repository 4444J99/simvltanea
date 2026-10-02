# Configurable repository layout

Physical directory names are declared in
[`src/simvltanea/layout.toml`](../../src/simvltanea/layout.toml).
Commands, template loaders, inventory, generated receipt references, structure
checks, and derived ignore rules consume that manifest.

## Logical roles

`generated` is the local output boundary. Its child roles are `work`, `samples`,
`renders`, `site`, `packages`, `proofs`, and `artifact_output`.
Tracked inputs use `examples`, `fixtures`, and `artifact_fixture`; `registry`
identifies the production registry inside `editions`.
Other roles identify the source, package, tools, tests, docs, archive, evidence,
GitHub governance, and lint configuration directories.

Names such as `work` are stable role identifiers. Their physical locations can
change independently, including to nested directories. Placement rules refer
to roles with templates such as `{generated}/.gitkeep`, rather than repeating
physical names in Python policy tables.

Authoring JSON uses references such as `@samples/inaugural` and
`@examples/project.example.json`. File loaders resolve these to absolute paths
in the selected workspace. Ordinary relative media references keep their
existing document-relative meaning. Use `resolve_references` when loading these
configurations in another consumer; raw `json.loads` preserves the symbolic text.

## Change a layout

1. Edit the `[paths]` table in the manifest. Keep generated lanes disjoint and
   inside the generated root; keep tracked directories outside that boundary.
2. Move retained inputs if their roles changed. Regenerate or move local outputs
   as needed. Existing receipts remain records of their original layout.
3. Synchronize the derived Git and lint exclusions:

   ```bash
   python3 -m tools.verification.sync_layout --write
   ```

4. Run structure, lifecycle, edition, naming, and test checks. CI checks that the
   derived exclusions agree with the manifest.

Each command resolves the manifest when its process starts. A process that is
already running keeps its existing layout; use `load_layout` to construct a
separate layout explicitly. This is configuration-driven behavior, not automatic
filesystem watching or automatic relocation of existing files.

Python import namespaces and build metadata remain explicit software contracts.
Moving source packages also requires keeping the build configuration consistent;
changing output lanes does not require editing their consumers.

## Workspace and manifest selection

`SIMVLTANEA_ROOT` explicitly selects the workspace. Otherwise discovery checks
the package and current-directory ancestors for this project's `pyproject.toml`.
An installed package outside a checkout uses the current working directory,
with the bundled manifest as its default.

`[tool.simvltanea].layout` in `pyproject.toml` selects the repository manifest.
`SIMVLTANEA_LAYOUT` overrides it; a relative override resolves against the
selected workspace. The package includes the default manifest for installed use.

Layouts reject absolute role locations, traversal, symlink escapes, overlapping
generated lanes, and tracked directories overlapping local output. Explicit
output arguments still have to satisfy their command's containment rules.

Inventory reports preserve logical lane IDs for policy decisions and include a
`directory` field containing the configured generated-root-relative location.
Generated receipt paths use the configured locations as well.
