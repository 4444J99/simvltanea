# Python imports and full verification

Replace dynamic feature exports with ordinary imports, remove test-local path
mutation, use pytest importlib discovery, retain one historical unittest hook,
and include all existing root tests. Heal FFmpeg audio filtergraph compatibility
and align the independent continuity oracle with per-media observation times.
Retain timing tolerances and negative controls. Preserve legacy output before
relocating it under the configured generated lane. Validate the complete suite,
package build, structure, and layout checks; update PR 20 with measured results.

## Legacy output custody

Relocated 458 untracked generated files (154870734 bytes)
from the five legacy root lanes into `var/work/legacy-layout-20261002/`.
No source lanes were tracked and no open files were reported by lsof.
Every file was SHA-256 verified before and after relocation. The preserved
manifest is `var/work/legacy-layout-20261002/manifest.json`, SHA-256
`7d8a575878629231bb01e50ef8f958e65efcad50d2bddc2c0399b43191b5ec92`.

## Reconciled concurrent declarations

Photos edition and handoff commits landed during verification. The simvl-live
edition now declares its existing simultaneous-field family and panel role.
Edition validation retains portable role strings while separately checking role
resolution; tests identify inaugural by slug instead of registry order.
Continuation Markdown and the exact PR-20 JSON receipt are declared in the
layout contract. Arbitrary JSON remains rejected.

## Final verification

- Fresh detached checkout, editable install in a temporary environment inheriting
  the host verification dependencies; no existing output fixtures were copied.
- `python -m unittest discover -s tests -v`: 217 tests, exit 0, no skips;
  implementation head `4df57d1`, 155.601 seconds.
- `python -m pytest -q`: 217 tests and 292 subtests passed, exit 0;
  implementation head `2582a44`, 116.44 seconds.
- Naming, changed Markdown, repository structure, feature boundaries, edition
  presets, layout synchronization, example layouts, and local lifecycle passed.
- Wheel build succeeded; both browser assets and the layout contract are present.
- Runtime and clock tolerances were retained; the oracle's new unit regressions
  distinguish pixel-capture delay from actual media-clock drift.
- The initial local full run's audio and continuity failures were healed. Its
  remaining registry/order/receipt failures were reconciled before the fresh run.
- Verification checkout retained at
  `/var/folders/l9/zn9x070d4xqb1qb5wfzr9tjr0000gn/T/simvltanea-polish-check-lipfn1fa`;
  environment retained at `/tmp/simvltanea-polish-venv`.
- Root Finder metadata was also preserved as
  `var/work/legacy-layout-20261002/root.DS_Store`, SHA-256
  `3e58fb908ae6417d542b2d058afabc444f5de4a01c9fd0d09a745f64dcc7ed73`.
- These are local code-verification results. No merge, remote CI acceptance,
  Photos custody completion, full-album export, or historical-media acceptance
  is represented by this verification.
