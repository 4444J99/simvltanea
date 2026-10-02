"""Read-only, scoped metadata derivation; never rename files or activate policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tomllib
import unicodedata
from typing import Any, Mapping

SCHEMA = "simvltanea.repository-profile/v1"
IMPLEMENTATION_VERSION = "1.0.0-draft.1"
_ID = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*\Z", re.ASCII)
_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z", re.ASCII)
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z", re.ASCII,
)
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{kind}{number}" for kind in ("com", "lpt") for number in range(1, 10)
}
_STATES = {"draft", "approved", "effective", "deprecated", "rolled-back"}


class ProfileError(ValueError):
    """Invalid or unsupported contract input, with no input contents in errors."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ProfileError(code)


def shape(value: Any, fields: set[str], code: str) -> None:
    require(isinstance(value, dict) and set(value) == fields, code)


def member(value: Any, choices: Any) -> bool:
    return isinstance(value, str) and value in choices


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1024 and not any(
        ord(char) < 32 for char in value
    )


def semver(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = _SEMVER.fullmatch(value)
    if not match:
        return False
    return all(not (part.isdigit() and len(part) > 1 and part[0] == "0")
               for part in (match[4] or "").split("."))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def path_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def safe_path(value: Any) -> str:
    require(isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 240,
            "path.invalid-or-overlong")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and value != "."
            and ".." not in path.parts and "\\" not in value, "path.not-relative-canonical")
    for part in path.parts:
        require(not any(ord(char) < 32 or char in '<>:"|?*' for char in part)
                and not part.endswith((" ", "."))
                and part.split(".")[0].casefold() not in _RESERVED, "path.not-portable")
    return value


def expand(template: Any, roles: Mapping[str, str]) -> str:
    require(isinstance(template, str), "locator.not-text")
    try:
        # Only a single leading logical role is permitted, not Python format syntax.
        match = re.fullmatch(r"\{([a-z_]+)\}(/[^{}]+)?", template)
        require(match is not None, "locator.must-use-logical-role")
        return safe_path(roles[match[1]] + (match[2] or ""))
    except KeyError:
        raise ProfileError("locator.unknown-role") from None


def derive(document: dict[str, Any]) -> dict[str, Any]:
    """Validate the new binding and return a deterministic proposal, not conformance.

    Existing layout loading remains the authority for runtime layout semantics.
    This function has no I/O and does not classify unregistered repository files.
    """
    require(isinstance(document, dict), "document.not-table")
    roles = document.get("paths")
    require(isinstance(roles, dict) and bool(roles), "layout.missing-roles")
    profile = document.get("repository_profile")
    shape(profile, {"schema", "version", "vocabulary_version", "state", "scope",
                    "owner_authority", "authorities", "concepts", "classes",
                    "objects", "role_metadata", "exceptions"}, "profile.fields")
    require(profile["schema"] == SCHEMA, "profile.unsupported-schema")
    require(semver(profile["version"]) and semver(profile["vocabulary_version"]),
            "profile.invalid-version")
    require(member(profile["state"], _STATES), "profile.invalid-state")
    require(profile["state"] == "draft", "profile.activation-not-supported")
    require(profile["version"] == "1.0.0-draft.1"
            and profile["vocabulary_version"] == "1.0.0", "profile.unsupported-version")
    require(profile["scope"] == "registered-maintenance-objects", "profile.unsupported-scope")
    for role, location in roles.items():
        require(isinstance(role, str) and re.fullmatch(r"[a-z_]+", role) is not None,
                "layout.invalid-role")
        safe_path(location)
    require(len({path_key(path) for path in roles.values()}) == len(roles),
            "layout.case-or-unicode-collision")

    authorities = profile["authorities"]
    require(isinstance(authorities, dict) and bool(authorities), "authority.missing")
    facts = set()
    for name, authority in authorities.items():
        require(isinstance(name, str) and _ID.fullmatch(name) is not None, "authority.invalid-id")
        shape(authority, {"fact", "locator", "owner_authority", "write_path", "refresh",
                          "drift_check", "conflict", "git_blob"}, "authority.fields")
        require(all(text(authority[field]) for field in ("fact", "write_path", "refresh", "drift_check")),
                "authority.missing-responsibility")
        require(member(authority["owner_authority"], authorities), "authority.missing-owner")
        require(authority["fact"] not in facts, "authority.duplicate-fact")
        facts.add(authority["fact"])
        require(authority["conflict"] == "resolved", "authority.unresolved-conflict")
        expand(authority["locator"], roles)
        require(isinstance(authority["git_blob"], str)
                and re.fullmatch(r"[0-9a-f]{40}", authority["git_blob"]) is not None,
                "authority.unpinned-input")
    require(member(profile["owner_authority"], authorities), "profile.missing-owner")

    metadata = profile["role_metadata"]
    require(isinstance(metadata, dict) and set(metadata) == set(roles), "roles.incomplete-classification")
    for record in metadata.values():
        shape(record, {"material", "lifecycle", "purpose"}, "roles.fields")
        require(member(record["material"], {"authored", "generated", "historical", "tool-owned",
                                      "fixture", "registry", "reviewed-evidence", "template"}),
                "roles.unknown-material")
        require(member(record["lifecycle"], {"active", "retained", "local-only"}) and text(record["purpose"]),
                "roles.invalid-lifecycle-or-purpose")

    concepts = profile["concepts"]
    require(isinstance(concepts, dict) and bool(concepts), "concept.missing")
    for name, concept in concepts.items():
        require(isinstance(name, str) and _ID.fullmatch(name) is not None, "concept.invalid-id")
        shape(concept, {"term", "definition"}, "concept.fields")
        require(isinstance(concept["term"], str) and _TOKEN.fullmatch(concept["term"]) is not None
                and text(concept["definition"]), "concept.invalid-term-or-definition")

    classes = profile["classes"]
    require(isinstance(classes, dict) and bool(classes), "class.missing")
    for name, rule in classes.items():
        require(isinstance(name, str) and _ID.fullmatch(name) is not None, "class.invalid-id")
        shape(rule, {"role", "area", "prefix", "case", "extension", "definition"}, "class.fields")
        require(member(rule["role"], roles) and isinstance(rule["area"], str)
                and _TOKEN.fullmatch(rule["area"]) is not None, "class.unknown-placement")
        require(rule["prefix"] == "" or (isinstance(rule["prefix"], str)
                and _TOKEN.fullmatch(rule["prefix"]) is not None), "class.invalid-prefix")
        require(member(rule["case"], {"snake", "upper-snake"})
                and member(rule["extension"], {".py", ".md"}) and text(rule["definition"]),
                "class.unsupported-grammar")
        require(metadata[rule["role"]]["material"] == "authored", "class.protected-material")

    exceptions = profile["exceptions"]
    require(isinstance(exceptions, list), "exception.not-list")
    exception_paths = set()
    for exception in exceptions:
        shape(exception, {"scope", "reason", "owner_authority", "authority", "review_when",
                          "compatibility"}, "exception.fields")
        scope = expand(exception["scope"], roles)
        require(scope not in exception_paths, "exception.duplicate-scope")
        exception_paths.add(scope)
        require(member(exception["owner_authority"], authorities) and member(exception["authority"], authorities),
                "exception.missing-authority")
        require(all(text(exception[key]) for key in ("reason", "review_when", "compatibility")),
                "exception.missing-review-condition")

    objects = profile["objects"]
    require(isinstance(objects, list) and bool(objects), "object.missing")
    ids = set()
    paths: dict[str, str] = {}
    proposals = []
    for item in objects:
        shape(item, {"id", "class", "concept", "lifecycle", "access", "relationships", "keywords"},
              "object.fields")
        identity = item["id"]
        require(isinstance(identity, str) and _ID.fullmatch(identity) is not None, "object.invalid-id")
        require(identity not in ids, "object.duplicate-identity")
        ids.add(identity)
        require(member(item["class"], classes) and member(item["concept"], concepts), "object.unregistered-fact")
        require(item["lifecycle"] == "active" and item["access"] == "public", "object.not-public-active")
        require(isinstance(item["keywords"], list) and all(text(word) for word in item["keywords"]),
                "object.invalid-discovery-keywords")
        require(isinstance(item["relationships"], dict), "object.relationships-not-table")
        for relation, targets in item["relationships"].items():
            require(relation in {"tests", "documents"} and isinstance(targets, list)
                    and bool(targets) and all(isinstance(target, str) for target in targets)
                    and len(set(targets)) == len(targets), "object.invalid-relationship")
        rule = classes[item["class"]]
        term = concepts[item["concept"]]["term"]
        stem = "_".join(part.replace("-", "_") for part in (rule["prefix"], term) if part)
        if rule["case"] == "upper-snake":
            stem = stem.upper()
        path = safe_path(f"{roles[rule['role']]}/{rule['area']}/{stem}{rule['extension']}")
        require(not any(path == scope or path.startswith(scope + "/") for scope in exception_paths),
                "object.in-preserved-scope")
        key = path_key(path)
        require(key not in paths, "object.canonical-path-collision")
        paths[key] = identity
        proposals.append({"id": identity, "class": item["class"], "concept": item["concept"],
                          "canonical_path": path, "role": rule["role"],
                          "rule": f"repository_profile.classes.{item['class']}",
                          "facts": "repository_profile.objects + repository_profile.concepts + paths"})
    for item in objects:
        for relation, targets in item["relationships"].items():
            require(all(target in ids and target != item["id"] for target in targets),
                    "object.dangling-or-self-reference")
            require((relation != "tests" or item["class"] == "governance-test")
                    and (relation != "documents" or item["class"] == "governance-guide"),
                    "object.relationship-type-mismatch")

    return {"schema": SCHEMA, "implementation_version": IMPLEMENTATION_VERSION,
            "profile_version": profile["version"], "vocabulary_version": profile["vocabulary_version"],
            "state": profile["state"], "scope": profile["scope"],
            "claim": "derivation-preview-only", "repository_conformance": False,
            "input_sha256": hashlib.sha256(canonical_bytes(document)).hexdigest(),
            "classified_roles": len(roles), "registered_objects": len(objects),
            "objects": sorted(proposals, key=lambda item: item["id"])}


def regular_file(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = root / safe_path(relative)
    require(target.resolve().is_relative_to(root), "filesystem.symlink-escape")
    for parent in (target, *target.parents):
        if parent == root:
            break
        require(not parent.is_symlink(), "filesystem.symlink-not-regular")
    require(stat.S_ISREG(target.stat().st_mode), "filesystem.not-regular-file")
    return target


def check_repository(document: dict[str, Any], root: Path, layout: Any) -> dict[str, Any]:
    """Check registered objects against the existing placement validator and pins."""
    from tools.verification.verify_repository_structure import path_violation, run_git

    report = derive(document)
    errors = []
    for name, authority in sorted(document["repository_profile"]["authorities"].items()):
        try:
            source = regular_file(root, expand(authority["locator"], document["paths"]))
            content = source.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            if blob != authority["git_blob"]:
                errors.append(f"authority.{name}.pin-drift")
        except (OSError, ProfileError):
            errors.append(f"authority.{name}.missing-or-unsafe")
    require(run_git(root, "rev-parse", "--show-prefix") == b"\n", "repository.not-worktree-root")
    visible = run_git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths = [os.fsdecode(path) for path in visible.split(b"\0") if path]
    for item in report["objects"]:
        path = item["canonical_path"]
        try:
            regular_file(root, path)
        except (OSError, ProfileError):
            errors.append(f"object.{item['id']}.missing-or-unsafe")
        if path not in paths:
            errors.append(f"object.{item['id']}.not-git-visible")
        if path_violation(path, layout):
            errors.append(f"object.{item['id']}.existing-placement-conflict")
        if any(other != path and path_key(other) == path_key(path) for other in paths):
            errors.append(f"object.{item['id']}.existing-path-collision")
    report["errors"] = sorted(set(errors))
    report["checked_revision"] = run_git(root, "rev-parse", "HEAD").decode("ascii").strip()
    report["dirty_state"] = {
        "staged_diff_sha256": hashlib.sha256(run_git(root, "diff", "--cached", "--binary")).hexdigest(),
        "unstaged_diff_sha256": hashlib.sha256(run_git(root, "diff", "--binary")).hexdigest(),
        "git_visible_inventory_sha256": hashlib.sha256(visible).hexdigest(),
        "boundary": "untracked contents and ignored/private work are not inventoried; not custody evidence",
    }
    report["unregistered_git_visible_paths"] = len(set(paths) - {
        item["canonical_path"] for item in report["objects"]
    })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check", action="store_true", help="check registered files and pinned authorities")
    parser.add_argument("--json", action="store_true", help="deterministic, machine-readable preview")
    parser.add_argument("--enforce", action="store_true", help="reserved; activation is not authorized by this tool")
    args = parser.parse_args(argv)
    try:
        if args.enforce:
            raise ProfileError("activation.requires-owner-approved-successor; this reader is preview-only")
        from tools.paths import load_layout
        layout = load_layout(args.root)
        require(layout.manifest.stat().st_size <= 1024 * 1024, "profile.input-too-large")
        document = tomllib.loads(layout.manifest.read_text(encoding="utf-8"))
        report = check_repository(document, args.root, layout) if args.check else derive(document)
        report["validator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if args.json:
            print(json.dumps(report, sort_keys=True, indent=2))
        else:
            print(f"repository profile {report['state']}: {report['registered_objects']} registered objects; preview only")
            for item in report["objects"]:
                print(f"{item['id']} -> {item['canonical_path']}")
            for error in report.get("errors", []):
                print(error, file=sys.stderr)
        return 1 if report.get("errors") else 0
    except ProfileError as error:
        print(f"repository profile error: {error}; no changes made", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, KeyError, TypeError, ValueError, ImportError, UnicodeError):
        # Do not echo arbitrary metadata, private filesystem paths, or Git stderr.
        print("repository profile error: invalid, unsupported, or unavailable input; no changes made", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
