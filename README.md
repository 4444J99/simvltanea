# Independent Loop Compositor

Reusable software for independently clocked simultaneous audiovisual compositions.
It compiles authored loop states and orientation layouts, stages browser previews,
and renders audiovisual exports through the existing implementation.

| Identity | Authority |
| --- | --- |
| Software | `independent-loop-compositor` |
| New Python API | `independent_loop_compositor` |
| Compatibility distribution and implementation namespace | `simvltanea` |
| Repository | `4444J99/simvltanea`, stable GitHub id `1364497735` |
| Artwork | **SIMVLTANEA**, recorded in `ace-manifest.json` |
| Historical instantiation | **TripTicks** (ETCETER4, 17 August 2017) |

[ACE identity contract](ace-manifest.json) separates software, capabilities,
modules, compositions, artwork, editions, source records, and archives.
[Migration and compatibility](docs/governance/IDENTITY_MIGRATION.md) explain the
retained implementation paths and how another artwork uses the same software.

```bash
python -m independent_loop_compositor preview --help
python -m independent_loop_compositor render --help
# After installation, the equivalent command is independent-loop-compositor.
```

On Windows or macOS, see [Windows and macOS](docs/authoring/WINDOWS_AND_MAC.md) for FFmpeg setup, PowerShell commands and what is macOS-only.

## Processing responsibility

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

The software preserves independent loop identity and authored relational geometry.
Source identifiers, composition identities, and artwork titles are caller data.

## Supported configurations

Two layout families exist. **Strips** (default) are computed full-bleed partitions
for any count from 1 through 12. **Authored** engineering pairs exist for 2 through
7. Each family places exactly one cell per independent loop. A count outside the
selected family's range fails explicitly and is never filled, duplicated or moved
to the other family: `build_artifact001(8)` still raises, and strips at 13 raise.

| N | Family | Portrait | Landscape |
| --- | --- | --- | --- |
| 1 | strips | one full-canvas strip | one full-canvas strip |
| 2 to 7 | strips (default) | rows | columns |
| 2 to 7 | authored | authored | authored |
| 8 to 12 | strips | rows | columns |
| 13 or more | none | refused | refused |

Every cell is a distinct loop (no filler), sources are never reused (no implicit
duplication), and no family substitutes for another. N=1 is a field of one loop,
by the owner's explicit choice.

Strips touch edge to edge with no gutter or margin. Zoom is tied to N through
the state-wide slice, `zoom(N) = 8 / N^(3/5)` (8× at 1, 3.05× at 5, 1.80× at 12).
Strips and the zoom curve are engineering presets matched to the owner's sketch,
not artist-approved designs. See [Layout presets](docs/authoring/LAYOUT_PRESETS.md)
and [`layout_presets.py`](src/simvltanea/authoring/layout_presets.py).

The seven-loop authored pair promotes the previously experimental Portvs
geometry into the reviewed engineering family. Authored layouts live in
[`src/simvltanea/authoring/artifact001_layouts.py`](src/simvltanea/authoring/artifact001_layouts.py).
They are synthetic engineering geometries, not artist-approved designs.

Capacity is measured on one desktop only (Apple M5, headless Chrome 156, synthetic
540×720 clips): twelve strips dropped 4.6–8.9% of frames. No claim is made about
phones, Safari/WebKit or real footage.

## Repository Layout

```text
independent-loop-compositor/
├── ace-manifest.json # Typed software, artwork, edition, and archive identities
├── .github/      # CI, templates, security, contributions, and ownership
├── config/lint/  # Naming and Markdown lint policy
├── src/independent_loop_compositor/ # Functional public API and commands
├── src/simvltanea/ # Existing implementation and compatibility imports
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
- Browser preview: [`src/simvltanea/browser/browser_runtime.py`](src/simvltanea/browser/browser_runtime.py) / [`src/simvltanea/browser/browser.runtime.js`](src/simvltanea/browser/browser.runtime.js)
- Release seal: `build_simvltanea_release_seal` (Wave 5) produces a SHA-256 digested seal covering spatial amalgamation manifest and custody parity for release readiness.

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

## Artwork lineage

```text
PERSONA / VISUAL FORM CANON
        │
        ├── NARCISSUS          (separate work; do not merge)
        ├── SIMVLTANEA         (an artwork using this software)
        ├── Floating Points    (historical; original bytes unresolved)
        ├── Up the Hill Backwards (historical; original bytes unresolved)
        └── other visual works
```

Portvs is the portal / previous incubator, not the artwork.
ORGANVM supplies the ideal-form → instantiation → observation loop.
TripTicks is one historical instantiation. The N-loop renderer is reusable
software; independent works supply their own compositions and source records.

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
