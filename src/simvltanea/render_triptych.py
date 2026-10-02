"""Compatibility entry point for :mod:`simvltanea.rendering.render_triptych`."""
import importlib
import runpy
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    runpy.run_module("simvltanea.rendering.render_triptych", run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module("simvltanea.rendering.render_triptych")
