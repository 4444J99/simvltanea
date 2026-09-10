# SIMVLTANEA Test Suite

This directory contains the complete verification suite for SIMVLTANEA (120 tests across 7 modules):

| Test Module | Coverage / Area |
| --- | --- |
| [`test_authoring_contract.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_authoring_contract.py) | Schema validation, invariant enforcement, loop parameter bounds |
| [`test_composition_model.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_composition_model.py) | Relational composition model, spatial coordinates, loop geometry |
| [`test_composition_render.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_composition_render.py) | FFmpeg filtergraph rendering, multi-stream compilation, frame resolution |
| [`test_review_proof.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_review_proof.py) | Export package verification, review readiness, proof assertions |
| [`test_browser_runtime.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_browser_runtime.py) | Playwright / Headless Chrome runtime simulation, DOM bindings |
| [`test_browser_boundaries.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_browser_boundaries.py) | Edge-case browser boundaries, aspect ratio handling, viewport resizing |
| [`test_browser_continuity.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tests/test_browser_continuity.py) | Loop playback continuity, drift prevention, synchronization across reorientation |

## Running Tests

Run with unittest:
```bash
python3 -m unittest discover -s tests
```

Or run with pytest:
```bash
pytest
```
