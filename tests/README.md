# SIMVLTANEA Test Suite

This directory contains SIMVLTANEA's unit, media, browser, provenance, and
repository-governance verification suite. Test discovery includes these modules:

| Test Module | Coverage / Area |
| --- | --- |
| [`test_authoring_contract.py`](model/test_authoring_contract.py) | Schema validation, invariant enforcement, loop parameter bounds |
| [`test_composition_model.py`](model/test_composition_model.py) | Relational composition model, spatial coordinates, loop geometry |
| [`test_composition_render.py`](render/test_composition_render.py) | FFmpeg filtergraph rendering, multi-stream compilation, frame resolution |
| [`test_review_proof.py`](governance/test_review_proof.py) | Export package verification, review readiness, proof assertions |
| [`test_browser_runtime.py`](browser/test_browser_runtime.py) | Playwright / Headless Chrome runtime simulation, DOM bindings |
| [`test_browser_boundaries.py`](browser/test_browser_boundaries.py) | Edge-case browser boundaries, aspect ratio handling, viewport resizing |
| [`test_browser_continuity.py`](browser/test_browser_continuity.py) | Loop playback continuity, drift prevention, synchronization across reorientation |
| [`test_audio_editions.py`](editions/test_audio_editions.py) | Audio edition declarations and historical-exporter boundaries |
| [`test_audio_model.py`](model/test_audio_model.py) | Audio v1.1 authoring, rational clocks, and verified media bindings |
| [`test_audio_render.py`](render/test_audio_render.py) | Decoded synthetic-tone evidence for soundtrack and spatial audio |
| [`test_browser_audio.py`](browser/test_browser_audio.py) | Verified audio plans and native Web Audio signal behavior |
| [`test_archive_media_provenance.py`](governance/test_archive_media_provenance.py) | Retained media checksums, stream metadata, decoding, and portable manifest links |
| [`test_inaugural_fixture.py`](editions/test_inaugural_fixture.py) | Clean-clone synthetic fixture generation, decodability, and output boundaries |
| [`test_repository_structure.py`](governance/test_repository_structure.py) | Required paths, placement rules, generated boundaries, Git states, and lifecycle checks |

## Running Tests

Run with unittest:

```bash
python3 -m unittest discover -s tests
```

Or run with pytest:

```bash
pytest
```

CI also runs naming, repository-structure, changed-Markdown, and lifecycle
gates. See [Contributing](../.github/CONTRIBUTING.md#verify-before-pr) for pinned tools,
local verification commands, and the generated-output policy.

Tests are grouped into `model/`, `browser/`, `render/`, `editions/`, and
`governance/`. Select a suite with `pytest tests/browser` or a unittest module
with `python3 -m unittest tests.browser.test_browser_runtime`.
