# Browser studio

The SIMVLTANEA studio is a static, client-only web page. A visitor picks a
layout family and a number of panels, then chooses or drops one of their own
video loops per panel. The page plays them at the same time, each on its own
clock, in the family's portrait or landscape layout for that count. The visitor
needs no installation, Python, or FFmpeg. When the number of loops differs from
the number of panels, the page says how many to add or remove. It never pads,
repeats, or duplicates a loop to reach the chosen count.

## Layout family and panels

The page opens on **Strips** with **5** panels. Strips fill the stage edge to
edge with one band per loop: rows in portrait, columns in landscape. Each
strips count carries its zoom: the state-wide slice, which zooms in more the
fewer panels there are (8 times at one panel, about 3 times at five, and 1.8
times at twelve). Strips are engineering presets, not artist-approved designs.

| Control | Effect |
| --- | --- |
| **Strips / Authored** | Chooses the family. **Authored** plays the hand-placed engineering pairs |
| **Panels** | Lists exactly the counts the chosen family offers: 1 to 12 for strips, 2 to 7 for authored |
| **Use my own layout file** | Reads a preset or pair file and offers it as the **My file** family |

The families and their counts come from `layouts.json`, never from a constant
in the page. A switch keeps the panel count when the new family offers it.
Otherwise it moves to the nearest count and says so in one line, for example
"Authored layouts cover 2 to 7 panels; Panels is now 7." A count is never moved
silently from one family to another. When the loops do not match the panels,
the message offers both remedies, for example "3 loops chosen for 5 panels.
Add 2 more, or set Panels to 3."

## Your own layout file

**Use my own layout file** accepts a JSON file in one of two formats. Like the
videos, it is read on the device and never uploaded.

- A `simvltanea.layout-preset/1` preset, for example
  `examples/layout-presets/strips.json` with changed weights, zoom, jitter, or
  corner radius. Panels then lists the counts the preset declares.
- A `simvltanea.layout-pair/1` pair: one authored `{portrait, landscape}` pair
  for one count. Panels then offers that count only.

The page validates the file exactly as Python `load_layout_file` does, with the
compiler's `loadLayoutBytes`. A refused file leaves the current layout in place
and shows one line that names the file, the location, and the reason, with the
same reason code as Python. For example: "mine.json, count 3, portrait:
full_bleed requires the rects to tile the unit square exactly; they cover
2999999999/3000000000". Loop k (the k-th listed video) plays in the cell for
`loop-k`. A pair whose cells use other loop names is relabelled in portrait
cell order.

## Privacy

**Your videos never leave this device. Nothing is uploaded.** The page reads,
checks, hashes, and plays the chosen files inside the browser. Its content
security policy permits only its own scripts and `layouts.json` from its own
origin. The chosen videos play from local `blob:` URLs, and a chosen layout
file is read in place. The page uses no
analytics, fonts, CDNs, or other network requests.

## What the studio does with each file

1. **Size cap.** The chosen files may total 512 MiB. The browser holds about
   twice that in memory while it plays them. A file that would exceed the cap
   is refused by name.
2. **Playability.** The page reads the container and the first video track's
   codec. QuickTime and MP4 share one box structure, so both report a codec
   string such as `avc1.64001E` or `hvc1.1.6.L93.B0`. The page asks
   `video.canPlayType()` about that codec and then loads the file for real. It
   accepts the file only after the browser decodes a frame. Otherwise the
   message reads "This browser cannot play `name` (`type`, codec)".
3. **Duration.** `video.duration` is a float. The page floors it to whole
   frames of the composition (24 fps) and declares the exact fraction
   `frames/24`. A loop therefore never seeks past its end, and the declared
   duration stays within one frame of the real one. Loops must last at least
   a quarter of a second.
4. **Digest.** Each file is hashed once with `crypto.subtle.digest('SHA-256')`.
   The runtime's integrity check reuses that digest. Two files with the same
   bytes are refused, because every loop needs its own video.

The list order is the cell order: the first listed loop plays in `loop-1`, the
first strip. Each loop has Up, Down, and Remove buttons. Play compiles the
composition, with the chosen layout and, for strips, its zoom slice, with
`compiler.js`. It then starts the unmodified `runtime.js` through
`window.compositionIO`. All loops start muted
and inline, and only after the Play press. The studio never autoplays, which
also respects `prefers-reduced-motion`.

## Supported media

| Property | Support |
| --- | --- |
| Containers | QuickTime `.mov`, MP4 `.mp4`/`.m4v`; WebM where the browser plays it |
| Video | H.264 everywhere; HEVC where the browser decodes it (Safari, Chrome on macOS) |
| Pixel formats | 8-bit `yuv420p` and full-range `yuvj420p` |
| Rotation | Display-matrix rotation tags; the browser reports the rotated size |
| Frame rate | Constant or variable; durations never assume an integer frame rate |
| Audio | Allowed in the file and always muted; the composition is silent |
| Count | One loop per panel: 1 to 12 with strips, 2 to 7 with authored, or the counts of your own layout file |
| Total size | 512 MiB |

Firefox and many Linux or Windows browsers cannot decode HEVC. Those browsers
name the file and its codec in the refusal message. An H.264 ("Most
Compatible") export plays almost everywhere.

## Playback controls

- **Play/Pause** uses the same gesture as a click on the stage. Space toggles
  playback anywhere outside a focused control.
- **Restart** returns every loop to the beginning of the piece.
- **Layout: Auto/Portrait/Landscape.** Auto follows the stage shape. The other
  two pin the family's portrait or landscape layout through
  `runtime.setOrientation()`. Switching moves loop boxes only. No loop is reset, duplicated, or substituted, and
  every clock keeps advancing.
- **Auto-repeat** is on by default. When the piece finishes, the studio
  restarts it through the runtime's restart-after-finish path.
- **Change loops** releases the media and returns to the list.

The piece lasts two minutes by default. The `seconds` query parameter sets
another length, capped at the compiler's 14400 frames (600 seconds at 24 fps).
For example, `index.html?seconds=30` sets 30 seconds. Each pass through a loop
starts it again, and the compiler allows at most 1024 starts per loop on
average across the selection. A long piece with very short loops can exceed
that budget: the quarter-second minimum fits only up to 256 seconds. The page
then keeps Play disabled, says so before Play is pressed, and names the longest
`seconds` value that fits the chosen loops.

## Runtime hook

`browser.runtime.js` reads optional fields from `window.compositionIO`. These
apply only when media arrives through the hook. Staged previews keep their
MP4-only, 256 MiB rules.

| Field | Effect |
| --- | --- |
| `type(source)` | The Blob MIME type for a video source; the runtime falls back to the path suffix, then `video/mp4` |
| `maxMediaBytes` | Raises the memory guard, capped at 512 MiB |

Video paths may use any short lowercase alphanumeric suffix, such as
`media/<sha256>.mov`.

## Run it locally

`stage_studio(output)` writes five flat files with relative URLs:
`index.html`, `runtime.js`, `compiler.js`, `studio.js`, and `layouts.json`.
`layouts.json` is the `simvltanea.layout-bundle/2` from `layout_bundle_v2()`:
the strips family (1 to 12, the default) and the authored family (2 to 7). The
page also reads a legacy authored-only bundle, which offers the authored
family alone. It refuses a directory that holds anything else, and staging
twice yields identical bytes.

```bash
PYTHONPATH=src python3 -m simvltanea.browser.browser_studio --output var/site/studio
python3 -m http.server --directory var/site 8000
# Open http://localhost:8000/studio/
```

The page needs a secure context for `crypto.subtle`. Use `localhost` or HTTPS;
GitHub Pages works under any subpath. In Python, call
`simvltanea.browser.stage_studio(Path(...))`.

`src/simvltanea/browser/test_browser_studio.py` serves the staged studio under
a subpath and drives the real file input in Chrome. It uses synthetic loops
and phone-like clips that FFmpeg generates at test time: H.264 and HEVC MOV, a
rotation tag, variable frame rate, and audio. A ProRes file and a file larger
than the cap exercise the refusals. The layout tests check the strips default
at five panels and bundles served with other counts. They play strips with 1,
3, 8, and 12 loops edge to edge with their zoom and play authored pairs for 2
to 7 loops. They also load valid and invalid preset and pair files from
`fixtures/layouts/`.
