#!/usr/bin/env python3
"""Generate labeled original synthetic media, paired data and an experimental N=7.

The seven-loop pair is an explicitly authored engineering experiment, NOT a
reviewed extension of artifact001_layouts.AUTHORED and NOT recovered historical art.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import composition as c
from artifact001_layouts import build_artifact001
from browser_runtime import build_preview

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'runtime-proof'
# Two deliberately specified compositions, not a generated generic grid.
SEVEN = {
    'portrait': [('4/100','3/100','92/100','30/100'),
                 ('4/100','37/100','44/100','18/100'),('52/100','37/100','44/100','18/100'),
                 ('4/100','58/100','28/100','17/100'),('36/100','58/100','28/100','17/100'),
                 ('68/100','58/100','28/100','17/100'),('4/100','79/100','92/100','18/100')],
    'landscape': [('3/100','5/100','38/100','90/100'),
                  ('45/100','5/100','24/100','26/100'),('73/100','5/100','24/100','26/100'),
                  ('45/100','36/100','24/100','28/100'),('73/100','36/100','24/100','28/100'),
                  ('45/100','69/100','24/100','26/100'),('73/100','69/100','24/100','26/100')],
}


def prepare(root: Path = ROOT) -> list[Path]:
    root = root.resolve()
    c.require(root.is_relative_to(HERE), 'fixture output must remain inside incubator')
    (root / 'media').mkdir(parents=True, exist_ok=True)
    (root / 'evidence').mkdir(exist_ok=True)
    (root / 'renders').mkdir(exist_ok=True)
    sources, commands = [], []
    font = ImageFont.truetype('DejaVuSans-Bold.ttf', 32)
    small = ImageFont.truetype('DejaVuSans.ttf', 22)
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
    for count in (3,4,5,6,7):
        if count < 7:
            authored = build_artifact001(count)
            state = c.from_authoring_model(authored,{f'fixtures/loop-{i+1}.mp4':sources[i] for i in range(count)})
            for layout in state['layouts'].values():
                layout['name'] += '-labeled-contain-study'
                for cell in layout['cells']: cell['fit']='contain'
        else:
            state = copy.deepcopy(c.load_state(states[-1]))
            state['sources']=copy.deepcopy(sources)
            state['loops'].append(dict(id='loop-7',bank=['source-7'],offset='93/50',rate='71/50',period='8',epoch=0,held=False))
            state['layouts']={orientation:dict(name=f'experimental-seven-{orientation}',cells=[
                dict(loop=f'loop-{i+1}',rect=list(rect),fit='contain',focal=['1/2','1/2'])
                for i,rect in enumerate(rects)]) for orientation,rects in SEVEN.items()}
        path=root/f'state-{count}.json';c.save_state(state,path);states.append(path)
        build_preview(path,root/f'preview-{count}')
    control=copy.deepcopy(c.load_state(states[0]))
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
    wrap=copy.deepcopy(c.load_state(states[0]));wrap['loops'][0]['trim']=['1','2']
    c.save_state(wrap,root/'state-trim.json');build_preview(root/'state-trim.json',root/'preview-trim')
    (root/'sources.json').write_text(json.dumps(dict(kind='original-synthetic',sources=sources,commands=commands),indent=2)+'\n')
    return states


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    prepare()
