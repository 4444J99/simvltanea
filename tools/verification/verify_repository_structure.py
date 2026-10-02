#!/usr/bin/env python3
"""Enforce SIMVLTANEA's Git-visible repository layout without changing files."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.paths import LAYOUT, REPO_ROOT, Layout, load_layout

ROOT = REPO_ROOT


def policy_values(layout: Layout) -> dict:
    result = {}
    for name, values in layout.policy.items():
        if isinstance(values, dict):
            result[name.upper()] = {layout.expand(key): frozenset(items) for key, items in values.items()}
        else:
            result[name.upper()] = layout.policy_paths(name)
    return result


# Public policy aliases preserve existing callers; verification resolves --root separately.
globals().update(policy_values(LAYOUT))

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


def is_generated_path(path: str, layout: Layout = LAYOUT) -> bool:
    """Classify output using the same configured roles as command defaults."""
    policy = policy_values(layout)
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    if ".DS_Store" in parts or "__pycache__" in parts:
        return True
    if path in policy["ALLOWED_LANE_PLACEHOLDERS"]:
        return False
    for base in policy["GENERATED_LANES"] | policy["LOCAL_ONLY_ROOTS"] | policy["PROOF_OUTPUT_DIRECTORIES"]:
        if path == base or path.startswith(base + "/"):
            return True
    fixture = layout.relative("artifact_fixture")
    if path == fixture or path.startswith(fixture + "/"):
        return path not in policy["ARTIFACT_BASELINE_FILES"]
    raw = layout.relative("archive") + "/raw"
    if path == raw or path.startswith(raw + "/"):
        return path not in policy["RAW_INTAKE_FILES"]
    # Reject misplaced output trees as well as configured output locations.
    lane_names = {PurePosixPath(layout.relative(role)).name for role in
                  ("work", "samples", "renders", "site", "packages", "proofs", "artifact_output")}
    lane_names |= {"work", "samples", "renders", "site", "packages", "runtime-proof"}
    for role in ("source", "tools"):
        base = layout.relative(role)
        if path.startswith(base + "/") and any(part in lane_names for part in
                                                PurePosixPath(path[len(base)+1:]).parts[:-1]):
            return True
    return False


def path_violation(path: str, layout: Layout = LAYOUT) -> str | None:
    """Check placement; spelling and case remain governed by ls-lint."""
    policy = policy_values(layout)
    if is_generated_path(path, layout):
        return "generated/local-only path must stay out of Git; see docs/governance/STRUCTURE.md"
    entry = PurePosixPath(path)
    parts = entry.parts
    if len(parts) == 1:
        if path in policy["APPROVED_ROOT_FILES"]:
            return None
        return "unapproved root file; use an approved folder or update the policy"
    area = parts[0]
    if not any(path.startswith(base + "/") for base in policy["APPROVED_ROOT_DIRECTORIES"]):
        return "unapproved root directory; update the policy for an intentional addition"
    if path in policy["ALLOWED_LANE_PLACEHOLDERS"] or path in policy["ARTIFACT_BASELINE_FILES"]:
        return None
    if path.startswith(layout.relative("config") + "/"):
        return None if path in policy["CONFIG_FILES"] else "config/ allows documented lint configuration files"
    if path.startswith(layout.relative("editions") + "/"):
        return None if path == layout.relative("registry") or path == layout.relative("editions") + "/README.md" else "editions/ allows the production registry and its guide"
    source_role = next((base for base in policy["SOURCE_EXTENSIONS"] if path.startswith(base + "/")), None)
    if source_role is not None:
        area = source_role
    if area in policy["SOURCE_EXTENSIONS"]:
        if path in policy["SOURCE_FILE_EXCEPTIONS"] or entry.suffix in policy["SOURCE_EXTENSIONS"][area]:
            return None
        extensions = ", ".join(sorted(policy["SOURCE_EXTENSIONS"][area]))
        return f"{area}/ allows {extensions} files; put other material in its approved area"
    for role, logical in (("tests", "tests"), ("docs", "docs"), ("github", ".github"),
                          ("archive", "archive"), ("evidence", "evidence"),
                          ("config", "config"), ("editions", "editions")):
        base = layout.relative(role)
        if path.startswith(base + "/"):
            area = logical
            parts = (logical, *PurePosixPath(path[len(base)+1:]).parts)
            break
    if area == "tests":
        if entry.suffix == ".md":
            return None
        if entry.suffix == ".py" and (
            entry.name.startswith("test_") or entry.name in policy["TEST_PYTHON_EXCEPTIONS"]
        ):
            return None
        return "tests/ allows test_*.py, __init__.py, conftest.py, and Markdown"
    if area == "docs":
        if path in policy.get("DOCUMENTATION_FILE_EXCEPTIONS", frozenset()):
            return None
        if len(parts) > 2 and parts[1] not in policy["DOC_SUBDIRECTORIES"]:
            return "docs/ subdirectories must be documented topic groups"
        if entry.suffix == ".md":
            return None
        return "active documentation must be Markdown; historical records belong in archive/incubation/"
    if area == ".github":
        if path in policy["GOVERNANCE_FILES"]:
            return None
        if len(parts) == 2 and entry.suffix == ".md":
            return None
        if len(parts) >= 3 and parts[1] in policy["GITHUB_FOLDER_EXTENSIONS"]:
            if (len(parts) == 3 or parts[1] == "instructions") and (
                entry.suffix in policy["GITHUB_FOLDER_EXTENSIONS"][parts[1]]
            ):
                return None
        return ".github/ allows root Markdown, workflow YAML, issue templates, and instruction Markdown"
    if area == ".vscode":
        if len(parts) == 2 and entry.suffix == ".json":
            return None
        return ".vscode/ allows JSON configuration files directly inside the folder"
    if area == "archive":
        if len(parts) >= 3 and parts[1] == "incubation":
            return None
        if path == layout.relative("archive") + "/PROJECT_MANIFEST.md" or path in policy["RAW_INTAKE_FILES"]:
            return None
        if path == layout.relative("archive") + "/chatgpt/README.md":
            return None
        if len(parts) >= 4 and parts[1] == "chatgpt" and parts[2] in policy["ARCHIVE_CATEGORIES"]:
            return None
        return "archive/ material belongs in a documented archive/chatgpt/ category"
    if area == "evidence":
        if path in policy["PROOF_FILES"]:
            return None
        if (
            len(parts) >= 4 and parts[1:3] == ("visual-proof", "frames")
            and entry.suffix == ".png"
        ):
            return None
        return "evidence/ allows visual-proof/README.md, ledger.json, and frames/*.png"
    return "path is outside the approved folder role; see docs/governance/STRUCTURE.md"


def verify_structure(root: Path) -> list[tuple[str, str]]:
    """Validate the index and Git-visible additions against the worktree layout."""
    root = root.resolve()
    layout = load_layout(root)
    policy = policy_values(layout)
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
        message = path_violation(path, layout)
        if message:
            violations.append((path, message))
    for path in policy["REQUIRED_FILES"]:
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
    for path in policy["REQUIRED_DIRECTORIES"]:
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
    except (OSError, RuntimeError, ValueError, KeyError) as error:
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
