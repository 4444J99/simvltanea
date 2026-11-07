# Studio ecosystem implementation plan

> For agentic workers: execute the tasks with test-first regression proofs and a
> final independent branch review. Keep implementation decisions in the ledger.

**Goal:** Keep Studio playing continuously while clips enter, compete for sound
and space, and leave; publish forward and boomerang assets without archive files.

**Architecture:** A Studio-only live session owns persistent media decks and a
pause-aware simulation clock. The authored composition runtime and exporter keep
their existing timeline semantics. Library assets retain content-addressed paths.

**Tech stack:** Vanilla JavaScript, Web Audio, Python, FFmpeg, Playwright.

**Spec:** [Issue #89](https://github.com/4444J99/tool-video-loop-compositor/issues/89)
and its owner-supplied amendment; [original design](2026-11-07-studio-ecosystem-design.md).

## Global constraints

- Preserve existing layout families, uploaded files, manual counts, seed URLs,
  mute, volume, reduced motion, pause, rotation, and authored export behavior.
- A slot edit must not pause, seek, reload, or replace an untouched resident.
- One global preparation/crossfade lease; outgoing media loops until incoming
  decoded-frame readiness. Unload retired sources while retaining video nodes.
- Personal files stay local. Only the admitted public library enters deployment.
- Keep the five-file static site contract by bundling browser source modules.
- Record automated browser evidence separately from physical iPhone acceptance.
  The latter requires the owner's device and remains an explicit release gate.
- Do not merge this PR without the owner's explicit merge authorization.

## Review focus

Rapid repeated interactions, hidden/resumed tabs, decoder/play rejection, short
or silent audio, and manual counts beyond four must retain useful playback.
Tests below cover these cases; physical Safari and listening remain manual gates.

## Task 1: Persistent live playback

Files: `src/simvltanea/browser/browser.live.js`, `browser.studio.js`,
`browser_studio.py`, `test_browser_live.py`, `test_browser_studio.py`.

Interface: `SimvltaneaLive.Session(stage, options)` exposes
`reconcile({plan, items, playing})`, `unlock()`, `setSound({enabled, volume})`,
`start()`, `play()`, `pause()`, `snapshot()`, and `dispose()`.
Its `nodes`, `plan`, and `audio` keep Studio's inspectable runtime interface.

- [ ] Add failing browser regressions for first sound and single-slot replacement:
  sibling node identity, frame progress, clock and audio context persist.
- [ ] Implement persistent decks, serialized priming, outgoing-loop fallback,
  cancellation, visibility handling, and a simulation clock independent of audio.
- [ ] Wire Studio controls and generated voices to the live session; package it
  as Studio's `runtime.js` without changing authored playback.
- [ ] Verify load, rapid shuffle, count/family changes, failed preparation,
  muted startup, sound, pause, rotation, and multi-minute decoded-frame progress.

## Task 2: Verified boomerang assets

Files: `tools/media/build_boomerangs.py`, adjacent tests, library validators and
publishing integration as required by the verified manifest contract.

- [ ] Add failing CFR, VFR, silent, short-audio, endpoint and sample-count tests.
- [ ] Normalize to 30 fps / 48 kHz; use exact frame/sample counts and explicit
  mux timing. For M forward frames and K overlap frames, N = 2M - 2 - K.
- [ ] Preserve logical source identity, content hashes, dimensions, tags and
  existing forward media; add validated boomerang variants and energy metadata.
- [ ] Verify actual decoded frame timestamps and stream durations, rather than
  treating metadata averages or encoder flags as proof of gapless playback.

## Task 3: Finite lives and pacing

Files: `src/simvltanea/browser/browser.ecosystem.js`, adjacent tests and Studio
integration. Consume the live session's simulation time and transition queue.

- [ ] Add deterministic tests for lifetime quantization, cooldown, starvation,
  bounded preparation, rapid intent replacement, and tiny/manual populations.
- [ ] Implement steady, sparse and burst regimes with integer-loop extensions;
  keep the lease and minimum lifetime guards above burst scheduling priority.
- [ ] Implement departures and births with a visible minimum population, while
  explicit manual panel counts retain their meaning.

## Task 4: Ecological sound and territory

Files: `browser.ecosystem.js`, `browser.live.js`, adjacent browser/audio tests.

- [ ] Test silence, coherent peaks, impulses, gain changes, fatigue/recovery,
  neighbor inhibition and bounded spring geometry with actual browser rendering.
- [ ] Normalize nonnegative eligible weights, guard zero denominators, use
  conservative coherent gain bounds, and verify the final audio output stage.
- [ ] Animate supported generative geometry; preserve authored/custom layouts.
- [ ] Add proof telemetry without exposing private filenames or tags.

## Final verification and delivery

- [ ] Run affected browser, media, publishing and authored-runtime regressions;
  required repository checks and the full verification suite.
- [ ] Independently review the branch; fix substantive findings with regressions.
- [ ] Update PR #88 with exact head, commands, measured evidence and open gates.
- [ ] Publish a reviewable preview containing the website and admitted library.
  Record physical iPhone acceptance separately before production merge/rollout.
