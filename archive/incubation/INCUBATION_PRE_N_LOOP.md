# Triptych Video Canon

Status: incubating
Final owner: unresolved

## What This Is

A three-panel vertical video device for Instagram Story/Reels-style output. Videos
enter as delayed voices in a canon/round: one panel starts, then the active clip
moves across the triptych as new clips enter behind it.

## Why It Starts Here

The final home is not known yet. Portvs is serving as the conductor/incubator so
the work can begin without deciding whether the eventual owner is Media Ark,
portfolio, a-mavs-olevm, a new repo, or an archived experiment.

The current root-to-leaf map is `VISUAL_FORM_CANON.md`, with `UNIFICATION.md`
as the current Portvs conductor note. Together they treat this incubator as the
canonical Portvs record for the Visual Form Canon: triptych/time-based media,
ambient screensaver and wallpaper runtimes, OGOD symbolic worlds, ASCII/textual
visual design, browser visualizers and generative abstract runtimes, web/3D
chambers, Media Ark custody, portfolio projection, exhibit/kiosk/gallery forms,
and lifecycle governance. Media Ark, portfolio, organvm art/runtime repos,
exhibit/art repos, and archive remain promotion apertures rather than implicit
owners.

## First Reversible Artifact

Build the smallest local prototype that can take a small folder of exported videos
and produce or preview a vertical three-panel canon. Keep all prototype files under
this incubator directory.

Current prototype:

- `render_triptych.py`: Python stdlib + `ffmpeg` renderer for the left-to-right
  three-panel canon, with filled-round `clip` timing for uneven source
  durations and `fixed` timing for regular phrase lengths. It now supports
  direction-aware rendered audio, per-panel audio gains, opt-in tone balancing,
  rendered story panel-order permutations, and export-time per-clip duration
  caps for lightweight drafts.
- `render_visual_sketch.py`: Python stdlib + `ffmpeg` renderer for a tiny
  visual-arrangement draft from selected edition clips. It supports `slices`
  for simple collage, `score` for model-guided panel recomposition, `serial`
  for Noonlight-like portrait/gaze sequences, `fracture` for
  accident/collision grids, and `signal` for Glitche/Porn signal-damage maps
  without replacing the canon renderer. Slice and score sketches can use a
  staged arrangement-model still as a low-opacity
  structural underlay, so `ballerina whole` can guide the moving `ballerina
  danse` sketch. The `triptych` model-fit mode maps the model still's
  left/middle/right thirds into the visible panel order, preserving panel
  rearrangement as part of the composition. The `score` style then overlays
  moving rectangular fragments in a Ballerina-Whole-like map. Album-specific
  maps can now be authored as text in `visual_sketch.score_cells`,
  `visual_sketch.fracture_cells`, or `visual_sketch.signal_cells`, keeping the
  renderer shared while Ballerina, Accidents, Glitche, and gated Porn take
  different shapes.
- `export_project.py`: project runner that can create the Story, three panel
  Reels, and a static media-first landing-page seed from one text manifest.
  The landing surface opens on the moving triptych, hides prompts/settings/clip
  controls behind a drawer, and adapts from wide fullscreen panels to a narrow
  Story-like frame. It now generates disposable low-bitrate web video/audio
  proxies for the landing page so public playback can be lightweight and
  intentionally lossy while preserving originals for full renders. Its preview
  settings include an explicit three-slot panel arrangement board so visible
  columns can be recomposed without changing the internal canon voices. The
  generated page also accepts URL query parameters for named presets, surface,
  direction, panel order, start mode, labels, audio, and volumes, with a
  settings-drawer link writer for turning the current preview state into a
  shareable URL. The
  settings drawer also surfaces a read-only public arrangement-score summary so
  authored maps are understandable without opening JSON.
- `sync_flash_copy.py`: selected-edition sync command that regenerates
  lightweight web proxies, writes a private local flash-copy receipt under
  ignored `work/`, writes a proxy-centered public receipt under `site/`, and can
  rebuild the landing page and public edition index without copying or mutating
  the source library. Public receipts now include sanitized
  `arrangement_score` metadata, never private source paths.
- `build_site_index.py`: sanitized public index builder that reads only
  `site/editions/*/flash-copy.json`, uses public proxy media for previews, and
  writes the multi-edition `site/index.html` entry point plus the sanitized
  `site/public-manifest.json` post/share map with probed media facts and the
  human `site/release-board.html` posting board plus the
  `site/release-player.html` playback surface plus `site/player-presets.md`
  plus `site/exhibit-loop.md` gallery handoff plus
  `site/exhibit-programs.json` machine-readable program map plus
  `site/exhibit-cue-sheet.json` / `site/exhibit-cue-sheet.md` public
  exhibit cue sheet plus
  `site/curatorial-score.json` / `site/curatorial-score.md` public
  curatorial score plus
  `site/living-loop.json` / `site/living-loop.md` public seeded-loop
  contract plus
  `site/playback-contract.json` machine-readable URL-control boundary plus
  `site/composition-atlas.json` / `site/composition-atlas.md` public
  composition atlas plus
  `site/rhythm-map.json` / `site/rhythm-map.md` public cadence score plus
  `site/sound-map.json` / `site/sound-map.md` public audio/silence map plus
  `site/release-matrix.json` / `site/release-matrix.md` public target matrix
  plus
  `site/release-copy.md` copy deck plus `site/platform-plan.md` plus
  `site/release-queue.md`. It also surfaces public control-preset links and
  published Story/Reel post-pack links when those links exist in public
  receipts. The release player now has a verified kiosk URL for chromeless
  digital-frame/gallery playback.
- `verify_public_site.py`: public sharing gate that checks generated site text
  for private Photos/library tokens, validates public edition receipts, ensures
  referenced proxies and exports exist inside `site/`, validates public
  control-preset payloads, root-index preset links,
  release-board/player/presets/copy/platform/queue links, player kiosk hooks,
  exhibit-loop kiosk links, exhibit-program schema/counts,
  exhibit-cue-sheet runtime/audio/program consistency, and the public release
  manifest, validates curatorial-score work/runtime/program consistency,
  validates living-loop seed/program/no-media-regeneration consistency,
  validates playback-contract parameter bounds/examples,
  validates composition-atlas public links and composition fields,
  validates rhythm-map duration/count/link consistency,
  validates sound-map audio/silence/link consistency,
  validates release-matrix target/product-gate consistency,
  re-probes release-manifest media facts, probes public
  Story/Reel and visual-sketch exports for bounded 9:16 video, and keeps the
  static package size bounded.
- `verify_post_pack.py`: post-pack media gate that uses `ffprobe` to verify the
  rendered Story/Reel files referenced by a public receipt have valid duration,
  expected dimensions, 9:16 shape, and bounded size.
- `package_public_site.py`: hostable package writer that verifies the public
  static site, copies only `site/` into ignored `packages/`, normalizes package
  receipts, verifies the copied package root, writes file checksums plus public
  edition provenance and custody metadata, requires packaged editions to be
  `public-package-ready`, and creates a zip for static hosting or archival
  transfer.
- `verify_package.py`: read-only package-integrity gate that recomputes packaged
  file checksums, compares them with `package-manifest.json`, rejects private or
  generated source lanes inside the package, enforces public-package-ready
  custody metadata, and reruns the public-site verifier against the copied
  package tree.
- `preservation_manifest.py`: private custody ledger writer under ignored
  `work/`. It separates private durable source preservation, private operational
  lanes, public derivatives, and public apparatus, then records which editions
  may transfer publicly from the verified package.
- `prompt_lineage.py`: private prompt-lineage extractor for the wider visual
  form canon. It scans local Codex session prompts plus relevant project docs,
  writes ignored `work/visual-form-lineage.json` and
  `work/visual-form-lineage.md`, keeps compatibility
  `work/visual-media-lineage.*` receipts, and feeds the sanitized tracked
  synthesis in `VISUAL_FORM_CANON.md` and `UNIFICATION.md`.
- `remote_repo_census.py`: private GitHub repository census for the wider
  visual form canon. It treats remote repositories as the canonical project
  surface, writes ignored `work/remote-repo-census.json` and
  `work/remote-repo-census.md`, and keeps local checkouts in their correct role
  as runnable/inspectable caches.
- `generated_inventory.py`: read-only generated-media inventory that classifies
  `work/`, `renders/`, `site/`, `packages/`, and `samples/` so autonomous work
  can see local media weight without deleting anything. It can emit JSON and a
  read-only cleanup plan that ranks reclaim candidates with regeneration gates.
- `verify_local_lifecycle.py`: read-only Git-visible containment gate that
  fails when generated/local lanes leak into review and can enforce optional
  untracked file or text-line budgets before an autonomous pass ends.
- `overnight_checkpoint.py`: private read-only checkpoint writer under ignored
  `work/`. It combines creative coverage, living-loop rotations, package
  readiness, release-focus recommendations, cleanup pressure, and next
  autonomous moves without exposing source media paths or deleting generated
  files. It also writes `work/release-focus.json` and
  `work/release-focus.md` plus `work/release-focus.html` as standalone private
  posting/refinement focus files, and `work/control-auditions.json`,
  `work/control-auditions.md`, plus `work/control-auditions.html` as private
  text-control audition boards that generate no new media. It also writes
  `work/next-render-queue.json`, `work/next-render-queue.md`, and
  `work/next-render-queue.html` as planned-only render candidates with dry-run
  commands and post-render gates. It also writes
  `work/overnight-dashboard.json`, `work/overnight-dashboard.md`, and
  `work/overnight-dashboard.html` as the private conductor index over the
  current handoffs and package links. It also writes
  `work/static-hosting-handoff.json`, `work/static-hosting-handoff.md`, and
  `work/static-hosting-handoff.html` as the private no-secrets transfer scope
  for the verified static package. It also writes
  `work/first-release-packet.json`, `work/first-release-packet.md`, and
  `work/first-release-packet.html` as the private platform-specific first-post
  packet over verified package media. It also writes
  `work/posting-receipt-template.json`,
  `work/posting-receipt-template.md`, and
  `work/posting-receipt-template.html` as the private unposted receipt template
  for future platform evidence. It also writes
  `work/release-cadence-plan.json`, `work/release-cadence-plan.md`, and
  `work/release-cadence-plan.html` as the private ordered sequence over current
  release-focus candidates. It also writes
  `work/edition-refinement-slate.json`,
  `work/edition-refinement-slate.md`, and
  `work/edition-refinement-slate.html` as the private per-edition next-action
  slate across public-ready and gated work. It also writes
  `work/cache-retention-plan.json`, `work/cache-retention-plan.md`, and
  `work/cache-retention-plan.html` as the private read-only lane retention and
  reclaim posture. It also writes `work/source-curation-plan.json`,
  `work/source-curation-plan.md`, and
  `work/source-curation-plan.html` as the private dry-run-first album/source
  curation plan that keeps raw albums, arrangement model albums, and public
  gates distinct without staging media. It also writes
  `work/audio-control-plan.json`, `work/audio-control-plan.md`, and
  `work/audio-control-plan.html` as the private per-edition audio control plan
  for gain, panel balance, direction-aware audio, and browser-only playback
  controls. It also writes `work/paired-work-order.json`,
  `work/paired-work-order.md`, and `work/paired-work-order.html` as the private
  always-both work order that places each creative edit beside its containment
  gate before any render/source/audio change.
- `verify_private_workflow.py`: private receipt gate for the overnight
  checkpoint and release-focus handoffs. It validates local package/media refs,
  the private review/audition/render-queue/dashboard HTML files, product/shop
  deferral, edit prompts, no-destructive render planning, static-hosting scope,
  first-release packet integrity, posting receipt template truthfulness,
  release-cadence link/order integrity, edition-refinement gate integrity,
  cache-retention read-only posture, source-curation dry-run/source-gate
  integrity, audio-control no-source/no-mutation integrity, paired-work-order
  no-media/no-source integrity, and private-token absence without publishing
  anything.
- `OVERNIGHT_WORKSTREAM.md`: current autonomous operating note. It records the
  "always both" rule: creative engine expansion and lifecycle containment should
  advance together instead of competing.
- `build_edition.py`: named-edition runner that treats Photos albums or selected
  folders as different configurations of the same canon engine. It can build a
  local project, render it, render visual sketches, and sync a per-edition flash
  copy from a text preset.
- `edition_status.py`: read-only edition status reporter that summarizes preset,
  local project, public receipt, generated package, release manifest, visual
  sketch, source preset, visual-map, and post-pack state without printing
  private media paths.
- `verify_editions.py`: read-only source preset verifier. It validates edition
  family membership, source selectors, named control presets,
  score/fracture/signal cell maps, audio/effect values, and the Porn
  public-export gate before import, render, sync, or publish work touches media.
- `build_post_pack.py`: postable-output runner that takes a named edition,
  applies a bounded export profile, renders the Story plus panel Reels by
  default, syncs public receipts, and runs the public-site verifier.
- `import_photos.py`: explicit local Photos importer that reads the Photos
  catalog, stages local video files into ignored samples, can ask Photos.app to
  export missing originals after opt-in, writes an ignored local project
  manifest, and can run the exporter. It supports lightweight paging, date
  ranges, seeded random selection, Photos album/folder selection, album listing,
  and persistent source-UUID exclusions so the library can be explored without
  staging everything.
- `import_photos_visuals.py`: explicit local Photos still-album importer that
  reads selected visual albums/folders, converts local stills into short lossy
  MP4 motion clips with varied durations, stages optional arrangement-model
  stills, and writes a local project manifest for the same triptych renderer.
- `catalog_photos.py`: metadata-only Photos catalog writer for library-scale
  interaction. It records dates, durations, dimensions, orientation, yearly
  counts, and optional local-file availability under ignored `work/` without
  copying or rendering media.
- `import_folder.py`: local folder importer for a deliberate set of chosen
  videos, staged as symlinks or copies under ignored samples.
- `manage_clips.py`: small manifest editor for listing, hiding, showing, or
  isolating clips without hand-editing JSON. It can also ban/unban Photos source
  UUIDs from future imports via an ignored exclude file.
- `project.example.json`: cumulative creative brief, prompt stack, editor notes,
  and export presets.
- `editions.example.json`: named edition presets for album-shaped variants such
  as accidents, ballerina, noonlight, porn, and a currently video-ready glitche
  edition. It separates engine identity from work titles and families:
  `Ballerina Danse Recomposition`, `Noonlight Recomposition`, and `Accidents
  Fracture` are structural-recomposition works; `Glitche Signal Damage` and
  `Porn Signal Damage` share a signal-damage family. The Ballerina preset now
  carries an explicit Ballerina-Whole-like `score_cells` map, the Accidents
  preset carries an explicit `fracture_cells` rupture map, and the signal-damage
  presets carry explicit `signal_cells` maps instead of depending only on
  built-in grids.
- `manifest.example.json`: minimal single-render settings for the prototype.
- `README.md`: manual export, render, and landing-page workflow.
- `samples/`: ignored lane for manually exported source videos.
- `renders/`: ignored lane for generated outputs.
- `work/`: ignored lane for temporary render phrases.
- `site/`: static landing-page output lane.

## Current Boundaries

- Do not touch Limen.
- Do not mutate `graph.jsonl`.
- Do not add repo-root dependencies.
- Photos ingestion is allowed only as an explicit opt-in local path after the
  human authorizes it.
- Do not mutate the Photos library; read the catalog or ask Photos.app to export
  selected originals, then stage local media under ignored incubator paths.
- Keep manual exports supported as the lowest-friction fallback.
- Treat prompt changes as cumulative project direction unless explicitly reset.
- Support both text-driven direction and editor-like clip ordering.
- Keep the public surface media-first: videos are the first screen, while text
  direction, ordering, hiding, audio, and export controls stay behind taps.
- Treat shareable URLs as text-driven control surfaces: the public page can be
  opened with query parameters for named presets, surface, direction, panel
  order, start mode, labels, audio, and volume settings.
- If an edition has a rendered visual sketch, it may be selected from settings
  as the main landing-page surface; the default first screen remains the live
  canon preview.
- Preserve the filled-round cadence: blanks are allowed during the opening fill,
  then panels stay occupied; the longest active clip sets the round length and
  shorter clips loop until the round turns over.
- Treat direction as a MIDI-like visual effect layer: the current reversible
  version supports global forward, reverse, and ping-pong modes; deeper per-panel
  or per-clip routing can come after the basic surface proves itself.
- Treat panel arrangement as a first-class composition control: the canon voices
  remain left/middle/right internally, while the rendered or previewed triptych
  surface can permute which voice appears in each visible column. Single-panel
  Reel exports should follow the visible slot after that permutation.
- Treat still-model arrangements as composition scores: `ballerina whole` is not
  decorative reference art, but a sketch for how `ballerina danse` should be
  reconfigured across the visible triptych panels. Noonlight follows the same
  structural-recomposition rule through serial portrait/light, while Accidents
  needs a more complicated rupture/fracture map. These maps should be editable
  as text in edition presets so the album-specific shape does not fork the
  engine.
- Keep fast draft paths available so material selection does not require a full
  1080x1920 story plus three panel renders.
- Keep the 1000-video path metadata-first: the system may catalog the whole
  library, but it should stage and render only a small selected working set.
- Prefer authored source selection for public editions: a deliberate Finder
  folder works now, and a Photos album/collection importer is the next source
  lane if Photos-native curation proves better.
- Treat albums as configuration instances over one engine: a named edition binds
  source selection, order, direction, audio, tone, proxy recipe, landing output,
  and export targets without changing the renderer.
- Use `edition_status.py` as the lightweight checkpoint before deciding which
  album-shaped edition needs import, sketch, sync, release-manifest refresh,
  post-pack render, or package refresh next.
- Use `verify_editions.py` before source-config changes move into imports,
  renders, syncs, packages, or public sharing.
- Support album roles, not only album sources: an edition may use one album as
  raw material and another as the arrangement model. Current example:
  `ballerina danse` is raw material, while `ballerina whole` is the cubist /
  structural target for the eventual ballerina arrangement.
- Keep edition families visible in generated metadata: structural
  recomposition covers Ballerina, Noonlight, and Accidents; signal damage covers
  Glitche and Porn.
- Some Photos albums are visual/still-heavy rather than video-ready. Those can
  now enter the canon through generated lightweight still-to-motion MP4 clips;
  the first cubist/fracture/signal placement layer is now
  `visual_sketch.score_cells`, `visual_sketch.fracture_cells`, and
  `visual_sketch.signal_cells`.
- Visual model reads recorded so far: Ballerina is a wide sliced figure collage
  with translucent rectangular overlays; Noonlight is a close serial portrait
  study organized by gaze shifts, face angle, and window glare.
- Runnable visual-sketch editions exist for Ballerina, Noonlight, Accidents, and
  Glitche. They use the same staging/sync path but different sketch styles. Porn
  has a gated local signal map but no public receipt or package export.
- Treat per-panel audio levels and export-time tone normalization as lightweight
  render controls, not source-media mutations.
- Treat web playback media as disposable proxies: compression artifacts and
  distortions are part of the aesthetic, but originals remain the source of
  record for rerenders.
- Treat the eventual hosted surface as static/public output plus selected
  manifests, not as direct access to the private local Photos library.
- Treat flash copies as selected-edition receipts: `work/flash-copy.json` may
  include private source paths for local regeneration, while `site/flash-copy.json`
  should stay proxy-centered for shareable/static output.
- Treat rendered sketches as share-surface artifacts: `--sketch --sync` should
  publish the generated sketch path into the edition landing page and public
  flash-copy receipt without exposing private Photos paths. Public
  arrangement-score metadata may describe the work title, family, public album
  labels, sketch style, cell counts, and short composition notes.
- Treat post packs as the Story/Reels publishing lane: a named edition can render
  a bounded draft/share/full pack and publish those exports under the static
  edition site without exposing source media. Draft/share profiles may cap
  per-clip duration to keep long source clips from breaking the public package
  size gate; full renders remain source-duration-led.
- Treat post-pack verification as separate from public-site verification: the
  former proves rendered Story/Reel media properties, while the latter proves the
  static site is coherent and privacy-safe.
- Treat `site/index.html` as a generated public conductor surface over synced
  editions. It must be built from public receipts/proxies, not from private
  `work/` manifests or direct Photos paths. Public preset links may appear there
  only from sanitized `control_presets` receipt data. Published post-pack links
  should appear there only after the public receipt marks them existing and
  published.
- Treat `site/public-manifest.json` as the portable public release map for the
  current surface: edition pages, preset URLs, visual sketches, Story/Reel
  exports, families, counts, structured release queue, player presets, and
  probed media facts. It must be generated from the same sanitized public
  receipts as the root index and verified before hosting or transfer.
- Treat `site/release-board.html` as the generated human posting board. It must
  be built from the same sanitized public data and verified to link every public
  Story/Reel/sketch output.
- Treat `site/release-player.html` as the generated public playback surface. It
  must be built from the same sanitized public data, keep playback dependency
  free, expose text-addressable edition/family/mode/kiosk/program URLs, embed
  the sanitized exhibit program list, support bounded `volume` and `rate` URL
  playback controls, support `seed=<text>` for reproducible random loops, and be
  verified to link every public Story/Reel/sketch output.
- Treat `site/player-presets.md` as the generated text card for public playback
  presets. It must be built from sanitized public receipts and verified to list
  every expected local player URL, including the chromeless kiosk loop.
- Treat `site/exhibit-loop.md` as the generated gallery/digital-frame handoff.
  It must be built from sanitized public receipts, list all-work/family/edition
  kiosk programs, and restate the public-package operating gates without private
  source paths.
- Treat `site/exhibit-programs.json` as the machine-readable exhibit program
  map. It must be built from sanitized public receipts, expose only local player
  URLs, and keep all/family/edition program counts aligned with public
  Story/Reel/sketch exports. Each program should carry a sanitized playlist of
  its public media items. The release player should embed the same program list
  so `?program=<id>` URLs can drive kiosk playback without a server.
- Treat `site/exhibit-cue-sheet.json` and `site/exhibit-cue-sheet.md` as the
  public gallery/digital-frame cue sheet. They must be built from sanitized
  public exhibit programs and media facts, expose only local player/media links,
  summarize program runtime plus audio/silent counts, and be verified before
  hosting or transfer.
- Treat `site/curatorial-score.json` and `site/curatorial-score.md` as the
  public curatorial score for the album-shaped works. They must be built from
  sanitized public composition, rhythm, sound, release, and program facts, name
  each work's public note/program/runtime/output set, keep product/shop use
  deferred, and be verified before hosting or transfer.
- Treat `site/living-loop.json` and `site/living-loop.md` as the public seeded
  loop contract for an always-changing hosted surface. They must be built from
  sanitized public exhibit programs and curatorial score facts, expose only
  local seeded player URLs, make clear that seeds change browser playback order
  only, include text-only rotation sets, require no media regeneration, and be
  verified before hosting or transfer.
- Treat `site/playback-contract.json` as the machine-readable public player
  control boundary. It must be built from sanitized public receipts, expose only
  local player references, list allowed query parameters, keep `volume`, `rate`,
  `start`, `fit`, boolean, program, edition, family, and `seed` behavior
  bounded, and be verified before hosting or transfer.
- Treat `site/composition-atlas.json` and `site/composition-atlas.md` as the
  public album-shape index. They must be built from sanitized public receipts,
  expose only local public links, record edition family/material/style/model and
  panel-role language, keep Ballerina/Noonlight/Accidents/Glitche visible as
  different configurations of one engine, and be verified before hosting or
  transfer.
- Treat `site/rhythm-map.json` and `site/rhythm-map.md` as the public cadence
  score. They must be built from sanitized public media facts, expose only local
  public links, summarize Story/Reel/sketch durations, audio presence, family
  totals, edition totals, and queue order, and be verified before hosting or
  transfer.
- Treat `site/sound-map.json` and `site/sound-map.md` as the public
  audio/silence map. They must be built from sanitized public media facts,
  expose only local public links, identify audio-bearing post exports and silent
  visual sketches, keep browser mute/volume/rate controls source-immutable, and
  be verified before hosting or transfer.
- Treat `site/release-matrix.json` and `site/release-matrix.md` as the public
  target matrix. They must be built from the sanitized public release queue,
  expose only local public links, group Story/Reel/sketch outputs by edition and
  platform target, keep product/shop use deferred until an explicit product
  object exists, and be verified before hosting or transfer.
- Treat `site/release-copy.md` as the generated public text deck for captions,
  tags, media facts, and public links. It must be built from the same sanitized
  public data and verified to link every public Story/Reel/sketch output.
- Treat `site/platform-plan.md` as the generated public posting map for
  Instagram, YouTube/GitHub/portfolio, and deferred product/shop review. It must
  be built from the same sanitized public data and verified to link every public
  Story/Reel/sketch output.
- Treat `site/release-queue.md` as the generated public posting sequence. It
  must be built from the same sanitized public data, keep Story/Reel/sketch
  order explicit without becoming a calendar, and be verified to link every
  public Story/Reel/sketch output.
- Treat `verify_public_site.py` as the local share gate before hosting or
  publishing a generated `site/` package. It must verify public text/receipt
  privacy, public preset links, the public release manifest, referenced media,
  Story/Reel and visual-sketch media properties, release-manifest media facts,
  player preset links, embedded player programs, bounded player audio/rate
  controls, seeded random playback hooks, exhibit-loop kiosk links,
  exhibit-program schema/counts/playlists, exhibit-cue-sheet
  runtime/audio/program consistency, curatorial-score
  work/runtime/program consistency, living-loop seed/program/no-media
  consistency, playback-contract
  bounds/examples/counts, composition-atlas links/fields/counts,
  rhythm-map durations/counts/links, sound-map audio/silence/count/link
  coverage, release-matrix target/product-gate coverage, and kiosk hooks,
  release-board/player/presets/copy/platform-plan/queue links, and package
  size.
- Treat `packages/` as generated output from the verified public site. Packages
  may be uploaded or archived, but they must not include `work/`, `samples/`,
  `renders/`, or private Photos paths. The package command must verify both the
  source `site/` tree and the copied package tree unless explicitly skipped.
- Treat `package-manifest.json` as a portable receipt: it should include file
  checksums and public edition provenance, and `verify_package.py` should pass
  after local rebuilds or external transfer while rejecting any copied private
  source lanes.
- Treat autonomous overnight work as a paired loop: run the generated-media
  inventory and edition status first, make one creative move and one containment
  move when possible, prefer draft/proxy paths over full renders, verify the
  changed surface, write `work/overnight-checkpoint.json` with
  `python3 overnight_checkpoint.py`, use its release-focus section to choose the
  next verified Story/Reel/sketch output, use `work/release-focus.md` or
  `work/release-focus.html` for the focused posting handoff, use
  `work/control-auditions.html` to audition text-driven direction/panel/audio
  recipes without rendering, use `work/next-render-queue.html` only as a
  dry-run-first render plan, use `work/overnight-dashboard.html` as the private
  conductor index, use `work/static-hosting-handoff.html` for the verified
  package transfer scope, use `work/first-release-packet.html` when the next
  action is posting rather than rendering, use
  `work/posting-receipt-template.html` to keep future social-platform evidence
  private, use `work/release-cadence-plan.html` to choose the next verified
  focus item, use `work/edition-refinement-slate.html` to keep every edition in
  view, use `work/cache-retention-plan.html` before manual generated-media
  reclaim, use `work/source-curation-plan.html` before changing album source
  selection or staging media, use `work/audio-control-plan.html` before
  changing rendered audio, panel gains, or reverse/ping-pong audio posture, use
  `work/paired-work-order.html` to keep each creative move paired with its
  containment gate, run `python3 verify_private_workflow.py`, and end with git
  status.

## Current Generated Checkpoint

`edition_status.py` is the quick read on this state. As of the latest verified
package refresh:

- `ballerina` has a draft Story/Reels post pack, public exports, a visual
  sketch, and package copies.
- `noonlight` has a draft Story/Reels post pack, public exports, a visual
  sketch, and package copies.
- `accidents` has a draft Story/Reels post pack, public exports, a synced
  fracture visual sketch, and package copies.
- `glitche` has a draft Story/Reels post pack, public exports, a synced signal
  visual sketch, and package copies. It required the draft `max_clip_seconds`
  cap to preserve the public size gate because one source clip made the uncapped
  draft too large.
- `porn` remains a gated local source config with signal-map text and should
  stay gated by explicit review before public export.

## Candidate Promotion Targets

- Media Ark: if the core value becomes durable media processing/export.
- portfolio: if the core value becomes public presentation/product funnel.
- a-mavs-olevm / etceter4: if the core value becomes an artistic exhibit.
- New repo: if the device becomes a standalone product.
- Portvs only: if it remains an index/spec/conductor object.

## Promotion Receipt

Before leaving incubation, record:

- Target repo:
- Paths to move:
- Verification command:
- Reason this target is the right owner:

## Promotion Evidence To Watch

Promotion is justified only after the prototype proves one of these shapes:

- Media Ark: it becomes repeatable media processing/export infrastructure.
- portfolio: it becomes a public-facing creative/product surface.
- a-mavs-olevm / etceter4: it becomes an authored artistic exhibit.
- New repo: it needs standalone release, docs, issue tracking, or packaging.
- Portvs only: it remains a conductor/index/spec for the device.
