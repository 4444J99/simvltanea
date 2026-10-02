"""Reject imports that bypass another feature's public package API."""
from __future__ import annotations
import ast
from pathlib import Path
from tools.paths import REPO_ROOT

FEATURES = frozenset({"authoring", "browser", "rendering", "generators"})


def violations(source: str, owner: str | None = None) -> list[tuple[int, str]]:
    errors = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.ImportFrom):
            if node.level:
                # Same-feature relative imports are implementation details.
                if node.level == 1 and owner in FEATURES:
                    continue
                if node.level == 2 and owner in FEATURES:
                    names = ["simvltanea." + (node.module or "")]
                else:
                    continue
            else:
                names = [node.module or ""]
        elif isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        for name in names:
            parts = name.split(".")
            if len(parts) > 2 and parts[0] == "simvltanea" and parts[1] in FEATURES and parts[1] != owner:
                errors.append((node.lineno, f"import {'.'.join(parts[:2])} through its public API"))
    return errors


def verify(root: Path = REPO_ROOT) -> list[str]:
    errors = []
    for base in (root / "src" / "simvltanea", root / "tools"):
        for path in sorted(base.rglob("*.py")):
            if path.name.startswith("test_") or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            owner = path.parent.name if path.is_relative_to(root / "src" / "simvltanea") else None
            errors.extend(f"{relative}:{line}: {message}" for line, message in violations(path.read_text(), owner))
    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("\n".join(errors))
        return 1
    print("feature import boundaries ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
