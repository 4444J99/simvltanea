"""The generated index must not silently omit or rewrite historical source plans."""
from pathlib import Path
import tempfile
import unittest
from tools.verification.sync_plan_index import render


class PlanIndexTests(unittest.TestCase):
    def test_deterministic_order_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("2026-10-03-second", "2026-09-01-first"):
                (root / (name + ".md")).write_text("# Recorded | title\n\nImmutable text.\n")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            text = render(root, {"proofs": "custom/proofs"})
            self.assertEqual(text, render(root, {"proofs": "custom/proofs"}))
            self.assertLess(text.index("2026-09-01"), text.index("2026-10-03"))
            self.assertIn("custom/proofs", text)
            self.assertIn(r"Recorded \| title", text)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_unsupported_date_or_filename_cannot_disappear(self):
        for name in ("2026-02-31-bad.md", "2026-10-03-bad_name.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); (root / name).write_text("# Title\n")
                with self.assertRaises(ValueError):
                    render(root, {})

    def test_missing_title_is_not_invented(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "2026-10-03-title.md").write_text("no heading\n")
            with self.assertRaises(ValueError):
                render(root, {})

    def test_ignores_its_own_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "INDEX.md").write_text("# Never a dated plan\n")
            self.assertNotIn("Never a dated plan", render(root, {}))


if __name__ == "__main__":
    unittest.main()
