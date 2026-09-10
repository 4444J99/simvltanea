#!/usr/bin/env python3
"""Authored engineering layouts for Artifact 001.

These are synthetic design demonstrations, not artist-approved compositions.
"""
from __future__ import annotations

from composition_model import Composition, Layout, LoopState, Placement


def p(loop_id: str, x: float, y: float, w: float, h: float, z: int = 0, fit: str = "cover") -> Placement:
    return Placement(loop_id, x, y, w, h, z=z, fit=fit)


# Geometry is intentionally authored per count/orientation rather than generated
# by a generic grid. Negative space and hierarchy vary across the matrix.
AUTHORED = {
    3: {
        "portrait": ((0.04, .03, .92, .42), (.04, .48, .44, .49), (.52, .48, .44, .49)),
        "landscape": ((.03, .05, .46, .90), (.52, .05, .21, .90), (.76, .05, .21, .90)),
    },
    4: {
        "portrait": ((.04, .03, .56, .45), (.64, .03, .32, .45), (.04, .52, .32, .45), (.40, .52, .56, .45)),
        "landscape": ((.03, .05, .45, .56), (.03, .65, .45, .30), (.52, .05, .45, .30), (.52, .39, .45, .56)),
    },
    5: {
        "portrait": ((.04, .03, .92, .36), (.04, .43, .44, .25), (.52, .43, .44, .25), (.04, .72, .44, .25), (.52, .72, .44, .25)),
        "landscape": ((.03, .05, .40, .90), (.47, .05, .23, .42), (.74, .05, .23, .42), (.47, .53, .23, .42), (.74, .53, .23, .42)),
    },
    6: {
        "portrait": ((.04, .03, .44, .29), (.52, .03, .44, .29), (.04, .36, .92, .28), (.04, .68, .28, .29), (.36, .68, .28, .29), (.68, .68, .28, .29)),
        "landscape": ((.03, .05, .29, .42), (.03, .53, .29, .42), (.36, .05, .28, .90), (.68, .05, .29, .27), (.68, .365, .29, .27), (.68, .68, .29, .27)),
    },
}


def build_artifact001(count: int) -> Composition:
    if count not in AUTHORED:
        raise ValueError(f"count {count} has no reviewed engineering layout pair; supported demo counts: {sorted(AUTHORED)}")
    loops = tuple(
        LoopState(id=f"loop-{i+1}", source=f"fixtures/loop-{i+1}.mp4", rate=1.0 + i * .07, offset=i * .31, selection_seed=100 + i)
        for i in range(count)
    )
    layouts = []
    for orientation in ("portrait", "landscape"):
        placements = tuple(p(loops[i].id, *geometry) for i, geometry in enumerate(AUTHORED[count][orientation]))
        layouts.append(Layout(id=f"artifact001-{count}-{orientation}", orientation=orientation, placements=placements))
    composition = Composition(id=f"artifact001-{count}", loops=loops, layouts=tuple(layouts), seed=444499)
    composition.validate()
    return composition


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("count", type=int, choices=sorted(AUTHORED))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = build_artifact001(args.count).to_json() + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
