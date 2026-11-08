# Adjustable clip filters implementation plan

## Scope and authority

Implement the November 7 request for synchronized clip-level sound and image
filters in the persistent Studio runtime. Reuse the existing presence prototype
and PR #90 at `0f3743769e75011097d781e7d9c14b8fd66681a3` for local compatibility
verification. No merge, deployment, published-media replacement, or production
configuration change is authorized.

## Design

Each persistent deck owns its entrance time and current presence. The existing
simulation clock provides a single timeline for its gain, spectral filter and
image targets. The outgoing resident retains its identity until decoded-frame
promotion succeeds. Preparation remains serialized; envelopes on existing
residents continue independently while a successor loads.

Extend the current helper with bounded settings. Keep the established defaults:
1.2-second rise, linear fall, 12% waiting presence, gain and low-pass modulation,
brightness 0.55–1, saturation 0.3–1, and blur 2–0 CSS pixels. Offer a smooth curve
and separate controls for gain, low-pass, brightness, saturation, and blur.
A zero depth bypasses that effect. These are engineering defaults, not a claim
that the owner has approved an artistic preset.

Retain the Filters bypass button. Add an accessible Filter settings dialog with
labeled controls, keyboard dismissal and focus return, plus reset defaults.
Settings apply to the live field; each clip evaluates them on its own timeline.
Only named bounded effect values enter shared URLs. No clip paths, uploads or
user data are serialized. No new media elements, media-source bindings,
AudioContexts, master buses, or decoder permits are introduced. Generated loops
retain one synthesized input per visible deck, including both sides of a handoff.
Authored/export schemas and runtime stay unchanged.

## Implementation and verification

- [x] Preserve a stable snapshot of the pending presence work and inspect PR #90.
  Apply the repair locally and preserve all distinct regression cases.
- [x] Add pure settings normalization and adjustable envelope/effect tests,
  observing failures before implementation. Preserve default behavior and
  finite outputs for extreme/invalid inputs.
- [x] Connect the same settings to ecosystem and live deck calculations. Reuse
  the existing spectral filter stage. Preserve bypass,
  pause, reduced motion, mute, outgoing rollback and the mobile four-plus-one
  budget without recreating media or AudioContext objects.
- [x] Add the settings dialog and bounded URL persistence. Verify controls,
  keyboard behavior, reset, independent effect disabling and no media reload.
- [x] Add focused combined-runtime tests for concurrent resident envelopes,
  queued replacements, successor failures, gain/filter/image timing, stale
  automation, and sibling isolation. Include generated voices during a handoff
  and pending launch, with idempotent attachment and isolated failure cleanup.
- [x] Finish the affected browser and export gates and record their actual
  results, including any unavailable dependencies.
- [x] Inspect available Chromium and Linux WebKit evidence; attempt available
  engines and report physical iPhone verification separately. Obtain a focused
  independent production-code review and record its coverage, executed commands
  and observed results.

## Risks to test deliberately

A solo clip must retain its amplitude envelope after mix normalization. A new
deck must not inherit its predecessor's closing filter. Failed or frozen
successors must release preparation without retiring the outgoing resident.
Pause must freeze envelope time; resume must preserve resting loops. A settings
change must not restart videos, replace audio nodes, or affect source privacy.

## Delivery boundary

Keep the complete changes on an isolated review branch. Recheck current remote
heads before proposing any integration. Show precise intended integration and
publication operations and obtain explicit approval before carrying them out.
Linux desktop browser observations do not establish physical iPhone acceptance.

## Verification record

See [the implementation and verification receipt](../authoring/CLIP_FILTER_VERIFICATION.md)
for the exact focused command, 91 passing focused tests, broader authored/export
and Studio checks, installed-wheel proof, fixture retry history, unresolved
WebKit evidence, and the physical iPhone acceptance boundary.
