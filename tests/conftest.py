import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "src" / "simvltanea"
TOOLS = tuple(ROOT / "tools" / name for name in (
    "editions", "media", "preservation", "publishing", "verification"
))
TESTS = ROOT / "tests"

for p in (ROOT, ROOT / "src", CORE, *TOOLS, TESTS, *(TESTS / group for group in ("browser", "render", "model", "editions", "governance"))):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
