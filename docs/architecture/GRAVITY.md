# Gravity — related clips tend to appear together

Gravity is the parameterised "stickiness" between simultaneous loops. It is not random
and not fixed: each loop keeps changing on its own clock, and at every change the
incoming clip is drawn with odds weighted by how related it is to what is already on
screen. Strength is a dial, from drifting to magnetic. The same seed and inputs always
produce the same composition.

Gravity is one dial of the play-modes engine, the **relation** between simultaneous loops.
[PLAY_MODES](PLAY_MODES.md) describes the other three dials (order, path, timing), every
parameter, the presets, the guarantees, the privacy rules, the cost of the encoding and the
renderer limit. This page keeps to the relation rule: how related two clips are, and how that
changes what is drawn. Gravity chooses sources only. It never edits layouts, rates, offsets or
orientation behaviour, so the invariant in [CANON](CANON.md) and the README still holds: N
independent loops, presentation-only orientation changes, no filler and no implicit duplication.

| Piece | Location |
| --- | --- |
| Affinity between two clips | `src/simvltanea/authoring/gravity_affinity.py` |
| Scheduler that applies the relation rule | `src/simvltanea/authoring/play_engine.py` |
| Earlier entry point, kept as a thin wrapper | `src/simvltanea/authoring/gravity_scheduler.py` |
| Command that builds a state from private tag records | `tools/media/play_state.py` (see [PLAY_MODES](PLAY_MODES.md)) |
| Tests (synthetic pool only) | `test_gravity_affinity.py`, `test_gravity_scheduler.py`, `test_gravity_pool.py`, `test_play_modes.py` beside the source |

`schedule_gravity`, `GravityParams`, `GRAVITY_PRESETS`, `GravityError`, `eligible_pool`,
`build_affinity_model` and related types are exported from `simvltanea.authoring`.
`schedule_gravity` maps its parameters onto a play-mode configuration with the `random` path
shape and calls `schedule_play`. With the `sticky` values it is deterministic and gives the same state as the
score-everything path **while the eligible pool has at most `limits.max_candidates` clips (400 by default)**. The
earlier code scored every free clip at every change; the engine scores at most `limits.max_candidates` of them and
draws a seeded sample when more are free. The eligible pool bounds every free pool, so a pool of at most 400 can never
reach the limit. Above that size the states differ from the score-everything state. `--set limits.max_candidates=5000`
(the maximum) restores score-everything (slower) only while the eligible pool has at most 5,000 clips; a larger pool,
such as the 5,253-eligible pool measured in [PLAY_MODES](PLAY_MODES.md) "Cost and limits", is still sampled and cannot
be scored in full.

The output of the earlier, pre-play-mode scheduler is **no longer reproduced**. That held until the `relation.independence`
fix (a loop's own thread is the clip it is showing, not the clip two changes back), which changed every
gravity-scored pick on purpose; the exclusion rules had already been tightened before it. The digests pinned in
`test_play_modes.py` were re-pinned to the current output after each change, so
`test_sticky_and_schedule_gravity_match_the_pinned_digests` catches future drift and nothing more.
`test_the_score_everything_equality_holds_while_every_free_pool_fits_in_max_candidates` shows the equality inside
the condition and the difference outside it.

## Affinity

Affinity is symmetric and defined for every pair. It has two entry points with different return types:
`AffinityModel.affinity(a_id, b_id)` (from `build_affinity_model(records)`, and what the scheduler uses) returns an
**integer** from 0 to 1000 ("milli-affinity"), while the module-level helper
`gravity_affinity.affinity(a, b, pool=None)` takes two records and returns a **float** from 0 to 1 (the integer
divided by 1000). Only `AffinityModel` and `build_affinity_model` are exported from `simvltanea.authoring`;
the helper is not. Each component returns a value from 0 to 1, or "missing" when either clip lacks
its inputs. Only components present for both clips count:

<!-- BEGIN GENERATED: affinity-formula -->
```text
A = (P * V + sum(|w_k| * c_k)) / (P + sum(|w_k|))        P = 0.05, V = 0.5
c_k = s_k when w_k > 0,   c_k = 1 - s_k when w_k < 0
```
<!-- END GENERATED: affinity-formula -->

The pseudo-component P at value V pulls thin evidence toward neutral. Weights are signed
(`relation.weights`, -1 to 1): a negative weight rewards contrast in that component, so a mode can
match on colour while contrasting on environment. The eight components below carry the default weights.

<!-- BEGIN GENERATED: affinity-components -->
| Component | Weight | What it compares |
| --- | --- | --- |
| subjects | 0.22 | Weighted overlap (sum of minimums over sum of maximums). Term weight is prominence `4/(4+rank)` times IDF `sqrt((1+M)/(1+df))` over the eligible pool. |
| keywords | 0.1 | The same overlap without prominence. |
| context | 0.14 | Mean of small tables for setting, environment and time of day. `unclear` counts as missing. |
| mood | 0.1 | Moods as valence and arousal points; symmetric best match. |
| color | 0.16 | Circular hue, gated by saturation so grey clips do not vote on hue, plus palette distance (redmean). |
| tone | 0.1 | Closeness of luma and saturation. |
| motion | 0.1 | Tag motion level and measured frame-difference motion. |
| framing | 0.08 | Source orientation and shot size. |

`environment`, `shot`, `orientation`: single-attribute views, weight 0 unless set.

| Constant | Value | Meaning |
| --- | --- | --- |
| `PRIOR_WEIGHT`, `PRIOR_VALUE` | 0.05, 0.5 | The pseudo-component (P and V above) that pulls thin evidence toward neutral. |
| `COMPONENT_SCALE` | 10^12 | Each component is quantised to an integer in steps of 1/COMPONENT_SCALE before the components are combined. |
| `WEIGHT_SCALE`, `WEIGHT_RANGE` | 1/1000, -1 to 1 | Weights are signed and are used in integer thousandths. |
| `AFFINITY_SCALE` | 1000 | Milli-affinity, `AffinityModel.affinity`, is an integer 0 to 1000. |
| `PROMINENCE_RANK` | 4 | Prominence of a subject at position `rank` is `4/(4+rank)`. |
| `LOCAL_ONLY_COMPONENTS` | `color`, `tone`, `motion`, `framing` | The components a clip with local features and no tags can supply. |
| `BITS_PER_UNIT` | 8 | Bits of odds per 1.0 of logit at temperature 1 (see the relation rule). |
| softmax step | 1/16 bit | The integer softmax works in steps of 1/16 bit with a fixed table of 16 mantissas. |
<!-- END GENERATED: affinity-components -->

Graceful degradation:

- Clips with only local features (no tags) can supply `color`, `tone`, `motion` and `framing`, renormalised. With the default weights `framing` is then its orientation part only, because shot size is a tag; the `orientation` view is also computed but weighs 0 unless set.
- A tagged clip against an untagged one uses only the components both have.
- Missing or malformed fields drop their component rather than failing.
- With no data at all the result is exactly 500.

Reproducibility. The float operations in `gravity_affinity.py` are exactly these:

- `+ - * /` and `sqrt`, which IEEE 754 requires to be correctly rounded, so every engine returns the same double;
- operations that never round, because their result is one of their operands or is exactly representable:
  `abs`, `min`, `max`, comparisons, the float remainder `hue % 1.0` (hue is never negative, so Python's `%` and
  JavaScript's `%` are the same exact fmod), and floor division by 1, `(x * SCALE + 0.5) // 1`, which is the exact
  floor of a double and is how half-up quantisation is written (the products stay far below 2^53, so the
  conversion to an integer is exact).

There is no exp, log, pow or trigonometry, and never the builtin `sum` (CPython 3.12 and later use compensated
summation): float sums are plain left-to-right loops over sorted lists. Sets are iterated in sorted order and
rounding is explicit half-up, so values are identical across processes and
`PYTHONHASHSEED` values and can be matched bit for bit by a future port. Each component is
quantised to an integer (steps of 10^-12) before the components are combined, and the
combination is integer arithmetic, so the result does not depend on the order in which
components are added (`test_result_is_independent_of_component_summation_order`).

Python's Unicode string semantics are part of the contract too, because a straightforward JavaScript port does not
share them (measured with CPython 3.13, Unicode 15.1 tables). A port must reproduce each of these, not the nearest
built-in:

- **Stripping.** Keywords are normalised with `str.strip()`, which removes exactly what `str.isspace()` matches: `\t\n\v\f\r`,
  U+001C to U+001F, space, U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F and U+3000, and
  **not** U+FEFF. `String.prototype.trim()` strips U+FEFF and keeps U+001C to U+001F and U+0085, so it gives a different
  keyword set, and with it a different affinity (a keyword `"\ufeffbar"` is a different word from `"bar"` in Python).
  Subjects are not stripped or case-changed at all.
- **Case.** Keywords (and a sharing rating or a digest, via `strip().lower()`) are lower-cased with `str.lower()`, which
  follows the interpreter's Unicode tables; exclude ids are compared with `str.casefold()`, which is not `lower()`
  (`"ß".casefold()` is `"ss"`, `"ß".lower()` is `"ß"`) and not `toLowerCase()`. A port needs the same tables, so record the
  Unicode version (15.1 for the figures here).
- **Normalisation.** No Unicode normalisation is applied to keywords, subjects or ids: `"é"` (U+00E9) and `"e\u0301"` are
  different words. The guard on Photos library names is the one place that normalises (NFC, then `casefold()`), and
  it is a separate module.
- **Sort order.** Every `sorted()` over strings (terms, keywords, tags, canonical JSON keys with `sort_keys=True`) compares
  by code point. The two-pointer merge of two sorted term lists, and with it the float summation order, depends on it.
  JavaScript's default sort and `<` compare UTF-16 code units, which puts an astral character (U+1F600) before U+FF21;
  a port needs an explicit code-point comparator.
- **Length.** `len()` counts code points, `String.prototype.length` counts UTF-16 units: a seed's 200-character limit, a tag
  token's 40 and an id's 80 are code points, and an astral character counts once.
- **Encoding.** Digests are taken over UTF-8 bytes of canonical JSON written with `ensure_ascii=False`; a lone surrogate
  cannot be encoded and is refused, so a port must refuse it as well rather than substitute U+FFFD.

The `play_state` command is not exposed to most of this: it keeps only ASCII tokens and ids. The library API
(`build_affinity_model`, `schedule_play`, `schedule_gravity` on raw records) is, and
`UnicodeStringSemanticsTests` in `test_gravity_affinity.py` pins each Python behaviour above.

Speed: `AffinityModel.affinity` runs a prepared path. Per pool it computes, once per clip, the
terms already weighted by IDF, the palette with its share total and the interned categorical
tags; per pair it looks up the categorical components (context, mood, shot, orientation,
framing, palette names) in a memo and evaluates only the continuous ones.
`affinity_milli_uncached` is the plain reference, and `FastPathEquivalenceTests` asserts that both
return the same integer for every pair of a fixed pool, with default, signed and malformed
inputs, and that a whole schedule has the same digest through either path.

## The relation rule

At each change of a loop the path proposes candidates (see [PLAY_MODES](PLAY_MODES.md)). Each
candidate gets a score from what is already on screen, then one is drawn:

<!-- BEGIN GENERATED: relation-formula -->
```text
field  = weighted mean of A(candidate, clip on other loop), neighbours weighted up
grav   = (1 - independence) * field + independence * A(candidate, this loop's previous clip)
         (previous clip = the clip the loop is showing when the pick is made, the one being replaced)
logit  = strength * grav + anchor_pull * max A(candidate, anchor)
         - novelty * coverage_pressure - recency * recency_penalty
draw weight = 2^(8 * logit / temperature)      (integer table, SHA-256 draws)
```

The scale matters. `BITS_PER_UNIT` is 8, so a logit gap of 1.0 at temperature 1 is 8 bits of odds, about 256:1 (`play_rng.weighted_pick` over evenly spaced draws measures about 259:1 because the table is rounded), not 2:1 as a plain base-2 softmax of the logit would give and not e:1 as a natural-base softmax would. At temperature T the odds for a gap g are 2^(8 * g / T). Strength, novelty and recency are all logit terms, so each is multiplied by the same scale.
<!-- END GENERATED: relation-formula -->

Spatial neighbours are edge-sharing cells averaged over both authored orientations, so the
device orientation never changes what is chosen. The draw weight is computed in integers (base 2,
1/16-bit steps, fixed table), so no floating-point exponent is involved. A negative `strength`
runs through the same integer machinery and favours unlike clips.

<!-- BEGIN GENERATED: relation-settings -->
| Setting | Range | Default | Effect |
| --- | --- | --- | --- |
| `relation.strength` (`gravity` in `GravityParams`) | -4 to 4 | 2.5 | Pull toward related clips; negative repels. A negative strength multiplied by a negative component weight is attraction again (see "Two negatives"). |
| `relation.temperature` | 0.1 to 4 | 1 | Divides every score; higher is more random. |
| `relation.independence` | 0 to 1 | 0.25 | 0 attends to the whole field; 1 lets each loop follow its own thread. |
| `relation.adjacency` | 0 to 1 | 0.5 | Extra weight for neighbouring cells. |
| `relation.anchors`, `relation.anchor_pull` | list of clip ids, 0 to 2 | none, 0 | Attractor clips. Anchors only attract: the pull is never negative. |
| `relation.weights.*` | -1 to 1 | see the component table | Which components count, and whether they match or contrast. |
| `timing.recency`, `timing.recency_window`, `timing.novelty` | 0 to 2, 0.25 to 1e+06, 0 to 2 | 0.6, 120, 0.6 | Variety and coverage pressure that enters the logit. |
<!-- END GENERATED: relation-settings -->

The complete table, with ranges generated from the code, is in [PLAY_MODES](PLAY_MODES.md).

### Gravity presets

<!-- BEGIN GENERATED: gravity-presets -->
| Preset | Strength | Temperature | Odds for a grav gap of 0.1 | Character |
| --- | --- | --- | --- | --- |
| `drift` | 1 | 1 | 1.7:1 | Mild: related clips are slightly favoured. |
| `sticky` (default) | 2.5 | 1 | 4.0:1 | Related clips tend to appear together. |
| `magnetic` | 4 | 0.5 | 84.4:1 | Clustered: tight groups of related clips. |
<!-- END GENERATED: gravity-presets -->

`GravityParams.from_preset(name, **overrides)` builds them; `--mode NAME` selects the same
presets in the command, next to the other play modes.

### Two negatives, and what "opposites" is

A negative `relation.strength` and a negative component weight multiply: **two negatives cancel to attraction**. A
mode that starts from `opposites` (strength -2.5) and adds "contrast environment" (`relation.weights.environment` =
-1) therefore matches on environment instead of contrasting it. Over seeds 1 to 3 on the synthetic pool, with environment
as the only weighted component and temperature 0.5, the share of on-screen pairs in the same environment is 1.00
with strength -2 and weight -1, 0.15 with +2 and -1, 0.15 with -2 and +1, 1.00 with +2 and +1, and 0.32 with strength
0 (`test_a_negative_strength_with_a_negative_weight_cancels_to_attraction`). To repel on one component, keep the
strength positive and give that component a negative weight (that is how `city_vs_nature` and `near_vs_far` work), or
keep a negative strength with positive weights.

The `opposites` preset only **biases** the draw toward unlike clips; it does not pick the least related one. The
table ranks the candidates at each choice by the engine's own field and shows where the pick falls
(percentile 0 is the least related candidate, 0.5 is what a blind pick scores). Reaching near-argmin behaviour
needs a strength of -4, a temperature of 0.1 and no independence, novelty or recency, as in the last row.

<!-- BEGIN GENERATED: measured-opposites -->
| Setting (N=5) | Mean percentile of the pick (0 = least related candidate) | Picks that are the least related candidate |
| --- | --- | --- |
| `random` (no pull) | 0.49 | 1.5% |
| `sticky` (strength 2.5) | 0.80 | 0.2% |
| `opposites` (strength -2.5, temperature 1) | 0.37 | 2.8% |
| strength -4, temperature 0.1 | 0.20 | 8.1% |
| strength -4, temperature 0.1, independence 0, novelty 0, recency 0 | 0.01 | 72.0% |
<!-- END GENERATED: measured-opposites -->

## Measured trade-offs

Reproducible: every table in this section between generated markers is written by
`python3 -m tools.media.measure_gravity --write` from the repository's own synthetic pool and the current code
(`--check` exits 1 when the page differs from a fresh measurement, and a test runs it; a full run takes under a
minute). The pool is made up and its themes are a ground truth only the evaluation reads. The baseline is the same
scheduler with the same holds, cooldown and no-duplicate rule, but gravity, novelty and recency at 0. "Same-theme"
counts on-screen pairs that share a latent theme. These numbers moved when `relation.independence` was fixed (the pick
used to be related to the clip two changes back instead of the clip being replaced), and any later change to the
affinity, the engine or the default settings moves them again; the script is how to see by how much.

<!-- BEGIN GENERATED: measured-header -->
Pool: `make_pool(120)`, digest `85c43e02c7ee95a0`, 96 eligible clips, eight latent themes. 600 s at 24 fps, seeds 1 to 10, default settings except as listed. Regenerate with `python3 -m tools.media.measure_gravity --write`.
<!-- END GENERATED: measured-header -->

<!-- BEGIN GENERATED: measured-by-loops -->
| N | Mean affinity on screen (gravity / baseline) | Same-theme pairs (gravity / baseline) | Times | Coverage (g / b) | Median repeat gap, s (g / b) |
| --- | --- | --- | --- | --- | --- |
| 2 | .611 / .384 | .775 / .171 | 4.53 | .978 / .822 | 265 / 146 |
| 3 | .551 / .383 | .600 / .181 | 3.31 | .998 / .941 | 199 / 128 |
| 4 | .517 / .380 | .505 / .169 | 2.99 | 1.000 / .975 | 162 / 108 |
| 5 | .492 / .377 | .426 / .168 | 2.53 | 1.000 / .994 | 132 / 92 |
| 6 | .480 / .381 | .399 / .173 | 2.31 | 1.000 / .999 | 116 / 84 |
| 7 | .470 / .378 | .376 / .162 | 2.32 | 1.000 / 1.000 | 102 / 75 |
<!-- END GENERATED: measured-by-loops -->

Stickiness against variety at N=5 (same-theme fraction, coverage):

<!-- BEGIN GENERATED: measured-stickiness -->
| Setting | Same-theme | Coverage |
| --- | --- | --- |
| gravity 0 | .17 | .99 |
| gravity 1.0, temperature 1 (drift) | .22 | 1.00 |
| gravity 2.5, temperature 1 (sticky) | .43 | 1.00 |
| gravity 4, temperature 1 | .67 | 1.00 |
| gravity 4, temperature 0.5 (magnetic) | .80 | 1.00 |
<!-- END GENERATED: measured-stickiness -->

<!-- BEGIN GENERATED: measured-independence -->
Independence at N=5, same-theme fraction: .506 at 0, .426 at 0.25, .253 at 0.75, .176 at 1.
<!-- END GENERATED: measured-independence -->

The ratios quoted for the gravity presets (the preset descriptions say "about X times uniform"; the baseline is
not perfectly uniform because it keeps the cooldown) come from the same run, and `--check` fails when a description
differs from them by more than 0.05:

<!-- BEGIN GENERATED: measured-presets -->
| Preset | Same-theme pairs against the zero-gravity baseline, N=5 |
| --- | --- |
| `drift` | 1.3 times |
| `sticky` | 2.5 times |
| `magnetic` | 4.8 times |
<!-- END GENERATED: measured-presets -->

### Not reproducible from this repository

These were measured by the scout with scripts that are not in this repository (`synthetic_pool.py`,
`measure_gravity.py` and their one-off drivers), on the scout's own synthetic pool (about 120 clips, 109 eligible, a
different pool from `make_pool`), for the plan dated 2026-11-05, and before the `relation.independence` fix. They are
kept as records of what was seen, not as claims anyone can regenerate here, and they are not comparable with the tables
above:

- The earlier run of the repository's helpers before the independence fix gave, at N=5, .480 / .377 mean affinity and
  .405 / .168 same-theme pairs (2.40 times) against .492 / .377 and .426 / .168 (2.53 times) now: the fix makes the
  default slightly stickier, because the loop's own thread is now the clip it just showed. The earlier tree is not
  available to re-run.
- Across the runs there were no immediate repeats and the shortest repeat gap was the 30 s cooldown.
- Novelty and recency both off: higher affinity (.570) but coverage .894, very uneven show
  counts and a 74 s median gap. Both at 0.6: .536, coverage .998, 141 s.
- Features only (no tags, 120 clips): same-theme .286 against .200 at the default; .488 at
  gravity 2.5 and temperature 0.5; .584 at gravity 4 and temperature 0.5. Untagged clips
  need stronger settings to cluster.
- Spatial swaps only (7 clips on 7 loops): neighbour affinity .555 with gravity swaps,
  .521 without, .522 with random swaps.
- An anchor raised mean affinity of on-screen clips to it from .497 to .542 at pull 1.5.

## Eligibility, encoding, cost and pending decisions

These apply to every play mode, so they live in [PLAY_MODES](PLAY_MODES.md): the exclusion rules
(safety, privacy flags, minors, sharing sensitivity, untagged policy, exclusion by content
digest), the state encoding with the existing `reroll` and `swap` events, the event and work
budgets, the 1,024-segment limit of the offline renderer, and the pending owner decisions (the
`cue` event, the default preset and `exclusion.untagged_policy`).

Still open from this lane:

| Decision | Options and evidence |
| --- | --- |
| Hold times | 4 to 12 s against Live Photos of about 2 to 3 s means each clip loops 2 to 5 times before it changes. |
| Component weights | What "related" means: for example mood against color. The defaults are in the affinity table, and every weight is a parameter. |
| Swaps | Whether gravity-driven swaps are wanted. A swap visibly jumps two cells at once, so `timing.swap_interval` is off by default. |

## Known limits

- The clusters in the measurements are synthetic; real tags may separate less cleanly.
- The scout's JavaScript port matched Python on Node only (V8). It is not part of this
  repository, and no browser parity is claimed.
- `_normalize_subject_tags` and `_normalize_color_profile` in `composition_model.py` invent
  tags and colors from a hash of the clip id when data is missing. That separate
  `color_subject_affinity` path does not feed gravity and is unchanged.
