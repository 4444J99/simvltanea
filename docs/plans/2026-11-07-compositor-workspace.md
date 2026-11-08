# Direct editing workspace

## User correction

The user rejected the first Effects Lab surface as unhelpful and asked for
interaction comparable to Ableton or Final Cut. The new objective is direct
clip editing: the arrangement, regions, playhead, and envelopes are the main
controls. The user also explicitly requested publication during development.
The same existing Site URL is retained and updated at usable milestones.

This supersedes the interface direction in the earlier
[Effects Lab plan](2026-11-07-effects-lab.md). Its working DSP, independent
voices, local-media ownership, and saved-session safeguards are retained.

The subsequent correction specifies found sound and actual footage, rather than
music or supplied illustrations. Startup and Reset therefore create an empty
project. Local import is the primary workflow; generated examples are absent
from the public interface. Any later optional shared media needs an individual
source and reuse record.

## Interaction model

- A full-viewport workspace contains a media bin, composition preview, timeline,
  selected-clip inspector, and compact transport.
- Each clip pair has distinct Picture and Sound regions. Dragging a body moves
  their shared launch time; the right edges independently edit their durations.
- Envelope diamonds edit entrance time and the selected lane's opacity or gain.
- Clicking the ruler or empty arrangement space scrubs the actual media.
- Arrange plays scheduled regions. Perform provides live clip launching.
- Snap, zoom, loop-range controls, duplication, deletion, local import, and
  project save/import/export operate on the same engine state.
- Eight clip pairs are supported. Fractional region lengths are allowed.

The design follows the distinction between linear arrangement and live clip
launching described in the
[Ableton Arrangement guide](https://www.ableton.com/en/manual/arrangement-view/)
and [Session guide](https://www.ableton.com/en/manual/session-view/).
[Apple's trimming guide](https://support.apple.com/en-eg/guide/final-cut-pro/ver9847ec25/mac)
provides the direct edge-editing reference. This workspace edits looping region
duration and presence; it does not label those operations as source-frame cuts.

## Transport contract

`Engine.setTransport({mode, looping, loopStart, loopEnd})`, `seek(seconds)`, and
`stop()` extend the retained live engine. The default engine mode remains
`perform` for existing callers. The workspace initializes an empty `arrange`
project with a 0–60 second loop range, disabled until requested.

`settings.timelineStart` determines launch time. Picture and sound lifetime,
repeat state, and rates remain independent. Arrangement regions end at their
declared durations even when their presence is held. In Perform, hold retains
its existing indefinite meaning.

Repeat-indexed random draws make a seek reproduce the same rate history.
Stable saved clip identities preserve those draws and comb phase after reorder
or local-file reselection. Admission reserves pending IDs; the interface also
reserves unresolved saved IDs when allocating new clips.

Native elements and audio graphs survive edits and seeks. Picture-only edits
must preserve the running sound source. A paused native video repaints when its
seek completes. The browser transport does not claim sample-accurate DAW sync.

## Acceptance tasks

- Import and move a clip, then play across its new scheduled start.
- Trim the picture shorter than sound and verify continued decoded audio.
- Edit an envelope diamond and observe its actual presence/gain change.
- Scrub, loop a range, and switch Arrange/Perform with truthful controls.
- Save/reload an interleaved project, reselect local files, and recover order,
  schedule, transport settings, deterministic repeats, and independent tails.

## Earlier verification boundary

The replacement workspace's browser acceptance exercised paired movement,
independent region duration, envelope peak dragging, exact duration entry,
ruler scrubbing, native video and audio-only import, Arrange/Perform, and loop
playback. Browser checking exposed a notification-throttle freeze after a loop
wrapped backward; the engine now resets that throttle on both wrap paths, with
a reproducing regression. Layout checking corrected timeline overflow into the
inspector. Review also corrected saved identity and unresolved-file ID reuse.

The verification target is headless Chromium and the managed desktop browser.
It does not establish physical iPhone playback or artistic acceptance.

The first lab passed 42 focused tests and 34 affected staging/publisher tests.
Its broader repository run was interrupted after 876 test starts when this
new interface direction was accepted. It recorded one Studio About-panel
regression; that redundant paragraph was removed and the focused native Studio
test passed in 6.110 seconds. The interrupted run has no aggregate pass result
and does not verify this replacement workspace.

Publication keeps the existing Site access configuration. Before the first
successful deployment, access was verified as public (policy revision 2);
no audience change was made. Imported media stays on the visitor's device.
Shared context remains finalized 2026-10-16-v1.1 / sanitized v1.1-r2 with the
previously recorded CF02, CF29, A077, and A122 boundaries. No restructuring,
merge, or physical-device acceptance is inferred.
