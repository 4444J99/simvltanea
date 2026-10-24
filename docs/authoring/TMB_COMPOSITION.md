# TMB composition

The TMB importer builds a local engineering edition from two authenticated
eight-second generations. Each generation remains a complete four-view atlas;
SIMVLTANEA gives the two atlases independent clocks with offsets of zero and one
second. Both layouts contain the full atlas. The edition lasts sixteen seconds,
so both sources wrap during playback.

The matching F6 stereo excerpts are muxed without re-encoding. Encoded video and
audio packet hashes, exact packet times and AAC priming must match the inputs.
Schema 1.1 enables per-loop gains and
layout-derived stereo panning. These recordings are stereo, not four-channel
ambisonic material. The accepted shared engine continues to drive panel poses.

## Build

Use a TMB checkout containing the pinned source history, accepted engine, and
the two private derivative generations. The importer refuses missing or changed
sources. Source revisions are fixed by this reviewed recipe. The consumer
worktree must be clean so its recorded commit identifies the code executed.
It does not download media or reconstruct missing private material.

```bash
PYTHONPATH=src python3 -m tools.editions.build_tmb_composition \
  --tmb-root /path/to/time-moment-brief \
  --output var/proofs/tmb-composition
```

The output must be a fresh directory inside the ignored proof lane. A sibling
staging directory is published atomically after every check succeeds; failed
builds leave no incomplete edition at the final path. Concurrent destinations
are preserved. The edition contains
the authoring model, composition state, muxed media, portable browser preview powered by
[`src/simvltanea/browser/browser.runtime.js`](../../src/simvltanea/browser/browser.runtime.js),
source admission and edition receipt. The receipt records the source revisions,
recipe digest, accepted engine commit, observed owner HEAD and every served
preview file's digest. Keep this output private and out of Git.

Serve the preview directory over local HTTP and click the composition to start
sound. Click again or press Space to pause. Resizing changes presentation and
panning while preserving media nodes and loop clocks.

## Verify

```bash
PYTHONPATH=src python3 -m unittest tools.editions.test_tmb_composition -v
```

The tests cover source admission, authenticated manifest reads, exact timing,
independent phases, orientation continuity, isolated holds, spatial gain and
receipt completeness. A real-media browser run is separate evidence: decoding,
audible signal, native wrap, pause/resume and orientation must be observed on
the built edition. A successful build alone does not establish those results or
artistic and hardware acceptance.
