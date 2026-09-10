#!/usr/bin/env python3
"""Compile schema-1 state into a bounded browser playback proof.

The authoritative resolver stays in composition.py. JavaScript consumes its
per-loop spans; it does not reimplement source selection or event semantics.
This is a local, silent engineering preview, not a deployed website or a claim
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
PLAN_VERSION = 1
MAX_MEDIA_BYTES = 256 * 1024 * 1024
# Explicit native-preview capability, not a restriction on the offline model.
# The installed Chromium rejects smaller nonzero playbackRate values.
MIN_VIDEO_RATE = Fraction(1, 16)
HTML = '''<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Composition runtime proof</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}
#stage{position:relative;width:100%;height:100%;overflow:hidden;background:#000}
.loop{position:absolute;overflow:hidden;background:#000}
.loop video,.loop img{width:100%;height:100%;display:block}
</style><main id="stage" aria-label="Composition runtime proof"></main>
<script src="runtime.js" defer></script>
'''


def _continues(a: dict, b: dict, fps: int) -> bool:
    if any(a[k] != b[k] for k in ('id', 'source', 'kind', 'rate', 'held')):
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
    # CSS and FFmpeg independently rasterize normalized layout values.
    return dict(plan_version=PLAN_VERSION, engine_version=c.ENGINE_VERSION,
                state_sha256=hashlib.sha256(c.canonical_json(state).encode()).hexdigest(),
                fps=state['fps'], frames=state['frames'], audio='none',
                tracks=[dict(id=ident, spans=spans) for ident, spans in tracks.items()],
                layout_keyframes=layouts, sources=sources)


def build_preview(state_path: Path, output: Path) -> dict:
    """Copy verified media to an incubator-local preview; no public upload occurs."""
    state_path, output = state_path.resolve(), output.resolve()
    c.require(output.is_relative_to(HERE), 'preview must remain inside the incubator')
    c.require(output != state_path.parent and not state_path.is_relative_to(output),
              'preview output must not contain or replace the source state')
    state = c.load_state(state_path)
    plan = compile_plan(state)
    paths = c.media_paths(state, state_path.parent)
    c.require(sum(path.stat().st_size for path in paths.values()) <= MAX_MEDIA_BYTES,
              'preview media exceeds 256 MiB guard; no sources were omitted')
    # This bounded preview proves H.264/8-bit MP4 decoding, not every FFmpeg
    # container/codec. Legacy and offline rendering retain their wider support.
    for source in state['sources']:
        if source['kind'] != 'video':
            continue
        path = paths[source['id']]
        c.require(path.suffix.lower() == '.mp4', 'browser preview currently requires H.264 MP4')
        facts = json.loads(subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
             'stream=codec_name,pix_fmt:format=format_name', '-of', 'json', str(path)],
            check=True, capture_output=True, text=True).stdout)
        stream = facts['streams'][0]
        c.require('mp4' in facts['format']['format_name']
                  and stream.get('codec_name') == 'h264' and stream.get('pix_fmt') == 'yuv420p',
                  'browser preview currently requires 8-bit yuv420p H.264 MP4')
    output.mkdir(parents=True, exist_ok=True)
    c.require((output / 'media').resolve().is_relative_to(output), 'preview media directory escapes output')
    (output / 'media').mkdir(exist_ok=True)
    for source in plan['sources']:
        path = paths[source['id']]
        relative = Path('media') / (source['sha256'] + path.suffix.lower())
        target = output / relative
        c.require(not target.is_symlink(), 'preview destination must not be a symlink')
        if target != path:
            shutil.copyfile(path, target)
        source['path'] = relative.as_posix()
        source['bytes'] = target.stat().st_size
    for name in ('plan.json', 'state.json', 'runtime.js', 'index.html'):
        c.require(not (output / name).is_symlink(), 'preview destination must not be a symlink')
    # The saved preview state must itself be renderable using the copied media.
    # Rebasing filenames changes provenance identity, never loop/time decisions.
    portable = copy.deepcopy(state)
    by_id = {source['id']: source['path'] for source in plan['sources']}
    for source in portable['sources']:
        source['path'] = by_id[source['id']]
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
