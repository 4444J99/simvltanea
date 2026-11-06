# Live Photos edition

`simvl-live` is an edition configuration in `editions/registry.json`, sourced
from the exact `simvl-live` album in Photos.app. Additional configurations
can be added as independent entries in the same registry.

The source selects only Live Photo motion assets (`live_photos_only`), reads
album membership directly from Photos.app (`album_via_photos_app`), and
removes the default import cap (`all_local`). Existing hidden, trashed, and
invisible asset exclusions remain active.

On 2026-10-02, Photos.app reported 6,530 album members; 6,482 matched the
eligible Live Photo catalog rows. The cached database album relation had
zero members, so direct Photos.app membership is required for this album.
The 48 unmatched members have not been individually classified.

A 12-item preview was imported and synchronized, leaving the full-album
configuration intact:

```sh
.venv/bin/python -m tools.editions.build_edition simvl-live --limit 12 --sync
```

Preview output is `var/site/editions/simvl-live/`. Personal media and
identifying manifests remain in ignored local generated storage.

Removing `--limit 12` requests the full eligible album import. That is a
large export; it was not executed during this configuration session. The
web proxy configuration currently limits proxies to 72, independently of
the source import size. All-album web playback needs a paging strategy
before claiming that thousands of assets are available in the player.

## Exporting the album originals

`tools/media/export_photos_album.py` copies the original files of every Live
Photo in a Photos.app album to a private storage root. It is macOS only: it
drives Photos.app through `osascript`, with the AppleScript embedded in the
Python source. `tools/media/tag_clips.py` then describes and safety-screens
each exported clip. Both are optional local tools; nothing in the edition
build depends on them.

### Why AppleScript export

- Direct reads of a `.photoslibrary` package are blocked by macOS privacy
  (TCC) for agent processes, but AppleScript export from Photos.app works.
  The tools therefore never read from, or write inside, a library package, and
  `--root` is refused if it resolves to a path inside one.
- Originals are in iCloud ("Optimize Mac Storage"). A first export waits on a
  per-item download of about 4 MB per Live Photo: a JPEG or HEIC still plus a
  `.mov` of about 1.8 MB. Photos overlaps downloads when several exports are
  in flight, so the exporter runs 12 workers by default.
- Original filenames collide across assets (`FullSizeRender`, `IMG_xxxx`), so
  each asset gets its own folder named by its UUID.
- The default AppleEvent timeout (120 s) kills queued exports with error
  -1712. Every export runs inside `with timeout of 3600 seconds`; change it
  with `--timeout`.
- If a host process holds the Photos automation permission, `--launcher
  "command prefix"` runs `osascript` through it.

### Storage layout

Choose a root outside the checkout; 6,500 Live Photos are roughly 27 GB. A
root inside the checkout must be under `var/`, which Git ignores. The tools
refuse any other path inside the checkout, comparing paths case-insensitively
because the default macOS volume ignores case.

The check does not depend on which worktree runs the code. If the root lies
inside any Git working tree (another checkout or a sibling worktree of this
repository), the tools ask Git (`git check-ignore`) and accept it only when
that repository ignores the path. A root outside every repository is
accepted. Without `git` on the `PATH`, only the case-insensitive checkout
comparison applies, and the tool says so on stderr. Use a subdirectory of
`var/`, not `var/` itself, because Git ignores the contents of `var/` but not
the folder.

```text
<root>/
├── album-ids.json                 Photos media item ids, in album order
├── export-manifest.jsonl          one receipt per completed item
├── export-failures.jsonl          one line per failed attempt
├── STOP                           optional; created by you to stop the export
├── .export.lock                   held while an export runs (one run per root)
├── originals/
│   └── <uuid>/
│       ├── <uuid>.mov             primary paired video
│       ├── <uuid>.<heic|jpg|jpeg|png>  primary still (first image file)
│       ├── <uuid>.extraN.<ext>    any additional exported file
│       └── .done                  JSON receipt: sizes, sha256, ffprobe facts
└── analysis/                      written by tag_clips.py
    ├── frames/<uuid>/f0-f2.jpg    temporary; deleted once the clip is tagged
    ├── features/<uuid>.json       local features (palette, luma, motion, displayed geometry)
    ├── failed/<uuid>.json         clip with no usable frames; skipped until deleted
    ├── batches/<batch>.json       which clips went into which batch
    ├── tags/<uuid>.json           final per-clip record (the authoritative one)
    ├── tags.jsonl                 append-only copy as of collection time (historical)
    └── ledger.jsonl               cost estimate per collected batch
```

A `.done` receipt marks an item as finished. Items without one are exported
again from scratch, so an interrupted run resumes safely. The receipt is
checked again right before an unfinished folder is deleted, so a run that
waited on the metered-link rule never removes an item another run finished
meanwhile. A sidecar such as `.aae` is never the primary still: it is kept as
`<uuid>.extraN.aae`.

Only one export can run per root. The exporter takes an exclusive lock on
`.export.lock`; a second run exits immediately with code 4. Duplicate ids in
`album-ids.json` are exported once, in first-seen order. Ctrl-C cancels the
items still queued (one line says how many), lets in-flight items finish, and
exits with code 130; re-run to resume.

### Receipt and feature geometry

A phone portrait clip is a landscape-coded stream with a display rotation of
90 or 270 degrees, so its coded size says "landscape" for a clip that plays
upright as portrait. The receipt and the tag features therefore keep the coded
and the displayed geometry apart.

Receipt (`originals/<uuid>/.done`, schema `live-photo-export/v1`), under
`video`:

| Key | Meaning |
| --- | --- |
| `width`, `height` | the CODED size, as the schema has always defined them |
| `rotation` | display rotation in degrees, ffprobe's sign (`-90` clockwise, the phone-portrait case) |
| `display_width`, `display_height` | the coded size after the rotation is applied, before any container clean-aperture crop (a modern FFmpeg decode of a phone clip is about 9% smaller per axis; the orientation word is unaffected) |

`rotation`, `display_width` and `display_height` are optional: receipts written
before issue #60 have only the coded `width` and `height`, and every tool still
reads them. The exporter reads the rotation from a plain
`ffprobe -show_streams -show_format -of json` run (the stream's display-matrix
side data first, then the legacy `rotate` tag). A missing, unreadable, non-finite
or not-a-multiple-of-90 rotation counts as 0.

Features (`analysis/features/<uuid>.json`, and the `features` block of
`analysis/tags/<uuid>.json`): `width`, `height` and `orientation` describe the
DISPLAYED clip. `orientation` is `portrait` when the displayed height exceeds
the width and `landscape` otherwise, so a square clip is `landscape`. The keys
`rotation`, `coded_width` and `coded_height` keep the stored facts. When a
receipt has no `rotation`, `prepare` asks `ffprobe` about the original video
itself; if that fails the clip is marked failed rather than tagged from the
coded size. Luma, saturation, hue, motion and palette were never affected: the
frames are extracted already rotated.

### Private material

Everything under the root is private and is never committed: the media, the
receipts and manifests, the album ids, the frames, and the analysis. The
exporter writes only UUIDs, sizes, hashes and technical video facts to its
receipts, manifests and logs. It records no file names, captions or paths, and
its failure lines carry an error code instead of Photos' message. Tag records
contain model-written captions and are as private as the media. Reports print
counts and vocabulary terms only.

Only derived, reviewed, consented material belongs in an edition. Do not copy
files, UUIDs or captions from the root into tracked files.

### Commands

Install the optional dependencies for the tagger. They are separate from the
`verification` extra:

```sh
python3 -m pip install -e ".[analysis]"
```

Export (set `LIVE_ROOT` to a directory outside the checkout):

```sh
export LIVE_ROOT=/path/outside/the/checkout/live-photos
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT" --limit 12   # trial
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT"              # whole album
touch "$LIVE_ROOT/STOP"                                                      # stop after in-flight items
rm "$LIVE_ROOT/STOP"                                                         # then re-run to resume
```

Useful options: `--album NAME` (exact name, default `simvl-live`), `--workers`,
`--offset`, `--limit`, `--rounds` (retry rounds for failures, default 3),
`--refresh-ids`, and `--timeout`. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | all in-scope items exported |
| 1 | failures remain after the retry rounds, even if `STOP` also ended the run |
| 2 | stopped by `STOP` with no failures left |
| 3 | refused or deferred by the metered-link rule |
| 4 | another export holds the lock for this root |
| 5 | a local file error; the message shows the error type and no path |
| 130 | interrupted by Ctrl-C |

Tag the clips. Start with `--dry-run`, which extracts frames and computes local
features on this machine, prints the projected cost, and uploads nothing:

```sh
python3 -m tools.media.tag_clips run --root "$LIVE_ROOT" --limit 20 --dry-run
python3 -m tools.media.tag_clips run --root "$LIVE_ROOT" --limit 20 --confirm-upload
python3 -m tools.media.tag_clips report --root "$LIVE_ROOT"
```

The commands are `prepare` (frames and local features), `submit`, `collect
--batch ID` (poll, store results, delete frames), `collect --pending` (collect
every batch that has no line in `ledger.jsonl` yet), `run` (prepare, submit,
collect every pending batch, and report), and `report`. Options are `--model`,
`--frame-px` (default 640, at most 1024), `--batch-size` (default 200),
`--poll`, and `--limit`. `refresh-local` (below) corrects the geometry of clips
that are already tagged. A local file error exits with code 5 and prints only
the error type.

`prepare` extracts the three frames of a clip afresh each time (it deletes the
clip's frame folder first), so a frame never comes from an earlier run with a
different `--frame-px`. It stops with the install hint before extracting
anything if Pillow is missing.

The frames come from the video stream, not the container. A Live Photo's audio
can outlast its picture (for example 3 video frames over 0.4 s inside a 0.66 s
container), so `prepare` reads the video stream's frame count with `ffprobe`
and decodes the frames at about 10, 50 and 90 percent of the frame numbers. A
position with no image falls back to the last decodable frame. A clip with
fewer than three frames repeats its nearest frames, so the model still gets
three images.

One unusable clip never stops the run. If no frame or feature can be made for
a clip (a file ffmpeg cannot decode, an unreadable frame, a malformed receipt),
`prepare`, `submit` and `run` write `analysis/failed/<uuid>.json`, skip the
clip, continue with the others, and print `skipped N unusable clip(s)`. The
marker holds only `uuid`, `error` (`frame_extraction_failed`) and `attempts`
(the number of ffmpeg runs tried); it holds no path, file name or ffmpeg text.
A clip with a marker is not retried automatically. Delete its marker to try it
again. `report` prints `clips failed frame extraction: N`. A file error on the
root itself still exits with code 5.

#### Correcting clips tagged with the coded orientation

Clips tagged before issue #60 carry the coded geometry. `refresh-local`
corrects them without the API, a key, Pillow or frames. It runs a fresh
`ffprobe` on each original and rewrites only `width`, `height`, `orientation`,
`rotation`, `coded_width` and `coded_height` inside `features` in
`analysis/tags/<uuid>.json` and `analysis/features/<uuid>.json`. Every other key
and feature, including the model's analysis, the safety and privacy fields and
the cost, stays as it was, in the same order. Copy `analysis/` before running
it, and run it with `--dry-run` first:

```sh
cp -R "$LIVE_ROOT/analysis" "$LIVE_ROOT/analysis.backup"
python3 -m tools.media.tag_clips refresh-local --root "$LIVE_ROOT" --dry-run
python3 -m tools.media.tag_clips refresh-local --root "$LIVE_ROOT"
```

The command uses the same private-root guard as the other commands. It prints
counts only: clips examined, changed, unchanged, skipped because the original
is missing, skipped because the probe was unreadable, and the portrait and
landscape counts before and after. A skipped clip is never guessed. It is
idempotent: a clip whose geometry is already right is not rewritten, so a
second run reports 0 changed. Clips under `analysis/failed/` are ignored.

The per-clip files in `analysis/tags/` are the authoritative records.
`analysis/tags.jsonl` is a historical copy as of collection time and keeps the
old geometry; `refresh-local` does not touch it, `ledger.jsonl` or the
`tags-v1-pilot*` files. Read `analysis/tags/<uuid>.json`, not `tags.jsonl`.

Credentials use the SDK's standard resolution: set `ANTHROPIC_API_KEY`. On
macOS you can instead pass `--keychain-service NAME` to read the key from a
Keychain item. The tool never prints a key. The exporter needs neither
Pillow nor the SDK. The tagger's `prepare` step needs Pillow and FFmpeg, and
the steps that call the API need the SDK; without it they stop with an install
hint.

### What the tagger uploads

For each clip, `submit` sends the Anthropic Batch API:

- three downscaled JPEG frames (start, middle, end; long side `--frame-px`,
  default 640 px, capped at 1024 px),
- one fixed instruction (`PROMPT` in `tag_clips.py`) that asks for a
  controlled-vocabulary description and a safety verdict, and forbids
  identifying or naming anyone, and
- the clip's UUID as the request `custom_id`, an opaque identifier used only to
  match results to clips locally.

It sends no file names, captions, album names, paths, locations or metadata,
and no video. Frames are thumbnails: `--frame-px` is capped at 1024, so a
full-resolution image cannot be uploaded. Local features are never uploaded.
Nothing is sent unless you pass `--confirm-upload`; `submit` and `run` stop
before any work without it, and `prepare`, `report` and `--dry-run` never
contact the API. Frames are deleted once a clip's result is collected. Frames
from a `--dry-run` stay until the clip is tagged.

The model returns structured tags (subjects, setting, camera, motion, shot,
palette, mood, a caption, people and privacy flags, and a safety verdict).
Safety and privacy are separate questions. The safety verdict asks only
whether anything harmful is in the clip (explicit content, graphic violence,
weapons, drugs, hate symbols, self-harm, a child in a sensitive context,
visible distress); ordinary personal footage such as selfies, portraits or
people sleeping is `clear`. How private the moment is goes in
`privacy.sharing_sensitivity` (`low`, `moderate`, `high`), which never affects
the verdict. In a 38-clip pilot, a prompt that mixed the two sent 42% of clips
to review; separating them cleared all 38 and recorded 15 `low` and 23
`moderate`. Anything whose verdict is not `clear`, and any refusal or invalid
result, is marked `needs_review` for a human decision. A refusal, an invalid
result or a tag is final once collected, and `submit` skips clips that have a
tag record.

Transient results (`errored`, `expired`, `canceled`) are not final. They write
no tag record and keep the clip's frames; the batch's ledger line counts them
(`transient`), and the clip is selected again by the next `submit` or `run`.
Results whose `custom_id` is not a clip of that batch are ignored and counted
(`ignored`).

`submit` and `run` never send a clip that sits in a batch without a ledger
line, so pressing Ctrl-C while `run` polls and then running it again does not
upload the same clips twice. Collect those batches with `collect --pending`
(`run` does it too). A batch record that cannot be read stops `submit` rather
than risk a second upload.

Batches are created with the SDK's retries turned off (`max_retries=0` for
`batches.create` only) and hold at most 200 clips by default. A retried
multi-megabyte upload could create a billed batch that the tool never
recorded. Without retries a lost reply fails the command instead; a batch that
did get created then shows up as a pending batch in the Anthropic Console,
where you can see it. The smaller default keeps each upload small.

### Network guidance

A first export downloads about 27 GB for 6,500 items. On an iPhone Personal
Hotspot (gateway `172.20.10.x`, interface flagged `EXPENSIVE` or
`CONSTRAINED`) that is slow, uses the owner's data plan, and starves other
jobs, so the exporter refuses to start there:

```sh
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT" --wait
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT" --hotspot-budget-gb 2
```

- `--wait` sleeps while the link is metered and resumes on a real network.
- `--hotspot-budget-gb N` allows about N GB over a metered link, then defers
  the remaining items (exit 3). The budget counts completed exports only. The
  real transfer can exceed it by the items in flight (up to `--workers`) and by
  downloads of attempts that failed, timed out or are retried, none of which
  are counted. A killed `osascript` does not stop Photos from finishing its
  download.
- Metered-link detection uses `route` and `ifconfig -v` and works on macOS
  only. It checks the default route's gateway and the `EXPENSIVE` and
  `CONSTRAINED` flags in the `eflags=` and `xflags=` lines of `ifconfig -v`
  (plain `ifconfig` does not print them). When the default route goes through
  a tunnel (`utun*`, `ppp*`, `ipsec*`), it also inspects the active `en*`
  interfaces, so a VPN does not hide a hotspot. On other platforms, or if
  those tools are missing, it reports an unmetered link.

Prefer Wi-Fi or Ethernet for the first export. A rerun costs nothing for
finished items. The tagger uploads about 3 small JPEGs per clip, so a hotspot
is a poor fit for it as well; check the projected cost first.
