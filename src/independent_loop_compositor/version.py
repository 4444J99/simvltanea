"""Resolve the installed distribution version without importing the engine."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path
import tomllib

DISTRIBUTION = "simvltanea"
UNKNOWN_VERSION = "unknown"


def _source_tree_version() -> str | None:
    """Read the version from a source checkout's pyproject.toml, if this is one."""
    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        data = tomllib.loads(project.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    table = data.get("project", {})
    if table.get("name") != DISTRIBUTION:
        return None
    version = table.get("version")
    return version if isinstance(version, str) and version else None


def get_version() -> str:
    """Installed metadata first, then the source tree, then ``unknown``."""
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return _source_tree_version() or UNKNOWN_VERSION
