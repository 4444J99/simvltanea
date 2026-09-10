#!/usr/bin/env python3
"""Report generated-media weight for the triptych incubator.

This script is intentionally read-only. It names the live cache lanes that make
the project feel heavy, without deleting or publishing anything.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Lane:
    path: str
    role: str
    policy: str
    disposable: bool
    private: bool


@dataclass
class LaneReport:
    path: str
    role: str
    policy: str
    disposable: bool
    private: bool
    exists: bool
    bytes: int
    files: int
    symlinks: int
    last_modified: str | None


LANES = [
    Lane(
        "work",
        "private local state",
        "Private receipts, temporary phrases, catalogs, and model references. Regenerable; never publish.",
        True,
        True,
    ),
    Lane(
        "renders",
        "render cache",
        "Generated Story/Reel/sketch media. Regenerable from project manifests and staged sources.",
        True,
        False,
    ),
    Lane(
        "site",
        "public static build",
        "Generated public landing pages, proxies, and receipts. Share only after verify_public_site.py.",
        True,
        False,
    ),
    Lane(
        "packages",
        "hostable package build",
        "Generated copies/zips of site/. Regenerable after the public site verifies.",
        True,
        False,
    ),
    Lane(
        "samples",
        "staged selected media",
        "Ignored source/proxy staging lane. Heavy by design; delete only when originals can be restaged.",
        False,
        True,
    ),
]


REGENERATION_CHECKPOINTS = [
    "python3 edition_status.py",
    "python3 verify_editions.py",
    "python3 build_site_index.py",
    "python3 verify_post_pack.py work/editions/<slug>/project.json",
    "python3 verify_public_site.py",
    "python3 package_public_site.py",
    "python3 verify_package.py",
    "python3 verify_private_workflow.py",
]

CLEANUP_REGENERATION = {
    "packages": [
        "python3 package_public_site.py",
        "python3 verify_package.py",
    ],
    "site": [
        "python3 build_post_pack.py <edition> --profile draft",
        "python3 build_site_index.py",
        "python3 verify_public_site.py",
        "python3 package_public_site.py",
    ],
    "renders": [
        "python3 build_post_pack.py <edition> --profile draft",
        "python3 verify_post_pack.py work/editions/<slug>/project.json",
    ],
    "work": [
        "python3 edition_status.py",
        "python3 verify_editions.py",
    ],
}

CLEANUP_RISK = {
    "packages": "low: regenerated from a verified site",
    "site": "medium: public exports/proxies must be recreated or already packaged",
    "renders": "medium: render caches are expensive but source projects can rerender",
    "work": "high: private manifests/catalogs may be the only local selection receipt",
}


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def iter_lane_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        root_path = Path(root)
        for name in files:
            yield root_path / name


def lane_report(lane: Lane) -> LaneReport:
    path = ROOT / lane.path
    total_bytes = 0
    file_count = 0
    symlink_count = 0
    last_mtime = 0.0

    if path.exists():
        for item in iter_lane_files(path):
            try:
                stat = item.lstat()
            except OSError:
                continue
            file_count += 1
            total_bytes += stat.st_size
            last_mtime = max(last_mtime, stat.st_mtime)
            if item.is_symlink():
                symlink_count += 1

    last_modified = None
    if last_mtime:
        last_modified = datetime.fromtimestamp(last_mtime).isoformat(timespec="seconds")

    return LaneReport(
        path=lane.path,
        role=lane.role,
        policy=lane.policy,
        disposable=lane.disposable,
        private=lane.private,
        exists=path.exists(),
        bytes=total_bytes,
        files=file_count,
        symlinks=symlink_count,
        last_modified=last_modified,
    )


def print_table(reports: list[LaneReport]) -> None:
    print("Triptych generated-media inventory")
    print(f"Root: {ROOT}")
    print()
    print("Lane      Role                    Size       Files  Links  Policy")
    print("--------  ----------------------  ---------  -----  -----  ----------------")
    for report in reports:
        size = human_bytes(report.bytes) if report.exists else "missing"
        policy = "disposable" if report.disposable else "staged-source"
        private = "private" if report.private else "public-safe-after-verify"
        print(
            f"{report.path:<8}  {report.role:<22}  {size:>9}  "
            f"{report.files:>5}  {report.symlinks:>5}  {policy}; {private}"
        )

    total = sum(report.bytes for report in reports)
    generated = sum(report.bytes for report in reports if report.disposable)
    staged = sum(report.bytes for report in reports if not report.disposable)
    print()
    print(f"Total scanned: {human_bytes(total)}")
    print(f"Disposable/generated: {human_bytes(generated)}")
    print(f"Staged selected media: {human_bytes(staged)}")
    print()
    print("Regeneration checkpoints:")
    for command in REGENERATION_CHECKPOINTS:
        print(f"- {command}")


def cleanup_candidates(reports: list[LaneReport]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for report in sorted(reports, key=lambda item: item.bytes, reverse=True):
        if not report.exists or not report.disposable or report.bytes <= 0:
            continue
        candidates.append(
            {
                "lane": report.path,
                "bytes": report.bytes,
                "human_size": human_bytes(report.bytes),
                "files": report.files,
                "private": report.private,
                "risk": CLEANUP_RISK.get(report.path, "unknown"),
                "policy": report.policy,
                "regenerate_with": CLEANUP_REGENERATION.get(report.path, REGENERATION_CHECKPOINTS),
                "manual_only": True,
            }
        )
    return candidates


def print_cleanup_plan(reports: list[LaneReport]) -> None:
    candidates = cleanup_candidates(reports)
    print()
    print("Cleanup candidates (read-only; no deletion performed):")
    if not candidates:
        print("- none")
        return
    for candidate in candidates:
        print(
            f"- {candidate['lane']}/: {candidate['human_size']} across {candidate['files']} files; "
            f"{candidate['risk']}"
        )
        print("  Regenerate/check with:")
        for command in candidate["regenerate_with"]:  # type: ignore[index]
            print(f"  - {command}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only generated media inventory for triptych-video-canon."
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--cleanup-plan",
        action="store_true",
        help="print read-only reclaim candidates and regeneration gates",
    )
    args = parser.parse_args()

    reports = [lane_report(lane) for lane in LANES]
    candidates = cleanup_candidates(reports)
    if args.json:
        payload = {
            "root": str(ROOT),
            "reports": [asdict(report) for report in reports],
            "total_bytes": sum(report.bytes for report in reports),
            "disposable_bytes": sum(report.bytes for report in reports if report.disposable),
            "staged_media_bytes": sum(report.bytes for report in reports if not report.disposable),
            "cleanup_candidates": candidates,
            "regeneration_checkpoints": REGENERATION_CHECKPOINTS,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_table(reports)
        if args.cleanup_plan:
            print_cleanup_plan(reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
