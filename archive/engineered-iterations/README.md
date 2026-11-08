# Preserved engineered iterations

These are build inputs for the playable historical versions in the site's
Iterations catalog. They preserve exact source bytes from this repository's
history. They are not a second working copy of the current application.

Each Studio or modular Lab directory contains a `manifest.json` with the full
source commit, original repository paths, SHA-256 digests and Git blob identities.
Its `source/` directory retains those original paths. The publisher verifies the
complete file inventory and digests before running a historical Studio generator
or copying a Lab's browser assets. Early browser engines live under `early/` with
their own pinned provenance records.

Only generated HTML, JavaScript, CSS and public plan/data JSON enter the website.
The archive manifests, Python source, repository paths and historical ZIP bundles
are not published. Current public clips are admitted by the existing library
manifest and shared between the versions; they are not copied into each replay.

## Source and media boundaries

- An archived implementation remains byte-for-byte tied to its recorded commit.
- A surrounding replay page supplies current public clips and navigation. Any
  loading adapter is separate from the original implementation.
- Replays demonstrate historical software with available public media. They do
  not establish recovery of an original historical arrangement, private media
  collection, or the 2017 artwork documented on YouTube.
- The modular Lab retains its original speech-screening defaults. A public clip
  does not gain a fabricated screening record merely by entering a replay.
- The October shared-engine consumer requires a separately versioned dependency
  for that optional renderer. A native-renderer replay does not claim that the
  unavailable dependency or private TMB derivative generations were recovered.
- Later already-published website iterations remain linked to their immutable
  deployment URLs, with the correct Studio or editing-workspace entrypoint.

## Build and verify

The normal Pages build assembles the current application, restored iterations and
admitted library as one release:

```bash
PYTHONPATH=src python3 -m tools.publishing.build_studio_site
```

It also accepts `--library` for an already validated public library. A missing or
invalid source snapshot fails the build before the output is published. Existing
nonempty output is preserved.

The implementation milestones and full UTC source timestamps are maintained in
`src/simvltanea/browser/browser_iterations.py`; they are not asserted to be formal
versioned releases. Every recorded website deployment remains separately
available in the catalog's deployment-history section.
