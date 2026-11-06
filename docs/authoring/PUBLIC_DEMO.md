# Public demo package

`tools/media/build_public_demo.py` turns exported, already-tagged Live Photos
clips into a public demo: small proxies plus a manifest the studio can load.
The private root is read-only input. Nothing is written into it.

```bash
python3 -m tools.media.build_public_demo --root /path/to/live-photos --out /path/outside/repo --dry-run
python3 -m tools.media.build_public_demo --root /path/to/live-photos --out /path/outside/repo --limit 20
```

`--out` must be outside the checkout or under `var/`, and must not contain the
private root. `--dry-run` prints counts only and writes nothing. Output is
counts only: no identifier, caption, file name or path of a single clip is
printed.

## Which clips are selected

A clip is published only if its tag record passes every rule. Each rule is a
named option, on by default, and can be relaxed with its `--no-...` form.
Unknown or missing facts exclude the clip.

| Rule | Option | Excludes the clip when |
| --- | --- | --- |
| needs_review | `--exclude-needs-review` | the record is not exactly `needs_review: false` |
| unsafe | `--exclude-unsafe` | safety is not verdict `clear` with no categories, or is missing |
| document_or_screen | `--exclude-document-or-screen` | the privacy flag is not exactly `false` |
| license_plate | `--exclude-license-plate` | the privacy flag is not exactly `false` |
| location_identifiable | `--exclude-location-identifiable` | the privacy flag is not exactly `false` |
| readable_text | `--exclude-readable-text` | the privacy flag is not exactly `false` |

Clips with no usable analysis, an unreadable record or no original video are
always excluded. The report lists how many clips each reason excluded (each
clip under the first reason that applies, plus the overlapping flag hits).

## Audio

`--audio keep` is the default: the owner decided that people and their voices
may be published, so each proxy carries one AAC 64k mono stream. `--audio mute`
writes no audio stream at all. Metadata is stripped either way. Stage-time
verification fails if the output does not follow the chosen rule.

## Proxies and metadata stripping

Each proxy is H.264 `yuv420p`, at most 480 px on the long side after the
display rotation is applied, CRF 28, `+faststart`. Global, stream and chapter
metadata are dropped (`-map_metadata -1`, `-map_chapters -1`, bit-exact
muxing), so no GPS, creation time or device tags survive. HDR and 10-bit
sources are skipped rather than published with wrong colors.

Every output is re-probed with `ffprobe` before the manifest is written. The
check fails closed: unexpected streams, tags, side data (rotation), chapters,
non-empty metadata boxes, a wrong audio rule or a hash that does not match the
file name stop the run with exit code 3 and no manifest is written.

Files are named `clips/<first 12 hex of the SHA-256 of the proxy>.mp4`, so no
original identifier is public. A re-run reuses existing files and rewrites the
manifest atomically. Files in `clips/` that the manifest does not list are
reported as orphans and never deleted.

## Manifest schema

`manifest.json`, schema `simvltanea.public-demo/1`:

```json
{
  "schema": "simvltanea.public-demo/1",
  "clips": [
    {
      "id": "0123456789ab",
      "file": "clips/0123456789ab.mp4",
      "width": 270,
      "height": 480,
      "orientation": "portrait",
      "duration_seconds": 3.0,
      "bytes": 250000,
      "tags": {
        "keywords": ["sea", "light"],
        "mood": ["calm"],
        "shot": "wide",
        "palette": ["blue"]
      }
    }
  ]
}
```

`keywords` are limited to the first five short plain words. `mood`, `shot` and
`palette` come from the fixed tag vocabularies. Captions, people, sharing
notes, settings, subjects, original identifiers, timestamps and locations are
never copied.
