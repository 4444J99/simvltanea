#!/usr/bin/env python3
"""Enforce SIMVLTANEA's Git-visible repository layout without changing files."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]

# Change these policy tables in the same PR as an intentional layout change.
GENERATED_LANES = frozenset({"var"})
ALLOWED_LANE_PLACEHOLDERS = frozenset({"var/.gitkeep"})
ARTIFACT_BASELINE_FILES = frozenset({
    "fixtures/artifact-001/baseline-manifest.json",
    "fixtures/artifact-001/baseline/render_triptych.original.py",
})
RAW_INTAKE_FILES = frozenset({
    "archive/raw/.gitkeep",
    "archive/raw/README.md",
    "archive/raw/PR9_review_proof_2026-09-06/README.md",
})
LOCAL_ONLY_ROOTS = frozenset({"var", ".venv", ".pytest_cache"})
PROOF_OUTPUT_DIRECTORIES = frozenset({
    "evidence/visual-proof/media",
    "evidence/visual-proof/renders",
})

APPROVED_ROOT_DIRECTORIES = frozenset({
    ".github", ".vscode", "archive", "docs", "evidence", "examples",
    "fixtures", "src", "tests", "tools", "var",
}) | GENERATED_LANES
APPROVED_ROOT_FILES = frozenset({
    ".gitignore", ".ls-lint.yml", ".markdownlint.json", ".markdownlintignore",
    "CODEOWNERS",
    "CONTRIBUTING.md", "LICENSE", "README.md", "SECURITY.md",
    "editions.json", "pyproject.toml", "pytest.ini", "requirements.txt",
})
REQUIRED_FILES = (
    APPROVED_ROOT_FILES | ALLOWED_LANE_PLACEHOLDERS | ARTIFACT_BASELINE_FILES
) | frozenset({
    ".github/workflows/ci.yml",
    "src/simvltanea/__init__.py",
    "src/simvltanea/README.md",
    "tools/README.md",
    "tools/editions/__init__.py",
    "tools/media/__init__.py",
    "tools/preservation/__init__.py",
    "tools/publishing/__init__.py",
    "tools/verification/__init__.py",
    "tests/README.md",
    "examples/README.md",
    "docs/NAMING.md",
    "docs/BRANCHES.md",
    "docs/STATUS.md",
    "docs/STRUCTURE.md",
    "docs/historical/README.md",
    "docs/plans/INDEX.md",
    "archive/PROJECT_MANIFEST.md",
    "archive/chatgpt/README.md",
    "archive/raw/README.md",
    "evidence/visual-proof/README.md",
    "evidence/visual-proof/ledger.json",
})
REQUIRED_DIRECTORIES = (APPROVED_ROOT_DIRECTORIES - {".vscode"}) | frozenset({
    "archive/chatgpt", "archive/raw", "fixtures/artifact-001/baseline",
    "src/simvltanea", "tools/editions", "tools/media", "tools/preservation",
    "tools/publishing", "tools/verification",
    "docs/plans", "docs/historical", "evidence/visual-proof",
    "evidence/visual-proof/frames",
})

SOURCE_EXTENSIONS = {
    "src": frozenset({".py", ".js", ".md", ".typed"}),
    "tools": frozenset({".py", ".md"}),
    "examples": frozenset({".json", ".md"}),
}
SOURCE_FILE_EXCEPTIONS = frozenset({"src/simvltanea/layouts.json"})
TEST_PYTHON_EXCEPTIONS = frozenset({"__init__.py", "conftest.py"})
DOC_SUBDIRECTORIES = frozenset({"plans", "historical"})
GITHUB_FOLDER_EXTENSIONS = {
    "workflows": frozenset({".yml", ".yaml"}),
    "ISSUE_TEMPLATE": frozenset({".md", ".yml", ".yaml"}),
    "instructions": frozenset({".md"}),
}
ARCHIVE_CATEGORIES = frozenset({
    "threads", "handoffs", "receipts", "research", "evidence", "logs",
    "media", "bundles", "sessions", "prompts", "extracts",
})
PROOF_FILES = frozenset({
    "evidence/visual-proof/README.md", "evidence/visual-proof/ledger.json",
})


def run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(os.fsdecode(result.stderr).strip() or "git command failed")
    return result.stdout


def git_paths(root: Path, *args: str) -> list[str]:
    """Read Git filenames without quoting, newline splitting, or Unicode loss."""
    output = run_git(root, args[0], "-z", *args[1:])
    return [os.fsdecode(path) for path in output.split(b"\0") if path]


def is_generated_path(path: str) -> bool:
    """Shared structure/lifecycle boundary for generated or local-only paths."""
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    if ".DS_Store" in parts or "__pycache__" in parts:
        return True
    if parts[0] in {"tools", "src", "core"} and any(
        part in {"work", "samples", "renders", "site", "packages", "runtime-proof"}
        for part in parts[1:-1]
    ):
        return True
    if parts[0] in GENERATED_LANES:
        return path not in ALLOWED_LANE_PLACEHOLDERS
    if parts[0] in LOCAL_ONLY_ROOTS:
        return True
    if parts[0] == "fixtures" and parts[:2] == ("fixtures", "artifact-001"):
        return path not in ARTIFACT_BASELINE_FILES
    if parts[:2] == ("archive", "raw"):
        return path not in RAW_INTAKE_FILES
    return any(
        path == directory or path.startswith(f"{directory}/")
        for directory in PROOF_OUTPUT_DIRECTORIES
    )


def path_violation(path: str) -> str | None:
    """Check placement; spelling and case remain governed by ls-lint."""
    if is_generated_path(path):
        return "generated/local-only path must stay out of Git; see docs/STRUCTURE.md"
    entry = PurePosixPath(path)
    parts = entry.parts
    if len(parts) == 1:
        if path in APPROVED_ROOT_FILES:
            return None
        return "unapproved root file; use an approved folder or update the policy"
    area = parts[0]
    if area not in APPROVED_ROOT_DIRECTORIES:
        return "unapproved root directory; update the policy for an intentional addition"
    if path in ALLOWED_LANE_PLACEHOLDERS or path in ARTIFACT_BASELINE_FILES:
        return None
    if area in SOURCE_EXTENSIONS:
        if path in SOURCE_FILE_EXCEPTIONS or entry.suffix in SOURCE_EXTENSIONS[area]:
            return None
        extensions = ", ".join(sorted(SOURCE_EXTENSIONS[area]))
        return f"{area}/ allows {extensions} files; put other material in its approved area"
    if area == "tests":
        if entry.suffix == ".md":
            return None
        if entry.suffix == ".py" and (
            entry.name.startswith("test_") or entry.name in TEST_PYTHON_EXCEPTIONS
        ):
            return None
        return "tests/ allows test_*.py, __init__.py, conftest.py, and Markdown"
    if area == "docs":
        if len(parts) > 2 and parts[1] not in DOC_SUBDIRECTORIES:
            return "docs/ subdirectories must be plans/ or historical/"
        if len(parts) > 2 and parts[1] == "historical":
            return None
        if entry.suffix == ".md":
            return None
        return "active documentation must be Markdown; historical records belong in docs/historical/"
    if area == ".github":
        if len(parts) == 2 and entry.suffix == ".md":
            return None
        if len(parts) >= 3 and parts[1] in GITHUB_FOLDER_EXTENSIONS:
            if (len(parts) == 3 or parts[1] == "instructions") and (
                entry.suffix in GITHUB_FOLDER_EXTENSIONS[parts[1]]
            ):
                return None
        return ".github/ allows root Markdown, workflow YAML, issue templates, and instruction Markdown"
    if area == ".vscode":
        if len(parts) == 2 and entry.suffix == ".json":
            return None
        return ".vscode/ allows JSON configuration files directly inside the folder"
    if area == "archive":
        if path == "archive/PROJECT_MANIFEST.md" or path in RAW_INTAKE_FILES:
            return None
        if path == "archive/chatgpt/README.md":
            return None
        if len(parts) >= 4 and parts[1] == "chatgpt" and parts[2] in ARCHIVE_CATEGORIES:
            return None
        return "archive/ material belongs in a documented archive/chatgpt/ category"
    if area == "evidence":
        if path in PROOF_FILES:
            return None
        if (
            len(parts) >= 4 and parts[1:3] == ("visual-proof", "frames")
            and entry.suffix == ".png"
        ):
            return None
        return "evidence/ allows visual-proof/README.md, ledger.json, and frames/*.png"
    return "path is outside the approved folder role; see docs/STRUCTURE.md"


def verify_structure(root: Path) -> list[tuple[str, str]]:
    """Validate the index and Git-visible additions against the worktree layout."""
    root = root.resolve()
    if run_git(root, "rev-parse", "--is-inside-work-tree") != b"true\n":
        raise RuntimeError("--root must name a Git worktree")
    if run_git(root, "rev-parse", "--show-prefix") != b"\n":
        raise RuntimeError("--root must name the Git worktree root")
    paths = set(git_paths(root, "ls-files", "--cached")) | set(
        git_paths(root, "ls-files", "--others", "--exclude-standard")
    )
    staged_deletions = set(git_paths(
        root, "diff", "--cached", "--no-renames", "--diff-filter=D", "--name-only",
    ))
    violations = []
    directories = {
        parent.as_posix()
        for path in paths
        for parent in PurePosixPath(path).parents
        if parent != PurePosixPath(".")
    }

    for path in paths:
        message = path_violation(path)
        if message:
            violations.append((path, message))
    for path in REQUIRED_FILES:
        if path in staged_deletions:
            violations.append((path, "required file is staged for deletion; restore it to the index"))
            continue
        if path not in paths:
            violations.append((path, "required file is missing from Git-visible paths"))
            continue
        try:
            mode = (root / path).lstat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            violations.append((path, "required file is missing from the working tree"))
        else:
            if not stat.S_ISREG(mode):
                violations.append((path, "required path must be a regular file"))
    for path in REQUIRED_DIRECTORIES:
        if path not in directories:
            violations.append((path, "required directory needs Git-visible children"))
            continue
        try:
            mode = (root / path).lstat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            violations.append((path, "required directory is missing from the working tree"))
        else:
            if not stat.S_ISDIR(mode):
                violations.append((path, "required path must be a real directory"))
    return sorted(violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=ROOT,
        help="Git worktree root to verify (default: this repository)",
    )
    args = parser.parse_args(argv)
    try:
        violations = verify_structure(args.root)
    except (OSError, RuntimeError) as error:
        print(f"repository structure error: {error}", file=sys.stderr)
        return 2
    if violations:
        print("Repository structure check failed:")
        for path, message in violations:
            print(f"- {path!r}: {message}")
        return 1
    print("repository structure ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
