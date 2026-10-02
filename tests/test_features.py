"""Expose co-located suites to historical unittest discovery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tests(loader, suite, pattern):
    for base in (ROOT / "src" / "simvltanea", ROOT / "tools"):
        for path in sorted(base.rglob(pattern or "test_*.py")):
            relative = path.relative_to(ROOT / "src" if path.is_relative_to(ROOT / "src") else ROOT)
            name = ".".join(relative.with_suffix("").parts)
            suite.addTests(loader.loadTestsFromName(name))
    return suite
