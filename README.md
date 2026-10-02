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

Authored engineering pairs currently exist for **2 through 7** loops:

| N | Portrait | Landscape |
| --- | --- | --- |
| 2 | authored | authored |
| 3 | authored | authored |
| 4 | authored | authored |
| 5 | authored | authored |
| 6 | authored | authored |
| 7 | authored | authored |

The seven-loop pair promotes the previously experimental Portvs geometry into
the reviewed engineering family. Counts without an authored pair still fail
explicitly; eight loops are currently unsupported.

Layouts live in [`src/simvltanea/authoring/artifact001_layouts.py`](src/simvltanea/authoring/artifact001_layouts.py). They are synthetic engineering
geometries, not artist-approved designs.

## Repository Layout

```text
SIMVLTANEA/
├── .github/      # CI, templates, security, contributions, and ownership
├── config/lint/  # Naming and Markdown lint policy
├── src/simvltanea/ # Authoring, browser, rendering, and generator subpackages
├── tools/        # Edition, media, publishing, preservation, and verification commands
├── tests/        # Browser, render, model, edition, and governance suites
├── editions/     # Production edition registry
├── examples/     # Safe authoring templates
├── fixtures/     # Tracked regression inputs
├── evidence/     # Reviewed proof ledgers and frames
├── docs/         # Architecture, authoring, governance, provenance, and plans
├── archive/      # Retained ChatGPT and incubation records
├── var/          # Ignored generated and private local outputs
└── pyproject.toml # Packaging, verification dependencies, and pytest settings
```

## Rendering Model

- Schema: silent `visual-form-composition/v1`; opt-in audio `visual-form-composition/v1.1`
- Authoring model: [`src/simvltanea/authoring/composition_model.py`](src/simvltanea/authoring/composition_model.py)
- Compiler / state: [`src/simvltanea/authoring/composition.py`](src/simvltanea/authoring/composition.py)
- FFmpeg renderer: [`src/simvltanea/rendering/render_triptych.py`](src/simvltanea/rendering/render_triptych.py)
- Browser preview: [`src/simvltanea/browser/browser_runtime.py`](src/simvltanea/browser/browser_runtime.py) / [`src/simvltanea/browser/browser_runtime.js`](src/simvltanea/browser/browser_runtime.js)

Schema-1 loop exports remain silent. Explicit v1.1 states support a synchronized
soundtrack or spatial loop mix. Legacy `none` / `panel` / `mix` audio routing is
preserved on the historical three-panel path. See [Audio architecture](docs/architecture/AUDIO_ARCHITECTURE.md)
for the version contract, synthetic examples, and verification boundaries.

## Verify

Physical locations and placement policy use a [configurable layout](docs/governance/LAYOUT.md).
Authoring templates refer to logical paths such as `@samples/inaugural`.

CI also enforces [file and directory naming](docs/governance/NAMING.md),
[repository structure](docs/governance/STRUCTURE.md), and added or edited Markdown,
including MD041 titles and MD047 final newlines. See
[Contributing](.github/CONTRIBUTING.md#verify-before-pr) for pinned tools and local
governance commands.

```bash
# Run the full unit, media, browser, provenance, and governance suite
python3 -m unittest discover -s tests

# Or run with pytest
pytest

# Verify worktree cleanliness
python3 -m tools.verification.verify_local_lifecycle
```

Generate the synthetic Artifact 001 family:

```bash
PYTHONPATH=src python3 -m simvltanea.make_artifact_001
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

See `docs/governance/NAMING.md`. TripTicks remains the historical title.
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

- **[Project Manifest & Annotated Bibliography](archive/PROJECT_MANIFEST.md)** (`archive/PROJECT_MANIFEST.md`)
- **[Classified Archive Directory](archive/chatgpt)** (`archive/chatgpt/`)
