# Studio deployment

The existing Cloudflare Pages project is `loop-compositor-studio`, connected to
`4444J99/tool-video-loop-compositor`. Its production branch is `main`.

Use these Git build settings:

| Setting | Value |
| --- | --- |
| Root directory | Repository root (empty) |
| Build command | `python3 -m tools.publishing.build_studio_site` |
| Build output directory | `var/site/deploy` |

The command uses Python's standard library and needs no package installation.
It stages the five Studio files from the checked-out source and downloads only
the existing public library's manifest and listed clips. It never publishes the
repository root, archives, source material, tests, or build scratch files.

The library is pinned to the immutable deployment
`https://7fec0066.loop-compositor-studio.pages.dev/library/` and manifest SHA-256
`8d9d65a9f77dc3362e4cfc3e3fd84fa5ff5fabf227299e446df92ab03359a5c8`:
580 clips totaling 70,480,365 bytes. Keep that deployment available because builds
retrieve its public assets. The build verifies the manifest digest, schema,
clip sizes and content hashes, and the Pages 25 MiB per-file limit before
assembling the output. Missing or changed media fails the build.

For a local build, run the same command from the repository root. The output
must be absent or empty. To preserve a previous build, choose another directory:

```bash
python3 -m tools.publishing.build_studio_site --output var/site/release-check
```

An intentional future library replacement requires a reviewed immutable source
URL and its manifest digest. The `--library-url` and `--manifest-sha256` options
allow checking that replacement before updating the pinned defaults.

Cloudflare's Git integration performs the asset upload within its build system.
This build does not require a direct-upload token or a client call to the Pages
asset-preflight API.

## Direct-upload authentication

Pages asset endpoints require the project upload JWT, not an account API token.
Obtain it from
`GET /accounts/{account_id}/pages/projects/loop-compositor-studio/upload-token`,
then use that JWT as the Bearer credential on `/pages/assets/check-missing`,
`/pages/assets/upload`, and `/pages/assets/upsert-hashes`. Keep the JWT out of
logs, source files, and shell history.

During the November 2026 repair, the connector request path returned HTTP 403
even with a fresh project JWT. Sending the same JWT directly from the execution
environment to the asset-preflight endpoint returned HTTP 200. A connector
403 therefore did not establish that the project token itself was invalid.
The Git build path above avoids that client authentication exchange entirely.

The public library source also rejects the default `Python-urllib` User-Agent
with Cloudflare error 1010. The build identifies its requests with
`simvltanea-pages-build/1`; it retains TLS verification and inherited proxy
settings.

## Prepared boomerang library

Build variants from the already admitted public library. The source manifest,
forward clip bytes, logical IDs, and public tags remain unchanged. Personal
uploads remain local to the browser and are not discovered by this command.
FFmpeg and ffprobe are required for preparation and verification; ordinary
Pages builds still use Python's standard library without those executables.

```bash
python3 -m tools.media.build_boomerangs \
    --library var/site/deploy/library \
    --out var/site/ecosystem-library --jobs 4
python3 -m tools.media.verify_boomerangs \
    --library var/site/ecosystem-library \
    --receipt var/proofs/boomerang-library.json --jobs 4
python3 -m tools.publishing.build_studio_site \
    --library var/site/ecosystem-library \
    --output var/site/ecosystem-preview
```

The preparation destination must not exist and must be outside its source.
A successful build atomically publishes the new directory after validating all
assets. The builder uses bounded encoder concurrency, strips copied container
metadata, and enforces the Pages 25 MiB asset limit. No repository archive or
unlisted file enters the deploy directory.

The default soundtrack runs forward on both visual legs. Use `--audio-mode
reverse` to reverse sound on the return leg. The default two-frame visual/audio
overlap uses quarter-sine audio curves with measured input headroom. Set
`--fade-frames 0` for the exact visual sequence `0..M-1,M-2..1`; no endpoint frame
is repeated. The normalized source has `M` frames at 30 fps, so an overlap of `K`
frames yields `2*M-2-K` output frames and exactly 1600 audio samples per output
frame before AAC encoding. Short or missing audio is padded without truncating
the video.

The manifest keeps schema `simvltanea.public-demo/1`. Each forward entry may add
`variants.boomerang`, containing its own content-addressed `id`, `file`, `bytes`,
dimensions, orientation, and `duration_seconds`, plus `fps`, `frame_count`, and
`seam_offset_seconds`. The original top-level ID remains the logical identity
used to avoid showing both variants as separate clips.

Forward and variant entries can carry `has_audio`, `lufs_integrated`,
`peak_dbfs`, `envelope_hz: 10`, and `rms_envelope`. RMS values are linear native
channel amplitude, taking the largest channel RMS in each 100 ms interval and
saturating at 1. Peak is measured decoded **sample peak**, not true peak. Silence
has zero envelopes and null peak/loudness; a clip too short for integrated LUFS
also has null loudness. Failed measurements reject the build instead of
inventing values. Neither silence nor codec padding becomes an active voice.

Verification checks content hashes, exact decoded frame timestamps/counts,
30/1 frame rates, and less than 1 ms difference between MP4 audio and video
presentation durations. AAC may still decode padded codec frames beyond the
container's edit duration. These checks do not establish gapless Safari looping;
continuous playback and audible seams require the browser/device proof too.

After uploading and verifying `ecosystem-preview`, pin its **immutable**
deployment library URL and manifest SHA-256 in `build_studio_site.py`. That makes
subsequent Git deployments fetch the same verified forward and boomerang assets.
Keep the pinned deployment available. Until that explicit pin change, the
default Git build continues using the earlier forward-only library.
