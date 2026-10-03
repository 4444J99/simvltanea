"""Derive the current plan index from dated source documents; never edit plans."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import re


def render(plans: Path, generated_roles: dict[str, str]) -> str:
    rows = []
    for path in sorted(plans.glob("*.md")):
        if not re.match(r"\d{4}-", path.name):
            continue
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md", path.name)
        if not match or path.is_symlink():
            raise ValueError("dated plan has an unsafe or unsupported filename")
        date.fromisoformat(match[1])
        heading = next((line[2:].strip() for line in path.read_text().splitlines() if line.startswith("# ")), None)
        if not heading:
            raise ValueError("dated plan is missing its title")
        title = heading.replace("|", "\\|")
        rows.append(f"| {match[1]} | [{match[2]}]({path.name}) | {title} |")
    lines = ["# Plans Index — SIMVLTANEA", "", "Generated from dated plan filenames and their first level-one headings.",
             "Regenerate with `python3 -m tools.verification.sync_plan_index --write`.",
             "Check without writing with `python3 -m tools.verification.sync_plan_index`.", "",
             "Dated source records remain immutable. A plan title is not current completion",
             "evidence; branch, PR and workflow state belong in the current status projection.", "",
             "| Date | Plan | Recorded title |", "| --- | --- | --- |", *rows, "", "## Generated output roles", ""]
    lines.extend(f"`{name}` → `{value}`.  " for name, value in sorted(generated_roles.items()))
    lines += ["", "These locations are derived from the current layout authority, not historical paths.", ""]
    return "\n".join(lines)


def generated_roles(layout) -> dict[str, str]:
    """Derive every generated child from the effective layout's checked boundary."""
    boundary = layout.path("generated")
    return {role: layout.relative(role) for role in layout.roles
            if role != "generated" and layout.path(role).is_relative_to(boundary)}


def main() -> int:
    from tools.paths import LAYOUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    plans = LAYOUT.path("docs") / "plans"
    text = render(plans, generated_roles(LAYOUT))
    target = plans / "INDEX.md"
    if args.write:
        if target.is_symlink():
            raise ValueError("index cannot be a symlink")
        if not target.exists() or target.read_text() != text:
            target.write_text(text)
        return 0
    if not target.is_file() or target.is_symlink() or target.read_text() != text:
        print("Plan index differs from dated sources; regenerate the current index only.")
        return 1
    print("Plan index matches dated sources and current layout roles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
