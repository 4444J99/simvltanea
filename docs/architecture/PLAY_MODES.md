# Play modes — how the loops play

How a composition plays is configuration, not code. A **play mode** is a saved configuration
with four independent dials: **order**, **path**, **relation** and **timing**. Totally random,
chronological, "oldest meets newest", a round, opposites and gravity are all the same engine
with different values. Named presets are ordinary data, and anyone can add or override them
with a JSON file. [GRAVITY](GRAVITY.md) describes one dial in depth, the relation rule; this
page describes everything else.

Every mode produces the same kind of result: a composition state that uses only the existing
event vocabulary (`reroll` and `swap`) and the existing `ENGINE_VERSION`. A mode only chooses
which clip each independent loop shows. It never edits layouts, rates, offsets or orientation
behaviour, so the invariant in [CANON](CANON.md) holds: N independent loops, presentation-only
orientation changes, no filler and no implicit duplication.

| Piece | Location |
| --- | --- |
| Configuration, validation, `describe_parameters()` | `src/simvltanea/authoring/play_config.py` |
| Presets (data table) | `src/simvltanea/authoring/play_presets.py` |
| Eligibility and exclusions | `src/simvltanea/authoring/play_pool.py` |
| Order, paths and the round voice | `play_order.py`, `play_paths.py` beside it |
| Scheduler | `play_engine.py` (integer softmax draws in `play_rng.py`) |
| Encoding into a state, render-segment count and bound | `play_encode.py` |
| Affinity between two clips | `gravity_affinity.py` |
| Earlier gravity entry point (a thin wrapper) | `gravity_scheduler.py` |
| Command | `tools/media/play_state.py` |
| Capture-time index (container creation time only) | `tools/media/index_clips.py` |
| Output and root guard | `tools/media/play_guard.py` |
| Keeps the generated tables below equal to the code | `tools/media/play_docs.py` |

## Quick start

```bash
python3 -m tools.media.play_state --list-modes
python3 -m tools.media.play_state --describe
python3 -m tools.media.play_state --root /path/to/private-root --mode oldest_meets_newest \
  --n 5 --duration 120 --seed 7 --out /path/to/private-root/play-state.json
python3 -m tools.media.play_state --root /path/to/private-root --mode sticky \
  --set relation.strength=-2 --set timing.hold_min=6 --set timing.hold_max=10 --n 4
```

Precedence, lowest to highest: the mode, then `--config FILE`, then each `--set`, then the
shortcut flags (`--seed`, `--anchor`, `--pin`, `--exclude-id`). `--presets-file FILE` adds
modes or replaces built-in ones by name. A bad value fails with a message and writes nothing.

### Strips layouts: 8 to 12 panels

By default the panels are the authored Artifact 001 layouts, which exist for N = 2..7. `--layout-preset`
builds the panels from a strips layout preset instead (a built-in name, `strips`, or the path of a
`simvltanea.layout-preset/1` file): each panel is a cropped window in a mosaic of strips, and N may be
anything the preset accepts, up to 12 for the built-in. In Python the same choice is
`schedule_play(..., layout_preset="strips")`, which cannot be combined with `base_state`.

```bash
python3 -m tools.media.play_state --root /path/to/private-root --mode sticky \
  --layout-preset strips --n 12 --duration 120 --seed 7 --out /path/to/private-root/play-state.json
```

Limits: with a preset, N is 2..12 for the built-in `strips` (a strips layout alone allows N = 1, but a play
state needs at least two loops to relate); a count the preset refuses (13, say) stops with a message naming the
preset's range and writes nothing. Without `--layout-preset`, N stays 2..7 and the output is byte-identical to
earlier versions. The spatial gravity neighbours come from the strips cells (strips that share an edge, in
either orientation; the bleed overlap is presentation only and the cell rectangles abut), the usual render
segment and span limits apply, and the `.play.json` record keeps `layout_preset` so `--config` replays it.

Known limitation (issue #61): the browser's client compiler cannot read play states yet. Only the Python
`compile_plan` and the offline renderer do.

### Replaying a record

`--config` also reads the `.play.json` record of an earlier run (the file labelled
`schema: play-config/v1`, described under `--out` below). It uses the record's inner `config`, and its `n`, `duration_seconds` and `fps`
for whatever the command line leaves out, so this regenerates a state byte for byte from the same
private root:

```bash
python3 -m tools.media.play_state --root /path/to/private-root --out /path/to/play-state.json \
  --config /path/to/play-state.play.json --force
```

The record's configuration is complete, so `--mode` adds nothing; a later `--set`, `--seed`, `--n`,
`--duration` or `--fps` still wins, as for any other config file. A record with another `schema`, with no
`config` object or with an invalid one is refused and nothing is written. The record holds the digest
and count of the eligible clip ids, so when the pool has changed since (clips added, removed or newly
excluded) the command prints `warning: the eligible pool differs from the one in the record` on standard
error and the result is not a replay. The round trip is tested byte for byte for both files
(`test_a_state_regenerated_from_its_own_sidecar_is_byte_identical`).

`--verify-media` makes the command check each clip's size and SHA-256 against its export
receipt (it reads every media file; by default the receipt is trusted). `--exclude-id ID` that
matches no clip is an error; see "Privacy rules".

`--out` writes two files, never one:

| File | What it is for |
| --- | --- |
| `<name>.json` | The composition state: sources, loops, events. This is what `compile_plan` and the offline renderer read (see "What can read a play state" below). It contains opaque clip ids, source paths and digests, and no caption or personal text. |
| `<name>.play.json` | The record of the run (`schema: play-config/v1`): the fully resolved configuration, the seed, the duration, fps and loop count, the digest of the configuration, the count and a digest of the eligible clip ids, the state's digest and its render-segment count. Keep it with the state: the same pool and record reproduce the state byte for byte (see "Replaying a record" below), and it shows what a state was made from. Besides digests and counts, it holds the clip ids named in the configuration (`exclusion.exclude_ids`, `relation.anchors`, `path.pins`), because reproducing the run needs them. It never holds captions, tags or file names, and it never lists the eligible ids. Treat it like the configuration file you passed. |

**Both files are a private artifact: never commit them, never share them.** The clip ids are the Photos
library identifiers and the source paths (`originals/<uuid>/<uuid>.mov`) carry them again, by design (the renderer
needs them), so anyone who holds a state or a record learns which library items it was built from. Where they go
is only guarded against Git trees, not against synced folders such as iCloud or Dropbox, so keep `--out` somewhere
that is not synced or shared. The command ends every successful run with one line saying so (`private: ...`).

Both files go only under `var/work/` or outside every Git working tree. An existing file is
replaced only with `--force`, and a failed run leaves nothing behind (the one exception is a folder swapped for a link between the two writes, below). Source paths in the state
are `originals/<id>/<id><ext>`, relative to the state file, so write the state beside
`originals/` (`--out <root>/play-state.json`) to render or preview it (commands below, under
"What can read a play state").

### What can read a play state

What works today: Python's `compile_plan` (`simvltanea.browser`) accepts a play state, and the offline renderer
(`render_triptych`) renders it as long as the state needs at most 1,024 render segments (see "The
renderer limit (L8)"). Two command-line previews also read a play state, because both run Python's
`compile_plan` (the in-browser studio compiler is not involved; see below). They stage a `plan.json`, the
verified media and `index.html` / `runtime.js` for `browser.runtime.js`, which only plays the per-loop spans:

```bash
python -m independent_loop_compositor preview --state <state> --output var/work/<name>
python -m simvltanea.browser.browser_runtime --state <state> --output var/work/<name>
```

Both print `{"frames": ..., "loops": ..., "spans": ..., "state_sha256": ...}` and exit 0. Each needs the output
directory to be inside this repository's `var/` (anything else stops with `preview must remain inside the
incubator`), and the state's sources must be `.mp4` files holding 8-bit `yuv420p` H.264: a Photos `.mov`
export is refused with `browser preview currently requires H.264 MP4`, so a state built from `.mov` files
renders offline but does not preview. The preview copies the media into its output directory, so that
directory is as private as the state. The sibling `time-moment-brief` checkout ("shared engine") may be absent:
the command then prints a notice (and writes `shared-engine-unavailable.txt`) and still stages the
preview, which plays without it. Both commands were run against a generated play state with reroll and
swap events and multi-source banks.

To render a state offline, give the renderer an explicit output inside this repository:

```bash
python -m independent_loop_compositor render --state <root>/play-state.json \
    --orientation portrait --output var/work/play-portrait.mp4
```

Without `--output` the renderer writes `<state directory>/<state name>-<orientation>.mp4`, and a state written
beside `originals/` is outside this repository, so the default is refused with `output must remain inside the
incubator`. The renderer, the preview and `play_state` all write under `var/` (git-ignored by `/var/*`;
`var/work/` is the place for private output). The rendered video is as private as the state.

What does not work: the in-browser client compiler (`src/simvltanea/browser/browser.compiler.js` on the main
branch) refuses any state with `events` and any loop with a multi-source bank, with a `CompilerError`
("outside the browser compiler subset"). Almost every play state has one or both, so the in-browser web studio
cannot preview it, although Python's `compile_plan` accepts the same file. The one exception is a state with
every loop pinned (`path.pins`, one pin per loop): it has no events and only one-source banks, and the browser
compiler accepts it (`EventsAndBanksTests` in `test_play_modes.py` checks that shape). Closing the gap for the
rest is a separate lane (the `cue` event, or compiler support in the browser client); this lane does not touch
the compiler.

## The four dials

Every behaviour below is reachable by configuration alone. At each change of a loop the engine
works in this order: the **path** proposes candidates, the **relation** scores them against what
is on screen, the **timing** decides when each loop changes, and the **order** is the sequence
the path walks.

### Order: what the clips are ordered by

`order.axis` is `none`, `captured_at`, a numeric local feature (`luma`, `luma_spread`,
`saturation`, `hue`, `motion`, `duration`) or a tag ordinal (`motion_level`, `shot`,
`time_of_day`). `order.direction` reverses it, but only an axis that has values: `none` is a seeded
shuffle with no lowest end, so the direction is ignored there (the ordered shapes refuse axis `none`; the others
accept it). Ties break by clip id, so the order is stable.
A clip without a value on the axis follows `order.missing`: `exclude`, `end` (sorted by id) or
`random` (seeded positions). Random, playlist and follow ignore the order.

`captured_at` comes from `tools/media/index_clips.py`, which reads only the container creation
time of each exported clip with `ffprobe` and writes `analysis/index/<id>.json`. It never reads
or writes location or any other metadata.

### Path: how each loop travels along the order

| Shape | Behaviour |
| --- | --- |
| `random` | Uniform over free clips (or weighted by the relation rule). No immediate repeat, cooldown honoured. |
| `sequential` | Walk forward or backward (`direction`, `step`). At the end: `wrap`, `bounce` or `stop`. `spread` starts loops evenly spaced or all together. |
| `converge` | Loops take the two ends of the order (`groups`, `first_end`) and move toward each other. The meeting point is the middle of the order, `ceil(size / 2)`, for every loop count: the low zone is the first half, the high zone the second. With an odd loop count the end that takes the extra loop still gets only its half of the order (the one exception: with exactly as many clips as loops and `first_end` = `high`, that end needs the room, so the middle moves one place; every clip is on screen then and nothing moves). At the meeting point `on_meet` is `bounce` (reverse and diverge back out), `restart`, `hold` or `stop`. Every loop changes on its own random clock, so the two fronts come within a few clips of each other (the median closest approach is 1 to 4 ranks over eight seeds in the tests), not exactly side by side. |
| `diverge` | Start in the middle and move toward both ends. The two zones are proportional to the loops each end starts, so every loop has about the same room to travel. |
| `pingpong` | Sweep end to end and back. |
| `round` | A canon. Loop 0 follows a base voice (`path.base`, itself any other shape) and loop k plays the same voice `k * delay_beats * beat_seconds` later. `voice: clips` plays identical clips, delayed; `voice: tags` plays the same sequence of tag values on different clips. |
| `playlist` | A shuffled deal that exhausts the pool before any clip repeats. |
| `follow` | Each loop walks from its previous clip to a related one (a per-loop gravity walk). |

`path.window` sets how strictly cursor shapes follow the order. 0 is exactly the next clip;
k chooses among the next k+1 clips using the relation rule, so "chronological but
gravity-flavoured" is `window` above 0 with a positive `relation.strength`.

A `round` with `voice: clips` needs `delay_beats * beat_seconds >= hold` so the same clip is
never on two loops at once; otherwise the configuration is refused with a clear error. The
hold must be a whole number of beats at the chosen fps, and a round requires
`timing.synchronized` with `hold_min == hold_max`. The flag is required but a round's loops are
not simultaneous: see the note under "Settings that have no effect".

A round's base voice must keep moving. A `round` whose base is `sequential` or `diverge` with
`path.wrap = stop`, or `converge` with `path.on_meet = stop` or `hold`, is refused when the
configuration is validated, with a message that names the setting (use `wrap` or `bounce`, or
`bounce` or `restart`). Without this check such a round could work for a short run and fail
on a long one, because a voice that has halted must repeat a clip on several loops. The same
settings remain valid for the ordered shapes themselves.

### Relation: how simultaneous loops relate to each other

`relation.strength` is a signed number from -4 to 4: positive attracts related clips (gravity),
zero is neutral, negative repels (opposites). `relation.weights` holds one signed weight per
affinity component. A positive weight matches that component, a negative weight contrasts it,
so one mode can match colour while contrasting environment (city against nature) or shot size
(near against far). Weights are data, not constants.

Two negatives cancel: a negative `relation.strength` multiplied by a negative weight is attraction, so
`opposites` plus "contrast environment" matches on environment (measured: 1.00 of on-screen pairs in the same
environment, against 0.15 with exactly one negative). The `opposites` preset also only biases the draw toward
unlike clips; it does not pick the least related one (the measured percentile of its picks, and what near-argmin
needs, are in [GRAVITY](GRAVITY.md), "Two negatives, and what \"opposites\" is"). The rule, the components and the
measurements are in [GRAVITY](GRAVITY.md).

### Timing: when each loop changes

`hold_min` and `hold_max` set how long a clip stays (drawn per change, at least 0.25 s),
`stagger` keeps two loops from changing in the same instant, `synchronized` makes all loops
change on the same beat, `cooldown` is a hard minimum before a clip returns (relaxed only when
nothing else is free, never by inventing filler), `recency` and `novelty` are soft pressures
for variety and coverage, and `swap_interval` turns on gravity-driven swaps of two loops'
clips.

### Settings that have no effect

Some settings are accepted everywhere but only read by some shapes. The table below is
generated from a small table in `tools/media/play_docs.py`, and a test changes each listed
setting and compares the generated state byte for byte, so a listed row cannot drift from the
code. The table lists the cases found by changing each setting in turn across the configurations
those tests run; it is not a proof that no other case exists, so a setting that is not listed
may still have no effect somewhere the tests do not look. Nothing is refused or warned about,
because every configuration carries a value for every setting (defaults are always filled in),
so a warning would fire on every configuration.

<!-- BEGIN GENERATED: inert -->
| Where | Settings with no effect | Why |
| --- | --- | --- |
| `path.shape` = `round` with `path.voice` = `clips` (every base) | `timing.cooldown`, `timing.recency`, `timing.recency_window`, `timing.novelty`, `relation.independence`, `relation.adjacency`, `relation.anchors`, `relation.anchor_pull` | The voice is generated once and every loop plays it back unchanged, so nothing is scored (anchors included). The canon replays each clip one delay later on purpose, which a cooldown would contradict. |
| a `round` with `voice` = `clips` whose base is `random` or `playlist` | `relation.strength`, `relation.temperature`, `relation.weights.*` | These bases never score a choice. (A `follow` base uses them, and so does a cursor base once `path.window` is above 0.) |
| `random` and `follow`, and a `round` whose base is `random`, `playlist` or `follow` | `path.window` | These shapes do not look ahead along an order. |
| `follow`, also as the base of a round with `voice` = `clips` | `relation.independence`, `relation.adjacency` | `follow` always relates each loop to its own current clip, which is what an independence of 1 means, and it has no field of other loops to be adjacent in. |
| cursor shapes (`sequential`, `converge`, `diverge`, `pingpong`) and `playlist` with `path.window` = 0, also as the base of a round with `voice` = `clips` (a round with `voice` = `tags` reads all of these) | `relation.strength`, `relation.temperature`, `relation.weights.*`, `relation.independence`, `relation.adjacency`, `relation.anchors`, `relation.anchor_pull`, `timing.recency`, `timing.recency_window`, `timing.novelty` | With window 0 the next clip is taken as it comes and nothing is scored (anchors only attract a scored choice). `timing.cooldown` still skips a clip that is cooling down, except under `playlist` (next row). |
| `timing.synchronized` = true, every shape (a `round` always is) | `timing.stagger` | All loops change on the same frame, so there is nothing to space apart. |
| every `path.shape` except `round` | `path.base`, `path.voice`, `path.tag`, `path.delay_beats`, `path.beat_seconds` | These describe a round's canon and are read only by a `round`. |
| `random`, `playlist` and `follow` | `order.axis`, `order.direction`, `order.missing`, `path.step`, `path.direction`, `path.wrap`, `path.spread`, `path.on_meet`, `path.groups`, `path.first_end` | These shapes do not walk an order, so the order and everything that moves a cursor along it is unused. |
| a `round`, whatever its base and voice | `path.spread`, `path.groups` | A canon has one voice (`play_paths.voice_walkers`): it always starts together and alternates between the two ends, so the start spread and the grouping of loops are not read. |
| a `round` whose base is `random` or `follow` | `path.step`, `path.direction`, `path.wrap`, `path.on_meet`, `path.first_end` | These bases do not walk the order, so nothing that moves a cursor along it is read. (`order.axis` and `order.direction` still shape the order the voice draws from, when the axis is not `none`.) |
| a `round` whose base is `random`, `playlist` or `follow`, with `order.axis` = `none` | `order.direction` | Axis `none` is a seeded shuffle, not an order with a lowest end, so there is nothing to reverse. (The other shapes that accept axis `none` are listed above; the ordered shapes refuse it.) |
| two loops (`n` = 2), every shape | `relation.adjacency` | With two loops each loop's field is the single clip on the other loop. Adjacency only weights the clips of a field against each other, and a swap of the two loops has no third loop to be adjacent to. |
| `converge` and `diverge`, also as the base of a round | `path.direction`, `path.spread` | The two ends are set by `path.groups` and `path.first_end`, not by a travel direction or a start spread. |
| `converge` and `pingpong`, also as the base of a round | `path.wrap` | `converge` ends by `path.on_meet` and `pingpong` always turns round. `sequential` and `diverge` read it. |
| `sequential`, `pingpong` and `diverge`, also as the base of a round | `path.on_meet` | Only `converge` has a meeting point. |
| `sequential` and `pingpong`, also as the base of a round | `path.groups`, `path.first_end` | Only `converge` and `diverge` split the loops between the two ends. |
| `playlist` at any `path.window`, window 0 or above | `timing.cooldown` | A playlist plays its order as it comes: a clip is never skipped because it is cooling down. (The cursor shapes do skip it, and a `round` with `voice` = `clips` ignores it in every base, first row.) |

`timing.synchronized` means two things. In every shape but `round`, all loops change on the same frame and `timing.stagger` is not used. A `round` requires it to be true, but its loops are never simultaneous: loop k plays loop 0's voice `k * delay_beats` beats later (`k * delay_beats * beat_seconds` seconds), every change on the shared beat grid. With the shipped rounds (delay 3 beats of 2 s, hold 4 s) loop 2 therefore changes 2 s off loop 1. For a `round` the flag has no other effect.
<!-- END GENERATED: inert -->

## Parameter reference

The tables in this section are generated from `describe_parameters()` by
`python3 -m tools.media.play_docs --write`, and a test fails when they differ from the code.
`python3 -m tools.media.play_state --describe --json` prints the same metadata for a UI.

<!-- BEGIN GENERATED: parameters -->
### `order`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `order.axis` | one of `none`, `captured_at`, `luma`, `luma_spread`, `saturation`, `hue`, `motion`, `duration`, `motion_level`, `shot`, `time_of_day` | `none` | What the clips are ordered by: none, capture time, a numeric local feature, or a tag ordinal. Ignored by the random, playlist and follow shapes. |
| `order.direction` | one of `ascending`, `descending` | `ascending` | ascending puts the lowest value (oldest) first; descending reverses the order; ignored when the axis is none, which is a seeded shuffle. Ties always break by clip id. |
| `order.missing` | one of `exclude`, `end`, `random` | `exclude` | Clips without a value on the axis: exclude them, put them at the end (sorted by id), or insert them at seeded random positions. |

### `path`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `path.shape` | one of `random`, `sequential`, `converge`, `diverge`, `pingpong`, `round`, `playlist`, `follow` | `random` | How each loop travels along the order. random: uniform (or relation-weighted) over free clips. sequential: walk the order. converge: loops start at the two ends and move toward each other. diverge: start in the middle, move toward both ends. pingpong: sweep end to end and back. round: a canon (loop k plays loop 0's voice k*delay_beats beats later). playlist: shuffled deal that exhausts the pool before any repeat. follow: each loop walks from its previous clip to a related one. |
| `path.direction` | one of `forward`, `backward` | `forward` | sequential/pingpong: travel along the order (forward) or against it (backward). |
| `path.step` | integer 1 to 50 | 1 | Positions advanced per change (sequential, pingpong, converge, diverge). |
| `path.wrap` | one of `wrap`, `bounce`, `stop` | `wrap` | At the end of the order (sequential) or of the outward travel (diverge): wrap jumps back to the start, bounce reverses, stop leaves the loop on its last clip. |
| `path.spread` | one of `even`, `together` | `even` | sequential/pingpong start positions: even = evenly spaced along the order, together = side by side at the start. Not read by a round (its single voice always starts together). |
| `path.on_meet` | one of `bounce`, `restart`, `hold`, `stop` | `bounce` | converge, when a loop reaches the meeting point: bounce = reverse and diverge back out, restart = jump back to its end, hold = that loop keeps its clip, stop = every loop freezes at the first meeting. |
| `path.groups` | one of `alternate`, `halves` | `alternate` | converge/diverge: how loops split between the two ends. alternate = loops take the ends in turn; halves = the first half takes one end, the rest the other. Not read by a round (its single voice alternates between the ends). |
| `path.first_end` | one of `low`, `high` | `low` | converge/diverge: the end (low = oldest/first, high = newest/last) that loop 0 takes; with an odd loop count that end gets the extra loop. |
| `path.window` | integer 0 to 100 | 0 | Cursor shapes and playlist: 0 = exactly the next clip; k = choose among the next k+1 clips with the relation rule (chronological but gravity-flavoured). Ignored by random and follow, and by a round whose base is random, playlist or follow. |
| `path.base` | one of `random`, `sequential`, `converge`, `diverge`, `pingpong`, `playlist`, `follow` | `sequential` | round only: the path shape of the base voice that loop 0 follows. |
| `path.voice` | one of `clips`, `tags` | `clips` | round only: clips = every loop plays the same clips, delayed (needs delay_beats*beat_seconds >= hold); tags = every loop plays the same sequence of tag values on different clips. |
| `path.tag` | one of `shot`, `time_of_day`, `motion_level`, `environment`, `setting` | `shot` | round with voice=tags: which single-valued tag forms the voice. |
| `path.delay_beats` | integer 1 to 64 | 2 | round: loop k starts the voice k*delay_beats beats after loop 0. |
| `path.beat_seconds` | number 0.25 to 3600 | 2 | round: length of a beat in seconds; the hold must be a whole number of beats and every change lands on the beat grid. |
| `path.pins` | list of [loop, clip] pairs | none | [loop id, clip id] pairs: that loop never changes. One pin per loop. |

### `relation`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `relation.strength` | number -4 to 4 | 2.5 | Signed pull between simultaneous loops: positive attracts related clips (gravity), 0 is neutral, negative repels (opposites). Only used where a choice is scored; see "Settings that have no effect" in PLAY_MODES.md. |
| `relation.temperature` | number 0.1 to 4 | 1 | Divides every score; higher means more random. |
| `relation.independence` | number 0 to 1 | 0.25 | 0 = attend to the whole field of other loops; 1 = each loop only relates to the clip it is showing when the pick is made (the one being replaced). Ignored by the follow shape (which always relates each loop that way) and wherever no choice is scored. |
| `relation.adjacency` | number 0 to 1 | 0.5 | Extra weight for spatially neighbouring cells (both orientations averaged). Ignored by the follow shape and wherever no choice is scored. |
| `relation.anchors` | list of clip ids | none | Clip ids that attract the whole field. Anchors only attract: anchor_pull is 0 to 2 and never negative, so an anchor cannot repel. At most 10,000 ids. |
| `relation.anchor_pull` | number 0 to 2 | 0 | Strength of the anchor term; 0 turns anchors off. |
| `relation.weights.subjects` | number -1 to 1 | 0.22 | Signed weight of the subjects component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.keywords` | number -1 to 1 | 0.1 | Signed weight of the keywords component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.context` | number -1 to 1 | 0.14 | Signed weight of the context component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.mood` | number -1 to 1 | 0.1 | Signed weight of the mood component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.color` | number -1 to 1 | 0.16 | Signed weight of the color component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.tone` | number -1 to 1 | 0.1 | Signed weight of the tone component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.motion` | number -1 to 1 | 0.1 | Signed weight of the motion component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.framing` | number -1 to 1 | 0.08 | Signed weight of the framing component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.environment` | number -1 to 1 | 0 | Signed weight of the environment component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.shot` | number -1 to 1 | 0 | Signed weight of the shot component: positive matches it, negative contrasts it, 0 ignores it. |
| `relation.weights.orientation` | number -1 to 1 | 0 | Signed weight of the orientation component: positive matches it, negative contrasts it, 0 ignores it. |

### `timing`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `timing.hold_min` | number 0.25 to 3600 | 4 | Shortest stay of a clip on a loop, seconds. |
| `timing.hold_max` | number 0.25 to 3600 | 12 | Longest stay, seconds (>= hold_min); drawn per change. |
| `timing.stagger` | number 0 to 3600 | 0.5 | Minimum seconds between any two loops' changes (not used when synchronized). |
| `timing.synchronized` | true or false | false | All loops change together on the same frame (stagger is not used). A round requires true but is not simultaneous: loop k changes k * delay_beats beats after loop 0, every change on the shared beat grid, and the flag has no other effect there. |
| `timing.cooldown` | number 0 to 1e+06 | 30 | Hard minimum seconds before a clip may return; relaxed only when no other clip is free. Not used by the playlist shape (at any window), nor by a round with voice clips (the canon replays each clip on purpose). |
| `timing.recency` | number 0 to 2 | 0.6 | Soft penalty for recently shown clips. Only used where a choice is scored; not by a round with voice clips, nor by cursor shapes and playlist with window 0. |
| `timing.recency_window` | number 0.25 to 1e+06 | 120 | Seconds over which the recency penalty fades (unused wherever recency is). |
| `timing.novelty` | number 0 to 2 | 0.6 | Pressure toward under-shown clips (coverage). Only used where a choice is scored; not by a round with voice clips, nor by cursor shapes and playlist with window 0. |
| `timing.swap_interval` | number 0 to 1e+06 (0 or at least 0.25) | 0 | Seconds between gravity-driven swaps of two loops' clips; 0 = off (otherwise at least 0.25). Not available for ordered shapes. |

### `exclusion`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `exclusion.require_safety_clear` | true or false | true | Clips need safety verdict 'clear' and no pending review; a record the tagger refused (an error code or needs_review) is excluded too. A clip with no safety verdict at all (never tagged) is excluded under either untagged_policy. |
| `exclusion.exclude_privacy_flags` | list of `readable_text`, `license_plate`, `document_or_screen`, `location_identifiable` | `document_or_screen`, `license_plate`, `location_identifiable`, `readable_text` | Privacy flags that exclude a clip. A listed flag that is present but malformed (not a bool, number or short string) excludes the clip under either untagged_policy; a missing one follows untagged_policy. |
| `exclusion.exclude_minors` | true or false | true | Exclude clips where a minor is apparent. A malformed minors flag excludes the clip under either untagged_policy; a missing one follows untagged_policy. |
| `exclusion.max_sharing_sensitivity` | one of `low`, `moderate`, `high` | `moderate` | Clips rated above this are excluded. |
| `exclusion.untagged_policy` | one of `allow`, `exclude` | `allow` | What is done with what is UNKNOWN about a clip that carries a clear safety verdict: a missing or null sharing rating, a missing privacy flag, a missing minors flag. allow keeps the clip, exclude drops it. It also decides never-tagged clips when require_safety_clear is off; with require_safety_clear on, a clip with no safety verdict is excluded under either value. |
| `exclusion.exclude_ids` | list of clip ids | none | Clip ids that are never shown (letter case is ignored; byte-identical copies under other ids are excluded too). An id that matches no clip in the pool is counted and warned about, and is an error when given with --exclude-id. At most 10,000 ids. |

### `limits`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `limits.max_events` | integer 100 to 1000000 | 150000 | Refuse a request whose estimated event count exceeds this (the repository's validate_state grows super-linearly with events). |
| `limits.max_candidates` | integer 8 to 5000 | 400 | At most this many candidates are scored per change; a larger free pool is sampled deterministically by a seeded draw. |
| `limits.max_score_ops` | integer 10000 to 10000000000 | 30000000 | Refuse a request whose estimated scheduling work (changes x candidates x loops affinity lookups) exceeds this. |
| `limits.max_render_segments` | integer 1 to 1024 | 1024 | Your own render-segment limit, which can only be LOWER than the offline renderer's fixed limit of 1024 (composition.MAX_SEGMENTS). Whether a state is renderable is always judged against the renderer's limit; this value only decides when refuse_unrenderable refuses and when the command warns that you are over your own limit. |
| `limits.refuse_unrenderable` | true or false | false | Refuse (instead of warn) a state that needs more render segments than max_render_segments (at most the renderer's limit). The default keeps long states: they are still written and still compile with compile_plan, but the offline renderer will not render them. |

### `seed`

| Parameter | Values | Default | Effect |
| --- | --- | --- | --- |
| `seed` | integer or string | 0 | Integer (within +/-(2**53 - 1), so JSON keeps it exact) or string; identical (pool, seed, config) give a byte-identical state. |
<!-- END GENERATED: parameters -->

## Presets

A preset is a complete configuration saved under a name. The starting values of every setting
are exactly `sticky`. The table is generated from the preset table.

<!-- BEGIN GENERATED: presets -->
| Preset | What it does |
| --- | --- |
| `random` | Totally random: uniform over free clips, no immediate repeat, cooldown honoured. |
| `chronological` | Oldest to newest by capture time; loops start evenly spaced along the timeline and wrap. |
| `reverse_chronological` | Newest to oldest by capture time. |
| `oldest_meets_newest` | Loops alternate between the oldest and newest ends and move toward each other, meet at the middle of the order (for any loop count), then bounce back out. |
| `newest_meets_oldest` | The same, with loop 0 starting at the newest end (an odd loop count gives that end the extra loop). |
| `round_clips` | A round (canon) in time: loop 0 walks the timeline and each later loop plays the same clips 3 beats (6 s) after the one before. Nothing in it is random, so every seed shows the same clips. |
| `round_tags` | A round of tags: every loop plays the same sequence of shot sizes, each loop on different clips of that size. |
| `opposites` | Repel: clips unlike what is already on screen are favoured (negative strength). It tilts the odds toward unlike clips; it does not choose the least related one (see GRAVITY.md). |
| `city_vs_nature` | Match colour and tone but contrast environment: urban beside nature. |
| `near_vs_far` | Contrast shot size: close-ups beside wide shots, everything else neutral. |
| `drift` | Mild gravity: related clips are slightly favoured (about 1.3 times uniform at N=5). |
| `sticky` | Gravity: related clips tend to appear together (about 2.5 times uniform at N=5). The starting values of every setting. |
| `magnetic` | Strong gravity: tight clusters of related clips (about 4.8 times uniform at N=5). |
| `calm_to_intense` | Ordered by measured motion, calm to intense and back (bounce), gravity-flavoured over a window of 5 clips. |
| `dark_to_light` | Ordered by luma, dark to light, loops side by side, gravity-flavoured over 5 clips. |
| `rainbow` | Ordered by hue around the colour wheel, loops side by side, wrapping. |
<!-- END GENERATED: presets -->

### The owner's examples

| Example | Preset | Evidence that it behaves as described |
| --- | --- | --- |
| Totally random | `random` | `test_totally_random_has_no_order_and_covers_the_pool`: no rank correlation between time and luma, most of the pool shown. |
| Chronological order | `chronological` (and `reverse_chronological`) | `test_chronological_runs_oldest_to_newest_and_reverse_runs_the_other_way`: capture time strictly increasing (decreasing) on every loop. |
| The oldest with the newest, meeting in the middle | `oldest_meets_newest` (and `newest_meets_oldest`) | `test_oldest_meets_newest_in_the_middle`: two loops over 600 s start at the two ends, close in to within 4 clips at the middle of the order, and bounce back out. `test_the_two_fronts_meet_in_the_middle_for_every_loop_count_odd_or_even`: for 2, 3, 4, 5 and 7 loops, over eight seeds with the preset's own random holds, the median closest approach of the two fronts is at most 4 ranks and the turn is exactly at the middle. `test_every_walker_starts_inside_its_zone_whatever_the_order_size_loop_count_and_end`: no walker of the converge or diverge shape starts outside its zone, for any order size and loop count. |
| A round, like in classical music | `round_clips` and `round_tags` | `test_a_round_of_clips_is_an_exact_canon` and `test_a_round_of_tags_repeats_the_shot_sequence_on_different_clips`: loop k's sequence equals loop 0's shifted by k delays. |
| Opposites | `opposites` | `test_positive_strength_raises_and_negative_lowers_on_screen_affinity_against_random`: mean on-screen affinity below the random baseline. |
| City against nature | `city_vs_nature` | `test_city_against_nature_shows_different_environments_far_more_than_random`. |
| Near against far | `near_vs_far` | `test_near_against_far_shows_different_shot_sizes_more_than_random`. |
| Far apart in a feature, in order | `calm_to_intense`, `dark_to_light`, `rainbow` | `test_calm_to_intense_dark_to_light_and_rainbow_follow_their_axes`. |

All of these tests are in `src/simvltanea/authoring/test_play_examples.py` and
`test_play_modes.py`, on a synthetic pool only. The thresholds are conservative.

To make your own, write a JSON file shaped `{"name": {"description": "...", "config": {...}}}`
holding only the values that differ from the starting values, and pass it with
`--presets-file`. A name that matches a built-in preset replaces it for that run.

## Guarantees

All of these are tested on synthetic pools.

- Identical pool, seed and configuration give a byte-identical state, independent of pool
  order and of `PYTHONHASHSEED` (child processes with different values are compared).
- A different seed gives a different state (the seed is stored in it), and a different composition for every
  built-in mode that draws something at random (hold lengths, random, playlist and follow picks, scored choices,
  the candidate sample). The exception is `round_clips`: a sequential base with window 0, fixed 4 s holds and a
  canon that starts at the oldest clip draws nothing, so every seed shows the same clips at every frame, and only
  the `seed` field and the reroll encoding in the state change
  (`test_the_states_always_differ_but_the_composition_differs_for_every_preset_except_round_clips`).
- If fewer eligible clips exist than loops the call fails; no filler and no duplicated clip is
  ever created, and one clip is never on two loops at once.
- The `sticky` preset is deterministic and equals the score-everything path **while the eligible
  pool has at most `limits.max_candidates` clips (400 by default)**: inside that condition no
  free pool can reach the limit, so any limit at or above it gives the identical state. Above it
  the engine scores a seeded sample of the free clips and the state differs from the
  score-everything state (see [GRAVITY](GRAVITY.md); raising the limit to its maximum of 5,000
  restores score-everything only while the eligible pool has at most 5,000 clips). It does **not**
  reproduce the output of the earlier, pre-play-mode gravity scheduler any more. That held until
  the exclusion rules were tightened (a clip with no safety verdict is now excluded) and then
  until the `relation.independence` fix, which changed every gravity-scored pick on purpose: a
  loop's own thread is now the clip it is showing, not the clip two changes back. The digests
  pinned in `test_play_modes.py` were re-pinned to the current output after each of those two
  changes, so they catch future drift; they are not a comparison with the older implementation
  (`test_sticky_and_schedule_gravity_match_the_pinned_digests`). `schedule_gravity` remains as a
  wrapper over the same engine, and the equality with the score-everything path inside the
  condition is tested by
  `test_the_score_everything_equality_holds_while_every_free_pool_fits_in_max_candidates`.
- Selection uses integer arithmetic after each affinity component is quantised, and an integer
  softmax, so no floating-point rounding decides a pick and a port can match exactly.
- Every generated state passes `validate_state`, round-trips through `save_state` and
  `load_state`, and compiles with `compile_plan` to the scheduled sources. The generator counts
  the spans `compile_plan` will produce (exactly: `play_encode.count_plan_spans`, checked
  against the real plan on many varied states) and refuses a state with more than 1,024 spans
  per loop (`composition.MAX_SEGMENTS`), before `validate_state` and before anything is
  written. The message gives the spans needed against the 1,024 allowed per loop and says
  which cause dominates, counted on that very state. A shorter `--duration` always helps. Spans
  also come from every loop reaching the end of its clip, which repeats every
  `clip length / rate` seconds whatever the holds are, so when clip ends dominate (the usual
  case for the default `sticky` mode on long runs of short clips) only a shorter duration or
  longer source clips help, and a larger `timing.hold_min` does not. A larger hold floor is
  suggested only when source changes (the holds) dominate. Fewer loops and a lower fps never
  help: the limit grows with the loop count and spans follow seconds, not frames. The offline
  renderer has a separate, stricter limit on whole-state segments (see "The renderer limit").
- An integer seed must be within plus or minus 2**53 - 1, so it survives JSON unchanged; larger
  values are given as strings (the command keeps a longer number as a string).
- Seed text follows one rule on every path (`--seed`, `--set seed=` and the seed in `--config` and
  `--presets-file` files): text that is exactly an integer written the canonical way (an optional `-`, no
  leading zeros, ASCII digits, within the limit above) becomes that integer, and everything else stays a
  string. So `7` and `-7` are integers while `007`, `-0`, `+7` and `1.5` are strings, and each gives the same
  state whichever way it is passed. (`-0` is a string because the integer 0 is written `0`.) Code that calls
  `schedule_play(seed=...)` or `validate_config` with a Python value is not text: `1` and `"1"` stay different.
- A string seed must be encodable as UTF-8. A lone surrogate (an invalid byte in a command-line argument
  decodes to one) is refused by `validate_config` with a message that does not echo the text.
- Excluded clips never appear in a pool, an order, a bank, a source list, an event or the shown
  timeline.
- Work is bounded: the request is refused before anything is built when the estimated events
  exceed `limits.max_events` or the estimated scoring work exceeds `limits.max_score_ops`; at
  most `limits.max_candidates` clips are scored per change (a larger free pool is sampled by a
  seeded draw, so output stays reproducible); holds and beats have a floor of 0.25 s.
- A base state that carries events or loop trims is refused, never silently stripped.

## Privacy rules

- The pool is filtered before anything else is built. A clip is excluded when:
  - its id is in `exclusion.exclude_ids` (letter case is ignored);
  - safety is required (the default) and the record needs review, carries an error code (any
    value that is not null, however falsy: `""`, `0`, `false`, `[]`), or has a safety verdict
    other than `clear`. A refused record is excluded before anything else, and the error text
    is never read;
  - **safety is required and the clip has no safety verdict at all (never tagged): it is
    excluded under either `untagged_policy`** (reason `untagged`). This is a deliberate
    tightening: until the review of this lane, `untagged_policy = allow` showed such clips;
  - a tagged record has an analysis that sanitises to nothing (reason `safety` while safety is
    required);
  - a privacy flag in `exclusion.exclude_privacy_flags` is set, or `people.minors_apparent` is
    set while `exclusion.exclude_minors` is on;
  - one of those flags, or the sharing rating, is **present but malformed** (a list, an object,
    a string longer than 40 characters, null for a flag, or any rating that is not `low`,
    `moderate` or `high`): reasons `privacy_invalid`, `minors_invalid`, `sharing_invalid`.
    Intake keeps an explicit invalid marker instead of dropping the value, and a malformed
    value is excluded under either policy and is never read as permission. The same holds for
    a whole `privacy` or `people` section that is present but is not an object (a list, a
    string, a number, null): `privacy_invalid` (always) and `minors_invalid` (while
    `exclusion.exclude_minors` is on), under either policy and every sharing limit. Only a
    section that is absent is "unknown";
  - `sharing_sensitivity` is above `exclusion.max_sharing_sensitivity`;
  - something about a clip that DOES carry a clear verdict is unknown and the policy is
    `exclude`: a missing sharing rating (`sharing_unknown`), a missing or absent privacy flag
    or section (`privacy_unknown`), a missing `minors_apparent` or `people` section
    (`minors_unknown`). With `allow` these pass;
  - safety is not required, the clip is untagged and the policy is `exclude` (`untagged`);
  - it has no valid sha256 or duration.

  `untagged_policy` therefore governs only what is unknown about a clip that carries a clear
  verdict, and never-tagged clips when `require_safety_clear` is off.
- Exclusion follows content. Every other record carrying the sha256 of an excluded clip is
  excluded as well, with a reason that does not name the other id. The command also reads the
  export receipt of every id in `exclusion.exclude_ids`, tagged or not, so a clip that was
  exported but never tagged still hides its byte-identical copies. An id is matched to its
  `originals/` directory by comparing letter-case-folded names against a listing of
  `originals/`, never by asking the volume to resolve a differently spelled path, so the
  result is the same on a case-sensitive and a case-insensitive volume. For this exclusion
  direction only, the receipt is read leniently and a symlinked `originals/<id>/` (or
  `originals/`) is read through: reading can only add a digest to the hidden set, so it fails
  closed, and the id counts as an existing clip. Every `files[].sha256` in the receipt is
  hidden even when the clip's media file is missing or a link, its `.done` is a link, or its
  duration is text. The same holds for a tagged clip that is skipped because its receipt fails
  the display checks: if its own tag would exclude it (unsafe verdict, minors apparent, a
  privacy flag, a sharing rating over the limit, or a malformed record that cannot be judged),
  its receipt digests are hidden too, so its byte-identical copies stay out; a clean clip with
  a broken receipt hides nothing. Showing media stays strict and refuses all of those (see
  below). A directory that resolves into a `.photoslibrary` package (letter case and Unicode folded, as
  for `--root`) is never read: the run is refused with nothing written. `originals/` is listed
  once per run, however many ids are excluded, and each id list (`exclusion.exclude_ids`,
  `relation.anchors`) holds at most 10,000 ids.
- An exclude id that matches no clip in the pool is never silent. A listed id that is a typo
  excludes nothing, so the command counts such ids and prints `warning: N exclude id(s) match
  no clip in the pool; those are NOT excluded` on standard error, with how many of them are one
  character away from a pool id. An id given with `--exclude-id` that matches no clip (no pool
  record and no `originals/<id>/` directory) is an error: exit non-zero, nothing written. Both messages give
  counts, never the id.
- Only opaque ids matching `[A-Za-z0-9_-]{1,80}` enter the pool. Tag text is reduced to a
  whitelist of controlled vocabulary and numbers on intake: captions, sharing notes, safety
  reasons and error messages are never read into the pool or written to the state, the record
  or the output.
- The command prints counts and digests only: no ids, no captions, no file names, and the
  report holds counts by reason, never a per-id classification.
- A malformed record is skipped and counted, never fatal and never named.
- Output goes only under `var/work/` or outside every Git working tree, through an exclusive
  temporary file and an atomic replace that never follows a planted symlink. Case-variant
  paths, sibling worktrees, `.photoslibrary` packages and tracked files are refused. The destination is checked when
  the command starts and again, with the same guard, immediately before each of the two writes (the state, then the
  record): a folder on the path that was swapped for a link into a tracked directory or a Photos package while the
  pool was loading is refused with nothing written. If the swap happens between the two writes, the state is already
  down and the record is refused. The remaining window between a check and its write is a few instructions, not minutes.
- A root must not be the checkout or inside a Photos library package, and a root inside a Git
  working tree must be ignored by Git (for example under `var/`). The ignore check runs `git` with every `GIT_*`
  environment variable removed, so `GIT_DIR`, `GIT_WORK_TREE` and the like cannot point it at another repository. Inside the root, a symlinked
  `originals/` or `originals/<id>/` is never followed: the clip is skipped and counted as
  `no_usable_export_receipt` before its receipt is opened (a link could lead into a Photos
  library or another tree). `play_state` also refuses to run, exit non-zero with nothing
  written, when `analysis/`, `analysis/tags/` or `analysis/index/` is a link or resolves outside
  the root, so records cannot be fed in from another tree. `index_clips` refuses a symlinked `originals/`, and refuses to write
  when `analysis/` or `analysis/index/` is a link, is not a real directory, resolves elsewhere
  or holds `.git`, so it can never write into another repository's tracked files.
  Every index file it writes also passes through the same destination guard as `--out` (under `var/work/` or outside
  every Git working tree; Photos library names are compared after Unicode case folding), at the moment of the write, so a
  link planted mid-run is caught too. A root inside an ignored directory of a working tree can therefore be read but not indexed.
- Trust boundary of the media digests: by default the sha256 of a clip is the one the exporter
  wrote into its `.done` receipt after copying and hashing the file; the command does not read
  the media bytes (that would cost time proportional to the whole corpus). A file replaced
  after export without rewriting its receipt would therefore carry a stale digest, and content
  exclusion would not see it. `--verify-media` checks each file's size and SHA-256 against its
  receipt and skips mismatches as `no_usable_export_receipt`; use it before a shared build.
  Someone who can change files under `originals/` can also edit the tag records.

## Cost and limits

Scheduling cost is dominated by affinity scoring: at each change, every candidate (at most
`limits.max_candidates`) is scored against the clips on the other loops. The affinity model
prepares each clip once per pool (terms already weighted by their IDF, palettes with their
share totals, categorical tags interned) and memoises the categorical components per pair of
tag combinations. This produces the same integers as the plain per-pair functions: a test
compares the two paths on every pair of a fixed synthetic pool, with default, signed and
malformed inputs, and the state digest was unchanged on the pools and presets measured (measured on 2026-11-05, not regenerated by the drift guards).

Measured on 2026-11-05 (every figure in this subsection, the digest included, is hand-written and is not regenerated by the drift guards: `python3 -m tools.media.play_docs` and `measure_gravity --check` do not run it) with the real command on synthetic pools of 6,500 records, `--n 7 --duration 600
--fps 24 --seed 1` with the default `sticky` mode, on a shared 10-core machine whose load
average was 8 to 10 (so absolute times vary run to run; the figures are single runs, all of
them listed). The pools are built from the repository's synthetic generator (no real media),
from the repository root:

```sh
# mixed pool: 6,500 records, 554 of them untagged (no analysis), 5,946 tagged
python -c "import sys; sys.path[:0]=['.','src']; from pathlib import Path; \
from tools.media.test_play_state import build_root; build_root(Path('var/work/root6500'), 6500)"
# tagged-only pool: the same generator, keeping only the 5,946 records that carry an analysis
python -c "import sys; sys.path[:0]=['.','src']; from pathlib import Path; \
from tools.media.test_play_state import add_clip; from simvltanea.authoring.test_gravity_pool import make_pool; \
[add_clip(Path('var/work/root6500t'), r['id'], r) for r in make_pool(6500) if r['analysis'] is not None]"
# the run (repeat per root); /usr/bin/time -l reports wall, user CPU and peak memory
/usr/bin/time -l python -m tools.media.play_state --root var/work/root6500t \
  --out var/work/out/state.json --n 7 --duration 600 --fps 24 --seed 1
```

Untagged clips are excluded by default (a clip with no safety verdict is never shown; see
"Privacy rules"), and this changes the output for any pool that contains untagged records:
state digests from before that change cannot be compared with current ones. Both pools give
5,253 eligible clips and the same state, `sha256` `f26635daffe79d8061a5aacb40ce427a1e7696f2bcaa35b34133e4e9a8195e9b`
(523 sources, 37,719 events, 2,539 render segments). That digest is from after the fix to
`relation.independence`, which changed every gravity-scored state (it was
`9b7426e52abf8610b4a1458cbf8c5dab5b951452422a4bc3800d4f82ac836b6b`, 40,244 events and 2,523 segments
before; with only that fix reverted, the current code reproduces the old digest); on the mixed pool 1,247 records are excluded (864
safety, 109 minors, 123 privacy flags, 151 sharing sensitivity; the 554 untagged records are
counted under safety because the synthetic ones carry a tagger refusal code), on the
tagged-only pool 693 are.

| Run | Wall time | User CPU time | Peak memory |
| --- | --- | --- | --- |
| Default, mixed pool (3 runs) | 15.5 s, 16.9 s, 17.1 s | 12.4 s, 13.3 s, 13.5 s | 148 MB, 139 MB, 143 MB |
| Default, tagged-only pool (3 runs) | 16.2 s, 18.1 s, 16.4 s | 13.2 s, 14.5 s, 13.4 s | 135 MB, 129 MB, 143 MB |
| Default, tagged-only pool, after the independence fix (1 run, load average 8.5) | 15.7 s | 13.4 s | 147 MB |
| Default, mixed pool, after the independence fix (1 run) | 13.0 s | 12.4 s | 145 MB |
| Reference path, tagged-only pool (2 runs) | 27.8 s, 24.4 s | 22.6 s, 21.1 s | 127 MB, 138 MB |

The reference path is the plain per-pair component functions (`affinity_milli_uncached`)
substituted for the prepared path for that run only; it produced the identical state digest.
The `validate_state` of the repository grows super-linearly with events, which is why the
event budget exists.

### The renderer limit (L8)

The offline renderer (`render_triptych`) stops with "composition exceeds segment resource
guard" when a state needs more than 1,024 render segments (`composition.MAX_SEGMENTS`).
**A 10-minute state with 7 loops generated with default settings does not render offline.**
Measured on synthetic pools with the `sticky` mode, N=7, 600 s, seed 1 (reproduce with
`play(cfg("sticky"), 7, 600, 1, pool=N)` from `test_play_support.py`): 2,455 segments on a pool of
120 clips and 2,536 on a pool of 1,000 (re-measured after the independence fix; 2,489 and 2,503 before it; measured on 2026-11-05, not regenerated by the drift guards). `compile_plan` has a
separate, looser limit: at most 1,024 spans per loop (`composition.MAX_SEGMENTS` times the
loop count in total), where a span starts at a source change or a wrap of that one loop. The
renderer's limit is on the whole state (a segment starts whenever ANY loop changes or wraps),
which is why a 10-minute N=7 default state passes `compile_plan`'s limit (about 400 spans per
loop) and fails the renderer's. A state over `compile_plan`'s limit is refused by the command
(see "Guarantees"); a state over only the renderer's limit is written, because it still previews with
`compile_plan` (that is the default: `limits.refuse_unrenderable` is false), and the command then prints
a loud, exact warning on standard error:

```text
WARNING: NOT RENDERABLE OFFLINE: this state needs 1243 render segments and the offline renderer allows 1024 (219 over); ...
```

`report.renderable` (and `renderable` in the `.play.json` record) is always judged against
`composition.MAX_SEGMENTS`, 1,024, whatever the configuration says. `limits.max_render_segments` can only be
LOWER than that constant (a larger value is refused when the configuration is validated, so it can no longer
mark an unrenderable state renderable). A lower value is your own ceiling: when the state is over it the
command prints a second, milder warning, and `--set limits.refuse_unrenderable=true` refuses the state at
that ceiling (at 1,024 when you did not lower it). The report carries `configured_render_segment_limit` and
`over_configured_limit` next to the renderer's own `render_segment_limit`.

A render segment starts at frame 0, at every frame where any loop changes its source, and
wherever a loop's local clock wraps past the end of its current clip. Because every loop
wraps every `clip length / rate` seconds, the count grows with the loop count and the duration
and falls with longer clips; hold settings matter less, since wraps dominate.
`play_encode.render_segment_bound` computes a bound from settings alone:

```text
changes per loop <= (frames - 1) // hold_frames + 1          (hold_frames from timing.hold_min)
segments <= 1 + sum over loops of (2 * changes + 1 + seconds * rate / shortest_clip)
```

and `render_segment_estimate` gives the expected count, `1 + seconds * sum(rate / mean_clip +
1 / mean_hold)`. The bound held against the exact count in every case tested; the estimate
landed within 15 percent in the test and within about 6 percent in the measurements (measured on 2026-11-05, not regenerated by the drift guards). The table
gives the longest whole-second duration for which the count stays within 1,024, using the
default authored layouts and their loop rates, with swaps off. "Guaranteed" comes from the
bound; "typical" is the estimate with a 10 percent margin for clips averaging 2.4 s and the
default 4 to 12 s holds, and is not a guarantee. Durations are capped at 600 s.

<!-- BEGIN GENERATED: segments -->
| Loops (N) | Typical estimate | Guaranteed: holds from 4 s, clips from 1.5 s | Guaranteed: holds from 12 s, clips from 1.5 s | Guaranteed: holds from 4 s, clips from 3 s |
| --- | --- | --- | --- | --- |
| 2 | 600 s | 428 s | 594 s | 600 s |
| 3 | 540 s | 280 s | 384 s | 396 s |
| 4 | 395 s | 204 s | 280 s | 292 s |
| 5 | 305 s | 160 s | 217 s | 230 s |
| 6 | 250 s | 132 s | 178 s | 188 s |
| 7 | 210 s | 110 s | 147 s | 160 s |
<!-- END GENERATED: segments -->

What was actually rendered: a 12 s state with N=3 (20 segments) generated by the command from
14 synthetic clips rendered with `render_triptych` and ffmpeg at 360 by 640 into a 24 fps,
288-frame, 12.0 s file. The 600 s, N=7 state generated from the same 14 clips needed 2,260
segments (counted before the independence fix; not re-run, and not regenerated by the drift guards) and the renderer refused it with the guard message above. No longer state was
rendered, so the table is derived from the counting rule in the code, not from long renders.

## Pending owner decisions

Nothing below has been changed; every default stays as it was.

1. **A `cue` event.** Without one, each change to a loop is encoded as a run of `reroll`
   events searched until the engine's hash lands on the wanted clip, about one event per bank
   clip. A 10-minute N=7 state on a pool of 120 clips measured 28,061 `reroll` events (27,822 before the independence fix; measured on 2026-11-05, not regenerated by the drift guards), and
   `compile_plan` took 21.2 s (25.2 s earlier on a loaded machine; the scout measured about 31 s with scripts outside this repository). The event counts reproduce with `play(cfg("sticky"), 7, 600, 1, pool=120)`; the times depend on the machine. A `cue`
   event that pins a loop to a named source would need one event per change: this run had 517
   clip changes, and the scout's spike measured 501 events, about 51 KB and 4 s (measured outside this repository with scripts that are not in it, so not reproducible from it). It changes the
   state schema (old engines would reject it), so it may require a new `ENGINE_VERSION`.
   Recommendation: yes. It is not part of this change.
2. **The default preset.** `sticky` is the default for the command and the starting values
   of every setting (about 2.5 times as many same-theme pairs as the zero-gravity baseline at N=5; the generated table in [GRAVITY](GRAVITY.md) is kept equal to a fresh measurement by `tools/media/measure_gravity.py --check`, this sentence is not). `random`,
   `drift` and `magnetic` are the alternatives. Untagged material needs stronger settings to
   cluster.
3. **`exclusion.untagged_policy`.** A deliberate tightening was made after the review: with
   `require_safety_clear` on (the default), a clip with no safety verdict at all (never
   tagged) is now excluded under either policy, because "make sure there is nothing bad in
   them" cannot hold for a clip nobody checked. `untagged_policy` governs only what is
   unknown about a clip that DOES carry a clear verdict: a missing sharing rating, a missing
   privacy flag, a missing minors flag. It defaults to `allow`, which shows such a clip; that
   is fine for a fully tagged personal corpus and too lax for anything shared.
   Recommendation: `exclude` for shared builds (`--set exclusion.untagged_policy=exclude`),
   which also drops clips with an unknown rating or an unknown flag. Whether the new
   tightening itself is wanted is the owner's call; turning `require_safety_clear` off
   restores the old behaviour for untagged clips, and every other safety check with it.

Still open from the gravity lane, recorded in [GRAVITY](GRAVITY.md): hold times against short
Live Photos, the component weights, and whether gravity-driven swaps are wanted.

## Known limits

- The measurements use synthetic pools; real tags may separate less cleanly.
- The scout's JavaScript port matched Python on Node only (V8); it is not in this repository
  and no browser parity is claimed.
- A custom `base_state` must have no events or trims. The render-segment table assumes the
  default authored layouts and their loop rates.
- Swaps are not available for ordered shapes and rounds, and pins are not available for
  rounds; the configuration is refused.
