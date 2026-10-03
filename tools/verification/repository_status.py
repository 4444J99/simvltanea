"""Read-only, timestamped GitHub observations; never infer custody or conformance.

The current view is generated under the layout's proof role. Checked-in status
instructions point to these receipts rather than claiming that branches remain
synchronized forever. Collection is bounded, pagination-aware and fail-closed
for unknown data. Only fixed-host HTTPS GET requests are supported.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

LANES = tuple(f"lane/{name}" for name in ("verify", "heal", "expand", "evolve"))
DEFAULT_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/package.yml")


class ReadError(RuntimeError):
    """A redacted collection failure, never a false empty collection."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ReadError(f"redirect-refused:{code}")


class GitHubReader:
    def __init__(self, repository: str, token: str | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository identity")
        self.base = "https://api.github.com/repos/" + repository
        self.token = token
        self.opener = build_opener(NoRedirect())

    def get(self, path: str, params: dict | None = None) -> tuple[Any, dict]:
        if path and (not path.startswith("/") or ".." in path or "?" in path or "#" in path):
            raise ValueError("invalid fixed-host API path")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "simvltanea-current-status"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        url = self.base + path + (("?" + urlencode(params)) if params else "")
        try:
            with self.opener.open(Request(url, headers=headers, method="GET"), timeout=30) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
                if len(payload) > 8 * 1024 * 1024:
                    raise ReadError("response-too-large")
                return json.loads(payload), dict(response.headers)
        except HTTPError as error:
            raise ReadError(f"http:{error.code}") from None
        except (URLError, OSError, ValueError):
            raise ReadError("unavailable-or-invalid-json") from None

    def pages(self, path: str, params: dict | None = None, key: str | None = None,
              max_pages: int = 50) -> dict:
        items = []
        if not 1 <= max_pages <= 50:
            raise ValueError("invalid page bound")
        for page in range(1, max_pages + 1):
            try:
                data, headers = self.get(path, {**(params or {}), "per_page": 100, "page": page})
                rows = data.get(key) if key and isinstance(data, dict) else data
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    raise ReadError("invalid-collection")
                items.extend(rows)
                link = next((value for name, value in headers.items() if name.lower() == "link"), "")
                if not re.search(r'rel="next"', link):
                    return {"items": items, "complete": True}
            except ReadError as error:
                return {"items": items, "complete": False, "error": str(error)}
        return {"items": items, "complete": False, "error": "pagination-bound-reached"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect(reader: GitHubReader, expected_repository_id: int) -> dict:
    raw = {"started_at": utc_now(), "errors": []}

    def read(name: str, path: str):
        try:
            value, _ = reader.get(path)
            if not isinstance(value, dict):
                raise ReadError("invalid-object")
            raw[name] = value
        except ReadError as error:
            raw[name] = None
            raw["errors"].append({"collection": name, "error": str(error)})

    read("repository", "")
    repository = raw["repository"]
    if not repository or repository.get("id") != expected_repository_id:
        raise ReadError("repository-identity-unverified")
    branch = repository.get("default_branch")
    if not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", branch):
        raise ReadError("unsupported-default-branch")
    read("main_before", "/branches/" + branch)
    for name, path, params in (("branches", "/branches", {}),
                               ("pulls", "/pulls", {"state": "open"}),
                               ("issues", "/issues", {"state": "open"}),
                               ("releases", "/releases", {}),
                               ("rulesets", "/rulesets", {"includes_parents": "true"})):
        raw[name] = reader.pages(path, params)
    head = (raw["main_before"] or {}).get("commit", {}).get("sha")
    if isinstance(head, str) and re.fullmatch(r"[0-9a-f]{40}", head):
        raw["runs"] = reader.pages("/actions/runs", {"head_sha": head, "event": "push"}, "workflow_runs")
    else:
        raw["runs"] = {"items": [], "complete": False, "error": "main-head-unavailable"}
    read("main_after", "/branches/" + branch)
    raw["finished_at"] = utc_now()
    return raw


def project(raw: dict, source: dict, workflows: tuple[str, ...] = DEFAULT_WORKFLOWS) -> dict:
    if not workflows or len(set(workflows)) != len(workflows):
        raise ValueError("the observed verification scope must be explicit and nonempty")
    repository = raw["repository"]
    branch = repository["default_branch"]
    before = (raw.get("main_before") or {}).get("commit", {}).get("sha")
    after = (raw.get("main_after") or {}).get("commit", {}).get("sha")
    coherent = isinstance(before, str) and bool(re.fullmatch(r"[0-9a-f]{40}", before)) and before == after
    errors = list(raw.get("errors", []))
    collections = {}
    for name in ("branches", "pulls", "issues", "releases", "runs", "rulesets"):
        record = raw.get(name, {"items": [], "complete": False, "error": "not-collected"})
        collections[name] = record
        if not record["complete"]:
            errors.append({"collection": name, "error": record.get("error", "incomplete")})
    branches = {item["name"]: item.get("commit", {}).get("sha") for item in collections["branches"]["items"]}
    lanes = [{"name": name, "sha": branches.get(name),
              "matches_main": branches.get(name) == before if collections["branches"]["complete"] and coherent else None}
             for name in LANES]
    lane_parity = all(item["matches_main"] for item in lanes) if coherent and collections["branches"]["complete"] else None
    matching_runs = [run for run in collections["runs"]["items"]
                     if run.get("head_sha") == before and run.get("head_branch") == branch and run.get("event") == "push"]
    verification = []
    for path in workflows:
        candidates = [run for run in matching_runs if run.get("path", "").split("@")[0] == path]
        latest = max(candidates, key=lambda run: (run.get("id", 0), run.get("run_attempt", 0))) if candidates else None
        verification.append({"workflow": path, "run_id": latest["id"] if latest else None,
                             "status": latest.get("status") if latest else "not-observed",
                             "conclusion": latest.get("conclusion") if latest else None,
                             "url": latest.get("html_url") if latest else None})
    verification_pass = (coherent and collections["runs"]["complete"] and
                         all(row["status"] == "completed" and row["conclusion"] == "success" for row in verification))
    pull_rows = [{"number": item["number"], "title": item.get("title", ""), "draft": item.get("draft"),
                  "head_sha": item.get("head", {}).get("sha"), "base_sha": item.get("base", {}).get("sha")}
                 for item in collections["pulls"]["items"]]
    issue_rows = [{"number": item["number"], "title": item.get("title", "")}
                  for item in collections["issues"]["items"] if "pull_request" not in item]
    release_rows = [{"id": item["id"], "tag": item.get("tag_name"), "draft": item.get("draft"),
                     "prerelease": item.get("prerelease"), "published_at": item.get("published_at")}
                    for item in collections["releases"]["items"]]
    core_complete = coherent and all(collections[name]["complete"] for name in ("branches", "pulls", "issues", "releases", "runs"))
    return {"schema": "simvltanea.repository-status.v1", "observed_from": raw["started_at"],
            "observed_at": raw["finished_at"], "repository": repository["full_name"], "repository_id": repository["id"],
            "main": {"branch": branch, "sha": before, "sha_after": after, "coherent": coherent},
            "collection_complete": core_complete, "lanes": lanes, "lanes_synchronized": lane_parity,
            "pull_requests": {"items": pull_rows, "complete": collections["pulls"]["complete"]},
            "issues": {"items": issue_rows, "complete": collections["issues"]["complete"]},
            "releases": {"items": release_rows, "complete": collections["releases"]["complete"]},
            "verification": verification, "selected_post_merge_workflows_pass": verification_pass,
            "source_metadata": {**source, "matches_observed_main": source.get("git_sha") == before and coherent},
            "enforcement": {"branch_protected_observed": (raw.get("main_before") or {}).get("protected"),
                            "rulesets_complete": collections["rulesets"]["complete"],
                            "rulesets": [{"id": item["id"], "name": item.get("name"), "enforcement": item.get("enforcement")}
                                         for item in collections["rulesets"]["items"]],
                            "approved_requirements_verified": False},
            "repository_conformance": False, "release_authorized": False, "retirement_authorized": False,
            "errors": errors,
            "limits": ["Timestamped observations, not an atomic GitHub transaction",
                       "Selected post-merge workflows are not complete release or conformance acceptance",
                       "Branch protection/ruleset presence does not prove approved rule effectiveness",
                       "Local worktrees, private payload, restore custody and artist approval are not observed"]}


def markdown(report: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# SIMVLTANEA current observation", "", f"Observed: {report['observed_at']}", "",
             f"Repository: `{report['repository']}` (ID `{report['repository_id']}`).",
             f"Main: `{report['main']['sha']}`. Coherent head: `{report['main']['coherent']}`.",
             f"Core collections complete: `{report['collection_complete']}`.",
             f"Standing lanes synchronized: `{report['lanes_synchronized']}`.", "",
             "## Selected post-merge workflows", "", "| Workflow | Run | State | Conclusion |", "| --- | --- | --- | --- |"]
    lines += [f"| {cell(row['workflow'])} | {row['run_id']} | {cell(row['status'])} | {cell(row['conclusion'])} |" for row in report["verification"]]
    lines += ["", "## Standing lanes", "", "| Lane | SHA | Matches main |", "| --- | --- | --- |"]
    lines += [f"| `{row['name']}` | `{row['sha']}` | {row['matches_main']} |" for row in report["lanes"]]
    for key, title in (("pull_requests", "Open pull requests"), ("issues", "Open issues")):
        lines += ["", "## " + title, "", f"Collection complete: `{report[key]['complete']}`.", "",
                  "| Number | Title |", "| --- | --- |"]
        lines += [f"| #{row['number']} | {cell(row['title'])} |" for row in report[key]["items"]]
        if not report[key]["items"]:
            lines += ["| — | No items observed; absence is authoritative only for a complete collection. |"]
    lines += ["", "## Boundaries", "", "This receipt does not authorize release, retirement, profile activation or conformance.", "",
              "Enforcement observations and source-metadata revision are in the companion JSON.",
              "An incomplete collection or changed main head cannot produce a passing current-head claim.", ""]
    if report["errors"]:
        lines += ["## Collection gaps", "", "```json", json.dumps(report["errors"], indent=2), "```", ""]
    return "\n".join(lines)


def main() -> int:
    import tomllib
    from tools.paths import LAYOUT, PROOFS_DIR, REPO_ROOT, require_in_var
    from simvltanea.authoring import AUTHORED, ENGINE_VERSION, SCHEMA_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-repository-id", required=True, type=int)
    parser.add_argument("--workflow", action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = require_in_var(args.output or PROOFS_DIR / "current-status" / ("run-" + uuid.uuid4().hex))
    directory.mkdir(parents=True, exist_ok=False)
    source = {"git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip(),
              "package_version": tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["version"],
              "layout_contract": dict(LAYOUT.contract), "engine_version": ENGINE_VERSION,
              "composition_schema": SCHEMA_VERSION, "supported_loop_counts": sorted(AUTHORED)}
    try:
        raw = collect(GitHubReader(args.repository, os.environ.get("GITHUB_TOKEN")), args.expected_repository_id)
        report = project(raw, source, tuple(args.workflow or DEFAULT_WORKFLOWS))
    except (ReadError, ValueError, KeyError, TypeError):
        # Do not emit response bodies, tokens, private paths, or a fabricated empty view.
        report = {"schema": "simvltanea.repository-status-error.v1", "observed_at": utc_now(),
                  "error": "collection-or-schema-failure", "collection_complete": False,
                  "repository_conformance": False, "release_authorized": False, "retirement_authorized": False}
        (directory / "snapshot.json").write_text(json.dumps(report, indent=2) + "\n")
        return 2
    (directory / "snapshot.json").write_text(json.dumps(report, indent=2) + "\n")
    text = markdown(report)
    (directory / "STATUS.md").write_text(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(text)
    print(json.dumps({"receipt": directory.relative_to(REPO_ROOT).as_posix(), "complete": report["collection_complete"]}))
    return 0 if report["collection_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
