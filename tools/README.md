# SIMVLTANEA Tools & Automation (`tools/`)

This directory contains CLI utilities, media importers, site and post-pack builders, verification gatekeepers, and historical preservation audit scripts.

Repository governance combines `ls-lint` naming rules, the
[structure contract](../docs/STRUCTURE.md), changed-Markdown linting, and the
local lifecycle gate. See [Contributing](../CONTRIBUTING.md#verify-before-pr)
for pinned tools and verification commands.

## Tool Categories

### 1. Media Import & Management

- [`import_folder.py`](import_folder.py) — Import media files from local folders into edition projects.
- [`import_photos.py`](import_photos.py) — Opt-in local Apple Photos library video extractor and importer.
- [`import_photos_visuals.py`](import_photos_visuals.py) — Visual model importer from Apple Photos.
- [`catalog_photos.py`](catalog_photos.py) — Library-scale asset cataloging without duplicating source binaries.
- [`photos_universe_proxy.py`](photos_universe_proxy.py) — Proxy generator for Photos universes.
- [`manage_clips.py`](manage_clips.py) — Clip management and inspection utility.
- [`atomize_media.py`](atomize_media.py) — Media atomization tool.

### 2. Editions, Packaging & Web Distribution

- [`build_edition.py`](build_edition.py) — Build and compile named edition compositions from `editions.json`.
- [`edition_status.py`](edition_status.py) — Inspect readiness, assets, and render status across all editions.
- [`build_site_index.py`](build_site_index.py) — Generate multi-edition static web portal index.
- [`build_post_pack.py`](build_post_pack.py) — Generate deployment post packets.
- [`package_public_site.py`](package_public_site.py) — Bundle self-contained static site packages.
- [`export_project.py`](export_project.py) — Project exporter.
- [`sync_flash_copy.py`](sync_flash_copy.py) — Sync flash-copy manifests and static web assets.

### 3. Rendering & Sketches

- [`render_runtime_family.py`](render_runtime_family.py) — Batch runner for runtime family video renders.
- [`render_visual_sketch.py`](render_visual_sketch.py) — Visual sketch video preview generator.

### 4. Verification & Gates

- [`verify_repository_structure.py`](verify_repository_structure.py) — Approved paths, required files, folder roles, and generated-output boundaries in the Git index and nonignored untracked files.
- [`verify_local_lifecycle.py`](verify_local_lifecycle.py) — Worktree cleanliness and generated/local-only leakage checks across indexed and nonignored untracked paths.
- [`run_review_proof.py`](run_review_proof.py) — Sharded proof runner validating review readiness.
- [`verify_editions.py`](verify_editions.py) — Comprehensive edition validation.
- [`verify_package.py`](verify_package.py) — Package verification gate.
- [`verify_post_pack.py`](verify_post_pack.py) — Post pack verification.
- [`verify_public_site.py`](verify_public_site.py) — Public static site validation.
- [`verify_runtime_renders.py`](verify_runtime_renders.py) — Runtime render integrity checker.
- [`verify_private_workflow.py`](verify_private_workflow.py) — Private workflow validator.
- [`verify_legacy_decoded.py`](verify_legacy_decoded.py) — Legacy decoded video validator.

### 5. Historical Excavation & Auditing

- [`account_excavation.py`](account_excavation.py) — Historical account and asset excavation script.
- [`prompt_lineage.py`](prompt_lineage.py) — Tracing prompt lineage from incubation logs.
- [`remote_repo_census.py`](remote_repo_census.py) — Census of remote incubator repositories.
- [`generated_inventory.py`](generated_inventory.py) — Inventory of generated artifact files.
- [`overnight_checkpoint.py`](overnight_checkpoint.py) — Overnight workstream status checkpoint utility.
- [`preservation_manifest.py`](preservation_manifest.py) — Comprehensive file preservation manifest generator.
