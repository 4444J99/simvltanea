# PR #9 — Reconciled proof and review-readiness receipt

Proof ID: `PR9-RECONCILED-REVIEW-2026-09-06`.
Date: September 6, 2026. Scope: issue #8, `incubator/triptych-video-canon/` only.

**Decision: retain draft under the current execution gate and advertised scope.**
The normalized engine, rendered outputs and bounded native-browser behavior now
have a reproducible review packet. Normal served HTTP/WebCrypto loading remains
unverified, and hosted CodeQL has not succeeded. This is not a claim that code
review universally requires deployment, historical reconstruction, hardware
certification or artist approval; those remain separate, explicitly open gates.
No ready-for-review transition, merge, deployment or publication was performed.

## Exact source and concurrent work

The live starting head was `00d3788260e1b8d3d76cf030dd9b69418059101b`, not the
older five-commit/38-test handoff. While execution was in progress, the branch
advanced to `c3fbae7d4d354de0306e62f123c77eadddc4565e`. That concurrent commit's
independent continuity observer, tests and receipts were preserved, not replaced.

The tested code commit is `d523af18797996d9fc3b1446dfb1238cef7bbfbd`, a direct
child of `c3fbae7`, published by a non-forced fast-forward on the existing branch.
Its five changed files match the executed local bytes by Git blob and SHA-256.
The subsequent receipt commit changes documentation only. No competing branch
or agent was launched. Main and the separate audit PR #7 were not changed.

Execution used a scoped source snapshot: 19 starting files, two baseline files
and two incoming observer/test files were matched to their Git blobs. It was
not a full checkout. The attempted Git status command returned exit 128,
"not a git repository"; no clean-worktree or whole-repository claim is made.
Source verification records accompany the generated evidence bundle.

## Implementation completed

`browser_runtime.py` now rejects video playback rates below 1/16 in this bounded
native preview, while preserving the offline model's wider positive-rate range.
An actual Chromium setter probe accepted 1/16, 1/8, 1 and 8 and rejected 1/1000.
The guard is not a cross-browser capability matrix. Fraction-compatible source
and geometry spellings are canonicalized at the compiled transport boundary.

`browser_runtime.js` validates the compiled envelope before media IO or mounting:
versions, time bounds, identities, source references/metadata, ordered spans,
video rates, paired complete geometry and resource guards. Malformed plans now
fail closed. This is not plan authenticity verification or a second source/event
resolver. A startup error can no longer be overwritten with a "playing" state
when outstanding play promises settle; error state also clears readiness.

`test_browser_boundaries.py` adds nine tests: three compiler-boundary tests and
six browser-boundary tests. The latter cover seven malformed-plan subcases,
startup-error injection, explicit shared-source independent clocks, zero-size
container restoration, hold/resize/release/finish, and still/video swaps.
Seven malformed subcases are one unittest, not seven extra tests. The startup
case deliberately injects an error and defers play promises: it is a lifecycle
fault test, not naturally observed decoder-failure evidence.

Deliberate source reuse requires the existing explicit opt-in. Three instances
of one source retain separate native elements, rates, offsets and clocks through
resize; no automatic filler duplication was added. Still/video swaps replace
media only at the authored kind-change boundary, preserving loop wrappers and
the unrelated video's native element. Finish pauses playback and rejects restart.

`run_review_proof.py` runs bounded shards with explicit transport, fresh output
and nonzero exit on failures, errors, skips or timeouts. Default transport is
HTTP; in-memory is never an automatic fallback. `verify_legacy_decoded.py` pins
the preserved original and reproduces complete decoded-stream comparisons.
The original authoring model, normalized engine and FFmpeg renderer are unchanged
by this tranche. No root dependency, workflow or unrelated file was changed.

## Actual completed execution

Environment: Python 3.13.5, Chromium 144.0.7559.96, Playwright 1.57.0,
Pillow 12.3.0 and FFmpeg 7.1.5-0+deb13u1; existing installed tools were used.

The final reconciled runner completed all 12 groups: **90 distinct tests passed,
zero failures, errors, skips or unexpected successes**. This includes 58
model/compiler/renderer tests and 32 browser tests, including explicit fault
injections. All 16 incoming independent-continuity tests were rerun with the
revised production runtime. Earlier 74-test runs and development smoke tests
are not added to the count. The 360 legacy command comparisons remain checks
inside a single unittest. Before-fix failures are retained as diagnostics.

Passing browser runs explicitly used in-memory plan/media IO and injected digest,
with real Chromium DOM, native media clocks, decoding and frame callbacks.
They do not exercise served fetch, WebCrypto, response headers or hosting.

A separate default-HTTP independent-continuity attempt after reconciliation
returned exit 1: one test, one error, `ERR_BLOCKED_BY_ADMINISTRATOR` before
application loading. Policy was not altered. This error is not a pass or skip.
The shared transport text file records the last invocation only; completed-run
summaries and individual traces, not that file, establish each proof's transport.

### Independent resize measurements

Seven positive scenarios passed: N=3/4/5/6 and experimental 7, container-only
resize, and a held-loop scenario. Nine actual browser mutations were rejected:
time reset, same-source reload, source replacement, transient duplication,
transient removal/reinsertion, same-ID replacement, pause, rate change and wrong
layout. Transient mutations occur within one JavaScript task.

The independent observer records native media calls/events, DOM mutations,
video/wrapper/stage identity, clocks, decoded callbacks, geometry and source
pixels without trusting production runtime snapshots or its event log.

Fresh coverage: 42 checkpoints, 529 animation-frame samples, 2,584 sampled loop
observations, 186 decoded source-color checks, 150 moving pixel/decoder comparisons
and five held-pixel comparisons. No unexpected media or relevant DOM event was
recorded in the seven positive armed windows. Maximum sampled clock deviation
was **17.666 ms**, against native time at arming plus elapsed wall time times rate;
configured tolerance is 150 ms. This is not absolute model/frame accuracy.

Armed windows lasted about 1.70–1.77 seconds and deliberately excluded authored
source/hold/release/wrap boundaries, tested separately. One dropped frame was
reported on some videos. There is no zero-drop, indefinite/background playback,
physical orientation, iOS/Safari or hardware-capacity guarantee.

Thirty-five actual browser screenshots were inspected in three contact sheets:
21 independent-continuity and 14 boundary/control screenshots. Labeled synthetic
sources remained visible, moving counters advanced and held sources stayed fixed.
This is sampled inspection, not continuous human viewing, OCR, artist approval
or historical visual fidelity. Pixel fingerprints are change detectors, not
proof of exact frame numbers.

### Fresh rendering and compatibility

Ten small paired exports for 3/4/5/6/experimental 7 were regenerated through the
shared Triptych CLI: 360x640 or 640x360, 24 fps, 144 frames, six seconds, silent.
All ten MP4 hashes match the previous same-toolchain reference. The portable
seven-loop states reproduced both exports byte-for-byte. Decoded-pixel verification
passed again: 30 sampled frames, 150 visible-loop observations, 100 motion
comparisons and 30 rejected blank/wrong-source/frozen negative controls.

Five fresh original/current legacy pairs matched complete decoded video and
applicable decoded audio: clip/none, clip/panel, clip/mix, fixed/none and fixed/mix.
The original was matched to Git blob `6155fa1b8c9d5284c3deda0eaf56b342e47cf1bc`
and staged byte-for-byte inside the generated lane to respect its output guard.
The inherited fixed/mix result remains 123 frames / 5.145996 seconds. An earlier
failed invocation is preserved separately; only the final completed comparisons
are credited. These are synthetic legacy regression checks, not archive recovery.

The earlier eight full-HD reference exports and moving control export were not
regenerated in this tranche. Their prior receipt remains prior evidence. No
cross-toolchain byte-identical encoding guarantee follows from these comparisons.

## Blocked or deferred gates

Historical originals: fresh authorized retrieval attempts did not yield original
bytes. Floating Points V1's indexed locator did not produce a download; Up the
Hill Backwards video metadata resolved but byte transfer failed; TripTicks MOV
metadata resolved without successful private byte transfer. Targeted searches
did not establish the earlier selector/First Circle implementation or canonical
audiovisual Narcissus identity. No similarly named literary file was substituted.
No XML object graph, historical topology, dependency integrity, MOV/MP4 equivalence
or layer-count claim is promoted. No private paths, IDs, signed URLs or raw
archive media were published, and originals were not mutated.

Hosted CI at the tested code commit: `Analyze (python)` run `34027095294`, job
`101469897770`, completed with failure. The job returned no recorded steps;
log retrieval returned 404 `BlobNotFound`. Cause remains unknown, including
whether billing/quota or runner configuration is involved. Local passes do not
make that check green. Later receipt-head checks require their own fresh status.
The draft-skipped CodeRabbit status is not a completed review.

The immediate executable gate is the same suite through default served HTTP in
an authorized environment that permits local navigation. Physical target-device
checks, artist geometry approval, historical-source recovery, audio integration,
live-authoring UI and publication remain separate. No source-text expansion or
synthetic render can substitute for those specific observations or decisions.

## Reproduction and evidence

Run from the incubator with installed prerequisites. Use a fresh output directory:

```bash
python run_review_proof.py --transport http --output runtime-proof/review-http
```

That full HTTP command is a pending gate, not an executed passing run. Do not
change browser policy to run it. The completed final command was:

```bash
python run_review_proof.py --transport in-memory --output runtime-proof/review-reconciled
```

Additional freshly executed proof helpers:

```bash
python verify_legacy_decoded.py
python render_runtime_family.py
python verify_runtime_renders.py
```

Preserve old evidence before regenerating helpers with fixed output locations;
a stale JSON file is never proof that a later failed run succeeded. Count only
completed exit-zero logs and retain failed/setup/navigation attempts separately.

`REVIEW_READINESS_EVIDENCE.json` pins the tested source, completed log hashes,
summary/trace metrics, decoded and portable receipts, and failed HTTP evidence.
The conversation bundle includes actual synthetic media, raw traces, screenshots,
logs and scoped reproduction source with a per-file integrity manifest. Bulk
generated media are not added to Git. Earlier receipts remain historical records;
this addendum does not silently rewrite their measurements or scope.
