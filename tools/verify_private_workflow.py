#!/usr/bin/env python3
"""Verify private overnight workflow receipts without publishing them."""

from __future__ import annotations

import argparse
import html as html_lib
import json
from pathlib import Path
from typing import Any

import overnight_checkpoint


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_DIR = SCRIPT_DIR / "site"
DEFAULT_PACKAGE_DIR = SCRIPT_DIR / "packages" / "triptych-video-canon-site"
DEFAULT_CHECKPOINT = SCRIPT_DIR / "work" / "overnight-checkpoint.json"
DEFAULT_CHECKPOINT_DOC = SCRIPT_DIR / "work" / "overnight-checkpoint.md"
DEFAULT_FOCUS = SCRIPT_DIR / "work" / "release-focus.json"
DEFAULT_FOCUS_DOC = SCRIPT_DIR / "work" / "release-focus.md"
DEFAULT_FOCUS_HTML = SCRIPT_DIR / "work" / "release-focus.html"
DEFAULT_AUDITIONS = SCRIPT_DIR / "work" / "control-auditions.json"
DEFAULT_AUDITIONS_DOC = SCRIPT_DIR / "work" / "control-auditions.md"
DEFAULT_AUDITIONS_HTML = SCRIPT_DIR / "work" / "control-auditions.html"
DEFAULT_RENDER_QUEUE = SCRIPT_DIR / "work" / "next-render-queue.json"
DEFAULT_RENDER_QUEUE_DOC = SCRIPT_DIR / "work" / "next-render-queue.md"
DEFAULT_RENDER_QUEUE_HTML = SCRIPT_DIR / "work" / "next-render-queue.html"
DEFAULT_DASHBOARD = SCRIPT_DIR / "work" / "overnight-dashboard.json"
DEFAULT_DASHBOARD_DOC = SCRIPT_DIR / "work" / "overnight-dashboard.md"
DEFAULT_DASHBOARD_HTML = SCRIPT_DIR / "work" / "overnight-dashboard.html"
DEFAULT_HOSTING = SCRIPT_DIR / "work" / "static-hosting-handoff.json"
DEFAULT_HOSTING_DOC = SCRIPT_DIR / "work" / "static-hosting-handoff.md"
DEFAULT_HOSTING_HTML = SCRIPT_DIR / "work" / "static-hosting-handoff.html"
DEFAULT_FIRST_RELEASE = SCRIPT_DIR / "work" / "first-release-packet.json"
DEFAULT_FIRST_RELEASE_DOC = SCRIPT_DIR / "work" / "first-release-packet.md"
DEFAULT_FIRST_RELEASE_HTML = SCRIPT_DIR / "work" / "first-release-packet.html"
DEFAULT_POSTING_RECEIPT = SCRIPT_DIR / "work" / "posting-receipt-template.json"
DEFAULT_POSTING_RECEIPT_DOC = SCRIPT_DIR / "work" / "posting-receipt-template.md"
DEFAULT_POSTING_RECEIPT_HTML = SCRIPT_DIR / "work" / "posting-receipt-template.html"
DEFAULT_RELEASE_CADENCE = SCRIPT_DIR / "work" / "release-cadence-plan.json"
DEFAULT_RELEASE_CADENCE_DOC = SCRIPT_DIR / "work" / "release-cadence-plan.md"
DEFAULT_RELEASE_CADENCE_HTML = SCRIPT_DIR / "work" / "release-cadence-plan.html"
DEFAULT_EDITION_SLATE = SCRIPT_DIR / "work" / "edition-refinement-slate.json"
DEFAULT_EDITION_SLATE_DOC = SCRIPT_DIR / "work" / "edition-refinement-slate.md"
DEFAULT_EDITION_SLATE_HTML = SCRIPT_DIR / "work" / "edition-refinement-slate.html"
DEFAULT_RETENTION = SCRIPT_DIR / "work" / "cache-retention-plan.json"
DEFAULT_RETENTION_DOC = SCRIPT_DIR / "work" / "cache-retention-plan.md"
DEFAULT_RETENTION_HTML = SCRIPT_DIR / "work" / "cache-retention-plan.html"
DEFAULT_SOURCE_CURATION = SCRIPT_DIR / "work" / "source-curation-plan.json"
DEFAULT_SOURCE_CURATION_DOC = SCRIPT_DIR / "work" / "source-curation-plan.md"
DEFAULT_SOURCE_CURATION_HTML = SCRIPT_DIR / "work" / "source-curation-plan.html"
DEFAULT_AUDIO_CONTROL = SCRIPT_DIR / "work" / "audio-control-plan.json"
DEFAULT_AUDIO_CONTROL_DOC = SCRIPT_DIR / "work" / "audio-control-plan.md"
DEFAULT_AUDIO_CONTROL_HTML = SCRIPT_DIR / "work" / "audio-control-plan.html"
DEFAULT_PAIRED_WORK_ORDER = SCRIPT_DIR / "work" / "paired-work-order.json"
DEFAULT_PAIRED_WORK_ORDER_DOC = SCRIPT_DIR / "work" / "paired-work-order.md"
DEFAULT_PAIRED_WORK_ORDER_HTML = SCRIPT_DIR / "work" / "paired-work-order.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate private triptych workflow receipts under work/."
    )
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--checkpoint-doc", type=Path, default=DEFAULT_CHECKPOINT_DOC)
    parser.add_argument("--focus", type=Path, default=DEFAULT_FOCUS)
    parser.add_argument("--focus-doc", type=Path, default=DEFAULT_FOCUS_DOC)
    parser.add_argument("--focus-html", type=Path, default=DEFAULT_FOCUS_HTML)
    parser.add_argument("--auditions", type=Path, default=DEFAULT_AUDITIONS)
    parser.add_argument("--auditions-doc", type=Path, default=DEFAULT_AUDITIONS_DOC)
    parser.add_argument("--auditions-html", type=Path, default=DEFAULT_AUDITIONS_HTML)
    parser.add_argument("--render-queue", type=Path, default=DEFAULT_RENDER_QUEUE)
    parser.add_argument("--render-queue-doc", type=Path, default=DEFAULT_RENDER_QUEUE_DOC)
    parser.add_argument("--render-queue-html", type=Path, default=DEFAULT_RENDER_QUEUE_HTML)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--dashboard-doc", type=Path, default=DEFAULT_DASHBOARD_DOC)
    parser.add_argument("--dashboard-html", type=Path, default=DEFAULT_DASHBOARD_HTML)
    parser.add_argument("--hosting", type=Path, default=DEFAULT_HOSTING)
    parser.add_argument("--hosting-doc", type=Path, default=DEFAULT_HOSTING_DOC)
    parser.add_argument("--hosting-html", type=Path, default=DEFAULT_HOSTING_HTML)
    parser.add_argument("--first-release", type=Path, default=DEFAULT_FIRST_RELEASE)
    parser.add_argument("--first-release-doc", type=Path, default=DEFAULT_FIRST_RELEASE_DOC)
    parser.add_argument("--first-release-html", type=Path, default=DEFAULT_FIRST_RELEASE_HTML)
    parser.add_argument("--posting-receipt", type=Path, default=DEFAULT_POSTING_RECEIPT)
    parser.add_argument("--posting-receipt-doc", type=Path, default=DEFAULT_POSTING_RECEIPT_DOC)
    parser.add_argument("--posting-receipt-html", type=Path, default=DEFAULT_POSTING_RECEIPT_HTML)
    parser.add_argument("--release-cadence", type=Path, default=DEFAULT_RELEASE_CADENCE)
    parser.add_argument("--release-cadence-doc", type=Path, default=DEFAULT_RELEASE_CADENCE_DOC)
    parser.add_argument("--release-cadence-html", type=Path, default=DEFAULT_RELEASE_CADENCE_HTML)
    parser.add_argument("--edition-slate", type=Path, default=DEFAULT_EDITION_SLATE)
    parser.add_argument("--edition-slate-doc", type=Path, default=DEFAULT_EDITION_SLATE_DOC)
    parser.add_argument("--edition-slate-html", type=Path, default=DEFAULT_EDITION_SLATE_HTML)
    parser.add_argument("--retention", type=Path, default=DEFAULT_RETENTION)
    parser.add_argument("--retention-doc", type=Path, default=DEFAULT_RETENTION_DOC)
    parser.add_argument("--retention-html", type=Path, default=DEFAULT_RETENTION_HTML)
    parser.add_argument("--source-curation", type=Path, default=DEFAULT_SOURCE_CURATION)
    parser.add_argument("--source-curation-doc", type=Path, default=DEFAULT_SOURCE_CURATION_DOC)
    parser.add_argument("--source-curation-html", type=Path, default=DEFAULT_SOURCE_CURATION_HTML)
    parser.add_argument("--audio-control", type=Path, default=DEFAULT_AUDIO_CONTROL)
    parser.add_argument("--audio-control-doc", type=Path, default=DEFAULT_AUDIO_CONTROL_DOC)
    parser.add_argument("--audio-control-html", type=Path, default=DEFAULT_AUDIO_CONTROL_HTML)
    parser.add_argument("--paired-work-order", type=Path, default=DEFAULT_PAIRED_WORK_ORDER)
    parser.add_argument("--paired-work-order-doc", type=Path, default=DEFAULT_PAIRED_WORK_ORDER_DOC)
    parser.add_argument("--paired-work-order-html", type=Path, default=DEFAULT_PAIRED_WORK_ORDER_HTML)
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


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{path}: cannot read JSON: {error}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path}: JSON root must be an object")
        return {}
    return data


def local_ref_exists(ref: Any, errors: list[str], label: str) -> None:
    if not isinstance(ref, str) or not ref:
        errors.append(f"{label}: missing local ref")
        return
    ref_path = Path(ref.split("?", 1)[0])
    if ref_path.is_absolute() or ".." in ref_path.parts:
        errors.append(f"{label}: ref escapes incubator: {ref}")
        return
    target = (SCRIPT_DIR / ref_path).resolve()
    if not path_inside(target, SCRIPT_DIR):
        errors.append(f"{label}: ref escapes incubator: {ref}")
    elif not target.exists():
        errors.append(f"{label}: ref does not exist: {ref}")


def scan_private_tokens(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"{path}: cannot read: {error}")
            continue
        for token in overnight_checkpoint.PRIVATE_TEXT:
            if token in text:
                errors.append(f"{path}: contains private token {token!r}")


def validate_focus_links(focus: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("public_manifest", "release_board", "release_copy", "release_queue", "package_entrypoint"):
        local_ref_exists(focus.get(ref_key), errors, f"release-focus.{ref_key}")
    items = focus.get("focus")
    if not isinstance(items, list):
        errors.append("release-focus.focus must be a list")
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"release-focus.focus[{index}] must be an object")
            continue
        href = item.get("href")
        local_ref_exists(f"site/{href}" if isinstance(href, str) else href, errors, f"release-focus.focus[{index}].href")
        for ref_key in ("package_media_href", "release_board_href", "release_player_href"):
            local_ref_exists(item.get(ref_key), errors, f"release-focus.focus[{index}].{ref_key}")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"release-focus.focus[{index}].product_shop_gate must stay deferred")
        if not item.get("edit_prompt"):
            errors.append(f"release-focus.focus[{index}].edit_prompt must be present")


def validate_focus_html(focus: dict[str, Any], focus_html: Path, errors: list[str]) -> None:
    try:
        text = focus_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{focus_html}: cannot read: {error}")
        return
    if "Triptych Release Focus" not in text:
        errors.append(f"{focus_html}: missing Triptych Release Focus title")
    if "http://" in text or "https://" in text:
        errors.append(f"{focus_html}: must use package-local refs, not remote URLs")
    items = focus.get("focus")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        for ref_key in ("package_media_href", "release_board_href", "release_player_href"):
            ref = item.get(ref_key)
            if not isinstance(ref, str) or not ref:
                errors.append(f"{focus_html}: focus item {index} missing {ref_key}")
                continue
            expected = html_lib.escape(f"../{ref}", quote=True)
            if expected not in text:
                errors.append(f"{focus_html}: focus item {index} missing HTML ref {expected}")
        for text_key in ("work_title", "label", "edit_prompt", "caption_seed"):
            value = item.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{focus_html}: focus item {index} missing {text_key}")


def validate_audition_links(auditions: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("public_manifest", "playback_contract", "living_loop", "package_entrypoint"):
        local_ref_exists(auditions.get(ref_key), errors, f"control-auditions.{ref_key}")
    items = auditions.get("auditions")
    if not isinstance(items, list):
        errors.append("control-auditions.auditions must be a list")
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"control-auditions.auditions[{index}] must be an object")
            continue
        local_ref_exists(item.get("href"), errors, f"control-auditions.auditions[{index}].href")
        if item.get("media_generation") != "none":
            errors.append(f"control-auditions.auditions[{index}].media_generation must be none")
        if item.get("source_access") != "none":
            errors.append(f"control-auditions.auditions[{index}].source_access must be none")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"control-auditions.auditions[{index}].product_shop_gate must stay deferred")


def validate_auditions_html(auditions: dict[str, Any], auditions_html: Path, errors: list[str]) -> None:
    try:
        text = auditions_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{auditions_html}: cannot read: {error}")
        return
    if "Triptych Control Auditions" not in text:
        errors.append(f"{auditions_html}: missing Triptych Control Auditions title")
    if "http://" in text or "https://" in text:
        errors.append(f"{auditions_html}: must use package-local refs, not remote URLs")
    items = auditions.get("auditions")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        href = item.get("href")
        if isinstance(href, str):
            expected = html_lib.escape(f"../{href}", quote=True)
            if expected not in text:
                errors.append(f"{auditions_html}: audition item {index} missing HTML ref {expected}")
        for text_key in ("label", "work_title", "intent"):
            value = item.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{auditions_html}: audition item {index} missing {text_key}")


def validate_render_queue_links(render_queue: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("source_checkpoint", "source_release_focus", "source_control_auditions"):
        local_ref_exists(render_queue.get(ref_key), errors, f"next-render-queue.{ref_key}")
    items = render_queue.get("queue")
    if not isinstance(items, list):
        errors.append("next-render-queue.queue must be a list")
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"next-render-queue.queue[{index}] must be an object")
            continue
        for ref_key in ("project_manifest", "current_package_page", "expected_public_receipt", "expected_package_receipt"):
            local_ref_exists(item.get(ref_key), errors, f"next-render-queue.queue[{index}].{ref_key}")
        command = str(item.get("render_command") or "")
        dry_run = str(item.get("dry_run_command") or "")
        if "--photos-export-missing" in command or "--no-verify" in command or "--no-sync" in command:
            errors.append(f"next-render-queue.queue[{index}].render_command contains forbidden flag")
        if dry_run != f"{command} --dry-run":
            errors.append(f"next-render-queue.queue[{index}].dry_run_command must be render_command plus --dry-run")


def validate_render_queue_html(render_queue: dict[str, Any], render_queue_html: Path, errors: list[str]) -> None:
    try:
        text = render_queue_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{render_queue_html}: cannot read: {error}")
        return
    if "Triptych Next Render Queue" not in text:
        errors.append(f"{render_queue_html}: missing Triptych Next Render Queue title")
    if "http://" in text or "https://" in text:
        errors.append(f"{render_queue_html}: must use package-local refs, not remote URLs")
    items = render_queue.get("queue")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        href = item.get("current_package_page")
        if isinstance(href, str):
            expected = html_lib.escape(f"../{href}", quote=True)
            if expected not in text:
                errors.append(f"{render_queue_html}: queue item {index} missing package page ref {expected}")
        for text_key in ("work_title", "dry_run_command", "render_command", "why"):
            value = item.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{render_queue_html}: queue item {index} missing {text_key}")


def validate_hosting_links(hosting: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("source_checkpoint", "public_manifest", "package_manifest", "package_dir", "package_zip"):
        local_ref_exists(hosting.get(ref_key), errors, f"static-hosting-handoff.{ref_key}")
    for index, entry in enumerate(hosting.get("entrypoints") or [], start=1):
        if not isinstance(entry, dict):
            errors.append(f"static-hosting-handoff.entrypoints[{index}] must be an object")
            continue
        local_ref_exists(entry.get("href"), errors, f"static-hosting-handoff.entrypoints[{index}].href")
    never_upload = hosting.get("never_upload")
    if not isinstance(never_upload, list) or not {"work/", "samples/", "renders/"}.issubset(set(never_upload)):
        errors.append("static-hosting-handoff.never_upload must include work/, samples/, renders/")
    if hosting.get("requires_secrets") is not False:
        errors.append("static-hosting-handoff.requires_secrets must be false")


def validate_hosting_html(hosting: dict[str, Any], hosting_html: Path, errors: list[str]) -> None:
    try:
        text = hosting_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{hosting_html}: cannot read: {error}")
        return
    if "Triptych Static Hosting Handoff" not in text:
        errors.append(f"{hosting_html}: missing Triptych Static Hosting Handoff title")
    if "http://" in text or "https://" in text:
        errors.append(f"{hosting_html}: must use local refs, not remote URLs")
    for index, entry in enumerate(hosting.get("entrypoints") or [], start=1):
        if not isinstance(entry, dict):
            continue
        href = entry.get("href")
        if isinstance(href, str):
            expected = html_lib.escape(f"../{href}", quote=True)
            if expected not in text:
                errors.append(f"{hosting_html}: entrypoint {index} missing HTML ref {expected}")
        for text_key in ("label", "purpose"):
            value = entry.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{hosting_html}: entrypoint {index} missing {text_key}")
    for token in ("work/", "samples/", "renders/"):
        if html_lib.escape(token, quote=True) not in text:
            errors.append(f"{hosting_html}: missing never-upload token {token}")


def validate_first_release_links(first_release: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("source_checkpoint", "source_release_focus", "source_static_hosting_handoff"):
        local_ref_exists(first_release.get(ref_key), errors, f"first-release-packet.{ref_key}")
    selected = first_release.get("selected")
    if not isinstance(selected, dict):
        errors.append("first-release-packet.selected must be an object")
        selected = {}
    for ref_key in ("package_media_href", "release_board_href", "release_player_href"):
        local_ref_exists(selected.get(ref_key), errors, f"first-release-packet.selected.{ref_key}")
    if selected.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("first-release-packet.selected.product_shop_gate must stay deferred")
    packets = first_release.get("platform_packets")
    if not isinstance(packets, list):
        errors.append("first-release-packet.platform_packets must be a list")
        return
    for index, packet in enumerate(packets, start=1):
        if not isinstance(packet, dict):
            errors.append(f"first-release-packet.platform_packets[{index}] must be an object")
            continue
        local_ref_exists(packet.get("upload_ref"), errors, f"first-release-packet.platform_packets[{index}].upload_ref")
        if not packet.get("caption"):
            errors.append(f"first-release-packet.platform_packets[{index}].caption must be present")
        if not packet.get("alt_text"):
            errors.append(f"first-release-packet.platform_packets[{index}].alt_text must be present")
    for ref in first_release.get("package_entrypoints") or []:
        local_ref_exists(ref, errors, "first-release-packet.package_entrypoint")
    if first_release.get("media_generation") != "none":
        errors.append("first-release-packet.media_generation must be none")
    if first_release.get("source_access") != "none":
        errors.append("first-release-packet.source_access must be none")
    if first_release.get("deployment") != "manual posting only":
        errors.append("first-release-packet.deployment must be manual posting only")
    if first_release.get("requires_secrets") is not False:
        errors.append("first-release-packet.requires_secrets must be false")
    if first_release.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("first-release-packet.product_shop_gate must stay deferred")


def validate_first_release_html(first_release: dict[str, Any], first_release_html: Path, errors: list[str]) -> None:
    try:
        text = first_release_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{first_release_html}: cannot read: {error}")
        return
    if "Triptych First Release Packet" not in text:
        errors.append(f"{first_release_html}: missing Triptych First Release Packet title")
    if "http://" in text or "https://" in text:
        errors.append(f"{first_release_html}: must use local refs, not remote URLs")
    selected = first_release.get("selected")
    if isinstance(selected, dict):
        for ref_key in ("package_media_href", "release_board_href", "release_player_href"):
            ref = selected.get(ref_key)
            if isinstance(ref, str):
                expected = html_lib.escape(f"../{ref}", quote=True)
                if expected not in text:
                    errors.append(f"{first_release_html}: selected missing HTML ref {expected}")
        for text_key in ("work_title", "label", "why", "alt_text"):
            value = selected.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{first_release_html}: selected missing {text_key}")
    packets = first_release.get("platform_packets")
    if not isinstance(packets, list):
        return
    for index, packet in enumerate(packets, start=1):
        if not isinstance(packet, dict):
            continue
        upload_ref = packet.get("upload_ref")
        if isinstance(upload_ref, str):
            expected = html_lib.escape(f"../{upload_ref}", quote=True)
            if expected not in text:
                errors.append(f"{first_release_html}: platform packet {index} missing upload ref {expected}")
        for text_key in ("target", "caption", "alt_text"):
            value = packet.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{first_release_html}: platform packet {index} missing {text_key}")


def validate_posting_receipt_links(posting_receipt: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("source_first_release_packet", "source_static_hosting_handoff"):
        local_ref_exists(posting_receipt.get(ref_key), errors, f"posting-receipt-template.{ref_key}")
    selected = posting_receipt.get("selected")
    if not isinstance(selected, dict):
        errors.append("posting-receipt-template.selected must be an object")
        selected = {}
    for ref_key in ("package_media_href", "release_player_href", "release_board_href"):
        local_ref_exists(selected.get(ref_key), errors, f"posting-receipt-template.selected.{ref_key}")
    slots = posting_receipt.get("slots")
    if not isinstance(slots, list):
        errors.append("posting-receipt-template.slots must be a list")
        return
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            errors.append(f"posting-receipt-template.slots[{index}] must be an object")
            continue
        local_ref_exists(slot.get("upload_ref"), errors, f"posting-receipt-template.slots[{index}].upload_ref")
        local_ref_exists(slot.get("source_first_release_packet"), errors, f"posting-receipt-template.slots[{index}].source_first_release_packet")
        if slot.get("status") != "unposted":
            errors.append(f"posting-receipt-template.slots[{index}].status must be unposted")
        if slot.get("private_only") is not True:
            errors.append(f"posting-receipt-template.slots[{index}].private_only must be true")
        if slot.get("public_package_mutation") is not False:
            errors.append(f"posting-receipt-template.slots[{index}].public_package_mutation must be false")
        if slot.get("posted_url") or slot.get("posted_at") or slot.get("caption_used") or slot.get("notes"):
            errors.append(f"posting-receipt-template.slots[{index}] must not claim posted state")
        if slot.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"posting-receipt-template.slots[{index}].product_shop_gate must stay deferred")
    if posting_receipt.get("receipt_status") != "template-unposted":
        errors.append("posting-receipt-template.receipt_status must be template-unposted")
    if posting_receipt.get("posted_count") != 0:
        errors.append("posting-receipt-template.posted_count must be 0")
    if posting_receipt.get("media_generation") != "none":
        errors.append("posting-receipt-template.media_generation must be none")
    if posting_receipt.get("source_access") != "none":
        errors.append("posting-receipt-template.source_access must be none")
    if posting_receipt.get("deployment") != "none":
        errors.append("posting-receipt-template.deployment must be none")
    if posting_receipt.get("requires_secrets") is not False:
        errors.append("posting-receipt-template.requires_secrets must be false")
    if posting_receipt.get("public_package_mutation") is not False:
        errors.append("posting-receipt-template.public_package_mutation must be false")
    if posting_receipt.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("posting-receipt-template.product_shop_gate must stay deferred")


def validate_posting_receipt_html(posting_receipt: dict[str, Any], posting_receipt_html: Path, errors: list[str]) -> None:
    try:
        text = posting_receipt_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{posting_receipt_html}: cannot read: {error}")
        return
    if "Triptych Posting Receipt Template" not in text:
        errors.append(f"{posting_receipt_html}: missing Triptych Posting Receipt Template title")
    if "http://" in text or "https://" in text:
        errors.append(f"{posting_receipt_html}: must use local refs, not remote URLs")
    selected = posting_receipt.get("selected")
    if isinstance(selected, dict):
        for ref_key in ("package_media_href", "release_player_href", "release_board_href"):
            ref = selected.get(ref_key)
            if isinstance(ref, str):
                expected = html_lib.escape(f"../{ref}", quote=True)
                if expected not in text:
                    errors.append(f"{posting_receipt_html}: selected missing HTML ref {expected}")
        for text_key in ("work_title", "label"):
            value = selected.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{posting_receipt_html}: selected missing {text_key}")
    slots = posting_receipt.get("slots")
    if not isinstance(slots, list):
        return
    for index, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            continue
        upload_ref = slot.get("upload_ref")
        if isinstance(upload_ref, str):
            expected = html_lib.escape(f"../{upload_ref}", quote=True)
            if expected not in text:
                errors.append(f"{posting_receipt_html}: slot {index} missing upload ref {expected}")
        for text_key in ("target", "caption_variant", "alt_text", "status"):
            value = slot.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{posting_receipt_html}: slot {index} missing {text_key}")


def validate_release_cadence_links(release_cadence: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_release_focus",
        "source_first_release_packet",
        "source_posting_receipt_template",
        "source_next_render_queue",
    ):
        local_ref_exists(release_cadence.get(ref_key), errors, f"release-cadence-plan.{ref_key}")
    items = release_cadence.get("sequence")
    if not isinstance(items, list):
        errors.append("release-cadence-plan.sequence must be a list")
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"release-cadence-plan.sequence[{index}] must be an object")
            continue
        for ref_key in ("package_media_href", "release_player_href", "release_board_href", "render_queue_ref"):
            local_ref_exists(item.get(ref_key), errors, f"release-cadence-plan.sequence[{index}].{ref_key}")
        if item.get("receipt_template") == "work/posting-receipt-template.html":
            local_ref_exists(item.get("receipt_template"), errors, f"release-cadence-plan.sequence[{index}].receipt_template")
        if item.get("status") != "candidate-unposted":
            errors.append(f"release-cadence-plan.sequence[{index}].status must be candidate-unposted")
        if item.get("media_generation") != "none":
            errors.append(f"release-cadence-plan.sequence[{index}].media_generation must be none")
        if item.get("source_access") != "none":
            errors.append(f"release-cadence-plan.sequence[{index}].source_access must be none")
        if item.get("destructive_actions") != "none":
            errors.append(f"release-cadence-plan.sequence[{index}].destructive_actions must be none")
        if item.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"release-cadence-plan.sequence[{index}].product_shop_gate must stay deferred")
        if not item.get("primary_target"):
            errors.append(f"release-cadence-plan.sequence[{index}].primary_target must be present")
    if release_cadence.get("cadence_mode") != "ordered private sequence, not a calendar":
        errors.append("release-cadence-plan.cadence_mode must be ordered private sequence, not a calendar")
    if release_cadence.get("posting_receipt_status") != "template-unposted":
        errors.append("release-cadence-plan.posting_receipt_status must be template-unposted")
    if release_cadence.get("media_generation") != "none":
        errors.append("release-cadence-plan.media_generation must be none")
    if release_cadence.get("source_access") != "none":
        errors.append("release-cadence-plan.source_access must be none")
    if release_cadence.get("deployment") != "none":
        errors.append("release-cadence-plan.deployment must be none")
    if release_cadence.get("requires_secrets") is not False:
        errors.append("release-cadence-plan.requires_secrets must be false")
    if release_cadence.get("public_package_mutation") is not False:
        errors.append("release-cadence-plan.public_package_mutation must be false")
    if release_cadence.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("release-cadence-plan.product_shop_gate must stay deferred")


def validate_release_cadence_html(release_cadence: dict[str, Any], release_cadence_html: Path, errors: list[str]) -> None:
    try:
        text = release_cadence_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{release_cadence_html}: cannot read: {error}")
        return
    if "Triptych Release Cadence Plan" not in text:
        errors.append(f"{release_cadence_html}: missing Triptych Release Cadence Plan title")
    if "http://" in text or "https://" in text:
        errors.append(f"{release_cadence_html}: must use local refs, not remote URLs")
    items = release_cadence.get("sequence")
    if not isinstance(items, list):
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        for ref_key in ("package_media_href", "release_player_href", "release_board_href", "render_queue_ref"):
            ref = item.get(ref_key)
            if isinstance(ref, str):
                expected = html_lib.escape(f"../{ref}", quote=True)
                if expected not in text:
                    errors.append(f"{release_cadence_html}: sequence item {index} missing HTML ref {expected}")
        for text_key in ("work_title", "label", "primary_target", "caption_seed", "edit_prompt", "status"):
            value = item.get(text_key)
            if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{release_cadence_html}: sequence item {index} missing {text_key}")


def validate_edition_slate_links(edition_slate: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_control_auditions",
        "source_next_render_queue",
        "source_release_cadence",
        "preset_source",
    ):
        local_ref_exists(edition_slate.get(ref_key), errors, f"edition-refinement-slate.{ref_key}")
    rows = edition_slate.get("rows")
    if not isinstance(rows, list):
        errors.append("edition-refinement-slate.rows must be a list")
        return
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"edition-refinement-slate missing {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"edition-refinement-slate.rows[{index}] must be an object")
            continue
        if row.get("media_generation") != "none":
            errors.append(f"edition-refinement-slate.rows[{index}].media_generation must be none")
        if row.get("source_access") != "none":
            errors.append(f"edition-refinement-slate.rows[{index}].source_access must be none")
        if row.get("destructive_actions") != "none":
            errors.append(f"edition-refinement-slate.rows[{index}].destructive_actions must be none")
        if row.get("product_shop_gate") != "deferred until explicit product review":
            errors.append(f"edition-refinement-slate.rows[{index}].product_shop_gate must stay deferred")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("edition-refinement-slate porn row must stay gated-local-only")
        if row.get("edition") != "porn" and row.get("public_export_gate") not in {"public-package-ready", "not-public"}:
            errors.append(
                f"edition-refinement-slate.rows[{index}].public_export_gate must be public-package-ready or not-public"
            )
        package_page = row.get("package_page")
        if package_page:
            local_ref_exists(package_page, errors, f"edition-refinement-slate.rows[{index}].package_page")
        surface = row.get("next_private_surface")
        if isinstance(surface, str) and surface.startswith("work/"):
            local_ref_exists(surface, errors, f"edition-refinement-slate.rows[{index}].next_private_surface")
        for item_index, item in enumerate(row.get("cadence_items") or [], start=1):
            if isinstance(item, dict):
                local_ref_exists(
                    item.get("package_media_href"),
                    errors,
                    f"edition-refinement-slate.rows[{index}].cadence_items[{item_index}].package_media_href",
                )
    if edition_slate.get("media_generation") != "none":
        errors.append("edition-refinement-slate.media_generation must be none")
    if edition_slate.get("source_access") != "none":
        errors.append("edition-refinement-slate.source_access must be none")
    if edition_slate.get("deployment") != "none":
        errors.append("edition-refinement-slate.deployment must be none")
    if edition_slate.get("requires_secrets") is not False:
        errors.append("edition-refinement-slate.requires_secrets must be false")
    if edition_slate.get("public_package_mutation") is not False:
        errors.append("edition-refinement-slate.public_package_mutation must be false")
    if edition_slate.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("edition-refinement-slate.product_shop_gate must stay deferred")


def validate_edition_slate_html(edition_slate: dict[str, Any], edition_slate_html: Path, errors: list[str]) -> None:
    try:
        text = edition_slate_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{edition_slate_html}: cannot read: {error}")
        return
    if "Triptych Edition Refinement Slate" not in text:
        errors.append(f"{edition_slate_html}: missing Triptych Edition Refinement Slate title")
    if "http://" in text or "https://" in text:
        errors.append(f"{edition_slate_html}: must use local refs, not remote URLs")
    rows = edition_slate.get("rows")
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        package_page = row.get("package_page")
        if isinstance(package_page, str) and package_page:
            expected = html_lib.escape(f"../{package_page}", quote=True)
            if expected not in text:
                errors.append(f"{edition_slate_html}: row {index} missing package page {expected}")
        surface = row.get("next_private_surface")
        if isinstance(surface, str) and surface.startswith("work/"):
            expected = html_lib.escape(f"../{surface}", quote=True)
            if expected not in text:
                errors.append(f"{edition_slate_html}: row {index} missing private surface {expected}")
        for text_key in ("work_title", "edition", "public_export_gate", "recommended_next_action", "rationale"):
            value = row.get(text_key)
            if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{edition_slate_html}: row {index} missing {text_key}")


def validate_retention_links(retention: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_edition_refinement_slate",
        "source_release_cadence",
        "source_static_hosting_handoff",
    ):
        local_ref_exists(retention.get(ref_key), errors, f"cache-retention-plan.{ref_key}")
    for ref in retention.get("protected_private_surfaces") or []:
        local_ref_exists(ref, errors, "cache-retention-plan.protected_private_surface")
    for ref in retention.get("creative_proof_surfaces") or []:
        local_ref_exists(ref, errors, "cache-retention-plan.creative_proof_surface")
    rows = retention.get("rows")
    if not isinstance(rows, list):
        errors.append("cache-retention-plan.rows must be a list")
        return
    lanes = {str(row.get("lane") or "") for row in rows if isinstance(row, dict)}
    for required in ("work", "renders", "site", "packages", "samples"):
        if required not in lanes:
            errors.append(f"cache-retention-plan missing lane {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"cache-retention-plan.rows[{index}] must be an object")
            continue
        if row.get("manual_only") is not True:
            errors.append(f"cache-retention-plan.rows[{index}].manual_only must be true")
        if row.get("media_generation") != "none":
            errors.append(f"cache-retention-plan.rows[{index}].media_generation must be none")
        if row.get("source_access") != "none":
            errors.append(f"cache-retention-plan.rows[{index}].source_access must be none")
        if row.get("destructive_actions") != "none":
            errors.append(f"cache-retention-plan.rows[{index}].destructive_actions must be none")
        if row.get("lane") in {"work", "samples"} and not str(row.get("decision") or "").startswith("protect"):
            errors.append(f"cache-retention-plan.rows[{index}] must protect {row.get('lane')}/")
        commands = row.get("regenerate_with")
        if not isinstance(commands, list) or not commands:
            errors.append(f"cache-retention-plan.rows[{index}].regenerate_with must be non-empty")
    if retention.get("media_generation") != "none":
        errors.append("cache-retention-plan.media_generation must be none")
    if retention.get("source_access") != "none":
        errors.append("cache-retention-plan.source_access must be none")
    if retention.get("deployment") != "none":
        errors.append("cache-retention-plan.deployment must be none")
    if retention.get("requires_secrets") is not False:
        errors.append("cache-retention-plan.requires_secrets must be false")
    if retention.get("deletion_performed") is not False:
        errors.append("cache-retention-plan.deletion_performed must be false")
    if retention.get("public_package_mutation") is not False:
        errors.append("cache-retention-plan.public_package_mutation must be false")
    if retention.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("cache-retention-plan.product_shop_gate must stay deferred")


def validate_retention_html(retention: dict[str, Any], retention_html: Path, errors: list[str]) -> None:
    try:
        text = retention_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{retention_html}: cannot read: {error}")
        return
    if "Triptych Cache Retention Plan" not in text:
        errors.append(f"{retention_html}: missing Triptych Cache Retention Plan title")
    if "http://" in text or "https://" in text:
        errors.append(f"{retention_html}: must use local refs, not remote URLs")
    for forbidden in ("rm ", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"{retention_html}: contains destructive token {forbidden!r}")
    rows = retention.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            for text_key in ("lane", "decision", "human_size", "rationale", "creative_impact"):
                value = row.get(text_key)
                if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                    errors.append(f"{retention_html}: row {index} missing {text_key}")
    for ref in list(retention.get("protected_private_surfaces") or []) + list(retention.get("creative_proof_surfaces") or []):
        if isinstance(ref, str):
            expected = html_lib.escape(f"../{ref}", quote=True)
            if expected not in text:
                errors.append(f"{retention_html}: missing ref {expected}")


def validate_source_curation_links(source_curation: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_edition_refinement_slate",
        "source_cache_retention_plan",
        "preset_source",
    ):
        local_ref_exists(source_curation.get(ref_key), errors, f"source-curation-plan.{ref_key}")
    rows = source_curation.get("rows")
    if not isinstance(rows, list):
        errors.append("source-curation-plan.rows must be a list")
        return
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"source-curation-plan missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"source-curation-plan.rows[{index}] must be an object")
            continue
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"source-curation-plan.rows[{index}].{key} must be {expected}")
        if row.get("public_package_mutation") is not False:
            errors.append(f"source-curation-plan.rows[{index}].public_package_mutation must be false")
        if not row.get("raw_album"):
            errors.append(f"source-curation-plan.rows[{index}].raw_album must be present")
        if row.get("edition") == "ballerina" and row.get("model_album") == row.get("raw_album"):
            errors.append("source-curation-plan ballerina row must keep raw and model albums distinct")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("source-curation-plan porn row must stay gated-local-only")
        dry_run = str(row.get("dry_run_command") or "")
        if "--dry-run" not in dry_run:
            errors.append(f"source-curation-plan.rows[{index}].dry_run_command must include --dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"source-curation-plan.rows[{index}].dry_run_command must not export missing originals")
        surface = row.get("review_surface")
        if isinstance(surface, str) and surface.startswith("work/"):
            local_ref_exists(surface, errors, f"source-curation-plan.rows[{index}].review_surface")
    if source_curation.get("media_generation") != "none":
        errors.append("source-curation-plan.media_generation must be none")
    if source_curation.get("source_access") != "none":
        errors.append("source-curation-plan.source_access must be none")
    if source_curation.get("deployment") != "none":
        errors.append("source-curation-plan.deployment must be none")
    if source_curation.get("requires_secrets") is not False:
        errors.append("source-curation-plan.requires_secrets must be false")
    if source_curation.get("public_package_mutation") is not False:
        errors.append("source-curation-plan.public_package_mutation must be false")
    if source_curation.get("photos_library_mutation") is not False:
        errors.append("source-curation-plan.photos_library_mutation must be false")
    if source_curation.get("staging_mutation") is not False:
        errors.append("source-curation-plan.staging_mutation must be false")
    if source_curation.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("source-curation-plan.product_shop_gate must stay deferred")


def validate_source_curation_html(source_curation: dict[str, Any], source_curation_html: Path, errors: list[str]) -> None:
    try:
        text = source_curation_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{source_curation_html}: cannot read: {error}")
        return
    if "Triptych Source Curation Plan" not in text:
        errors.append(f"{source_curation_html}: missing Triptych Source Curation Plan title")
    if "http://" in text or "https://" in text:
        errors.append(f"{source_curation_html}: must use local refs, not remote URLs")
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"{source_curation_html}: contains forbidden token {forbidden!r}")
    rows = source_curation.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            for text_key in (
                "work_title",
                "edition",
                "raw_album",
                "model_album",
                "public_export_gate",
                "recommended_source_action",
                "rationale",
                "dry_run_command",
            ):
                value = row.get(text_key)
                if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                    errors.append(f"{source_curation_html}: row {index} missing {text_key}")
            surface = row.get("review_surface")
            if isinstance(surface, str):
                expected = html_lib.escape(f"../{surface}", quote=True)
                if expected not in text:
                    errors.append(f"{source_curation_html}: row {index} missing review surface {expected}")


def validate_audio_control_links(audio_control: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_public_sound_map",
        "source_playback_contract",
        "source_source_curation_plan",
        "preset_source",
    ):
        local_ref_exists(audio_control.get(ref_key), errors, f"audio-control-plan.{ref_key}")
    snapshot = audio_control.get("public_sound_snapshot")
    if not isinstance(snapshot, dict):
        errors.append("audio-control-plan.public_sound_snapshot must be an object")
    elif snapshot.get("browser_only_controls") != ["muted", "volume", "rate"]:
        errors.append("audio-control-plan.browser controls must be muted, volume, rate")
    rows = audio_control.get("rows")
    if not isinstance(rows, list):
        errors.append("audio-control-plan.rows must be a list")
        return
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"audio-control-plan missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"audio-control-plan.rows[{index}] must be an object")
            continue
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"audio-control-plan.rows[{index}].{key} must be {expected}")
        if row.get("source_audio_mutation") is not False:
            errors.append(f"audio-control-plan.rows[{index}].source_audio_mutation must be false")
        if row.get("public_package_mutation") is not False:
            errors.append(f"audio-control-plan.rows[{index}].public_package_mutation must be false")
        dry_run = str(row.get("dry_run_command") or "")
        if "--dry-run" not in dry_run or "--skip-import" not in dry_run:
            errors.append(f"audio-control-plan.rows[{index}].dry_run_command must be skip-import dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"audio-control-plan.rows[{index}].dry_run_command must not export missing originals")
        if row.get("edition") == "porn" and row.get("review_player_href"):
            errors.append("audio-control-plan porn row must not expose a public review player")
        if row.get("direction") not in {"forward", "reverse", "pingpong"}:
            errors.append(f"audio-control-plan.rows[{index}].direction is invalid")
        if not isinstance(row.get("control_presets"), list):
            errors.append(f"audio-control-plan.rows[{index}].control_presets must be a list")
        surface = row.get("review_surface")
        if isinstance(surface, str) and surface:
            local_ref_exists(surface, errors, f"audio-control-plan.rows[{index}].review_surface")
        href = row.get("review_player_href")
        if isinstance(href, str) and href:
            local_ref_exists(href, errors, f"audio-control-plan.rows[{index}].review_player_href")
    if audio_control.get("media_generation") != "none":
        errors.append("audio-control-plan.media_generation must be none")
    if audio_control.get("source_access") != "none":
        errors.append("audio-control-plan.source_access must be none")
    if audio_control.get("deployment") != "none":
        errors.append("audio-control-plan.deployment must be none")
    if audio_control.get("requires_secrets") is not False:
        errors.append("audio-control-plan.requires_secrets must be false")
    if audio_control.get("public_package_mutation") is not False:
        errors.append("audio-control-plan.public_package_mutation must be false")
    if audio_control.get("source_audio_mutation") is not False:
        errors.append("audio-control-plan.source_audio_mutation must be false")
    if audio_control.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("audio-control-plan.product_shop_gate must stay deferred")


def validate_audio_control_html(audio_control: dict[str, Any], audio_control_html: Path, errors: list[str]) -> None:
    try:
        text = audio_control_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{audio_control_html}: cannot read: {error}")
        return
    if "Triptych Audio Control Plan" not in text:
        errors.append(f"{audio_control_html}: missing Triptych Audio Control Plan title")
    if "http://" in text or "https://" in text:
        errors.append(f"{audio_control_html}: must use local refs, not remote URLs")
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"{audio_control_html}: contains forbidden token {forbidden!r}")
    rows = audio_control.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            for text_key in (
                "work_title",
                "edition",
                "audio_mode",
                "direction",
                "recommended_audio_action",
                "rationale",
                "dry_run_command",
            ):
                value = row.get(text_key)
                if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                    errors.append(f"{audio_control_html}: row {index} missing {text_key}")
            surface = row.get("review_surface")
            if isinstance(surface, str) and surface:
                expected = html_lib.escape(f"../{surface}", quote=True)
                if expected not in text:
                    errors.append(f"{audio_control_html}: row {index} missing review surface {expected}")
            href = row.get("review_player_href")
            if isinstance(href, str) and href:
                expected = html_lib.escape(f"../{href}", quote=True)
                if expected not in text:
                    errors.append(f"{audio_control_html}: row {index} missing player href {expected}")


def validate_paired_work_order_links(paired_work_order: dict[str, Any], errors: list[str]) -> None:
    for ref_key in (
        "source_checkpoint",
        "source_edition_refinement_slate",
        "source_source_curation_plan",
        "source_audio_control_plan",
        "source_cache_retention_plan",
        "source_next_render_queue",
        "preset_source",
        "first_next_surface",
        "first_containment_surface",
    ):
        local_ref_exists(paired_work_order.get(ref_key), errors, f"paired-work-order.{ref_key}")
    rows = paired_work_order.get("rows")
    if not isinstance(rows, list):
        errors.append("paired-work-order.rows must be a list")
        return
    slugs = {str(row.get("edition") or "") for row in rows if isinstance(row, dict)}
    for required in ("accidents", "ballerina", "noonlight", "glitche", "porn"):
        if required not in slugs:
            errors.append(f"paired-work-order missing edition {required}")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"paired-work-order.rows[{index}] must be an object")
            continue
        if row.get("paired_tracks") != ["creative", "containment"]:
            errors.append(f"paired-work-order.rows[{index}].paired_tracks must be creative + containment")
        for key, expected in (
            ("media_generation", "none"),
            ("source_access", "none"),
            ("deployment", "none"),
            ("destructive_actions", "none"),
            ("product_shop_gate", "deferred until explicit product review"),
        ):
            if row.get(key) != expected:
                errors.append(f"paired-work-order.rows[{index}].{key} must be {expected}")
        for key in (
            "requires_secrets",
            "public_package_mutation",
            "photos_library_mutation",
            "staging_mutation",
            "source_audio_mutation",
        ):
            if row.get(key) is not False:
                errors.append(f"paired-work-order.rows[{index}].{key} must be false")
        dry_run = str(row.get("dry_run_command") or "")
        if row.get("edition") != "porn" and ("--dry-run" not in dry_run or "--skip-import" not in dry_run):
            errors.append(f"paired-work-order.rows[{index}].dry_run_command must be skip-import dry-run")
        if "--photos-export-missing" in dry_run:
            errors.append(f"paired-work-order.rows[{index}].dry_run_command must not export missing originals")
        if row.get("edition") == "porn" and row.get("public_export_gate") != "gated-local-only":
            errors.append("paired-work-order porn row must stay gated-local-only")
        if row.get("edition") != "porn" and row.get("public_export_gate") not in {"public-package-ready", "not-public"}:
            errors.append(f"paired-work-order.rows[{index}].public_export_gate must be public-package-ready or not-public")
        if not row.get("creative_action") or not row.get("containment_action") or not row.get("text_edit_prompt"):
            errors.append(f"paired-work-order.rows[{index}] must include creative, containment, and text edit fields")
        for ref_key in ("creative_surface", "containment_surface", "source_surface", "audio_surface", "package_page"):
            ref = row.get(ref_key)
            if isinstance(ref, str) and ref:
                local_ref_exists(ref, errors, f"paired-work-order.rows[{index}].{ref_key}")
        commands = row.get("preflight_commands")
        if not isinstance(commands, list) or "python3 verify_private_workflow.py" not in commands:
            errors.append(f"paired-work-order.rows[{index}].preflight must include private workflow verification")
    if paired_work_order.get("media_generation") != "none":
        errors.append("paired-work-order.media_generation must be none")
    if paired_work_order.get("source_access") != "none":
        errors.append("paired-work-order.source_access must be none")
    if paired_work_order.get("deployment") != "none":
        errors.append("paired-work-order.deployment must be none")
    if paired_work_order.get("requires_secrets") is not False:
        errors.append("paired-work-order.requires_secrets must be false")
    if paired_work_order.get("public_package_mutation") is not False:
        errors.append("paired-work-order.public_package_mutation must be false")
    if paired_work_order.get("photos_library_mutation") is not False:
        errors.append("paired-work-order.photos_library_mutation must be false")
    if paired_work_order.get("staging_mutation") is not False:
        errors.append("paired-work-order.staging_mutation must be false")
    if paired_work_order.get("source_audio_mutation") is not False:
        errors.append("paired-work-order.source_audio_mutation must be false")
    if paired_work_order.get("product_shop_gate") != "deferred until explicit product review":
        errors.append("paired-work-order.product_shop_gate must stay deferred")


def validate_paired_work_order_html(
    paired_work_order: dict[str, Any],
    paired_work_order_html: Path,
    errors: list[str],
) -> None:
    try:
        text = paired_work_order_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{paired_work_order_html}: cannot read: {error}")
        return
    if "Triptych Paired Work Order" not in text:
        errors.append(f"{paired_work_order_html}: missing Triptych Paired Work Order title")
    if "http://" in text or "https://" in text:
        errors.append(f"{paired_work_order_html}: must use local refs, not remote URLs")
    for forbidden in ("--all-local", "--photos-export-missing", "rm -", "`rm", "trash ", "delete now"):
        if forbidden in text:
            errors.append(f"{paired_work_order_html}: contains forbidden token {forbidden!r}")
    rows = paired_work_order.get("rows")
    if isinstance(rows, list):
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            for text_key in (
                "work_title",
                "edition",
                "public_export_gate",
                "creative_action",
                "containment_action",
                "text_edit_prompt",
                "dry_run_command",
            ):
                value = row.get(text_key)
                if isinstance(value, str) and value and html_lib.escape(value, quote=True) not in text:
                    errors.append(f"{paired_work_order_html}: row {index} missing {text_key}")
            for ref_key in ("creative_surface", "containment_surface", "source_surface", "audio_surface", "package_page"):
                ref = row.get(ref_key)
                if isinstance(ref, str) and ref:
                    expected = html_lib.escape(f"../{ref}", quote=True)
                    if expected not in text:
                        errors.append(f"{paired_work_order_html}: row {index} missing {ref_key} {expected}")


def validate_dashboard_links(dashboard: dict[str, Any], errors: list[str]) -> None:
    for ref_key in ("source_checkpoint", "release_focus", "control_auditions", "next_render_queue"):
        local_ref_exists(dashboard.get(ref_key), errors, f"overnight-dashboard.{ref_key}")
    links = dashboard.get("links")
    if not isinstance(links, list):
        errors.append("overnight-dashboard.links must be a list")
        return
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            errors.append(f"overnight-dashboard.links[{index}] must be an object")
            continue
        local_ref_exists(link.get("href"), errors, f"overnight-dashboard.links[{index}].href")


def validate_dashboard_html(dashboard: dict[str, Any], dashboard_html: Path, errors: list[str]) -> None:
    try:
        text = dashboard_html.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{dashboard_html}: cannot read: {error}")
        return
    if "Triptych Overnight Dashboard" not in text:
        errors.append(f"{dashboard_html}: missing Triptych Overnight Dashboard title")
    if "http://" in text or "https://" in text:
        errors.append(f"{dashboard_html}: must use local refs, not remote URLs")
    links = dashboard.get("links")
    if not isinstance(links, list):
        return
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            continue
        href = link.get("href")
        if isinstance(href, str):
            expected = html_lib.escape(f"../{href}", quote=True)
            if expected not in text:
                errors.append(f"{dashboard_html}: dashboard link {index} missing HTML ref {expected}")
        for text_key in ("label", "purpose"):
            value = link.get(text_key)
            if isinstance(value, str) and html_lib.escape(value, quote=True) not in text:
                errors.append(f"{dashboard_html}: dashboard link {index} missing {text_key}")


def main() -> int:
    args = parse_args()
    site_dir = resolve_inside(args.site_dir, "site-dir")
    package_dir = resolve_inside(args.package_dir, "package-dir")
    checkpoint_path = resolve_inside(args.checkpoint, "checkpoint")
    checkpoint_doc = resolve_inside(args.checkpoint_doc, "checkpoint-doc")
    focus_path = resolve_inside(args.focus, "focus")
    focus_doc = resolve_inside(args.focus_doc, "focus-doc")
    focus_html = resolve_inside(args.focus_html, "focus-html")
    auditions_path = resolve_inside(args.auditions, "auditions")
    auditions_doc = resolve_inside(args.auditions_doc, "auditions-doc")
    auditions_html = resolve_inside(args.auditions_html, "auditions-html")
    render_queue_path = resolve_inside(args.render_queue, "render-queue")
    render_queue_doc = resolve_inside(args.render_queue_doc, "render-queue-doc")
    render_queue_html = resolve_inside(args.render_queue_html, "render-queue-html")
    dashboard_path = resolve_inside(args.dashboard, "dashboard")
    dashboard_doc = resolve_inside(args.dashboard_doc, "dashboard-doc")
    dashboard_html = resolve_inside(args.dashboard_html, "dashboard-html")
    hosting_path = resolve_inside(args.hosting, "hosting")
    hosting_doc = resolve_inside(args.hosting_doc, "hosting-doc")
    hosting_html = resolve_inside(args.hosting_html, "hosting-html")
    first_release_path = resolve_inside(args.first_release, "first-release")
    first_release_doc = resolve_inside(args.first_release_doc, "first-release-doc")
    first_release_html = resolve_inside(args.first_release_html, "first-release-html")
    posting_receipt_path = resolve_inside(args.posting_receipt, "posting-receipt")
    posting_receipt_doc = resolve_inside(args.posting_receipt_doc, "posting-receipt-doc")
    posting_receipt_html = resolve_inside(args.posting_receipt_html, "posting-receipt-html")
    release_cadence_path = resolve_inside(args.release_cadence, "release-cadence")
    release_cadence_doc = resolve_inside(args.release_cadence_doc, "release-cadence-doc")
    release_cadence_html = resolve_inside(args.release_cadence_html, "release-cadence-html")
    edition_slate_path = resolve_inside(args.edition_slate, "edition-slate")
    edition_slate_doc = resolve_inside(args.edition_slate_doc, "edition-slate-doc")
    edition_slate_html = resolve_inside(args.edition_slate_html, "edition-slate-html")
    retention_path = resolve_inside(args.retention, "retention")
    retention_doc = resolve_inside(args.retention_doc, "retention-doc")
    retention_html = resolve_inside(args.retention_html, "retention-html")
    source_curation_path = resolve_inside(args.source_curation, "source-curation")
    source_curation_doc = resolve_inside(args.source_curation_doc, "source-curation-doc")
    source_curation_html = resolve_inside(args.source_curation_html, "source-curation-html")
    audio_control_path = resolve_inside(args.audio_control, "audio-control")
    audio_control_doc = resolve_inside(args.audio_control_doc, "audio-control-doc")
    audio_control_html = resolve_inside(args.audio_control_html, "audio-control-html")
    paired_work_order_path = resolve_inside(args.paired_work_order, "paired-work-order")
    paired_work_order_doc = resolve_inside(args.paired_work_order_doc, "paired-work-order-doc")
    paired_work_order_html = resolve_inside(args.paired_work_order_html, "paired-work-order-html")
    errors: list[str] = []
    checkpoint = load_json(checkpoint_path, errors)
    focus = load_json(focus_path, errors)
    auditions = load_json(auditions_path, errors)
    render_queue = load_json(render_queue_path, errors)
    dashboard = load_json(dashboard_path, errors)
    hosting = load_json(hosting_path, errors)
    first_release = load_json(first_release_path, errors)
    posting_receipt = load_json(posting_receipt_path, errors)
    release_cadence = load_json(release_cadence_path, errors)
    edition_slate = load_json(edition_slate_path, errors)
    retention = load_json(retention_path, errors)
    source_curation = load_json(source_curation_path, errors)
    audio_control = load_json(audio_control_path, errors)
    paired_work_order = load_json(paired_work_order_path, errors)
    if checkpoint:
        errors.extend(overnight_checkpoint.validate_private_payload(checkpoint))
        expected_focus = overnight_checkpoint.release_focus_payload(checkpoint)
        if focus and focus.get("focus") != expected_focus.get("focus"):
            errors.append(f"{focus_path}: focus list must match checkpoint creative_track.release_focus")
        expected_auditions = overnight_checkpoint.control_auditions_payload(checkpoint)
        if auditions and auditions.get("auditions") != expected_auditions.get("auditions"):
            errors.append(f"{auditions_path}: auditions list must match checkpoint control_auditions_payload")
        expected_render_queue = overnight_checkpoint.render_queue_payload(checkpoint)
        if render_queue and render_queue.get("queue") != expected_render_queue.get("queue"):
            errors.append(f"{render_queue_path}: queue list must match checkpoint render_queue_payload")
        expected_hosting = overnight_checkpoint.static_hosting_handoff_payload(checkpoint)
        if hosting and hosting.get("entrypoints") != expected_hosting.get("entrypoints"):
            errors.append(f"{hosting_path}: entrypoints must match checkpoint static_hosting_handoff_payload")
        expected_first_release = overnight_checkpoint.first_release_packet_payload(checkpoint, focus or expected_focus, hosting or expected_hosting)
        if first_release and first_release.get("platform_packets") != expected_first_release.get("platform_packets"):
            errors.append(f"{first_release_path}: platform_packets must match checkpoint first_release_packet_payload")
        if first_release and first_release.get("selected") != expected_first_release.get("selected"):
            errors.append(f"{first_release_path}: selected must match checkpoint first_release_packet_payload")
        expected_posting_receipt = overnight_checkpoint.posting_receipt_template_payload(first_release or expected_first_release)
        if posting_receipt and posting_receipt.get("slots") != expected_posting_receipt.get("slots"):
            errors.append(f"{posting_receipt_path}: slots must match checkpoint posting_receipt_template_payload")
        if posting_receipt and posting_receipt.get("selected") != expected_posting_receipt.get("selected"):
            errors.append(f"{posting_receipt_path}: selected must match checkpoint posting_receipt_template_payload")
        expected_release_cadence = overnight_checkpoint.release_cadence_payload(
            checkpoint,
            focus or expected_focus,
            first_release or expected_first_release,
            posting_receipt or expected_posting_receipt,
            render_queue or expected_render_queue,
        )
        if release_cadence and release_cadence.get("sequence") != expected_release_cadence.get("sequence"):
            errors.append(f"{release_cadence_path}: sequence must match checkpoint release_cadence_payload")
        expected_edition_slate = overnight_checkpoint.edition_refinement_slate_payload(
            checkpoint,
            auditions or expected_auditions,
            render_queue or expected_render_queue,
            release_cadence or expected_release_cadence,
        )
        if edition_slate and edition_slate.get("rows") != expected_edition_slate.get("rows"):
            errors.append(f"{edition_slate_path}: rows must match checkpoint edition_refinement_slate_payload")
        expected_retention = overnight_checkpoint.cache_retention_plan_payload(
            checkpoint,
            edition_slate or expected_edition_slate,
            release_cadence or expected_release_cadence,
            hosting or expected_hosting,
        )
        if retention and retention.get("rows") != expected_retention.get("rows"):
            errors.append(f"{retention_path}: rows must match checkpoint cache_retention_plan_payload")
        expected_source_curation = overnight_checkpoint.source_curation_plan_payload(
            checkpoint,
            edition_slate or expected_edition_slate,
            retention or expected_retention,
        )
        if source_curation and source_curation.get("rows") != expected_source_curation.get("rows"):
            errors.append(f"{source_curation_path}: rows must match checkpoint source_curation_plan_payload")
        expected_audio_control = overnight_checkpoint.audio_control_plan_payload(
            checkpoint,
            source_curation or expected_source_curation,
        )
        if audio_control and audio_control.get("rows") != expected_audio_control.get("rows"):
            errors.append(f"{audio_control_path}: rows must match checkpoint audio_control_plan_payload")
        expected_paired_work_order = overnight_checkpoint.paired_work_order_payload(
            checkpoint,
            edition_slate or expected_edition_slate,
            source_curation or expected_source_curation,
            audio_control or expected_audio_control,
            retention or expected_retention,
            render_queue or expected_render_queue,
        )
        if paired_work_order and paired_work_order.get("rows") != expected_paired_work_order.get("rows"):
            errors.append(f"{paired_work_order_path}: rows must match checkpoint paired_work_order_payload")
        if (
            focus and auditions and render_queue and hosting and first_release and posting_receipt
            and release_cadence and edition_slate and retention and source_curation and audio_control
            and paired_work_order
        ):
            expected_dashboard = overnight_checkpoint.dashboard_payload(
                checkpoint,
                focus,
                auditions,
                render_queue,
                hosting,
                first_release,
                posting_receipt,
                release_cadence,
                edition_slate,
                retention,
                source_curation,
                audio_control,
                paired_work_order,
            )
            if dashboard and dashboard.get("links") != expected_dashboard.get("links"):
                errors.append(f"{dashboard_path}: dashboard links must match checkpoint dashboard_payload")
    if focus:
        errors.extend(overnight_checkpoint.validate_release_focus_payload(focus, site_dir))
        validate_focus_links(focus, errors)
        validate_focus_html(focus, focus_html, errors)
    if auditions:
        errors.extend(overnight_checkpoint.validate_control_auditions_payload(auditions))
        validate_audition_links(auditions, errors)
        validate_auditions_html(auditions, auditions_html, errors)
    if render_queue:
        errors.extend(overnight_checkpoint.validate_render_queue_payload(render_queue))
        validate_render_queue_links(render_queue, errors)
        validate_render_queue_html(render_queue, render_queue_html, errors)
    if hosting:
        errors.extend(overnight_checkpoint.validate_static_hosting_handoff_payload(hosting))
        validate_hosting_links(hosting, errors)
        validate_hosting_html(hosting, hosting_html, errors)
    if first_release:
        errors.extend(overnight_checkpoint.validate_first_release_packet_payload(first_release))
        validate_first_release_links(first_release, errors)
        validate_first_release_html(first_release, first_release_html, errors)
    if posting_receipt:
        errors.extend(overnight_checkpoint.validate_posting_receipt_template_payload(posting_receipt))
        validate_posting_receipt_links(posting_receipt, errors)
        validate_posting_receipt_html(posting_receipt, posting_receipt_html, errors)
    if release_cadence:
        errors.extend(overnight_checkpoint.validate_release_cadence_payload(release_cadence))
        validate_release_cadence_links(release_cadence, errors)
        validate_release_cadence_html(release_cadence, release_cadence_html, errors)
    if edition_slate:
        errors.extend(overnight_checkpoint.validate_edition_refinement_slate_payload(edition_slate))
        validate_edition_slate_links(edition_slate, errors)
        validate_edition_slate_html(edition_slate, edition_slate_html, errors)
    if retention:
        errors.extend(overnight_checkpoint.validate_cache_retention_plan_payload(retention))
        validate_retention_links(retention, errors)
        validate_retention_html(retention, retention_html, errors)
    if source_curation:
        errors.extend(overnight_checkpoint.validate_source_curation_plan_payload(source_curation))
        validate_source_curation_links(source_curation, errors)
        validate_source_curation_html(source_curation, source_curation_html, errors)
    if audio_control:
        errors.extend(overnight_checkpoint.validate_audio_control_plan_payload(audio_control))
        validate_audio_control_links(audio_control, errors)
        validate_audio_control_html(audio_control, audio_control_html, errors)
    if paired_work_order:
        errors.extend(overnight_checkpoint.validate_paired_work_order_payload(paired_work_order))
        validate_paired_work_order_links(paired_work_order, errors)
        validate_paired_work_order_html(paired_work_order, paired_work_order_html, errors)
    if dashboard:
        errors.extend(overnight_checkpoint.validate_dashboard_payload(dashboard))
        validate_dashboard_links(dashboard, errors)
        validate_dashboard_html(dashboard, dashboard_html, errors)
    local_ref_exists("packages/triptych-video-canon-site/package-manifest.json", errors, "package manifest")
    if not package_dir.exists():
        errors.append(f"{package_dir}: package dir missing")
    scan_private_tokens(
        [
            checkpoint_path,
            checkpoint_doc,
            focus_path,
            focus_doc,
            focus_html,
            auditions_path,
            auditions_doc,
            auditions_html,
            render_queue_path,
            render_queue_doc,
            render_queue_html,
            hosting_path,
            hosting_doc,
            hosting_html,
            first_release_path,
            first_release_doc,
            first_release_html,
            posting_receipt_path,
            posting_receipt_doc,
            posting_receipt_html,
            release_cadence_path,
            release_cadence_doc,
            release_cadence_html,
            edition_slate_path,
            edition_slate_doc,
            edition_slate_html,
            retention_path,
            retention_doc,
            retention_html,
            source_curation_path,
            source_curation_doc,
            source_curation_html,
            audio_control_path,
            audio_control_doc,
            audio_control_html,
            paired_work_order_path,
            paired_work_order_doc,
            paired_work_order_html,
            dashboard_path,
            dashboard_doc,
            dashboard_html,
        ],
        errors,
    )
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    focus_count = focus.get("focus_count", 0)
    audition_count = auditions.get("audition_count", 0)
    render_count = render_queue.get("queue_count", 0)
    hosting_entries = len(hosting.get("entrypoints", [])) if isinstance(hosting.get("entrypoints"), list) else 0
    first_release_packets = first_release.get("platform_packet_count", 0)
    posting_receipt_slots = posting_receipt.get("slot_count", 0)
    release_cadence_items = release_cadence.get("cadence_count", 0)
    edition_slate_rows = edition_slate.get("edition_count", 0)
    retention_lanes = retention.get("row_count", 0)
    source_curation_rows = source_curation.get("row_count", 0)
    audio_control_rows = audio_control.get("row_count", 0)
    paired_work_order_rows = paired_work_order.get("row_count", 0)
    dashboard_links = len(dashboard.get("links", [])) if isinstance(dashboard.get("links"), list) else 0
    print(
        f"private workflow ok: {focus_count} focus items; "
        f"{audition_count} control auditions; {render_count} render candidates; "
        f"{hosting_entries} hosting entrypoints; {first_release_packets} first-release platform packets; "
        f"{posting_receipt_slots} posting receipt slots; {release_cadence_items} cadence items; "
        f"{edition_slate_rows} edition slate rows; {retention_lanes} retention lanes; "
        f"{source_curation_rows} source curation rows; "
        f"{audio_control_rows} audio control rows; "
        f"{paired_work_order_rows} paired work-order rows; "
        f"{dashboard_links} dashboard links; "
        f"package {package_dir.name}; receipts private"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
