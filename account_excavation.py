#!/usr/bin/env python3
"""Build local account-excavation receipts for the Triptych-first launch.

The receipt stays under ignored work/. It records paths, media facts, and
conversation indexes without copying source media or writing raw transcripts
into tracked files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parent
WORKTREE_ROOT = ROOT.parents[1]
WORKSPACE_HOME = WORKTREE_ROOT.parents[3]
DEFAULT_OUT_DIR = ROOT / "work" / "account-excavation-20260706"
CHATGPT_APP_SUPPORT = Path.home() / "Library/Application Support/com.openai.chat"
CCE_SRC = Path.home() / "Workspace/organvm-i-theoria/conversation-corpus-engine/src"
SESSION_META_ROOT = Path.home() / "Workspace/session-meta"
SESSION_META_MANIFEST = SESSION_META_ROOT / "ingest/manifest.jsonl"
CHATGPT_ARCHIVE_ROOT = SESSION_META_ROOT / "data/session-transcripts/chatgpt"

KEYWORDS = (
    "TripTicks",
    "Tryptich",
    "Triptych",
    "tryptich",
    "triptych",
    "Narcissus",
    "professional dashboard",
    "4444j99",
    "4444jj999",
    "Howard Stern",
    "mocap",
    "motion capture",
    "podcast",
    "audio visual",
    "audiovisual",
    "Instagram",
    "god's ears",
    "gods ears",
    "glyph cascade",
    "visual form",
)

LOW_SIGNAL_KEYWORDS = {"4444j99", "Instagram", "podcast"}

MEDIA_TARGETS = (
    {
        "id": "tripticks_download",
        "role": "User-referenced TripTicks source or near-source video.",
        "path": Path.home() / "Downloads/TripTicks.mp4",
    },
    {
        "id": "gods_ears_second_draft",
        "role": "User-referenced short film outside the current Triptych lane.",
        "path": Path.home() / "Downloads/2020 04 26   god's ears   second draft.mp4",
    },
    {
        "id": "story_triptych_download",
        "role": "Existing rendered Story-scale Triptych output in Downloads.",
        "path": Path.home() / "Downloads/story-triptych.mp4",
    },
)

DIRECTORY_TARGETS = (
    {
        "id": "glyph_cascade_desktop_pack",
        "role": "Desktop pack visible in the user screenshot.",
        "path": Path.home() / "Desktop/glyph-cascade-ig-2026-06-29",
    },
)

SEARCH_ROOTS = (
    {
        "id": "session_meta",
        "path": SESSION_META_ROOT,
        "max_hits": 80,
    },
    {
        "id": "portvs_triptych_incubator",
        "path": ROOT,
        "max_hits": 120,
    },
    {
        "id": "organvm_runtime_persona_plans",
        "path": Path.home() / "Workspace/organvm/claude-runtime-state/plans",
        "max_hits": 120,
    },
    {
        "id": "organvm_portfolio",
        "path": Path.home() / "Workspace/organvm/portfolio",
        "max_hits": 120,
    },
    {
        "id": "private_portfolio",
        "path": Path.home() / "Workspace/4444J99/portfolio",
        "max_hits": 120,
    },
    {
        "id": "distribution_strategy",
        "path": Path.home() / "Workspace/organvm/distribution-strategy",
        "max_hits": 80,
    },
    {
        "id": "media_ark",
        "path": Path.home() / "Workspace/4444J99/media-ark",
        "max_hits": 80,
    },
    {
        "id": "claude_projects",
        "path": Path.home() / ".claude/projects",
        "max_hits": 120,
    },
    {
        "id": "codex_sessions_june_28",
        "path": Path.home() / ".codex/sessions/2026/06/28",
        "max_hits": 80,
    },
    {
        "id": "codex_sessions_june_29",
        "path": Path.home() / ".codex/sessions/2026/06/29",
        "max_hits": 100,
    },
    {
        "id": "codex_sessions_july",
        "path": Path.home() / ".codex/sessions/2026/07",
        "max_hits": 120,
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_probe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    if not Path(ffprobe).exists():
        return {"status": "skipped", "reason": "ffprobe not found"}
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-print_format",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return {"status": "failed", "error": result.stderr.strip()}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"invalid ffprobe JSON: {exc}"}

    video = next(
        (
            stream
            for stream in payload.get("streams", [])
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        {},
    )
    audio = next(
        (
            stream
            for stream in payload.get("streams", [])
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        {},
    )
    fmt = payload.get("format") or {}
    return {
        "status": "ok",
        "duration_seconds": as_float(fmt.get("duration")),
        "bit_rate": as_int(fmt.get("bit_rate")),
        "format_name": fmt.get("format_name"),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "avg_frame_rate": video.get("avg_frame_rate"),
        },
        "audio": {
            "present": bool(audio),
            "codec": audio.get("codec_name"),
            "channels": audio.get("channels"),
            "sample_rate": audio.get("sample_rate"),
        },
    }


def as_float(value: object) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def file_record(path: Path, *, role: str | None = None, hash_bytes: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if role:
        record["role"] = role
    if not path.exists():
        return record

    stat = path.stat()
    record.update(
        {
            "kind": "directory" if path.is_dir() else "file",
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )
    if path.is_file():
        if hash_bytes:
            record["sha256"] = sha256_file(path)
        if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".mkv"}:
            record["media_probe"] = media_probe(path)
    return record


def directory_record(target: dict[str, Any], *, max_entries: int, hash_bytes: bool) -> dict[str, Any]:
    path = target["path"]
    record = file_record(path, role=target.get("role"), hash_bytes=False)
    if not path.exists() or not path.is_dir():
        return record

    entries = sorted([item for item in path.rglob("*") if item.is_file()])
    record["file_count"] = len(entries)
    record["entries"] = [
        file_record(item, hash_bytes=hash_bytes and item.stat().st_size <= 200 * 1024 * 1024)
        for item in entries[:max_entries]
    ]
    record["entries_truncated"] = len(entries) > max_entries
    return record


def rg_pattern() -> str:
    return "|".join(re.escape(keyword) for keyword in KEYWORDS)


def matched_keywords(path: Path) -> dict[str, Any]:
    found: set[str] = set()
    line_numbers: list[int] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for idx, line in enumerate(handle, start=1):
                line_lower = line.lower()
                for keyword in KEYWORDS:
                    if keyword.lower() in line_lower:
                        found.add(keyword)
                if found and len(line_numbers) < 8 and any(
                    keyword.lower() in line_lower for keyword in KEYWORDS
                ):
                    line_numbers.append(idx)
    except OSError:
        pass
    return {"keywords": sorted(found, key=str.lower), "line_numbers": line_numbers}


def run_rg(root: Path, *, max_hits: int) -> dict[str, Any]:
    if not root.exists():
        return {"path": str(root), "exists": False, "matches": []}

    command = [
        "rg",
        "--ignore-case",
        "--files-with-matches",
        "--glob",
        "!node_modules",
        "--glob",
        "!.git",
        "--glob",
        "!__pycache__",
        rg_pattern(),
        str(root),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return {"path": str(root), "exists": True, "status": "timeout", "matches": []}

    if result.returncode not in {0, 1}:
        return {
            "path": str(root),
            "exists": True,
            "status": "failed",
            "error": result.stderr.strip(),
            "matches": [],
        }

    paths = [Path(line) for line in result.stdout.splitlines() if line]
    matches = []
    for match_path in paths[:max_hits]:
        info = matched_keywords(match_path)
        matches.append(
            {
                "path": str(match_path),
                "keywords": info["keywords"],
                "line_numbers": info["line_numbers"],
            }
        )
    return {
        "path": str(root),
        "exists": True,
        "status": "ok",
        "match_count": len(paths),
        "matches": matches,
        "matches_truncated": len(paths) > max_hits,
    }


def local_chatgpt_project_ids() -> list[str]:
    if not CHATGPT_APP_SUPPORT.exists():
        return []
    return sorted(
        {
            path.name.replace("project-", "", 1)
            for path in CHATGPT_APP_SUPPORT.glob("project-g-p-*")
            if path.is_dir()
        }
    )


def keyword_hits(text: str) -> list[str]:
    text_lower = text.lower()
    return sorted(
        {keyword for keyword in KEYWORDS if keyword.lower() in text_lower},
        key=str.lower,
    )


def high_signal_keywords(keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword not in LOW_SIGNAL_KEYWORDS]


def chatgpt_local_method_receipt() -> list[dict[str, Any]]:
    methods = [
        {
            "id": "session_meta_chatgpt_adapter",
            "path": SESSION_META_ROOT / "ingest/adapters/chatgpt.py",
            "purpose": "Parses native ChatGPT export JSON mapping trees into message atoms.",
        },
        {
            "id": "cce_chatgpt_export_importer",
            "path": CCE_SRC / "conversation_corpus_engine/import_chatgpt_export_corpus.py",
            "purpose": "Imports a native ChatGPT export bundle into the conversation corpus.",
        },
        {
            "id": "cce_chatgpt_local_session_importer",
            "path": CCE_SRC / "conversation_corpus_engine/import_chatgpt_local_session_corpus.py",
            "purpose": "Uses the desktop session cookie jar to fetch and import a local-session bundle.",
        },
        {
            "id": "cce_chatgpt_local_session_client",
            "path": CCE_SRC / "conversation_corpus_engine/chatgpt_local_session.py",
            "purpose": "Discovers ChatGPT desktop auth/session state and backend conversation routes.",
        },
        {
            "id": "chatgpt_exporter_to_bundle",
            "path": Path.home()
            / "Workspace/organvm-i-theoria/conversation-corpus-engine/scripts/chatgpt_exporter_to_bundle.py",
            "purpose": "Converts ChatGPT-exporter output into the bundle shape used by the corpus importer.",
        },
    ]
    return [
        {
            "id": method["id"],
            "path": str(method["path"]),
            "exists": method["path"].exists(),
            "purpose": method["purpose"],
        }
        for method in methods
    ]


def chatgpt_archive_manifest_index(*, max_entries: int = 80) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "archive_root": str(CHATGPT_ARCHIVE_ROOT),
        "archive_root_exists": CHATGPT_ARCHIVE_ROOT.exists(),
        "manifest": str(SESSION_META_MANIFEST),
        "manifest_exists": SESSION_META_MANIFEST.exists(),
        "local_methods": chatgpt_local_method_receipt(),
        "manifest_entries": 0,
        "total_bytes": 0,
        "by_lane": {},
        "by_kind": {},
        "by_format": {},
        "important_entries": [],
    }
    if not SESSION_META_MANIFEST.exists():
        receipt["status"] = "manifest-missing"
        return receipt

    important_patterns = (
        "conversations.json",
        "conversations.json.gz",
        "conversations-",
        "corpus/",
        "threads-index",
        "pairs-index",
        "action-ledger",
        "unresolved-ledger",
    )
    latest_mtime = ""
    with SESSION_META_MANIFEST.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rel_path = str(row.get("path") or "")
            if row.get("source") != "chatgpt" and not rel_path.startswith(
                "data/session-transcripts/chatgpt/"
            ):
                continue
            receipt["manifest_entries"] += 1
            size = as_int(row.get("bytes")) or 0
            receipt["total_bytes"] += size
            lane = "root"
            parts = Path(rel_path).parts
            try:
                idx = parts.index("chatgpt")
                if len(parts) > idx + 1:
                    lane = parts[idx + 1]
            except ValueError:
                pass
            receipt["by_lane"][lane] = receipt["by_lane"].get(lane, 0) + 1
            kind = str(row.get("klass") or "unknown")
            fmt = str(row.get("fmt") or "unknown")
            receipt["by_kind"][kind] = receipt["by_kind"].get(kind, 0) + 1
            receipt["by_format"][fmt] = receipt["by_format"].get(fmt, 0) + 1
            mtime = str(row.get("mtime") or "")
            if mtime > latest_mtime:
                latest_mtime = mtime
            if len(receipt["important_entries"]) < max_entries and any(
                pattern in rel_path for pattern in important_patterns
            ):
                actual_path = SESSION_META_ROOT / rel_path
                receipt["important_entries"].append(
                    {
                        "path": rel_path,
                        "bytes": size,
                        "fmt": fmt,
                        "kind": kind,
                        "sha256": row.get("sha256"),
                        "exists_in_checkout": actual_path.exists(),
                    }
                )

    receipt["latest_mtime"] = latest_mtime or None
    receipt["status"] = "ok"
    receipt["manifest_only_in_this_checkout"] = (
        receipt["manifest_entries"] > 0 and not CHATGPT_ARCHIVE_ROOT.exists()
    )
    return receipt


def scan_chatgpt_details(
    *,
    conversations: list[dict[str, Any]],
    session: Any,
    fetch_json: Any,
    chatgpt_host: str,
    detail_limit: int,
) -> dict[str, int]:
    details_scanned = 0
    detail_matches = 0
    detail_high_signal_matches = 0
    detail_failures = 0
    rate_limited = 0
    detail_candidates = sorted(
        conversations,
        key=lambda item: (
            bool(item.get("title_high_signal_keywords")),
            bool(item.get("title_keyword_match")),
            str(item.get("update_time") or item.get("create_time") or ""),
        ),
        reverse=True,
    )
    for item in conversations:
        item["detail_scan_status"] = "not-scanned"
    for item in detail_candidates[:detail_limit]:
        conversation_id = item.get("id")
        if not conversation_id:
            continue
        try:
            detail = fetch_json(
                session,
                f"https://{chatgpt_host}/backend-api/conversation/{conversation_id}",
            )
        except Exception as exc:
            error = str(exc)
            detail_failures += 1
            if "429" in error or "Too many" in error:
                rate_limited += 1
            item["detail_scan_status"] = "failed"
            item["detail_scan_error"] = error
            continue
        details_scanned += 1
        serialized = json.dumps(detail, ensure_ascii=False)
        detail_keywords = keyword_hits(serialized)
        detail_high_signal = high_signal_keywords(detail_keywords)
        item["detail_scan_status"] = "ok"
        item["detail_keywords"] = detail_keywords
        item["detail_high_signal_keywords"] = detail_high_signal
        item["detail_keyword_match"] = bool(detail_keywords)
        item["detail_high_signal_match"] = bool(detail_high_signal)
        if detail_keywords:
            detail_matches += 1
        if detail_high_signal:
            detail_high_signal_matches += 1
    return {
        "scanned": details_scanned,
        "matched": detail_matches,
        "high_signal_matched": detail_high_signal_matches,
        "failed": detail_failures,
        "rate_limited": rate_limited,
    }


def chatgpt_global_conversation_index(
    *,
    session: Any,
    fetch_json: Any,
    chatgpt_host: str,
    pages: int,
    limit: int,
    detail_scan: bool,
    detail_limit: int,
) -> dict[str, Any]:
    conversations: list[dict[str, Any]] = []
    errors: list[str] = []
    for page_num in range(max(1, pages)):
        offset = page_num * limit
        url = (
            f"https://{chatgpt_host}/backend-api/conversations?"
            f"{urlencode({'offset': offset, 'limit': limit, 'is_archived': 'false'})}"
        )
        try:
            data = fetch_json(session, url)
        except Exception as exc:
            errors.append(str(exc))
            break
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            errors.append("unexpected items shape")
            break
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            title_keywords = keyword_hits(title)
            conversations.append(
                {
                    "id": item.get("id") or item.get("conversation_id"),
                    "title": title,
                    "create_time": item.get("create_time"),
                    "update_time": item.get("update_time"),
                    "title_keywords": title_keywords,
                    "title_high_signal_keywords": high_signal_keywords(title_keywords),
                    "title_keyword_match": bool(title_keywords),
                }
            )

    detail_stats = {"enabled": detail_scan, "limit": detail_limit, "scanned": 0, "matched": 0}
    if detail_scan and conversations:
        detail_counts = scan_chatgpt_details(
            conversations=conversations,
            session=session,
            fetch_json=fetch_json,
            chatgpt_host=chatgpt_host,
            detail_limit=detail_limit,
        )
        detail_stats.update(detail_counts)

    matched = [
        item
        for item in conversations
        if item.get("title_keyword_match") or item.get("detail_keyword_match")
    ]
    high_signal_matched = [
        item
        for item in conversations
        if item.get("title_high_signal_keywords") or item.get("detail_high_signal_keywords")
    ]
    return {
        "status": "ok" if not errors else "partial",
        "errors": errors,
        "conversation_count_indexed": len(conversations),
        "keyword_match_count": len(matched),
        "high_signal_match_count": len(high_signal_matched),
        "keyword_matches": matched[:40],
        "high_signal_matches": high_signal_matched[:40],
        "detail_scan": detail_stats,
    }


def chatgpt_conversation_index(
    *,
    pages: int,
    limit: int,
    detail_scan: bool,
    detail_limit: int,
    global_pages: int,
    global_limit: int,
    global_detail_limit: int,
) -> dict[str, Any]:
    project_ids = local_chatgpt_project_ids()
    receipt: dict[str, Any] = {
        "app_support": str(CHATGPT_APP_SUPPORT),
        "project_count": len(project_ids),
        "projects": [],
    }
    if not project_ids:
        receipt["status"] = "no-local-project-cache"
        return receipt

    if str(CCE_SRC) not in sys.path and CCE_SRC.exists():
        sys.path.insert(0, str(CCE_SRC))
    try:
        from conversation_corpus_engine.chatgpt_local_session import (  # type: ignore
            CHATGPT_HOST,
            build_chatgpt_session,
            fetch_json,
        )
    except Exception as exc:  # pragma: no cover - local integration guard
        receipt["status"] = "failed"
        receipt["error"] = f"conversation-corpus-engine unavailable: {exc}"
        return receipt

    try:
        session = build_chatgpt_session()
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"ChatGPT session unavailable: {exc}"
        return receipt

    project_rows: list[dict[str, Any]] = []
    for project_id in project_ids:
        conversations: list[dict[str, Any]] = []
        cursor: str | None = None
        error: str | None = None
        for page_num in range(max(1, pages)):
            params = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            elif page_num == 0:
                params["offset"] = 0
            url = (
                f"https://{CHATGPT_HOST}/backend-api/gizmos/{project_id}/conversations?"
                f"{urlencode(params)}"
            )
            try:
                data = fetch_json(session, url)
            except Exception as exc:
                error = str(exc)
                break
            items = data.get("items") if isinstance(data, dict) else []
            if not isinstance(items, list):
                error = "unexpected items shape"
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "")
                title_keywords = keyword_hits(title)
                title_high_signal = high_signal_keywords(title_keywords)
                conversations.append(
                    {
                        "id": item.get("id") or item.get("conversation_id"),
                        "title": title,
                        "create_time": item.get("create_time"),
                        "update_time": item.get("update_time"),
                        "title_keywords": title_keywords,
                        "title_high_signal_keywords": title_high_signal,
                        "title_keyword_match": bool(title_keywords),
                    }
                )
            cursor_value = data.get("cursor") if isinstance(data, dict) else None
            cursor = cursor_value if isinstance(cursor_value, str) and cursor_value else None
            if not cursor:
                break

        project_rows.append(
            {
                "project_id": project_id,
                "conversations": conversations,
                "has_more_cursor": bool(cursor),
                "error": error,
            }
        )

    if detail_scan:
        all_project_conversations = [
            item for row in project_rows for item in row["conversations"]
        ]
        detail_counts = scan_chatgpt_details(
            conversations=all_project_conversations,
            session=session,
            fetch_json=fetch_json,
            chatgpt_host=CHATGPT_HOST,
            detail_limit=detail_limit,
        )
    else:
        detail_counts = {"scanned": 0, "matched": 0, "high_signal_matched": 0}

    for row in project_rows:
        conversations = row["conversations"]
        matched = [
            item
            for item in conversations
            if item.get("title_keyword_match") or item.get("detail_keyword_match")
        ]
        title_matches = [item for item in conversations if item.get("title_keyword_match")]
        scanned_matches = [item for item in conversations if item.get("detail_keyword_match")]
        receipt["projects"].append(
            {
                "project_id": row["project_id"],
                "conversation_count_indexed": len(conversations),
                "title_keyword_match_count": len(title_matches),
                "detail_keyword_match_count": len(scanned_matches),
                "keyword_match_count": len(matched),
                "high_signal_match_count": len(
                    [
                        item
                        for item in conversations
                        if item.get("title_high_signal_keywords")
                        or item.get("detail_high_signal_keywords")
                    ]
                ),
                "keyword_matches": matched[:20],
                "has_more_cursor": row["has_more_cursor"],
                "error": row["error"],
            }
        )
    receipt["status"] = "ok"
    receipt["detail_scan"] = {
        "enabled": detail_scan,
        "limit": detail_limit,
        "scanned": detail_counts["scanned"],
        "matched": detail_counts["matched"],
        "high_signal_matched": detail_counts["high_signal_matched"],
        "failed": detail_counts.get("failed", 0),
        "rate_limited": detail_counts.get("rate_limited", 0),
    }
    receipt["global_conversations"] = chatgpt_global_conversation_index(
        session=session,
        fetch_json=fetch_json,
        chatgpt_host=CHATGPT_HOST,
        pages=global_pages,
        limit=global_limit,
        detail_scan=detail_scan,
        detail_limit=global_detail_limit,
    )
    return receipt


def write_markdown_summary(path: Path, receipt: dict[str, Any]) -> None:
    media = receipt["media_targets"]
    directories = receipt["directory_targets"]
    searches = receipt["search_roots"]
    archive = receipt.get("chatgpt_archive") or {}
    chatgpt = receipt["chatgpt"]
    lines = [
        "# Account Excavation Receipt",
        "",
        f"Generated: {receipt['generated_at']}",
        "",
        "## Media Targets",
        "",
    ]
    for target in media:
        status = "found" if target.get("exists") else "missing"
        lines.append(f"- `{target['path']}` - {status}")
        probe = target.get("media_probe") or {}
        if probe.get("status") == "ok":
            video = probe.get("video") or {}
            lines.append(
                f"  - {probe.get('duration_seconds')}s, "
                f"{video.get('width')}x{video.get('height')}, {video.get('codec')}"
            )
    lines.extend(["", "## Desktop/Directory Targets", ""])
    for target in directories:
        status = "found" if target.get("exists") else "missing"
        lines.append(f"- `{target['path']}` - {status}, files={target.get('file_count', 0)}")
    lines.extend(["", "## Search Roots", ""])
    for root in searches:
        lines.append(
            f"- `{root['path']}` - {root.get('status', 'unknown')}, "
            f"matches={root.get('match_count', 0)}"
        )
    lines.extend(["", "## ChatGPT Archive / Prior Local Methods", ""])
    lines.append(
        f"- archive root `{archive.get('archive_root')}` exists={archive.get('archive_root_exists')}"
    )
    lines.append(
        f"- manifest entries={archive.get('manifest_entries', 0)}, "
        f"manifest-only={archive.get('manifest_only_in_this_checkout')}"
    )
    lines.append(f"- lanes={json.dumps(archive.get('by_lane') or {}, sort_keys=True)}")
    method_count = sum(1 for method in archive.get("local_methods", []) if method.get("exists"))
    lines.append(f"- local method files present={method_count}/{len(archive.get('local_methods', []))}")
    lines.extend(["", "## ChatGPT Live/App Index", ""])
    lines.append(
        f"- status={chatgpt.get('status')}, local project dirs={chatgpt.get('project_count', 0)}"
    )
    detail_scan = chatgpt.get("detail_scan") or {}
    if detail_scan:
        lines.append(
            f"- detail scan={detail_scan.get('scanned', 0)}/{detail_scan.get('limit', 0)}, "
            f"matches={detail_scan.get('matched', 0)}, "
            f"high-signal={detail_scan.get('high_signal_matched', 0)}, "
            f"failed={detail_scan.get('failed', 0)}, "
            f"rate-limited={detail_scan.get('rate_limited', 0)}"
        )
    nonempty = [
        project
        for project in chatgpt.get("projects", [])
        if project.get("conversation_count_indexed", 0) > 0
    ]
    lines.append(f"- non-empty indexed projects={len(nonempty)}")
    keyword_projects = [
        project
        for project in chatgpt.get("projects", [])
        if project.get("keyword_match_count", 0) > 0
    ]
    lines.append(f"- projects with keyword matches={len(keyword_projects)}")
    global_index = chatgpt.get("global_conversations") or {}
    if global_index:
        global_detail = global_index.get("detail_scan") or {}
        lines.append(
            f"- global recent conversations={global_index.get('conversation_count_indexed', 0)}, "
            f"keyword matches={global_index.get('keyword_match_count', 0)}, "
            f"high-signal matches={global_index.get('high_signal_match_count', 0)}, "
            f"detail scan={global_detail.get('scanned', 0)}/{global_detail.get('limit', 0)}, "
            f"failed={global_detail.get('failed', 0)}, "
            f"rate-limited={global_detail.get('rate_limited', 0)}"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "scope": "triptych-first account excavation",
        "worktree": str(WORKTREE_ROOT),
        "incubator": str(ROOT),
        "keywords": list(KEYWORDS),
        "media_targets": [
            {"id": target["id"], **file_record(target["path"], role=target["role"], hash_bytes=not args.no_hash)}
            for target in MEDIA_TARGETS
        ],
        "directory_targets": [
            {
                "id": target["id"],
                **directory_record(target, max_entries=args.max_directory_entries, hash_bytes=not args.no_hash),
            }
            for target in DIRECTORY_TARGETS
        ],
        "search_roots": [
            {"id": root["id"], **run_rg(root["path"], max_hits=root["max_hits"])}
            for root in SEARCH_ROOTS
        ],
        "chatgpt_archive": chatgpt_archive_manifest_index(),
        "chatgpt": (
            {"status": "skipped", "reason": "--skip-chatgpt"}
            if args.skip_chatgpt
            else chatgpt_conversation_index(
                pages=args.chatgpt_pages,
                limit=args.chatgpt_limit,
                detail_scan=not args.skip_chatgpt_detail_scan,
                detail_limit=args.chatgpt_detail_limit,
                global_pages=args.chatgpt_global_pages,
                global_limit=args.chatgpt_global_limit,
                global_detail_limit=args.chatgpt_global_detail_limit,
            )
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--no-hash", action="store_true", help="Skip sha256 hashing of target media.")
    parser.add_argument("--skip-chatgpt", action="store_true", help="Skip live ChatGPT project indexing.")
    parser.add_argument(
        "--skip-chatgpt-detail-scan",
        action="store_true",
        help="Only index ChatGPT project conversation titles; do not fetch conversation details.",
    )
    parser.add_argument("--chatgpt-pages", type=int, default=3)
    parser.add_argument("--chatgpt-limit", type=int, default=20)
    parser.add_argument("--chatgpt-detail-limit", type=int, default=160)
    parser.add_argument("--chatgpt-global-pages", type=int, default=4)
    parser.add_argument("--chatgpt-global-limit", type=int, default=50)
    parser.add_argument("--chatgpt-global-detail-limit", type=int, default=120)
    parser.add_argument("--max-directory-entries", type=int, default=80)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir.expanduser()
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    receipt = build_receipt(args)
    json_path = out_dir / "account-excavation.json"
    md_path = out_dir / "account-excavation.md"
    json_path.write_text(json.dumps(receipt, indent=2, default=json_default) + "\n", encoding="utf-8")
    write_markdown_summary(md_path, receipt)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
