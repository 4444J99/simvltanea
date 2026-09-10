# SIMVLTANEA Core Engine & Runtime (`core/`)

This directory contains the canonical multi-stream composition engine, strict compiler, authoring model, geometry layout definitions, browser runtime preview, and FFmpeg filtergraph renderers.

## Components

| Module | Description |
| --- | --- |
| [`composition.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/composition.py) | Canonical compiler, state validation, frame resolver, and segment generator (`visual-form-composition/v1`) |
| [`composition_model.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/composition_model.py) | High-level authoring datatypes (`CompositionModel`, `Loop`, `Layout`, `Placement`, `Event`, `HoldEvent`, `SwapEvent`, `RerollEvent`, `MoveEvent`) |
| [`artifact001_layouts.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/artifact001_layouts.py) | Authored engineering layout matrices for 3, 4, 5, and 6 simultaneous loops (portrait & landscape pairs) |
| [`browser_runtime.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/browser_runtime.py) | Headless browser execution harness and plan compiler for zero-drift client runtime |
| [`browser_runtime.js`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/browser_runtime.js) | Self-contained, zero-restart browser client engine (WebCrypto verified, keyed HTML5 video nodes) |
| [`browser_continuity_probe.js`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/browser_continuity_probe.js) | Playback continuity, DOM layout, and clock drift verification probe |
| [`render_triptych.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/render_triptych.py) | Production FFmpeg filtergraph video renderer (supporting legacy 3-panel and N-loop placements) |
| [`make_artifact_001.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/make_artifact_001.py) | Generator for synthetic Artifact 001 reference family |
| [`make_runtime_fixture.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/core/make_runtime_fixture.py) | Generator for labeled synthetic media fixtures and experimental N=7 study |
