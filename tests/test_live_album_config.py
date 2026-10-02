"""Full-album imports must retain explicit preview overrides."""
import json
import unittest
from pathlib import Path

from tools.editions.build_edition import import_command


class LiveAlbumConfigTests(unittest.TestCase):
    def test_full_album_and_preview_override(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "editions/registry.json").read_text())
        edition = next(e for e in payload["editions"] if e["slug"] == "simvl-live")
        args = (root / "var/work/live-test.json", root / "var/samples/live-test", False, True)
        command = import_command(payload, edition, *args)
        self.assertIn("--all-local", command)
        self.assertIn("--live-photos-only", command)
        self.assertIn("--album-via-photos-app", command)
        self.assertNotIn("--limit", command)
        edition["source"]["limit"] = 12
        preview = import_command(payload, edition, *args)
        self.assertNotIn("--all-local", preview)
        self.assertEqual(preview[preview.index("--limit") + 1], "12")


if __name__ == "__main__":
    unittest.main()
