# Effects Lab implementation plan

## Goal and current authority

Build a playable environment for the November 7 artistic direction: layered
image effects, a swept comb filter on each voice, presence-driven low/high-pass
filtering, and separate audio/video repeat speeds and lifetimes after a shared
launch. A picture can disappear while its sound keeps looping and fading.

The current request authorizes implementation and a private playable environment.
It does not establish approval to merge the existing Studio branches, replace
the public production deployment, or declare physical iPhone acceptance.

## Design

Add an Effects Lab page to the existing compositor's deterministic static
staging. Keep the existing Studio session and its in-progress presence work.
The lab uses a canvas for ordered visual blending, muted native video tracks,
separate audio media elements for imported clips, and Web Audio for filters.
Starter material is generated locally: three animated compositions and three
synthetic sound loops. Imported media remains on the visitor's device.

Alternatives considered: extend the Studio's two-deck handoff directly; create
a separate unrelated application; or add a dedicated instrument page sharing
the compositor's staging and master protection. The dedicated page is selected
as an implementation decision because audio tails have a different ownership
model from the existing foreground decks, and the user needs direct controls.

The interface has a large live stage, a reorderable layer list, per-layer
Picture / Sound / Motion controls, a pair of independent envelope indicators,
transport, master level, automatic succession, presets, and local settings
save/import/export. It works on phone widths as well as desktop. There is no
server media upload or account integration.

## Component contracts

### Pure model: `browser.lab_model.js`

Global/CommonJS export `SimvltaneaLabModel`:

- `DEFAULTS`, `BLENDS`, `FILTER_MODES`, `PRESETS`, `MAX_CLIPS = 4`.
- `normalizeSettings(partial, base=DEFAULTS)` returns a new bounded flat object.
- `envelope(age, life, attack)` returns a 0..1 rise-and-fall value, exactly zero
  after life. Attack is clamped to at most half of life.
- `phase(age, life, attack)` returns `waiting`, `entering`, `leaving`, or `ended`.
- `combFrequency(time, settings, offset=0)` gives a logarithmic triangle sweep
  between `combLow` and `combHigh` over `combPeriod` seconds.
- `filterTargets(presence, phase, settings, sampleRate=48000)` returns
  `{lowpassHz, highpassHz, bandpassHz, bandpassQ, bandpassEnabled}`. Presence mode
  opens low-pass during entrance and thins through high-pass during departure;
  reverse presence swaps those roles. Manual modes use `cutoff`.
- `nextRate(current, wander, random=Math.random)` changes a rate multiplicatively
  within 0.25..3; wander zero preserves it. Audio/video use distinct draws.

Settings (defaults; bounds): `blend='screen'`; `opacity=.85` (0..1);
`brightness=1` (0..2); `contrast=1.15` (0..3); `saturation=1.1` (0..3);
`hue=0` (-180..180); `blur=0` (0..12); `invert=0` (0..1);
`attack=2` (.1..10); `videoLife=24` (4..120); `audioLife=36` (4..180);
`audioGain=.65` (0..1); `filterMode='presence'`; `cutoff=1800` (40..16000);
`resonance=.8` (.1..8); `combMix=.45` (0..1); `combFeedback=.35` (0...75);
`combLow=100` (40..2000); `combHigh=2400` (100..8000);
`combPeriod=8` (.5..30); `videoRate=1`, `audioRate=1` (.25..3);
`videoWander=.12`, `audioWander=.2` (0...5); `preservePitch=false`;
`hold=false`; `videoEnabled=true`; `audioEnabled=true`.
Comb bounds must satisfy low <= high; bounds and enum choices are validated.
Filter modes: `presence`, `presence-reverse`, `lowpass`, `highpass`, `bandpass`,
`off`. Blends: `normal`, `screen`, `multiply`, `overlay`, `soft-light`,
`difference`, `exclusion`, `color-dodge`, `lighten`, `darken`.

### Playback: `browser.lab_engine.js`

Export `SimvltaneaLabEngine.Engine` and `createVoiceGraph(context, destination)`
(the graph exposes input, lowpass/highpass/bandpass, delay, feedback, wet/dry,
gain, apply(settings, presence, phase, time, offset), dispose).

`new Engine(canvas, {onChange, onError}={})`; `addClip(source, settings={})`
returns Promise<string>; source is `{id?, name, kind:'demo'|'video'|'audio',
url?, demo?:'tide'|'prism'|'grain', ownedURL?:boolean}`. Native media is loaded
before admission; a failed import leaves existing voices untouched.

Methods: async `play()`, `pause()`, async `launch(id)`, `set(id, partial)`,
`remove(id)`, `move(id, delta)`, `setMaster({volume?, muted?})`,
`setSequence({enabled?, interval?})`, `snapshot()`, `dispose()`.

Snapshot: `{playing,time,volume,muted,sequence:{enabled,interval},clips:[
{id,name,kind,active,settings,age,error,video:{age,position,rate,loops,presence,
active},audio:{age,position,rate,loops,presence,active,combHz}}]}`.

Add order is bottom to top; move +1 brings forward. Automatic succession launches
the next inactive clip at the selected interval (default 8 seconds), never
restarting an active audio tail. A manual launch deliberately restarts that pair.
First play launches the first ready clip; user can launch additional layers.
Each repeat independently chooses a new bounded rate. Pause/hidden visibility
freeze both clocks; resume never requeues or resynchronizes the pair. Editing
settings never recreates media. Deleting/disposal releases nodes and blob URLs.
At most four admitted pairs. Three starter sources use procedural canvas loops
and generated AudioBuffers, clearly identified as starter material.

Use the existing `SimvltaneaLiveAudio.createMasterBus` with restrained initial
volume (.45), per-voice headroom, and smooth parameter updates. A finite
feed-forward delay comb sweeps with per-voice phase. Geometric tap decay gives
the resonance control a bounded response. The settings key `combFeedback` is
retained internally but does not claim an infinite feedback circuit. This
choice avoids the [Web Audio](https://www.w3.org/TR/webaudio/) render-quantum
minimum on feedback delay cycles,
which would otherwise prevent the requested upper sweep frequencies.
The master ceiling is sample protection, not a true-peak claim.

### Interface and staging

`browser.lab_ui.js` owns interface, not playback. `browser_lab.py` owns the HTML
and CSS strings, `lab_files()` returning `lab.html`, `lab_model.js`,
`lab_engine.js`, `lab_ui.js`, and `lab_audio.js`. Lab HTML loads those scripts in
that order (audio before engine). HTML/CSS are not separate files under `src/`.

Root integrates lab files into `studio_files()` and adds an Effects Lab link.
A separate private Sites source receives the exact staged lab bytes, with
`lab.html` copied to `index.html`; source provenance records the compositor
commit. No public Studio deployment changes.

## Work and verification

- [x] Pure model with meaningful tests for finite bounds, independent rate draws,
  asymmetric envelopes, pass direction, and logarithmic comb reversal.
- [x] Independent playback engine and actual audio signal tests; protect pause,
  failed media, sound after picture departure, same-gesture launch and cleanup.
- [x] Responsive controls, presets, local settings round-trip and imports; show
  real rates, loop counts and moving filter position from engine snapshots.
- [x] Stage lab alongside Studio, validate generated assets and naming.
- [x] Use the supported browser preview to verify transport, real filter changes,
  layer order/blends, differing loop rates and audible tails; check mobile layout.
- [ ] Independent review, affected regressions, preserved feature branch,
  private playable deployment, verified delivery receipt with exact revisions.

## Verification observed on November 7

The complete Effects Lab suite passed 42 tests. The affected Studio staging and
library publisher suite passed 34 tests, including two lab integration checks.
Actual rendered signals verify presence/reverse-presence spectral direction,
transparent bypass, finite comb tails, and comb notches at 2,400 and 8,000 Hz
spacing. Rendered pixels verify whole-picture opacity, usable base blending,
and the CSS fallback when the canvas filter property is unavailable.

A generated H.264/AAC fixture verifies independent native repeats and speeds,
nonzero audio after picture expiry, and pause/resume position retention. The
shared master graph measures default Tide at RMS 0.0168221 and peak 0.100864 at
full presence, sweep time two seconds, and master volume 0.45. Generated loops
use normalized buffers and their own headroom; native inputs retain the
conservative original voice gain.

The supported Sites preview was exercised in Chrome: playback, different
audio/video rates and repeat counts, picture removal/restoration, stacked
blending, local video admission, Save/Load, and JSON export. A local clip moved
below all three generated layers remained in that position after Save/Load and
file reselection. Export while the file was unresolved retained its settings
and position without a media URL or bytes.

A temporary 390-pixel iframe harness exercised the responsive layout in the
same browser. Its content width and scroll width were both 375 pixels (the
remaining width was the browser scrollbar), with usable stacked controls and
no horizontal overflow. This is CSS layout evidence, not physical iPhone or
Safari playback acceptance. The temporary harness is excluded from delivery.

Independent review verified the transport corrections and identified the local
file order/pending-settings issue, which was fixed and regression-tested.

## Evidence boundaries

Source base: local preserved presence commit
`d95669d002c43e00d366510c105cd2e05fa4acbc`, parent main
`63612a9a7394d8b4e1ec1d375baaa17eaf265eb9`. Other active worktrees are retained.
The inherited presence work has known incomplete regression evidence and is
not represented as accepted. PR #90 is a separate unmerged WebKit investigation.

Relevant shared context: finalized 2026-10-16-v1.1 / sanitized v1.1-r2,
CF02, CF29, A077, A122 (historical source attribution). Its exported snapshot is
accessible; the private memory project's live account-wide state is not verified.
No old approval grants new merge, restructuring or public publication authority.
