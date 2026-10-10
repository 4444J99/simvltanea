"""Build a bounded, local TMB atlas composition with SIMVLTANEA spatial audio."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from simvltanea.authoring import (
    Composition, SpatialLoopsAudio, build_artifact001, composition as c,
    composition_model,
)
from simvltanea.browser import browser_runtime, build_preview
from simvltanea.paths import LAYOUT, REPO_ROOT

# Accepted source observations, separately pinned from the executable engine.
SOURCE_REVISION = '44d815c978fc9b57526ff9b18165cd5b8d777b5c'
ATLAS_REVISION = 'cbce79dcbcf34ce214ba77cd2aa8d8bb9ed32fa5'
MEDIA = Path('synchronized-generation-calibration/media')
GENERATIONS = ('G01', 'G02')
DURATION = Fraction(8)
FPS = 24
SOURCE_FRAMES = 192
EDITION_FRAMES = 384
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def run(command: list[str], *, binary: bool = False) -> bytes | str:
    result = subprocess.run(command, check=True, capture_output=True,
                            text=not binary, timeout=30,
                            env={k: v for k, v in os.environ.items()
                                 if not k.startswith('GIT_')})
    return result.stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_revision(root: Path, revision: str) -> None:
    c.require(bool(re.fullmatch(r'[0-9a-f]{40}', revision)),
              'source revision must be a full pinned Git commit')
    run(['git', '-C', str(root), 'merge-base', '--is-ancestor', revision, 'HEAD'])


def verify_blob(root: Path, relative: Path, revision: str) -> dict:
    """Authenticate current bytes against an explicit accepted Git tree."""
    path = root / relative
    c.require(path.is_file() and not path.is_symlink(), f'missing regular source: {relative}')
    c.require(path.resolve().is_relative_to(root.resolve()), 'source escapes TMB root')
    c.require(path.stat().st_size <= MAX_SOURCE_BYTES, 'source exceeds bounded import size')
    blob = run(['git', '-C', str(root), 'show', f'{revision}:{relative.as_posix()}'], binary=True)
    expected = hashlib.sha256(blob).hexdigest()
    c.require(digest(path) == expected, f'source hash differs from pinned Git tree: {relative}')
    return dict(path=relative.as_posix(), sha256=expected, revision=revision,
                bytes=path.stat().st_size)


def probe(path: Path) -> dict:
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))


def validate_streams(facts: dict, kind: str) -> dict:
    streams = facts.get('streams', [])
    c.require(len(streams) == 1 and streams[0].get('codec_type') == kind,
              f'expected one isolated {kind} stream')
    stream = streams[0]
    c.require(Fraction(stream.get('duration', '0')) == DURATION,
              f'{kind} duration must be exactly eight seconds')
    c.require(Fraction(stream.get('start_time', '0')) == 0,
              f'{kind} stream must start at zero')
    if kind == 'video':
        c.require(stream.get('codec_name') == 'h264' and stream.get('pix_fmt') == 'yuv420p',
                  'atlas must be 8-bit H.264')
        c.require((stream.get('width'), stream.get('height')) == (768, 528),
                  'atlas must preserve the accepted four-view 768x528 geometry')
        c.require(Fraction(stream.get('avg_frame_rate', '0')) == FPS and
                  int(stream.get('nb_frames', 0)) == SOURCE_FRAMES,
                  'atlas must contain 192 frames at 24 fps')
    else:
        c.require(stream.get('codec_name') == 'aac' and stream.get('channels') == 2 and
                  int(stream.get('sample_rate', 0)) == 48000,
                  'F6 excerpt must be stereo AAC at 48 kHz')
    return stream


def admit_sources(root: Path, source_revision: str, atlas_revision: str) -> dict:
    verify_revision(root, source_revision)
    verify_revision(root, atlas_revision)
    manifest_file = MEDIA / 'audio-manifest.json'
    manifest_identity = verify_blob(root, manifest_file, source_revision)
    manifest_bytes = (root / manifest_file).read_bytes()
    c.require(hashlib.sha256(manifest_bytes).hexdigest() == manifest_identity['sha256'],
              'audio manifest changed after admission')
    manifest = json.loads(manifest_bytes)
    c.require(manifest.get('schema') == 'synchronized-generation-audio/0.1',
              'unsupported TMB audio manifest')
    sources = []
    for index, generation in enumerate(GENERATIONS, 1):
        stem = f'generation-{index:02d}'
        video = MEDIA / f'{stem}.mp4'
        audio = MEDIA / f'{stem}.audio.m4a'
        video_identity = verify_blob(root, video, atlas_revision)
        entry = manifest.get('generations', {}).get(generation, {})
        path = root / audio
        c.require(path.is_file() and not path.is_symlink(), f'missing regular source: {audio}')
        c.require(path.resolve().is_relative_to(root.resolve()), 'audio escapes TMB root')
        c.require(path.stat().st_size <= MAX_SOURCE_BYTES, 'audio exceeds bounded import size')
        c.require(digest(path) == entry.get('sha256'), f'audio hash mismatch: {generation}')
        c.require(path.stat().st_size == entry.get('size_bytes'), f'audio size mismatch: {generation}')
        c.require(entry.get('generation') == generation and entry.get('codec') == 'aac' and
                  entry.get('channels') == 2 and entry.get('sample_rate') == 48000 and
                  entry.get('duration_seconds') == 8 and
                  entry.get('shared_start') == 510 + (index - 1) * 8 and
                  entry.get('shared_end') == 518 + (index - 1) * 8,
                  f'audio timing or format does not match accepted generation: {generation}')
        validate_streams(probe(root / video), 'video')
        validate_streams(probe(path), 'audio')
        sources.append(dict(generation=generation, video=video_identity,
                            audio=dict(path=audio.as_posix(), sha256=entry['sha256'],
                                       bytes=entry['size_bytes']),
                            shared_start=entry['shared_start'], shared_end=entry['shared_end']))
    return dict(source_revision=source_revision, atlas_revision=atlas_revision,
                observed_head=run(['git', '-C', str(root), 'rev-parse', 'HEAD']).strip(),
                audio_manifest=manifest_identity, generations=sources,
                audio_provenance=dict(recording='F6 stereo room recording',
                                      channels=2, sample_rate=48000,
                                      upstream_gain_db=manifest.get('gain_applied_db'),
                                      rendering='SIMVLTANEA stereo spatial panning',
                                      ambisonic_recording=False))


def packet_digest(path: Path, stream: str) -> str:
    """Hash encoded packets independently of container metadata."""
    return run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-map', stream,
                '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).strip()


def mux_generation(root: Path, source: dict, output: Path) -> dict:
    video = root / source['video']['path']
    audio = root / source['audio']['path']
    # Recheck after admission so changed input cannot inherit a stale receipt.
    c.require(digest(video) == source['video']['sha256'] and
              digest(audio) == source['audio']['sha256'], 'source changed after admission')
    run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(video), '-i', str(audio),
         '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-movflags', '+faststart', str(output)])
    video_hash, audio_hash = packet_digest(output, '0:v:0'), packet_digest(output, '0:a:0')
    c.require(video_hash == packet_digest(video, '0:v:0'), 'mux changed encoded video packets')
    c.require(audio_hash == packet_digest(audio, '0:a:0'), 'mux changed encoded audio packets')
    c.require(digest(video) == source['video']['sha256'] and
              digest(audio) == source['audio']['sha256'], 'source changed during mux')
    return dict(path=f'media/{output.name}', sha256=digest(output),
                video_packet_hash=video_hash, audio_packet_hash=audio_hash,
                operation='stream copy; no reencoding')


def composition_state(media: list[dict]) -> tuple[Composition, dict]:
    c.require(len(media) == 2 and media[0]['sha256'] != media[1]['sha256'],
              'composition requires two distinct generations')
    authored = build_artifact001(2)
    loops = tuple(replace(loop, source=media[index]['path'], rate=1.0, offset=float(index),
                          trim_in=0.0, trim_out=8.0)
                  for index, loop in enumerate(authored.loops))
    layouts = tuple(replace(layout, placements=tuple(replace(cell, fit='contain')
                                                   for cell in layout.placements))
                    for layout in authored.layouts)
    authored = replace(authored, id='tmb-simvltanea-spatial-composition', loops=loops,
                       layouts=layouts, schema_version=composition_model.AUDIO_SCHEMA_VERSION,
                       audio=SpatialLoopsAudio(master_volume='7/10', spatial_panning=True,
                           per_loop={'loop-1': composition_model.LoopAudio(gain='4/5'),
                                     'loop-2': composition_model.LoopAudio(gain='3/5')}))
    bindings = {item['path']: dict(id=f'generation-{index:02d}', path=item['path'],
                                  sha256=item['sha256'], duration='8', kind='video')
                for index, item in enumerate(media, 1)}
    return authored, c.from_authoring_model(authored, bindings, frames=EDITION_FRAMES, fps=FPS)


def validate_output(output: Path) -> Path:
    c.require(not output.exists() and not output.is_symlink(), 'output destination already occupied')
    output = output.resolve()
    proofs = LAYOUT.path('proofs').resolve()
    c.require(output.is_relative_to(proofs) and output != proofs,
              'output must be a fresh child of the ignored proof lane')
    return output


def write_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def preview_digests(root: Path) -> dict[str, str]:
    """Record every served file, including runtime, state, adapters and media."""
    result = {}
    for path in sorted(root.rglob('*')):
        c.require(not path.is_symlink(), 'preview contains a symbolic link')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    c.require(bool(result), 'preview has no files to authenticate')
    return result


def build(tmb_root: Path, output: Path, source_revision: str = SOURCE_REVISION,
          atlas_revision: str = ATLAS_REVISION) -> dict:
    output = validate_output(output)
    tmb_root = tmb_root.resolve()
    engine = browser_runtime.resolve_shared_engine()
    c.require(engine.release_status == 'accepted', 'composition requires an accepted engine release')
    c.require(engine.root.resolve() == tmb_root, 'TMB sources and accepted engine must share one owner')
    admission = admit_sources(tmb_root, source_revision, atlas_revision)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'media').mkdir()
    receipt = dict(schema='tmb-simvltanea-edition/v1', status='building',
                   created_at=datetime.now(timezone.utc).isoformat(), source=admission,
                   engine=dict(engine.describe(), accepted_commit=engine.pin['release']['commit'],
                               observed_head=engine.git_commit),
                   consumer_revision=run(['git', '-C', str(REPO_ROOT), 'rev-parse', 'HEAD']).strip(),
                   recipe=dict(path='tools/editions/build_tmb_composition.py',
                               sha256=digest(Path(__file__))),
                   scope='local engineering edition; artistic approval and device acceptance pending')
    write_json(output / 'source-admission.json', admission)
    media = [mux_generation(tmb_root, source, output / 'media' / f'generation-{index:02d}.mp4')
             for index, source in enumerate(admission['generations'], 1)]
    authored, state = composition_state(media)
    write_json(output / 'authoring.json', json.loads(authored.to_json()))
    write_json(output / 'composition.json', state)
    plan = build_preview(output / 'composition.json', output / 'preview')
    receipt.update(status='built; browser acceptance pending', media=media,
                   composition=dict(path='composition.json', sha256=digest(output / 'composition.json'),
                                    schema_version=state['schema_version'], frames=state['frames'],
                                    fps=FPS, phase_offsets_seconds=[0, 1],
                                    atlas_views='four aligned source views per atomic generation'),
                   preview=dict(path='preview/index.html', state_sha256=plan['state_sha256'],
                                files=preview_digests(output / 'preview')))
    write_json(output / 'edition-receipt.json', receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tmb-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-revision', default=SOURCE_REVISION)
    parser.add_argument('--atlas-revision', default=ATLAS_REVISION)
    args = parser.parse_args()
    receipt = build(args.tmb_root, args.output, args.source_revision, args.atlas_revision)
    print(json.dumps(dict(status=receipt['status'], output=str(args.output), loops=2)))


if __name__ == '__main__':
    main()
