# Effects Lab editing workspace

Effects Lab is a browser editing workspace for **Independent Loop Compositor**.
It combines a media bin, composition preview, arrangement timeline, clip
inspector, and a separate performance view. Open it from the **Effects Lab** link
in Studio, or directly at `lab.html` in a staged compositor site. The page opens
on an empty timeline, ready for your footage and found sounds. No clips are
inserted automatically. An optional **Public media** picker offers recorded
footage and found sounds with their source and rights records.

The earlier [dataset Lab](LAB.md) still explores strip layout, framing, pool
selection, and source metadata. This workspace focuses on overlapping picture
and sound pairs with independent repeat speeds, effects, and endings. It shares
Studio's master audio protection and static publication path. Existing authored
composition rendering and export retain their separate behavior.

## Start editing

Start with your own material. Use **Import media**, the timeline's **Import local
files** button, or the **＋** button to choose footage or found sounds. You can
also drop video or audio files directly onto the timeline. Audio-only material
is supported; no picture or musical structure is required.

1. Import or drop a file. Its regions initially use the real source duration.
2. Press **Play** in the top transport to unlock sound and play the arrangement.
3. Select a picture or sound region to open that pair's settings in the inspector.
4. Drag a region's body to move both lanes to a new shared start.
5. Drag its right edge to change that lane's region duration.
6. Drag an envelope diamond horizontally to change the entrance time and
   vertically to change picture opacity or sound level.

**Reset** clears the arrangement and the current page's media bin, returning to
an empty project. It also clears the public-media cache used by this workspace;
if browser storage cannot be cleared, the interface reports that failure. Reset
does not overwrite the separately saved project.

The timeline has one row per clip pair, with distinct **Picture** and **Sound**
lanes. Up to **eight pairs** can occupy the project, including unresolved local
media slots. Higher rows are in front in the visual blend stack. Row arrows
change that order without changing scheduled start times.

A picture and its sound always share a launch time. Their region durations,
media positions, repeat counts, playback rates, and rate changes are independent.
For example, a pair starting at 8 seconds with a 12-second picture region and a
48-second sound region loses its picture at 20 seconds while its sound continues
until 56 seconds.

## Timeline controls

| Action | Result |
| --- | --- |
| Drag either region body | Move the pair's shared timeline start. |
| Drag a picture right edge | Change only picture region duration. |
| Drag a sound right edge | Change only sound region duration. |
| Drag an envelope diamond left or right | Change the pair's shared entrance time. Each lane bounds its effective peak to its own duration. |
| Drag a picture diamond up or down | Change that picture's opacity. |
| Drag a sound diamond up or down | Change that voice's audio gain. |
| Click or drag the ruler or an empty timeline area | Seek the real arrangement playhead and preview. |
| Enable **Snap ¼s** | Quantize timeline movement and duration edits to quarter seconds. Hold Shift during a drag to bypass snapping. |
| Adjust zoom or press **Fit** | Change the timeline scale. Horizontal and vertical scrolling remain inside the timeline. |
| **Duplicate** | Add a new pair with the selected settings, a separate identity, and a start one second later. |
| **Delete** | Remove the selected pair and release its playback resources. Imported source files remain reusable in the current page's media bin. |

The **Timing** inspector provides exact numeric fields for timeline start,
entrance, picture region duration, and sound region duration. Picture regions
support 0.25–600 seconds; sound regions support 0.25–900 seconds. Starts are
bounded to 0–3600 seconds. Entrance is bounded to 0.01–60 seconds, with its
effective peak limited to half of each lane's region duration.

**A right-edge edit changes region duration. It does not set source in/out
points.** Each region starts from the beginning of its source. A region that
outlasts the source repeats it, using that lane's independent playback clock.
The current workspace does not expose source-offset cropping or slip editing.

The timeline line drawings are editable presence envelopes, not extracted audio
waveforms. Native source duration labels come from actual media metadata.

## Arrange and Perform

### Arrange

Arrange plays clips according to their timeline starts and independent region
ends. Scrubbing reconstructs both source positions, repeat counts, and playback
rates at the requested time. Seeking a paused local video updates the preview
when the browser has decoded the requested frame.

The top **Loop** toggle and start/end fields define an arrangement loop range.
**Stop** pauses playback and returns to zero. **Play** resumes from the playhead.
The row play button and the selected-clip transport button seek to that pair's
scheduled start and play the arrangement, including any other regions active
there.

**Hold level within each region** makes presence flat inside the two fixed
regions. Their ends still apply. The envelope diamond is hidden while presence
is held; turn Hold off to shape the entrance and departure again.

### Perform

Perform presents launchable clip slots. Pressing a slot's **Launch** deliberately
restarts that picture-and-sound pair. Its two clocks then continue independently.
The timeline schedule is not used for performance launches.

Optional automatic sequence launches resting pairs on the chosen interval. It
does not reuse a pair while that pair's sound tail is still active. A manual
launch explicitly restarts it. **Hold presence indefinitely** keeps a launched
pair present until its settings or playback are changed.

Arrangement loop controls are disabled in Perform. Returning to Arrange restores
scheduled playback semantics. Ruler scrubbing explicitly uses Arrange mode.

## Import and reuse local media

Use **Import media**, the add-media button, or drop video/audio onto the workspace.
Dropping a source onto the timeline places it at that time; clicking a source in
the bin places it at the playhead. The media bin contains files you imported
or explicitly chose from the optional public-media catalog.

Imported files stay in the current page's media bin and can be reused after a
clip is deleted. Native clips initially use their actual source durations for
their regions. Audio-only sources have a sound region and no active picture.
If all eight timeline slots are occupied, an imported file can remain in the bin
until a slot becomes available.

Media is read through local object URLs and is not uploaded. Each duplicate
local clip receives a separate owned URL so deleting one does not invalidate
another. Browser codec support determines which files can be decoded; an
unsupported import reports an error without replacing existing clips.

## Optional public media

Open **Public media** in the top bar, including on small screens, or use the
media-bin shortcut. The fixed catalog contains two recordings with picture and
original location sound, plus two audio-only field recordings. Each card shows
the creator, reuse terms, source page, delivered format, approximate duration,
and download size. The selected clip's inspector retains the source and rights
links after it has been added.

Choose **Add to timeline** to download that source and place it at the current
playhead. Adding a source does not start playback when the transport is stopped,
and it does not interrupt an already running composition. Audio-only sources
open the Sound inspector when Picture was selected. These files enter the same
native-media path and use the same timeline, blending, filtering, and repeat
controls as local imports.

The delivered videos are VP9/Opus WebM; the audio recordings are MP3. The picker
disables a format when the browser reports that it cannot play it, and reports
actual download or decoding errors. The source page remains available for other
download variants. It does not claim universal Safari or physical iPhone support.

See [public-media sources and verification](EFFECTS_LAB_OPEN_MEDIA.md) for the
four original creator/rights records, exact delivered variants, and bounded
browser evidence. The two audio recordings have author public-domain releases;
they are not labelled CC0. Credit links remain useful provenance even where the
stated reuse terms do not require attribution.

Downloads use a fixed Wikimedia host and catalog allowlist, with credentials
omitted. The workspace accepts no arbitrary remote media URL from a project
file. Your own files are never uploaded. Downloaded Files are reused during the
page session and stored in this workspace's browser cache when storage is
available. Reset clears both reuse stores without adding any sample material.

## Picture, sound, and timing effects

Selecting a region updates the **Picture**, **Sound**, and **Timing** inspector
for that pair only. Changing selection does not copy settings between clips.
Presets change the selected pair's settings, including their envelope durations,
but preserve its scheduled start. They are editable starting points.

### Picture

The preview composites visible pictures in layer order. Available blend modes
are Normal, Screen, Multiply, Overlay, Soft light, Difference, Exclusion, Color
dodge, Lighten, and Darken. Opacity combines with the picture's presence envelope.
Brightness, contrast, saturation, hue, blur, and inversion are independent
controls.

**Vanish picture** disables that picture while leaving its sound clock and region
active. **Bring picture back** restores an eligible picture at its existing clock
position. If its region has ended, seek to it or launch it again. This provides
a direct way to hear a sound tail.

### Sound

Each voice has its own swept comb and spectral pass filters. Comb spacing sweeps
logarithmically between its lower and upper frequency settings, then returns.
The period is a complete round trip; clip identities provide separate stable
phase offsets. The live comb display reports this moving spacing, not a single
low-pass cutoff.

The comb uses finite feed-forward delay taps. **Comb decay** changes their
weights; it does not create an infinite feedback circuit. The saved-settings key
`combFeedback` retains its original name for compatibility.

Presence filtering opens low-pass filtering on entrance and thins the departing
sound with high-pass filtering. Reverse presence exchanges those roles. Manual
low-pass, high-pass, band-pass, and Off modes are also available. Filter resonance
applies to the selected pass mode, and the comb has its own mix control.

The master graph provides compression and sample limiting, without a true-peak
limiting claim. Master mute and volume affect the whole composition; voice level
changes only the selected pair.

### Independent repeat rates

Picture and sound each have a base rate and their own variation amount per
repeat. A rate changes at that track's repeat boundary, not at the other track's
boundary. Rates remain within 0.25–3 times normal speed. Live readouts report the
actual rates, repeat counts, and presence values.

Sound normally uses varispeed: speed changes also change pitch. Pitch
preservation is enabled when the browser exposes that capability for the
selected local source. Picture filters likewise follow the available canvas or CSS filter
path; unavailable capabilities are identified rather than presented as working
controls.

## Save and restore

**Save** stores project settings in the current browser. **Open saved** restores
that project. **Export JSON** and **Import JSON** move the settings between pages
or devices. Restoring a project opens it paused.

The JSON describes arranged clips, their settings and layer order, source names,
stable clip identities, transport mode, and loop range. Public-media clips also
retain a known catalog `sampleId`. The JSON contains no media bytes, blob URLs,
or remote download URLs. It does not record a rendered composition, the active
playhead position, or a durable copy of the entire source bin.

Local files must be selected again after a reload. Unresolved files remain as
ordered placeholders with their original settings, durations, scheduled starts,
and identities. They can be edited, reordered, removed, or saved again before
reselection. Choosing the matching file name and media type restores its saved
position. A file name is a restoration aid, not verification that the file's
contents are unchanged.

Public-media clips restore from the fixed catalog automatically, using the
browser cache or downloading again. Their stable identities, settings, start
times, and stack positions are retained. If a download fails, its saved slot
remains visible as **Public media · download pending** with a retry control;
restoration continues for the other clips. Local-file slots still require
reselection and are labelled separately.

Stable clip identities retain deterministic repeat decisions and comb phase
through reordering and restoration. New clips reserve identities belonging to
unresolved media, preventing a later file restoration from colliding with a new
admission. Duplicates receive fresh identities. Older settings without clip
identities or timeline starts remain importable. Legacy projects containing
generated test sources can still be opened, but those sources are not offered
in the public import workflow and are never added at startup or Reset.

## Keyboard and focused controls

| Key | Action |
| --- | --- |
| Space | Play/pause when the workspace owns keyboard focus. |
| Home | Stop and return to zero. |
| 1–8 | Select a pair in front-to-back row order. |
| L | Play/launch the selected pair using the current mode. |
| V | Toggle its picture. |
| Delete or Backspace | Remove the selected pair. |
| Ctrl/Cmd+D | Duplicate the selected pair. |
| Left/Right on a focused region or duration edge | Move or change duration by 0.25 seconds; Shift uses one second. |
| Arrow keys on a focused envelope diamond | Adjust entrance horizontally and lane level vertically. |

Text fields and focused buttons retain their normal keyboard behavior. Inspector
and workspace tabs support keyboard navigation. On narrow screens, use the
inspector toggle and add-media button to reach controls that are persistently
visible on desktop.

## Scope and acceptance

This is a direct browser arrangement editor with a live compositor and separate
picture/sound clocks. It does not claim full Ableton Live or Final Cut parity.
Source in/out trimming, split/merge and ripple editing, waveform extraction,
recording, and rendered multitrack export are not implemented here. The browser
transport is not a sample-accurate native DAW transport.

Build the static workspace with the existing Studio command:

```bash
PYTHONPATH=src python -m simvltanea.browser.browser_studio --output var/site/studio
```

Open staged `lab.html` using the supported local or hosted preview. The workspace
adds five declared assets to the existing five-file Studio output. Public
library staging uses the same allowlist and rejects unrelated files.

Desktop browser, decoded-frame/audio-signal, and emulated phone checks remain
separate from physical iPhone Safari acceptance. This workspace does not close
the ongoing native Studio WebKit continuity investigation. See
[Studio playback](STUDIO_PLAYBACK.md) for that boundary.
