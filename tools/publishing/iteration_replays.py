"""Publish source-pinned historical renderers with clearly identified replay plans.

The renderer files are byte-identical Git snapshots.  The small replay wrapper
uses their existing compositionIO extension to map current public library files
into the old content-addressed transport format.  It does not patch a renderer,
copy media, or claim to recover an original composition or artwork state.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "archive" / "engineered-iterations" / "early"
MEDIA_NOTE = (
    "Historical renderer replay using distinct clips from the current public library. "
    "The selection and composition are new replay material, not a recovered original artwork state."
)
HISTORICAL_REPLAYS = (
    {
        "slug": "authored-loops", "title": "Authored N-loop runtime", "date": "2026-09-10",
        "revision": "65510a93c3b9842b6a6b428964681d5a0aacead4",
        "description": "The initial silent native-media renderer: independent rational clocks and authored portrait and landscape layouts.",
        "media_note": MEDIA_NOTE,
        "source_path": "browser_runtime.js",
        "source_sha256": "be1e9a960815839dd623bf154922b7877fee6489ccf3b5857c5e9cf61ed3a0dd",
    },
    {
        "slug": "seamed-slices", "title": "Seamed slices", "date": "2026-09-10",
        "revision": "7577a9ce36052d7f0d966206a02d06eff216f68f",
        "description": "Source-region slicing and feathered seams added to the silent independent-loop renderer.",
        "media_note": MEDIA_NOTE,
        "source_path": "core/browser_runtime.js",
        "source_sha256": "c2beca5607afe4c9e715473bb0cc882f7683ac0cde8d302aaaa08e687f686314",
    },
    {
        "slug": "spatial-audio", "title": "Spatial audio v1.1", "date": "2026-09-13",
        "revision": "c638a25d5c863f28b13188a50799ecbc3d723dc7",
        "description": "The corrected v1.1 renderer adds opt-in source audio, per-loop gain, spatial panning, pause and resume.",
        "media_note": MEDIA_NOTE,
        "source_path": "core/browser_runtime.js",
        "source_sha256": "010ba703bb6639146440defed14260a26eba835cacac0a1cc4ede1d960c64c10",
    },
    {
        "slug": "viewport-composition", "title": "Viewport composition", "date": "2026-10-25",
        "revision": "192ccf23728b1ac8b3848539a27520228f63c9f1",
        "description": "The later compositor preserves explicit source viewports and transport recovery. External shared-engine framing is unavailable in this replay.",
        "media_note": MEDIA_NOTE,
        "source_path": "src/simvltanea/browser/browser.runtime.js",
        "source_sha256": "4e416904ffbe47a63420016d0f484375ad1581b72a35f9a04fbb8eefabba02c1",
    },
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _fraction(value: object) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError) as error:
        raise ValueError("replay clip duration must be a finite positive number") from error
    if result <= 0:
        raise ValueError("replay clip duration must be positive")
    return result


def _select_clips(clips: list[dict]) -> list[dict]:
    """Choose up to three unique, bounded public files without reusing a clip."""
    selected, ids, files = [], set(), set()
    total = 0
    for clip in sorted(clips, key=lambda item: (str(item["id"]), str(item["file"]))):
        filename = clip["file"]
        path = PurePosixPath(filename) if isinstance(filename, str) else None
        if (not filename or path is None or path.is_absolute() or ".." in path.parts
                or "\\" in filename or ":" in filename or "?" in filename or "#" in filename
                or any(ord(char) < 32 for char in filename) or path.suffix.lower() != ".mp4"):
            raise ValueError("replay media must be a relative public-library MP4 path")
        duration = _fraction(clip["duration_seconds"])
        size = clip["bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("replay clip byte count must be a positive integer")
        if clip["id"] in ids or filename in files:
            continue
        # Every retained video must support at least one frame at the historical
        # renderer's minimum 1/16 playback rate; never manufacture held filler.
        if duration < Fraction(1, 480) or total + size > 256 * 1024 * 1024:
            continue
        selected.append(clip)
        ids.add(clip["id"])
        files.add(filename)
        total += size
        if len(selected) == 3:
            break
    if not selected:
        raise ValueError("historical replays need at least one playable public clip within the 256 MiB source budget")
    return selected


def _plan(item: dict, clips: list[dict], *, audio: bool = False) -> dict:
    fps, frames = 30, 900
    sources, tracks = [], []
    rates = (Fraction(1), Fraction(7, 8), Fraction(5, 4))
    for index, clip in enumerate(clips):
        source_id, track_id = f"source-{index + 1}", f"loop-{index + 1}"
        duration = _fraction(clip["duration_seconds"])
        source = {
            "id": source_id, "kind": "video", "duration": str(duration),
            "path": "../../library/" + quote(clip["file"], safe="/"),
            "bytes": clip["bytes"], "sha256": "0" * 64,
            "public_id": str(clip["id"]),
        }
        if audio:
            # The public manifest does not attest to an AAC codec/channel count.
            # Null leaves that capability unasserted; native media can still play
            # whatever source audio the browser decodes after explicit opt-in.
            source["audio_stream"] = None
        sources.append(source)
        rate = min(rates[index], duration * fps)
        margin = min(Fraction(1, 4), duration / 10)
        period = max(1, int((duration - margin) * fps / rate))
        spans = []
        for frame in range(0, frames, period):
            span = {"id": track_id, "frame": frame, "source": source_id,
                    "kind": "video", "held": False, "rate": str(rate), "source_offset": "0"}
            if item["slug"] != "authored-loops":
                # Each distinct source has its own viewport; no clone panels.
                if item["slug"] == "viewport-composition":
                    span["slice_rect"] = [str(Fraction(index, 12)), "1/8", "3/4", "3/4"]
                else:
                    span["slice_rect"] = ["1/8", "0", "3/4", "1"]
            spans.append(span)
        tracks.append({"id": track_id, "spans": spans})
    count = len(tracks)
    layouts = {}
    for orientation in ("portrait", "landscape"):
        cells = []
        for index, track in enumerate(tracks):
            start, width = str(Fraction(index, count)), str(Fraction(1, count))
            rect = [start, "0", width, "1"] if orientation == "landscape" else ["0", start, "1", width]
            cells.append({"loop": track["id"], "fit": "cover", "rect": rect, "focal": ["1/2", "1/2"]})
        layouts[orientation] = {"cells": cells}
    plan = {
        "plan_version": 2 if audio else 1,
        "engine_version": "1.1.0" if audio else "1.0.0",
        "audio": "none", "fps": fps, "frames": frames,
        "sources": sources, "tracks": tracks,
        "layout_keyframes": [{"frame": 0, "layouts": layouts}],
    }
    if item["slug"] != "authored-loops":
        plan["seam"] = {"enabled": True, "mode": "feather", "width": "1/100", "sigma": "1/125"}
    if audio:
        plan["audio"] = {
            "mode": "spatial_loops", "master_volume": "1/2", "spatial_panning": True,
            "per_loop": {track["id"]: {"gain": str(Fraction(1, count)), "mute_on_hold": True} for track in tracks},
        }
    plan["state_sha256"] = hashlib.sha256(_json_bytes(plan)).hexdigest()
    return plan


def _page(item: dict, clips: list[dict], has_audio_plan: bool) -> bytes:
    esc = html.escape
    title, slug = esc(item["title"]), item["slug"]
    audio_control = (
        '<a id="audio-mode" class="control" href="?audio=1">Enable source audio</a>'
        if has_audio_plan else '<span class="mode-note">Silent replay</span>'
    )
    external_note = (
        '<p class="dependency-note">The external shared-engine framing package is not included. '
        'This replay runs the preserved native compositor with its source viewports; external panel motion is unavailable.</p>'
        if slug == "viewport-composition" else ""
    )
    media_items = "".join(
        '<li><a href="../../library/' + quote(clip["file"], safe="/") + '">'
        + esc(str(clip["id"])) + '</a></li>' for clip in clips
    )
    pause = '<button id="pause" type="button" disabled>Pause</button>' if slug in ("spatial-audio", "viewport-composition") else ""
    transport_note = "Pause and resume use this renderer’s original transport." if pause else "This early renderer has no pause operation. Restart loads the replay again."
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · SIMVLTANEA Iterations</title><link rel="stylesheet" href="replay.css">
<script src="replay.js" defer></script><script src="runtime.js" defer></script></head>
<body data-iteration="{esc(slug)}" data-audio-plan="{'true' if has_audio_plan else 'false'}">
<header><a href="../../iterations.html">← Iterations</a><span class="eyebrow">SIMVLTANEA / ENGINEERED</span></header>
<main><section class="intro"><p class="eyebrow">Historical renderer replay · {esc(item['date'])} UTC</p>
<h1>{title}</h1><p>{esc(item['description'])}</p><p class="media-note">{esc(item['media_note'])}</p>{external_note}</section>
<section aria-label="Replay player"><div class="transport"><button id="play" type="button" disabled>Play</button>{pause}
<button id="restart" type="button">Restart</button><button id="orientation" type="button" aria-pressed="false">Portrait view</button>{audio_control}</div>
<p id="replay-status" role="status" aria-live="polite">Loading current public media…</p>
<div id="stage" data-status="loading" aria-label="Historical composition player"></div>
<p class="hint">30-second replay. {transport_note} Orientation changes layout while keeping the independent media clocks.</p></section>
<details><summary>Sources and replay provenance</summary><p>Preserved renderer revision <code>{esc(item['revision'])}</code>.</p>
<p>Renderer SHA-256 <code>{esc(item['source_sha256'])}</code>.</p><p>Current public clips:</p><ul>{media_items}</ul>
<p><a href="plan.json">Replay plan</a> · <a href="provenance.json">Provenance</a> · <a href="runtime.js">Exact renderer source</a></p>
<p>The loading adapter hashes the fetched public files, then supplies those bytes through the renderer’s original I/O extension. No historical source-media hashes are asserted.</p></details>
</main></body></html>'''
    return document.encode("utf-8")


REPLAY_CSS = """*{box-sizing:border-box}html{color-scheme:dark}body{margin:0;background:#0b0d10;color:#e8e8e6;font:16px/1.55 system-ui,sans-serif}a{color:#c4d9ee}header{display:flex;justify-content:space-between;gap:1rem;padding:1rem 4vw;border-bottom:1px solid #30343a}main{max-width:1180px;margin:auto;padding:2rem 4vw 4rem}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:.75rem;color:#b2bac5}h1{font-size:clamp(1.8rem,4vw,3rem);line-height:1.12;margin:.6rem 0 1rem}.intro{max-width:850px;margin-bottom:1.5rem}.media-note,.dependency-note{font-size:.9rem;color:#c8ccd2}.dependency-note{border-left:2px solid #b0a07c;padding-left:1rem}.transport{display:flex;align-items:center;flex-wrap:wrap;gap:.6rem}button,.control{font:inherit;color:#e8e8e6;background:#20252c;border:1px solid #56606f;border-radius:4px;padding:.55rem .9rem;text-decoration:none;cursor:pointer}button:disabled{opacity:.5;cursor:wait}button:focus-visible,a:focus-visible,#stage:focus-visible{outline:2px solid #b7ddff;outline-offset:3px}.mode-note,.hint{font-size:.85rem;color:#b3bac4}#replay-status{font-size:.9rem;min-height:1.4em}#stage{position:relative;isolation:isolate;width:100%;aspect-ratio:16/9;background:#060708;overflow:hidden;margin:1rem auto}#stage.portrait{aspect-ratio:9/16;max-width:420px}.loop{position:absolute;overflow:hidden}.loop video,.loop img{display:block;width:100%;height:100%;object-fit:cover}.hint{max-width:850px}details{margin-top:2rem;border-top:1px solid #30343a;padding-top:1rem}summary{cursor:pointer}code{font-size:.8rem;overflow-wrap:anywhere}li{margin:.35rem 0}@media(max-width:600px){header .eyebrow{display:none}main{padding-top:1rem}.transport{gap:.45rem}button,.control{font-size:.9rem}}\n"""

REPLAY_JS = r"""'use strict';
(() => {
  const host = document.querySelector('#stage');
  const status = document.querySelector('#replay-status');
  const play = document.querySelector('#play');
  const pause = document.querySelector('#pause');
  const audioLink = document.querySelector('#audio-mode');
  const audioEnabled = document.body.dataset.audioPlan === 'true' &&
    new URLSearchParams(location.search).get('audio') === '1';
  if (audioLink && audioEnabled) {
    audioLink.href = './'; audioLink.textContent = 'Use silent replay';
  }
  if (document.body.dataset.iteration === 'viewport-composition') {
    window.__sharedEngineUnavailable = 'External shared-engine framing is not included in this historical replay.';
  }
  const cache = new Map();
  const sourcePaths = new Map();
  let userError = '';
  async function digest(buffer) {
    if (!crypto.subtle) throw new Error('A secure context is required to verify public media.');
    const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', buffer));
    return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  }
  window.compositionIO = {
    async plan() {
      const response = await fetch(audioEnabled ? 'audio-plan.json' : 'plan.json');
      if (!response.ok) throw new Error('Cannot load historical replay plan');
      const plan = await response.json();
      let total = 0;
      for (const source of plan.sources) {
        const url = new URL(source.path, location.href);
        const library = new URL('../../library/', location.href);
        if (url.origin !== location.origin || !url.pathname.startsWith(library.pathname))
          throw new Error('Replay media must come from the same public library');
        sourcePaths.set(source.id, source.path);
        status.textContent = 'Loading public clip ' + (cache.size + 1) + ' of ' + plan.sources.length + '…';
        const media = await fetch(url);
        if (!media.ok) throw new Error('Missing public media: ' + source.id);
        const bytes = await media.arrayBuffer();
        if (bytes.byteLength !== source.bytes) throw new Error('Public media size differs from its manifest: ' + source.id);
        total += bytes.byteLength;
        if (total > 256 * 1024 * 1024) throw new Error('Historical renderer media budget exceeded');
        const hash = await digest(bytes);
        if (!/^[a-f0-9]{12}$/.test(source.public_id) || hash.slice(0, 12) !== source.public_id)
          throw new Error('Public media integrity differs from its manifest: ' + source.id);
        cache.set(source.id, bytes);
        source.sha256 = hash;
        source.path = 'media/' + hash + '.mp4';
        delete source.public_id;
      }
      return plan;
    },
    async bytes(source) {
      if (!cache.has(source.id)) throw new Error('Public media was not loaded: ' + source.id);
      return cache.get(source.id);
    },
    digest,
  };
  // Exposed for provenance and browser verification, not an alternate renderer.
  window.historicalReplay = {audioEnabled, sourcePaths};
  const showError = error => { userError = String(error.message || error); status.textContent = userError; };
  play.addEventListener('click', async () => {
    const engine = window.compositionRuntime;
    if (!engine?.ready || engine.error || engine.running) return;
    userError = '';
    try { await engine.start(); } catch (error) { showError(error); }
  });
  if (pause) pause.addEventListener('click', () => {
    try { window.compositionRuntime.pause(); userError = ''; } catch (error) { showError(error); }
  });
  document.querySelector('#restart').addEventListener('click', () => location.reload());
  document.querySelector('#orientation').addEventListener('click', event => {
    const portrait = host.classList.toggle('portrait');
    event.currentTarget.setAttribute('aria-pressed', String(portrait));
    event.currentTarget.textContent = portrait ? 'Landscape view' : 'Portrait view';
  });
  function refresh() {
    const engine = window.compositionRuntime;
    if (!engine) return;
    play.disabled = !engine.ready || Boolean(engine.error) || engine.running || engine.finished || engine.starting;
    if (pause) pause.disabled = !engine.running || Boolean(engine.error) || engine.starting;
    play.textContent = engine.frame > 0 && !engine.finished && pause ? 'Resume' : 'Play';
    if (engine.error) status.textContent = 'Playback unavailable: ' + engine.error;
    else if (userError) status.textContent = userError;
    else if (engine.finished) status.textContent = 'Replay finished. Restart to play again.';
    else if (engine.running) status.textContent = 'Playing · ' + (audioEnabled ? 'source audio enabled' : 'silent') + ' · ' + (engine.orientation || 'landscape');
    else if (engine.ready) status.textContent = (engine.frame > 0 ? 'Paused' : 'Ready') + ' · ' + (audioEnabled ? 'source audio enabled; press Play' : 'silent replay');
  }
  setInterval(refresh, 200);
  document.addEventListener('visibilitychange', () => {
    const engine = window.compositionRuntime;
    if (document.hidden && engine?.running && typeof engine.pause === 'function') {
      try { engine.pause(); } catch (error) { showError(error); }
    }
  });
  window.addEventListener('pagehide', () => {
    const engine = window.compositionRuntime;
    if (engine?.dispose) engine.dispose();
  }, {once: true});
})();
"""


def historical_replay_files(clips: list[dict]) -> dict[str, bytes]:
    """Return four runnable renderer replay routes using admitted public media.

    One clip is sufficient; up to three distinct files are selected.  Media files
    remain in the shared public library.  Archived renderer bytes are checked
    against fixed SHA-256 values before they enter a build.
    """
    selected = _select_clips(clips)
    files: dict[str, bytes] = {}
    for item in HISTORICAL_REPLAYS:
        archive = ARCHIVE_ROOT / item["slug"] / "browser_runtime.js"
        if archive.is_symlink() or not archive.is_file():
            raise ValueError("historical renderer source is missing or linked: " + item["slug"])
        source = archive.read_bytes()
        if hashlib.sha256(source).hexdigest() != item["source_sha256"]:
            raise ValueError("historical renderer source digest mismatch: " + item["slug"])
        # Unknown audio capability permits an explicit attempt; an explicitly
        # silent library does not advertise nonexistent source sound.
        has_audio_plan = item["slug"] in ("spatial-audio", "viewport-composition") and any(
            clip.get("has_audio") is not False for clip in selected
        )
        prefix = "iterations/" + item["slug"] + "/"
        assets = {
            "index.html": _page(item, selected, has_audio_plan),
            "replay.css": REPLAY_CSS.encode("utf-8"),
            "replay.js": REPLAY_JS.encode("utf-8"),
            "runtime.js": source,
            "plan.json": _json_bytes(_plan(item, selected)),
        }
        if has_audio_plan:
            assets["audio-plan.json"] = _json_bytes(_plan(item, selected, audio=True))
        provenance = copy.deepcopy(item)
        provenance.update({
            "schema": "simvltanea.historical-replay/1",
            "wrapper": "Present-day public-media loading adapter and controls; renderer source is unchanged.",
            "media_integrity": "Fetched bytes must match the public manifest byte count and 12-character SHA-256 content ID. Their full SHA-256 values are then supplied to the historical renderer; zero placeholders in the saved replay plan are not archival checksums.",
            "media": [{"id": str(clip["id"]), "path": "../../library/" + quote(clip["file"], safe="/")} for clip in selected],
            "audio_default": "silent",
            "audio_opt_in": has_audio_plan,
            "external_shared_engine": "unavailable" if item["slug"] == "viewport-composition" else "not required",
        })
        assets["provenance.json"] = _json_bytes(provenance)
        files.update({prefix + path: data for path, data in assets.items()})
    return files
