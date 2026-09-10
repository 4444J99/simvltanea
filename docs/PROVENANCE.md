# Provenance

```text
TripTicks (2017, ETCETER4)
        → Portvs incubator `triptych-video-canon`
        → N-loop paired composition branch
        → SIMVLTANEA canonical repository
```

## Verified commits (organvm/portvs)

| SHA | Role |
| --- | --- |
| `0a76143b4fc02a2e869eb4056dc59bdc9acba24e` | PR #1 incubator checkpoint |
| `48da3da293ecd7604b6c9d3ce19d0bf49a70013d` | PR #3 excavation checkpoint; current `main` |
| `9197a5aff76c2595511b4269d6ae60e46b70f868` | declarative n-loop model |
| `08aee37e96bb2e3b47387825bcb60b9e8fdef0fa` | authored 3–6 portrait/landscape layouts |
| `1009628e58563bb1b20771bfbe69fe573d31adbf` | Artifact 001 through existing renderer |
| `c9fa438847da98cbb6901c032f94ca443f607a21` | latest N-loop branch head used for this extract |

## Verified coordination objects

- Issue #8 — composition contract
- PR #7 — documentation audit (separate)
- PR #9 — implementation draft
- PR #11 — portal / Narcissus ownership correction; pending engine remote was never created

## What moved

The incubator implementation tree from `c9fa438` was copied into this repository.
Generated caches (`work/`, `site/`, `packages/`, `runtime-proof/`) were not treated
as canon. The historical incubator README is stored at
`docs/PORTVS_INCUBATOR_README.md`.

## What was repaired

Error strings that required files to remain inside
`incubator/triptych-video-canon/` now name the SIMVLTANEA repository root.
`artifact-001/baseline/render_triptych.original.py` was left byte-identical to
Portvs.

No Portvs history was rewritten. The incubator copy was not deleted.
