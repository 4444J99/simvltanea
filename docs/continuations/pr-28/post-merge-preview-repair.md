# Post-merge preview repair

The original consumer PR #28 merged at `fc78b41625f20d70e00693fe792d3ede64ee9337`.
Owner PR #3 merged at `e5900ef98fa7a9644af1708e0e6c6cbbcde5b180`, and its
acceptance PR #4 merged at `44d815c978fc9b57526ff9b18165cd5b8d777b5c`.
This change is a successor for findings that remain on the landed consumer,
not a duplicate of the original staging implementation. The six-file owner
pin and its digests remain unchanged.

## Changes

- Atomic publication accepts children of the declared generated storage only,
  rejects tracked paths, and refuses replacement of unrelated directories.
  New generations carry an ownership marker. Legacy previews can be replaced
  only when their complete file/directory inventory and bytes reproduce from
  their portable state. This includes executable files and nested directories;
  loose or modified content remains untouched. The exact runtime shipped by #28
  is recognized by its digest, with narrow allowances for its old receipt format.
  The tracked-file guard runs for checkouts and worktrees and fails closed on
  Git errors; installed workspaces without checkout metadata need no Git binary.
- First publication follows ordinary directory creation permissions and the
  caller's umask. Replacement retains the old preview root's permission bits.
- Installed use resolves the engine relative to the workspace already selected
  by the canonical path/layout resolver, rather than searching site-packages.
- Malformed digest values and invalid UTF-8 provenance fail through the ordinary
  unavailable-engine path. Containment uses paths rather than platform separators.
  `verify()` reloads provenance, hashes the graph, and checks current Git ancestry.
  An ancestry command failure in a full checkout is refused, never mislabeled
  as the documented shallow-history exception.
- Runtime snapshot identity names the verified pin. Poses and their rendered
  time are cached when applied, so pausing or sampling between frames cannot
  manufacture a pose absent from the screen. Track identity survives reordered
  portrait/landscape cell arrays. Positive left/up poses move the source focal
  point in that direction. Sliced panels move through bounded source offsets
  instead of silently bypassing choreography.
  Slice offsets use percentage `left` and `top`, so vertical motion follows the
  panel height on both wide and tall panels rather than CSS margin percentages.

## Verification

The focused run passed 83 tests and 51 subtests, with three owner-binding tests
skipped for the absent checkout. Additional final resolver/staging/render-logic
coverage passed 40 tests (one owner-binding class unavailable). The legacy
replacement/preservation regression passed separately.

An explicit test-only byte fixture was retrieved from the exact owner merge
through authenticated GitHub file access. All six executable digests and owner
provenance match the unchanged production pin. The fixture is injected only in
the test runner: no production resolver or release guard is bypassed or re-pinned.
Local checkout ancestry for this fixture is unmeasured and its receipt says so.
With Chromium 153.0.8010.0 and synthetic H.264 media, all 14 rendered-preview and
owner-binding tests passed, with zero skips. These include visible slice motion,
stable portrait identity, paused snapshot consistency, numeric evaluator identity,
missing-module reporting and per-panel rendered motion.

An isolated installed wheel produced verified portrait and landscape renders.
Structure, feature boundaries, layout, lifecycle, edition presets, example
layouts and JavaScript syntax checks passed. The uncontended broad run passed
361 tests and 370 subtests, with 14 owner-dependent tests skipped; those 14 passed
separately using the verified byte fixture. Hosted CI and package verification
also passed on the first successor head. Review then identified legacy nested
extras, vertical slice positioning and ancestry-error classification; the
corrected-head results are recorded on the successor PR.
The review corrections passed 56 focused tests and 14 subtests, followed by all
15 owner-fixture integration tests, including nested-engine preservation and
actual portrait/wide-panel vertical slice bounds.
Linux directory exchange was exercised; macOS and Windows were not exercised here.

## Acceptance boundary

The owner acceptance receipt and `DEVICE_ACCEPTANCE_RESULTS.json` at
`44d815c978fc9b57526ff9b18165cd5b8d777b5c` record previous Chromium/Apple M5,
SwiftShader and native Safari/Apple GPU checks, including bounded real decoded
frames. Those results belong to that owner head and are not a new measurement of
this consumer change.

Full physical acceptance remains HOLD for the inputs already named there:
mounted archival originals and an independent physical custody disk; the actual
matched fourth-camera and GoPro MAX/FOA material where required; and an unlocked
target phone, a WebXR headset, physical-output capture hardware and the wearer's
comfort observations. Existing private originals and historical evidence are
preserved. This repair does not assert physical acceptance or deployment.
