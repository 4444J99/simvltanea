"""Compatibility discovery for the co-located regression suites."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SUITES = ("src/simvltanea/authoring", "src/simvltanea/browser", "src/simvltanea/rendering", "tools/editions", "tools/verification")
for directory in (".", "src", "src/simvltanea", "tools/media", "tools/preservation", "tools/publishing", "tools/editions", "tools/verification"):
    sys.path.insert(0, str(ROOT / directory))

def load_tests(loader, tests, pattern):
    for directory in SUITES:
        tests.addTests(loader.discover(str(ROOT / directory), pattern or "test_*.py", top_level_dir=str(ROOT)))
    return tests
