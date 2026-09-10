#!/usr/bin/env python3
"""Write a private custody ledger for triptych source, work, and public outputs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import generated_inventory


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EDITIONS = SCRIPT_DIR / "editions.example.json"
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_PACKAGE_DIR = SCRIPT_DIR / "packages" / "triptych-video-canon-site"
DEFAULT_SLATE = SCRIPT_DIR / "work" / "edition-refinement-slate.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "work" / "preservation-ledger.json"
DEFAULT_DOC = SCRIPT_DIR / "work" / "preservation-ledger.md"
DEFAULT_HTML = SCRIPT_DIR / "work" / "preservation-ledger.html"
SCHEMA = "triptych.preservation-ledger.v1"
PACKAGE_MANIFEST = "package-manifest.json"
PRIVATE_TEXT = (
    "/Users/",
    ".photoslibrary",
    "Photos Library",
    "Photos.sqlite",
    "resources/derivatives",
    "absolute_path",
    "resolved_path",
    "source_uuid",
    "sourceSrc",
    "source_src",
    "symlink_target",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private preservation/custody ledger. The ledger names what "
            "belongs in private durable custody, private operational staging, "
            "public derivatives, and public apparatus without exposing local paths."
        )
    )
    parser.add_argument("--editions", type=Path, default=DEFAULT_EDITIONS, help="Edition preset JSON.")
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Generated public site.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR, help="Generated package.")
    parser.add_argument("--slate", type=Path, default=DEFAULT_SLATE, help="Private edition slate JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Private JSON ledger path.")
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC, help="Private markdown ledger path.")
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML, help="Private HTML ledger path.")
    parser.add_argument("--json", action="store_true", help="Print the ledger JSON instead of writing files.")
    parser.add_argument("--verify", action="store_true", help="Validate the computed ledger and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print write targets without writing files.")
    return parser.parse_args()


def path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolve_inside(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    resolved = expanded.resolve() if expanded.is_absolute() else (SCRIPT_DIR / expanded).resolve()
    if not path_inside(resolved, SCRIPT_DIR):
        raise SystemExit(f"{label} must stay inside the SIMVLTANEA repository root.")
    return resolved


def rel(path: Path) -> str:
    return path.relative_to(SCRIPT_DIR).as_posix()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: JSON root must be an object")
    return data


def safe_slug(value: Any) -> str:
    text = str(value or "edition").strip().lower()
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text).strip(".-")
    return cleaned or "edition"


def edition_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    editions = payload.get("editions")
    if not isinstance(editions, list):
        raise SystemExit("editions file must contain an editions array.")
    return [edition for edition in editions if isinstance(edition, dict)]


def edition_slug(edition: dict[str, Any]) -> str:
    return safe_slug(edition.get("slug") or edition.get("name"))


def slate_rows(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    if not payload:
        return {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("edition")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("edition"), str)
    }


def source_summary(edition: dict[str, Any]) -> dict[str, Any]:
    source = edition.get("source") if isinstance(edition.get("source"), dict) else {}
    composition = edition.get("composition") if isinstance(edition.get("composition"), dict) else {}
    summary = {
        "custody_tier": "private_durable",
        "preservation_state": "requires-private-archive",
        "source_type": source.get("type", "unknown"),
        "source_album": source.get("album", ""),
        "album_match": source.get("album_match", ""),
        "order": source.get("order", ""),
        "limit": source.get("limit", 0),
        "arrangement_model_album": composition.get("arrangement_model_album", ""),
        "archive_requirement": "checksum source selections and keep originals in controlled private storage",
    }
    return {key: value for key, value in summary.items() if value not in ("", None)}


def source_fingerprint(clip: dict[str, Any]) -> str:
    parts = [
        str(clip.get("source") or ""),
        str(clip.get("source_uuid") or ""),
        str(clip.get("source_created") or ""),
        str(clip.get("original_filename") or ""),
        str(clip.get("duration") or ""),
        str(clip.get("width") or ""),
        str(clip.get("height") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def project_source_selection(project: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {
            "custody_tier": "private_operational",
            "selection_state": "not-staged",
            "clip_count": 0,
            "fingerprints": [],
        }
    clips = project.get("clips")
    if not isinstance(clips, list):
        clips = []
    fingerprints = [
        source_fingerprint(clip)
        for clip in clips
        if isinstance(clip, dict)
    ]
    return {
        "custody_tier": "private_operational",
        "selection_state": "staged-project",
        "clip_count": len(fingerprints),
        "fingerprints": fingerprints,
        "path_policy": "relative staging refs only; do not publish source selections",
    }


def receipt_counts(receipt: dict[str, Any] | None) -> tuple[int, int, int]:
    if not isinstance(receipt, dict):
        return (0, 0, 0)
    post_count = 0
    sketch_count = 0
    for export in receipt.get("exports") or []:
        if not isinstance(export, dict) or export.get("exists") is not True:
            continue
        if export.get("layout") == "visual-sketch":
            sketch_count += 1
        elif export.get("published") is True:
            post_count += 1
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    clips = int(counts.get("manifest_clips") or len(receipt.get("clips") or []))
    return (clips, post_count, sketch_count)


def public_derivative_state(
    slug: str,
    site_dir: Path,
    package_dir: Path,
    slate_row: dict[str, Any] | None,
) -> dict[str, Any]:
    site_receipt_path = site_dir / "editions" / slug / "flash-copy.json"
    package_receipt_path = package_dir / "editions" / slug / "flash-copy.json"
    site_receipt = load_json(site_receipt_path)
    package_receipt = load_json(package_receipt_path)
    clips, post_exports, visual_sketches = receipt_counts(package_receipt or site_receipt)
    public_gate = ""
    if isinstance(slate_row, dict):
        public_gate = str(slate_row.get("public_export_gate") or "")
    if not public_gate:
        public_gate = "gated-local-only" if slug == "porn" else ("public-package-ready" if package_receipt else "not-public")

    package_page = ""
    if isinstance(slate_row, dict) and isinstance(slate_row.get("package_page"), str):
        package_page = slate_row["package_page"]
    elif package_receipt:
        package_page = f"packages/triptych-video-canon-site/editions/{slug}/index.html"

    if public_gate == "public-package-ready":
        promotion_state = "public-package-ready"
    elif public_gate == "gated-local-only":
        promotion_state = "gated-local-only"
    else:
        promotion_state = "not-public"

    return {
        "custody_tier": "public_derivative" if promotion_state == "public-package-ready" else "no_public_derivative",
        "promotion_state": promotion_state,
        "public_export_gate": public_gate,
        "site_receipt": rel(site_receipt_path) if site_receipt_path.exists() else "",
        "package_receipt": rel(package_receipt_path) if package_receipt_path.exists() else "",
        "package_page": package_page,
        "package_synced": package_receipt is not None,
        "clip_count": clips,
        "published_post_exports": post_exports,
        "visual_sketches": visual_sketches,
        "public_transfer_allowed": promotion_state == "public-package-ready" and package_receipt is not None,
    }


def lane_custody() -> list[dict[str, Any]]:
    reports = [generated_inventory.lane_report(lane) for lane in generated_inventory.LANES]
    records: list[dict[str, Any]] = []
    tier_by_lane = {
        "work": "private_operational",
        "samples": "private_operational",
        "renders": "private_operational",
        "site": "public_derivative_staging",
        "packages": "public_derivative_transfer",
    }
    for report in reports:
        records.append(
            {
                "lane": report.path,
                "custody_tier": tier_by_lane.get(report.path, "private_operational"),
                "role": report.role,
                "policy": report.policy,
                "private": report.private,
                "disposable": report.disposable,
                "exists": report.exists,
                "bytes": report.bytes,
                "human_size": generated_inventory.human_bytes(report.bytes),
                "files": report.files,
                "symlinks": report.symlinks,
            }
        )
    return records


def package_manifest_state(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / PACKAGE_MANIFEST
    manifest = load_json(manifest_path)
    if not manifest:
        return {
            "exists": False,
            "path": rel(manifest_path),
            "public_transfer_allowed": False,
            "editions": [],
        }
    summary = manifest.get("edition_summary") if isinstance(manifest.get("edition_summary"), dict) else {}
    editions = summary.get("editions") if isinstance(summary.get("editions"), list) else []
    ready = [
        str(edition.get("slug"))
        for edition in editions
        if isinstance(edition, dict) and edition.get("promotion_state") == "public-package-ready"
    ]
    blocked = [
        str(edition.get("slug"))
        for edition in editions
        if isinstance(edition, dict) and edition.get("promotion_state") != "public-package-ready"
    ]
    return {
        "exists": True,
        "path": rel(manifest_path),
        "custody_tier": ((manifest.get("custody") or {}).get("tier") if isinstance(manifest.get("custody"), dict) else ""),
        "promotion_state": ((manifest.get("custody") or {}).get("promotion_state") if isinstance(manifest.get("custody"), dict) else ""),
        "public_transfer_allowed": bool(editions) and not blocked,
        "file_count": manifest.get("file_count", 0),
        "size_bytes": manifest.get("size_bytes", 0),
        "ready_editions": ready,
        "blocked_editions": blocked,
    }


def build_payload(editions_path: Path, site_dir: Path, package_dir: Path, slate_path: Path) -> dict[str, Any]:
    editions_payload = load_json(editions_path)
    if editions_payload is None:
        raise SystemExit(f"editions file does not exist: {editions_path}")
    slate_by_slug = slate_rows(slate_path)
    records: list[dict[str, Any]] = []
    for edition in edition_list(editions_payload):
        slug = edition_slug(edition)
        project_path = SCRIPT_DIR / "work" / "editions" / slug / "project.json"
        project = load_json(project_path)
        public_state = public_derivative_state(slug, site_dir, package_dir, slate_by_slug.get(slug))
        records.append(
            {
                "edition": slug,
                "work_title": edition.get("work_title") or edition.get("name") or slug,
                "family": edition.get("family") or "",
                "configured_status": edition.get("status", "ready"),
                "source": source_summary(edition),
                "source_selection": project_source_selection(project),
                "public_derivative": public_state,
                "next_custody_action": custody_action(slug, public_state, project),
            }
        )

    package_state = package_manifest_state(package_dir)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "private custody ledger for source preservation, operational staging, and public transfer",
        "tier_definitions": {
            "private_durable": "source identity and source selections that must be backed up privately",
            "private_operational": "local staging, queues, renders, and receipts used to produce the work",
            "public_derivative": "sanitized generated outputs that can be hosted or transferred after verification",
            "public_apparatus": "tracked renderer, verifier, examples, and docs that explain the work without exposing sources",
        },
        "sources": {
            "editions": rel(editions_path),
            "edition_slate": rel(slate_path) if slate_path.exists() else "",
            "site_dir": rel(site_dir),
            "package_dir": rel(package_dir),
        },
        "package_gate": package_state,
        "lanes": lane_custody(),
        "editions": records,
        "public_apparatus": {
            "custody_tier": "public_apparatus",
            "paths": [
                "INCUBATION.md",
                "README.md",
                "editions.example.json",
                "project.example.json",
                "render_triptych.py",
                "render_visual_sketch.py",
                "export_project.py",
                "build_edition.py",
                "build_post_pack.py",
                "build_site_index.py",
                "sync_flash_copy.py",
                "package_public_site.py",
                "verify_public_site.py",
                "verify_package.py",
                "preservation_manifest.py",
            ],
        },
        "operating_rule": (
            "Personal material should move into private durable custody before broad cleanup; "
            "only public-package-ready derivatives may enter the transfer package."
        ),
    }


def custody_action(slug: str, public_state: dict[str, Any], project: dict[str, Any] | None) -> str:
    if public_state.get("promotion_state") == "gated-local-only":
        return "keep local/private; require explicit public-export review before derivative packaging"
    if public_state.get("promotion_state") == "public-package-ready":
        return "review/post from package; preserve source selections privately before deleting local staging"
    if project:
        return "archive source selections privately, then decide whether to render a public derivative"
    if slug == "porn":
        return "keep gated; do not stage public derivative"
    return "curate source privately with dry-run first"


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != SCHEMA:
        errors.append("unexpected preservation ledger schema")
    package_gate = payload.get("package_gate")
    if not isinstance(package_gate, dict):
        errors.append("package_gate must be an object")
    elif package_gate.get("public_transfer_allowed") and package_gate.get("blocked_editions"):
        errors.append("package_gate cannot allow transfer with blocked editions")
    for record in payload.get("editions") or []:
        if not isinstance(record, dict):
            errors.append("edition record must be an object")
            continue
        slug = str(record.get("edition") or "")
        public_state = record.get("public_derivative")
        if not isinstance(public_state, dict):
            errors.append(f"{slug}: public_derivative must be an object")
            continue
        if slug == "porn" and public_state.get("public_export_gate") != "gated-local-only":
            errors.append("porn must stay gated-local-only")
        if public_state.get("public_transfer_allowed") and public_state.get("custody_tier") != "public_derivative":
            errors.append(f"{slug}: transferable edition must be public_derivative")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"preservation ledger contains private token {token!r}")
    return errors


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Preservation Ledger",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        payload["operating_rule"],
        "",
        "## Custody Tiers",
        "",
    ]
    for tier, note in payload["tier_definitions"].items():
        lines.append(f"- {tier}: {note}")
    lines.extend(["", "## Package Gate", ""])
    gate = payload["package_gate"]
    lines.extend(
        [
            f"- Package manifest: {gate['path']}",
            f"- Public transfer allowed: {gate['public_transfer_allowed']}",
            f"- Ready editions: {', '.join(gate['ready_editions']) if gate['ready_editions'] else 'none'}",
            f"- Blocked editions: {', '.join(gate['blocked_editions']) if gate['blocked_editions'] else 'none'}",
            "",
            "## Editions",
            "",
        ]
    )
    for record in payload["editions"]:
        public_state = record["public_derivative"]
        selection = record["source_selection"]
        source = record["source"]
        lines.extend(
            [
                f"### {record['work_title']}",
                "",
                f"- Edition: {record['edition']}",
                f"- Family: {record['family']}",
                f"- Source custody: {source['custody_tier']} / {source['preservation_state']}",
                f"- Source album: {source.get('source_album', '[none]')}",
                f"- Selection: {selection['selection_state']} / {selection['clip_count']} clips",
                f"- Public gate: {public_state['public_export_gate']}",
                f"- Promotion state: {public_state['promotion_state']}",
                f"- Package synced: {public_state['package_synced']}",
                f"- Post exports: {public_state['published_post_exports']}",
                f"- Visual sketches: {public_state['visual_sketches']}",
                f"- Next custody action: {record['next_custody_action']}",
                "",
            ]
        )
    lines.extend(["## Lanes", ""])
    for lane in payload["lanes"]:
        lines.append(
            f"- {lane['lane']}/: {lane['custody_tier']}; {lane['human_size']}; "
            f"{lane['files']} files; {lane['policy']}"
        )
    return "\n".join(lines) + "\n"


def html_doc(payload: dict[str, Any]) -> str:
    rows = []
    for record in payload["editions"]:
        public_state = record["public_derivative"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(record['edition']))}</td>"
            f"<td>{html.escape(str(record['work_title']))}</td>"
            f"<td>{html.escape(str(record['family']))}</td>"
            f"<td>{html.escape(str(public_state['public_export_gate']))}</td>"
            f"<td>{html.escape(str(public_state['promotion_state']))}</td>"
            f"<td>{html.escape(str(record['source_selection']['clip_count']))}</td>"
            f"<td>{html.escape(str(record['next_custody_action']))}</td>"
            "</tr>"
        )
    lane_rows = []
    for lane in payload["lanes"]:
        lane_rows.append(
            "<tr>"
            f"<td>{html.escape(str(lane['lane']))}</td>"
            f"<td>{html.escape(str(lane['custody_tier']))}</td>"
            f"<td>{html.escape(str(lane['human_size']))}</td>"
            f"<td>{html.escape(str(lane['files']))}</td>"
            f"<td>{html.escape(str(lane['policy']))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Preservation Ledger</title>
  <style>
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f4ef; color: #1d1b19; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1, h2 {{ line-height: 1.1; }}
    .summary {{ border-left: 4px solid #2f6f62; padding: 10px 16px; background: #fffdfa; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0 28px; background: #fffdfa; }}
    th, td {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid #ded7ca; font-size: 14px; }}
    th {{ color: #5d5348; }}
    code {{ background: #eee7dc; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Triptych Preservation Ledger</h1>
  <p class="summary">{html.escape(str(payload["operating_rule"]))}</p>
  <p>Generated: <code>{html.escape(str(payload["generated_at"]))}</code></p>
  <h2>Package Gate</h2>
  <p>Public transfer allowed: <strong>{html.escape(str(payload["package_gate"]["public_transfer_allowed"]))}</strong></p>
  <p>Ready editions: {html.escape(", ".join(payload["package_gate"]["ready_editions"]) or "none")}</p>
  <p>Blocked editions: {html.escape(", ".join(payload["package_gate"]["blocked_editions"]) or "none")}</p>
  <h2>Editions</h2>
  <table>
    <thead><tr><th>Edition</th><th>Work</th><th>Family</th><th>Gate</th><th>Promotion</th><th>Clips</th><th>Next custody action</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>Lanes</h2>
  <table>
    <thead><tr><th>Lane</th><th>Custody tier</th><th>Size</th><th>Files</th><th>Policy</th></tr></thead>
    <tbody>{''.join(lane_rows)}</tbody>
  </table>
</main>
</body>
</html>
"""


def write_text(path: Path, text: str, dry_run: bool) -> None:
    print(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    editions_path = resolve_inside(args.editions, "editions")
    site_dir = resolve_inside(args.site_dir, "site-dir")
    package_dir = resolve_inside(args.package_dir, "package-dir")
    slate_path = resolve_inside(args.slate, "slate")
    output = resolve_inside(args.output, "output")
    doc = resolve_inside(args.doc, "doc")
    html_path = resolve_inside(args.html, "html")

    payload = build_payload(editions_path, site_dir, package_dir, slate_path)
    errors = validate_payload(payload)
    if errors:
        raise SystemExit("preservation ledger invalid:\n- " + "\n- ".join(errors))

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.verify:
        print(
            "preservation ledger ok: "
            f"{len(payload['editions'])} editions; "
            f"transfer allowed {payload['package_gate']['public_transfer_allowed']}; "
            f"ready {len(payload['package_gate']['ready_editions'])}"
        )
        return 0

    write_text(output, json.dumps(payload, indent=2, sort_keys=True) + "\n", args.dry_run)
    write_text(doc, markdown(payload), args.dry_run)
    write_text(html_path, html_doc(payload), args.dry_run)
    print(
        "preservation ledger ok: "
        f"{len(payload['editions'])} editions; "
        f"transfer allowed {payload['package_gate']['public_transfer_allowed']}; "
        f"ready {len(payload['package_gate']['ready_editions'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
