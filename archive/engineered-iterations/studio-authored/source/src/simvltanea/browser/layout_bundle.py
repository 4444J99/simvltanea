#!/usr/bin/env python3
"""Export the authored portrait/landscape layouts for browser.compiler.js.

The geometry is never copied by hand: every pair is the ``layouts`` object that
``from_authoring_model`` emits for ``build_artifact001(count)``, so the browser
receives the same exact rationals as the Python state pipeline. The bundle is
generated on demand because source JSON files are not permitted under ``src/``::

    python -m simvltanea.browser.layout_bundle > layouts.json
"""
from __future__ import annotations

import argparse
import json

from simvltanea.authoring import AUTHORED, build_artifact001, from_authoring_model


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


def authored_layout_bundle() -> dict[str, dict]:
    """Map every authored loop count (as a JSON string key) to its layout pair."""
    return {str(count): authored_layouts(count) for count in sorted(AUTHORED)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    print(json.dumps(authored_layout_bundle(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
