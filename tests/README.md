# Test discovery

Regression tests live beside their owning features in `src/simvltanea/` and
`tools/`; remaining repository integration tests live here. Install the package
with `python3 -m pip install -e ".[verification]"`, then run `python3 -m pytest`.
Pytest uses importlib mode and only the repository and src import roots.

The historical `python3 -m unittest discover -s tests` command also works with
the installed package. `test_features.py` loads co-located suites by qualified
module name; tests use qualified imports without mutating sys.path.
