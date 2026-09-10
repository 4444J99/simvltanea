# SIMVLTANEA

Configurable simultaneous video-loop compositions.

Historical origin: **TripTicks** (ETCETER4, 17 August 2017).
Incubation home: `organvm/portvs` / `incubator/triptych-video-canon/`.
Canonical repository: `4444J99/simvltanea`.

This is an artwork/system in the Persona / Visual Form Canon. It is not NARCISSUS,
not Portvs, and not a generic video wall.

## What the work is

N independently authored video-loop instances occupy one authored spatial
composition at the same time. Adding a panel adds a loop. Orientation changes
choose a different authored layout and must not reset, duplicate, or substitute
those loops.

TripTicks is the three-panel historical instantiation. A triptych is one
configuration. The project identity is the simultaneous field, not the number
three.

## Historical origin

| Field | Recovered fact | Status |
| --- | --- | --- |
| Title | TripTicks | verified on YouTube |
| Channel | ETCETER4 | verified |
| Upload | 2017-08-17 18:52:55 GMT | verified |
| URL | https://www.youtube.com/watch?v=PHP7mOJT60I | verified |
| Description | empty | verified |
| Original source MOV / archive bytes | not retrieved | missing |
| Family / nature / friends category order | prior note only | historical claim |

Do not treat the YouTube encode as the complete present system. It specifies lineage.

## Invariant

```text
N independent loops
+ authored portrait and landscape layouts
+ independent local clocks
+ simultaneous temporal coexistence
+ presentation-only orientation changes
+ no filler, no implicit duplication
```

Variable: panel count, source per loop, geometry, orientation, ordering,
dimensions, offsets, hold/reroll/swap/move events.

What keeps this from being a generic video wall is independent loop identity
tied to an authored relational composition, originally from a personal archive,
not a tiled repeat of one feed.

## Supported configurations

Authored engineering pairs currently exist for **3, 4, 5, and 6** loops:

| N | Portrait | Landscape |
| --- | --- | --- |
| 3 | authored | authored |
| 4 | authored | authored |
| 5 | authored | authored |
| 6 | authored | authored |

Seven-loop exports exist only as a named experimental family in the Portvs
proof receipts. `artifact001_layouts.py` still rejects 7 as an unsupported
reviewed pair. Do not advertise 7 as a supported configuration.

Layouts live in `artifact001_layouts.py`. They are synthetic engineering
geometries, not artist-approved designs.

## Rendering model

- Schema: `visual-form-composition/v1`
- Authoring model: `composition_model.py`
- Compiler / state: `composition.py`
- FFmpeg renderer: `render_triptych.py` (legacy three-panel path plus compiled N-loop placements)
- Browser preview: `browser_runtime.py` / `browser_runtime.js` (bounded, silent)

New schema-1 loop exports are silent. Legacy `none` / `panel` / `mix` audio
routing is preserved on the historical three-panel path.

## Verify

```bash
# Run full suite (120 tests across unit, ffmpeg render, browser runtime, and continuity)
python3 -m unittest discover -s tests

# Or run with pytest
pytest

# Verify worktree cleanliness
python3 verify_local_lifecycle.py
```

Generate the synthetic Artifact 001 family:

```bash
python3 make_artifact_001.py
```

## Relationship

```text
PERSONA / VISUAL FORM CANON
        │
        ├── NARCISSUS          (separate work; do not merge)
        ├── SIMVLTANEA         (this repository)
        ├── Floating Points    (historical; original bytes unresolved)
        ├── Up the Hill Backwards (historical; original bytes unresolved)
        └── other visual works
```

Portvs is the portal / previous incubator, not the artwork.
ORGANVM supplies the ideal-form → instantiation → observation loop.
TripTicks is one historical instantiation. The N-loop renderer is a later
abstraction of the same grammar.

## Naming

See `docs/NAMING.md`. TripTicks remains the historical title.
Triptych remains a configuration word.
`organvm/visual-composition-engine` was a provisioning-pending extract name
from Portvs PR #11 and was never created.

## Provenance

Recovered from `organvm/portvs` branch
`work/n-loop-paired-compositions-2026-09-05` at
`c9fa438847da98cbb6901c032f94ca443f607a21`.

The Portvs incubator copy is not deleted.

## Archive & Project Manifest

Historical ChatGPT transcripts, execution handoffs, receipts, telemetry traces, bundles, and media proofs are cataloged in the master annotated bibliography:

- **[Project Manifest & Annotated Bibliography](file:///Users/4jp/Workspace/4444J99/simvltanea/archive/PROJECT_MANIFEST.md)** (`archive/PROJECT_MANIFEST.md`)
- **[Classified Archive Directory](file:///Users/4jp/Workspace/4444J99/simvltanea/archive/chatgpt/)** (`archive/chatgpt/`)

