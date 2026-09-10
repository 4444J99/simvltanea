# HANDOFF ADDENDUM — N Video Loops × Portrait/Landscape Compositions

Date: September 5, 2026 (America/New_York)
Canonical coordination: https://github.com/organvm/portvs/issues/8
Implementation boundary: `organvm/portvs/incubator/triptych-video-canon/`
Related audit PR: https://github.com/organvm/portvs/pull/7

Append this to the previous “Visual Form Canon: Located Sources → Common Composition Engine → Artifact 001” handoff. This supersedes its narrower three-panel/four-panel-only completion gate. Preserve the previous handoff’s other evidence, privacy, compatibility and mutation boundaries.

## Governing artist clarification

“Each arrangement of 3, 4, 5, 6, etc panels (adding panels for this particular project adds a new video loop (that’s what the project essentially is)) needs to be designed both vertically and horizontally (mobile & desktop).”

The fundamental unit is an independent video loop, not a decorative rectangle. For this project, N panels contain N independent video-loop instances. Increasing the panel count adds another loop instance. Do not substitute empty tiles, mirrored viewports, or automatically duplicated filler clips. Deliberate reuse of a source file is different from silently reusing the same loop instance.

## Separate content and time from presentation

A composition owns stable loop IDs, sources, trim/loop bounds, rates, offsets, selection seeds and event state. Its paired layouts own geometry, ordering, spacing, aspect/fit/crop decisions and focal points.

Every supported count and every named arrangement variant must have both an authored portrait layout and an authored landscape layout. Implement both through the same engine and schema, not separate applications. A generic grid generator is not evidence of completed visual design. Equal panels, unequal panels, hierarchy, overlap and negative space remain design choices, not preapproved requirements.

Both orientations must show the same loop instances and temporal state. Rotation or resize must not restart playback, reroll sources, reset clocks, duplicate loops or drop panels. Normal clock progression continues through an orientation change. Adding/removing a loop must not inadvertently restart the surviving loops.

Select the interactive layout from actual viewport/container dimensions and orientation; do not equate “phone” permanently with portrait or “desktop” permanently with landscape. Select export orientation explicitly. Keep the audio mix independent of orientation; adding a video panel does not implicitly enable another audible source.

## First acceptance matrix

| Independent loops / panels | Portrait composition | Landscape composition |
|---|---|---|
| 3 | Required | Required |
| 4 | Required | Required |
| 5 | Required | Required |
| 6 | Required | Required |
| Every later supported N | Required | Required |

The first four counts require at least eight authored compositions. Additional named variants require additional pairs. The model must extend beyond six through configuration; six is not a product ceiling. A later count is not supported merely because a parser accepts its integer: both designs and relevant execution checks must pass. State actual resource limits rather than promising unlimited simultaneous playback or silently reducing panel count.

Use 1080×1920 and 1920×1080 as proposed reference export sizes, not artist-approved restrictions. Verify coherent behavior at representative mobile and desktop viewport sizes as well. Do not accept “the landscape version was cropped into portrait” as sufficient design evidence.

## Artifact 001 is now a paired-layout family

Preserve and test the historical Triptych baseline first. Then produce eight short moving renders and their reference stills, one for each required matrix cell. Use distinct synthetic video-loop fixtures with visible motion and identifiable loop identities when historical sources are not yet inspected or cleared. Each orientation pair must derive from the same composition state and time interval so it can be compared directly.

Record state/source manifests, exact commands, engine/tool versions, output hashes/media facts and actual test results. Visually inspect every render. Label synthetic fixtures as engineering demonstrations, not historical reconstructions or artist-approved releases.

Tests must cover one-to-one active-loop/layout mapping, deterministic replay, independent clocks, explicit fit/crop behavior, serialization, hold/reroll/swap/move semantics, portrait→landscape→portrait state continuity, and adding a loop without resetting existing loops. Preserve/test still-image compatibility where needed, but stills alone cannot prove this video-loop project.

Distinguish model tests, offline render evidence and live-browser playback evidence. Do not claim that one establishes the others. Preserve the existing media-first preview and clean-export boundaries; do not turn this into a separate interface project.

## Execution status and first action

Issue #8’s body has been amended to carry this requirement and the expanded acceptance gates. No code change, agent dispatch, completed design, render or passing test is established by that requirements update. PR #7 was not modified in this amendment.

Re-read the current issue, branches and existing agent/PR activity before editing or dispatching. Reconcile any already-running task with the new scope rather than starting a duplicate. Proceed from the existing renderer, retain source-inspection work in parallel, and report exact code/test/render evidence when work is performed.
