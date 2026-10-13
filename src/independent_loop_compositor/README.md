# Independent Loop Compositor public API

Use this functional namespace for new consumers. The established `simvltanea`
package remains the implementation and import-compatibility path. No composition
engine, browser asset, or accepted shared-playback build is copied here.

```python
from independent_loop_compositor import Composition, LoopState, Layout, Placement
from independent_loop_compositor.browser import build_preview
```

```bash
python -m independent_loop_compositor preview --help
python -m independent_loop_compositor render --help
```

The installed `independent-loop-compositor` command offers the same subcommands.
Composition ids and literal source identifiers are caller data. Artwork titles
and edition slugs belong to the registries, never to this package's identity.
See [identity migration](../../docs/governance/IDENTITY_MIGRATION.md).
