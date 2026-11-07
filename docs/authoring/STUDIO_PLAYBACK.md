# Continuous Studio playback

Studio uses a persistent native-video session. The authored composition runtime
and exporter retain their existing frame-based timeline behavior. Both paths use
the same layout conventions, including custom layout files and source crops.

An ordinary library visit begins with up to four panels. Mobile and touch devices
admit at most four foreground panels, including manual, seed, mix, upload and
layout requests. Desktop manual controls retain the range of one to twelve.
Each slot has two persistent video elements, but only one global preparation
permit covers metadata probes, standby playback and crossfades. On mobile this
bounds application activity to four foreground videos plus one preparing or
fading successor; it is not a measurement of hardware decoder allocation.

Tapping a panel replaces its clip. Untouched residents keep their elements,
playback positions and audio bindings. Shuffle queues replacements and compresses
queued crossfades to 0.2 seconds. The old clip keeps looping if its successor fails.
Failed boomerang derivatives fall back to their admitted forward source.
Promotion requires fulfilled playback and two distinct decoded media times before
retiring the old deck. A visible successor that cannot demonstrate progress within
two seconds rolls back to the retained outgoing clip.

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
control audible priority. Generative strips trade bounded territory; authored and
custom geometry remains as authored. Geometry writes are throttled to 20 Hz.
The simulation clock pauses with playback and hidden tabs, independently of audio.

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

The local filter integration includes the bounds and decoded-frame promotion
checks from draft [PR #90](https://github.com/4444J99/tool-video-loop-compositor/pull/90)
at `0f3743769e75011097d781e7d9c14b8fd66681a3`. Its November 7 sustained Linux
WebKit evidence still reports 27.302-second and 10.803-second frozen residents.
Those checks prevent a frozen seam from indefinitely blocking later handoffs;
they do not establish sustained WebKit continuity or physical iPhone acceptance.

Tracking: [issue #89](https://github.com/4444J99/tool-video-loop-compositor/issues/89)
and [PR #88](https://github.com/4444J99/tool-video-loop-compositor/pull/88).
