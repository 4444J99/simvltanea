"""The playable lab: a static, client-only web instrument for simultaneous loops.

The browser application in ``app/`` (plain ES modules, HTML and CSS; no build step, no
dependencies) is distributed with this subpackage. Python only locates it and generates
synthetic fixtures below the generated-output root; it never reads, serves or writes a
private dataset. See ``docs/authoring/LAB.md``.
"""
from pathlib import Path

from simvltanea.paths import PROOFS_DIR

LAB_DIR = Path(__file__).resolve().parent
APP_DIR = LAB_DIR / "app"
# Synthetic clips from ``python -m simvltanea.lab.make_fixtures`` (git-ignored, below var/).
FIXTURES_DIR = PROOFS_DIR / "lab-fixtures"

__all__ = ["APP_DIR", "FIXTURES_DIR", "LAB_DIR"]
