# SIMVLTANEA Example Configurations (`examples/`)

This directory contains template and example project configuration files for SIMVLTANEA:

| File | Description |
| --- | --- |
| [`editions.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/editions.example.json) | Example multi-edition registry demonstrating configuration structures for named editions |
| [`project.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/project.example.json) | Example single-project composition configuration file |
| [`manifest.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/manifest.example.json) | Example historical triptych manifest configuration |
| [`slice-seam-config.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/slice-seam-config.json) | All seamed-slice knobs (slice width/height, seam width/mode/sigma, N) — every value configurable via JSON/CLI/manifest/project/edition/state |
| [`layouts.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/layouts.json) | Legacy count map of rect arrays, checked by `python -m tools.verification.verify_layouts --examples`; never read from inside the package |
| [`layout-presets/strips.json`](layout-presets/strips.json) | The default full-bleed strips preset (`simvltanea.layout-preset/1`); see [layout presets](../docs/authoring/LAYOUT_PRESETS.md) |

Configure everything: CLI flags (`--slice-width`, `--seam-mode`, `--config`), `manifest`/`project`/`editions` JSON, explicit layout files by path (`load_layout_file`, `--layouts FILE`), state JSON `slice`/`seam`, and browser plan (via preview). See `docs/architecture/SEAMED_SLICE_FIELD.md`.

Location references such as `@samples` and `@site/media` follow the configured
[layout](../docs/governance/LAYOUT.md); ordinary relative media paths retain
their document-relative meaning.
