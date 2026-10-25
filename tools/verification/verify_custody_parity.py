#!/usr/bin/env python3
"""Evaluate Git custody parity and duplicate repository retirement eligibility.

Enforces Issue #12 custody parity gates:
- Assigned canonical repository must have 0 dirty files and 0 unpushed commits.
- Custody receipt must be verified with 0 missing blobs and matching HEAD SHA.
- Duplicate candidates are eligible for retirement ONLY when HEAD SHA matches canonical,
  dirty_files == 0, untracked_media_count == 0, and custody receipt is verified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def evaluate_custody_parity(
    assigned_state: dict[str, Any],
    duplicate_candidates: list[dict[str, Any]],
    custody_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate custody parity and retirement eligibility for duplicate candidates."""
    canonical_errors: list[str] = []
    receipt_errors: list[str] = []

    assigned_head = str(assigned_state.get("head_sha", "")).strip()
    assigned_dirty = int(assigned_state.get("dirty_files", 0))
    assigned_unpushed = int(assigned_state.get("unpushed_commits", 0))

    if not assigned_head:
        canonical_errors.append("Assigned canonical repository missing head_sha")
    if assigned_dirty > 0:
        canonical_errors.append(
            f"Assigned canonical repository has {assigned_dirty} dirty files (clean parity required)"
        )
    if assigned_unpushed > 0:
        canonical_errors.append(
            f"Assigned canonical repository has {assigned_unpushed} unpushed commits"
        )

    receipt_verified = bool(custody_receipt.get("verified", False))
    receipt_missing = int(custody_receipt.get("missing_blobs", 0))
    receipt_head = str(custody_receipt.get("head_sha", "")).strip()

    if not receipt_verified:
        receipt_errors.append("Custody receipt is not verified (verified != True)")
    if receipt_missing > 0:
        receipt_errors.append(f"Custody receipt reports {receipt_missing} missing blobs")
    if assigned_head and receipt_head and assigned_head != receipt_head:
        receipt_errors.append(
            f"HEAD SHA mismatch between canonical ({assigned_head}) and custody receipt ({receipt_head})"
        )
    elif not receipt_head:
        receipt_errors.append("Custody receipt missing head_sha")

    canonical_clean = len(canonical_errors) == 0
    receipt_clean = len(receipt_errors) == 0

    evaluated_duplicates: list[dict[str, Any]] = []
    for cand in duplicate_candidates:
        cand_path = str(cand.get("path", ""))
        cand_head = str(cand.get("head_sha", "")).strip()
        cand_dirty = int(cand.get("dirty_files", 0))
        cand_untracked_media = int(cand.get("untracked_media_count", 0))

        blocking: list[str] = []

        if not canonical_clean:
            blocking.append("Canonical repository copy lacks clean parity")
        if not receipt_clean:
            blocking.append("Custody receipt is unverified or invalid")

        if not cand_head:
            blocking.append("Duplicate candidate missing head_sha")
        elif assigned_head and cand_head != assigned_head:
            blocking.append(
                f"Candidate HEAD {cand_head[:10]} does not match canonical HEAD {assigned_head[:10]}"
            )

        if cand_dirty > 0:
            blocking.append(f"Candidate has {cand_dirty} uncommitted/dirty files")
        if cand_untracked_media > 0:
            blocking.append(
                f"Candidate contains {cand_untracked_media} untracked media assets"
            )

        eligible = len(blocking) == 0
        evaluated_duplicates.append({
            "path": cand_path,
            "head_sha": cand_head,
            "dirty_files": cand_dirty,
            "untracked_media_count": cand_untracked_media,
            "eligible_for_retirement": eligible,
            "blocking_reasons": blocking,
        })

    eligible_count = sum(1 for d in evaluated_duplicates if d["eligible_for_retirement"])
    blocked_count = sum(1 for d in evaluated_duplicates if not d["eligible_for_retirement"])

    overall_pass = canonical_clean and receipt_clean and (blocked_count == 0)

    return {
        "status": "PASS" if overall_pass else "GATED",
        "canonical_assigned": {
            "path": str(assigned_state.get("path", "")),
            "head_sha": assigned_head,
            "dirty_files": assigned_dirty,
            "unpushed_commits": assigned_unpushed,
            "clean_parity": canonical_clean,
            "errors": canonical_errors,
        },
        "custody_receipt": {
            "verified": receipt_verified,
            "missing_blobs": receipt_missing,
            "head_sha": receipt_head,
            "valid": receipt_clean,
            "errors": receipt_errors,
        },
        "duplicates": evaluated_duplicates,
        "total_candidates": len(duplicate_candidates),
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify custody parity and duplicate retirement eligibility.",
    )
    parser.add_argument(
        "--json-input",
        type=Path,
        help="Optional path to JSON file containing {assigned_state, duplicate_candidates, custody_receipt}",
    )
    args = parser.parse_args(argv)

    if args.json_input:
        if not args.json_input.is_file():
            print(f"Error: input file {args.json_input} not found", file=sys.stderr)
            return 2
        payload = json.loads(args.json_input.read_text(encoding="utf-8"))
        result = evaluate_custody_parity(
            payload.get("assigned_state", {}),
            payload.get("duplicate_candidates", []),
            payload.get("custody_receipt", {}),
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1

    print("Custody parity gate ready. Use evaluate_custody_parity() programmatically or supply --json-input.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
