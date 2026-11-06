"""Check the prerequisites the installed commands rely on.

Required checks decide the exit status. The shared engine is optional and is
reported for information only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .version import get_version

MINIMUM_PYTHON = (3, 12)
REQUIRED_ENCODERS = ("libx264", "aac")
FFMPEG_REMEDY = "install FFmpeg, for example `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Debian/Ubuntu)"
PROBE_TIMEOUT_SECONDS = 20
_ENCODER_LINE = re.compile(r"^\s*[VAS][A-Z.]{5}\s+(\S+)")

Check = dict[str, Any]


def _check(identifier: str, label: str, passed: bool, detail: str, remedy: str = "",
           required: bool = True) -> Check:
    if passed:
        status = "ok"
    else:
        status = "fail" if required else "info"
    return {"id": identifier, "label": label, "status": status, "required": required,
            "detail": detail, "remedy": "" if passed else remedy}


def check_python() -> Check:
    found = ".".join(str(part) for part in sys.version_info[:3])
    wanted = ".".join(str(part) for part in MINIMUM_PYTHON)
    return _check("python", f"python >= {wanted}", sys.version_info[:2] >= MINIMUM_PYTHON, found,
                  f"use Python {wanted} or newer to run independent-loop-compositor")


def _run_version(path: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run([path, "-version"], capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{path} is not runnable: {error}"
    if completed.returncode != 0:
        return False, f"{path} -version exited with status {completed.returncode}"
    lines = completed.stdout.strip().splitlines()
    banner = lines[0].split(" Copyright")[0] if lines else ""
    return True, f"{path} ({banner})" if banner else path


def check_tool(name: str) -> Check:
    path = shutil.which(name)
    if path is None:
        return _check(name, name, False, "not found on PATH", FFMPEG_REMEDY)
    runnable, detail = _run_version(path)
    return _check(name, name, runnable, detail, FFMPEG_REMEDY)


def listed_encoders(output: str) -> set[str]:
    """Encoder names from ``ffmpeg -encoders`` output."""
    return {match.group(1) for line in output.splitlines() if (match := _ENCODER_LINE.match(line))}


def check_encoders() -> list[Check]:
    path = shutil.which("ffmpeg")
    available: set[str] | None = None
    reason = "ffmpeg is unavailable, so encoders cannot be listed"
    if path is not None:
        try:
            completed = subprocess.run([path, "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", timeout=PROBE_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            reason = f"could not list encoders: {error}"
        else:
            if completed.returncode == 0:
                available = listed_encoders(completed.stdout)
            else:
                reason = f"ffmpeg -encoders exited with status {completed.returncode}"
    checks = []
    for encoder in REQUIRED_ENCODERS:
        if available is None:
            checks.append(_check(f"encoder-{encoder}", f"{encoder} encoder", False, reason, FFMPEG_REMEDY))
        else:
            checks.append(_check(
                f"encoder-{encoder}", f"{encoder} encoder", encoder in available,
                "listed by ffmpeg -encoders" if encoder in available else "not listed by ffmpeg -encoders",
                f"use an FFmpeg build with {encoder} enabled; {FFMPEG_REMEDY}"))
    return checks


def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.is_dir():
            return candidate
    return path


def check_workspace() -> Check:
    try:
        from simvltanea.paths import VAR_DIR
    except (ImportError, OSError, ValueError) as error:
        return _check("workspace", "workspace writable", False, f"cannot resolve workspace: {error}",
                      "set SIMVLTANEA_ROOT to an existing directory or run from your project directory")
    if Path(VAR_DIR).exists() and not Path(VAR_DIR).is_dir():
        return _check("workspace", "workspace writable", False, f"{VAR_DIR} exists but is not a directory",
                      f"remove or rename {VAR_DIR} so generated output can be written there")
    base = _nearest_existing(Path(VAR_DIR))
    try:
        with tempfile.TemporaryFile(dir=base):
            pass
    except OSError as error:
        return _check("workspace", "workspace writable", False, f"{VAR_DIR}: {error.strerror or error}",
                      f"make {base} writable or set SIMVLTANEA_ROOT to a directory you own")
    return _check("workspace", "workspace writable", True, str(VAR_DIR))


def check_shared_engine() -> Check:
    label = "shared engine (optional)"
    try:
        from simvltanea.browser import browser_runtime
        engine = browser_runtime.resolve_shared_engine()
    except Exception as error:  # informational probe: any failure means "not available", never a crash
        first = (str(error).strip().splitlines() or [type(error).__name__])[0].split(". ")[0]
        return _check("shared-engine", label, False, f"not available: {first}",
                      "optional; place the time-moment-brief checkout beside this repository to enable it", required=False)
    return _check("shared-engine", label, True, str(engine.root), required=False)


def run_checks() -> list[Check]:
    return [check_python(), check_tool("ffmpeg"), check_tool("ffprobe"), *check_encoders(),
            check_workspace(), check_shared_engine()]


def format_report(checks: list[Check]) -> str:
    lines = [f"independent-loop-compositor {get_version()} doctor"]
    width = max(len(check["label"]) for check in checks)
    for check in checks:
        marker = {"ok": "ok", "fail": "FAIL", "info": "info"}[check["status"]]
        lines.append(f"{marker:<4}  {check['label']:<{width}}  {check['detail']}")
        if check["remedy"]:
            lines.append(f"      {'fix' if check['status'] == 'fail' else 'note'}: {check['remedy']}")
    failed = [check for check in checks if check["status"] == "fail"]
    lines.append(f"{len(failed)} required check(s) failed" if failed else "all required checks passed")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="independent-loop-compositor doctor",
        description="Check Python, FFmpeg, encoders and workspace; exit 1 if a required check fails.",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    checks = run_checks()
    passed = not any(check["status"] == "fail" for check in checks)
    if args.json:
        print(json.dumps({"version": get_version(), "ok": passed, "checks": checks}, indent=2))
    else:
        print(format_report(checks))
    return 0 if passed else 1
