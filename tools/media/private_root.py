"""Validate the private storage root shared by the Live Photos export and tagging tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from tools.paths import REPO_ROOT, VAR_DIR

PHOTOS_LIBRARY_SUFFIX = ".photoslibrary"
GIT_TIMEOUT_SECONDS = 20
# Variables that would redirect Git to a different repository than the one that holds ``--root``.
GIT_REDIRECT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX",
                          "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM")


def inside_photos_library(path: Path) -> bool:
    """Return True when any component of ``path`` is a ``.photoslibrary`` package.

    Names are compared after Unicode normalisation and case folding, because the default macOS volume does the
    same: ``X.photoſlibrary`` (LATIN SMALL LETTER LONG S) opens ``X.photoslibrary`` although ``str.lower`` leaves it
    unchanged.
    """
    return any(unicodedata.normalize("NFC", part).casefold().endswith(PHOTOS_LIBRARY_SUFFIX) for part in path.parts)


def _real(path: Path | str) -> Path:
    """Symlink-free absolute path. ``realpath`` also resolves paths whose tail does not exist yet."""
    return Path(os.path.realpath(os.path.expanduser(path)))


def _folded(path: Path) -> Path:
    """Case-folded form for comparisons: the default macOS volume ignores case, ``resolve`` does not fix it."""
    return Path(os.path.normcase(str(path)).casefold())


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path
    while not candidate.is_dir():
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return candidate


def _git(arguments: list[str]) -> subprocess.CompletedProcess | None:
    """Run Git with a clean environment; ``None`` when Git cannot be executed at all."""
    executable = shutil.which("git")
    if executable is None:
        return None
    env = {name: value for name, value in os.environ.items() if name not in GIT_REDIRECT_VARIABLES}
    env["LC_ALL"] = "C"  # the "not a git repository" test below reads Git's English message
    try:
        return subprocess.run([executable, *arguments], capture_output=True, text=True, env=env,
                              timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None


def _require_ignored_by_git(resolved: Path) -> bool:
    """Apply the Git rule. Returns False when Git is unavailable (the caller then falls back).

    A root inside any Git working tree, whichever checkout or worktree that is, is accepted only
    when that repository ignores it. A root outside every repository is accepted.
    """
    top = _git(["-C", str(_nearest_existing_directory(resolved)), "rev-parse", "--show-toplevel"])
    if top is None:
        return False
    if top.returncode != 0:
        if "not a git repository" in (top.stderr or ""):
            return True  # not inside any working tree
        raise SystemExit("--root is inside a Git directory or a repository Git would not inspect; "
                         "choose a path outside any repository.")
    toplevel = top.stdout.strip()
    ignored = _git(["-C", toplevel, "check-ignore", "-q", "--", str(resolved)])
    if ignored is None:
        return False
    if ignored.returncode == 0:
        return True
    if ignored.returncode == 1:
        raise SystemExit("--root is inside a Git working tree and is not ignored by it, so personal media "
                         "could be committed. Use a path outside any repository, or a directory below var/ "
                         "(ignored by Git).")
    raise SystemExit("Git could not tell whether --root is ignored; choose a path outside any repository.")


def resolve_private_root(value: Path | str) -> Path:
    """Resolve a ``--root`` value or exit with a plain message.

    The root holds personal media and derived analysis. It may live anywhere outside the
    checkout (preferred for large archives). Inside the checkout it must stay below ``var/``,
    which is ignored by Git. Paths inside a ``.photoslibrary`` package are always refused,
    whether reached directly or through a symlink.

    Whatever worktree runs this code, a root inside *any* Git working tree is refused unless that
    repository ignores it. Comparisons with the checkout are case-insensitive. Without Git only the
    case-folded checkout comparison applies, and a note on stderr says so.
    """
    root = Path(value).expanduser()
    resolved = _real(root)
    if inside_photos_library(root.absolute()) or inside_photos_library(resolved):
        raise SystemExit("Refusing to use a path inside a Photos library package as --root.")
    checkout, var_dir = _real(REPO_ROOT), _real(VAR_DIR)
    if _under(_folded(resolved), _folded(checkout)) and not _under(resolved, var_dir):
        raise SystemExit(
            "--root inside the checkout must stay under var/ (ignored by Git); "
            "keep large personal media outside the repository."
        )
    if not _require_ignored_by_git(resolved):
        print("note: git is not available, so --root was checked against the checkout path only.",
              file=sys.stderr)
    return resolved
