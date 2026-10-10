#!/usr/bin/env python3
"""Compile schema-1 state into a bounded browser playback proof.

The authoritative resolver stays in composition.py. JavaScript consumes its
per-loop spans; it does not reimplement source selection or event semantics.
This is a local engineering preview, not a deployed website or a claim
of frame-exact, unlimited-duration, background-tab or mobile-device playback.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import os
import tempfile
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from simvltanea.authoring import composition as c
from simvltanea.browser.shared_engine import (
    SharedEngineUnavailable,
    resolve_shared_engine,
    _verify_graph,
)
from simvltanea.paths import REPO_ROOT

HERE = Path(__file__).resolve().parent
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


def stage_shared_engine(output: Path) -> dict | None:
    """Copy the digest-verified shared engine into the preview, or say why not.

    The engine is owned and versioned by time-moment-brief. This resolves it
    through the consumer resolver, which verifies every pinned digest and the
    accepted release, and copies the exact verified bytes. Nothing is regenerated
    or patched on the way in.

    A failure is not fatal to the preview and is not hidden either: the caller
    writes the reason into the generated HTML, so an operator opening the preview
    sees that the shared engine is absent instead of wondering why every panel
    stayed centred.
    """
    for name in ('shared-engine', 'shared-engine-adapter.js', 'shared-engine.js',
                 'shared-engine-unavailable.txt', 'index.html'):
        if (output / name).exists() or (output / name).is_symlink():
            raise ValueError('shared engine staging requires a fresh destination')
    try:
        engine = resolve_shared_engine()
    except SharedEngineUnavailable as error:
        print(f'shared engine unavailable: {error}', file=sys.stderr)
        (output / 'shared-engine-unavailable.txt').write_text(
            str(error) + '\n', encoding='utf-8')
        return None

    module_dir = output / 'shared-engine'
    # This helper only writes into a fresh, unpublished generation.
    for relative in sorted(engine.pin['runtime_graph']):
        inner = Path(relative).relative_to('shared-engine')
        source = engine.module_root / inner
        target = module_dir / inner
        if not target.resolve().is_relative_to(module_dir.resolve()):
            raise SharedEngineUnavailable(f'pinned path {relative} escapes the staged module')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Authenticate the destination, including mutations between resolve and copy.
    staged_digests = _verify_graph(module_dir, engine.pin)
    shutil.copyfile(HERE / 'shared-engine-adapter.js', output / 'shared-engine-adapter.js')
    # The browser entry publishes the module as a global the runtime can reach.
    # It imports rather than inlines, so the bytes the page runs are the bytes
    # that were verified.
    (output / 'shared-engine.js').write_text(
        "import * as SharedEngine from './shared-engine/index.js';\n"
        "globalThis.SharedEngine = SharedEngine;\n"
        "globalThis.__sharedEngineReady = Promise.resolve(SharedEngine);\n",
        encoding='utf-8')
    receipt = dict(module='time-moment-brief/shared-engine',
                   release_status=engine.release_status,
                   files_verified=len(staged_digests),
                   entrypoint=engine.pin['entrypoint'])
    receipt['release'] = engine.release or ''
    return receipt


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


def _build_preview_generation(state_path: Path, output: Path) -> dict:
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
    shutil.copyfile(HERE / 'browser.runtime.js', output / 'runtime.js')
    shared = stage_shared_engine(output)
    (output / 'index.html').write_text(HTML.replace(
        '<script src="runtime.js" defer></script>',
        f'<script src="runtime.js" defer></script>\n'
        # The adapter is a classic script; the module is a real ES module, copied
        # from the verified owner checkout. No copy of the maths lives here.
        f'<script src="shared-engine-adapter.js" defer></script>\n'
        f'<script type="module" src="shared-engine.js"></script>\n'
        f'<!-- shared-engine release {shared["release"][:12]}, '
        f'{shared["files_verified"]} files digest-verified -->\n'
        if shared else (
            '<script src="runtime.js" defer></script>\n'
            '<script>window.__sharedEngineUnavailable = '
            + json.dumps((output / 'shared-engine-unavailable.txt').read_text()).replace('<', '\\u003c')
            + ';</script>\n')))
    return plan


def _publish_preview(staging: Path, output: Path) -> None:
    """Atomically publish a complete directory, retaining old bytes on failure.

    Nonempty directories cannot be replaced with ordinary rename. Linux and
    macOS supply atomic exchange; unsupported hosts refuse replacement rather
    than exposing a gap or mixing generations. After exchange, staging holds the
    old generation and the caller removes it.
    """
    if not output.exists():
        os.replace(staging, output)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith('linux'):
        exchange = libc.renameat2
        exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint]
        result = exchange(-100, os.fsencode(staging), -100, os.fsencode(output), 2)
    elif sys.platform == 'darwin':
        exchange = libc.renamex_np
        exchange.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = exchange(os.fsencode(staging), os.fsencode(output), 2)
    else:
        raise OSError(errno.ENOTSUP, 'atomic preview directory exchange unavailable')
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(output))


def build_preview(state_path: Path, output: Path) -> dict:
    """Build privately and publish the HTML, receipt and executable bytes together."""
    c.require(not output.is_symlink(), 'preview destination must not be a symlink')
    state_path, output = state_path.resolve(), output.resolve()
    c.require(output.is_relative_to(REPO_ROOT), 'preview must remain inside the incubator')
    c.require(output != state_path.parent and not state_path.is_relative_to(output),
              'preview output must not contain or replace the source state')
    if output.exists():
        c.require(output.is_dir(), 'preview destination must be a directory')
        c.require(not any(path.is_symlink() for path in output.rglob('*')),
                  'preview destination must not be a symlink')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-stage-', dir=output.parent))
    try:
        plan = _build_preview_generation(state_path, staging)
        _publish_preview(staging, output)
        return plan
    finally:
        # On success this is the previous generation; on failure the private build.
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


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
