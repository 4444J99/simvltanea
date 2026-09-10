#!/usr/bin/env python3
"""Package the verified public triptych site for static hosting."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "packages"
DEFAULT_NAME = "triptych-video-canon-site"
MANIFEST_NAME = "package-manifest.json"
PUBLIC_PACKAGE_READY = "public-package-ready"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a hostable static-site package from the verified public site. "
            "Only copies site/ content, writes checksums, and optionally zips it."
        )
    )
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Public site directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Package output directory.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Package directory/zip basename.")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verify_public_site.py checks before and after packaging.",
    )
    parser.add_argument("--no-zip", action="store_true", help="Do not create a zip archive.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing package files.")
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def require_inside(path: Path, label: str) -> None:
    if not path_inside(path, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")


def resolved_path(path: Path, base: Path = SCRIPT_DIR) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (base / expanded).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == MANIFEST_NAME:
            continue
        relative = path.relative_to(root).as_posix()
        records.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def tree_size(records: list[dict[str, Any]]) -> int:
    return sum(int(record["size_bytes"]) for record in records)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: JSON root must be an object")
    return data


def public_export_counts(receipt: dict[str, Any]) -> tuple[int, int]:
    post_layouts = {"story", "left", "middle", "right"}
    post_count = 0
    sketch_count = 0
    for export in receipt.get("exports") or []:
        if not isinstance(export, dict) or not export.get("exists") or not export.get("published"):
            continue
        layout = export.get("layout")
        if layout in post_layouts:
            post_count += 1
        elif layout == "visual-sketch":
            sketch_count += 1
    return post_count, sketch_count


def promotion_state_for_receipt(receipt: dict[str, Any], post_count: int, sketch_count: int) -> str:
    if receipt.get("public") is True and (post_count + sketch_count) > 0:
        return PUBLIC_PACKAGE_READY
    return "public-derivative-staged"


def arrangement_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    score = receipt.get("arrangement_score")
    if not isinstance(score, dict):
        return {}
    summary: dict[str, Any] = {}
    for key in (
        "preview_label",
        "work_title",
        "family",
        "style",
        "cell_key",
        "cell_count",
        "model",
        "model_fit",
        "panel_role",
        "model_role",
        "material",
    ):
        value = score.get(key)
        if value not in (None, "", [], {}):
            summary[key] = value
    return summary


def edition_summary(package_dir: Path) -> dict[str, Any]:
    editions: list[dict[str, Any]] = []
    totals = {
        "clips": 0,
        "video_proxies": 0,
        "audio_proxies": 0,
        "published_post_exports": 0,
        "visual_sketches": 0,
    }

    for receipt_path in sorted((package_dir / "editions").glob("*/flash-copy.json")):
        receipt = read_json(receipt_path)
        slug = receipt_path.parent.name
        counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
        clips = int(counts.get("manifest_clips") or len(receipt.get("clips") or []))
        video_proxies = int(counts.get("video_proxies") or 0)
        audio_proxies = int(counts.get("audio_proxies") or 0)
        post_count, sketch_count = public_export_counts(receipt)
        promotion_state = promotion_state_for_receipt(receipt, post_count, sketch_count)
        presets = [
            str(preset.get("id"))
            for preset in receipt.get("control_presets") or []
            if isinstance(preset, dict) and preset.get("id")
        ]
        post_exports = [
            str(name)
            for name in ((receipt.get("post_pack") or {}).get("exports") or [])
            if isinstance(name, str)
        ]

        totals["clips"] += clips
        totals["video_proxies"] += video_proxies
        totals["audio_proxies"] += audio_proxies
        totals["published_post_exports"] += post_count
        totals["visual_sketches"] += sketch_count
        editions.append(
            {
                "slug": slug,
                "title": receipt.get("title"),
                "work_title": receipt.get("work_title"),
                "family": receipt.get("family"),
                "clips": clips,
                "video_proxies": video_proxies,
                "audio_proxies": audio_proxies,
                "control_presets": presets,
                "default_control_preset": presets[0] if presets else None,
                "post_exports": post_exports,
                "published_post_exports": post_count,
                "visual_sketches": sketch_count,
                "custody_tier": "public_derivative",
                "promotion_state": promotion_state,
                "public_export_gate": promotion_state,
                "arrangement_score": arrangement_summary(receipt),
            }
        )

    return {
        "edition_count": len(editions),
        **totals,
        "editions": editions,
    }


def verify_manifest_custody(payload: dict[str, Any]) -> None:
    summary = payload.get("edition_summary")
    editions = summary.get("editions") if isinstance(summary, dict) else None
    if not isinstance(editions, list) or not editions:
        raise SystemExit("package custody gate requires at least one packaged edition.")
    blocked = [
        str(edition.get("slug"))
        for edition in editions
        if not isinstance(edition, dict)
        or edition.get("custody_tier") != "public_derivative"
        or edition.get("promotion_state") != PUBLIC_PACKAGE_READY
        or edition.get("public_export_gate") != PUBLIC_PACKAGE_READY
    ]
    if blocked:
        raise SystemExit(
            "package custody gate rejected non-public-package-ready edition(s): "
            + ", ".join(sorted(blocked))
        )


def run_verify(site_dir: Path) -> None:
    command = [sys.executable, str(SCRIPT_DIR / "verify_public_site.py"), "--site-dir", str(site_dir)]
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


def print_verify(site_dir: Path) -> None:
    print(f"{sys.executable} {SCRIPT_DIR / 'verify_public_site.py'} --site-dir {site_dir}")


def copy_site(site_dir: Path, package_dir: Path, dry_run: bool) -> None:
    print(f"copy {site_dir} -> {package_dir}")
    if dry_run:
        return
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.copytree(site_dir, package_dir)


def rewrite_public_receipts(site_dir: Path, package_dir: Path, dry_run: bool) -> None:
    receipt_root = site_dir if dry_run else package_dir
    for receipt_path in sorted((receipt_root / "editions").glob("*/flash-copy.json")):
        target_path = package_dir / receipt_path.relative_to(receipt_root) if dry_run else receipt_path
        print(f"normalize {target_path}")
        if dry_run:
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["landing_page"] = f"editions/{receipt_path.parent.name}/index.html"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def write_manifest(
    package_dir: Path,
    package_name: str,
    source_site: Path,
    dry_run: bool,
) -> dict[str, Any]:
    manifest_source = source_site if dry_run else package_dir
    records = file_records(manifest_source)
    payload = {
        "schema": "triptych.public-site-package.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "package": package_name,
        "source_site": source_site.relative_to(SCRIPT_DIR).as_posix(),
        "entrypoint": "index.html",
        "file_count": len(records),
        "size_bytes": tree_size(records),
        "edition_summary": edition_summary(manifest_source),
        "custody": {
            "tier": "public_derivative",
            "promotion_state": PUBLIC_PACKAGE_READY,
            "public_export_gate": PUBLIC_PACKAGE_READY,
            "source_boundary": "copied from sanitized site/ only",
            "private_durable_receipt": "work/preservation-ledger.json",
            "forbidden_lanes": ["work/", "samples/", "renders/"],
            "rule": "Only public-package-ready derivatives belong in this transfer package.",
        },
        "files": records,
        "verification": {
            "public_site": "python3 verify_public_site.py --site-dir site",
            "package_site": f"python3 verify_public_site.py --site-dir packages/{package_name}",
            "package_integrity": f"python3 verify_package.py --package-dir packages/{package_name}",
            "post_pack": "python3 verify_post_pack.py <local-edition-project>",
        },
        "notes": [
            "This package is generated from the sanitized public site tree.",
            "It should not contain private local receipts, source samples, local renders, or direct Photos library paths.",
        ],
    }
    manifest_path = package_dir / MANIFEST_NAME
    print(f"write {manifest_path}")
    if dry_run and manifest_source != package_dir:
        print(f"dry-run: manifest summary from {manifest_source}")
    if not dry_run:
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    verify_manifest_custody(payload)
    return payload


def zip_package(package_dir: Path, zip_path: Path, dry_run: bool) -> None:
    print(f"zip {package_dir} -> {zip_path}")
    if dry_run:
        return
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in package_dir.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(package_dir).as_posix())


def main() -> int:
    args = parse_args()
    site_dir = resolved_path(args.site_dir)
    output_dir = resolved_path(args.output_dir)
    package_dir = output_dir / args.name
    zip_path = output_dir / f"{args.name}.zip"

    require_inside(site_dir, "site-dir")
    require_inside(output_dir, "output-dir")
    require_inside(package_dir, "package-dir")
    require_inside(zip_path, "zip")
    if not site_dir.exists():
        raise SystemExit(f"site directory does not exist: {site_dir}")
    if path_inside(package_dir, site_dir) or path_inside(site_dir, package_dir):
        raise SystemExit("package-dir and site-dir must not contain each other.")

    if not args.no_verify and not args.dry_run:
        run_verify(site_dir)
    elif not args.no_verify:
        print_verify(site_dir)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    copy_site(site_dir, package_dir, args.dry_run)
    rewrite_public_receipts(site_dir, package_dir, args.dry_run)
    manifest = write_manifest(package_dir, args.name, site_dir, args.dry_run)
    if not args.no_verify and not args.dry_run:
        run_verify(package_dir)
    elif not args.no_verify:
        print_verify(package_dir)
    if not args.no_zip:
        zip_package(package_dir, zip_path, args.dry_run)

    size_mb = float(manifest.get("size_bytes", 0)) / (1024 * 1024)
    print(f"package ready: {package_dir.relative_to(SCRIPT_DIR)} ({size_mb:.1f} MB)")
    if not args.no_zip:
        print(f"archive: {zip_path.relative_to(SCRIPT_DIR)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
