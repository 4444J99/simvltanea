# Continuous Studio playback

Studio uses a persistent native-video session. The authored composition runtime
and exporter retain their existing frame-based timeline behavior. Both paths use
the same layout conventions, including custom layout files and source crops.

An ordinary library visit begins with up to four panels. Mobile and touch devices
admit at most four foreground panels, including manual, seed, mix, upload and
layout requests. Desktop manual controls retain the range of one to twelve.
Each slot has two persistent video elements, but only one global preparation
permit covers personal-file metadata probes, standby playback and crossfades.
On mobile this bounds application activity to four foreground videos plus one preparing or
fading successor; it is not a measurement of hardware decoder allocation.

Published-library prefetch checks the validated manifest, downloaded byte count,
SHA-256 prefix, container and browser codec support without creating a temporary
metadata decoder. Its dimensions and whole-frame duration come from that
manifest. Actual decoding is checked when the persistent standby admits the
asset. A hash-consistent asset that cannot decode is therefore refused at that
handoff, while the outgoing resident keeps playing. Personal uploads still decode
their metadata before entering the local pool.

Tapping a panel replaces its clip. Untouched residents keep their elements,
playback positions and audio bindings. Shuffle queues replacements and compresses
queued crossfades to 0.2 seconds. The old clip keeps looping if its successor fails.
Failed boomerang derivatives fall back to their admitted forward source.
When a primed successor must wait for a future loop boundary, its hidden video
pauses without seeking. The preparation permit remains held, while the outgoing
clip and its neighbors continue playing. This reduces unnecessary concurrent
decoding; the activity ceiling alone does not guarantee hardware capacity.
An eligible resident rescue takes priority over queued ordinary preparations.
An ordinary preparation can yield while its incoming deck is still hidden:
rollback unloads that deck before releasing the permit, leaving its outgoing
resident and neighbors untouched. The same request retries after urgent work if
its reconciliation and resident identity remain valid. Visible fades and
promotions, active rescues and personal metadata probes are not preempted.
This arbitration reduces rescue queue delay; it does not guarantee recovery
within two seconds on every device.
Running replacements revalidate two fresh, nonseeking decoded frames after any
seam wait and before revealing the successor. A source-bound progress monitor then
spans the fade and promotion without restarting its deadline. Its normal budget
is 800 milliseconds, capped by the configured progress timeout. A stale successor
rolls back to the retained outgoing clip; promotion still requires fulfilled
playback and two distinct decoded media times before retiring the old deck.
Browsers without video-frame callbacks use ready media-time progress as a fallback.

Video frame callbacks arrive on the page's animation-frame cadence. A hidden or unfocused
pane, or a battery saver, can lower that cadence to a few frames per second, and then silence
from the callbacks says nothing about the decoder. While a freshness check holds it, the session
measures animation frames; after a 400 ms window below 12 per second it also accepts the media
clock of a playing, unpaused, unseeking clip as evidence of progress, polled every 100 ms. At a
healthy cadence nothing is polled and the callbacks alone decide, so a frozen or paused successor
is refused as before. A starved page cannot tell a frozen decoder whose clock still advances from
a healthy one; that case is accepted rather than refusing every clip the page cannot confirm.
This was the cause of one of four decks playing in a hidden Browser pane: in an unthrottled
headless Chromium all four played from the same staged site.

With an outgoing resident available, transient readiness timeouts record
`handoff-deferred` and return an unsuccessful handoff. Automatic scheduling retains
the old resident and extends its deadline
by a whole loop. Decode errors and rejected playback remain errors. Deliberate
pause suspends monitoring of a verified visible successor; pausing before fresh
reveal defers the handoff. A manual edit that stays paused can still admit a
decoded still image. These safeguards preserve the original frame-progress
history and the separate two-second verification gate.

Selection, share links and export metadata are committed from the residents that
actually remain after a change. A deferred panel does not undo successful changes
in other panels. During a multi-panel edit, an already resident source keeps its
slot; requested permutations and shrinking layouts cannot copy it into a second
slot and leave duplicate residents after a refusal. When this changes a seeded
roll's order or source set, the share link records the actual public mix.

Exports requested during a change wait for settlement. Each issued plan retains
its own source-file bindings across subsequent edits, including retained forward
variants and local files. A compilation failure can reuse the previous accepted
snapshot only when it still describes the live residents; otherwise export reports
unavailable metadata until a later change settles. Generated voices continue
scheduling independently while export metadata is pending.
Edits made while built-in clips are recording wait for that preparation. The
latest requested count, family, shuffle and share link survive the readiness
retry, while the existing residents keep playing.

## Rhythm and controls

Automatic residents draw a 10–24 second target lifetime and round up to a whole
number of native loops. A long clip can therefore exceed 24 seconds. Readiness,
cooldowns and the single preparation permit take priority over the rhythm. An
automatic handoff waits for an outgoing native loop boundary; manual taps do not.
If decoded media time stops advancing for two simulation seconds, or the expected
remaining loop plus that allowance elapses without a boundary, the waiting handoff
continues with its prepared successor. This releases the shared preparation permit
instead of letting one frozen native loop block the whole stage. A `seam-fallback`
event records the reason. Normal advancing loops retain boundary alignment.
Departed logical clips have a ten-second return cooldown, shared by both variants.
Personal files use their content digest for that cooldown and draw replacements
from the admitted local pool. When every file is already on screen or cooling
down, the resident continues for another whole loop. Automatic changes wait until
an import batch finishes. Personal replacements read the admitted files locally,
without network requests.

Whole-loop extensions preserve the resident's original retirement priority.
Once a clip is overdue, younger clips yield when its next retry boundary is
within ten seconds. This reserves a scheduling turn without starting a decoder
early. A farther-away boundary remains eligible for later consideration, so a
long clip cannot block every other replacement for another full long loop.
Failed replacements rejoin at their next whole-loop deadline; waking a resting
clip gives it a fresh priority at its next boundary. Scarcity can still extend a
lifetime, but repeated cooldown collisions no longer erase its place in line.

Steady, sparse and burst regimes vary arrival spacing. Sparse periods target a
time-averaged population near 65 percent for four panels, with at least two active
residents. Readiness and lifetime guards can change the achieved average. Resting
residents keep their native loops moving, dimmed and silent, avoiding an extra
pause/resume transition when they wake. Explicit pause still stops every resident,
including resting ones. A manual panel count disables automatic resting and
survives shuffle; finite replacements continue.

The infinity button holds automatic changes after any current handoff completes.
The direction button switches published forward and boomerang playback. Local
uploads remain forward loops and never leave the device. Reduced-motion settings
start paused and disable automatic evolution and territorial motion.

Sound unlocks on a gesture. Source energy, age, neighboring prominence and fatigue
control audible priority. Sustained acoustic leaders also keep their spectrum
open while quieter rivals receive more low-pass filtering. This spectral effect
respects the Filters switch, Low-pass filter strength and reduced-motion bypass;
it does not add another image or volume envelope. Generative strips trade bounded
territory; authored and custom geometry remains as authored. Geometry writes are
throttled to 20 Hz.
The simulation clock pauses with playback and hidden tabs, independently of audio.
Competition follows recorded clip energy and resident age/fatigue; synthesized
accents inherit their resident's gain and spectral filtering. Individual synth
note amplitudes do not feed the clip-energy model.

## Clip presence filters

The **ƒx** button in the top corner toggles linked audio and image filters.
They are on by default; `fx=0` in the URL bypasses them, and `fx=1` enables them.
The explicit setting survives shuffles. Toggling filters keeps the same video
elements, playback positions, and audio connections.

The adjacent **☷ Filter settings** button opens adjustable timing, sound, and
image controls. The field keeps playing while the dialog is open. Escape closes
the dialog and returns focus to its button. Reset filters restores the defaults;
it does not change the composition or the separate Filters bypass switch.

| Control | Range | Default |
| --- | --- | --- |
| Rise | 0.1–5 seconds | 1.2 seconds |
| Curve | Linear or smooth | Linear |
| Waiting presence | 5–50 percent | 12 percent |
| Volume swell | 0–100 percent | 100 percent |
| Low-pass filter | 0–100 percent | 100 percent |
| Brightness swell | 0–100 percent | 100 percent |
| Color swell | 0–100 percent | 100 percent |
| Blur | 0–2 CSS pixels | 2 pixels |

Set an effect's strength to zero to bypass it independently. Settings apply to
the live field while each clip retains its own envelope phase. Nondefault values
are retained as bounded `fx_attack`, `fx_curve`, `fx_tail`, `fx_gain`,
`fx_lowpass`, `fx_brightness`, `fx_saturation`, and `fx_blur` URL parameters.
No local media names, paths, bytes, or tags enter these parameters. The five-second
rise bound keeps an arriving deck's rise consistent with the scheduler's shortest
ten-second planned lifespan.

Each evolving resident rises to a peak over 1.2 seconds, then recedes across its
planned lifetime. The same presence value controls its selected gain, low-pass opening,
brightness, saturation, and up to 2 CSS pixels of blur. The picture becomes
clearer and the sound opens as the clip rises. These are tuning defaults, not
an artist-approved preset.

An overdue clip retains a quiet 0.12 tail until a decoded successor can take over.
Extending its retirement deadline does not restart its rise. The incoming deck
starts a separate envelope when it becomes visible; the moving crossfade finishes
the predecessor's departure. Preparation time and native playhead wraparound do
not count as the new clip's age.

Presence multiplies the normalized mix gain, so it remains audible even with a
single resident. The low-pass cutoff moves logarithmically from 420 Hz to at most
16 kHz or 45 percent of the actual sample rate. The existing master protection
remains in the signal path. Bypass clears image filters, flattens the filter's
magnitude response, and removes this amplitude envelope.

Holding automatic changes, or playing a source without automatic succession,
keeps steady presence after entry. Pause and hidden-tab suspension freeze the
envelope clock. Reduced-motion mode disables these animated filters. Authored
exports are unchanged; this feature belongs to the interactive Studio session.

Library and uploaded clips use independent incoming and outgoing audio filters.
Built-in generated loops also attach one synthesized voice to each entering deck,
so both sounds overlap through their own filters and gains during the visual
handoff. Retirement or failure disconnects only that deck's voice; other voices
retain their scheduling position. Sound unlocked during a handoff attaches both
visible decks to the same existing audio context.
If recording is unavailable and Studio uses its live canvas preview, the Filters
control is disabled; that fallback keeps its existing image and sound behavior.

## Recovery attempts for native loop seeks

An observed native WebKit failure can leave a previously moving boomerang's first
frame frozen after a loop boundary, even when `seeking` is false and the media
clock advances. The runtime watches the active deck from the simulation tick.
An observed end-to-wrap transition remains eligible only until the next distinct
decoded frame. After 600 milliseconds of continuous
foreground simulation time without decoded progress, it pauses that element,
seeks forward to the next frame and calls play in the same task. Its source,
audio routing and sibling decks retain their identities. The explicit
`nativeLoopSeekPauseBeforeSeek: false` diagnostic control retains the former
seek/play operation for paired native trials.

Starting a repair requires known asset frame timing, prior decoded movement, a ready and
error-free element, and a running visible session. An issued repair retains
ownership while that same element buffers at `readyState` 1 or 2 during its seek;
new repairs still require `readyState >= 3`. Current library boomerangs
provide that timing; forward and personal clips do not participate. Pause,
backgrounding, rest/wake transitions, and replacement or source changes in the watched slot
invalidate the evidence. A sibling's pending replacement does not suspend the guard.
A resting resident still displays a dimmed, playing picture; a newly observed
wrap while it remains resting can qualify independently. Changing its rest state
cancels the existing repair before a successor can take ownership.
A delayed host callback contributes at most 100 milliseconds. Another ordinary
attempt requires decoded recovery and a newly observed loop boundary. Resuming
after a cancelled attempt can establish a new attempt owned by the current
session only if that same previously attempted source remains frozen at its seek target
and still reports seeking. A new observed seam can qualify independently of that flag;
startup or an arbitrary quiet frame cannot.

If the first native attempt does not produce two nonseeking frames within another
200 milliseconds of foreground simulation time, one standby repair can prepare
the same cached clip through the existing global permit. It retains the outgoing
picture until the normal freshness and promotion checks succeed, with a fade of
at most 0.2 seconds. This is an operation budget; an occupied permit or a slow
decoder can still delay completion. Failure retains the outgoing resident.

A successful decoder repair preserves the clip, its birth time, age and presence
settings. Its logical resident identity transfers only after verified promotion,
so pending exports can recognize the same resident without accepting unrelated
new admissions. Source changes, removal, pause, backgrounding and disposal cancel
owned repair work. A sibling edit does not cancel it. The unchanged asset-timing
requirement excludes generated built-in voices from this repair path.

Proof output retains bounded attempt, recovery, rejection and interruption
receipts, including the operation strategy and immediate native state. Recovery
requires two distinct decoded frames after seeking ends; a
fulfilled play promise is insufficient. The original frame-progress history and
two-second verification gate remain unchanged. This is a bounded recovery attempt,
not a guarantee that the browser's native seek will complete. Native evidence must
distinguish an exercised recovery from a passing run that never triggers it.

When a replacement is ready, an outgoing source that is still seeking after its
own recovery attempt can use a 0.2-second fade. This requires the same source,
epoch and playback generation, with no distinct decoded frame since the attempt.
The incoming clip must first pass its normal freshness check. Healthy or recovered
sources keep the requested fade duration, and deliberate suspension invalidates
the shortcut. A `handoff-expedited` event records the decision. This shortens the
frozen picture's departure without declaring recovery or clearing frame history.

## Audio and asset evidence

The persistent master chain includes compression, a compensated soft clipper and
a final sample guard. Tests render the actual production graph in OfflineAudioContext,
including correlated tones, impulses and high-frequency signals. The measured
sample ceiling is approximately 0.891251, or −1 dBFS, within floating-point tolerance.
This is sample-peak protection, not a true-peak or lookahead-limiter guarantee.

Published boomerangs are encoded offline as forward-playing CFR H.264/AAC media.
The builder preserves the original forward files and logical clip identities,
then adds content-addressed variants and measured audio envelopes. Frame timestamps
and separate audio/video durations are verified. Container timing alone does not
prove seamless native-browser playback. See [deployment](STUDIO_DEPLOYMENT.md).

## Device acceptance

Append `proof=1` to a preview URL to show simulation time, preparation count,
per-slot media time, decoded-frame callbacks and waiting events. Waiting events
include startup buffering; judge them alongside actual frame progress and pixels.

On the owner's iPhone, record the model and iOS version, then check initial loading,
several minutes of evolving playback, individual taps, repeated shuffles, forward
and boomerang modes, sound/mute/volume, pause, rotation and background/resume.
Confirm that untouched panels keep moving and that no transition clears the stage.
Confirm that panel controls stop at four on the phone, including after uploads
or opening a shared composition that requests more panels.
Linux WebKit and an emulated phone viewport are separate automated evidence.

Native verification distinguishes a cancelled internal blob read during hidden
preparation from an active-source failure. Successful admission evidence must bind
the same slot, deck, URL and source epoch across priming and parking, retain
recorded ownership and outgoing playback, then show two fresh frames before
visibility and a completed promotion. Missing or contradictory evidence remains
an error. The separate one-second recovered-read rule is unchanged.

The filter integration retains the accepted continuity and progress verification
from merged [PR #90](https://github.com/4444J99/tool-video-loop-compositor/pull/90).
PR #92 at `5dc225a87684012a529bad97770e10a8883d3585` passed CI and packaging,
but its Apple WebKit run recorded a 2,648-millisecond decoded-frame hold across
all four panels. The integrated revision needs independent native verification.
See [the current integration status](CLIP_FILTER_VERIFICATION.md#integration-status--november-8-2026)
for the exact revisions and runs. Physical iPhone acceptance remains pending.

Tracking: [issue #89](https://github.com/4444J99/tool-video-loop-compositor/issues/89)
and [PR #95](https://github.com/4444J99/tool-video-loop-compositor/pull/95).
