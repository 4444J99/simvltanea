---
title: "Recovering TripTicks to Configurable Video Panels "
date: "2026-09-10T12:37:44 (UTC -04:00)"
source: x.com
---
## Q: 


## A: 
40 sources

## Q: 
Explore N-loop temporal offset mechanics

## A: 
Offset is per-loop local time, not a shared stagger schedule. The recovered system has two layers that agree on that point and disagree on a few details.

## What “offset” is

Each loop has its own clock. Composition time is shared; media time is not.

Authoring model (composition_model.LoopState.media_time):

$t_{\text{media}}(c) = \begin{cases} t_{\text{in}} + o + c\cdot r & \text{unheld}\\ t_{\text{in}} + o + c_{\text{hold}}\cdot r & \text{held} \end{cases}$

If a trim-out exists, that value wraps inside $[t_{\text{in}}, t_{\text{out}})$:

$t_{\text{in}} + \bigl((t_{\text{media}} - t_{\text{in}}) \bmod (t_{\text{out}}-t_{\text{in}})\bigr)$

Compiled replay (composition.local_time / source_offset):

$t_{\text{local}}(f) = o + \mathbf{1}_{\neg\text{held}}\cdot\frac{f-a}{\text{fps}}\cdot r$$t_{\text{src}} = \begin{cases} 0 & \text{still}\\ t_{\text{low}} + (t_{\text{local}} \bmod (t_{\text{high}}-t_{\text{low}})) & \text{video} \end{cases}$

offset $o$ is the loop’s phase at composition time 0. rate $r$ is how fast that local clock runs. trim is the playable window inside the source. They are separate fields.

## Artifact 001’s authored phases

Layouts stamp a unique offset and rate on each loop:

```language-41:41:/tmp/simvltanea/artifact001_layouts.py
LoopState(id=f"loop-{i+1}", source=f"fixtures/loop-{i+1}.mp4", rate=1.0 + i * .07, offset=i * .31, selection_seed=100 + i)
```

For N=6 at composition clocks 0 / 1.5 / 3:

| loop | rate | offset | $t=0$ | $t=1.5$ | $t=3$ | $t=1.5 \bmod 3$ |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1.00 | 0.00 | 0.000 | 1.500 | 3.000 | 1.500 |
| 2 | 1.07 | 0.31 | 0.310 | 1.915 | 3.520 | 1.915 |
| 3 | 1.14 | 0.62 | 0.620 | 2.330 | 4.040 | 2.330 |
| 4 | 1.21 | 0.93 | 0.930 | 2.745 | 4.560 | 2.745 |
| 5 | 1.28 | 1.24 | 1.240 | 3.160 | 5.080 | 0.160 |
| 6 | 1.35 | 1.55 | 1.550 | 3.575 | 5.600 | 0.575 |

That last column is what the adapter checks against compiled source_offset on 3-second synthetic sources. Adding loop 6 does not rewrite loops 1–5; their media times at the same clock stay identical.

## Independence rules

*   One global composition clock / frame index.
*   N local clocks. A change to loop $k$ must not move loop $j$.
*   Orientation reads a layout; it does not recompute media_time.
*   swap exchanges sources, not offsets or rates.
*   move changes a rectangle, not time.
*   reroll / epoch change bank selection, not the clock.

That is the difference from the legacy three-panel canon. Legacy fixed timing used source_offset = panel_index \* phrase_seconds and let clips migrate left→middle→right. N-loop identity stays put; only its local time advances.

## Hold rebases offset; it does not pause the composition

Authoring hold at clock 3, release at 8, loop-1 rate 1:

*   unheld $t=3$: 3.0
*   held $t=8$: still 3.0 (held_at=3, offset unchanged)
*   released $t=8$: still 3.0, but offset becomes \-5.0
*   released $t=10$: 5.0 (resumed, no catch-up)
*   loop-2 at $t=8$: 8.87 before and after

The release formula is:

$o \leftarrow o + (c_{\text{hold}} - c_{\text{now}})\cdot r$

Negative offsets are legal in the authoring model. The compiler rejects offset < 0 and instead freezes by baking local_time into offset, setting anchor to the event frame, and flipping held. Release is hold with value=false: same bake, then the clock runs again from that anchor. Same visible continuity, different stored numbers.

## Offset also drives source choice

Compiled choose_source does not use wall time. It uses local time:

$\text{cycle} = \bigl\lfloor t_{\text{local}} / \text{period} \bigr\rfloor$

then hashes (rng, seed, loop_id, epoch, cycle, bank). Shifting offset can change which bank member is current without touching any other loop. Stills ignore local time and report source_offset=0.

## How the renderer consumes it

compile_segments walks every frame. A new FFmpeg segment starts only when continuity breaks: identity/source/kind/rate/held change, or source_offset fails to advance by exactly $r/\text{fps}$. Held and still loops must keep the same source_offset. The panel handed to FFmpeg is that loop’s source_offset at the segment start; clocked=True means the renderer trims from that point rather than using the old left/middle/right phrase schedule.

Trim example from the tests: trim=['1','2'], default offset 0, rate 1, frame 24 at 24 fps → source_offset='1'. Local time 1 wraps onto the in-point of a 1-second window.

## Constraints and seams

| Rule | Where |
| --- | --- |
| Authoring offset may be any finite float, including negative after release | LoopState.validate |
| Compiled offset must be $\ge 0$ | validate_state |
| Compiled rate $\in (0,8]$ | validate_state |
| Adapter copies authoring offset/rate as rationals, but only from an unheld initial snapshot | from_authoring_model |
| Applied authoring event history is not translated | fails closed |
| Orientation / viewport never writes clocks | presentation_at |
| No panel is dropped to keep time aligned | segment guard fails instead |

What this is not: a musical canon that passes one clip across panels, a single shared delay line, or a guarantee of frame-exact browser clocks. Offset is authored phase on independent loops. Simultaneous coexistence is the product of those phases, not of one stagger algorithm.

## Q: 
Explore source bank selection logic

## A: 
Bank selection is compiled, deterministic, and per-loop. The authoring snapshot has a weaker, incompatible sampler. The browser does not choose sources at all.

## Two selectors, one contract

**Authoring (composition_model.choose_source)** is a snapshot pick, not a timeline:

```language-195:200:/tmp/simvltanea/composition_model.py
def choose_source(self, loop_id: str, ordered_bank: tuple[str, ...]) -> str:
        if not ordered_bank:
            raise ValueError("media bank cannot be empty")
        loop = next(loop for loop in self.loops if loop.id == loop_id)
        rng = random.Random(f"{self.seed}:{loop.selection_seed}:{loop.reroll_index}:{loop.id}")
        return ordered_bank[rng.randrange(len(ordered_bank))]
```

Same inputs always yield the same member. Call order does not matter. Time does not matter. reroll only bumps that loop’s reroll_index. swap exchanges source, selection_seed, and reroll_index, not clocks.

**Compiled replay (composition.choose_source)** is the versioned engine:

```language-240:246:/tmp/simvltanea/composition.py
def choose_source(state: dict, loop: dict, frame: int) -> str:
    if loop.get("pin") is not None:
        return loop["pin"]
    cycle = int(local_time(loop, frame, state["fps"]) // rational(loop["period"], "period"))
    payload = [RNG, state["seed"], loop["id"], loop["epoch"], cycle, loop["bank"]]
    value = int.from_bytes(hashlib.sha256(canonical_json(payload).encode("utf-8")).digest(), "big")
    return loop["bank"][value % len(loop["bank"])]
```

RNG is the string sha256-counter-v1. The hash is stateless. There is no random.Random stream to consume out of order.

The adapter between them is explicit about the break: it does **not** translate the old Mersenne Twister pick. Each authored loop becomes a one-item bank of its already-resolved source, epoch=0, period=source.duration. Event history is refused.

The browser runtime only plays a compiled plan of spans. It checks hashes and offsets; it never hashes a bank.

## What the hash actually keys

| Input | Effect |
| --- | --- |
| sha256-counter-v1 | algorithm tag; other rng values fail validation |
| composition seed | global family of draws; clocks unchanged |
| loop["id"] | two loops with the same bank still diverge |
| loop["epoch"] | reroll salt |
| cycle | floor of local time / period |
| loop["bank"] | ordered ID list; order is part of the digest **and** the index |

So selection is:

$\text{cycle}(f)=\Bigl\lfloor t_{\text{local}}(f)\,/\,\text{period}\Bigr\rfloor$$i = \operatorname{SHA256}(\operatorname{canon}([\text{rng},\text{seed},\text{id},\text{epoch},\text{cycle},\text{bank}])) \bmod |bank|$

Bank rules: nonempty, unique IDs, every ID exists in sources. Duplicates inside one bank are illegal. period > 0. epoch is a nonnegative int.

## Cycle is local time, not wall time

A shared three-source bank, period=1, rate=1, seed 444499:

| frame | local | cycle | sources |
| --- | --- | --- | --- |
| 0–23 | 0–0.958 | 0 | media-2, media-1, media-2 |
| 24–47 | 1–1.958 | 1 | media-3, media-2, media-1 |
| 48 | 2 | 2 | media-1, media-3, media-1 |

Same seed, reversed bank order at frame 24: media-1, media-3, media-3. Seed 7 at frame 24: media-2, media-1, media-3. Locals stay identical; only the chosen IDs move.

Hold freezes t_local, so cycle freezes, so the source stops changing. Sibling loops keep advancing. That is why hold is a content event for the compiler: a new segment starts when source would have flipped and did not, or when it later resumes.

## Pin vs epoch

pin is runtime-only. resolve_at starts every loop at pin=None. It is never stored in validated state JSON.

*   **swap at frame $f$** sets  
    a.pin = choose_source(b, f)  
    b.pin = choose_source(a, f)  
    That is the source each loop _would choose at $f$_, not the source it showed at $f-1$. Banks are not exchanged. Clocks are not exchanged. A pin can name a source that is **not** in the destination loop’s bank.
*   The pin then sticks across later cycles. After a swap at 24 in the shared-bank demo, loop-1 stays media-2 at frame 48 even though an unpinned draw there is media-1.
*   **reroll** does epoch += 1 and pin = None. The loop hashes again with the new epoch at the current cycle. Only that loop changes.

Still-controls fixture (allow_source_reuse=true):

*   loop-1 bank ['still']
*   loop-2 bank ['media-2','media-3']
*   loop-3 bank ['media-3']
*   events: hold loop-2 24–48, reroll loop-2 at 60, swap 2↔3 at 84

Loop-2’s epoch becomes 1 at frame 60; its local time is untouched. Loop-1 and loop-3 are bit-identical to the unreroled resolve. Swap then pins whatever each would pick at 84; both happen to resolve to media-3 here because loop-3’s bank is a singleton.

Authoring swap is different: it really exchanges bound source plus selection salts. No pin, no cycle.

## Reuse is a post-choice guard

After every loop has a source, if allow_source_reuse is false:

*   resolved source IDs must be unique
*   resolved source SHA-256s must be unique

Same bytes under two IDs still fail. Validation also runs resolve_at at frame 0 and every event frame, so an implicit collision fails before encode. Artifact 001 states default this flag to false and give each loop a singleton bank. The still-controls file is the documented exception; it turns the flag on because loop-2’s bank overlaps loop-3.

Trim is checked against **every** bank member at validate time, and again against the _resolved_ source at replay (swapped source does not fit loop trim). A pin to a shorter clip can fail even if the loop’s own bank was legal.

## What selection does not do

*   It does not consult wall clock or Python call order. Reversing the loop array changes the _list order_ of resolve_at output, not the per-id choice. Tests compare dicts keyed by loop id.
*   It does not live in the browser. Source changes there happen only when a compiled span’s source field changes.
*   It does not pick a new file every frame. Continuity requires the same source until cycle, epoch, pin, or hold changes it; that cut starts a new FFmpeg segment.
*   It does not implement weighted banks, “avoid last pick,” or exclusive assignment across loops. Collision avoidance is only the reuse flag, and it is all-or-nothing.
*   It does not keep authoring random.Random and compiled SHA-256 interchangeable. That is a hard adapter refusal, not a missing test.

Net: a loop owns an ordered bank and a local-time cycle counter. The engine maps (seed, id, epoch, cycle, bank) to one member. Hold freezes the cycle. Swap pins two resolved IDs. Reroll breaks the pin and salts the hash. Everything else is presentation.

## Q: 
Investigate local time calculation

## A: 
Local time is the loop’s unbounded phase clock. Media playback position is a later wrap of that clock. Those two numbers are not the same field.

## Compiled formula

Replay never uses wall time. Every query is a frame index plus saved state.

```language-235:237:/tmp/simvltanea/composition.py
def local_time(loop: dict, frame: int, fps: int) -> Fraction:
    elapsed = Fraction(0) if loop["held"] else Fraction(frame - loop["anchor"], fps) * rational(loop["rate"], "rate")
    return rational(loop["offset"], "offset") + elapsed
```$t_{\text{local}}(f)= o + \begin{cases} 0 & \text{if held}\\ \dfrac{f-a}{\text{fps}}\cdot r & \text{otherwise} \end{cases}$

Initial replay copies each loop and sets anchor=0, pin=None. So before any hold:

$t_{\text{local}}(f)=o+\frac{f}{\text{fps}}\cdot r$

All of $o$, $r$, and the result are Fractions. JSON stores them as rational strings (31/100, not 0.31). Floats are rejected at validate time.

resolve_at allows $f\in[0,F]$, so frame $F$ (one past the last encoded frame) is a legal query. Artifact 001 is $F=144$, fps $24$; frame 144 is exactly 6 seconds.

## Authoring formula

Authoring talks seconds, not frames, and uses IEEE floats:

$t_{\text{media}}(c)=t_{\text{in}}+o+e\cdot r,\quad e=\begin{cases}c_{\text{hold}}& \text{held}\\c&\text{otherwise}\end{cases}$

If trim_out is set it wraps _inside_ media_time. If not, authoring local time is also unbounded. Artifact 001 loops have no trim, so at clock $c=f/24$:

$t_{\text{media}}(c)=t_{\text{local}}(f)$

Checked at frame 36 / 1.5s: loop-2 is 383/200 on both sides (1.915). The adapter rounds authored floats to nine decimals before Fraction, which is why those rationals match i\*0.31 and 1+i\*0.07.

## Local does not wrap. Source offset does.

After local time is computed:

$t_{\text{src}}= \begin{cases} 0 & \text{still}\\ t_{\text{low}}+(t_{\text{local}}\bmod(t_{\text{high}}-t_{\text{low}})) & \text{video} \end{cases}$

Default window is [0, duration]. Artifact sources are 3s, so at frame 36 loop-5:

| field | value |
| --- | --- |
| local | 79/25 = 3.16 |
| source_offset | 4/25 = 0.16 |
| authoring media_time(1.5) | 3.16 |
| media_time % 3 | 0.16 |

The adapter test compares media_time(1.5) % 3 to source_offset, not to local. That is the intended split.

Trim [1,2] on loop-1 (offset 0, rate 1):

| frame | local | source_offset |
| --- | --- | --- |
| 0 | 0 | 1 |
| 12 | 1/2 | 3/2 |
| 24 | 1 | 1 |
| 36 | 3/2 | 3/2 |
| 48 | 2 | 1 |

Local climbs through 0, 0.5, 1, 1.5, 2. The playhead stays inside [1,2). Cycle for bank selection uses **local**, so this loop still changes cycle every period seconds of local time even when the file playhead is wrapping a one-second window.

Stills keep advancing local (period/cycle still exist) but force source_offset=0. Loop-1 in still-controls is local 0,1,2 at frames 0,24,48 with source offset always 0.

## Hold rebases the stored offset, then freezes elapsed

A compiled hold event at frame $f$:

1.  write offset ← local_time(now)
2.  write anchor ← f
3.  write held ← value

While held is true, elapsed is zero, so later queries return that baked offset. Release is the same event with value=false: bake current local into offset, move the anchor to now, clear held. Time resumes from that local value. No catch-up.

Hold at 24, release at 72, loop-1 rate 1 offset 0:

| frame | local | held | loop-2 local |
| --- | --- | --- | --- |
| 23 | 23/24 | false | 641/480 |
| 24 | 1 | true | 69/50 |
| 60 | 1 | true | 597/200 |
| 72 | 1 | false | 88/25 |
| 73 | 25/24 | false | 1711/480 |
| 96 | 2 | false | 459/100 |

Authoring does the same visible thing with different storage: held_at=1.0 leaves offset at 0; release at 3.0 sets offset=-2.0. Both give media/local 1 at t=3 and 2 at t=4. Compiler cannot store that negative offset; it keeps a nonnegative baked offset plus a new anchor.

Reroll and swap do not write local time. Tests assert local is identical to the unreroled / unswapped resolve.

## What is not in the clock

*   Viewport and orientation. Frames 24/48/72 across portrait and landscape still report loop-1 locals '1','2','3'.
*   Adding a loop. States 5 and 6 share locals for loops 1–5 at frames 0, 55, 143.
*   Bank selection, except that cycle = floor(local / period) reads this clock.
*   Layout move.

## Who consumes which number

**FFmpeg export** gets source_offset at the segment start, not local. Clocked panels do trim=start={source_offset}. Held or still panels then freeze that single frame with loop. Continuity between frames requires source_offset to advance by exactly $r/\text{fps}$ unless held or still, in which case it must stay put. A wrap (3 → 0 at frame 72 for loop-1) is a discontinuity, so a new segment starts.

**Browser** also never sees local. On span activation:

```language-97:99:/tmp/simvltanea/browser_runtime.js
const elapsed = (frame - span.frame) / runtime.plan.fps;
    const target = number(span.source_offset) + (span.held ? 0 : elapsed * number(span.rate));
```

That is the compiled formula again, but starting from the already-wrapped source_offset at the span’s first frame. Between spans the <video> element just plays at playbackRate=r. Seek only happens at span boundaries. Browser validation further requires source_offset < duration, which is true of the wrapped field and would not be true of raw local time after one period.

## Practical reading

When you inspect a resolved loop:

*   local — how far this loop’s private clock has run, including holds as pauses of _that_ clock only.
*   source_offset — where to seek in the current file.
*   rate — how fast both clocks run when unheld.
*   held — whether elapsed is currently forced to zero.

If those two time fields disagree, the loop has wrapped or is a still. That is expected, not a desync.

## Q: 
Investigate bank selection cycle logic

## A: 
Cycle is the only time index the compiled selector uses. It is not a frame number, not a wrap count inside the file, and it does not exist in the authoring snapshot.

## Definition

```language-240:246:/tmp/simvltanea/composition.py
def choose_source(state: dict, loop: dict, frame: int) -> str:
    if loop.get("pin") is not None:
        return loop["pin"]
    cycle = int(local_time(loop, frame, state["fps"]) // rational(loop["period"], "period"))
    payload = [RNG, state["seed"], loop["id"], loop["epoch"], cycle, loop["bank"]]
    value = int.from_bytes(hashlib.sha256(canonical_json(payload).encode("utf-8")).digest(), "big")
    return loop["bank"][value % len(loop["bank"])]
```$\operatorname{cycle}(f)=\left\lfloor\frac{t_{\text{local}}(f)}{\text{period}}\right\rfloor$

// on Fraction is floor division. int(...) then yields a Python int for the hash payload. For compiler state this is safe: offset ≥ 0 and rate > 0, so local time is nonnegative and floor equals truncation. A negative local would floor the other way (\-1/2 // 1 = -1) while int(Fraction) would truncate toward zero. The compiler refuses that case.

period is an independent rational, defaulted by the adapter to **source duration**, not to composition length. It is not required to equal duration, trim length, or 1 second.

## When cycle increments

Unheld, t_local = offset + (f / fps) \* rate, so the next boundary is the smallest frame with

$o+\frac{f}{\text{fps}}r \ge (k+1)\cdot\text{period}$

Worked cases from state-3 mutated to a shared 3-source bank:

| knobs | first flip | meaning |
| --- | --- | --- |
| period=1, offset=0, rate=1 | frame 24 | one cycle per second |
| period=1, offset=1/2, rate=1 | frame 12 | already halfway through cycle 0 |
| period=1, offset=0, rate=2 | frame 12 | local runs twice as fast |
| period=5/2, offset=0, rate=1 | frame 60 | non-integer period is exact |

Shared-bank source lists at those exact frames:

*   cycle 0 (f=0): media-2, media-1, media-2
*   cycle 1 (f=24): media-3, media-2, media-1
*   cycle 2 (f=48): media-1, media-3, media-1
*   cycle 3 (f=72): media-1, media-2, media-3

Same seed and banks; only cycle in the payload changed. A cycle change does **not** guarantee a new source. A singleton bank (Artifact 001 default) increments cycle and still returns the same ID.

## Artifact 001’s real cycles

Adapter sets period = duration = 3. Offsets and rates differ, so loops do not cross cycle 1 together.

| frame | loop-1 local / cycle | loop-2 local / cycle | loop-3 local / cycle |
| --- | --- | --- | --- |
| 0 | 0 / 0 | 0.31 / 0 | 0.62 / 0 |
| 70 | < 3 / 0 | < 3 / 0 | < 3 / 0 |
| 71 | 71/24≈2.958 / **0** | 8341/2400≈3.475 / **1** | 1597/400≈3.992 / **1** |
| 72 | 3 / **1** | 3.52 / 1 | 4.04 / 1 |
| 143 | 5.958 / 1 | 6.685 / **2** | 7.412 / **2** |
| 144 | 6 / **2** | 6.73 / 2 | 7.46 / 2 |

Loop-2 and loop-3 enter cycle 1 one frame before loop-1 because their local clocks already started ahead and run faster. Sources stay media-1/2/3 the whole time because each bank has one member. Cycle is still in the hash; it just cannot change the pick.

## Hold freezes cycle; release does not skip

Hold at frame 20 with period 1, rate 1, offset 0 bakes local=5/6. Cycle stays 0 for the whole hold because 5/6 < 1. Loop-2 continues: by frame 49 it is already in cycle 2 (49/24).

Release at 50 keeps local=5/6 and starts elapsed again. Cycle 1 arrives when local reaches 1, at frame 54 — four frames later, not at the composition time when an unheld loop would have flipped (frame 24). That is the selection counterpart of “no catch-up.”

## Pin disables cycle; reroll does not

choose_source returns pin before computing cycle. Swap writes pins from choose_source **at the event frame**, so the pin is “whatever cycle $k$ would have chosen then.” Later cycle boundaries do not update a pinned loop.

Swap at 24 (cycle 1): pinned media-2 / media-3. At frame 48 unpinned loops move to cycle 2 (media-1 / media-3); pinned loops stay put through frame 72.

Reroll clears pin and increments epoch. Cycle is unchanged at that frame. Mid-cycle reroll at f=30 (local=5/4, still cycle 1) can keep the same source; the next cycle hashes (epoch=1, cycle=2) and diverges (here media-2 vs unpinned media-1 at f=48).

## Cycle vs file wrap

Two different moduli:

*   **cycle** uses unbounded local / period
*   **source_offset** uses local % trim_span (or duration)

They only coincide when period == trim_span and you are counting wraps of that same window. Artifact 001 looks like that because the adapter chose period=duration. A trim of [1,2] with period=3 wraps the playhead every 1s of local time while cycle only ticks every 3s. Bank selection then ignores the file wrap.

Continuity / FFmpeg segment cuts look at source identity and source_offset step, not at cycle. A cycle tick that keeps the same source does not split a segment. A cycle tick that changes source does.

## What cycle is not

*   Not in the authoring model. choose_source there is a single seeded draw; reroll_index is the only salt.
*   Not computed in the browser. Spans already carry a chosen source.
*   Not a global bar. Each loop’s cycle is a function of that loop’s local time and its own period.
*   Not an exclusive allocator. Two loops can land on the same source in the same cycle; only allow_source_reuse=false rejects that after the fact.
*   Not stored. resolve_at recomputes it from offset, anchor, held, rate, period, and frame every time.

Read a resolve record as: local is the clock, period is the tick length, epoch is the reroll salt, cycle = floor(local/period) is the current draw index, source is that draw unless a pin is holding an older one.

## Q: 
Investigate source offset logic

## A: 
source_offset is the seek into the current file. It is derived from local time; it is not local time.

## Compiled definition

After the source is chosen:

```language-279:284:/tmp/simvltanea/composition.py
local = local_time(loop, frame, state["fps"])
        low, high = (rational(x, "trim") for x in loop.get("trim", [0, src["duration"]]))
        require(high <= rational(src["duration"], "duration"), "swapped source does not fit loop trim")
        offset = Fraction(0) if src["kind"] == "still" else low + local % (high - low)
```$t_{\text{src}}(f)= \begin{cases} 0 & \text{still}\\ t_{\text{low}}+\bigl(t_{\text{local}}(f)\bmod(t_{\text{high}}-t_{\text{low}})\bigr) & \text{video} \end{cases}$

Default window is [0, duration]. Optional trim must satisfy 0 ≤ low < high and high ≤ duration for **every** bank member at validate time, then again for the resolved source (swap/pin can name a shorter clip).

Python Fraction modulo never lands on high. local=3, duration 3 → 0. Trim [1,2], local=1 or 2 → 1. Browser validation source_offset < duration depends on that.

Stored form is a rational string (69/50). Segment compilation then does float(Fraction(...)) onto Panel.source_offset.

## What it is not

| Field | Role |
| --- | --- |
| loop offset | phase of the private clock at composition time 0 |
| local | unbounded private clock |
| source_offset | playhead inside [low, high) |
| bank cycle | floor(local / period), another modulus |

They only look similar when trim=[0,duration], period=duration, and local < duration. Artifact 001 starts that way; it stops at the first wrap.

Frame 36, loop-5: local=79/25=3.16, source_offset=4/25=0.16. The adapter test compares authoring media_time(1.5) % 3 to source_offset, not to local.

Stills keep advancing local and still compute cycles; source_offset stays 0.

## Continuity is defined on this field

```language-321:329:/tmp/simvltanea/composition.py
def continuous(previous: dict, current: dict, fps: int, orientation: str) -> bool:
    ...
        delta = Fraction(0) if a["held"] or a["kind"] == "still" else Fraction(a["rate"]) / fps
        if Fraction(b["source_offset"]) != Fraction(a["source_offset"]) + delta:
            return False
```

Unheld video must step by exactly $r/\text{fps}$. Held and still must not move. A wrap fails the add and starts a new segment.

Loop-1 around the 3s wrap:

*   70→71: 35/12 + 1/24 = 71/24 (continuous)
*   71→72: 71/24 + 1/24 ≠ 0 (cut)
*   72→73: 0 + 1/24 = 1/24 (continuous again)

One loop wrapping cuts **every** loop’s segment. compile_segments snapshots all N source_offsets at that frame. State-6 portrait 360×640 therefore emits 13 segments in 6 seconds: each distinct wrap (loop-6 first at 1.083s, then 5, 4, 3, 2, 1, then the second orbit) is a global cut. Segment 0 starts at authored phases 0, 0.31, 0.62, 0.93, 1.24, 1.55. Segment 6 starts at composition t=3.0 with loop-1 back at 0.0.

## Hold freezes the wrapped playhead

Hold bakes local into loop offset and zeros elapsed. source_offset is then the wrap of that frozen local.

Still-controls loop-2: hold at frame 24 leaves source_offset=69/50. At frame 48 it is still 69/50 even though release has just happened. Local is the same number; the playhead did not catch up. Loop-1 (still) reports source_offset=0 at every event frame while its local goes 0,1,2,5/2,7/2.

FFmpeg encodes that freeze by taking one frame at trim=start=source_offset and looping it. The browser seeks to source_offset and does not add elapsed while held.

## How exporters consume it

**Clocked N-loop path** (Panel.clocked=True, set only by compile_segments):

```plain text
trim=start={source_offset}, setpts=PTS-STARTPTS,
  [held/still] fps, trim=end_frame=1, loop
  [else]       setpts=PTS/rate, fps, tpad clone,
trim=duration={segment}, setpts=PTS-STARTPTS
```

Inputs are \-stream_loop -1, so the file can physically wrap, but the model still splits on wrap so each segment begins at the reset playhead. tpad exists because a fractional start plus rate-stretched PTS can run out of decoded frames before the segment ends.

**Legacy canon** uses the same Panel.source_offset field with a different meaning:

*   fixed: panel_index \* phrase_seconds (left=0, middle=phrase, right=2×phrase)
*   clip: segment_start - interval.start (how far this panel is into its current occupancy)

That is stagger through a migrating clip, not wrap of an independent clock. Test fixed[2].panels[2].source_offset == 2 is that old schedule. State exports never call it; \--state cannot mix with \--timing/--phrase.

Legacy audio does atrim=start=source_offset. Versioned loop exports are silent in v1, so that path is unused for SIMVLTANEA state.

**Browser** reconstructs playhead only at span activation:

$\text{target}=t_{\text{src,span}}+(0 \text{ if held else }(f-f_{\text{span}})/\text{fps}\cdot r)$

Between spans the element just plays at playbackRate=r. source_offset must already be wrapped; the runtime will not modulo again.

## Constraints that bite

*   Loop offset (clock phase) may be any nonnegative rational. source_offset is always in [low, high).
*   A pin to a source whose duration is shorter than the loop trim fails at resolve, not at hash time.
*   Float conversion at compile time is the first precision drop. Continuity itself is exact rational. FFmpeg seconds() then prints six decimal places.
*   source_offset does not choose the file. Bank selection can change source at a cycle boundary while source_offset is still mid-window; that also splits a segment, because continuous compares source identity first.

Read a resolved loop as: seek here (source_offset), in this file (source), at this speed (rate), or freeze this frame (held / still). The private clock that produced that seek is local.

