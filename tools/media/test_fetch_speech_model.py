"""Exercise the model fetcher against a local ``http.server``: never the real network, never a real model."""
import contextlib
import hashlib
import http.server
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

from tools.media import fetch_speech_model as fetcher

PAYLOAD = bytes(range(256)) * 400  # 102 400 bytes standing in for the model
TREE_PATH = f"/api/models/{fetcher.REPO}/tree/main"
FILE_PATH = f"/{fetcher.REPO}/resolve/main/{fetcher.NAME}"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "stub"

    def log_message(self, *args):  # keep the test output clean
        pass

    def do_GET(self):
        state = self.server.state
        state["requests"].append((self.path, self.headers.get("Range")))
        if self.path == TREE_PATH:
            body = json.dumps(state["tree"]).encode()
            self.send_response(200)
        elif self.path == FILE_PATH:
            body, start = state["served"], 0
            ranged = self.headers.get("Range")
            if ranged and state["honour_range"]:
                start = int(ranged.split("=")[1].split("-")[0])
                body = body[start:]
                self.send_response(206)
            else:
                self.send_response(200)
        else:
            self.send_error(404)
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FetchCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = pathlib.Path(self._tmp.name).resolve() / "models"
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.state = {"served": PAYLOAD, "honour_range": True, "requests": [],
                             "tree": [{"path": "other.bin"},
                                      {"path": fetcher.NAME, "lfs": {"size": len(PAYLOAD),
                                                                      "oid": hashlib.sha256(PAYLOAD).hexdigest()}}]}
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def run_main(self, *extra, dest=None, endpoint=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fetcher.main(["--dest", str(dest or self.dest), "--endpoint", endpoint or self.endpoint, *extra])
        self.stdout, self.stderr = out.getvalue(), err.getvalue()
        return code


class FetchTests(FetchCase):
    def test_a_matching_download_is_verified_and_kept(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.dest / fetcher.NAME).read_bytes(), PAYLOAD)
        self.assertFalse((self.dest / (fetcher.NAME + ".part")).exists())
        self.assertIn("verified", self.stdout)
        self.assertEqual(self.run_main(), 0)  # second run: already present, still verified
        self.assertIn("already present", self.stdout)
        self.assertEqual(sum(1 for path, _ in self.server.state["requests"] if path == FILE_PATH), 1)

    def test_a_checksum_mismatch_is_rejected_and_the_file_is_deleted(self):
        corrupted = bytearray(PAYLOAD)
        corrupted[10] ^= 0xFF  # same size, different bytes
        self.server.state["served"] = bytes(corrupted)
        self.assertEqual(self.run_main(), fetcher.EXIT_MISMATCH)
        self.assertIn("CHECKSUM MISMATCH", self.stderr)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_a_size_mismatch_is_rejected_and_the_file_is_deleted(self):
        self.server.state["served"] = PAYLOAD[:-1]
        self.assertEqual(self.run_main(), fetcher.EXIT_MISMATCH)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_a_wrong_existing_file_of_the_right_size_is_deleted_not_trusted(self):
        self.dest.mkdir()
        (self.dest / fetcher.NAME).write_bytes(b"\0" * len(PAYLOAD))
        self.assertEqual(self.run_main(), fetcher.EXIT_MISMATCH)
        self.assertFalse((self.dest / fetcher.NAME).exists())

    def test_a_partial_download_is_resumed_with_a_range_request(self):
        self.dest.mkdir()
        (self.dest / (fetcher.NAME + ".part")).write_bytes(PAYLOAD[:1000])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.dest / fetcher.NAME).read_bytes(), PAYLOAD)
        self.assertIn((FILE_PATH, "bytes=1000-"), self.server.state["requests"])

    def test_a_server_that_ignores_range_does_not_corrupt_the_file(self):
        self.dest.mkdir()
        (self.dest / (fetcher.NAME + ".part")).write_bytes(PAYLOAD[:1000])
        self.server.state["honour_range"] = False
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.dest / fetcher.NAME).read_bytes(), PAYLOAD)

    def test_unreachable_server_and_missing_metadata_are_one_line_errors(self):
        self.assertEqual(self.run_main(endpoint="http://127.0.0.1:9"), fetcher.EXIT_NETWORK)
        self.assertNotIn("Traceback", self.stderr)
        self.server.state["tree"] = [{"path": fetcher.NAME}]
        self.assertEqual(self.run_main(), fetcher.EXIT_NETWORK)
        self.assertEqual(len(self.stderr.strip().splitlines()), 1)
        self.assertFalse(self.dest.exists())

    def test_dest_option_and_environment_fallback_have_no_default(self):
        out, err = io.StringIO(), io.StringIO()
        saved = os.environ.pop(fetcher.DEST_ENV, None)
        self.addCleanup(lambda: saved is None or os.environ.__setitem__(fetcher.DEST_ENV, saved))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fetcher.main([])
        self.assertEqual(code, fetcher.EXIT_USAGE)
        self.assertIn(fetcher.DEST_ENV, err.getvalue())
        os.environ[fetcher.DEST_ENV] = str(self.dest)
        self.addCleanup(os.environ.pop, fetcher.DEST_ENV, None)
        self.assertEqual(fetcher.build_parser().parse_args([]).dest, self.dest)

    def test_dest_inside_a_photos_library_package_is_refused_in_any_case(self):
        base = pathlib.Path(self._tmp.name)
        for name in ("Photos Library.photoslibrary", "Pictures.PhotosLibrary"):
            library = base / name
            library.mkdir()
            with self.subTest(name=name), self.assertRaises(SystemExit) as caught:
                self.run_main(dest=library / "models")
            self.assertIn("Photos library", str(caught.exception))
            self.assertEqual(list(library.iterdir()), [])
        self.assertEqual(self.server.state["requests"], [])

    def test_importing_the_module_and_asking_for_help_use_no_network(self):
        completed = subprocess.run([sys.executable, "-m", "tools.media.fetch_speech_model", "--help"],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--dest", completed.stdout)


if __name__ == "__main__":
    unittest.main()
