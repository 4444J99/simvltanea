# Visual proof set — 2026-09-10

Synthetic fixtures only. Not TripTicks source footage. Not artist-approved geometry.

Command path: `artifact001_layouts.build_artifact001` → FFmpeg overlay of six hue-shifted `testsrc2` loops.

Inspected frames:

| File | Observed |
| --- | --- |
| `frames/n3-portrait.png` | 720x1280. Large upper field, two lower cells. Three distinct hues. |
| `frames/n3-landscape.png` | 1280x720. Wide left field, two stacked-right columns. Not a scaled portrait. |
| `frames/n4-portrait.png` | Four cells, staggered pair geometry. |
| `frames/n4-landscape.png` | Four cells, different hierarchy from portrait. |
| `frames/n5-portrait.png` | Wide header plus 2x2 lower bank. Five sources. |
| `frames/n5-landscape.png` | Tall left field plus 2x2 right bank. |
| `frames/n6-portrait.png` | Two top cells, wide mid band, three lower cells. Six sources. |
| `frames/n6-landscape.png` | Left stack, tall mid column, right stack of three. |

Independence checks in this package:

- N source files for N panels
- layout mapping is 1:1 (`loop-id` set equals placement set)
- portrait and landscape geometries are authored separately

Playback / orientation continuity of native video elements is covered by
Portvs PR #9 receipts, not re-executed as a live Chromium session here.
Model-level orientation continuity passed in `test_composition_model.py`.
