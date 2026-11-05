# Proxy clips

A proxy is a small copy of a clip made for playback inside the composition. It
is not an archival copy. Keep your originals.

## Why low resolution is enough

Each loop fills a cell with `fit: cover`, so every panel is a tightly cropped
window onto its video. Together the panels form one new image. No single clip is
shown at full size, so its full resolution is never used. Playing 8 to 12
phone-resolution HEVC streams at once also stutters on phones and laptops, while
small H.264 proxies play smoothly in any browser.

The owner chooses quality over size and has said that low resolution and low
quality are acceptable for proxies. Raise `--short-side` or lower `--crf` if a
composition needs more detail.

## One command

```bash
independent-loop-compositor proxy phone-clips --out proxies
```

Use `--dry-run` first to see the plan without encoding anything. Each clip gets
one line, for example:

```text
portrait.MOV: HEVC 1440x1080 rot -90 VFR yuvj420p -> 540x720 24fps h264 0.4 MB (4.1 MB)
```

The line shows the source codec, coded size, rotation, constant or variable
frame rate and pixel format, then the proxy size, frame rate, codec, proxy file
size and original file size. A final summary gives counts, total sizes and the
names of any clips that failed. Add `--json` for a machine-readable report with
each clip's input name, output name, settings, sizes, SHA-256 and duration. The
report contains no absolute paths.

## Defaults

| Option | Default | Meaning |
| --- | --- | --- |
| `--out` | `./proxies` | Output directory, created if missing |
| `--short-side` | `540` | Short side in pixels; even, never upscaled |
| `--crf` | `28` | x264 quality (1 to 51, lower is better) |
| `--fps` | `24` | Constant output frame rate, for example `30000/1001` |
| `--dry-run` | off | Probe and print the plan only |
| `--force` | off | Replace existing proxies in `--out` |
| `--json` | off | Print the report as JSON |

Every proxy is `<stem>.mp4` encoded as follows:

- H.264 (`libx264`), Main profile, `-preset medium`, `yuv420p`, `-movflags +faststart`.
- Rotation baked into the pixels: a portrait phone clip stored landscape with a
  rotation tag comes out portrait, with no rotation tag or display matrix left.
- Constant frame rate at `--fps`, even when the source has a variable frame rate.
- No audio, because the composition is silent.
- Short side scaled to `--short-side` with Lanczos, keeping the aspect ratio. A
  smaller clip keeps its size, rounded down to even numbers.
- Limited range BT.709 (`-color_range tv`, BT.709 matrix, primaries and
  transfer). Full-range phone video (`yuvj420p`) is converted explicitly from
  its own matrix (BT.709, or BT.601 / SMPTE 170M). An untagged HD clip is read
  as BT.709 and an untagged SD clip as BT.601, so blacks stay black and whites
  stay white.
- Metadata such as location and capture date is not copied.

After each encode the proxy is probed again. If it is not H.264 `yuv420p`,
limited range, silent, unrotated, constant at `--fps`, within the short side
bound and within one frame of the source duration, that clip fails with a
message and nothing is written for it.

## Inputs

An input is a file or a directory. Directories are read without recursion and
hidden files are ignored. Supported extensions are `.mov`, `.mp4`, `.m4v`,
`.mkv`, `.webm` and `.avi`, in any letter case. HEVC and H.264 phone clips
work, as does any 8-bit video FFmpeg can decode.

These clips are refused with a one-line message while the other clips are
still converted:

- 10-bit or higher clips, including iPhone HDR (HLG or Dolby Vision). Tone
  mapping is out of scope; export an 8-bit SDR copy first.
- HDR transfer (PQ or HLG) or BT.2020 wide-gamut clips at any bit depth.
- Unreadable or damaged files.

The exit code is 1 if any clip failed and 0 otherwise.

## Safe output

- Proxies go only into `--out`. A directory that holds an input clip is
  rejected as `--out`, so nothing is written next to or over an original.
- An existing proxy is kept and reported as skipped unless you pass `--force`.
- Two inputs with the same stem get `-2`, `-3` suffixes in input order (for
  example `clip.mp4` and `clip-2.mp4`), and the line for each renamed clip shows
  its new name.
- Each proxy is written to a hidden temporary file and only takes its final name
  after validation.

If `ffmpeg` or `ffprobe` is missing, the command says so in one line and points
to `independent-loop-compositor doctor`.
