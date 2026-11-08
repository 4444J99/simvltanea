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

Three narrowly evidenced resource outcomes are reported separately:

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

## Running on a Mac

From a clean checkout, install the pinned browser in a temporary directory:

```bash
export NODE_PATH="$(mktemp -d)/node_modules"
npm install --prefix "${NODE_PATH%/node_modules}" --no-save --package-lock=false --ignore-scripts playwright@1.65.0
node "$NODE_PATH/playwright/cli.js" install webkit
python3 -m tools.publishing.build_studio_site --output var/site/macos-webkit
node src/simvltanea/browser/verify_webkit_sustained.js var/site/macos-webkit var/proofs/macos-webkit
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
python3 -m unittest src.simvltanea.browser.test_webkit_verifier
```

Reanalysis writes a separate derived receipt and retains the original artifact
and its hash. It does not turn historical missing telemetry into positive proof.

This is an Apple desktop WebKit/media-backend check with an iPhone viewport
profile. It does not certify physical iPhone Safari, mobile hardware decoder
limits, audible loop seams, or frame-perfect rendering between observations.
