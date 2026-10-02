"""Compatibility entry point for :mod:`simvltanea.authoring.composition_model`."""
import importlib
import runpy
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    runpy.run_module("simvltanea.authoring.composition_model", run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module("simvltanea.authoring.composition_model")
