# Browser compiler

`src/simvltanea/browser/browser.compiler.js` compiles a composition inside the
browser, without Python. It turns caller loops, their sources, and a layout pair
(authored, strips, or a visitor's own layout file) into the plan that
`browser.runtime.js` already plays. For every state
in its supported subset, the plan equals the output of Python `compile_plan`
exactly, including key order and the state hash. Everything else is a
refusal: the compiler throws a `CompilerError` and never returns a plan that
differs from Python's.

The file is a classic script without dependencies. It publishes
`globalThis.SimvltaneaCompiler` and supports `require()` in Node. All time and
geometry arithmetic uses exact `BigInt` rationals.

## API

| Function | Purpose |
| --- | --- |
| `buildState({sources, loops, layouts, frames, fps?, seed?, slice?})` | Returns a validated `visual-form-composition/v1` state |
| `compilePlan(state)` | Returns the same structure as Python `compile_plan(state)` |
| `compile(input)` | Shorthand for `compilePlan(buildState(input))` |
| `bindLayouts(pair, loopIds)` | Copies a layout pair onto caller loop IDs, in portrait cell order |
| `stagePreview(state, sizes)` | Applies the `build_preview` rebasing: `media/<sha256>.<ext>` paths, byte counts, and the portable state hash |
| `validateState(state)` | Validates without compiling |
| `stateDigest(state)` | SHA-256 of the state's canonical JSON, matching Python's `canonical_json` |
| `layoutFamilies(bundle)` | The families a layout bundle offers and the loop counts of each, for either bundle format |
| `layoutEntry(bundle, family, count)` | `{layouts, slice, adjacency}` for one count of one family |
| `stripsLayouts(count, preset?, name?)` | Python `strips_layouts`: the strips pair for 1 to 12 loops |
| `stripsSlice(count, preset?, name?)` | Python `strips_slice`: the state-wide zoom slice for that count |
| `adjacency(cells)` | Python `adjacency`: the exact shared edges between cells, in draw order |
| `validateLayoutPair(pair, loopIds?, {source, count}?)` | Python `validate_layout_pair` |
| `loadLayoutFile(text, name?)`, `loadLayoutBytes(bytes, name?)` | Python `load_layout_file` for a preset or pair file the caller has read |
| `describeLayoutFile(data, name?)` | `{kind, name, counts}` of a loaded layout file |
| `layoutFromFile(data, count, name?)` | `{layouts, slice}` that a loaded file gives `count` loops, with canonical rationals |

`buildState` inputs:

- `sources` items are `{id, path, sha256, duration, kind?}`. `kind` defaults to
  `video`; `still` requires a PNG or JPEG path.
- `loops` items are `{id, source, offset?, rate?, trim?, held?}`. Each loop names
  one source ID. Defaults are offset `0`, rate `1`, and an unheld clock. The
  selection period is the source duration and the epoch is zero.
- `layouts` is a `{portrait, landscape}` pair whose cells use the loop IDs.
- `slice` is the optional state-wide slice, for example the zoom that a strips
  bundle entry or `stripsSlice` gives.
- `fps` defaults to 24 and `seed` to 0. `frames` is required.

A drop-in page hashes each file, reads its duration, and converts that duration
to an exact rational itself. It then compiles and passes the plan to the runtime
through `window.compositionIO`:

```js
const C = SimvltaneaCompiler;
const ids = sources.map((_, i) => `loop-${i + 1}`);
// bundle: layouts.json from `layout_bundle --format 2`; the strips family covers 1 to 12.
const entry = C.layoutEntry(bundle, 'strips', sources.length);
const state = C.buildState({
  sources,
  frames: 240,
  loops: sources.map((source, i) => ({id: ids[i], source: source.id})),
  layouts: entry.layouts, // strips cells already use loop-1 to loop-N
  slice: entry.slice,
});
const {plan} = C.stagePreview(state, sizes); // sizes: {sourceId: byteLength}
window.compositionIO = {plan: async () => plan, bytes, digest};
```

For an authored pair, or any pair whose cells use other loop names, pass
`C.bindLayouts(entry.layouts, ids)` instead and omit `slice`.

## Supported subset

- `schema_version` 1, engine `1.0.0`, and silent audio.
- Between 1 and 12 loops. This is the browser subset for every family. The
  counts each family offers come from the layout bundle, never from a constant
  in the compiler: strips 1 to 12, authored 2 to 7. The invariant holds: N
  independent loops, no filler, and no implicit duplication.
- Exactly one source in each loop bank. Every declared source is bound to exactly
  one loop. Source IDs and media digests are distinct. `allow_source_reuse` is
  false.
- Video and still sources. Each loop supports offset, rate, trim, and an initial
  held flag. Video rates stay within the runtime range of 1/16 to 8.
- `fps` from 1 to 60 and `frames` from 1 to 14400.
- Layouts may carry the optional `full_bleed`, `presentation`, and cell
  `lateral_offset` declarations. They are checked as Python's
  `validate_layout_pair` checks them, and every other key is refused.
- The state-wide slice, enabled or not. With it enabled, every span carries the
  `slice_rect` that `composition.slice_rect` picks: a `sha256-counter-v1`
  window per loop and per selection period, so the window moves at each wrap
  of the loop's local time. A new window starts a new span, as in Python.
- The seam is absent or disabled.

`src/simvltanea/browser/test_browser_compiler.py` tests both sides of this
boundary against Python with Node 22. Slice plans are compared for 1, 2, 3, 5,
8, and 12 loops, with and without a slice, both orientations, several frame
rates, and every period wrap. It also plays compiled plans in the unmodified
runtime under Chrome.

## Refusals

Every input outside the subset throws a `CompilerError`. It is always a refusal
and never a wrong plan. The `error.unsupported` flag tells you which kind:

- `unsupported === true`: Python compiles the state, but the browser compiler
  does not cover it. That covers hold, reroll, swap, and move events; Audio v1.1;
  N outside 1 to 12; multi-source banks; enabled seams; and duplicate media.
  A slice on one loop is not part of the state schema, so Python refuses it too.
- `unsupported === false`: either Python refuses the state too, or Python reads
  a spelling or value that the compiler will not. The second group is `'+1/2'`,
  `' 1/2'`, `'1_0/3'`, non-ASCII digits, decimal strings such as `'1.5'`,
  exponent strings such as `'3e0'`, and seeds above 2^53. The browser runtime
  does not read the decimal and exponent strings either.

Layout errors also carry `error.code`, the stable reason code of Python's
`LayoutError` (for example `full-bleed-coverage` or `overlap-px`).

Rationals must be integers or `"n/d"` strings, optionally negative. Floats and
non-finite numbers are rejected. A numerator or denominator of more than 4300
digits is rejected, leading zeros included, because Python's `Fraction()` refuses
it too.

### Number spellings in JSON files

`compilePlan` receives JavaScript values, not JSON text. `JSON.parse` turns the
spellings `8.0`, `2.4e1` and `1e0` into the integers 8, 24 and 1 before the
compiler runs, so the compiler cannot see them. Python's `json.loads` keeps them
as floats and refuses the state. The plan and `state_sha256` describe the integer
state that `JSON.parse` produced. A caller that needs Python's exact strictness
must reject these spellings in the raw text before parsing. One line that does
this, after blanking out strings:

```js
if (/\d[.eE]/.test(text.replace(/"(?:[^"\\]|\\.)*"/g, '""'))) throw new Error('float spelling');
```

### Objects

Only plain objects are accepted: the prototype must be `Object.prototype` or
`null`. A key counts only when it is an own enumerable property. This keeps an
inherited property from changing a plan without changing `state_sha256`. Objects
built with `Object.create(proto)` or from a class are refused. Copy objects that
come from another realm with `structuredClone` first.

## Layout files

`loadLayoutFile(text, name)` mirrors Python `load_layout_file`. It accepts a
`simvltanea.layout-preset/1` file, whose every count is expanded and
validated, and a `simvltanea.layout-pair/1` file. The text is parsed with the
strictness of Python's `json.loads` and the loader's hooks. Duplicate keys and
`NaN` or `Infinity` are errors. Numbers spelled `2.0` or `1e3` stay floats, so
they fail where an integer is required. Integers stay exact. Each error names
the file, and where known the count, orientation, and cell index. Each error
also has the same `code` as in Python. The parity tests hold its message to
Python's, word for word, except the wording of JSON syntax errors, which
follows each runtime's decoder.

Layout files accept every ASCII spelling that Python's `Fraction()` reads,
such as `"0.5"`, `" 1/3 "`, `"1_000"`, or `"25E-1"`. One difference is
deliberate: digits outside ASCII, which Python reads, are refused in JavaScript
with the same code. `layoutFromFile` returns canonical `"n/d"` strings, so a
state built from any file compiles under the strict rules above.

`stripsLayouts` and `stripsSlice` expand a preset with exact `BigInt`
rationals. The expansion covers the direction and order per orientation,
weights, focal points, the zoom curve and table, quantum, and minimum zoom. It
also covers the lateral jitter, from `sha256-counter-v1` over `[rng, preset
name, N, orientation, "jitter", k]` and quantised to 1/1000. The canonical JSON
is byte-identical to Python `strips_layouts` and `strips_slice` for
`examples/layout-presets/strips.json` and every valid file in
`fixtures/layouts/`. The invalid files there fail with Python's code.

## Layout bundle

The browser never copies geometry by hand. The authored pairs come from
`src/simvltanea/authoring/artifact001_layouts.py`, converted exactly as
`from_authoring_model` converts them. The strips pairs, slices, and adjacency
lists come from `strips_layouts`, `strips_slice`, and `adjacency`. Policy
forbids committing JSON under `src/`, so the bundle is generated on demand:

```bash
PYTHONPATH=src python3 -m simvltanea.browser.layout_bundle > var/work/layouts.json
PYTHONPATH=src python3 -m simvltanea.browser.layout_bundle --format 2 > var/work/layouts-v2.json
```

Without a flag, the output is unchanged, byte for byte: it maps each authored
count (`"2"` to `"7"`) to its `{portrait, landscape}` pair, with loop IDs
`loop-1` to `loop-N`. `--format 2` emits `simvltanea.layout-bundle/2`:

```json
{
  "format": "simvltanea.layout-bundle/2",
  "default_family": "strips",
  "families": {
    "authored": {"counts": {"2": {"portrait": {}, "landscape": {}}}},
    "strips": {
      "preset": {"format": "simvltanea.layout-preset/1", "name": "strips"},
      "counts": {
        "5": {
          "portrait": {}, "landscape": {},
          "slice": {"enabled": true, "width": "41/125", "height": "41/125"},
          "adjacency": {"portrait": [], "landscape": []}
        }
      }
    }
  }
}
```

The empty objects and arrays stand for the full values. `authored.counts`
holds 2 to 7 and `strips.counts` holds 1 to 12. `layoutFamilies` and
`layoutEntry` read both formats; a legacy bundle is the authored family. A
count that a family lacks is refused, never filled from another family. In
Python, call `simvltanea.browser.authored_layout_bundle()`,
`authored_layouts(count)`, or `layout_bundle_v2()`. Regenerate the bundle
whenever the layouts change.
