# HANDOFF — Visual Form Canon: N-Loop Composition Engine → Rendered System → Historical Integration

Continue the Visual Form Canon / persona audiovisual-system work from the current **PR #9 implementation state**.

This is an **autonomous execution tranche** intended to run for a long stretch.

Do not stop after one commit, one test fix, one rendered artifact, one issue comment, or one intermediate milestone if further useful work remains executable.

Do not restart planning.

Do not return merely because the next step is obvious.

Move through successive gates until:

1. the requested system is substantially operational;
2. a genuine external dependency prevents further progress;
3. a safety/privacy boundary prevents further progress;
4. an irreversible/high-impact action requires user authorization;
5. or the remaining work specifically requires inaccessible hardware/software/media that cannot be reached remotely.

When one subtask completes, immediately identify and execute the next highest-leverage task within the established scope.

---

# 1. Canonical current state

Primary repository:

`organvm/portvs`

Canonical implementation directory:

`incubator/triptych-video-canon/`

Coordination:

- Issue #8 — `Recover visual-form ancestors and prove one normalized composition state`
- PR #7 — evolutionary-audit documentation, open/draft
- PR #9 — `feat: establish N-loop paired composition model`, open/draft

Current implementation branch:

`work/n-loop-paired-compositions-2026-09-05`

Known PR #9 checkpoint at last verification:

`74d21760a9c8ceb074ff4445724facea15c1c992`

Do not assume that SHA is still current.

**First action:** re-fetch repository, branch, issue, and PR state and reconcile any work that has happened since this handoff.

Do not create a competing implementation branch if PR #9 remains the correct active branch.

---

# 2. Governing artistic requirement

The project is fundamentally a composition of **independent video loops**.

For this project:

**N panels = N independent video-loop instances.**

Adding another panel means adding another video loop.

Do not interpret panels as decorative rectangles, duplicated viewports, filler tiles, automatically mirrored clips, or multiple windows onto one state object.

Each loop must retain its own:

- stable identity;
- source identity;
- playback position;
- trim/loop interval;
- rate;
- offset;
- deterministic selection state;
- interaction/event state;
- optional audio-routing state.

The spatial presentation is separate from this loop state.

---

# 3. Paired-orientation requirement

Every supported loop count requires **two deliberately authored compositions**:

- portrait / vertical;
- landscape / horizontal.

The initial required matrix is:

| N loops | Portrait | Landscape |
|---|---|---|
| 3 | required | required |
| 4 | required | required |
| 5 | required | required |
| 6 | required | required |

Six is not the architectural ceiling.

The engine must permit higher N through data/configuration without separate applications.

However:

**Do not claim support for N until both orientation designs exist and the relevant runtime/render checks pass.**

If multiple arrangement families exist for the same N, each arrangement family requires its own portrait/landscape pair.

A generic automatic grid is not equivalent to an authored composition.

The current layouts in PR #9 are **engineering fixtures**, not final artist-approved compositions.

Preserve that distinction.

---

# 4. Current implementation already present

PR #9 currently adds:

- `composition_model.py`
- `artifact001_layouts.py`
- `test_composition_model.py`
- `ARTIFACT_001_RECEIPT.md`

The model separates:

**loop/content/time state**

from:

**layout/presentation state**

It currently specifies model semantics for:

- hold;
- release;
- reroll;
- swap;
- move;
- seeded selection;
- serialization;
- independent local loop clocks.

The existing historical renderer:

`render_triptych.py`

remains unchanged and is still structurally based around:

`PANEL_NAMES = ("left", "middle", "right")`

Do not discard that renderer.

Use it as the concrete bridge from historical Triptych machinery into the generalized N-loop system.

---

# 5. Primary objective

Move PR #9 from:

**plausible renderer-agnostic model**

to:

**demonstrated audiovisual composition engine**

and then continue into historical-source integration and stronger runtime evidence.

The system should ultimately demonstrate:

`Composition State`
→ `Authored Layout`
→ `N independent loop timelines`
→ `Renderer`
→ `Portrait/Landscape moving artifact`
→ `Serialized reproducible state`
→ `Visual verification`

without separate applications for each N.

---

# 6. Autonomous execution sequence

Proceed through these phases continuously.

Do not ask for confirmation between phases unless an action crosses an explicit authorization boundary.

## PHASE A — Reconcile and baseline

1. Fetch:
   - current `main`;
   - PR #7;
   - PR #9;
   - issue #8;
   - active branch heads;
   - recent commits;
   - CI/workflow state if available.

2. Read applicable `AGENTS.md` and repository-specific instructions.

3. Confirm whether another agent/session has already modified PR #9.

4. Inspect the complete relevant implementation, not excerpts only.

5. Establish the historical Triptych baseline:
   - current CLI behavior;
   - manifest behavior;
   - dimensions;
   - source scheduling;
   - audio behavior;
   - output structure;
   - dry-run behavior;
   - actual renderer assumptions.

6. Run existing tests and baseline commands in an available execution environment.

Do not report tests as passing unless actually executed.

If no shell is available in the immediate environment, use the strongest available remote coding/execution route rather than stopping.

---

# 7. PHASE B — Harden the model before rendering

Run:

`python3 -m unittest -v test_composition_model.py`

Fix actual failures.

Then extend tests where necessary.

At minimum verify:

- unique loop IDs;
- exactly one placement per active loop;
- no dropped loops;
- no accidental duplicate placements;
- portrait/landscape layout pair required;
- serialization round-trip;
- schema-version validation;
- deterministic source selection;
- evaluation-order independence;
- independent loop clocks;
- targeted hold;
- release continuity;
- targeted reroll;
- source swap without clock reset;
- move affects presentation, not content state;
- malformed layout rejection;
- invalid trim ranges;
- missing sources;
- unsupported counts.

### Important continuity correction

The existing unit test for orientation changes proves only that layout lookup does not mutate time at a fixed clock.

Add stronger integration-level evidence for actual advancing playback:

`portrait @ t1`
→ `landscape @ t2`
→ `portrait @ t3`

where:

`t1 < t2 < t3`

Verify that every surviving loop advances continuously and is not restarted, rerolled, duplicated, or replaced by the orientation change.

---

# 8. PHASE C — Connect Composition to the real renderer

This is the central engineering gate.

Extend the existing FFmpeg-backed rendering path so that the normalized `Composition` model can drive it.

Do not create a second completely separate renderer solely for N-loop mode unless unavoidable.

Prefer extracting/generalizing existing primitives.

The renderer must obtain from composition/layout state:

- canvas dimensions;
- selected orientation;
- placements;
- z-order;
- crop/fit behavior;
- focal position;
- source;
- trim range;
- offset;
- rate;
- local playback time;
- hold state where relevant.

Preserve current Triptych behavior through a compatibility fixture or adapter.

The existing three-panel result should remain reproducible.

---

# 9. PHASE D — Synthetic moving source bank

Create a small deterministic test-media bank suitable for automated rendering.

Requirements:

- actual moving video;
- visually distinguishable loops;
- obvious loop identity;
- obvious time progression;
- no private/user media;
- no copyright ambiguity;
- compact enough for repeated CI/local execution.

Prefer programmatically generated fixtures where possible.

Each loop should make it visually obvious if:

- playback restarts;
- a source is duplicated;
- orientation changes reset time;
- loop identities get swapped;
- one panel disappears;
- cropping is incorrect.

Generate enough unique test loops to cover at least N=6 simultaneously.

---

# 10. PHASE E — Artifact 001: first real moving pair

Do not jump immediately to all eight exports.

First prove one real pair end-to-end.

Use N=3 unless another count is more useful after inspection.

Produce:

- portrait moving render;
- landscape moving render;
- corresponding reference stills;
- serialized composition state;
- source manifest;
- exact commands;
- output hashes;
- duration/frame/dimension facts.

Use the **same loop identities and same temporal interval** for the portrait and landscape versions.

Visually inspect both.

Verify:

- three independent loops visible;
- one-to-one mapping;
- no accidental duplicate loop instances;
- correct crop/fit behavior;
- continuous timing;
- intended spatial differences between orientations.

If incorrect, fix before expanding the matrix.

---

# 11. PHASE F — Full 3/4/5/6 paired family

Once the first pair is valid, render all:

- 3 portrait;
- 3 landscape;
- 4 portrait;
- 4 landscape;
- 5 portrait;
- 5 landscape;
- 6 portrait;
- 6 landscape.

That is the minimum Artifact 001 family.

For each:

- verify panel count;
- verify loop uniqueness;
- verify dimensions;
- inspect representative frames;
- verify timing;
- record hashes;
- preserve state manifest.

Do not call the geometry artist-approved.

Call it:

**synthetic authored engineering composition**

until the artist reviews it.

---

# 12. PHASE G — Orientation/runtime continuity

Static FFmpeg exports prove composition rendering but not responsive runtime behavior.

After render proof exists, test the state model under orientation changes in a live or simulated runtime.

Required behavior:

- same loop IDs;
- same source selections;
- same playback progression;
- no implicit reroll;
- no restart;
- no dropped panels;
- no duplicated panels;
- layout changes only presentation geometry.

Use actual viewport/container dimensions rather than:

`mobile = portrait`
`desktop = landscape`

Test at minimum:

- narrow portrait;
- wide landscape;
- tall desktop/browser window;
- horizontal mobile-like viewport.

Do not build a large frontend product unless necessary.

The goal is proof of state continuity.

---

# 13. PHASE H — Extendability beyond six

Once 3–6 work, test whether the **model and renderer** remain generic beyond six.

Do not immediately create final designs for arbitrary N.

Instead:

1. verify no hard-coded `3`, `4`, `5`, `6` assumptions remain in the generalized engine where they should not;
2. identify genuine performance/resource ceilings;
3. test one experimental higher count if feasible;
4. keep unsupported layout counts explicit.

The system should fail clearly when an authored layout pair does not exist.

Never silently reduce N due to performance constraints.

---

# 14. PHASE I — Historical archive archaeology

Continue historical inspection in parallel with engineering.

Do not block the synthetic engine on full historical reconstruction.

## Floating Points

Known archive root:

`/Mac/Design.dbx-computer-backup/floating_points_v1/`

Known objects include:

- `floating_points_V1.prproj`
- `floating_points_V2.prproj`
- `floating_points_V3.prproj`
- source/captured media
- audio
- sequence breakdown CSV
- archived project-tree records

Objectives:

- retrieve and hash representative source projects where possible;
- identify Premiere project format/signature;
- extract structural information using read-only methods;
- identify sequences;
- nested sequences;
- layers;
- masks;
- source assets;
- geometry;
- timing;
- opacity/blend behavior where recoverable;
- missing dependencies;
- render references.

Do not infer actual compositing behavior solely from sequence names.

## Up the Hill Backwards

Known objects include:

- Ableton `.als`;
- WAV/MP3;
- `up-the-hill-backwards.mp4`;
- Premiere-related archive material.

Objectives:

- inspect actual rendered video;
- establish verified panel count/topology;
- sample representative timestamps;
- establish timing relationships;
- identify exact project source if possible;
- distinguish audio-project evidence from visual-project evidence.

Do not promote “quad” from testimony to verified until the media demonstrates it.

## Triptych / First Circle

Keep separate:

- conceptual `TRIPTYCH.md`;
- archival `TripTicks.mov`;
- current Portvs video renderer;
- earlier photo-selector implementation;
- First Circle lineage.

Resolve equivalence only with evidence.

## Narcissus

Continue bounded searches.

Do not conflate:

`narcissus-&-echo-re-dux.pdf`

with the audiovisual Narcissus merely because the name overlaps.

---

# 15. PHASE J — Historical compatibility fixtures

As historical structures become verified, encode them as **separate compatibility fixtures** rather than rewriting historical claims into the generic engine.

For example:

- `triptych-historical`
- `up-the-hill-historical`
- `floating-points-derived-study`

Only create such names after enough evidence exists.

Distinguish:

- exact reconstruction;
- structural approximation;
- formal study;
- synthetic descendant.

Never label an approximation as the historical artwork.

---

# 16. PHASE K — Media-canon implications

As evidence accumulates, update the Visual Form Canon to distinguish:

**historical works**
from
**reusable formal principles**
from
**current engine capabilities**
from
**future extensions**

Potential reusable formal dimensions include:

- N simultaneous loops;
- spatial arrangement;
- hierarchy;
- equal/unequal panel weighting;
- independent clocks;
- nested media;
- opacity;
- overlap;
- masking;
- stochastic source selection;
- deterministic replay;
- audiovisual routing;
- interaction;
- audience control;
- capture/export.

Do not convert every historical feature into a mandatory engine feature.

Use historical evidence to expand the engine only where it serves the current project.

---

# 17. PHASE L — Audio boundary

Preserve existing audio behavior.

For this project:

**N video loops does not automatically mean N audible audio streams.**

Keep visual-loop count and audio-routing topology separable.

If existing video files contain audio:

- determine current behavior;
- make it explicit;
- avoid accidental multi-source cacophony;
- preserve muting/routing controls.

Do not build the full generative-audio system in this tranche unless it becomes the next direct blocker after the visual engine is operational.

Document appropriate extension seams toward:

- Ableton;
- Max for Live;
- Max/MSP;
- Alchemical Synthesizer;
- external modulation sources.

Do not implement all of them merely because they are future targets.

---

# 18. PHASE M — Repository integration

Keep the active implementation coherent.

Preferred approach:

- continue PR #9 for the bounded generalized-engine tranche;
- make logically grouped commits;
- keep PR #7 audit separate unless merging/rebasing becomes clearly justified;
- update issue #8 with real execution evidence;
- do not create redundant issues for work already coordinated there.

When a meaningful executable gate closes, update issue #8 with:

- commit;
- command;
- actual result;
- artifact location;
- remaining evidence boundary.

Do not spam issue comments for trivial edits.

---

# 19. Evidence discipline

Use the following hierarchy precisely:

### Located
A filename/path/metadata entry exists.

### Retrieved
Bytes were actually accessed.

### Hashed
Cryptographic hash recorded.

### Structurally inspected
Format/project structure was parsed or examined.

### Visually inspected
Media/render was actually viewed.

### Executed
Code/project ran.

### Verified
A specific behavioral claim was demonstrated by the appropriate evidence.

These are not interchangeable.

Examples:

A `.prproj` path in Dropbox:
**located**

A downloaded `.prproj`:
**retrieved**

A parsed project tree:
**structurally inspected**

A rendered video watched:
**visually inspected**

A renderer completing:
**executed**

“Four independent loops are visible and maintain timing”:
**verified only after appropriate visual/runtime evidence**

---

# 20. Privacy and archive boundaries

Do not:

- publish private Dropbox paths into public-facing artwork;
- expose signed Dropbox URLs;
- publish personal/private source media;
- commit raw archive files unless clearly appropriate;
- relocate/delete archive originals;
- expose credentials/secrets;
- turn private archive custody into public distribution.

Repository evidence documents may reference sanitized artifact identifiers where needed.

---

# 21. Mutation boundaries

Allowed:

- branch commits;
- tests;
- implementation;
- issue comments;
- draft PR updates;
- synthetic fixture generation;
- documentation directly supporting execution.

Do not automatically:

- merge PR #9;
- merge PR #7;
- publish artwork;
- deploy public-facing releases;
- post social content;
- alter unrelated repositories;
- delete/archive historical sources;
- change production infrastructure outside the necessary scope.

Leave final merge/release decisions for user review unless explicit authority is later provided.

---

# 22. Avoid documentation-as-progress

Do not produce another architecture document when code can be executed.

Do not produce another checklist when a test can be run.

Do not produce another mock specification when a render can be generated.

Do not produce another handoff while substantial executable work remains available.

Documentation is justified when it records:

- evidence;
- interfaces;
- decisions necessary for implementation;
- reproducibility;
- unresolved boundaries.

The unit of progress is:

**working behavior, verified evidence, closed gate, or artifact.**

---

# 23. Autonomous decision rule

For each completed task, ask internally:

> What is the next action that most reduces uncertainty or increases executable capability?

Then perform it.

Prefer, in order:

1. failing test → fix;
2. missing executable bridge → implement;
3. unrendered state → render;
4. uninspected render → inspect;
5. incomplete matrix → extend;
6. unverified runtime behavior → test;
7. known historical source → inspect;
8. newly established historical form → encode compatibility fixture;
9. missing provenance → record;
10. only then broader documentation.

Do not stop merely because one PR has become “good enough.”

---

# 24. Failure behavior

If something fails:

1. inspect the actual failure;
2. isolate root cause;
3. repair if within scope;
4. rerun;
5. record the actual outcome.

Do not interpret:

- command launch as success;
- zero-byte artifact as render;
- code presence as execution;
- test definition as passing test;
- PR creation as completed implementation;
- synthetic layout as artist approval.

If a dependency blocks progress, continue all independent work before stopping.

---

# 25. Long-run priority order

Unless evidence changes the dependency structure, use this order:

**Priority 1**
Execute and harden PR #9 tests.

**Priority 2**
Connect generalized composition state to FFmpeg.

**Priority 3**
Generate test-loop media bank.

**Priority 4**
Produce and inspect first 3-loop portrait/landscape pair.

**Priority 5**
Render full 3/4/5/6 paired family.

**Priority 6**
Test real orientation continuity.

**Priority 7**
Remove accidental fixed-N assumptions.

**Priority 8**
Inspect Up the Hill Backwards rendered media.

**Priority 9**
Inspect Floating Points project structure.

**Priority 10**
Resolve First Circle / Triptych ancestor evidence.

**Priority 11**
Continue bounded Narcissus recovery.

**Priority 12**
Create historical compatibility fixtures where evidence permits.

**Priority 13**
Update canon and coordination records from demonstrated facts.

---

# 26. Desired end state of this autonomous tranche

Push as far toward this state as the available environment permits:

### Engine

One generalized composition engine supports arbitrary authored N-loop layouts.

### Initial layouts

3, 4, 5, and 6 each have portrait and landscape engineering compositions.

### Temporal behavior

Every loop has an independent clock and survives presentation changes.

### Rendering

The normalized state drives real moving outputs.

### Reproduction

State + media manifest + seed + versions reproduce the composition.

### Interaction semantics

Hold, release, reroll, swap, and move are deterministic and tested.

### Evidence

Rendered outputs are visually inspected and hashes recorded.

### Historical corpus

Floating Points and Up the Hill Backwards move from archive-location evidence toward structural/visual verification.

### Lineage

Historical derivation is claimed only where evidence supports it.

### Repository state

PR #9 contains substantive executable evidence and is reviewable without false completion claims.

---

# 27. Final reporting rule

Do not end the autonomous stretch with a generic summary.

Return an **execution receipt** containing:

- current branch;
- final head SHA;
- PR state;
- commits created;
- files changed;
- tests actually run;
- passing/failing counts;
- render commands;
- artifacts actually produced;
- hashes/dimensions/durations;
- visual inspection findings;
- runtime/orientation findings;
- historical sources inspected;
- evidence states promoted;
- evidence states still unresolved;
- issue/PR updates made;
- blockers;
- next exact executable gate.

Separate clearly:

**completed**
**partially completed**
**blocked**
**not attempted because lower priority**

Do not claim future work has been done.

---

# 28. Governing principle

This tranche should convert the current system from:

**a model of the artwork**

into:

**a functioning instrument capable of producing the artwork.**

Continue autonomously through successive executable gates for as long as meaningful remote work remains.