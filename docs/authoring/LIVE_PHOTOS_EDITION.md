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
