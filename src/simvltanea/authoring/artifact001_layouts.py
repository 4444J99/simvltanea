#!/usr/bin/env python3
"""Authored engineering layouts for Artifact 001.

These are synthetic design demonstrations, not artist-approved compositions.
"""
from __future__ import annotations

from pathlib import Path

from simvltanea.authoring.composition_model import Composition, Layout, LoopState, Placement


def p(loop_id: str, x: float, y: float, w: float, h: float, z: int = 0, fit: str = "cover") -> Placement:
    return Placement(loop_id, x, y, w, h, z=z, fit=fit)


# Geometry is intentionally authored per count/orientation rather than generated
# by a generic grid. Negative space and hierarchy vary across the matrix.
# Other geometry comes from explicit files by path (``load_layout_file``), never from the package.
_AUTHORED_DEFAULT = {
    2: {
        "portrait": ((0.04, 0.03, 0.92, 0.44), (0.04, 0.52, 0.92, 0.44)),
        "landscape": ((0.03, 0.05, 0.46, 0.90), (0.51, 0.05, 0.46, 0.90)),
    },
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
    7: {
        "portrait": ((.04, .03, .92, .30), (.04, .37, .44, .18), (.52, .37, .44, .18), (.04, .58, .28, .17), (.36, .58, .28, .17), (.68, .58, .28, .17), (.04, .79, .92, .18)),
        "landscape": ((.03, .05, .38, .90), (.45, .05, .24, .26), (.73, .05, .24, .26), (.45, .36, .24, .28), (.73, .36, .24, .28), (.45, .69, .24, .26), (.73, .69, .24, .26)),
    },
    8: {
        "portrait": ((.04, .03, .92, .3), (.04, .36, .28, .18), (.36, .36, .28, .18), (.68, .36, .28, .18), (.04, .57, .44, .18), (.52, .57, .44, .18), (.04, .78, .44, .19), (.52, .78, .44, .19)),
        "landscape": ((.03, .05, .34, .9), (.4, .05, .17, .28), (.6, .05, .17, .28), (.8, .05, .17, .28), (.4, .36, .27, .26), (.7, .36, .27, .26), (.4, .65, .27, .3), (.7, .65, .27, .3)),
    },
    9: {
        "portrait": ((.04, .03, .44, .22), (.52, .03, .44, .22), (.04, .28, .92, .26), (.04, .57, .28, .19), (.36, .57, .28, .19), (.68, .57, .28, .19), (.04, .79, .28, .18), (.36, .79, .28, .18), (.68, .79, .28, .18)),
        "landscape": ((.03, .05, .22, .27), (.03, .35, .22, .27), (.03, .65, .22, .3), (.28, .05, .44, .5), (.28, .58, .205, .37), (.515, .58, .205, .37), (.75, .05, .22, .27), (.75, .35, .22, .27), (.75, .65, .22, .3)),
    },
    10: {
        "portrait": ((.04, .03, .92, .24), (.04, .3, .28, .21), (.36, .3, .28, .21), (.68, .3, .28, .21), (.04, .54, .28, .21), (.36, .54, .28, .21), (.68, .54, .28, .21), (.04, .78, .28, .19), (.36, .78, .28, .19), (.68, .78, .28, .19)),
        "landscape": ((.03, .05, .3, .9), (.36, .05, .18, .28), (.575, .05, .18, .28), (.79, .05, .18, .28), (.36, .36, .18, .28), (.575, .36, .18, .28), (.79, .36, .18, .28), (.36, .67, .18, .28), (.575, .67, .18, .28), (.79, .67, .18, .28)),
    },
    11: {
        "portrait": ((.04, .03, .92, .2), (.04, .26, .44, .16), (.52, .26, .44, .16), (.04, .45, .2, .24), (.28, .45, .2, .24), (.52, .45, .2, .24), (.76, .45, .2, .24), (.04, .72, .2, .25), (.28, .72, .2, .25), (.52, .72, .2, .25), (.76, .72, .2, .25)),
        "landscape": ((.03, .05, .28, .9), (.34, .05, .19, .2), (.56, .05, .19, .2), (.78, .05, .19, .2), (.34, .28, .19, .2), (.56, .28, .19, .2), (.78, .28, .19, .2), (.34, .51, .19, .2), (.56, .51, .19, .2), (.78, .51, .19, .2), (.34, .74, .63, .21)),
    },
    12: {
        "portrait": ((.04, .03, .44, .22), (.52, .03, .44, .22), (.04, .28, .28, .2), (.36, .28, .28, .2), (.68, .28, .28, .2), (.04, .51, .2, .22), (.28, .51, .2, .22), (.52, .51, .2, .22), (.76, .51, .2, .22), (.04, .76, .28, .21), (.36, .76, .28, .21), (.68, .76, .28, .21)),
        "landscape": ((.03, .05, .2, .27), (.03, .35, .2, .27), (.03, .65, .2, .3), (.26, .05, .2, .195), (.26, .275, .2, .195), (.26, .5, .2, .195), (.26, .725, .2, .225), (.49, .05, .26, .435), (.49, .515, .26, .435), (.78, .05, .19, .27), (.78, .35, .19, .27), (.78, .65, .19, .3)),
    },
}

AMBIENT_OVERRIDE = Path(__file__).resolve().parents[1] / "layouts.json"


class AmbientLayoutOverrideError(RuntimeError):
    """The removed in-package override file is present."""


def refuse_ambient_override(path: Path = AMBIENT_OVERRIDE) -> None:
    """Fail loudly instead of silently reading layout geometry from inside the package."""
    if path.exists():
        raise AmbientLayoutOverrideError(
            f"{path}: the in-package layout override was removed and is never read. Delete this file and "
            "supply layouts as explicit files by path: load_layout_file(path) for a "
            "simvltanea.layout-preset/1 or simvltanea.layout-pair/1 file (check it with "
            "python -m tools.verification.verify_layouts --layouts FILE).")


refuse_ambient_override()
AUTHORED = dict(_AUTHORED_DEFAULT)


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
    parser = argparse.ArgumentParser()
    parser.add_argument("count", type=int, choices=sorted(AUTHORED))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = build_artifact001(args.count).to_json() + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
