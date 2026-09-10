#!/usr/bin/env python3
"""Write a private overnight checkpoint for the triptych incubator."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import generated_inventory


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_PACKAGE_DIR = SCRIPT_DIR / "packages" / "triptych-video-canon-site"
DEFAULT_OUTPUT = SCRIPT_DIR / "work" / "overnight-checkpoint.json"
DEFAULT_DOC = SCRIPT_DIR / "work" / "overnight-checkpoint.md"
DEFAULT_FOCUS_OUTPUT = SCRIPT_DIR / "work" / "release-focus.json"
DEFAULT_FOCUS_DOC = SCRIPT_DIR / "work" / "release-focus.md"
DEFAULT_FOCUS_HTML = SCRIPT_DIR / "work" / "release-focus.html"
DEFAULT_AUDITIONS_OUTPUT = SCRIPT_DIR / "work" / "control-auditions.json"
DEFAULT_AUDITIONS_DOC = SCRIPT_DIR / "work" / "control-auditions.md"
DEFAULT_AUDITIONS_HTML = SCRIPT_DIR / "work" / "control-auditions.html"
DEFAULT_RENDER_QUEUE_OUTPUT = SCRIPT_DIR / "work" / "next-render-queue.json"
DEFAULT_RENDER_QUEUE_DOC = SCRIPT_DIR / "work" / "next-render-queue.md"
DEFAULT_RENDER_QUEUE_HTML = SCRIPT_DIR / "work" / "next-render-queue.html"
DEFAULT_DASHBOARD_OUTPUT = SCRIPT_DIR / "work" / "overnight-dashboard.json"
DEFAULT_DASHBOARD_DOC = SCRIPT_DIR / "work" / "overnight-dashboard.md"
DEFAULT_DASHBOARD_HTML = SCRIPT_DIR / "work" / "overnight-dashboard.html"
DEFAULT_HOSTING_OUTPUT = SCRIPT_DIR / "work" / "static-hosting-handoff.json"
DEFAULT_HOSTING_DOC = SCRIPT_DIR / "work" / "static-hosting-handoff.md"
DEFAULT_HOSTING_HTML = SCRIPT_DIR / "work" / "static-hosting-handoff.html"
DEFAULT_FIRST_RELEASE_OUTPUT = SCRIPT_DIR / "work" / "first-release-packet.json"
DEFAULT_FIRST_RELEASE_DOC = SCRIPT_DIR / "work" / "first-release-packet.md"
DEFAULT_FIRST_RELEASE_HTML = SCRIPT_DIR / "work" / "first-release-packet.html"
DEFAULT_POSTING_RECEIPT_OUTPUT = SCRIPT_DIR / "work" / "posting-receipt-template.json"
DEFAULT_POSTING_RECEIPT_DOC = SCRIPT_DIR / "work" / "posting-receipt-template.md"
DEFAULT_POSTING_RECEIPT_HTML = SCRIPT_DIR / "work" / "posting-receipt-template.html"
DEFAULT_RELEASE_CADENCE_OUTPUT = SCRIPT_DIR / "work" / "release-cadence-plan.json"
DEFAULT_RELEASE_CADENCE_DOC = SCRIPT_DIR / "work" / "release-cadence-plan.md"
DEFAULT_RELEASE_CADENCE_HTML = SCRIPT_DIR / "work" / "release-cadence-plan.html"
DEFAULT_EDITION_SLATE_OUTPUT = SCRIPT_DIR / "work" / "edition-refinement-slate.json"
DEFAULT_EDITION_SLATE_DOC = SCRIPT_DIR / "work" / "edition-refinement-slate.md"
DEFAULT_EDITION_SLATE_HTML = SCRIPT_DIR / "work" / "edition-refinement-slate.html"
DEFAULT_RETENTION_OUTPUT = SCRIPT_DIR / "work" / "cache-retention-plan.json"
DEFAULT_RETENTION_DOC = SCRIPT_DIR / "work" / "cache-retention-plan.md"
DEFAULT_RETENTION_HTML = SCRIPT_DIR / "work" / "cache-retention-plan.html"
DEFAULT_SOURCE_CURATION_OUTPUT = SCRIPT_DIR / "work" / "source-curation-plan.json"
DEFAULT_SOURCE_CURATION_DOC = SCRIPT_DIR / "work" / "source-curation-plan.md"
DEFAULT_SOURCE_CURATION_HTML = SCRIPT_DIR / "work" / "source-curation-plan.html"
DEFAULT_AUDIO_CONTROL_OUTPUT = SCRIPT_DIR / "work" / "audio-control-plan.json"
DEFAULT_AUDIO_CONTROL_DOC = SCRIPT_DIR / "work" / "audio-control-plan.md"
DEFAULT_AUDIO_CONTROL_HTML = SCRIPT_DIR / "work" / "audio-control-plan.html"
DEFAULT_PAIRED_WORK_ORDER_OUTPUT = SCRIPT_DIR / "work" / "paired-work-order.json"
DEFAULT_PAIRED_WORK_ORDER_DOC = SCRIPT_DIR / "work" / "paired-work-order.md"
DEFAULT_PAIRED_WORK_ORDER_HTML = SCRIPT_DIR / "work" / "paired-work-order.html"
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
PHASE_PRIORITY = {
    "story": 90,
    "visual-sketch": 74,
    "reel": 64,
}
PACKAGE_ROOT = "packages/triptych-video-canon-site"


def human_size(value: Any) -> str:
    return generated_inventory.human_bytes(int(value or 0)) if isinstance(value, int | float) else "0 B"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private read-only checkpoint for the overnight triptych workstream. "
            "The receipt summarizes creative coverage, public-share readiness, and cleanup pressure."
        )
    )
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Generated site directory.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR, help="Generated package directory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Private JSON checkpoint path.")
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC, help="Private markdown checkpoint path.")
    parser.add_argument(
        "--focus-output",
        type=Path,
        default=DEFAULT_FOCUS_OUTPUT,
        help="Private JSON release-focus path.",
    )
    parser.add_argument(
        "--focus-doc",
        type=Path,
        default=DEFAULT_FOCUS_DOC,
        help="Private markdown release-focus path.",
    )
    parser.add_argument(
        "--focus-html",
        type=Path,
        default=DEFAULT_FOCUS_HTML,
        help="Private HTML release-focus review path.",
    )
    parser.add_argument(
        "--auditions-output",
        type=Path,
        default=DEFAULT_AUDITIONS_OUTPUT,
        help="Private JSON control-auditions path.",
    )
    parser.add_argument(
        "--auditions-doc",
        type=Path,
        default=DEFAULT_AUDITIONS_DOC,
        help="Private markdown control-auditions path.",
    )
    parser.add_argument(
        "--auditions-html",
        type=Path,
        default=DEFAULT_AUDITIONS_HTML,
        help="Private HTML control-auditions path.",
    )
    parser.add_argument(
        "--render-queue-output",
        type=Path,
        default=DEFAULT_RENDER_QUEUE_OUTPUT,
        help="Private JSON next-render queue path.",
    )
    parser.add_argument(
        "--render-queue-doc",
        type=Path,
        default=DEFAULT_RENDER_QUEUE_DOC,
        help="Private markdown next-render queue path.",
    )
    parser.add_argument(
        "--render-queue-html",
        type=Path,
        default=DEFAULT_RENDER_QUEUE_HTML,
        help="Private HTML next-render queue path.",
    )
    parser.add_argument(
        "--dashboard-output",
        type=Path,
        default=DEFAULT_DASHBOARD_OUTPUT,
        help="Private JSON overnight dashboard path.",
    )
    parser.add_argument(
        "--dashboard-doc",
        type=Path,
        default=DEFAULT_DASHBOARD_DOC,
        help="Private markdown overnight dashboard path.",
    )
    parser.add_argument(
        "--dashboard-html",
        type=Path,
        default=DEFAULT_DASHBOARD_HTML,
        help="Private HTML overnight dashboard path.",
    )
    parser.add_argument(
        "--hosting-output",
        type=Path,
        default=DEFAULT_HOSTING_OUTPUT,
        help="Private JSON static-hosting handoff path.",
    )
    parser.add_argument(
        "--hosting-doc",
        type=Path,
        default=DEFAULT_HOSTING_DOC,
        help="Private markdown static-hosting handoff path.",
    )
    parser.add_argument(
        "--hosting-html",
        type=Path,
        default=DEFAULT_HOSTING_HTML,
        help="Private HTML static-hosting handoff path.",
    )
    parser.add_argument(
        "--first-release-output",
        type=Path,
        default=DEFAULT_FIRST_RELEASE_OUTPUT,
        help="Private JSON first-release packet path.",
    )
    parser.add_argument(
        "--first-release-doc",
        type=Path,
        default=DEFAULT_FIRST_RELEASE_DOC,
        help="Private markdown first-release packet path.",
    )
    parser.add_argument(
        "--first-release-html",
        type=Path,
        default=DEFAULT_FIRST_RELEASE_HTML,
        help="Private HTML first-release packet path.",
    )
    parser.add_argument(
        "--posting-receipt-output",
        type=Path,
        default=DEFAULT_POSTING_RECEIPT_OUTPUT,
        help="Private JSON posting receipt template path.",
    )
    parser.add_argument(
        "--posting-receipt-doc",
        type=Path,
        default=DEFAULT_POSTING_RECEIPT_DOC,
        help="Private markdown posting receipt template path.",
    )
    parser.add_argument(
        "--posting-receipt-html",
        type=Path,
        default=DEFAULT_POSTING_RECEIPT_HTML,
        help="Private HTML posting receipt template path.",
    )
    parser.add_argument(
        "--release-cadence-output",
        type=Path,
        default=DEFAULT_RELEASE_CADENCE_OUTPUT,
        help="Private JSON release-cadence plan path.",
    )
    parser.add_argument(
        "--release-cadence-doc",
        type=Path,
        default=DEFAULT_RELEASE_CADENCE_DOC,
        help="Private markdown release-cadence plan path.",
    )
    parser.add_argument(
        "--release-cadence-html",
        type=Path,
        default=DEFAULT_RELEASE_CADENCE_HTML,
        help="Private HTML release-cadence plan path.",
    )
    parser.add_argument(
        "--edition-slate-output",
        type=Path,
        default=DEFAULT_EDITION_SLATE_OUTPUT,
        help="Private JSON edition-refinement slate path.",
    )
    parser.add_argument(
        "--edition-slate-doc",
        type=Path,
        default=DEFAULT_EDITION_SLATE_DOC,
        help="Private markdown edition-refinement slate path.",
    )
    parser.add_argument(
        "--edition-slate-html",
        type=Path,
        default=DEFAULT_EDITION_SLATE_HTML,
        help="Private HTML edition-refinement slate path.",
    )
    parser.add_argument(
        "--retention-output",
        type=Path,
        default=DEFAULT_RETENTION_OUTPUT,
        help="Private JSON cache-retention plan path.",
    )
    parser.add_argument(
        "--retention-doc",
        type=Path,
        default=DEFAULT_RETENTION_DOC,
        help="Private markdown cache-retention plan path.",
    )
    parser.add_argument(
        "--retention-html",
        type=Path,
        default=DEFAULT_RETENTION_HTML,
        help="Private HTML cache-retention plan path.",
    )
    parser.add_argument(
        "--source-curation-output",
        type=Path,
        default=DEFAULT_SOURCE_CURATION_OUTPUT,
        help="Private JSON source-curation plan path.",
    )
    parser.add_argument(
        "--source-curation-doc",
        type=Path,
        default=DEFAULT_SOURCE_CURATION_DOC,
        help="Private markdown source-curation plan path.",
    )
    parser.add_argument(
        "--source-curation-html",
        type=Path,
        default=DEFAULT_SOURCE_CURATION_HTML,
        help="Private HTML source-curation plan path.",
    )
    parser.add_argument(
        "--audio-control-output",
        type=Path,
        default=DEFAULT_AUDIO_CONTROL_OUTPUT,
        help="Private JSON audio-control plan path.",
    )
    parser.add_argument(
        "--audio-control-doc",
        type=Path,
        default=DEFAULT_AUDIO_CONTROL_DOC,
        help="Private markdown audio-control plan path.",
    )
    parser.add_argument(
        "--audio-control-html",
        type=Path,
        default=DEFAULT_AUDIO_CONTROL_HTML,
        help="Private HTML audio-control plan path.",
    )
    parser.add_argument(
        "--paired-work-order-output",
        type=Path,
        default=DEFAULT_PAIRED_WORK_ORDER_OUTPUT,
        help="Private JSON paired work-order path.",
    )
    parser.add_argument(
        "--paired-work-order-doc",
        type=Path,
        default=DEFAULT_PAIRED_WORK_ORDER_DOC,
        help="Private markdown paired work-order path.",
    )
    parser.add_argument(
        "--paired-work-order-html",
        type=Path,
        default=DEFAULT_PAIRED_WORK_ORDER_HTML,
        help="Private HTML paired work-order path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print summary without writing files.")
    parser.add_argument("--json", action="store_true", help="Emit the checkpoint JSON to stdout.")
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def compact_edition(edition: dict[str, Any]) -> dict[str, Any]:
    score = edition.get("arrangement_score")
    if not isinstance(score, dict):
        score = {}
    counts = edition.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    presets = edition.get("control_presets")
    if not isinstance(presets, list):
        presets = []
    default_preset = "none"
    for preset in presets:
        if isinstance(preset, dict) and preset.get("default") is True:
            default_preset = str(preset.get("id") or "default")
            break
    public_presets = []
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        public_presets.append(
            {
                "id": str(preset.get("id") or ""),
                "label": str(preset.get("label") or preset.get("id") or ""),
                "default": preset.get("default") is True,
                "href": str(preset.get("href") or ""),
            }
        )
    return {
        "slug": str(edition.get("slug") or ""),
        "work_title": str(edition.get("work_title") or edition.get("title") or ""),
        "family": str(edition.get("family") or ""),
        "clips": int(counts.get("clips", 0)) if isinstance(counts.get("clips"), int) else 0,
        "post_exports": int(counts.get("post_exports", 0)) if isinstance(counts.get("post_exports"), int) else 0,
        "visual_sketches": int(counts.get("visual_sketches", 0)) if isinstance(counts.get("visual_sketches"), int) else 0,
        "default_preset": default_preset,
        "arrangement_style": str(score.get("style") or "none"),
        "arrangement_cells": int(score.get("cell_count", 0)) if isinstance(score.get("cell_count"), int) else 0,
        "page": str(edition.get("page") or ""),
        "control_presets": public_presets,
    }


def markdown_text(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("\n", " ").strip()
    for char in "\\`*_{}[]<>#|":
        text = text.replace(char, "")
    return " ".join(text.split())


def html_text(value: Any) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def work_href(ref: Any) -> str:
    if not isinstance(ref, str) or not ref:
        return "#"
    return "../" + ref


def arrangement_label(edition: dict[str, Any]) -> str:
    score = edition.get("arrangement_score")
    if isinstance(score, dict):
        label = score.get("preview_label") or score.get("style") or score.get("family")
        if isinstance(label, str) and label:
            return markdown_text(label)
    return markdown_text(edition.get("family") or "triptych")


def caption_seed(edition: dict[str, Any], item: dict[str, Any]) -> str:
    title = markdown_text(edition.get("work_title") or edition.get("title") or edition.get("slug"))
    label = markdown_text(item.get("label") or item.get("name") or item.get("kind"))
    score = arrangement_label(edition)
    if str(edition.get("family")) == "signal_damage":
        body = "compression, reversal, and signal damage become the surface"
    else:
        body = "fragments pass across the triptych as a canon"
    return f"{title} / {label}. {score}: {body}."


def edit_prompt(edition: dict[str, Any], item: dict[str, Any]) -> str:
    title = markdown_text(edition.get("work_title") or edition.get("slug"))
    style = arrangement_label(edition)
    kind = str(item.get("kind") or "item")
    if str(edition.get("family")) == "signal_damage":
        return (
            f"Review {title} as {kind}: preserve the {style} damage map, then test whether reversal, "
            "compression, and browser playback rate make the signal feel more alive without rerendering."
        )
    if style.startswith("score"):
        return (
            f"Review {title} as {kind}: keep the Ballerina Whole structural score legible, then test "
            "whether panel order or a text preset should lead the next refinement."
        )
    if style.startswith("fracture"):
        return (
            f"Review {title} as {kind}: keep rupture and delayed consequence visible, then test whether "
            "broken-grid cells need a sharper text score before the next render."
        )
    return (
        f"Review {title} as {kind}: preserve the {style} composition language, then choose whether the "
        "next move is posting, caption refinement, or a lighter draft render."
    )


def platform_targets(kind: str) -> list[str]:
    if kind == "story":
        return ["Instagram Story", "YouTube Shorts draft", "portfolio teaser"]
    if kind == "reel":
        return ["Instagram Reel", "YouTube Shorts draft", "panel excerpt"]
    return ["GitHub/portfolio context", "process post"]


def media_summary(item: dict[str, Any]) -> dict[str, Any]:
    media = item.get("media")
    if not isinstance(media, dict):
        media = {}
    width = media.get("width")
    height = media.get("height")
    duration = media.get("duration_seconds")
    size = media.get("size_bytes")
    return {
        "duration_seconds": duration if isinstance(duration, int | float) else 0,
        "size_bytes": size if isinstance(size, int) else 0,
        "human_size": human_size(size),
        "dimensions": f"{width}x{height}" if isinstance(width, int) and isinstance(height, int) else "unknown",
        "has_audio": media.get("has_audio") is True,
    }


def item_score(edition: dict[str, Any], item: dict[str, Any]) -> int:
    kind = str(item.get("kind") or "")
    score = PHASE_PRIORITY.get(kind, 50)
    media = media_summary(item)
    arrangement = edition.get("arrangement_score")
    if isinstance(arrangement, dict):
        if arrangement.get("model"):
            score += 18
        if isinstance(arrangement.get("cell_count"), int) and arrangement["cell_count"] >= 9:
            score += 8
        if arrangement.get("style") in {"score", "fracture", "signal", "serial"}:
            score += 5
    if media["duration_seconds"] and float(media["duration_seconds"]) <= 45:
        score += 5
    if media["size_bytes"] and int(media["size_bytes"]) <= 4 * 1024 * 1024:
        score += 5
    if media["has_audio"] and kind in {"story", "reel"}:
        score += 4
    if not media["has_audio"] and kind == "visual-sketch":
        score += 4
    if str(edition.get("family")) == "signal_damage":
        score += 3
    return score


def release_focus(public_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    editions = public_manifest.get("editions")
    if not isinstance(editions, list):
        return []
    items: list[dict[str, Any]] = []
    for edition in editions:
        if not isinstance(edition, dict):
            continue
        release_items = edition.get("post_exports")
        if not isinstance(release_items, list):
            release_items = []
        sketch = edition.get("visual_sketch")
        if isinstance(sketch, dict):
            release_items = [*release_items, sketch]
        for item in release_items:
            if not isinstance(item, dict):
                continue
            media = media_summary(item)
            kind = str(item.get("kind") or "")
            href = str(item.get("href") or "")
            edition_slug = str(edition.get("slug") or "")
            items.append(
                {
                    "edition": edition_slug,
                    "work_title": str(edition.get("work_title") or edition.get("title") or edition.get("slug") or ""),
                    "family": str(edition.get("family") or ""),
                    "label": str(item.get("label") or item.get("name") or kind),
                    "kind": kind,
                    "href": href,
                    "package_media_href": f"{PACKAGE_ROOT}/{href}",
                    "release_board_href": f"{PACKAGE_ROOT}/release-board.html",
                    "release_player_href": f"{PACKAGE_ROOT}/release-player.html?{urlencode({'edition': edition_slug, 'mode': 'sequential', 'muted': '0', 'volume': '0.35', 'rate': '0.75'})}",
                    "score": item_score(edition, item),
                    "targets": platform_targets(kind),
                    "media": media,
                    "caption_seed": caption_seed(edition, item),
                    "edit_prompt": edit_prompt(edition, item),
                    "why": focus_reason(edition, item, media),
                    "product_shop_gate": "deferred until explicit product review",
                    "review_before_posting": [
                        "Open package_media_href or release_player_href from the verified package.",
                        "Confirm the caption keeps source albums, work receipts, and private paths out.",
                        "Keep product/shop use deferred unless a concrete product object is selected.",
                    ],
                }
            )
    top_by_role: list[dict[str, Any]] = []
    role_filters = (
        ("story anchor", lambda item: item["kind"] == "story"),
        ("process sketch", lambda item: item["kind"] == "visual-sketch"),
        ("signal contrast", lambda item: item["family"] == "signal_damage" and item["kind"] in {"story", "reel"}),
        ("panel excerpt", lambda item: item["kind"] == "reel"),
    )
    used_hrefs: set[str] = set()
    for role, predicate in role_filters:
        candidates = [item for item in items if predicate(item) and item["href"] not in used_hrefs]
        if not candidates:
            continue
        chosen = sorted(candidates, key=lambda item: (-int(item["score"]), item["edition"], item["label"]))[0]
        chosen = {**chosen, "role": role, "rank": len(top_by_role) + 1}
        used_hrefs.add(chosen["href"])
        top_by_role.append(chosen)
    return top_by_role


def focus_reason(edition: dict[str, Any], item: dict[str, Any], media: dict[str, Any]) -> str:
    style = arrangement_label(edition)
    kind = str(item.get("kind") or "item")
    duration = media.get("duration_seconds", 0)
    size = media.get("human_size", "0 B")
    audio = "audio-bearing" if media.get("has_audio") else "silent"
    return (
        f"{kind} is verified public media for {markdown_text(edition.get('work_title') or edition.get('slug'))}; "
        f"{style}; {duration}s, {size}, {audio}."
    )


def public_family_counts(editions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edition in editions:
        family = str(edition.get("family") or "unknown")
        counts[family] = counts.get(family, 0) + 1
    return counts


def rotation_summary(living_loop: dict[str, Any]) -> list[dict[str, Any]]:
    rotations = living_loop.get("rotation_sets")
    if not isinstance(rotations, list):
        return []
    summary: list[dict[str, Any]] = []
    for rotation in rotations:
        if not isinstance(rotation, dict):
            continue
        slots = rotation.get("slots")
        if not isinstance(slots, list):
            slots = []
        first_href = ""
        if slots and isinstance(slots[0], dict):
            first_href = str(slots[0].get("href") or "")
        summary.append(
            {
                "id": str(rotation.get("id") or ""),
                "label": str(rotation.get("label") or ""),
                "volume": str(rotation.get("volume") or ""),
                "rate": str(rotation.get("rate") or ""),
                "slot_count": len(slots),
                "first_href": first_href,
            }
        )
    return summary


def package_summary(package_dir: Path) -> dict[str, Any]:
    manifest = load_json(package_dir / "package-manifest.json")
    if not manifest:
        return {"exists": False, "schema_ok": False, "file_count": 0, "size_bytes": 0}
    return {
        "exists": True,
        "schema_ok": manifest.get("schema") == "triptych.public-site-package.v1",
        "file_count": manifest.get("file_count", 0),
        "size_bytes": manifest.get("size_bytes", 0),
        "human_size": generated_inventory.human_bytes(int(manifest.get("size_bytes", 0) or 0)),
        "entrypoint": manifest.get("entrypoint"),
    }


def checkpoint(site_dir: Path, package_dir: Path) -> dict[str, Any]:
    public_manifest = load_json(site_dir / "public-manifest.json")
    living_loop = load_json(site_dir / "living-loop.json")
    curatorial_score = load_json(site_dir / "curatorial-score.json")
    release_matrix = load_json(site_dir / "release-matrix.json")
    editions = public_manifest.get("editions") if isinstance(public_manifest.get("editions"), list) else []
    compact_editions = [compact_edition(edition) for edition in editions if isinstance(edition, dict)]
    reports = [generated_inventory.lane_report(lane) for lane in generated_inventory.LANES]
    cleanup = generated_inventory.cleanup_candidates(reports)
    package = package_summary(package_dir)
    totals = public_manifest.get("totals") if isinstance(public_manifest.get("totals"), dict) else {}
    rotations = rotation_summary(living_loop)
    focus_items = release_focus(public_manifest)
    release_targets = release_matrix.get("targets") if isinstance(release_matrix.get("targets"), list) else []
    checks = [
        {
            "id": "public-manifest-schema",
            "ok": public_manifest.get("schema") == "triptych.public-release-manifest.v1",
            "evidence": "site/public-manifest.json",
        },
        {
            "id": "living-loop-rotations",
            "ok": living_loop.get("schema") == "triptych.living-loop.v1" and len(rotations) >= 3,
            "evidence": "site/living-loop.json",
        },
        {
            "id": "package-manifest",
            "ok": package["exists"] is True and package["schema_ok"] is True,
            "evidence": "packages/triptych-video-canon-site/package-manifest.json",
        },
        {
            "id": "porn-gated",
            "ok": not (site_dir / "editions" / "porn" / "flash-copy.json").exists(),
            "evidence": "site/editions/porn/flash-copy.json absent",
        },
        {
            "id": "cleanup-plan-read-only",
            "ok": all(candidate.get("manual_only") is True for candidate in cleanup),
            "evidence": "generated_inventory.py --cleanup-plan",
        },
        {
            "id": "release-focus-local",
            "ok": bool(focus_items)
            and all(
                isinstance(item.get("href"), str)
                and item["href"]
                and not item["href"].startswith(("/", "http://", "https://"))
                and ".." not in Path(item["href"]).parts
                and item.get("product_shop_gate") == "deferred until explicit product review"
                for item in focus_items
            ),
            "evidence": "site/public-manifest.json",
        },
    ]
    return {
        "schema": "triptych.overnight-checkpoint.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "private paired creative/containment checkpoint for the incubated triptych-video-canon workstream",
        "inputs": {
            "public_manifest": "site/public-manifest.json",
            "living_loop": "site/living-loop.json",
            "curatorial_score": "site/curatorial-score.json",
            "release_matrix": "site/release-matrix.json",
            "package_manifest": "packages/triptych-video-canon-site/package-manifest.json",
        },
        "creative_track": {
            "edition_count": len(compact_editions),
            "families": public_family_counts(compact_editions),
            "public_items": int(curatorial_score.get("item_count", 0) or 0),
            "runtime_seconds": curatorial_score.get("total_duration_seconds", 0),
            "post_exports": int(totals.get("post_exports", 0) or 0),
            "visual_sketches": int(totals.get("visual_sketches", 0) or 0),
            "living_rotation_sets": rotations,
            "release_focus": focus_items,
            "release_targets": [
                {
                    "target": str(target.get("target") or ""),
                    "item_count": target.get("item_count", 0),
                }
                for target in release_targets
                if isinstance(target, dict)
            ],
            "editions": compact_editions,
        },
        "containment_track": {
            "package": package,
            "inventory": [asdict(report) for report in reports],
            "cleanup_candidates": cleanup,
            "regeneration_checkpoints": generated_inventory.REGENERATION_CHECKPOINTS,
            "public_share_gates": [
                "python3 verify_editions.py",
                "python3 verify_public_site.py",
                "python3 package_public_site.py",
                "python3 verify_package.py",
            ],
        },
        "checks": checks,
        "next_autonomous_moves": [
            "Review the living-loop rotation sets in the package before rendering new media.",
            "Review the release-focus recommendations and choose one Story/Reel/sketch output to post or refine.",
            "If disk pressure matters, start with the renders/ cleanup candidate only after confirming rerender commands.",
            "Keep Porn local-only unless explicit public-export review changes the gate.",
        ],
    }


def validate_private_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.overnight-checkpoint.v1":
        errors.append("unexpected checkpoint schema")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("checks must be a non-empty list")
    else:
        for check in checks:
            if not isinstance(check, dict) or check.get("ok") is not True:
                errors.append(f"checkpoint check failed: {check}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"checkpoint contains private token {token!r}")
    return errors


def release_focus_payload(payload: dict[str, Any]) -> dict[str, Any]:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    return {
        "schema": "triptych.release-focus.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "public_manifest": payload["inputs"]["public_manifest"],
        "release_board": "site/release-board.html",
        "release_copy": "site/release-copy.md",
        "release_queue": "site/release-queue.md",
        "package_entrypoint": "packages/triptych-video-canon-site/index.html",
        "package_ready": containment["package"].get("exists") is True and containment["package"].get("schema_ok") is True,
        "product_shop_gate": "deferred until explicit product review",
        "focus_count": len(creative["release_focus"]),
        "focus": creative["release_focus"],
        "operating_gates": [
            "Use only package-relative public media hrefs.",
            "Open the release board or package before posting.",
            "Keep source albums, work receipts, samples, local Photos paths, and private notes out of captions.",
            "Product/shop use remains deferred until a concrete product object is selected.",
            "This artifact is private workflow state under work/ and should be regenerated from sanitized public receipts.",
        ],
    }


def package_href(ref: Any) -> str:
    raw = str(ref or "").lstrip("/")
    if not raw:
        return ""
    if raw.startswith(f"{PACKAGE_ROOT}/"):
        return raw
    return f"{PACKAGE_ROOT}/{raw}"


def edition_recipe_href(page: str, params: dict[str, str]) -> str:
    return package_href(f"{page}?{urlencode(params)}")


def control_auditions_payload(payload: dict[str, Any]) -> dict[str, Any]:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    auditions: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        auditions.append(
            {
                "rank": len(auditions) + 1,
                "media_generation": "none",
                "source_access": "none",
                "product_shop_gate": "deferred until explicit product review",
                **item,
            }
        )

    for edition in creative["editions"]:
        slug = str(edition.get("slug") or "")
        page = str(edition.get("page") or "")
        title = str(edition.get("work_title") or slug)
        default_preset = str(edition.get("default_preset") or "")
        if not slug or not page:
            continue
        for preset in edition.get("control_presets", []):
            if not isinstance(preset, dict) or not preset.get("href"):
                continue
            add(
                {
                    "id": f"{slug}-preset-{preset.get('id')}",
                    "category": "edition preset",
                    "edition": slug,
                    "work_title": title,
                    "label": str(preset.get("label") or preset.get("id") or "Preset"),
                    "href": package_href(preset.get("href")),
                    "intent": "Open a receipt-authored landing preset from the verified package.",
                    "controls": {
                        "preset": str(preset.get("id") or ""),
                        "default": preset.get("default") is True,
                    },
                }
            )

        preset_value = default_preset if default_preset and default_preset != "none" else slug
        sketch_surface = "sketch" if int(edition.get("visual_sketches", 0) or 0) else "canon"
        recipes = [
            (
                "sketch-pingpong-recomposed",
                "Sketch pingpong recomposed",
                {
                    "preset": preset_value,
                    "surface": sketch_surface,
                    "dir": "pingpong",
                    "order": "rml",
                    "start": "random",
                    "labels": "0",
                    "audio": "0",
                },
                "Audition the album-shape sketch as a moving structural score without loading source media.",
            ),
            (
                "canon-forward-audible",
                "Canon forward audible",
                {
                    "preset": preset_value,
                    "surface": "canon",
                    "dir": "forward",
                    "order": "lmr",
                    "start": "oldest",
                    "labels": "0",
                    "audio": "1",
                    "vol": "0.35",
                    "left": "0.8",
                    "middle": "0.55",
                    "right": "0.35",
                },
                "Audition the canonical left-to-right movement with restrained per-panel sound.",
            ),
            (
                "canon-reverse-quiet",
                "Canon reverse quiet",
                {
                    "preset": preset_value,
                    "surface": "canon",
                    "dir": "reverse",
                    "order": "mlr",
                    "start": "random",
                    "labels": "0",
                    "audio": "1",
                    "vol": "0.25",
                    "left": "0.25",
                    "middle": "0.45",
                    "right": "0.75",
                },
                "Audition reverse playback and a rearranged panel balance before spending render time.",
            ),
        ]
        for suffix, label, params, intent in recipes:
            add(
                {
                    "id": f"{slug}-{suffix}",
                    "category": "text recipe",
                    "edition": slug,
                    "work_title": title,
                    "label": label,
                    "href": edition_recipe_href(page, params),
                    "intent": intent,
                    "controls": params,
                }
            )

    for rotation in creative["living_rotation_sets"]:
        first_href = str(rotation.get("first_href") or "")
        if not first_href:
            continue
        add(
            {
                "id": f"loop-{rotation.get('id')}",
                "category": "living loop",
                "edition": "all",
                "work_title": "Triptych Video Canon",
                "label": str(rotation.get("label") or rotation.get("id") or "Living loop"),
                "href": package_href(first_href),
                "intent": "Open a seeded package loop with browser-only volume/rate changes.",
                "controls": {
                    "volume": str(rotation.get("volume") or ""),
                    "rate": str(rotation.get("rate") or ""),
                    "slot_count": rotation.get("slot_count", 0),
                },
            }
        )

    seen_focus_players: set[str] = set()
    for focus in creative["release_focus"]:
        href = str(focus.get("release_player_href") or "")
        edition = str(focus.get("edition") or "")
        if not href or href in seen_focus_players:
            continue
        seen_focus_players.add(href)
        add(
            {
                "id": f"focus-player-{edition}",
                "category": "focus player",
                "edition": edition,
                "work_title": str(focus.get("work_title") or edition),
                "label": f"{focus.get('work_title') or edition} release player",
                "href": href,
                "intent": "Open the current private release-focus edition in the verified package player.",
                "controls": {
                    "mode": "sequential",
                    "volume": "0.35",
                    "rate": "0.75",
                },
            }
        )

    return {
        "schema": "triptych.control-auditions.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "public_manifest": payload["inputs"]["public_manifest"],
        "playback_contract": "site/playback-contract.json",
        "living_loop": payload["inputs"]["living_loop"],
        "package_entrypoint": "packages/triptych-video-canon-site/index.html",
        "package_ready": containment["package"].get("exists") is True and containment["package"].get("schema_ok") is True,
        "media_generation": "none",
        "source_access": "none",
        "product_shop_gate": "deferred until explicit product review",
        "audition_count": len(auditions),
        "auditions": auditions,
        "operating_gates": [
            "Use these as text-control auditions; do not render new media until one recipe proves worth baking.",
            "All hrefs must stay package-local and resolve inside incubator/triptych-video-canon/.",
            "Audio/rate/direction/panel-order controls are browser or landing-page controls, not source-media mutations.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_release_focus_payload(payload: dict[str, Any], site_dir: Path) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.release-focus.v1":
        errors.append("unexpected release-focus schema")
    if payload.get("package_ready") is not True:
        errors.append("release-focus package_ready must be true")
    focus = payload.get("focus")
    if not isinstance(focus, list) or not focus:
        errors.append("release-focus focus must be a non-empty list")
        focus = []
    if payload.get("focus_count") != len(focus):
        errors.append("release-focus focus_count must match focus length")
    for index, item in enumerate(focus, start=1):
        if not isinstance(item, dict):
            errors.append(f"release-focus item {index} must be an object")
            continue
        href = item.get("href")
        if not isinstance(href, str) or not href:
            errors.append(f"release-focus item {index} missing href")
            continue
        href_path = Path(href)
        if href_path.is_absolute() or ".." in href_path.parts:
            errors.append(f"release-focus item {index} href escapes site: {href}")
            continue
        target = (site_dir / href_path).resolve()
        if not path_inside(target, site_dir):
            errors.append(f"release-focus item {index} href escapes site: {href}")
        elif not target.exists():
            errors.append(f"release-focus item {index} href does not exist: {href}")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"release-focus item {index} product gate must remain deferred")
        for field in ("package_media_href", "release_board_href", "release_player_href"):
            raw_ref = item.get(field)
            if not isinstance(raw_ref, str) or not raw_ref:
                errors.append(f"release-focus item {index} missing {field}")
                continue
            ref_path = Path(raw_ref.split("?", 1)[0])
            if ref_path.is_absolute() or ".." in ref_path.parts:
                errors.append(f"release-focus item {index} {field} escapes incubator: {raw_ref}")
                continue
            ref_target = (SCRIPT_DIR / ref_path).resolve()
            if not path_inside(ref_target, SCRIPT_DIR):
                errors.append(f"release-focus item {index} {field} escapes incubator: {raw_ref}")
            elif not ref_target.exists():
                errors.append(f"release-focus item {index} {field} does not exist: {raw_ref}")
        caption = str(item.get("caption_seed") or "")
        edit = str(item.get("edit_prompt") or "")
        if not edit:
            errors.append(f"release-focus item {index} edit_prompt must be present")
        for token in PRIVATE_TEXT:
            if token in caption:
                errors.append(f"release-focus item {index} caption contains private token {token!r}")
            if token in edit:
                errors.append(f"release-focus item {index} edit prompt contains private token {token!r}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"release-focus contains private token {token!r}")
    return errors


def validate_control_auditions_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.control-auditions.v1":
        errors.append("unexpected control-auditions schema")
    if payload.get("package_ready") is not True:
        errors.append("control-auditions package_ready must be true")
    if payload.get("media_generation") != "none":
        errors.append("control-auditions media_generation must be none")
    if payload.get("source_access") != "none":
        errors.append("control-auditions source_access must be none")
    if payload.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("control-auditions product gate must remain deferred")
    auditions = payload.get("auditions")
    if not isinstance(auditions, list) or not auditions:
        errors.append("control-auditions auditions must be a non-empty list")
        auditions = []
    if payload.get("audition_count") != len(auditions):
        errors.append("control-auditions audition_count must match auditions length")
    categories = {str(item.get("category") or "") for item in auditions if isinstance(item, dict)}
    for required in ("edition preset", "text recipe", "living loop", "focus player"):
        if required not in categories:
            errors.append(f"control-auditions missing category {required!r}")
    for index, item in enumerate(auditions, start=1):
        if not isinstance(item, dict):
            errors.append(f"control-auditions item {index} must be an object")
            continue
        href = item.get("href")
        if not isinstance(href, str) or not href:
            errors.append(f"control-auditions item {index} missing href")
            continue
        if not href.startswith(f"{PACKAGE_ROOT}/"):
            errors.append(f"control-auditions item {index} href must stay in package: {href}")
        ref_path = Path(href.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"control-auditions item {index} href escapes incubator: {href}")
            continue
        ref_target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(ref_target, SCRIPT_DIR):
            errors.append(f"control-auditions item {index} href escapes incubator: {href}")
        elif not ref_target.exists():
            errors.append(f"control-auditions item {index} href does not exist: {href}")
        if item.get("media_generation") != "none":
            errors.append(f"control-auditions item {index} media_generation must be none")
        if item.get("source_access") != "none":
            errors.append(f"control-auditions item {index} source_access must be none")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"control-auditions item {index} product gate must remain deferred")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"control-auditions contains private token {token!r}")
    return errors


def render_queue_payload(payload: dict[str, Any]) -> dict[str, Any]:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    focus_order: dict[str, int] = {}
    focus_reasons: dict[str, str] = {}
    for focus in creative["release_focus"]:
        edition = str(focus.get("edition") or "")
        if edition and edition not in focus_order:
            focus_order[edition] = int(focus.get("rank", len(focus_order) + 1) or len(focus_order) + 1)
            focus_reasons[edition] = str(focus.get("why") or "")

    profiles = {
        "ballerina": ("share", "all", "Highest release-focus score; test a more durable posting render after the Ballerina Whole audition pass."),
        "glitche": ("draft", "story", "Signal-damage contrast is release-relevant, but keep it story-only until the package size impact is known."),
        "accidents": ("share", "story", "Fracture map needs a stronger story pass before expanding to all panel Reels."),
        "noonlight": ("share", "all", "Small public footprint makes it a good share-profile control case for serial portrait/light."),
    }

    queue: list[dict[str, Any]] = []
    public_editions = [
        edition
        for edition in creative["editions"]
        if isinstance(edition, dict) and str(edition.get("slug") or "") != "porn"
    ]
    public_editions.sort(
        key=lambda edition: (
            focus_order.get(str(edition.get("slug") or ""), 50),
            str(edition.get("slug") or ""),
        )
    )
    render_pressure = next(
        (candidate for candidate in containment["cleanup_candidates"] if candidate.get("lane") == "renders"),
        {},
    )
    for edition in public_editions:
        slug = str(edition.get("slug") or "")
        if not slug:
            continue
        profile, pack, reason = profiles.get(
            slug,
            ("draft", "story", "Keep the next render bounded until this edition has a stronger release reason."),
        )
        render_command = f"python3 build_post_pack.py {slug} --skip-import --profile {profile} --pack {pack}"
        dry_run_command = f"{render_command} --dry-run"
        project_manifest = f"work/editions/{slug}/project.json"
        queue.append(
            {
                "rank": len(queue) + 1,
                "edition": slug,
                "work_title": str(edition.get("work_title") or slug),
                "family": str(edition.get("family") or ""),
                "profile": profile,
                "pack": pack,
                "render_command": render_command,
                "dry_run_command": dry_run_command,
                "project_manifest": project_manifest,
                "current_package_page": package_href(edition.get("page")),
                "expected_public_receipt": f"site/editions/{slug}/flash-copy.json",
                "expected_package_receipt": f"{PACKAGE_ROOT}/editions/{slug}/flash-copy.json",
                "why": focus_reasons.get(slug) or reason,
                "render_pressure_note": (
                    f"renders lane currently {render_pressure.get('human_size', 'unknown')}; use cleanup plan before broad rerenders"
                ),
                "review_before_render": [
                    "Open work/control-auditions.html and test the matching edition recipes first.",
                    "Run dry_run_command before render_command.",
                    "Do not pass --photos-export-missing unless the human explicitly authorizes Photos export.",
                    "Do not delete renders/ or site/ while this queue is being evaluated.",
                ],
                "post_render_gates": [
                    f"python3 verify_post_pack.py {project_manifest}",
                    "python3 verify_public_site.py",
                    "python3 package_public_site.py",
                    "python3 verify_package.py",
                    "python3 overnight_checkpoint.py",
                    "python3 verify_private_workflow.py",
                ],
                "media_generation": "planned-only",
                "source_access": "staged-project-only",
                "destructive_actions": "none",
                "product_shop_gate": "deferred until explicit product review",
            }
        )

    return {
        "schema": "triptych.next-render-queue.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_release_focus": "work/release-focus.json",
        "source_control_auditions": "work/control-auditions.json",
        "package_ready": containment["package"].get("exists") is True and containment["package"].get("schema_ok") is True,
        "media_generation": "planned-only",
        "source_access": "staged-project-only",
        "destructive_actions": "none",
        "product_shop_gate": "deferred until explicit product review",
        "queue_count": len(queue),
        "queue": queue,
        "operating_gates": [
            "This queue is advisory; it must not render by itself.",
            "Run dry_run_command and review control auditions before render_command.",
            "Run every post_render_gates command after any actual render.",
            "Do not use Photos export or delete generated lanes from this queue.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_render_queue_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.next-render-queue.v1":
        errors.append("unexpected next-render queue schema")
    if payload.get("package_ready") is not True:
        errors.append("next-render queue package_ready must be true")
    if payload.get("media_generation") != "planned-only":
        errors.append("next-render queue media_generation must be planned-only")
    if payload.get("source_access") != "staged-project-only":
        errors.append("next-render queue source_access must be staged-project-only")
    if payload.get("destructive_actions") != "none":
        errors.append("next-render queue destructive_actions must be none")
    if payload.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("next-render queue product gate must remain deferred")
    queue = payload.get("queue")
    if not isinstance(queue, list) or not queue:
        errors.append("next-render queue must be a non-empty list")
        queue = []
    if payload.get("queue_count") != len(queue):
        errors.append("next-render queue_count must match queue length")
    for index, item in enumerate(queue, start=1):
        if not isinstance(item, dict):
            errors.append(f"next-render queue item {index} must be an object")
            continue
        command = str(item.get("render_command") or "")
        dry_run = str(item.get("dry_run_command") or "")
        if not command.startswith("python3 build_post_pack.py "):
            errors.append(f"next-render queue item {index} render_command must use build_post_pack.py")
        if "--dry-run" in command:
            errors.append(f"next-render queue item {index} render_command must not include --dry-run")
        if "--photos-export-missing" in command or "--no-verify" in command or "--no-sync" in command:
            errors.append(f"next-render queue item {index} render_command contains forbidden flag")
        if dry_run != f"{command} --dry-run":
            errors.append(f"next-render queue item {index} dry_run_command must be render_command plus --dry-run")
        if item.get("media_generation") != "planned-only":
            errors.append(f"next-render queue item {index} media_generation must be planned-only")
        if item.get("source_access") != "staged-project-only":
            errors.append(f"next-render queue item {index} source_access must be staged-project-only")
        if item.get("destructive_actions") != "none":
            errors.append(f"next-render queue item {index} destructive_actions must be none")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"next-render queue item {index} product gate must remain deferred")
        for ref_field in ("project_manifest", "current_package_page", "expected_public_receipt", "expected_package_receipt"):
            ref = item.get(ref_field)
            if not isinstance(ref, str) or not ref:
                errors.append(f"next-render queue item {index} missing {ref_field}")
                continue
            ref_path = Path(ref.split("?", 1)[0])
            if ref_path.is_absolute() or ".." in ref_path.parts:
                errors.append(f"next-render queue item {index} {ref_field} escapes incubator: {ref}")
                continue
            ref_target = (SCRIPT_DIR / ref_path).resolve()
            if not path_inside(ref_target, SCRIPT_DIR):
                errors.append(f"next-render queue item {index} {ref_field} escapes incubator: {ref}")
            elif not ref_target.exists():
                errors.append(f"next-render queue item {index} {ref_field} does not exist: {ref}")
        gates = item.get("post_render_gates")
        if not isinstance(gates, list) or len(gates) < 5:
            errors.append(f"next-render queue item {index} must list post-render gates")
        else:
            required_gate_prefixes = (
                "python3 verify_post_pack.py ",
                "python3 verify_public_site.py",
                "python3 package_public_site.py",
                "python3 verify_package.py",
                "python3 overnight_checkpoint.py",
                "python3 verify_private_workflow.py",
            )
            for prefix in required_gate_prefixes:
                if not any(isinstance(gate, str) and gate.startswith(prefix) for gate in gates):
                    errors.append(f"next-render queue item {index} missing gate {prefix}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"next-render queue contains private token {token!r}")
    return errors


def static_hosting_handoff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    package = containment["package"]
    zip_ref = f"{PACKAGE_ROOT}.zip"
    entrypoints = [
        {
            "id": "index",
            "label": "Media-first index",
            "href": f"{PACKAGE_ROOT}/index.html",
            "purpose": "Primary static package entry.",
        },
        {
            "id": "release-player",
            "label": "Release player",
            "href": f"{PACKAGE_ROOT}/release-player.html",
            "purpose": "Sequential/random/kiosk playback surface.",
        },
        {
            "id": "release-board",
            "label": "Release board",
            "href": f"{PACKAGE_ROOT}/release-board.html",
            "purpose": "Posting board for public Story/Reel/sketch outputs.",
        },
        {
            "id": "exhibit-loop",
            "label": "Exhibit loop",
            "href": f"{PACKAGE_ROOT}/exhibit-loop.md",
            "purpose": "Gallery and digital-frame handoff.",
        },
        {
            "id": "living-loop",
            "label": "Living loop contract",
            "href": f"{PACKAGE_ROOT}/living-loop.md",
            "purpose": "Seeded no-regeneration loop contract.",
        },
    ]
    return {
        "schema": "triptych.static-hosting-handoff.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "public_manifest": payload["inputs"]["public_manifest"],
        "package_manifest": f"{PACKAGE_ROOT}/package-manifest.json",
        "package_dir": PACKAGE_ROOT,
        "package_zip": zip_ref,
        "package_ready": package.get("exists") is True and package.get("schema_ok") is True,
        "package_file_count": package.get("file_count", 0),
        "package_size": package.get("human_size", "0 B"),
        "media_generation": "none",
        "source_access": "none",
        "deployment": "manual static host upload only",
        "requires_secrets": False,
        "destructive_actions": "none",
        "product_shop_gate": "deferred until explicit product review",
        "creative_summary": {
            "edition_count": creative["edition_count"],
            "post_exports": creative["post_exports"],
            "visual_sketches": creative["visual_sketches"],
            "families": creative["families"],
        },
        "entrypoints": entrypoints,
        "preflight_commands": [
            "python3 verify_public_site.py",
            "python3 package_public_site.py",
            "python3 verify_package.py",
            "python3 overnight_checkpoint.py",
            "python3 verify_private_workflow.py",
        ],
        "upload_scope": [
            PACKAGE_ROOT,
            zip_ref,
        ],
        "never_upload": [
            "work/",
            "samples/",
            "renders/",
            "local photo library bundle",
            "local photo catalog database",
            "source media paths",
        ],
        "post_upload_checks": [
            "Open index.html on the hosted static URL.",
            "Open release-player.html and test one edition URL plus one kiosk URL.",
            "Confirm browser audio controls work without exposing source paths.",
            "Keep product/shop links absent until a concrete product object is selected.",
        ],
        "operating_gates": [
            "This handoff does not deploy or require hosting credentials.",
            "Only upload the verified package directory or zip.",
            "Regenerate package-manifest.json before transfer if site/ changes.",
            "Do not upload private work/, samples/, renders/, or Photos-library lanes.",
        ],
    }


def validate_static_hosting_handoff_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.static-hosting-handoff.v1":
        errors.append("unexpected static-hosting handoff schema")
    if payload.get("package_ready") is not True:
        errors.append("static-hosting handoff package_ready must be true")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "manual static host upload only"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"static-hosting handoff {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("static-hosting handoff requires_secrets must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("public_manifest", payload.get("public_manifest")),
        ("package_manifest", payload.get("package_manifest")),
        ("package_dir", payload.get("package_dir")),
        ("package_zip", payload.get("package_zip")),
    ]
    for entry in payload.get("entrypoints") or []:
        if isinstance(entry, dict):
            refs.append((f"entrypoint {entry.get('id')}", entry.get("href")))
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"static-hosting handoff missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"static-hosting handoff {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"static-hosting handoff {label} escapes incubator: {ref}")
        elif not target.exists():
            errors.append(f"static-hosting handoff {label} does not exist: {ref}")
    never_upload = payload.get("never_upload")
    if not isinstance(never_upload, list) or not {"work/", "samples/", "renders/"}.issubset(set(never_upload)):
        errors.append("static-hosting handoff must exclude work/, samples/, and renders/")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"static-hosting handoff contains private token {token!r}")
    return errors


def first_release_caption(item: dict[str, Any], tone: str) -> str:
    seed = markdown_text(item.get("caption_seed") or "")
    title = markdown_text(item.get("work_title") or item.get("edition") or "Triptych")
    label = markdown_text(item.get("label") or item.get("kind") or "release")
    if tone == "short":
        return f"{title}. {label}. A triptych canon from selected moving fragments."
    if tone == "process":
        return (
            f"{seed} This is the current first posting pass: panel movement, uneven durations, "
            "and lightweight compression left visible."
        )
    if tone == "context":
        return (
            f"{title} is one configuration of the triptych canon engine: selected media enters, "
            "moves across three panels, and becomes a browser-playable/public-package surface."
        )
    return seed


def first_release_alt_text(item: dict[str, Any]) -> str:
    title = markdown_text(item.get("work_title") or item.get("edition") or "Triptych")
    kind = markdown_text(item.get("kind") or "video")
    label = markdown_text(item.get("label") or "")
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    audio = "with audio" if media.get("has_audio") else "silent"
    detail = f" {label}" if label else ""
    return (
        f"{title}{detail}: a {kind} in three vertical panels where fragments move across "
        f"the triptych canon; {audio}."
    )


def first_release_platform_packets(selected: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "instagram-story",
            "target": "Instagram Story",
            "role": "first public post",
            "upload_ref": selected["package_media_href"],
            "caption": first_release_caption(selected, "short"),
            "alt_text": first_release_alt_text(selected),
            "review": [
                "Confirm the video opens cleanly from the verified package before posting.",
                "Keep the upload as the full three-panel Story when the selected item is a story.",
                "Do not add product/shop language on this pass.",
            ],
        },
        {
            "id": "instagram-reel-feed",
            "target": "Instagram Reel/Feed",
            "role": "caption or follow-up cut",
            "upload_ref": selected["package_media_href"],
            "caption": first_release_caption(selected, "process"),
            "alt_text": first_release_alt_text(selected),
            "review": [
                "Use this only if the Story output also reads as a feed post.",
                "Let compression and uneven source durations remain visible.",
                "Keep local source names and private workflow notes out of the caption.",
            ],
        },
        {
            "id": "youtube-shorts-draft",
            "target": "YouTube Shorts draft",
            "role": "cross-post test",
            "upload_ref": selected["package_media_href"],
            "caption": first_release_caption(selected, "process"),
            "alt_text": first_release_alt_text(selected),
            "review": [
                "Treat this as a draft unless the audio and loop feel strong after playback.",
                "Use the same verified package media rather than rendering a new one.",
                "Record the posted URL later in a private receipt, not in the public package.",
            ],
        },
        {
            "id": "github-portfolio-context",
            "target": "GitHub/portfolio context",
            "role": "process context",
            "upload_ref": selected["release_player_href"],
            "caption": first_release_caption(selected, "context"),
            "alt_text": first_release_alt_text(selected),
            "review": [
                "Point to the package player or release board when documenting the work.",
                "Keep the public page media-first; put process context outside the first viewport.",
                "Do not promote the incubator to a permanent repo from this packet alone.",
            ],
        },
    ]


def first_release_packet_payload(
    payload: dict[str, Any],
    focus: dict[str, Any],
    hosting: dict[str, Any],
) -> dict[str, Any]:
    focus_items = focus.get("focus") if isinstance(focus.get("focus"), list) else []
    selected = dict(sorted(focus_items, key=lambda item: int(item.get("rank", 999) or 999))[0]) if focus_items else {}
    if selected:
        selected["alt_text"] = first_release_alt_text(selected)
    platform_packets = first_release_platform_packets(selected) if selected else []
    return {
        "schema": "triptych.first-release-packet.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_release_focus": "work/release-focus.json",
        "source_static_hosting_handoff": "work/static-hosting-handoff.json",
        "package_ready": focus.get("package_ready") is True and hosting.get("package_ready") is True,
        "media_generation": "none",
        "source_access": "none",
        "deployment": "manual posting only",
        "requires_secrets": False,
        "destructive_actions": "none",
        "product_shop_gate": "deferred until explicit product review",
        "selected": selected,
        "platform_packet_count": len(platform_packets),
        "platform_packets": platform_packets,
        "package_entrypoints": [
            "packages/triptych-video-canon-site/index.html",
            "packages/triptych-video-canon-site/release-board.html",
            "packages/triptych-video-canon-site/release-player.html",
        ],
        "preflight_commands": [
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "review_before_posting": [
            "Open work/first-release-packet.html and play the selected media.",
            "Open work/static-hosting-handoff.html if posting from a hosted copy.",
            "Confirm captions do not include private source albums, local paths, or workflow receipts.",
            "Keep product/shop use deferred until a concrete product object is selected.",
        ],
        "post_posting_receipt": [
            "Record the platform, posted URL, caption variant used, and posting date in a future private receipt.",
            "If the post leads to a new edit decision, update text presets before rendering more media.",
            "Do not mutate the public package solely to record social-platform state.",
        ],
        "operating_gates": [
            "This packet is private workflow state under work/ and should not be packaged.",
            "It selects from verified package media only and generates no new media.",
            "All upload refs must resolve inside incubator/triptych-video-canon/.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_first_release_packet_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.first-release-packet.v1":
        errors.append("unexpected first-release packet schema")
    if payload.get("package_ready") is not True:
        errors.append("first-release packet package_ready must be true")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "manual posting only"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"first-release packet {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("first-release packet requires_secrets must be false")
    selected = payload.get("selected")
    if not isinstance(selected, dict) or not selected:
        errors.append("first-release packet selected must be a non-empty object")
        selected = {}
    else:
        for field in ("edition", "work_title", "label", "kind", "package_media_href", "release_board_href", "release_player_href"):
            if not selected.get(field):
                errors.append(f"first-release packet selected missing {field}")
        if selected.get("product_shop_gate") != "deferred until explicit product review":
            errors.append("first-release packet selected product gate must remain deferred")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_release_focus", payload.get("source_release_focus")),
        ("source_static_hosting_handoff", payload.get("source_static_hosting_handoff")),
    ]
    for ref_key in ("package_media_href", "release_board_href", "release_player_href"):
        refs.append((f"selected.{ref_key}", selected.get(ref_key)))
    for entrypoint in payload.get("package_entrypoints") or []:
        refs.append(("package_entrypoint", entrypoint))
    packets = payload.get("platform_packets")
    if not isinstance(packets, list) or not packets:
        errors.append("first-release packet platform_packets must be a non-empty list")
        packets = []
    if payload.get("platform_packet_count") != len(packets):
        errors.append("first-release packet platform_packet_count must match platform_packets length")
    targets = {str(packet.get("target") or "") for packet in packets if isinstance(packet, dict)}
    for required in ("Instagram Story", "YouTube Shorts draft", "GitHub/portfolio context"):
        if required not in targets:
            errors.append(f"first-release packet missing target {required!r}")
    for index, packet in enumerate(packets, start=1):
        if not isinstance(packet, dict):
            errors.append(f"first-release packet platform item {index} must be an object")
            continue
        refs.append((f"platform_packets[{index}].upload_ref", packet.get("upload_ref")))
        if not packet.get("caption"):
            errors.append(f"first-release packet platform item {index} missing caption")
        if not packet.get("alt_text"):
            errors.append(f"first-release packet platform item {index} missing alt_text")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"first-release packet missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"first-release packet {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"first-release packet {label} escapes incubator: {ref}")
        elif not target.exists():
            errors.append(f"first-release packet {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"first-release packet contains private token {token!r}")
    return errors


def posting_receipt_template_payload(first_release: dict[str, Any]) -> dict[str, Any]:
    selected = first_release["selected"]
    slots = []
    for packet in first_release["platform_packets"]:
        slots.append(
            {
                "id": str(packet.get("id") or ""),
                "target": str(packet.get("target") or ""),
                "status": "unposted",
                "source_first_release_packet": "work/first-release-packet.json",
                "work_title": str(selected.get("work_title") or ""),
                "edition": str(selected.get("edition") or ""),
                "kind": str(selected.get("kind") or ""),
                "upload_ref": str(packet.get("upload_ref") or ""),
                "caption_variant": str(packet.get("caption") or ""),
                "alt_text": str(packet.get("alt_text") or ""),
                "posted_url": "",
                "posted_at": "",
                "caption_used": "",
                "notes": "",
                "private_only": True,
                "public_package_mutation": False,
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    return {
        "schema": "triptych.posting-receipt-template.v1",
        "generated_at": first_release["generated_at"],
        "source_first_release_packet": "work/first-release-packet.json",
        "source_static_hosting_handoff": first_release["source_static_hosting_handoff"],
        "receipt_status": "template-unposted",
        "posted_count": 0,
        "slot_count": len(slots),
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "selected": {
            "work_title": selected.get("work_title"),
            "edition": selected.get("edition"),
            "kind": selected.get("kind"),
            "label": selected.get("label"),
            "package_media_href": selected.get("package_media_href"),
            "release_player_href": selected.get("release_player_href"),
            "release_board_href": selected.get("release_board_href"),
        },
        "slots": slots,
        "private_receipt_fields": [
            "platform",
            "posted_url",
            "posted_at",
            "caption_used",
            "alt_text_used",
            "source_first_release_packet",
            "package_media_href",
            "notes",
        ],
        "preflight_commands": [
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "operating_gates": [
            "This is a private unposted template, not proof of publication.",
            "Future platform URLs belong in private posting receipts, not in the public static package.",
            "A posted receipt should reference verified package media instead of local source media.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_posting_receipt_template_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.posting-receipt-template.v1":
        errors.append("unexpected posting receipt template schema")
    if payload.get("receipt_status") != "template-unposted":
        errors.append("posting receipt template receipt_status must be template-unposted")
    if payload.get("posted_count") != 0:
        errors.append("posting receipt template posted_count must be 0")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"posting receipt template {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("posting receipt template requires_secrets must be false")
    if payload.get("public_package_mutation") is not False:
        errors.append("posting receipt template public_package_mutation must be false")
    refs: list[tuple[str, Any]] = [
        ("source_first_release_packet", payload.get("source_first_release_packet")),
        ("source_static_hosting_handoff", payload.get("source_static_hosting_handoff")),
    ]
    selected = payload.get("selected")
    if not isinstance(selected, dict) or not selected:
        errors.append("posting receipt template selected must be a non-empty object")
        selected = {}
    for ref_key in ("package_media_href", "release_player_href", "release_board_href"):
        refs.append((f"selected.{ref_key}", selected.get(ref_key)))
    slots = payload.get("slots")
    if not isinstance(slots, list) or not slots:
        errors.append("posting receipt template slots must be a non-empty list")
        slots = []
    if payload.get("slot_count") != len(slots):
        errors.append("posting receipt template slot_count must match slots length")
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            errors.append(f"posting receipt template slot {index} must be an object")
            continue
        if slot.get("status") != "unposted":
            errors.append(f"posting receipt template slot {index} status must be unposted")
        if slot.get("private_only") is not True:
            errors.append(f"posting receipt template slot {index} private_only must be true")
        if slot.get("public_package_mutation") is not False:
            errors.append(f"posting receipt template slot {index} public_package_mutation must be false")
        if slot.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"posting receipt template slot {index} product gate must remain deferred")
        if slot.get("posted_url") or slot.get("posted_at") or slot.get("caption_used") or slot.get("notes"):
            errors.append(f"posting receipt template slot {index} must not claim posted state")
        if not slot.get("caption_variant"):
            errors.append(f"posting receipt template slot {index} missing caption_variant")
        if not slot.get("alt_text"):
            errors.append(f"posting receipt template slot {index} missing alt_text")
        refs.append((f"slots[{index}].upload_ref", slot.get("upload_ref")))
        refs.append((f"slots[{index}].source_first_release_packet", slot.get("source_first_release_packet")))
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"posting receipt template missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"posting receipt template {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"posting receipt template {label} escapes incubator: {ref}")
        elif not target.exists() and ref != "work/first-release-packet.json":
            errors.append(f"posting receipt template {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"posting receipt template contains private token {token!r}")
    return errors


def primary_cadence_target(item: dict[str, Any]) -> str:
    targets = item.get("targets") if isinstance(item.get("targets"), list) else []
    if item.get("kind") == "story" and "Instagram Story" in targets:
        return "Instagram Story"
    if item.get("kind") == "visual-sketch":
        return "GitHub/portfolio context" if "GitHub/portfolio context" in targets else "process post"
    if item.get("family") == "signal_damage":
        return "Instagram Reel" if "Instagram Reel" in targets else (str(targets[0]) if targets else "process post")
    return str(targets[0]) if targets else "process post"


def release_cadence_payload(
    payload: dict[str, Any],
    focus: dict[str, Any],
    first_release: dict[str, Any],
    posting_receipt: dict[str, Any],
    render_queue: dict[str, Any],
) -> dict[str, Any]:
    focus_items = focus.get("focus") if isinstance(focus.get("focus"), list) else []
    queue_by_edition = {
        str(item.get("edition") or ""): item
        for item in render_queue.get("queue", [])
        if isinstance(item, dict) and item.get("edition")
    }
    first_href = ""
    selected = first_release.get("selected")
    if isinstance(selected, dict):
        first_href = str(selected.get("package_media_href") or "")
    sequence = []
    for item in sorted(focus_items, key=lambda entry: int(entry.get("rank", 999) or 999)):
        edition = str(item.get("edition") or "")
        queue_item = queue_by_edition.get(edition, {})
        is_first = str(item.get("package_media_href") or "") == first_href
        sequence.append(
            {
                "sequence_rank": len(sequence) + 1,
                "status": "candidate-unposted",
                "edition": edition,
                "work_title": str(item.get("work_title") or ""),
                "family": str(item.get("family") or ""),
                "role": str(item.get("role") or ""),
                "kind": str(item.get("kind") or ""),
                "label": str(item.get("label") or ""),
                "primary_target": primary_cadence_target(item),
                "target_candidates": item.get("targets") if isinstance(item.get("targets"), list) else [],
                "package_media_href": str(item.get("package_media_href") or ""),
                "release_player_href": str(item.get("release_player_href") or ""),
                "release_board_href": str(item.get("release_board_href") or ""),
                "caption_seed": str(item.get("caption_seed") or ""),
                "edit_prompt": str(item.get("edit_prompt") or ""),
                "why": str(item.get("why") or ""),
                "receipt_template": "work/posting-receipt-template.html" if is_first else "regenerate after promoting this item to first-release",
                "render_queue_ref": "work/next-render-queue.html",
                "dry_run_command": str(queue_item.get("dry_run_command") or ""),
                "review_before_posting": [
                    "Open the package media or release player from this cadence row.",
                    "If it should become the next post, regenerate overnight handoffs before recording a receipt.",
                    "Keep captions free of private source names, local paths, and workflow-only notes.",
                    "Keep product/shop use deferred until a concrete product object is selected.",
                ],
                "if_not_ready": (
                    "Open work/control-auditions.html for this edition before rendering; use "
                    "work/next-render-queue.html only after a dry-run command is justified."
                ),
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    return {
        "schema": "triptych.release-cadence-plan.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_release_focus": "work/release-focus.json",
        "source_first_release_packet": "work/first-release-packet.json",
        "source_posting_receipt_template": "work/posting-receipt-template.json",
        "source_next_render_queue": "work/next-render-queue.json",
        "package_ready": focus.get("package_ready") is True and first_release.get("package_ready") is True,
        "cadence_mode": "ordered private sequence, not a calendar",
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "posting_receipt_status": posting_receipt.get("receipt_status"),
        "cadence_count": len(sequence),
        "sequence": sequence,
        "preflight_commands": [
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "operating_gates": [
            "This is a private order-of-operations handoff, not a posting calendar.",
            "A cadence row may become the next first-release packet only after regeneration.",
            "All media refs must resolve to verified package files.",
            "Future social-platform evidence belongs in private receipts, not the public package.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_release_cadence_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.release-cadence-plan.v1":
        errors.append("unexpected release-cadence plan schema")
    if payload.get("package_ready") is not True:
        errors.append("release-cadence plan package_ready must be true")
    for key, expected in (
        ("cadence_mode", "ordered private sequence, not a calendar"),
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"release-cadence plan {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("release-cadence plan requires_secrets must be false")
    if payload.get("public_package_mutation") is not False:
        errors.append("release-cadence plan public_package_mutation must be false")
    if payload.get("posting_receipt_status") != "template-unposted":
        errors.append("release-cadence plan must point at an unposted receipt template")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_release_focus", payload.get("source_release_focus")),
        ("source_first_release_packet", payload.get("source_first_release_packet")),
        ("source_posting_receipt_template", payload.get("source_posting_receipt_template")),
        ("source_next_render_queue", payload.get("source_next_render_queue")),
    ]
    sequence = payload.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        errors.append("release-cadence plan sequence must be a non-empty list")
        sequence = []
    if payload.get("cadence_count") != len(sequence):
        errors.append("release-cadence plan cadence_count must match sequence length")
    ranks = []
    for index, item in enumerate(sequence, start=1):
        if not isinstance(item, dict):
            errors.append(f"release-cadence plan sequence item {index} must be an object")
            continue
        ranks.append(item.get("sequence_rank"))
        if item.get("status") != "candidate-unposted":
            errors.append(f"release-cadence plan item {index} status must be candidate-unposted")
        if not item.get("primary_target"):
            errors.append(f"release-cadence plan item {index} primary_target must be present")
        if not isinstance(item.get("target_candidates"), list) or not item.get("target_candidates"):
            errors.append(f"release-cadence plan item {index} target_candidates must be non-empty")
        for field in ("package_media_href", "release_player_href", "release_board_href", "render_queue_ref"):
            refs.append((f"sequence[{index}].{field}", item.get(field)))
        if item.get("receipt_template") == "work/posting-receipt-template.html":
            refs.append((f"sequence[{index}].receipt_template", item.get("receipt_template")))
        if item.get("media_generation") != "none":
            errors.append(f"release-cadence plan item {index} media_generation must be none")
        if item.get("source_access") != "none":
            errors.append(f"release-cadence plan item {index} source_access must be none")
        if item.get("destructive_actions") != "none":
            errors.append(f"release-cadence plan item {index} destructive_actions must be none")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"release-cadence plan item {index} product gate must remain deferred")
    if ranks != list(range(1, len(ranks) + 1)):
        errors.append("release-cadence plan sequence ranks must be contiguous")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"release-cadence plan missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"release-cadence plan {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"release-cadence plan {label} escapes incubator: {ref}")
        elif not target.exists() and ref not in {
            "work/first-release-packet.json",
            "work/posting-receipt-template.json",
        }:
            errors.append(f"release-cadence plan {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"release-cadence plan contains private token {token!r}")
    return errors


def visual_map_summary(edition: dict[str, Any]) -> dict[str, Any]:
    sketch = edition.get("visual_sketch")
    if not isinstance(sketch, dict):
        return {"style": "none", "cell_count": 0}
    style = str(sketch.get("style") or "none")
    cell_count = 0
    for key in ("score_cells", "fracture_cells", "signal_cells"):
        cells = sketch.get(key)
        if isinstance(cells, list):
            cell_count = max(cell_count, len(cells))
    if not cell_count and isinstance(sketch.get("slices"), int):
        cell_count = int(sketch["slices"])
    return {"style": style, "cell_count": cell_count}


def sanitized_source_summary(edition: dict[str, Any]) -> dict[str, Any]:
    source = edition.get("source")
    if not isinstance(source, dict):
        source = {}
    composition = edition.get("composition")
    if not isinstance(composition, dict):
        composition = {}
    source_type = str(source.get("type") or "manual_folder")
    raw_album = str(composition.get("material_album") or source.get("album") or "")
    arrangement_model_album = str(composition.get("arrangement_model_album") or "")
    if not arrangement_model_album and source_type == "photos_visual_album":
        arrangement_model_album = raw_album
    language = composition.get("language")
    if not isinstance(language, list):
        language = []
    return {
        "source_type": source_type,
        "source_mode": "still-to-motion" if source_type == "photos_visual_album" else "video-native",
        "raw_album": raw_album,
        "album_match": str(source.get("album_match") or "exact"),
        "order": str(source.get("order") or "oldest"),
        "selection_limit": int(source.get("limit", 0) or 0),
        "model_album": arrangement_model_album,
        "model_limit": int(source.get("model_limit", 0) or 0),
        "motion": str(source.get("motion") or ("native-video" if source_type == "photos_album" else "hold")),
        "fps": int(source.get("fps", 0) or 0),
        "crf": int(source.get("crf", 0) or 0),
        "stage_mode": str(source.get("mode") or "generated-proxy"),
        "arrangement_model_role": markdown_text(composition.get("arrangement_model_role") or ""),
        "arrangement_model_observation": markdown_text(composition.get("arrangement_model_observation") or ""),
        "arrangement_model_instruction": markdown_text(composition.get("arrangement_model_instruction") or ""),
        "panel_arrangement_role": markdown_text(composition.get("panel_arrangement_role") or ""),
        "language": [markdown_text(item) for item in language if isinstance(item, str) and item],
    }


def sanitized_audio_settings(edition: dict[str, Any]) -> dict[str, Any]:
    settings = edition.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    audio = settings.get("audio")
    if not isinstance(audio, dict):
        audio = {}
    effects = settings.get("effects")
    if not isinstance(effects, dict):
        effects = {}
    panel_gains = audio.get("panel_gains")
    if not isinstance(panel_gains, dict):
        panel_gains = {}
    presets = edition.get("control_presets")
    if not isinstance(presets, list):
        presets = []
    safe_presets = []
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        panel_volumes = preset.get("panel_volumes")
        if not isinstance(panel_volumes, dict):
            panel_volumes = {}
        safe_presets.append(
            {
                "id": str(preset.get("id") or ""),
                "label": str(preset.get("label") or preset.get("id") or ""),
                "surface": str(preset.get("surface") or "canon"),
                "direction": str(preset.get("direction") or effects.get("direction") or "forward"),
                "audio": preset.get("audio") is True,
                "volume": float(preset.get("volume", audio.get("gain", 0)) or 0),
                "panel_volumes": {
                    panel: float(value or 0)
                    for panel, value in panel_volumes.items()
                    if panel in {"left", "middle", "right"} and isinstance(value, int | float)
                },
            }
        )
    return {
        "audio_mode": str(audio.get("mode") or "mix"),
        "audio_panel": str(audio.get("panel") or ""),
        "render_gain": float(audio.get("gain", 0) or 0),
        "panel_gains": {
            panel: float(value or 0)
            for panel, value in panel_gains.items()
            if panel in {"left", "middle", "right"} and isinstance(value, int | float)
        },
        "fade_seconds": float(audio.get("fade_seconds", 0) or 0),
        "direction": str(effects.get("direction") or "forward"),
        "control_presets": safe_presets,
        "audio_preset_count": sum(1 for preset in safe_presets if preset["audio"] is True),
    }


def safe_preset_editions() -> list[dict[str, Any]]:
    data = load_json(SCRIPT_DIR / "editions.example.json")
    editions = data.get("editions") if isinstance(data.get("editions"), list) else []
    safe: list[dict[str, Any]] = []
    for edition in editions:
        if not isinstance(edition, dict):
            continue
        presets = edition.get("control_presets")
        if not isinstance(presets, list):
            presets = []
        default_preset = "none"
        for preset in presets:
            if isinstance(preset, dict) and preset.get("default") is True:
                default_preset = str(preset.get("id") or "default")
                break
        visual_map = visual_map_summary(edition)
        source_summary = sanitized_source_summary(edition)
        audio_summary = sanitized_audio_settings(edition)
        safe.append(
            {
                "slug": str(edition.get("slug") or edition.get("name") or ""),
                "work_title": str(edition.get("work_title") or edition.get("name") or ""),
                "family": str(edition.get("family") or ""),
                "preset_status": str(edition.get("status") or ""),
                "note": markdown_text(edition.get("note") or ""),
                "default_preset": default_preset,
                "preset_count": len(presets),
                "visual_map": visual_map,
                "source": source_summary,
                "audio": audio_summary,
            }
        )
    return [edition for edition in safe if edition["slug"]]


def edition_refinement_action(
    slug: str,
    public: dict[str, Any],
    cadence_items: list[dict[str, Any]],
    render_item: dict[str, Any],
) -> tuple[str, str]:
    if slug == "porn":
        return (
            "keep local-only",
            "Review signal-map language and source selection privately; do not create public exports without explicit review.",
        )
    if cadence_items:
        return (
            "review cadence item",
            "Open the cadence item, then either post from the verified package or refine with text controls before rendering.",
        )
    if render_item:
        return (
            "audition before render",
            "Open control auditions first; run the dry-run command only if the edition needs a fresh post pack.",
        )
    if public:
        return (
            "hold verified state",
            "Keep the package state verified and wait for a stronger creative reason before rendering.",
        )
    return (
        "verify before import",
        "Run edition verification before any import, render, sync, or public-share work.",
    )


def edition_refinement_slate_payload(
    payload: dict[str, Any],
    auditions: dict[str, Any],
    render_queue: dict[str, Any],
    release_cadence: dict[str, Any],
) -> dict[str, Any]:
    creative = payload["creative_track"]
    public_by_slug = {
        str(edition.get("slug") or ""): edition
        for edition in creative.get("editions", [])
        if isinstance(edition, dict) and edition.get("slug")
    }
    render_by_slug = {
        str(item.get("edition") or ""): item
        for item in render_queue.get("queue", [])
        if isinstance(item, dict) and item.get("edition")
    }
    cadence_by_slug: dict[str, list[dict[str, Any]]] = {}
    for item in release_cadence.get("sequence", []):
        if isinstance(item, dict):
            cadence_by_slug.setdefault(str(item.get("edition") or ""), []).append(item)
    audition_counts: dict[str, int] = {}
    for item in auditions.get("auditions", []):
        if isinstance(item, dict):
            edition = str(item.get("edition") or "")
            audition_counts[edition] = audition_counts.get(edition, 0) + 1

    rows = []
    for preset in safe_preset_editions():
        slug = preset["slug"]
        public = public_by_slug.get(slug, {})
        render_item = render_by_slug.get(slug, {})
        cadence_items = cadence_by_slug.get(slug, [])
        action, rationale = edition_refinement_action(slug, public, cadence_items, render_item)
        package_page = package_href(public.get("page")) if public.get("page") else ""
        rows.append(
            {
                "rank": len(rows) + 1,
                "edition": slug,
                "work_title": preset["work_title"] or str(public.get("work_title") or slug),
                "family": preset["family"] or str(public.get("family") or ""),
                "preset_status": preset["preset_status"],
                "public_export_gate": "gated-local-only" if slug == "porn" else ("public-package-ready" if public else "not-public"),
                "package_page": package_page,
                "post_exports": int(public.get("post_exports", 0) or 0) if isinstance(public.get("post_exports"), int) else int(public.get("post_exports", 0) or 0) if public else 0,
                "visual_sketches": int(public.get("visual_sketches", 0) or 0) if public else 0,
                "default_preset": preset["default_preset"],
                "preset_count": preset["preset_count"],
                "visual_map": preset["visual_map"],
                "cadence_items": [
                    {
                        "sequence_rank": item.get("sequence_rank"),
                        "kind": item.get("kind"),
                        "primary_target": item.get("primary_target"),
                        "package_media_href": item.get("package_media_href"),
                    }
                    for item in cadence_items
                ],
                "audition_count": audition_counts.get(slug, 0),
                "dry_run_command": str(render_item.get("dry_run_command") or ""),
                "next_private_surface": (
                    "work/release-cadence-plan.html"
                    if cadence_items
                    else ("work/control-auditions.html" if slug != "porn" else "work/edition-refinement-slate.html")
                ),
                "recommended_next_action": action,
                "rationale": rationale,
                "note": preset["note"],
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    return {
        "schema": "triptych.edition-refinement-slate.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_control_auditions": "work/control-auditions.json",
        "source_next_render_queue": "work/next-render-queue.json",
        "source_release_cadence": "work/release-cadence-plan.json",
        "preset_source": "editions.example.json",
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "edition_count": len(rows),
        "rows": rows,
        "preflight_commands": [
            "python3 verify_editions.py",
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "operating_gates": [
            "This slate is private edition steering, not a render command.",
            "Porn remains local-only until explicit public-export review changes that gate.",
            "Open control auditions before new render work unless a verified cadence item is ready.",
            "All public-ready refs must resolve inside the verified package.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_edition_refinement_slate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.edition-refinement-slate.v1":
        errors.append("unexpected edition-refinement slate schema")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"edition-refinement slate {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("edition-refinement slate requires_secrets must be false")
    if payload.get("public_package_mutation") is not False:
        errors.append("edition-refinement slate public_package_mutation must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_control_auditions", payload.get("source_control_auditions")),
        ("source_next_render_queue", payload.get("source_next_render_queue")),
        ("source_release_cadence", payload.get("source_release_cadence")),
        ("preset_source", payload.get("preset_source")),
    ]
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("edition-refinement slate rows must be a non-empty list")
        rows = []
    if payload.get("edition_count") != len(rows):
        errors.append("edition-refinement slate edition_count must match rows length")
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"edition-refinement slate missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"edition-refinement slate row {index} must be an object")
            continue
        if row.get("media_generation") != "none":
            errors.append(f"edition-refinement slate row {index} media_generation must be none")
        if row.get("source_access") != "none":
            errors.append(f"edition-refinement slate row {index} source_access must be none")
        if row.get("destructive_actions") != "none":
            errors.append(f"edition-refinement slate row {index} destructive_actions must be none")
        if row.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"edition-refinement slate row {index} product gate must remain deferred")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("edition-refinement slate porn row must stay gated-local-only")
        if row.get("edition") != "porn" and row.get("public_export_gate") not in {"public-package-ready", "not-public"}:
            errors.append(
                f"edition-refinement slate row {index} public_export_gate must be public-package-ready or not-public"
            )
        package_page = row.get("package_page")
        if package_page:
            refs.append((f"rows[{index}].package_page", package_page))
        surface = row.get("next_private_surface")
        if isinstance(surface, str) and surface.startswith("work/"):
            refs.append((f"rows[{index}].next_private_surface", surface))
        for cadence_index, item in enumerate(row.get("cadence_items") or [], start=1):
            if isinstance(item, dict):
                refs.append((f"rows[{index}].cadence_items[{cadence_index}].package_media_href", item.get("package_media_href")))
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"edition-refinement slate missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"edition-refinement slate {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"edition-refinement slate {label} escapes incubator: {ref}")
        elif not target.exists() and ref in {
            "work/release-cadence-plan.json",
            "work/release-cadence-plan.html",
            "work/edition-refinement-slate.html",
        }:
            continue
        elif not target.exists():
            errors.append(f"edition-refinement slate {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"edition-refinement slate contains private token {token!r}")
    return errors


def retention_lane_decision(lane: dict[str, Any]) -> tuple[str, str]:
    path = str(lane.get("path") or "")
    if path == "renders":
        return (
            "manual-reclaim-candidate",
            "Largest cache lane; reclaim only after package/public verification and rerender commands are accepted.",
        )
    if path == "packages":
        return (
            "regenerable-after-transfer",
            "Package copies and zip are low risk after verify_package.py, but keep them while hosting or transfer is active.",
        )
    if path == "site":
        return (
            "regenerable-public-build",
            "Public build can be rebuilt, but keep it while it is the source of a verified package or posting review.",
        )
    if path == "work":
        return (
            "protect-private-receipts",
            "Private manifests, catalog receipts, and overnight handoffs are small enough to preserve during autonomous work.",
        )
    if path == "samples":
        return (
            "protect-staged-source",
            "Staged selected media is the local creative source lane; delete only after originals can be restaged.",
        )
    return ("review-manually", "Unknown lane; do not delete without a new policy.")


def retention_creative_impact(lane: dict[str, Any]) -> str:
    path = str(lane.get("path") or "")
    if path == "renders":
        return "Current public package remains the proof surface, but fresh Story/Reel/sketch work would need rerendering."
    if path == "packages":
        return "Hosted/archive transfer copy would need regeneration from site/."
    if path == "site":
        return "Public package must already be current before this generated build is discarded."
    if path == "work":
        return "Deleting this risks losing private selection, catalog, and overnight steering receipts."
    if path == "samples":
        return "Deleting this risks losing staged selected media for album-shaped rerenders."
    return "Unknown creative impact."


def cache_retention_plan_payload(
    payload: dict[str, Any],
    edition_slate: dict[str, Any],
    release_cadence: dict[str, Any],
    hosting: dict[str, Any],
) -> dict[str, Any]:
    containment = payload["containment_track"]
    inventory = containment.get("inventory") if isinstance(containment.get("inventory"), list) else []
    cleanup_candidates = containment.get("cleanup_candidates") if isinstance(containment.get("cleanup_candidates"), list) else []
    candidates_by_lane = {
        str(candidate.get("lane") or ""): candidate
        for candidate in cleanup_candidates
        if isinstance(candidate, dict)
    }
    rows = []
    for lane in inventory:
        if not isinstance(lane, dict):
            continue
        decision, rationale = retention_lane_decision(lane)
        candidate = candidates_by_lane.get(str(lane.get("path") or ""), {})
        rows.append(
            {
                "lane": str(lane.get("path") or ""),
                "role": str(lane.get("role") or ""),
                "decision": decision,
                "rationale": rationale,
                "creative_impact": retention_creative_impact(lane),
                "bytes": int(lane.get("bytes", 0) or 0),
                "human_size": human_size(lane.get("bytes", 0)),
                "files": int(lane.get("files", 0) or 0),
                "private": lane.get("private") is True,
                "disposable": lane.get("disposable") is True,
                "manual_only": True,
                "cleanup_candidate": bool(candidate),
                "risk": str(candidate.get("risk") or ("protected" if decision.startswith("protect") else "review")),
                "regenerate_with": candidate.get("regenerate_with")
                if isinstance(candidate.get("regenerate_with"), list)
                else generated_inventory.REGENERATION_CHECKPOINTS,
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
            }
        )
    return {
        "schema": "triptych.cache-retention-plan.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_edition_refinement_slate": "work/edition-refinement-slate.json",
        "source_release_cadence": "work/release-cadence-plan.json",
        "source_static_hosting_handoff": "work/static-hosting-handoff.json",
        "inventory_command": "python3 generated_inventory.py --cleanup-plan",
        "package_ready": hosting.get("package_ready") is True,
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "deletion_performed": False,
        "public_package_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "totals": {
            "total_bytes": sum(int(row.get("bytes", 0) or 0) for row in rows),
            "generated_bytes": sum(int(row.get("bytes", 0) or 0) for row in rows if row.get("disposable") is True),
            "staged_source_bytes": sum(int(row.get("bytes", 0) or 0) for row in rows if row.get("disposable") is not True),
            "human_total": human_size(sum(int(row.get("bytes", 0) or 0) for row in rows)),
        },
        "row_count": len(rows),
        "rows": rows,
        "protected_private_surfaces": [
            "work/overnight-dashboard.html",
            "work/edition-refinement-slate.html",
            "work/release-cadence-plan.html",
            "work/first-release-packet.html",
            "work/posting-receipt-template.html",
        ],
        "creative_proof_surfaces": [
            "packages/triptych-video-canon-site/index.html",
            "packages/triptych-video-canon-site/release-player.html",
            "packages/triptych-video-canon-site/release-board.html",
            "packages/triptych-video-canon-site/package-manifest.json",
        ],
        "preflight_commands": [
            "python3 generated_inventory.py --cleanup-plan",
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
            "python3 edition_status.py",
        ],
        "operating_gates": [
            "This plan is read-only; it performs no deletion and generates no media.",
            "Do not delete work/ or samples/ during autonomous overnight work.",
            "Reclaim renders/ only after accepting rerender cost and verifying package/public surfaces.",
            "Reclaim packages/ or site/ only after package transfer/hosting state is no longer needed.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
        "context": {
            "edition_rows": edition_slate.get("edition_count"),
            "cadence_items": release_cadence.get("cadence_count"),
            "hosting_upload_scope": hosting.get("upload_scope"),
        },
    }


def validate_cache_retention_plan_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.cache-retention-plan.v1":
        errors.append("unexpected cache-retention plan schema")
    if payload.get("package_ready") is not True:
        errors.append("cache-retention plan package_ready must be true")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"cache-retention plan {key} must be {expected}")
    if payload.get("requires_secrets") is not False:
        errors.append("cache-retention plan requires_secrets must be false")
    if payload.get("deletion_performed") is not False:
        errors.append("cache-retention plan deletion_performed must be false")
    if payload.get("public_package_mutation") is not False:
        errors.append("cache-retention plan public_package_mutation must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_edition_refinement_slate", payload.get("source_edition_refinement_slate")),
        ("source_release_cadence", payload.get("source_release_cadence")),
        ("source_static_hosting_handoff", payload.get("source_static_hosting_handoff")),
    ]
    for ref in payload.get("protected_private_surfaces") or []:
        refs.append(("protected_private_surface", ref))
    for ref in payload.get("creative_proof_surfaces") or []:
        refs.append(("creative_proof_surface", ref))
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("cache-retention plan rows must be a non-empty list")
        rows = []
    if payload.get("row_count") != len(rows):
        errors.append("cache-retention plan row_count must match rows length")
    lanes = {str(row.get("lane") or "") for row in rows if isinstance(row, dict)}
    for required in ("work", "renders", "site", "packages", "samples"):
        if required not in lanes:
            errors.append(f"cache-retention plan missing lane {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"cache-retention plan row {index} must be an object")
            continue
        if row.get("manual_only") is not True:
            errors.append(f"cache-retention plan row {index} manual_only must be true")
        if row.get("media_generation") != "none":
            errors.append(f"cache-retention plan row {index} media_generation must be none")
        if row.get("source_access") != "none":
            errors.append(f"cache-retention plan row {index} source_access must be none")
        if row.get("destructive_actions") != "none":
            errors.append(f"cache-retention plan row {index} destructive_actions must be none")
        if row.get("lane") in {"work", "samples"} and not str(row.get("decision") or "").startswith("protect"):
            errors.append(f"cache-retention plan row {index} must protect {row.get('lane')}/")
        commands = row.get("regenerate_with")
        if not isinstance(commands, list) or not commands:
            errors.append(f"cache-retention plan row {index} regenerate_with must be non-empty")
    text = json.dumps(payload, sort_keys=True)
    for forbidden in ("rm ", "trash ", "delete now", "deletion_performed\": true"):
        if forbidden in text:
            errors.append(f"cache-retention plan contains destructive token {forbidden!r}")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"cache-retention plan missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"cache-retention plan {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"cache-retention plan {label} escapes incubator: {ref}")
        elif not target.exists() and ref in {
            "work/edition-refinement-slate.json",
            "work/edition-refinement-slate.html",
        }:
            continue
        elif not target.exists():
            errors.append(f"cache-retention plan {label} does not exist: {ref}")
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"cache-retention plan contains private token {token!r}")
    return errors


def source_curation_action(
    preset: dict[str, Any],
    slate_row: dict[str, Any],
) -> tuple[str, str, str]:
    slug = str(preset.get("slug") or "")
    source = preset.get("source") if isinstance(preset.get("source"), dict) else {}
    source_type = str(source.get("source_type") or "")
    if slug == "porn":
        return (
            "private review only",
            "Keep this signal-damage source gated; review the album language and signal map before any public export.",
            "work/edition-refinement-slate.html",
        )
    if slug == "ballerina":
        return (
            "preserve raw/model split",
            "Use ballerina danse as raw material and ballerina whole as the arrangement score before changing clips or panels.",
            "work/control-auditions.html",
        )
    if source_type == "photos_visual_album":
        return (
            "dry-run still-to-motion refresh",
            "Review the current visual sketch first; refresh staged still-to-motion clips only when the album shape needs new evidence.",
            "work/edition-refinement-slate.html",
        )
    if slate_row.get("public_export_gate") == "public-package-ready":
        return (
            "hold video selection",
            "The video-heavy branch has a verified package; use dry-run preview before changing staged source.",
            "work/release-cadence-plan.html",
        )
    return (
        "verify before import",
        "Run edition verification and inspect dry-run import commands before staging source media.",
        "work/edition-refinement-slate.html",
    )


def source_curation_plan_payload(
    payload: dict[str, Any],
    edition_slate: dict[str, Any],
    retention_plan: dict[str, Any],
) -> dict[str, Any]:
    slate_by_slug = {
        str(row.get("edition") or ""): row
        for row in edition_slate.get("rows", [])
        if isinstance(row, dict) and row.get("edition")
    }
    rows = []
    for preset in safe_preset_editions():
        slug = preset["slug"]
        source = preset.get("source") if isinstance(preset.get("source"), dict) else {}
        slate_row = slate_by_slug.get(slug, {})
        action, rationale, review_surface = source_curation_action(preset, slate_row)
        public_gate = str(
            slate_row.get("public_export_gate")
            or ("gated-local-only" if slug == "porn" else "not-public")
        )
        rows.append(
            {
                "rank": len(rows) + 1,
                "edition": slug,
                "work_title": preset["work_title"],
                "family": preset["family"],
                "preset_status": preset["preset_status"],
                "source_type": source.get("source_type", ""),
                "source_mode": source.get("source_mode", ""),
                "raw_album": source.get("raw_album", ""),
                "model_album": source.get("model_album", ""),
                "album_match": source.get("album_match", ""),
                "order": source.get("order", ""),
                "selection_limit": source.get("selection_limit", 0),
                "model_limit": source.get("model_limit", 0),
                "motion": source.get("motion", ""),
                "fps": source.get("fps", 0),
                "crf": source.get("crf", 0),
                "stage_mode": source.get("stage_mode", ""),
                "visual_map": preset["visual_map"],
                "arrangement_model_role": source.get("arrangement_model_role", ""),
                "arrangement_model_observation": source.get("arrangement_model_observation", ""),
                "arrangement_model_instruction": source.get("arrangement_model_instruction", ""),
                "panel_arrangement_role": source.get("panel_arrangement_role", ""),
                "language": source.get("language", []),
                "public_export_gate": public_gate,
                "post_exports": int(slate_row.get("post_exports", 0) or 0),
                "visual_sketches": int(slate_row.get("visual_sketches", 0) or 0),
                "recommended_source_action": action,
                "rationale": rationale,
                "review_surface": review_surface,
                "dry_run_command": f"python3 build_edition.py {slug} --dry-run",
                "status_command": "python3 edition_status.py",
                "preflight_commands": [
                    "python3 verify_editions.py",
                    f"python3 build_edition.py {slug} --dry-run",
                    "python3 verify_private_workflow.py",
                ],
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
                "public_package_mutation": False,
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    return {
        "schema": "triptych.source-curation-plan.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_edition_refinement_slate": "work/edition-refinement-slate.json",
        "source_cache_retention_plan": "work/cache-retention-plan.json",
        "preset_source": "editions.example.json",
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "photos_library_mutation": False,
        "staging_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "row_count": len(rows),
        "rows": rows,
        "context": {
            "retention_lanes": retention_plan.get("row_count"),
            "edition_rows": edition_slate.get("edition_count"),
            "protected_source_lane": "samples/",
            "private_receipt_lane": "work/",
        },
        "preflight_commands": [
            "python3 verify_editions.py",
            "python3 edition_status.py",
            "python3 generated_inventory.py --cleanup-plan",
            "python3 verify_private_workflow.py",
        ],
        "operating_gates": [
            "This plan is private source steering and performs no import, export, render, deletion, or Photos.app mutation.",
            "Use dry-run commands before any source refresh.",
            "Keep raw album and arrangement model album roles distinct when the preset defines both.",
            "Do not stage the whole library; keep selection limits explicit and small.",
            "Porn remains local-only until explicit public-export review changes that gate.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_source_curation_plan_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.source-curation-plan.v1":
        errors.append("unexpected source-curation plan schema")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"source-curation plan {key} must be {expected}")
    for key in ("requires_secrets", "public_package_mutation", "photos_library_mutation", "staging_mutation"):
        if payload.get(key) is not False:
            errors.append(f"source-curation plan {key} must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_edition_refinement_slate", payload.get("source_edition_refinement_slate")),
        ("source_cache_retention_plan", payload.get("source_cache_retention_plan")),
        ("preset_source", payload.get("preset_source")),
    ]
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("source-curation plan rows must be a non-empty list")
        rows = []
    if payload.get("row_count") != len(rows):
        errors.append("source-curation plan row_count must match rows length")
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"source-curation plan missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"source-curation plan row {index} must be an object")
            continue
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"source-curation plan row {index} {key} must be {expected}")
        if row.get("public_package_mutation") is not False:
            errors.append(f"source-curation plan row {index} public_package_mutation must be false")
        if not row.get("raw_album"):
            errors.append(f"source-curation plan row {index} raw_album must be present")
        if row.get("edition") == "ballerina" and row.get("model_album") == row.get("raw_album"):
            errors.append("source-curation plan ballerina row must keep raw and model albums distinct")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("source-curation plan porn row must stay gated-local-only")
        dry_run = str(row.get("dry_run_command") or "")
        if "--dry-run" not in dry_run:
            errors.append(f"source-curation plan row {index} dry_run_command must include --dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"source-curation plan row {index} dry_run_command must not export missing Photos originals")
        surface = row.get("review_surface")
        if isinstance(surface, str) and surface.startswith("work/"):
            refs.append((f"rows[{index}].review_surface", surface))
        commands = row.get("preflight_commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"source-curation plan row {index} preflight_commands must be non-empty")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"source-curation plan missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"source-curation plan {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"source-curation plan {label} escapes incubator: {ref}")
        elif not target.exists() and ref in {
            "work/edition-refinement-slate.json",
            "work/edition-refinement-slate.html",
            "work/cache-retention-plan.json",
            "work/control-auditions.html",
            "work/release-cadence-plan.html",
        }:
            continue
        elif not target.exists():
            errors.append(f"source-curation plan {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"source-curation plan contains forbidden token {forbidden!r}")
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"source-curation plan contains private token {token!r}")
    return errors


def audio_action(
    preset: dict[str, Any],
    public_sound: dict[str, Any],
) -> tuple[str, str]:
    slug = str(preset.get("slug") or "")
    audio = preset.get("audio") if isinstance(preset.get("audio"), dict) else {}
    direction = str(audio.get("direction") or "forward")
    if slug == "porn":
        return (
            "keep gated and silent",
            "Keep the signal-damage audio posture private until the edition receives explicit public-export review.",
        )
    if direction in {"reverse", "pingpong"}:
        return (
            "audition direction-aware audio",
            "Use package playback for browser-only rate/volume review, then rerender from staged media only if reverse or ping-pong audio needs to be baked into exports.",
        )
    if int(public_sound.get("audio_items", 0) or 0) > 0:
        return (
            "review package audio balance",
            "Use the verified package and public sound map to decide whether the current gain and panel balance should stay as the posting default.",
        )
    return (
        "keep sketch silent",
        "Treat the current public surface as a visual sketch until a concrete audio reason justifies a draft rerender.",
    )


def audio_control_plan_payload(
    payload: dict[str, Any],
    source_curation: dict[str, Any],
) -> dict[str, Any]:
    sound_map = load_json(SCRIPT_DIR / "site" / "sound-map.json")
    sound_by_slug = {
        str(row.get("edition") or ""): row
        for row in sound_map.get("editions", [])
        if isinstance(row, dict) and row.get("edition")
    }
    rows = []
    for preset in safe_preset_editions():
        slug = preset["slug"]
        audio = preset.get("audio") if isinstance(preset.get("audio"), dict) else {}
        public_sound = sound_by_slug.get(slug, {})
        action, rationale = audio_action(preset, public_sound)
        review_url = f"{PACKAGE_ROOT}/release-player.html?{urlencode({'edition': slug, 'mode': 'sequential', 'muted': '0', 'volume': '0.35', 'rate': '0.75'})}"
        rows.append(
            {
                "rank": len(rows) + 1,
                "edition": slug,
                "work_title": preset["work_title"],
                "family": preset["family"],
                "audio_mode": audio.get("audio_mode", "mix"),
                "audio_panel": audio.get("audio_panel", ""),
                "render_gain": audio.get("render_gain", 0),
                "panel_gains": audio.get("panel_gains", {}),
                "fade_seconds": audio.get("fade_seconds", 0),
                "direction": audio.get("direction", "forward"),
                "control_presets": audio.get("control_presets", []),
                "audio_preset_count": audio.get("audio_preset_count", 0),
                "public_audio_items": int(public_sound.get("audio_items", 0) or 0),
                "public_silent_items": int(public_sound.get("silent_items", 0) or 0),
                "public_audio_duration_seconds": public_sound.get("audio_duration_seconds", 0),
                "public_silent_duration_seconds": public_sound.get("silent_duration_seconds", 0),
                "recommended_audio_action": action,
                "rationale": rationale,
                "review_surface": "packages/triptych-video-canon-site/sound-map.md"
                if slug != "porn"
                else "work/edition-refinement-slate.html",
                "review_player_href": review_url if slug != "porn" else "",
                "dry_run_command": f"python3 build_edition.py {slug} --skip-import --render --draft --dry-run",
                "preflight_commands": [
                    "python3 verify_editions.py",
                    f"python3 build_edition.py {slug} --skip-import --render --draft --dry-run",
                    "python3 verify_private_workflow.py",
                    "python3 verify_public_site.py",
                ],
                "browser_only_controls": sound_map.get("controls", {}).get("browser_only", []),
                "source_audio_mutation": False,
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
                "public_package_mutation": False,
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    return {
        "schema": "triptych.audio-control-plan.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_public_sound_map": "site/sound-map.json",
        "source_playback_contract": "site/playback-contract.json",
        "source_source_curation_plan": "work/source-curation-plan.json",
        "preset_source": "editions.example.json",
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "source_audio_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "row_count": len(rows),
        "rows": rows,
        "public_sound_snapshot": {
            "item_count": int(sound_map.get("item_count", 0) or 0),
            "audio_item_count": int(sound_map.get("audio_item_count", 0) or 0),
            "silent_item_count": int(sound_map.get("silent_item_count", 0) or 0),
            "browser_only_controls": sound_map.get("controls", {}).get("browser_only", []),
            "quiet_review": sound_map.get("controls", {}).get("quiet_review", ""),
            "muted_kiosk": sound_map.get("controls", {}).get("muted_kiosk", ""),
            "seeded_audio_review": sound_map.get("controls", {}).get("seeded_audio_review", ""),
        },
        "context": {
            "source_curation_rows": source_curation.get("row_count"),
            "render_audio_changes_require": "dry-run, staged media, public-site verification, package verification",
            "browser_controls": "muted, volume, and rate affect playback only",
        },
        "preflight_commands": [
            "python3 verify_editions.py",
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "operating_gates": [
            "This plan is private audio steering and performs no render, import, export, source access, deletion, or deployment.",
            "Browser muted, volume, and rate controls do not mutate source audio or rendered post packs.",
            "Reverse and ping-pong audio changes require a deliberate rerender from staged media after dry-run review.",
            "Visual sketches may remain intentionally silent.",
            "Porn remains local-only until explicit public-export review changes that gate.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_audio_control_plan_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.audio-control-plan.v1":
        errors.append("unexpected audio-control plan schema")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"audio-control plan {key} must be {expected}")
    for key in ("requires_secrets", "public_package_mutation", "source_audio_mutation"):
        if payload.get(key) is not False:
            errors.append(f"audio-control plan {key} must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_public_sound_map", payload.get("source_public_sound_map")),
        ("source_playback_contract", payload.get("source_playback_contract")),
        ("source_source_curation_plan", payload.get("source_source_curation_plan")),
        ("preset_source", payload.get("preset_source")),
    ]
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("audio-control plan rows must be a non-empty list")
        rows = []
    if payload.get("row_count") != len(rows):
        errors.append("audio-control plan row_count must match rows length")
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"audio-control plan missing edition {required}")
    snapshot = payload.get("public_sound_snapshot")
    if not isinstance(snapshot, dict):
        errors.append("audio-control plan public_sound_snapshot must be an object")
        snapshot = {}
    controls = snapshot.get("browser_only_controls")
    if controls != ["muted", "volume", "rate"]:
        errors.append("audio-control plan browser controls must be muted, volume, rate")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"audio-control plan row {index} must be an object")
            continue
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"audio-control plan row {index} {key} must be {expected}")
        if row.get("source_audio_mutation") is not False:
            errors.append(f"audio-control plan row {index} source_audio_mutation must be false")
        if row.get("public_package_mutation") is not False:
            errors.append(f"audio-control plan row {index} public_package_mutation must be false")
        dry_run = str(row.get("dry_run_command") or "")
        if "--dry-run" not in dry_run or "--skip-import" not in dry_run:
            errors.append(f"audio-control plan row {index} dry_run_command must be skip-import dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"audio-control plan row {index} dry_run_command must not export missing originals")
        if row.get("edition") == "porn" and row.get("review_player_href"):
            errors.append("audio-control plan porn row must not expose a public review player")
        if row.get("direction") not in {"forward", "reverse", "pingpong"}:
            errors.append(f"audio-control plan row {index} invalid direction")
        if not isinstance(row.get("control_presets"), list):
            errors.append(f"audio-control plan row {index} control_presets must be a list")
        surface = row.get("review_surface")
        if isinstance(surface, str) and surface:
            refs.append((f"rows[{index}].review_surface", surface))
        href = row.get("review_player_href")
        if isinstance(href, str) and href:
            refs.append((f"rows[{index}].review_player_href", href))
        commands = row.get("preflight_commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"audio-control plan row {index} preflight_commands must be non-empty")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"audio-control plan missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"audio-control plan {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"audio-control plan {label} escapes incubator: {ref}")
        elif not target.exists() and ref in {
            "work/source-curation-plan.json",
            "work/edition-refinement-slate.html",
        }:
            continue
        elif not target.exists():
            errors.append(f"audio-control plan {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"audio-control plan contains forbidden token {forbidden!r}")
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"audio-control plan contains private token {token!r}")
    return errors


def rows_by_edition(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("edition") or ""): row
        for row in rows
        if isinstance(row, dict) and row.get("edition")
    }


def queue_by_edition(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("queue")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("edition") or ""): row
        for row in rows
        if isinstance(row, dict) and row.get("edition")
    }


def paired_work_order_payload(
    payload: dict[str, Any],
    edition_slate: dict[str, Any],
    source_curation: dict[str, Any],
    audio_control: dict[str, Any],
    retention_plan: dict[str, Any],
    render_queue: dict[str, Any],
) -> dict[str, Any]:
    slate_rows = edition_slate.get("rows") if isinstance(edition_slate.get("rows"), list) else []
    source_rows = rows_by_edition(source_curation)
    audio_rows = rows_by_edition(audio_control)
    render_rows = queue_by_edition(render_queue)
    retention_rows = retention_plan.get("rows") if isinstance(retention_plan.get("rows"), list) else []
    generated_lanes = [
        row for row in retention_rows
        if isinstance(row, dict) and row.get("cleanup_candidate") is True and row.get("lane") not in {"work", "samples"}
    ]
    largest_lane = max(generated_lanes, key=lambda row: int(row.get("bytes", 0) or 0), default={})
    rows = []
    for slate in slate_rows:
        if not isinstance(slate, dict):
            continue
        slug = str(slate.get("edition") or "")
        source = source_rows.get(slug, {})
        audio = audio_rows.get(slug, {})
        render = render_rows.get(slug, {})
        public_gate = str(slate.get("public_export_gate") or "")
        if slug == "porn":
            creative_action = "keep gated signal map in private review"
            containment_action = "block public export until explicit review changes the gate"
            next_surface = "work/edition-refinement-slate.html"
        else:
            creative_action = str(slate.get("recommended_next_action") or source.get("recommended_source_action") or "audition before render")
            containment_action = "verify private/public/package gates before any render or source refresh"
            next_surface = str(slate.get("next_private_surface") or "work/control-auditions.html")
        dry_run = str(render.get("dry_run_command") or slate.get("dry_run_command") or "")
        if not dry_run and slug != "porn":
            dry_run = f"python3 build_post_pack.py {slug} --skip-import --profile draft --pack story --dry-run"
        text_edit_prompt = (
            f"{markdown_text(slug)}: {markdown_text(source.get('panel_arrangement_role') or slate.get('note') or creative_action)} "
            f"Audio posture: {markdown_text(audio.get('recommended_audio_action') or 'review current public sound map')}. "
            "Keep this as a text audition until the dry-run and verification gates pass."
        )
        rows.append(
            {
                "rank": int(slate.get("rank", len(rows) + 1) or len(rows) + 1),
                "edition": slug,
                "family": str(slate.get("family") or source.get("family") or ""),
                "work_title": str(slate.get("work_title") or source.get("work_title") or audio.get("work_title") or slug),
                "public_export_gate": public_gate,
                "paired_tracks": ["creative", "containment"],
                "creative_action": creative_action,
                "creative_surface": next_surface,
                "creative_basis": {
                    "visual_map": slate.get("visual_map") if isinstance(slate.get("visual_map"), dict) else {},
                    "source_action": source.get("recommended_source_action", ""),
                    "audio_action": audio.get("recommended_audio_action", ""),
                    "arrangement_role": source.get("arrangement_model_role", ""),
                    "panel_role": source.get("panel_arrangement_role", ""),
                    "language": source.get("language") if isinstance(source.get("language"), list) else [],
                },
                "text_edit_prompt": text_edit_prompt,
                "dry_run_command": dry_run,
                "render_queue_profile": str(render.get("profile") or ""),
                "render_queue_pack": str(render.get("pack") or ""),
                "containment_action": containment_action,
                "containment_surface": "work/cache-retention-plan.html",
                "source_surface": str(source.get("review_surface") or "work/source-curation-plan.html"),
                "audio_surface": str(audio.get("review_surface") or "work/audio-control-plan.html"),
                "package_page": str(slate.get("package_page") or render.get("current_package_page") or ""),
                "drive_pressure_lane": str(largest_lane.get("lane") or "renders"),
                "drive_pressure_size": str(largest_lane.get("human_size") or ""),
                "containment_gate": (
                    "No import, Photos export, render, delete, deployment, package mutation, or source-audio mutation in this work order."
                ),
                "preflight_commands": [
                    "python3 verify_editions.py",
                    dry_run,
                    "python3 verify_private_workflow.py",
                    "python3 verify_public_site.py",
                    "python3 verify_package.py",
                    "python3 generated_inventory.py --cleanup-plan",
                ],
                "media_generation": "none",
                "source_access": "none",
                "destructive_actions": "none",
                "deployment": "none",
                "requires_secrets": False,
                "public_package_mutation": False,
                "photos_library_mutation": False,
                "staging_mutation": False,
                "source_audio_mutation": False,
                "product_shop_gate": "deferred until explicit product review",
            }
        )
    rows.sort(key=lambda row: row["rank"])
    return {
        "schema": "triptych.paired-work-order.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "source_edition_refinement_slate": "work/edition-refinement-slate.json",
        "source_source_curation_plan": "work/source-curation-plan.json",
        "source_audio_control_plan": "work/audio-control-plan.json",
        "source_cache_retention_plan": "work/cache-retention-plan.json",
        "source_next_render_queue": "work/next-render-queue.json",
        "preset_source": "editions.example.json",
        "package_ready": payload["containment_track"]["package"].get("exists") is True,
        "media_generation": "none",
        "source_access": "none",
        "deployment": "none",
        "requires_secrets": False,
        "destructive_actions": "none",
        "public_package_mutation": False,
        "photos_library_mutation": False,
        "staging_mutation": False,
        "source_audio_mutation": False,
        "product_shop_gate": "deferred until explicit product review",
        "row_count": len(rows),
        "rows": rows,
        "paired_rule": "Every autonomous pass chooses one creative move and one containment move.",
        "first_next_surface": rows[0]["creative_surface"] if rows else "work/edition-refinement-slate.html",
        "first_containment_surface": "work/cache-retention-plan.html",
        "preflight_commands": [
            "python3 generated_inventory.py --cleanup-plan",
            "python3 verify_editions.py",
            "python3 verify_private_workflow.py",
            "python3 verify_public_site.py",
            "python3 verify_package.py",
        ],
        "operating_gates": [
            "This paired work order is private steering only; it performs no import, render, Photos export, delete, deployment, or package mutation.",
            "A creative move is not actionable unless the paired containment gate is visible beside it.",
            "Dry-run commands may be copied into an explicit render pass, but this handoff itself must remain no-media-generation.",
            "Porn remains local-only until explicit public-export review changes that gate.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_paired_work_order_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.paired-work-order.v1":
        errors.append("unexpected paired work-order schema")
    if payload.get("package_ready") is not True:
        errors.append("paired work-order package_ready must be true")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("deployment", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"paired work-order {key} must be {expected}")
    for key in (
        "requires_secrets",
        "public_package_mutation",
        "photos_library_mutation",
        "staging_mutation",
        "source_audio_mutation",
    ):
        if payload.get(key) is not False:
            errors.append(f"paired work-order {key} must be false")
    refs: list[tuple[str, Any]] = [
        ("source_checkpoint", payload.get("source_checkpoint")),
        ("source_edition_refinement_slate", payload.get("source_edition_refinement_slate")),
        ("source_source_curation_plan", payload.get("source_source_curation_plan")),
        ("source_audio_control_plan", payload.get("source_audio_control_plan")),
        ("source_cache_retention_plan", payload.get("source_cache_retention_plan")),
        ("source_next_render_queue", payload.get("source_next_render_queue")),
        ("preset_source", payload.get("preset_source")),
        ("first_next_surface", payload.get("first_next_surface")),
        ("first_containment_surface", payload.get("first_containment_surface")),
    ]
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("paired work-order rows must be a non-empty list")
        rows = []
    if payload.get("row_count") != len(rows):
        errors.append("paired work-order row_count must match rows length")
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"paired work-order missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"paired work-order row {index} must be an object")
            continue
        if row.get("paired_tracks") != ["creative", "containment"]:
            errors.append(f"paired work-order row {index} paired_tracks must be creative + containment")
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("deployment", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"paired work-order row {index} {key} must be {expected}")
        for key in (
            "requires_secrets",
            "public_package_mutation",
            "photos_library_mutation",
            "staging_mutation",
            "source_audio_mutation",
        ):
            if row.get(key) is not False:
                errors.append(f"paired work-order row {index} {key} must be false")
        dry_run = str(row.get("dry_run_command") or "")
        if row.get("edition") != "porn" and ("--dry-run" not in dry_run or "--skip-import" not in dry_run):
            errors.append(f"paired work-order row {index} dry_run_command must be skip-import dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"paired work-order row {index} dry_run_command must not export missing originals")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("paired work-order porn row must stay gated-local-only")
        if row.get("edition") != "porn" and row.get("public_export_gate") not in {"public-package-ready", "not-public"}:
            errors.append(f"paired work-order row {index} public_export_gate must be public-package-ready or not-public")
        if not row.get("creative_action") or not row.get("containment_action") or not row.get("text_edit_prompt"):
            errors.append(f"paired work-order row {index} must include creative, containment, and text edit fields")
        for ref_key in ("creative_surface", "containment_surface", "source_surface", "audio_surface", "package_page"):
            ref = row.get(ref_key)
            if isinstance(ref, str) and ref:
                refs.append((f"rows[{index}].{ref_key}", ref))
        commands = row.get("preflight_commands")
        if not isinstance(commands, list) or "python3 verify_private_workflow.py" not in commands:
            errors.append(f"paired work-order row {index} preflight must include private workflow verification")
    for label, ref in refs:
        if not isinstance(ref, str) or not ref:
            errors.append(f"paired work-order missing {label}")
            continue
        ref_path = Path(ref.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"paired work-order {label} escapes incubator: {ref}")
            continue
        target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(target, SCRIPT_DIR):
            errors.append(f"paired work-order {label} escapes incubator: {ref}")
        elif not target.exists() and ref in {
            "work/paired-work-order.html",
            "work/edition-refinement-slate.html",
            "work/cache-retention-plan.html",
            "work/source-curation-plan.html",
            "work/audio-control-plan.html",
        }:
            continue
        elif not target.exists():
            errors.append(f"paired work-order {label} does not exist: {ref}")
    text = json.dumps(payload, sort_keys=True)
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"paired work-order contains forbidden token {forbidden!r}")
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"paired work-order contains private token {token!r}")
    return errors


def dashboard_payload(
    payload: dict[str, Any],
    focus: dict[str, Any],
    auditions: dict[str, Any],
    render_queue: dict[str, Any],
    hosting: dict[str, Any],
    first_release: dict[str, Any],
    posting_receipt: dict[str, Any],
    release_cadence: dict[str, Any],
    edition_slate: dict[str, Any],
    retention_plan: dict[str, Any],
    source_curation: dict[str, Any],
    audio_control: dict[str, Any],
    paired_work_order: dict[str, Any],
) -> dict[str, Any]:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    package = containment["package"]
    inventory = containment["inventory"]
    cleanup = containment["cleanup_candidates"]
    links = [
        {
            "id": "checkpoint",
            "label": "Overnight checkpoint",
            "kind": "private receipt",
            "href": "work/overnight-checkpoint.md",
            "purpose": "Creative and containment summary.",
        },
        {
            "id": "release-focus",
            "label": "Release focus",
            "kind": "private review",
            "href": "work/release-focus.html",
            "purpose": "Visual review of current posting/refinement candidates.",
        },
        {
            "id": "control-auditions",
            "label": "Control auditions",
            "kind": "private review",
            "href": "work/control-auditions.html",
            "purpose": "Text-control recipes for direction, panels, audio, presets, and loops.",
        },
        {
            "id": "next-render-queue",
            "label": "Next render queue",
            "kind": "private plan",
            "href": "work/next-render-queue.html",
            "purpose": "Dry-run-first render candidates and post-render gates.",
        },
        {
            "id": "static-hosting-handoff",
            "label": "Static hosting handoff",
            "kind": "private handoff",
            "href": "work/static-hosting-handoff.html",
            "purpose": "Verified package transfer scope and hosting preflight gates.",
        },
        {
            "id": "first-release-packet",
            "label": "First release packet",
            "kind": "private posting packet",
            "href": "work/first-release-packet.html",
            "purpose": "Platform-specific first-post checklist from verified package media.",
        },
        {
            "id": "posting-receipt-template",
            "label": "Posting receipt template",
            "kind": "private receipt template",
            "href": "work/posting-receipt-template.html",
            "purpose": "Private unposted receipt slots for future platform evidence.",
        },
        {
            "id": "release-cadence-plan",
            "label": "Release cadence plan",
            "kind": "private sequence",
            "href": "work/release-cadence-plan.html",
            "purpose": "Ordered posting/refinement sequence over verified focus items.",
        },
        {
            "id": "edition-refinement-slate",
            "label": "Edition refinement slate",
            "kind": "private edition slate",
            "href": "work/edition-refinement-slate.html",
            "purpose": "Per-edition next actions across public-ready and gated work.",
        },
        {
            "id": "cache-retention-plan",
            "label": "Cache retention plan",
            "kind": "private retention plan",
            "href": "work/cache-retention-plan.html",
            "purpose": "Read-only lane reclaim posture with creative proof surfaces.",
        },
        {
            "id": "source-curation-plan",
            "label": "Source curation plan",
            "kind": "private source plan",
            "href": "work/source-curation-plan.html",
            "purpose": "Album roles, raw/model distinctions, and dry-run-only source refresh posture.",
        },
        {
            "id": "audio-control-plan",
            "label": "Audio control plan",
            "kind": "private audio plan",
            "href": "work/audio-control-plan.html",
            "purpose": "Per-edition gain, panel balance, direction-aware audio, and browser-only playback controls.",
        },
        {
            "id": "paired-work-order",
            "label": "Paired work order",
            "kind": "private paired plan",
            "href": "work/paired-work-order.html",
            "purpose": "Always-both next moves: creative edit beside containment gate.",
        },
        {
            "id": "package-index",
            "label": "Package index",
            "kind": "package",
            "href": "packages/triptych-video-canon-site/index.html",
            "purpose": "Verified package entry point.",
        },
        {
            "id": "release-board",
            "label": "Release board",
            "kind": "package",
            "href": "packages/triptych-video-canon-site/release-board.html",
            "purpose": "Public posting board inside the verified package.",
        },
        {
            "id": "release-player",
            "label": "Release player",
            "kind": "package",
            "href": "packages/triptych-video-canon-site/release-player.html",
            "purpose": "Public playback surface inside the verified package.",
        },
        {
            "id": "public-manifest",
            "label": "Public manifest",
            "kind": "public receipt",
            "href": "site/public-manifest.json",
            "purpose": "Sanitized release/post map.",
        },
    ]
    return {
        "schema": "triptych.overnight-dashboard.v1",
        "generated_at": payload["generated_at"],
        "source_checkpoint": "work/overnight-checkpoint.json",
        "release_focus": "work/release-focus.json",
        "control_auditions": "work/control-auditions.json",
        "next_render_queue": "work/next-render-queue.json",
        "package_ready": package.get("exists") is True and package.get("schema_ok") is True,
        "media_generation": "none",
        "source_access": "none",
        "destructive_actions": "none",
        "product_shop_gate": "deferred until explicit product review",
        "creative_summary": {
            "edition_count": creative["edition_count"],
            "families": creative["families"],
            "public_items": creative["public_items"],
            "runtime_seconds": creative["runtime_seconds"],
            "post_exports": creative["post_exports"],
            "visual_sketches": creative["visual_sketches"],
            "focus_count": focus["focus_count"],
            "audition_count": auditions["audition_count"],
            "render_candidate_count": render_queue["queue_count"],
            "hosting_entrypoint_count": len(hosting["entrypoints"]),
            "first_release_packets": first_release["platform_packet_count"],
            "posting_receipt_slots": posting_receipt["slot_count"],
            "release_cadence_items": release_cadence["cadence_count"],
            "edition_refinement_rows": edition_slate["edition_count"],
            "retention_lanes": retention_plan["row_count"],
            "source_curation_rows": source_curation["row_count"],
            "audio_control_rows": audio_control["row_count"],
            "paired_work_order_rows": paired_work_order["row_count"],
        },
        "containment_summary": {
            "package_file_count": package.get("file_count", 0),
            "package_size": package.get("human_size", "0 B"),
            "work_files": next((lane.get("files", 0) for lane in inventory if lane.get("path") == "work"), 0),
            "work_size": next((human_size(lane.get("bytes", 0)) for lane in inventory if lane.get("path") == "work"), "0 B"),
            "render_cache_size": next((human_size(lane.get("bytes", 0)) for lane in inventory if lane.get("path") == "renders"), "0 B"),
            "cleanup_candidate_count": len(cleanup),
        },
        "links": links,
        "next_actions": [
            "Open work/first-release-packet.html when the next move is posting instead of rendering.",
            "Use work/posting-receipt-template.html to keep future social-platform receipts private.",
            "Use work/release-cadence-plan.html when choosing the next verified focus item.",
            "Use work/edition-refinement-slate.html to keep every edition, including gated Porn, in view.",
            "Use work/cache-retention-plan.html before reclaiming generated media manually.",
            "Use work/source-curation-plan.html before changing album source selection or staging media.",
            "Use work/audio-control-plan.html before changing rendered audio, panel gains, or reverse/ping-pong audio posture.",
            "Use work/paired-work-order.html to keep each creative move paired with a containment gate.",
            "Open work/release-focus.html and choose whether a current public output is ready to post or refine.",
            "Open work/control-auditions.html before any rerender to test text controls against package media.",
            "Use work/next-render-queue.html only as a dry-run-first plan if a render is justified.",
            "Run python3 verify_private_workflow.py after regenerating private handoffs.",
        ],
        "operating_gates": [
            "Dashboard is private workflow state under work/ and should not be packaged.",
            "All package links must resolve inside incubator/triptych-video-canon/.",
            "No media generation, source access, Photos export, or deletion is performed by this dashboard.",
            "Product/shop use remains deferred until a concrete product object is selected.",
        ],
    }


def validate_dashboard_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "triptych.overnight-dashboard.v1":
        errors.append("unexpected overnight dashboard schema")
    if payload.get("package_ready") is not True:
        errors.append("overnight dashboard package_ready must be true")
    for key, expected in (
        ("media_generation", "none"),
        ("source_access", "none"),
        ("destructive_actions", "none"),
        ("product_shop_gate", "deferred until explicit product review"),
    ):
        if payload.get(key) != expected:
            errors.append(f"overnight dashboard {key} must be {expected}")
    links = payload.get("links")
    if not isinstance(links, list) or not links:
        errors.append("overnight dashboard links must be a non-empty list")
        links = []
    link_ids = {str(link.get("id") or "") for link in links if isinstance(link, dict)}
    for required in (
        "checkpoint",
        "release-focus",
        "control-auditions",
        "next-render-queue",
        "first-release-packet",
        "posting-receipt-template",
        "release-cadence-plan",
        "edition-refinement-slate",
        "cache-retention-plan",
        "source-curation-plan",
        "audio-control-plan",
        "paired-work-order",
        "package-index",
    ):
        if required not in link_ids:
            errors.append(f"overnight dashboard missing link {required!r}")
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            errors.append(f"overnight dashboard link {index} must be an object")
            continue
        href = link.get("href")
        if not isinstance(href, str) or not href:
            errors.append(f"overnight dashboard link {index} missing href")
            continue
        ref_path = Path(href.split("?", 1)[0])
        if ref_path.is_absolute() or ".." in ref_path.parts:
            errors.append(f"overnight dashboard link {index} escapes incubator: {href}")
            continue
        ref_target = (SCRIPT_DIR / ref_path).resolve()
        if not path_inside(ref_target, SCRIPT_DIR):
            errors.append(f"overnight dashboard link {index} escapes incubator: {href}")
        elif not ref_target.exists() and href not in {
            "work/static-hosting-handoff.html",
            "work/first-release-packet.html",
            "work/posting-receipt-template.html",
            "work/release-cadence-plan.html",
            "work/edition-refinement-slate.html",
            "work/cache-retention-plan.html",
            "work/source-curation-plan.html",
            "work/audio-control-plan.html",
            "work/paired-work-order.html",
        }:
            errors.append(f"overnight dashboard link {index} does not exist: {href}")
    text = json.dumps(payload, sort_keys=True)
    for token in PRIVATE_TEXT:
        if token in text:
            errors.append(f"overnight dashboard contains private token {token!r}")
    return errors


def markdown(payload: dict[str, Any]) -> str:
    creative = payload["creative_track"]
    containment = payload["containment_track"]
    package = containment["package"]
    lines = [
        "# Triptych Overnight Checkpoint",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Creative Track",
        "",
        f"- Editions: {creative['edition_count']}",
        f"- Families: {', '.join(f'{key}={value}' for key, value in sorted(creative['families'].items()))}",
        f"- Public items: {creative['public_items']}",
        f"- Runtime: {creative['runtime_seconds']} seconds",
        f"- Post exports: {creative['post_exports']}",
        f"- Visual sketches: {creative['visual_sketches']}",
        f"- Living rotation sets: {len(creative['living_rotation_sets'])}",
        f"- Release focus candidates: {len(creative['release_focus'])}",
        "",
        "## Rotation Sets",
        "",
    ]
    for rotation in creative["living_rotation_sets"]:
        lines.append(
            f"- {rotation['id']}: {rotation['slot_count']} slots, volume {rotation['volume']}, "
            f"rate {rotation['rate']}, first URL {rotation['first_href']}"
        )
    lines.extend(
        [
            "",
            "## Release Focus",
            "",
        ]
    )
    for item in creative["release_focus"]:
        lines.extend(
            [
                f"### {item['rank']}. {markdown_text(item['role'])}: {markdown_text(item['work_title'])} / {markdown_text(item['label'])}",
                "",
                f"- Media: {item['href']}",
                f"- Package media: {item['package_media_href']}",
                f"- Release board: {item['release_board_href']}",
                f"- Release player: {item['release_player_href']}",
                f"- Kind: {item['kind']}",
                f"- Targets: {', '.join(item['targets'])}",
                f"- Facts: {item['media']['duration_seconds']}s / {item['media']['dimensions']} / {item['media']['human_size']} / {'audio' if item['media']['has_audio'] else 'silent'}",
                f"- Caption seed: {markdown_text(item['caption_seed'])}",
                f"- Edit prompt: {markdown_text(item['edit_prompt'])}",
                f"- Why: {markdown_text(item['why'])}",
                f"- Product/shop gate: {item['product_shop_gate']}",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## Containment Track",
            "",
            f"- Package: {'yes' if package['exists'] else 'no'} / {package.get('file_count', 0)} files / {package.get('human_size', '0 B')}",
            "- Cleanup candidates:",
        ]
    )
    for candidate in containment["cleanup_candidates"]:
        lines.append(
            f"  - {candidate['lane']}/: {candidate['human_size']} / {candidate['risk']}"
        )
    lines.extend(["", "## Checks", ""])
    for check in payload["checks"]:
        marker = "ok" if check["ok"] else "fail"
        lines.append(f"- {marker}: {check['id']} ({check['evidence']})")
    lines.extend(["", "## Next Autonomous Moves", ""])
    for move in payload["next_autonomous_moves"]:
        lines.append(f"- {move}")
    return "\n".join(lines).rstrip() + "\n"


def focus_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Release Focus",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private posting/refinement focus generated from sanitized public receipts. Use the package or release board for review before posting.",
        "",
        "- Source checkpoint: work/overnight-checkpoint.json",
        f"- Public manifest: {payload['public_manifest']}",
        f"- Release board: {payload['release_board']}",
        f"- Release copy: {payload['release_copy']}",
        f"- Release queue: {payload['release_queue']}",
        f"- Package entrypoint: {payload['package_entrypoint']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    lines.extend(["", "## Focus", ""])
    for item in payload["focus"]:
        lines.extend(
            [
                f"### {item['rank']}. {markdown_text(item['role'])}: {markdown_text(item['work_title'])} / {markdown_text(item['label'])}",
                "",
                f"- Media: {item['href']}",
                f"- Package media: {item['package_media_href']}",
                f"- Release board: {item['release_board_href']}",
                f"- Release player: {item['release_player_href']}",
                f"- Kind: {item['kind']}",
                f"- Targets: {', '.join(item['targets'])}",
                f"- Facts: {item['media']['duration_seconds']}s / {item['media']['dimensions']} / {item['media']['human_size']} / {'audio' if item['media']['has_audio'] else 'silent'}",
                f"- Caption seed: {markdown_text(item['caption_seed'])}",
                f"- Edit prompt: {markdown_text(item['edit_prompt'])}",
                f"- Why: {markdown_text(item['why'])}",
                f"- Product/shop gate: {item['product_shop_gate']}",
                "",
                "Review before posting:",
            ]
        )
        for check in item["review_before_posting"]:
            lines.append(f"- {markdown_text(check)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def focus_html(payload: dict[str, Any]) -> str:
    cards: list[str] = []
    for item in payload["focus"]:
        media = item["media"]
        targets = "".join(f"<li>{html_text(target)}</li>" for target in item["targets"])
        checks = "".join(f"<li>{html_text(check)}</li>" for check in item["review_before_posting"])
        media_href = html_text(work_href(item["package_media_href"]))
        board_href = html_text(work_href(item["release_board_href"]))
        player_href = html_text(work_href(item["release_player_href"]))
        cards.append(
            f"""
      <article class="focus-card">
        <div class="media-frame">
          <video controls preload="metadata" playsinline src="{media_href}"></video>
        </div>
        <div class="card-copy">
          <p class="role">#{html_text(item['rank'])} {html_text(item['role'])}</p>
          <h2>{html_text(item['work_title'])}</h2>
          <p class="label">{html_text(item['label'])}</p>
          <dl>
            <div><dt>Kind</dt><dd>{html_text(item['kind'])}</dd></div>
            <div><dt>Facts</dt><dd>{html_text(media['duration_seconds'])}s / {html_text(media['dimensions'])} / {html_text(media['human_size'])} / {html_text('audio' if media['has_audio'] else 'silent')}</dd></div>
            <div><dt>Gate</dt><dd>{html_text(item['product_shop_gate'])}</dd></div>
          </dl>
          <p class="why">{html_text(item['why'])}</p>
          <p><strong>Caption seed:</strong> {html_text(item['caption_seed'])}</p>
          <p><strong>Edit prompt:</strong> {html_text(item['edit_prompt'])}</p>
          <ul class="targets">{targets}</ul>
          <div class="links">
            <a href="{media_href}">Media</a>
            <a href="{player_href}">Player</a>
            <a href="{board_href}">Board</a>
          </div>
          <details>
            <summary>Review gates</summary>
            <ul>{checks}</ul>
          </details>
        </div>
      </article>
"""
        )
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Release Focus</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #11110f;
      --panel: #1a1a17;
      --line: #34342f;
      --text: #f1eee6;
      --muted: #b8b1a4;
      --accent: #9ed3c6;
      --hot: #f0a96a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1500px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 36px;
    }}
    header {{
      display: grid;
      gap: 12px;
      grid-template-columns: 1fr auto;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 56px); font-weight: 650; }}
    h2 {{ font-size: clamp(21px, 2.2vw, 34px); line-height: 1.05; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{
      color: var(--muted);
      max-width: 76ch;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--hot);
      padding: 8px 12px;
      white-space: nowrap;
    }}
    .focus-list {{
      display: grid;
      gap: 18px;
    }}
    .focus-card {{
      display: grid;
      grid-template-columns: minmax(250px, 38vw) minmax(0, 1fr);
      gap: 18px;
      min-height: 420px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }}
    .media-frame {{
      background: #050505;
      min-height: 380px;
      display: grid;
      place-items: center;
      overflow: hidden;
    }}
    video {{
      width: 100%;
      height: 100%;
      max-height: 78vh;
      aspect-ratio: 9 / 16;
      object-fit: contain;
      background: #000;
    }}
    .card-copy {{
      display: grid;
      align-content: start;
      gap: 12px;
      min-width: 0;
    }}
    .role, .label, .why, dt, summary {{
      color: var(--muted);
    }}
    .role {{
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0;
    }}
    dl {{
      display: grid;
      gap: 8px;
      margin: 0;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    dt {{
      font-size: 12px;
    }}
    dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .targets {{
      color: var(--accent);
      display: flex;
      flex-wrap: wrap;
      gap: 8px 20px;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .links a {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      min-width: 76px;
      text-align: center;
    }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      margin-top: 24px;
      color: var(--muted);
      max-width: 90ch;
    }}
    @media (max-width: 820px) {{
      main {{ width: min(100vw - 20px, 620px); padding-top: 12px; }}
      header, .focus-card {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
      dl {{ grid-template-columns: 1fr; }}
      .focus-card {{ min-height: 0; }}
      .media-frame {{ min-height: 0; }}
      video {{ max-height: 70vh; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Release Focus</h1>
        <p class="meta">Private review surface generated from sanitized public receipts. Generated: {html_text(payload['generated_at'])}. Product/shop gate: {html_text(payload['product_shop_gate'])}.</p>
      </div>
      <div class="pill">{html_text(payload['focus_count'])} focus items</div>
    </header>
    <section class="focus-list" aria-label="Release focus candidates">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Operating gates">
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def control_auditions_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Control Auditions",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private text-control audition board generated from sanitized public receipts. These links should help choose direction, surface, panel order, player rate, and audio balance before rendering more media.",
        "",
        "- Source checkpoint: work/overnight-checkpoint.json",
        f"- Public manifest: {payload['public_manifest']}",
        f"- Playback contract: {payload['playback_contract']}",
        f"- Living loop: {payload['living_loop']}",
        f"- Package entrypoint: {payload['package_entrypoint']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    current_category = ""
    for item in payload["auditions"]:
        category = markdown_text(item["category"])
        if category != current_category:
            lines.extend(["", f"## {category.title()}", ""])
            current_category = category
        controls = ", ".join(f"{key}={value}" for key, value in item.get("controls", {}).items())
        lines.extend(
            [
                f"### {item['rank']}. {markdown_text(item['label'])}",
                "",
                f"- Work: {markdown_text(item['work_title'])}",
                f"- Edition: {markdown_text(item['edition'])}",
                f"- Link: {item['href']}",
                f"- Intent: {markdown_text(item['intent'])}",
                f"- Controls: {markdown_text(controls)}",
                f"- Media generation: {item['media_generation']}",
                f"- Source access: {item['source_access']}",
                f"- Product/shop gate: {item['product_shop_gate']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def control_auditions_html(payload: dict[str, Any]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in payload["auditions"]:
        groups.setdefault(str(item.get("category") or "other"), []).append(item)
    sections: list[str] = []
    for category, items in groups.items():
        cards: list[str] = []
        for item in items:
            controls = "".join(
                f"<span>{html_text(key)}={html_text(value)}</span>"
                for key, value in item.get("controls", {}).items()
            )
            cards.append(
                f"""
        <article class="audition">
          <p class="rank">#{html_text(item['rank'])} / {html_text(item['edition'])}</p>
          <h3>{html_text(item['label'])}</h3>
          <p>{html_text(item['work_title'])}</p>
          <p class="intent">{html_text(item['intent'])}</p>
          <div class="controls">{controls}</div>
          <a class="open" href="{html_text(work_href(item['href']))}">Open audition</a>
        </article>
"""
            )
        sections.append(
            f"""
      <section>
        <h2>{html_text(category.title())}</h2>
        <div class="grid">{''.join(cards)}
        </div>
      </section>
"""
        )
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Control Auditions</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101112;
      --panel: #191b1d;
      --line: #33383a;
      --text: #f2f0e9;
      --muted: #b5b2aa;
      --accent: #a8d8b9;
      --warn: #f1b276;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 24px;
      display: grid;
      gap: 12px;
      grid-template-columns: 1fr auto;
      align-items: end;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 54px); line-height: 1; }}
    h2 {{ font-size: 20px; margin: 24px 0 12px; }}
    h3 {{ font-size: 18px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta, .intent, .rank, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .audition {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      background: var(--panel);
      min-height: 220px;
      display: grid;
      align-content: start;
      gap: 10px;
    }}
    .rank {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .controls span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 7px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .open {{
      width: max-content;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
      margin-top: 2px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 26px;
      padding-top: 16px;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Control Auditions</h1>
        <p class="meta">Private text-control board generated from sanitized public receipts. Generated: {html_text(payload['generated_at'])}. Media generation: {html_text(payload['media_generation'])}.</p>
      </div>
      <div class="pill">{html_text(payload['audition_count'])} auditions</div>
    </header>
{''.join(sections)}
    <section class="gates">
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def render_queue_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Next Render Queue",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private render-intention queue. It names candidate commands only; it does not render, delete, export Photos originals, or publish by itself.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source release focus: {payload['source_release_focus']}",
        f"- Source control auditions: {payload['source_control_auditions']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Destructive actions: {payload['destructive_actions']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Operating Gates",
        "",
    ]
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    lines.extend(["", "## Queue", ""])
    for item in payload["queue"]:
        lines.extend(
            [
                f"### {item['rank']}. {markdown_text(item['work_title'])}",
                "",
                f"- Edition: {item['edition']}",
                f"- Profile: {item['profile']}",
                f"- Pack: {item['pack']}",
                f"- Dry run: `{item['dry_run_command']}`",
                f"- Render: `{item['render_command']}`",
                f"- Project: {item['project_manifest']}",
                f"- Current package page: {item['current_package_page']}",
                f"- Why: {markdown_text(item['why'])}",
                f"- Render pressure: {markdown_text(item['render_pressure_note'])}",
                f"- Media generation: {item['media_generation']}",
                f"- Source access: {item['source_access']}",
                f"- Destructive actions: {item['destructive_actions']}",
                "",
                "Review before render:",
            ]
        )
        for review in item["review_before_render"]:
            lines.append(f"- {markdown_text(review)}")
        lines.extend(["", "Post-render gates:"])
        for gate in item["post_render_gates"]:
            lines.append(f"- `{gate}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_queue_html(payload: dict[str, Any]) -> str:
    cards: list[str] = []
    for item in payload["queue"]:
        reviews = "".join(f"<li>{html_text(review)}</li>" for review in item["review_before_render"])
        gates = "".join(f"<li><code>{html_text(gate)}</code></li>" for gate in item["post_render_gates"])
        cards.append(
            f"""
      <article class="render-card">
        <p class="rank">#{html_text(item['rank'])} / {html_text(item['edition'])}</p>
        <h2>{html_text(item['work_title'])}</h2>
        <dl>
          <div><dt>Profile</dt><dd>{html_text(item['profile'])}</dd></div>
          <div><dt>Pack</dt><dd>{html_text(item['pack'])}</dd></div>
          <div><dt>Actions</dt><dd>{html_text(item['destructive_actions'])}</dd></div>
        </dl>
        <p>{html_text(item['why'])}</p>
        <p class="pressure">{html_text(item['render_pressure_note'])}</p>
        <div class="commands">
          <p><strong>Dry run</strong><code>{html_text(item['dry_run_command'])}</code></p>
          <p><strong>Render</strong><code>{html_text(item['render_command'])}</code></p>
        </div>
        <p><a href="{html_text(work_href(item['current_package_page']))}">Open current package page</a></p>
        <details open>
          <summary>Review before render</summary>
          <ul>{reviews}</ul>
        </details>
        <details>
          <summary>Post-render gates</summary>
          <ul>{gates}</ul>
        </details>
      </article>
"""
        )
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Next Render Queue</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10100f;
      --panel: #1a1b18;
      --line: #34362f;
      --text: #f1eee6;
      --muted: #b9b2a5;
      --accent: #aad1ef;
      --warn: #e8b073;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1300px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
      display: grid;
      gap: 12px;
      grid-template-columns: 1fr auto;
      align-items: end;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 54px); line-height: 1; }}
    h2 {{ font-size: 24px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      display: block;
      overflow-x: auto;
      white-space: pre;
      margin-top: 4px;
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .meta, .rank, .pressure, dt, summary {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .render-list {{
      display: grid;
      gap: 14px;
    }}
    .render-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 16px;
      display: grid;
      gap: 12px;
    }}
    .rank {{
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0;
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; }}
    .commands {{
      display: grid;
      gap: 8px;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Next Render Queue</h1>
        <p class="meta">Private planned-only render queue. Generated: {html_text(payload['generated_at'])}. Destructive actions: {html_text(payload['destructive_actions'])}.</p>
      </div>
      <div class="pill">{html_text(payload['queue_count'])} render candidates</div>
    </header>
    <section class="render-list" aria-label="Next render candidates">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Operating gates">
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def static_hosting_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Static Hosting Handoff",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private hosting handoff for transferring only the verified static package.",
        "",
        f"- Package directory: {payload['package_dir']}",
        f"- Package zip: {payload['package_zip']}",
        f"- Package manifest: {payload['package_manifest']}",
        f"- Package size: {payload['package_size']}",
        f"- Package files: {payload['package_file_count']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deployment: {payload['deployment']}",
        f"- Requires secrets: {payload['requires_secrets']}",
        f"- Destructive actions: {payload['destructive_actions']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Entrypoints",
        "",
    ]
    for entry in payload["entrypoints"]:
        lines.extend(
            [
                f"### {markdown_text(entry['label'])}",
                "",
                f"- Link: {entry['href']}",
                f"- Purpose: {markdown_text(entry['purpose'])}",
                "",
            ]
        )
    lines.extend(["## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Upload Scope", ""])
    for item in payload["upload_scope"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Never Upload", ""])
    for item in payload["never_upload"]:
        lines.append(f"- {markdown_text(item)}")
    lines.extend(["", "## Post Upload Checks", ""])
    for check in payload["post_upload_checks"]:
        lines.append(f"- {markdown_text(check)}")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def static_hosting_html(payload: dict[str, Any]) -> str:
    entry_cards = []
    for entry in payload["entrypoints"]:
        entry_cards.append(
            f"""
        <article class="card">
          <p class="kind">entrypoint</p>
          <h3>{html_text(entry['label'])}</h3>
          <p>{html_text(entry['purpose'])}</p>
          <a href="{html_text(work_href(entry['href']))}">Open</a>
        </article>
"""
        )
    commands = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    never = "".join(f"<li>{html_text(item)}</li>" for item in payload["never_upload"])
    checks = "".join(f"<li>{html_text(check)}</li>" for check in payload["post_upload_checks"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Static Hosting Handoff</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10110f;
      --panel: #1b1c18;
      --line: #34382f;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a9d5f2;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1280px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 21px; margin: 22px 0 12px; }}
    h3 {{ font-size: 18px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .meta, .kind, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }}
    .stat, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .stat p:first-child, .kind {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .stat p:last-child {{
      font-size: 21px;
      margin-top: 4px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
    }}
    .card {{
      display: grid;
      gap: 9px;
      align-content: start;
      min-height: 160px;
    }}
    .card a {{
      width: max-content;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Static Hosting Handoff</h1>
        <p class="meta">Private transfer scope for the verified package. Generated: {html_text(payload['generated_at'])}. Requires secrets: {html_text(payload['requires_secrets'])}.</p>
      </div>
      <div class="pill">{html_text(payload['package_size'])} / {html_text(payload['package_file_count'])} files</div>
    </header>
    <section aria-label="Package summary">
      <div class="stats">
        <div class="stat"><p>Package directory</p><p>{html_text(payload['package_dir'])}</p></div>
        <div class="stat"><p>Package zip</p><p>{html_text(payload['package_zip'])}</p></div>
        <div class="stat"><p>Deployment</p><p>{html_text(payload['deployment'])}</p></div>
        <div class="stat"><p>Actions</p><p>{html_text(payload['destructive_actions'])}</p></div>
      </div>
    </section>
    <section aria-label="Entrypoints">
      <h2>Entrypoints</h2>
      <div class="grid">{''.join(entry_cards)}
      </div>
    </section>
    <section class="gates" aria-label="Hosting gates">
      <h2>Preflight Commands</h2>
      <ul>{commands}</ul>
      <h2>Never Upload</h2>
      <ul>{never}</ul>
      <h2>Post Upload Checks</h2>
      <ul>{checks}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def first_release_packet_markdown(payload: dict[str, Any]) -> str:
    selected = payload["selected"]
    media = selected.get("media") if isinstance(selected.get("media"), dict) else {}
    lines = [
        "# Triptych First Release Packet",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private posting packet generated from the verified static package. It selects one release-focus item and turns it into platform-specific copy without rendering new media.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source release focus: {payload['source_release_focus']}",
        f"- Source static hosting handoff: {payload['source_static_hosting_handoff']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deployment: {payload['deployment']}",
        f"- Requires secrets: {payload['requires_secrets']}",
        f"- Destructive actions: {payload['destructive_actions']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Selected",
        "",
        f"- Work: {markdown_text(selected.get('work_title'))}",
        f"- Edition: {markdown_text(selected.get('edition'))}",
        f"- Role: {markdown_text(selected.get('role'))}",
        f"- Kind: {markdown_text(selected.get('kind'))}",
        f"- Label: {markdown_text(selected.get('label'))}",
        f"- Package media: {selected.get('package_media_href')}",
        f"- Release player: {selected.get('release_player_href')}",
        f"- Release board: {selected.get('release_board_href')}",
        f"- Facts: {media.get('duration_seconds', 0)}s / {media.get('dimensions', 'unknown')} / {media.get('human_size', '0 B')} / {'audio' if media.get('has_audio') else 'silent'}",
        f"- Why: {markdown_text(selected.get('why'))}",
        f"- Alt text: {markdown_text(selected.get('alt_text'))}",
        "",
        "## Platform Packets",
        "",
    ]
    for packet in payload["platform_packets"]:
        lines.extend(
            [
                f"### {markdown_text(packet['target'])}",
                "",
                f"- Role: {markdown_text(packet['role'])}",
                f"- Upload ref: {packet['upload_ref']}",
                f"- Caption: {markdown_text(packet['caption'])}",
                f"- Alt text: {markdown_text(packet['alt_text'])}",
                "",
                "Review:",
            ]
        )
        for review in packet["review"]:
            lines.append(f"- {markdown_text(review)}")
        lines.append("")
    lines.extend(["## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Review Before Posting", ""])
    for review in payload["review_before_posting"]:
        lines.append(f"- {markdown_text(review)}")
    lines.extend(["", "## Post Posting Receipt", ""])
    for receipt in payload["post_posting_receipt"]:
        lines.append(f"- {markdown_text(receipt)}")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def first_release_packet_html(payload: dict[str, Any]) -> str:
    selected = payload["selected"]
    media = selected.get("media") if isinstance(selected.get("media"), dict) else {}
    media_href = html_text(work_href(selected.get("package_media_href")))
    player_href = html_text(work_href(selected.get("release_player_href")))
    board_href = html_text(work_href(selected.get("release_board_href")))
    packet_cards = []
    for packet in payload["platform_packets"]:
        reviews = "".join(f"<li>{html_text(review)}</li>" for review in packet["review"])
        packet_cards.append(
            f"""
        <article class="packet">
          <p class="kind">{html_text(packet['role'])}</p>
          <h3>{html_text(packet['target'])}</h3>
          <p><strong>Upload</strong> <a href="{html_text(work_href(packet['upload_ref']))}">{html_text(packet['upload_ref'])}</a></p>
          <label>Caption<textarea readonly>{html_text(packet['caption'])}</textarea></label>
          <label>Alt text<textarea readonly>{html_text(packet['alt_text'])}</textarea></label>
          <details>
            <summary>Review</summary>
            <ul>{reviews}</ul>
          </details>
        </article>
"""
        )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    review = "".join(f"<li>{html_text(item)}</li>" for item in payload["review_before_posting"])
    receipt = "".join(f"<li>{html_text(item)}</li>" for item in payload["post_posting_receipt"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych First Release Packet</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1010;
      --panel: #191a19;
      --line: #343733;
      --text: #f2efe8;
      --muted: #b9b2a5;
      --accent: #b8d8a6;
      --warn: #f1b172;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1480px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 58px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .selected {{
      display: grid;
      grid-template-columns: minmax(260px, 36vw) minmax(0, 1fr);
      gap: 18px;
      align-items: start;
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 18px;
    }}
    .media-frame {{
      background: #050505;
      display: grid;
      place-items: center;
      min-height: 420px;
      overflow: hidden;
    }}
    video {{
      width: 100%;
      height: 100%;
      max-height: 78vh;
      aspect-ratio: 9 / 16;
      object-fit: contain;
      background: #000;
    }}
    .copy {{
      display: grid;
      gap: 12px;
      align-content: start;
      min-width: 0;
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .links, .packets {{
      display: grid;
      gap: 12px;
    }}
    .links {{
      grid-template-columns: repeat(auto-fit, minmax(120px, max-content));
    }}
    .links a {{
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
      text-align: center;
    }}
    .packets {{
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    .packet {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
    }}
    textarea {{
      width: 100%;
      min-height: 120px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      background: #111211;
      color: var(--text);
      font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 820px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, .selected, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
      .media-frame {{ min-height: 0; }}
      video {{ max-height: 70vh; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych First Release Packet</h1>
        <p class="meta">Private first-post handoff generated from verified package media. Generated: {html_text(payload['generated_at'])}. Media generation: {html_text(payload['media_generation'])}.</p>
      </div>
      <div class="pill">{html_text(payload['platform_packet_count'])} platform packets</div>
    </header>
    <section class="selected" aria-label="Selected release">
      <div class="media-frame">
        <video controls preload="metadata" playsinline src="{media_href}"></video>
      </div>
      <div class="copy">
        <p class="kind">selected / {html_text(selected.get('role'))}</p>
        <h2>{html_text(selected.get('work_title'))}</h2>
        <p>{html_text(selected.get('label'))}</p>
        <dl>
          <div><dt>Kind</dt><dd>{html_text(selected.get('kind'))}</dd></div>
          <div><dt>Facts</dt><dd>{html_text(media.get('duration_seconds', 0))}s / {html_text(media.get('dimensions', 'unknown'))} / {html_text(media.get('human_size', '0 B'))} / {html_text('audio' if media.get('has_audio') else 'silent')}</dd></div>
          <div><dt>Gate</dt><dd>{html_text(payload['product_shop_gate'])}</dd></div>
        </dl>
        <p>{html_text(selected.get('why'))}</p>
        <p><strong>Alt text:</strong> {html_text(selected.get('alt_text'))}</p>
        <div class="links">
          <a href="{media_href}">Media</a>
          <a href="{player_href}">Player</a>
          <a href="{board_href}">Board</a>
        </div>
      </div>
    </section>
    <section aria-label="Platform packets">
      <h2>Platform Packets</h2>
      <div class="packets">{''.join(packet_cards)}
      </div>
    </section>
    <section class="gates" aria-label="Preflight and gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Review Before Posting</h2>
      <ul>{review}</ul>
      <h2>Post Posting Receipt</h2>
      <ul>{receipt}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def posting_receipt_template_markdown(payload: dict[str, Any]) -> str:
    selected = payload["selected"]
    lines = [
        "# Triptych Posting Receipt Template",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private unposted receipt template for future platform evidence. It records what should be captured after a post exists without mutating the public package today.",
        "",
        f"- Source first-release packet: {payload['source_first_release_packet']}",
        f"- Source static-hosting handoff: {payload['source_static_hosting_handoff']}",
        f"- Receipt status: {payload['receipt_status']}",
        f"- Posted count: {payload['posted_count']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deployment: {payload['deployment']}",
        f"- Requires secrets: {payload['requires_secrets']}",
        f"- Destructive actions: {payload['destructive_actions']}",
        f"- Public package mutation: {payload['public_package_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Selected",
        "",
        f"- Work: {markdown_text(selected.get('work_title'))}",
        f"- Edition: {markdown_text(selected.get('edition'))}",
        f"- Kind: {markdown_text(selected.get('kind'))}",
        f"- Label: {markdown_text(selected.get('label'))}",
        f"- Package media: {selected.get('package_media_href')}",
        f"- Release player: {selected.get('release_player_href')}",
        f"- Release board: {selected.get('release_board_href')}",
        "",
        "## Receipt Slots",
        "",
    ]
    for slot in payload["slots"]:
        lines.extend(
            [
                f"### {markdown_text(slot['target'])}",
                "",
                f"- Status: {slot['status']}",
                f"- Upload ref: {slot['upload_ref']}",
                f"- Posted URL: {slot['posted_url'] or '[blank]'}",
                f"- Posted at: {slot['posted_at'] or '[blank]'}",
                f"- Caption used: {slot['caption_used'] or '[blank]'}",
                f"- Caption variant: {markdown_text(slot['caption_variant'])}",
                f"- Alt text: {markdown_text(slot['alt_text'])}",
                f"- Public package mutation: {slot['public_package_mutation']}",
                f"- Product/shop gate: {slot['product_shop_gate']}",
                "",
            ]
        )
    lines.extend(["## Private Receipt Fields", ""])
    for field in payload["private_receipt_fields"]:
        lines.append(f"- {field}")
    lines.extend(["", "## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def posting_receipt_template_html(payload: dict[str, Any]) -> str:
    selected = payload["selected"]
    slot_cards = []
    for slot in payload["slots"]:
        slot_cards.append(
            f"""
        <article class="slot">
          <p class="kind">{html_text(slot['status'])} / {html_text(slot['target'])}</p>
          <h3>{html_text(slot['work_title'])}</h3>
          <p><strong>Upload</strong> <a href="{html_text(work_href(slot['upload_ref']))}">{html_text(slot['upload_ref'])}</a></p>
          <dl>
            <div><dt>Posted URL</dt><dd>{html_text(slot['posted_url'] or '[blank]')}</dd></div>
            <div><dt>Posted at</dt><dd>{html_text(slot['posted_at'] or '[blank]')}</dd></div>
            <div><dt>Package mutation</dt><dd>{html_text(slot['public_package_mutation'])}</dd></div>
          </dl>
          <label>Caption variant<textarea readonly>{html_text(slot['caption_variant'])}</textarea></label>
          <label>Alt text<textarea readonly>{html_text(slot['alt_text'])}</textarea></label>
          <p class="gate">{html_text(slot['product_shop_gate'])}</p>
        </article>
"""
        )
    fields = "".join(f"<li><code>{html_text(field)}</code></li>" for field in payload["private_receipt_fields"])
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    media_href = html_text(work_href(selected.get("package_media_href")))
    player_href = html_text(work_href(selected.get("release_player_href")))
    board_href = html_text(work_href(selected.get("release_board_href")))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Posting Receipt Template</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1111;
      --panel: #191b1b;
      --line: #333837;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a7d7c9;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1400px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 19px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .meta, .kind, dt, .gate, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .selected, .slot {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .selected {{
      display: grid;
      gap: 10px;
      margin-bottom: 18px;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .links a {{
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    .slots {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }}
    .slot {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
    }}
    textarea {{
      width: 100%;
      min-height: 100px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      background: #111312;
      color: var(--text);
      font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Posting Receipt Template</h1>
        <p class="meta">Private unposted receipt template generated from the first-release packet. Generated: {html_text(payload['generated_at'])}. Public package mutation: {html_text(payload['public_package_mutation'])}.</p>
      </div>
      <div class="pill">{html_text(payload['slot_count'])} unposted slots</div>
    </header>
    <section class="selected" aria-label="Selected work">
      <p class="kind">selected / {html_text(selected.get('edition'))}</p>
      <h2>{html_text(selected.get('work_title'))}</h2>
      <p>{html_text(selected.get('label'))}</p>
      <div class="links">
        <a href="{media_href}">Media</a>
        <a href="{player_href}">Player</a>
        <a href="{board_href}">Board</a>
      </div>
    </section>
    <section aria-label="Receipt slots">
      <h2>Receipt Slots</h2>
      <div class="slots">{''.join(slot_cards)}
      </div>
    </section>
    <section class="gates" aria-label="Receipt gates">
      <h2>Private Receipt Fields</h2>
      <ul>{fields}</ul>
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def release_cadence_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Release Cadence Plan",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private ordered sequence for choosing the next verified focus item. This is not a calendar and does not publish, render, or record social-platform state.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source release focus: {payload['source_release_focus']}",
        f"- Source first-release packet: {payload['source_first_release_packet']}",
        f"- Source posting receipt template: {payload['source_posting_receipt_template']}",
        f"- Source next render queue: {payload['source_next_render_queue']}",
        f"- Cadence mode: {payload['cadence_mode']}",
        f"- Posting receipt status: {payload['posting_receipt_status']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deployment: {payload['deployment']}",
        f"- Public package mutation: {payload['public_package_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Sequence",
        "",
    ]
    for item in payload["sequence"]:
        lines.extend(
            [
                f"### {item['sequence_rank']}. {markdown_text(item['work_title'])} / {markdown_text(item['label'])}",
                "",
                f"- Status: {item['status']}",
                f"- Edition: {item['edition']}",
                f"- Role: {markdown_text(item['role'])}",
                f"- Kind: {item['kind']}",
                f"- Primary target: {markdown_text(item['primary_target'])}",
                f"- Target candidates: {', '.join(markdown_text(target) for target in item['target_candidates'])}",
                f"- Package media: {item['package_media_href']}",
                f"- Release player: {item['release_player_href']}",
                f"- Release board: {item['release_board_href']}",
                f"- Receipt template: {markdown_text(item['receipt_template'])}",
                f"- Dry run command: `{item['dry_run_command']}`" if item["dry_run_command"] else "- Dry run command: [none]",
                f"- Caption seed: {markdown_text(item['caption_seed'])}",
                f"- Edit prompt: {markdown_text(item['edit_prompt'])}",
                f"- Why: {markdown_text(item['why'])}",
                f"- If not ready: {markdown_text(item['if_not_ready'])}",
                "",
                "Review before posting:",
            ]
        )
        for review in item["review_before_posting"]:
            lines.append(f"- {markdown_text(review)}")
        lines.append("")
    lines.extend(["## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def release_cadence_html(payload: dict[str, Any]) -> str:
    cards = []
    for item in payload["sequence"]:
        targets = "".join(f"<li>{html_text(target)}</li>" for target in item["target_candidates"])
        reviews = "".join(f"<li>{html_text(review)}</li>" for review in item["review_before_posting"])
        dry_run = html_text(item["dry_run_command"] or "[none]")
        cards.append(
            f"""
        <article class="cadence-card">
          <p class="kind">#{html_text(item['sequence_rank'])} / {html_text(item['status'])} / {html_text(item['edition'])}</p>
          <h3>{html_text(item['work_title'])}</h3>
          <p>{html_text(item['label'])}</p>
          <dl>
            <div><dt>Role</dt><dd>{html_text(item['role'])}</dd></div>
            <div><dt>Kind</dt><dd>{html_text(item['kind'])}</dd></div>
            <div><dt>Target</dt><dd>{html_text(item['primary_target'])}</dd></div>
          </dl>
          <p>{html_text(item['why'])}</p>
          <p><strong>Caption seed</strong> {html_text(item['caption_seed'])}</p>
          <p><strong>Edit prompt</strong> {html_text(item['edit_prompt'])}</p>
          <div class="links">
            <a href="{html_text(work_href(item['package_media_href']))}">Media</a>
            <a href="{html_text(work_href(item['release_player_href']))}">Player</a>
            <a href="{html_text(work_href(item['release_board_href']))}">Board</a>
            <a href="{html_text(work_href(item['render_queue_ref']))}">Render queue</a>
          </div>
          <details>
            <summary>Targets and gates</summary>
            <ul>{targets}</ul>
            <p><strong>Receipt</strong> {html_text(item['receipt_template'])}</p>
            <p><strong>Dry run</strong><code>{dry_run}</code></p>
            <p>{html_text(item['if_not_ready'])}</p>
            <ul>{reviews}</ul>
          </details>
        </article>
"""
        )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Release Cadence Plan</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10100f;
      --panel: #1a1b18;
      --line: #35362f;
      --text: #f2efe8;
      --muted: #b9b2a5;
      --accent: #bedf91;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      display: block;
      overflow-x: auto;
      margin-top: 4px;
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .cadence-list {{
      display: grid;
      gap: 12px;
    }}
    .cadence-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .links a {{
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Release Cadence Plan</h1>
        <p class="meta">Private ordered sequence over verified focus items. Generated: {html_text(payload['generated_at'])}. Mode: {html_text(payload['cadence_mode'])}.</p>
      </div>
      <div class="pill">{html_text(payload['cadence_count'])} cadence items</div>
    </header>
    <section class="cadence-list" aria-label="Release cadence sequence">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Cadence gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def edition_refinement_slate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Edition Refinement Slate",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private per-edition steering slate. It keeps public-ready editions and gated local work visible together without rendering, publishing, or exposing source paths.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source control auditions: {payload['source_control_auditions']}",
        f"- Source next render queue: {payload['source_next_render_queue']}",
        f"- Source release cadence: {payload['source_release_cadence']}",
        f"- Preset source: {payload['preset_source']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deployment: {payload['deployment']}",
        f"- Public package mutation: {payload['public_package_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Editions",
        "",
    ]
    for row in payload["rows"]:
        cadence = ", ".join(
            f"#{item['sequence_rank']} {markdown_text(item['kind'])} -> {markdown_text(item['primary_target'])}"
            for item in row["cadence_items"]
        ) or "none"
        lines.extend(
            [
                f"### {row['rank']}. {markdown_text(row['work_title'])}",
                "",
                f"- Edition: {row['edition']}",
                f"- Family: {row['family']}",
                f"- Public gate: {row['public_export_gate']}",
                f"- Package page: {row['package_page'] or '[none]'}",
                f"- Default preset: {markdown_text(row['default_preset'])} ({row['preset_count']} presets)",
                f"- Visual map: {markdown_text(row['visual_map']['style'])} / {row['visual_map']['cell_count']} cells",
                f"- Post exports: {row['post_exports']}",
                f"- Visual sketches: {row['visual_sketches']}",
                f"- Cadence: {cadence}",
                f"- Auditions: {row['audition_count']}",
                f"- Dry run: `{row['dry_run_command']}`" if row["dry_run_command"] else "- Dry run: [none]",
                f"- Next private surface: {row['next_private_surface']}",
                f"- Recommended next action: {markdown_text(row['recommended_next_action'])}",
                f"- Rationale: {markdown_text(row['rationale'])}",
                f"- Note: {markdown_text(row['note'])}",
                f"- Product/shop gate: {row['product_shop_gate']}",
                "",
            ]
        )
    lines.extend(["## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def edition_refinement_slate_html(payload: dict[str, Any]) -> str:
    cards = []
    for row in payload["rows"]:
        cadence = "".join(
            f"<li>#{html_text(item['sequence_rank'])} {html_text(item['kind'])} -> {html_text(item['primary_target'])}</li>"
            for item in row["cadence_items"]
        ) or "<li>none</li>"
        package_link = (
            f'<a href="{html_text(work_href(row["package_page"]))}">Package page</a>'
            if row["package_page"]
            else "<span>No package page</span>"
        )
        dry_run = html_text(row["dry_run_command"] or "[none]")
        cards.append(
            f"""
        <article class="edition-card {html_text(row['public_export_gate'])}">
          <p class="kind">#{html_text(row['rank'])} / {html_text(row['edition'])} / {html_text(row['public_export_gate'])}</p>
          <h3>{html_text(row['work_title'])}</h3>
          <p>{html_text(row['note'])}</p>
          <dl>
            <div><dt>Family</dt><dd>{html_text(row['family'])}</dd></div>
            <div><dt>Preset</dt><dd>{html_text(row['default_preset'])} / {html_text(row['preset_count'])}</dd></div>
            <div><dt>Map</dt><dd>{html_text(row['visual_map']['style'])} / {html_text(row['visual_map']['cell_count'])}</dd></div>
            <div><dt>Posts</dt><dd>{html_text(row['post_exports'])}</dd></div>
            <div><dt>Sketches</dt><dd>{html_text(row['visual_sketches'])}</dd></div>
            <div><dt>Auditions</dt><dd>{html_text(row['audition_count'])}</dd></div>
          </dl>
          <p><strong>Next</strong> {html_text(row['recommended_next_action'])}</p>
          <p>{html_text(row['rationale'])}</p>
          <div class="links">
            {package_link}
            <a href="{html_text(work_href(row['next_private_surface']))}">Next private surface</a>
          </div>
          <details>
            <summary>Cadence and render posture</summary>
            <ul>{cadence}</ul>
            <p><strong>Dry run</strong><code>{dry_run}</code></p>
            <p>{html_text(row['product_shop_gate'])}</p>
          </details>
        </article>
"""
        )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Edition Refinement Slate</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101110;
      --panel: #1b1c1a;
      --line: #343833;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a7d7c9;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      display: block;
      overflow-x: auto;
      margin-top: 4px;
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .edition-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 12px;
    }}
    .edition-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .gated-local-only {{
      border-color: var(--warn);
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .links a, .links span {{
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    .links span {{
      border-color: var(--line);
      color: var(--muted);
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Edition Refinement Slate</h1>
        <p class="meta">Private per-edition steering over public-ready and gated work. Generated: {html_text(payload['generated_at'])}. Media generation: {html_text(payload['media_generation'])}.</p>
      </div>
      <div class="pill">{html_text(payload['edition_count'])} editions</div>
    </header>
    <section class="edition-grid" aria-label="Edition refinement rows">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Slate gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def cache_retention_plan_markdown(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        "# Triptych Cache Retention Plan",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private read-only retention plan for generated lanes. It names manual reclaim posture without deleting files, rendering media, or changing the public package.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source edition slate: {payload['source_edition_refinement_slate']}",
        f"- Source release cadence: {payload['source_release_cadence']}",
        f"- Source hosting handoff: {payload['source_static_hosting_handoff']}",
        f"- Inventory command: `{payload['inventory_command']}`",
        f"- Total scanned: {totals['human_total']}",
        f"- Generated bytes: {human_size(totals['generated_bytes'])}",
        f"- Staged source bytes: {human_size(totals['staged_source_bytes'])}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Deletion performed: {payload['deletion_performed']}",
        f"- Public package mutation: {payload['public_package_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Lane Decisions",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"### {row['lane']}/",
                "",
                f"- Role: {markdown_text(row['role'])}",
                f"- Size: {row['human_size']} / {row['files']} files",
                f"- Decision: {markdown_text(row['decision'])}",
                f"- Risk: {markdown_text(row['risk'])}",
                f"- Rationale: {markdown_text(row['rationale'])}",
                f"- Creative impact: {markdown_text(row['creative_impact'])}",
                f"- Private: {row['private']}",
                f"- Disposable: {row['disposable']}",
                f"- Manual only: {row['manual_only']}",
                "",
                "Regenerate/check with:",
            ]
        )
        for command in row["regenerate_with"]:
            lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Protected Private Surfaces", ""])
    for ref in payload["protected_private_surfaces"]:
        lines.append(f"- {ref}")
    lines.extend(["", "## Creative Proof Surfaces", ""])
    for ref in payload["creative_proof_surfaces"]:
        lines.append(f"- {ref}")
    lines.extend(["", "## Preflight Commands", ""])
    for command in payload["preflight_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def cache_retention_plan_html(payload: dict[str, Any]) -> str:
    rows = []
    for row in payload["rows"]:
        commands = "".join(f"<li><code>{html_text(command)}</code></li>" for command in row["regenerate_with"])
        rows.append(
            f"""
        <article class="lane-card {html_text(row['decision'])}">
          <p class="kind">{html_text(row['lane'])}/ / {html_text(row['decision'])}</p>
          <h3>{html_text(row['role'])}</h3>
          <dl>
            <div><dt>Size</dt><dd>{html_text(row['human_size'])}</dd></div>
            <div><dt>Files</dt><dd>{html_text(row['files'])}</dd></div>
            <div><dt>Private</dt><dd>{html_text(row['private'])}</dd></div>
            <div><dt>Disposable</dt><dd>{html_text(row['disposable'])}</dd></div>
            <div><dt>Manual only</dt><dd>{html_text(row['manual_only'])}</dd></div>
            <div><dt>Risk</dt><dd>{html_text(row['risk'])}</dd></div>
          </dl>
          <p>{html_text(row['rationale'])}</p>
          <p><strong>Creative impact</strong> {html_text(row['creative_impact'])}</p>
          <details>
            <summary>Regeneration gates</summary>
            <ul>{commands}</ul>
          </details>
        </article>
"""
        )
    protected = "".join(
        f'<li><a href="{html_text(work_href(ref))}">{html_text(ref)}</a></li>'
        for ref in payload["protected_private_surfaces"]
    )
    proofs = "".join(
        f'<li><a href="{html_text(work_href(ref))}">{html_text(ref)}</a></li>'
        for ref in payload["creative_proof_surfaces"]
    )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    totals = payload["totals"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Cache Retention Plan</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101110;
      --panel: #1a1c1b;
      --line: #343836;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a7d7c9;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .stats, .lane-grid {{
      display: grid;
      gap: 12px;
    }}
    .stats {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-bottom: 16px;
    }}
    .stat, .lane-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .stat p:first-child {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .stat p:last-child {{
      font-size: 22px;
      margin-top: 4px;
    }}
    .lane-grid {{
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }}
    .lane-card {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .protect-private-receipts,
    .protect-staged-source {{
      border-color: var(--warn);
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Cache Retention Plan</h1>
        <p class="meta">Private read-only lane posture. Generated: {html_text(payload['generated_at'])}. Deletion performed: {html_text(payload['deletion_performed'])}.</p>
      </div>
      <div class="pill">{html_text(payload['row_count'])} lanes / {html_text(totals['human_total'])}</div>
    </header>
    <section class="stats" aria-label="Inventory totals">
      <div class="stat"><p>Total scanned</p><p>{html_text(totals['human_total'])}</p></div>
      <div class="stat"><p>Generated</p><p>{html_text(human_size(totals['generated_bytes']))}</p></div>
      <div class="stat"><p>Staged source</p><p>{html_text(human_size(totals['staged_source_bytes']))}</p></div>
      <div class="stat"><p>Mutation</p><p>{html_text(payload['public_package_mutation'])}</p></div>
    </section>
    <section class="lane-grid" aria-label="Retention lane decisions">
{''.join(rows)}
    </section>
    <section class="gates" aria-label="Retention gates">
      <h2>Protected Private Surfaces</h2>
      <ul>{protected}</ul>
      <h2>Creative Proof Surfaces</h2>
      <ul>{proofs}</ul>
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def source_curation_plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Source Curation Plan",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private dry-run-first album/source steering. This handoff performs no import, export, render, deletion, or source mutation.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Source edition slate: {payload['source_edition_refinement_slate']}",
        f"- Source cache retention plan: {payload['source_cache_retention_plan']}",
        f"- Preset source: {payload['preset_source']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Photos library mutation: {payload['photos_library_mutation']}",
        f"- Staging mutation: {payload['staging_mutation']}",
        f"- Public package mutation: {payload['public_package_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Edition Source Rows",
        "",
    ]
    for row in payload["rows"]:
        language = ", ".join(row.get("language", [])) or "none"
        model_album = row["model_album"] or "same as raw album"
        lines.extend(
            [
                f"### {row['rank']}. {markdown_text(row['work_title'])}",
                "",
                f"- Edition: {row['edition']}",
                f"- Family: {row['family']}",
                f"- Source type: {row['source_type']} / {row['source_mode']}",
                f"- Raw album: {row['raw_album']}",
                f"- Model album: {model_album}",
                f"- Match/order/limit: {row['album_match']} / {row['order']} / {row['selection_limit']}",
                f"- Motion/fps/crf: {row['motion']} / {row['fps']} / {row['crf']}",
                f"- Visual map: {row['visual_map']['style']} / {row['visual_map']['cell_count']} cells",
                f"- Public gate: {row['public_export_gate']}",
                f"- Recommended source action: {markdown_text(row['recommended_source_action'])}",
                f"- Rationale: {markdown_text(row['rationale'])}",
                f"- Review surface: {row['review_surface']}",
                f"- Dry-run command: `{row['dry_run_command']}`",
                f"- Status command: `{row['status_command']}`",
                f"- Panel role: {markdown_text(row['panel_arrangement_role'])}",
                f"- Arrangement model role: {markdown_text(row['arrangement_model_role'])}",
                f"- Arrangement model observation: {markdown_text(row['arrangement_model_observation'])}",
                f"- Arrangement model instruction: {markdown_text(row['arrangement_model_instruction'])}",
                f"- Language: {markdown_text(language)}",
                f"- Media generation: {row['media_generation']}",
                f"- Source access: {row['source_access']}",
                "",
                "Preflight:",
            ]
        )
        for command in row["preflight_commands"]:
            lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def source_curation_plan_html(payload: dict[str, Any]) -> str:
    cards = []
    for row in payload["rows"]:
        commands = "".join(f"<li><code>{html_text(command)}</code></li>" for command in row["preflight_commands"])
        language = ", ".join(row.get("language", [])) or "none"
        model_album = row["model_album"] or "same as raw album"
        cards.append(
            f"""
        <article class="source-card {html_text(row['public_export_gate'])}">
          <p class="kind">{html_text(row['edition'])} / {html_text(row['source_mode'])}</p>
          <h3>{html_text(row['work_title'])}</h3>
          <dl>
            <div><dt>Raw album</dt><dd>{html_text(row['raw_album'])}</dd></div>
            <div><dt>Model album</dt><dd>{html_text(model_album)}</dd></div>
            <div><dt>Family</dt><dd>{html_text(row['family'])}</dd></div>
            <div><dt>Limit</dt><dd>{html_text(row['selection_limit'])}</dd></div>
            <div><dt>Order</dt><dd>{html_text(row['order'])}</dd></div>
            <div><dt>Map</dt><dd>{html_text(row['visual_map']['style'])} / {html_text(row['visual_map']['cell_count'])}</dd></div>
            <div><dt>Gate</dt><dd>{html_text(row['public_export_gate'])}</dd></div>
            <div><dt>Action</dt><dd>{html_text(row['recommended_source_action'])}</dd></div>
          </dl>
          <p>{html_text(row['rationale'])}</p>
          <p><strong>Panel role</strong> {html_text(row['panel_arrangement_role'])}</p>
          <p><strong>Arrangement model</strong> {html_text(row['arrangement_model_role'])}</p>
          <p><strong>Observation</strong> {html_text(row['arrangement_model_observation'])}</p>
          <p><strong>Language</strong> {html_text(language)}</p>
          <p><strong>Review</strong> <a href="{html_text(work_href(row['review_surface']))}">{html_text(row['review_surface'])}</a></p>
          <details>
            <summary>Dry-run and preflight</summary>
            <p><code>{html_text(row['dry_run_command'])}</code></p>
            <ul>{commands}</ul>
          </details>
        </article>
"""
        )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Source Curation Plan</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10110f;
      --panel: #1a1d1a;
      --line: #353932;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #b9d98c;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .source-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }}
    .source-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .gated-local-only {{ border-color: var(--warn); }}
    dl {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Source Curation Plan</h1>
        <p class="meta">Private dry-run-first album/source steering. Generated: {html_text(payload['generated_at'])}. Source access: {html_text(payload['source_access'])}.</p>
      </div>
      <div class="pill">{html_text(payload['row_count'])} source rows</div>
    </header>
    <section class="source-grid" aria-label="Source curation rows">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Source curation gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def panel_gain_text(panel_gains: dict[str, Any]) -> str:
    if not isinstance(panel_gains, dict) or not panel_gains:
        return "none"
    return ", ".join(
        f"{panel}={panel_gains[panel]}"
        for panel in ("left", "middle", "right")
        if panel in panel_gains
    ) or "none"


def audio_control_plan_markdown(payload: dict[str, Any]) -> str:
    snapshot = payload["public_sound_snapshot"]
    lines = [
        "# Triptych Audio Control Plan",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private audio steering for rendered gains, direction-aware audio, and browser-only playback controls. This handoff performs no render, source access, or source-audio mutation.",
        "",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Public sound map: {payload['source_public_sound_map']}",
        f"- Playback contract: {payload['source_playback_contract']}",
        f"- Source curation plan: {payload['source_source_curation_plan']}",
        f"- Preset source: {payload['preset_source']}",
        f"- Public items: {snapshot['item_count']}",
        f"- Audio-bearing items: {snapshot['audio_item_count']}",
        f"- Silent items: {snapshot['silent_item_count']}",
        f"- Browser controls: {', '.join(snapshot['browser_only_controls'])}",
        f"- Quiet review: {snapshot['quiet_review']}",
        f"- Muted kiosk: {snapshot['muted_kiosk']}",
        f"- Seeded audio review: {snapshot['seeded_audio_review']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Source audio mutation: {payload['source_audio_mutation']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Edition Audio Rows",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"### {row['rank']}. {markdown_text(row['work_title'])}",
                "",
                f"- Edition: {row['edition']}",
                f"- Family: {row['family']}",
                f"- Audio mode: {row['audio_mode']}",
                f"- Audio panel: {row['audio_panel'] or 'all'}",
                f"- Render gain: {row['render_gain']}",
                f"- Panel gains: {panel_gain_text(row['panel_gains'])}",
                f"- Fade seconds: {row['fade_seconds']}",
                f"- Direction: {row['direction']}",
                f"- Audio presets: {row['audio_preset_count']} of {len(row['control_presets'])}",
                f"- Public audio/silent items: {row['public_audio_items']} / {row['public_silent_items']}",
                f"- Public audio runtime: {row['public_audio_duration_seconds']} seconds",
                f"- Recommended audio action: {markdown_text(row['recommended_audio_action'])}",
                f"- Rationale: {markdown_text(row['rationale'])}",
                f"- Review surface: {row['review_surface']}",
                f"- Review player: {row['review_player_href'] or 'private gated'}",
                f"- Dry-run command: `{row['dry_run_command']}`",
                f"- Source audio mutation: {row['source_audio_mutation']}",
                "",
                "Control presets:",
            ]
        )
        for preset in row["control_presets"]:
            lines.append(
                "- "
                f"{markdown_text(preset['id'])}: {preset['direction']} / "
                f"{'audio' if preset['audio'] else 'silent'} / volume {preset['volume']} / "
                f"panels {panel_gain_text(preset.get('panel_volumes', {}))}"
            )
        lines.append("")
        lines.append("Preflight:")
        for command in row["preflight_commands"]:
            lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def audio_control_plan_html(payload: dict[str, Any]) -> str:
    cards = []
    for row in payload["rows"]:
        commands = "".join(f"<li><code>{html_text(command)}</code></li>" for command in row["preflight_commands"])
        presets = "".join(
            "<li>"
            f"{html_text(preset['id'])}: {html_text(preset['direction'])} / "
            f"{html_text('audio' if preset['audio'] else 'silent')} / "
            f"volume {html_text(preset['volume'])} / panels {html_text(panel_gain_text(preset.get('panel_volumes', {})))}"
            "</li>"
            for preset in row["control_presets"]
        )
        review_link = (
            f'<a href="{html_text(work_href(row["review_player_href"]))}">Player</a>'
            if row.get("review_player_href")
            else "<span>private gated</span>"
        )
        cards.append(
            f"""
        <article class="audio-card {html_text(row['direction'])}">
          <p class="kind">{html_text(row['edition'])} / {html_text(row['direction'])}</p>
          <h3>{html_text(row['work_title'])}</h3>
          <dl>
            <div><dt>Mode</dt><dd>{html_text(row['audio_mode'])}</dd></div>
            <div><dt>Panel</dt><dd>{html_text(row['audio_panel'] or 'all')}</dd></div>
            <div><dt>Gain</dt><dd>{html_text(row['render_gain'])}</dd></div>
            <div><dt>Panel gains</dt><dd>{html_text(panel_gain_text(row['panel_gains']))}</dd></div>
            <div><dt>Fade</dt><dd>{html_text(row['fade_seconds'])}</dd></div>
            <div><dt>Public audio</dt><dd>{html_text(row['public_audio_items'])} audio / {html_text(row['public_silent_items'])} silent</dd></div>
            <div><dt>Action</dt><dd>{html_text(row['recommended_audio_action'])}</dd></div>
            <div><dt>Mutation</dt><dd>{html_text(str(row['source_audio_mutation']))}</dd></div>
          </dl>
          <p>{html_text(row['rationale'])}</p>
          <p><strong>Review</strong> <a href="{html_text(work_href(row['review_surface']))}">{html_text(row['review_surface'])}</a> {review_link}</p>
          <details>
            <summary>Control presets</summary>
            <ul>{presets}</ul>
          </details>
          <details>
            <summary>Dry-run and preflight</summary>
            <p><code>{html_text(row['dry_run_command'])}</code></p>
            <ul>{commands}</ul>
          </details>
        </article>
"""
        )
    snapshot = payload["public_sound_snapshot"]
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Audio Control Plan</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101110;
      --panel: #1b1d1c;
      --line: #343837;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a7d7c9;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .stats, .audio-grid {{
      display: grid;
      gap: 12px;
    }}
    .stats {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-bottom: 16px;
    }}
    .stat, .audio-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .stat p:first-child {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .stat p:last-child {{
      font-size: 22px;
      margin-top: 4px;
    }}
    .audio-grid {{
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }}
    .audio-card {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .reverse,
    .pingpong {{
      border-color: var(--warn);
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Audio Control Plan</h1>
        <p class="meta">Private audio steering generated from edition presets and sanitized public sound facts. Generated: {html_text(payload['generated_at'])}. Source audio mutation: {html_text(str(payload['source_audio_mutation']))}.</p>
      </div>
      <div class="pill">{html_text(payload['row_count'])} audio rows</div>
    </header>
    <section class="stats" aria-label="Public sound snapshot">
      <div class="stat"><p>Public items</p><p>{html_text(snapshot['item_count'])}</p></div>
      <div class="stat"><p>Audio items</p><p>{html_text(snapshot['audio_item_count'])}</p></div>
      <div class="stat"><p>Silent items</p><p>{html_text(snapshot['silent_item_count'])}</p></div>
      <div class="stat"><p>Controls</p><p>{html_text(', '.join(snapshot['browser_only_controls']))}</p></div>
    </section>
    <section class="audio-grid" aria-label="Audio control rows">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Audio gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def paired_work_order_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Triptych Paired Work Order",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private next-move handoff for the always-both loop: every creative edit stays paired with a lifecycle gate.",
        "",
        f"- Paired rule: {markdown_text(payload['paired_rule'])}",
        f"- Source checkpoint: {payload['source_checkpoint']}",
        f"- Edition slate: {payload['source_edition_refinement_slate']}",
        f"- Source curation: {payload['source_source_curation_plan']}",
        f"- Audio control: {payload['source_audio_control_plan']}",
        f"- Cache retention: {payload['source_cache_retention_plan']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Work Orders",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"### {row['rank']}. {markdown_text(row['work_title'])}",
                "",
                f"- Edition: {row['edition']}",
                f"- Family: {row['family']}",
                f"- Public gate: {row['public_export_gate']}",
                f"- Creative action: {markdown_text(row['creative_action'])}",
                f"- Creative surface: {row['creative_surface']}",
                f"- Containment action: {markdown_text(row['containment_action'])}",
                f"- Containment surface: {row['containment_surface']}",
                f"- Source surface: {row['source_surface']}",
                f"- Audio surface: {row['audio_surface']}",
                f"- Package page: {row['package_page'] or 'private gated'}",
                f"- Drive pressure: {row['drive_pressure_lane']} {row['drive_pressure_size']}",
                f"- Text edit prompt: {markdown_text(row['text_edit_prompt'])}",
                f"- Dry-run command: `{row['dry_run_command']}`",
                f"- Containment gate: {markdown_text(row['containment_gate'])}",
                "",
                "Creative basis:",
            ]
        )
        basis = row["creative_basis"]
        lines.extend(
            [
                f"- Source action: {markdown_text(basis.get('source_action', ''))}",
                f"- Audio action: {markdown_text(basis.get('audio_action', ''))}",
                f"- Arrangement role: {markdown_text(basis.get('arrangement_role', ''))}",
                f"- Panel role: {markdown_text(basis.get('panel_role', ''))}",
                f"- Language: {', '.join(markdown_text(item) for item in basis.get('language', []))}",
                "",
                "Preflight:",
            ]
        )
        for command in row["preflight_commands"]:
            if command:
                lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def paired_work_order_html(payload: dict[str, Any]) -> str:
    cards = []
    for row in payload["rows"]:
        commands = "".join(f"<li><code>{html_text(command)}</code></li>" for command in row["preflight_commands"] if command)
        basis = row["creative_basis"]
        language = ", ".join(str(item) for item in basis.get("language", []))
        package = (
            f'<a href="{html_text(work_href(row["package_page"]))}">Package page</a>'
            if row.get("package_page")
            else "<span>private gated</span>"
        )
        cards.append(
            f"""
        <article class="order-card">
          <p class="kind">{html_text(row['edition'])} / {html_text(row['public_export_gate'])}</p>
          <h3>{html_text(row['rank'])}. {html_text(row['work_title'])}</h3>
          <div class="paired">
            <section>
              <h4>Creative</h4>
              <p>{html_text(row['creative_action'])}</p>
              <p><a href="{html_text(work_href(row['creative_surface']))}">{html_text(row['creative_surface'])}</a></p>
            </section>
            <section>
              <h4>Containment</h4>
              <p>{html_text(row['containment_action'])}</p>
              <p><a href="{html_text(work_href(row['containment_surface']))}">{html_text(row['containment_surface'])}</a></p>
            </section>
          </div>
          <p class="prompt">{html_text(row['text_edit_prompt'])}</p>
          <dl>
            <div><dt>Source</dt><dd><a href="{html_text(work_href(row['source_surface']))}">{html_text(row['source_surface'])}</a></dd></div>
            <div><dt>Audio</dt><dd><a href="{html_text(work_href(row['audio_surface']))}">{html_text(row['audio_surface'])}</a></dd></div>
            <div><dt>Package</dt><dd>{package}</dd></div>
            <div><dt>Drive</dt><dd>{html_text(row['drive_pressure_lane'])} {html_text(row['drive_pressure_size'])}</dd></div>
            <div><dt>Mutation</dt><dd>{html_text(str(row['public_package_mutation']))} package / {html_text(str(row['source_audio_mutation']))} audio</dd></div>
            <div><dt>Tracks</dt><dd>{html_text(' + '.join(row['paired_tracks']))}</dd></div>
          </dl>
          <details>
            <summary>Creative basis</summary>
            <ul>
              <li>Source: {html_text(basis.get('source_action', ''))}</li>
              <li>Audio: {html_text(basis.get('audio_action', ''))}</li>
              <li>Arrangement: {html_text(basis.get('arrangement_role', ''))}</li>
              <li>Panel: {html_text(basis.get('panel_role', ''))}</li>
              <li>Language: {html_text(language)}</li>
            </ul>
          </details>
          <details>
            <summary>Dry-run and gates</summary>
            <p><code>{html_text(row['dry_run_command'])}</code></p>
            <p>{html_text(row['containment_gate'])}</p>
            <ul>{commands}</ul>
          </details>
        </article>
"""
        )
    preflight = "".join(f"<li><code>{html_text(command)}</code></li>" for command in payload["preflight_commands"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Paired Work Order</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101110;
      --panel: #1b1d1c;
      --line: #343837;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #a7d7c9;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, h4, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 22px; margin: 24px 0 12px; }}
    h3 {{ font-size: 20px; line-height: 1.1; }}
    h4 {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      color: var(--accent);
      font: 13px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .meta, .kind, dt, summary, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .order-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 12px;
    }}
    .order-card {{
      display: grid;
      gap: 12px;
      align-content: start;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .paired {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .paired section {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
    }}
    .prompt {{
      border-left: 3px solid var(--warn);
      padding-left: 10px;
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{ font-size: 12px; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    ul {{ margin: 0; padding-left: 18px; }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
      display: grid;
      gap: 10px;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header, .paired, dl {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Paired Work Order</h1>
        <p class="meta">Private always-both handoff. Generated: {html_text(payload['generated_at'])}. Media generation: {html_text(payload['media_generation'])}. Source audio mutation: {html_text(str(payload['source_audio_mutation']))}.</p>
      </div>
      <div class="pill">{html_text(payload['row_count'])} paired rows</div>
    </header>
    <section class="order-grid" aria-label="Paired work orders">
{''.join(cards)}
    </section>
    <section class="gates" aria-label="Work-order gates">
      <h2>Preflight Commands</h2>
      <ul>{preflight}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def dashboard_markdown(payload: dict[str, Any]) -> str:
    creative = payload["creative_summary"]
    containment = payload["containment_summary"]
    lines = [
        "# Triptych Overnight Dashboard",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Private conductor dashboard for the current overnight workstream.",
        "",
        "## Creative",
        "",
        f"- Editions: {creative['edition_count']}",
        f"- Families: {', '.join(f'{key}={value}' for key, value in sorted(creative['families'].items()))}",
        f"- Public items: {creative['public_items']}",
        f"- Runtime: {creative['runtime_seconds']} seconds",
        f"- Post exports: {creative['post_exports']}",
        f"- Visual sketches: {creative['visual_sketches']}",
        f"- Release focus items: {creative['focus_count']}",
        f"- First release platform packets: {creative['first_release_packets']}",
        f"- Posting receipt slots: {creative['posting_receipt_slots']}",
        f"- Release cadence items: {creative['release_cadence_items']}",
        f"- Edition refinement rows: {creative['edition_refinement_rows']}",
        f"- Retention lanes: {creative['retention_lanes']}",
        f"- Source curation rows: {creative['source_curation_rows']}",
        f"- Audio control rows: {creative['audio_control_rows']}",
        f"- Paired work-order rows: {creative['paired_work_order_rows']}",
        f"- Control auditions: {creative['audition_count']}",
        f"- Render candidates: {creative['render_candidate_count']}",
        "",
        "## Containment",
        "",
        f"- Package: {containment['package_file_count']} files / {containment['package_size']}",
        f"- Work lane: {containment['work_files']} files / {containment['work_size']}",
        f"- Render cache: {containment['render_cache_size']}",
        f"- Cleanup candidates: {containment['cleanup_candidate_count']}",
        f"- Media generation: {payload['media_generation']}",
        f"- Source access: {payload['source_access']}",
        f"- Destructive actions: {payload['destructive_actions']}",
        f"- Product/shop gate: {payload['product_shop_gate']}",
        "",
        "## Links",
        "",
    ]
    for link in payload["links"]:
        lines.extend(
            [
                f"### {markdown_text(link['label'])}",
                "",
                f"- Kind: {markdown_text(link['kind'])}",
                f"- Link: {link['href']}",
                f"- Purpose: {markdown_text(link['purpose'])}",
                "",
            ]
        )
    lines.extend(["## Next Actions", ""])
    for action in payload["next_actions"]:
        lines.append(f"- {markdown_text(action)}")
    lines.extend(["", "## Operating Gates", ""])
    for gate in payload["operating_gates"]:
        lines.append(f"- {markdown_text(gate)}")
    return "\n".join(lines).rstrip() + "\n"


def dashboard_html(payload: dict[str, Any]) -> str:
    creative = payload["creative_summary"]
    containment = payload["containment_summary"]
    link_cards = []
    for link in payload["links"]:
        link_cards.append(
            f"""
        <article class="link-card">
          <p class="kind">{html_text(link['kind'])}</p>
          <h3>{html_text(link['label'])}</h3>
          <p>{html_text(link['purpose'])}</p>
          <a href="{html_text(work_href(link['href']))}">Open</a>
        </article>
"""
        )
    actions = "".join(f"<li>{html_text(action)}</li>" for action in payload["next_actions"])
    gates = "".join(f"<li>{html_text(gate)}</li>" for gate in payload["operating_gates"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Triptych Overnight Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10110f;
      --panel: #1a1c18;
      --line: #343830;
      --text: #f2efe8;
      --muted: #b8b2a6;
      --accent: #b9d98c;
      --warn: #efb06e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(30px, 4vw, 56px); line-height: 1; }}
    h2 {{ font-size: 21px; margin: 22px 0 12px; }}
    h3 {{ font-size: 18px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta, .kind, .gates {{ color: var(--muted); }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--warn);
      white-space: nowrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }}
    .stat, .link-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .stat p:first-child {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .stat p:last-child {{
      font-size: 22px;
      margin-top: 4px;
    }}
    .links {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
    }}
    .link-card {{
      display: grid;
      gap: 9px;
      align-content: start;
      min-height: 170px;
    }}
    .kind {{
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0;
    }}
    .link-card a {{
      width: max-content;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    .gates {{
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 16px;
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 640px); padding-top: 12px; }}
      header {{ grid-template-columns: 1fr; }}
      .pill {{ width: max-content; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Triptych Overnight Dashboard</h1>
        <p class="meta">Private conductor surface generated from current receipts. Generated: {html_text(payload['generated_at'])}. Media generation: {html_text(payload['media_generation'])}.</p>
      </div>
      <div class="pill">{html_text(creative['edition_count'])} editions / {html_text(creative['render_candidate_count'])} render candidates</div>
    </header>
    <section aria-label="Creative and containment summary">
      <div class="stats">
        <div class="stat"><p>Public posts</p><p>{html_text(creative['post_exports'])}</p></div>
        <div class="stat"><p>Visual sketches</p><p>{html_text(creative['visual_sketches'])}</p></div>
        <div class="stat"><p>Release packets</p><p>{html_text(creative['first_release_packets'])}</p></div>
        <div class="stat"><p>Receipt slots</p><p>{html_text(creative['posting_receipt_slots'])}</p></div>
        <div class="stat"><p>Cadence items</p><p>{html_text(creative['release_cadence_items'])}</p></div>
        <div class="stat"><p>Edition rows</p><p>{html_text(creative['edition_refinement_rows'])}</p></div>
        <div class="stat"><p>Retention lanes</p><p>{html_text(creative['retention_lanes'])}</p></div>
        <div class="stat"><p>Source rows</p><p>{html_text(creative['source_curation_rows'])}</p></div>
        <div class="stat"><p>Audio rows</p><p>{html_text(creative['audio_control_rows'])}</p></div>
        <div class="stat"><p>Paired rows</p><p>{html_text(creative['paired_work_order_rows'])}</p></div>
        <div class="stat"><p>Control auditions</p><p>{html_text(creative['audition_count'])}</p></div>
        <div class="stat"><p>Package</p><p>{html_text(containment['package_size'])}</p></div>
        <div class="stat"><p>Work lane</p><p>{html_text(containment['work_size'])}</p></div>
        <div class="stat"><p>Render cache</p><p>{html_text(containment['render_cache_size'])}</p></div>
      </div>
    </section>
    <section aria-label="Dashboard links">
      <h2>Open Surfaces</h2>
      <div class="links">{''.join(link_cards)}
      </div>
    </section>
    <section class="gates" aria-label="Next actions">
      <h2>Next Actions</h2>
      <ul>{actions}</ul>
      <h2>Operating Gates</h2>
      <ul>{gates}</ul>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    site_dir = resolve_inside(args.site_dir, "site-dir")
    package_dir = resolve_inside(args.package_dir, "package-dir")
    output = resolve_inside(args.output, "output")
    doc = resolve_inside(args.doc, "doc")
    focus_output = resolve_inside(args.focus_output, "focus-output")
    focus_doc = resolve_inside(args.focus_doc, "focus-doc")
    focus_html_path = resolve_inside(args.focus_html, "focus-html")
    auditions_output = resolve_inside(args.auditions_output, "auditions-output")
    auditions_doc = resolve_inside(args.auditions_doc, "auditions-doc")
    auditions_html_path = resolve_inside(args.auditions_html, "auditions-html")
    render_queue_output = resolve_inside(args.render_queue_output, "render-queue-output")
    render_queue_doc = resolve_inside(args.render_queue_doc, "render-queue-doc")
    render_queue_html_path = resolve_inside(args.render_queue_html, "render-queue-html")
    dashboard_output = resolve_inside(args.dashboard_output, "dashboard-output")
    dashboard_doc = resolve_inside(args.dashboard_doc, "dashboard-doc")
    dashboard_html_path = resolve_inside(args.dashboard_html, "dashboard-html")
    hosting_output = resolve_inside(args.hosting_output, "hosting-output")
    hosting_doc = resolve_inside(args.hosting_doc, "hosting-doc")
    hosting_html_path = resolve_inside(args.hosting_html, "hosting-html")
    first_release_output = resolve_inside(args.first_release_output, "first-release-output")
    first_release_doc = resolve_inside(args.first_release_doc, "first-release-doc")
    first_release_html_path = resolve_inside(args.first_release_html, "first-release-html")
    posting_receipt_output = resolve_inside(args.posting_receipt_output, "posting-receipt-output")
    posting_receipt_doc = resolve_inside(args.posting_receipt_doc, "posting-receipt-doc")
    posting_receipt_html_path = resolve_inside(args.posting_receipt_html, "posting-receipt-html")
    release_cadence_output = resolve_inside(args.release_cadence_output, "release-cadence-output")
    release_cadence_doc = resolve_inside(args.release_cadence_doc, "release-cadence-doc")
    release_cadence_html_path = resolve_inside(args.release_cadence_html, "release-cadence-html")
    edition_slate_output = resolve_inside(args.edition_slate_output, "edition-slate-output")
    edition_slate_doc = resolve_inside(args.edition_slate_doc, "edition-slate-doc")
    edition_slate_html_path = resolve_inside(args.edition_slate_html, "edition-slate-html")
    retention_output = resolve_inside(args.retention_output, "retention-output")
    retention_doc = resolve_inside(args.retention_doc, "retention-doc")
    retention_html_path = resolve_inside(args.retention_html, "retention-html")
    source_curation_output = resolve_inside(args.source_curation_output, "source-curation-output")
    source_curation_doc = resolve_inside(args.source_curation_doc, "source-curation-doc")
    source_curation_html_path = resolve_inside(args.source_curation_html, "source-curation-html")
    audio_control_output = resolve_inside(args.audio_control_output, "audio-control-output")
    audio_control_doc = resolve_inside(args.audio_control_doc, "audio-control-doc")
    audio_control_html_path = resolve_inside(args.audio_control_html, "audio-control-html")
    paired_work_order_output = resolve_inside(args.paired_work_order_output, "paired-work-order-output")
    paired_work_order_doc = resolve_inside(args.paired_work_order_doc, "paired-work-order-doc")
    paired_work_order_html_path = resolve_inside(args.paired_work_order_html, "paired-work-order-html")
    payload = checkpoint(site_dir, package_dir)
    focus_payload = release_focus_payload(payload)
    auditions_payload = control_auditions_payload(payload)
    render_queue = render_queue_payload(payload)
    hosting_handoff = static_hosting_handoff_payload(payload)
    first_release = first_release_packet_payload(payload, focus_payload, hosting_handoff)
    posting_receipt = posting_receipt_template_payload(first_release)
    release_cadence = release_cadence_payload(payload, focus_payload, first_release, posting_receipt, render_queue)
    edition_slate = edition_refinement_slate_payload(payload, auditions_payload, render_queue, release_cadence)
    retention_plan = cache_retention_plan_payload(payload, edition_slate, release_cadence, hosting_handoff)
    source_curation = source_curation_plan_payload(payload, edition_slate, retention_plan)
    audio_control = audio_control_plan_payload(payload, source_curation)
    paired_work_order = paired_work_order_payload(
        payload,
        edition_slate,
        source_curation,
        audio_control,
        retention_plan,
        render_queue,
    )
    dashboard = dashboard_payload(
        payload,
        focus_payload,
        auditions_payload,
        render_queue,
        hosting_handoff,
        first_release,
        posting_receipt,
        release_cadence,
        edition_slate,
        retention_plan,
        source_curation,
        audio_control,
        paired_work_order,
    )
    if not args.dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(markdown(payload), encoding="utf-8")
        focus_output.parent.mkdir(parents=True, exist_ok=True)
        focus_output.write_text(json.dumps(focus_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        focus_doc.parent.mkdir(parents=True, exist_ok=True)
        focus_doc.write_text(focus_markdown(focus_payload), encoding="utf-8")
        focus_html_path.parent.mkdir(parents=True, exist_ok=True)
        focus_html_path.write_text(focus_html(focus_payload), encoding="utf-8")
        auditions_output.parent.mkdir(parents=True, exist_ok=True)
        auditions_output.write_text(json.dumps(auditions_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        auditions_doc.parent.mkdir(parents=True, exist_ok=True)
        auditions_doc.write_text(control_auditions_markdown(auditions_payload), encoding="utf-8")
        auditions_html_path.parent.mkdir(parents=True, exist_ok=True)
        auditions_html_path.write_text(control_auditions_html(auditions_payload), encoding="utf-8")
        render_queue_output.parent.mkdir(parents=True, exist_ok=True)
        render_queue_output.write_text(json.dumps(render_queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        render_queue_doc.parent.mkdir(parents=True, exist_ok=True)
        render_queue_doc.write_text(render_queue_markdown(render_queue), encoding="utf-8")
        render_queue_html_path.parent.mkdir(parents=True, exist_ok=True)
        render_queue_html_path.write_text(render_queue_html(render_queue), encoding="utf-8")
        hosting_output.parent.mkdir(parents=True, exist_ok=True)
        hosting_output.write_text(json.dumps(hosting_handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        hosting_doc.parent.mkdir(parents=True, exist_ok=True)
        hosting_doc.write_text(static_hosting_markdown(hosting_handoff), encoding="utf-8")
        hosting_html_path.parent.mkdir(parents=True, exist_ok=True)
        hosting_html_path.write_text(static_hosting_html(hosting_handoff), encoding="utf-8")
        first_release_output.parent.mkdir(parents=True, exist_ok=True)
        first_release_output.write_text(json.dumps(first_release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        first_release_doc.parent.mkdir(parents=True, exist_ok=True)
        first_release_doc.write_text(first_release_packet_markdown(first_release), encoding="utf-8")
        first_release_html_path.parent.mkdir(parents=True, exist_ok=True)
        first_release_html_path.write_text(first_release_packet_html(first_release), encoding="utf-8")
        posting_receipt_output.parent.mkdir(parents=True, exist_ok=True)
        posting_receipt_output.write_text(json.dumps(posting_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        posting_receipt_doc.parent.mkdir(parents=True, exist_ok=True)
        posting_receipt_doc.write_text(posting_receipt_template_markdown(posting_receipt), encoding="utf-8")
        posting_receipt_html_path.parent.mkdir(parents=True, exist_ok=True)
        posting_receipt_html_path.write_text(posting_receipt_template_html(posting_receipt), encoding="utf-8")
        release_cadence_output.parent.mkdir(parents=True, exist_ok=True)
        release_cadence_output.write_text(json.dumps(release_cadence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        release_cadence_doc.parent.mkdir(parents=True, exist_ok=True)
        release_cadence_doc.write_text(release_cadence_markdown(release_cadence), encoding="utf-8")
        release_cadence_html_path.parent.mkdir(parents=True, exist_ok=True)
        release_cadence_html_path.write_text(release_cadence_html(release_cadence), encoding="utf-8")
        edition_slate_output.parent.mkdir(parents=True, exist_ok=True)
        edition_slate_output.write_text(json.dumps(edition_slate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        edition_slate_doc.parent.mkdir(parents=True, exist_ok=True)
        edition_slate_doc.write_text(edition_refinement_slate_markdown(edition_slate), encoding="utf-8")
        edition_slate_html_path.parent.mkdir(parents=True, exist_ok=True)
        edition_slate_html_path.write_text(edition_refinement_slate_html(edition_slate), encoding="utf-8")
        retention_output.parent.mkdir(parents=True, exist_ok=True)
        retention_output.write_text(json.dumps(retention_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        retention_doc.parent.mkdir(parents=True, exist_ok=True)
        retention_doc.write_text(cache_retention_plan_markdown(retention_plan), encoding="utf-8")
        retention_html_path.parent.mkdir(parents=True, exist_ok=True)
        retention_html_path.write_text(cache_retention_plan_html(retention_plan), encoding="utf-8")
        source_curation_output.parent.mkdir(parents=True, exist_ok=True)
        source_curation_output.write_text(json.dumps(source_curation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        source_curation_doc.parent.mkdir(parents=True, exist_ok=True)
        source_curation_doc.write_text(source_curation_plan_markdown(source_curation), encoding="utf-8")
        source_curation_html_path.parent.mkdir(parents=True, exist_ok=True)
        source_curation_html_path.write_text(source_curation_plan_html(source_curation), encoding="utf-8")
        audio_control_output.parent.mkdir(parents=True, exist_ok=True)
        audio_control_output.write_text(json.dumps(audio_control, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        audio_control_doc.parent.mkdir(parents=True, exist_ok=True)
        audio_control_doc.write_text(audio_control_plan_markdown(audio_control), encoding="utf-8")
        audio_control_html_path.parent.mkdir(parents=True, exist_ok=True)
        audio_control_html_path.write_text(audio_control_plan_html(audio_control), encoding="utf-8")
        paired_work_order_output.parent.mkdir(parents=True, exist_ok=True)
        paired_work_order_output.write_text(json.dumps(paired_work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paired_work_order_doc.parent.mkdir(parents=True, exist_ok=True)
        paired_work_order_doc.write_text(paired_work_order_markdown(paired_work_order), encoding="utf-8")
        paired_work_order_html_path.parent.mkdir(parents=True, exist_ok=True)
        paired_work_order_html_path.write_text(paired_work_order_html(paired_work_order), encoding="utf-8")
        dashboard_output.parent.mkdir(parents=True, exist_ok=True)
        dashboard_output.write_text(json.dumps(dashboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        dashboard_doc.parent.mkdir(parents=True, exist_ok=True)
        dashboard_doc.write_text(dashboard_markdown(dashboard), encoding="utf-8")
        dashboard_html_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_html_path.write_text(dashboard_html(dashboard), encoding="utf-8")
    errors = validate_private_payload(payload)
    errors.extend(validate_release_focus_payload(focus_payload, site_dir))
    errors.extend(validate_control_auditions_payload(auditions_payload))
    errors.extend(validate_render_queue_payload(render_queue))
    errors.extend(validate_static_hosting_handoff_payload(hosting_handoff))
    errors.extend(validate_first_release_packet_payload(first_release))
    errors.extend(validate_posting_receipt_template_payload(posting_receipt))
    errors.extend(validate_release_cadence_payload(release_cadence))
    errors.extend(validate_edition_refinement_slate_payload(edition_slate))
    errors.extend(validate_cache_retention_plan_payload(retention_plan))
    errors.extend(validate_source_curation_plan_payload(source_curation))
    errors.extend(validate_audio_control_plan_payload(audio_control))
    errors.extend(validate_paired_work_order_payload(paired_work_order))
    errors.extend(validate_dashboard_payload(dashboard))
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    summary = (
        "overnight checkpoint ok: "
        f"{payload['creative_track']['edition_count']} editions; "
        f"{payload['creative_track']['post_exports']} posts; "
        f"{payload['creative_track']['visual_sketches']} sketches; "
        f"{len(payload['creative_track']['release_focus'])} focus candidates; "
        f"{auditions_payload['audition_count']} control auditions; "
        f"{render_queue['queue_count']} render candidates; "
        "hosting handoff refreshed; "
        "first-release packet refreshed; "
        "posting receipt template refreshed; "
        "release cadence plan refreshed; "
        "edition refinement slate refreshed; "
        "cache retention plan refreshed; "
        "source curation plan refreshed; "
        "audio control plan refreshed; "
        "paired work order refreshed; "
        "dashboard refreshed; "
        f"{len(payload['containment_track']['cleanup_candidates'])} cleanup candidates"
    )
    print(summary, file=sys.stderr if args.json else sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
