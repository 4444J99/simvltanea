"""Static guards that keep the Python tools portable to Windows as well as macOS and Linux.

CI runs on Linux only, so these tests read the audited sources (every non-test ``.py`` file
under ``src/`` and ``tools/``, apart from the files another lane owns) and fail when a pattern
that breaks on Windows comes back. See docs/authoring/WINDOWS_AND_MAC.md.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import unittest
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Owned by another lane (Live Photos tagger geometry); audited by reading only.
NOT_AUDITED = {"tools/media/tag_clips.py", "tools/media/video_geometry.py"}
# Modules that exist only on POSIX (or only on Windows) must be imported inside a try/except ImportError.
PLATFORM_MODULES = {"fcntl", "termios", "pwd", "grp", "resource", "msvcrt", "winreg"}
# os.rename keeps its no-clobber meaning only where the destination must not exist (see the functions).
OS_RENAME_ALLOWED = {
    ("src/simvltanea/browser/browser_runtime.py", "_rename_preview"),  # Windows no-clobber publish
    ("src/simvltanea/browser/browser_runtime.py", "_retain_preview"),  # target is inside a fresh mkdtemp
}
# relpath results become site URLs or project JSON; they must use "/" on every platform.
RELPATH_ALLOWED = {"tools/media/import_photos.py"}  # macOS-only Photos importer
# The CLI render, proxy and doctor path decodes FFmpeg output as UTF-8, not the Windows ANSI code page.
UTF8_SUBPROCESS_FILES = (
    "src/independent_loop_compositor/doctor.py",
    "src/independent_loop_compositor/proxy.py",
    "src/simvltanea/authoring/composition.py",
    "src/simvltanea/rendering/render_triptych.py",
)
POSIX_ONLY_CALLS = {("os", "fork"), ("os", "getuid"), ("os", "geteuid"), ("os", "system"), ("os", "popen"),
                    ("os", "killpg"), ("os", "setsid")}
POSIX_ONLY_SIGNALS = {"SIGKILL", "SIGSTOP", "SIGHUP", "SIGUSR1", "SIGUSR2"}
POSIX_ONLY_PATHS = ("/dev/null", "/tmp/")


def audited_files() -> list[Path]:
    files = []
    for base in ("src", "tools"):
        for path in sorted((ROOT / base).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative not in NOT_AUDITED and not path.name.startswith("test_"):
                files.append(path)
    return files


@cache
def parsed(path: Path) -> ast.Module:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]
    return tree


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def ancestors(node: ast.AST):
    while (node := getattr(node, "parent", None)) is not None:
        yield node


def enclosing_function(node: ast.AST) -> str | None:
    return next((a.name for a in ancestors(node) if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))), None)


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def is_self_rooted(node: ast.expr) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id == "self"


def text_mode_without_encoding(call: ast.Call) -> bool:
    """True for a text-mode open/read_text/write_text that leaves the encoding to the platform."""
    func = call.func
    if keyword(call, "encoding") is not None:
        return False
    if isinstance(func, ast.Name) and func.id == "open":
        mode = call.args[1] if len(call.args) > 1 else keyword(call, "mode")
    elif isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
        return len(call.args) < (2 if func.attr == "write_text" else 1)
    elif isinstance(func, ast.Attribute) and func.attr == "open" and not is_self_rooted(func.value):
        if isinstance(func.value, ast.Name) and func.value.id in {"os", "io", "tarfile", "zipfile", "gzip", "wave",
                                                                   "Image", "webbrowser"}:
            return False
        mode = call.args[0] if call.args else keyword(call, "mode")
        if mode is None:
            return False  # a bare .open() is ambiguous (not always a path); text opens here name a mode
    else:
        return False
    if mode is None:
        return True
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value


def calls(path: Path):
    return (node for node in ast.walk(parsed(path)) if isinstance(node, ast.Call))


class PortableSourceTests(unittest.TestCase):
    def test_audited_tree_is_not_empty(self):
        self.assertGreater(len(audited_files()), 50)

    def test_text_io_names_its_encoding(self):
        found = [f"{relative(path)}:{call.lineno}" for path in audited_files() for call in calls(path)
                 if text_mode_without_encoding(call)]
        self.assertEqual(found, [], "text I/O without encoding='utf-8' (Windows defaults to the ANSI code page)")

    def test_platform_only_modules_are_imported_inside_a_guard(self):
        found = []
        for path in audited_files():
            for node in ast.walk(parsed(path)):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = {node.module.split(".")[0]}
                else:
                    continue
                if not names & PLATFORM_MODULES:
                    continue
                guarded = any(isinstance(a, ast.Try) and any(
                    isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError")
                    for h in a.handlers) for a in ancestors(node))
                if not guarded:
                    found.append(f"{relative(path)}:{node.lineno}")
        self.assertEqual(found, [], "unguarded import of a platform-only module")

    def test_no_posix_only_process_calls_signals_or_paths(self):
        found = []
        for path in audited_files():
            for node in ast.walk(parsed(path)):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    if (node.value.id, node.attr) in POSIX_ONLY_CALLS or (
                            node.value.id == "signal" and node.attr in POSIX_ONLY_SIGNALS):
                        found.append(f"{relative(path)}:{node.lineno}:{node.value.id}.{node.attr}")
                elif isinstance(node, ast.Call) and isinstance(keyword(node, "shell"), ast.Constant) \
                        and keyword(node, "shell").value is True:
                    found.append(f"{relative(path)}:{node.lineno}:shell=True")
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and node.value.startswith(POSIX_ONLY_PATHS):
                    found.append(f"{relative(path)}:{node.lineno}:{node.value}")
        self.assertEqual(found, [])

    def test_renames_that_may_overwrite_use_replace(self):
        found = []
        for path in audited_files():
            for call in calls(path):
                func = call.func
                if not (isinstance(func, ast.Attribute) and func.attr == "rename"):
                    continue
                is_os = isinstance(func.value, ast.Name) and func.value.id == "os"
                if is_os and (relative(path), enclosing_function(call)) in OS_RENAME_ALLOWED:
                    continue
                found.append(f"{relative(path)}:{call.lineno}")
        self.assertEqual(found, [], "rename fails on Windows when the target exists; use os.replace/Path.replace")

    def test_relpath_results_use_forward_slashes(self):
        found = []
        for path in audited_files():
            if relative(path) in RELPATH_ALLOWED:
                continue
            for call in calls(path):
                func = call.func
                if not (isinstance(func, ast.Attribute) and func.attr == "relpath"
                        and isinstance(func.value, ast.Attribute) and func.value.attr == "path"):
                    continue
                parent = getattr(call, "parent", None)
                outer = getattr(parent, "parent", None)
                normalised = (isinstance(parent, ast.Attribute) and parent.attr == "replace"
                              and isinstance(outer, ast.Call) and len(outer.args) == 2
                              and ast.unparse(outer.args[0]) == "os.sep"
                              and isinstance(outer.args[1], ast.Constant) and outer.args[1].value == "/")
                if not normalised:
                    found.append(f"{relative(path)}:{call.lineno}")
        self.assertEqual(found, [], 'os.path.relpath(...) must be followed by .replace(os.sep, "/")')

    def test_cli_subprocess_output_is_decoded_as_utf8(self):
        found = []
        for name in UTF8_SUBPROCESS_FILES:
            for call in calls(ROOT / name):
                text = keyword(call, "text")
                if isinstance(text, ast.Constant) and text.value is True and keyword(call, "encoding") is None:
                    found.append(f"{name}:{call.lineno}")
        self.assertEqual(found, [], "subprocess text=True without encoding='utf-8'")

    def test_native_libc_is_loaded_only_on_platforms_that_have_it(self):
        path = ROOT / "src/simvltanea/browser/browser_runtime.py"
        found = []
        for call in calls(path):
            if ast.unparse(call.func) == "ctypes.CDLL":
                if not any(isinstance(a, ast.If) and "sys.platform" in ast.unparse(a.test) for a in ancestors(call)):
                    found.append(call.lineno)
        self.assertEqual(found, [], "ctypes.CDLL(None) raises on Windows; load it inside a sys.platform branch")


class MacOnlyToolTests(unittest.TestCase):
    def test_photos_export_fails_with_one_plain_sentence_without_macos(self):
        # A child process hides fcntl (as on Windows) so the module seen by other suites stays untouched.
        script = (
            "import sys\n"
            "sys.modules['fcntl'] = None\n"
            "import tools.media.export_photos_album as exporter\n"
            "sys.platform = 'win32'\n"
            "for attempt in (lambda: exporter.preflight(()), lambda: exporter.acquire_lock(None)):\n"
            "    try:\n"
            "        attempt()\n"
            "    except SystemExit as stop:\n"
            "        print(stop.code)\n"
        )
        environment = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "src")]),
                       "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True,
                              text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        messages = done.stdout.splitlines()
        self.assertEqual(len(messages), 2, done.stdout)
        for message in messages:
            self.assertTrue(message.startswith("Photos export needs macOS"), message)
            self.assertIn("on Windows", message)
            self.assertIn("folder", message)
            self.assertEqual(message.count(". "), 0, "one sentence")

    def test_folder_import_copies_by_default_on_windows(self):
        from tools.media import import_folder
        self.assertEqual(import_folder.DEFAULT_MODE, "copy" if os.name == "nt" else "symlink")


class PlatformGuideTests(unittest.TestCase):
    def test_guide_exists_and_is_linked_from_the_readme(self):
        guide = ROOT / "docs/authoring/WINDOWS_AND_MAC.md"
        text = guide.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# "))
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
        for needle in ("winget install Gyan.FFmpeg", "brew install ffmpeg", "py -3 -m", "$env:PYTHONPATH"):
            self.assertIn(needle, text)
        self.assertIn("docs/authoring/WINDOWS_AND_MAC.md", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
