#!/usr/bin/env python3
"""Build a public-safe proxy from a Photos Universe aggregate receipt.

The proxy is creative steering only. It imports no media, exposes no raw paths
or hashes, and authorizes no Photos-library mutation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_PHOTOS_REPO = Path("/Users/4jp/Workspace/photos-universe-20260629-182431")
DEFAULT_RECEIPT = Path("docs/photos-universe-duplicate-proof-2026-06-29.json")


def git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def load_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    safety = data.get("safety") or {}
    if safety.get("read_only") is not True:
        raise SystemExit("receipt is not marked read_only")
    if safety.get("deleted_or_moved_files") is not False:
        raise SystemExit("receipt does not prove no delete/move actions")
    if safety.get("full_paths_or_hashes_in_public_receipt") is not False:
        raise SystemExit("receipt may contain full paths or hashes")
    return data


def build_proxy(
    receipt: dict[str, Any],
    *,
    photos_head: str,
    receipt_path: Path,
    metadata_preview_assets: int,
    metadata_preview_screenshots: int,
) -> dict[str, Any]:
    status_counts = receipt.get("status_counts") or {}
    matched = int(status_counts.get("all_available_match") or 0)
    rejected = int(status_counts.get("hash_mismatch") or 0)
    return {
        "schema": 1,
        "generated_at": str(receipt.get("generated_at") or "unknown"),
        "source": {
            "lane": "photos-universe",
            "repo": "organvm/limen",
            "branch": "work/photos-universe-20260629-182431",
            "head": photos_head,
            "receipt": str(receipt_path),
            "receipt_type": "aggregate_duplicate_hash_proof",
        },
        "safety": {
            "raw_media_paths": False,
            "raw_hashes": False,
            "photos_library_mutation": False,
            "file_delete_or_move": False,
            "media_import_or_export": False,
            "render_authorized": False,
        },
        "proof": {
            "candidate_groups_total": int(receipt.get("candidates_total") or 0),
            "processed_total": int(receipt.get("processed_total") or 0),
            "processed_this_receipt": int(receipt.get("processed_this_run") or 0),
            "hash_matching_duplicate_groups": matched,
            "hash_rejected_candidate_groups": rejected,
            "bytes_proven_duplicate": int(receipt.get("bytes_proven_duplicate") or 0),
            "available_path_classes": receipt.get("available_path_classes") or {},
        },
        "metadata_preview": {
            "assets_previewed": metadata_preview_assets,
            "screenshot_flagged_assets": metadata_preview_screenshots,
            "write_mode": "preview",
        },
        "creative_steering": {
            "allowed_use": "source-selection steering through local proxy manifests only",
            "duplicate_groups": (
                "Treat hash-proven duplicate groups as dedupe evidence, not as source media."
            ),
            "rejected_candidates": (
                "Treat rejected duplicate candidates as signal that visual similarity needs "
                "human review before any staging decision."
            ),
            "screenshot_heavy_preview": (
                "Use the screenshot-heavy preview as a candidate mood/source lane only after "
                "human-selected exports or generated proxies exist."
            ),
            "next_triptych_action": (
                "Review staged project manifests and dry-run edition builders; do not call "
                "Photos export or render from this proxy."
            ),
        },
    }


def write_markdown(proxy: dict[str, Any], path: Path) -> None:
    proof = proxy["proof"]
    preview = proxy["metadata_preview"]
    source = proxy["source"]
    steering = proxy["creative_steering"]
    path.write_text(
        "\n".join(
            [
                "# Photos Universe Proxy",
                "",
                f"Generated: `{proxy['generated_at']}`",
                "",
                "This is a public-safe creative steering proxy for the triptych incubator. It",
                "contains aggregate proof only: no raw media paths, no raw hashes, no Photos",
                "library writes, no file moves/deletes, and no render authorization.",
                "",
                "## Source",
                "",
                f"- Photos lane head: `{source['head']}`",
                f"- Aggregate receipt: `{source['receipt']}`",
                "",
                "## Aggregate Proof",
                "",
                f"- Candidate groups total: `{proof['candidate_groups_total']}`",
                f"- Processed groups total: `{proof['processed_total']}`",
                f"- Hash-matching duplicate groups: `{proof['hash_matching_duplicate_groups']}`",
                f"- Hash-rejected candidate groups: `{proof['hash_rejected_candidate_groups']}`",
                f"- Bytes in hash-proven duplicate groups: `{proof['bytes_proven_duplicate']}`",
                f"- Photos metadata preview assets: `{preview['assets_previewed']}`",
                f"- Screenshot-flagged preview assets: `{preview['screenshot_flagged_assets']}`",
                "",
                "## Creative Steering",
                "",
                f"- Allowed use: {steering['allowed_use']}.",
                f"- Duplicate groups: {steering['duplicate_groups']}",
                f"- Rejected candidates: {steering['rejected_candidates']}",
                f"- Screenshot preview: {steering['screenshot_heavy_preview']}",
                f"- Next triptych action: {steering['next_triptych_action']}",
                "",
                "## Gates",
                "",
                "- No Photos export, album mutation, delete, move, or library write follows from this proxy.",
                "- No render is authorized by this proxy; render queues still require their own dry-run gates.",
                "- Operational JSON/Markdown proxies may be regenerated under ignored `work/`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos-repo", type=Path, default=DEFAULT_PHOTOS_REPO)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--out-json", type=Path, default=Path("work/photos-universe-proof-proxy.json"))
    parser.add_argument("--out-md", type=Path, default=Path("PHOTOS_UNIVERSE_PROXY.md"))
    parser.add_argument("--work-md", type=Path, default=Path("work/photos-universe-proof-proxy.md"))
    parser.add_argument("--metadata-preview-assets", type=int, default=50)
    parser.add_argument("--metadata-preview-screenshots", type=int, default=32)
    args = parser.parse_args()

    receipt_path = args.receipt
    if not receipt_path.is_absolute():
        receipt_path = args.photos_repo / receipt_path
    receipt = load_receipt(receipt_path)
    proxy = build_proxy(
        receipt,
        photos_head=git_head(args.photos_repo),
        receipt_path=args.receipt,
        metadata_preview_assets=args.metadata_preview_assets,
        metadata_preview_screenshots=args.metadata_preview_screenshots,
    )

    out_json = args.out_json if args.out_json.is_absolute() else ROOT / args.out_json
    out_md = args.out_md if args.out_md.is_absolute() else ROOT / args.out_md
    work_md = args.work_md if args.work_md.is_absolute() else ROOT / args.work_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    work_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(proxy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(proxy, out_md)
    if work_md != out_md:
        write_markdown(proxy, work_md)
    print(f"wrote {out_json.relative_to(ROOT)}")
    print(f"wrote {out_md.relative_to(ROOT)}")
    if work_md != out_md:
        print(f"wrote {work_md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
