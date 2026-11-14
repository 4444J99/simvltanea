"""Executed proofs for the SIMVLTANEA web studio (browser_studio + browser.studio.js).

The staged studio is served from a local HTTP server under a subpath and driven
in the installed Chrome through Playwright. It must play on load with no
interaction (built-in loops recorded in the page), reroll from ?seed, turn the
sound on at the first gesture, and accept the visitor's own files through the
real file input or a drop. Every video is
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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit

import simvltanea.authoring.composition as c
from simvltanea.browser import stage_studio, StudioStagingError
from simvltanea.browser.browser_runtime import HERE
from simvltanea.browser.browser_studio import INDEX_HTML, STUDIO_FILES, studio_files
from simvltanea.browser.layout_bundle import authored_layout_bundle, layout_bundle_v2
from simvltanea.browser.test_browser_runtime import browser_executable
from simvltanea.paths import WORK_DIR
from tools.publishing.stage_library_site import stage_library_site
from tools.verification.verify_public_site import private_path_fragments

STUDIO_JS = HERE / 'browser.studio.js'
ROOT = WORK_DIR / 'browser-studio'
FIXTURES = ROOT / 'fixtures'
SITE = ROOT / 'site'
SUBPATH = 'simvltanea/studio'
FPS = 24
MIB = 1024 * 1024
MEDIA_BUDGET_PROBE = r'''(() => {
  const videos=new Set(), create=Document.prototype.createElement;
  window.mediaBudget={populated:0,playing:0};
  const sample=()=>{const loaded=[...videos].filter(video=>video.getAttribute('src'));
    mediaBudget.populated=Math.max(mediaBudget.populated,loaded.length);
    mediaBudget.playing=Math.max(mediaBudget.playing,loaded.filter(video=>!video.paused).length);};
  Document.prototype.createElement=function(...args){const node=create.apply(this,args);
    if(node instanceof HTMLVideoElement) videos.add(node);return node;};
  const src=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'src');
  Object.defineProperty(HTMLMediaElement.prototype,'src',{...src,set(value){src.set.call(this,value);sample();}});
  for(const method of ['play','load']){const native=HTMLMediaElement.prototype[method];
    HTMLMediaElement.prototype[method]=function(...args){const result=native.apply(this,args);sample();return result;};}
  const tick=()=>{sample();requestAnimationFrame(tick)};requestAnimationFrame(tick);
})();'''
BUILTIN_RECORDING_GATE = r'''(() => {
  const NativeRecorder = MediaRecorder;
  let next = 0;
  window.heldBuiltinRecordings = new Map();
  window.MediaRecorder = class extends NativeRecorder {
    constructor(...args) { super(...args); this.builtinIndex = next++; }
    set onstop(handler) {
      super.onstop = event => heldBuiltinRecordings.set(this.builtinIndex, () => handler.call(this, event));
    }
  };
  window.releaseBuiltinRecordings = (indices = null) => {
    for (const [index, release] of heldBuiltinRecordings) {
      if (indices && !indices.includes(index)) continue;
      heldBuiltinRecordings.delete(index); release();
    }
  };
})();'''
REPOSITORY = HERE.parents[2]
# Twelve distinct H.264 MP4 loops with AAC audio and pairwise different periods.
LOOPS = [(f'loop-{index}.mp4', seconds, hue) for index, (seconds, hue) in
         enumerate(zip((1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0, 1.3, 1.6, 1.9, 2.2, 2.5),
                       (0, 50, 100, 150, 200, 250, 300, 25, 75, 125, 175, 225)), 1)]


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


LIBRARY = ROOT / 'library'
LIBRARY_SITES = ROOT / 'library-sites'
LIBRARY_CLIPS = 30
# A keyword no page text, attribute, log line or snapshot may ever contain: tags stay private to selection.
TAG_SENTINEL = 'zephyrine'
FAMILIES = {'authored': list(range(2, 8)), 'strips': list(range(1, 13))}


def library_shape(number: int) -> tuple[int, int]:
    return (144, 192) if number % 2 == 0 else (192, 144)


def library_tags(number: int) -> dict:
    # Six palette+shot looks, each in both orientations, so a roll can always avoid a repeated look.
    return {'keywords': [TAG_SENTINEL, f'word{number}'], 'mood': [('calm', 'bright', 'dark', 'still')[number % 4]],
            'shot': ('wide', 'close')[(number // 6) % 2], 'palette': [('blue', 'red', 'green')[(number // 2) % 3]]}


def library_entry(clip_id: str, number: int, size: int, seconds: float) -> dict:
    width, height = library_shape(number)
    return {'id': clip_id, 'file': f'clips/{clip_id}.mp4', 'width': width, 'height': height,
            'orientation': 'portrait' if height > width else 'landscape', 'duration_seconds': round(seconds, 3),
            'bytes': size, 'tags': library_tags(number)}


def prepare_library() -> dict:
    """A synthetic public-demo library: FFmpeg lavfi clips with a mono AAC tone, named by their digest."""
    raw = FIXTURES / 'library-raw'
    raw.mkdir(parents=True, exist_ok=True)
    if LIBRARY.exists():
        shutil.rmtree(LIBRARY)
    (LIBRARY / 'clips').mkdir(parents=True)
    clips = []
    for number in range(LIBRARY_CLIPS):
        width, height = library_shape(number)
        source = raw / f'clip-{number:02d}.mp4'
        if not source.exists():
            ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate=24,hue=h={number * 12}',
                   '-f', 'lavfi', '-i', f'sine=frequency={220 + number * 20}:sample_rate=48000',
                   '-t', f'{1 + (number % 7) * 0.2:.1f}', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                   '-c:a', 'aac', '-ac', '1', '-b:a', '64k', '-shortest', '-map_metadata', '-1',
                   '-movflags', '+faststart', str(source))
        data = source.read_bytes()
        clip_id = hashlib.sha256(data).hexdigest()[:12]
        (LIBRARY / 'clips' / f'{clip_id}.mp4').write_bytes(data)
        clips.append(library_entry(clip_id, number, len(data), float(probe(source)['format']['duration'])))
    manifest = {'schema': 'simvltanea.public-demo/1', 'clips': clips}
    (LIBRARY / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


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
        self.assertEqual(set(STUDIO_FILES), {'shell.js', 'watch.html', 'iterations.html', 'engineered-iterations.json',
                                           'iterations.json', 'index.html', 'runtime.js', 'compiler.js', 'studio.js', 'layouts.json',
                                           'workspace.html', 'lab.html', 'lab_model.js', 'lab_engine.js', 'lab_ui.js', 'lab_audio.js',
                                           'lab_compiler.js', 'lab_layouts.js'})
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in output.iterdir()))
        runtime_bytes = (output / 'runtime.js').read_bytes()
        self.assertIn(b'SimvltaneaLive', runtime_bytes)
        self.assertNotEqual(runtime_bytes, (HERE / 'browser.runtime.js').read_bytes())
        self.assertEqual((output / 'compiler.js').read_bytes(), (HERE / 'browser.compiler.js').read_bytes())
        self.assertEqual((output / 'studio.js').read_bytes(), STUDIO_JS.read_bytes())
        self.assertEqual(json.loads((output / 'layouts.json').read_text()), layout_bundle_v2())
        html = (output / 'watch.html').read_text()
        self.assertEqual((output / 'watch.html').read_text(), INDEX_HTML)
        self.assertIn('<html lang="en">', html)
        self.assertIn('<title>SIMVLTANEA studio: loops on their own clocks</title>', html)
        for name in ('compiler.js', 'studio.js', 'runtime.js'):
            self.assertIn(f'<script src="{name}" defer></script>', html)
        # Studio creates its live session from the already loaded runtime module.
        self.assertLess(html.index('compiler.js'), html.index('runtime.js'))
        self.assertLess(html.index('runtime.js'), html.index('studio.js'))

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
        # Only the fixed public media and historical deployment catalogs may use HTTPS.
        # Keep exact URLs, rather than permitting arbitrary paths on these hosts.
        lab_https_urls = {
            'lab.html': {'https://upload.wikimedia.org'},
            'iterations.json': {"https://2056b2b0.loop-compositor-studio.pages.dev","https://6874f745.loop-compositor-studio.pages.dev","https://bf6d702a.loop-compositor-studio.pages.dev","https://5af076c9.loop-compositor-studio.pages.dev","https://2ed9367c.loop-compositor-studio.pages.dev","https://ad500a11.loop-compositor-studio.pages.dev","https://c58f18b7.loop-compositor-studio.pages.dev","https://77791df4.loop-compositor-studio.pages.dev","https://9b3510be.loop-compositor-studio.pages.dev","https://504efa8c.loop-compositor-studio.pages.dev","https://77eb8fcc.loop-compositor-studio.pages.dev","https://fd14a75e.loop-compositor-studio.pages.dev","https://24390369.loop-compositor-studio.pages.dev","https://1b1f00b6.loop-compositor-studio.pages.dev","https://fafae868.loop-compositor-studio.pages.dev","https://677dcc96.loop-compositor-studio.pages.dev","https://32ac6d2d.loop-compositor-studio.pages.dev","https://6888f4c6.loop-compositor-studio.pages.dev","https://6061fab7.loop-compositor-studio.pages.dev","https://2b8d8b66.loop-compositor-studio.pages.dev","https://23fc1c10.loop-compositor-studio.pages.dev","https://9eb72122.loop-compositor-studio.pages.dev","https://97464aea.loop-compositor-studio.pages.dev","https://7a4ec3e2.loop-compositor-studio.pages.dev","https://b5586918.loop-compositor-studio.pages.dev","https://06279a78.loop-compositor-studio.pages.dev","https://16d63a9f.loop-compositor-studio.pages.dev","https://be6a4dbd.loop-compositor-studio.pages.dev","https://14238b8f.loop-compositor-studio.pages.dev","https://0620cdd3.loop-compositor-studio.pages.dev","https://3d678bfa.loop-compositor-studio.pages.dev","https://e5d9b9de.loop-compositor-studio.pages.dev","https://22267eb7.loop-compositor-studio.pages.dev","https://4fd3d646.loop-compositor-studio.pages.dev","https://0fe8f773.loop-compositor-studio.pages.dev","https://7365f793.loop-compositor-studio.pages.dev","https://3236dd5f.loop-compositor-studio.pages.dev","https://33af4610.loop-compositor-studio.pages.dev","https://278340dc.loop-compositor-studio.pages.dev","https://c1054351.loop-compositor-studio.pages.dev","https://1ce073eb.loop-compositor-studio.pages.dev","https://b459ec4b.loop-compositor-studio.pages.dev","https://5f07482e.loop-compositor-studio.pages.dev","https://cf2925a6.loop-compositor-studio.pages.dev","https://75cafe28.loop-compositor-studio.pages.dev","https://c30d12fb.loop-compositor-studio.pages.dev","https://be188707.loop-compositor-studio.pages.dev","https://3eb09914.loop-compositor-studio.pages.dev","https://559936a6.loop-compositor-studio.pages.dev","https://7fec0066.loop-compositor-studio.pages.dev","https://5fef4067.loop-compositor-studio.pages.dev","https://439faded.loop-compositor-studio.pages.dev","https://ed33655f.loop-compositor-studio.pages.dev","https://b7ef6276.loop-compositor-studio.pages.dev","https://eae78fa4.loop-compositor-studio.pages.dev","https://d8c2a026.loop-compositor-studio.pages.dev","https://fd79c985.loop-compositor-studio.pages.dev"},
            'workspace.html': {'https://upload.wikimedia.org'},
            'lab_ui.js': {
                'https://upload.wikimedia.org',
                'https://creativecommons.org/publicdomain/zero/1.0/deed.en',
                'https://commons.wikimedia.org/wiki/File:Rainy_night_in_Sham_Shui_Po.webm',
                'https://commons.wikimedia.org/wiki/File:StreamOfFlowingWater.webm',
                'https://commons.wikimedia.org/wiki/File:Flowing-water-100019.ogg',
                'https://commons.wikimedia.org/wiki/File:Flowing-water-100019.ogg#Licensing',
                'https://commons.wikimedia.org/wiki/File:Compressor_motor.ogg',
                'https://commons.wikimedia.org/wiki/File:Compressor_motor.ogg#Licensing',
                'https://upload.wikimedia.org/wikipedia/commons/transcoded/3/36/Rainy_night_in_Sham_Shui_Po.webm/Rainy_night_in_Sham_Shui_Po.webm.480p.vp9.webm',
                'https://upload.wikimedia.org/wikipedia/commons/transcoded/e/e0/StreamOfFlowingWater.webm/StreamOfFlowingWater.webm.480p.vp9.webm',
                'https://upload.wikimedia.org/wikipedia/commons/transcoded/2/26/Flowing-water-100019.ogg/Flowing-water-100019.ogg.mp3',
                'https://upload.wikimedia.org/wikipedia/commons/transcoded/d/db/Compressor_motor.ogg/Compressor_motor.ogg.mp3',
            },
        }
        iteration_urls = {
            'https://c1054351.loop-compositor-studio.pages.dev/',
            'https://33af4610.loop-compositor-studio.pages.dev/',
            'https://0fe8f773.loop-compositor-studio.pages.dev/',
            'https://3d678bfa.loop-compositor-studio.pages.dev/lab.html',
            'https://16d63a9f.loop-compositor-studio.pages.dev/lab.html',
            'https://fafae868.loop-compositor-studio.pages.dev/lab.html',
            'https://6061fab7.loop-compositor-studio.pages.dev/lab.html',
            'https://bf6d702a.loop-compositor-studio.pages.dev/workspace.html',
        }
        for name in ('index.html', 'iterations.html', 'engineered-iterations.json'):
            lab_https_urls[name] = iteration_urls
        for path in output.iterdir():
            text = path.read_text(encoding='utf-8')
            with self.subTest(file=path.name):
                self.assertEqual(private_path_fragments(text), [])
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn(str(HERE), text)
                self.assertNotIn('http://', text.replace('http://www.w3.org', ''))
                self.assertEqual(set(re.findall(r'''https://[^\s"'<>;]+''', text)),
                                 lab_https_urls.get(path.name, set()))
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
    counts: [[0, 5], [1, 5], [5, 5], [7, 7], [8, 7], [3, 5, [1, 2, 3, 4, 5]], [8, 7, [2, 3, 4, 5, 6, 7]],
             [1, 1], [12, 12], [2, null]].map(([count, panels, available]) => S.countVerdict(count, panels, available)),
    nearest: [[[2, 3, 4, 5, 6, 7], 12], [[2, 3, 4, 5, 6, 7], 1], [[1, 2, 3], 5], [[2, 4], 3], [[], 5]]
      .map(([counts, wanted]) => S.nearestCount(counts, wanted)),
    labels: [S.familyLabel('strips'), S.familyLabel('authored'), S.familyLabel('grid'), S.familyLabel('file', 'mine.json')],
    lines: [S.oneLine('a\n  b\r\nc', 'x.json'), S.oneLine('x.json, count 3: bad', 'x.json'), S.oneLine('plain')],
    defaults: [S.DEFAULT_PANELS, S.OWN_FAMILY, 'MAX_LOOPS' in S, 'MIN_LOOPS' in S],
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
        rule = 'Every panel plays one of your loops; nothing is padded, repeated or duplicated.'
        self.assertEqual([item['ok'] for item in out['counts']],
                         [False, False, True, True, False, False, False, True, True, False])
        self.assertEqual([item['message'] for item in out['counts']], [
            f'No loops chosen yet. Choose 5 videos for 5 panels. {rule}',
            f'1 loop chosen for 5 panels. Add 4 more. {rule}',
            '5 loops chosen. Ready to play.', '7 loops chosen. Ready to play.',
            f'8 loops chosen for 7 panels. Remove 1 loop. {rule}',
            f'3 loops chosen for 5 panels. Add 2 more, or set Panels to 3. {rule}',
            f'8 loops chosen for 7 panels. Remove 1 loop. {rule}',
            '1 loop chosen. Ready to play.', '12 loops chosen. Ready to play.',
            f'Choose a layout and a panel count first. {rule}'])
        self.assertEqual(out['nearest'], [7, 2, 3, 2, None])
        self.assertEqual(out['labels'], ['Strips', 'Authored', 'Grid', 'My file: mine.json'])
        self.assertEqual(out['lines'], ['x.json: a b c', 'x.json, count 3: bad', 'plain'])
        self.assertEqual(out['defaults'], [5, 'file', False, False])
        self.assertIsNone(out['sizes'][0])
        self.assertRegex(out['sizes'][1], r'^b\.mov was not added: .*600 MiB, over the 512 MiB limit')
        self.assertRegex(out['sizes'][2], 'empty')
        self.assertIsNone(out['sizes'][3])
        self.assertEqual(out['frames'], [2880, 96, 2880, 2880, 14400])
        self.assertEqual(out['types'], ['video/quicktime', 'video/quicktime', 'video/mp4', 'video/quicktime',
                                        'video/mp4'])
        self.assertEqual(out['suffixes'], ['mov', 'mov', 'mp4'])
        self.assertEqual((out['cap'], out['fps'], out['frames120']), (512 * MIB, 24, 2880))

    def test_span_verdict_agrees_with_the_compiler_guard(self):
        """The ready/not-ready verdict must match what compilePlan accepts, and name a piece length that compiles."""
        script = r'''
const S = require(process.argv[1]);
const path = require('path');
const C = require(path.join(path.dirname(process.argv[1]), 'browser.compiler.js'));
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const {bundle} = JSON.parse(input);
  const compiles = (frames, loopFrames) => {
    const ids = loopFrames.map((_, index) => `loop-${index + 1}`);
    const sources = loopFrames.map((count, index) => {
      const sha = String(index + 1).padStart(64, '0');
      return {id: `source-${index + 1}`, path: `media/${sha}.mp4`, sha256: sha, kind: 'video',
              duration: S.quantizeDuration(count / S.FPS, S.FPS).duration};
    });
    try {
      C.compilePlan(C.buildState({sources, frames, fps: S.FPS,
        loops: sources.map((source, index) => ({id: ids[index], source: source.id})),
        layouts: C.bindLayouts(bundle[String(loopFrames.length)], ids)}));
      return true;
    } catch (error) {
      if (/span resource guard/.test(error.message)) return false;
      throw error;
    }
  };
  const cases = [];
  for (const count of [2, 3, 4]) for (const seconds of [120, 256, 257, 600]) for (const each of [6, 12, 15, 1440]) {
    const loops = Array(count).fill(each), frames = Math.min(seconds * S.FPS, 14400), verdict = S.spanVerdict(frames, loops);
    const named = verdict.ok ? null : Number((/\?seconds=(\d+)/.exec(verdict.message) || [])[1]);
    cases.push({count, seconds, each, ok: verdict.ok, compiles: compiles(frames, loops), named,
      namedFits: named === null ? null : compiles(named * S.FPS, loops),
      nextFails: named === null ? null : !compiles((named + 1) * S.FPS, loops)});
  }
  const pair = S.spanVerdict(14400, [12, 12]);
  process.stdout.write(JSON.stringify({cases, pair, short: S.spanVerdict(2880, [6, 6]), constant: S.MAX_SPANS_PER_TRACK}));
});
'''
        out = node(script, {'bundle': authored_layout_bundle()})
        for case in out['cases']:
            with self.subTest(**{key: case[key] for key in ('count', 'seconds', 'each')}):
                self.assertEqual(case['ok'], case['compiles'], case)
                if not case['ok']:
                    self.assertTrue(case['namedFits'], case)
                    self.assertTrue(case['nextFails'], case)
        self.assertTrue(any(not case['ok'] for case in out['cases']))
        self.assertFalse(out['pair']['ok'])
        self.assertIn('?seconds=512', out['pair']['message'])
        self.assertTrue(out['short']['ok'])
        self.assertEqual(out['constant'], 1024)

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
    """The staged studio, served under a subpath: it plays on load and the visitor's files are optional."""

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
        # The application root owns navigation; exercise the Studio itself here.
        cls.url = f'{cls.origin}/{SUBPATH}/watch.html'
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

    def open(self, query='', width=1280, height=720, reduced_motion='no-preference', init_script=None):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, reduced_motion=reduced_motion)
        self.addCleanup(context.close)
        page = context.new_page()
        page.requests, page.errors = [], []
        page.on('request', lambda request: page.requests.append(request.url))
        page.on('pageerror', lambda error: page.errors.append(str(error)))
        if init_script is not None:
            page.add_init_script(init_script)
        page.goto(self.url + query)
        page.wait_for_function('() => window.SimvltaneaStudio && window.SimvltaneaStudio.snapshot && '
                               'window.compositionRuntime && SimvltaneaStudio.snapshot().seed !== null')
        self.addCleanup(lambda: self.assertEqual(page.errors, []))
        return page

    def snapshot(self, page):
        return page.evaluate('SimvltaneaStudio.snapshot()')

    def settled(self, page):
        """Wait for the current intent's accepted residents and export metadata."""
        return page.evaluate('''async () => {
          let timer;
          try {
            await Promise.race([compositionIO.plan(), new Promise((_, reject) => {
              timer=setTimeout(() => reject(new Error('Studio settlement timed out')),45000);
            })]);
            return SimvltaneaStudio.snapshot();
          } finally { clearTimeout(timer); }
        }''')

    def playing(self, page, count=None, timeout=45000):
        """Wait until the runtime plays every panel with decoded frames, then return its snapshot."""
        page.wait_for_function(
            '''count => { const r = compositionRuntime;
              return r.error || (r.running && r.snapshot().compositionTime > 0.3 &&
                (count === null || r.nodes.size === count) &&
                [...r.nodes.values()].every(n => !n.busy && n.media && n.media.readyState >= 2)); }''',
            arg=count, timeout=timeout)
        self.assertIsNone(page.evaluate('compositionRuntime.error'))
        return page.evaluate('''() => { const r = compositionRuntime, s = r.snapshot();
          s.sha = r.plan.sources.map(x => x.sha256); s.version = r.plan.plan_version;
          s.muted = [...document.querySelectorAll('#stage video[data-deck=active]')].map(v => v.muted);
          s.inline = [...document.querySelectorAll('#stage video[data-deck=active]')].map(v => v.playsInline);
          return s; }''')

    def advancing(self, page):
        before = page.evaluate('compositionRuntime.snapshot().compositionTime')
        page.wait_for_function('t => compositionRuntime.running && compositionRuntime.snapshot().compositionTime > t + 0.3',
                               arg=before, timeout=15000)

    def unlock(self, page):
        """A real click on the stage: the first gesture turns the sound on (and rerolls nothing)."""
        before = self.snapshot(page)['selection']
        box = page.locator('#frame').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.wait_for_function('''() => { const r = compositionRuntime;
          return r.error || (r.running && r.plan.plan_version === 2 && r.audio.enabled &&
            r.audio.context && r.audio.context.state === 'running'); }''', timeout=30000)
        self.assertEqual(self.snapshot(page)['selection'], before)

    def tap(self, page, selector):
        """Move the pointer first, as a person does: the idle control bar returns, then the click lands."""
        page.mouse.move(5, 5)
        page.mouse.move(9, 9)
        page.wait_for_function("() => !document.querySelector('#studio').classList.contains('idle')")
        page.click(selector)

    def add(self, page, paths):
        page.set_input_files('#files', [str(path) for path in paths])
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy', timeout=60000)
        return self.snapshot(page)

    def allowed(self, page):
        """Requests beyond the staged files and the optional library manifest probe (blob: and data: URLs
        are made on the device)."""
        staged = {f'{self.origin}/{SUBPATH}/{name}' for name in ('', *STUDIO_FILES, 'library/manifest.json')}
        return [url for url in page.requests if not (url.split('?')[0] in staged or url.startswith(('blob:', 'data:')))]

    def observe_ecology(self, page):
        """Observe real scheduler decisions without changing its clock or policy."""
        page.evaluate('''() => {
          window.automaticRequests=[];
          const step=SimvltaneaEcosystem.Engine.prototype.step;
          SimvltaneaEcosystem.Engine.prototype.step=function(time,dt,residents,options) {
            const out=step.call(this,time,dt,residents,options);
            window.ecologyOptions={enabled:options.enabled,canReplace:options.canReplace,canRest:options.canRest};
            for(const request of out.requests) automaticRequests.push({time,...request});
            return out;
          };
        }''')

    # ---- tests -------------------------------------------------------------

    def test_plays_at_once_without_any_interaction(self):
        page = self.open()
        # The preview canvases move before the recordings are ready.
        drawn = page.evaluate('''async () => {
          const canvas = document.querySelector('#preview canvas');
          if (!canvas) return null;
          const pixels = () => Array.from(canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data).join(',');
          const first = pixels(); await new Promise(r => setTimeout(r, 400)); return first !== pixels(); }''')
        self.assertTrue(drawn)
        snapshot = self.snapshot(page)
        self.assertEqual(snapshot['source'], 'builtin')
        self.assertEqual(snapshot['sound'], 'locked')
        self.assertIn(snapshot['family'], ('strips', 'authored'))
        self.assertIn(snapshot['panels'], snapshot['counts'])
        self.assertEqual(len(set(snapshot['selection'])), snapshot['panels'])
        state = self.playing(page, snapshot['panels'])
        self.assertEqual(state['version'], 1)  # silent until a gesture
        self.assertEqual(state['muted'], [True] * snapshot['panels'])
        self.assertEqual(state['inline'], [True] * snapshot['panels'])
        self.assertEqual(len(set(state['sha'])), snapshot['panels'])
        self.assertEqual(self.snapshot(page)['builtinsReady'], 12)
        self.advancing(page)
        self.assertRegex(page.evaluate('location.search'), r'^\?seed=\d+&rv=2$')
        self.assertEqual(self.allowed(page), [])
        self.assertEqual(page.evaluate("[...document.querySelectorAll('p')].filter(p => p.offsetParent).length"), 0)

    def test_seed_reproduces_a_roll_and_shuffle_rerolls(self):
        families = {'authored': list(range(2, 8)), 'strips': list(range(1, 13))}
        expected = node(r"""const s = require(process.argv[1]); let input = '';
          process.stdin.on('data', d => input += d).on('end', () => { const {seed, families} = JSON.parse(input);
          process.stdout.write(JSON.stringify(s.rollComposition(seed, families, 12))); });""",
                        dict(seed=424242, families=families))
        names = [item['name'] for item in node(r"""const s = require(process.argv[1]);
          process.stdout.write(JSON.stringify(s.BUILTINS));""", None)]
        first = self.open('?seed=424242')
        second = self.open('?seed=424242', width=390, height=844)
        for page in (first, second):
            snapshot = self.snapshot(page)
            self.assertEqual((snapshot['seed'], snapshot['family'], snapshot['style']),
                             (424242, expected['family'], expected['style']))
            self.assertEqual(snapshot['selection'], [names[index] for index in expected['loops']])
        state = self.playing(first, expected['panels'])
        self.assertEqual(len(state['loops']), expected['panels'])
        layouts = first.evaluate('compositionRuntime.plan.layout_keyframes[0].layouts')
        self.assertEqual(len(layouts['portrait']['cells']), expected['panels'])
        if expected['family'] == 'strips':
            self.assertTrue(first.evaluate('compositionRuntime.plan.slice.enabled'))
        rolls = set()
        for _ in range(4):
            before = self.snapshot(first)
            self.tap(first, '#shuffle')
            first.wait_for_function('s => SimvltaneaStudio.snapshot().seed !== s', arg=before['seed'])
            after = self.settled(first)
            self.assertRegex(first.evaluate('location.search'), rf'^\?seed={after["seed"]}&rv=2(?:&mix=[sa][\d.]+)?$')
            rolls.add((after['family'], tuple(after['selection'])))
            self.assertEqual(len(set(after['selection'])), after['panels'])
        self.assertGreater(len(rolls), 1)
        last = self.snapshot(first)
        self.playing(first, last['panels'])
        # Resident clips keep their slots; the settled URL records any normalized mix.
        again = self.open(first.evaluate('location.search'))
        self.assertEqual(self.settled(again)['selection'], last['selection'])
        self.assertEqual(self.allowed(first), [])

    def test_unlock_during_recording_produces_audio_after_transition(self):
        page = self.open('?gen=1&seed=314159', init_script="""(() => {
          const connect = AudioNode.prototype.connect;
          window.studioOutputMeters = new Map();
          AudioNode.prototype.connect = function (target, ...ports) {
            const result = connect.call(this, target, ...ports);
            // Observe the final output node after the sample guard.
            if (target === this.context.destination) {
              const meter = this.context.createAnalyser();
              connect.call(this, meter);
              studioOutputMeters.set(this.context, meter);
            }
            return result;
          };
        })();""")
        self.assertEqual(self.snapshot(page)['record'], 'recording')
        self.tap(page, '#speaker')
        self.assertEqual(self.snapshot(page)['sound'], 'on')
        self.playing(page)
        snapshot = self.snapshot(page)
        self.assertEqual((snapshot['source'], snapshot['record'], snapshot['builtinsReady'], snapshot['phase']),
                         ('builtin', 'recorded', 12, 'playing'))
        self.assertTrue(page.evaluate('studioOutputMeters.has(compositionRuntime.audio.context)'))
        page.wait_for_function("""() => {
          const meter = studioOutputMeters.get(compositionRuntime.audio.context);
          const samples = new Float32Array(meter.fftSize);
          meter.getFloatTimeDomainData(samples);
          return samples.some(sample => Math.abs(sample) > 0.001);
        }""", timeout=10000)

    def test_canvas_fallback_uses_one_protected_audio_context(self):
        page = self.open('?gen=1&seed=314159', init_script='''(() => {
          window.MediaRecorder = undefined;
          const NativeAudio = AudioContext, connect = AudioNode.prototype.connect;
          window.contextCount = 0;
          window.AudioContext = class extends NativeAudio {
            constructor(...args) { super(...args); contextCount++; }
          };
          AudioNode.prototype.connect = function(target, ...ports) {
            const result = connect.call(this, target, ...ports);
            if (target === this.context.destination) {
              window.fallbackMeter = this.context.createAnalyser();
              window.fallbackOutputType = this.constructor.name;
              connect.call(this, fallbackMeter);
            }
            return result;
          };
        })();''')
        self.assertEqual(self.snapshot(page)['record'], 'canvas')
        self.assertTrue(page.is_disabled('#effects'))
        self.assertEqual(page.get_attribute('#effects', 'aria-pressed'), 'false')
        self.assertFalse(self.snapshot(page)['filters'])
        self.tap(page, '#speaker')
        page.wait_for_function('''() => {
          if (!window.fallbackMeter) return false;
          const samples = new Float32Array(fallbackMeter.fftSize);
          fallbackMeter.getFloatTimeDomainData(samples);
          return samples.some(value => Math.abs(value) > .001);
        }''')
        self.assertEqual(page.evaluate('contextCount'), 1)
        self.assertEqual(page.evaluate('fallbackOutputType'), 'WaveShaperNode')

    def test_first_gesture_turns_sound_on_and_m_mutes(self):
        page = self.open('?seed=7')
        self.assertEqual(page.get_attribute('#speaker', 'aria-label'), 'Tap for sound')
        self.playing(page)
        self.unlock(page)
        page.wait_for_function('() => [...compositionRuntime.nodes.values()].some(n => n.audio && n.audio.gain.gain.value > 0)')
        state = page.evaluate('''() => { const r = compositionRuntime;
          return {mode: r.audio.mode, gains: [...r.nodes.values()].map(n => n.audio ? n.audio.gain.gain.value : 0),
                  muted: [...document.querySelectorAll('#stage video[data-deck=active]')].map(v => v.muted),
                  audio: r.plan.sources.map(s => s.audio_stream)}; }''')
        self.assertEqual(state['mode'], 'spatial_loops')
        self.assertTrue(any(gain > 0 for gain in state['gains']), state)
        self.assertEqual(set(state['muted']), {False})
        self.assertEqual(set(map(json.dumps, state['audio'])), {'null'})  # built-in sound is generated live
        self.assertEqual(self.snapshot(page)['sound'], 'on')
        self.assertEqual(page.get_attribute('#speaker', 'aria-label'), 'Mute')
        page.keyboard.press('m')
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().sound === 'off' &&
          [...document.querySelectorAll('#stage video[data-deck=active]')].every(v => v.muted)''')
        self.assertEqual(page.get_attribute('#speaker', 'aria-label'), 'Unmute')
        page.keyboard.press('m')
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().sound === 'on' &&
          [...document.querySelectorAll('#stage video[data-deck=active]')].every(v => !v.muted)''')
        text = page.evaluate('document.documentElement.textContent') + INDEX_HTML
        self.assertNotRegex(text.lower(), r'sound is never played|always muted|never plays sound')

    def test_tapping_a_panel_rerolls_only_that_panel(self):
        page = self.open('?seed=31')
        snapshot = self.snapshot(page)
        self.playing(page, snapshot['panels'])
        self.unlock(page)
        before = self.snapshot(page)['selection']
        box = page.locator('#stage .loop[data-loop-id="loop-1"]').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.wait_for_function('b => SimvltaneaStudio.snapshot().selection.join() !== b.join()', arg=before)
        after = self.settled(page)['selection']
        self.assertEqual(len(after), len(before))
        if len(before) < 12:
            self.assertNotEqual(after[0], before[0])
            self.assertEqual(after[1:], before[1:])
        self.assertRegex(page.evaluate('location.search'), r'^\?seed=31&mix=[sa]\d')
        self.playing(page, len(after))

    def test_panel_count_family_and_keys(self):
        page = self.open('?seed=5')
        snapshot = self.snapshot(page)
        page.locator('body').press('ArrowRight' if snapshot['panels'] < 7 else 'ArrowLeft')
        page.wait_for_function('n => SimvltaneaStudio.snapshot().panels !== n', arg=snapshot['panels'])
        changed = self.snapshot(page)
        self.assertEqual(abs(changed['panels'] - snapshot['panels']), 1)
        self.assertEqual(page.inner_text('#panel-count'), str(changed['panels']))
        # The family toggle keeps the count where the family offers it, else the nearest, with a toast.
        if self.snapshot(page)['family'] == 'authored':
            self.tap(page, '#families button[data-family="strips"]')
            page.wait_for_function("() => SimvltaneaStudio.snapshot().family === 'strips'")
        # Authored mosaics now exist for 8 to 12, so the count carries across the family toggle.
        while self.snapshot(page)['panels'] < 8:
            self.tap(page, '#more')
        self.tap(page, '#families button[data-family="authored"]')
        page.wait_for_function("() => SimvltaneaStudio.snapshot().family === 'authored'")
        self.assertEqual(self.snapshot(page)['panels'], 8)
        while self.snapshot(page)['panels'] < 12:
            self.tap(page, '#more')
        self.assertTrue(page.is_disabled('#more'))
        while self.snapshot(page)['panels'] > 8:
            self.tap(page, '#fewer')
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().toastShown', timeout=10000)
        seed = self.snapshot(page)['seed']
        page.locator('body').press('r')
        page.wait_for_function('s => SimvltaneaStudio.snapshot().seed !== s', arg=seed)
        self.settled(page)
        # Manual population survives shuffle and is retained in the reproducible URL.
        self.assertRegex(page.evaluate('location.search'), r'^\?seed=\d+&rv=2&mix=[sa][\d.]+$')
        self.assertEqual(self.snapshot(page)['panels'], 8)
        self.playing(page)
        self.assertEqual(self.allowed(page), [])

    def test_recording_completion_preserves_pending_keyboard_edits_and_share_link(self):
        # Delay only delivery of real MediaRecorder stop events. The controls,
        # compiler, recorded bytes, and playback all use the real implementation.
        page = self.open('?seed=5', init_script=BUILTIN_RECORDING_GATE)
        page.wait_for_function('() => heldBuiltinRecordings.size === 12')
        initial = self.snapshot(page)
        page.locator('body').press('ArrowRight' if initial['panels'] < 7 else 'ArrowLeft')
        if self.snapshot(page)['family'] == 'authored':
            self.tap(page, '#families button[data-family="strips"]')
        while self.snapshot(page)['panels'] < 8:
            self.tap(page, '#more')
        self.tap(page, '#families button[data-family="authored"]')
        self.assertEqual(self.snapshot(page)['panels'], 8)
        page.locator('body').press('r')
        requested = self.snapshot(page)
        self.assertNotEqual(requested['seed'], initial['seed'])
        self.assertEqual(requested['builtinsReady'], 0)
        page.evaluate('releaseBuiltinRecordings()')
        accepted = self.settled(page)
        self.assertEqual(accepted['seed'], requested['seed'])
        self.assertEqual(accepted['family'], requested['family'])
        self.assertEqual(accepted['selection'], requested['selection'])
        self.assertEqual(accepted['panels'], 8)
        self.assertRegex(page.evaluate('location.search'), rf'^\?seed={requested["seed"]}&rv=2&mix=[sa][\d.]+$')
        self.playing(page, 8)

    def test_pending_builtin_edit_keeps_new_intent_and_export_waiter(self):
        page = self.open('?seed=5&mix=s0.1&evolve=0', init_script=BUILTIN_RECORDING_GATE)
        page.wait_for_function('() => heldBuiltinRecordings.size === 12')
        page.evaluate('releaseBuiltinRecordings([0, 1])')
        page.wait_for_function('() => SimvltaneaStudio.snapshot().builtinsReady === 2')
        self.tap(page, '#families button[data-family="authored"]')
        self.settled(page)
        self.playing(page, 2)
        self.tap(page, '#more')
        pending = page.evaluate('''async () => {
          window.pendingRecordingExport = null;
          compositionIO.plan().then(plan => { window.pendingRecordingExport = plan; });
          await Promise.resolve();
          return {snapshot:SimvltaneaStudio.snapshot(), exported:pendingRecordingExport !== null};
        }''')
        page.evaluate('releaseBuiltinRecordings()')
        accepted = self.settled(page)
        self.assertEqual(pending['snapshot']['panels'], 3, 'recording must not discard the requested third panel')
        self.assertFalse(pending['exported'], 'export must wait for the pending user intent')
        self.assertEqual(accepted['panels'], 3)
        self.playing(page, 3)
        page.wait_for_function('() => pendingRecordingExport !== null')
        self.assertEqual(page.evaluate('pendingRecordingExport.tracks.length'), 3)

    def test_recording_completion_preserves_initial_explicit_mix(self):
        page = self.open('?seed=5&mix=s0.1', init_script=BUILTIN_RECORDING_GATE)
        page.wait_for_function('() => heldBuiltinRecordings.size === 12')
        page.evaluate('releaseBuiltinRecordings()')
        accepted = self.settled(page)
        self.assertEqual(accepted['selection'], ['drift', 'bands'])
        self.assertEqual(accepted['family'], 'strips')
        self.assertEqual(page.evaluate('location.search'), '?seed=5&mix=s0.1')
        self.playing(page, 2)

    def test_recording_completion_preserves_family_only_share_intent(self):
        page = self.open('?seed=5', init_script=BUILTIN_RECORDING_GATE)
        page.wait_for_function('() => heldBuiltinRecordings.size === 12')
        before = self.snapshot(page)['panels']
        self.tap(page, '#families button[data-family="authored"]')
        requested = self.snapshot(page)
        page.evaluate('releaseBuiltinRecordings()')
        accepted = self.settled(page)
        self.assertEqual(accepted['selection'], requested['selection'])
        self.assertEqual(accepted['family'], 'authored')
        self.assertEqual(accepted['panels'], before)  # every count the strips family offered has an authored pair
        self.assertRegex(page.evaluate('location.search'), r'^\?seed=5&mix=a[\d.]+$')
        self.playing(page, before)

    def test_picker_replaces_the_loops_with_the_visitors_own(self):
        page = self.open('?seconds=30')
        self.assertEqual(page.get_attribute('#files', 'accept'), 'video/*,.mov,.mp4,.m4v,.webm,.json,application/json')
        snapshot = self.add(page, self.loops[:3])
        self.assertEqual((snapshot['source'], snapshot['panels'], snapshot['refusals']), ('own', 3, []))
        self.assertEqual(snapshot['toast'], '3 loops added. Nothing was uploaded.')
        state = self.playing(page, 3)
        self.assertEqual(sorted(state['sha']), sorted(loop['sha256'] for loop in snapshot['loops']))
        self.assertEqual(page.evaluate('[compositionRuntime.plan.frames, compositionRuntime.plan.fps]'), [720, 24])
        self.assertEqual([loop['audio'] for loop in snapshot['loops']], [{'codec': 'aac', 'channels': 1}] * 3)
        self.unlock(page)
        self.assertEqual(page.evaluate('compositionRuntime.plan.sources.map(s => s.audio_stream.codec)'), ['aac'] * 3)
        self.assertEqual(self.allowed(page), [])

    def test_personal_spares_evolve_locally_with_hold_and_stable_siblings(self):
        page = self.open('?seed=99&evolve=0')
        methods = []
        page.on('request', lambda request: methods.append(request.method))
        admitted = self.add(page, self.loops[:3])
        self.playing(page, 3)
        self.tap(page, '#fewer')
        self.playing(page, 2)
        page.wait_for_function('() => compositionRuntime.audio.context?.state===\'running\' && '
                               '[...compositionRuntime.nodes.values()].every(n=>n.audio)')
        self.observe_ecology(page)
        page.evaluate('''() => {
          window.localBefore=[...compositionRuntime.nodes.values()].map(n=>({id:n.id,media:n.media,
            binding:n.audio,sha:n.item.sha256,frames:n.callbacks,calls:[]}));
          for(const entry of localBefore) for(const name of ['play','pause','load']) {
            const original=entry.media[name].bind(entry.media);
            entry.media[name]=(...args)=>{entry.calls.push(name);return original(...args)};
          }
          window.localContext=compositionRuntime.audio.context;
        }''')
        self.tap(page, '#activity')
        page.wait_for_function('() => window.ecologyOptions?.enabled===true', timeout=1500)
        page.wait_for_function('''() => !compositionRuntime.draining &&
          [...compositionRuntime.nodes.values()].some((n,i)=>n.item.sha256!==localBefore[i].sha)''', timeout=40000)
        self.tap(page, '#activity')
        page.wait_for_function('() => !compositionRuntime.draining')
        after = page.evaluate('''() => {
          const r=compositionRuntime, nodes=[...r.nodes.values()];
          return {changes:nodes.map((n,i)=>n.item.sha256!==localBefore[i].sha),
            stable:nodes.map((n,i)=>n.item.sha256===localBefore[i].sha ?
              n.media===localBefore[i].media && n.audio===localBefore[i].binding && localBefore[i].calls.length===0 : true),
            old:localBefore.map(n=>n.sha),current:nodes.map(n=>n.item.sha256),
            context:r.audio.context===localContext,budget:r.snapshot().maxConcurrentStandbys,
            forward:nodes.every(n=>n.media.loop && n.media.playbackRate===1 && !n.item.clip && n.media.src.startsWith('blob:'))};
        }''')
        self.assertEqual(sum(after['changes']), 1)
        self.assertTrue(all(after['stable']))
        self.assertTrue(after['context'])
        self.assertTrue(after['forward'])
        self.assertEqual(after['budget'], 1)
        self.assertTrue(set(after['current']).issubset({item['sha256'] for item in admitted['loops']}))
        self.assertEqual(self.snapshot(page)['panels'], 2)
        self.assertTrue(page.is_hidden('#loop-mode'))
        page.wait_for_function('() => window.ecologyOptions?.enabled===false && ecologyOptions.canReplace===false', timeout=1500)
        # The sole spare has just departed, so its SHA is still cooling down.
        held_at = page.evaluate('compositionRuntime.clock.simTime')
        page.wait_for_function('at=>compositionRuntime.clock.simTime>at+2', arg=held_at)
        self.assertFalse(page.evaluate('ecologyOptions.canReplace'))
        held = after['current']
        frames = page.evaluate('[...compositionRuntime.nodes.values()].map(n=>n.callbacks)')
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().ecosystem.residents.every(
          resident=>resident.age>resident.deadlineAge+.2)''', timeout=35000)
        self.assertEqual(page.evaluate('[...compositionRuntime.nodes.values()].map(n=>n.item.sha256)'), held)
        self.assertTrue(page.evaluate('before=>[...compositionRuntime.nodes.values()].every((n,i)=>n.callbacks>before[i])', frames))
        self.tap(page, '#activity')
        page.wait_for_function('''before => !compositionRuntime.draining &&
          [...compositionRuntime.nodes.values()].some((n,i)=>n.item.sha256!==before[i])''', arg=held, timeout=10000)
        departed = next(sha for sha in after['old'] if sha not in held)
        self.assertIn(departed, page.evaluate('[...compositionRuntime.nodes.values()].map(n=>n.item.sha256)'))
        self.assertEqual(self.allowed(page), [])
        self.assertTrue(all(method == 'GET' for method in methods))
        self.assertNotIn('mix=', page.evaluate('location.search'))
        for path in self.loops[:3]:
            self.assertNotIn(path.name, page.evaluate('location.href'))

    def test_personal_pool_without_spares_extends_full_loops_in_place(self):
        page = self.open('?seed=99&mix=s0.1')
        self.add(page, self.loops[:2])
        self.playing(page, 2)
        self.observe_ecology(page)
        page.wait_for_function('() => window.ecologyOptions?.enabled===true', timeout=1500)
        before = self.snapshot(page)['ecosystem']['residents']
        page.evaluate('window.localResidents=[...compositionRuntime.nodes.values()].map(n=>({media:n.media,sha:n.item.sha256,frames:n.callbacks}))')
        page.wait_for_function('''before=>SimvltaneaStudio.snapshot().ecosystem.residents.some(
          (resident,i)=>resident.deadlineAge>before[i].deadlineAge)''', arg=before, timeout=35000)
        after = self.snapshot(page)['ecosystem']['residents']
        extended = [(now, old) for now, old in zip(after, before) if now['deadlineAge'] > old['deadlineAge']]
        self.assertTrue(extended)
        for now, old in extended:
            multiple = (now['deadlineAge'] - old['deadlineAge']) / now['duration']
            self.assertAlmostEqual(multiple, round(multiple))
        state = page.evaluate('''() => ({same:[...compositionRuntime.nodes.values()].every((n,i)=>
          n.media===localResidents[i].media && n.item.sha256===localResidents[i].sha &&
          n.callbacks>localResidents[i].frames && !n.resting && !n.media.paused),
          requests:automaticRequests,eligible:ecologyOptions.canReplace})''')
        self.assertTrue(state['same'])
        self.assertFalse(state['eligible'])
        self.assertEqual(state['requests'], [])
        self.assertEqual(self.allowed(page), [])

    def test_personal_admission_blocks_automatic_selection_of_partial_pool(self):
        page = self.open('?seed=99&mix=s0.1&evolve=0')
        self.add(page, self.loops[:2])
        self.playing(page, 2)
        self.observe_ecology(page)
        page.evaluate('''() => {
          const read=File.prototype.arrayBuffer;
          File.prototype.arrayBuffer=function() {
            if(this.name==='pending-fourth.mp4')return new Promise(resolve=>{
              window.releaseLocalAdmission=()=>resolve(read.call(this));
            });
            return read.call(this);
          };
          window.admissionBefore=[...compositionRuntime.nodes.values()].map(n=>n.media);
        }''')
        page.set_input_files('#files', [dict(name=self.loops[2].name,mimeType='video/mp4',buffer=self.loops[2].read_bytes()),
                                      dict(name='pending-fourth.mp4',mimeType='video/mp4',buffer=self.loops[3].read_bytes())])
        page.wait_for_function('() => SimvltaneaStudio.snapshot().busy && SimvltaneaStudio.snapshot().loops.length===3 && Boolean(window.releaseLocalAdmission)')
        self.tap(page, '#activity')
        page.wait_for_function('() => window.ecologyOptions?.enabled===true', timeout=1500)
        self.assertEqual(page.evaluate('ecologyOptions'), dict(enabled=True,canReplace=False,canRest=False))
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().ecosystem.residents.some(
          resident=>resident.age>resident.presenceDeadlineAge+.2)''', timeout=35000)
        self.assertEqual(page.evaluate('automaticRequests'), [])
        self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===admissionBefore[i])'))
        page.evaluate('releaseLocalAdmission()')
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy')
        self.playing(page, 4)
        self.assertEqual(len(self.snapshot(page)['loops']), 4)
        self.assertEqual(self.allowed(page), [])

    def test_drop_anywhere_replaces_the_loops(self):
        page = self.open()
        files = [dict(name=path.name, data=base64.b64encode(path.read_bytes()).decode()) for path in self.loops[3:5]]
        states = page.evaluate('''files => {
          const transfer = new DataTransfer();
          for (const f of files) transfer.items.add(new File([Uint8Array.from(atob(f.data), c => c.charCodeAt(0))],
            f.name, {type: 'video/mp4'}));
          const seen = [], studio = document.querySelector('#studio');
          for (const type of ['dragenter', 'dragover', 'drop']) {
            const event = new DragEvent(type, {dataTransfer: transfer, bubbles: true, cancelable: true});
            document.querySelector('#stage').dispatchEvent(event);
            seen.push([type, event.defaultPrevented, studio.classList.contains('dragging')]);
          }
          return seen; }''', files)
        self.assertEqual(states, [['dragenter', True, True], ['dragover', True, True], ['drop', True, False]])
        page.wait_for_function("() => SimvltaneaStudio.snapshot().source === 'own' && !SimvltaneaStudio.snapshot().busy")
        self.assertEqual(self.snapshot(page)['panels'], 2)
        self.playing(page, 2)

    def test_refusals_show_one_toast_and_keep_their_messages(self):
        page = self.open()
        snapshot = self.add(page, [self.fixtures['huge.mov'], self.fixtures['prores.mov'],
                                   self.fixtures['garbage.mp4'], self.loops[0]])
        refusals = [
            'huge.mov was not added: the chosen videos would total 513 MiB, over the 512 MiB limit for this page '
            '(the browser holds about twice that in memory).',
            'This browser cannot play prores.mov (video/quicktime, ProRes 422 apcn).',
            'This browser cannot play garbage.mp4 (video/mp4).']
        self.assertEqual(snapshot['refusals'], refusals)
        self.assertEqual([loop['name'] for loop in snapshot['loops']], ['loop-1.mp4'])
        self.assertEqual(page.inner_text('#toast'), refusals[0] + ' (+2 more not added)')
        self.assertEqual(page.locator('#toast').get_attribute('role'), 'status')
        duplicate = self.fixtures['loop-1.mp4'].parent / 'loop-1-copy.mp4'
        shutil.copyfile(self.fixtures['loop-1.mp4'], duplicate)
        self.addCleanup(duplicate.unlink)
        snapshot = self.add(page, [duplicate])
        self.assertEqual(snapshot['refusals'], ['loop-1-copy.mp4 was not added: it is the same video as loop-1.mp4. '
                                                'Each loop needs its own video; nothing is duplicated.'])
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().toastShown', timeout=10000)
        self.assertEqual(snapshot['source'], 'own')
        self.playing(page, 1)

    def test_overlapping_batches_share_one_size_cap(self):
        page = self.open()
        files = [dict(name=path.name, data=base64.b64encode(path.read_bytes()).decode()) for path in self.loops[:2]]
        page.evaluate('''files => {
          for (const spec of files) {
            const file = new File([Uint8Array.from(atob(spec.data), c => c.charCodeAt(0))], spec.name, {type: 'video/mp4'});
            Object.defineProperty(file, 'size', {value: 300 * 1048576});
            const drop = new Event('drop', {bubbles: true, cancelable: true});
            Object.defineProperty(drop, 'dataTransfer', {value: {files: [file]}});
            document.dispatchEvent(drop);
          }
        }''', files)
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy && SimvltaneaStudio.snapshot().refusals.length',
                               timeout=60000)
        snapshot = self.snapshot(page)
        self.assertEqual([loop['name'] for loop in snapshot['loops']], ['loop-1.mp4'])
        self.assertRegex(snapshot['refusals'][0], r'^loop-2\.mp4 was not added: .*600 MiB, over the 512 MiB limit')

    def test_phone_like_clips_keep_their_facts(self):
        names = ['phone-h264.mov', 'phone-rotated.mov', 'phone-vfr.mov', 'phone-hevc.mov']
        facts = {name: probe(self.fixtures[name]) for name in names}
        self.assertEqual([item.get('rotation') for item in video_stream(facts['phone-rotated.mov'])['side_data_list']],
                         [-90])
        page = self.open('?seconds=30', width=844, height=390)
        snapshot = self.add(page, [self.fixtures[name] for name in names])
        [hevc] = node(SNIFF, [str(self.fixtures['phone-hevc.mov'])])
        hevc_playable = page.evaluate("q => document.createElement('video').canPlayType(q)",
                                      hevc['queries']['queries'][0]) != ''
        accepted = {loop['name']: loop for loop in snapshot['loops']}
        if hevc_playable:
            self.assertEqual(snapshot['refusals'], [])
        else:
            self.assertRegex(snapshot['refusals'][0], r'^This browser cannot play phone-hevc\.mov \(video/quicktime, '
                                                      r'HEVC hvc1\.')
        self.assertEqual((accepted['phone-rotated.mov']['width'], accepted['phone-rotated.mov']['height']), (360, 480))
        for name, loop in accepted.items():
            declared = Fraction(loop['declared'])
            self.assertLessEqual(declared, Fraction(loop['duration']))
            self.assertLessEqual(abs(declared - Fraction(video_stream(facts[name])['duration'])), Fraction(1, FPS), name)
        self.assertEqual(accepted['phone-vfr.mov']['declared'], '5/3')
        self.playing(page, len(accepted))
        self.assertEqual(page.evaluate('compositionRuntime.plan.sources.map(s => s.path.split(".").pop())'),
                         ['mov'] * len(accepted))

    def test_reduced_motion_starts_paused_with_one_play_control(self):
        page = self.open(width=360, height=740, reduced_motion='reduce')
        page.wait_for_function('() => compositionRuntime.ready', timeout=45000)
        self.assertTrue(self.snapshot(page)['held'])
        self.assertTrue(page.is_visible('#start'))
        self.assertFalse(page.evaluate('compositionRuntime.running'))
        self.assertTrue(page.is_disabled('#effects'))
        self.assertEqual(page.get_attribute('#effects', 'aria-pressed'), 'false')
        self.assertFalse(self.snapshot(page)['filters'])
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()]
          .every(n => n.media.style.filter === '')'''))
        page.click('#start')
        page.wait_for_function('() => compositionRuntime.running && compositionRuntime.plan.plan_version === 2',
                               timeout=30000)
        self.assertFalse(page.is_visible('#start'))
        self.assertEqual(self.snapshot(page)['sound'], 'on')

    def test_chrome_is_small_labelled_and_fits_phones_to_wide_screens(self):
        for width, height in ((360, 740), (390, 844), (1440, 900)):
            with self.subTest(width=width):
                page = self.open(width=width, height=height)
                geometry = page.evaluate('''() => {
                  const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect();
                    return [r.left, r.top, r.right, r.bottom]; };
                  const visible = [...document.querySelectorAll('#bar button, #corner button')].filter(b => b.offsetParent);
                  return {stage: rect('#stage'), bar: rect('#bar'), corner: rect('#corner'),
                    scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                    labels: visible.map(b => b.getAttribute('aria-label')),
                    sizes: visible.map(b => [b.offsetWidth, b.offsetHeight]),
                    font: getComputedStyle(document.body).fontFamily}; }''')
                self.assertEqual(geometry['stage'], [0, 0, width, height])
                self.assertGreaterEqual(geometry['bar'][0], 0)
                self.assertLessEqual(geometry['bar'][2], width)
                self.assertLessEqual(geometry['bar'][3], height)
                self.assertLessEqual(geometry['corner'][2], width)
                self.assertLessEqual(geometry['scroll'], [width, height])
                self.assertTrue(all(geometry['labels']), geometry['labels'])
                self.assertTrue(all(w >= 40 and h >= 40 for w, h in geometry['sizes']), geometry['sizes'])
                self.assertTrue(geometry['font'].startswith('system-ui'))
                for name in ('Shuffle', 'Fewer panels', 'More panels', 'Tap for sound', 'Add your own videos',
                             'About this page'):
                    self.assertEqual(page.get_by_role('button', name=name, exact=True).count(), 1, name)
                self.assertEqual(page.get_by_role('slider', name='Volume').count(), 1)
                self.assertEqual(page.get_by_role('toolbar', name='Controls').count(), 1)
        self.tap(page, '#help')
        self.assertTrue(page.is_visible('#about'))
        self.assertIn('Your videos never leave this device. Nothing is uploaded.', page.inner_text('#about'))
        self.assertLessEqual(page.locator('#about p').count(), 3)
        page.keyboard.press('Escape')
        self.assertFalse(page.is_visible('#about'))
        # Without pointer movement the bar fades; movement brings it back.
        page.wait_for_function("() => document.querySelector('#studio').classList.contains('idle')", timeout=10000)
        page.mouse.move(20, 20)
        page.wait_for_function("() => !document.querySelector('#studio').classList.contains('idle')")


ROLL_LIBRARY = r'''
const S = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const {manifest, families, seeds, exclude} = JSON.parse(input);
  const clips = S.libraryClips(manifest);
  process.stdout.write(JSON.stringify(seeds.map(seed => {
    const rolled = S.rollLibrary(seed, families, clips, exclude || []);
    return {...rolled, ids: rolled.loops.map(index => clips[index].id)};
  })));
});
'''


def fake_manifest(count: int = LIBRARY_CLIPS) -> dict:
    """A manifest without media, for the pure selection rules."""
    return {'schema': 'simvltanea.public-demo/1',
            'clips': [library_entry(hashlib.sha256(bytes([number])).hexdigest()[:12], number, 100_000, 2.0)
                      for number in range(count)]}


ROLL_GOLDEN = r'''
const S = require(process.argv[1]);
const crypto = require('crypto');
let input = '';
process.stdin.on('data', chunk => { input += chunk; }).on('end', () => {
  const {authored, manifest, version} = JSON.parse(input);
  const range = (a, b) => Array.from({length: b - a + 1}, (_, i) => a + i);
  const out = [];
  for (const cap of [4, 12]) {
    const families = {authored: authored.filter(count => count <= cap), strips: range(1, 12).filter(count => count <= cap)};
    for (let step = 1; step <= 300; step++) {
      const seed = (step * 2654435761) >>> 0;
      for (const pool of [3, 5, 8, 12]) {
        const rolled = S.rollComposition(seed, families, pool, version);
        out.push(rolled && [rolled.seed, rolled.family, rolled.panels, rolled.loops, rolled.style]);
      }
      for (const size of [5, 9, 30]) {
        const clips = S.libraryClips({...manifest, clips: manifest.clips.slice(0, size)});
        const rolled = S.rollLibrary(seed, families, clips, [], version);
        out.push(rolled && [rolled.seed, rolled.family, rolled.panels, rolled.loops, rolled.style]);
      }
    }
  }
  const counts = {};
  for (const row of out) if (row && row[1] === 'authored') counts[row[2]] = (counts[row[2]] || 0) + 1;
  process.stdout.write(JSON.stringify({rolls: out.length, authoredCounts: counts,
    digest: crypto.createHash('sha256').update(JSON.stringify(out)).digest('hex')}));
});
'''

# Digest of every roll below, produced by the studio at origin/main 930f3d0 (before roll versions) with the
# authored family offering 2..7 (the bundle then). A version 1 roll must reproduce it byte for byte.
ROLL_V1_DIGEST = '129793fa3e40925fb9d750592e8ba0169ad59775673a8e9a8cc3949feaa6f984'


class LibrarySelectionTests(unittest.TestCase):
    """The manifest gate and the tag-weighted rolls, as pure functions under Node."""

    def test_version_one_rolls_are_unchanged_when_the_bundle_offers_more_counts(self):
        manifest = fake_manifest()
        old = node(ROLL_GOLDEN, dict(authored=list(range(2, 8)), manifest=manifest, version=1))
        wide = node(ROLL_GOLDEN, dict(authored=list(range(2, 13)), manifest=manifest, version=1))
        self.assertEqual(old, wide)
        self.assertEqual(wide['digest'], ROLL_V1_DIGEST)
        self.assertEqual(sorted(int(count) for count in wide['authoredCounts']), list(range(2, 8)))

    def test_version_two_rolls_reach_the_authored_counts_above_seven(self):
        manifest = fake_manifest()
        v2 = node(ROLL_GOLDEN, dict(authored=list(range(2, 13)), manifest=manifest, version=2))
        self.assertNotEqual(v2['digest'], ROLL_V1_DIGEST)
        self.assertEqual(sorted(int(count) for count in v2['authoredCounts']), list(range(2, 13)))
        narrow = node(ROLL_GOLDEN, dict(authored=list(range(2, 8)), manifest=manifest, version=2))
        self.assertEqual(narrow['digest'], ROLL_V1_DIGEST)  # nothing above seven offered: same draws

    def test_roll_version_comes_from_the_address(self):
        out = node(r'''const S = require(process.argv[1]);
          process.stdout.write(JSON.stringify(['', '?seed=7', '?seed=7&rv=2', '?rv=2', '?seed=7&rv=1', '?seed=x', '?rv=3&seed=4']
            .map(search => S.parseRollVersion(search)).concat([S.ROLL_VERSION])));''', None)
        self.assertEqual(out, [2, 1, 2, 2, 1, 2, 1, 2])

    def test_succession_is_seeded_and_cools_departed_logical_clips(self):
        result = node(r'''const S = require(process.argv[1]);
          if (!S.createSuccession) { process.stdout.write(JSON.stringify({available:false})); }
          else {
            const a = S.createSuccession(123), b = S.createSuccession(123), c = S.createSuccession(124);
            const first = Array.from({length: 8}, () => a.random());
            a.depart('logical-source', 4);
            process.stdout.write(JSON.stringify({available:true, first,
              again:Array.from({length:8}, () => b.random()), other:Array.from({length:8}, () => c.random()),
              eligibility:[a.eligible('logical-source', 4.9), a.eligible('logical-source', 14), a.eligible('another', 5)]}));
          }''', None)
        self.assertTrue(result['available'])
        self.assertEqual(result['first'], result['again'])
        self.assertNotEqual(result['first'], result['other'])
        self.assertEqual(result['eligibility'], [False, True, True])

    def test_boomerang_variant_preserves_logical_identity_and_checks_assets(self):
        manifest = fake_manifest(1)
        clip = manifest['clips'][0]
        variant = {**clip, 'id': '0123456789ab', 'file': 'clips/0123456789ab.mp4',
                   'fps': 30, 'frame_count': 120, 'duration_seconds': 4.0,
                   'seam_offset_seconds': 2.0, 'has_audio': True,
                   'lufs_integrated': -18.0, 'peak_dbfs': -2.0,
                   'rms_envelope': [0.25] * 40, 'envelope_hz': 10}
        variant.pop('tags')
        clip['variants'] = {'boomerang': variant}
        clip.update(has_audio=True, lufs_integrated=-18.0, peak_dbfs=-2.0,
                    rms_envelope=[0.25] * 20, envelope_hz=10)
        out = node(r'''const S = require(process.argv[1]); let input = '';
          process.stdin.on('data', d => input += d).on('end', () => {
            const m = JSON.parse(input), good = S.libraryClips(m);
            m.clips[0].variants.boomerang.file = '../secret.mp4';
            const badPath = S.libraryClips(m);
            m.clips[0].variants.boomerang.file = 'clips/0123456789ab.mp4';
            m.clips[0].variants.boomerang.rms_envelope[0] = -1;
            process.stdout.write(JSON.stringify({good, badPath, badEnergy:S.libraryClips(m)}));
          });''', manifest)
        self.assertEqual(out['good'][0]['id'], clip['id'])
        self.assertEqual(out['good'][0].get('variants', {}).get('boomerang', {}).get('id'), variant['id'])
        self.assertIsNone(out['badPath'])
        self.assertIsNone(out['badEnergy'])

    def test_manifest_gate_accepts_only_a_well_formed_library(self):
        manifest = fake_manifest(4)
        clip = manifest['clips'][0]
        variants = {
            'valid': manifest,
            'no-tags': {**manifest, 'clips': [{key: value for key, value in clip.items() if key != 'tags'}]},
            'schema': {**manifest, 'schema': 'simvltanea.public-demo/2'},
            'not-object': [manifest],
            'no-clips': {**manifest, 'clips': []},
            'clips-object': {**manifest, 'clips': {'a': clip}},
            'traversal': {**manifest, 'clips': [{**clip, 'file': '../index.html'}]},
            'absolute': {**manifest, 'clips': [{**clip, 'file': f'/clips/{clip["id"]}.mp4'}]},
            'other-id': {**manifest, 'clips': [{**clip, 'file': 'clips/0123456789ab.mp4'}]},
            'uppercase': {**manifest, 'clips': [{**clip, 'id': clip['id'].upper(),
                                                 'file': f'clips/{clip["id"].upper()}.mp4'}]},
            'duplicate': {**manifest, 'clips': [clip, clip]},
            'fraction': {**manifest, 'clips': [{**clip, 'width': 144.5}]},
            'zero-bytes': {**manifest, 'clips': [{**clip, 'bytes': 0}]},
            'huge': {**manifest, 'clips': [{**clip, 'bytes': 65 * MIB}]},
            'wide': {**manifest, 'clips': [{**clip, 'width': 5000}]},
            'orientation': {**manifest, 'clips': [{**clip, 'orientation': 'landscape'}]},
            'short': {**manifest, 'clips': [{**clip, 'duration_seconds': 0.1}]},
            'long': {**manifest, 'clips': [{**clip, 'duration_seconds': 601}]},
            'text-duration': {**manifest, 'clips': [{**clip, 'duration_seconds': '2'}]},
            'tags-list': {**manifest, 'clips': [{**clip, 'tags': ['sea']}]},
        }
        out = node(r'''const S = require(process.argv[1]); let input = '';
          process.stdin.on('data', d => input += d).on('end', () => {
          const variants = JSON.parse(input), out = {};
          for (const [name, data] of Object.entries(variants)) out[name] = S.libraryClips(data);
          process.stdout.write(JSON.stringify(out)); });''', variants)
        self.assertEqual([item['id'] for item in out['valid']], sorted(item['id'] for item in manifest['clips']))
        # Only comparison keys survive from the tags: no keyword, caption or tag text is kept.
        self.assertEqual(set(out['valid'][0]), {'id', 'file', 'bytes', 'width', 'height', 'duration_seconds', 'orientation', 'look', 'mood'})
        self.assertNotIn(TAG_SENTINEL, json.dumps(out))
        self.assertEqual(len(out['no-tags']), 1)
        self.assertIsNone(out['no-tags'][0]['look'])
        for name, value in out.items():
            if name not in ('valid', 'no-tags'):
                with self.subTest(variant=name):
                    self.assertIsNone(value)

    def test_rolls_are_seeded_varied_and_mixed(self):
        manifest = fake_manifest()
        seeds = list(range(200))
        rolls = node(ROLL_LIBRARY, dict(manifest=manifest, families=FAMILIES, seeds=seeds))
        again = node(ROLL_LIBRARY, dict(manifest=manifest, families=FAMILIES, seeds=seeds))
        self.assertEqual(rolls, again)
        # The order of the manifest does not matter: clips are indexed by id.
        shuffled = {**manifest, 'clips': list(reversed(manifest['clips']))}
        self.assertEqual([roll['ids'] for roll in node(ROLL_LIBRARY, dict(manifest=shuffled, families=FAMILIES,
                                                                            seeds=seeds))],
                         [roll['ids'] for roll in rolls])
        by_id = {clip['id']: clip for clip in manifest['clips']}
        look = lambda clip_id: (tuple(by_id[clip_id]['tags']['palette']), by_id[clip_id]['tags']['shot'])
        for seed, roll in zip(seeds, rolls):
            with self.subTest(seed=seed):
                self.assertIn(roll['panels'], FAMILIES[roll['family']])
                self.assertEqual(len(roll['ids']), roll['panels'])
                self.assertEqual(len(set(roll['ids'])), roll['panels'])
                self.assertEqual(len({look(clip_id) for clip_id in roll['ids']}), min(roll['panels'], 6))
                if roll['panels'] >= 2:
                    self.assertEqual({by_id[clip_id]['orientation'] for clip_id in roll['ids']},
                                     {'portrait', 'landscape'})
        self.assertGreater(len({tuple(roll['ids']) for roll in rolls}), 150)
        self.assertGreater(len({clip_id for roll in rolls for clip_id in roll['ids']}), LIBRARY_CLIPS - 2)
        # Clips that failed to load are never chosen again.
        excluded = node(ROLL_LIBRARY, dict(manifest=manifest, families=FAMILIES, seeds=seeds, exclude=list(range(20))))
        ids = sorted(by_id)
        self.assertTrue(all(ids.index(clip_id) >= 20 for roll in excluded for clip_id in roll['ids']))

    def test_mix_addresses_large_libraries(self):
        out = node(r'''const S = require(process.argv[1]);
          process.stdout.write(JSON.stringify([S.parseMix('s1200.7.3', {strips: [1, 2, 3]}, 2000),
            S.parseMix('s1200.7.3', {strips: [1, 2, 3]}, 1000), S.parseMix('s12345', {strips: [1]}, 20000),
            S.LIBRARY_CACHE]));''', None)
        self.assertEqual(out, [{'family': 'strips', 'loops': [1200, 7, 3]}, None, None, 24])


class StudioLibraryTests(unittest.TestCase):
    def test_filters_share_lifecycle_presence_and_toggle_without_restarting_clips(self):
        page = self.open(query='?seed=99&mix=s0')
        self.showing(page, self.snapshot(page)['selection'])
        self.assertEqual(page.locator('#effects').count(), 1, 'Filters control is missing')
        page.evaluate('window.originalMedia=compositionRuntime.nodes.get("loop-1").media')
        page.wait_for_function('''() => {
          const node=compositionRuntime.nodes.get('loop-1');
          return node.active.presence>.5 && node.media.style.filter.includes('brightness');
        }''')
        self.unlock(page)
        page.wait_for_function('compositionRuntime.audio.enabled')
        page.wait_for_function('''() => {
          const state=SimvltaneaStudio.snapshot().ecosystem.residents[0];
          return state.age>4 && state.presence<.9;
        }''')
        state = page.evaluate('''() => {const n=compositionRuntime.nodes.get('loop-1');return {
          presence:n.active.presence,gain:n.audio.target,mixGain:n.targetGain,
          cutoff:n.audio.filter.frequency.value,type:n.audio.filter.type};}''')
        self.assertAlmostEqual(state['gain'], state['mixGain'] * state['presence'], delta=.0001)
        self.assertLess(state['cutoff'], 16000)
        self.assertEqual(state['type'], 'lowpass')
        self.tap(page, '#effects')
        self.assertEqual(page.get_attribute('#effects', 'aria-pressed'), 'false')
        self.assertFalse(self.snapshot(page)['filters'])
        self.assertIn('fx=0', page.evaluate('location.search'))
        self.assertTrue(page.evaluate('''() => {const n=compositionRuntime.nodes.get('loop-1');
          return n.media===originalMedia && !n.media.paused && n.media.style.filter==='' && n.audio.filter.type==='allpass';}'''))
        self.tap(page, '#effects')
        self.assertTrue(self.snapshot(page)['filters'])
        self.assertIn('fx=1', page.evaluate('location.search'))
        page.wait_for_function('compositionRuntime.nodes.get("loop-1").media.style.filter!==""')

    def test_filter_bypass_url_is_retained_through_shuffle(self):
        page = self.open(query='?seed=99&mix=s0.1&fx=0&evolve=0')
        self.showing(page, self.snapshot(page)['selection'])
        self.assertFalse(self.snapshot(page).get('filters', True))
        self.tap(page, '#shuffle')
        self.showing(page, self.snapshot(page)['selection'])
        self.assertIn('fx=0', page.evaluate('location.search'))
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()]
          .every(n=>n.media.style.filter==='')'''))

    """Library mode: a staged studio with a synthetic public library beside it, served on one origin."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.manifest = prepare_library()
        cls.ids = sorted(clip['id'] for clip in cls.manifest['clips'])
        cls.by_id = {clip['id']: clip for clip in cls.manifest['clips']}
        if LIBRARY_SITES.exists():
            shutil.rmtree(LIBRARY_SITES)
        studio = LIBRARY_SITES / 'studio-out'
        stage_studio(studio)
        stage_library_site(studio, LIBRARY, LIBRARY_SITES / 'good')
        # The deploy helper refuses an invalid manifest, so this site is assembled by hand.
        bad = LIBRARY_SITES / 'bad'
        shutil.copytree(LIBRARY_SITES / 'good', bad)
        broken = json.loads((bad / 'library' / 'manifest.json').read_text())
        broken['clips'][0]['file'] = '../index.html'
        (bad / 'library' / 'manifest.json').write_text(json.dumps(broken))
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                                                     functools.partial(QuietHandler, directory=str(LIBRARY_SITES)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
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

    snapshot = StudioBrowserTests.snapshot
    settled = StudioBrowserTests.settled
    playing = StudioBrowserTests.playing
    unlock = StudioBrowserTests.unlock
    tap = StudioBrowserTests.tap

    def open(self, site='good', query='', width=1280, height=720, init_script=None, has_touch=False):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, has_touch=has_touch)
        self.addCleanup(context.close)
        page = context.new_page()
        page.requests, page.errors, page.logs, page.compiler_workers = [], [], [], []
        page.on('worker', lambda worker: page.compiler_workers.append(worker))
        page.on('request', lambda request: page.requests.append(request.url))
        page.on('pageerror', lambda error: page.errors.append(str(error)))
        page.on('console', lambda message: page.logs.append(message.text))
        if init_script is not None:
            page.add_init_script(init_script)
        page.goto(f'{self.origin}/{site}/watch.html{query}')
        page.wait_for_function('() => window.SimvltaneaStudio && window.SimvltaneaStudio.snapshot && '
                               'window.compositionRuntime && SimvltaneaStudio.snapshot().seed !== null')
        self.addCleanup(lambda: self.assertEqual(page.errors, []))
        return page

    def roll(self, seed):
        return node(ROLL_LIBRARY, dict(manifest=self.manifest, families=FAMILIES, seeds=[seed]))[0]

    def clip_requests(self, page):
        return [url.rsplit('/', 1)[1][:-4] for url in page.requests if '/library/clips/' in url]

    def showing(self, page, ids, timeout=45000):
        """Wait until the runtime plays exactly these clips (by digest prefix), then return its state."""
        page.wait_for_function('ids => { const r = compositionRuntime; return r.error || (r.plan && '
                               'r.plan.sources.map(s => s.sha256.slice(0, 12)).join() === ids.join()); }',
                               arg=ids, timeout=timeout)
        state = self.playing(page, len(ids), timeout)
        self.assertEqual([sha[:12] for sha in state['sha']], ids)
        return state

    def prefetched(self, page):
        page.wait_for_function('() => { const l = SimvltaneaStudio.snapshot().library; '
                               'return l.prefetch.length && !l.inflight.length && '
                               'l.prefetch.every(id => l.cached.includes(id)); }', timeout=30000)
        return self.snapshot(page)['library']

    def private_tags_absent(self, page):
        exposed = page.content() + json.dumps(self.snapshot(page)) + '\n'.join(page.logs)
        self.assertNotIn(TAG_SENTINEL, exposed)
        for word in ('palette', 'keywords', 'mood'):
            self.assertNotIn(word, json.dumps(self.snapshot(page)))

    def test_library_compiles_away_from_the_ui_thread(self):
        """A twelve-panel selection runs the real compiler in a same-origin worker."""
        page = self.open(query='?seed=99&mix=s0.1.2.3.4.5.6.7.8.9.10.11')
        self.showing(page, self.ids[:12])
        self.assertTrue(page.compiler_workers, 'compilation still blocks the UI thread')
        self.assertTrue(all(worker.url == f'{self.origin}/good/compiler.js' for worker in page.compiler_workers))

    def test_touch_mix_controls_and_shuffle_never_exceed_four_foregrounds_plus_standby(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3.4.5.6.7.8.9.10.11&evolve=0',
                         has_touch=True, init_script=MEDIA_BUDGET_PROBE)
        self.assertEqual(self.snapshot(page)['panels'], 4)
        self.showing(page, self.ids[:4])
        self.assertEqual(self.snapshot(page)['counts'], [1, 2, 3, 4])
        for _ in range(8):
            page.keyboard.press('ArrowUp')
        self.assertEqual(self.snapshot(page)['panels'], 4)
        self.assertTrue(page.locator('#more').is_disabled())
        for _ in range(3):
            before = self.snapshot(page)
            self.tap(page, '#shuffle')
            page.wait_for_function('seed=>SimvltaneaStudio.snapshot().seed!==seed', arg=before['seed'])
            requested = self.snapshot(page)['selection']
            accepted = self.settled(page)
            # Surviving residents keep their slots even when the requested
            # shuffle lists those clips in a different order.
            self.assertCountEqual(accepted['selection'], requested)
            self.assertEqual(len(set(accepted['selection'])), 4)
            for slot, clip in enumerate(before['selection']):
                if clip in requested:
                    self.assertEqual(accepted['selection'][slot], clip)
            self.showing(page, accepted['selection'])
            self.assertEqual(accepted['panels'], 4)
        budget = page.evaluate('mediaBudget')
        self.assertLessEqual(budget['populated'], 5, budget)
        self.assertLessEqual(budget['playing'], 5, budget)
        self.assertGreaterEqual(budget['populated'], 5, 'standby transition was not exercised')
        seeded = self.open(query='?seed=99&evolve=0', has_touch=True)
        self.assertLessEqual(self.snapshot(seeded)['panels'], 4)

    def test_touch_custom_layout_and_local_pool_keep_active_population_bounded(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0', has_touch=True, init_script=MEDIA_BUDGET_PROBE)
        self.playing(page, 4)
        preset = page.evaluate("SimvltaneaStudio.stripsPreset({z1:'2',jitter:'0',reverse:false})")
        preset['counts'] = {'min': 5, 'max': 12}
        page.set_input_files('#files', {'name': 'too-many.json', 'mimeType': 'application/json',
                                       'buffer': json.dumps(preset).encode()})
        page.wait_for_function("() => SimvltaneaStudio.snapshot().toast.includes('too-many.json')")
        self.assertIsNone(self.snapshot(page)['layoutFile'])
        self.assertNotIn('file', [family['name'] for family in self.snapshot(page)['families']])
        preset['counts'] = {'min': 1, 'max': 12}
        page.set_input_files('#files', {'name': 'bounded.json', 'mimeType': 'application/json',
                                       'buffer': json.dumps(preset).encode()})
        page.wait_for_function("() => SimvltaneaStudio.snapshot().family==='file'")
        self.assertEqual(self.snapshot(page)['counts'], [1, 2, 3, 4])
        fixtures = prepare_fixtures()
        page.set_input_files('#files', [str(fixtures[name]) for name, _, _ in LOOPS])
        page.wait_for_function("() => SimvltaneaStudio.snapshot().source==='own' && !SimvltaneaStudio.snapshot().busy", timeout=60000)
        self.assertEqual(len(self.snapshot(page)['loops']), 12)
        self.assertEqual(self.snapshot(page)['panels'], 4)
        self.playing(page, 4)
        self.assertTrue(page.locator('#more').is_disabled())
        budget = page.evaluate('mediaBudget')
        self.assertLessEqual(budget['populated'], 5, budget)
        self.assertLessEqual(budget['playing'], 5, budget)

    def test_library_plays_without_worker_support(self):
        page = self.open(query='?seed=7', init_script='window.Worker = undefined;')
        self.showing(page, self.roll(7)['ids'])
        self.assertEqual(page.compiler_workers, [])

    def test_new_selection_supersedes_an_inflight_compilation(self):
        page = self.open(query='?seed=99&mix=s0.1', init_script=r'''(() => {
          const NativeWorker = Worker;
          window.Worker = class extends NativeWorker {
            postMessage(input) { setTimeout(() => super.postMessage(input), 200); }
          };
        })();''')
        page.keyboard.press('ArrowUp')
        page.keyboard.press('ArrowUp')
        self.assertEqual(self.snapshot(page)['panels'], 4)
        expected = self.snapshot(page)['selection']
        self.showing(page, expected)
        self.assertEqual(len(page.query_selector_all('#stage video[data-deck=active]')), 4)
        self.assertFalse(self.snapshot(page)['toastShown'])

    def test_first_sound_gesture_during_initial_compilation_is_applied(self):
        page = self.open(query='?seed=7', init_script=r'''(() => {
          const NativeWorker = Worker, queue = [];
          let gated = true;
          window.releaseCompilation = () => { gated = false; queue.splice(0).forEach(send => send()); };
          window.Worker = class extends NativeWorker {
            postMessage(input) {
              if (gated) { queue.push(() => super.postMessage(input)); window.compilationWaiting = true; }
              else super.postMessage(input);
            }
          };
        })();''')
        page.wait_for_function('() => window.compilationWaiting')
        self.assertFalse(page.evaluate('compositionRuntime.ready'))
        page.click('#speaker')
        page.evaluate('window.releaseCompilation()')
        self.showing(page, self.roll(7)['ids'])
        page.wait_for_function("() => compositionRuntime.audio.mode === 'spatial_loops'", timeout=4000)
        self.assertTrue(page.evaluate('compositionRuntime.audio.enabled'))
        self.assertEqual(page.get_attribute('#speaker', 'aria-label'), 'Mute')

    def test_library_starts_when_media_preload_is_deferred(self):
        """A browser that waits for play() must not leave admission or runtime loading forever."""
        page = self.open(query='?seed=7', init_script=r'''(() => {
          // Defer the real decoded-frame event until a muted play request, as on low-data media paths.
          const primed = new WeakSet(), create = Document.prototype.createElement;
          const play = HTMLMediaElement.prototype.play;
          Document.prototype.createElement = function(...args) {
            const node = create.apply(this, args);
            if (node instanceof HTMLVideoElement) node.addEventListener('loadeddata', event => {
              if (!primed.has(node)) event.stopImmediatePropagation();
            }, true);
            return node;
          };
          HTMLMediaElement.prototype.play = function(...args) {
            primed.add(this); return play.apply(this, args);
          };
        })();''')
        state = self.showing(page, self.roll(7)['ids'], timeout=4000)
        self.assertTrue(state['running'])
        self.assertTrue(all(value for value in state['muted']))
        self.assertEqual(self.snapshot(page)['library']['broken'], 0)

    def test_sound_and_panel_edits_preserve_untouched_media(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3')
        self.showing(page, self.snapshot(page)['selection'])
        page.evaluate('''() => {
          window.residents = [...compositionRuntime.nodes.values()].map(n => n.media);
          window.originalClock = compositionRuntime.snapshot().compositionTime;
          window.siblingEvents = [];
          const time = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
          for (const v of residents.slice(1)) {
            for (const type of ['pause', 'emptied']) v.addEventListener(type, () => siblingEvents.push(type));
            // Native loop wraps may emit seeking; only application seeks violate isolation.
            Object.defineProperty(v, 'currentTime', {
              get() { return time.get.call(this); },
              set(value) { siblingEvents.push('seek-write'); time.set.call(this, value); }
            });
          }
        }''')
        self.unlock(page)
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()]
          .every((n, i) => n.media === residents[i])'''))
        self.assertGreaterEqual(page.evaluate('compositionRuntime.snapshot().compositionTime'),
                                page.evaluate('originalClock'))
        page.evaluate('window.originalAudio = compositionRuntime.audio.context')
        before = self.snapshot(page)['selection']
        box = page.locator('#stage .loop[data-loop-id="loop-1"]').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.wait_for_function('b => SimvltaneaStudio.snapshot().selection[0] !== b', arg=before[0])
        self.showing(page, self.snapshot(page)['selection'])
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()].slice(1)
          .every((n, i) => n.media === residents[i + 1])'''))

        self.assertEqual(page.evaluate('siblingEvents'), [])
        self.assertTrue(page.evaluate('compositionRuntime.audio.context === originalAudio'))
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()].slice(1)
          .every((n, i) => n.media === residents[i + 1])'''))

    def test_library_evolves_while_manual_population_stays_fixed(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3')
        self.showing(page, self.snapshot(page)['selection'])
        before = self.snapshot(page)['selection']
        # The requested plan can change while its incoming resident still waits
        # for a preparation permit. Prove an actual committed replacement.
        page.wait_for_function('''before => {
          const r=compositionRuntime, selection=SimvltaneaStudio.snapshot().selection;
          const actual=[...r.nodes.values()].map(node=>node.item?.name);
          return !r.draining && actual.join()===selection.join() && actual.join()!==before.join();
        }''', arg=before, timeout=40000)
        self.assertEqual(self.snapshot(page)['panels'], 4)
        state = page.evaluate('compositionRuntime.snapshot()')
        self.assertEqual(state['maxConcurrentStandbys'], 1)
        self.tap(page, '#activity')
        # Hold allows a handoff already in flight to finish. Capture its settled
        # residents before checking that no further automatic changes begin.
        page.wait_for_function('''() => {
          const r=compositionRuntime, selection=SimvltaneaStudio.snapshot().selection;
          return !r.draining && [...r.nodes.values()].map(node=>node.item?.name).join()===selection.join();
        }''', timeout=10000)
        held = self.snapshot(page)['selection']
        frames = page.evaluate('[...compositionRuntime.nodes.values()].map(node=>node.callbacks)')
        self.assertFalse(self.snapshot(page)['evolving'])
        page.wait_for_timeout(3000)
        self.assertEqual(self.snapshot(page)['selection'], held)
        actual = page.evaluate('[...compositionRuntime.nodes.values()].map(node=>({name:node.item.name,frames:node.callbacks}))')
        self.assertEqual([node['name'] for node in actual], held)
        # Native loop wraps briefly return HAVE_METADATA (readyState=1). Real
        # decoded-frame progress verifies continuity without racing that dip.
        self.assertTrue(all(node['frames'] > earlier for node, earlier in zip(actual, frames)), actual)

    def test_four_panel_ecology_changes_actual_territory(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3')
        self.showing(page, self.snapshot(page)['selection'])
        page.wait_for_function('''() => {
          const widths = [...compositionRuntime.nodes.values()].map(n => n.box.getBoundingClientRect().width);
          return widths.length === 4 && Math.max(...widths) - Math.min(...widths) > 2;
        }''', timeout=6000)
        self.assertEqual(page.evaluate('compositionRuntime.nodes.size'), 4)

    def test_pause_during_initial_priming_is_honored(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3', init_script='''(() => {
          const frame = HTMLVideoElement.prototype.requestVideoFrameCallback;
          HTMLVideoElement.prototype.requestVideoFrameCallback = function(callback) {
            return frame.call(this, (time, metadata) => setTimeout(() => callback(time, metadata), 600));
          };
        })();''')
        page.wait_for_function('() => compositionRuntime.running && compositionRuntime.draining && !compositionRuntime.ready')
        self.tap(page, '#play')
        page.wait_for_function('() => compositionRuntime.ready')
        self.assertTrue(self.snapshot(page)['paused'])
        self.assertFalse(page.evaluate('compositionRuntime.running'))
        self.assertTrue(page.evaluate('() => [...compositionRuntime.nodes.values()].every(n => n.media.paused)'))

    def test_failed_boomerang_keeps_its_healthy_forward_clip(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0')
        manifest = json.loads((LIBRARY / 'manifest.json').read_text())
        clip = sorted(manifest['clips'], key=lambda item: item['id'])[0]
        variant_id = '0123456789ab'
        clip['variants'] = {'boomerang': {
            **{key: clip[key] for key in ('width', 'height', 'orientation', 'bytes')},
            'id': variant_id, 'file': f'clips/{variant_id}.mp4', 'duration_seconds': 1,
            'fps': 30, 'frame_count': 30, 'seam_offset_seconds': .5,
            'has_audio': False, 'lufs_integrated': None, 'peak_dbfs': None,
            'rms_envelope': [0] * 10, 'envelope_hz': 10,
        }}
        page.route('**/library/manifest.json', lambda route: route.fulfill(json=manifest))
        page.route(f'**/library/clips/{variant_id}.mp4', lambda route: route.fulfill(status=404))
        page.reload()
        page.wait_for_function('''() => window.SimvltaneaStudio?.snapshot &&
          (SimvltaneaStudio.snapshot().library?.broken > 0 || compositionRuntime.ready)''')
        self.assertEqual(self.snapshot(page)['library']['broken'], 0)
        self.assertIn(clip['id'], self.snapshot(page)['selection'])
        self.assertEqual(page.evaluate('compositionRuntime.nodes.get("loop-1").item.asset.id'), clip['id'])

    def test_tap_with_no_spare_clip_keeps_every_sibling(self):
        page = self.open(query='?seed=99&mix=s0.1&evolve=0')
        manifest = json.loads((LIBRARY / 'manifest.json').read_text())
        manifest['clips'] = sorted(manifest['clips'], key=lambda item: item['id'])[:2]
        page.route('**/library/manifest.json', lambda route: route.fulfill(json=manifest))
        page.reload()
        page.wait_for_function('() => window.SimvltaneaStudio?.snapshot && compositionRuntime.ready')
        self.unlock(page)
        before = self.snapshot(page)['selection']
        page.evaluate('window.originalResidents = [...compositionRuntime.nodes.values()].map(n => n.media)')
        box = page.locator('#stage .loop[data-loop-id="loop-1"]').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        self.assertEqual(self.snapshot(page)['selection'], before)
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()]
          .every((n, i) => n.media === originalResidents[i])'''))

    def test_pending_manual_selection_outranks_automatic_replacement(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3', init_script='''(() => {
          const NativeWorker = Worker, queued = [];
          window.holdCompilation = false;
          window.releaseCompilation = () => {
            holdCompilation = false;
            queued.splice(0).forEach(send => { try { send(); } catch (_) {} });
          };
          window.Worker = class extends NativeWorker {
            postMessage(input) {
              if (holdCompilation) queued.push(() => super.postMessage(input));
              else super.postMessage(input);
            }
          };
        })();''')
        self.showing(page, self.snapshot(page)['selection'])
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().ecosystem.residents.some(
          r => r.deadlineAge - r.age < 0.8)''', timeout=35000)
        page.evaluate('holdCompilation = true')
        self.tap(page, '#more')
        expected = self.snapshot(page)['selection']
        self.assertEqual(len(expected), 5)
        page.wait_for_timeout(3500)
        self.assertEqual(self.snapshot(page)['selection'], expected)
        page.evaluate('releaseCompilation()')
        self.showing(page, expected)

    def test_library_fetch_continuation_respects_personal_pool_change(self):
        for added in (True, False):
            with self.subTest(personal_file_admitted=added):
                page = self.open(query='?seed=99&mix=s0.1&evolve=0')
                held, block = [], [True]

                def route(request):
                    clip_id = request.request.url.rsplit('/', 1)[-1][:-4]
                    if block[0] and clip_id not in self.ids[:2]:
                        held.append(request)
                    else:
                        request.continue_()

                page.route('**/library/clips/*.mp4', route)
                page.reload()
                self.showing(page, self.ids[:2])
                self.tap(page, '#speaker')
                page.wait_for_function("() => SimvltaneaStudio.snapshot().sound==='on'")
                page.evaluate('''() => {
                  const r=compositionRuntime, reconcile=r.reconcile.bind(r);
                  window.admissionReconciles=[];
                  r.reconcile=request=>{admissionReconciles.push({busy:SimvltaneaStudio.snapshot().busy,
                    shas:request.items.map(item=>item.sha256)});return reconcile(request)};
                  window.originalLocalHandoff=[...r.nodes.values()].map(n=>n.media);
                  const read=File.prototype.arrayBuffer;
                  File.prototype.arrayBuffer=function(){return this.name==='second.mp4' ?
                    new Promise(resolve=>{window.releaseSecondLocal=()=>resolve(read.call(this))}) : read.call(this)};
                  const step=SimvltaneaEcosystem.Engine.prototype.step;
                  SimvltaneaEcosystem.Engine.prototype.step=function(time,dt,residents,options){
                    window.observedLogicalIds=residents.map(item=>({logicalId:item.logicalId,sha:item.clipKey}));
                    return step.call(this,time,dt,residents,options);
                  };
                }''')
                page.locator('.loop[data-loop-id="loop-2"]').click()
                page.wait_for_function('before=>SimvltaneaStudio.snapshot().selection.join()!==before.join()', arg=self.ids[:2])
                wanted = self.snapshot(page)['selection'][1]
                payloads = [dict(name=name,mimeType='video/mp4',buffer=(LIBRARY / self.by_id[clip_id]['file']).read_bytes() if added else b'invalid')
                            for name, clip_id in zip(('first.mp4', 'second.mp4'), self.ids[:2])]
                page.set_input_files('#files', payloads)
                page.wait_for_function('count=>Boolean(window.releaseSecondLocal) && SimvltaneaStudio.snapshot().busy && '
                                       'SimvltaneaStudio.snapshot().loops.length===count', arg=int(added))
                self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===originalLocalHandoff[i])'))
                block[0] = False
                for request in held:
                    request.continue_()
                page.wait_for_function('id=>SimvltaneaStudio.snapshot().library.cached.includes(id)', arg=wanted)
                if added:
                    # Let fulfilled fetch and compile microtasks run while the
                    # second file is still blocked at its normal local read.
                    page.wait_for_timeout(200)
                    self.assertEqual(page.evaluate('admissionReconciles'), [])
                    self.assertEqual(page.evaluate('compositionRuntime.nodes.size'), 2)
                    self.assertTrue(page.evaluate('[...compositionRuntime.nodes.values()].every((n,i)=>n.media===originalLocalHandoff[i])'))
                else:
                    # An entirely refused batch never changes the pool. The
                    # original library request must still complete normally.
                    self.showing(page, self.snapshot(page)['selection'])
                    self.assertTrue(page.evaluate('admissionReconciles.length>0'))
                    self.assertEqual(self.snapshot(page)['source'], 'library')
                page.evaluate('releaseSecondLocal()')
                page.wait_for_function('() => !SimvltaneaStudio.snapshot().busy')
                self.playing(page, 2)
                self.assertEqual(self.snapshot(page)['source'], 'own' if added else 'library')
                if added:
                    page.wait_for_function('() => !compositionRuntime.draining && observedLogicalIds.length===2 && '
                                           'observedLogicalIds.every(item=>SimvltaneaStudio.snapshot().loops.some(loop=>loop.sha256===item.sha))')
                    self.assertTrue(page.evaluate('observedLogicalIds.every(item=>item.logicalId===item.sha)'))

    def test_library_mode_fetches_only_the_rolls_clips(self):
        page = self.open(query='?seed=424242')
        expected = self.roll(424242)
        snapshot = self.snapshot(page)
        self.assertEqual((snapshot['source'], snapshot['record'], snapshot['builtinsReady']), ('library', 'library', 0))
        self.assertEqual((snapshot['family'], snapshot['selection']), (expected['family'], expected['ids']))
        state = self.showing(page, expected['ids'])
        self.assertEqual(state['version'], 1)
        self.assertEqual(state['muted'], [True] * len(expected['ids']))
        self.assertEqual(page.evaluate("document.querySelectorAll('#preview canvas').length"), 0)
        prefetch = self.prefetched(page)['prefetch']
        requested = self.clip_requests(page)
        self.assertEqual(len(requested), len(set(requested)), 'a clip was fetched twice')
        self.assertEqual(set(requested), set(expected['ids']) | set(prefetch))
        self.assertLess(len(set(requested)), LIBRARY_CLIPS)
        staged = {f'{self.origin}/good/{name}' for name in ('', *STUDIO_FILES, 'library/manifest.json')}
        others = [url for url in page.requests if not (url.split('?')[0] in staged or '/good/library/clips/' in url
                                                       or url.startswith(('blob:', 'data:')))]
        self.assertEqual(others, [])
        looks = {(tuple(self.by_id[i]['tags']['palette']), self.by_id[i]['tags']['shot']) for i in expected['ids']}
        self.assertEqual(len(looks), min(len(expected['ids']), 6))
        if len(expected['ids']) >= 2:
            self.assertEqual({self.by_id[i]['orientation'] for i in expected['ids']}, {'portrait', 'landscape'})
        self.private_tags_absent(page)

    def test_seed_reproduces_the_clips_and_shuffle_plays_the_next_roll(self):
        first = self.open(query='?seed=99')
        second = self.open(query='?seed=99', width=390, height=844)
        expected = self.roll(99)
        for page in (first, second):
            self.assertEqual(self.snapshot(page)['selection'], expected['ids'])
        self.showing(first, expected['ids'])
        self.showing(second, expected['ids'])
        ready = self.prefetched(first)
        self.assertEqual(ready['prefetch'], self.roll(ready['next'])['ids'])
        self.tap(first, '#shuffle')
        first.wait_for_function('s => SimvltaneaStudio.snapshot().seed !== s', arg=99)
        after = self.settled(first)
        self.assertEqual(after['seed'], ready['next'])
        self.assertEqual(after['panels'], len(ready['prefetch']))
        self.assertEqual(len(set(after['selection'])), after['panels'])
        self.assertTrue(set(after['selection']) <= set(expected['ids']) | set(ready['prefetch']))
        self.assertTrue(set(ready['prefetch']) - set(expected['ids']) <= set(after['selection']))
        # A resident requested again keeps its surviving slot through a shuffle.
        # Shrinking can retain a different old clip instead of moving a retiring one.
        for slot, clip_id in enumerate(expected['ids'][:after['panels']]):
            if clip_id in ready['prefetch']:
                self.assertEqual(after['selection'][slot], clip_id)
        self.assertRegex(first.evaluate('location.search'), rf'^\?seed={after["seed"]}&rv=2(?:&mix=[sa][\d.]+)?$')
        self.showing(first, after['selection'])
        again = self.open(query=first.evaluate('location.search'))
        self.assertEqual(self.settled(again)['selection'], after['selection'])
        self.showing(again, after['selection'])
        later = self.prefetched(first)
        requested = self.clip_requests(first)
        self.assertEqual(len(requested), len(set(requested)), 'a clip was fetched twice')
        self.assertTrue(set(after['selection']) <= set(requested))
        self.assertTrue(set(requested) <= set(expected['ids']) | set(after['selection']) | set(later['prefetch']))
        self.assertLessEqual(len(later['cached']), 24)
        # Keys: R rolls again; arrows change the count, fetching only the clips that are added.
        before = set(self.clip_requests(first))
        self.assertIn(after['panels'], after['counts'])
        first.locator('body').press('ArrowRight' if after['panels'] < max(after['counts']) else 'ArrowLeft')
        first.wait_for_function('n => SimvltaneaStudio.snapshot().panels !== n', arg=after['panels'])
        edited = self.settled(first)
        self.showing(first, edited['selection'])
        self.assertTrue(set(self.clip_requests(first)) - before <= set(edited['selection']) | set(later['prefetch']))
        self.assertRegex(first.evaluate('location.search'), rf'^\?seed={after["seed"]}&rv=2&mix=[sa]\d')
        self.private_tags_absent(first)

    def test_clips_play_their_own_audio_after_the_first_click(self):
        page = self.open(query='?seed=7')
        expected = self.roll(7)
        self.showing(page, expected['ids'])
        self.assertEqual(page.get_attribute('#speaker', 'aria-label'), 'Tap for sound')
        self.unlock(page)
        page.wait_for_function('() => [...compositionRuntime.nodes.values()].every(n => n.audio && n.audio.gain.gain.value > 0)')
        count = len(expected['ids'])
        state = page.evaluate('''() => { const r = compositionRuntime;
          return {mode: r.audio.mode, gains: [...r.nodes.values()].map(n => n.audio.gain.gain.value),
                  perLoop: Object.values(r.plan.audio.per_loop).map(l => l.gain),
                  muted: [...document.querySelectorAll('#stage video[data-deck=active]')].map(v => v.muted),
                  audio: r.plan.sources.map(s => s.audio_stream)}; }''')
        self.assertEqual(state['mode'], 'spatial_loops')
        self.assertTrue(all(gain > 0 for gain in state['gains']), state)
        self.assertEqual(state['audio'], [{'codec': 'aac', 'channels': 1}] * count)
        self.assertEqual(set(state['perLoop']), {f'{max(1, round(1000 / math.sqrt(count)))}/1000'})
        self.assertEqual(set(state['muted']), {False})
        self.assertEqual(self.snapshot(page)['sound'], 'on')
        page.keyboard.press('m')
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().sound === 'off' &&
          [...document.querySelectorAll('#stage video[data-deck=active]')].every(v => v.muted)''')
        page.keyboard.press('m')
        page.wait_for_function('''() => SimvltaneaStudio.snapshot().sound === 'on' &&
          [...document.querySelectorAll('#stage video[data-deck=active]')].every(v => !v.muted)''')
        # A tapped panel gets a new clip, fetched on demand; the others stay.
        before = self.snapshot(page)['selection']
        box = page.locator('#stage .loop[data-loop-id="loop-1"]').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.wait_for_function('b => SimvltaneaStudio.snapshot().selection.join() !== b.join()', arg=before)
        after = self.snapshot(page)['selection']
        self.assertNotEqual(after[0], before[0])
        self.assertEqual(after[1:], before[1:])
        self.showing(page, after)
        self.assertEqual(page.evaluate('compositionRuntime.plan.plan_version'), 2)
        self.assertIn(after[0], self.clip_requests(page))
        self.private_tags_absent(page)

    def test_invalid_manifest_falls_back_to_generated_loops(self):
        page = self.open(site='bad')
        snapshot = self.snapshot(page)
        self.assertEqual((snapshot['source'], snapshot['library']), ('builtin', None))
        self.playing(page, snapshot['panels'])
        self.assertEqual(self.snapshot(page)['builtinsReady'], 12)
        self.assertIn(f'{self.origin}/bad/library/manifest.json', page.requests)
        self.assertEqual(self.clip_requests(page), [])

    def test_gen_forces_the_generated_loops(self):
        page = self.open(query='?gen=1&seed=5')
        snapshot = self.snapshot(page)
        self.assertEqual((snapshot['source'], snapshot['library']), ('builtin', None))
        self.playing(page, snapshot['panels'])
        self.assertEqual([url for url in page.requests if '/library/' in url], [])


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
