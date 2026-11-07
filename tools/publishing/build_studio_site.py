#!/usr/bin/env python3
"""Build the Pages site with the existing, pinned public clip library.

Run from the repository root with ``python3 -m tools.publishing.build_studio_site``.
Only staged Studio files and manifest-listed public clips enter ``var/site/deploy``.
The immutable deployment URL and manifest digest preserve the published library
without copying private source media or repository archives into the build.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

from tools.paths import SITE_DIR
from simvltanea.browser import stage_studio
from tools.publishing.stage_library_site import LibrarySiteError, stage_library_site, validate_manifest


LIBRARY_URL = 'https://7fec0066.loop-compositor-studio.pages.dev/library/'
MANIFEST_SHA256 = '8d9d65a9f77dc3362e4cfc3e3fd84fa5ff5fabf227299e446df92ab03359a5c8'
PAGES_MAX_BYTES = 25 * 1024 * 1024


def download(url: str, limit: int) -> bytes:
    """Read a bounded public asset using inherited proxy and TLS settings."""
    request = Request(url, headers={'User-Agent': 'simvltanea-pages-build/1'})
    with urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise LibrarySiteError('download exceeds its permitted file size')
    return data


def build_studio_site(output: Path, library_url: str = LIBRARY_URL,
                      manifest_sha256: str = MANIFEST_SHA256) -> int:
    """Validate and assemble a complete site; leave existing content untouched."""
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise LibrarySiteError('output must be absent or an empty directory')
    library_url = library_url.rstrip('/') + '/'
    manifest = download(library_url + 'manifest.json', PAGES_MAX_BYTES)
    if hashlib.sha256(manifest).hexdigest() != manifest_sha256:
        raise LibrarySiteError('library manifest SHA-256 does not match the pinned publication')
    clips = validate_manifest(json.loads(manifest))
    if any(clip['bytes'] > PAGES_MAX_BYTES for clip in clips):
        raise LibrarySiteError('library clip exceeds the Pages 25 MiB file limit')

    with tempfile.TemporaryDirectory(prefix='studio-pages-build-') as temporary:
        staging = Path(temporary)
        studio, library = staging / 'studio', staging / 'library'
        stage_studio(studio)
        if any(path.stat().st_size > PAGES_MAX_BYTES for path in studio.iterdir()):
            raise LibrarySiteError('studio file exceeds the Pages 25 MiB file limit')
        (library / 'clips').mkdir(parents=True)
        (library / 'manifest.json').write_bytes(manifest)

        def fetch_clip(clip: dict) -> None:
            data = download(library_url + clip['file'], clip['bytes'])
            if len(data) != clip['bytes']:
                raise LibrarySiteError('downloaded clip size does not match its manifest entry')
            (library / clip['file']).write_bytes(data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(fetch_clip, clips))
        # Existing staging checks every content hash before creating the output.
        return stage_library_site(studio, library, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, default=SITE_DIR / 'deploy')
    parser.add_argument('--library-url', default=LIBRARY_URL)
    parser.add_argument('--manifest-sha256', default=MANIFEST_SHA256)
    args = parser.parse_args(argv)
    try:
        count = build_studio_site(args.output, args.library_url, args.manifest_sha256)
    except (LibrarySiteError, OSError, URLError, ValueError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(f'site built: 5 studio files, {count} library clips')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
