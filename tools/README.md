# SIMVLTANEA Tools & Automation (`tools/`)

This directory contains CLI utilities, media importers, site and post-pack builders, verification gatekeepers, and historical preservation audit scripts.

## Tool Categories

### 1. Media Import & Management
- [`import_folder.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/import_folder.py) — Import media files from local folders into edition projects.
- [`import_photos.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/import_photos.py) — Opt-in local Apple Photos library video extractor and importer.
- [`import_photos_visuals.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/import_photos_visuals.py) — Visual model importer from Apple Photos.
- [`catalog_photos.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/catalog_photos.py) — Library-scale asset cataloging without duplicating source binaries.
- [`photos_universe_proxy.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/photos_universe_proxy.py) — Proxy generator for Photos universes.
- [`manage_clips.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/manage_clips.py) — Clip management and inspection utility.
- [`atomize_media.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/atomize_media.py) — Media atomization tool.

### 2. Editions, Packaging & Web Distribution
- [`build_edition.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/build_edition.py) — Build and compile named edition compositions from `editions.json`.
- [`edition_status.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/edition_status.py) — Inspect readiness, assets, and render status across all editions.
- [`build_site_index.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/build_site_index.py) — Generate multi-edition static web portal index.
- [`build_post_pack.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/build_post_pack.py) — Generate deployment post packets.
- [`package_public_site.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/package_public_site.py) — Bundle self-contained static site packages.
- [`export_project.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/export_project.py) — Project exporter.
- [`sync_flash_copy.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/sync_flash_copy.py) — Sync flash-copy manifests and static web assets.

### 3. Rendering & Sketches
- [`render_runtime_family.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/render_runtime_family.py) — Batch runner for runtime family video renders.
- [`render_visual_sketch.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/render_visual_sketch.py) — Visual sketch video preview generator.

### 4. Verification & Gates
- [`verify_local_lifecycle.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_local_lifecycle.py) — Fast worktree cleanliness check preventing generated lane leakage into git.
- [`run_review_proof.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/run_review_proof.py) — Sharded proof runner validating review readiness.
- [`verify_editions.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_editions.py) — Comprehensive edition validation.
- [`verify_package.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_package.py) — Package verification gate.
- [`verify_post_pack.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_post_pack.py) — Post pack verification.
- [`verify_public_site.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_public_site.py) — Public static site validation.
- [`verify_runtime_renders.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_runtime_renders.py) — Runtime render integrity checker.
- [`verify_private_workflow.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_private_workflow.py) — Private workflow validator.
- [`verify_legacy_decoded.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/verify_legacy_decoded.py) — Legacy decoded video validator.

### 5. Historical Excavation & Auditing
- [`account_excavation.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/account_excavation.py) — Historical account and asset excavation script.
- [`prompt_lineage.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/prompt_lineage.py) — Tracing prompt lineage from incubation logs.
- [`remote_repo_census.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/remote_repo_census.py) — Census of remote incubator repositories.
- [`generated_inventory.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/generated_inventory.py) — Inventory of generated artifact files.
- [`overnight_checkpoint.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/overnight_checkpoint.py) — Overnight workstream status checkpoint utility.
- [`preservation_manifest.py`](file:///Users/4jp/Workspace/4444J99/simvltanea/tools/preservation_manifest.py) — Comprehensive file preservation manifest generator.
