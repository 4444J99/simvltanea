# Browser studio

The SIMVLTANEA studio is a static, client-only web page that is already playing
when it opens. It fills the screen with built-in generative loops, each on its
own clock, in a composition chosen by chance: accidents waiting to happen. The
first touch, click, or key press turns the sound on. Visitors may drop their own
videos onto the page, but they never have to. Nothing needs installing, and no
Python or FFmpeg is required.

## What happens on load

Each load rolls one composition:

- a family, **strips** or **authored**;
- a panel count that family offers (strips 1 to 12, authored 2 to 7);
- which loops play, distinct and in a random order;
- for strips, a zoom and a lateral jitter within the strips preset's ranges.

Every panel plays a real, distinct loop. The compiler's rule holds: nothing is
padded, repeated, or duplicated to fill a count.

With `prefers-reduced-motion: reduce`, the page shows the first frame of the
composition, paused, behind a single large play button.

## Controls

A small floating bar sits at the bottom of the screen, with full screen and
**?** in the top corner. Both fade after about three seconds without pointer
movement, and come back on movement, a touch, or keyboard focus. Every icon has
an accessible name and a visible focus ring, and every target is at least 40
pixels (44 on wider screens).

| Control | Key | Effect |
| --- | --- | --- |
| Play / pause | Space | Pauses or resumes every loop together |
| Shuffle | R | Rolls a new composition with a short crossfade |
| Fewer / more panels | ← → (also ↓ ↑) | Removes the last loop, or adds an unused one |
| Strips / authored | none | Switches family; the nearest count it offers is kept |
| Speaker | M | Three states: tap for sound, sound on, muted by you |
| Volume | none | Master level; appears when the speaker is hovered or focused |
| Add yours | none | Opens the file picker for your own videos |
| ƒx Filters | none | Links each clip's audible and visible rise and fall; toggles the effect without restarting playback |
| ☷ Filter settings | Esc closes | Adjusts rise, curve, waiting presence, and separate sound and image effect strengths |
| Full screen | F | Enters or leaves full screen where the browser allows it |
| ? | Esc closes | Three short lines: what this is, privacy, the keys |
| A panel | none | Swaps that panel's loop for one not on screen |

Messages appear as one short toast that dismisses itself, for example
"Authored: 7 panels." or a file refusal. Nothing stays on screen as text.

## URL parameters

| Parameter | Effect |
| --- | --- |
| `?seed=<n>` | Repeats a roll exactly; `n` is a whole number up to 4294967295. The page writes the current seed into the address after every roll, so the address is shareable |
| `&mix=s3.7.1` | Written after hand edits (panel taps, count, family): the family's initial and the built-in loops by number. Together with the seed it reproduces the edited composition |
| `?seconds=<n>` | Length of one pass of the piece, in seconds (default 120). At the end it starts again |
| `?gen=1` | Plays the built-in loops even when a library is deployed, without requesting it |
| `&fx=0` / `&fx=1` | Bypasses / enables clip presence filters; reduced motion keeps them disabled |

See [continuous Studio playback](STUDIO_PLAYBACK.md#clip-presence-filters) for
the current resident lifecycle, filter envelope, and device verification boundaries.

## Sound

Browsers refuse sound before a gesture, so the page starts with the silent
field: every video is muted and inline, which every browser lets autoplay. The
first click, tap, or key press on the page turns the sound on with no dialog.
The page then plays the same composition with the runtime's `spatial_loops`
mix: each loop's own audio, at about 1/√N each so twelve loops are no louder
than one, panned by panel position in landscape. M, or the speaker, mutes and
unmutes. A video element is unmuted only after that first gesture and only
while the speaker is on. The mix passes through a gentle limiter, so its peaks
stay well below clipping.

The built-in loops have generated voices in D major pentatonic. Each voice has
its own register and figure: soft pads, filtered-noise swells, plucks, bells,
and quiet granular ticks. Each voice is scheduled on its loop's clock, so it
repeats with the picture. Web Audio produces the voices, which feed the
runtime's per-loop pan and gain.

## Built-in loops

Twelve canvas drawings (drift, bands, sweep, grain, tide, lattice, orbit, bloom,
moire, aurora, weave, pulse) move in whole cycles of their own periods, from
2.5 to 5.25 seconds, so the last frame meets the first. At load the page draws
them live as the panels at once. Meanwhile `MediaRecorder` records each one,
once, from `canvas.captureStream()` into a local WebM or MP4 blob. The
recordings then fade in and play through `compiler.js` and `runtime.js` like
any other video loop.

Recording in the page keeps the studio to five small static files with no media
to stage, but it costs a few seconds of drawing after load and depends on
`MediaRecorder`. Where `MediaRecorder` or `captureStream` is missing, or every
recording fails, the live canvases stay as the panels and their voices play
through the page's own audio context instead of the runtime.

## Library mode

A deployment can put a public clip library beside the page:
`library/manifest.json` (schema `simvltanea.public-demo/1`, written by
`tools/media/build_public_demo.py`, see `PUBLIC_DEMO.md`) and
`library/clips/<id>.mp4`. On load the page requests the manifest once. When it
validates, its clips replace the built-in loops. When it is absent, unreadable,
or invalid, the built-in loops play as before. `?gen=1` forces the built-in
loops without the request.

The manifest validates only if every one of these holds:

- the schema string matches;
- `clips` is a non-empty array;
- every `file` is exactly `clips/<id>.mp4`, where the id is 12 lowercase hex
  digits, and no id repeats;
- widths, heights, and byte sizes are positive whole numbers within bounds;
- the orientation agrees with the width and height;
- the duration lies between a quarter of a second and ten minutes.

Clips are fetched only for the roll on screen, never the whole library. Each
clip then goes through the same checks as a dropped file:

1. Its byte count must equal the manifest's.
2. Its SHA-256 must begin with its id.
3. Its codec, a decoded frame, and its whole-frame duration are checked as
   for your own videos.

A clip that fails is left out and its panel gets another. At most about 24
checked clips stay in memory, so rerolls are quick. While the page is idle,
it fetches the next shuffle's clips, unless the browser asks to save data. A
reroll cancels fetches it no longer needs.

A roll picks a family, a panel count, and then clips by their tags. It avoids
two clips with the same palette and shot when others exist, mixes portrait and
landscape clips, and prefers moods not yet on screen. The same seed with the
same manifest always picks the same clips, on any screen. After hand edits,
`&mix=` numbers the clips in id order. The tags only guide
the choice: they are never shown, logged, or written into the page.

The clips carry their own sound. After the first gesture each clip's audio
plays in the same spatial mix as your own videos, at about 1/√N per loop. The
generated voices are not used in library mode. Shuffle, panel taps, the
panel-count keys, the speaker, and reduced motion behave as with the built-in
loops.

`stage_studio` still writes only its five files. The library joins them at
deploy time:

```bash
PYTHONPATH=src python3 -m simvltanea.browser.browser_studio --output var/site/studio
python3 -m tools.publishing.stage_library_site --studio-out var/site/studio \
    --library /path/to/public-demo --site var/site/deploy
```

`stage_library_site` copies both into an absent or empty `--site`. It checks
everything before it writes, and it refuses each of these:

- a studio output that is not exactly the five files;
- a library without a valid manifest;
- a file in `clips/` that the manifest does not name;
- a listed clip that is missing, or whose size or digest differs;
- any other file in the library, including hidden files and symlinks.

## Privacy

**Your videos never leave this device. Nothing is uploaded.** The page reads,
checks, hashes, and plays dropped or picked files inside the browser. Its
content security policy permits only its own scripts, `layouts.json`, and the
optional `library/` from its own origin. Built-in loops, library clips, and your
own videos play from local `blob:` URLs. The page uses no analytics, fonts,
CDNs, or other network requests. Its one typeface is the system UI stack.

## Your own videos

Drop video files anywhere on the page, or use the add-yours icon. They replace
the built-in loops: all of them play at once, up to twelve, and later drops add
to them. Shuffle then rolls among your loops. A dropped
`simvltanea.layout-preset/1` or `simvltanea.layout-pair/1` JSON file becomes a
third layout family.

Each file passes four checks before it becomes a loop:

1. **Size cap.** Your files may total 512 MiB; the browser holds about twice
   that in memory. A file over the cap is refused by name.
2. **Playability.** The page reads the container and the first video track's
   codec (for example `avc1.64001E` or `hvc1.1.6.L93.B0`). It asks
   `video.canPlayType()` about that codec, then loads the file for real. The
   file is accepted only after a frame decodes.
3. **Duration.** The duration is floored to whole frames at 24 fps and declared
   as the exact fraction, so a loop never seeks past its end. Loops must last at
   least a quarter of a second.
4. **Digest.** Each file is hashed once with `crypto.subtle`, and the runtime's
   integrity check reuses that digest. Two files with the same bytes are refused.

## Supported media

| Property | Support |
| --- | --- |
| Containers | QuickTime `.mov`, MP4 `.mp4`/`.m4v`; WebM where the browser plays it |
| Video | H.264 everywhere; HEVC where the browser decodes it (Safari, Chrome on macOS) |
| Pixel formats | 8-bit `yuv420p` and full-range `yuvj420p` |
| Rotation | Display-matrix rotation tags; the browser reports the rotated size |
| Frame rate | Constant or variable; durations never assume an integer frame rate |
| Audio | Played after the first gesture, each loop's own track in the spatial mix; AAC is declared to the runtime, and other tracks play where the browser decodes them |
| Count | 1 to 12 loops with strips, 2 to 7 with authored, or your layout file's counts |
| Total size | 512 MiB |

## Runtime hook

`browser.runtime.js` reads optional fields from `window.compositionIO`. These
apply only when media arrives through the hook. Staged previews keep their
MP4-only, 256 MiB rules.

| Field | Effect |
| --- | --- |
| `type(source)` | The Blob MIME type for a video source; the runtime falls back to the path suffix, then `video/mp4` |
| `maxMediaBytes` | Raises the memory guard, capped at 512 MiB |

The studio compiles the silent v1 plan with `compiler.js`. After the first
gesture it presents that same plan as plan v2 `spatial_loops`, with
`master_volume`, `spatial_panning`, per-loop `gain` and `mute_on_hold`, and an
`audio_stream` on every source.

## Run it locally

`stage_studio(output)` writes ten flat files with relative URLs:
`index.html`, `runtime.js`, `compiler.js`, `studio.js`, `layouts.json`,
`lab.html`, `lab_model.js`, `lab_engine.js`, `lab_ui.js`, and `lab_audio.js`. It
refuses a directory that holds anything else, and staging twice yields
identical bytes.

The **Effects Lab** link opens a separate live instrument for overlapping
visual layers, swept comb and pass filters, and independently evolving sound
and picture clocks. See [Effects Lab](EFFECTS_LAB.md) for its controls and limits.

```bash
PYTHONPATH=src python3 -m simvltanea.browser.browser_studio --output var/site/studio
python3 -m http.server --directory var/site 8000
# Open http://localhost:8000/studio/
```

The page needs a secure context for `crypto.subtle` and the recordings. Use
`localhost` or HTTPS.

`src/simvltanea/browser/test_browser_studio.py` serves the staged studio under a
subpath in headless Chrome. It proves the following:

- the page plays with no interaction;
- a seed reproduces a roll, and shuffle changes it;
- the first click turns sound on and M mutes;
- a panel tap rerolls only that panel;
- the picker and a drop replace the loops;
- refusals (ProRes, over the cap, a duplicate) show a toast;
- reduced motion starts paused;
- the control bar fits from 360 pixels to 1440;
- nothing is requested beyond the staged files and the library manifest.

Its library tests serve a synthetic library of 30 FFmpeg test clips with a tone,
assembled by `stage_library_site`. They prove the following:

- library mode is used;
- only the roll's clips and the prefetched next roll are requested;
- a seed reproduces the same clips;
- a shuffle plays the prefetched roll;
- the clips' own audio plays after the first click;
- an invalid manifest falls back to the built-in loops;
- `?gen=1` forces the built-in loops.
