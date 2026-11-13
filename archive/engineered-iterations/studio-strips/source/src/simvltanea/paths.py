"""Resolve logical repository roles from a validated layout manifest."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
from types import MappingProxyType
import tomllib
from typing import Any, Mapping

PACKAGE_DIR = Path(__file__).resolve().parent
_GENERATED_ROLES = frozenset({"work", "samples", "renders", "site", "packages", "proofs", "artifact_output"})


def discover_root() -> Path:
    explicit = os.environ.get("SIMVLTANEA_ROOT")
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"SIMVLTANEA_ROOT is not a directory: {root}")
        return root
    for start in (PACKAGE_DIR, Path.cwd()):
        for candidate in (start, *start.parents):
            project = candidate / "pyproject.toml"
            if project.is_file():
                data = tomllib.loads(project.read_text())
                if data.get("project", {}).get("name") == "simvltanea":
                    return candidate
    # Installed packages use the caller's workspace, never site-packages, for output.
    return Path.cwd().resolve()


@dataclass(frozen=True)
class Layout:
    root: Path
    roles: Mapping[str, str]
    policy: Mapping[str, Any]
    manifest: Path
    lint: Mapping[str, Any]
    contract: Mapping[str, Any]

    def path(self, role: str) -> Path:
        path = (self.root / self.roles[role]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Layout role {role} escapes repository through a symlink")
        if role in _GENERATED_ROLES:
            boundary = (self.root / self.roles['generated']).resolve()
            if not path.is_relative_to(boundary):
                raise ValueError(f"Layout role {role} escapes generated output through a symlink")
        return path

    def relative(self, role: str) -> str:
        return self.roles[role]

    def expand(self, template: str) -> str:
        return template.format_map(self.roles)

    def generated(self, role: str, child: str = "") -> Path:
        if role not in _GENERATED_ROLES:
            raise ValueError(f"Not a generated path role: {role}")
        target = (self.path(role) / child).resolve()
        if not target.is_relative_to(self.path(role)):
            raise ValueError(f"Path escapes generated role {role}: {child}")
        return target

    def reference(self, role: str, child: str = "") -> str:
        """Physical generated-root-relative reference for receipts and links."""
        return self.generated(role, child).relative_to(self.path("generated")).as_posix()

    def policy_paths(self, name: str) -> frozenset[str]:
        return frozenset(self.expand(path) for path in self.policy[name])


def load_layout(root: Path, manifest: Path | None = None) -> Layout:
    root = root.resolve()
    explicit = os.environ.get("SIMVLTANEA_LAYOUT")
    if manifest is None and explicit:
        manifest = Path(explicit).expanduser()
    if manifest is None:
        project = root / "pyproject.toml"
        data = tomllib.loads(project.read_text()) if project.is_file() else {}
        configured = data.get("tool", {}).get("simvltanea", {}).get("layout")
        manifest = root / configured if configured else PACKAGE_DIR / "layout.toml"
    if not manifest.is_absolute():
        manifest = root / manifest
    data = tomllib.loads(manifest.read_text())
    roles = data.get("paths", {})
    required = _GENERATED_ROLES | {"generated", "examples", "fixtures", "artifact_fixture", "registry", "source", "package", "tools", "tests", "docs", "archive", "evidence", "config", "github", "editions"}
    if set(roles) != required:
        raise ValueError(f"Layout roles mismatch: missing {sorted(required-set(roles))}; unknown {sorted(set(roles)-required)}")
    for role, value in roles.items():
        if not isinstance(value, str) or not value or "\\" in value:
            raise ValueError(f"Invalid relative layout path for {role}: {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or '..' in path.parts or path.as_posix() != value or value == '.':
            raise ValueError(f"Invalid relative layout path for {role}: {value!r}")
        if not (root / value).resolve().is_relative_to(root):
            raise ValueError(f"Layout role {role} escapes repository through a symlink")
    contract = MappingProxyType(data.get("contract", {}))
    version = contract.get("version", "")
    if version:
        parts = version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"contract.version must be major.minor.patch, got: {version!r}")
    layout = Layout(root, MappingProxyType(dict(roles)), MappingProxyType(data['policy']), manifest.resolve(), MappingProxyType(data.get('lint', {})), contract)
    generated_root = layout.path('generated')
    for role in _GENERATED_ROLES:
        if not layout.path(role).is_relative_to(generated_root) or layout.path(role) == generated_root:
            raise ValueError(f"Generated role {role} must be a child of generated root")
    lane_paths = [layout.path(role) for role in _GENERATED_ROLES]
    for index, path in enumerate(lane_paths):
        if any(path.is_relative_to(other) or other.is_relative_to(path) for other in lane_paths[index+1:]):
            raise ValueError("Generated roles must have distinct, non-overlapping paths")
    for role in required - _GENERATED_ROLES - {'generated'}:
        path = layout.path(role)
        if path.is_relative_to(generated_root) or generated_root.is_relative_to(path):
            raise ValueError(f"Tracked role {role} overlaps generated output")
    for child_role, parent_role in (("registry", "editions"), ("artifact_fixture", "fixtures"), ("package", "source")):
        if not layout.path(child_role).is_relative_to(layout.path(parent_role)):
            raise ValueError(f"Layout role {child_role} must be within {parent_role}")
    top_roles = required - _GENERATED_ROLES - {'generated', 'package', 'registry', 'artifact_fixture'}
    top_paths = [(role, layout.path(role)) for role in sorted(top_roles)]
    for index, (role, path) in enumerate(top_paths):
        for other_role, other_path in top_paths[index+1:]:
            if path.is_relative_to(other_path) or other_path.is_relative_to(path):
                raise ValueError(f"Tracked roles {role} and {other_role} overlap")
    # Resolve every placement template now so typos fail before any command writes.
    for value in layout.policy.values():
        for template in value if isinstance(value,list) else value.keys():
            layout.expand(template)
    return layout


REPO_ROOT = discover_root()
LAYOUT = load_layout(REPO_ROOT)
SRC_DIR = LAYOUT.path('source')
EXAMPLES_DIR = LAYOUT.path('examples')
FIXTURES_DIR = LAYOUT.path('fixtures')
ARTIFACT_FIXTURE_DIR = LAYOUT.path('artifact_fixture')
EDITIONS_FILE = LAYOUT.path('registry')
VAR_DIR = LAYOUT.path('generated')
WORK_DIR = LAYOUT.path('work')
SAMPLES_DIR = LAYOUT.path('samples')
RENDERS_DIR = LAYOUT.path('renders')
SITE_DIR = LAYOUT.path('site')
PACKAGES_DIR = LAYOUT.path('packages')
PROOFS_DIR = LAYOUT.path('proofs')
ARTIFACT_OUTPUT_DIR = LAYOUT.path('artifact_output')


def lane_ref(role: str, child: str = "") -> str:
    return LAYOUT.reference(role, child)


def resolve_references(value: Any) -> Any:
    """Expand @role/path configuration references to absolute paths.

    Ordinary relative media paths retain their document-relative meaning.
    """
    if isinstance(value, str) and value.startswith('@'):
        role, _, child = value[1:].partition('/')
        if role not in LAYOUT.roles:
            raise ValueError(f"Unknown layout reference: {value}")
        base = LAYOUT.path(role)
        target = (base / child).resolve()
        if not target.is_relative_to(base):
            raise ValueError(f"Layout reference escapes {role}: {value}")
        return str(target)
    if isinstance(value, list):
        return [resolve_references(item) for item in value]
    if isinstance(value, dict):
        return {key:resolve_references(item) for key,item in value.items()}
    return value


def in_var(path: Path) -> bool:
    return path.resolve().is_relative_to(VAR_DIR)


def require_in_var(path: Path, label: str = "output") -> Path:
    resolved = path.expanduser().resolve()
    if not in_var(resolved):
        raise ValueError(f"{label} must stay inside {VAR_DIR}")
    return resolved
