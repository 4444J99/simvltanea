# Local personal Photos preview

The Mac checkout was fast-forwarded from `0324129` to origin main
`f063a3d`. The clean tracked checkout did not contain the uncommitted
Codespace archival-film implementation described in the handoff.

The authorized Photos.app importer exported 12 personal videos using its
oldest-first selection, including Live Photos eligibility and a 45-second
maximum clip duration. The selected videos date from 2010 through 2013.
This is a fresh selection under the documented defaults; an earlier exact
selection manifest was not found in the workspace search.

Private originals and their identifying manifest remain generated local
data under `var/samples/photos-import/` and
`var/work/project.photos-local.json`. No personal media was published or
committed. The editable package is installed in `.venv`.

The personal project's landing output and web proxies were isolated under
`var/site/editions/photos-personal/`. Its public-format receipt is
`flash-copy.json` in that directory. The synthetic inaugural fixture was
built separately and remains available alongside it in `var/site/index.html`.

Chromium decoded the personal preview and advanced playback from 0.024 to
1.528 seconds without a media error. The local site is served at
`http://127.0.0.1:8001/`; port 8000 was already occupied by VS Code.
Full-resolution story/reel exports were not completed; browser proxies and
the interactive preview were completed.

The registry verifier currently fails on macOS because it resolves logical
path references to absolute paths before rejecting `/Users/` as a private
token. This is an existing verification portability issue, not evidence
that personal source paths were added to the tracked edition registry.

To rebuild the preserved local preview without reselecting Photos assets:

```sh
.venv/bin/python -m tools.media.sync_flash_copy var/work/project.photos-local.json --manifest var/work/photos-personal-flash-copy.json --site-manifest var/site/editions/photos-personal/flash-copy.json
```

The recovered TripTicks composed film remains a separate source. Its
Codespace changes and media must be transferred or pushed before that
third edition can be verified in this Mac checkout.
