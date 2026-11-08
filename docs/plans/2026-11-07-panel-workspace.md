# Spatial panels in the editing workspace

## Correction

The direct editing workspace omitted the original compositor's spatial panels.
Its timeline controlled overlapping full-frame clips. The user asked where the
panel elements had gone, then explicitly requested that the omission be fixed.
This change restores panel geometry within the existing editor and republishes
the same Site. It does not replace the original Studio or authorize a merge.

## Composition model

- A composition owns a layout family, visible panel count, orientation, and
  framing choice. New projects open with three empty strips panels.
- Geometry comes from the existing compiler and generated layout bundle:
  strips offers 1–12 panels and authored layouts offer 2–7. Empty panels are
  allowed independently of the existing eight-clip playback limit.
- Each clip retains a stable numeric panel assignment, shared launch time,
  independent picture/sound clocks, envelopes, filters, and repeat decisions.
- Clips assigned to one panel blend in their existing layer order inside that
  panel. The first visible picture in every panel has an independent base.
  Effects are clipped to panel bounds, including the CSS filter fallback.
- Layout, count, framing, and assignment edits redraw without recreating media
  elements, audio graphs, or playback clocks. Lowering the visible panel count
  parks the extra pictures; their assignments and sound remain intact.
- The preview exposes direct panel selection. The timeline and inspector show
  panel membership, assignment, and clip succession within a panel.
- Project save/restore retains layout and panel assignments, including pending
  local files. Older projects without layout data open as one full-frame panel.

## Framing

Fill and Fit are explicit choices. Original slice uses the existing strips
framing definition. Plain center-cover is not described as the original slice.
Portrait strips are horizontal rows; landscape strips are vertical columns.
Authored orientation pairs preserve the same panel identities.

## Verification boundary

Acceptance covers canonical geometry, per-panel compositing, live clock and
sound-tail continuity, parked-assignment restoration, settings round trips,
direct UI selection and editing, responsive layout, and the published Site.
Existing audio/filter and timeline regressions remain in the focused gate.
Physical iPhone acceptance and the separate Studio WebKit investigation remain
outside this change. Verification results are recorded after the checks run.

## Completed verification

- The final focused gate passed **106 tests in 19.713 seconds**: model, engine,
  actual audio signals and rendered pixels, shell, canonical panel parity,
  Lab integration, Studio staging, and public-library staging.
- Canonical parity covers 108 family/count/orientation/framing combinations,
  using the generated Python bundle as the oracle.
- A native H.264/AAC continuity test observed no play, pause, or seeking events
  from panel reassignment, count shrink, or orientation change. Both native
  clocks advanced; media and graph identities stayed unchanged; audio remained
  nonzero while the picture was parked and decoded picture returned on expansion.
- The managed browser exercised recorded public footage in separate panels,
  direct selection, Authored/Portrait changes during playback, duplication,
  Queue after, reassignment, preset preservation, and count shrink/expansion.
  A 12-second picture with a 48-second sound region was observed at 30.81 seconds
  as a sound tail. Save/reload/Open restored all three clip identities and the
  selected third panel.
- A 390-pixel iframe check confirmed reachable layout controls and direct
  portrait-panel selection, with document width and scroll width both 390.
  This is responsive-layout evidence, not physical-phone playback acceptance.
- Independent review found and corrected a selected-panel restoration issue
  caused by asynchronous public-media admission. No unresolved core blocker
  remained after the correction.
- JavaScript syntax, whitespace, the generated plan index, and the final static
  asset allowlist passed. The temporary responsive-layout harness was removed
  before packaging.

The original Studio's blanket ban on remote URL strings in staging tests was
updated for the already-authorized optional public-media catalog: only the
Wikimedia download/provenance and Creative Commons rights-link hosts are allowed
in the Lab shell/UI. Executable dependencies remain relative, and private-path
checks remain in place.
