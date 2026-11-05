# Browser compiler

`src/simvltanea/browser/browser.compiler.js` compiles a composition inside the
browser, without Python. It turns caller loops, their sources, and the authored
layouts into the plan that `browser.runtime.js` already plays. For every state
in its supported subset, the plan equals the output of Python `compile_plan`
exactly, including key order and the state hash. Anything outside the subset
throws a `CompilerError`. The compiler never returns a plan that differs from
Python's.

The file is a classic script without dependencies. It publishes
`globalThis.SimvltaneaCompiler` and supports `require()` in Node. All time and
geometry arithmetic uses exact `BigInt` rationals.

## API

| Function | Purpose |
| --- | --- |
| `buildState({sources, loops, layouts, frames, fps?, seed?})` | Returns a validated `visual-form-composition/v1` state |
| `compilePlan(state)` | Returns the same structure as Python `compile_plan(state)` |
| `compile(input)` | Shorthand for `compilePlan(buildState(input))` |
| `bindLayouts(pair, loopIds)` | Copies an authored pair onto caller loop IDs, in portrait cell order |
| `stagePreview(state, sizes)` | Applies the `build_preview` rebasing: `media/<sha256>.<ext>` paths, byte counts, and the portable state hash |
| `validateState(state)` | Validates without compiling |
| `stateDigest(state)` | SHA-256 of the state's canonical JSON, matching Python's `canonical_json` |

`buildState` inputs:

- `sources` items are `{id, path, sha256, duration, kind?}`. `kind` defaults to
  `video`; `still` requires a PNG or JPEG path.
- `loops` items are `{id, source, offset?, rate?, trim?, held?}`. Each loop names
  one source ID. Defaults are offset `0`, rate `1`, and an unheld clock. The
  selection period is the source duration and the epoch is zero.
- `layouts` is a `{portrait, landscape}` pair whose cells use the loop IDs.
- `fps` defaults to 24 and `seed` to 0. `frames` is required.

A drop-in page hashes each file, reads its duration, and converts that duration
to an exact rational itself. It then compiles and passes the plan to the runtime
through `window.compositionIO`:

```js
const C = SimvltaneaCompiler;
const ids = sources.map((_, i) => `loop-${i + 1}`);
const state = C.buildState({
  sources,
  frames: 240,
  loops: sources.map((source, i) => ({id: ids[i], source: source.id})),
  layouts: C.bindLayouts(bundle[String(sources.length)], ids),
});
const {plan} = C.stagePreview(state, sizes); // sizes: {sourceId: byteLength}
window.compositionIO = {plan: async () => plan, bytes, digest};
```

## Supported subset

- `schema_version` 1, engine `1.0.0`, and silent audio.
- Between 2 and 7 loops. This is the invariant: N independent loops, no filler,
  and no implicit duplication.
- Exactly one source in each loop bank. Every declared source is bound to exactly
  one loop. Source IDs and media digests are distinct. `allow_source_reuse` is
  false.
- Video and still sources. Each loop supports offset, rate, trim, and an initial
  held flag. Video rates stay within the runtime range of 1/16 to 8.
- `fps` from 1 to 60 and `frames` from 1 to 14400.
- Slice and seam are absent or disabled.

The compiler throws for anything else, with `error.unsupported` set to `true`.
That covers hold, reroll, swap, and move events; Audio v1.1; N outside 2 to 7;
multi-source banks; enabled slices or seams; and duplicate media. Rationals must be
integers or `"n/d"` strings. The compiler rejects decimal and exponent spellings,
floats, and non-finite numbers. Python accepts decimal strings, but the browser
runtime does not.

`src/simvltanea/browser/test_browser_compiler.py` tests both sides of this
boundary against Python with Node 22. It also plays compiled plans in the
unmodified runtime under Chrome.

## Layout bundle

The browser never copies geometry by hand. The authored pairs come from
`src/simvltanea/authoring/artifact001_layouts.py`, converted exactly as
`from_authoring_model` converts them. Policy forbids committing JSON under
`src/`, so the bundle is generated on demand:

```bash
PYTHONPATH=src python3 -m simvltanea.browser.layout_bundle > var/work/layouts.json
```

The output maps each count (`"2"` to `"7"`) to its `{portrait, landscape}` pair,
with loop IDs `loop-1` to `loop-N`. In Python, call
`simvltanea.browser.authored_layout_bundle()` or `authored_layouts(count)`.
Regenerate the bundle whenever the authored layouts change.
