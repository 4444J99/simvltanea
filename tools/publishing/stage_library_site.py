#!/usr/bin/env python3
"""Assemble a deployable studio site with the public demo library beside it.

``stage_studio`` writes the declared Studio and Effects Lab files; ``tools.media.build_public_demo``
writes ``manifest.json`` and ``clips/<id>.mp4``. This deploy helper copies both
into one fresh directory, so the studio finds its library on the same origin::

    <site>/index.html  runtime.js  compiler.js  studio.js  layouts.json
    <site>/lab.html  lab_model.js  lab_engine.js  lab_ui.js  lab_audio.js
    <site>/lab_compiler.js  lab_layouts.js
    <site>/library/manifest.json
    <site>/library/clips/<id>.mp4

    python3 -m tools.publishing.stage_library_site --studio-out var/site/studio \\
        --library /path/to/public-demo --site var/site/deploy

Everything is checked before a byte is written, and a refusal writes nothing:
the studio output must hold exactly the declared studio files; the library must hold
only ``manifest.json`` and ``clips/*.mp4``, with a valid
``simvltanea.public-demo/1`` manifest; every clip must be listed, every listed
forward/variant clip present, and each file's size and SHA-256 prefix must match
its entry. No symlinks or hidden files are accepted. ``--site`` must be absent or empty.
Output is counts only. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path

from simvltanea.browser import STUDIO_FILES
LAB_REQUIRED = ('index.html', 'player.js')
SCHEMA = 'simvltanea.public-demo/1'
MANIFEST = 'manifest.json'
CLIPS = 'clips'
CLIP_ID = re.compile(r'^[0-9a-f]{12}$')
CLIP_FILE = re.compile(r'^clips/[0-9a-f]{12}\.mp4$')
# The same bounds browser.studio.js applies before it trusts a manifest.
MAX_CLIPS = 5000
MAX_CLIP_BYTES = 64 * 1024 * 1024
MAX_SIDE = 4096
MIN_SECONDS = 0.25
MAX_SECONDS = 600
ORIENTATIONS = ('portrait', 'landscape')


class LibrarySiteError(ValueError):
    """The inputs cannot be assembled into a safe deployable site."""


def _size(value, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= maximum


def _number(value, minimum: float, maximum: float) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and minimum <= value <= maximum)


AUDIO_FIELDS = ('has_audio', 'lufs_integrated', 'peak_dbfs', 'envelope_hz', 'rms_envelope')
ASSET_FIELDS = ('id', 'file', 'width', 'height', 'orientation', 'bytes', 'duration_seconds')
VARIANT_FIELDS = ('fps', 'frame_count', 'seam_offset_seconds')


def _validate_audio(asset: dict, where: str, required: bool = False) -> None:
    if not required and not any(field in asset for field in AUDIO_FIELDS):
        return
    if any(field not in asset for field in AUDIO_FIELDS):
        raise LibrarySiteError(f'{where}: audio metadata must include all audio fields')
    audible = asset['has_audio']
    if not isinstance(audible, bool):
        raise LibrarySiteError(f'{where}: has_audio must be a boolean')
    loudness, peak = asset['lufs_integrated'], asset['peak_dbfs']
    # Very short clips may not yield a gated integrated loudness measurement.
    if loudness is not None and not _number(loudness, -160, 12):
        raise LibrarySiteError(f'{where}: lufs_integrated must be finite or null')
    if (audible and not _number(peak, -160, 24)) or (not audible and peak is not None):
        raise LibrarySiteError(f'{where}: peak_dbfs must be finite for sound and null for silence')
    if not audible and loudness is not None:
        raise LibrarySiteError(f'{where}: silent integrated loudness must be null')
    envelope = asset['rms_envelope']
    if (asset['envelope_hz'] != 10 or isinstance(asset['envelope_hz'], bool)
            or not isinstance(envelope, list)
            or len(envelope) != math.ceil(asset['duration_seconds'] * 10)
            or any(not _number(sample, 0, 1) for sample in envelope)):
        raise LibrarySiteError(f'{where}: rms_envelope must contain bounded 10 Hz samples for the duration')


def _validate_asset(asset, where: str, variant: bool = False) -> None:
    if not isinstance(asset, dict):
        raise LibrarySiteError(f'{where} is not an object')
    clip_id, file = asset.get('id'), asset.get('file')
    if not isinstance(clip_id, str) or not CLIP_ID.fullmatch(clip_id):
        raise LibrarySiteError(f'{where}: id must be 12 lowercase hex digits')
    if not isinstance(file, str) or not CLIP_FILE.fullmatch(file) or file != f'{CLIPS}/{clip_id}.mp4':
        raise LibrarySiteError(f'{where}: file must be clips/<id>.mp4')
    width, height = asset.get('width'), asset.get('height')
    if not _size(width, MAX_SIDE) or not _size(height, MAX_SIDE):
        raise LibrarySiteError(f'{where}: width and height must be whole pixels up to {MAX_SIDE}')
    if not _size(asset.get('bytes'), MAX_CLIP_BYTES):
        raise LibrarySiteError(f'{where}: bytes must be a size up to {MAX_CLIP_BYTES}')
    expected = 'portrait' if height > width else 'landscape'
    if asset.get('orientation') not in ORIENTATIONS or asset.get('orientation') != expected:
        raise LibrarySiteError(f'{where}: orientation must be {expected}')
    seconds = asset.get('duration_seconds')
    if not _number(seconds, MIN_SECONDS, MAX_SECONDS):
        raise LibrarySiteError(f'{where}: duration_seconds must lie in {MIN_SECONDS}..{MAX_SECONDS}')
    _validate_audio(asset, where, required=variant)
    if variant:
        if (not _size(asset.get('fps'), 30) or asset['fps'] != 30
                or not _size(asset.get('frame_count'), int(MAX_SECONDS * 30))
                or abs(asset['frame_count'] / 30 - seconds) >= 0.001):
            raise LibrarySiteError(f'{where}: frame_count and duration must describe CFR 30 fps')
        if not _number(asset.get('seam_offset_seconds'), 0, seconds):
            raise LibrarySiteError(f'{where}: seam_offset_seconds must lie within the duration')


def manifest_assets(clips: list[dict]) -> list[dict]:
    """Flatten validated logical clips into distinct content-addressed assets."""
    assets = {}
    for clip in clips:
        assets[clip['file']] = clip
        for variant in clip.get('variants', {}).values():
            assets[variant['file']] = variant
    return list(assets.values())


def validate_manifest(document) -> list[dict]:
    """Return logical clips after validating forward assets and optional variants."""
    if not isinstance(document, dict) or document.get('schema') != SCHEMA:
        raise LibrarySiteError(f'library manifest schema must be {SCHEMA}')
    clips = document.get('clips')
    if not isinstance(clips, list) or not clips or len(clips) > MAX_CLIPS:
        raise LibrarySiteError(f'library manifest needs 1 to {MAX_CLIPS} clips')
    logical_ids, assets = set(), {}

    def remember(asset: dict, where: str) -> None:
        facts = {field: asset[field] for field in (*ASSET_FIELDS, *AUDIO_FIELDS, *VARIANT_FIELDS)
                 if field in asset}
        previous = assets.get(asset['id'])
        if previous is not None and previous != facts:
            raise LibrarySiteError(f'{where}: duplicate content id has conflicting asset facts')
        assets[asset['id']] = facts

    for number, clip in enumerate(clips, 1):
        where = f'library manifest clip {number}'
        _validate_asset(clip, where)
        if clip['id'] in logical_ids:
            raise LibrarySiteError(f'{where}: duplicate id')
        logical_ids.add(clip['id'])
        if not isinstance(clip.get('tags', {}), dict):
            raise LibrarySiteError(f'{where}: tags must be an object')
        remember(clip, where)
        variants = clip.get('variants', {})
        if not isinstance(variants, dict) or any(mode != 'boomerang' for mode in variants):
            raise LibrarySiteError(f'{where}: variants must be an object containing only boomerang')
        for mode, variant in variants.items():
            variant_where = f'{where} variant {mode}'
            _validate_asset(variant, variant_where, variant=True)
            if variant['id'] == clip['id']:
                raise LibrarySiteError(f'{variant_where}: duplicate forward id')
            remember(variant, variant_where)
    return clips


def _plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def check_studio(studio_out: Path) -> None:
    if studio_out.is_symlink() or not studio_out.is_dir():
        raise LibrarySiteError('studio output must be a directory staged by stage_studio')
    names = sorted(entry.name for entry in studio_out.iterdir())
    if names != sorted(STUDIO_FILES) or not all(_plain_file(studio_out / name) for name in names):
        raise LibrarySiteError(f'studio output must hold exactly {", ".join(STUDIO_FILES)}')


def check_library(library: Path) -> list[dict]:
    """Validate the builder output and return its clips."""
    if library.is_symlink() or not library.is_dir():
        raise LibrarySiteError('library must be a directory written by build_public_demo')
    foreign = sorted(entry.name for entry in library.iterdir() if entry.name not in (MANIFEST, CLIPS))
    if foreign:
        raise LibrarySiteError(f'library holds {len(foreign)} entries other than manifest.json and clips/')
    manifest = library / MANIFEST
    if not _plain_file(manifest):
        raise LibrarySiteError('library has no manifest.json')
    try:
        document = json.loads(manifest.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LibrarySiteError(f'library manifest.json is not JSON ({error.__class__.__name__})') from None
    clips = validate_manifest(document)
    folder = library / CLIPS
    if folder.is_symlink() or not folder.is_dir():
        raise LibrarySiteError('library has no clips/ directory')
    listed = {asset['file'].split('/', 1)[1]: asset for asset in manifest_assets(clips)}
    present = {entry.name: entry for entry in folder.iterdir()}
    unlisted = [name for name in present if name not in listed]
    if unlisted:
        raise LibrarySiteError(f'library clips/ holds {len(unlisted)} files the manifest does not list')
    missing = [name for name in listed if name not in present]
    if missing:
        raise LibrarySiteError(f'library manifest lists {len(missing)} clips that are missing from clips/')
    for name, clip in listed.items():
        path = present[name]
        if not _plain_file(path):
            raise LibrarySiteError('library clips must be regular files, not links or directories')
        data = path.read_bytes()
        if len(data) != clip['bytes']:
            raise LibrarySiteError(f'library clip size does not match its manifest entry ({len(data)} bytes)')
        if hashlib.sha256(data).hexdigest()[:12] != clip['id']:
            raise LibrarySiteError('library clip content does not match its manifest id')
    return clips




def check_lab(lab_out: Path) -> None:
    if lab_out.is_symlink() or not lab_out.is_dir():
        raise LibrarySiteError('lab output must be a directory')
    names = {entry.name for entry in lab_out.iterdir()}
    if not all(name in names for name in LAB_REQUIRED):
        raise LibrarySiteError(f'lab output must contain {", ".join(LAB_REQUIRED)}')
    if not all(_plain_file(lab_out / name) for name in names if (lab_out / name).is_file()):
        raise LibrarySiteError('lab output must hold regular files only')


def _lab_clips_from_manifest(clips: list[dict]) -> list[dict]:
    out = []
    for clip in clips:
        cid = clip['id']
        out.append({
            "id": cid,
            "video": f"media/{cid}.mp4",
            "still": "",
            "duration": clip.get('duration_seconds'),
            "width": clip.get('width'),
            "height": clip.get('height'),
            "orientation": clip.get('orientation'),
            "has_audio": False,
            "loudness_db": None,
            "audio": {"screened": False},
            "captured_at": None,
            "tags": {},
            "features": {},
        })
    return out


def stage_lab_site(lab_out: Path, library: Path, site: Path) -> int:
    """Stage the Lab player plus a Lab-compatible dataset built from the public demo."""
    lab_out, library, site = Path(lab_out), Path(library), Path(site)
    check_lab(lab_out)
    clips = check_library(library)
    if site.is_symlink() or (site.exists() and (not site.is_dir() or any(site.iterdir()))):
        raise LibrarySiteError('site must be absent or an empty directory')
    for inside in (lab_out, library):
        if site.resolve() == inside.resolve() or inside.resolve() in site.resolve().parents:
            raise LibrarySiteError('site must not lie inside the lab output or the library')
    (site / 'media').mkdir(parents=True, exist_ok=True)
    (site / 'data').mkdir(parents=True, exist_ok=True)
    for entry in lab_out.iterdir():
        if not _plain_file(entry):
            continue
        shutil.copyfile(entry, site / entry.name)
    # copy clips into media/ with Lab naming
    for clip in clips:
        src = library / clip['file']
        dst = site / 'media' / (clip['id'] + '.mp4')
        shutil.copyfile(src, dst)
    lab_clips = _lab_clips_from_manifest(clips)
    import json as _json
    (site / 'data' / 'clips.json').write_text(_json.dumps({"version": 1, "clips": lab_clips}, separators=(",", ":")), encoding='utf-8')
    return len(clips)

def stage_library_site(studio_out: Path, library: Path, site: Path) -> int:
    """Copy the studio and the library into ``site``; return the number of clips."""
    studio_out, library, site = Path(studio_out), Path(library), Path(site)
    check_studio(studio_out)
    clips = check_library(library)
    if site.is_symlink() or (site.exists() and (not site.is_dir() or any(site.iterdir()))):
        raise LibrarySiteError('site must be absent or an empty directory')
    for inside in (studio_out, library):
        if site.resolve() == inside.resolve() or inside.resolve() in site.resolve().parents:
            raise LibrarySiteError('site must not lie inside the studio output or the library')
    (site / 'library' / CLIPS).mkdir(parents=True, exist_ok=True)
    for name in STUDIO_FILES:
        shutil.copyfile(studio_out / name, site / name)
    shutil.copyfile(library / MANIFEST, site / 'library' / MANIFEST)
    for asset in manifest_assets(clips):
        shutil.copyfile(library / asset['file'], site / 'library' / asset['file'])
    return len(clips)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--studio-out', type=Path, default=None, help='directory stage_studio wrote (studio playback)')
    parser.add_argument('--lab-out', type=Path, default=None, help='directory containing the Lab app (lab playback)')
    parser.add_argument('--library', type=Path, required=True, help='build_public_demo output directory')
    parser.add_argument('--site', type=Path, required=True, help='absent or empty directory to receive the site')
    parser.add_argument('--playback', choices=('studio', 'lab'), default='studio', help='which playback surface to stage')
    args = parser.parse_args(argv)
    try:
        if args.playback == 'lab':
            if args.lab_out is None:
                raise LibrarySiteError('--lab-out is required for lab playback')
            count = stage_lab_site(args.lab_out, args.library, args.site)
            print(f'site assembled: lab playback, {count} library clips')
        else:
            if args.studio_out is None:
                raise LibrarySiteError('--studio-out is required for studio playback')
            count = stage_library_site(args.studio_out, args.library, args.site)
            print(f'site assembled: {len(STUDIO_FILES)} studio files, {count} library clips')
    except LibrarySiteError as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
