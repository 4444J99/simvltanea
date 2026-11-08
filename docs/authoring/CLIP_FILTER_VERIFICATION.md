# Adjustable clip filters: implementation and verification

## Integration status — November 8, 2026

The implementation receipts below describe the original November 7 branch and
remain historical evidence. PR #90 subsequently passed its Apple WebKit gate at
`ae4e0dc89932ef66753f3a6cfb3e59358e064f16` and merged as
`97e6e3e75fe5b8310603f91e533cbc7c6dfda089`. This integration combines that accepted
runtime and progress verifier with PR #92 at
`5dc225a87684012a529bad97770e10a8883d3585`, retaining both sets of regression tests.
It also retains the accepted test's simulation-clock isolation when directly
measuring the native low-pass response.

PR #92's exact revision passed CI run `42431559310` and package run
`42431559340`, but Apple WebKit run `42431559354` **failed**: the seeded run
recorded all four decoded timestamps and callback counts unchanged for 2,648 ms
across 17 observations (maximum polling gap 294 ms). The fresh run passed.
Reanalysis with the accepted verifier still fails the seeded recording.
Preserving the newer progress instrumentation does not repair that dense hold.
The merged local source passed 136 focused runtime, filter, progress and verifier
tests plus 107 subtests on Linux Chromium. A separate control smoke proved the
five-source diagnostic's public handoff and decoded-wrap coverage; it is not
Apple WebKit or 180-second acceptance. The optional native diagnostic retains
both default baselines and all native thresholds; see
[the diagnostic contract](WEBKIT_VERIFICATION.md#controlled-held-source-diagnostic).
This integrated revision still needs its own native verification; no native pass
is inferred from either parent. Physical iPhone acceptance remains pending.

## Scope and source baseline

This change implements the November 7, 2026 direction for clips to emerge,
reach a peak of audiovisual presence, and recede as successors enter. It extends
the persistent Studio session. The authored timeline, exporter, public media,
production configuration, and master audio protection remain outside the change.

The inspected main revision is
`63612a9a7394d8b4e1ec1d375baaa17eaf265eb9`, the merge of
[PR #88](https://github.com/4444J99/tool-video-loop-compositor/pull/88).
Existing in-progress presence work was preserved as a local snapshot before
extension. The local integration also includes the continuity changes from draft
[PR #90](https://github.com/4444J99/tool-video-loop-compositor/pull/90), pinned at
`0f3743769e75011097d781e7d9c14b8fd66681a3`. Both remote heads were rechecked
on November 7. This is a local integration of source changes, not a merge or
deployment of either branch.

## What inspection established

| Area | Existing mechanism | Completed here |
| --- | --- | --- |
| Playback | Persistent A/B videos, one preparation permit, native loops and moving crossfades | Reused the session and preserved its deck identities and resource admission |
| Audio | Per-deck gain, spectral filter and pan feeding the protected master graph | Added configurable presence modulation using the existing gain and filter |
| Image | Native-video crossfade opacity and ecological layout changes | Added independently adjustable brightness, saturation and blur driven by presence |
| Timing | Finite lifetimes, ecological mix weights and a pending presence prototype | Shared bounded timing settings, stable planned lifespan, entrance epoch and overdue tail |
| Controls | Pending global Filters toggle | Added timing, sound and image settings, independent effect bypass and bounded URL persistence |
| Generated sound | A synthesized input attached after resident promotion | Attached separate incoming/outgoing voices during the visual handoff and preserved sibling scheduling |
| Continuity | Draft bounded seam and decoded-frame promotion repair | Integrated its regression cases and repaired pause/resume and final-fade handoff races |

The inspected code established an existing spectral filter stage; it did not
establish a separate continuously writing spectral-ducking controller to combine
with this envelope. This implementation uses that existing stage. Bypassing
presence stops its per-frame filter writes, including when another caller sets
the filter directly.

## Temporal and signal contract

Every visible deck owns an entrance time. Preparation time is excluded, and a
native loop wrapping to its start does not restart the envelope. Evolving clips
rise to full presence, fall across their planned lifespan, and retain a bounded
waiting tail until a successor can take over. Retrying or postponing retirement
does not create another peak. The existing moving crossfade finishes the outgoing
clip's departure while the incoming deck follows its own entrance phase.

The same scalar presence supplies gain, low-pass, brightness, saturation and blur
targets. Gain modulation is applied after ecological mix normalization, so it
also works for a single resident. Gain and cutoff automation use the same
15-millisecond smoothing constant. This establishes shared phase and target
timing, not sample-exact equality between audio output and displayed pixels.

The following defaults and bounds are engineering choices exposed for adjustment:

| Setting | Bounds | Default |
| --- | --- | --- |
| Rise | 0.1–5 seconds | 1.2 seconds |
| Curve | Linear or smooth | Linear |
| Waiting presence | 5–50 percent | 12 percent |
| Gain, low-pass, brightness and saturation depth | 0–100 percent each | 100 percent each |
| Blur | 0–2 CSS pixels | 2 pixels |

Zero depth independently bypasses an effect. A separate global bypass retains
the settings. Controls apply to the live field, with each clip retaining its
own envelope age. Pause and hidden-tab suspension freeze the simulation clock.
Hold keeps steady presence after entry; reduced motion bypasses the animated
filters. The live canvas fallback, used when generated recording is unavailable,
keeps its previous behavior and disables the filter controls.

Incoming and outgoing generated voices now use their own deck filters and gains.
Attachment is idempotent for the same deck, item and binding. A failed successor
disconnects only its own voice; retirement disconnects only the outgoing voice.
The preserved scheduling clock keeps sibling synth events running while Studio
prepares a new metadata session. Pause and disposal stop new scheduling.

The outgoing resident's identity is retained until promotion succeeds. A
same-task pause/resume during decoded-frame verification requires another
verification attempt. At the final fade tick the incoming deck remains recognized
as audible while the replacement promise completes. A refused or frozen
successor restores the old deck, filter phase and gain and releases preparation.

The mobile resource contract remains four foreground videos plus one preparing
or fading successor. Concurrent resident envelopes and queued replacements do
not permit concurrent extra preparations. Settings changes do not recreate
media elements, media-source bindings, the AudioContext or master bus.

## Historical executed local verification

Environment: Linux, Python 3.12.14, pytest 9.2.0, Playwright 1.57.0 and Chrome
for Testing headless shell 157.0.8103.38 with native H.264 decoding. Browser
fixtures use synthetic media. The new Studio tests route actual staged bytes
in-process, retain the production content security policy, and observe all
network requests. They do not contact the published Studio.

The complete focused command was:

```bash
PYTHONPATH=src:. python -m pytest -q \
  src/simvltanea/browser/test_browser_presence.py \
  src/simvltanea/browser/test_browser_presence_settings.py \
  src/simvltanea/browser/test_browser_ecosystem.py \
  src/simvltanea/browser/test_browser_live.py \
  src/simvltanea/browser/test_browser_filter_runtime.py \
  src/simvltanea/browser/test_browser_filter_controls.py \
  src/simvltanea/browser/test_browser_generated_filters.py
```

`PORTVS_BROWSER_EXECUTABLE` selected the H.264-capable headless shell. Result:
**91 passed in 84.02 seconds**, with no skips. Coverage includes bounded/invalid
settings, rise and fall timing, delayed retirement, independent clip ages,
normalized solo gain, queued handoffs, frozen or rejected successors, late audio
unlock, mute/bypass/reduced motion, actual audio parameter settling, generated
signal during the fade, sibling frames and scheduling, and the four-plus-one
budget while adjusting settings.

The meaningful failures were observed before their fixes: missing settings APIs,
unavailable URL settings, incoming generated sound absent during a fade, sibling
synth scheduling stopped during pending launch, paused-successor promotion after
immediate resume, rejected-resume promotion, and the final fade briefly muting its
incoming deck.

Additional executed checks:

- Studio staging, quantization, library selection, runtime-hook boundaries and
  plan index: **22 passed, 376 subtests passed**.
- Broader audio, compiler, continuity, authored/export parity and site-boundary
  batch: **124 passed, 952 subtests passed**. Its 11 fixture-setup errors were
  rerun serially: **11 passed, 7 subtests passed** in 49.95 seconds.
- Wheel build and isolated installed-consumer verification passed, including
  portrait and landscape synthetic renders. The packaged presence helper was
  compared byte-for-byte with its source.
- JavaScript syntax, whitespace, repository structure, feature boundaries,
  layout synchronization and plan-index synchronization passed.
- The settings dialog was visually inspected at a 390-by-844 touch viewport.
  It fits horizontally and scrolls its remaining controls vertically. Keyboard
  dismissal, focus return, reset and playback isolation are tested.
- A focused independent review found no confirmed blocking correctness issue
  in the inspected production paths. It covered envelopes, settings, handoffs,
  rollback, audio ownership and ecology. It was not an end-to-end audit of every
  test and document, and did not independently rerun the suites.

The original native spectral-filter suppression check was also restored to run
with the simulation clock active. Its three related native filter regressions
passed after that test-only change; no production change was needed.

Earlier broad attempts encountered a truncated local synthetic ramp clip and a
collision between two batches publishing the same temporary preview fixture.
The synthetic clip was regenerated. The collision did not require an application
change; the affected tests subsequently passed serially. These attempts are not
counted as successful runs. The historical PR #88 CI total of 1,692 passing tests
and 51 skips is not a verification result for this change.

The optional pinned external authored engine was unavailable locally. Its
diagnostic remains in the bounded consumer proof. No substitute engine or
relaxed pin validation was introduced.

## Historical WebKit status and physical iPhone boundary

Local WebKit launch was attempted; the required Playwright WebKit executable was
not installed. No local WebKit pass is claimed.

PR #90 at the pinned head still reports **FAIL** for both three-minute Linux
WebKit candidate runs: a 27.302-second frozen resident with seed `528316659`, and
a 10.803-second freeze in a fresh composition. Bounded seam fallback allowed
later replacements, but did not establish sustained continuity. The PR remained
open, draft and unmerged when rechecked. See the
[repair evidence](https://github.com/4444J99/tool-video-loop-compositor/pull/90)
and [acceptance issue #89](https://github.com/4444J99/tool-video-loop-compositor/issues/89).

Physical iPhone acceptance remains unverified. After an explicitly approved
preview publication, record the device and iOS version and verify:

1. Several minutes of evolving four-panel playback with sound, observing actual
   frame progress and `proof=1` evidence through multiple replacements.
2. Filter rise, peak and recession; independent zero-depth controls; global
   bypass; and restoration from a shared settings URL.
3. Panel taps and repeated shuffles while sibling panels and sound continue.
4. Sound unlock, mute, volume, pause/resume, rotation and background/foreground
   recovery, including a handoff already in progress.
5. Forward and boomerang sources, local uploads and the four-panel limit.
6. Sustained responsiveness with the selected filter strengths, especially blur;
   the application budget is not a hardware decoder or GPU measurement.

## Historical publication boundary

No push, pull request creation, merge, deployment, published-media replacement
or production configuration change is included in this work. Pushing the review
branch would trigger a Cloudflare preview deployment. That operation requires
explicit approval of the exact branch and revision. The unresolved WebKit and
physical-device gates remain visible before any release decision.
