#!/usr/bin/env python3
"""Build the Pages site with a pinned or locally admitted public clip library.

Run from the repository root with ``python3 -m tools.publishing.build_studio_site``.
Only staged browser assets and manifest-listed public clips enter ``var/site/deploy``.
The immutable deployment URL and manifest digest preserve the published library
without copying private source media or repository archives into the build.
Use ``--library PATH`` to stage a validated local public library with variants.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

from tools.paths import SITE_DIR
from simvltanea.browser import ENGINEERED_ITERATIONS, STUDIO_FILES, stage_studio
from tools.publishing.iteration_archive import preserved_iteration_files
from tools.publishing.iteration_replays import historical_replay_files
from tools.publishing.stage_library_site import (LibrarySiteError, check_library, manifest_assets,
                                                 stage_library_site, validate_manifest)


LIBRARY_URL = 'https://75cafe28.loop-compositor-studio.pages.dev/library/'
MANIFEST_SHA256 = '030d6446b3a57ea003ec056fdb7ed3e553c10f184b477346822eec5b4f9ca401'
PAGES_MAX_BYTES = 25 * 1024 * 1024


def assemble_release(output: Path, library: Path) -> int:
    """Build every advertised local iteration before publishing one complete tree."""
    clips = check_library(library)
    historical = preserved_iteration_files(clips)
    early = historical_replay_files(clips)
    if historical.keys() & early.keys():
        raise LibrarySiteError('historical iterations emitted overlapping assets')
    historical.update(early)
    for name, body in historical.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or not name.startswith('iterations/')
                or path.suffix not in ('.html', '.css', '.js', '.json')):
            raise LibrarySiteError('historical iteration emitted an unsafe asset path')
        if len(body) > PAGES_MAX_BYTES:
            raise LibrarySiteError('historical iteration exceeds the Pages 25 MiB file limit')
    for item in ENGINEERED_ITERATIONS:
        if item['url'].startswith('iterations/') and item['url'] + 'index.html' not in historical:
            raise LibrarySiteError('advertised historical iteration is missing: ' + item['slug'])

    # A sibling staging tree makes the final rename atomic on the output filesystem.
    # A failed download, historical build, or media validation cannot publish half a site.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.studio-pages-build-', dir=output.parent) as temporary:
        staging = Path(temporary)
        studio, release = staging / 'studio', staging / 'release'
        stage_studio(studio)
        if any(path.stat().st_size > PAGES_MAX_BYTES for path in studio.iterdir()):
            raise LibrarySiteError('studio file exceeds the Pages 25 MiB file limit')
        count = stage_library_site(studio, library, release)
        for name, body in historical.items():
            destination = release / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise LibrarySiteError('output must still be absent or an empty directory')
        release.replace(output)
    return count


def download(url: str, limit: int) -> bytes:
    """Read a bounded public asset using inherited proxy and TLS settings."""
    request = Request(url, headers={'User-Agent': 'simvltanea-pages-build/1'})
    with urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise LibrarySiteError('download exceeds its permitted file size')
    return data


def build_studio_site(output: Path, library_url: str = LIBRARY_URL,
                      manifest_sha256: str = MANIFEST_SHA256, *, library: Path | None = None) -> int:
    """Validate and assemble a complete site; leave existing content untouched."""
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise LibrarySiteError('output must be absent or an empty directory')
    if library is not None:
        library = Path(library)
        clips = check_library(library)
        if any(asset['bytes'] > PAGES_MAX_BYTES for asset in manifest_assets(clips)):
            raise LibrarySiteError('library clip exceeds the Pages 25 MiB file limit')
        if (library / 'manifest.json').stat().st_size > PAGES_MAX_BYTES:
            raise LibrarySiteError('library manifest exceeds the Pages 25 MiB file limit')
        return assemble_release(output, library)
    library_url = library_url.rstrip('/') + '/'
    manifest = download(library_url + 'manifest.json', PAGES_MAX_BYTES)
    if hashlib.sha256(manifest).hexdigest() != manifest_sha256:
        raise LibrarySiteError('library manifest SHA-256 does not match the pinned publication')
    clips = validate_manifest(json.loads(manifest))
    assets = manifest_assets(clips)
    if any(asset['bytes'] > PAGES_MAX_BYTES for asset in assets):
        raise LibrarySiteError('library clip exceeds the Pages 25 MiB file limit')

    with tempfile.TemporaryDirectory(prefix='studio-pages-build-') as temporary:
        staging = Path(temporary)
        library = staging / 'library'
        (library / 'clips').mkdir(parents=True)
        (library / 'manifest.json').write_bytes(manifest)

        def fetch_clip(clip: dict) -> None:
            data = download(library_url + clip['file'], clip['bytes'])
            if len(data) != clip['bytes']:
                raise LibrarySiteError('downloaded clip size does not match its manifest entry')
            (library / clip['file']).write_bytes(data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(fetch_clip, assets))
        # Existing staging checks every content hash before creating the output.
        return assemble_release(output, library)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, default=SITE_DIR / 'deploy')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--library-url', default=LIBRARY_URL)
    source.add_argument('--library', type=Path, help='already admitted public library with optional variants')
    parser.add_argument('--manifest-sha256', default=MANIFEST_SHA256)
    args = parser.parse_args(argv)
    try:
        count = build_studio_site(args.output, args.library_url, args.manifest_sha256, library=args.library)
    except (LibrarySiteError, OSError, URLError, ValueError) as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(f'site built: {len(STUDIO_FILES)} studio files, {count} library clips, '
          f'{len(ENGINEERED_ITERATIONS)} named iterations')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
