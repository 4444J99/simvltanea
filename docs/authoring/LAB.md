# The lab

For overlapping picture layers, swept comb filters, and independently changing
audio/video clocks, open the [Effects Lab](EFFECTS_LAB.md) from Studio. The
dataset-based instrument described here focuses on strips, framing, and source
selection.

The lab is a playable, modular-synth-style web instrument for simultaneous loops.
N video loops play at once as edge-to-edge strips, heavily cropped; the more strips,
the less zoomed each one is. Every parameter of the engine, layout, zoom, framing,
audio and reveal is a knob, switch or selector with immediate effect. Tap a strip
to see the original still.

It is plain static ES modules, HTML and CSS: no build step, no dependencies, no CDN
and no network beyond its own origin. The app lives in
[`src/simvltanea/lab/app/`](../../src/simvltanea/lab/app/) and is distributed with
the `simvltanea.lab` subpackage. It is an engineering instrument for exploring the
material, not an artist-approved design.

## Run it

Generate the synthetic test clips once (FFmpeg required), then serve the repository
root on the loopback interface and open the app with a `?data=` base:

```sh
PYTHONPATH=src python3 -m simvltanea.lab.make_fixtures   # writes var/proofs/lab-fixtures/
python3 -m http.server 8000 --bind 127.0.0.1
# open http://127.0.0.1:8000/src/simvltanea/lab/app/?data=/var/proofs/lab-fixtures/
```

`--bind 127.0.0.1` keeps the server on this machine; without it, `http.server`
listens on every network interface. The fixtures are test patterns and sine tones
only; no real media is read. `--force` rebuilds them.

For your own clips, build a dataset below `var/` (see
[Build a dataset](#build-a-dataset)) and point `?data=` at it:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
# open http://127.0.0.1:8000/src/simvltanea/lab/app/?data=/var/samples/lab-data/
```

A dataset kept outside the checkout works the same way from a separate site folder
that holds a copy of `app/` and the dataset side by side:

```text
site/
  app/          a copy of src/simvltanea/lab/app/
  lab-data/
    data/clips.json
    media/<id>.mp4
    still/<id>.jpg
```

Serve it with `cd site && python3 -m http.server 8000 --bind 127.0.0.1` and open
`http://127.0.0.1:8000/app/?data=/lab-data/`.

- Audio is blocked by browsers until a gesture: press **Start sound** (or the
  _Sound_ button in the PATCH module).
- Use a browser that plays H.264/AAC MP4 (Chrome, Safari, Edge, or Firefox on most
  platforms). A plain `http.server` is enough; small proxies need no range requests.

## The `?data=` contract

`?data=<base>` is the dataset base. The default is `./`, meaning `app/data/clips.json`.
The base must be **same-origin**: a cross-origin base is refused before any request
is made. Below the base the app reads exactly these paths:

| Path | Content |
| --- | --- |
| `data/clips.json` | `{"version": 1, "clips": [...]}`, described under [Data schema](#data-schema) |
| `media/<id>.mp4` | one H.264/AAC proxy per clip |
| `still/<id>.jpg` | the original still, shown by the reveal |

`video` and `still` in each record resolve relative to the base.

## Build a dataset

[`tools/media/build_lab_dataset.py`](../../tools/media/build_lab_dataset.py) writes
exactly that layout from exported, tagged, safety-clear Live Photo clips:

```sh
python3 -m tools.media.build_lab_dataset --root /path/to/live-photos --dest var/samples/lab-data
```

`--root` falls back to `$SIMVLTANEA_LIVE_PHOTOS_ROOT` and `--dest` to
`$SIMVLTANEA_LAB_DATA_DIR`; there is no default path. Inside the checkout both must
stay below `var/`, which Git ignores; anywhere outside a repository is fine too. The
tool needs FFmpeg and ffprobe and is incremental:

- `media/<id>.mp4` uses the validated proxy chain (540 px short side, 24 fps,
  H.264) and keeps the clip's audio, so every panel can play its own sound.
- `still/<id>.jpg` is the real still. Converting HEIC uses `sips`, so stills are
  macOS only; elsewhere `still` is empty and the reveal falls back to the video.
- `id` is an opaque keyed hash of the Photos identifier; no Photos UUID appears in
  any file name or value, and `captured_at` is never a location.
- `audio` comes from the local speech screen
  ([`tools/media/screen_audio.py`](../../tools/media/screen_audio.py)): derived
  fields only, never a transcript. Clips without a screen record carry
  `{"screened": false}` and are muted by default.

## Keys and gestures

| Input | Action |
| --- | --- |
| tap, click or Enter on a panel | reveal the original (Esc, a tap or the x closes it) |
| Space | pause or resume everything (switches and buttons keep Space for themselves) |
| H | hide or show every bit of chrome (on touch a faint _Show_ chip returns it) |
| knob: drag, wheel, arrows | Shift is fine (drag, wheel) or x10 (arrows); PageUp/PageDown step 10 %; Home/End go to min/max |
| knob: double-click or Enter | type an exact value (Enter commits, Esc cancels) |
| MOD (floats) | assign an LFO: sine, triangle, random walk or square, with rate (Hz) and depth (fraction of the half range); the teal arc shows the live value |
| LOCK | exclude a control from RANDOMIZE |
| BYP / RST (module header) | bypass runs the module on its defaults; reset restores defaults and removes LFOs |

On a phone (640 px wide or less) the panel becomes a bottom sheet toggled by the
_Settings_ button. On larger screens it docks left, right or bottom and floats over
the art; it never changes the full-bleed layout.

## How it plays: four dials

A preset is just data (`app/presets.js`) that sets these four dials. Use the PATCH
module's preset menu or set them by hand.

- **ORDER** ranks the pool: `none` (seeded shuffle), `captured_at`, `luma`,
  `saturation`, `hue`, `motion`, `duration`, and the tag ordinals `motion_level`,
  `shot`, `time_of_day` and `people`. Unknown values sort last.
- **PATH** is how each panel travels along that order: `random`; `sequential` (each
  panel from its own start, spread over the order); `converge` and `diverge` (the
  two ends walk together or apart, per group); `pingpong`; `round` (a canon: panel
  _k_ plays panel 0's sequence _k_ x delay steps later; `voice=clips` plays the same
  clips, `voice=tags` plays different clips that resemble the leader's); `playlist`
  (one shared queue dealt to whichever panel changes next, exhausted before it
  repeats); and `follow` (each panel stays beside its left neighbour). `on_meet`
  decides what happens at meetings and ends: bounce, restart, hold or stop.
  `window` lets RELATION choose among clips near the path target.
- **RELATION** is the signed pull between the panels on screen at the same time:
  strength from -4 (repel) to +4 (attract), temperature, independence, adjacency,
  signed weights per component (subjects, keywords, scene, mood, colour, tone,
  motion, framing) and per-attribute _contrast_ switches (environment nature against
  urban, shot near against far, orientation, time of day, motion).
- **TIMING** holds, stagger, a shared beat grid, cooldown (hard), recency and
  novelty (soft), swap interval and speed.

No clip is ever on two panels at once, unless the filtered pool has fewer clips than
panels. The engine samples a bounded set of candidates per change, so 6,500 clips
cost about a quarter of a millisecond per change.

## Layout and zoom

Panels are strips stacked along the viewport's long axis: columns on wide screens,
rows on tall ones, or forced. Rect edges are integer pixels, adjacent strips share
edges (plus the optional few-pixel overlap) and the union covers the viewport at any
N from 1 to 16 and any size or aspect. Each video is a natural-size element scaled
by a CSS transform inside an `overflow:hidden` cell:
`scale = max(cover(cell + jitter overscan), cover(cell) x zoom)`, with the focal
point clamped, so the cell is never left empty.

`zoom(N) = max(floor, Z1 / N^gamma)`, with defaults Z1 = 8, gamma = 0.6 and
floor = 1 (plain cover). The ZOOM module shows a live readout of the zoom and the
share of the clip visible. Zoom 1 means "just covers the strip", so strips get
_less_ cropped, and more recognisable, as panels are added.

## Framing: a new window for every appearance

The zoom module says _how much_ of a clip a strip shows; FRAMING decides _which
part_. Every time a panel gets a clip (and, in `drift` mode, at every hold)
`app/framing.js` derives a window `{cx, cy, zoom}` in normalised source
coordinates. The window keeps the strip's aspect ratio, never leaves the source, and
its zoom is never below cover (including the layout jitter overscan), so a strip
cannot show empty space. The zoom curve is the baseline; `zoom_jitter` varies each
window by a percentage around it. The same clip therefore looks different each time
it appears and, in `blend` and `contrast`, depends on what surrounds it. Cropping
hides much of each photograph, but it is not anonymisation.

| Mode | What it does |
| --- | --- |
| `center` | the zoom module's focal point (`zoom.focal_mode`) and curve, nothing derived; bit-for-bit the plain transform |
| `random` | a seeded window per appearance (seed, clip and appearance index) |
| `thirds` | a rule-of-thirds point of the clip placed on a rule-of-thirds point of the window (16 combinations, seeded) |
| `detail` | among K candidates, prefers windows with more local colour variance in `grid8` |
| `blend` | among K candidates, the window whose edge colours best match the facing edge of the neighbouring panel's window |
| `contrast` | the opposite: maximises the edge difference |
| `drift` | a slow seeded pan and zoom through the window range during the hold; still under reduced motion |

`spread` scales how far from the centre windows may go (0 is always centred).
`temperature` 0 always takes the best candidate. `neighbour_influence` scales how
much the neighbours steer `blend` and `contrast`; `match_on` compares colour,
brightness or hue. `vary_per_appearance` off gives a clip the same window every
time. With `memory` M, any M consecutive appearances of a clip show M different
windows, best effort when the range holds fewer. Modes that need colour use
`features.grid8`, else a flat colour from `features.palette`, `hue` or `luma`, else
fall back to `random` for that clip. REVEAL > _Outline window_ draws the panel's
current window on the full still.

## Audio and the speech policy

After **Start sound**, one Web Audio graph is built:
`video -> MediaElementSource -> slot gain (loudness normalisation, cross-fade) ->
panel bus (size weighting, mute/solo) -> StereoPanner (position along the strip
axis) -> master (x 1/sqrt(N) auto-trim) -> limiter -> destination`. Every panel
plays at once. Normalisation uses `loudness_db` (missing is unity, boost is capped
at +20 dB, `has_audio: false` is silent). Each strip has a VU bar and M / S buttons
on hover, also in the AUDIO module.

Speech can carry names, numbers and private conversation that the frames never
show. In local screens, roughly a third to 43 % of the clips that have audio
contained speech. `audio.speech_policy` therefore defaults to **`mute`**. It
applies to clips with `audio.speech === true` and to clips carrying any of the flags
`number_sequence`, `email_like`, `introduces_self`, `possible_name` or
`long_speech`:

- `play`: sound as usual.
- `mute` (default): the picture plays, the clip's gain is 0 and its element is muted,
  in the reveal too.
- `exclude`: never shown; removed from the pool and replaced if already on screen.

`audio.mute_unscreened` (default on) also mutes clips whose `audio.screened` is not
`true`, including clips with no `audio` record. A malformed `speech` or `flags`
value counts as speech. No preset, scene or RANDOMIZE changes either setting.

## Data schema

`<base>data/clips.json`:

```json
{"version":1,"clips":[{
  "id":"opaque-id","video":"media/ID.mp4","still":"still/ID.jpg","duration":2.1,
  "width":540,"height":720,"orientation":"portrait|landscape","has_audio":true,"loudness_db":-37.6,
  "captured_at":"2019-08-17T18:02:11Z",
  "tags":{"subjects":["tree","sky"],"setting":"indoor|outdoor|mixed|unclear",
          "environment":"nature|urban|domestic|workplace|transit|event|studio|unclear",
          "time_of_day":"day|golden_hour|dusk|night|artificial_light|unclear",
          "camera":"locked|handheld|pan|tilt|zoom|tracking|unclear",
          "motion_level":"still|subtle|moderate|intense","shot":"close_up|medium|wide",
          "palette":["blue","green"],"mood":["calm"],"keywords":["tree"],
          "people":{"count":"0|1|2-3|4+","faces_visible":false,"minors_apparent":false},
          "privacy":{"readable_text":false,"license_plate":false,"document_or_screen":false,
                     "location_identifiable":false,"sharing_sensitivity":"low|moderate|high"},
          "safety":{"verdict":"clear"}},
  "features":{"luma":0.5,"luma_spread":0.1,"saturation":0.4,"hue":0.55,"motion":0.05,
              "palette":[{"hex":"#336699","share":0.4}],
              "grid8":"384 hex chars: 8x8 mean colours of the middle frame, row-major, rrggbb x 64"},
  "audio":{"screened":true,"speech":false,"words":0,"flags":[],"low_confidence":false}}]}
```

Every field except `id` and `video` is optional; a missing value is _unknown_.
`features.grid8` and `audio` are optional, and a `grid8` that is not exactly 384 hex
characters is ignored. Records without a usable `id` or `video` are dropped;
duplicate ids keep the first.

Filtering (SOURCE module): strings are trimmed and lower-cased before comparing. A
missing value follows the _Untagged policy_ (include by default). A present but
malformed value (wrong type, unknown word, a privacy flag that is an object) is
excluded whenever the matching filter is active. Defaults are cautious: safety
verdict `clear`, minors excluded, `license_plate` and `document_or_screen` excluded;
sharing sensitivity is not limited until you lower it. RANDOMIZE never touches
SOURCE, the master level or the limiter.

## Privacy

Nothing leaves the machine:

- The page talks only to its own origin: no CDN, fonts, analytics or telemetry.
  Serve it on `127.0.0.1`.
- Patches live in the browser's `localStorage`; exported and imported patches are
  plain JSON files.
- The share URL carries only the configuration (never clips or file names) in the
  `#hash`, which browsers do not send to servers.
- The reveal shows the original still, so treat the page like the private dataset it
  displays.

Real media and `clips.json` stay out of Git. Keep datasets below `var/` or outside
the repository. Below `src/simvltanea/lab/`, folders named `data/`, `media/` or
`still/` are git-ignored (rules derived by `tools.verification.sync_layout` from
`private_dataset_directories` in the layout contract), and the structure verifier
rejects them even when force-added.

## Patches

The PATCH module saves, loads and deletes named patches (`localStorage`, key
`lab.patches.v1`), exports and imports JSON, copies a share URL (the whole
configuration in the hash; opening it restores everything), randomizes (within each
parameter's range, skipping locked controls, SOURCE, the limiter and the speech
policy) and resets all. Presets change ORDER, PATH, RELATION and TIMING only;
_scenes_ also set layout, zoom and framing. Nothing here touches the speech policy.

## Debug API

`window.__lab` exposes `params()` (stored values), `effective()` (what the engine
uses this frame, with LFOs and bypass applied), `set(id, value)`, `config()`,
`engine()` (clip id per panel), `scheduled()`, `layoutRects()`, `audio()` (per-panel
gain, norm, pan, muted, solo and Web Audio node values), `seed()`, `axis()`,
`zoomInfo()`, `framing()` (per panel: clip, appearance index, mode, derived and
applied window, colour source and neighbour mismatch), `reveal()`, `paused()`,
`pool()`, `store` and `player`.

## Tests

The Python suite runs both lab suites (`python3 -m unittest discover -s tests` and
`pytest` find them):

| Module | What it runs | Needs |
| --- | --- | --- |
| `simvltanea.lab.test_lab_unit` | `node --test` over `tests/unit/*.test.mjs`, and the config reference check below | Node.js; skips with that reason without `node` |
| `simvltanea.lab.test_lab_e2e` | the Playwright suite `tests/e2e/e2e_*.py` in headless Chrome, serving the repository root on a random loopback port | Node.js (skips without it), Chrome or Chromium (`PORTVS_BROWSER_EXECUTABLE`), Python Playwright, pytest and FFmpeg |
| `simvltanea.lab.test_lab_privacy` | the dataset and personal-path gate | Git |

CI runs all three, like the other browser suites. To run the pieces by hand:

```sh
cd src/simvltanea/lab && node --test tests/unit/*.test.mjs
PYTHONPATH=src python3 -m unittest simvltanea.lab.test_lab_unit simvltanea.lab.test_lab_privacy
python3 -m pytest src/simvltanea/lab/tests/e2e -p no:cacheprovider -o python_files='e2e_*.py'
```

Headless tests cannot hear anything: audio is verified through the Web Audio graph
(gain and pan node values, analyser levels, element mute state), not through
speakers.

## Configuration reference

Generated from the parameter registry (`app/params.js`) by
`src/simvltanea/lab/scripts/gen_config_reference.mjs`; the UI is built from the same
registry. Regenerate with `node src/simvltanea/lab/scripts/gen_config_reference.mjs`;
`--check` fails when the table is stale, and `test_lab_unit` runs that check.

<!-- BEGIN CONFIG REFERENCE (generated by src/simvltanea/lab/scripts/gen_config_reference.mjs; do not edit) -->

_94 parameters._

### SOURCE

Which clips may play at all (privacy and pool filters).

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `source.safety` | Safety verdict | enum | clear / any | clear |  |  | clear: only clips whose safety.verdict is "clear" (missing = unknown, see Untagged; anything else is excluded). any: ignore the verdict. |
| `source.max_sensitivity` | Max sharing sensitivity | enum | low / moderate / high | high |  |  | Clips whose privacy.sharing_sensitivity is above this level are excluded. high = no limit. |
| `source.exclude_privacy` | Exclude privacy flags | multi | subset of readable_text, license_plate, document_or_screen, location_identifiable | [license_plate, document_or_screen] |  |  | Clips flagged with any ticked privacy flag are excluded. Malformed flag values count as flagged. |
| `source.exclude_minors` | Exclude minors | bool | on / off | true |  |  | Exclude clips where people.minors_apparent is true (or malformed). |
| `source.untagged` | Untagged policy | enum | include / exclude | include |  |  | What to do with clips that lack the information a filter needs (no tags, no safety verdict, no date...). Present-but-malformed values are always excluded when the filter is active. |
| `source.year_min` | Year from | int | 1990 to 2040 (step 1) | 1990 | year |  | Earliest capture year allowed. |
| `source.year_max` | Year to | int | 1990 to 2040 (step 1) | 2040 | year |  | Latest capture year allowed. |
| `source.tags_include` | Tags include | list | list of strings | [] |  |  | Comma-separated words; a clip must carry at least one (subjects, keywords, mood, palette, setting, environment, time of day, camera, shot, motion level). Empty = no constraint. |
| `source.tags_exclude` | Tags exclude | list | list of strings | [] |  |  | Comma-separated words; clips carrying any of them are excluded. |
| `source.seed` | Seed | int | 0 to 999999 (step 1) | 0 |  |  | Seed for every random decision. 0 = pick a new seed at each page load. |

### ORDER

What clips are ranked by.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `order.axis` | Axis | enum | none / captured_at / luma / saturation / hue / motion / duration / motion_level / shot / time_of_day / people | none |  |  | What clips are ranked by. none = a seeded shuffle. |
| `order.direction` | Direction | enum | asc / desc | asc |  |  | asc: low to high (oldest first for captured_at). desc: reversed. |

### PATH

How each panel travels along that order.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `path.shape` | Shape | enum | random / sequential / converge / diverge / pingpong / round / playlist / follow | random |  |  | random: any clip. sequential: each panel walks the order from its own start. converge: two ends walk toward the middle. diverge: from the middle outward. pingpong: back and forth. round: canon, every panel plays the same sequence, each later. playlist: one shared queue dealt to whichever panel changes next. follow: each panel stays beside its left neighbour in the order. |
| `path.step` | Step | int | 1 to 64 (step 1) | 1 | positions |  | Positions advanced along the order at each change. |
| `path.wrap` | Wrap | bool | on / off | true |  |  | Sequential: wrap around at the ends. Off: apply "On meet" at the ends. |
| `path.on_meet` | On meet / end | enum | bounce / restart / hold / stop | bounce |  |  | What happens when travellers meet (converge) or reach an end: bounce back, restart, hold the last clip, or stop (freeze the panel). |
| `path.groups` | Groups | int | 1 to 8 (step 1) | 1 |  |  | Converge/diverge: split the order into this many segments, each with its own pair of travellers. |
| `path.delay_beats` | Delay | int | 0 to 16 (step 1) | 2 | beats |  | Round: panel k starts k x delay steps later. Converge/diverge: spacing of panels travelling on the same side. |
| `path.voice` | Voice | enum | clips / tags | clips |  |  | Round: clips = every panel plays the very same clips. tags = later panels play different clips that resemble the leader's clip from k x delay steps ago. |
| `path.window` | Window | int | 0 to 500 (step 1) | 20 | positions |  | Candidates are drawn from this many positions either side of the path target; relation then chooses among them. 0 = exactly the path. |

### RELATION

How simultaneous panels relate: attract, ignore, repel.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `relation.strength` | Strength | float | -4 to 4 (step 0.05) | 0 |  | yes | Signed pull between simultaneous panels: positive attracts (similar clips together), 0 ignores, negative repels. |
| `relation.temperature` | Temperature | float | 0 to 2 (step 0.01) | 0.5 |  | yes | Randomness of the choice among candidates. 0 = always the best scoring; high = nearly uniform. |
| `relation.independence` | Independence | float | 0 to 1 (step 0.01) | 0 |  | yes | Probability that a panel ignores the others when it picks. |
| `relation.adjacency` | Adjacency | float | 0 to 1 (step 0.01) | 0 |  | yes | 0: every other panel counts equally. 1: only neighbouring panels count. |
| `relation.w_subjects` | Subjects | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared subjects. |
| `relation.w_keywords` | Keywords | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared keywords. |
| `relation.w_scene` | Scene | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of matching setting, environment and time of day. |
| `relation.w_mood` | Mood | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of shared mood. |
| `relation.w_colour` | Colour | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar hue. |
| `relation.w_tone` | Tone | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar brightness and saturation. |
| `relation.w_motion` | Motion | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar amount of motion. |
| `relation.w_framing` | Framing | float | -1 to 1 (step 0.01) | 1 |  | yes | Signed weight of similar shot size and camera movement. |
| `relation.contrast_environment` | Contrast environment | bool | on / off | false |  |  | Prefer clips whose environment differs from the other panels (nature against urban). |
| `relation.contrast_shot` | Contrast shot | bool | on / off | false |  |  | Prefer clips whose shot size differs (near against far). |
| `relation.contrast_orientation` | Contrast orientation | bool | on / off | false |  |  | Prefer clips whose orientation differs (portrait against landscape). |
| `relation.contrast_time` | Contrast time of day | bool | on / off | false |  |  | Prefer clips whose time of day differs (night against day). |
| `relation.contrast_motion` | Contrast motion | bool | on / off | false |  |  | Prefer clips whose motion level differs (still against intense). |

### TIMING

When clips change and how fresh the picks are.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `timing.hold_min` | Hold min | float | 0.5 to 60 (step 0.1) | 4 | s | yes | Shortest time a clip stays in a panel. If min > max the two are swapped. |
| `timing.hold_max` | Hold max | float | 0.5 to 120 (step 0.1) | 10 | s | yes | Longest time a clip stays in a panel. |
| `timing.stagger` | Stagger | float | 0 to 1 (step 0.01) | 0.6 |  | yes | How far apart the panels' first changes are spread. 0 = all together. |
| `timing.synchronized` | Synchronized | bool | on / off | false |  |  | All panels change together on the beat grid. |
| `timing.beat` | Beat length | float | 0.25 to 8 (step 0.05) | 2 | s | yes | Length of one beat; synchronized holds are rounded up to whole beats. |
| `timing.cooldown` | Cooldown | float | 0 to 300 (step 1) | 20 | s | yes | A clip cannot return to any panel for this long after it was shown. Relaxed automatically if the pool is too small. |
| `timing.recency` | Recency | float | 0 to 1 (step 0.01) | 0.5 |  | yes | Soft penalty for clips shown recently. |
| `timing.recency_window` | Recency window | int | 0 to 500 (step 1) | 50 | clips |  | How many recent clips the recency penalty remembers. |
| `timing.novelty` | Novelty | float | 0 to 1 (step 0.01) | 0.3 |  | yes | Bonus for clips not shown yet. |
| `timing.swap_interval` | Swap interval | float | 0 to 60 (step 0.1) | 0 | s | yes | If above 0, a single panel (the one on screen longest) changes every interval instead of independent holds. |
| `timing.speed` | Speed | float | 0.25 to 2 (step 0.01) | 1 | x | yes | Playback rate of every video. |

### LAYOUT

Edge-to-edge strips: count, direction, split, overlap.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `layout.panels` | Panels | int | 1 to 16 (step 1) | 4 |  |  | Number of simultaneous panels (N). |
| `layout.direction` | Strip direction | enum | auto / rows / columns | auto |  |  | auto: strips are stacked along the screen's long axis (columns on wide screens, rows on tall ones). |
| `layout.split` | Split weights | enum | equal / random / golden / custom | equal |  |  | How the screen is divided among the strips. |
| `layout.split_custom` | Custom weights | list | list of numbers | [3, 2, 1] |  |  | Comma-separated relative widths, cycled over the panels (used when split = custom). |
| `layout.overlap` | Overlap | float | 0 to 40 (step 1) | 3 | px | yes | Neighbouring strips overlap by this many pixels. |
| `layout.radius` | Corner radius | float | 0 to 80 (step 1) | 0 | px | yes | Rounded corners (0 keeps the screen perfectly filled). |
| `layout.jitter` | Sideways jitter | float | 0 to 80 (step 1) | 0 | px | yes | Strips sway sideways by up to this much; the video is over-scanned so nothing is left empty. |
| `layout.jitter_rate` | Jitter rate | float | 0.02 to 2 (step 0.01) | 0.2 | Hz | yes | Speed of the sideways sway. |

### ZOOM

How hard each strip is cropped in.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `zoom.z1` | Z1 (zoom at one panel) | float | 1 to 40 (step 0.1) | 8 | x | yes | zoom(N) = max(floor, Z1 / N^gamma). |
| `zoom.gamma` | Gamma | float | 0 to 2 (step 0.01) | 0.6 |  | yes | How quickly the zoom relaxes as panels are added. |
| `zoom.floor` | Floor (1 = cover) | float | 1 to 4 (step 0.01) | 1 | x | yes | Minimum zoom. 1 is plain cover: the crop never gets looser than just filling the strip. |
| `zoom.manual` | Manual override | float | 0 to 60 (step 0.1) | 0 | x | yes | If above 0, use this zoom for every N instead of the curve. |
| `zoom.focal_mode` | Focal point | enum | static / drift | static |  |  | static: each strip looks at a fixed spot of its clip. drift: the spot wanders slowly. |
| `zoom.drift_speed` | Drift speed | float | 0 to 30 (step 0.1) | 3 | cycles/min | yes | Speed of the wandering focal point. |

### FRAMING

Which part of each clip a strip shows: a window derived anew for every appearance.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `framing.mode` | Mode | enum | center / random / thirds / detail / blend / contrast / drift | blend |  |  | center: today's behaviour (the zoom module's focal point). random: a seeded window per appearance. thirds: snap to rule-of-thirds points. detail: prefer windows with more local colour variance (grid8). blend: choose the window whose edge colours best match the facing edge of the neighbouring panel. contrast: the opposite, maximise the edge difference. drift: a slow seeded pan/zoom path through the window range during the hold (Ken Burns style; still under reduced motion). Modes that need colour data fall back to random for clips without any. |
| `framing.spread` | Spread | float | 0 to 1 (step 0.01) | 0.85 |  | yes | How far the window may move from the centre of the clip. 0 = always centred, 1 = anywhere inside the clip. |
| `framing.zoom_jitter` | Zoom jitter | float | 0 to 50 (step 1) | 15 | % | yes | Each window's zoom varies by up to this many percent either side of the zoom module's baseline (never below cover). |
| `framing.candidates` | Candidates (K) | int | 1 to 256 (step 1) | 48 |  |  | How many candidate windows detail, blend and contrast compare (random modes draw until one is allowed by Memory). |
| `framing.temperature` | Temperature | float | 0 to 2 (step 0.01) | 0.2 |  | yes | Randomness of the pick among candidates. 0 = always the best candidate; higher = more varied; about 2 = nearly uniform. |
| `framing.neighbour_influence` | Neighbour influence | float | 0 to 1 (step 0.01) | 0.8 |  | yes | How much the neighbouring panels' windows steer blend and contrast. 0 = ignore them. |
| `framing.edge_sample` | Edge sample width | float | 0.01 to 0.5 (step 0.01) | 0.1 | of window | yes | Width of the band along a window edge whose colours are compared (fraction of the window size across the edge). |
| `framing.match_on` | Match on | enum | colour / luma / hue | colour |  |  | What blend and contrast compare along facing edges: full colour, brightness only, or hue only (weighted by saturation). |
| `framing.vary_per_appearance` | Vary per appearance | bool | on / off | true |  |  | On: every time a clip appears it gets a different window. Off: a clip always gets the same window. |
| `framing.memory` | Memory (M) | int | 1 to 32 (step 1) | 6 | windows |  | A clip must show M different windows before a window repeats (per-clip history). 1 = no restriction. Best effort when the window range holds fewer than M distinct windows. |
| `framing.drift_speed` | Drift speed | float | 0.1 to 30 (step 0.1) | 2 | cycles/min | yes | Drift mode: one cycle is a pan/zoom out and back; a leg lasts 30 / speed seconds. |

### AUDIO

Every panel plays its own sound, simultaneously.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `audio.speech_policy` | Speech policy | enum | play / mute / exclude | mute |  |  | For clips whose audio screen found speech (audio.speech, or the flags number_sequence, email_like, introduces_self, possible_name, long_speech). play: sound as usual. mute: the picture plays, the sound does not (also in the reveal). exclude: such clips are never shown. Never randomized. |
| `audio.mute_unscreened` | Mute unscreened | bool | on / off | true |  |  | Mute clips whose audio.screened is not true (including clips with no audio record at all). |
| `audio.master` | Master | float | 0 to 1.5 (step 0.01) | 0.8 |  | yes | Master gain. |
| `audio.pan` | Spatial pan | bool | on / off | true |  |  | Pan each panel by its position on screen (along the strip direction). |
| `audio.pan_width` | Pan width | float | 0 to 1 (step 0.01) | 0.8 |  | yes | 1 = outermost panels fully left/right. |
| `audio.normalize` | Loudness normalise | bool | on / off | true |  |  | Gain each clip toward the target using its loudness_db (unknown loudness stays at unity). |
| `audio.norm_target_db` | Normalise target | float | -60 to -6 (step 0.5) | -30 | dB | yes | Target loudness for normalisation. Boost is capped at +20 dB. |
| `audio.size_gain` | Size to gain | float | 0 to 1 (step 0.01) | 0.5 |  | yes | Bigger panels are louder: gain = (panel share / mean share)^amount. |
| `audio.auto_trim` | Auto trim | bool | on / off | true |  |  | Scale the master by 1/sqrt(N) so many panels do not clip. |
| `audio.muted_panels` | Muted panels | multi | subset of 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | [] |  |  | Panels (1-based) that are silent. |
| `audio.solo_panels` | Solo panels | multi | subset of 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | [] |  |  | If any panel is soloed only soloed panels sound. |
| `audio.fade` | Fade length | float | 0 to 3 (step 0.01) | 0.4 | s | yes | Cross-fade when a panel changes clip (avoids clicks). |
| `audio.limiter` | Limiter | bool | on / off | true |  |  | Compressor/limiter before the output. |
| `audio.limiter_ceiling` | Limiter ceiling | float | -24 to 0 (step 0.5) | -3 | dB | yes | Threshold of the limiter. |

### REVEAL

What tapping a panel shows.

| id | label | type | range / options | default | unit | MOD | description |
|---|---|---|---|---|---|---|---|
| `reveal.action` | Tap action | enum | still / video / both | still |  |  | What tapping a panel shows: the original still, the full-frame video, or the still with the video inset. |
| `reveal.show_date` | Show date | bool | on / off | true |  |  | Show the capture date. |
| `reveal.show_tags` | Show tags | bool | on / off | true |  |  | Show tag chips on the reveal. |
| `reveal.show_window` | Outline window | bool | on / off | false |  |  | Outline, on the full still, the window the panel was showing ("where this panel was looking"). |
| `reveal.pause_others` | Pause others | bool | on / off | false |  |  | Pause the other panels while a reveal is open. |
| `reveal.animation` | Animation | enum | none / zoom / fade | zoom |  |  | zoom: expands from the panel's rectangle. |
| `reveal.anim_ms` | Animation time | float | 0 to 1500 (step 10) | 350 | ms | yes | Duration of the reveal animation. |

<!-- END CONFIG REFERENCE -->
