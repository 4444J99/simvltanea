#!/usr/bin/env python3
"""Decode the labeled synthetic family and check visible identity and motion.

This is a fixture-specific pixel verifier, not OCR, historical-media analysis,
proof of frame-exact browser timing, or a substitute for visual inspection.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
import composition as c

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'runtime-proof'
CHECK_FRAMES = (12, 48, 120)


def decode_frames(path: Path, width: int, height: int) -> list[Image.Image]:
    select = '+'.join(f'eq(n\\,{frame})' for frame in CHECK_FRAMES)
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vf',
                             f'select={select}', '-fps_mode', 'passthrough',
                             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                            check=True, capture_output=True)
    size = width * height * 3
    c.require(len(result.stdout) == size * len(CHECK_FRAMES), 'decoded frame count mismatch')
    return [Image.frombytes('RGB', (width, height), result.stdout[i:i + size])
            for i in range(0, len(result.stdout), size)]


def background(path: Path) -> tuple[int, ...]:
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v',
                             '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                            check=True, capture_output=True)
    with Image.open(io.BytesIO(result.stdout)) as image:
        c.require(image.size == (320, 320), 'verifier requires the labeled square fixture')
        return tuple(ImageStat.Stat(image.convert('RGB').crop((20, 20, 100, 60))).median)


def check_pixels(image: Image.Image, placement, expected: str,
                 palette: dict[str, tuple[int, ...]]) -> dict:
    c.require(placement.fit == 'contain', 'verifier requires the labeled contain-study family')
    side = min(placement.width, placement.height)
    x = placement.x + (placement.width - side) // 2
    y = placement.y + (placement.height - side) // 2
    margin = max(2, round(side * .1))
    crop = image.crop((x + margin, y + margin, x + side - margin, y + side - margin))
    median = tuple(ImageStat.Stat(crop).median)
    distances = {source: sum((a - b) ** 2 for a, b in zip(median, color)) ** .5
                 for source, color in palette.items()}
    matched = min(distances, key=distances.get)
    c.require(matched == expected and distances[matched] <= 12,
              f'visible source mismatch for {placement.name}: expected {expected}, matched {matched}')
    return dict(visible_source=matched, median_rgb=median, color_distance=distances[matched],
                pixel_box=[x + margin, y + margin, x + side - margin, y + side - margin])


def check_motion(before: Image.Image, after: Image.Image) -> dict:
    c.require(before.size == after.size, 'motion regions must share dimensions')
    difference = ImageChops.difference(before, after)
    red, green, blue = difference.split()
    peak = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = sum(peak.histogram()[21:])
    fraction = changed / (before.width * before.height)
    c.require(fraction > .01, 'fixture region did not demonstrate motion above the noise threshold')
    return dict(changed_pixel_fraction=fraction, noise_threshold=20, minimum_fraction=.01)


def verify_family() -> dict:
    records = json.loads((ROOT / 'evidence/render-family.json').read_text())
    palette = {f'source-{i}': background(ROOT / f'media/source-{i}.mp4') for i in range(1, 8)}
    results = []
    negative_checks = 0
    observations = 0
    for record in records:
        count, orientation = record['count'], record['orientation']
        state = c.load_state(ROOT / f'state-{count}.json')
        video = ROOT / record['output']
        c.require(c.sha256_file(video) == record['sha256'], 'render bytes differ from execution receipt')
        facts = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
            'stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration', '-of', 'json', str(video)],
            capture_output=True, text=True, check=True).stdout)
        stream = facts['streams'][0]
        c.require(len(facts['streams']) == 1 and stream['codec_type'] == 'video', 'silent-video boundary failed')
        c.require(stream['nb_frames'] == '144' and stream['r_frame_rate'] == '24/1'
                  and facts['format']['duration'] == '6.000000', 'timing facts differ from fixture')
        width, height = stream['width'], stream['height']
        images = decode_frames(video, width, height)
        frame_records = []
        previous = {}
        for frame, image in zip(CHECK_FRAMES, images):
            resolved = c.resolve_at(state, frame)
            loops = {loop['id']: loop for loop in resolved['loops']}
            placements = c.pixel_placements(resolved['layouts'][orientation], width, height)
            c.require(len(placements) == count == len(loops), 'loop/placement count mismatch')
            visible = []
            for placement in placements:
                expected = loops[placement.name]['source']
                observed = check_pixels(image, placement, expected, palette)
                crop = image.crop(observed['pixel_box'])
                if placement.name in previous:
                    observed['motion'] = check_motion(previous[placement.name], crop)
                previous[placement.name] = crop
                observed.update(loop=placement.name,
                                model_source_offset=loops[placement.name]['source_offset'])
                visible.append(observed)
                observations += 1
            c.require(len({x['visible_source'] for x in visible}) == count, 'duplicated visible source')
            frame_records.append(dict(frame=frame, loops=visible))
        # Real negative controls ensure the verifier does not pass a blank image,
        # mislabeled source assignment, or repeated frozen frame.
        placement = c.pixel_placements(state['layouts'][orientation], width, height)[0]
        expected = c.resolve_at(state, CHECK_FRAMES[0])['loops'][0]['source']
        for blank, wanted in [(Image.new('RGB', images[0].size), expected),
                              (images[0], next(s for s in palette if s != expected))]:
            try:
                check_pixels(blank, placement, wanted, palette)
            except c.StateError:
                negative_checks += 1
            else:
                raise AssertionError('negative visible-source control passed unexpectedly')
        try:
            check_motion(images[0], images[0])
        except c.StateError:
            negative_checks += 1
        else:
            raise AssertionError('negative frozen-frame control passed unexpectedly')
        results.append(dict(count=count, orientation=orientation, sha256=record['sha256'], frames=frame_records))
    report = dict(status='passed', exports=len(results), sampled_frames=len(results) * len(CHECK_FRAMES),
                  visible_loop_observations=observations, rejected_negative_controls=negative_checks,
                  boundary='Fixture-specific visible color identity and motion; not OCR or frame-exact timing.',
                  exports_checked=results)
    (ROOT / 'evidence/decoded-pixel-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    result = verify_family()
    print(json.dumps({k: v for k, v in result.items() if k != 'exports_checked'}, indent=2))
