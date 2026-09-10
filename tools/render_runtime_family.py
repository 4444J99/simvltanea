#!/usr/bin/env python3
"""Render the labeled engineering family using the existing Triptych CLI.

This orchestration script does not implement a second rendering path.
Generated sources, exports and evidence stay in the ignored runtime-proof lane.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import composition as c
from make_artifact_001 import probe
from make_runtime_fixture import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'runtime-proof'


def render_family() -> list[dict]:
    prepare()
    receipts = []
    for count in (3, 4, 5, 6, 7):
        for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
            output = ROOT / 'renders' / f'labeled-{count}-{orientation}.mp4'
            command = ['python3', 'render_triptych.py', '--state', f'runtime-proof/state-{count}.json',
                       '--orientation', orientation, '--width', str(width), '--height', str(height),
                       '--preset', 'ultrafast', '--crf', '18', '--output', str(output.relative_to(HERE))]
            start = time.monotonic()
            with (ROOT / 'evidence' / f'render-{count}-{orientation}.log').open('w') as log:
                subprocess.run(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT, check=True)
            elapsed = time.monotonic() - start
            facts = probe(output)
            video = facts['streams'][0]
            c.require(len(facts['streams']) == 1, 'unexpected audio stream')
            c.require((video['width'], video['height'], video['nb_frames']) == (width, height, '144'),
                      'unexpected output dimensions or frame count')
            c.require(facts['format']['duration'] == '6.000000', 'unexpected output duration')
            stills = []
            for frame in (12, 48, 120):
                image = output.with_name(output.stem + f'-f{frame:03}.png')
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output), '-vf',
                                f'select=eq(n\\,{frame})', '-frames:v', '1', str(image)], check=True)
                stills.append(dict(frame=frame, path=str(image.relative_to(ROOT)), sha256=c.sha256_file(image)))
            receipts.append(dict(count=count, orientation=orientation, command=command, returncode=0,
                                 elapsed_seconds=elapsed, output=str(output.relative_to(ROOT)),
                                 sha256=c.sha256_file(output), facts=facts, stills=stills))
            (ROOT / 'evidence/render-family.json').write_text(json.dumps(receipts, indent=2) + '\n')
            print(count, orientation, c.sha256_file(output), flush=True)
    return receipts


def verify_portable_reproduction() -> list[dict]:
    receipts = []
    for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
        output = ROOT / 'renders' / f'portable-7-{orientation}.mp4'
        command = ['python3', 'render_triptych.py', '--state', 'runtime-proof/preview-7/state.json',
                   '--orientation', orientation, '--width', str(width), '--height', str(height),
                   '--preset', 'ultrafast', '--crf', '18', '--output', str(output.relative_to(HERE))]
        subprocess.run(command, cwd=HERE, check=True, capture_output=True, text=True)
        digest = c.sha256_file(output)
        reference = c.sha256_file(ROOT / 'renders' / f'labeled-7-{orientation}.mp4')
        c.require(digest == reference, 'portable state did not reproduce identical bytes')
        receipts.append(dict(command=command, orientation=orientation, sha256=digest,
                             reference_sha256=reference, byte_identical=True))
    (ROOT / 'evidence/portable-reproduction.json').write_text(json.dumps(receipts, indent=2) + '\n')
    return receipts


if __name__ == '__main__':
    render_family()
    verify_portable_reproduction()
