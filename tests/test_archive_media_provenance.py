"""Bind the retained portrait study's catalogue entry to its unchanged media."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RELATIVE_MEDIA = "chatgpt/media/MEDA-002_visual-form-canon-7-portrait.mp4"
MEDIA = ROOT / "archive" / RELATIVE_MEDIA
EXPECTED_SHA256 = "a5b117f704863d27e6db7bf30f40c70a9ad0cda84bb74b121c48541f5a4d6f46"
EXPECTED_FORMAT = "MP4 Video (H.264, 360x640, 6 seconds; no audio stream)"


class ArchiveMediaProvenanceTests(unittest.TestCase):
    def setUp(self):
        manifest = (ROOT / "archive" / "PROJECT_MANIFEST.md").read_text(encoding="utf-8")
        entries = re.findall(
            r"^### \[`MEDA-002`\].*?(?=^---|\Z)", manifest, re.MULTILINE | re.DOTALL
        )
        self.assertEqual(len(entries), 1, "MEDA-002 must have one catalogue entry")
        self.entry = entries[0]

    def test_manifest_matches_pinned_metadata(self):
        metadata = re.findall(
            r"^- \*\*Size\*\*: ([\d,]+) bytes \| \*\*SHA-256\*\*: `([0-9a-f]{64})`$",
            self.entry,
            re.MULTILINE,
        )
        self.assertEqual(metadata, [("517,743", EXPECTED_SHA256)])
        self.assertIn(f"- **Format**: {EXPECTED_FORMAT}\n", self.entry)
        self.assertIn("`#experimental-7-loop`", self.entry)
        self.assertIn("experimental $N=7$ vertical layout", self.entry)

    def test_manifest_uses_portable_file_links(self):
        links = re.findall(r"\]\(([^)]+)\)", self.entry)
        self.assertEqual(links, [RELATIVE_MEDIA, RELATIVE_MEDIA])

    def test_retained_media_bytes(self):
        self.assertFalse(MEDIA.is_symlink())
        payload = MEDIA.read_bytes()
        self.assertEqual(len(payload), 517743)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), EXPECTED_SHA256)

    def test_retained_media_streams(self):
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,codec_name,width,height:format=duration",
                "-of", "json", str(MEDIA),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        probe = json.loads(result.stdout)
        self.assertEqual(
            probe["streams"],
            [{"codec_name": "h264", "codec_type": "video", "width": 360, "height": 640}],
        )
        self.assertAlmostEqual(float(probe["format"]["duration"]), 6.0, places=3)

    def test_retained_media_decodes(self):
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(MEDIA),
                "-map", "0:v:0", "-f", "null", "-",
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )


if __name__ == "__main__":
    unittest.main()
