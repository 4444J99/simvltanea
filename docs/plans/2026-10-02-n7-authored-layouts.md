# Plan — N=7 Authored Layouts (2026-10-02)

> Doctrine: Verify → Heal → Expand → Evolve. Lane: `lane/evolve`, which requires a
> spec before code (`BRANCHES.md:16`). This document is that spec: it fixes the design
> decision and the acceptance gate. It authorizes no implementation by itself.

Issue: [#3 — N=7 authored layouts, experimental family parked](https://github.com/4444J99/simvltanea/issues/3)

## Decision

The authored N=7 portrait/landscape geometry is the `SEVEN` rect set currently held at
`core/make_runtime_fixture.py:26-35`, promoted verbatim into `_AUTHORED_DEFAULT[7]` in
`core/artifact001_layouts.py`. Once promoted, `build_artifact001(7)` stops raising and the
count joins the supported 2–6 family.

| Orientation | Rects `[x, y, w, h]` |
| --- | --- |
| Portrait | `.04 .03 .92 .30` · `.04 .37 .44 .18` · `.52 .37 .44 .18` · `.04 .58 .28 .17` · `.36 .58 .28 .17` · `.68 .58 .28 .17` · `.04 .79 .92 .18` |
| Landscape | `.03 .05 .38 .90` · `.45 .05 .24 .26` · `.73 .05 .24 .26` · `.45 .36 .24 .28` · `.73 .36 .24 .28` · `.45 .69 .24 .26` · `.73 .69 .24 .26` |

## Why this geometry is a family continuation, not a rival design

1. **Deliberately specified, not grid-generated.** Every rect was chosen individually —
   the set carries uneven columns, unequal heights and a two-tier hierarchy
   (`archive/chatgpt/handoffs/HNDF-003_…:20`, `HNDF-001_…:111`). A generic grid generator
   would not produce this arrangement.

2. **The loop clocks already match the authored formula.** `build_artifact001` derives
   `rate = 1 + i*0.07` and `offset = i*0.31` (`core/artifact001_layouts.py:71`). At `i=6`
   that is `71/50` and `93/50` — byte-for-byte the values the experimental
   `runtime-proof/state-7.json` already carries for `loop-7`. The compiler rounds authored
   floats to nine decimals before exact rational conversion
   (`core/composition.py:655-656`), which is what makes them line up. The experimental count
   was never a different design; it was the same design that could not be reached through
   `build_artifact001` because `AUTHORED` had no `7` key.

3. **Focal points already match.** The fixture emits `focal=['1/2','1/2']`;
   `Placement.focal_x/focal_y` default to `0.5` (`core/composition_model.py:142-143`).

4. **It is already executed and evidenced.** `runtime-proof/state-7.json`,
   `runtime-proof/preview-7/`, `tests/test_browser_runtime.py` N=7 continuity,
   `tests/test_browser_continuity.py` N=7 continuity, the `counts-6-7` group in
   `tools/run_review_proof.py`, and two archived renders — `MEDA-002` (portrait) and
   `MEDA-003` (landscape) in `archive/chatgpt/media/`.

5. **It already passes this repository's own layout guard.** The bounds and non-overlap
   rules in `tools/verify_layouts.py` were re-evaluated against both orientations: all
   seven portrait rects and all seven landscape rects are in-bounds and mutually
   non-overlapping. No rect required adjustment.

## Non-claims

These bound what the promotion asserts. They must survive into the code, the tests and
the documentation.

- These are **synthetic engineering geometries, not artist-approved designs** — the same
  status the 2–6 pairs already carry (`core/artifact001_layouts.py:2-5`, `README.md:71-72`).
- They are **not recovered historical art**. Nothing here reconstructs TripTicks, First
  Circle, Floating Points or Up the Hill Backwards.
- `contain` fit is a **labeled-fixture trait**, not part of the authored geometry. The
  authored pair keeps `cover`; `core/make_runtime_fixture.py` relabels fit per study, as it
  already does for 2–6.
- Promotion establishes that an authored pair exists and is exercised. It is **not** a
  product ceiling claim and **not** a claim about resource capacity.

## Known serialization change

`from_authoring_model` canonicalizes rationals through `str(Fraction(...))`, so authored
floats re-serialize in lowest terms. Values are unchanged; text is not:

| Fixture literal | Canonical form |
| --- | --- |
| `92/100` | `23/25` |
| `38/100` | `19/50` |
| `28/100` | `7/25` |

The generated `state-7.json` layout name also changes from `experimental-seven-portrait`
to `artifact001-7-portrait-labeled-contain-study`. `runtime-proof/` is gitignored and
regenerable, but the N=7 render and still hashes in
`runtime-proof/evidence/render-family.json` are re-baselined by the regeneration.

## Implementation shape

1. `core/artifact001_layouts.py` — add `7:` to `_AUTHORED_DEFAULT`. `build_artifact001`
   and the `_load_authored` JSON-override path need no change; both become count-agnostic
   over the table.
2. `core/make_runtime_fixture.py` — delete `SEVEN` and the `else:` branch, so counts 2–7
   share one derivation path. Collapse is behaviour-preserving because the loop clocks and
   focal points already agree (see above).
3. `core/make_artifact_001.py` — extend the source bank and the count loop to 7 so the
   1080×1920 / 1920×1080 reference family actually produces the new cell.
4. Tests — extend the acceptance set to `{2,3,4,5,6,7}` and **move the explicit-failure
   assertion to N=8**. The "a missing pair fails loudly" behaviour is canon
   (`HNDF-001_…:457`, `RCPT-003_…:257-258`); retiring it with the count would quietly
   delete the guard. `build_artifact001(8)` must still raise
   `no reviewed engineering layout pair`.
5. Documentation — the support matrix gains a 7 row and the standing "7 is rejected"
   statements in `README.md` and `CONTRIBUTING.md` are corrected in the same change, so no
   release point of `main` ever states a falsehood.

## Acceptance gate

- `build_artifact001(7)` returns a valid paired composition: 7 loops, both orientations,
  one placement per loop per layout.
- `build_artifact001(8)` still raises `ValueError` matching `no reviewed engineering
  layout pair`.
- Segment compilation succeeds for N=7 in both orientations with 7 panels per segment.
- `tools/verify_layouts.py --examples` reports `layouts ok`.
- `python3 core/make_runtime_fixture.py && python3 tools/render_runtime_family.py &&
  python3 tools/verify_runtime_renders.py` regenerates cleanly; `preview-7` reproduces
  `labeled-7-{portrait,landscape}` byte-identically (`tools/render_runtime_family.py:63-66`)
  — the strongest available proof that collapsing the fixture branch changed no rendered
  behaviour.
- `python3 core/make_artifact_001.py` produces the extended reference family and ledger.
- Full suite green, plus `verify_local_lifecycle.py`, `verify_editions.py` and
  `edition_status.py`.

## Explicitly out of scope

`archive/PROJECT_MANIFEST.md:305-310` — the MEDA-003 entry (the N=7 landscape archive
proof) still carries a machine-local `file:///Users/4jp/…` link and describes the file as
H.264/**AAC**, contradicting its actual silent stream. PR #11 repaired only the MEDA-002
entry. It is the same defect class and belongs in a separate `lane/heal` branch; it is not
addressed by this plan.

`tests/test_archive_media_provenance.py` is also untouched by design. It pins the
`#experimental-7-loop` tag and the "experimental $N=7$" wording in the manifest, which
describe the September 2026 experiment accurately. Rewriting them would rewrite provenance.