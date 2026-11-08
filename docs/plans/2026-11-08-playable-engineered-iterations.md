# Playable engineered iterations

## Goal and design

Make the older engineered SIMVLTANEA implementations directly playable from the existing website's Iterations navigation. Exclude the YouTube lineage recording. Preserve current Watch and Compose sessions and the existing public media boundary.

Use exact historical source snapshots for versions that were never deployed. Replay them with the already-public clip library and disclose that media substitution. Keep their engines and original controls intact. Give distinct shipped Effects Lab, arrangement and panel-workspace versions their actual entry routes. Retain the complete existing deployment list separately as build history.

Alternatives considered: deployment links alone leave older source-only implementations absent; rewriting historical engines would blur their behavior. Additive source archives with pinned revisions preserve the implementations and allow the current standard-library publishing command to build them reliably.

## Implementation

- [x] Inventory named implementation milestones and pin full source revisions.
- [x] Archive the exact source dependencies for the first Studio and modular Lab versions; retain file digests and source paths.
- [x] Build the early authored, seamed, audio and viewport runtime replays using the shared public library.
- [x] Build the original interactive Studio and modular Lab interfaces under stable `iterations/<slug>/` routes, with clearly labeled public-media replay wrappers.
- [x] Replace the deployment-only catalog with dated implementation entries and a separate build-history disclosure; add a direct `iterations.html` route.
- [x] Include iteration assets in the existing Pages build atomically without changing the Studio default or publishing archive source files.
- [ ] Verify source digests, asset closure, manifests and routing, run relevant and full repository checks, inspect the public-facing views in the browser, and review the change independently.
- [ ] Publish through a PR and the existing Git-connected Pages pipeline; verify the deployed iteration routes.

## Interfaces and verification

`tools.publishing.iteration_replays.historical_replay_files(clips)` returns a mapping of relative site paths to bytes; `HISTORICAL_REPLAYS` records the early source pins. The root publishing module combines that with the preserved Studio/Lab assets and the catalog. All build inputs are versioned code and validated public manifest records. Original private media and unknown publication permissions do not enter the build.

Tests must catch a missing historical route, a changed archived engine, an invalid or escaping asset path, accidental synthetic-media substitution, silent schema-1 behavior changes, and staging failures that would replace an existing release. Browser checks cover entering Iterations, opening the old versions, loading actual library clips, returning to the catalog, and keeping current Watch/Compose navigation functional.

## Execution record

Base: `e703cb24c86a14f8e536c43d052a39b428f11a46` (PR #98). The existing catalog lists recent deployments and explicitly leaves older source-only versions unreconstructed. The owner reiterated the missing versions in the current request. Work proceeds in a separate checkout and feature branch; history and unrelated source trees remain intact.
