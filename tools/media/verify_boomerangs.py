#!/usr/bin/env python3
"""Verify every prepared public-library loop and write a measured JSON receipt.

Run: python3 -m tools.media.verify_boomerangs --library var/site/loops --receipt var/proofs/loops.json
This checks encoded frame PTS and MP4 presentation durations; it does not claim
that padded AAC decoder frames or mobile playback are automatically gapless.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

from tools.media.build_boomerangs import BuildError, verify_encoded
from tools.publishing.stage_library_site import LibrarySiteError, check_library


def verify_library(library: Path, *, jobs: int = 2) -> dict:
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise BuildError('jobs must be an integer between one and eight')
    library = Path(library)
    try:
        clips = check_library(library)
    except LibrarySiteError as error:
        raise BuildError(str(error)) from error
    if any('boomerang' not in clip.get('variants', {}) for clip in clips):
        raise BuildError('every logical clip must have a boomerang variant')

    def inspect(clip):
        variant = clip['variants']['boomerang']
        measured = verify_encoded(library / variant['file'], variant['frame_count'])
        if abs(measured['duration_seconds'] - variant['duration_seconds']) >= .001:
            raise BuildError('manifest duration differs from encoded presentation duration')
        return {'logical_id': clip['id'], 'variant_id': variant['id'], 'file': variant['file'],
                'bytes': variant['bytes'], **measured}

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        assets = list(executor.map(inspect, clips))
    return {'status': 'PASS', 'logical_clips': len(clips),
            'variants': len({asset['variant_id'] for asset in assets}),
            'max_av_delta_seconds': max(asset['av_delta_seconds'] for asset in assets),
            'manifest_sha256': hashlib.sha256((library / 'manifest.json').read_bytes()).hexdigest(),
            'scope': 'Content hashes, exact CFR frame PTS/count, MP4 video/audio presentation durations.',
            'assets': assets}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if args.receipt:
            receipt = args.receipt.resolve()
            library = args.library.resolve()
            if receipt == library or library in receipt.parents:
                raise BuildError('receipt must live outside the admitted library')
        document = verify_library(args.library, jobs=args.jobs)
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(document, indent=1, allow_nan=False) + '\n')
    except (BuildError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 2
    print(f'PASS: {document["logical_clips"]} logical clips, {document["variants"]} variants, '
          f'max A/V presentation delta {document["max_av_delta_seconds"] * 1000:.6f} ms')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
