# SIMVLTANEA engine and runtime

This installable package contains the composition compiler, authoring model,
authored layouts, browser preview runtime, synthetic fixture generators, and
FFmpeg renderer.

| Module | Responsibility |
| --- | --- |
| `authoring/composition.py` | Strict state validation, frame resolution, and segment compilation |
| `authoring/composition_model.py` | Renderer-independent authoring datatypes |
| `authoring/artifact001_layouts.py` | Authored portrait and landscape layout pairs |
| `browser/browser_runtime.py` / `browser.runtime.js` | Bounded native-browser preview |
| `rendering/render_triptych.py` | Legacy and N-loop FFmpeg rendering |
| `make_*_fixture.py` | Synthetic engineering inputs under `var/proofs/` |
| `generators/make_artifact_001.py` | Artifact 001 output under `var/artifact-001/` |
| `paths.py` | Canonical repository, fixture, and generated-output locations |

Invoke package commands from the repository root with `PYTHONPATH=src`, or
install the project in editable mode.

Root package modules are compatibility entry points. New imports should use
the `authoring`, `browser`, `rendering`, and `generators` subpackages.
