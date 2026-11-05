"""Executed proofs for the SIMVLTANEA web studio (browser_studio + browser.studio.js).

The staged studio is served from a local HTTP server under a subpath and driven
in the installed Chrome through Playwright's real file input. Every video is
synthetic and generated at test time by FFmpeg under var/work; nothing personal
is read and nothing generated is committed. The phone-like fixtures mimic the
measured properties of real exported motion clips: QuickTime MOV, H.264 High
with full-range yuvj420p or HEVC hvc1, a rotation tag on landscape-coded
frames, variable frame rate and an audio track in every clip.

Requires Python Playwright, an installed Chromium/Chrome, FFmpeg/ffprobe (with
libx264, libx265 and prores_ks) and Node.js. Missing tools fail; nothing skips.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path

import simvltanea.authoring.composition as c
from simvltanea.browser import stage_studio, StudioStagingError
from simvltanea.browser.browser_runtime import HERE
from simvltanea.browser.browser_studio import INDEX_HTML, STUDIO_FILES, studio_files
from simvltanea.browser.layout_bundle import authored_layout_bundle
from simvltanea.browser.test_browser_runtime import browser_executable
from simvltanea.paths import WORK_DIR
from tools.verification.verify_public_site import private_path_fragments

STUDIO_JS = HERE / 'browser.studio.js'
ROOT = WORK_DIR / 'browser-studio'
FIXTURES = ROOT / 'fixtures'
SITE = ROOT / 'site'
SUBPATH = 'simvltanea/studio'
FPS = 24
MIB = 1024 * 1024
# Seven distinct H.264 MP4 loops with AAC audio and pairwise different periods.
LOOPS = [(f'loop-{index}.mp4', seconds, hue) for index, (seconds, hue) in
         enumerate(zip((1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0), (0, 50, 100, 150, 200, 250, 300)), 1)]


def tool(name: str) -> str:
    for candidate in (shutil.which(name), f'/opt/homebrew/bin/{name}', f'/usr/local/bin/{name}'):
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(f'{name} is required for the studio proofs (no skip substituted)')


def ffmpeg(*arguments: str) -> None:
    subprocess.run([tool('ffmpeg'), '-v', 'error', '-y', *arguments], check=True, timeout=300)


def probe(path: Path) -> dict:
    completed = subprocess.run(
        [tool('ffprobe'), '-v', 'error', '-show_entries',
         'stream=codec_type,codec_name,codec_tag_string,profile,width,height,pix_fmt,color_range,'
         'avg_frame_rate,r_frame_rate,duration:stream_side_data=rotation:format=duration,format_name',
         '-of', 'json', str(path)], check=True, capture_output=True, text=True, timeout=60)
    return json.loads(completed.stdout)


def video_stream(facts: dict) -> dict:
    return next(stream for stream in facts['streams'] if stream['codec_type'] == 'video')


def prepare_fixtures() -> dict[str, Path]:
    """Generate (once per checkout) the synthetic loops and phone-like clips."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    paths = {}
    tone = ['-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000']
    for name, seconds, hue in LOOPS:
        target = paths[name] = FIXTURES / name
        if not target.exists():
            ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size=192x144:rate=30,hue=h={hue}', *tone, '-t', str(seconds),
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                   '-shortest', str(target))
    source = ['-f', 'lavfi', '-i', 'testsrc2=size=480x360:rate=30', *tone]
    jobs = {
        # Live-photo-like H.264 High, full-range yuvj420p, smpte170m, AAC, MOV.
        'phone-h264.mov': [*source, '-t', '2', '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuvj420p',
                           '-color_range', 'pc', '-colorspace', 'smpte170m', '-c:a', 'aac'],
        # HEVC Main in an hvc1-tagged MOV with PCM audio.
        'phone-hevc.mov': [*source, '-t', '2', '-c:v', 'libx265', '-tag:v', 'hvc1', '-pix_fmt', 'yuv420p',
                           '-x265-params', 'log-level=error', '-c:a', 'pcm_s16le'],
        # Variable frame rate: irregular timestamps on a 1/600 time base.
        'phone-vfr.mov': [*source, '-t', '1.7', '-vf', "settb=1/600,setpts='N*20+mod(N*7\\,11)'",
                          '-fps_mode', 'passthrough', '-video_track_timescale', '600', '-c:v', 'libx264',
                          '-pix_fmt', 'yuv420p', '-c:a', 'aac'],
        # A codec Chrome cannot decode, in the same container.
        'prores.mov': ['-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30', '-t', '1', '-c:v', 'prores_ks',
                       '-profile:v', '2'],
    }
    for name, arguments in jobs.items():
        target = paths[name] = FIXTURES / name
        if not target.exists():
            ffmpeg(*arguments, str(target))
    # Landscape-coded frames with a -90 degree display matrix, as phones record portrait.
    rotated = paths['phone-rotated.mov'] = FIXTURES / 'phone-rotated.mov'
    if not rotated.exists():
        ffmpeg('-display_rotation:v:0', '-90', '-i', str(paths['phone-h264.mov']), '-c', 'copy', str(rotated))
    garbage = paths['garbage.mp4'] = FIXTURES / 'garbage.mp4'
    if not garbage.exists():
        garbage.write_bytes(hashlib.sha512(b'not a video').digest() * 2048)
    # Sparse: a size above the cap without writing (or reading) half a gigabyte.
    huge = paths['huge.mov'] = FIXTURES / 'huge.mov'
    if not huge.exists() or huge.stat().st_size != 513 * MIB:
        with huge.open('wb') as handle:
            handle.truncate(513 * MIB)
    return paths


def node(script: str, payload) -> object:
    completed = subprocess.run([tool('node'), '-e', script, str(STUDIO_JS)], input=json.dumps(payload),
                               capture_output=True, text=True, check=True, timeout=120)
    return json.loads(completed.stdout)


QUANTIZE = r'''
const S = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const results = JSON.parse(input).map(([value, fps]) => {
    const seconds = value === 'Infinity' ? Infinity : value;
    try { return {ok: true, value: S.quantizeDuration(seconds, fps)}; }
    catch (error) { return {ok: false, message: error.message}; }
  });
  process.stdout.write(JSON.stringify(results));
});
'''


SNIFF = r'''
const S = require(process.argv[1]); const fs = require('fs');
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  process.stdout.write(JSON.stringify(JSON.parse(input).map(path => {
    const sniff = S.sniffContainer(fs.readFileSync(path));
    return {sniff, queries: S.playbackQueries(S.blobType(path, '', sniff), sniff)};
  })));
});
'''


class StageStudioTests(unittest.TestCase):
    def setUp(self):
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        self.temp = Path(tempfile.mkdtemp(prefix='studio-stage-', dir=WORK_DIR))
        self.addCleanup(shutil.rmtree, self.temp, True)

    def digests(self, root: Path) -> dict[str, str]:
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.iterdir())}

    def test_flat_layout_exactly_as_specified(self):
        output = self.temp / 'nested' / 'studio'
        stage_studio(output)
        self.assertEqual(sorted(path.name for path in output.iterdir()), sorted(STUDIO_FILES))
        self.assertEqual(set(STUDIO_FILES), {'index.html', 'runtime.js', 'compiler.js', 'studio.js', 'layouts.json'})
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in output.iterdir()))
        self.assertEqual((output / 'runtime.js').read_bytes(), (HERE / 'browser.runtime.js').read_bytes())
        self.assertEqual((output / 'compiler.js').read_bytes(), (HERE / 'browser.compiler.js').read_bytes())
        self.assertEqual((output / 'studio.js').read_bytes(), STUDIO_JS.read_bytes())
        self.assertEqual(json.loads((output / 'layouts.json').read_text()), authored_layout_bundle())
        html = (output / 'index.html').read_text()
        self.assertEqual(html, INDEX_HTML)
        self.assertIn('<html lang="en">', html)
        self.assertIn('<title>SIMVLTANEA studio: your loops, playing at once</title>', html)
        for name in ('compiler.js', 'studio.js', 'runtime.js'):
            self.assertIn(f'<script src="{name}" defer></script>', html)
        # Order matters: the studio installs compositionIO before the runtime reads it.
        self.assertLess(html.index('compiler.js'), html.index('studio.js'))
        self.assertLess(html.index('studio.js'), html.index('runtime.js'))

    def test_staging_is_deterministic_and_overwrites_only_its_own_files(self):
        first, second = self.temp / 'a', self.temp / 'b'
        stage_studio(first)
        stage_studio(second)
        self.assertEqual(self.digests(first), self.digests(second))
        before = self.digests(first)
        (first / 'runtime.js').write_text('stale')
        stage_studio(first)
        self.assertEqual(self.digests(first), before)
        self.assertEqual(self.digests(first), {name: hashlib.sha256(data).hexdigest()
                                               for name, data in studio_files().items()})

    def test_refuses_foreign_content_without_writing(self):
        cases = {'foreign-file': lambda root: (root / 'notes.txt').write_text('mine'),
                 'hidden-file': lambda root: (root / '.DS_Store').write_bytes(b'x'),
                 'directory': lambda root: (root / 'media').mkdir(),
                 'owned-name-as-directory': lambda root: (root / 'studio.js').mkdir()}
        for name, populate in cases.items():
            with self.subTest(case=name):
                root = self.temp / name
                root.mkdir()
                populate(root)
                before = sorted(path.name for path in root.iterdir())
                with self.assertRaisesRegex(StudioStagingError, 'does not own'):
                    stage_studio(root)
                self.assertEqual(sorted(path.name for path in root.iterdir()), before)
        link = self.temp / 'link'
        link.symlink_to(self.temp / 'directory', target_is_directory=True)
        with self.assertRaisesRegex(StudioStagingError, 'symlink'):
            stage_studio(link)
        regular = self.temp / 'file'
        regular.write_text('x')
        with self.assertRaisesRegex(StudioStagingError, 'not a directory'):
            stage_studio(regular)
        self.assertIsInstance(StudioStagingError('x'), ValueError)

    def test_staged_text_is_public_safe_and_relative(self):
        output = self.temp / 'public'
        stage_studio(output)
        for path in output.iterdir():
            text = path.read_text(encoding='utf-8')
            with self.subTest(file=path.name):
                self.assertEqual(private_path_fragments(text), [])
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn(str(HERE), text)
                self.assertNotIn('http://', text.replace('http://www.w3.org', ''))
                self.assertNotIn('https://', text)
        self.assertFalse([path for path in output.iterdir() if path.name.startswith('.')])
        html = (output / 'index.html').read_text()
        self.assertIn("default-src 'none'", html)
        self.assertIn("script-src 'self'", html)

    def test_module_entry_stages_the_studio(self):
        src = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(src), str(src.parent)]))
        output = self.temp / 'cli'
        completed = subprocess.run([sys.executable, '-m', 'simvltanea.browser.browser_studio', '--output', str(output)],
                                   env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(sorted(path.name for path in output.iterdir()), sorted(STUDIO_FILES))


class QuantizationTests(unittest.TestCase):
    """quantizeDuration under Node, checked against Python-declared and probed durations."""

    @classmethod
    def setUpClass(cls):
        from simvltanea.generators.make_runtime_fixture import ROOT as PROOFS, prepare
        prepare()
        cls.proofs = PROOFS
        cls.fixtures = prepare_fixtures()

    def test_repository_fixtures_match_their_python_declared_durations(self):
        sources = json.loads((self.proofs / 'sources.json').read_text())['sources']
        probed = [float(probe(self.proofs / source['path'])['format']['duration']) for source in sources]
        results = node(QUANTIZE, [[seconds, FPS] for seconds in probed])
        state = c.load_state(self.proofs / 'state-7.json')
        for source, result in zip(sources, results):
            with self.subTest(source=source['id']):
                self.assertTrue(result['ok'], result)
                self.assertEqual(Fraction(result['value']['duration']), Fraction(source['duration']))
        # Python's own media binding accepts the browser-declared durations.
        declared = {source['id']: result['value']['duration'] for source, result in zip(sources, results)}
        for source in state['sources']:
            source['duration'] = declared[source['id']]
        self.assertEqual(len(c.media_paths(state, self.proofs)), 7)

    def test_generated_loops_are_within_one_frame_and_never_longer(self):
        names = [name for name, _, _ in LOOPS] + ['phone-h264.mov', 'phone-vfr.mov', 'phone-hevc.mov']
        probed = {name: Fraction(video_stream(probe(self.fixtures[name]))['duration']) for name in names}
        for fps in (24, 25, 30, 60):
            results = node(QUANTIZE, [[float(probed[name]), fps] for name in names])
            for name, result in zip(names, results):
                with self.subTest(fixture=name, fps=fps):
                    declared = Fraction(result['value']['duration'])
                    self.assertEqual(declared, Fraction(result['value']['frames'], fps))
                    self.assertLessEqual(declared, probed[name])
                    # The tolerance composition.media_paths enforces against ffprobe.
                    self.assertLessEqual(abs(declared - probed[name]), Fraction(1, fps))
        state = {'fps': FPS, 'sources': []}
        mp4 = [name for name, _, _ in LOOPS]
        for name, result in zip(mp4, node(QUANTIZE, [[float(probed[name]), FPS] for name in mp4])):
            data = self.fixtures[name].read_bytes()
            state['sources'].append(dict(id=name.split('.')[0], path=name, kind='video',
                                         sha256=hashlib.sha256(data).hexdigest(), duration=result['value']['duration']))
        self.assertEqual(len(c.media_paths(state, FIXTURES)), len(mp4))

    def test_float_spellings_and_refusals(self):
        accepted = [(2, 24), (0.7, 30), (1.2, 24), (8.0000001, 24), (7.9999999, 24), (1001 / 30000 * 90, 30),
                    (1.7, 24), (3.6, 24), (0.05, 24), (2.4333333333333336, 30), (1 / 3, 60), (600.0, 24)]
        results = node(QUANTIZE, accepted)
        for (seconds, fps), result in zip(accepted, results):
            with self.subTest(seconds=seconds, fps=fps):
                self.assertTrue(result['ok'], result)
                # Oracle: IEEE double arithmetic, as JavaScript performs it, with the one-microframe tolerance.
                frames = math.floor(seconds * fps + 1e-6)
                self.assertEqual(result['value']['frames'], frames)
                declared = Fraction(result['value']['duration'])
                self.assertEqual(declared, Fraction(frames, fps))
                self.assertLess(Fraction(seconds) - declared, Fraction(1, fps))
                self.assertLessEqual(declared - Fraction(seconds), Fraction(1, 10**6 * fps))
        self.assertEqual([result['value']['duration'] for result in results[:3]], ['2', '7/10', '7/6'])
        refused = [(0.04, 24), (0, 24), (-1, 24), ('Infinity', 24), ('2', 24), (2, 0), (2, 61), (2, 2.5)]
        for case, result in zip(refused, node(QUANTIZE, refused)):
            with self.subTest(case=case):
                self.assertFalse(result['ok'])

    def test_pure_helpers(self):
        script = r'''
const S = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const out = {
    counts: [0, 1, 2, 7, 8].map(S.countVerdict),
    sizes: [S.admitSize('a.mov', 100, 0), S.admitSize('b.mov', 400 * 1048576, 200 * 1048576),
            S.admitSize('c.mov', 0, 0), S.admitSize('d.mov', 512 * 1048576, 0)],
    frames: ['', '?seconds=4', '?seconds=0', '?seconds=abc', '?seconds=9999'].map(q => S.compositionFrames(q)),
    types: [S.blobType('x.MOV', '', null), S.blobType('x.mov', 'video/quicktime', null), S.blobType('x', '', {container: 'isobmff'}),
            S.blobType('x.bin', '', {container: 'quicktime'}), S.blobType('x', '', {container: 'unknown'})],
    suffixes: [S.mediaSuffix('a.MOV', null), S.mediaSuffix('a', {container: 'quicktime'}), S.mediaSuffix('a.b c', null)],
    cap: S.MAX_TOTAL_BYTES, fps: S.FPS, frames120: S.DEFAULT_SECONDS * S.FPS,
  };
  process.stdout.write(JSON.stringify(out));
});
'''
        out = node(script, None)
        self.assertEqual([item['ok'] for item in out['counts']], [False, False, True, True, False])
        self.assertRegex(out['counts'][1]['message'], r'^1 loop chosen\. Add at least 1 more\. .*2 to 7 loops')
        self.assertRegex(out['counts'][4]['message'], r'^8 loops chosen\. Remove 1 to continue\. ')
        self.assertIsNone(out['sizes'][0])
        self.assertRegex(out['sizes'][1], r'^b\.mov was not added: .*600 MiB, over the 512 MiB limit')
        self.assertRegex(out['sizes'][2], 'empty')
        self.assertIsNone(out['sizes'][3])
        self.assertEqual(out['frames'], [2880, 96, 2880, 2880, 14400])
        self.assertEqual(out['types'], ['video/quicktime', 'video/quicktime', 'video/mp4', 'video/quicktime',
                                        'video/mp4'])
        self.assertEqual(out['suffixes'], ['mov', 'mov', 'mp4'])
        self.assertEqual((out['cap'], out['fps'], out['frames120']), (512 * MIB, 24, 2880))

    def test_container_sniff_reports_rfc6381_codecs(self):
        script = SNIFF
        names = ['loop-1.mp4', 'phone-h264.mov', 'phone-hevc.mov', 'phone-rotated.mov', 'prores.mov', 'garbage.mp4']
        out = dict(zip(names, node(script, [str(self.fixtures[name]) for name in names])))
        self.assertEqual(out['loop-1.mp4']['sniff']['container'], 'isobmff')
        self.assertRegex(out['loop-1.mp4']['sniff']['codec']['string'], r'^avc1\.[0-9A-F]{6}$')
        self.assertEqual(out['phone-h264.mov']['sniff']['container'], 'quicktime')
        self.assertEqual(out['phone-h264.mov']['sniff']['codec']['string'][:7], 'avc1.64')  # High profile
        self.assertRegex(out['phone-hevc.mov']['sniff']['codec']['string'], r'^hvc1\.1\.6\.L\d+(\.[0-9A-F]{2})*$')
        self.assertEqual(out['phone-hevc.mov']['sniff']['codec']['label'], 'HEVC')
        self.assertEqual(out['phone-rotated.mov']['sniff']['codec'], out['phone-h264.mov']['sniff']['codec'])
        self.assertEqual(out['prores.mov']['sniff']['codec']['label'], 'ProRes 422')
        self.assertEqual(out['prores.mov']['queries'], {'decisive': True, 'queries': ['video/mp4; codecs="apcn"']})
        self.assertEqual(out['garbage.mp4']['sniff'], {'container': 'unknown', 'brand': None, 'codec': None})
        self.assertEqual(out['garbage.mp4']['queries'], {'decisive': False, 'queries': ['video/mp4']})


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class StudioBrowserTests(unittest.TestCase):
    """The staged studio, served under a subpath, driven through its real file input."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.fixtures = prepare_fixtures()
        cls.loops = [cls.fixtures[name] for name, _, _ in LOOPS]
        if SITE.exists():
            shutil.rmtree(SITE)
        stage_studio(SITE / SUBPATH)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                                                     functools.partial(QuietHandler, directory=str(SITE)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.url = f'{cls.origin}/{SUBPATH}/'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                             args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    # ---- helpers -----------------------------------------------------------

    def open(self, query='', width=1280, height=720, reduced_motion='no-preference'):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, reduced_motion=reduced_motion)
        self.addCleanup(context.close)
        page = context.new_page()
        page.requests, page.errors = [], []
        page.on('request', lambda request: page.requests.append(request.url))
        page.on('pageerror', lambda error: page.errors.append(str(error)))
        page.goto(self.url + query)
        page.wait_for_function('() => window.SimvltaneaStudio && window.SimvltaneaStudio.snapshot && '
                               'window.compositionRuntime')
        self.addCleanup(lambda: self.assertEqual(page.errors, []))
        return page

    def add(self, page, paths):
        page.set_input_files('#files', [str(path) for path in paths])
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy', timeout=60000)
        return page.evaluate('SimvltaneaStudio.snapshot()')

    def play(self, page):
        page.click('#start')
        page.wait_for_function('() => compositionRuntime.running || compositionRuntime.error', timeout=30000)
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        self.assertEqual(page.evaluate("document.querySelector('#studio').dataset.view"), 'player')

    def clocks(self, page, after=0.0):
        """A settled snapshot with each loop's own period from the compiled plan."""
        page.wait_for_function(
            '''after => { const r = compositionRuntime;
              return r.error || (r.running && r.snapshot().compositionTime > after &&
                [...r.nodes.values()].every(n => !n.busy && n.media && n.media.readyState >= 2)); }''',
            arg=after, timeout=30000)
        return page.evaluate('''() => {
          const r = compositionRuntime, s = r.snapshot();
          const number = v => { const [n, d = 1] = String(v).split('/').map(Number); return n / d; };
          const periods = Object.fromEntries(r.plan.sources.map(x => [x.id, number(x.duration)]));
          s.periods = s.loops.map(loop => periods[loop.source]);
          s.muted = [...document.querySelectorAll('#stage video')].map(v => v.muted && v.defaultMuted);
          s.inline = [...document.querySelectorAll('#stage video')].map(v => v.playsInline);
          s.sha = r.plan.sources.map(x => x.sha256);
          return s; }''')

    def assert_own_clocks(self, snapshot, tolerance=0.2):
        """Each loop sits at the shared composition time modulo its own period."""
        for loop, period in zip(snapshot['loops'], snapshot['periods']):
            expected = snapshot['compositionTime'] % period
            distance = abs(loop['currentTime'] - expected)
            self.assertLess(min(distance, period - distance), tolerance, (loop['id'], loop['currentTime'], expected))

    def assert_advancing(self, before, after):
        for old, new in zip(before['loops'], after['loops']):
            self.assertEqual(old['id'], new['id'])
            self.assertFalse(new['paused'])
            self.assertGreater(new['callbacks'], old['callbacks'])
            moved = (new['currentTime'] - old['currentTime']) % next(
                p for p, loop in zip(after['periods'], after['loops']) if loop['id'] == new['id'])
            self.assertGreater(moved, 0.05)

    def external(self, page):
        allowed = (f'{self.origin}/{SUBPATH}/', 'blob:', 'data:')
        return [url for url in page.requests if not url.startswith(allowed)]

    # ---- tests -------------------------------------------------------------

    def test_two_to_seven_loops_play_at_once_on_independent_clocks(self):
        for count in range(2, 8):
            with self.subTest(count=count):
                page = self.open('?seconds=30', width=390, height=844)
                snapshot = self.add(page, self.loops[:count])
                self.assertEqual(snapshot['count'], f'{count} loops chosen. Ready to play.')
                self.assertEqual(snapshot['refusals'], [])
                self.assertTrue(page.is_enabled('#start'))
                self.play(page)
                first = self.clocks(page, after=1.3)
                self.assertEqual(len(first['loops']), count)
                self.assertEqual(page.locator('#stage > .loop').count(), count)
                self.assertEqual(page.locator('#stage video').count(), count)
                self.assertEqual(len(set(first['sha'])), count)
                self.assertEqual(first['sha'], [loop['sha256'] for loop in snapshot['loops']])
                self.assertEqual(first['muted'], [True] * count)
                self.assertEqual(first['inline'], [True] * count)
                self.assertEqual(first['orientation'], 'portrait')
                self.assertEqual(page.locator('#stage video').evaluate_all(
                    'nodes => nodes.map(n => n.getAttribute("aria-label"))'),
                    [f'Loop {index} of {count}' for index in range(1, count + 1)])
                self.assert_own_clocks(first)
                page.wait_for_timeout(700)
                second = self.clocks(page)
                self.assert_own_clocks(second)
                self.assert_advancing(first, second)
                frames = page.evaluate('[compositionRuntime.plan.frames, compositionRuntime.plan.fps]')
                self.assertEqual(frames, [720, 24])
                # Every box sits inside the stage and no two overlap.
                rects = [loop['rect'] for loop in second['loops']]
                for index, a in enumerate(rects):
                    self.assertGreater(a['width'] * a['height'], 0)
                    for b in rects[index + 1:]:
                        self.assertFalse(a['x'] < b['x'] + b['width'] - 1 and b['x'] < a['x'] + a['width'] - 1 and
                                         a['y'] < b['y'] + b['height'] - 1 and b['y'] < a['y'] + a['height'] - 1)
                self.assertEqual(self.external(page), [])
                self.assertTrue(any(url.endswith(f'/{SUBPATH}/layouts.json') for url in page.requests))

    def test_default_piece_is_two_minutes_and_each_file_is_hashed_once(self):
        page = self.open()
        page.evaluate('''() => { window.digests = []; const digest = SubtleCrypto.prototype.digest;
          SubtleCrypto.prototype.digest = function (algorithm, data) {
            digests.push([algorithm, data.byteLength]); return digest.call(this, algorithm, data); }; }''')
        snapshot = self.add(page, self.loops[:2])
        self.assertIn('2 minutes', page.inner_text('#length'))
        sizes = [path.stat().st_size for path in self.loops[:2]]
        self.assertEqual(page.evaluate('digests'), [['SHA-256', size] for size in sizes])
        self.assertEqual([loop['sha256'] for loop in snapshot['loops']],
                         [hashlib.sha256(path.read_bytes()).hexdigest() for path in self.loops[:2]])
        self.play(page)
        self.assertEqual(page.evaluate('[compositionRuntime.plan.frames, compositionRuntime.plan.fps]'), [2880, 24])
        # The runtime's integrity check reused the digests: no second hash of any file.
        self.assertEqual(page.evaluate('digests'), [['SHA-256', size] for size in sizes])
        self.assertEqual(page.evaluate('compositionRuntime.plan.sources.map(s => s.bytes)'), sizes)

    def test_one_and_eight_loops_are_refused_never_padded_or_duplicated(self):
        page = self.open()
        snapshot = self.add(page, self.loops[:1])
        self.assertRegex(snapshot['count'], r'^1 loop chosen\. Add at least 1 more\. The studio plays 2 to 7 loops')
        self.assertTrue(page.is_disabled('#start'))
        page.evaluate("document.querySelector('#start').click()")
        self.assertEqual(page.evaluate("document.querySelector('#studio').dataset.view"), 'setup')
        snapshot = self.add(page, [*self.loops[1:], self.fixtures['phone-h264.mov']])
        self.assertEqual(len(snapshot['loops']), 8)
        self.assertRegex(snapshot['count'], r'^8 loops chosen\. Remove 1 to continue\. ')
        self.assertTrue(page.is_disabled('#start'))
        self.assertFalse(page.evaluate('compositionRuntime.ready'))
        self.assertEqual(page.locator('#stage video').count(), 0)
        # The same bytes under another name are refused, not admitted as a second loop.
        copy = FIXTURES / 'copy-of-loop-1.mp4'
        shutil.copyfile(self.loops[0], copy)
        snapshot = self.add(page, [copy])
        self.assertEqual(len(snapshot['loops']), 8)
        self.assertEqual(snapshot['refusals'], ['copy-of-loop-1.mp4 was not added: it is the same video as '
                                                'loop-1.mp4. Each loop needs its own video; nothing is duplicated.'])
        page.click('[aria-label="Remove phone-h264.mov"]')
        self.assertEqual(page.inner_text('#count'), '7 loops chosen. Ready to play.')
        self.play(page)
        self.assertEqual(len(self.clocks(page)['loops']), 7)

    def test_drop_zone_accepts_dropped_files(self):
        page = self.open()
        files = [dict(name=path.name, type='video/mp4', data=base64.b64encode(path.read_bytes()).decode())
                 for path in self.loops[:2]]
        states = page.evaluate('''files => {
          const transfer = new DataTransfer();
          for (const file of files) transfer.items.add(new File([Uint8Array.from(atob(file.data), c => c.charCodeAt(0))],
            file.name, {type: file.type}));
          const zone = document.querySelector('#drop'), seen = [];
          for (const type of ['dragenter', 'dragover']) {
            const event = new DragEvent(type, {dataTransfer: transfer, bubbles: true, cancelable: true});
            zone.dispatchEvent(event); seen.push([type, event.defaultPrevented, zone.classList.contains('over')]);
          }
          const drop = new DragEvent('drop', {dataTransfer: transfer, bubbles: true, cancelable: true});
          zone.dispatchEvent(drop); seen.push(['drop', drop.defaultPrevented, zone.classList.contains('over')]);
          return seen; }''', files)
        self.assertEqual(states, [['dragenter', True, True], ['dragover', True, True], ['drop', True, False]])
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy && SimvltaneaStudio.snapshot().loops.length === 2')
        self.assertEqual(page.inner_text('#count'), '2 loops chosen. Ready to play.')
        self.play(page)
        self.assertEqual(len(self.clocks(page)['loops']), 2)

    def test_remove_and_reorder_with_labelled_focusable_buttons(self):
        page = self.open()
        self.add(page, self.loops[:3])
        names = lambda: page.locator('#loops .loop-name').all_inner_texts()
        self.assertEqual(names(), ['loop-1.mp4', 'loop-2.mp4', 'loop-3.mp4'])
        for name in ('loop-1.mp4', 'loop-2.mp4', 'loop-3.mp4'):
            for label in (f'Move {name} up', f'Move {name} down', f'Remove {name}'):
                self.assertEqual(page.get_by_role('button', name=label, exact=True).count(), 1)
        self.assertTrue(page.is_disabled('[aria-label="Move loop-1.mp4 up"]'))
        self.assertTrue(page.is_disabled('[aria-label="Move loop-3.mp4 down"]'))
        page.click('[aria-label="Move loop-3.mp4 up"]')
        self.assertEqual(names(), ['loop-1.mp4', 'loop-3.mp4', 'loop-2.mp4'])
        self.assertEqual(page.evaluate("document.activeElement.getAttribute('aria-label')"), 'Move loop-3.mp4 up')
        page.keyboard.press('Enter')
        self.assertEqual(names(), ['loop-3.mp4', 'loop-1.mp4', 'loop-2.mp4'])
        page.click('[aria-label="Move loop-3.mp4 down"]')
        self.assertEqual(names(), ['loop-1.mp4', 'loop-3.mp4', 'loop-2.mp4'])
        # Keyboard focus is visible on list buttons.
        page.focus('[aria-label="Remove loop-1.mp4"]')
        page.keyboard.press('Shift+Tab')
        page.keyboard.press('Tab')
        focus = page.evaluate('''() => ({label: document.activeElement.getAttribute('aria-label'),
          visible: document.activeElement.matches(':focus-visible'),
          outline: getComputedStyle(document.activeElement).outlineStyle})''')
        self.assertEqual(focus, {'label': 'Remove loop-1.mp4', 'visible': True, 'outline': 'solid'})
        page.keyboard.press('Enter')
        self.assertEqual(names(), ['loop-3.mp4', 'loop-2.mp4'])
        self.assertEqual(page.evaluate("document.activeElement.getAttribute('aria-label')"), 'Remove loop-3.mp4')
        self.assertEqual(page.inner_text('#count'), '2 loops chosen. Ready to play.')
        snapshot = page.evaluate('SimvltaneaStudio.snapshot()')
        self.play(page)
        # The list order is the authored cell order: loop-1 is the first listed file.
        plan = page.evaluate('''() => compositionRuntime.plan.tracks.map(t => [t.id,
          compositionRuntime.plan.sources.find(s => s.id === t.spans[0].source).sha256])''')
        self.assertEqual(plan, [['loop-1', snapshot['loops'][0]['sha256']], ['loop-2', snapshot['loops'][1]['sha256']]])
        page.click('#change')
        self.assertEqual(page.evaluate("document.querySelector('#studio').dataset.view"), 'setup')
        page.click('[aria-label="Remove loop-2.mp4"]')
        self.assertTrue(page.is_disabled('#start'))
        self.assertRegex(page.inner_text('#count'), r'^1 loop chosen')

    def test_controls_play_pause_restart_orientation_and_change_loops(self):
        page = self.open('?seconds=60', width=1280, height=720)
        self.add(page, self.loops[:3])
        self.play(page)
        self.assertEqual(page.get_attribute('#toggle', 'aria-label'), 'Pause')
        # Pause freezes every clock; Play resumes them.
        page.click('#toggle')
        page.wait_for_function("() => stage.dataset.status === 'paused'")
        self.assertEqual(page.get_attribute('#toggle', 'aria-label'), 'Play')
        paused = page.evaluate('compositionRuntime.snapshot()')
        page.wait_for_timeout(400)
        still = page.evaluate('compositionRuntime.snapshot()')
        self.assertTrue(all(loop['paused'] for loop in still['loops']))
        self.assertEqual([loop['currentTime'] for loop in paused['loops']],
                         [loop['currentTime'] for loop in still['loops']])
        page.click('#toggle')
        page.wait_for_function("() => stage.dataset.status === 'playing'")
        # Orientation is presentation only: same media elements, clocks keep advancing.
        page.evaluate('window.initialMedia = [...compositionRuntime.nodes.values()].map(n => n.media)')
        before = self.clocks(page, after=1.0)
        self.assertEqual(before['orientation'], 'landscape')
        stage_shape = lambda: page.evaluate('(() => { const r = stage.getBoundingClientRect(); '
                                            'return [r.width, r.height]; })()')
        for choice, expected in (('portrait', 'portrait'), ('landscape', 'landscape'), ('auto', 'landscape')):
            page.check(f'input[name="orientation"][value="{choice}"]')
            page.wait_for_timeout(500)
            after = self.clocks(page)
            self.assertEqual(after['orientation'], expected)
            self.assertEqual(after['orientationOverride'], None if choice == 'auto' else choice)
            self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n, i) => '
                                          'n.media === initialMedia[i])'))
            self.assert_advancing(before, after)
            self.assert_own_clocks(after)
            width, height = stage_shape()
            if choice == 'portrait':
                self.assertLess(width, height)
            else:
                self.assertGreater(width, height)
            before = after
        events = page.evaluate('compositionRuntime.events.map(e => e.type)')
        self.assertIn('orientation-override', events)
        # Portrait in a landscape window keeps auto off: resize does not flip it.
        page.check('input[name="orientation"][value="portrait"]')
        page.set_viewport_size({'width': 1400, 'height': 700})
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate('compositionRuntime.snapshot().orientation'), 'portrait')
        page.check('input[name="orientation"][value="auto"]')
        # Restart returns every loop to the beginning of the piece.
        page.wait_for_function('() => compositionRuntime.snapshot().compositionTime > 2')
        page.click('#restart')
        page.wait_for_function("() => stage.dataset.status === 'playing' && compositionRuntime.running")
        restarted = self.clocks(page)
        self.assertLess(restarted['compositionTime'], 1.5)
        self.assertIn('transport-seek', page.evaluate('compositionRuntime.events.map(e => e.type)'))
        self.assert_own_clocks(restarted)
        # Change loops returns to the list, releases the media and plays a new set.
        page.click('#change')
        self.assertEqual(page.evaluate("document.querySelector('#studio').dataset.view"), 'setup')
        self.assertTrue(page.is_visible('#setup'))
        self.assertFalse(page.is_visible('#player'))
        self.assertEqual(page.evaluate('[compositionRuntime.ready, compositionRuntime.nodes.size]'), [False, 0])
        self.add(page, self.loops[3:5])
        self.assertEqual(page.inner_text('#count'), '5 loops chosen. Ready to play.')
        self.play(page)
        self.assertEqual(len(self.clocks(page)['loops']), 5)

    def test_auto_repeat_restarts_through_the_runtime_restart_path(self):
        page = self.open('?seconds=2')
        self.add(page, self.loops[:2])
        self.assertTrue(page.is_checked('#repeat'))
        self.play(page)
        page.wait_for_function('''() => { const e = compositionRuntime.events.map(x => x.type);
          return e.includes('finished') && e.lastIndexOf('restart') > e.lastIndexOf('finished') &&
            compositionRuntime.running; }''', timeout=15000)
        events = page.evaluate('compositionRuntime.events.map(e => e.type)')
        tail = events[events.index('finished'):]
        self.assertLess(tail.index('restart'), tail.index('transport-seek'))
        restarted = self.clocks(page)
        self.assertLess(restarted['compositionTime'], 2)
        self.assert_own_clocks(restarted)
        page.uncheck('#repeat')
        page.wait_for_function("() => stage.dataset.status === 'finished'", timeout=10000)
        page.wait_for_timeout(800)
        self.assertEqual(page.evaluate('[stage.dataset.status, compositionRuntime.running]'), ['finished', False])
        page.click('#toggle')
        page.wait_for_function('() => compositionRuntime.running')

    def test_space_toggles_playback_once(self):
        page = self.open('?seconds=60')
        self.add(page, self.loops[:2])
        page.evaluate("() => { window.toggles = []; new MutationObserver(() => toggles.push(stage.dataset.status))"
                      ".observe(stage, {attributes: true, attributeFilter: ['data-status']}); }")
        self.play(page)
        page.wait_for_function("() => stage.dataset.status === 'playing'")
        # Focus on the Play/Pause button: the button handles Space, the runtime does not repeat it.
        self.assertEqual(page.evaluate('document.activeElement.id'), 'toggle')
        page.evaluate('toggles.length = 0')
        page.keyboard.press('Space')
        page.wait_for_function("() => stage.dataset.status === 'paused'")
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate('toggles'), ['paused'])
        # From the page body, the runtime's document-level handler toggles.
        page.evaluate('document.activeElement.blur()')
        page.keyboard.press('Space')
        page.wait_for_function("() => stage.dataset.status === 'playing'")
        page.keyboard.press('Space')
        page.wait_for_function("() => stage.dataset.status === 'paused'")
        self.assertEqual(page.evaluate('toggles'), ['paused', 'playing', 'paused'])

    def test_size_cap_and_unplayable_files_get_their_own_messages(self):
        page = self.open()
        page.evaluate('''() => { window.objectUrls = []; const create = URL.createObjectURL;
          URL.createObjectURL = blob => { objectUrls.push([blob.size, blob.type]); return create(blob); }; }''')
        # canPlayType refuses ProRes before any media load; garbage passes it and fails the real load.
        self.add(page, [self.fixtures['prores.mov']])
        self.assertEqual(page.evaluate('objectUrls'), [])
        self.add(page, [self.fixtures['garbage.mp4']])
        self.assertEqual(page.evaluate('objectUrls'), [[self.fixtures['garbage.mp4'].stat().st_size, 'video/mp4']])
        snapshot = self.add(page, [self.fixtures['huge.mov'], self.fixtures['prores.mov'],
                                   self.fixtures['garbage.mp4'], self.loops[0]])
        self.assertEqual(snapshot['refusals'], [
            'huge.mov was not added: the chosen videos would total 513 MiB, over the 512 MiB limit for this page '
            '(the browser holds about twice that in memory).',
            'This browser cannot play prores.mov (video/quicktime, ProRes 422 apcn).',
            'This browser cannot play garbage.mp4 (video/mp4).'])
        self.assertEqual([loop['name'] for loop in snapshot['loops']], ['loop-1.mp4'])
        self.assertEqual(page.locator('#refusals li').all_inner_texts(), snapshot['refusals'])
        self.assertEqual(page.inner_text('#progress'), 'Checked 4 files: 1 added, 3 not added.')
        self.assertEqual(self.external(page), [])

    def test_phone_like_clips_rotation_mute_vfr_and_hevc(self):
        names = ['phone-h264.mov', 'phone-rotated.mov', 'phone-vfr.mov', 'phone-hevc.mov']
        facts = {name: probe(self.fixtures[name]) for name in names}
        for name, fact in facts.items():
            stream = video_stream(fact)
            self.assertIn('mov', fact['format']['format_name'])
            self.assertIn('audio', [item['codec_type'] for item in fact['streams']], name)
            self.assertEqual((stream['width'], stream['height']), (480, 360), name)
        self.assertEqual(video_stream(facts['phone-h264.mov'])['pix_fmt'], 'yuvj420p')
        self.assertEqual(video_stream(facts['phone-h264.mov'])['profile'], 'High')
        self.assertEqual(video_stream(facts['phone-hevc.mov'])['codec_name'], 'hevc')
        self.assertEqual(video_stream(facts['phone-hevc.mov'])['codec_tag_string'], 'hvc1')
        self.assertIn('pcm_s16le', [item['codec_name'] for item in facts['phone-hevc.mov']['streams']])
        self.assertEqual([item.get('rotation') for item in video_stream(facts['phone-rotated.mov'])['side_data_list']],
                         [-90])
        self.assertNotEqual(Fraction(video_stream(facts['phone-vfr.mov'])['avg_frame_rate']).denominator, 1)

        page = self.open('?seconds=30', width=844, height=390)
        snapshot = self.add(page, [self.fixtures[name] for name in names])
        [hevc] = node(SNIFF, [str(self.fixtures['phone-hevc.mov'])])
        hevc_query = hevc['queries']['queries'][0]
        hevc_playable = page.evaluate("q => document.createElement('video').canPlayType(q)", hevc_query) != ''
        # Recorded for the operator's report: what this Chrome does with the HEVC fixture.
        (ROOT / 'chrome-hevc-verdict.txt').write_text(
            f'{self.browser.version} {hevc_query}: {"plays" if hevc_playable else "refused"}\n')
        accepted = {loop['name']: loop for loop in snapshot['loops']}
        if hevc_playable:
            self.assertEqual(snapshot['refusals'], [])
            self.assertEqual(accepted['phone-hevc.mov']['codec'], 'HEVC')
        else:
            self.assertEqual(len(snapshot['refusals']), 1)
            self.assertRegex(snapshot['refusals'][0], r'^This browser cannot play phone-hevc\.mov \(video/quicktime, '
                                                      r'HEVC hvc1\.')
        for loop in accepted.values():
            self.assertEqual((loop['type'], loop['suffix'], loop['container']), ('video/quicktime', 'mov', 'quicktime'))
        # The installed Chrome applies the display matrix: the -90 degree clip reports portrait dimensions.
        self.assertEqual((accepted['phone-h264.mov']['width'], accepted['phone-h264.mov']['height']), (480, 360))
        self.assertEqual((accepted['phone-rotated.mov']['width'], accepted['phone-rotated.mov']['height']), (360, 480))
        for name, loop in accepted.items():
            probed = Fraction(video_stream(facts[name])['duration'])
            declared = Fraction(loop['declared'])
            self.assertEqual(declared, Fraction(loop['frames'], FPS))
            self.assertLessEqual(declared, Fraction(loop['duration']))
            self.assertLessEqual(abs(declared - probed), Fraction(1, FPS), name)
        self.assertEqual(accepted['phone-vfr.mov']['declared'], '5/3')
        self.play(page)
        first = self.clocks(page, after=1.0)
        self.assertEqual(len(first['loops']), len(accepted))
        self.assertEqual(first['muted'], [True] * len(accepted))
        self.assertTrue(page.evaluate("[...document.querySelectorAll('#stage video')].every(v => v.volume === 1 && "
                                      "v.muted && !v.controls)"))
        page.wait_for_timeout(1500)
        second = self.clocks(page)
        self.assert_advancing(first, second)
        self.assert_own_clocks(second, tolerance=0.25)
        # The runtime received the files' own Blob type through the io hook.
        self.assertEqual(page.evaluate('compositionRuntime.plan.sources.map(s => s.path.split(".").pop())'),
                         ['mov'] * len(accepted))
        self.assertEqual(self.external(page), [])

    def test_reduced_motion_never_autoplays_and_page_is_accessible_and_responsive(self):
        page = self.open(width=360, height=740, reduced_motion='reduce')
        self.assertEqual(page.evaluate('document.documentElement.lang'), 'en')
        self.assertEqual(page.title(), 'SIMVLTANEA studio: your loops, playing at once')
        self.assertEqual(page.locator('h1').inner_text(), 'SIMVLTANEA studio')
        self.assertIn('Your videos never leave this device.', page.inner_text('.privacy'))
        self.assertIn('Nothing is uploaded', page.inner_text('.privacy'))
        self.assertEqual(page.get_by_label('Choose videos').get_attribute('multiple'), '')
        self.assertTrue(page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'))
        self.add(page, self.loops[:2])
        page.wait_for_timeout(1000)
        self.assertEqual(page.evaluate('[compositionRuntime.running, compositionRuntime.ready]'), [False, False])
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 360)
        for name in ('Play these loops', 'Move loop-1.mp4 down', 'Remove loop-2.mp4'):
            self.assertEqual(page.get_by_role('button', name=name, exact=True).count(), 1)
        self.play(page)
        for name in ('Pause', 'Restart', 'Change loops'):
            self.assertEqual(page.get_by_role('button', name=name, exact=True).count(), 1)
        for name in ('Auto', 'Portrait', 'Landscape'):
            self.assertEqual(page.get_by_role('radio', name=name, exact=True).count(), 1)
        self.assertEqual(page.get_by_role('checkbox', name='Auto-repeat').count(), 1)
        self.assertEqual(page.get_by_role('group', name='Playback controls').count(), 1)
        geometry = page.evaluate('''() => { const s = stage.getBoundingClientRect(), b = bar.getBoundingClientRect();
          return {stage: [s.top, s.height, s.width], bar: [b.top, b.bottom], width: document.documentElement.scrollWidth,
                  height: innerHeight}; }''')
        self.assertEqual(geometry['stage'][0], 0)
        self.assertGreater(geometry['stage'][1], 0.55 * geometry['height'])
        self.assertEqual(geometry['stage'][2], 360)
        self.assertLessEqual(geometry['bar'][1], geometry['height'])
        self.assertAlmostEqual(geometry['bar'][0], geometry['stage'][1], delta=1)
        self.assertLessEqual(geometry['width'], 360)
        page.set_viewport_size({'width': 1440, 'height': 900})
        page.wait_for_timeout(300)
        wide = page.evaluate('(() => { const s = stage.getBoundingClientRect(); return [s.width, s.height]; })()')
        self.assertEqual(wide[0], 1440)
        self.assertEqual(page.evaluate('compositionRuntime.snapshot().orientation'), 'landscape')


class RuntimeHookTests(unittest.TestCase):
    """The io-hook relaxations leave staged previews (no hook) exactly as strict as before."""

    @classmethod
    def setUpClass(cls):
        from simvltanea.browser import test_browser_runtime as legacy
        from simvltanea.generators.make_runtime_fixture import ROOT as PROOFS
        legacy.BrowserTests.setUpClass.__func__(cls)
        cls.proofs = PROOFS

    @classmethod
    def tearDownClass(cls):
        from simvltanea.browser import test_browser_runtime as legacy
        legacy.BrowserTests.tearDownClass.__func__(cls)

    def test_staged_preview_without_io_hook_still_requires_mp4_and_256_mib(self):
        source = self.proofs / 'preview-2'
        target = self.proofs / 'preview-studio-mov-check'
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        self.addCleanup(shutil.rmtree, target, True)
        plan = json.loads((target / 'plan.json').read_text())
        for item in plan['sources']:
            old = target / item['path']
            item['path'] = item['path'][:-4] + '.mov'
            old.rename(target / item['path'])
        (target / 'plan.json').write_text(json.dumps(plan))
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(f'{self.base}/{target.name}/')
        page.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error', timeout=20000)
        self.assertEqual(page.evaluate('compositionRuntime.error'), 'Error: Invalid compiled plan: media path/kind')
        # The same plan through the io hook plays, with the Blob type the hook names.
        bytes_by_sha = {item['sha256']: list((target / item['path']).read_bytes()) for item in plan['sources']}
        page2 = self.browser.new_page()
        self.addCleanup(page2.close)
        page2.goto(f'{self.base}/{target.name}/plan.json')
        page2.set_content('<main id="stage"></main><p id="runtime-status"></p>')
        page2.evaluate('''({plan, bytes}) => {
          window.types = [];
          window.compositionIO = {plan: async () => plan, maxMediaBytes: 300 * 1048576,
            bytes: async s => new Uint8Array(bytes[s.sha256]).buffer,
            digest: async b => [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))]
              .map(v => v.toString(16).padStart(2, '0')).join(''),
            type: s => { types.push(s.id); return 'video/quicktime'; }};
        }''', dict(plan=plan, bytes=bytes_by_sha))
        page2.add_script_tag(content=(HERE / 'browser.runtime.js').read_text())
        page2.wait_for_function('window.compositionRuntime?.ready || window.compositionRuntime?.error', timeout=20000)
        self.assertIsNone(page2.evaluate('compositionRuntime.error'))
        self.assertEqual(page2.evaluate('types'), [item['id'] for item in plan['sources']])
        # The io hook may raise the memory guard to 512 MiB and no further.
        errors = page2.evaluate('''async plan => {
          const MiB = 1048576, out = [];
          for (const [bytes, max] of [[300 * MiB, undefined], [300 * MiB, 512 * MiB], [600 * MiB, 2 ** 40]]) {
            const variant = structuredClone(plan); variant.sources[0].bytes = bytes;
            compositionIO.plan = async () => variant; compositionIO.maxMediaBytes = max;
            await compositionRuntime.initialize().catch(() => {});
            out.push(compositionRuntime.error);
          }
          compositionIO.plan = async () => plan; compositionIO.maxMediaBytes = undefined;
          await compositionRuntime.initialize();
          out.push(compositionRuntime.error);
          return out;
        }''', plan)
        self.assertEqual(errors, ['Error: Invalid compiled plan: media metadata', 'Error: Media integrity: source-1',
                                  'Error: Invalid compiled plan: media metadata', None])


if __name__ == '__main__':
    unittest.main()
