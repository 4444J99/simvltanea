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
refuse any other path inside the checkout.

```text
<root>/
├── album-ids.json                 Photos media item ids, in album order
├── export-manifest.jsonl          one receipt per completed item
├── export-failures.jsonl          one line per failed attempt
├── STOP                           optional; created by you to stop the export
├── originals/
│   └── <uuid>/
│       ├── <uuid>.mov             primary paired video
│       ├── <uuid>.<jpg|heic>      primary still
│       ├── <uuid>.extraN.<ext>    any additional exported file
│       └── .done                  JSON receipt: sizes, sha256, ffprobe facts
└── analysis/                      written by tag_clips.py
    ├── frames/<uuid>/f0-f2.jpg    temporary; deleted once the clip is tagged
    ├── features/<uuid>.json       local features (palette, luma, motion)
    ├── batches/<batch>.json       which clips went into which batch
    ├── tags/<uuid>.json           final per-clip record
    ├── tags.jsonl                 append-only copy of the records
    └── ledger.jsonl               cost estimate per collected batch
```

A `.done` receipt marks an item as finished. Items without one are exported
again from scratch, so an interrupted run resumes safely.

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
`--refresh-ids`, and `--timeout`. Exit codes are 0 (all exported), 1 (failures
remain), 2 (stopped), and 3 (refused or deferred by the metered-link rule).

Tag the clips. Start with `--dry-run`, which extracts frames and computes local
features on this machine, prints the projected cost, and uploads nothing:

```sh
python3 -m tools.media.tag_clips run --root "$LIVE_ROOT" --limit 20 --dry-run
python3 -m tools.media.tag_clips run --root "$LIVE_ROOT" --limit 20 --confirm-upload
python3 -m tools.media.tag_clips report --root "$LIVE_ROOT"
```

The commands are `prepare` (frames and local features), `submit`, `collect
--batch ID` (poll, store results, delete frames), `run` (prepare, submit,
collect and report), and `report`. Options are `--model`, `--frame-px`
(default 640), `--batch-size`, `--poll`, and `--limit`.

Credentials use the SDK's standard resolution: set `ANTHROPIC_API_KEY`. On
macOS you can instead pass `--keychain-service NAME` to read the key from a
Keychain item. The tool never prints a key. The exporter needs neither
Pillow nor the SDK. The tagger's `prepare` step needs Pillow and FFmpeg, and
the steps that call the API need the SDK; without it they stop with an install
hint.

### What the tagger uploads

For each clip, `submit` sends the Anthropic Batch API:

- three downscaled JPEG frames (start, middle, end; long side `--frame-px`,
  default 640 px),
- one fixed instruction (`PROMPT` in `tag_clips.py`) that asks for a
  controlled-vocabulary description and a safety verdict, and forbids
  identifying or naming anyone, and
- the clip's UUID as the request `custom_id`, an opaque identifier used only to
  match results to clips locally.

It sends no file names, captions, album names, paths, locations or metadata,
and no full-resolution frames or video. Local features are never uploaded.
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
result, is marked `needs_review` for a human decision. A clip's result is
final once collected;
`submit` skips clips that already have a tag record. Submitting before
collecting a pending batch would send the same clips again.

### Network guidance

A first export downloads about 27 GB for 6,500 items. On an iPhone Personal
Hotspot (gateway `172.20.10.x`, interface flagged `constrained`) that is slow,
uses the owner's data plan, and starves other jobs, so the exporter refuses to
start there:

```sh
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT" --wait
python3 -m tools.media.export_photos_album --root "$LIVE_ROOT" --hotspot-budget-gb 2
```

- `--wait` sleeps while the link is metered and resumes on a real network.
- `--hotspot-budget-gb N` allows about N GB over a metered link, then defers
  the remaining items (exit 3). With several workers it can overshoot by a few
  items.
- Metered-link detection uses `route` and `ifconfig` and works on macOS only.
  On other platforms, or if those tools are missing, it reports an unmetered
  link.

Prefer Wi-Fi or Ethernet for the first export. A rerun costs nothing for
finished items. The tagger uploads about 3 small JPEGs per clip, so a hotspot
is a poor fit for it as well; check the projected cost first.
