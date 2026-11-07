#!/usr/bin/env python3
"""Add verified boomerang variants to an already admitted public clip library.

Forward files and logical IDs stay unchanged. Output is a fresh atomic directory;
no private-media discovery, shell execution, or publication occurs here. MP4
presentation durations are verified separately from AAC's padded decoder frames.
Run: python3 -m tools.media.build_boomerangs --library var/site/deploy/library --out var/site/loops
"""
from __future__ import annotations

import argparse
from array import array
import copy
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from tools.publishing.stage_library_site import LibrarySiteError, check_library

FPS = 30
SAMPLE_RATE = 48000
SAMPLES_PER_FRAME = 1600
ENVELOPE_HZ = 10
MAX_DURATION = 600
MAX_FILE_BYTES = 25 * 1024 * 1024
TIMEOUT = 600


class BuildError(Exception):
    """An invalid input or failed encode/measurement; no output is admitted."""


def run(arguments: list, *, stdout=subprocess.PIPE) -> subprocess.CompletedProcess:
    if arguments[0] == 'ffmpeg':
        arguments = [arguments[0], '-nostdin', '-threads', '1', '-filter_threads', '1',
                     '-filter_complex_threads', '1', *arguments[1:]]
    try:
        result = subprocess.run([str(value) for value in arguments], stdin=subprocess.DEVNULL,
                                stdout=stdout, stderr=subprocess.PIPE, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise BuildError(f'{arguments[0]} unavailable or timed out') from error
    if result.returncode:
        raise BuildError(f'{arguments[0]} failed: {result.stderr.decode(errors="replace")[-1500:]}')
    return result


def probe(path: Path, *, frames: bool = False) -> dict:
    command = ['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format']
    if frames:
        command += ['-select_streams', 'v:0', '-show_frames', '-show_entries',
                    'frame=pts,best_effort_timestamp:stream']
    try:
        return json.loads(run([*command, '-of', 'json', path]).stdout)
    except (ValueError, TypeError) as error:
        raise BuildError('ffprobe did not return JSON') from error


def loop_frame_count(frame_count: int, fade_frames: int) -> int:
    if (type(frame_count) is not int or frame_count < 8 or type(fade_frames) is not int
            or fade_frames < 0 or fade_frames > frame_count - 4):
        raise BuildError('need at least eight frames and an integer overlap between zero and M-4')
    count = 2 * frame_count - 2 - fade_frames
    if count / FPS > MAX_DURATION:
        raise BuildError('derived loop exceeds the 600-second library limit')
    return count


def _streams(data: dict) -> tuple[dict, dict | None]:
    video = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
    audio = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
    if len(video) != 1 or len(audio) > 1:
        raise BuildError('expected one video and at most one audio stream')
    return video[0], audio[0] if audio else None


def verify_encoded(path: Path, expected_frames: int) -> dict:
    """Verify actual frame timestamps and separate audio/video presentation lengths."""
    data = probe(path)
    video, audio = _streams(data)
    if not audio or video.get('codec_name') != 'h264' or audio.get('codec_name') != 'aac':
        raise BuildError('expected H.264 and AAC output')
    if video.get('pix_fmt') != 'yuv420p' or audio.get('sample_rate') != str(SAMPLE_RATE):
        raise BuildError('unexpected pixel format or sample rate')
    try:
        count = int(video['nb_read_frames'])
        v_duration = Fraction(int(video['duration_ts'])) * Fraction(video['time_base'])
        a_duration = Fraction(int(audio['duration_ts'])) * Fraction(audio['time_base'])
        if (count != expected_frames or abs(v_duration - Fraction(count, FPS)) >= Fraction(1, 1000)
                or abs(v_duration - a_duration) >= Fraction(1, 1000)
                or video['r_frame_rate'] != '30/1' or video['avg_frame_rate'] != '30/1'):
            raise BuildError('encoded frame count, CFR or A/V duration contract failed')
        frames = probe(path, frames=True)['frames']
        pts = [Fraction(int(frame.get('pts', frame.get('best_effort_timestamp'))))
               * Fraction(video['time_base']) for frame in frames]
        if (len(pts) != count or pts[0] != 0
                or any(b - a != Fraction(1, FPS) for a, b in zip(pts, pts[1:]))):
            raise BuildError('encoded frame presentation timestamps are not exact CFR')
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise BuildError('missing or invalid encoded timing facts') from error
    if path.stat().st_size > MAX_FILE_BYTES:
        raise BuildError('derived clip exceeds the Pages 25 MiB file limit')
    return {'frame_count': count, 'duration_seconds': float(v_duration),
            'av_delta_seconds': float(abs(v_duration - a_duration)),
            'audio_duration_seconds': float(a_duration),
            'r_frame_rate': video['r_frame_rate'], 'avg_frame_rate': video['avg_frame_rate'],
            'width': int(video['width']), 'height': int(video['height'])}


def audio_facts(path: Path, duration: float, has_stream: bool) -> dict:
    """Measure final decoded PCM; RMS is linear amplitude per 100ms, saturated at1.

    The envelope is the larger channel RMS. Peak is sample-peak dBFS, not a
    claim of true-peak limiting. Null integrated LUFS means silence or material
    too short for the gated measurement. No failed measurement is fabricated.
    """
    if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
        raise BuildError('invalid audio measurement duration')
    bins = math.ceil(duration * ENVELOPE_HZ)
    silent = {'has_audio': False, 'lufs_integrated': None, 'peak_dbfs': None,
              'rms_envelope': [0.0] * bins, 'envelope_hz': ENVELOPE_HZ}
    if not has_stream:
        return silent
    try:
        data = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                               '-show_entries', 'stream=channels', '-of', 'json', path]).stdout)
        channels = int(data['streams'][0]['channels'])
        if not 1 <= channels <= 8:
            raise ValueError('unsupported channel count')
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise BuildError('cannot measure native audio channels') from error
    peak = 0.0
    envelope = []
    frames_per_bin = SAMPLE_RATE // ENVELOPE_HZ
    with tempfile.TemporaryFile() as pcm:
        run(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-af',
             f'apad,atrim=duration={duration:.9f}', '-ar', str(SAMPLE_RATE),
             '-f', 'f32le', '-'], stdout=pcm)
        pcm.seek(0)
        for _ in range(bins):
            samples = array('f')
            samples.frombytes(pcm.read(frames_per_bin * channels * 4))
            if sys.byteorder != 'little':
                samples.byteswap()
            if not samples:
                envelope.append(0.0)
                continue
            if any(not math.isfinite(x) for x in samples):
                raise BuildError('decoded audio contains nonfinite samples')
            peak = max(peak, max(abs(x) for x in samples))
            channel_energy = [sum(x * x for x in samples[channel::channels])
                              for channel in range(channels)]
            rms = math.sqrt(max(channel_energy) / max(1, len(samples) // channels))
            envelope.append(round(min(1.0, rms), 7))
    if peak <= 1e-8:
        return silent
    measured = run(['ffmpeg', '-nostats', '-i', path, '-map', '0:a:0', '-af',
                    'ebur128=peak=true', '-f', 'null', '-']).stderr.decode(errors='replace')
    summary = measured.rsplit('Summary:', 1)
    match = re.search(r'I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS', summary[-1])
    if len(summary) != 2 or not match:
        raise BuildError('missing integrated loudness measurement')
    loudness = float(match.group(1))
    # ebur128 reports its -70 LUFS floor for insufficient gated material.
    lufs = loudness if math.isfinite(loudness) and loudness > -70 else None
    return {'has_audio': True, 'lufs_integrated': lufs, 'peak_dbfs': round(20 * math.log10(peak), 6),
            'rms_envelope': envelope, 'envelope_hz': ENVELOPE_HZ}


def _normalize(source: Path, intermediate: Path, with_audio: bool) -> int:
    command = ['ffmpeg', '-y', '-v', 'error', '-i', source]
    if not with_audio:
        command += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']
    command += ['-map', '0:v:0', '-map', '0:a:0' if with_audio else '1:a:0',
                '-vf', 'fps=30:round=near,settb=1/30,format=yuv420p,setsar=1',
                '-af', 'aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,apad',
                '-c:v', 'ffv1', '-level', '3', '-c:a', 'pcm_f32le', '-shortest',
                '-threads:v', '1', '-map_metadata', '-1', '-map_chapters', '-1', intermediate]
    run(command)
    video, _ = _streams(probe(intermediate))
    try:
        return int(video['nb_read_frames'])
    except (KeyError, ValueError) as error:
        raise BuildError('cannot count normalized frames') from error


def build_variant(source: Path, destination: Path, *, fade_frames: int = 2,
                  audio_mode: str = 'forward') -> dict:
    if audio_mode not in ('forward', 'reverse'):
        raise BuildError('audio mode must be forward or reverse')
    _, audio = _streams(probe(source))
    with tempfile.TemporaryDirectory(prefix='boomerang-') as temporary:
        intermediate = Path(temporary) / 'cfr.mkv'
        count = _normalize(source, intermediate, bool(audio))
        total = loop_frame_count(count, fade_frames)
        duration, samples = total / FPS, total * SAMPLES_PER_FRAME
        overlap, offset = fade_frames / FPS, (count - fade_frames) / FPS
        # Reassert frame rate on both links: reverse/setpts can erase it.
        video = (f'[0:v]split[vf][vr];[vf]trim=end_frame={count},setpts=PTS-STARTPTS,fps=30,settb=1/30[f];'
                 f'[vr]trim=start_frame=1:end_frame={count-1},reverse,setpts=PTS-STARTPTS,fps=30,settb=1/30[r];')
        video += (f'[f][r]xfade=transition=fade:duration={overlap:.9f}:offset={offset:.9f}' if fade_frames
                  else '[f][r]concat=n=2:v=1:a=0')
        video += f',fps=30,settb=1/30,trim=end_frame={total},setpts=PTS-STARTPTS[v]'
        # Independent audio inputs avoid a streaming asplit/acrossfade EOF trap.
        sound = (f'[0:a]apad,atrim=end_sample={count*1600},asetpts=N/SR/TB[af];'
                 f'[1:a]apad,atrim=end_sample={count*1600},atrim=start_sample=1600:end_sample={(count-1)*1600},'
                 + ('areverse,' if audio_mode == 'reverse' else '') + 'asetpts=N/SR/TB[ar];')
        sound += (f'[af][ar]acrossfade=ns={fade_frames*1600}:c1=qsin:c2=qsin' if fade_frames
                  else '[af][ar]concat=n=2:v=0:a=1')
        # Headroom accounts for correlated equal-power crossfades before encoding.
        source_facts = audio_facts(intermediate, min(count / FPS, MAX_DURATION), bool(audio))
        source_peak = 10 ** (source_facts['peak_dbfs'] / 20) if source_facts['has_audio'] else 0
        headroom = min(1.0, .85 / (source_peak * (math.sqrt(2) if fade_frames else 1))) if source_peak else 1
        sound += (f',apad,atrim=end_sample={samples},asetpts=N/SR/TB,volume={headroom:.12f},'
                  f'afade=t=in:ss=0:ns=64,afade=t=out:ss={samples-64}:ns=64[a]')
        run(['ffmpeg', '-y', '-v', 'error', '-i', intermediate, '-i', intermediate,
             '-filter_complex', video + ';' + sound, '-map', '[v]', '-map', '[a]',
             '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-preset', 'medium',
             '-crf', '20', '-g', '30', '-keyint_min', '15', '-sc_threshold', '0',
             '-r', '30', '-fps_mode', 'cfr', '-enc_time_base:v', '1:30',
             '-video_track_timescale', '30000', '-movie_timescale', '48000',
             '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2',
             '-t', f'{duration:.9f}', '-use_editlist', '1', '-movflags', '+faststart',
             '-map_metadata', '-1', '-map_chapters', '-1', '-fflags', '+bitexact',
             '-flags:v', '+bitexact', '-flags:a', '+bitexact', '-threads:v', '1', destination])
    facts = verify_encoded(destination, total)
    width, height = facts['width'], facts['height']
    return {'width': width, 'height': height, 'orientation': 'portrait' if height > width else 'landscape',
            'duration_seconds': round(duration, 9), 'fps': FPS, 'frame_count': total,
            'seam_offset_seconds': round(offset, 9),
            **audio_facts(destination, duration, True)}


def build_library(source: Path, output: Path, *, fade_frames: int = 2, audio_mode: str = 'forward',
                  jobs: int = 1) -> dict:
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise BuildError('jobs must be an integer between one and eight')
    source, output = Path(source), Path(output)
    source_resolved, output_resolved = source.resolve(), output.resolve()
    if (output.exists() or output.is_symlink() or source_resolved == output_resolved
            or source_resolved in output_resolved.parents or output_resolved in source_resolved.parents):
        raise BuildError('output must be a new directory outside the input library')
    if source.is_symlink():
        raise BuildError('input library must not be a symlink')
    try:
        clips = check_library(source)
    except LibrarySiteError as error:
        raise BuildError(str(error)) from error
    if any(clip['bytes'] > MAX_FILE_BYTES for clip in clips):
        raise BuildError('forward asset exceeds the Pages 25 MiB file limit')
    if type(fade_frames) is not int or fade_frames < 0 or audio_mode not in ('forward', 'reverse'):
        raise BuildError('invalid overlap or audio mode')
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.boomerangs-', dir=output.parent))
    try:
        (work / 'clips').mkdir()
        def prepare(clip):
            entry = copy.deepcopy(clip)
            entry.pop('variants', None)
            source_file = source / clip['file']
            shutil.copyfile(source_file, work / clip['file'])
            _, audio = _streams(probe(source_file))
            entry.update(audio_facts(source_file, clip['duration_seconds'], bool(audio)))
            temporary = work / f'variant-{clip["id"]}.mp4'
            facts = build_variant(source_file, temporary, fade_frames=fade_frames, audio_mode=audio_mode)
            blob = temporary.read_bytes()
            identity = hashlib.sha256(blob).hexdigest()[:12]
            file = f'clips/{identity}.mp4'
            target = work / file
            if identity == clip['id']:
                raise BuildError('variant unexpectedly has the forward asset identity')
            if target.exists() and target.read_bytes() != blob:
                raise BuildError('content hash prefix collision')
            temporary.replace(target)
            entry['variants'] = {'boomerang': {'id': identity, 'file': file, 'bytes': len(blob), **facts}}
            return entry

        entries = [None] * len(clips)
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            pending = {executor.submit(prepare, clip): number for number, clip in enumerate(clips)}
            try:
                for done, future in enumerate(as_completed(pending), 1):
                    entry = future.result()
                    entries[pending[future]] = entry
                    frames = entry['variants']['boomerang']['frame_count']
                    print(f'verified boomerang {done}/{len(clips)}: {frames} frames', flush=True)
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
        document = {'schema': 'simvltanea.public-demo/1', 'clips': entries}
        (work / 'manifest.json').write_text(json.dumps(document, indent=1, sort_keys=True, allow_nan=False) + '\n')
        try:
            check_library(work)
        except LibrarySiteError as error:
            raise BuildError(str(error)) from error
        # An existing destination is never replaced, even if it appeared mid-build.
        if output.exists() or output.is_symlink():
            raise BuildError('output appeared while building')
        os.rename(work, output)
        return document
    finally:
        if work.exists():
            shutil.rmtree(work)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--library', type=Path, required=True, help='already admitted public library')
    parser.add_argument('--out', type=Path, required=True, help='new output directory')
    parser.add_argument('--fade-frames', type=int, default=2)
    parser.add_argument('--audio-mode', choices=('forward', 'reverse'), default='forward')
    parser.add_argument('--jobs', type=int, default=2, help='bounded concurrent encoders (1..8)')
    args = parser.parse_args(argv)
    try:
        document = build_library(args.library, args.out, fade_frames=args.fade_frames, audio_mode=args.audio_mode, jobs=args.jobs)
    except (BuildError, OSError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(f'verified library: {len(document["clips"])} forward clips and boomerang variants')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
