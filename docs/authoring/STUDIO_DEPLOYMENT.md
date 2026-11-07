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
