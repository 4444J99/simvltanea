#!/usr/bin/env python3
"""Regenerate Audio v1.1 engineering examples; no historical media is used."""
from __future__ import annotations

import copy
from pathlib import Path
import subprocess

import composition as c
from artifact001_layouts import build_artifact001
from browser_runtime import build_preview

ROOT = Path(__file__).resolve().parent.parent / 'runtime-proof' / 'audio-v1.1'


def prepare() -> list[Path]:
    (ROOT / 'media').mkdir(parents=True, exist_ok=True)
    sources = {}
    for index, (color, frequency) in enumerate((('navy', 440), ('maroon', 660)), 1):
        target = ROOT / 'media' / f'synthetic-loop-{index}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            f'color=c={color}:s=160x160:r=24:d=4', '-f', 'lavfi', '-i',
            f'sine=frequency={frequency}:sample_rate=48000:duration=4',
            '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(target)], check=True)
        sources[f'fixtures/loop-{index}.mp4'] = dict(id=f'source-{index}',
            path=target.relative_to(ROOT).as_posix(), sha256=c.sha256_file(target),
            kind='video', duration='4')
    soundtrack = ROOT / 'media' / 'synthetic-soundtrack.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'sine=frequency=220:sample_rate=48000:duration=2',
        '-c:a', 'pcm_s16le', str(soundtrack)], check=True)
    state = c.from_authoring_model(build_artifact001(2), sources, frames=144, fps=24)
    state['schema_version'] = c.AUDIO_SCHEMA_VERSION
    state['engine_version'] = c.AUDIO_ENGINE_VERSION
    state['events'] = [dict(op='hold', frame=48, loop='loop-1', value=True),
                       dict(op='hold', frame=72, loop='loop-1', value=False)]
    configurations = {
        'soundtrack': dict(mode='soundtrack', source=soundtrack.relative_to(ROOT).as_posix(),
            sha256=c.sha256_file(soundtrack), duration='2', volume=.8, loop=True,
            fade_in_seconds=.3, fade_out_seconds=.5),
        'spatial-loops': dict(mode='spatial_loops', master_volume=.7, spatial_panning=True,
            per_loop={'loop-1': {'gain': 1, 'mute_on_hold': True},
                      'loop-2': {'gain': .8, 'mute_on_hold': True}}),
    }
    paths = []
    for name, audio in configurations.items():
        example = copy.deepcopy(state)
        example['audio'] = audio
        path = ROOT / f'{name}.json'
        c.save_state(example, path)
        build_preview(path, ROOT / f'preview-{name}')
        paths.append(path)
    return paths


if __name__ == '__main__':
    for state in prepare():
        print(state.relative_to(ROOT.parent.parent))
