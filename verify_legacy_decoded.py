#!/usr/bin/env python3
"""Re-render five synthetic original/current pairs and compare decoded streams.

The preserved original's Git blob is pinned. No archive media or historical
fidelity is tested. Original and current share the same synthetic inputs and
FFmpeg toolchain. Generated outputs stay inside the ignored runtime-proof lane.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import composition as c
from make_artifact_001 import prepare, probe

HERE = Path(__file__).resolve().parent
BASELINE = HERE / 'artifact-001/baseline/render_triptych.original.py'
BASELINE_BLOB = '6155fa1b8c9d5284c3deda0eaf56b342e47cf1bc'
CASES = (('clip', 'none'), ('clip', 'panel'), ('clip', 'mix'),
         ('fixed', 'none'), ('fixed', 'mix'))


def decoded_hash(path: Path, kind: str) -> str:
    command = ['ffmpeg', '-v', 'error', '-i', str(path)]
    if kind == 'video':
        command += ['-map', '0:v:0', '-an', '-pix_fmt', 'rgb24']
    elif kind == 'audio':
        command += ['-map', '0:a:0', '-vn', '-acodec', 'pcm_s16le', '-ar', '48000', '-ac', '2']
    else:
        raise ValueError('Unknown decoded stream kind')
    command += ['-f', 'hash', '-hash', 'sha256', '-']
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          timeout=120).stdout.strip()


def verify() -> dict:
    data = BASELINE.read_bytes()
    actual = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
    c.require(actual == BASELINE_BLOB, 'preserved original differs from pinned Git blob')
    prepare(HERE/'artifact-001')
    output = HERE/'runtime-proof/legacy-regression'
    output.mkdir(parents=True, exist_ok=False)
    # Preserve the original bytes and its script-local output guard unchanged.
    # A byte-identical execution copy makes that guard own this generated lane.
    staged_original = output / 'render_triptych.original.py'
    shutil.copyfile(BASELINE, staged_original)
    c.require(staged_original.read_bytes() == data, 'staged original bytes changed')
    receipt = dict(kind='synthetic-decoded-regression', baseline_git_blob=actual,
                   ffmpeg=subprocess.run(['ffmpeg','-version'], capture_output=True,
                                         text=True, check=True).stdout.splitlines()[0],
                   cases=[], status='running')
    receipt_path = output/'receipt.json'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    for timing, audio in CASES:
        pair = []
        for version, script in (('original', staged_original), ('current', HERE/'render_triptych.py')):
            name=f'{timing}-{audio}-{version}'
            target=output/f'{name}.mp4'
            command=[sys.executable, str(script.relative_to(HERE)),
                     '--manifest', 'artifact-001/baseline-manifest.json',
                     '--timing',timing,'--phrase','1','--audio',audio,
                     '--output',str(target.relative_to(HERE)),
                     '--work-dir',str((output/f'work-{name}').relative_to(HERE))]
            with (output/f'{name}.log').open('w') as log:
                subprocess.run(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,
                               check=True,timeout=120)
            facts=probe(target)
            has_audio=any(stream['codec_type']=='audio' for stream in facts['streams'])
            c.require(has_audio == (audio!='none'), 'audio stream boundary changed')
            pair.append(dict(version=version,command=command,returncode=0,
                             output=target.name,sha256=c.sha256_file(target),facts=facts,
                             video_sha256=decoded_hash(target,'video'),
                             audio_sha256=decoded_hash(target,'audio') if has_audio else None))
        for key in ('video_sha256','audio_sha256'):
            c.require(pair[0][key] == pair[1][key], f'legacy decoded {key} changed: {timing}/{audio}')
        receipt['cases'].append(dict(timing=timing,audio=audio,decoded_equal=True,pair=pair))
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        print(f'{timing}/{audio}: decoded video and applicable audio equal',flush=True)
    receipt['status']='passed'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    verify()
