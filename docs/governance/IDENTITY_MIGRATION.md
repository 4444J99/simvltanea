# Functional software identity migration

## Authority and responsibility

The software identity is `independent-loop-compositor`; the artwork title is
SIMVLTANEA. `ace-manifest.json` binds this distinction to GitHub repository id
`1364497735`. Authenticated repository metadata was checked on October 13, 2026:
visibility is public and the current account has push and administration access.
This migration adds no private source locations, media identities, or personal
source relationships. Its empty `source_media` array means no new source records
are published here; existing intake and provenance authorities remain in place.

The software compiles independent loop clocks, authored orientation geometry,
and explicit audio decisions into a browser plan or an FFmpeg render. It also
adapts authenticated external spatial playback generations. It does not become
the owner of the shared playback engine by consuming it.

## Identity boundaries

| Kind | Current authority | Meaning |
| --- | --- | --- |
| System | `audiovisual-composition-system` | Cross-repository coordination |
| Software | `ace-manifest.json` software record | Independent Loop Compositor |
| Capability | `ace-manifest.json` capabilities | A reusable processing responsibility |
| Module | `ace-manifest.json` modules | Existing implementation path and public interfaces |
| Source media | Existing intake and provenance records | Media bytes and literal descriptive identifiers; no inferred artwork title |
| Composition | Existing edition `composition` object or caller-authored model | A specific arrangement of loops, layouts, timing, and audio |
| Artwork | `ace-manifest.json` artwork record | SIMVLTANEA and its stable project id |
| Edition | `editions/registry.json` | Configured realizations; readiness is not publication acceptance |
| Archive | `archive/PROJECT_MANIFEST.md` | Retained provenance and historical names |

The inaugural composition and edition entries in the ACE descriptor are pointers
into the existing registry, not duplicate editable configurations. Other existing
editions remain governed by that registry. Publication status remains unverified;
this change does not grant publication approval or prove source custody.

## New consumer interface

```python
from independent_loop_compositor import Composition, LoopState, Layout, Placement
from independent_loop_compositor.authoring import from_authoring_model
from independent_loop_compositor.browser import compile_plan, build_preview
```

Provide your own `Composition.id`, loop ids, literal source paths, and paired
layouts. Associate the composition with artwork metadata in your own registry.
The compiler does not require an artwork title, a SIMVLTANEA project record,
or an edition slug. The cross-artwork test creates two independent compositions
with different source identifiers through this API and verifies equivalent
legacy/new results without sharing their identities.

```bash
python -m independent_loop_compositor preview --state state.json --output var/site/example
python -m independent_loop_compositor render --state state.json --output var/renders/example.mp4
```

After installation, `independent-loop-compositor` accepts the same subcommands.
Use `preview --help` or `render --help` for the inherited arguments.

## Compatibility and reversible migration

| Existing interface | Functional interface | Migration rule |
| --- | --- | --- |
| `simvltanea.authoring` | `independent_loop_compositor.authoring` | Same exported runtime classes and functions |
| `simvltanea.browser` | `independent_loop_compositor.browser` | Same compilation and preview functions |
| `simvltanea.rendering` | `independent_loop_compositor.rendering` | Same renderer implementation |
| `python -m simvltanea.browser_runtime` | `independent-loop-compositor preview` | Delegate to the existing command |
| `python -m simvltanea.render_triptych` | `independent-loop-compositor render` | Delegate to the existing command |
| Distribution `simvltanea` | Distribution `simvltanea` | Retained for installer compatibility |
| `src/simvltanea/` | `src/simvltanea/` | Retained implementation path, recorded explicitly |

The new package contains only public interface facades. Existing assets, schema
versions, environment variables, layouts, source registrations, edition slugs,
and archive paths remain valid. In particular, `shared_engine_pin.json` and its
accepted release/runtime hashes remain byte-identical. There is one compiler,
one renderer, and one browser implementation; neither namespace copies them.

Consumers can switch back to the existing imports or commands without migrating
stored compositions or media. To roll back this repository change, revert its
commit and restore consumers to the existing API first. No media move or history
rewrite is involved. A later distribution/repository rename must be a separate,
verified migration with its own installer and URL compatibility plan.

## Verification

`tools/verification/test_functional_identity.py` checks public function identity,
source-neutral composition reuse, command argument/exit compatibility, local
manifest references, and the composition/edition pointers. The installed-wheel
consumer exercises both namespaces and old/new render entry points outside the
checkout. Existing structure, naming, profile, feature-boundary, media, and
browser suites retain their responsibility.
