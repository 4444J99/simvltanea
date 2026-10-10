"""Resolve and verify the shared audiovisual engine consumed by this composition.

`time-moment-brief/shared-engine/` is the single source home for the 360
timeline and projection core. This module resolves it **relative to the
checkout**, not through an environment variable: a path that a caller can point
anywhere is configuration, not reuse, and would let a divergent copy pass
silently.

Resolution walks up from this file looking for a sibling checkout whose
`shared-engine/PROVENANCE.json` is present and whose every recorded digest
matches the bytes on disk. Anything less raises. There is no fallback and no
degraded mode: a composition that cannot prove which implementation it is
running has no business presenting a frame.

To relocate the engine, move the checkout, not the configuration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROVENANCE_NAME = 'shared-engine/PROVENANCE.json'
SIBLINGS_NAME = 'shared-engine.siblings.json'
SEARCH_DEPTH = 6
MODULES = ('index.js', 'src/spatial-score.js', 'src/panoramic-projection.js',
           'src/video-texture.js')
# Checked in alongside this module. This selects *which sibling checkout* to read,
# never *which implementation*: every candidate is verified byte-for-byte against
# the extractor's PROVENANCE.json before it is accepted. Relocating the engine
# means moving a checkout and naming it here, not changing what the code does.
SIBLINGS = ('time-moment-brief', '.wt-agent7-shared-engine')


class SharedEngineUnavailable(RuntimeError):
    """The shared engine could not be resolved, or its bytes are not the recorded ones."""


@dataclass(frozen=True)
class SharedEngine:
    """A verified, checkout-relative handle on the shared engine module."""

    root: Path
    module_root: Path
    provenance: dict
    digests: dict[str, str]

    @property
    def entrypoint(self) -> Path:
        return self.module_root / 'index.js'

    def read(self, relative: str) -> str:
        """Read a repository-relative path, e.g. 'shared-engine/index.js'."""
        return (self.root / relative).read_text(encoding='utf-8')

    def describe(self) -> dict:
        """Redacted handle for receipts: repository-relative, no personal paths."""
        return {
            'module': 'time-moment-brief/shared-engine',
            'digests': dict(sorted(self.digests.items())),
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_roots(start: Path = HERE, depth: int = SEARCH_DEPTH):
    """Yield checkout-relative candidates, nearest first.

    At each ancestor of this file we look for a sibling checkout holding
    `shared-engine/PROVENANCE.json`. Symlinks are resolved so a worktree and its
    main checkout resolve to the same bytes.
    """
    current = start.resolve()
    for _ in range(depth + 1):
        yield current / PROVENANCE_NAME
        for sibling in SIBLINGS:
            yield current / sibling / PROVENANCE_NAME
        if current.parent == current:
            return
        current = current.parent


def _load(path: Path) -> SharedEngine:
    provenance = json.loads(path.read_text(encoding='utf-8'))
    module_root = path.parent           # .../time-moment-brief/shared-engine
    root = module_root.parent            # .../time-moment-brief  (paths are repo-relative)
    mismatches, digests = [], {}
    for entry in provenance.get('files', []):
        generated = entry['generated']
        target = root / generated
        if not target.is_file():
            mismatches.append(f'{generated}: absent')
            continue
        actual = _sha256(target)
        digests[generated] = actual
        if actual != entry['generated_sha256']:
            mismatches.append(
                f"{generated}: sha256 {actual[:12]} != recorded {entry['generated_sha256'][:12]}")
    if mismatches:
        raise SharedEngineUnavailable(
            'shared engine provenance mismatch at ' + str(root) + ':\n  '
            + '\n  '.join(mismatches)
            + '\nRe-stage from the source of record with '
              'time-moment-brief: python3 tools/stage_shared_engine.py')
    missing = [m for m in MODULES if not (module_root / m).is_file()]
    if missing:
        raise SharedEngineUnavailable(
            f'shared engine at {module_root} is missing required modules: '
            + ', '.join(missing))
    return SharedEngine(root=root, module_root=module_root,
                       provenance=provenance, digests=digests)


def resolve_shared_engine(start: Path = HERE) -> SharedEngine:
    """Resolve and verify the shared engine, or raise with the paths searched."""
    searched = []
    for candidate in candidate_roots(start):
        searched.append(str(candidate))
        if candidate.is_file():
            return _load(candidate)
    raise SharedEngineUnavailable(
        'shared engine not found. This composition consumes '
        'time-moment-brief/shared-engine in place and has no local copy. Searched:\n  '
        + '\n  '.join(searched)
        + '\nRestore the time-moment-brief checkout beside this one, or re-run from a '
          'workspace that contains both.')
