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
duration, and explicit numeric playback-quality counters. No init script, prototype
patch, analyser, canvas read, or retained-video registry is installed during
these baselines. Screenshots are omitted: Playwright's WebKit screenshot helper
injects a stylesheet even with caret hiding and animation changes disabled,
which produces an unrelated CSP error under the application's strict policy.

The gate checks joint clock/frame holds and decoded-frame holds independently;
either reaching two seconds fails. Increasing callback counts alone do not
prove progress. Measurements follow each slot/clip/deck/birth identity across
REST transitions, because dimmed residents must keep moving. REST intervals
also have separate hold and pause measurements. Unexpected pauses and global
suspension fail separately. Outgoing residents remain measured during
transitions rather than hiding holds behind the pending state.

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

- A Blob error-1 message or cancelled Blob request follows retirement of that
  exact URL by at most 1,000 ms. The retirement must record a paused element at
  readyState 0, and subsequent samples must not contradict the disposal by
  showing it active before the error.
- A plain cancelled Blob request is followed within 1,000 ms by two distinct
  decoded times and increasing callbacks on the same deck and native source
  URL, with no native media error. This proves that the cancelled read did not
  terminate that source; callback counts alone are insufficient.
- A plain cancelled HTTP fetch follows an explicit application abort of that
  exact outstanding asset request by at most 1,000 ms.

Each classification retains its raw-record reference and timing or frame
evidence. Unknown URLs, future retirements/aborts, other error types, and
unproven recovery fail. Independent two-second playback gates still reject
freezes, even when a resource cancellation has been explained.

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
receipt. A failure in one sustained run does not skip the other run.

This is an Apple desktop WebKit/media-backend check with an iPhone viewport
profile. It does not certify physical iPhone Safari, mobile hardware decoder
limits, audible loop seams, or frame-perfect rendering between observations.
