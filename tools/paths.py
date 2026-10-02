"""Expose the engine's canonical path contract to operational commands."""

from __future__ import annotations

import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from simvltanea.paths import (  # noqa: E402,F401
    ARTIFACT_FIXTURE_DIR,
    ARTIFACT_OUTPUT_DIR,
    EXAMPLES_DIR,
    FIXTURES_DIR,
    PACKAGES_DIR,
    PROOFS_DIR,
    RENDERS_DIR,
    REPO_ROOT,
    SAMPLES_DIR,
    SITE_DIR,
    VAR_DIR,
    WORK_DIR,
    in_var,
    require_in_var,
)
