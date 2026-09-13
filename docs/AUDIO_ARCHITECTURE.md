# SIMVLTANEA Audio Architecture (Schema v1 & v1.1)

> **Document Type**: Technical Design Specification
> **Schema Context**: silent `visual-form-composition/v1`; opt-in `visual-form-composition/v1.1`
> **Repository**: `4444J99/simvltanea`
> **Status**: Implemented — verification and boundaries below; issue #2 tracks integration.

---

## 1. Background & Evolution

The audio design of the configurable panel project evolved across three historical phases:

1. **Legacy TripTicks (2017–2026 Incubator)**:
   - Fixed 3-panel layout.
   - Three discrete audio routing modes:
     - `none`: Completely silent video output.
     - `panel`: Route audio exclusively from one selected panel (e.g. `left`, `middle`, or `right`).
     - `mix`: Combine audio from all three panels with individual gain coefficients and crossfades.
2. **Schema v1 Ingestion & Artifact 001 (2026 Extraction)**:
   - Generalized to $N$ independent video loops ($N \in \{3, 4, 5, 6, \dots\}$).
   - Ingested Schema v1 exports default to **purely silent visual fields** (`audio: null` or silent stream).
   - This avoided sonic cacophony when evaluating independent multi-loop rational clock mechanics.
3. **Canonical SIMVLTANEA Specification (Schema v1.1+)**:
   - Formalizes three explicit, predictable audio modes designed for multi-stream simultaneity.

---

## 2. Audio Operating Modes

| Mode | Source of sound | Clock |
| --- | --- | --- |
| Silent field | None | Visual clocks only |
| Synchronized soundtrack | One verified external track | Global composition clock |
| Spatial loop mix | Audio present in each selected video | Independent loop source clocks |

### Mode 0: Silent Field (Default / Pure Visual Art)
- **Behavior**: All video loops are exported without audio streams (`-an` in FFmpeg; `muted` attribute in `<video>` tags).
- **Rationale**: Emphasizes pure visual rhythm, geometry, and temporal coexistence across the $N$ panels. Ideal for gallery installations, silent digital displays, and mobile autoplay.

---

### Mode 1: Synchronized Ambient Soundtrack (Master Audio Track)
- **Behavior**: A single external master audio soundtrack plays alongside the visual composition.
- **Clock Binding**:
  - The soundtrack clock $t_{\text{audio}}$ is locked directly to global composition time $c$:
    $$t_{\text{audio}} = c \pmod{T_{\text{soundtrack}}}$$
  - Rotating between portrait and landscape modes maintains continuous playback of the master track without glitch or restart.
- **Specification**:
  ```json
  {
    "audio": {
      "mode": "soundtrack",
      "source": "audio/ambient-master-001.mp3",
      "volume": 0.8,
      "loop": true,
      "fade_in_seconds": 1.5,
      "fade_out_seconds": 2.0
    }
  }
  ```

---

### Mode 2: Multi-Track Spatial Loop Mix (Per-Loop Sound Field)
- **Behavior**: Each active video loop instance $i$ emits its own audio track derived from its current playback position $t_{\text{src}, i}(t)$.
- **Spatial Positioning**:
  - In horizontal/landscape modes, audio tracks are spatially panned stereo according to the panel center coordinate $x_i \in [0, 1]$:
    $$\text{pan}_i = 2 \cdot x_i - 1 \quad (\text{pan} \in [-1.0, +1.0])$$
  - In vertical/portrait modes, pan is centered ($\text{pan}_i = 0$). Optional scaling by vertical focal hierarchy is reserved and unimplemented.
- **Hold & Mute Semantics**:
  - A held loop is silent. Its final 50ms of audible playback ramps down to zero at the authored hold boundary. The compiled timeline makes this anticipation possible: pausing a native video stops its audio samples immediately. Holds at frame zero begin silent; release resumes the frozen source clock without catch-up.
  - Sibling loops continue audible playback uninterrupted.
- **Specification**:
  ```json
  {
    "audio": {
      "mode": "spatial_loops",
      "master_volume": 0.7,
      "spatial_panning": true,
      "per_loop": {
        "loop-1": { "gain": 1.0, "mute_on_hold": true },
        "loop-2": { "gain": 0.8, "mute_on_hold": true },
        "loop-3": { "gain": 0.6, "mute_on_hold": true }
      }
    }
  }
  ```

---

## 3. FFmpeg & Web Runtime Implementation

### FFmpeg

`core/render_triptych.py` retains the historical rendering path. Explicit v1.1
audio is assembled across the full composition into 48 kHz stereo PCM, then
encoded to AAC once alongside the concatenated video. Visual segment boundaries
cannot restart a soundtrack or introduce per-segment AAC priming.

Spatial audio uses `atrim`, pitch-preserving `atempo`, equal-power `pan`, gain,
hold fades, and `amix` with `normalize=0`. Continuous spans of the same loop are
coalesced across unrelated visual/sibling boundaries. Still images and videos
without audio contribute silence. Each absolute boundary is rounded to a sample,
avoiding accumulated error from rounding individual segment durations.

The mix applies authored gains without an automatic limiter or loudness
normalization. A loud multitrack sum can clip; choose gains accordingly.

### Browser Runtime (Web Audio API)
In [`core/browser_runtime.js`](../core/browser_runtime.js):
- In spatial mode, each video element connects to a `MediaElementAudioSourceNode` feeding a `StereoPannerNode` and a `GainNode`.
- Orientation transitions smoothly update `StereoPannerNode.pan.linearRampToValueAtTime(...)` over 200ms without interrupting audio buffer playback.

The soundtrack uses a decoded `AudioBufferSourceNode` on the global AudioContext
clock. It is not recreated by layout changes. Audible playback starts with a
click or Space key in the preview; pause/resume and explicit seek are available
through `compositionRuntime`. Unsupported Web Audio, integrity failures, media
decode failures, and audio-context interruptions stop playback visibly through
the runtime error state; they are never represented as successful silent audio.

## 4. Version and source contract

| Surface | Existing silent contract | Explicit audio contract |
| --- | --- | --- |
| Authoring `Composition.schema_version` | `visual-form-composition/v1` | `visual-form-composition/v1.1` |
| Serialized frame state `schema_version` | integer `1` | string `"1.1"` |
| Frame-state `engine_version` | `1.0.0` | `1.1.0` |
| Compiled browser plan | version `1`, `audio: "none"` | version `2`, typed audio object |

The existing authoring engine remains `0.1.0`. Its typed audio dataclasses are
`SilentAudio`, `SoundtrackAudio`, `LoopAudio`, and `SpatialLoopsAudio`. Existing
v1 authoring serialization keeps its original shape; a v1.1 snapshot is required
to emit either audible mode. Compiled silent audio remains
`{"mode":"none","routing":null,"generative":null}`.

The conceptual soundtrack example in section 2 additionally requires `sha256`
(the actual source bytes' lowercase SHA-256) and `duration` (positive integer or
rational string) in executable state. `source` is a local path relative to that
state. Traversal, URLs, symlink escapes, absent media, digest mismatches, and
unverifiable durations are rejected. Preview copies are hash named and checked
again before browser decoding. Duration/loop clocks use rationals. Finite decimal
JSON gain and fade controls are accepted and normalized by decimal spelling.

Soundtrack fades follow the global clock, once across the composition, rather
than restarting each loop cycle. The gain envelope is the minimum of unity,
the fade-in ramp, and the fade-out ramp. With `loop: false`, sound ends at the
earlier of the source duration or composition end; remaining video continues.

Spatial defaults are master gain 1, panning enabled, and per-loop gain 1.
Gains/volume are bounded to 0..1. Portrait pan is zero; landscape pan uses the
authored cell center, including letterboxing and gaps. Unknown loop IDs and
unsupported controls are rejected. `mute_on_hold: false`, frozen-audio synthesis,
optional portrait focal-volume scaling, and generative audio are not implemented.

`tools/verify_editions.py` accepts both new audio declarations while preserving
historical `none`/`panel`/`mix` validation. Preset validation does not bind media
or establish edition readiness. The historical project exporter and its landing
page retain their existing audio contract; v1.1 rendering uses the versioned
`--state` path and preview builder below. The production edition registry is
unchanged.

## 5. Reproduce the synthetic examples

From the repository root, with FFmpeg/ffprobe and the pinned Python dependencies:

```bash
python3 core/make_audio_fixture.py
python3 core/render_triptych.py --state runtime-proof/audio-v1.1/soundtrack.json --orientation landscape --width 320 --height 180 --output runtime-proof/audio-v1.1/soundtrack.mp4
python3 core/render_triptych.py --state runtime-proof/audio-v1.1/spatial-loops.json --orientation landscape --width 320 --height 180 --output runtime-proof/audio-v1.1/spatial-loops.mp4
python3 -m http.server 8000 --bind 127.0.0.1 --directory runtime-proof/audio-v1.1
```

Open `/preview-soundtrack/` or `/preview-spatial-loops/` on the local server and
click the composition to start. Resize it to change orientation. These are
synthetic tones and color fields in the existing engineering layouts, not
artist-approved soundtracks, recovered historical media, or a public release.

Verification commands:

```bash
python3 -m unittest discover -s tests -v
python3 tools/verify_legacy_decoded.py
python3 tools/verify_editions.py
python3 tools/verify_layouts.py --examples
python3 tools/verify_local_lifecycle.py
```

Native browser tests require a working installed Chrome/Chromium with H.264
support and Playwright. Set `PORTVS_BROWSER_EXECUTABLE` to its absolute path and
`PORTVS_BROWSER_TRANSPORT=in-memory` when needed. Verification uses decoded PCM,
native Web Audio, rational state checks, and decoded historical comparisons.
Browser evidence is bounded foreground desktop playback; it does not establish
sample-exact native-video seeking, background-tab continuity, mobile-device
support, or parity across all media codecs. No original TripTicks media was
recovered, and no provenance or artist-approval claims are advanced by these tests.

The browser preview accepts spatial audio from mono/stereo AAC in its supported
H.264 MP4 videos; unsupported present audio is rejected. Videos without audio
remain valid silent contributors. Browser soundtracks are bounded to 600 seconds
and mono/stereo decoding to limit PCM memory. The offline path keeps its wider
media support. Declared soundtrack duration is authoritative within the verified
one-frame media tolerance: decoded PCM is padded or trimmed to that duration so
repeated playback does not drift between browser and export.

Loop selection and source discontinuities remain addressed at composition-frame
boundaries, as in the visual model. Between those boundaries native video and
offline spans consume continuous audio. A fractional trim or wrap falling between
frames is applied on the next resolved frame; this is not a claim of subframe
sample-exact loop switching. Output PCM length and global soundtrack looping are
separate sample-count guarantees.
