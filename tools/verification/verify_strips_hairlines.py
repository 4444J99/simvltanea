#!/usr/bin/env python3
"""Hairline matrix for the full-bleed strips raster in a real headless Chrome.

Seam test 6 of docs/plans/2026-11-05-full-bleed-layout-presets.md: a screenshot of
the real browser runtime playing strips N=1, 5, 8 and 12 at 375x812, 390x844 and
360x780 (1x, 2x, 3x), at 1280x720 and 1366x768 (1x, 2x) and at the near-square
360x360, 744x768 and 800x800 (1x, 2x), with corner_radius and lateral_jitter at 0 and at their
maxima, has zero background pixels. A background pixel is a device pixel whose
largest channel is below 40. The near-square viewports give the thinnest strips
relative to the radius (N=12 at 360x360: 30 px strips, configured radius 18 px), where
the runtime reduces the radius so the earlier strip backs the whole cutout.

The clips are synthetic ``ffmpeg -f lavfi`` ramps (R = row, G = column, B = 80 + 14k
per clip, plus temporal noise), so the background is the only near-black colour;
the clips are checked for near-black pixels before any page is measured. Nothing
here reads personal media or downloads anything. Output stays under
``var/proofs/strips-raster/``. The always-on suite runs N=5 and N=12
(``test_browser_raster``); this command runs the full matrix and prints a report.

This is a pixel probe of one browser build on this machine. It is not a claim about
Safari/WebKit, phones or real footage.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path

from tools.paths import PROOFS_DIR, require_in_var

from PIL import Image, ImageChops
from simvltanea.authoring import build_strips, strips_slice
from simvltanea.browser import HERE, browser_runtime, compile_plan

ROOT = PROOFS_DIR / 'strips-raster'
CLIP_WIDTH, CLIP_HEIGHT, CLIP_FPS, CLIP_SECONDS = 540, 720, 24, 4
MAX_CLIPS = 12
NEAR_BLACK = 40  # largest channel below this is a background pixel
PHONES = ((375, 812), (390, 844), (360, 780))
DESKTOPS = ((1280, 720), (1366, 768))
NEAR_SQUARE = ((360, 360), (744, 768), (800, 800))  # 800x800 @2x is the canvas that exposed the corner defect
# Grouped by device pixel ratio: one browser context per ratio, resized in place.
VIEWPORTS = ((1, PHONES + DESKTOPS + NEAR_SQUARE), (2, PHONES + DESKTOPS + NEAR_SQUARE), (3, PHONES))
STYLES = {'flat': ('0', '0'), 'max': ('1/20', '1/20')}  # (corner_radius, lateral_jitter)
FULL_COUNTS = (1, 5, 8, 12)
DEFAULT_COUNTS = (5, 12)
PLAN_FRAMES = 480  # 20 s at 24 fps: playback outlasts the measurement
PROGRESS_WAIT_MS = 1500  # how long a playing loop may take to present its next frame before it counts as stalled
CHROME_APP = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def clip_command(index: int, target: Path) -> list[str]:
    """A 540x720 H.264 ramp whose blue channel identifies the clip (FFmpeg 6.1 options only)."""
    blue = 80 + 14 * index
    source = (f'nullsrc=s={CLIP_WIDTH}x{CLIP_HEIGHT}:r={CLIP_FPS}:d={CLIP_SECONDS},format=gbrp,'
              f"geq=r='255*Y/H':g='255*X/W':b='{blue}',noise=alls=8:allf=t")
    return ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', source, '-an', '-c:v', 'libx264',
            '-preset', 'veryfast', '-crf', '20', '-g', str(CLIP_FPS), '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(target)]


def _darkest(path: Path) -> int:
    """Smallest largest-channel value over three decoded frames of a clip."""
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vf',
                             "select='eq(n\\,0)+eq(n\\,47)+eq(n\\,95)'", '-fps_mode', 'passthrough',
                             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], check=True, capture_output=True)
    size = CLIP_WIDTH * CLIP_HEIGHT * 3
    frames = [result.stdout[i:i + size] for i in range(0, len(result.stdout), size)]
    if len(frames) != 3 or any(len(frame) != size for frame in frames):
        raise RuntimeError(f'{path.name}: expected three decoded frames')
    darkest = 255
    for frame in frames:
        darkest = min(darkest, _max_channel(Image.frombytes('RGB', (CLIP_WIDTH, CLIP_HEIGHT), frame)).getextrema()[0])
    return darkest


def _max_channel(image: Image.Image) -> Image.Image:
    red, green, blue = image.convert('RGB').split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def prepare_clips(root: Path = ROOT) -> list[dict]:
    """Encode (or reuse) the synthetic clips; return state sources in loop order."""
    media = root / 'media'
    media.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'clips.json'
    commands = [clip_command(k, Path('media') / f'clip-{k + 1}.mp4') for k in range(MAX_CLIPS)]
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    cached = manifest.get('sha256', []) if manifest.get('commands') == commands else []
    if len(cached) == MAX_CLIPS and all((media / f'{sha}.mp4').is_file() and
                                        hashlib.sha256((media / f'{sha}.mp4').read_bytes()).hexdigest() == sha
                                        for sha in cached):
        digests = cached
    else:
        digests = []
        for command in commands:
            scratch = root / command[-1]
            subprocess.run(command[:-1] + [str(scratch)], check=True)
            digest = hashlib.sha256(scratch.read_bytes()).hexdigest()
            os.replace(scratch, media / f'{digest}.mp4')
            digests.append(digest)
        manifest_path.write_text(json.dumps(dict(kind='original-synthetic', commands=commands, sha256=digests),
                                            indent=2) + '\n')
    for k, digest in enumerate(digests):
        darkest = _darkest(media / f'{digest}.mp4')
        if darkest < NEAR_BLACK:
            raise RuntimeError(f'clip {k + 1} has near-black pixels (largest channel {darkest}); '
                               'the background would not be distinguishable')
    (root / 'index.html').write_text(browser_runtime.HTML.replace('<script src="runtime.js" defer></script>\n', ''))
    return [dict(id=f'source-{k + 1}', path=f'media/{digest}.mp4', sha256=digest, kind='video',
                 duration=str(CLIP_SECONDS)) for k, digest in enumerate(digests)]


def strips_preset(radius: str = '0', jitter: str = '0') -> dict:
    return {'format': 'simvltanea.layout-preset/1', 'name': 'strips', 'family': 'strips',
            'style': {'corner_radius': radius, 'lateral_jitter': jitter}}


def strips_plan(count: int, sources: list[dict], *, style: str = 'flat', zoom: bool = True,
                root: Path = ROOT) -> dict:
    """Compile a strips state (zoom tied to N unless ``zoom`` is false) into a servable plan."""
    radius, jitter = STYLES[style]
    preset = strips_preset(radius, jitter)
    state = build_strips(count, preset, sources=[dict(item) for item in sources[:count]], frames=PLAN_FRAMES,
                         fps=CLIP_FPS)
    state['slice'] = strips_slice(count, preset) if zoom else {'enabled': False}
    plan = compile_plan(state)
    for source in plan['sources']:
        source['bytes'] = (root / source['path']).stat().st_size
    return plan


def browser_executable() -> str:
    """A caller-pinned or preinstalled Chrome/Chromium; nothing is downloaded."""
    configured = os.environ.get('PORTVS_BROWSER_EXECUTABLE')
    if configured:  # an explicit pin is used or refused, never replaced by another browser
        pinned = Path(configured).expanduser()
        if not (pinned.is_absolute() and pinned.is_file() and os.access(pinned, os.X_OK)):
            raise RuntimeError(f'PORTVS_BROWSER_EXECUTABLE is not an absolute executable file: {configured}')
        return str(pinned)
    candidates = [CHROME_APP] + [shutil.which(name) for name in
                                 ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser')]
    for candidate in candidates:
        if candidate and Path(candidate).is_absolute() and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        bundled = playwright.chromium.executable_path
    if bundled and Path(bundled).is_file():
        return bundled
    raise RuntimeError('an installed Chrome or Chromium is required (set PORTVS_BROWSER_EXECUTABLE)')


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def count_background(png: bytes) -> dict:
    """Device pixels whose largest channel is below NEAR_BLACK, with their bounding box."""
    image = Image.open(io.BytesIO(png))
    level = _max_channel(image)
    dark = sum(level.histogram()[:NEAR_BLACK])
    mask = level.point(lambda value: 255 if value < NEAR_BLACK else 0)
    return dict(pixels=image.width * image.height, background=dark, bbox=mask.getbbox(),
                size=[image.width, image.height])


class RasterProbe:
    """One HTTP server and one headless Chrome serving the runtime with a compiled plan."""

    def __init__(self, root: Path = ROOT, executable: str | None = None):
        self.root, self.executable = root, executable
        self._stack = ExitStack()

    def __enter__(self) -> 'RasterProbe':
        try:
            return self._start()
        except BaseException:
            self._stack.close()
            raise

    def _start(self) -> 'RasterProbe':
        from playwright.sync_api import sync_playwright
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_Quiet, directory=str(self.root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._stack.callback(thread.join)
        self._stack.callback(server.server_close)
        self._stack.callback(server.shutdown)
        self.base = f'http://127.0.0.1:{server.server_port}'
        playwright = sync_playwright().start()
        self._stack.callback(playwright.stop)
        self.browser = playwright.chromium.launch(executable_path=self.executable or browser_executable(),
                                                  headless=True, args=['--no-sandbox', '--disable-dev-shm-usage',
                                                                       '--autoplay-policy=no-user-gesture-required'])
        self._stack.callback(self.browser.close)
        self.runtime_js = (HERE / 'browser.runtime.js').read_text()
        return self

    def __exit__(self, *exc):
        self._stack.close()

    def open(self, plan: dict, width: int, height: int, ratio: int, *, start: bool = True):
        """Load the runtime with ``plan``; return (context, page, page errors)."""
        context = self.browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=ratio)
        try:
            return self._load(context, plan, start)
        except BaseException:
            context.close()
            raise

    def _load(self, context, plan: dict, start: bool):
        page = context.new_page()
        errors: list[str] = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'{self.base}/index.html')
        page.evaluate("""plan => {
          window.compositionIO = {
            async plan() { return structuredClone(plan); },
            async bytes(source) {
              const response = await fetch(source.path);
              if (!response.ok) throw new Error(`Missing media: ${source.id}`);
              return response.arrayBuffer();
            },
            async digest(bytes) {
              return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
                .map(v => v.toString(16).padStart(2, '0')).join('');
            },
          };
        }""", plan)
        page.add_script_tag(content=self.runtime_js)
        page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error', timeout=60000)
        error = page.evaluate('compositionRuntime.error')
        if error:
            raise RuntimeError(f'runtime refused the plan: {error}')
        # Status overlays are page chrome, not the field.
        page.evaluate("document.querySelectorAll('#runtime-status,#runtime-note').forEach(e => e.remove())")
        if start:
            page.evaluate('compositionRuntime.start()')
            page.wait_for_function('[...compositionRuntime.nodes.values()].every(n => n.callbacks >= 2)',
                                   timeout=60000)
        return context, page, errors

    @staticmethod
    def settle(page, width: int, height: int) -> None:
        """Resize in place and wait until the runtime has laid out that exact stage."""
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_function("""([w, h]) => {
          const r = window.compositionRuntime, box = document.querySelector('#stage').getBoundingClientRect();
          const last = r.events.filter(e => e.type === 'layout').at(-1);
          return box.width === w && box.height === h && last && last.width === w && last.height === h;
        }""", arg=[width, height], timeout=30000)
        page.evaluate('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')

    @staticmethod
    def stretch(page) -> list[float]:
        """Element aspect over source aspect for every loop (1.0 means no distortion)."""
        return page.evaluate("""() => [...compositionRuntime.nodes.values()].map(n => {
          const r = n.media.getBoundingClientRect();
          return (r.width / r.height) / (n.media.videoWidth / n.media.videoHeight);
        })""")

    def measure(self, plan: dict, ratio: int, sizes, label: str = '') -> list[dict]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout  # lazy: the module loads without Playwright
        rows = []
        first = sizes[0]
        context, page, errors = self.open(plan, first[0], first[1], ratio)
        # Progress is the playback position, not the frame-callback count: a resize repaint can fire one
        # callback from a loop that is frozen, but it cannot move a frozen loop's currentTime.
        frames = '() => [...compositionRuntime.nodes.values()].map(n => n.media.currentTime)'
        try:
            previous = page.evaluate(frames)
            for width, height in sizes:
                self.settle(page, width, height)
                result = count_background(page.screenshot())
                expected = [round(width * ratio), round(height * ratio)]
                if result['size'] != expected:
                    raise RuntimeError(f'screenshot is {result["size"]}, expected {expected} device pixels')
                snapshot = page.evaluate('compositionRuntime.snapshot()')
                # The measurement can land between two video frames (41.7 ms apart at 24 fps), so an
                # unchanged frame count alone proves nothing: give every playing video a bounded
                # interval to present a frame before judging. A frozen one still times out and counts.
                try:
                    page.wait_for_function('''previous => [...compositionRuntime.nodes.values()].every((n, i) =>
                      n.busy || n.media.ended || n.media.paused || n.kind !== 'video' || n.span.held ||
                      n.media.currentTime !== previous[i])''', arg=previous, timeout=PROGRESS_WAIT_MS)
                except PlaywrightTimeout:
                    pass  # the loop below counts the loops that did not progress
                # A loop at native EOF waits on its last frame for the next frame-addressed
                # boundary, and a boundary seek pauses briefly; neither is a stall. An unpaused
                # video that presented no frame since the previous measurement is one.
                stalled, previous = page.evaluate('''previous => {
                  const nodes = [...compositionRuntime.nodes.values()];
                  return [nodes.filter((n, i) => !n.busy && !n.media.ended && (n.media.paused ||
                    (n.kind === 'video' && !n.span.held && n.media.currentTime === previous[i]))).length,
                    nodes.map(n => n.media.currentTime)];
                }''', previous)
                rows.append(dict(case=label, viewport=f'{width}x{height}', ratio=ratio, **result,
                                 orientation=snapshot['orientation'], error=snapshot['error'],
                                 running=snapshot['running'], stalled=stalled,
                                 stretch=max(abs(value - 1) for value in self.stretch(page)) if plan['slice'].get('enabled') else 0.0,
                                 page_errors=list(errors)))
        finally:
            context.close()
        return rows


def without_bleed(plan: dict) -> dict:
    """The same plan with overlap_px forced to 0: the negative control."""
    plan = json.loads(json.dumps(plan))
    for keyframe in plan['layout_keyframes']:
        for layout in keyframe['layouts'].values():
            layout['presentation']['overlap_px'] = 0
    return plan


# Cases the spec measured with hairlines before the bleed existed (zoom N=12 at 1366x768:
# 1536 px @1x, 6144 px @2x; cover N=5 at 375x812 @1x: 750 px). Without the bleed the
# probe must see background there, or a zero in the matrix would prove nothing.
CONTROLS = ((12, True, ((1, ((1366, 768),)), (2, ((1366, 768),)))), (5, False, ((1, ((375, 812),)),)))


def run_controls(probe: 'RasterProbe', sources: list[dict], root: Path = ROOT) -> list[dict]:
    rows = []
    for count, zoom, viewports in CONTROLS:
        plan = without_bleed(strips_plan(count, sources, zoom=zoom, root=root))
        for ratio, sizes in viewports:
            rows.extend(probe.measure(plan, ratio, sizes,
                                      label=f'control N={count} {"zoom" if zoom else "cover"} overlap_px 0'))
    return rows


def run_matrix(counts=FULL_COUNTS, styles=tuple(STYLES), viewports=VIEWPORTS, *, executable: str | None = None,
               root: Path = ROOT, log=None) -> list[dict]:
    sources = prepare_clips(root)
    rows = []
    with RasterProbe(root, executable) as probe:
        controls = run_controls(probe, sources, root)
        if log:
            for row in controls:
                log(format_row(row))
        for count in counts:
            for style in styles:
                plan = strips_plan(count, sources, style=style, root=root)
                for ratio, sizes in viewports:
                    measured = probe.measure(plan, ratio, sizes, label=f'strips N={count} {style}')
                    rows.extend(measured)
                    if log:
                        for row in measured:
                            log(format_row(row))
    return rows, controls


def format_row(row: dict) -> str:
    return (f"{row['case']:<20} {row['viewport']:>9} @{row['ratio']}x  {row['orientation']:<9} "
            f"background {row['background']:>6} / {row['pixels']:>8}  stretch {row['stretch']:.4f}"
            + (f"  bbox {row['bbox']}" if row['bbox'] else '')
            + (f"  ERRORS {row['page_errors']}" if row['page_errors'] or row['error'] else '')
            + ('' if row['running'] and not row['stalled'] else f"  NOT PLAYING ({row['stalled']} stalled)"))


def failures(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row['background'] or row['error'] or row['page_errors'] or row['stretch'] > 0.005
            or not row['running'] or row['stalled']]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--counts', type=int, nargs='+', default=list(FULL_COUNTS), choices=range(1, 13),
                        metavar='N', help='strip counts (default: 1 5 8 12)')
    parser.add_argument('--json', type=Path, help='also write every row as JSON to this path under var/')
    args = parser.parse_args(argv)
    began = time.monotonic()
    rows, controls = run_matrix(tuple(args.counts), log=print)
    bad = failures(rows)
    blind = [row for row in controls if not row['background']]
    total = sum(row['background'] for row in rows)
    print(f'negative control (overlap_px 0): {len(controls)} screenshots, '
          f'{sum(row["background"] for row in controls)} background pixels, {len(blind)} without any')
    print(f'hairline matrix: {len(rows)} screenshots, {total} background pixels, '
          f'{len(bad)} failing, max stretch deviation {max(row["stretch"] for row in rows):.4f}, '
          f'{time.monotonic() - began:.0f} s')
    if args.json:
        require_in_var(args.json.resolve(), 'hairline report')
        args.json.write_text(json.dumps(dict(controls=controls, matrix=rows), indent=2) + '\n')
    if bad or blind:
        print('hairline matrix FAILED' + (' (the probe saw no hairline without the bleed)' if blind else ''))
        return 1
    print('hairline matrix ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
