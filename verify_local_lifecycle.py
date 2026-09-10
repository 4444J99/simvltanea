#!/usr/bin/env python3
"""Verify that generated triptych lanes are not leaking into Git review.

This is a local lifecycle gate, not a product verifier. It checks the shape of
the worktree so generated media, build packages, Finder metadata, and Python
cache files do not silently inflate the local diff again.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

GENERATED_LANES = {
    "packages",
    "renders",
    "samples",
    "site",
    "work",
}

ALLOWED_LANE_PLACEHOLDERS = {
    f"{lane}/.gitkeep" for lane in GENERATED_LANES
}


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def incubator_relative(repo_path: str) -> str | None:
    prefix = f"{ROOT.relative_to(REPO)}/"
    if not repo_path.startswith(prefix):
        return None
    return repo_path[len(prefix) :]


def visible_untracked_paths() -> list[str]:
    output = run_git("ls-files", "--others", "--exclude-standard", str(ROOT.relative_to(REPO)))
    return [line for line in output.splitlines() if line]


def visible_modified_paths() -> list[str]:
    output = run_git("diff", "--name-only", "--", str(ROOT.relative_to(REPO)))
    return [line for line in output.splitlines() if line]


def visible_staged_paths() -> list[str]:
    output = run_git("diff", "--cached", "--name-only", "--", str(ROOT.relative_to(REPO)))
    return [line for line in output.splitlines() if line]


def visible_status_entries() -> list[str]:
    output = run_git(
        "status",
        "--porcelain=v1",
        "-uall",
        "--",
        str(ROOT.relative_to(REPO)),
    )
    return [line for line in output.splitlines() if line]


def is_generated_leak(repo_path: str) -> bool:
    rel = incubator_relative(repo_path)
    if rel is None:
        return False
    parts = Path(rel).parts
    if not parts:
        return False
    if rel in ALLOWED_LANE_PLACEHOLDERS:
        return False
    if parts[0] in GENERATED_LANES:
        return True
    return Path(rel).name in {".DS_Store"} or "__pycache__" in parts


def text_line_count(repo_paths: list[str]) -> int:
    total = 0
    for repo_path in repo_paths:
        path = REPO / repo_path
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        total += data.count(b"\n")
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-untracked",
        type=int,
        default=None,
        help="optional maximum Git-visible untracked file count",
    )
    parser.add_argument(
        "--max-untracked-lines",
        type=int,
        default=None,
        help="optional maximum text lines across Git-visible untracked files",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="fail if any Git-visible incubator changes are pending",
    )
    args = parser.parse_args(argv)

    untracked = visible_untracked_paths()
    modified = visible_modified_paths()
    staged = visible_staged_paths()
    status_entries = visible_status_entries()
    leaks = [path for path in untracked if is_generated_leak(path)]
    untracked_lines = text_line_count(untracked)

    print("Triptych local lifecycle")
    print(f"Root: {ROOT}")
    print(f"Git-visible untracked files: {len(untracked)}")
    print(f"Git-visible untracked text lines: {untracked_lines}")
    print(f"Staged files: {len(staged)}")
    print(f"Unstaged tracked files: {len(modified)}")
    print(f"Git-visible pending entries: {len(status_entries)}")

    if leaks:
        print()
        print("Generated/local lanes visible to Git:")
        for path in leaks:
            print(f"- {path}")

    failures = []
    if leaks:
        failures.append("generated or local-only lanes are Git-visible")
    if args.max_untracked is not None and len(untracked) > args.max_untracked:
        failures.append(f"untracked file count {len(untracked)} exceeds {args.max_untracked}")
    if args.max_untracked_lines is not None and untracked_lines > args.max_untracked_lines:
        failures.append(
            f"untracked text lines {untracked_lines} exceeds {args.max_untracked_lines}"
        )
    if args.require_clean and status_entries:
        failures.append(f"{len(status_entries)} Git-visible incubator entries are still pending")

    if failures:
        print()
        print("Lifecycle check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print()
    print("local lifecycle ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
