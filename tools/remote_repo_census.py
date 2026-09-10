#!/usr/bin/env python3
"""Build a private GitHub repo census for visual-form canon review.

Remote repositories are the canonical scope. Local checkouts are only cached
working copies. This command writes ignored receipts under work/ so tracked
notes can cite aggregate counts and decisions without dumping the repo list.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = ROOT / "work"
DEFAULT_OWNERS = ("organvm", "4444J99")


@dataclass(frozen=True)
class Signal:
    id: str
    title: str
    patterns: tuple[str, ...]


SIGNALS = (
    Signal(
        "ascii_textual_visual_design",
        "ASCII / textual visual design",
        (
            r"\bglyph\b",
            r"\bglyph[-_ ]?cascade\b",
            r"\bascii\b",
            r"\bansi\b",
            r"\btypograph",
            r"\btext[-_ ]?as[-_ ]?image\b",
            r"\btextual\b",
        ),
    ),
    Signal(
        "visual_runtime_art",
        "Visual runtime / generative art",
        (
            r"\bvisual\b",
            r"\bvisuali[sz]er\b",
            r"\bvisuali[sz]ation\b",
            r"\bgenerative[-_ ]?abstract\b",
            r"\babstract[-_ ]?environments?\b",
            r"\bgenerative[-_ ]?art\b",
            r"\binteractive[-_ ]?art\b",
            r"\bcanvas\b",
            r"\bp5js\b",
            r"\bp5\.js\b",
            r"\bcreative[-_ ]?coding\b",
            r"\brendering[-_ ]?pipelines?\b",
            r"\bperformance[-_ ]?systems\b",
        ),
    ),
    Signal(
        "ambient_screensaver_wallpaper_runtime",
        "Ambient screensaver / wallpaper runtime",
        (
            r"\bscreensaver\b",
            r"\bscreen[-_ ]?saver\b",
            r"\bwallpaper\b",
            r"\bidle[-_ ]?display\b",
            r"\bambient\b",
        ),
    ),
    Signal(
        "ogod_symbolic_visual_worlds",
        "OGOD / symbolic visual worlds",
        (
            r"\bogod\b",
            r"\betceter4\b",
            r"\ba[-_ ]?mavs[-_ ]?olevm\b",
            r"\bpantheon\b",
            r"\btemple\b",
            r"\bsymbolic\b",
            r"\bworldbuilding\b",
        ),
    ),
    Signal(
        "web_3d_chambers",
        "Web / 3D chambers",
        (
            r"\bwebgl\b",
            r"\bthree\b",
            r"\b3d\b",
            r"\bspatial\b",
            r"\bimmersive\b",
            r"\bviewer\b",
        ),
    ),
    Signal(
        "media_ark_source_custody",
        "Media Ark / source custody",
        (
            r"\bmedia[-_ ]?ark\b",
            r"\barchive\b",
            r"\bpast[-_ ]?works\b",
            r"\bprovenance\b",
            r"\bsource[-_ ]?custody\b",
            r"\bmedia[-_ ]?processing\b",
        ),
    ),
    Signal(
        "portfolio_public_gateway",
        "Portfolio / public gateway",
        (
            r"\bportfolio\b",
            r"\bshowcase\b",
            r"\blanding[-_ ]?page\b",
            r"\bgithub[-_ ]?pages\b",
            r"\bpublic[-_ ]?process\b",
            r"\bcase[-_ ]?studies\b",
        ),
    ),
    Signal(
        "exhibit_kiosk_gallery",
        "Exhibit / kiosk / gallery",
        (
            r"\bexhibit\b",
            r"\bgallery\b",
            r"\bkiosk\b",
            r"\binstallation\b",
            r"\binteractive[-_ ]?installation\b",
            r"\bdigital[-_ ]?frame\b",
        ),
    ),
    Signal(
        "audio_visual_waveform",
        "Audio-visual waveform runtime",
        (
            r"\baudio[-_ ]?visual\b",
            r"\baudiovisual\b",
            r"\bwaveform\b",
            r"\bsynth\b",
            r"\bsonic\b",
            r"\btone\.js\b",
            r"\bweb[-_ ]?audio\b",
        ),
    ),
)


def run_gh_repo_list(owner: str, limit: int) -> list[dict[str, Any]]:
    cmd = [
        "gh",
        "repo",
        "list",
        owner,
        "--limit",
        str(limit),
        "--json",
        "name,nameWithOwner,description,isArchived,isPrivate,updatedAt,url,repositoryTopics",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not isinstance(data, list):
        raise ValueError(f"unexpected gh repo list payload for {owner}: {type(data)!r}")
    return data


def text_for_repo(repo: dict[str, Any]) -> str:
    topics = repo.get("repositoryTopics") or []
    topic_names = " ".join(str(topic.get("name", "")) for topic in topics if isinstance(topic, dict))
    return " ".join(
        (
            str(repo.get("nameWithOwner") or ""),
            str(repo.get("name") or ""),
            str(repo.get("description") or ""),
            topic_names,
        )
    )


def matching_signals(repo: dict[str, Any]) -> list[dict[str, Any]]:
    text = text_for_repo(repo).lower()
    matches: list[dict[str, Any]] = []
    for signal in SIGNALS:
        hit_patterns = [pattern for pattern in signal.patterns if re.search(pattern, text, re.IGNORECASE)]
        if hit_patterns:
            matches.append(
                {
                    "id": signal.id,
                    "title": signal.title,
                    "matched_patterns": hit_patterns,
                }
            )
    return matches


def normalize_repo(repo: dict[str, Any], owner: str) -> dict[str, Any]:
    topics = repo.get("repositoryTopics") or []
    topic_names = [str(topic.get("name")) for topic in topics if isinstance(topic, dict) and topic.get("name")]
    signals = matching_signals(repo)
    return {
        "owner": owner,
        "name": repo.get("name"),
        "nameWithOwner": repo.get("nameWithOwner"),
        "description": repo.get("description") or "",
        "isArchived": bool(repo.get("isArchived")),
        "isPrivate": bool(repo.get("isPrivate")),
        "updatedAt": repo.get("updatedAt"),
        "url": repo.get("url"),
        "topics": topic_names,
        "visualFormSignals": signals,
        "visualFormSignalCount": len(signals),
    }


def sort_repo(repo: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(repo.get("visualFormSignalCount") or 0),
        str(repo.get("nameWithOwner") or ""),
    )


def summarize(repos: list[dict[str, Any]]) -> dict[str, Any]:
    by_signal: dict[str, dict[str, Any]] = {
        signal.id: {"id": signal.id, "title": signal.title, "repo_count": 0, "repos": []}
        for signal in SIGNALS
    }
    for repo in repos:
        for signal in repo["visualFormSignals"]:
            bucket = by_signal[signal["id"]]
            bucket["repo_count"] += 1
            bucket["repos"].append(repo["nameWithOwner"])

    owners = sorted({repo["owner"] for repo in repos})
    visual_candidates = [repo for repo in repos if repo["visualFormSignals"]]
    return {
        "owners": owners,
        "repo_count": len(repos),
        "private_repo_count": sum(1 for repo in repos if repo["isPrivate"]),
        "archived_repo_count": sum(1 for repo in repos if repo["isArchived"]),
        "visual_candidate_count": len(visual_candidates),
        "signals": [bucket for bucket in by_signal.values() if bucket["repo_count"]],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    repos = payload["visual_candidates"]
    lines = [
        "# Remote Repo Census",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Remote repositories are canonical scope. Local checkouts are cached working copies only.",
        "",
        "## Summary",
        "",
        f"- Owners: {', '.join(summary['owners'])}",
        f"- Repositories scanned: {summary['repo_count']}",
        f"- Private repositories: {summary['private_repo_count']}",
        f"- Archived repositories: {summary['archived_repo_count']}",
        f"- Visual-form candidates: {summary['visual_candidate_count']}",
        "",
        "## Signal Counts",
        "",
        "| Signal | Repositories |",
        "| --- | ---: |",
    ]
    for signal in summary["signals"]:
        lines.append(f"| {signal['title']} | {signal['repo_count']} |")

    lines.extend(
        [
            "",
            "## Visual-Form Candidates",
            "",
            "| Repository | Signals | Updated | Private | Archived | Description |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for repo in repos:
        signal_titles = ", ".join(signal["title"] for signal in repo["visualFormSignals"])
        description = str(repo["description"]).replace("|", "\\|")
        lines.append(
            "| {name} | {signals} | {updated} | {private} | {archived} | {desc} |".format(
                name=repo["nameWithOwner"],
                signals=signal_titles,
                updated=repo["updatedAt"],
                private=str(repo["isPrivate"]).lower(),
                archived=str(repo["isArchived"]).lower(),
                desc=description,
            )
        )

    path.write_text("\n".join(lines) + "\n")


def build_census(owners: Iterable[str], limit: int) -> dict[str, Any]:
    repos: list[dict[str, Any]] = []
    for owner in owners:
        for raw_repo in run_gh_repo_list(owner, limit):
            repos.append(normalize_repo(raw_repo, owner))
    repos.sort(key=lambda repo: str(repo.get("nameWithOwner") or ""))
    visual_candidates = sorted((repo for repo in repos if repo["visualFormSignals"]), key=sort_repo)
    return {
        "schema": "triptych.remote-repo-census.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "owners": list(owners),
        "summary": summarize(repos),
        "repos": repos,
        "visual_candidates": visual_candidates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", action="append", dest="owners", help="GitHub owner to scan. Repeatable.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum repos per owner.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Receipt directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    owners = tuple(args.owners or DEFAULT_OWNERS)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_census(owners, args.limit)
    json_path = out_dir / "remote-repo-census.json"
    md_path = out_dir / "remote-repo-census.md"
    write_json(json_path, payload)
    write_markdown(md_path, payload)

    summary = payload["summary"]
    print(f"remote repos: {summary['repo_count']}")
    print(f"visual-form candidates: {summary['visual_candidate_count']}")
    print(f"wrote {display_path(json_path)}")
    print(f"wrote {display_path(md_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
