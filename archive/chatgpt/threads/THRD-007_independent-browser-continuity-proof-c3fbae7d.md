---
id: THRD-007
title: "Independent Native Browser Continuity Proof (c3fbae7d)"
date: 2026-09-06
tags: ["browser-continuity", "c3fbae7d", "playwright", "chromium", "timing-probe"]
source: "chatgpt-responses--multiple-chats.txt (Lines 668-726)"
---

# Independent Native Browser Continuity Proof (c3fbae7d)

> **Unique ID**:   
> **Date**: 2026-09-06  
> **Tags**: , , , ,   
> **Source**: Extracted from ChatGPT conversation archive (, Lines 668–726)

## Summary & Significance
Implements and verifies browser_continuity_probe.js and test_browser_continuity.py (committed as c3fbae7d4d35). Demonstrates that resize and orientation change do not alter media DOM elements, loop clocks, playback rates, or frame counters.

---

## Transcript Content

Implemented, executed, and committed the independent browser proof to PR #9 as **`c3fbae7d4d354de0306e62f123c77eadddc4565e`**. The PR description and evidence comment now distinguish the new results from earlier render evidence. **PR #9 remains open and draft; nothing was merged or deployed.** 

**The demonstrated result is bounded native-browser continuity—not yet end-to-end served-browser or physical-device continuity.**

:chatgpt-content-reference{index="11"} · :chatgpt-content-reference{index="12"} · :chatgpt-content-reference{index="13"}

## What I implemented

The new `browser_continuity_probe.js` observes the browser independently of the runtime’s own snapshots and event log. It records actual media method/setter calls, native media events, DOM additions and removals, persistent video/wrapper identities, native playback clocks, decoded-frame callbacks, displayed geometry, and decoded synthetic-source pixels.

The accompanying `test_browser_continuity.py` checks those observations against the expected loop identities, sources, rates, held state, and authored layout. **The production runtime, compiler, authoring model, renderer, and dependencies were unchanged.** The commit contains those two test files, two evidence records, and an addition to `INCUBATION.md`. 

This strengthens the earlier proof in an important way: a video could disappear and reappear between screenshots while spaced snapshots still looked correct. The new observer records transient mutations—including removal/reinsertion within a single JavaScript task.

## What actually passed

| Completed final test group | Passing tests |
|---|---:|
| Existing model, authoring, renderer, and browser-plan tests | 55 |
| Existing native-browser tests | 10 |
| New positive continuity scenarios | 7 |
| New injected-failure detection tests | 9 |
| **Distinct passing tests** | **81** |

Those completed runs had zero failures, errors, or skips. **Separately, two HTTP attempts failed before application loading; they are preserved as errors and are not included as passing results.** 

The seven positive scenarios cover **N=3, 4, 5, 6, and experimental 7**, container-only resizing within an unchanged desktop viewport, and resizing while one loop remains held and the others advance. The viewport sequence was:

```text
390×844 → 1280×720 → 900×1300 → 844×390 → 700×700 → 390×844
```

Across those windows, loop identities, sources, native video elements, wrappers, and independent playback clocks were preserved. The held loop retained its frame while the other loops continued. No unexpected media command/event or relevant DOM mutation was recorded. 

I also deliberately injected **time resets, same-source reloads, source replacement, transient duplication, transient removal/reinsertion, same-ID element replacement, pauses, playback-rate changes, and incorrect geometry**. The same verifier rejected all nine. These are executed negative controls—not merely assertions that the test should detect those failures. 

## What the measurements establish—and their limits

The seven positive traces contain **42 checkpoints, 539 animation-frame samples, 2,631 sampled loop observations, 186 decoded source-color checks, and 150 moving pixel/decoder comparisons**. Twenty-one actual browser screenshots were inspected in two contact sheets. The bundle contains the raw traces, screenshots, final logs, synthetic fixtures, scoped source, patch, and hash manifest. 

The maximum sampled native-clock deviation was **12.996 milliseconds**, measured against the clock at arming plus elapsed wall time multiplied by each loop’s playback rate. The configured tolerance is 150 milliseconds. This is **not** an absolute model/frame-accuracy measurement, nor a claimed improvement over the earlier model-error metric. 

The armed resize windows lasted approximately **1.69–1.79 seconds** after startup settled. They deliberately excluded scheduled source, hold/release, and trim boundaries; the existing control and wrap tests were rerun separately. Some videos reported one dropped frame. Consequently, the receipt makes no frame-exact, zero-drop, indefinite-playback, or background-tab guarantee. The eight offline reference exports and five full historical decoded-output comparisons were not rerun or relabeled as new evidence. 

## What remains open

**Served HTTP/WebCrypto:** both attempted HTTP tests encountered `ERR_BLOCKED_BY_ADMINISTRATOR` before the application loaded. I did not change browser policy. Successful runs explicitly used in-memory plan/media delivery and an injected digest function, while retaining real Chromium DOM, native playback clocks, and video decoding. That establishes native-browser behavior, not the complete served-loading path. Physical iOS/mobile rotation also remains untested. 

**Hosted CI:** the new commit’s `Analyze (python)` check failed—run `34026330350`, job/check `101467837281`. Its cause has not been established, and local success has not been represented as hosted-CI success. 

The next execution gate is the checked-in suite through HTTP in an authorized environment that permits localhost navigation:

```bash
cd incubator/triptych-video-canon
PORTVS_BROWSER_TRANSPORT=http \
  python3 -m unittest -v test_browser_continuity
```

That command is documented as **an outstanding reproduction gate, not an executed passing result**. Target-device checks and hosted CI remain separate unresolved gates. PR #9 now records the native continuity evidence actually obtained without prematurely declaring overall review readiness.
