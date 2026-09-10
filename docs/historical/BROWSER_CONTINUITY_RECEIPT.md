# Browser continuity proof — September 6, 2026

Proof ID: `PR9-NATIVE-RESIZE-2026-09-06`.
Scope: `organvm/portvs`, draft PR #9, issue #8, this incubator only.
Reconciled starting head: `00d3788260e1b8d3d76cf030dd9b69418059101b`.
This is an execution addendum to `RUNTIME_RECEIPT.md`, not a replacement for its
historical record. The supplied five-commit/38-test description was older than
that live head, which already contained a native runtime and 65 scoped tests.

**Result:** bounded native Chromium resize continuity was independently observed.
Served-HTTP/WebCrypto loading and physical-device orientation remain unverified.
PR #9 remains draft; overall review readiness, hosted-CI success and release
readiness are not claimed.

## What changed

`browser_continuity_probe.js` is a test-only observer installed before runtime
execution. It does not read `compositionRuntime`, its snapshots or its event
log. It records actual media setter/method calls, native media events and DOM
mutations, retaining video, wrapper and stage identity with opaque tokens. It
observes native animation-frame clocks and decoded-video callbacks. Checkpoints
also capture authored CSS geometry, source-background pixels and decoded-frame
fingerprints. The probe forwards native methods/setters; playback is not mocked.

`test_browser_continuity.py` reuses the existing fixture and transport, not its
continuity assertions. Its oracle checks exact N, unique loop IDs and source
URLs, persistent native elements/wrappers, stable playback rates and sources,
advancing clocks/decoded frames, correct authored geometry and decoded source
colors. A separately generated held-loop fixture verifies that loop 1 remains
held while the other two advance through the same viewport changes.

Nine actual browser mutations test the same oracle: time reset, same-source
reload, source replacement, transient duplication, transient removal/reinsertion,
same-ID node replacement, pause, rate change and incorrect layout. All nine were
rejected. Transient add/remove actions happen within one JavaScript task, so the
mutation observer adds coverage beyond spaced snapshots. The source-replacement
fault is not a claim that a live reroll UI was built.

Production `browser_runtime.js`, its Python compiler, the authoring model,
normalized composition engine, FFmpeg renderer and dependencies are unchanged.
No alternative source-selection engine or per-N application was introduced.

## Actual execution and evidence

Environment: Python 3.13.5; Chromium 144.0.7559.96; Python Playwright 1.57.0;
Pillow 12.3.0; FFmpeg 7.1.5-0+deb13u1. Existing installed tools were used.

The execution source was a scoped snapshot whose 21 upstream files were checked
against the live Git blob hashes at the starting head. A network clone was not
available. It was not a full checkout: `git status --short --branch --ahead-behind`
reported that there was no Git repository. No local Git-clean or whole-repository
verification claim is made. The delivered source-verification manifest records
those checks; branch writes use parented commits and a non-forced ref update.

Both an existing continuity test and the new independent test were attempted
with default HTTP transport. Each exited 1 with one error:
`ERR_BLOCKED_BY_ADMINISTRATOR`, before application loading. The two error logs
are retained separately. Policy was not modified and there is no automatic
fallback. These attempts did **not** pass and are not counted among passing tests.

Completed native runs explicitly selected `PORTVS_BROWSER_TRANSPORT=in-memory`.
Only plan/media byte IO and the digest function are injected from local files;
Chromium DOM, video decoding, native media clocks, gestures and frame callbacks
are real. This does not exercise served fetch/WebCrypto, HTTP headers or hosting.

| Completed final run group | Passed | Failures/errors/skips |
| --- | ---: | ---: |
| Independent browser groups a–d | 16 | 0 / 0 / 0 |
| Existing model/authoring/renderer/plan group | 55 | 0 / 0 / 0 |
| Existing browser groups a–c | 10 | 0 / 0 / 0 |
| Distinct tests in these completed runs | 81 | 0 / 0 / 0 |

The 16 new tests are seven positive scenarios and nine fault injections. The
65 existing tests were rerun, including native hold/release, changed-source
reroll, swap, move, trim wraps, corrupt-media rejection and loading-time resize.
The 360 legacy segment-command comparisons remain checks within one unittest,
not 360 additional tests. Development smoke runs are not added to the count.
The eight offline reference exports and five full historical decoded-output
comparisons were **not** rerun in this tranche.

## Measured resize coverage

N=3, 4, 5, 6 and experimental 7 each passed six viewport shapes:

`390x844 -> 1280x720 -> 900x1300 -> 844x390 -> 700x700 -> 390x844`.

Container-only coverage held the viewport at `1600x1000` while the stage changed:

`390x844 -> 844x390 -> 450x900 -> 900x450 -> 700x700 -> 390x844`.

The held-loop scenario used the six viewport shapes. Square geometry exercised
the existing landscape tie rule. These are desktop Chromium dimension changes,
not a physical screen-orientation event or an actual iPhone/Safari test.

Across seven positive traces: **42 checkpoints, 539 animation-frame samples,
2,631 sampled loop observations, 186 decoded source-color checks, 150 moving
pixel/decoder comparisons and five held-pixel comparisons**. No unexpected media
command/event or relevant DOM mutation was recorded during these armed windows.
Each moving loop retained its own source, native element and clock; the held loop
retained its frame while the other loops advanced.

Maximum sampled clock deviation was **0.012996 seconds** against the native
clock at arming plus elapsed wall time multiplied by that loop's playback rate.
This is not an absolute model/frame-accuracy measurement. The configured clock
tolerance is 0.15 seconds, held-clock tolerance 0.001 seconds, geometry tolerance
1.1 CSS pixels and synthetic source-color tolerance 12 per RGB channel.

Armed windows lasted approximately **1.69–1.79 seconds** after initial playback
settled. The tests deliberately exclude authored source/hold/release/trim
boundaries inside these windows; those controls have separate existing tests.
One dropped frame was reported on some videos. No frame-exact, zero-drop,
indefinite, background-tab or hardware-capacity guarantee is inferred.

Twenty-one actual browser screenshots were inspected in two contact sheets:
all five counts, container-only resize and the held-loop scenario, each before,
during and after portrait/landscape changes. The labeled sources remained
recognizable; moving counters progressed and the held source stayed fixed.
This is sampled visual inspection, not continuous human viewing. The small
canvas fingerprints are non-cryptographic change detectors, not OCR or proof of
an exact decoded frame number. Checks concern synthetic fixtures, not archives.

`BROWSER_CONTINUITY_EVIDENCE.json` records per-case metrics, test/runtime hashes,
final log hashes and all 16 trace hashes. The accompanying conversation bundle
contains those raw JSON traces, screenshots, logs, synthetic media and scoped
reproduction sources. Generated bulk evidence/media are not added to Git.

## Reproduction

Run from this incubator with the installed prerequisites. Use a fresh evidence
directory for each independent execution: archive or rename an existing
`runtime-proof/evidence/independent-continuity` directory first. A prior JSON
file is never evidence that a later failed invocation passed. Count only the
specific completed exit-zero logs; preserve setup/navigation failures separately.

The default transport is HTTP. In a permitted local-navigation environment run:

```bash
PORTVS_BROWSER_TRANSPORT=http python3 -m unittest -v test_browser_continuity
```

That full HTTP command is a reproduction gate, **not an executed passing run**.
Do not change browser policy to make it work. The executed in-memory new-test
shards were the following (the same shards can be used for HTTP by changing
only the explicit transport value):

```bash
export PORTVS_BROWSER_TRANSPORT=in-memory
python3 -m unittest -v \
  test_browser_continuity.ContinuityTests.test_3 \
  test_browser_continuity.ContinuityTests.test_4 \
  test_browser_continuity.ContinuityTests.test_5 \
  test_browser_continuity.ContinuityTests.test_6
python3 -m unittest -v \
  test_browser_continuity.ContinuityTests.test_7_experimental \
  test_browser_continuity.ContinuityTests.test_container_only \
  test_browser_continuity.ContinuityTests.test_held_loop_survives_resize \
  test_browser_continuity.ContinuityTests.test_reject_wrong_layout
python3 -m unittest -v \
  test_browser_continuity.ContinuityTests.test_reject_time_reset \
  test_browser_continuity.ContinuityTests.test_reject_same_source_reload \
  test_browser_continuity.ContinuityTests.test_reject_source_reroll \
  test_browser_continuity.ContinuityTests.test_reject_transient_duplicate
python3 -m unittest -v \
  test_browser_continuity.ContinuityTests.test_reject_transient_removal \
  test_browser_continuity.ContinuityTests.test_reject_same_id_replacement \
  test_browser_continuity.ContinuityTests.test_reject_pause \
  test_browser_continuity.ContinuityTests.test_reject_rate_change
python3 -m unittest -v test_composition_model test_authoring_contract \
  test_composition_render test_browser_runtime.PlanTests
```

The three existing native-browser shards are listed in `RUNTIME_RECEIPT.md`;
they were also rerun here. Final logs are `final-independent-a.log` through
`final-independent-d.log`, `final-regression-unit.log` and
`final-existing-browser-a.log` through `final-existing-browser-c.log`.
`http-attempt.log` and `http-independent-attempt.log` contain the two failed
HTTP attempts. The shared legacy `browser-transport.txt` records the last attempt
only; it must not be used to relabel earlier runs. Each new trace embeds its own
transport, browser version and source hashes.

## Remaining gates and boundaries

The next execution gate is these tests through default served HTTP/WebCrypto in
an authorized environment that permits localhost navigation, followed by actual
target-device/browser checks. No result in this receipt closes either gate.
Current hosted CI must be assessed independently; local success does not make
CodeQL or required PR checks green. No review-ready transition was requested.

All geometry remains synthetic engineering work; seven remains experimental.
Artist review, historical-original recovery, audio integration, live-authoring
UI, private-media custody and publication authorization are unchanged. No merge,
deployment, release, approval, owner promotion or unrelated change occurred.
