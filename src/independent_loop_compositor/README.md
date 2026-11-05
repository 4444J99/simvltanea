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
python -m independent_loop_compositor doctor
python -m independent_loop_compositor --version
```

`doctor` checks Python 3.12+, `ffmpeg` and `ffprobe` on `PATH`, the `libx264` and
`aac` encoders, and that the workspace `var/` directory is writable. It also
reports whether the optional shared engine is available, without failing on it.
Use `doctor --json` for machine-readable output; the exit code is 1 when a
required check fails.

Expected failures print one line, `independent-loop-compositor: error: <message>`,
and exit 1. Set `SIMVLTANEA_DEBUG=1` to get the full traceback instead.

The installed `independent-loop-compositor` command offers the same subcommands.
Composition ids and literal source identifiers are caller data. Artwork titles
and edition slugs belong to the registries, never to this package's identity.
See [identity migration](../../docs/governance/IDENTITY_MIGRATION.md).
