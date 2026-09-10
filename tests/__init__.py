import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "core"
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"

for p in (ROOT, CORE, TOOLS, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
