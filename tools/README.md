# SIMVLTANEA operational commands

Commands are grouped by the workflow they serve. Run them as modules from the
repository root; this keeps imports stable and routes all generated output
through the shared `var/` boundary.

```bash
python3 -m tools.verification.verify_editions
python3 -m tools.editions.edition_status
python3 -m tools.publishing.build_site_index
```

## Workflow groups

- `editions/` builds, exports, inspects, and sketches editions.
- `media/` imports, catalogs, atomizes, selects, and synchronizes media.
- `publishing/` builds the static site, post packs, and distributable packages.
- `verification/` holds repository, edition, runtime, site, and package gates.
- `preservation/` holds provenance, inventory, excavation, checkpoint, and
  historical audit commands.

Reusable engine behavior belongs in `src/simvltanea/`, not in command modules.
Operational defaults come from `simvltanea.paths` through `tools.paths`; command
files must not derive output roots from their own location.

See [repository structure governance](../docs/STRUCTURE.md) and
[contributing](../CONTRIBUTING.md#verify-before-pr) for the enforced contract.
