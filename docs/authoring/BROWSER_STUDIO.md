# Browser studio

The SIMVLTANEA studio is a static, client-only web page. A visitor chooses or
drops two to seven of their own video loops, and the page plays them at the
same time, each on its own clock, in the authored portrait or landscape layout
for that count. The visitor needs no installation, Python, or FFmpeg. The page
refuses one loop or more than seven with a clear message. It never pads,
repeats, or duplicates a loop to reach a supported count.

## Privacy

**Your videos never leave this device. Nothing is uploaded.** The page reads,
checks, hashes, and plays the chosen files inside the browser. Its content
security policy permits only its own scripts and `layouts.json` from its own
origin. The chosen videos play from local `blob:` URLs. The page uses no
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

The list order is the authored cell order. Each loop has Up, Down, and Remove
buttons. Play compiles the composition with `compiler.js` and starts the
unmodified `runtime.js` through `window.compositionIO`. All loops start muted
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
| Count | 2 to 7 loops |
| Total size | 512 MiB |

Firefox and many Linux or Windows browsers cannot decode HEVC. Those browsers
name the file and its codec in the refusal message. An H.264 ("Most
Compatible") export plays almost everywhere.

## Playback controls

- **Play/Pause** uses the same gesture as a click on the stage. Space toggles
  playback anywhere outside a focused control.
- **Restart** returns every loop to the beginning of the piece.
- **Layout: Auto/Portrait/Landscape.** Auto follows the stage shape. The other
  two pin the authored layout through `runtime.setOrientation()`. Switching
  moves loop boxes only. No loop is reset, duplicated, or substituted, and
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
It refuses a directory that holds anything else, and staging twice yields
identical bytes.

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
than the cap exercise the refusals.
