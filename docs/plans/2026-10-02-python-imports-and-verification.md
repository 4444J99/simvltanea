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
