"""Browser versus export parity for full-bleed strips (spec seam test 7).

Spec: docs/plans/2026-11-05-full-bleed-layout-presets.md, "Seam tests required of
the implementation" (7) and "Slice rendering parity and scope". An exported frame and
a headless-Chrome screenshot of the same strips state must show the same source rows
(and columns) per strip within 2 percent of the source extent, with the strips slice
(zoom tied to N) and with the slice disabled. The old browser ``fill`` stretch showed
the whole slice window (or the whole clip) in every cell. The test computes that
prediction and shows it lies more than 5 percent away (N=1: see ``STRETCH_FACTOR``),
so a return of the stretch fails here.

Fixture: ``make_runtime_fixture.prepare()`` writes the 540x720 ramp clips (red is a
vertical ramp over source rows, green a horizontal ramp over source columns, blue a
per-clip tint), ``state-strips-N.json`` and its preview ``preview-strips-N``. The
clips are static, so the export's frame 0 and a paused browser frame show the same
picture whenever every loop shows its frame-0 slice window. Slice windows re-roll at
loop wraps, the first at frame 63 for N=12, so the browser is paused soon after
playback starts and each screenshot is taken only after the runtime reports the
frame-0 window for every loop; nothing depends on wall-clock timing.

Measurement: the blue tint names the clip on every line across the strips, which
gives each strip's visible extent. Inside a strip, the per-line source coordinate is
fitted with a straight line (cover magnification is uniform) and extrapolated to the
strip's visible edges, which gives the source range the strip actually shows. The
export is decoded through ``yuv444p`` and converted with BT.601 here: FFmpeg 9's
direct ``yuv420p`` to ``rgb24`` path biases red by about two levels (about seven
rows). Chrome colour-manages the tagged clips, so the screenshot is read through a
per-clip colour calibration taken in the same browser (``Calibration``). Outputs stay
under ``var/proofs/``.
"""
from __future__ import annotations

import copy
import functools
import http.server
import io
import json
import math
import subprocess
import sys
import threading
import unittest
from fractions import Fraction
from pathlib import Path

from PIL import Image

import simvltanea.authoring.composition as c
from simvltanea.browser.browser_runtime import build_preview
from simvltanea.browser.test_browser_runtime import browser_executable
from simvltanea.generators.make_runtime_fixture import RAMP_SIZE, ROOT, prepare, ramp_row, ramp_tint

REPO = Path(__file__).resolve().parents[3]
COUNTS = (1, 5, 12)
VARIANTS = ('slice', 'no-slice')
# 390x844 rather than 375x812: 375 is odd and cannot be an H.264 export width.
VIEWPORTS = (('portrait', 390, 844), ('landscape', 1280, 720))
SOURCE_EXTENT = {'rows': RAMP_SIZE[1], 'columns': RAMP_SIZE[0]}
PARITY = Fraction(2, 100)  # spec seam test 7: same source rows within +-2 percent
STRETCH_MARGIN = Fraction(5, 100)  # the old stretch must miss by more than this (N >= 2)
# N=1's 1/8 window is 67.5x90 source pixels: stretching it moves the shown edges by at
# most 2.4% of the source, which still fails PARITY. The span ratio is scale-free.
STRETCH_FACTOR = 1.5  # spec table: the old stretch is 1.62 (N=1 portrait) up to 7.39
EDGE = 4  # lines beside a strip edge: export chroma rings over about 3 lines there, so they are not fitted
MIN_TINT_GAP = 8  # source tints differ by 14; Chrome compresses the top of the range to about 12
EXPORT_FRAMES = 2  # frame 0 is measured; the frame-0 resolution is checked to be identical


def bt601(luma: float, cb: float, cr: float) -> tuple[float, float, float]:
    """Limited-range BT.601 to RGB, the matrix the ramp clips are tagged with."""
    y, u, v = 1.164 * (luma - 16), cb - 128, cr - 128
    return y + 1.596 * v, y - 0.392 * u - 0.813 * v, y + 2.017 * u


def band(plane: Image.Image, axis: str, low: int, high: int) -> Image.Image:
    """The band [low, high) across ``axis``, transposed so that every image row is one line along ``axis``.

    ``axis`` 'y' gives one line per canvas row (the band spans columns low..high);
    ``axis`` 'x' gives one line per canvas column (the band spans rows low..high).
    """
    if axis == 'y':
        return plane.crop((low, 0, high, plane.height))
    return plane.crop((0, low, plane.width, high)).transpose(Image.Transpose.TRANSPOSE)


class ExportReader:
    """Frame 0 of an export, decoded to yuv444p and converted with BT.601 here.

    The conversion is affine, so a line's mean planes give the line's mean colour, and
    ``ramp_row`` (linear) turns mean red into the mean source row, mean green into the
    mean source column.
    """

    def __init__(self, path: Path, width: int, height: int):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v', '1', '-f', 'rawvideo',
                              '-pix_fmt', 'yuv444p', '-'], capture_output=True, check=True).stdout
        size = width * height
        if len(raw) != 3 * size:
            raise AssertionError(f'{path.name}: decoded {len(raw)} bytes, expected {3 * size}')
        self.planes = [Image.frombytes('L', (width, height), raw[i * size:(i + 1) * size]) for i in range(3)]
        self.width, self.height = width, height

    def colours(self, axis, low, high, first=0, end=None):
        means = []
        for plane in self.planes:
            lines = band(plane, axis, low, high)
            data, stride = lines.tobytes(), lines.width
            means.append([sum(data[i * stride:(i + 1) * stride]) / stride
                          for i in range(first, lines.height if end is None else end)])
        return [bt601(*values) for values in zip(*means)]

    def blues(self, axis, low, high):
        return [blue for _, _, blue in self.colours(axis, low, high)]

    @staticmethod
    def blue_level(clip):
        return ramp_tint(clip)

    def coordinates(self, axis, low, high, clip, first, end):
        """Lines [first, end): mean (source row, source column), continuous (pixel centre = index + 1/2)."""
        return [(ramp_row(red, SOURCE_EXTENT['rows']) + 0.5, ramp_row(green, SOURCE_EXTENT['columns']) + 0.5)
                for red, green, _ in self.colours(axis, low, high, first, end)]


class Calibration:
    """How this Chrome colours each ramp clip, measured at native size.

    Chrome colour-manages the tagged BT.601/SMPTE-C clips into its output space with a
    channel-mixing, non-linear transform (measured on Chrome 156: source red 33 reads
    38..67 along one source row, depending on green), so ``ramp_row`` cannot read a
    screenshot directly. A plain ``<video>`` at the clip's own 540x720 size, outside
    the runtime, shows source pixel (row, column) at screen x = column, y = row, so each
    clip's screenshot is a table from screen (red, green) to source (row, column). It
    calibrates colour only; every geometric fact in the parity check comes from the
    runtime under test. A browser that does not colour-manage gives a near-identity table.
    """

    def __init__(self, images: list[Image.Image]):
        width = RAMP_SIZE[0]
        self.tables, self.tints = [], []
        for image in images:
            if image.size != RAMP_SIZE:
                raise AssertionError(f'calibration image is {image.size}, expected {RAMP_SIZE}')
            data = image.tobytes()
            sums: dict[tuple[int, int], list[float]] = {}
            for index, key in enumerate(zip(data[0::3], data[1::3])):
                entry = sums.setdefault(key, [0.0, 0.0, 0])
                entry[0] += index // width + 0.5
                entry[1] += index % width + 0.5
                entry[2] += 1
            self.tables.append({key: (row / n, column / n) for key, (row, column, n) in sums.items()})
            blues = sorted(data[2::3])
            self.tints.append(blues[len(blues) // 2])
        if any(b - a < MIN_TINT_GAP for a, b in zip(self.tints, self.tints[1:])):
            raise AssertionError(f'calibrated clip tints are not separable: {self.tints}')

    def lookup(self, clip: int, red: int, green: int) -> tuple[float, float]:
        table = self.tables[clip]
        found = table.get((red, green))
        if found is not None:
            return found
        # A colour between calibration samples (scaling interpolates): the nearest ring of entries.
        for radius in range(1, 5):
            ring = [table[key] for key in ((red + dr, green + dg) for dr in range(-radius, radius + 1)
                                           for dg in range(-radius, radius + 1)
                                           if max(abs(dr), abs(dg)) == radius) if key in table]
            if ring:
                found = (sum(r for r, _ in ring) / len(ring), sum(c for _, c in ring) / len(ring))
                table[red, green] = found
                return found
        raise AssertionError(f'screen colour ({red}, {green}) is not a colour of clip {clip}')


class ScreenReader:
    """A device-pixel-ratio-1 screenshot, read through the clip calibration."""

    STEP = 2  # every second pixel across a line is enough for a per-line mean

    def __init__(self, png: bytes, calibration: Calibration):
        image = Image.open(io.BytesIO(png)).convert('RGB')
        self.planes = image.split()
        self.width, self.height = image.size
        self.calibration = calibration

    def blues(self, axis, low, high):
        lines = band(self.planes[2], axis, low, high)
        data, stride = lines.tobytes(), lines.width
        return [sum(data[i * stride:(i + 1) * stride]) / stride for i in range(lines.height)]

    def blue_level(self, clip):
        return self.calibration.tints[clip]

    def coordinates(self, axis, low, high, clip, first, end):
        reds, greens = (band(plane, axis, low, high) for plane in self.planes[:2])
        stride, red, green = reds.width, reds.tobytes(), greens.tobytes()
        lookup = self.calibration.lookup
        lines = []
        for line in range(first, end):
            points = [lookup(clip, red[i], green[i]) for i in range(line * stride, (line + 1) * stride, self.STEP)]
            lines.append((sum(r for r, _ in points) / len(points), sum(c for _, c in points) / len(points)))
        return lines


def fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares line ``value = a + b * position``."""
    n = len(points)
    mean_p = sum(p for p, _ in points) / n
    mean_v = sum(v for _, v in points) / n
    slope = sum((p - mean_p) * (v - mean_v) for p, v in points) / sum((p - mean_p) ** 2 for p, _ in points)
    return mean_v - slope * mean_p, slope


def source_range(reader, axis: str, band_low: int, band_high: int, clip: int, which: int, first: int, end: int,
                 low: int, high: int) -> tuple[float, float]:
    """Source coordinates shown at pixel edges ``low`` and ``high``, fitted over lines [first, end).

    Cover magnifies uniformly, so the source coordinate is linear in the screen
    coordinate; the fit is extrapolated to the strip's visible edges.
    """
    lines = reader.coordinates(axis, band_low, band_high, clip, first, end)
    intercept, slope = fit([(first + i + 0.5, values[which]) for i, values in enumerate(lines)])
    return intercept + slope * low, intercept + slope * high


def strip_edges(blues: list[float], tints: list[float], orientation: str) -> list[tuple[float, float]]:
    """Visible extent [start, end) of every strip along the stack axis, from the clip tints.

    Each line names the clip with the nearest tint, within half the closest pair of
    tints. Next to a strip edge the export's subsampled chroma rings (a line can read
    darker than any tint or nearer the neighbour's), so only lines within ``EDGE`` of a
    transition may be unnamed; a gap between two strips is split at its middle. Any
    other unnamed line, a clip out of order or a missing clip fails.
    """
    count = len(tints)
    limit = min((abs(a - b) for a in tints for b in tints if a != b), default=2 * MIN_TINT_GAP) / 2
    labels = []
    for blue in blues:
        nearest = min(range(count), key=lambda k: abs(blue - tints[k]))
        labels.append(nearest if abs(blue - tints[nearest]) < limit else None)
    named = [(line, label) for line, label in enumerate(labels) if label is not None]
    # Order: a strip may end with a ringing line that names its successor; a run of
    # fewer than EDGE lines is such a line, not a strip of its own.
    runs = []
    for line, label in named:
        if runs and runs[-1][0] == label:
            runs[-1][2] = line + 1
        else:
            runs.append([label, line, line + 1])
    runs = [run for run in runs if run[2] - run[1] >= EDGE]
    merged = []
    for label, first, end in runs:
        if merged and merged[-1][0] == label:
            merged[-1][2] = end
        else:
            merged.append([label, first, end])
    if [label for label, _, _ in merged] != list(range(count)):
        raise AssertionError(f'{orientation}: strips read {[label for label, _, _ in merged]}, '
                             f'expected clips 0..{count - 1} in loop order')
    for (_, _, end), (_, first, _) in zip(merged, merged[1:]):
        if first - end > 2 * EDGE:
            raise AssertionError(f'{orientation}: lines {end}..{first - 1} name no clip between two strips')
    for _, first, end in merged:
        stray = [line for line in range(first, end) if labels[line] is None and
                 min(line - first, end - 1 - line) >= EDGE]
        if stray:
            raise AssertionError(f'{orientation}: lines {stray} inside a strip name no clip')
    bounds = [0.0] + [(end + first) / 2 for (_, _, end), (_, first, _) in zip(merged, merged[1:])] + [float(len(blues))]
    return list(zip(bounds, bounds[1:]))


def measure(reader, orientation: str, count: int) -> list[dict]:
    """Per strip: its visible pixel extent and the source rows and columns it shows."""
    portrait = orientation == 'portrait'
    stack_axis, cross_axis = ('y', 'x') if portrait else ('x', 'y')
    cross_extent = reader.width if portrait else reader.height
    margin = cross_extent // 10
    # Coordinates are (row, column): rows run along y, columns along x.
    along, across = (0, 'rows') if portrait else (1, 'columns'), (1, 'columns') if portrait else (0, 'rows')
    edges = strip_edges(reader.blues(stack_axis, margin, cross_extent - margin),
                        [reader.blue_level(k) for k in range(count)], orientation)
    strips = []
    for k, (start, end) in enumerate(edges):
        first, last = math.ceil(start) + EDGE, math.floor(end) - EDGE
        if last - first < EDGE:
            raise AssertionError(f'{orientation}: strip {k} is only {end - start} lines')
        which, name = along
        shown = {name: source_range(reader, stack_axis, margin, cross_extent - margin, k, which, first, last,
                                    start, end)}
        which, name = across
        shown[name] = source_range(reader, cross_axis, first, last, k, which, EDGE, cross_extent - EDGE,
                                   0, cross_extent)
        strips.append(dict(strip=k, pixels=[start, end], rows=shown['rows'], columns=shown['columns']))
    return strips


def stretched(slice_rect) -> dict:
    """What the old ``fill`` path showed: the whole slice window (or the whole clip) in every cell."""
    if slice_rect is None:
        return {'rows': (0.0, float(SOURCE_EXTENT['rows'])), 'columns': (0.0, float(SOURCE_EXTENT['columns']))}
    sx, sy, sw, sh = (float(Fraction(value)) for value in slice_rect)
    return {'rows': (sy * SOURCE_EXTENT['rows'], (sy + sh) * SOURCE_EXTENT['rows']),
            'columns': (sx * SOURCE_EXTENT['columns'], (sx + sw) * SOURCE_EXTENT['columns'])}


def deviation(a: dict, b: dict, axis: str) -> float:
    """Largest endpoint difference on ``axis``, as a fraction of the source extent."""
    return max(abs(a[axis][0] - b[axis][0]), abs(a[axis][1] - b[axis][1])) / SOURCE_EXTENT[axis]


def stretch_factor(measured: dict, prediction: dict) -> float:
    """How much more source the stretched prediction shows than the strip, on its most cropped axis."""
    return max((prediction[axis][1] - prediction[axis][0]) / (measured[axis][1] - measured[axis][0])
               for axis in SOURCE_EXTENT)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserExportParityTests(unittest.TestCase):
    """Seam test 7 at 390x844 portrait and 1280x720 landscape, N=1, 5 and 12."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        prepare()
        cls.cases = {}
        for count in COUNTS:
            state = c.load_state(ROOT / f'state-strips-{count}.json')
            # The strips default carries the slice; the variant disables it as the export tests do.
            if not state['slice'].get('enabled'):
                raise AssertionError(f'state-strips-{count}.json should carry the strips zoom slice')
            off = copy.deepcopy(state)
            off['slice'] = {'enabled': False}
            c.validate_state(off)
            off_path = ROOT / f'parity-strips-{count}-no-slice.json'
            c.save_state(off, off_path)
            build_preview(off_path, ROOT / f'preview-parity-strips-{count}-no-slice')
            for variant, full, preview in (('slice', state, f'preview-strips-{count}'),
                                           ('no-slice', off, f'preview-parity-strips-{count}-no-slice')):
                export = copy.deepcopy(full)
                export['frames'] = EXPORT_FRAMES
                frame0 = c.resolve_at(full, 0)
                if c.resolve_at(export, 0) != frame0:
                    raise AssertionError('shortening the export must not change frame 0')
                export_path = ROOT / f'parity-strips-{count}-{variant}-export.json'
                c.save_state(export, export_path)
                cls.cases[count, variant] = dict(preview=preview, export=export_path, frame0=frame0)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_Quiet, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=browser_executable(), headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required'])
        cls.measured = {}
        cls.calibration = cls.calibrate()

    @classmethod
    def calibrate(cls) -> Calibration:
        """Screenshot every ramp clip in a plain ``<video>`` at its native size (see ``Calibration``)."""
        width, height = RAMP_SIZE
        clips = max(COUNTS)
        across = 4
        videos = ''.join(f'<video src="media/strip-{k + 1}.mp4" muted playsinline preload="auto" style="position:'
                         f'absolute;left:{width * (k % across)}px;top:{height * (k // across)}px;width:{width}px;'
                         f'height:{height}px"></video>' for k in range(clips))
        page_path = ROOT / 'parity-calibration.html'
        page_path.write_text('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#000}'
                             f'</style>{videos}\n')
        rows = -(-clips // across)
        context = cls.browser.new_context(viewport={'width': width * across, 'height': height * rows},
                                          device_scale_factor=1)
        try:
            page = context.new_page()
            page.goto(f'{cls.base}/{page_path.name}')
            page.wait_for_function("[...document.querySelectorAll('video')].every(v => v.readyState >= 2)",
                                   timeout=60000)
            page.evaluate("""() => Promise.all([...document.querySelectorAll('video')].map(v => new Promise(done => {
              v.requestVideoFrameCallback(() => { v.pause(); done(); }); v.play(); })))""")
            page.evaluate('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
            sheet = Image.open(io.BytesIO(page.screenshot())).convert('RGB')
        finally:
            context.close()
        return Calibration([sheet.crop((width * (k % across), height * (k // across),
                                        width * (k % across) + width, height * (k // across) + height))
                            for k in range(clips)])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        report = [dict(count=count, variant=variant, orientation=orientation, **values)
                  for (count, variant, orientation), values in sorted(cls.measured.items())]
        (ROOT / 'evidence').mkdir(exist_ok=True)
        (ROOT / 'evidence' / 'browser-export-parity.json').write_text(json.dumps(report, indent=2) + '\n')

    # Export side -----------------------------------------------------------------

    def export(self, case, orientation, width, height) -> Path:
        output = ROOT / 'renders' / f'{case["export"].stem}-{orientation}.mp4'
        command = [sys.executable, '-m', 'simvltanea.rendering.render_triptych', '--state', str(case['export']),
                   '--orientation', orientation, '--width', str(width), '--height', str(height),
                   '--preset', 'ultrafast', '--output', str(output)]
        done = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-4000:])
        return output

    # Browser side ----------------------------------------------------------------

    def screenshots(self, case, count) -> dict:
        """Load the staged preview, play, pause on the frame-0 slice windows, screenshot both orientations."""
        expected = {loop['id']: loop.get('slice_rect') for loop in case['frame0']['loops']}
        _, width, height = VIEWPORTS[0]
        context = self.browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'{self.base}/{case["preview"]}/')
        page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error', timeout=60000)
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        page.evaluate("document.querySelectorAll('#runtime-status,#runtime-note').forEach(e => e.remove())")
        page.evaluate('compositionRuntime.start()')
        page.wait_for_function('[...compositionRuntime.nodes.values()].every(n => n.callbacks >= 2)', timeout=60000)
        # Pausing freezes the picture; the slice check below makes the timing irrelevant.
        page.evaluate('compositionRuntime.pause()')
        page.wait_for_function("""() => { const r = compositionRuntime;
          return !r.running && !r.starting && [...r.nodes.values()].every(n => !n.busy && n.media.paused); }""",
                               timeout=30000)
        shots = {}
        for orientation, width, height in VIEWPORTS:
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_function("""([w, h]) => {
              const r = compositionRuntime, box = document.querySelector('#stage').getBoundingClientRect();
              const last = r.events.filter(e => e.type === 'layout').at(-1);
              return box.width === w && box.height === h && last && last.width === w && last.height === h &&
                [...r.nodes.values()].every(n => n.media.readyState >= 2 && !n.media.seeking);
            }""", arg=[width, height], timeout=30000)
            page.evaluate('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
            state = page.evaluate("""() => ({orientation: compositionRuntime.orientation, frame: compositionRuntime.frame,
              slices: Object.fromEntries([...compositionRuntime.nodes.values()].map(n => [n.id,
                n.span.slice_rect ?? null]))})""")
            png = page.screenshot()
            after = page.evaluate("""() => Object.fromEntries([...compositionRuntime.nodes.values()].map(n => [n.id,
                n.span.slice_rect ?? null]))""")
            self.assertEqual(state['orientation'], orientation)
            self.assertEqual(state['slices'], expected,
                             f'N={count}: the paused browser frame {state["frame"]} is not on the frame-0 slice windows')
            self.assertEqual(after, expected)
            shots[orientation] = (png, state['frame'])
        self.assertEqual(errors, [])
        return shots

    # Measurement -----------------------------------------------------------------

    def measurements(self, count, variant) -> dict:
        key = (count, variant)
        if (count, variant, VIEWPORTS[0][0]) not in self.measured:
            case = self.cases[key]
            shots = self.screenshots(case, count)
            for orientation, width, height in VIEWPORTS:
                png, frame = shots[orientation]
                browser = ScreenReader(png, self.calibration)
                self.assertEqual((browser.width, browser.height), (width, height))
                exported = ExportReader(self.export(case, orientation, width, height), width, height)
                self.measured[count, variant, orientation] = dict(
                    browser_frame=frame,
                    browser=measure(browser, orientation, count), export=measure(exported, orientation, count),
                    stretched=[stretched(loop.get('slice_rect')) for loop in case['frame0']['loops']])
        return {orientation: self.measured[count, variant, orientation] for orientation, _, _ in VIEWPORTS}

    def assert_parity(self, variant):
        for count in COUNTS:
            for orientation, values in self.measurements(count, variant).items():
                self.assertEqual(len(values['browser']), count)
                for browser, export in zip(values['browser'], values['export']):
                    for axis in SOURCE_EXTENT:
                        with self.subTest(count=count, orientation=orientation, strip=browser['strip'], axis=axis):
                            self.assertLessEqual(deviation(browser, export, axis), PARITY,
                                                 f'browser {browser[axis]} vs export {export[axis]}')

    def test_strips_with_the_slice_show_the_same_source_rows_in_browser_and_export(self):
        self.assert_parity('slice')

    def test_strips_without_a_slice_show_the_same_source_rows_in_browser_and_export(self):
        self.assert_parity('no-slice')

    def test_the_old_fill_stretch_would_fail_the_parity_check(self):
        """The stretched prediction lies more than 5 percent from what either side shows (N=1: see PARITY)."""
        for variant in VARIANTS:
            for count in COUNTS:
                margin = STRETCH_MARGIN if count > 1 else PARITY
                for orientation, values in self.measurements(count, variant).items():
                    for k, prediction in enumerate(values['stretched']):
                        for side in ('browser', 'export'):
                            measured = values[side][k]
                            miss = max(deviation(measured, prediction, axis) for axis in SOURCE_EXTENT)
                            with self.subTest(variant=variant, count=count, orientation=orientation, strip=k,
                                              side=side):
                                self.assertGreater(miss, margin, f'{measured} vs stretched {prediction}')
                                self.assertGreater(stretch_factor(measured, prediction), STRETCH_FACTOR)

    def test_the_slice_changes_what_each_strip_shows(self):
        """The variants differ by far more than the tolerance: the slice is really applied on both sides."""
        for count in COUNTS:
            with_slice, without = self.measurements(count, 'slice'), self.measurements(count, 'no-slice')
            for orientation, _, _ in VIEWPORTS:
                for side in ('browser', 'export'):
                    for on, off in zip(with_slice[orientation][side], without[orientation][side]):
                        with self.subTest(count=count, orientation=orientation, side=side, strip=on['strip']):
                            self.assertGreater(max(deviation(on, off, axis) for axis in SOURCE_EXTENT),
                                               STRETCH_MARGIN)


if __name__ == '__main__':
    unittest.main()
