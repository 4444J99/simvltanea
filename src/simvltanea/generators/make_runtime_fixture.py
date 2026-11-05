#!/usr/bin/env python3
"""Generate labeled original synthetic media and paired data.

Authored pairs cover N=2 through N=7 (unchanged). Strips fixtures cover N=1, 5, 8
and 12 in both orientations with ramp media whose rows are distinguishable: red is a
vertical ramp over the source rows, green a horizontal ramp over the source columns,
and blue a per-clip tint. No ramp pixel is near black, so an empty (background)
pixel in an export or a screenshot is unambiguous.
"""
from __future__ import annotations

import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import copy
import json
import math
import subprocess
from fractions import Fraction

from PIL import Image, ImageDraw, ImageFont
from simvltanea.authoring import composition as c
from simvltanea.authoring import build_artifact001, build_strips
from simvltanea.browser import HERE, build_preview
from simvltanea.paths import PROOFS_DIR, REPO_ROOT, require_in_var

ROOT = PROOFS_DIR
# Strips fixtures: counts, ramp media geometry and the styled preset at the style maxima.
STRIPS_COUNTS = (1, 5, 8, 12)
RAMP_SIZE = (540, 720)  # 3:4, the clip shape measured in the layout presets spec
RAMP_LOW, RAMP_SPAN = 32, 192  # red/green ramps run 32..223; blue tints run 80..234
STYLED_STRIPS_PRESET = {"format": "simvltanea.layout-preset/1", "name": "strips-styled", "family": "strips",
                        "style": {"corner_radius": "1/20", "lateral_jitter": "1/20"}}


def ramp_tint(index: int) -> int:
    """Blue tint of strip clip ``index`` (0-based); distinct per clip and never near black."""
    return 80 + 14 * index


def ramp_level(position: int, extent: int) -> int:
    """Ramp value of row (or column) ``position`` out of ``extent``, rounded half up."""
    return RAMP_LOW + (2 * (RAMP_SPAN - 1) * position + extent - 1) // (2 * (extent - 1))


def ramp_row(value: float, extent: int = RAMP_SIZE[1]) -> float:
    """Inverse ramp: the source row (red) or column (green, ``extent=540``) carrying ``value``."""
    return (value - RAMP_LOW) * (extent - 1) / (RAMP_SPAN - 1)


def ramp_frame(index: int) -> Image.Image:
    width, height = RAMP_SIZE
    red = Image.new('L', (width, height))
    red.putdata([ramp_level(y, height) for y in range(height) for _ in range(width)])
    green = Image.new('L', (width, height))
    green.putdata([ramp_level(x, width) for _ in range(height) for x in range(width)])
    return Image.merge('RGB', (red, green, Image.new('L', (width, height), ramp_tint(index))))


def ramp_sources(root: Path, commands_out: list[list[str]] | None = None) -> list[dict]:
    """Write (or reuse) the twelve ramp clips under ``root/media``; return hashed sources."""
    root = root.resolve()
    c.require(require_in_var(root, 'fixture output') == root, 'fixture output must remain inside var')
    (root / 'media').mkdir(parents=True, exist_ok=True)
    ramps = []
    width, height = RAMP_SIZE
    for index in range(max(STRIPS_COUNTS)):
        target = root / 'media' / f'strip-{index + 1}.mp4'
        command = ['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                   '-s',f'{width}x{height}','-r','24','-i','-','-an','-c:v','libx264',
                   '-preset','ultrafast','-crf','12','-threads','1','-pix_fmt','yuv420p',
                   # Tag the BT.601 matrix FFmpeg converts with, so browsers decode the ramps alike.
                   '-colorspace','smpte170m','-color_primaries','smpte170m','-color_trc','smpte170m',
                   '-color_range','tv',str(target)]
        if not target.exists():
            frame = ramp_frame(index).tobytes()
            process = subprocess.Popen(command, stdin=subprocess.PIPE)
            try:
                for _ in range(192):
                    process.stdin.write(frame)
            finally:
                process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError('Synthetic ramp encoding failed')
        ramps.append(dict(id=f'strip-{index + 1}', path=f'media/strip-{index + 1}.mp4',
                          sha256=c.sha256_file(target), kind='video', duration='8'))
        if commands_out is not None:
            commands_out.append(command[:-1] + [str(target.relative_to(root))])
    return ramps


def prepare_strips(root: Path, sources_out: list[dict], commands_out: list[list[str]]) -> list[Path]:
    """Write ramp media and strips states (default and styled) for STRIPS_COUNTS."""
    ramps = ramp_sources(root, commands_out)
    sources_out.extend(ramps)
    paths = []
    for count in STRIPS_COUNTS:
        for suffix, preset in (('', 'strips'), ('-styled', STYLED_STRIPS_PRESET)):
            state = build_strips(count, preset, sources=ramps[:count])
            path = root / f'state-strips-{count}{suffix}.json'
            c.save_state(state, path)
            build_preview(path, root / f'preview-strips-{count}{suffix}')
            paths.append(path)
    return paths


def _get_font(name: str, size: int):
    candidates = [name, 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc', 'Arial.ttf']
    for cand in candidates:
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            pass
    return ImageFont.load_default()


def prepare(root: Path = ROOT, slice_width: float = 0.5, slice_height: float = 0.66, seam_width: float = 0.036, seam_mode: str = "feather", seam_sigma: float = 0.005) -> list[Path]:
    root = root.resolve()
    c.require(require_in_var(root, 'fixture output') == root, 'fixture output must remain inside var')
    # Allow all knobs via args (configurable)
    _slice_w = str(Fraction(str(slice_width)).limit_denominator(1000))
    _slice_h = str(Fraction(str(slice_height)).limit_denominator(1000))
    _seam_w = str(Fraction(str(seam_width)).limit_denominator(1000))
    _seam_s = str(Fraction(str(seam_sigma)).limit_denominator(1000))
    (root / 'media').mkdir(parents=True, exist_ok=True)
    (root / 'evidence').mkdir(exist_ok=True)
    (root / 'renders').mkdir(exist_ok=True)
    sources, commands = [], []
    font = _get_font('DejaVuSans-Bold.ttf', 32)
    small = _get_font('DejaVuSans.ttf', 22)
    colors = [(170,45,45),(32,125,70),(35,80,170),(120,50,155),
              (170,110,25),(25,130,145),(145,45,100)]
    for i, color in enumerate(colors, 1):
        target = root / 'media' / f'source-{i}.mp4'
        command = ['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                   '-s','320x320','-r','24','-i','-','-an','-c:v','libx264',
                   '-preset','ultrafast','-crf','18','-threads','1','-pix_fmt','yuv420p',str(target)]
        if not target.exists():
            process = subprocess.Popen(command, stdin=subprocess.PIPE)
            try:
                for frame in range(192):
                    im = Image.new('RGB',(320,320),color);d=ImageDraw.Draw(im)
                    d.rectangle((6,6,313,313),outline='white',width=3)
                    d.line((160,10,160,70),fill='white',width=2)
                    d.text((160,112),f'S{i:02}',font=font,anchor='mm',fill='white')
                    d.text((160,160),f'F{frame:03}',font=font,anchor='mm',fill='white')
                    d.text((160,201),f'{frame/24:.2f}s',font=small,anchor='mm',fill='white')
                    x=25+270*frame/191;y=268+15*math.sin(frame/12+i)
                    d.ellipse((x-10,y-10,x+10,y+10),fill='white')
                    d.rectangle((18,295,18+284*frame/191,304),fill='white')
                    process.stdin.write(im.tobytes())
            finally:
                process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError('Synthetic media encoding failed')
        sources.append(dict(id=f'source-{i}',path=f'media/source-{i}.mp4',
                            sha256=c.sha256_file(target),kind='video',duration='8'))
        commands.append(command[:-1]+[str(target.relative_to(root))])
    states = []
    for count in (2,3,4,5,6,7):
        authored = build_artifact001(count)
        state = c.from_authoring_model(authored,{f'fixtures/loop-{i+1}.mp4':sources[i] for i in range(count)})
        for layout in state['layouts'].values():
            layout['name'] += '-labeled-contain-study'
            for cell in layout['cells']: cell['fit']='contain'
        path=root/f'state-{count}.json';c.save_state(state,path);states.append(path)
        build_preview(path,root/f'preview-{count}')
    # Seamed slice field: N=2 with deterministic random crops + seam blur/merge (all configurable via CLI)
    slice_state = copy.deepcopy(c.load_state(root / 'state-2.json'))
    slice_state['slice'] = {"enabled": True, "width": _slice_w, "height": _slice_h}
    slice_state['seam'] = {"enabled": True, "width": _seam_w, "mode": seam_mode, "sigma": _seam_s}
    # Opposing crops: width <1 ensures no full frame ever revealed; seam merges sides
    c.save_state(slice_state, root / 'state-slice.json')
    build_preview(root / 'state-slice.json', root / 'preview-slice')
    # Morph variant for N=3 (uses same slice width, half seam width for variety)
    slice3 = copy.deepcopy(c.load_state(root / 'state-3.json'))
    slice3['slice'] = {"enabled": True, "width": _slice_w, "height": "3/5"}
    slice3['seam'] = {"enabled": True, "width": _seam_w, "mode": "morph", "sigma": _seam_s}
    c.save_state(slice3, root / 'state-slice-3.json')
    build_preview(root / 'state-slice-3.json', root / 'preview-slice-3')
    control=copy.deepcopy(c.load_state(root / 'state-3.json'))
    control['seed']=2  # This fixture's reroll visibly changes loop-2's disjoint source bank.
    control['events']=[dict(op='hold',frame=24,loop='loop-1',value=True),
                       dict(op='hold',frame=48,loop='loop-1',value=False),
                       dict(op='reroll',frame=60,loop='loop-2'),
                       dict(op='swap',frame=84,a='loop-2',b='loop-3'),
                       dict(op='move',frame=108,loop='loop-1',orientation='portrait',rect=['1/10','3/100','4/5','21/50'])]
    # Reroll has a disjoint, two-source bank so it cannot duplicate another loop.
    control['sources'].append(copy.deepcopy(sources[3]))
    control['loops'][1]['bank']=['source-2','source-4']
    control_path=root/'state-controls.json';c.save_state(control,control_path)
    build_preview(control_path,root/'preview-controls')
    wrap=copy.deepcopy(c.load_state(root / 'state-3.json'));wrap['loops'][0]['trim']=['1','2']
    c.save_state(wrap,root/'state-trim.json');build_preview(root/'state-trim.json',root/'preview-trim')
    states += prepare_strips(root, sources, commands)
    (root/'sources.json').write_text(json.dumps(dict(kind='original-synthetic',sources=sources,commands=commands),indent=2)+'\n')
    return states


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice-width", type=float, default=0.5, help="Slice width fraction configurable (0..1)")
    parser.add_argument("--slice-height", type=float, default=0.66, help="Slice height fraction")
    parser.add_argument("--seam-width", type=float, default=0.036, help="Seam width fraction")
    parser.add_argument("--seam-mode", choices=("blur","feather","morph"), default="feather", help="Seam mode")
    parser.add_argument("--seam-sigma", type=float, default=0.005, help="Seam sigma")
    args=parser.parse_args()
    prepare(slice_width=args.slice_width, slice_height=args.slice_height, seam_width=args.seam_width, seam_mode=args.seam_mode, seam_sigma=args.seam_sigma)
