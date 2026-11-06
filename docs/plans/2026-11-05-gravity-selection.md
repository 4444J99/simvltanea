# Plan — Gravity selection for the generative composer (2026-11-05)

> Lane: `feat/gravity-selection`. Brings the scout's measured prototype into the repository
> without changing the engine vocabulary, then generalises it into play modes. Design references:
> [GRAVITY](../architecture/GRAVITY.md) (the relation rule) and
> [PLAY_MODES](../architecture/PLAY_MODES.md) (everything else).

## Decision

The generative composer gets "stickiness or gravity" between simultaneous clips: not random,
always changing, with related clips tending to appear together. Strength is a parameter, with
three presets (`drift`, `sticky`, `magnetic`). The default is `sticky`.

Gravity is one of several play modes. How a composition plays is configuration: four dials
(order, path, relation, timing), named presets that are data, and a command that takes a mode, a
config file and single overrides. Random, chronological, oldest meets newest, a round, opposites
and city against nature are presets of the same engine.

## Scope

- `authoring/gravity_affinity.py`: integer affinity from weighted components, with graceful degradation.
- `authoring/play_*.py`: the play-modes engine (configuration, presets, order, paths, pool
  eligibility, seeded scheduler, state encoding) that emits a schema-valid state using the
  existing `reroll` and `swap` events. No `cue` event and no `ENGINE_VERSION` change.
- `authoring/gravity_scheduler.py`: `schedule_gravity` kept as a thin wrapper over the engine.
- Tag schema v2: `max_sharing_sensitivity` (default `moderate`), with unknown ratings following
  `untagged_policy`, on top of the existing safety, privacy, minor and untagged exclusions.
- `tools/media/play_state.py`: reads private tag records and export receipts, writes the state
  and a `.play.json` record only under `var/work/` or outside the checkout, and never carries
  captions or personal text. `tools/media/index_clips.py` writes capture times;
  `tools/media/play_guard.py` guards roots and outputs; `tools/media/play_docs.py` keeps the
  generated tables in PLAY_MODES equal to the code.
- Tests beside the source using a synthetic pool, and the architecture record.

## Acceptance gate

Measured by the scout and required of this implementation:

1. At the default setting, same-theme pairs on screen are about 2 times the zero-gravity
   baseline at N=5 (the scout's figure, taken with scripts outside this repository; the repository's own
   measurement, which `python3 -m tools.media.measure_gravity --check` keeps equal to GRAVITY.md, is about 2.5).
2. The pool is still covered (about .996 at N=5, the scout's figure; the repository's own measurement, kept equal to GRAVITY.md by `measure_gravity --check`, is 1.000 with gravity and .994 for the baseline).
3. No immediate repeats and a cooldown of at least 30 s.
4. Byte-identical output for identical inputs across processes with different `PYTHONHASHSEED`.
5. Excluded clips, including `sharing_sensitivity` `high`, never reach a bank, source list or event.
6. Every state the command writes passes `validate_state`, round-trips, and compiles with `compile_plan` to the schedule. The generator counts `compile_plan`'s spans exactly and refuses a state over its limit of 1,024 spans per loop before writing anything; the offline renderer has a separate, stricter whole-state limit of 1,024 segments (a warning, or a refusal with `limits.refuse_unrenderable`).

## Verification

```bash
ls-lint --config config/lint/ls-lint.yml
python3 -m tools.verification.sync_layout
python3 -m tools.verification.verify_repository_structure
python3 -m tools.verification.verify_feature_boundaries
python3 -m tools.verification.sync_plan_index
python3 -m pytest -q -p no:cacheprovider src/simvltanea/authoring tools/media tools/verification
python3 -m tools.verification.verify_local_lifecycle
python3 -m tools.media.play_docs
python3 -m tools.media.measure_gravity --check
```

## Re-measurement against the repository implementation

The scout's measurement driver was re-run against the repository code on the scout's own
synthetic pool (120 clips, 600 s, 24 fps, 10 seeds per setting, N=2 to 7). Every row of the
scout's table was reproduced, including the same-theme ratio at N=5 (1.98 against 1.99). That
was before the fix to `relation.independence` (the thread now relates a pick to the clip being replaced,
not the clip two changes back); GRAVITY.md holds the numbers measured after it, which differ.
One state digest (`04b1d8c3…`) was identical to the scout's across processes with
`PYTHONHASHSEED` 0, 1 and 12345 at that time; the independence fix changed the digest, and the
golden digests in `test_play_modes.py` were re-pinned. Twenty seeds gave 20 distinct states.

## Finishing the play-modes lane (2026-11-05)

Three items remained after the independent review. Nothing here changes a default or the state
schema.

### Speed (review item M3)

A synthetic 6,500-clip pool, N=7, 600 s, 24 fps, seed 1 and the default `sticky` mode spent almost
all its time in about 1.17 million uncached affinity calls. The affinity model now prepares each
clip once per pool and memoises the categorical components per pair of tag combinations; the
plain per-pair functions stay as the reference. Output is unchanged: the state digest was
identical before and after on pools of 300 and 2,000 clips (seeds 1 to 3, modes `sticky`,
`magnetic`, `opposites`, plus `city_vs_nature` and `near_vs_far`), on all 16 presets at 120 and
900 clips, and the full command output of the 6,500-clip run (state and `.play.json`) was
byte-identical. The component values are still quantised one by one and combined in integers.

The figures below were taken when the affinity fast path was added, before untagged clips became
excluded by default; the pool, the eligible count and the digest of that run are not the ones the
command produces now. Current measurements are in `docs/architecture/PLAY_MODES.md` ("Cost and
limits").

Measured with `python3 -m tools.media.play_state --root <synthetic root of 6,500 clips under
var/work/> --out <path under var/work/> --force --n 7 --duration 600 --fps 24 --seed 1`, on a
shared 10-core machine whose load average was 12 to 15:

| | Before | After |
| --- | --- | --- |
| Wall time | 28.4 s | 19.1 s |
| User CPU time | 21.9 s | 14.3 s |
| Peak memory (resident) | 136 MB | 140 MB |

Interleaved runs of the scheduler alone (`schedule_play`) gave 21 to 33 s before and 16 to 24 s
after. The review's 58.5 s baseline did not reproduce on a quieter moment: the same workload
(1,168,320 uncached calls) took 21 to 25 s here, and 80 s under a profiler, so the review figure
probably came from a loaded machine. After the change the run is under the 30 s target in every
measurement taken, so step two (lowering `limits.max_candidates`) was not applied and the default
stays 400. For the record, a cap of 200 gave 12.4 s against 16.4 s in one run and changes the
output, so it buys little.

Guard: `FastPathEquivalenceTests` in `test_gravity_affinity.py` (every pair of a fixed pool
through the prepared, cached and reference paths, for five weight sets, untagged and malformed
records; a memo that keeps clearing; palette and overlap helpers bit for bit; a whole schedule
with the same digest through either path). Mutating the palette arithmetic or the overlap
minimum makes it fail.

### What can read a play state

Python's `compile_plan` accepts a play state, and the offline renderer renders it within its
1,024-segment limit. The command-line previews (`python -m independent_loop_compositor preview` and
`python -m simvltanea.browser.browser_runtime`, each with `--state` and an `--output` under `var/`) also
read a play state, because they run `compile_plan`; they need `.mp4` H.264 sources and do not need the sibling
shared-engine checkout (see PLAY_MODES.md for the working commands, including the offline render command that needs
an explicit `--output`). The in-browser client compiler
(`src/simvltanea/browser/browser.compiler.js` on the main branch) refuses any state with `events` and any
multi-source bank with a `CompilerError` ("outside the browser compiler subset"). Almost every play state has one
or both, so the in-browser web studio cannot preview it; the exception is a state with every loop pinned
(`path.pins`), which has neither and compiles. Closing that gap is a separate lane (the `cue` event, or compiler support in the
browser client); this lane does not touch the compiler.

### Renderer limit (L8)

The offline renderer allows 1,024 segments. A 10-minute N=7 state with default settings needs
about 2,500 (2,455 on 120 clips, 2,536 on 1,000), so it does not render offline. `compile_plan`
has its own, looser limit of 1,024 spans per loop, which that state meets and
which the generator now enforces (a state over it is refused, not written). `play_encode.render_segment_bound` and `render_segment_estimate`
compute, from settings alone, a guaranteed bound and an expected count, and
[PLAY_MODES](../architecture/PLAY_MODES.md) tabulates the longest durations per loop count.
Only a 12 s, N=3 state (20 segments) was rendered with ffmpeg; the 600 s N=7 state from the same
synthetic clips was refused by the renderer's guard. Guard: `test_play_segments.py` (hand-computed
case; bound at least the exact count on 66 generated states; swaps; estimate within 15 percent;
refusal) and `tools/media/test_play_docs.py` (the documented durations stay within the limit).

### Documentation

`docs/architecture/PLAY_MODES.md` is new: the four dials, every parameter generated from
`describe_parameters()`, the preset table generated from the preset table, the owner's examples
with the test that shows each, guarantees, privacy rules, cost and the renderer limit, the two
files `--out` writes (the state and the `.play.json` record), and the pending decisions.
`tools/media/test_play_docs.py` fails when a generated table drifts from the code, when the page
cites a test that does not exist, or when an owner example names an unknown preset.
`GRAVITY.md` now keeps to the relation rule and links to it.

### Independent review (fixes applied)

An independent adversarial review of this lane was applied. Fail-closed privacy rules (a
malformed or missing flag, a refused record keyed on an error code, a clip with no verdict),
an exclude-id check that is case-insensitive, counted and loud, content exclusion that follows
the receipt of an excluded clip that has no tag record, symlinked clip directories refused,
`index_clips` writing only into a real `analysis/index/`, strict hex colours and palette shares
(identical on the fast and reference affinity paths), `converge` splitting at the true middle
for any loop count, an exact `compile_plan` span count that refuses a state before writing it,
JavaScript-safe integer seeds, an opt-in `--verify-media`, and documentation of the settings
that have no effect and of what the sidecar really holds (the clip ids named in the
configuration). The details are in [PLAY_MODES](../architecture/PLAY_MODES.md); the state of
`oldest_meets_newest` and `newest_meets_oldest` changes for an odd loop count, and a pool that
contains never-tagged clips yields different states than before.

## Open owner decisions

Deliberately left open and recorded with their measurements in
[PLAY_MODES](../architecture/PLAY_MODES.md) and [GRAVITY](../architecture/GRAVITY.md). None has
been decided or changed:

- the `cue` event and whether it changes `ENGINE_VERSION` (recommendation: add it; it cuts a
  10-minute N=7 state from about 28,000 events (28,061 measured with the current code; 27,822 before the
  independence fix) to about 500);
- the default preset (`sticky` today);
- `exclusion.untagged_policy`, which defaults to `allow` (recommendation: `exclude` for anything
  shared). After the review, a clip with no safety verdict at all is excluded under either value
  while `require_safety_clear` is on (a deliberate tightening); the policy now governs only what
  is unknown about a clip that carries a clear verdict;
- hold times;
- the component weights;
- whether gravity-driven swaps are wanted.

## Out of scope

- A JavaScript port for the web studio and any browser feature extractor.
- Changes to `composition.py`, `composition_model.py`, `ENGINE_VERSION` or the browser runtime.
- The tag and export commands themselves, which live in a separate lane.
