#!/usr/bin/env python3
"""Export the layout families for browser.compiler.js and the studio.

The geometry is never copied by hand. Every authored pair is the ``layouts`` object
that ``from_authoring_model`` emits for ``build_artifact001(count)``, and every strips
pair, slice and adjacency list comes from ``strips_layouts``, ``strips_slice`` and
``adjacency``, so the browser receives the same exact rationals as the Python state
pipeline. The bundle is generated on demand because source JSON files are not
permitted under ``src/``::

    python -m simvltanea.browser.layout_bundle > layouts.json             # legacy authored map
    python -m simvltanea.browser.layout_bundle --format 2 > layouts.json  # simvltanea.layout-bundle/2

Without flags the output is the legacy map (count -> authored pair), byte for byte as
before. ``--format 2`` adds the strips family (N=1..12, the default family) beside the
authored family (N=2..12), each strips count with its state-wide ``slice`` and the
exact ``adjacency`` of both orientations.
"""
from __future__ import annotations

import argparse
import json

from simvltanea.authoring import (
    AUTHORED,
    adjacency,
    build_artifact001,
    from_authoring_model,
    strips_layouts,
    strips_slice,
)

BUNDLE_FORMAT = 'simvltanea.layout-bundle/2'
PRESET_FORMAT = 'simvltanea.layout-preset/1'
STRIPS_PRESET = 'strips'
STRIPS_COUNTS = range(1, 13)
DEFAULT_FAMILY = 'strips'


def authored_layouts(count: int) -> dict:
    """Return the authored ``{"portrait": ..., "landscape": ...}`` pair for ``count`` loops.

    Unsupported counts raise ``ValueError`` from ``build_artifact001``. The
    placeholder media bindings exist only to drive the canonical conversion;
    their loop clocks and sources are discarded and never reach the bundle.
    """
    composition = build_artifact001(count)
    placeholders = {
        loop.source: dict(id=f'layout-source-{index}', path=f'media/layout-source-{index}.mp4',
                          sha256=f'{index:064x}', kind='video', duration='1')
        for index, loop in enumerate(composition.loops, 1)
    }
    return from_authoring_model(composition, placeholders, frames=1)['layouts']


# Counts the Studio and Effects Lab offer from the authored family: every authored count (2..12).
# Seeded rolls stay reproducible because the Studio versions them (browser.studio.js ROLL_VERSION):
# a link without ?rv draws the authored family from 2..7 only, as it did before 8..12 were offered.
LEGACY_ROLL_AUTHORED_MAX = 7
BUNDLE_AUTHORED_COUNTS = tuple(sorted(AUTHORED))


def authored_layout_bundle() -> dict[str, dict]:
    """Map every bundled authored loop count (as a JSON string key) to its layout pair."""
    return {str(count): authored_layouts(count) for count in BUNDLE_AUTHORED_COUNTS}


def strips_entry(count: int, preset: str = STRIPS_PRESET) -> dict:
    """Return one strips count: both layouts, the state-wide slice and both adjacency lists."""
    layouts = strips_layouts(count, preset)
    return {
        'portrait': layouts['portrait'],
        'landscape': layouts['landscape'],
        'slice': strips_slice(count, preset),
        'adjacency': {orientation: adjacency(layouts[orientation]['cells'])
                      for orientation in ('portrait', 'landscape')},
    }


def layout_bundle_v2() -> dict:
    """Return the ``simvltanea.layout-bundle/2`` object: authored 2..12 and strips 1..12."""
    return {
        'format': BUNDLE_FORMAT,
        'default_family': DEFAULT_FAMILY,
        'families': {
            'authored': {'counts': authored_layout_bundle()},
            'strips': {
                'preset': {'format': PRESET_FORMAT, 'name': STRIPS_PRESET},
                'counts': {str(count): strips_entry(count) for count in STRIPS_COUNTS},
            },
        },
    }


def render_bundle(version: int = 1) -> str:
    """The exact text the command prints (without its final newline)."""
    bundle = authored_layout_bundle() if version == 1 else layout_bundle_v2()
    return json.dumps(bundle, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--format', type=int, choices=(1, 2), default=1, dest='version',
                        help='1: the legacy authored map (default, unchanged); 2: simvltanea.layout-bundle/2')
    args = parser.parse_args(argv)
    print(render_bundle(args.version))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
