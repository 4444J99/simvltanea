"""Canonical repository and generated-output paths.

All runtime output belongs below ``var/``.  Keeping path resolution here avoids
commands silently creating parallel ``tools/work`` or ``tools/site`` trees.
"""

from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
REPO_ROOT = SRC_DIR.parent

EXAMPLES_DIR = REPO_ROOT / "examples"
FIXTURES_DIR = REPO_ROOT / "fixtures"
ARTIFACT_FIXTURE_DIR = FIXTURES_DIR / "artifact-001"

VAR_DIR = REPO_ROOT / "var"
WORK_DIR = VAR_DIR / "work"
SAMPLES_DIR = VAR_DIR / "samples"
RENDERS_DIR = VAR_DIR / "renders"
SITE_DIR = VAR_DIR / "site"
PACKAGES_DIR = VAR_DIR / "packages"
PROOFS_DIR = VAR_DIR / "proofs"
ARTIFACT_OUTPUT_DIR = VAR_DIR / "artifact-001"


def in_var(path: Path) -> bool:
    """Return whether *path* resolves inside the generated-output boundary."""
    try:
        path.resolve().relative_to(VAR_DIR.resolve())
    except ValueError:
        return False
    return True


def require_in_var(path: Path, label: str = "output") -> Path:
    """Resolve an output path and reject writes outside ``var/``."""
    resolved = path.expanduser().resolve()
    if not in_var(resolved):
        raise ValueError(f"{label} must stay inside {VAR_DIR}")
    return resolved
