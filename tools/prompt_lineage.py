#!/usr/bin/env python3
"""Build a private prompt-lineage index for the visual form canon.

The raw prompt excerpts written by this script stay under ignored work/.
Tracked notes should use only the aggregate cluster counts and synthesized
decision signals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
WORKTREE_ROOT = ROOT.parents[1]
WORKSPACE_ROOT = WORKTREE_ROOT.parents[2]
WORKSPACE_HOME = WORKTREE_ROOT.parents[3]
ORGANVM_ROOT = WORKSPACE_HOME / "organvm"
DEFAULT_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
DEFAULT_OUT_DIR = ROOT / "work"


@dataclass(frozen=True)
class Cluster:
    id: str
    title: str
    promotion_signal: str
    patterns: tuple[str, ...]


CLUSTERS = [
    Cluster(
        "triptych_time_based_media",
        "Triptych / time-based media",
        "Keep the timed three-panel video canon as one reusable time-based visual form.",
        (
            r"\btriptych\b",
            r"\bthree[- ]video[- ]panel\b",
            r"\bthree[- ]panel\b",
            r"\bvideo[- ]panel\b",
            r"\binstagram story\b",
            r"\binstagram reels?\b",
            r"\bstory[- ]style\b",
            r"\bround robin\b",
            r"\bbaroque\b",
            r"\bclassical canon\b",
            r"\bcanon\s*(?:/|or)\s*round\b",
            r"\bvideo canon\b",
            r"\bvisual[- ]sketch\b",
            r"\bpanel reels?\b",
            r"\bPHP7mOJT60I\b",
            r"\bleft panel\b",
            r"\bright panel\b",
        ),
    ),
    Cluster(
        "ambient_screensaver_wallpaper_runtime",
        "Ambient screensaver / wallpaper runtime",
        "Treat idle displays, wallpapers, and ambient loops as runtime visual forms.",
        (
            r"\bscreensaver\b",
            r"\bscreen saver\b",
            r"\bwallpaper\b",
            r"\bidle display\b",
            r"\bambient display\b",
            r"\bambient resonance\b",
            r"\bprocedural svg waves?\b",
            r"\bW4V3L0RD\b",
            r"\bp5\.js\b",
            r"\blive wallpaper\b",
            r"\bdesktop wallpaper\b",
            r"\bphone wallpaper\b",
        ),
    ),
    Cluster(
        "ogod_symbolic_visual_worlds",
        "OGOD / symbolic visual worlds",
        "Treat OGOD, Pantheon, and chamber worlds as symbolic interface visual forms.",
        (
            r"\bogod\b",
            r"\bogod\.html\b",
            r"\bogod[-_ ]?3d\b",
            r"\betceter4\b",
            r"\ba-mavs-olevm\b",
            r"\bliving[- ]pantheon\b",
            r"\bpantheon\b",
            r"\bparthenon\b",
            r"\btemple architecture\b",
            r"\bchambers?\b",
            r"\bpinakotheke\b",
            r"\btheatron\b",
            r"\bodeion\b",
        ),
    ),
    Cluster(
        "ascii_textual_visual_design",
        "ASCII / textual visual design",
        "Treat text, glyph, ANSI, and prompt-wall composition as visual forms.",
        (
            r"\bascii\b",
            r"\bascii[- ]?art\b",
            r"\bansi\b",
            r"\bterminal art\b",
            r"\btextual visual\b",
            r"\btext[- ]as[- ]image\b",
            r"\btypographic diagram\b",
            r"\bprompt wall\b",
            r"\bglyph\b",
            r"\bmonospace\b",
            r"\bA-System-Operates\b",
            r"\bivi3\b",
            r"\b122325-asciiart\b",
        ),
    ),
    Cluster(
        "web_3d_chambers",
        "Web / 3D chambers",
        "Treat WebGL, 3D, and chamber viewers as reusable spatial visual forms.",
        (
            r"\bwebgl\b",
            r"\bthree\.js\b",
            r"\b3d\b",
            r"\b3-d\b",
            r"\bchamber viewer\b",
            r"\bogod-viewer\b",
            r"\bspatial integration\b",
            r"\bimmersive\b",
            r"\bvisual worlds?\b",
            r"\bviewer\b",
        ),
    ),
    Cluster(
        "pre_inception_visual_media",
        "Image / moving-image overlap",
        "Unify adjacent image-based work through a visual-form canon, not a narrow renderer.",
        (
            r"\bimage[- ]based\b",
            r"\bmoving image\b",
            r"\bvisual work\b",
            r"\bvisual/design\b",
            r"\bvisual designs?\b",
            r"\bmy own films\b",
            r"\bfilms\b",
            r"\bgenerative visual\b",
            r"\bimage project\b",
            r"\bvisual project\b",
            r"\bmicro-tato\b",
            r"\bB60\b",
            r"\bweapon[-_ ]nano\b",
            r"\bweapon[- ]shaped\b",
            r"\bnano visuals?\b",
            r"\breactive scenery\b",
            r"\bvisual mood\b",
            r"\bmood state\b",
            r"\bNanoBody\b",
        ),
    ),
    Cluster(
        "media_ark_source_custody",
        "Media Ark / source custody",
        "Keep source libraries, albums, and reusable ingestion metadata-first and restageable.",
        (
            r"\bmedia ark\b",
            r"\bmedia-ark\b",
            r"\bphotos app\b",
            r"\bmacos photos\b",
            r"\bphotos library\b",
            r"\ball my videos\b",
            r"\bphoto library\b",
            r"\bsource library\b",
            r"\bmedia library\b",
            r"\bcatalog(?:ing)? all videos\b",
            r"\bfinder folder\b",
            r"\bphotos album\b",
            r"\balbums?\b",
            r"\bcapture pipeline\b",
            r"\braw captures?\b",
            r"\bprocess captures?\b",
            r"\bcanonicalized layouts?\b",
            r"\bsidecar metadata\b",
            r"\bqueryable indexes?\b",
            r"\bOCR\b",
        ),
    ),
    Cluster(
        "portfolio_public_gateway",
        "Portfolio / public product gateway",
        "Use portfolio for public presentation, product framing, and commerce handoff.",
        (
            r"\bportfolio\b",
            r"\bpublic gateway\b",
            r"\bpublic (?:creative|product|media|posting|release) surface\b",
            r"\bproduct (?:surface|funnel|shop|gateway)\b",
            r"\bproduct/shop\b",
            r"\b(?:media|creative|product) shop\b",
            r"\bfunnel\b",
            r"\bmugs\b",
            r"\bshirts\b",
            r"\bcommerce\b",
            r"\byoutube\b",
            r"\binstagram\b",
        ),
    ),
    Cluster(
        "exhibit_kiosk_gallery",
        "Exhibit / kiosk / gallery",
        "Use exhibit or art repos for gallery, installation, kiosk, and artwork-specific runtimes.",
        (
            r"\bexhibit\b",
            r"\bgallery\b",
            r"\bdigital[- ]frame\b",
            r"\bkiosk\b",
            r"\binstallation\b",
            r"\bcuratorial\b",
        ),
    ),
    Cluster(
        "lifecycle_generated_form_governance",
        "Lifecycle / generated-form governance",
        "Keep generated visual forms bounded, ignored, verifiable, and separated from source custody.",
        (
            r"\bgenerated form\b",
            r"\bgenerated forms\b",
            r"\bgenerated media\b",
            r"\blocal sprawl\b",
            r"\bcustody\b",
            r"\bpreservation\b",
            r"\bpublic package\b",
            r"\bpublic-package\b",
            r"\bprivate receipts?\b",
            r"\bgit-visible\b",
            r"\bignored\b",
            r"\blifecycle\b",
            r"\bdirty worktree\b",
            r"\bcleanup\b",
            r"\bcache\b",
        ),
    ),
]

NOISE_PREFIXES = (
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<apps_instructions>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<codex_internal_context",
    "<turn_aborted>",
    "# AGENTS.md instructions for",
)

DEFAULT_DOCUMENTS = (
    ROOT / "HANDOFF_PROMPT.md",
    ROOT / "INCUBATION.md",
    ROOT / "OVERNIGHT_WORKSTREAM.md",
    ROOT / "README.md",
    ROOT / "project.example.json",
    ROOT / "editions.example.json",
    WORKTREE_ROOT / "config" / "_config" / "Image-Self-Setting.md",
    Path.home() / ".codex" / "memories" / "MEMORY.md",
    WORKSPACE_ROOT / "media-ark" / "README.md",
    WORKSPACE_ROOT / "media-ark" / "docs" / "README.md",
    WORKSPACE_ROOT / "portfolio" / "README.md",
    WORKSPACE_ROOT / "portfolio" / "AGENTS.md",
    WORKSPACE_ROOT / "portfolio" / ".conductor" / "active-handoff.md",
    ORGANVM_ROOT / "a-mavs-olevm" / "AGENTS.md",
    ORGANVM_ROOT / "a-mavs-olevm" / "PANTHEON_EXPANSION_SUMMARY.md",
    ORGANVM_ROOT / "a-mavs-olevm" / "OGOD.html",
    ORGANVM_ROOT / "a-mavs-olevm" / "ogod-3d.html",
    ORGANVM_ROOT / "a-mavs-olevm" / "js" / "ogod.js",
    ORGANVM_ROOT / "etceter4-revival" / "PANTHEON_EXPANSION_SUMMARY.md",
    ORGANVM_ROOT / "etceter4-revival" / "OGOD.html",
    ORGANVM_ROOT / "etceter4-revival" / "ogod-3d.html",
    ORGANVM_ROOT / "etceter4-2011" / "PANTHEON_EXPANSION_SUMMARY.md",
    ORGANVM_ROOT / "etceter4-2011" / "OGOD.html",
    ORGANVM_ROOT / "chthon-oneiros" / "AGENTS.md",
    ORGANVM_ROOT / "chthon-oneiros" / "docs" / "122325-asciiart-README.md",
    ORGANVM_ROOT / "chthon-oneiros" / "release" / "week_03" / "met4morfoses_sync.md",
    ORGANVM_ROOT / "chthon-oneiros" / "bible" / "core_loop.md",
    ORGANVM_ROOT / "chthon-oneiros" / "research" / "world-09-screen-life.md",
    ORGANVM_ROOT / "chthon-oneiros" / "research" / "world-10-args-immersive.md",
    ORGANVM_ROOT
    / "praxis-perpetua"
    / "sessions"
    / "gemini"
    / "cli"
    / "4jp"
    / "2026-01-09--session-2026--prompts.md",
    ORGANVM_ROOT / "recursive-engine--generative-entity" / "docs" / "source-materials" / "specs" / "grokking-algorithms-for-os.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build ignored private prompt-lineage receipts for the triptych visual form canon."
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=DEFAULT_SESSIONS_ROOT,
        help="Codex sessions root to scan.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Ignored output directory for lineage receipts.",
    )
    parser.add_argument("--json", action="store_true", help="Print the private JSON receipt to stdout.")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_noise_text(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return True
    if any(stripped.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True
    return False


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"input_text", "output_text", "text"}:
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def cluster_matches(text: str) -> dict[str, int]:
    matches: dict[str, int] = {}
    for cluster in CLUSTERS:
        count = sum(1 for pattern in cluster.patterns if re.search(pattern, text, flags=re.IGNORECASE))
        if count:
            matches[cluster.id] = count
    return matches


def primary_cluster(matches: dict[str, int]) -> str:
    ranked = sorted(matches.items(), key=lambda item: (-item[1], cluster_order(item[0])))
    return ranked[0][0]


def cluster_order(cluster_id: str) -> int:
    for index, cluster in enumerate(CLUSTERS):
        if cluster.id == cluster_id:
            return index
    return len(CLUSTERS)


def prompt_id(path: Path, line_number: int, text: str) -> str:
    digest = hashlib.sha1(f"{path}:{line_number}:{text}".encode("utf-8")).hexdigest()
    return digest[:16]


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def iter_session_prompts(session_paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in session_paths:
        session_id = path.stem
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "session_meta":
                    payload = record.get("payload", {})
                    if isinstance(payload, dict):
                        session_id = str(payload.get("id") or payload.get("session_id") or session_id)
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                raw_text = text_from_content(payload.get("content"))
                if is_noise_text(raw_text):
                    continue
                text = normalize_text(raw_text)
                matches = cluster_matches(text)
                if not matches:
                    continue
                yield {
                    "prompt_id": prompt_id(path, line_number, text),
                    "session_id": session_id,
                    "created_at": record.get("timestamp"),
                    "source_path": str(path),
                    "line_number": line_number,
                    "cluster": primary_cluster(matches),
                    "confidence": max(matches.values()),
                    "excerpt": text[:900],
                    "project_overlap": sorted(matches, key=cluster_order),
                    "promotion_signal": cluster_by_id(primary_cluster(matches)).promotion_signal,
                    "privacy_level": "private-session-prompt",
                }


def cluster_by_id(cluster_id: str) -> Cluster:
    for cluster in CLUSTERS:
        if cluster.id == cluster_id:
            return cluster
    raise KeyError(cluster_id)


def scan_document(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = cluster_matches(text)
    if not matches:
        return None
    return {
        "path": str(path),
        "cluster": primary_cluster(matches),
        "confidence": max(matches.values()),
        "project_overlap": sorted(matches, key=cluster_order),
        "privacy_level": "private-path-document-evidence",
    }


def summarize(prompts: list[dict[str, Any]], documents: list[dict[str, Any]]) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    for cluster in CLUSTERS:
        prompt_hits = [
            item
            for item in prompts
            if cluster.id in item.get("project_overlap", [item["cluster"]])
        ]
        doc_hits = [
            item
            for item in documents
            if cluster.id in item.get("project_overlap", [item["cluster"]])
        ]
        all_prompt_dates = sorted(
            str(item.get("created_at")) for item in prompt_hits if item.get("created_at")
        )
        clusters.append(
            {
                "cluster": cluster.id,
                "title": cluster.title,
                "prompt_count": len(prompt_hits),
                "document_count": len(doc_hits),
                "date_range": [all_prompt_dates[0], all_prompt_dates[-1]] if all_prompt_dates else [],
                "promotion_signal": cluster.promotion_signal,
            }
        )
    return {
        "prompt_count": len(prompts),
        "document_count": len(documents),
        "clusters": clusters,
    }


def build_receipt(sessions_root: Path) -> dict[str, Any]:
    session_paths = sorted(sessions_root.expanduser().glob("**/*.jsonl"))
    prompts = list(iter_session_prompts(session_paths))
    documents = [doc for path in DEFAULT_DOCUMENTS if (doc := scan_document(path)) is not None]
    return {
        "schema": "triptych.visual-form-lineage.v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sessions_root": str(sessions_root.expanduser()),
        "session_files_scanned": len(session_paths),
        "source_policy": {
            "raw_prompt_excerpts": "private; keep under ignored work/",
            "tracked_summary": "aggregate cluster counts and synthesized decisions only",
            "excluded_user_blocks": list(NOISE_PREFIXES),
        },
        "summary": summarize(prompts, documents),
        "clusters": [asdict(cluster) for cluster in CLUSTERS],
        "prompts": prompts,
        "documents": documents,
    }


def write_markdown(receipt: dict[str, Any], path: Path) -> None:
    summary = receipt["summary"]
    lines = [
        "# Visual Form Prompt Lineage",
        "",
        "Private receipt. Raw excerpts and source paths must not be copied into tracked docs.",
        "",
        f"- Generated: {receipt['generated_at']}",
        f"- Session files scanned: {receipt['session_files_scanned']}",
        f"- Session prompts matched: {summary['prompt_count']}",
        f"- Document evidence matched: {summary['document_count']}",
        "",
        "## Cluster Overlap Summary",
        "",
        "Prompts and documents can appear in more than one cluster.",
        "",
        "| Cluster | Prompt overlaps | Document overlaps | Date range | Promotion signal |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for cluster in summary["clusters"]:
        rendered_date_range = " - ".join(cluster["date_range"]) if cluster["date_range"] else "n/a"
        lines.append(
            f"| {cluster['title']} | {cluster['prompt_count']} | "
            f"{cluster['document_count']} | {rendered_date_range} | "
            f"{cluster['promotion_signal']} |"
        )
    lines.extend(["", "## Private Examples", ""])
    for prompt in receipt["prompts"][:24]:
        lines.extend(
            [
                f"### {prompt['cluster']} / {prompt['prompt_id']}",
                "",
                f"- Created: {prompt.get('created_at') or 'unknown'}",
                f"- Session: {prompt['session_id']}",
                f"- Source: {prompt['source_path']}:{prompt['line_number']}",
                "",
                "```text",
                str(prompt["excerpt"]),
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    sessions_root = args.sessions_root.expanduser()
    if not sessions_root.exists():
        raise SystemExit(f"sessions root does not exist: {sessions_root}")
    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    receipt = build_receipt(sessions_root)
    json_path = out_dir / "visual-media-lineage.json"
    md_path = out_dir / "visual-media-lineage.md"
    visual_form_json_path = out_dir / "visual-form-lineage.json"
    visual_form_md_path = out_dir / "visual-form-lineage.md"
    rendered_json = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    visual_form_json_path.write_text(rendered_json, encoding="utf-8")
    write_markdown(receipt, visual_form_md_path)

    # Compatibility receipts for earlier Visual Media Canon references.
    json_path.write_text(rendered_json, encoding="utf-8")
    write_markdown(receipt, md_path)

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        summary = receipt["summary"]
        print(f"lineage prompts: {summary['prompt_count']}")
        print(f"lineage documents: {summary['document_count']}")
        print(f"wrote {display_path(visual_form_json_path)}")
        print(f"wrote {display_path(visual_form_md_path)}")
        print(f"wrote compatibility {display_path(json_path)}")
        print(f"wrote compatibility {display_path(md_path)}")


if __name__ == "__main__":
    main()
