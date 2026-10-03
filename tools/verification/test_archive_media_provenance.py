"""Bind the retained N=7 studies' catalogue entry to its unchanged media."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
RELATIVE_MEDIA = "chatgpt/media/MEDA-002_visual-form-canon-7-portrait.mp4"
MEDIA = ROOT / "archive" / RELATIVE_MEDIA
EXPECTED_SHA256 = "a5b117f704863d27e6db7bf30f40c70a9ad0cda84bb74b121c48541f5a4d6f46"
EXPECTED_FORMAT = "MP4 Video (H.264, 360x640, 6 seconds; no audio stream)"


class ArchiveMediaProvenanceTests(unittest.TestCase):
    """Check the catalogue against the unchanged, experimental portrait media."""
    identity = "MEDA-002"
    relative_media = RELATIVE_MEDIA
    expected_sha256 = EXPECTED_SHA256
    expected_format = EXPECTED_FORMAT
    expected_bytes = 517743
    width, height = 360, 640
    orientation = "vertical"

    def setUp(self):
        """Isolate the selected catalogue entry before each assertion."""
        manifest = (ROOT / "archive" / "PROJECT_MANIFEST.md").read_text(encoding="utf-8")
        entries = re.findall(
            rf"^### \[`{self.identity}`\].*?(?=^---|\Z)", manifest, re.MULTILINE | re.DOTALL
        )
        self.assertEqual(len(entries), 1, f"{self.identity} must have one catalogue entry")
        self.entry = entries[0]
        self.media = ROOT / "archive" / self.relative_media

    def test_manifest_matches_pinned_metadata(self):
        """Require the corrected metadata and retain the experimental boundary."""
        metadata = re.findall(
            r"^- \*\*Size\*\*: ([\d,]+) bytes \| \*\*SHA-256\*\*: `([0-9a-f]{64})`$",
            self.entry,
            re.MULTILINE,
        )
        self.assertEqual(metadata, [(f"{self.expected_bytes:,}", self.expected_sha256)])
        self.assertIn(f"- **Format**: {self.expected_format}\n", self.entry)
        self.assertIn("`#experimental-7-loop`", self.entry)
        self.assertIn(f"experimental $N=7$ {self.orientation} layout", self.entry)

    def test_manifest_uses_portable_file_links(self):
        """Require both catalogue links to address the repository-relative file."""
        links = re.findall(r"\]\(([^)]+)\)", self.entry)
        self.assertEqual(links, [self.relative_media, self.relative_media])

    def test_retained_media_bytes(self):
        """Reject a replaced, modified, missing or symlinked media artifact."""
        self.assertFalse(self.media.is_symlink())
        payload = self.media.read_bytes()
        self.assertEqual(len(payload), self.expected_bytes)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), self.expected_sha256)

    def test_retained_media_streams(self):
        """Probe the actual file for its sole video stream and six-second duration."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,codec_name,width,height:format=duration",
                "-of", "json", str(self.media),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        probe = json.loads(result.stdout)
        self.assertEqual(
            probe["streams"],
            [{"codec_name": "h264", "codec_type": "video", "width": self.width, "height": self.height}],
        )
        self.assertAlmostEqual(float(probe["format"]["duration"]), 6.0, places=3)

    def test_retained_media_decodes(self):
        """Decode the complete retained video, failing on any FFmpeg error."""
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(self.media),
                "-map", "0:v:0", "-f", "null", "-",
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )


class LandscapeMediaProvenanceTests(ArchiveMediaProvenanceTests):
    """Apply the same actual-byte, stream and catalogue gates to MEDA-003."""
    identity = "MEDA-003"
    relative_media = "chatgpt/media/MEDA-003_visual-form-canon-7-landscape.mp4"
    expected_sha256 = "3f7dad91e3313541744231b16559733e45c4c34b7787d3e05d3de6b04c3d924e"
    expected_format = "MP4 Video (H.264, 640x360, 6 seconds; no audio stream)"
    expected_bytes = 537344
    width, height = 640, 360
    orientation = "horizontal"


if __name__ == "__main__":
    unittest.main()
