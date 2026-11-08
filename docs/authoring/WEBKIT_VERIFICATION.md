# macOS WebKit verification

The `macOS WebKit playback` workflow runs on pull requests and pushes to `main`.
It uses `macos-15`, Node 22, and an isolated `playwright@1.65.0` installation with
its own WebKit browser. Missing browser support, public media, or native audio
support fails the job. There is no Linux, Chromium, synthetic-media, or
mathematical fallback.

The ordinary `build_studio_site` command stages the checked-out Studio and its
pinned public library, validating the manifest and media hashes. The proof
records the Git commit, macOS/browser versions, device descriptor, and hashes of
the staged files. Generated media and receipts remain below `var/`.

## Sustained playback

Two separate browser sessions run for 180 seconds each: seed `528316659` and a
fresh composition whose resulting seed/URL is retained. Both enable sound by
clicking the speaker. They read native current time and decoded media time every
137 ms, with application snapshots each second. Samples also retain the audio
clock, gain values and targets, each existing deck's source URL and native
duration, and explicit numeric playback-quality counters. In `?proof=1`, the
existing native frame callback also maintains distinct-media-time counters,
source epochs, and a monotonic maximum foreground gap. A preallocated 128-point
ring retains distinct callback changes; up to 16 retired sources retain their
final bounded trace and native error. Traces are read once per second, while
counters and maximum gaps are read on every poll. No additional frame observer
or playback action is installed. No init script, prototype
patch, analyser, canvas read, or retained-video registry is installed during
these baselines. Screenshots are omitted: Playwright's WebKit screenshot helper
injects a stylesheet even with caret hiding and animation changes disabled,
which produces an unrelated CSP error under the application's strict policy.

The gate checks joint clock/frame holds and decoded-frame holds independently;
either reaching two seconds fails. Increasing callback counts alone do not
prove progress. Two polling samples can contain the same decoded time after
one or more complete loops. Distinct native media-time changes and the retained
maximum gap resolve that ambiguity, including stalls that begin and recover
entirely between polls. Source retirement and replacement cannot erase a prior
maximum. Measurements include incoming visible decks and outgoing residents
throughout their transition.

Current receipts declare `progressSchema: 1`. Every sample must include supported,
consistent source identities, monotonic counters and maxima, and matching active
node/deck observations. Missing or malformed coverage fails the gate. Historical
receipts without this telemetry cannot prove continuity across a polling gap of
two seconds or more: reanalysis reports `INCONCLUSIVE` with `pass: false`, rather
than inventing a continuous freeze from matching endpoint phases. A dense,
observed hold still reports `FAIL`; no threshold has been relaxed. Both verdicts
block a successful verification receipt.

REST remains visible playback and never resets progress. REST intervals also
have separate hold and pause measurements. Only explicit global pause time is
excluded from the tracker; active no-progress time on either side is retained.
The sustained run itself never pauses, so a monotonic session suspension counter
also rejects a pause/resume hidden between host samples.

Receipts also require four persistent foreground slots, native wraps, a successor
in every initial slot, and no native media, runtime, page, HTTP, or unexplained
resource errors. Console errors retain their message and source location;
failed requests retain the URL and native failure details. Error timestamps
record when the runner received the event, with both epoch and monotonic clocks.
The document's `performance.timeOrigin` aligns those receipt times with media
samples and the application's proof-only resource-retirement events. They are
not exact browser emission timestamps. Navigation, sustained playback, controls
and browser-closing phases remain distinguishable. Every raw error is retained.

Births and natural succession follow logical residents, independently of physical
deck ownership. A verified same-clip decoder repair preserves that identity and
cannot satisfy the succession requirement. Its outgoing and incoming frame
histories still contribute independently to the original continuity limits.

Four narrowly evidenced resource outcomes are reported separately:

- A Blob error-1 message or cancelled Blob request follows verified retirement
  of that exact URL. The retirement must record a paused element at readyState
  0. Every subsequent sample through the end of capture is checked for reuse:
  the URL must never be a populated source or the current source of an active,
  populated deck. A stale `currentSrc` on a cleared inactive deck is permitted.
  Asynchronous delivery can lag disposal by seconds; the receipt records that
  delay without imposing an unrelated timing limit on confirmed disposal.
- A plain cancelled Blob request is followed within 1,000 ms by two distinct
  decoded times and increasing sequences on the same deck, source epoch and
  native source URL, with no native media error. Either sampled frames or the
  bounded native callback trace can supply that evidence. A later host poll may
  deliver the trace, but both callback timestamps must fall inside the original
  1,000 ms receipt window. Malformed, ambiguous or cross-epoch traces cannot
  qualify. This proves that the cancelled read did not terminate that source;
  callback counts alone are insufficient.
- A plain cancelled HTTP fetch follows an explicit application abort of that
  exact outstanding asset request by at most 1,000 ms.
- A cancelled hidden preparation read has the same owned deck, URL and epoch
  through priming, parking, fresh-frame verification and successful promotion.
  Its outgoing resident must continue progressing while the standby is parked.
  Only an independently proven retirement console record is excluded from its
  error association; another error for the same URL still rejects admission.

Each classification retains its raw-record reference and timing or frame
evidence. Unknown URLs, future retirements/aborts, other error types, and
unproven recovery fail. Independent two-second playback gates still reject
freezes, even when a resource cancellation has been explained.
Only the exact request-failure dialects `cancelled` and `net::ERR_ABORTED` qualify
as cancellations; each requires the same positive disposal, recovery, or explicit
fetch-abort evidence. The recovery and fetch-abort windows remain 1,000 ms.

All three pacing regimes must appear across the two runs combined; each run
reports its own coverage. A missing regime is a coverage failure, not proof of
a playback defect. They enforce at
most four foreground slots, five populated/playing session decks, and one
preparation lease. Sampled software counts do not measure hardware decoders or
every moment between samples.

## Separate interaction and audio checks

After both baselines, a new browser checks isolated tapping, shuffle,
forward/boomerang selection, portrait/landscape layout, Filters bypass/restoration
with its URL state and persistent media identities, global pause/resume,
the mobile population limit, and sound mute/unmute. All three sessions retain
the proof-only resource-retirement log. The interaction session reads existing
decks at the same 137 ms cadence and attaches a post-master meter, requiring
nonzero digital output and
silence when muted. These intentional actions never enter the continuity
measurements.

A separate native `OfflineAudioContext` renders four correlated 440 Hz sources
at gain `0.425` through the production `SimvltaneaLiveAudio` master chain. The
rendered sample peak must exceed `0.1` and remain at or below `0.891251`.
This checks sample peaks, not reconstructed true peaks, physical speaker output,
or human listening quality.

## Controlled held-source diagnostic

The workflow additionally passes `--held-source-diagnostic`. This adds a separate
180-second session; it does not replace either default baseline or change the
two-second hold threshold. The step allows 22 minutes and the job 35 minutes so
the additional work does not consume the original baselines' time allowance.

The source set comes from failed Apple run `42431559354` at PR #92 head
`5dc225a87684012a529bad97770e10a8883d3585`. Its original artifact `13597902240`
has SHA-256 `da5959ad179bf7bb4a942605edac0f859df70cf6fd0dfd76097d8d572a88d193`.
Seventeen dense observations recorded all four decoded positions and callback
counts unchanged for 2,648 ms. That failure remains unresolved.

The diagnostic copies the five complete original manifest entries for held
residents `107936da1aae`, `2f00e7f10d19`, `443fbc2c885a`, `c1d21417eede` and
predecessor `37b398494e0d`. Both the full and subset manifests must pass Studio's
existing schema gate. The pinned full-manifest digest and every selected forward
and boomerang file's full digest and byte length are checked. Only a separate
diagnostic server returns the subset manifest; file paths and bytes remain
unchanged. No asset is re-encoded and neither the staged site nor full library is
modified. The fixture, original URLs, full hashes, source run and helper digest
are retained in the artifact.

A public composition URL starts the predecessor alongside the three held
siblings with evolution off. Read-only observations must prove active decoded
progress and a decoded-time wrap for each. A public tap on panel 1 then chooses
the sole spare, `107936da1aae`. The resulting quartet and unchanged sibling
identities are checked. After the arriving source has decoded and wrapped,
the activity control enables evolution for the full 180-second measurement.
Sampling continues throughout the tap and handoff.

The receipt requires all five sources' exact hashes, active admission, multiple
advancing decoded observations, and a decoded-time wrap within one unchanged
slot/deck/birth/source epoch. The four held sources must also satisfy that
coverage during the sustained phase. Media-clock movement, passive prefetch,
missing samples or a requested seed cannot supply this proof. Brief native
`HAVE_METADATA` at a loop seam does not invalidate subsequent decoded callback
evidence; unsupported telemetry and native holds reaching two seconds still fail.
Raw prelude samples stream to the bounded journal, including on failure.

This controlled four-active composition uses a manual mix, which suppresses
sparse resting. It reproduces the selected assets and one predecessor-to-successor
handoff, not the original wall timing, deck ages or complete ecological history.
The two default baselines retain ordinary population and rest coverage. A passing
diagnostic establishes that coverage for its tested revision, not a cause or
repair of the archived failure.

## Paired source-controlled seek experiment

`--seek-cohort-diagnostic` adds two further 180-second sessions, while requiring
all three original phases above. The reference arm explicitly sets
`nativeLoopSeekPauseBeforeSeek=false`; the candidate arm sets it to `true`.
A diagnostic-only initialization hook applies that option when Studio assigns
its newly constructed Session, before initial media admission. Start and end
option snapshots record that boundary. No production query or control is added.

The cohort comes from original failed run `42444130199`, head
`373e3870a82421ff99a1a3add283ddbece785697`, artifact `13602957458`
(SHA-256 `3eae6b8870706e0f5719f829af7108512e639aa10a83c7bb3baa73d3543ae522`).
The archived target's decoded gap was 3,221 ms despite an attempted recovery;
that failure remains preserved. Both arms use the same six full manifest entries
and hash-verified forward and boomerang bytes:

| Role | Source | Slot |
| --- | --- | --- |
| Peer | `2f949d8676d1` | 1 |
| Peer | `efe8ffd8c723` | 2 |
| Resident sibling | `3ffa0d345ed1` | 3 |
| Target | `8356ed30a9fe` | 4 |
| Target predecessor | `443fbc2c885a` | 4 |
| Incoming sibling | `99835e485b6e` | 3 |

The adapter begins with the two peers, resident sibling and predecessor in Hold.
After decoded wraps are observed, it supplies pinned Blob items to the actual
`Session.reconcile` API: predecessor to target, then resident to incoming sibling.
The second transition starts after observing the resident's next phrase. Native
priming, seam waiting, crossfading, the preparation lease, persistent media
elements and audio graph remain owned by Session. The adapter never calls a
video's play, pause or seek methods. It verifies the manifest and incoming bytes
again in the browser and records admission hashes and exact transition samples.

Setup must prove all six sources decoded and wrapped, unchanged sibling and
slot identities, and actual incoming-sibling decoded advances while the target
and outgoing sibling coexist. Raw priming observations are retained separately
from qualified overlap evidence. The final quartet stays in Hold for 180 seconds
and must each decode and wrap again. This reproduces source identities and
transition order, not original wall timing, deck ages or ecological history.

Each arm preserves its unmodified `analyse()` verdict, including the expected
natural-succession failure for a fixed composition. A separate named controlled
verdict marks only succession as not applicable. Every other original check,
including the two-second decoded hold, observation coverage, errors, native
wraps and resource limits, remains required, together with the cohort coverage.
The candidate controlled verdict is required; the reference arm is diagnostic.
Neither can replace any original phase's full natural-evolution verdict.

Both arms keep the same production standby-rescue policy enabled; only the
pause-before-seek operation differs. Held composition can cross a physical
decoder change only with a complete, source-owned repair receipt and independent
fresh-frame and retirement evidence. Logical clip identity and birth time must
remain unchanged. Missing, stale or unrelated bridge evidence fails coverage;
native wraps are never inferred by joining frames from different sources.

Attempt attribution uses authoritative `nativeLoopSeek` proof receipts, joined
to exact cohort slot, source hash, URL and epoch after option assignment. The
ordinary event ring is retained but not double-counted: its wall timestamp is
recorded separately from the proof receipt. Missing receipts or a mismatched
strategy fail attribution. Zero attempts is `NOT_EXERCISED`; observed recovery
does not alone establish a causal improvement over the reference arm. The
original failures, all raw JSON/NDJSON, both verdicts, source hashes and strategy
substep receipts remain in the uploaded artifact without trimming.

## Native loop-seek recovery evidence

`progressSummary.nativeLoopSeek` retains attempted, recovered, rejected and
interrupted counts plus at most sixteen receipts in traced samples. `dropped`
reports receipt eviction; totals survive the ordinary 256-event log. Each receipt
identifies its source URL and epoch. Attempts include the observed native seam,
seeking state, accumulated simulation time and forward seek target. Recovery
requires two distinct nonseeking frames with uninterrupted source ownership.

These records do not reset or exclude any frame-progress gap. A causal assessment
must inspect the original native samples, attempt and recovery records, and the
unchanged continuity gates. Zero attempts means the mechanism was not exercised,
even if the run passed. Missing or evicted evidence cannot establish an otherwise
unobserved successful recovery. Historical failures remain retained separately.

## Running on a Mac

From a clean checkout, install the pinned browser in a temporary directory:

```bash
export NODE_PATH="$(mktemp -d)/node_modules"
npm install --prefix "${NODE_PATH%/node_modules}" --no-save --package-lock=false --ignore-scripts playwright@1.65.0
node "$NODE_PATH/playwright/cli.js" install webkit
python3 -m tools.publishing.build_studio_site --output var/site/macos-webkit
node src/simvltanea/browser/verify_webkit_sustained.js var/site/macos-webkit var/proofs/macos-webkit --held-source-diagnostic --seek-cohort-diagnostic
```

The workflow uploads `var/proofs/macos-webkit/` on success or failure, including
setup/build logs, source identity, raw samples, individual checks, and the final
receipt. During each sustained run, an asynchronous NDJSON journal appends one
bounded record at a time, honoring stream backpressure. It records run metadata,
samples, coarse snapshots and raw errors, preserving partial evidence if the
process terminates. Records over 2 MiB or stream write/flush failures fail the
run. Full-result JSON is serialized only after measurement finishes; the growing
result is never synchronously rewritten during playback. A partial journal
cannot count as a completed passing run. A failure in one sustained run does not
skip the other run.

Analyzer and journal regressions run without a browser:

```bash
python3 -m unittest src.simvltanea.browser.test_webkit_verifier src.simvltanea.browser.test_webkit_held_sources src.simvltanea.browser.test_webkit_seek_cohort src.simvltanea.browser.test_webkit_seek_adapter
```

Reanalysis writes a separate derived receipt and retains the original artifact
and its hash. It does not turn historical missing telemetry into positive proof.

This is an Apple desktop WebKit/media-backend check with an iPhone viewport
profile. It does not certify physical iPhone Safari, mobile hardware decoder
limits, audible loop seams, or frame-perfect rendering between observations.
