"""Functionally named commands delegating to the established implementation."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from .version import get_version

PROGRAM = "independent-loop-compositor"
DEBUG_VARIABLE = "SIMVLTANEA_DEBUG"
FFMPEG_TOOLS = ("ffmpeg", "ffprobe")
STDERR_LINES = 12
DOCTOR_HINT = f"Run `{PROGRAM} doctor` to check prerequisites."
_MISSING_TOOL = re.compile(r"No such file or directory: '(ffmpeg|ffprobe)'")

COMMANDS = {
    "preview": "compile a composition state into a local browser preview",
    "render": "render a composition state (or exported clips) to MP4 with FFmpeg",
    "doctor": "check Python, FFmpeg, encoders and the workspace",
    "proxy": "make small, browser-playable H.264 proxies of phone clips",
}
EPILOG = (
    "commands:\n"
    + "\n".join(f"  {name:<8}{summary}" for name, summary in COMMANDS.items())
    + f"\n\nUse `{PROGRAM} COMMAND --help` for the options of one command.\n\n"
    "example:\n"
    f"  {PROGRAM} doctor\n"
    f"  {PROGRAM} render --state composition.json --orientation landscape\n"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Author-independent preview and rendering of simultaneous video loops.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {get_version()}")
    parser.add_argument("command", choices=tuple(COMMANDS), metavar="COMMAND",
                        help="one of: " + ", ".join(COMMANDS))
    parser.add_argument("arguments", nargs=argparse.REMAINDER,
                        help="Arguments for the selected command; use COMMAND --help")
    return parser


def _error(message: str) -> int:
    print(f"{PROGRAM}: error: {message}", file=sys.stderr)
    return 1


def _process_failure(error: subprocess.CalledProcessError) -> str:
    """Name the failed tool and show its own last stderr lines, never the command line."""
    command = error.cmd if isinstance(error.cmd, (list, tuple)) and error.cmd else [str(error.cmd)]
    message = f"{Path(str(command[0])).name} failed with exit status {error.returncode}"
    text = error.stderr if isinstance(error.stderr, str) else ""
    tail = "\n".join([line for line in text.strip().splitlines() if line.strip()][-STDERR_LINES:])
    return f"{message}:\n{tail}" if tail else message


def _missing_tool(error: OSError) -> str | None:
    name = Path(str(error.filename)).name if error.filename else ""
    return name if name in FFMPEG_TOOLS else None


def _string_exit(message: str) -> str:
    """Delegated commands exit with a message; add the doctor pointer for a missing tool."""
    if _MISSING_TOOL.search(message):
        return f"{message}\n{DOCTOR_HINT}"
    return message


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "doctor":
        from .doctor import main as run_doctor
        return run_doctor(args.arguments)
    if args.command == "preview":
        from simvltanea.browser import browser_runtime
        run = browser_runtime.main
    elif args.command == "proxy":
        from .proxy import main as run
    else:
        from simvltanea.rendering import render_triptych
        run = render_triptych.main
    debug = os.environ.get(DEBUG_VARIABLE) == "1"
    previous_argv = sys.argv
    try:
        sys.argv = [f"{PROGRAM} {args.command}", *args.arguments]
        return run() or 0
    except SystemExit as exit_request:
        # Numeric exits (argparse usage errors, --help) already printed their own text.
        if debug or not isinstance(exit_request.code, str):
            raise
        return _error(_string_exit(exit_request.code))
    except Exception as error:
        if debug:
            raise
        from .authoring import StateError
        if isinstance(error, StateError):
            return _error(str(error))
        if isinstance(error, subprocess.CalledProcessError):
            return _error(_process_failure(error))
        if isinstance(error, OSError):
            tool = _missing_tool(error)
            if tool and isinstance(error, FileNotFoundError):
                return _error(f"{tool} not found on PATH. {DOCTOR_HINT}")
            detail = f"{error.strerror}: {error.filename}" if error.strerror and error.filename else str(error)
            return _error(detail)
        raise
    finally:
        sys.argv = previous_argv
