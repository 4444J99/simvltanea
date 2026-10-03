"""Test Git isolation and same-byte decoding without needing private source media."""
from contextlib import redirect_stderr
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.verification import verify_archive_media as verifier


class ArchiveSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.relative = verifier.MEDIA["MEDA-003"]
        self.path = self.root / self.relative
        self.path.parent.mkdir(parents=True)
        self.payload = b"synthetic snapshot byte identity"
        self.path.write_bytes(self.payload)
        self.proofs = self.root / "var" / "proofs"
        self.enterContext(patch.object(verifier, "REPO_ROOT", self.root))
        self.enterContext(patch.object(verifier, "PROOFS_DIR", self.proofs))
        self.revision = "a" * 40
        self.blob = hashlib.sha1(f"blob {len(self.payload)}\0".encode() + self.payload).hexdigest()

    def test_git_environment_isolation_and_timeout(self):
        hostile = {key: "/unrelated" for key in (
            "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG_COUNT")}
        with patch.dict(os.environ, hostile), patch.object(verifier.subprocess, "run") as run:
            run.return_value.stdout = self.revision + "\n"
            self.assertEqual(verifier.git_identity("HEAD^{commit}"), self.revision)
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["cwd"], self.root)
            self.assertEqual(kwargs["timeout"], 10)
            self.assertTrue(kwargs["check"])
            self.assertEqual({k: v for k, v in kwargs["env"].items() if k.startswith("GIT_")},
                             {"GIT_NO_REPLACE_OBJECTS": "1"})
            self.assertEqual(os.environ["GIT_DIR"], "/unrelated")

    def test_git_timeout_fails_closed(self):
        with patch.object(verifier.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 10)):
            with self.assertRaisesRegex(verifier.IntegrityError, "timed out"):
                verifier.git_identity("HEAD^{commit}")

    def test_git_identity_must_be_exact(self):
        with patch.object(verifier.subprocess, "run") as run:
            for output in ("HEAD", "a" * 64, self.revision + "\n" + self.blob):
                run.return_value.stdout = output
                with self.subTest(output=output), self.assertRaises(verifier.IntegrityError):
                    verifier.git_identity("HEAD^{commit}")

    def test_snapshot_is_read_only_unlinked_and_independent(self):
        with verifier.private_snapshot(self.path) as snapshot:
            self.assertEqual(fcntl.fcntl(snapshot.fileno(), fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
            self.assertEqual(os.fstat(snapshot.fileno()).st_nlink, 0)
            self.path.write_bytes(b"changed source")
            self.assertEqual(snapshot.read(), self.payload)
            with self.assertRaises(OSError):
                os.write(snapshot.fileno(), b"cannot write")
        self.assertEqual(list(self.proofs.rglob("snapshot-*")), [])
        self.assertEqual(self.path.read_bytes(), b"changed source")

    def test_probe_and_decode_share_pinned_snapshot_despite_source_changes(self):
        observed = []
        def run(command, **kwargs):
            fd = kwargs["pass_fds"][0]
            input_path = command[-1] if command[0] == "ffprobe" else command[command.index("-i") + 1]
            observed.append((fd, input_path))
            self.assertNotIn(str(self.path), command)
            self.assertEqual(os.fstat(fd).st_nlink, 0)
            self.assertEqual(os.read(fd, 1000), self.payload)
            self.assertEqual(self.path.read_bytes(), self.payload)
            self.path.write_bytes(b"unrelated bytes while decoder runs")
            self.assertGreater(kwargs["timeout"], 0)
            self.path.write_bytes(self.payload)
            return subprocess.CompletedProcess(command, 0, stdout='{"streams":[],"format":{}}')
        with patch.object(verifier, "git_identity", return_value=self.blob) as identity:
            with patch.object(verifier.subprocess, "run", side_effect=run):
                result = verifier.measure(self.relative, revision=self.revision)
            identity.assert_called_once_with(self.revision + ":" + self.relative)
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(result["sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(result["verification_source"], "private-unlinked-read-only-snapshot")
        self.assertTrue(result["full_decode"])

    def test_mismatched_blob_never_reaches_decoder(self):
        with patch.object(verifier, "git_identity", return_value="0" * 40):
            with patch.object(verifier.subprocess, "run") as run:
                with self.assertRaises(verifier.IntegrityError):
                    verifier.measure(self.relative, revision=self.revision)
                run.assert_not_called()
        self.assertEqual(list(self.proofs.rglob("snapshot-*")), [])
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_decoder_failure_releases_snapshot_without_touching_source(self):
        descriptor = []
        def fail(command, **kwargs):
            descriptor.extend(kwargs["pass_fds"])
            raise subprocess.TimeoutExpired(command[0], kwargs["timeout"])
        with patch.object(verifier, "git_identity", return_value=self.blob):
            with patch.object(verifier.subprocess, "run", side_effect=fail):
                with self.assertRaises(subprocess.TimeoutExpired):
                    verifier.measure(self.relative, revision=self.revision)
        with self.assertRaises(OSError):
            os.fstat(descriptor[0])
        self.assertEqual(list(self.proofs.rglob("snapshot-*")), [])
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_unapproved_path_and_unpinned_revision_refused(self):
        for path, revision in (("../../other.mp4", self.revision), (self.relative, "HEAD")):
            with self.subTest(path=path, revision=revision), self.assertRaises(verifier.IntegrityError):
                verifier.measure(path, revision=revision)

    def test_main_timeout_publishes_no_success_receipt(self):
        with patch.object(verifier, "git_identity", side_effect=verifier.IntegrityError("timed out")):
            with redirect_stderr(io.StringIO()) as error:
                self.assertEqual(verifier.main(), 2)
        self.assertIn("no verified receipt", error.getvalue())
        self.assertEqual(list(self.proofs.rglob("receipt.json")), [])


if __name__ == "__main__":
    unittest.main()
