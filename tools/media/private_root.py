"""Validate the private storage root shared by the Live Photos export and tagging tools."""

from __future__ import annotations

from pathlib import Path

from tools.paths import REPO_ROOT, VAR_DIR

PHOTOS_LIBRARY_SUFFIX = ".photoslibrary"


def inside_photos_library(path: Path) -> bool:
    """Return True when any component of ``path`` is a ``.photoslibrary`` package."""
    return any(part.lower().endswith(PHOTOS_LIBRARY_SUFFIX) for part in path.parts)


def resolve_private_root(value: Path | str) -> Path:
    """Resolve a ``--root`` value or exit with a plain message.

    The root holds personal media and derived analysis. It may live anywhere outside the
    checkout (preferred for large archives). Inside the checkout it must stay below ``var/``,
    which is ignored by Git. Paths inside a ``.photoslibrary`` package are always refused,
    whether reached directly or through a symlink.
    """
    root = Path(value).expanduser()
    resolved = root.resolve()
    if inside_photos_library(root.absolute()) or inside_photos_library(resolved):
        raise SystemExit("Refusing to use a path inside a Photos library package as --root.")
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(VAR_DIR.resolve()):
        raise SystemExit(
            "--root inside the checkout must stay under var/ (ignored by Git); "
            "keep large personal media outside the repository."
        )
    return resolved
