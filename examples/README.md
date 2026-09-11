# SIMVLTANEA Example Configurations (`examples/`)

This directory contains template and example project configuration files for SIMVLTANEA:

| File | Description |
| --- | --- |
| [`editions.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/editions.example.json) | Example multi-edition registry demonstrating configuration structures for named editions |
| [`project.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/project.example.json) | Example single-project composition configuration file |
| [`manifest.example.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/manifest.example.json) | Example historical triptych manifest configuration |
| [`slice-seam-config.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/slice-seam-config.json) | All seamed-slice knobs (slice width/height, seam width/mode/sigma, N) — every value configurable via JSON/CLI/manifest/project/edition/state |
| [`layouts.json`](file:///Users/4jp/Workspace/4444J99/simvltanea/examples/layouts.json) | Example override for authored N=2..6 geometry — copy to `core/layouts.json` to customize (see `core/artifact001_layouts.py:12`) |

Configure everything: CLI flags (`--slice-width`, `--seam-mode`, `--config`), `manifest`/`project`/`editions` JSON, `core/layouts.json` layouts, state JSON `slice`/`seam`, and browser plan (via preview). See `docs/SEAMED_SLICE_FIELD.md`.
