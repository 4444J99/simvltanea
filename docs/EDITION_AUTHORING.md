# SIMVLTANEA Edition 001 Authoring & Production Guide

> **Document Type**: Operational Production Guide  
> **Repository**: `4444J99/simvltanea`  
> **Applies to**: Real Media Ingestion, Edition Manifests & Master Exports  

---

## 1. Overview

An **Edition** in SIMVLTANEA is an authored, cohesive collection of $N$-loop compositions created from real personal or curated video archives.

Unlike synthetic test runs, an Edition features:
- High-definition source footage (1080p / 4K).
- Authored loop banks, selection probabilities, and rational phase offsets.
- Verified portrait (9:16) and landscape (16:9) master renders.

---

## 2. Ingestion & Clip Preparation Workflow

```text
1. Raw Media Intake      ───►  samples/ or external folder
2. Atomize / Transcode   ───►  atomize_media.py (Standardize FPS, CRF 18, 1080x1080/1080p)
3. Catalog & Hash        ───►  manage_clips.py / preservation_manifest.py
4. Author Edition Spec   ───►  editions.json (Loops, source banks, trim windows, rates)
5. Build Master Renders  ───►  build_edition.py (FFmpeg 1080p portrait & landscape)
6. Verify & Status       ───►  edition_status.py / verify_editions.py
```

### Step 1: Placing Raw Video Clips
Drop raw video files (MP4, MOV) into `samples/` or import from a local folder:
```bash
python3 import_folder.py --source /path/to/my/video-clips --target samples/
```

### Step 2: Atomizing Clips
Standardize all media to consistent frame rates (e.g., 24fps or 30fps) and keyframe intervals:
```bash
python3 atomize_media.py --input-dir samples/ --output-dir media/
```

### Step 3: Authoring `editions.json`
Define the loop bindings in `editions.json`:
```json
{
  "editions": [
    {
      "id": "edition-001",
      "title": "Simvltanea Inaugural (Archive Pass)",
      "date": "2026-09-10",
      "configurations": [3, 4, 5, 6],
      "canvas": {
        "portrait": { "width": 1080, "height": 1920, "fps": 24 },
        "landscape": { "width": 1920, "height": 1080, "fps": 24 }
      },
      "sources": [
        { "id": "clip-family-01", "path": "media/family-01.mp4", "duration": "12" },
        { "id": "clip-nature-01", "path": "media/nature-01.mp4", "duration": "15" },
        { "id": "clip-urban-01",  "path": "media/urban-01.mp4",  "duration": "10" }
      ],
      "loops": [
        { "id": "loop-1", "bank": ["clip-family-01"], "offset": "0", "rate": "1" },
        { "id": "loop-2", "bank": ["clip-nature-01"], "offset": "31/100", "rate": "107/100" },
        { "id": "loop-3", "bank": ["clip-urban-01"],  "offset": "62/100", "rate": "114/100" }
      ]
    }
  ]
}
```

### Step 4: Compiling and Rendering
Run the edition builder to render both portrait and landscape video files:
```bash
python3 build_edition.py --edition edition-001 --output-dir renders/
```

### Step 5: Verification & Status
Inspect the rendering status and checksum receipts:
```bash
python3 edition_status.py
python3 verify_editions.py
```
