# Overnight Workstream

This incubator should always run on two tracks at once:

1. Creative engine: improve the triptych/canon/still-to-motion device as an
   expressive surface for Ballerina, Noonlight, Accidents, Glitche, and later
   product-facing editions.
2. Lifecycle containment: keep generated media bounded, private receipts private,
   public packages verifiable, and source selection reversible.

The answer to "creative work or debt cleanup?" is both. Each autonomous pass
should leave either a better creative surface, a clearer lifecycle boundary, or
both; it should not add unbounded media weight without a regeneration path.

## Nightly Loop

1. Read `AGENTS.md` and this incubator's `INCUBATION.md`.
2. Run `python3 generated_inventory.py`, `python3 verify_local_lifecycle.py`,
   `python3 verify_editions.py`, and `python3 edition_status.py`.
3. Pick one creative move and one containment move.
4. Prefer text-configurable edition presets, draft profiles, and lightweight
   proxy refreshes over full renders.
5. Verify the narrow changed surface.
6. Run `python3 generated_inventory.py` again if new media was produced.
7. Run `python3 overnight_checkpoint.py` to refresh the private creative and
   containment receipt plus `work/release-focus.json`,
   `work/release-focus.md`, `work/release-focus.html`,
   `work/control-auditions.json`, `work/control-auditions.md`, and
   `work/control-auditions.html`, plus `work/next-render-queue.json`,
   `work/next-render-queue.md`, `work/next-render-queue.html`,
   `work/overnight-dashboard.json`, `work/overnight-dashboard.md`, and
   `work/overnight-dashboard.html`, plus `work/static-hosting-handoff.json`,
   `work/static-hosting-handoff.md`, and `work/static-hosting-handoff.html`,
   plus `work/first-release-packet.json`, `work/first-release-packet.md`, and
   `work/first-release-packet.html`, plus
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
8. Run `python3 verify_private_workflow.py` to verify private handoffs.
9. Run `python3 verify_local_lifecycle.py --require-clean` and end with
   `git status --short --branch --ahead-behind`.

## Creative Queue

- Preserve panel rearrangement as a first-class quality of the triptych.
- Keep `ballerina danse` as raw material and `ballerina whole` as the structural
  score for `Ballerina Danse Recomposition`.
- Continue treating Noonlight as a serial portrait/light recomposition.
- Continue treating Accidents as a rupture/fracture map, not a clean grid.
- Keep Glitche and Porn in the signal-damage family through authored
  `signal_cells`; Porn remains gated until explicitly reviewed for public export.
- Extend named control presets only when they make the public page more playable
  without exposing settings on first load.
- Keep the release player useful in two public modes: review-board playback with
  queue/chrome visible, and kiosk playback for chromeless digital-frame/gallery
  loops.
- Keep `site/exhibit-loop.md` as the public gallery handoff: all-work, family,
  and edition kiosk URLs plus operating gates, generated from public receipts.
- Keep `site/exhibit-programs.json` as the machine-readable program map for
  future hosted players, digital frames, and exhibit controllers; it should
  expose only local player URLs, public item counts, and sanitized public
  playlists, and the release player should embed it for `?program=<id>`
  playback.
- Keep `site/exhibit-cue-sheet.json` and `site/exhibit-cue-sheet.md` as the
  public gallery/digital-frame cue sheet; they should expose only sanitized
  public program URLs, runtime, audio/silent counts, playlists, and verification
  gates.
- Keep `site/curatorial-score.json` and `site/curatorial-score.md` as the
  public work score for gallery, portfolio, posting, and product review; they
  should expose only sanitized public work notes, program URLs, runtime,
  sound splits, output lists, and a deferred product/shop gate.
- Keep `site/living-loop.json` and `site/living-loop.md` as the public
  seeded-loop contract for the hosted or digital-frame surface; it should
  expose only local seeded player URLs, make seed changes browser-only, and
  require no media regeneration. Rotation sets such as `studio-review`,
  `gallery-slow`, and `post-spark` should remain URL recipes, not rendered
  media variants.
- Keep `site/playback-contract.json` as the machine-readable text-control
  boundary for public playback; it should expose only local player references,
  allowed query parameters, numeric bounds, seeded examples, and privacy gates.
- Keep `site/composition-atlas.json` and `site/composition-atlas.md` as the
  public album-shape index; they should expose only sanitized edition
  composition language, family grouping, public sketch/post links, and
  verification gates.
- Keep `site/rhythm-map.json` and `site/rhythm-map.md` as the public cadence
  score; they should expose only sanitized public media durations, audio
  presence, family/edition totals, queue order, and verification gates.
- Keep `site/sound-map.json` and `site/sound-map.md` as the public
  audio/silence map; they should expose only sanitized public media sound roles,
  browser-only playback controls, and source-immutable verification gates.
- Keep `site/release-matrix.json` and `site/release-matrix.md` as the public
  target matrix; they should expose only sanitized public release links, edition
  and platform groupings, and an explicit deferred product/shop gate.
- Keep public audio/playback controls text-driven and bounded: `volume=0..1`
  and `rate=0.25..2` may affect browser playback but must not mutate source
  media or rendered post packs.
- Keep random public loops optionally reproducible: `seed=<text>` should affect
  browser shuffle order only, so an exhibit or posting handoff can replay the
  same living sequence without generating new media.

## Containment Queue

- Keep direct Photos access local and opt-in.
- Keep the 1000-video path metadata-first; stage only selected editions.
- Treat `work/`, `renders/`, `site/`, and `packages/` as generated lanes.
- Treat `samples/` as staged selected media, not disposable by default.
- Use `python3 generated_inventory.py --cleanup-plan` for drive-pressure
  triage. It is read-only and should rank reclaim candidates with regeneration
  gates instead of deleting files.
- Use `python3 verify_local_lifecycle.py` before and after autonomous passes so
  generated lanes, Finder metadata, and Python caches cannot remain
  Git-visible. Use `--max-untracked` and `--max-untracked-lines` when a pass is
  expected to end with no untracked source surface, and `--require-clean` when
  the pass should end with no pending incubator diff.
- Use `python3 overnight_checkpoint.py` after verification to write the private
  paired-state receipt. It should summarize creative coverage, package health,
  release-focus recommendations, cleanup pressure, Porn gating, and the next
  autonomous moves without exposing private source paths. The standalone
  `work/release-focus.md` and `work/release-focus.html` handoffs should point
  only at verified public Story/Reel/sketch hrefs and keep product/shop use
  deferred. The standalone `work/control-auditions.md` and
  `work/control-auditions.html` handoffs should expose package-local preset,
  direction, panel-order, volume/rate, and living-loop URL recipes without
  rendering new media. The standalone `work/next-render-queue.md` and
  `work/next-render-queue.html` handoffs should name planned-only render
  candidates, dry-run commands, and post-render gates without executing renders
  or deleting generated lanes. The standalone `work/overnight-dashboard.md` and
  `work/overnight-dashboard.html` handoffs should be the private conductor
  index across focus, auditions, render queue, package entry points, and
  containment posture. The standalone `work/static-hosting-handoff.md` and
  `work/static-hosting-handoff.html` handoffs should name the verified package
  transfer scope, preflight gates, and never-upload lanes without deploying or
  requiring secrets. The standalone `work/first-release-packet.md` and
  `work/first-release-packet.html` handoffs should select one verified package
  media item and turn it into platform-specific posting copy without rendering
  new media. The standalone `work/posting-receipt-template.md` and
  `work/posting-receipt-template.html` handoffs should keep future
  social-platform evidence private and explicitly unposted until a real post
  exists. The standalone `work/release-cadence-plan.md` and
  `work/release-cadence-plan.html` handoffs should order the verified focus
  candidates without becoming a calendar or publishing surface. The standalone
  `work/edition-refinement-slate.md` and
  `work/edition-refinement-slate.html` handoffs should keep each edition's
  next action, public gate, visual map, cadence state, and render posture
  visible together. The standalone `work/cache-retention-plan.md` and
  `work/cache-retention-plan.html` handoffs should keep disk pressure visible
  while making deletion explicitly manual and gated. The standalone
  `work/source-curation-plan.md` and `work/source-curation-plan.html` handoffs
  should keep raw album, arrangement model album, dry-run command, and public
  gate decisions visible before any source refresh. The standalone
  `work/audio-control-plan.md` and `work/audio-control-plan.html` handoffs
  should keep gain, panel balance, reverse/ping-pong posture, public sound
  facts, and browser-only playback controls visible before any audio rerender.
  The standalone `work/paired-work-order.md` and
  `work/paired-work-order.html` handoffs should keep every next creative edit
  visibly paired with a containment gate before any render, source, audio, or
  cache action.
- Use `python3 verify_private_workflow.py` before treating private handoffs as
  actionable. It checks package/media refs, the private review/audition HTML,
  edit prompts, deferred product/shop state, no-media audition state,
  no-destructive render planning, dashboard link integrity, static-hosting
  scope, first-release packet integrity, posting receipt template truthfulness,
  release-cadence link/order integrity, edition-refinement gate integrity, and
  cache-retention read-only posture, source-curation dry-run/source-gate
  integrity, audio-control no-source/no-mutation integrity, paired-work-order
  no-media/no-source integrity, and private-token absence.
- Before sharing, run `python3 verify_public_site.py`; this includes public
  preset links, the public release manifest, plus Story/Reel and visual-sketch
  media probing, release-manifest media-fact checks, and release-board/player
  links, player preset URLs, kiosk hooks, the preset card, and exhibit-loop
  kiosk URLs, embedded player programs, bounded player audio/rate controls,
  seeded random playback hooks, exhibit-program schema/counts/playlists,
  exhibit-cue-sheet runtime/audio/program consistency, playback-contract
  bounds/examples/counts, curatorial-score work/runtime/program consistency,
  living-loop seed/program/no-media-regeneration consistency,
  composition-atlas links/fields/counts,
  rhythm-map durations/counts/links, sound-map audio/silence/count/link coverage, plus
  release-matrix target/product-gate coverage, plus
  release-copy/platform-plan/release-queue coverage.
- Before source edition changes feed imports or syncs, run
  `python3 verify_editions.py`.
- Before publishing Story/Reel packs, run `python3 verify_post_pack.py` for the
  relevant edition or use `build_post_pack.py`.
- Before packaging, run `python3 package_public_site.py`, which verifies source
  and copied package trees.
- After packaging or transfer, run `python3 verify_package.py` to recompute the
  manifest checksums, reject copied private/generated source lanes, and rerun
  the public-site gate against the package.

## Stop Conditions

Stop and report instead of continuing if:

- A command would require touching outside `incubator/triptych-video-canon/`.
- A task would mutate the Photos library instead of staging exports/proxies.
- A public artifact would expose private local paths or Photos-library tokens.
- Generated media grows substantially without a matching verification or
  regeneration note.
- Generated/local lanes remain Git-visible after `verify_local_lifecycle.py`.
- The work implies choosing the final owner before the artifact proves its shape.
