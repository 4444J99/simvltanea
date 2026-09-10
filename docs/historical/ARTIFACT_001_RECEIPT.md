# Artifact 001 — executed synthetic composition proof

Date: 2026-09-05 America/New_York (execution timestamps extend into 2026-09-06 UTC).
Coordination: issue #8. Implementation: draft PR #9, branch `work/n-loop-paired-compositions-2026-09-05`. Audit corrections remain in PR #7. Neither PR is authorized to merge automatically.

## Exact starting points

The inherited renderer was reconstructed from main `48da3da293ecd7604b6c9d3ce19d0bf49a70013d`; its bytes match Git blob `6155fa1b8c9d5284c3deda0eaf56b342e47cf1bc`. A sparse execution directory, not a complete Git checkout, was used because direct network access failed. The original snapshot is retained solely as a regression fixture under `artifact-001/baseline/`.

Concurrent authoring PR #9 was discovered at `74d21760a9c8ceb074ff4445724facea15c1c992` and reused, not replaced. Its `composition_model.py`, `artifact001_layouts.py` and `test_composition_model.py` are unchanged. `composition.py` adapts its initial, resolved-source geometry and clocks to schema 1 / engine 1.0.0. Old implicit random selection and already-applied 0.1.0 event histories are NOT silently translated.

Executed source blob identities:

| File | Git blob SHA |
|---|---|
| render_triptych.py | 864d3037491f7bb0224c4e15b128ca0dbf7874cd |
| composition.py | 8aee4771ec9e4bee7f724b6b42df0da89fc216db |
| make_artifact_001.py | dd2213fc3dae448de3f9e8f7a6ce312c27de20a3 |
| test_composition_render.py | c1134e70a0466bdab6b9f5e84b045e4fc4097b42 |

## Executed results

Eight reference compositions: 3, 4, 5 and 6 distinct video sources, each with an explicit portrait and landscape layout. Every reference MP4 is H.264, 24 fps, 144 frames and 6.000000 seconds. Portrait is 1080x1920; landscape is 1920x1080. Each has an extracted PNG at two seconds. A ninth portrait fixture exercises a still alongside video and hold/release/reroll/swap/move events.

These are synthetic engineering demonstrations, not recovered historical artworks or artist-approved designs. Exported images contain no controls/proof chrome. Inspection sheets are separate QA records. All eight layouts and sampled control transitions were visually inspected; the integration test also measures frozen versus moving decoded regions. No browser, iOS playback, live orientation switch, deployment or public release is claimed.

| MP4 basename | SHA-256 |
|---|---|
| state-3-portrait.mp4 | 61d1c7adc9d4924346d190f5060631a07e1ceacea66f8d0f0fcf456a6d935bf4 |
| state-3-landscape.mp4 | 124b3e9dcc30f82b774aa9078eb6c032a88d5f24df9533cfed58a5639bd9bb5b |
| state-4-portrait.mp4 | 0b66133134684db86ee233145b94f41c900fa9fdb0efa3a437e8fea4c9e83870 |
| state-4-landscape.mp4 | 8fa491c003ba6de1cb0014ce8d56755cadb2ff29f4e7d2d4b771ebd023095896 |
| state-5-portrait.mp4 | c58118272553a01dac568716776d28a95b19f7c3b2f6995f6fe942f4a6e485f0 |
| state-5-landscape.mp4 | 2492fc13b38ebf79ed855a2a6fe79679ff51bffcc9d9389a774cff3b69506190 |
| state-6-portrait.mp4 | 9cf295a85a106af805fba8ad732cc3141c0746c9820331305de69681d5a6420a |
| state-6-landscape.mp4 | 4bc233cd103e4b902abe8e3bc794db6991dcc364fb34eb9d9a39b5ccaba7ac8d |
| state-still-controls-portrait.mp4 | fa2f6dc5ce64380889cf8973e16e7a3e1a67964f68263b53455eb5a72369d613 |

## Baseline and tests

Python 3.13.5 and FFmpeg/ffprobe 7.1.5-0+deb13u1 were used. No third-party Python package is needed for rendering or these tests. FFmpeg must include libx264, AAC, lavfi and the filters invoked in the recorded commands.

`python -m unittest -v test_composition_model.py test_composition_render.py` passed all 38 tests, with no skips, in 5.198 seconds in the recorded run. This is a narrow suite, not the complete repository's test/verification suite. Initial unittest discovery in the sparse original renderer directory found zero tests; this does not mean the repository has no tests. Existing private/public website and export-project verification scripts were not executed.

The command-graph regression compares 360 original/modified segment commands across both timing modes, four story/reel selections, three audio modes, three playback directions and reordered panels. Five complete legacy renders were also repeated; all decoded video hashes, and audio hashes where present, matched the original baseline exactly.

Original baseline facts: clip-none and fixed-none are 120 frames / 5 seconds. Clip-panel and clip-mix are 120 frames with AAC and container duration 5.021333 seconds. Fixed-mix has an inherited quirk: 123 frames and container duration 5.145996 seconds for a nominal five-second schedule. That behavior is preserved, not fixed or concealed. The baseline demonstrates entry order, fixed source offsets, clip-timed filled rounds and end wraparound.

## Reproduce

Run these commands from `incubator/triptych-video-canon/`, either in the implementation branch or the delivered execution bundle:

```sh
python make_artifact_001.py --prepare-only
python -m unittest -v test_composition_model.py test_composition_render.py
python make_artifact_001.py
```

The generator writes/replaces only its synthetic fixtures and results under `artifact-001/`; do not keep authored work in that generated namespace. The baseline source snapshot and manifest are versioned regression fixtures. Generated media, renders and logs are ignored by Git and supplied in the execution bundle, not published from the repository.

To replay one saved state without regenerating it:

```sh
python render_triptych.py --state artifact-001/state-4.json \
  --orientation landscape --output artifact-001/renders/replay-4-landscape.mp4 \
  --preset ultrafast --crf 20
```

The bundle contains the exact source media, hashes, initial authoring snapshots, executable states, test logs, baseline logs and output probes. Full render commands/probes/PNG hashes are in `artifact-001/evidence/renders.json`; decoded legacy comparisons in `legacy-regression.json`; toolchain and code identities in their corresponding evidence files. The source manifest is `artifact-001/sources.json`.

Deterministic source/state replay is distinct from byte-identical encoding across different toolchains. Regenerating synthetic source media on another encoder may change its bytes and hashes. Retain the supplied sources when replaying the supplied state.

## State/control contract and deliberate limits

Time is rational and evaluated at integer output frames. Selection uses `sha256-counter-v1` over seed, loop ID, epoch, local selection cycle and ordered bank. Evaluation order of unrelated loops does not change choices. Layout cells do not own clocks. Orientation mapping preserves all loops and their current content; live browser continuity remains untested.

Hold freezes local time and automatic selection; release resumes without catch-up. Reroll increments only the target epoch and clears its source override without resetting time; it may select the same source again. Swap exchanges and pins current source identities, not clocks, banks or geometry; reroll clears the pin. Move changes one orientation's rectangle without changing content/time. Same-frame events execute in array order and are saved for replay. Stills have explicit positive durations and display a constant frame while selected.

The existing legacy CLI retains none/panel/mix audio and existing effects. Schema-1 loop exports are deliberately silent; non-none audio/routing/generative requests fail clearly. Overlap, masks, depth, alpha blending and generative audio are not implemented. Frame/segment/pixel/loop guards are resource guards, not measured hardware playback capacity.

## Historical evidence and executor boundary

Floating Points V1 advanced from a known locator to inspected connector-extracted project text: sequence labels including `floating_points_V1_SEQ`, dependency references and `AE.ADBE Opacity` identifiers are present. This flattened text is not raw-project structural parsing. No original-byte hash, track/layer count, geometry, blend configuration, masks, keyframe graph, complete dependency set or Premiere playback has been verified. The V1 temporary-download request failed with NOT_FOUND; metadata lookup rejected its file type; text extraction succeeded separately.

The located Up the Hill Backwards MP4 resolved through Dropbox metadata/download-link generation, but byte retrieval failed in the execution environment. No representative frames or historical quad topology were verified. TripTicks, the earlier First Circle/photo selector, later video canon and conceptual records remain distinct. Narcissus audiovisual identity is unresolved; the similarly named PDF is not assumed related. Danse was not imported or behaviorally revalidated. The lineage remains a provisional network, not a proven chronological chain. Private identifiers, paths and temporary links are intentionally absent here.

No new coding agent was dispatched. Existing Copilot run 33995118520/job 101384202095 was observed failed with no recorded steps/runner; billing/quota was not established as its cause. This proof was executed directly in the active environment. Issue #8 remains open for historical recovery and the additional live-browser gates. The next historical blocking gate is actual source-byte retrieval for a bounded structural/video-frame inspection, not access to the user's Mac.
