# SIMVLTANEA Audio Architecture Specification (Schema v1 & Next)

> **Document Type**: Technical Design Specification  
> **Schema Context**: `visual-form-composition/v1`  
> **Repository**: `4444J99/simvltanea`  
> **Status**: Approved Specification  

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

```text
                               ┌─── Mode 0: Silent Field (Default)
                               │
SIMVLTANEA Audio Architecture ──┼─── Mode 1: Synchronized Ambient Soundtrack (Global)
                               │
                               └─── Mode 2: Multi-Track Spatial Loop Mix (Interactive)
```

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
  - In vertical/portrait modes, pan is centered ($\text{pan}_i = 0$), and volume can optionally scale with vertical focal hierarchy.
- **Hold & Mute Semantics**:
  - If a loop is in a **`held`** state, its audio track is immediately muted or frozen with a 50ms smooth gain ramp-down.
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

### FFmpeg Filtergraph for Mode 2
When rendering an $N$-loop composition with audio mix:
```plain text
[0:a]atrim=start=t1,asetpts=PTS-STARTPTS,pan=stereo|c0=0.8*c0|c1=0.2*c1,volume=0.9[a1];
[1:a]atrim=start=t2,asetpts=PTS-STARTPTS,pan=stereo|c0=0.5*c0|c1=0.5*c1,volume=0.9[a2];
[2:a]atrim=start=t3,asetpts=PTS-STARTPTS,pan=stereo|c0=0.2*c0|c1=0.8*c1,volume=0.9[a3];
[a1][a2][a3]amix=inputs=3:duration=first:dropout_transition=2[aout]
```

### Browser Runtime (Web Audio API)
In [`browser_runtime.js`](file:///Users/4jp/Workspace/4444J99/simvltanea/browser_runtime.js):
- Each `<video>` element connects to a `MediaElementAudioSourceNode` feeding a `StereoPannerNode` and a `GainNode`.
- Orientation transitions smoothly update `StereoPannerNode.pan.linearRampToValueAtTime(...)` over 200ms without interrupting audio buffer playback.
