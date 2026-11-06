"""Where play-mode commands may read and write.

Rules (the same hardening as the private-root guard of the Live Photos lane, implemented locally):

* No path component, given or resolved, may end in ``.photoslibrary`` (compared after Unicode NFC normalisation and case folding).
* Ancestors are compared with ``os.path.samestat``, never by spelling, so a case-variant path, a
  symlink or a hard-linked alias of the checkout cannot be mistaken for "outside".
* Output: the target must sit under this checkout's ``var/work/`` or in a location that is not
  inside any Git working tree. Any ancestor containing ``.git`` (this checkout, a sibling
  worktree, any other repository) rejects the path, except through ``var/work/`` itself.
* Input roots: a root inside a Git working tree must be ignored by Git (``git check-ignore``);
  anything else in a working tree is refused.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from tools.paths import REPO_ROOT, WORK_DIR

PHOTOS_LIBRARY_SUFFIX = ".photoslibrary"


class GuardError(SystemExit):
    """A refused path; the message never contains the path's contents."""


def _has_library_component(*paths: Path) -> bool:
    """True when any component is a ``.photoslibrary`` package name.

    Names are compared after Unicode normalisation and case folding, because the default macOS volume does the
    same: ``X.photoſlibrary`` (LATIN SMALL LETTER LONG S) opens ``X.photoslibrary`` although ``str.lower`` leaves it
    unchanged.
    """
    return any(unicodedata.normalize("NFC", part).casefold().endswith(PHOTOS_LIBRARY_SUFFIX)
               for path in paths for part in path.parts)


has_library_component = _has_library_component


def _existing_ancestors(path: Path) -> list[Path]:
    """The path itself (if it exists) and every ancestor, deepest first, that exists."""
    out = []
    for candidate in (path, *path.parents):
        if os.path.lexists(candidate):
            out.append(candidate)
    return out


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.samestat(os.stat(a), os.stat(b))
    except OSError:
        return False


def _has_git(directory: Path) -> bool:
    return os.path.lexists(directory / ".git")


def _git_tree_of(path: Path) -> Path | None:
    for ancestor in _existing_ancestors(path):
        if ancestor.is_dir() and _has_git(ancestor):
            return ancestor
    return None


def resolve_out(value: str | Path) -> Path:
    """Allow only this checkout's var/work/ or a location outside every Git working tree."""
    lexical = Path(value).expanduser().absolute()
    out = lexical.parent.resolve() / lexical.name          # the final name is never followed: a link there is replaced
    if _has_library_component(lexical, out, out.resolve()):
        raise GuardError("Refusing to write inside a Photos library package.")
    if out.suffix != ".json" or out.name.startswith("."):
        raise GuardError("--out must be a .json file path.")
    WORK_DIR.mkdir(parents=True, exist_ok=True)           # ignored by Git; lets samestat identify it
    for candidate in (out, lexical):
        for ancestor in _existing_ancestors(candidate):
            if ancestor.is_dir() and _same(ancestor, WORK_DIR):
                break
            if ancestor.is_dir() and (_has_git(ancestor) or _same(ancestor, REPO_ROOT)):
                raise GuardError("--out must stay under var/work/ or be outside every Git working tree.")
    return out


def resolve_root(value: str | Path, require_tags: bool = True) -> Path:
    """A private input root: not a Photos library, and ignored by Git when inside a working tree."""
    lexical = Path(value).expanduser().absolute()
    root = lexical.resolve()
    if _has_library_component(lexical, root):
        raise GuardError("Refusing to read from inside a Photos library package.")
    if not root.is_dir():
        raise GuardError("--root is not a directory.")
    if _same(root, REPO_ROOT):
        raise GuardError("--root must not be the checkout.")
    tree = _git_tree_of(root)
    if tree is not None and not _git_ignores(tree, root):
        raise GuardError("--root inside a Git working tree must be ignored by Git (for example under var/).")
    if require_tags and not (root / "analysis" / "tags").is_dir():
        raise GuardError("--root has no analysis/tags directory.")
    return root


def check_analysis_dirs(root: Path) -> None:
    """``analysis/``, ``analysis/tags/`` and ``analysis/index/`` (the last when present) must be real directories
    inside ``root``: never a link, never something that resolves elsewhere. A link there would feed records from
    another tree into the pool, the same bypass as a linked ``originals/``. Raises ``GuardError``."""
    base = root.resolve()
    analysis = root / "analysis"
    for part in (analysis, analysis / "tags", analysis / "index"):
        if not os.path.lexists(part):
            continue
        if os.path.islink(part) or not part.is_dir() or not Path(os.path.realpath(part)).is_relative_to(base):
            raise GuardError("analysis, analysis/tags and analysis/index must be real directories inside --root.")


def _git_environment() -> dict[str, str]:
    """The caller's environment without any ``GIT_*`` variable.

    ``GIT_DIR``, ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``, ``GIT_COMMON_DIR``, ``GIT_CEILING_DIRECTORIES``,
    ``GIT_NAMESPACE``, ``GIT_CONFIG_PARAMETERS`` and the rest could point Git at a repository (or inject a
    configuration) other than the one that holds the root, for example one whose ``info/exclude`` is ``*``.
    Every variable with the prefix is dropped rather than a list of known names, so a later Git cannot add one
    that slips through.
    """
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def _git_ignores(tree: Path, path: Path) -> bool:
    try:
        done = subprocess.run(["git", "-C", str(tree), "check-ignore", "-q", "--", str(path)],
                              capture_output=True, timeout=20, env=_git_environment())
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def write_private_file(out: Path, data: bytes, force: bool) -> None:
    """Write ``data`` to ``out`` through an exclusively created temporary file in the same directory.

    The temporary file is made with ``mkstemp`` (O_EXCL, never following a planted link) and is
    moved into place atomically. Without ``force`` an existing target (even a dangling symlink)
    is never replaced; with it, the target name itself is replaced, never written through.
    """
    if os.path.lexists(out) and not force:
        raise GuardError("output already exists; pass --force to replace it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, out)
        else:
            try:
                os.link(temporary, out)        # fails if the name appeared meanwhile: never overwrites
            except FileExistsError:
                raise
            except OSError:                    # no hard links on this filesystem: exclusive create instead
                fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
    except FileExistsError:
        raise GuardError("output already exists; pass --force to replace it.") from None
    finally:
        temporary.unlink(missing_ok=True)
