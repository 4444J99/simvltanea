"""Resolve and verify the shared audiovisual engine this composition executes.

The shared engine is **owned and versioned by time-moment-brief**. This module
consumes it; it never carries a copy and never edits it.

Two independent things must hold before any frame is presented, and neither is
optional:

1. **Resolution is deterministic and portable.** The engine is found at one
   documented location: a sibling checkout named ``time-moment-brief`` beside
   this repository, or beside its parent when this repository is itself a
   worktree. There is no environment override, no ancestor-wide search that could
   land on an unrelated copy, and no hardcoded workstation path. If the checkout
   lives somewhere else, move it or create that sibling link -- configuration is
   not a dependency resolution strategy.

2. **The bytes are the accepted bytes.** ``shared_engine_pin.json`` records the
   accepted entrypoint digest, the accepted release commit, and a digest for every
   file in the executable graph. All of them are checked. A manifest that omits
   the entrypoint, an empty graph, an altered module, or a checkout whose HEAD
   does not contain the accepted commit is a refusal, not a warning.

To relocate the engine, move the checkout. To change which implementation runs,
review and re-pin. Never to make a failure go away.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROVENANCE_RELATIVE = Path('shared-engine') / 'PROVENANCE.json'
PIN_NAME = 'shared_engine_pin.json'
# The documented relative layout. A bare name, resolved against the checkout and
# its parent -- not a path from any particular machine.
OWNER_DIRECTORY = 'time-moment-brief'
# The consumer must see this file; a graph without it means an entrypoint that was
# never verified, which is the exact case a manifest-only check used to accept.
ENTRYPOINT = 'shared-engine/index.js'


class SharedEngineUnavailable(RuntimeError):
    """The shared engine could not be resolved, or what was found is not the accepted build."""


@dataclass(frozen=True)
class SharedEngine:
    """A verified, digest-pinned handle on the accepted shared engine."""

    root: Path
    module_root: Path
    provenance: dict
    pin: dict
    digests: dict
    git_commit: str | None
    owner_directory: str

    @property
    def entrypoint(self) -> Path:
        return self.module_root / 'index.js'

    @property
    def release(self) -> str | None:
        return self.git_commit

    def read(self, relative: str) -> str:
        """Read a repository-relative path, e.g. 'shared-engine/index.js'."""
        return (self.root / relative).read_text(encoding='utf-8')

    def describe(self) -> dict:
        """Redacted handle for receipts. Repository-relative; no personal paths.

        Absolute paths belong in a local run log, not in a tracked receipt, so this
        is the shape a receipt should record.
        """
        return {
            'module': 'time-moment-brief/shared-engine',
            'entrypoint': ENTRYPOINT,
            'release': self.git_commit,
            'runtime_graph': dict(sorted(self.pin['runtime_graph'].items())),
        }

    def verify(self) -> dict:
        """Re-run every check. Returns a receipt; raises on any failure."""
        mismatches = []
        for relative, expected in sorted(self.pin['runtime_graph'].items()):
            target = self.module_root / Path(relative).relative_to('shared-engine')
            if not target.is_file():
                mismatches.append(f'{relative}: absent')
            elif _sha256(target) != expected:
                mismatches.append(f'{relative}: sha256 {_short(_sha256(target))} != accepted {_short(expected)}')
        if mismatches:
            raise SharedEngineUnavailable(
                'shared engine no longer matches the accepted build:\n  '
                + '\n  '.join(mismatches)
                + '\nThis checkout was edited after acceptance. Re-pin deliberately; '
                  'do not silently adopt it.')
        return {
            'module': 'time-moment-brief/shared-engine',
            'release': self.git_commit,
            'files_verified': len(self.digests),
            'entrypoint': ENTRYPOINT,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _short(digest: str) -> str:
    return digest[:12]


def _load_json(path: Path, what: str) -> dict:
    if not path.is_file():
        raise SharedEngineUnavailable(
            f'{what} is absent at {path.name}. This composition has no local copy of '
            f'the shared engine and cannot proceed without it.')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise SharedEngineUnavailable(
            f'{path.name} is not readable JSON ({error}). A malformed manifest is a '
            f'refusal, not an empty verification.') from error


def load_pin() -> dict:
    """The consumer's own record of which build it accepts."""
    pin = _load_json(HERE / PIN_NAME, 'the accepted shared-engine pin')
    graph = pin.get('runtime_graph')
    if not isinstance(graph, dict) or not graph:
        raise SharedEngineUnavailable(
            f'{PIN_NAME} records no runtime graph. An empty graph would verify '
            f'nothing while appearing to pass, so it is refused.')
    if ENTRYPOINT not in graph:
        raise SharedEngineUnavailable(
            f'{PIN_NAME} omits the runtime entrypoint {ENTRYPOINT}. Consumers verify '
            f'the whole executable graph; an unverified entrypoint can hand out any '
            f'implementation it likes.')
    if pin.get('entrypoint') != ENTRYPOINT:
        raise SharedEngineUnavailable(
            f'{PIN_NAME} declares entrypoint {pin.get("entrypoint")!r}, expected '
            f'{ENTRYPOINT!r}.')
    release = pin.get('release') or {}
    if not release.get('commit'):
        raise SharedEngineUnavailable(
            f'{PIN_NAME} pins no release commit. A pin without a version cannot '
            f'reject a stale checkout.')
    return pin


def repository_root(start: Path = HERE) -> Path:
    """The checkout root, found by walking up to the project marker.

    Resolved from this file rather than assumed to be three levels up, so the
    layout survives the package moving and works identically for a plain checkout
    and for a worktree.
    """
    for base in [start.resolve(), *start.resolve().parents]:
        if (base / 'pyproject.toml').is_file():
            return base
    return start.resolve().parents[2]


def candidate_roots(start: Path = HERE):
    """Yield the documented sibling locations only, nearest first.

    Deliberately not an ancestor-wide scan. An earlier version walked six levels
    up and accepted anything it found, so a stray checkout in a grandparent
    directory could supply the implementation while every real one failed, and a
    hardcoded worktree name was needed to reach the real one at all.
    """
    root = repository_root(start)
    for base in (root, root.parent, root.parent.parent):
        yield base / OWNER_DIRECTORY


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_contains(root: Path, commit: str) -> bool:
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, 'HEAD'],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _verify_graph(module_root: Path, pin: dict) -> dict:
    """Hash every pinned file. All must match; partial verification is a refusal."""
    digests, mismatches = {}, []
    for relative, expected in sorted(pin['runtime_graph'].items()):
        inner = Path(relative).relative_to('shared-engine')
        target = module_root / inner
        # A pin path that escapes the module is a malformed pin, not a file to read.
        if not str(target.resolve()).startswith(str(module_root.resolve()) + '/'):
            raise SharedEngineUnavailable(
                f'pinned path {relative} escapes the shared-engine module.')
        if not target.is_file():
            mismatches.append(f'{relative}: absent')
            continue
        actual = _sha256(target)
        digests[relative] = actual
        if actual != expected:
            mismatches.append(f'{relative}: sha256 {_short(actual)} != accepted {_short(expected)}')
    if mismatches:
        raise SharedEngineUnavailable(
            'shared engine does not match the accepted build:\n  '
            + '\n  '.join(mismatches)
            + '\nRepair by reviewing the divergence and re-pinning, not by editing this '
              'consumer and not by copying the module here.')
    return digests


def _verify_provenance(provenance: dict, pin: dict) -> None:
    """The owner's manifest must agree with this consumer's pin, and be complete."""
    graph = provenance.get('runtime_graph')
    if not isinstance(graph, dict) or not graph:
        raise SharedEngineUnavailable(
            'the owner manifest records no runtime graph. Refusing to treat an '
            'incomplete manifest as verified.')
    if provenance.get('entrypoint') != ENTRYPOINT:
        raise SharedEngineUnavailable(
            f'the owner manifest declares entrypoint {provenance.get("entrypoint")!r}, '
            f'expected {ENTRYPOINT!r}.')
    # Completeness first, then agreement. A manifest missing a pinned file is
    # incomplete, not merely different, and conflating the two would report a
    # digest mismatch for a file the owner never claimed to hash.
    incomplete = sorted(set(pin['runtime_graph']) - set(graph))
    if incomplete:
        raise SharedEngineUnavailable(
            'the owner manifest does not cover the full executable graph:\n'
            + '\n'.join(f'  {rel}: not recorded' for rel in incomplete)
            + '\nA manifest that omits a file this consumer pins cannot be checked '
              'against it.')
    disagree = [
        f'  {rel}: owner {_short(graph[rel])} != this consumer {_short(mine)}'
        for rel, mine in sorted(pin['runtime_graph'].items())
        if graph[rel] != mine
    ]
    if disagree:
        raise SharedEngineUnavailable(
            'the owner manifest and this consumer disagree about the shared engine:\n'
            + '\n'.join(disagree)
            + '\nOne side is stale. Re-pin deliberately; do not accept whichever copy '
              'happened to be found.')


def resolve_shared_engine(start: Path = HERE, pin: dict | None = None) -> SharedEngine:
    """Resolve, verify and pin-check the shared engine, or raise with what was tried."""
    pin = pin or load_pin()
    searched = []
    found = []
    for candidate in candidate_roots(start):
        searched.append(str(candidate))
        manifest = candidate / PROVENANCE_RELATIVE
        if not manifest.is_file():
            continue
        provenance = _load_json(manifest, 'the owner provenance record')
        module_root = candidate / 'shared-engine'
        digests = _verify_graph(module_root, pin)
        _verify_provenance(provenance, pin)
        commit = _git_commit(candidate)
        pinned = pin['release']['commit']
        if commit is None:
            raise SharedEngineUnavailable(
                f'{candidate} is not a readable git checkout, so its release cannot be '
                f'checked against the accepted commit {pinned[:12]}. A checkout of '
                f'unknown vintage is not an accepted release.')
        if not _git_contains(candidate, pinned):
            raise SharedEngineUnavailable(
                f'{candidate} is at {commit[:12]}, which does not contain the accepted '
                f'release {pinned[:12]}. The engine is stale; check out the accepted '
                f'release rather than re-pinning to whatever is present.')
        found.append(SharedEngine(
            root=candidate, module_root=module_root, provenance=provenance, pin=pin,
            digests=digests, git_commit=commit, owner_directory=candidate.name))

    if not found:
        raise SharedEngineUnavailable(
            'shared engine not found. This composition executes '
            'time-moment-brief/shared-engine in place and has no local copy. Looked at '
            'the documented sibling layout only:\n  '
            + '\n  '.join(searched)
            + '\nPlace the time-moment-brief checkout beside this repository, or beside '
              'its parent, and check out the accepted release.')
    if len(found) > 1:
        raise SharedEngineUnavailable(
            'the shared engine resolves ambiguously to '
            + ', '.join(str(handle.root) for handle in found)
            + '. Two owners would mean two implementations. Keep exactly one '
              'time-moment-brief checkout in the documented location.')
    return found[0]