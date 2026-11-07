# Studio as an evolving audiovisual ecosystem

Status: proposed design, pending owner approval. No product implementation or
production change is included. Numerical defaults below are proposals, not
owner-approved requirements.

## Intent

The Studio should keep moving while someone interacts with it. Short Live Photo
clips may repeat forward or move forward and backward as a boomerang. Each clip
has a finite residence: newcomers arrive, coexist, gain or lose prominence, and
eventually leave. Sound behaves like a small competing ecosystem, with changing
foreground voices and spatial relationships rather than an equal-volume pileup.

The owner's reference is Game of Life. Use local interaction, birth, aging,
competition, recovery, and departure as compositional rules; a literal binary
Conway grid is not a requirement.

## Evidence and current behavior

An owner-supplied 77.7-second iPhone recording was inspected locally. Sampled
frames show partial disappearance near 6 seconds and a black stage near
34 seconds during panel-count interaction. The recording and its Photos-picker
contents remain outside Git and deployment artifacts.

Source inspection and instrumented production playback establish a separate,
repeatable cause: every edit invokes a complete runtime initialization. First
sound activation replaced both video elements and reset the composition clock
from 0.925 to 0.011 seconds. Tapping one panel replaced both videos; the untouched
panel retained its clip but restarted from 0.918 to 0.012 seconds. Those actions
took about 0.44 and 0.40 seconds in single Chromium emulation runs. These are
causal observations, not physical-device performance benchmarks.

`browser.studio.js` freezes current frames into canvases, then `launch()` calls
`runtime.initialize()`. Initialization destroys media nodes and the audio graph.
The current selection repeats indefinitely. There is no autonomous succession,
and `style.reverse` reverses panel order, not playback direction.

Earlier Linux WebKit probes also found frozen decoded frames after some authored
loop seeks, although clocks continued. Standalone videos survived equivalent
seeks. Treat this as an unresolved Studio/media interaction; do not claim it is
only a Linux artifact or infer a Safari pass from advancing clocks.

## Approaches

| Approach | Benefit | Cost or limitation |
| --- | --- | --- |
| Periodic whole-scene reshuffle | Smallest change | Preserves global restarts and cannot provide fluid independent lives |
| Precompile all population and mix changes | Strong exact timeline/export parity | Broad compiler changes; interactive interventions remain expensive |
| Persistent live session with independent clip residents | Preserves motion and supports interactive succession and competition | Requires a live controller, bounded media preparation, and new verification |

Recommend the persistent live session. Retain the existing authored compiler and
runtime for authored plans and exports. The default generative Studio uses the
live session, while library admission, clip identity, layout families, mute,
reduced-motion behavior, and file privacy retain their existing contracts.

The Lab's pure `Scheduler` in `lab/app/engine.js` offers stagger, recency,
cooldown, novelty, and neighbor affinity. Its player demonstrates persistent
audio buses and live crossfades. Reuse those ideas without importing the Lab
player wholesale: it has a different manifest, creates two players per panel,
and waits for decoded data before requesting playback.

## Continuous playback and interaction

- A resident owns its video element, playback clock, and audio connection until
  departure. An edit elsewhere does not replace or seek it.
- Create one AudioContext after the first real gesture and retain it. Sound
  activation and mute/unmute change the audio graph's gains, never the videos.
- Prepare one incoming resident while the outgoing clip remains moving. Admit
  the replacement only after an actual decoded frame is ready, then crossfade
  both moving images over approximately 500 milliseconds.
- Limit preparation to two fetches and one decoding probe at a time. Allow at
  most one extra decoder beyond the visible population during a transition.
  Bound retained source bytes and variants; retain the existing cache limit as
  a ceiling, not a target to fill with active decoder probes.
- Coalesce repeated edits to the latest intent. A pending control shows its
  requested state without falsely declaring that new media is already playing.
  Preparation failure leaves existing media playing and chooses another clip.
- A panel tap changes that panel only. Population changes animate layout boxes
  while preserving surviving video elements. Rotation remaps the same residents.
- Use native forward looping in live mode. Do not reconstruct a fixed timeline
  or seek every video on each loop boundary. Pause freezes the session clock;
  returning from a hidden tab resumes without a burst of missed events.

## Rhythm and finite lives

Proposed default: an evolving ecosystem with occasional bursts and quiet phases.
This is a slow compositional pulse, not mandatory synchronization to a drum beat.

- Start with two clips. On a phone, grow toward three or four; on a larger screen,
  toward four to six. Existing manual panel-count choices remain explicit user
  overrides, including lower counts. Never automatically grow to twelve on a phone.
- Offer an arrival or departure every 3–6 seconds, with seeded variation and
  occasional skipped opportunities. At most one resident changes per opportunity.
- Give each clip roughly 3–7 completed loops and ordinarily 10–24 seconds of
  residence. Schedule retirement at the next loop boundary, with a 30-second
  target ceiling; long clips may fade mid-pass there. Both boomerang legs count
  as one loop. The bounds are tuning defaults, not export timing semantics.
- A newcomer fades in, gains a brief chance to be heard, settles, then ages.
  Older or persistently suppressed residents are more likely to retire. A clip
  does not disappear merely because one audio sample was quiet.
- Keep a floor of two residents unless the user selects one or fewer than two
  eligible sources exist. A departure may open space temporarily, then a new
  resident fills it. No mass extinction or complete black scene.
- Add a cooldown so a departed logical clip cannot immediately return. Forward
  and boomerang variants share that logical identity and cannot coexist as duplicates.
- Let population density rise and fall over phrases of roughly 30–45 seconds.
  Availability and decoder readiness may delay births; the scheduler never
  forces an unready clip onto the screen to meet a deadline.
- Continuity and the population floor outrank retirement deadlines when no
  eligible replacement is ready. Keep the existing video and clock, mark its
  retirement overdue, and retry a bounded number of other candidates. Do not
  reset its age to hide failure. With only one or two eligible clips, show the
  limited pool in settings and retain unique residents rather than manufacturing
  duplicates or repeatedly removing and readmitting the same clip.
- A manual count sets a desired population and disables automatic phrase-density
  changes. Scheduled departures may temporarily undershoot it by one, subject to
  the floor. Shuffle preserves the override; choosing an Activity preset restores
  automatic density. Family changes choose the nearest supported count as today.
  Controls distinguish requested count from a still-preparing admission.

For example: A and B begin; C enters around 4 seconds; D enters around 9;
A recedes and leaves around 16; E enters around 20 while B, C, and D keep their
own playback positions. This illustrates overlap, not a fixed repeated script.

## Competition for sound and space

Each resident carries energy, age, fatigue, and recent foreground time. Neighbors
come from the actual layout's adjacent panels, including after rotation.

- Evaluate interaction on a fixed simulation tick independent of rendering speed.
  Neighbor activity suppresses rivals; a brief newcomer bonus and recovery while
  quiet prevent permanent domination. Foreground residence creates fatigue.
- Use recorded clip envelopes normalized to that clip's own range, plus novelty
  and age. Raw amplitude alone must not make the loudest recording win forever.
  Do not invent loudness metadata when the library lacks it: generate compact
  envelopes and loudness measurements with the media derivatives.
- Usually maintain one foreground voice and one secondary voice. Other residents
  remain quieter, rather than being chopped on and off every tick. Silence in
  the source stays silence; no new synthetic music is implied.
- Ramp gains smoothly over 300–800 milliseconds, conserve the total gain-energy
  budget, and retain the master volume and limiter. User mute is authoritative.
  Existing source sound eligibility rules stay in force.
- Pan according to screen position. Competition affects acoustic prominence first.
  In strips, a sustained winner may gain a bounded share of screen area through
  a slow layout change; authored layouts keep their authored geometry. No panel
  expands or shrinks on every audio transient.
- Decisions use seeded randomness and a deterministic simulation clock. The same
  seed reproduces logical decisions given the same admitted media and interaction
  events; network timing can delay admissions, so identical wall-clock presentation
  across devices is not promised. Hidden-tab time does not age residents.

This combines emergence with limits: power can shift, but no permanent winner,
unbounded volume, frantic resizing, or uncontrolled decoder population is allowed.

## Forward loops and boomerang

Prepare browser-friendly H.264 derivatives for the existing public library.
Forward mode plays the source repeatedly; boomerang plays a prepared forward
then reverse sequence through an ordinary positive-rate video element. Remove
duplicated endpoint frames and measure the actual visual duration. Do not use
negative playbackRate or frame-by-frame backward seeking on the phone.

Proposed sound policy: keep the original sound moving forward under either
visual direction, with short seam fades. Reversed speech is not enabled by default.
The boomerang derivative can contain two forward audio passes, so it does not
need a second live audio decoder solely for reversal.

Extend the library manifest with optional validated variant records, separate
content hashes, byte sizes, durations, and compact sound envelopes. Preserve
logical identity and backwards compatibility. Publish only listed derivatives,
with the same archive exclusion and hash checks as the existing deployment.

Initial delivery covers the existing public library. Personal files remain
local and forward-looped unless a compatible boomerang variant is already
provided. Reliable on-device reversal of arbitrary uploads is a separate cost;
never silently upload them for conversion. This scope needs owner confirmation.

## Controls and scope

Keep the main toolbar compact: play/pause, shuffle, count, family, sound, and
add-files retain their purpose. Put Motion (Forward / Boomerang / Mixed) and
Activity (Calm / Restless) in a small accessible settings surface. Mixed mode
chooses motion per resident, not by reversing an already-playing decoder.
The proposed initial default is Mixed with moderate activity.

Shuffle starts a succession wave rather than blacking out and rebuilding the
whole scene. Reduced motion still requires an explicit start and avoids layout
animation. Existing imported-file validation and privacy stay intact.

This work does not redesign the separate Lab, change authored exports, upload
private media, build a literal Conway display, or promise all iPhone models can
decode twelve simultaneous clips. Exact scoring coefficients, crossfade easing,
module boundaries, and bounded cache sizing are implementation choices to tune
against the acceptance evidence.

## Acceptance and release evidence

1. Reproduce the recording's sequence: shuffle, single-panel swap, count changes,
   family changes, sound, rotation, file-picker return, and fullscreen. Untouched
   residents retain element identity and playback progression through every edit.
2. Sample decoded image changes across multiple loop boundaries, not only
   currentTime. Verify forward and boomerang motion and endpoint behavior.
3. A hands-off run visibly produces staggered births, overlapping lives, and
   departures without a global reset. Test population bounds, residence deadlines,
   overdue-retirement handling, limited pools, and manual population overrides.
4. Measure competing gains and output waveform: prominence changes, formerly
   suppressed voices recover, and sustained loud sources cannot win indefinitely.
   Mute, master volume, and limiting still work.
5. Throttle network and force a missing/corrupt/undecodable candidate: current
   playback survives, preparation stays bounded, and failed clips cannot stall
   every panel. Repeated taps do not grow a queue or leak decoders/audio nodes.
6. Test pause/resume, reduced motion, background/foreground, portrait/landscape,
   and a sustained ten-minute run for memory and decoder stability.
7. Verify Chromium and WebKit, then the owner's physical iPhone Safari, recording
   its actual model, iOS/Safari version, and playback settings with the evidence.
   Passing that device establishes that tested baseline, not all iPhones. Older
   supported-device targets can be added explicitly. A desktop WebKit
   clock advancing does not count as physical-device playback proof. Keep the
   current release available until the replacement has measured evidence.

Deliver in this order: persistent playback and bounded preparation; forward and
boomerang assets; finite lives and staggered rhythm; competing sound and restrained
space changes; then phone verification and deployment. Do not add a changing
population on top of the current whole-scene restart mechanism.
