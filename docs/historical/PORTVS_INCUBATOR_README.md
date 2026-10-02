# Triptych Video Canon Prototype

Small reversible renderer for manually exported videos. It builds a 9:16,
three-panel video where each source enters on the left, advances to the middle,
then advances to the right before leaving the canon.

## Local Workflow

1. Export a small batch of videos from Photos by hand.
2. Put them in `samples/`.
3. Render the full configured set:

```bash
python3 export_project.py project.example.json
```

That produces:

- `renders/story-triptych.mp4`: one three-panel Story.
- `renders/reel-left.mp4`: the left panel as its own Reel.
- `renders/reel-middle.mp4`: the middle panel as its own Reel.
- `renders/reel-right.mp4`: the right panel as its own Reel.
- `site/index.html`: a static media-first landing-page seed. It opens on the
  triptych itself; prompts, clip ordering, hiding, preview audio, and rendered
  export links live behind the settings drawer.
- `site/media/`: ignored lightweight web proxies for the landing page when it
  is built. These are disposable lossy derivatives, not source media.

To render only one export:

```bash
python3 export_project.py project.example.json --only reel-left
```

To render quickly while choosing material:

```bash
python3 export_project.py work/project.photos-local.json --draft
```

Draft mode renders the story only by default at `540x960`, `15fps`, `crf 30`,
`ultrafast`, and the first five enabled clips. Use `--draft --only reel-left` to
make a quick panel-specific draft.

To append another text direction into the project:

```bash
python3 export_project.py project.example.json --add-prompt "Make the right panel feel like a delayed memory." --skip-render
```

## Media Atomization

The heavy local media lanes can be treated as content-addressed atoms instead
of permanent repo material. This is the "small object until needed" layer:
source media stays private and restageable, while generated renders/site/package
bytes stay reconstructable from manifests and commands.

Build the local atom map without duplicating the 2 GB media surface:

```bash
python3 atomize_media.py
```

That writes ignored private receipts:

- `work/media-atoms.json`: content hashes, chunk hashes, media facts, lanes,
  and project recipes.
- `work/media-atoms.md`: human-readable decode/rebuild model.

By default this is manifest-only: it reads bytes to hash them, but it does not
copy chunks. Use `--limit N --no-ffprobe` for a fast smoke test. Use
`--write-chunks` only when intentionally materializing a local content-addressed
chunk store under `work/atom-chunks/`, because that duplicates media bytes.

## Custody Ledger

The personal/public boundary is tracked as custody, not as a simple local/public
split. Source identities and selections belong in private durable custody,
`work/`, `samples/`, and `renders/` are private operational lanes, `site/` is a
sanitized public derivative staging lane, and `packages/` is the public transfer
artifact.

Generate the private custody ledger:

```bash
python3 preservation_manifest.py
```

That writes ignored private receipts:

- `work/preservation-ledger.json`
- `work/preservation-ledger.md`
- `work/preservation-ledger.html`

The package manifest carries the same custody decision. `verify_package.py`
rejects packages that contain private lanes or any edition that is not explicitly
`public-package-ready`.

## Visual Form Canon Unification

`VISUAL_FORM_CANON.md` is the root-to-leaf map for the broader visual system:
triptych/video, ambient screensaver and wallpaper runtimes, OGOD symbolic worlds,
ASCII/textual visual design, browser visualizers and generative abstract
runtimes, web/3D chambers, Media Ark custody, portfolio projection,
exhibit/kiosk forms, and lifecycle governance.

`UNIFICATION.md` records the current Portvs conductor model for that canon. The
older Visual Media Canon is now treated as one branch of the Visual Form Canon,
not the whole object.

Start cross-project review from remote repository canon, not from local
checkout inventory:

```bash
python3 remote_repo_census.py
```

That writes ignored private receipts:

- `work/remote-repo-census.json`
- `work/remote-repo-census.md`

Current remote-canon scope is 273 repositories scanned across `organvm` and
`4444J99`, with 48 visual-form candidate repositories matched.

Then refresh the private prompt-lineage receipt:

```bash
python3 prompt_lineage.py
```

That writes ignored private receipts:

- `work/visual-form-lineage.json`
- `work/visual-form-lineage.md`

It also writes compatibility receipts for earlier Visual Media Canon references:

- `work/visual-media-lineage.json`
- `work/visual-media-lineage.md`

Those receipts may contain raw prompt excerpts and local session paths. Tracked
docs should use only aggregate counts, clusters, and decisions. Current
non-circular scope is 1,018 local session files scanned, 123 session prompts
matched, and 28 source/project document evidence surfaces matched.

## Landing Surface

The generated page is intentionally media-first. On a wide or fullscreen
viewport, the three panels fill the screen as equal columns. On a narrow or
portrait viewport, the triptych constrains toward a vertical Story shape.

`site/index.html` is the sanitized multi-edition entry point. It is built only
from public `site/editions/*/flash-copy.json` receipts and uses lightweight
edition proxies as previews. When a receipt includes a published post pack, the
index also links the Story and panel Reel exports directly from that sanitized
receipt. Public control presets appear there as direct edition links, so the
index can open a work in modes like `whole-score`, `fracture-sketch`,
`damage-loop`, `signal-sketch`, or `serial-sketch` without exposing the settings
drawer first.

The same build also writes `site/public-manifest.json`: a sanitized public
release map of edition pages, preset URLs, visual sketches, Story/Reel exports,
families, counts, a structured release queue, and verified media facts such as
duration, dimensions, file size, codec, and audio presence. Treat that JSON as
the lightweight post/share manifest for Instagram, YouTube, GitHub, static
hosting, and later product-surface handoff.

It also writes `site/release-board.html`: a human-facing board of the same
public Story, Reel, and sketch outputs with video controls and media facts, so
posting can be selected from the generated package without opening private
receipts or source folders.

`site/release-player.html` is the static playback surface for the same verified
public media. It can run the release sequence as a sequential or random loop,
filter by edition or family, and start muted/autoplaying through URL parameters,
which makes the package usable as a lightweight review loop without adding a
server. Add `kiosk=1` for chromeless digital-frame or gallery playback, and
`fit=contain` when the full frame matters more than edge-to-edge crop.

Player URLs are text-addressable:

```text
site/release-player.html?edition=ballerina&mode=random&muted=1&autoplay=1
site/release-player.html?family=signal_damage&mode=random&muted=1
site/release-player.html?mode=random&muted=1&autoplay=1&kiosk=1
site/release-player.html?program=edition-ballerina-kiosk-random-muted
site/release-player.html?program=edition-ballerina-kiosk-random-muted&muted=0&volume=0.35&rate=0.75
site/release-player.html?start=6
```

`site/player-presets.md` is the generated text card for those player URLs. It
lists the receipt-derived all-release, kiosk, edition, and family loops so
gallery, digital-frame, and review modes can be opened from plain text.

`site/exhibit-loop.md` is the generated gallery/digital-frame handoff. It turns
the same public data into all-work, family, and edition kiosk programs plus the
operating gates for hosting without private Photos or render lanes.

`site/exhibit-programs.json` is the machine-readable version of that handoff:
all-work, family, and edition kiosk programs with local player URLs and item
counts for future hosted players, digital frames, and exhibit controllers. Each
program also carries a sanitized playlist of public Story/Reel/sketch items, so
external players can consume the program without scraping the release queue. The
release player embeds the same program list and accepts `program=<id>` URLs, so
programs can be selected without manually composing query strings.

`site/exhibit-cue-sheet.json` and `site/exhibit-cue-sheet.md` are the public
gallery/digital-frame cue sheet. They combine the public exhibit programs with
public media facts so each loop has a local player URL, item count, runtime,
audio count, silent count, and sanitized playlist.

`site/curatorial-score.json` and `site/curatorial-score.md` are the public
curatorial score. They combine public composition, rhythm, sound, release, and
program facts so each edition has a work note, program URL, runtime, sound
split, output list, and deferred product/shop gate without exposing source
media lanes.

`site/living-loop.json` and `site/living-loop.md` are the public seeded-loop
contract for the hosted/digital-frame surface. They map exhibit programs to
stable seeded player URLs so the surface can feel newly arranged by changing
only text seeds or slot URLs; no source library access or media regeneration is
required. The contract also includes named rotation sets such as
`studio-review`, `gallery-slow`, and `post-spark`, each with bounded browser
volume/rate settings and deterministic seeds for every public exhibit program.

`site/playback-contract.json` is the machine-readable URL-control boundary for
the public player. It lists the allowed query parameters, numeric bounds,
seeded-loop examples, public counts, and privacy gates so future hosted players
or exhibit controllers can stay text-driven without expanding access to private
media lanes.

`site/composition-atlas.json` and `site/composition-atlas.md` are the public
composition index. They name each edition's family, material role, visual style,
panel role, model language, public sketch, and post exports from sanitized
receipts only, so Ballerina, Noonlight, Accidents, and Glitche can remain
different shapes of the same engine.

`site/rhythm-map.json` and `site/rhythm-map.md` are the public cadence score.
They summarize public Story/Reel/sketch duration, audio presence, family totals,
edition totals, and queue order from sanitized media facts only.

`site/sound-map.json` and `site/sound-map.md` are the public audio/silence map.
They identify audio-bearing post exports, intentionally silent visual sketches,
and browser-only playback controls without mutating source audio or rendered
post packs.

`site/release-matrix.json` and `site/release-matrix.md` are the public
posting-target matrix. They group Story/Reel/sketch outputs by edition and
platform target while keeping product/shop use explicitly deferred.

Public player audio/playback controls are URL-driven and bounded:
`volume=0..1` and `rate=0.25..2`. They affect only browser playback of the
public export; they do not mutate source media or regenerated post packs.

`site/release-copy.md` is the companion text deck: caption starters, tags,
media facts, and direct public links for the same generated Story/Reel/sketch
outputs.

`site/platform-plan.md` maps those same public outputs to Instagram Story/Reels,
YouTube Shorts drafts, GitHub/portfolio context, and a deferred product/shop
gate.

`site/release-queue.md` turns the same public outputs into an ordered posting
queue: Story anchor first, panel Reels as excerpts, and visual sketches as
process/context posts. It is intentionally not a calendar, so posting dates can
stay outside the package until they are real.

The visible controls are minimal: play/pause, restart, fullscreen, and settings.
The settings drawer contains:

- preview labels, audio, volume, canon/sketch surface mode, oldest/random start
  mode, direction effect, named presets, and panel arrangement;
- a read-only score panel for the edition's public arrangement metadata;
- the cumulative prompt stack;
- clip reordering and local hide/show controls;
- links to rendered Story and Reel exports.

The browser preview uses embedded clip durations from the project manifest. It
starts with the left panel only, fills the center and right panels, then advances
the full triptych in rounds. Each round is held by the longest active clip;
shorter clips loop in place until the round turns over.

The Direction setting acts like a simple MIDI-style video effect across all
panels: `forward`, `reverse`, or `pingpong` for forward-then-backward playback.

The Panels setting rearranges the triptych surface. The canon voices still enter
as left, then middle, then right internally, but the visible columns can be
ordered as any permutation of those three voices. The drawer also includes a
three-slot arrangement board for tap-driven movement between columns. Rendered
Story exports and single-panel Reel exports can use the same setting through
`canvas.panel_order` in the project JSON; for Reels, `left`, `middle`, and
`right` mean the visible output slot after rearrangement.

Settings can also be carried by the public URL. This makes a composition
shareable as text without editing the generated HTML:

```text
site/editions/ballerina/index.html?preset=whole-score&surface=sketch&dir=pingpong&order=rml&start=random&labels=0&audio=0
```

Supported query parameters are `preset=<id>`, `surface=canon|sketch`,
`dir=forward|reverse|pingpong`, `order=lmr` shorthand or comma-separated panel
names, `start=oldest|random`, `labels=0|1`, `audio=0|1`, `vol=0..1`, and
per-panel `left`, `middle`, `right` volume gains from `0` to `1.5`. The
Settings drawer's Link control rewrites the current preview state into the
address bar.

To preview the schedule without rendering:

```bash
python3 render_triptych.py samples --dry-run
```

To render one custom Story directly:

```bash
python3 render_triptych.py samples --output renders/triptych-canon.mp4 --phrase 4
```

## Folder Workflow

If you collect specific videos in a normal filesystem folder, stage that folder
as a local project:

```bash
python3 import_folder.py ~/Desktop/triptych-selects --render
```

Useful variants:

```bash
python3 import_folder.py ~/Desktop/triptych-selects --recursive --order oldest --render
python3 import_folder.py ~/Desktop/triptych-selects --mode copy --limit 12
python3 export_project.py work/project.folder-local.json --draft
```

This is the cleanest current way to make a better edition: curate the source
clips first, then let the tool handle cadence, mixing, and exports. A Photos
album importer is the next useful source lane so a named Photos collection can
become the edition without staging the whole library.

## Album Editions

Photos albums can now act as named edition inputs and arrangement references.
The same canon engine can run different configurations for albums such as
`accidents`, `ballerina`, `noonlight`, `porn`, or a video-heavy album like
`Glitché`.

The engine title remains `Triptych Video Canon`, but the generated editions are
works with their own titles and families. Current working titles:

- `Ballerina Danse Recomposition`: `ballerina danse` is raw material and
  `ballerina whole` is the panel-reconfiguration score.
- `Noonlight Recomposition`: the still series is both material and serial
  portrait/light score.
- `Accidents Fracture`: the still series needs a more complicated rupture map,
  not just a clean triptych division.
- `Glitche Signal Damage` and `Porn Signal Damage`: a shared signal-damage
  branch for compression, reversal, feedback color, glare, mediation, and
  authored signal-tear maps.

An edition can distinguish raw material from a composition model. For the
ballerina edition, `etcetera/ballerina danse` is the raw material and
`etcetera/ballerina whole` is the arrangement model: the goal is not a linear
dance edit, but a cubist/structural reconstruction of figure fragments across
the triptych. `ballerina whole` should be read as a sketch for how the visible
triptych panels can be reconfigured, not merely as a background image.

List the edition presets:

```bash
python3 build_edition.py --list
```

List Photos albums and their video availability:

```bash
python3 import_photos.py --list-albums --include-live-photos --album-match contains --album accidents --album ballerina --album noonlight --album porn
```

List still-heavy Photos albums and their visual material:

```bash
python3 import_photos_visuals.py --list-albums --album-match contains --album ballerina
```

Build a named edition project without rendering:

```bash
python3 build_edition.py glitche
```

Build a small flash copy from an iCloud-backed Photos album by asking Photos.app
to export missing selected originals:

```bash
python3 build_edition.py glitche --limit 9 --photos-export-missing --sync
```

Build a still-heavy visual album as lightweight generated motion clips:

```bash
python3 build_edition.py ballerina --limit 6 --sync
```

Render a Ballerina arrangement sketch from those generated clips:

```bash
python3 build_edition.py ballerina --skip-import --sketch --sync
```

Build and publish a Noonlight serial-portrait sketch:

```bash
python3 build_edition.py noonlight --limit 6 --sketch --sync
```

Rebuild the public multi-edition index:

```bash
python3 build_site_index.py
```

Check which edition surfaces are staged, synced, packaged, sketched, or
post-packed without inspecting every manifest. The status output also reports
whether the public release manifest exists in both `site/` and the generated
package:

```bash
python3 edition_status.py
python3 edition_status.py --edition ballerina --json
```

Validate the source edition text before importing, rendering, syncing, or
publishing:

```bash
python3 verify_editions.py
```

That gate checks edition family membership, source selectors, named control
presets, panel orders, audio/effect values, score/fracture/signal cell maps,
and the Porn public-export gate without touching media.

Edition syncs update that index automatically when the landing page lives under
`site/editions/<slug>/`. The index surfaces per-edition landing pages, visual
sketches, and any published Story/Reel post-pack links recorded in public
receipts. The companion `site/public-manifest.json` records the same public
surface as portable data for posting, archival transfer, or product funnels;
`site/release-board.html` presents that public surface as a selectable posting
board, `site/release-copy.md` presents it as reusable public posting text, and
`site/platform-plan.md` maps it to platform targets. `site/release-queue.md`
turns the same public media into a posting order without binding the package to
a calendar. `site/release-player.html` turns the same public media into a
sequential/random playback surface with generated kiosk, edition, and family
presets. Random playback also accepts `seed=<text>` so a public loop can stay
text-addressable and reproducible without becoming fixed media.
`site/player-presets.md` exposes those presets and bounded playback examples as
a copyable text card. `site/exhibit-loop.md` translates those same URLs into a
compact gallery/digital-frame handoff with package gates, while
`site/exhibit-programs.json` carries the same programs as structured data.
`site/exhibit-cue-sheet.json` and `site/exhibit-cue-sheet.md` carry the public
program cue sheet with runtime and audio/silent counts.
`site/curatorial-score.json` and `site/curatorial-score.md` carry the public
work score for gallery, portfolio, posting, and later product review.
`site/living-loop.json` and `site/living-loop.md` carry the public seeded-loop
contract for always-new hosted or digital-frame playback without regenerating
media.
`site/playback-contract.json` records the allowed public URL controls and their
verification bounds.
`site/composition-atlas.json` and `site/composition-atlas.md` record the public
composition language for the album-shaped editions.
`site/rhythm-map.json` and `site/rhythm-map.md` record the public cadence and
duration score for the generated outputs.
`site/sound-map.json` and `site/sound-map.md` record the public audio/silence
roles for those outputs.
`site/release-matrix.json` and `site/release-matrix.md` record the public
platform-target matrix and product/shop gate.

That writes:

- `work/editions/<slug>/project.json`: private local project receipt;
- `samples/editions/<slug>/`: staged selected source media;
- `site/editions/<slug>/index.html`: per-edition landing page;
- `site/editions/<slug>/flash-copy.json`: public proxy-centered receipt;
- `site/editions/<slug>/media/`: ignored lightweight video/audio proxies.
- `site/index.html`: sanitized public index of synced editions.
- `site/public-manifest.json`: sanitized public release/post map generated from
  public receipts, including the structured release queue and player presets.
- `site/release-board.html`: sanitized human posting board generated from the
  public manifest data.
- `site/release-player.html`: sanitized static playback surface generated from
  the public manifest data, including the kiosk player mode.
- `site/player-presets.md`: sanitized player preset card generated from public
  receipts.
- `site/exhibit-loop.md`: sanitized gallery/digital-frame loop handoff
  generated from public receipts.
- `site/exhibit-programs.json`: sanitized machine-readable exhibit program map
  generated from public receipts.
- `site/exhibit-cue-sheet.json`: sanitized machine-readable exhibit cue sheet
  generated from public exhibit programs and media facts.
- `site/exhibit-cue-sheet.md`: sanitized human exhibit cue sheet generated from
  public exhibit programs and media facts.
- `site/curatorial-score.json`: sanitized machine-readable curatorial score
  generated from public composition, rhythm, sound, release, and program facts.
- `site/curatorial-score.md`: sanitized human curatorial score generated from
  public composition, rhythm, sound, release, and program facts.
- `site/living-loop.json`: sanitized machine-readable seeded-loop contract
  generated from public exhibit programs and curatorial score facts.
- `site/living-loop.md`: sanitized human seeded-loop contract generated from
  public exhibit programs and curatorial score facts.
- `site/playback-contract.json`: sanitized machine-readable playback control
  contract generated from public receipts.
- `site/composition-atlas.json`: sanitized machine-readable composition atlas
  generated from public receipts.
- `site/composition-atlas.md`: sanitized human composition atlas generated from
  public receipts.
- `site/rhythm-map.json`: sanitized machine-readable rhythm map generated from
  public media facts.
- `site/rhythm-map.md`: sanitized human rhythm map generated from public media
  facts.
- `site/sound-map.json`: sanitized machine-readable sound map generated from
  public media facts.
- `site/sound-map.md`: sanitized human sound map generated from public media
  facts.
- `site/release-matrix.json`: sanitized machine-readable release matrix
  generated from the public release queue.
- `site/release-matrix.md`: sanitized human release matrix generated from the
  public release queue.
- `site/release-copy.md`: sanitized markdown copy deck generated from the public
  manifest data.
- `site/platform-plan.md`: sanitized platform plan generated from the public
  manifest data.
- `site/release-queue.md`: sanitized public posting queue generated from the
  public manifest data.

Render from the same edition config when the source set feels right:

```bash
python3 build_edition.py glitche --skip-import --render --draft --only story-triptych
python3 build_edition.py glitche --skip-import --render --sync
```

Build a post pack when the edition is ready to publish as Story/Reels:

```bash
python3 build_post_pack.py ballerina --skip-import --profile draft
python3 build_post_pack.py glitche --skip-import --profile draft
```

The post-pack runner renders the configured Story plus three panel Reels by
default, syncs the public edition receipt, publishes those exports under
`site/editions/<slug>/exports/`, then runs `verify_post_pack.py` and
`verify_public_site.py`. Profiles are text-driven: `draft` is small and fast,
`share` is larger but still bounded, and `full` keeps the edition's configured
export settings. Draft/share profiles may cap per-clip duration with
`max_clip_seconds` so long raw videos remain lightweight for public packages;
source media is not changed, and `full` keeps the uncapped source-led cadence.

To verify a previously rendered pack without rerendering:

```bash
python3 verify_post_pack.py work/editions/ballerina/project.json
```

Still-heavy Photos albums use `import_photos_visuals.py`. It reads the Photos
catalog, selects local stills from the named album/folder, turns each selected
still into a short lossy MP4 with small motion, and then hands those generated
clips to the same canon renderer. Generated clip lengths can intentionally vary
with `duration_pattern`, preserving the imperfect cadence instead of forcing a
single beat.

For `ballerina`, `build_edition.py` also stages the first item from
`etcetera/ballerina whole` under ignored `work/editions/ballerina/models/` as
the arrangement model reference while using `etcetera/ballerina danse` as the
raw motion material.

Current visual read: Ballerina is a sliced/collaged structural whole with body
fragments and transparent rectangular overlays; Noonlight is a serial close
portrait study with subtle gaze shifts and blown-out window light; Accidents is
treated as a collision grid of rupture, aftermath, and repetition. Those are
composition sketches for the video editions, not only source albums.

`render_visual_sketch.py` is the first reversible attempt at that layer. It has
five text-configurable sketch styles: `slices` for simple collage, `score` for
model-guided recomposition, `serial` for Noonlight-like portrait/gaze sequences,
`fracture` for Accidents-like collision grids, and `signal` for Glitche/Porn
compression tears, feedback bands, and temporal misfire maps. It is a sketch
renderer, not a replacement for the canon cadence. For slice and score sketches,
it can read
`composition.arrangement_model_assets` and place a staged model still under the
moving fragments, so `ballerina whole` can structurally guide `ballerina danse`.
With `model_fit: "triptych"`, the staged model still's left/middle/right thirds
are mapped into the visible panel order, so panel rearrangement also rearranges
the structural sketch. The `score` style then overlays moving rectangular
fragments in a Ballerina-Whole-like composition map, making panel rearrangement
part of the work rather than a decorative preview control. That map can now live
in `visual_sketch.score_cells`, where each cell declares normalized `x`, `y`,
`width`, `height`, `alpha`, and optional source clip index values. Accidents can
use the parallel `visual_sketch.fracture_cells` field for an irregular rupture
map instead of the default regular collision grid. Signal-damage editions can
use `visual_sketch.signal_cells` for damaged rectangles, scanline tears, and
feedback-like overlaps without changing the shared renderer.
When synced, the generated `visual-sketch` video can be selected as the landing
page's main surface, appears in the export links, and is recorded in the public
flash-copy receipt. Sync also publishes a sanitized `arrangement_score` summary
into the landing page and flash-copy receipt: work title, family, public album
labels, sketch style, score/fracture/signal cell count, and short composition notes.
That keeps the authored map visible and shareable without exposing private
source paths or requiring a viewer to open the JSON preset.

## Lightweight Web Proxies

The landing page does not try to play every original file directly. When
`export_project.py` builds `site/index.html`, it also creates lightweight
proxies for the selected source clips under ignored `site/media/`:

- video proxy: low-frame-rate H.264 MP4, no audio;
- audio proxy: tiny AAC `.m4a`, mono by default;
- originals remain untouched and are still used for full ffmpeg Story/Reel
  renders.

The compression artifacts are intentional material. Tune the recipe in
`project.example.json` or a local project manifest:

```json
"web_media": {
  "enabled": true,
  "video_height": 540,
  "fps": 15,
  "crf": 36,
  "audio_bitrate": "48k",
  "audio_channels": 1
}
```

Keep this bounded to an edition. The system can catalog 1000+ videos, but it
should only proxy the selected working set that belongs on the current surface.

## Generated Media Lifecycle

The project should stay light on its feet even while generating drafts. Use the
read-only inventory before and after larger autonomous passes:

```bash
python3 generated_inventory.py
python3 generated_inventory.py --cleanup-plan
python3 generated_inventory.py --json
python3 verify_local_lifecycle.py
python3 overnight_checkpoint.py
python3 verify_private_workflow.py
```

This classifies the ignored local lanes:

- `work/`: private generated state, receipts, catalogs, phrases, and model refs;
- `renders/`: generated Story/Reel/sketch media;
- `site/`: generated static public surface and lightweight proxies;
- `packages/`: generated hostable copies/zips of the verified public site;
- `samples/`: staged selected media, heavy by design and not disposable by
  default unless the source can be restaged.

`--cleanup-plan` is still read-only. It ranks generated lanes by reclaimable
size, labels cleanup risk, and lists the commands needed to regenerate or
verify each lane before any manual deletion happens.

`verify_local_lifecycle.py` is the Git-visible containment gate. It fails if
generated/local lanes such as `site/`, `renders/`, `packages/`, `samples/`, or
`work/` leak back into review, and it can enforce optional budgets for
untracked file count or untracked text lines before an autonomous pass ends.
Use `--require-clean` at the final checkpoint when all reviewed source has been
committed or deliberately left for the human.

`overnight_checkpoint.py` writes ignored private receipts at
`work/overnight-checkpoint.json`, `work/overnight-checkpoint.md`,
`work/release-focus.json`, `work/release-focus.md`, and
`work/release-focus.html`, plus `work/control-auditions.json`,
`work/control-auditions.md`, `work/control-auditions.html`,
`work/next-render-queue.json`, `work/next-render-queue.md`,
`work/next-render-queue.html`, `work/overnight-dashboard.json`,
`work/overnight-dashboard.md`, `work/overnight-dashboard.html`,
`work/static-hosting-handoff.json`, `work/static-hosting-handoff.md`, and
`work/static-hosting-handoff.html`, plus `work/first-release-packet.json`,
`work/first-release-packet.md`, and `work/first-release-packet.html`, plus
`work/posting-receipt-template.json`,
`work/posting-receipt-template.md`, and
`work/posting-receipt-template.html`, plus `work/release-cadence-plan.json`,
`work/release-cadence-plan.md`, and `work/release-cadence-plan.html`, plus
`work/edition-refinement-slate.json`,
`work/edition-refinement-slate.md`, and
`work/edition-refinement-slate.html`, plus
`work/cache-retention-plan.json`, `work/cache-retention-plan.md`, and
`work/cache-retention-plan.html`, plus
`work/source-curation-plan.json`, `work/source-curation-plan.md`, and
`work/source-curation-plan.html`, plus
`work/audio-control-plan.json`, `work/audio-control-plan.md`, and
`work/audio-control-plan.html`, plus
`work/paired-work-order.json`, `work/paired-work-order.md`, and
`work/paired-work-order.html`. The
checkpoint pairs
creative state with containment state: public edition coverage, living-loop
rotations, release-focus recommendations, package readiness, cleanup
candidates, Porn gating, and the next autonomous moves. The standalone
release-focus files turn those recommendations into posting/refinement handoffs
without copying media; the HTML page is the private visual review surface over
the verified package videos. The standalone control-audition files turn public
presets, landing-page direction/panel/audio parameters, focus-player links, and
living-loop URLs into private text-control recipes that generate no new media.
The standalone next-render queue turns those reviews into planned-only render
candidates with dry-run commands and post-render gates. The standalone
overnight dashboard is the private conductor index over those handoffs, package
entry points, and containment posture. The standalone static-hosting handoff is
the no-secrets transfer scope for the verified package directory or zip. The
standalone first-release packet selects one verified package media item and
turns it into platform-specific posting copy without rendering new media. The
standalone posting receipt template keeps future platform evidence private and
unposted until a real post exists. The standalone release-cadence plan orders
verified focus candidates without becoming a calendar or publishing surface.
The standalone edition-refinement slate keeps each edition's next action,
public gate, visual map, cadence state, and render posture visible together.
The standalone cache-retention plan keeps disk pressure visible while making
deletion explicitly manual and gated. The standalone source-curation plan keeps
raw album, arrangement model album, dry-run command, public gate, and staging
posture visible before any source refresh. The standalone audio-control plan
keeps gain, panel balance, reverse/ping-pong posture, public sound facts, and
browser-only playback controls visible before any audio rerender. The
standalone paired-work-order keeps each next creative edit visibly paired with
its containment gate before render, source, audio, or cache changes.

`verify_private_workflow.py` validates those ignored private handoffs. It checks
that focus media links resolve to generated public/package files, the private
HTML pages match the JSON handoffs, edit prompts are present, product/shop use
remains deferred, control auditions stay no-media/no-source, render candidates
stay planned-only and non-destructive, dashboard links resolve locally, static
hosting scope excludes private/generated lanes, and private source tokens are
absent. It also checks the first-release packet's selected media, platform
packet refs, no-source/no-media posture, the posting receipt template's
truthful unposted state, release-cadence link/order integrity, and deferred
product/shop gate. It also checks edition-refinement gate integrity, including
that Porn remains gated local-only.
It also checks cache-retention read-only posture before any reclaim plan is
treated as actionable. It also checks source-curation dry-run/source-gate
integrity before source selection changes are treated as actionable. It also
checks audio-control no-source/no-mutation integrity before audio changes are
treated as actionable. It also checks paired-work-order no-media/no-source
integrity before the next always-both action is treated as actionable.

`OVERNIGHT_WORKSTREAM.md` records the current autonomous rule: every creative
iteration should also keep generated weight, privacy, and regeneration bounded.

## Flash Copy Sync

The lightweight "living" version is a flash copy: selected project metadata plus
disposable proxy media, not a clone of the Photos library.

```bash
python3 sync_flash_copy.py work/project.photos-local.json
```

That command:

- regenerates missing/stale `site/media/` video and audio proxies;
- writes `work/flash-copy.json`, an ignored private receipt that can include
  local source paths and Photos source IDs for regeneration;
- writes `site/flash-copy.json`, a proxy-centered receipt for static/public
  output;
- rebuilds `site/index.html` unless `--no-landing` is passed.

Useful variants:

```bash
python3 sync_flash_copy.py work/project.folder-local.json
python3 sync_flash_copy.py work/project.photos-local.json --no-landing
python3 sync_flash_copy.py work/project.photos-local.json --dry-run
```

This is the sharing boundary. A hosted/public edition should publish the static
site, selected renders, `site/flash-copy.json`, and `site/media/` proxies. It
should not publish the private Photos library or ignored `work/` receipts.

Before sharing or hosting the generated site, run:

```bash
python3 verify_public_site.py
```

That checks every public edition receipt and public text file under `site/` for
private Photos/library tokens, verifies referenced proxy media and published
exports exist inside the static site, validates public control presets, probes
published Story/Reel and visual-sketch exports with `ffprobe`, confirms the root
index links all synced editions and their preset URLs, verifies
`public-manifest.json` against public receipts and files, re-probes release
manifest media facts, confirms the release board links every public post/sketch,
confirms the release player, copy deck, platform plan, and release queue link
every public post/sketch, checks the player preset URLs remain local and
receipt-derived, confirms the player preset card lists them, and fails if the
generated package is no longer lightweight enough.

Package the verified public site for static hosting:

```bash
python3 package_public_site.py
```

That verifies `site/`, copies only `site/` into
`packages/triptych-video-canon-site/`, normalizes copied public receipts for the
package root, writes a checksummed `package-manifest.json` with a public edition
summary, verifies the package tree, and creates
`packages/triptych-video-canon-site.zip`. The package lane is generated and
ignored; it should not contain `work/`, `samples/`, `renders/`, or direct Photos
library paths.

Verify a generated or transferred package against its manifest:

```bash
python3 verify_package.py
```

That recomputes every packaged file checksum, checks the package manifest's
edition summary is present, rejects private/generated source lanes such as
`work/`, `samples/`, `renders/`, or nested `packages/`, and reruns the
public-site verifier against the package directory.

## Opt-In Photos Import

After explicit local permission, the prototype can read the macOS Photos catalog
and stage local video files automatically. It writes private/local state under
ignored paths, leaving the tracked example project clean.

```bash
python3 import_photos.py --include-live-photos --render
```

That command:

- reads `~/Pictures/Photos Library.photoslibrary/database/Photos.sqlite`;
- stages matched local media as symlinks in `samples/photos-import/`;
- orders staged media oldest-first, so the first local canon can begin with the
  earliest video Photos exposes locally;
- writes `work/project.photos-local.json`;
- renders the Story, three Reels, and landing page from that local project.

Useful variants:

```bash
python3 import_photos.py --limit 9 --max-duration 45 --include-live-photos --render
python3 import_photos.py --limit 24 --max-duration 90 --include-live-photos --render
python3 import_photos.py --all-local --max-duration 0 --mode copy
python3 import_photos.py --dry-run --include-live-photos
```

Photos assets that are still iCloud-only cannot be rendered until Photos has
downloaded the original or a local render exists in the library package.

When the catalog knows about an old video but the library package only has
thumbnails, this opt-in variant asks Photos.app to export the selected originals
by asset id:

```bash
python3 import_photos.py --limit 9 --max-duration 45 --include-live-photos --photos-export-missing --render
```

That path still stages only local incubator files and does not mutate Photos.

## Library-Scale Workflow

For 1000+ videos, keep the library as metadata until an edition needs a small
working set. The lightweight flow is:

1. Catalog everything as JSON metadata.
2. Select a small edition by date, offset, random seed, duration, or exclusions.
3. Stage only that edition as symlinks or Photos.app exports.
4. Draft quickly.
5. Render the Story/Reels only after the selection feels right.

Build the metadata catalog without copying videos:

```bash
python3 catalog_photos.py --include-live-photos
```

To also mark which Photos assets already have a local source file in the library
package:

```bash
python3 catalog_photos.py --include-live-photos --check-local
```

The catalog is written to `work/photos-catalog.json`, which is ignored by git.
It contains UUIDs, dates, durations, dimensions, orientation, yearly counts, and
optional local availability.

Page through the library without staging all of it:

```bash
python3 import_photos.py --limit 24 --offset 0 --include-live-photos
python3 import_photos.py --limit 24 --offset 24 --include-live-photos
python3 import_photos.py --limit 24 --offset 48 --include-live-photos
```

Make a stable random edition:

```bash
python3 import_photos.py --limit 36 --random-seed first-public-canon --include-live-photos
```

Select a date range:

```bash
python3 import_photos.py --start-date 2012-01-01 --end-date 2012-12-31 --limit 24 --include-live-photos
```

Ban a clip from future Photos imports after seeing it in the current project:

```bash
python3 manage_clips.py ban 3
python3 manage_clips.py ban IMG_0765 6F129562
```

That writes source UUIDs to `work/photos-exclude-uuids.txt`. Future
`import_photos.py` runs use that file by default. To undo:

```bash
python3 manage_clips.py unban 6F129562
```

A public hosted page cannot directly access the private local Photos library.
The light version is a local living loop that catalogs/selects/renders from
Photos, then publishes selected static outputs and manifests.

## Hiding Clips

Generated projects keep clip visibility in a `clips` array. You can hide/show
clips without opening the JSON:

```bash
python3 manage_clips.py list
python3 manage_clips.py hide 3
python3 manage_clips.py hide 2011 IMG_0765 6F129562
python3 manage_clips.py show 3
python3 manage_clips.py only 1 2 5
```

Then re-render:

```bash
python3 export_project.py work/project.photos-local.json --draft
python3 export_project.py work/project.photos-local.json --only story-triptych
```

## Timing Modes

The default `clip` timing mode treats uneven video lengths as part of the piece.
It starts left-only, then fills the center and right panels. Once the triptych is
filled, it stays filled: every cadence step is a round whose duration is the
longest active clip, while shorter clips loop in their panels until the round
turns over. Finite renders cycle the source list just long enough for the last
original clip to complete in the right panel.

For stricter phrase timing, use `fixed`:

```bash
python3 render_triptych.py samples --timing fixed --phrase 4 --output renders/fixed-story.mp4
```

The default output is `1080x1920` at `30fps`. Renders are silent unless an audio
mode is selected.

## Audio Modes

Audio is explicit because it changes the piece:

- `none`: silent output.
- `panel`: follow one named panel's source audio.
- `mix`: mix audible rendered panels together.

Examples:

```bash
python3 export_project.py work/project.photos-local.json --draft --audio panel --audio-panel left --audio-gain 0.9
python3 export_project.py work/project.photos-local.json --draft --audio mix --audio-gain 0.45 --audio-fade 0.08
python3 export_project.py work/project.photos-local.json --draft --audio mix --audio-gain 0.5 --audio-left-gain 1 --audio-middle-gain 0.7 --audio-right-gain 0.35
```

Rendered audio follows the selected direction effect. `reverse` reverses the
audible phrase, and `pingpong` plays the phrase forward then backward before
looping it to the round length.

The browser preview uses the generated `.m4a` proxies through WebAudio, so
preview audio can also run forward, reverse, or ping-pong. Browsers require a
tap/click before audio starts; the Audio setting in the drawer is the intended
unlock.

## Video Effects

Direction is a global visual effect in this prototype:

- `forward`: every panel plays normally.
- `reverse`: every panel loops backward.
- `pingpong`: every panel loops forward, then backward.

Examples:

```bash
python3 export_project.py work/project.photos-local.json --draft --direction reverse
python3 export_project.py work/project.photos-local.json --draft --direction pingpong
```

Tone balancing is opt-in and happens at render time, leaving source files alone.
Use `normalize` first; `histeq` is more aggressive.

```bash
python3 export_project.py work/project.photos-local.json --draft --tone normalize --tone-strength 0.35 --tone-smoothing 50
python3 export_project.py work/project.photos-local.json --draft --tone histeq
```

Panel-specific video effects and deeper per-clip routing are future layers.

## Canon Rule

In `fixed` mode, at phrase `0`, video `A` appears in the left panel.

At phrase `1`, video `A` moves to the middle and video `B` enters on the left.

At phrase `2`, video `A` moves to the right, `B` moves to the middle, and `C`
enters on the left.

The pattern continues until the final videos have passed through all three
panels.

In `clip` mode, the same left-to-right rule applies, but each round's duration is
set by the longest currently visible source clip. The opening state is left-only:
the middle and right panels stay blank until the canon fills. After that, panels
remain occupied, shorter clips loop under the longest one, and the finite render
closes by letting the last original clip finish its right-panel round.

## Files

- `render_triptych.py`: local renderer using Python stdlib plus `ffmpeg`.
  Supports `max_clip_seconds` for export-time duration caps without source
  mutation.
- `export_project.py`: text-driven export runner for Story, panel Reels, and the
  static landing page.
- `sync_flash_copy.py`: regenerates selected-edition web proxies and private/public
  flash-copy receipts.
- `build_site_index.py`: writes the sanitized multi-edition root index from
  public flash-copy receipts, including public preset links, post-pack links,
  `site/public-manifest.json` with probed public media facts, and
  `site/release-board.html`, `site/release-player.html`,
  `site/player-presets.md`, `site/exhibit-loop.md`,
  `site/exhibit-programs.json`, `site/exhibit-cue-sheet.json`,
  `site/exhibit-cue-sheet.md`, `site/curatorial-score.json`,
  `site/curatorial-score.md`, `site/living-loop.json`,
  `site/living-loop.md`, `site/playback-contract.json`,
  `site/composition-atlas.json`, `site/composition-atlas.md`,
  `site/rhythm-map.json`, `site/rhythm-map.md`,
  `site/sound-map.json`, `site/sound-map.md`,
  `site/release-matrix.json`, `site/release-matrix.md`,
  `site/release-copy.md`,
  `site/platform-plan.md`, and `site/release-queue.md`.
- `verify_editions.py`: validates the source edition preset file before import,
  render, sync, or publish work touches media.
- `verify_public_site.py`: checks the generated `site/` package for privacy,
  missing media/export references, public control-preset consistency, root-index
  preset links, public release-manifest consistency, structured release-queue
  consistency, player-preset/card consistency, exhibit-loop kiosk links,
  exhibit-program schema and counts, exhibit-cue-sheet runtime/audio/program
  consistency, curatorial-score work/runtime/program consistency,
  living-loop seed/program/no-media-regeneration consistency,
  playback-contract parameter bounds and
  examples, composition-atlas links and public composition fields,
  rhythm-map duration/count/link consistency, sound-map audio/silence
  consistency, release-matrix target/product-gate consistency, and media facts, release
  board/player/copy/platform-plan/queue links, Story/Reel and visual-sketch
  media properties, receipt consistency, and bounded size before sharing.
- `package_public_site.py`: copies the verified static site into an ignored
  hostable package, normalizes public receipts for the package root, verifies
  the copied package, writes file checksums plus public edition provenance, and
  optionally zips it.
- `verify_package.py`: recomputes package file hashes, compares them with
  `package-manifest.json`, rejects private/generated source lanes in the
  package, and reruns the public-site verifier against the packaged tree.
- `build_edition.py`: turns a named edition preset into a local project, optional
  render, and optional flash copy.
- `edition_status.py`: read-only status table for edition presets, local
  projects, public receipts, package receipts, release manifests, sketches, and
  post packs.
- `build_post_pack.py`: renders a named edition's Story/Reel pack with a chosen
  export profile, syncs public receipts, and runs the public site verifier.
- `verify_post_pack.py`: uses `ffprobe` to verify a rendered Story/Reel pack's
  public receipt state, dimensions, duration, 9:16 shape, and bounded file size.
- `import_photos.py`: explicit local Photos importer that stages local videos and
  writes an ignored local project manifest. It can also list/match Photos albums.
- `generated_inventory.py`: read-only generated-media inventory for keeping
  local cache, staged media, public site output, and packages bounded. It can
  emit JSON or a manual cleanup plan without deleting files.
- `overnight_checkpoint.py`: private checkpoint writer for the autonomous
  workstream. It refreshes `work/overnight-checkpoint.json` and
  `work/overnight-checkpoint.md` from sanitized public receipts plus local
  inventory state, including a deterministic release-focus section that points
  at verified public Story/Reel/sketch outputs. It also writes standalone
  `work/release-focus.json`, `work/release-focus.md`, and
  `work/release-focus.html` handoffs plus `work/control-auditions.json`,
  `work/control-auditions.md`, `work/control-auditions.html`,
  `work/next-render-queue.json`, `work/next-render-queue.md`,
  `work/next-render-queue.html`, `work/overnight-dashboard.json`,
  `work/overnight-dashboard.md`, `work/overnight-dashboard.html`,
  `work/static-hosting-handoff.json`, `work/static-hosting-handoff.md`, and
  `work/static-hosting-handoff.html`, plus `work/first-release-packet.json`,
  `work/first-release-packet.md`, and `work/first-release-packet.html`, plus
  `work/posting-receipt-template.json`,
  `work/posting-receipt-template.md`, and
  `work/posting-receipt-template.html`, plus
  `work/release-cadence-plan.json`, `work/release-cadence-plan.md`, and
  `work/release-cadence-plan.html`, plus
  `work/edition-refinement-slate.json`,
  `work/edition-refinement-slate.md`, and
  `work/edition-refinement-slate.html`, plus
  `work/cache-retention-plan.json`, `work/cache-retention-plan.md`, and
  `work/cache-retention-plan.html`, plus
  `work/source-curation-plan.json`, `work/source-curation-plan.md`, and
  `work/source-curation-plan.html`, plus
  `work/audio-control-plan.json`, `work/audio-control-plan.md`, and
  `work/audio-control-plan.html`, plus
  `work/paired-work-order.json`, `work/paired-work-order.md`, and
  `work/paired-work-order.html`.
- `verify_private_workflow.py`: private workflow verifier for ignored
  checkpoint and release-focus receipts. It checks local refs, the private
  review/audition HTML, edit prompts, product/shop deferral, no-media audition
  state, no-destructive render planning, dashboard link integrity,
  static-hosting scope, first-release packet integrity, posting receipt
  template truthfulness, release-cadence link/order integrity,
  edition-refinement gate integrity, cache-retention read-only posture,
  source-curation dry-run/source-gate integrity, audio-control
  no-source/no-mutation integrity, paired-work-order no-media/no-source
  integrity, and private-token absence.
- `OVERNIGHT_WORKSTREAM.md`: autonomous workstream note that keeps creative
  engine expansion paired with lifecycle containment.
- `editions.example.json`: named album/configuration presets for multiple forms
  of the same canon engine.
- `project.example.json`: cumulative project brief, export presets, and landing
  page settings.
- `manifest.example.json`: minimal single-render settings.
- `samples/`: manually exported source videos, ignored by git.
- `renders/`: rendered outputs, ignored by git.
- `work/`: temporary render segments, ignored by git.
- `site/`: generated static landing pages and public edition index.
- `site/media/`: generated web media proxies, ignored by git.

## Notes

This prototype does not add repo-root dependencies, deploy hosting, mutate
Photos, or decide the final owner. Photos ingestion is opt-in and local: it reads
the Photos catalog and stages media into ignored incubator paths. If the device
proves useful, the promotion target should be recorded in `INCUBATION.md` before
moving files.
