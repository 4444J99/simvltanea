# Visual Form Canon

Status: incubating
Canonical owner for now: Portvs incubator
Final implementation owner: unresolved

## Operating Chain

Use this order from root to leaf:

1. Remote repository canon defines the project surface.
2. Protocol dictates action inside the selected surface.
3. If protocol fails, precedent dictates action.
4. If protocol and precedent fail, explore without mutating adjacent repos until
   the ideal form is clear enough to classify.

For this pass, the controlling protocol is the Portvs incubator rule: keep new
work inside `incubator/triptych-video-canon/`, do not touch Limen, do not use
`config/_limen`, do not mutate `graph.jsonl`, and do not edit adjacent
implementation repos while the owner is unresolved.

Local checkouts are evidence caches, not canon. A cross-project visual-form
review starts with the GitHub remote census, then uses local files only to
inspect or run a repository already identified by remote scope.

## Canonical Object

The broader object is the **Visual Form Canon**. The previous Visual Media Canon
is one branch of it, not the whole system.

Every leaf should reduce to:

```text
source set + visual grammar + runtime target + remix transforms + public/private boundary + promotion target
```

## Root-To-Leaf Matrix

| Root branch | Known leaves | Ideal form | Promotion posture |
| --- | --- | --- | --- |
| Triptych / time-based media | Story, Reels, panel exports, visual sketches, release player | Timed canon and edition renderer | Keep in Portvs until the renderer becomes product/runtime infrastructure. |
| Ambient screensaver / wallpaper runtime | Screensaver, desktop wallpaper, phone wallpaper, idle display, ambient loop | Living display program over still/video/text sources | Promote to exhibit/art runtime if it becomes an installed or kiosk-like artwork. |
| OGOD / symbolic visual worlds | OGOD pages, Pantheon chambers, web chambers, symbolic interface systems | Navigable world/interface grammar | Promote toward a-mavs-olevm, etceter4, or another art repo when implementation resumes. |
| ASCII / textual visual design | ASCII art, ANSI/text-mode images, typographic diagrams, prompt-wall composition | Text-as-image grammar | Keep as source grammar that can feed terminal, web, print, or video forms. |
| Visualizer / generative abstract runtime | Confluence, mystical energy canvas, sacred geometry canvases, soul field, visualizer R&D substrates | Parameterized browser visualizer grammar | Promote toward the visualizer/art-runtime repo when the next object is browser interaction rather than lineage. |
| Web / 3D chambers | OGOD 3D, chamber viewers, WebGL/Three.js rooms | Spatial visual runtime | Promote to an art/runtime repo when a concrete viewer is the next object. |
| Media Ark / source custody | Photos, Finder folders, source media, sidecars, indexes | Restageable source and metadata custody | Promote ingestion, dedupe, canonical media, and indexing to Media Ark. |
| Portfolio / public gateway | Case studies, public pages, product/shop, commerce handoff | Sanitized public projection | Promote only verified packages, copy decks, and public manifests to portfolio. |
| Exhibit / kiosk / gallery | Digital frame, kiosk, gallery loop, installation program | Public playback contract | Promote when the work is meant to be shown as an artwork. |
| Lifecycle / generated-form governance | Private receipts, ignored caches, packages, cleanup plans | Bounded generated-lane discipline | Keep as a rule across every branch. |

## Classification Rules

- `keep`: remain in Portvs when the object is lineage, grammar, refraction, or
  promotion logic.
- `merge`: combine branches only when they share the same source set, grammar,
  and runtime target.
- `promote`: move implementation only after the destination owner and verifier
  are explicit.
- `archive`: preserve as source evidence when it is no longer an active runtime
  or public surface.
- `remix-source`: treat as material for future forms without claiming current
  ownership.

## Visual Surface Rules

- The first frame is the visual object, not a settings panel, selector strip, or
  proof surface.
- Runtime settings, parameters, proofs, and component selectors stay hidden until
  click or tap; exports must contain no chrome.
- Story/Reel outputs use full-frame visual fields with deliberate negative
  space. Do not shrink the artwork into a framed preview band.
- Browser QA must verify both states: render-only before click/tap, and controls
  visible after click/tap. If utility CSS is unreliable, critical fullscreen and
  tap-target geometry must be explicit enough to survive the build.

## Current Evidence Posture

`remote_repo_census.py` scans GitHub repository metadata first. Its private
receipts are:

- `work/remote-repo-census.json`
- `work/remote-repo-census.md`

Current remote-canon census scope:

- Owners scanned: `organvm`, `4444J99`
- Remote repositories scanned: 273
- Private repositories in census: 87
- Archived repositories in census: 11
- Visual-form candidate repositories matched: 48

Current remote-canon signal counts:

| Signal | Repository overlaps |
| --- | ---: |
| ASCII / textual visual design | 2 |
| Visual runtime / generative art | 16 |
| OGOD / symbolic visual worlds | 5 |
| Web / 3D chambers | 8 |
| Media Ark / source custody | 9 |
| Portfolio / public gateway | 11 |
| Exhibit / kiosk / gallery | 2 |
| Audio-visual waveform runtime | 5 |

`prompt_lineage.py` then scans local Codex session prompts plus selected
project documents for visual-form evidence. Its private receipts are:

- `work/visual-form-lineage.json`
- `work/visual-form-lineage.md`

It also writes compatibility receipts for the earlier Visual Media Canon names:

- `work/visual-media-lineage.json`
- `work/visual-media-lineage.md`

The receipts may contain raw prompt excerpts and local paths. Tracked docs should
only use aggregate counts, cluster names, and decisions.

Current non-circular receipt scope:

- Session files scanned: 1,018
- Session prompts matched: 123
- Source/project document evidence surfaces matched: 28

Current cluster overlap counts:

| Branch | Prompt overlaps | Document overlaps |
| --- | ---: | ---: |
| Triptych / time-based media | 15 | 7 |
| Ambient screensaver / wallpaper runtime | 1 | 12 |
| OGOD / symbolic visual worlds | 4 | 15 |
| ASCII / textual visual design | 2 | 6 |
| Web / 3D chambers | 1 | 9 |
| Image / moving-image overlap | 6 | 6 |
| Media Ark / source custody | 26 | 17 |
| Portfolio / public product gateway | 51 | 13 |
| Exhibit / kiosk / gallery | 1 | 10 |
| Lifecycle / generated-form governance | 43 | 8 |

## First Omega Gate

The first consolidation is complete only when the receipt can show all of these
branches explicitly: triptych/time-based media, ambient/screensaver/wallpaper,
OGOD/symbolic worlds, ASCII/textual visual design, visualizer/generative
abstract runtime, web/3D chambers, Media Ark custody, portfolio gateway,
exhibit/kiosk/gallery, and lifecycle governance.

The next omega gate is stricter: those branches must reconcile remote repository
canon first, then local prompt/session evidence. A local-only match is not enough
to claim the project surface exists.

## N-loop execution checkpoint — 2026-09-05

This checkpoint supplements, rather than revalidates, the older census counts
above. Detailed commands and limits are in `RUNTIME_RECEIPT.md`.

| Evidence class | Current boundary |
| --- | --- |
| Historical works | Floating Points projects and Up the Hill Backwards media remain archive locators or connector-extracted text, not recovered original-byte graphs or visually verified historical compositions. TripTicks, First Circle, the earlier selector and conceptual Triptych remain distinct unresolved identities. Narcissus audiovisual identity is unresolved; similarly named PDFs do not close it. |
| Reusable formal principles | N independent loops; authored spatial hierarchy; independent local clocks; deterministic selection/replay; presentation-only orientation changes; hold/release/reroll/swap/move. A principle is not proof of an ancestor's implementation. |
| Current engine capability | The existing FFmpeg path renders paired 3/4/5/6 engineering compositions. A separately named labeled contain-study family has paired 3–7 exports. Experimental seven uses the same compiler and renderer, not a new application. |
| Current runtime proof | Native Chromium video playback survives five advancing viewport checkpoints and independent container resizing with persistent keyed video nodes. Source decisions come from the Python compiler. The executed transport was offline file-backed IO; HTTP-served loading and physical devices remain unverified. |
| Future extensions | Dense overlap, masking, opacity/blend graphs, nesting, generative audio, live input events, indefinite playback, audience controls and physical installation are not completed by these tests. Historical features do not automatically become requirements. |

All arrangements remain **synthetic authored engineering compositions**, not
artist-approved geometry, historical reconstructions or public releases.
The browser preview is bounded and silent. Its source-bank hashes and portable
state can reproduce the corresponding offline exports; browser sampling is not
frame-exact. Resource guards are not measured hardware ceilings. Unsupported
layout pairs and excessive resource requests fail explicitly rather than
reducing N or adding filler. Portvs remains the incubator; promotion is undecided.
