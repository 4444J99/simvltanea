#!/usr/bin/env python3
"""Compile schema-1 state into a bounded browser playback proof.

The authoritative resolver stays in composition.py. JavaScript consumes its
per-loop spans; it does not reimplement source selection or event semantics.
This is a local engineering preview, not a deployed website or a claim
of frame-exact, unlimited-duration, background-tab or mobile-device playback.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import composition as c

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PLAN_VERSION = 1
MAX_MEDIA_BYTES = 256 * 1024 * 1024
# Explicit native-preview capability, not a restriction on the offline model.
# The installed Chromium rejects smaller nonzero playbackRate values.
MIN_VIDEO_RATE = Fraction(1, 16)
MAX_SOUNDTRACK_SECONDS = 600  # Eager decoded PCM, unlike streamed native videos.
HTML = '''<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Composition runtime proof</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}
#stage{position:relative;width:100%;height:100%;overflow:hidden;background:#000}
.loop{position:absolute;overflow:hidden;background:#000}
.loop video,.loop img{width:100%;height:100%;display:block}
#runtime-status{position:fixed;bottom:8px;left:8px;z-index:100;margin:0;padding:6px 9px;
font:13px/1.4 system-ui,sans-serif;color:#fff;background:#000b;pointer-events:none}
</style><main id="stage" aria-label="Composition runtime proof"></main>
<p id="runtime-status" role="status" aria-live="polite">Loading verified composition…</p>
<script src="runtime.js" defer></script>
'''


def _continues(a: dict, b: dict, fps: int) -> bool:
    if any(a[k] != b[k] for k in ('id', 'source', 'kind', 'rate', 'held')):
        return False
    if a.get('slice_rect') != b.get('slice_rect'):
        return False
    delta = Fraction(0) if a['held'] or a['kind'] == 'still' else Fraction(a['rate']) / fps
    return Fraction(b['source_offset']) == Fraction(a['source_offset']) + delta


def compile_plan(state: dict) -> dict:
    """Pure compilation; reject every invalid frame before starting playback."""
    c.validate_state(state)
    tracks = {item['id']: [] for item in state['loops']}
    previous = {}
    layouts = []
    for frame in range(state['frames']):
        resolved = c.resolve_at(state, frame)
        if not layouts or layouts[-1]['layouts'] != resolved['layouts']:
            layouts.append(dict(frame=frame, layouts=copy.deepcopy(resolved['layouts'])))
        for loop in resolved['loops']:
            ident = loop['id']
            if loop['kind'] == 'video':
                c.require(MIN_VIDEO_RATE <= Fraction(loop['rate']) <= 8,
                          'browser video rate must be within 1/16..8; offline model unchanged')
            if ident not in previous or not _continues(previous[ident], loop, state['fps']):
                tracks[ident].append(dict(frame=frame, **loop))
            previous[ident] = loop
    c.require(sum(map(len, tracks.values())) <= c.MAX_SEGMENTS * len(tracks),
              'browser span resource guard exceeded; no loops were dropped')
    # State permits Fraction-compatible spelling (including decimal strings).
    # Emit only canonical rationals so the browser need not reproduce that parser.
    for keyframe in layouts:
        for layout in keyframe['layouts'].values():
            for cell in layout['cells']:
                for field in ('rect', 'focal'):
                    cell[field] = [str(c.rational(value, field)) for value in cell[field]]
    sources = copy.deepcopy(state['sources'])
    for source in sources:
        source['duration'] = str(c.rational(source['duration'], 'duration'))
    # Canonicalize slice rects
    for spans in tracks.values():
        for span in spans:
            if 'slice_rect' in span and span['slice_rect'] is not None:
                span['slice_rect'] = [str(c.rational(v, 'slice_rect')) for v in span['slice_rect']]
    seam = copy.deepcopy(state.get('seam', {"enabled": False}))
    if seam and seam.get('enabled'):
        seam['width'] = str(c.rational(seam.get('width', '1/40'), 'seam.width'))
        seam['sigma'] = str(c.rational(seam.get('sigma', '1/200'), 'seam.sigma'))
    slice_cfg = copy.deepcopy(state.get('slice', {"enabled": False}))
    if slice_cfg and slice_cfg.get('enabled'):
        slice_cfg['width'] = str(c.rational(slice_cfg.get('width', '1/2'), 'slice.width'))
        slice_cfg['height'] = str(c.rational(slice_cfg.get('height', '1/2'), 'slice.height'))
    # CSS and FFmpeg independently rasterize normalized layout values.
    audio = c.audio_config(state)
    if audio['mode'] == 'soundtrack':
        audio['asset'] = dict(id='soundtrack', kind='audio', path=audio['source'],
                             sha256=audio['sha256'], duration=audio['duration'])
    return dict(plan_version=PLAN_VERSION if state['schema_version'] == 1 else 2,
                engine_version=state['engine_version'],
                state_sha256=hashlib.sha256(c.canonical_json(state).encode()).hexdigest(),
                fps=state['fps'], frames=state['frames'],
                audio='none' if state['schema_version'] == 1 else audio,
                tracks=[dict(id=ident, spans=spans) for ident, spans in tracks.items()],
                layout_keyframes=layouts, sources=sources, seam=seam, slice=slice_cfg)


def build_preview(state_path: Path, output: Path) -> dict:
    """Copy verified media to an incubator-local preview; no public upload occurs."""
    state_path, output = state_path.resolve(), output.resolve()
    c.require(output.is_relative_to(REPO_ROOT), 'preview must remain inside the incubator')
    c.require(output != state_path.parent and not state_path.is_relative_to(output),
              'preview output must not contain or replace the source state')
    state = c.load_state(state_path)
    plan = compile_plan(state)
    paths = c.media_paths(state, state_path.parent)
    soundtrack = c.soundtrack_path(state, state_path.parent)
    if soundtrack is not None:
        c.require(soundtrack.suffix.lower() in ('.wav', '.mp3', '.m4a', '.ogg', '.flac'),
                  'browser soundtrack requires WAV, MP3, M4A, Ogg or FLAC')
        c.require(Fraction(plan['audio']['duration']) <= MAX_SOUNDTRACK_SECONDS,
                  'browser soundtrack exceeds 600-second decoded PCM guard; offline model unchanged')
        audio_facts = json.loads(subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
             'stream=channels', '-of', 'json', str(soundtrack)],
            check=True, capture_output=True, text=True).stdout)
        c.require(audio_facts['streams'][0].get('channels') in (1, 2),
                  'browser soundtrack requires mono or stereo audio')
    c.require(sum(path.stat().st_size for path in paths.values()) +
              (soundtrack.stat().st_size if soundtrack else 0) <= MAX_MEDIA_BYTES,
              'preview media exceeds 256 MiB guard; no sources were omitted')
    # This bounded preview proves H.264/8-bit MP4 decoding, not every FFmpeg
    # container/codec. Legacy and offline rendering retain their wider support.
    for source in state['sources']:
        if source['kind'] != 'video':
            continue
        path = paths[source['id']]
        c.require(path.suffix.lower() == '.mp4', 'browser preview currently requires H.264 MP4')
        facts = json.loads(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'stream=codec_type,codec_name,pix_fmt,channels:format=format_name', '-of', 'json', str(path)],
            check=True, capture_output=True, text=True).stdout)
        stream = next(stream for stream in facts['streams'] if stream.get('codec_type') == 'video')
        c.require('mp4' in facts['format']['format_name']
                  and stream.get('codec_name') == 'h264' and stream.get('pix_fmt') == 'yuv420p',
                  'browser preview currently requires 8-bit yuv420p H.264 MP4')
        if isinstance(plan['audio'], dict) and plan['audio']['mode'] == 'spatial_loops':
            audio_stream = next((stream for stream in facts['streams'] if stream.get('codec_type') == 'audio'), None)
            c.require(audio_stream is None or (audio_stream.get('codec_name') == 'aac' and
                                               audio_stream.get('channels') in (1, 2)),
                      'browser spatial preview requires AAC mono/stereo when an audio stream is present')
            compiled_source = next(item for item in plan['sources'] if item['id'] == source['id'])
            compiled_source['audio_stream'] = (dict(codec='aac', channels=audio_stream['channels'])
                                                if audio_stream else None)
    output.mkdir(parents=True, exist_ok=True)
    c.require((output / 'media').resolve().is_relative_to(output), 'preview media directory escapes output')
    (output / 'media').mkdir(exist_ok=True)
    assets = [(source, paths[source['id']]) for source in plan['sources']]
    if soundtrack is not None:
        assets.append((plan['audio']['asset'], soundtrack))
    for source, path in assets:
        relative = Path('media') / (source['sha256'] + path.suffix.lower())
        target = output / relative
        c.require(not target.is_symlink(), 'preview destination must not be a symlink')
        if target != path:
            shutil.copyfile(path, target)
        source['path'] = relative.as_posix()
        source['bytes'] = target.stat().st_size
    if soundtrack is not None:
        plan['audio']['source'] = plan['audio']['asset']['path']
    for name in ('plan.json', 'state.json', 'runtime.js', 'index.html'):
        c.require(not (output / name).is_symlink(), 'preview destination must not be a symlink')
    # The saved preview state must itself be renderable using the copied media.
    # Rebasing filenames changes provenance identity, never loop/time decisions.
    portable = copy.deepcopy(state)
    by_id = {source['id']: source['path'] for source in plan['sources']}
    for source in portable['sources']:
        source['path'] = by_id[source['id']]
    if soundtrack is not None:
        portable['audio']['source'] = plan['audio']['source']
    plan['origin_state_sha256'] = plan['state_sha256']
    plan['state_sha256'] = hashlib.sha256(c.canonical_json(portable).encode()).hexdigest()
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    c.save_state(portable, output / 'state.json')
    shutil.copyfile(HERE / 'browser_runtime.js', output / 'runtime.js')
    (output / 'index.html').write_text(HTML)
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = build_preview(args.state, args.output)
    print(c.canonical_json(dict(loops=len(plan['tracks']), frames=plan['frames'],
                                spans=sum(len(x['spans']) for x in plan['tracks']),
                                state_sha256=plan['state_sha256'])))


if __name__ == '__main__':
    main()
