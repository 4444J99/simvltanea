# Final execution receipt — Visual Form Canon

## Repository closeout

Repository: organvm/portvs
Branch: work/n-loop-paired-compositions-2026-09-05
Final head: 00d3788260e1b8d3d76cf030dd9b69418059101b
Reconciled start: 042cbe555f9f1d73aa92968cf427bcf830ee6929
Main unchanged: 48da3da293ecd7604b6c9d3ce19d0bf49a70013d
PR #9: open, draft, unmerged; eight commits and 23 changed files across the whole PR.
This tranche: two commits, 12 changed paths, zero commits behind its reconciled start.
PR #7: open/draft/unmerged, unchanged at 5c2f29ef3b427cc42de6949aee087da5bbf7004c.
Issue #8: remains open; execution comment 5556494965 added.
PR #9 title/body updated with current evidence and explicit remaining boundaries.

Commits created:
- 186decc3c6987ab9e2fb2e03f6d3507cfc3b0e83 — native playback, portable media, labeled fixtures and tests.
- 00d3788260e1b8d3d76cf030dd9b69418059101b — decoded-pixel verification, portable-state reproduction, execution/canon records.

Changed paths, all relative to incubator/triptych-video-canon/:
- browser_runtime.py (new)
- browser_runtime.js (new)
- make_runtime_fixture.py (new)
- test_browser_runtime.py (new)
- render_runtime_family.py (new)
- verify_runtime_renders.py (new)
- requirements-runtime-proof.txt (new)
- .gitignore (modified)
- RUNTIME_RECEIPT.md (new)
- VISUAL_FORM_CANON.md (append-only update)
- INCUBATION.md (current entry point)
- INCUBATION_PRE_N_LOOP.md (unchanged prior notes preserved as the same Git blob)

Existing composition_model.py, composition.py and render_triptych.py were not
changed by this tranche. Their exact source blobs were checked in the execution
snapshot. The snapshot is not a full clone: the required git-status command ran
and returned exit 128, not a fabricated clean-worktree result. Remote comparison
confirmed the two-commit fast-forward and scoped changes.

## Completed, partial, blocked and lower-priority work

Completed: baseline/core regression execution; bounded native-browser runtime;
portable media/state integrity; original moving labeled bank; full 3–6 paired
reference family; labeled 3–7 paired family; experimental seven-loop rendering
and native continuity; byte-identical seven-loop portable replay; sampled visual
inspection; decoded pixel identity/motion verification; repository evidence and
coordination updates; synthetic-only delivery integrity verification.

Partially completed: browser/runtime surface (native foreground finite playback
verified; served loading, real devices, indefinite/background playback and live
interactive authoring unverified); practical resource understanding (explicit
guards and narrow measured runs, not a capacity benchmark); historical recovery
(locators and limited connector-extracted text, not original-byte reconstruction).

Blocked: HTTP navigation by environment policy; historical raw-byte transfer;
physical target-device access; hosted CodeQL diagnostic availability. Hosted
run 34007708720 / job 101417856302 failed with no recorded steps or assigned
runner; logs returned 404 BlobNotFound. Root cause remains unresolved. CodeRabbit
reported success, but this is not a hosted-CI-green result.

Not attempted because lower priority or outside the bounded proof: final artist
designs, additional N beyond seven, comprehensive performance stress testing,
live-authoring/audience UI, generative audio/routing integration, opacity/blend/
mask/nesting implementation, Ableton/Max integrations and unrelated websites.
No release, merge, deployment, historical-original mutation or public artwork
publication was performed; those are authorization boundaries, not completion.

## Delivered bundles

- Visual_Form_Canon_execution_2026-09-05.zip: 102915438 bytes; SHA-256 dd3ad083009feae455a3205c3b39e0028feae970dd722aa135a336799d9ef7d0
- Visual_Form_Canon_labeled_review_2026-09-05.zip: 4801959 bytes; SHA-256 d136d5c2698b73b86f8dbacb8c06fdc666470179108c3696beba1e79e067bc84
- Visual_Form_Canon_SHA256SUMS.json: 63811 bytes; SHA-256 1c28b457cb73989e7006ef4b3722dff9c59cd2103b3f4da5b12dcaae25e0b17f

All 298 files listed in the full bundle manifest were read back and hash-verified. No fonts or private archival media are included.

# N-loop runtime execution receipt — 2026-09-05

Scope: `organvm/portvs`, `incubator/triptych-video-canon/`, issue #8, draft PR #9.
Reconciled start: `042cbe555f9f1d73aa92968cf427bcf830ee6929`, not the handoff's older SHA.
Browser implementation commit: `186decc3c6987ab9e2fb2e03f6d3507cfc3b0e83`.
Main was `48da3da293ecd7604b6c9d3ce19d0bf49a70013d`; audit PR #7 remains separate.
No merge, public release, deployment, social post or archive mutation occurred.

## Executed result

The authoritative normalized compiler still feeds the existing Triptych FFmpeg
renderer. This tranche added a bounded native-media browser consumer, not a
second source-selection engine or per-count application. Python resolves every
frame into independent loop spans and separate layout keyframes. ResizeObserver
changes presentation geometry without assigning sources, seeking, or replacing
video elements. Preview media are copied by content hash and checked before
mounting; the copied state refers to those actual copied bytes.

The original 3–6 engineering family was regenerated at full reference resolution.
A labeled contain-study family adds explicit identity/time/progress markers for
3–6 and an independently authored experimental seven-loop pair. Both seven-loop
exports reproduce byte-for-byte from their portable preview state. No final
geometry or artwork approval is implied.

## Environment and execution scope

Observed: Python 3.13.5, FFmpeg 7.1.5-0+deb13u1, Chromium 144.0.7559.96,
Pillow 12.3.0 and Python Playwright 1.57.0. Existing Chromium was used; no browser
was downloaded. DejaVu fonts are local generation prerequisites, not bundled files.

Execution used a scoped source snapshot verified against Git blob hashes, not a
full Git checkout. Network cloning was unavailable. Remote writes used the
existing branch, parented commits and non-forced ref updates. A local Git-clean
or whole-repository test claim is therefore not made.

HTTP navigation failed with `ERR_BLOCKED_BY_ADMINISTRATOR` before application
loading. That policy was not changed. Native browser tests instead used explicit
`PORTVS_BROWSER_TRANSPORT=in-memory`: local file bytes supplied to about:blank,
with genuine Chromium video decoding, DOM, playback clocks and decoded-frame
callbacks. Only plan/media IO and its digest function were injected. The default
HTTP/WebCrypto path is implemented but was not verified in this environment.

## Tests actually executed

| Final command group | Passed | Failed/errors | Skipped |
| --- | ---: | ---: | ---: |
| Original model, authoring contract, renderer and browser PlanTests | 55 | 0 | 0 |
| Browser N=3/4/5 plus container-only resize | 4 | 0 | 0 |
| Browser N=6/7, corrupt-media rejection, loading-time resize | 4 | 0 | 0 |
| Native control sequence and trim-wrap sequence | 2 | 0 | 0 |
| Total distinct unittest tests | 65 | 0 | 0 |

The first 46 tests were rerun before new implementation. The final 65 comprise
those 46 plus nine compilation/export contract tests and ten browser tests.
The renderer suite includes 360 legacy segment-command comparisons inside a
single unittest and a real decoded-frame still/hold render; these are not 360
additional unittest cases. Five full historical-renderer output regressions from
the previous tranche were not newly rerun here. No whole-site or hosted-CI pass
is inferred from these narrow tests.

Final logs are `final-model-render-plan-tests.log`, `final-browser-a.log`,
`final-browser-b.log`, and `final-browser-c.log` in the delivery evidence folder.
An initial HTTP run errored, an earlier full browser invocation timed out,
and a misspelled test-method invocation failed. Those are not counted as passing
runs. Final execution used bounded completed shards.

Actual defects repaired: resize while media was still loading; acceptance of an
unverified browser container; and portable state retaining stale media paths.
The browser preview now explicitly accepts verified 8-bit yuv420p H.264 MP4 for
video, rather than implying support for every FFmpeg-readable container.

## Reproduction commands

Run from this incubator with the observed prerequisites installed:

```bash
python3 make_artifact_001.py --prepare-only
python3 -m unittest -v test_composition_model.py test_authoring_contract.py test_composition_render.py
python3 make_artifact_001.py
python3 make_runtime_fixture.py
python3 render_runtime_family.py
python3 verify_runtime_renders.py
PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest -v test_browser_runtime.PlanTests
```

The browser tests were run in these bounded groups:

```bash
PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest -v \
  test_browser_runtime.BrowserTests.test_3_loop_native_continuity \
  test_browser_runtime.BrowserTests.test_4_loop_native_continuity \
  test_browser_runtime.BrowserTests.test_5_loop_native_continuity \
  test_browser_runtime.BrowserTests.test_container_resize_without_viewport_change
PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest -v \
  test_browser_runtime.BrowserTests.test_6_loop_native_continuity \
  test_browser_runtime.BrowserTests.test_7_loop_experimental_continuity \
  test_browser_runtime.BrowserTests.test_browser_rejects_altered_media_before_mounting \
  test_browser_runtime.BrowserTests.test_resize_while_media_is_loading
PORTVS_BROWSER_TRANSPORT=in-memory python3 -m unittest -v \
  test_browser_runtime.BrowserTests.test_native_controls_hold_release_swap_reroll_move \
  test_browser_runtime.BrowserTests.test_native_trim_loop_boundaries
```

`render_runtime_family.py` is an orchestration wrapper around the existing CLI.
For example, its seven-loop portrait command is:

```bash
python3 render_triptych.py --state runtime-proof/state-7.json \
  --orientation portrait --width 360 --height 640 --preset ultrafast --crf 18 \
  --output runtime-proof/renders/labeled-7-portrait.mp4
```

The portable reproduction uses `runtime-proof/preview-7/state.json` with identical
render options. Exact commands, source hashes, state files, probe facts, output
hashes and still hashes are retained in the generated delivery bundle:
`artifact-001/evidence/renders.json`, `runtime-proof/sources.json`,
`runtime-proof/evidence/render-family.json`, and
`runtime-proof/evidence/portable-reproduction.json`.

## Moving outputs and visual evidence

Nine reference exports were produced: eight 3/4/5/6 orientation exports plus one
still/video/control export. Each is six seconds, 24 fps, 144 frames; portrait is
1080x1920 and landscape is 1920x1080. Nine reference PNGs accompany them.

Ten labeled family exports cover 3/4/5/6/7, both orientations. Each is six seconds,
24 fps, 144 frames; portrait is 360x640 and landscape is 640x360. Each has sampled
PNGs at frames 12, 48 and 120. The seven-loop pair additionally has two identical
portable-state re-renders. New normalized outputs are silent.

| Labeled export | SHA-256 |
| --- | --- |
| 3 portrait | e0222027bab8301b94862ad6242ef476b856309355998e9d4f13c354012467ff |
| 3 landscape | 21e61328b0a36b75f188d12c64efc17189c69b844b857f324da7d42fd9a205a9 |
| 4 portrait | 7cf8a97f9426a8c933ec6b256522537dc1d2d2819f0cdac369147e52e8fe9a9d |
| 4 landscape | 62a929c9a835649c403d8de69c74843ecd62199ef27baae92e287e257a36e009 |
| 5 portrait | 56729dba558e4366c69e9e1db5e9374bf9c5b48f2fff612640a19952db070384 |
| 5 landscape | 22ae74f323c6aa01fe71ce93077214edd7271bd2dd59061c2589b003e98572ba |
| 6 portrait | 6de21c9fd72c8adf07324432aa33bfb8176d984590135fed0da8c279fb5c9a24 |
| 6 landscape | 66be3d4cf85ea16fe12ffcd33a87a96969ebec60c2ab1d4f73fcc9fad76ab6ed |
| 7 portrait | a5b117f704863d27e6db7bf30f40c70a9ad0cda84bb74b121c48541f5a4d6f46 |
| 7 landscape | 3f7dad91e3313541744231b16559733e45c4c34b7787d3e05d3de6b04c3d924e |

Sampled-frame visual inspection covered all eight reference geometries, all ten
labeled geometries, every browser count's viewport changes and the control
sequence. Distinct source markers remain visible, clocks advance, contain-study
borders are retained, and the authored hierarchy differs between orientations.
Reference cover layouts intentionally crop source patterns; labeled contain
layouts intentionally expose the full square source. These are different named
engineering studies, not one silently altered arrangement.

`verify_runtime_renders.py` separately decoded 30 actual video frames and checked
150 visible-loop observations against the source bank. All 100 between-sample
motion comparisons passed; the minimum changed-pixel fraction was 0.0254153 above
an RGB-noise threshold of 20. Thirty blank/wrong-source/frozen negative controls
were rejected. This fixture-specific color/motion check is not OCR, exact temporal
frame matching, continuous human viewing or historical-media verification.

## Runtime continuity and resource limits

Each count 3–7 passed advancing viewport changes:
390x844 -> 1280x720 -> 900x1300 -> 844x390 -> 390x844.
A separate test held the browser at 1600x1000 and resized only the container:
390x844 -> 844x390 -> 450x900. Tall desktop and horizontal mobile-like shapes use
their actual dimensions. The same loop IDs, source selections, DOM video objects,
and decoded progression survive; resize caused no source load or playback seek.

The maximum sampled model/currentTime discrepancy across the final continuity
runs was 0.070275 seconds. One four-loop checkpoint reported one dropped frame;
other sampled runs reported zero. These measurements do not establish zero-drop,
frame-exact, background-tab, indefinite, mobile or hardware-capacity guarantees.

Native controls demonstrate targeted hold with other loops advancing, release
continuity, an actual changed-source reroll, a swap consistent with persistent
local clocks, and a presentation-only move. A one-second trim interval wraps
only its target loop. Controls are compiled events, not a finished live-authoring
or audience-control interface.

Current normalized guards include at most 32 loops, 14,400 frames and 1,024
segments, with a 4K-pixel export guard and 256 MiB browser-media guard. These are
explicit resource limits, not measured ceilings or claims that every allowed
count has authored layouts. Only the proven families are advertised. A missing
pair fails; no silent grid, count reduction or media filler is introduced.

## Historical inspection and unresolved gates

| Source class | This tranche's evidence | Still unresolved |
| --- | --- | --- |
| Up the Hill Backwards | MP4 locator and provider download metadata; a candidate Premiere project's connector-extracted text was read | Raw video/project bytes, file SHA-256, signature, exact source identity, sampled visual topology and timing. Quad remains artist-attested. |
| Floating Points | Fresh V1 and V3 project locators; V1 metadata/download attempts failed with unsupported-type/not-found errors | Original bytes and hashes, real XML/object graph, sequences/tracks/layers/masks/geometry/blends/dependencies. Prior extracted-text findings are not new graph evidence. |
| TripTicks | MOV locator re-found | Bytes, playback, MOV/MP4 equivalence and relationship to selector/First Circle/current renderer. |
| First Circle | Bounded title search did not resolve the implementation | Absence is not established; earlier-selector identity remains open. |
| Narcissus | Bounded audiovisual-extension search returned no match; broader stem search found similarly named PDFs | Audiovisual source identity remains open. PDFs and unrelated matches were not treated as the artwork. |

The Up the Hill Backwards link resolved, but the transfer tool did not deliver
bytes into the execution environment. No provider content-hash was relabeled as
an ordinary file SHA-256. No signed URL, private archive path or raw archive media
is committed or placed in the synthetic deliverable. No historical compatibility
fixture was invented from sequence names or artist testimony alone.

## Next exact external gates

Run the same browser tests with the default HTTP transport in an environment
where local navigation is allowed; then test actual target devices. This is not
a request to deploy or bypass the present policy. Separately, retrieve one
already-located archival original through a working authorized byte-transfer
route, hash/signature-check it and inspect structure or representative frames.
Neither gate requires restarting the composition-engine work.

Audio remains separate: legacy renderer behavior was retained and its command
compatibility checked. New normalized output and browser preview remain silent.
Ableton, Max for Live, Max/MSP, Alchemical Synthesizer and external modulation
would connect through explicit routing/state/event adapters; none was built or
claimed operational. Artist review, live controls, generative audio, overlap,
masking, dense nesting and public release remain outside the completed proof.

## Full-reference export SHA-256 values

| Export | Dimensions | Frames | Duration | SHA-256 |
| --- | --- | ---: | --- | --- |
| renders/state-3-portrait.mp4 | 1080x1920 | 144 | 6.000000 s | 61d1c7adc9d4924346d190f5060631a07e1ceacea66f8d0f0fcf456a6d935bf4 |
| renders/state-3-landscape.mp4 | 1920x1080 | 144 | 6.000000 s | 124b3e9dcc30f82b774aa9078eb6c032a88d5f24df9533cfed58a5639bd9bb5b |
| renders/state-4-portrait.mp4 | 1080x1920 | 144 | 6.000000 s | 0b66133134684db86ee233145b94f41c900fa9fdb0efa3a437e8fea4c9e83870 |
| renders/state-4-landscape.mp4 | 1920x1080 | 144 | 6.000000 s | 8fa491c003ba6de1cb0014ce8d56755cadb2ff29f4e7d2d4b771ebd023095896 |
| renders/state-5-portrait.mp4 | 1080x1920 | 144 | 6.000000 s | c58118272553a01dac568716776d28a95b19f7c3b2f6995f6fe942f4a6e485f0 |
| renders/state-5-landscape.mp4 | 1920x1080 | 144 | 6.000000 s | 2492fc13b38ebf79ed855a2a6fe79679ff51bffcc9d9389a774cff3b69506190 |
| renders/state-6-portrait.mp4 | 1080x1920 | 144 | 6.000000 s | 9cf295a85a106af805fba8ad732cc3141c0746c9820331305de69681d5a6420a |
| renders/state-6-landscape.mp4 | 1920x1080 | 144 | 6.000000 s | 4bc233cd103e4b902abe8e3bc794db6991dcc364fb34eb9d9a39b5ccaba7ac8d |
| renders/state-still-controls-portrait.mp4 | 1080x1920 | 144 | 6.000000 s | fa2f6dc5ce64380889cf8973e16e7a3e1a67964f68263b53455eb5a72369d613 |

## Next exact executable gate

In an environment where local HTTP navigation is allowed, execute the same
browser test shards with PORTVS_BROWSER_TRANSPORT=http, starting with
`python3 -m unittest -v test_browser_runtime.BrowserTests.test_3_loop_native_continuity`.
Do not change or bypass the present navigation policy. The independent historical
gate is retrieval of one already-located original, followed immediately by a
real file SHA-256/signature check and structural parsing or representative-frame
inspection. Artist approval and release remain separate decisions.
