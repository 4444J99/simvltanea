"""Layout guard: declared bleed passes, interior overlap fails, presets and strict files (seam test 4)."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from simvltanea.authoring import strips_layouts
from tools.verification import verify_layouts as guard

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "layouts"
PRESET = ROOT / "examples" / "layout-presets" / "strips.json"


def run(*argv: str) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output), redirect_stderr(output):
        code = guard.main(list(argv))
    return code, output.getvalue()


class LayoutGuardTests(unittest.TestCase):
    def test_oversized_integer_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.json"
            path.write_text('{"format": "simvltanea.layout-pair/1", "count": ' + "1" * 5000 + "}")
            errors, summary = guard.validate_file(path)
            self.assertEqual(summary, "")
            self.assertEqual(len(errors), 1, errors)
            self.assertTrue(errors[0].startswith(f"{path}: cannot read JSON: "), errors[0])

    def test_legacy_duplicate_keys_are_rejected(self):
        # The first "2" overlaps and the second is valid: keeping only the last value would hide it.
        shadowed = ('{"2": {"portrait": [[0,0,1,0.6],[0,0.5,1,0.5]], "landscape": [[0,0,0.5,1],[0.5,0,0.5,1]]}, '
                    '"2": {"portrait": [[0,0,1,0.5],[0,0.5,1,0.5]], "landscape": [[0,0,0.5,1],[0.5,0,0.5,1]]}}')
        repeated = ('{"2": {"portrait": [[0,0,1,0.6],[0,0.5,1,0.5]], "portrait": [[0,0,1,0.5],[0,0.5,1,0.5]], '
                    '"landscape": [[0,0,0.5,1],[0.5,0,0.5,1]]}}')
        with tempfile.TemporaryDirectory() as tmp:
            for name, text, key in (("shadowed.json", shadowed, "2"), ("repeated.json", repeated, "portrait")):
                with self.subTest(name=name):
                    path = Path(tmp) / name
                    path.write_text(text)
                    self.assertEqual(guard.validate_file(path), ([f"{path}: duplicate JSON key: {key} [json]"], ""))

    def test_literal_at_names_are_not_path_references(self):
        data = json.loads((CORPUS / "valid/strips-1-pair.json").read_text())
        data["portrait"]["name"] = "@portrait"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "at-name-pair.json"
            path.write_text(json.dumps(data))
            self.assertEqual(guard.validate_file(path), ([], "pair: count 1"))

    def test_declared_bleed_is_accepted(self):
        for name in ("valid/strips-5-pair.json", "valid/grid-4-bleed-pair.json"):
            with self.subTest(name=name):
                data = json.loads((CORPUS / name).read_text())
                self.assertGreater(data["portrait"]["presentation"]["overlap_px"], 0)
                code, output = run("--layouts", str(CORPUS / name))
                self.assertEqual(code, 0, output)
                self.assertIn("layouts ok", output)

    def test_interior_overlap_is_rejected_even_with_declared_bleed(self):
        data = json.loads((CORPUS / "invalid/pair-interior-overlap.json").read_text())
        self.assertEqual(data["portrait"]["presentation"]["overlap_px"], 2)
        code, output = run("--layouts", str(CORPUS / "invalid/pair-interior-overlap.json"))
        self.assertEqual(code, 1)
        self.assertIn("overlapping/occluded panels are not supported", output)
        self.assertIn("[overlap]", output)
        self.assertIn("pair-interior-overlap.json, count 3, portrait, cell 1", output)
        # The legacy count map goes through the same validator.
        legacy = {"2": {"portrait": [[0, 0, 1, 0.6], [0, 0.5, 1, 0.5]],
                        "landscape": [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]}}
        errors = guard.validate_payload(legacy, Path("legacy.json"))
        self.assertEqual(len(errors), 1)
        self.assertIn("legacy.json, count 2, portrait, cell 1", errors[0])
        self.assertIn("[overlap]", errors[0])
        touching = {"2": {"portrait": [[0, 0, 1, 0.5], [0, 0.5, 1, 0.5]],
                          "landscape": [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]}}
        self.assertEqual(guard.validate_payload(touching, Path("legacy.json")), [])

    def test_bleed_bounds_through_the_guard(self):
        for name in ("pair-overlap-px-9", "pair-overlap-px-fraction", "pair-overlap-px-no-shared-edge"):
            with self.subTest(name=name):
                code, output = run("--layouts", str(CORPUS / f"invalid/{name}.json"))
                self.assertEqual(code, 1)
                self.assertIn(f"{name}.json", output)
                self.assertIn("overlap_px", output)

    def test_presets(self):
        code, output = run("--presets", str(PRESET))
        self.assertEqual(code, 0, output)
        self.assertIn("preset strips: counts 1..12", output)
        code, output = run("--presets", str(CORPUS / "valid/strips-custom-preset.json"))
        self.assertEqual(code, 0, output)
        code, output = run("--presets", str(CORPUS / "valid/strips-5-pair.json"))
        self.assertEqual(code, 1)
        self.assertIn("[format]", output)
        code, output = run("--presets", str(CORPUS / "invalid/preset-unknown-key.json"))
        self.assertEqual(code, 1)
        self.assertIn(str(CORPUS / "invalid/preset-unknown-key.json"), output)
        self.assertIn("[unknown-key]", output)

    def test_examples_and_default(self):
        for argv in (("--examples",), ()):
            code, output = run(*argv)
            self.assertEqual(code, 0, output)
            self.assertIn("layouts ok", output)
            self.assertIn("counts: ['2', '3']", output)
        code, output = run("--examples", "--json")
        self.assertEqual(json.loads(output)["ok"], True)

    def test_strict_failures_name_the_file(self):
        code, output = run("--layouts", str(CORPUS / "invalid/malformed.json"))
        self.assertEqual(code, 1)
        self.assertIn(str(CORPUS / "invalid/malformed.json"), output)
        code, output = run("--layouts", str(CORPUS / "invalid/absent.json"))
        self.assertEqual(code, 1)
        self.assertIn("absent.json: missing layout file", output)
        code, output = run("--layouts", str(CORPUS / "invalid/pair-gap.json"), "--json")
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertIn("[full-bleed-coverage]", payload["errors"][0])
        with tempfile.TemporaryDirectory() as tmp:
            ambient = Path(tmp) / "layouts.json"
            ambient.write_text("{}")
            with patch.object(guard, "AMBIENT_OVERRIDE", ambient):
                code, output = run("--examples")
            self.assertEqual(code, 1)
            self.assertIn(str(ambient), output)
            self.assertIn("--layouts FILE", output)

    def test_validate_file_accepts_generated_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in (1, 7, 12):
                path = Path(tmp) / f"strips-{n}.json"
                path.write_text(json.dumps({"format": "simvltanea.layout-pair/1", "count": n, **strips_layouts(n)}))
                self.assertEqual(guard.validate_file(path), ([], f"pair: count {n}"))


if __name__ == "__main__":
    unittest.main()
