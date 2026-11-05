"""Public site text must not reveal the build machine's absolute paths."""
from pathlib import Path
import tempfile
import unittest

from tools.verification.verify_public_site import private_path_fragments, scan_text_files


class PrivatePathScanTests(unittest.TestCase):
    def scan(self, name: str, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / name).write_text(text, encoding="utf-8")
            errors: list[str] = []
            scan_text_files(site, errors)
            # Report only the file-relative part; the temporary root is not under test.
            return [error.split(": ", 1)[1] for error in errors]

    def test_every_private_root_is_rejected_in_public_text(self):
        cases = {
            "/Users/": "<p>/Users/alice/proofs</p>",
            "/Volumes/": "<p>/Volumes/Archive/proofs</p>",
            "/private/": 'note = "/private/tmp/site";',
            "/home/": "Looked at /home/runner/work/time-moment-brief\n",
            "/var/": "Looked at /var/folders/xy/proofs\n",
            "/tmp/": '{"root": "/tmp/build/site"}',
            "C:\\": '{"root": "C:\\\\Users\\\\alice\\\\site"}',
            "C:/": "<a href='C:/Users/alice/site/index.html'>local</a>",
            "d:\\": "Looked at d:\\builds\\site\n",
            "/volumes/": '<p>"/volumes/archive/proofs"</p>',
            "/opt/": 'cache = "/opt/build/site";',
            "/root/": "Looked at /root/work/site\n",
            "/mnt/": '{"root": "/mnt/disk/site"}',
            "/srv/": "<p>/srv/www/site</p>",
            "/__w/": 'path = "/__w/repo/repo/site";',
        }
        for fragment, text in cases.items():
            for suffix in (".html", ".txt", ".json", ".js"):
                with self.subTest(fragment=fragment, suffix=suffix):
                    errors = self.scan("page" + suffix, text)
                    self.assertTrue(errors, f"{fragment!r} leaked through a {suffix} file")
                    self.assertTrue(all("private" in error for error in errors), errors)

    def test_file_urls_to_drive_paths_are_rejected(self):
        self.assertEqual(private_path_fragments("<a href=\"file:///C:/site\">x</a>"),
                         ["file:///C:"])

    def test_staged_preview_unavailable_note_in_old_form_is_rejected(self):
        """The message format the preview used to publish must not pass."""
        leaked = ("shared engine not found. Looked at the documented sibling layout only:\n"
                  "  /Volumes/Archive4T/Projects/time-moment-brief\n"
                  "  /private/var/folders/xy/time-moment-brief\n")
        errors = self.scan("shared-engine-unavailable.txt", leaked)
        self.assertEqual(sorted(errors), sorted([
            "contains private absolute path '/Volumes/'",
            "contains private absolute path '/private/'",
        ]))

    def test_relative_paths_urls_and_code_are_public(self):
        public = "\n".join((
            '<a href="https://example.org/home/tmp/var/">home</a>',
            '<script src="../var/site/runtime.js"></script>',
            "See var/site/index.html and simvltanea/tmp/notes.",
            "const pick = ready?a:/x/.test(s); const re = {a:/re/};",
            "https://example.org:8080/private/page",
            '<a href="https://example.org/opt/root/mnt/srv/__w/volumes/">dirs</a>',
            "See ../opt/site, ./root/notes and mnt/srv/index.html.",
            "Time 12:30/14:00 and ratio 1:/2.",
            "Shared engine not included in this build (not found at build time); "
            "loops play with their authored framing.",
        ))
        self.assertEqual(private_path_fragments(public), [])
        self.assertEqual(self.scan("index.html", public), [])

    def test_binary_media_suffixes_are_not_scanned_as_text(self):
        self.assertEqual(self.scan("clip.mp4", "/Volumes/Archive/clip"), [])


if __name__ == "__main__":
    unittest.main()
