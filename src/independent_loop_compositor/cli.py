"""Functionally named commands delegating to the established implementation."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="independent-loop-compositor",
        description="Author-independent preview and rendering of simultaneous video loops.",
    )
    parser.add_argument("command", choices=("preview", "render"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER,
                        help="Arguments for the selected command; use COMMAND --help")
    args = parser.parse_args(argv)
    if args.command == "preview":
        from simvltanea.browser import browser_runtime
        run = browser_runtime.main
    else:
        from simvltanea.rendering import render_triptych
        run = render_triptych.main
    previous_argv = sys.argv
    try:
        sys.argv = [f"independent-loop-compositor {args.command}", *args.arguments]
        return run() or 0
    finally:
        sys.argv = previous_argv
