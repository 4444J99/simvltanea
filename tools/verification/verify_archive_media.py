"""Measure retained MEDA studies against one Git revision and private byte snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import BinaryIO, Iterator
import uuid

from tools.paths import PROOFS_DIR, REPO_ROOT
from tools.preservation.media_chunks import IntegrityError, new_output, parent_fd, regular_reader

MEDIA = {
    "MEDA-002": "archive/chatgpt/media/MEDA-002_visual-form-canon-7-portrait.mp4",
    "MEDA-003": "archive/chatgpt/media/MEDA-003_visual-form-canon-7-landscape.mp4",
}
GIT_TIMEOUT_SECONDS = 10


def git_identity(revision: str) -> str:
    """Resolve only this checkout, not a caller's alternate Git directory/index."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", revision], cwd=REPO_ROOT, env=environment,
            text=True, capture_output=True, check=True, timeout=GIT_TIMEOUT_SECONDS,
        ).stdout.strip()
    except subprocess.TimeoutExpired as error:
        raise IntegrityError("Git identity lookup timed out") from error
    if not re.fullmatch(r"[0-9a-f]{40}", result):
        raise IntegrityError("expected the repository's SHA-1 Git object identity")
    return result


@contextmanager
def private_snapshot(path: Path) -> Iterator[BinaryIO]:
    """Yield an unlinked, read-only snapshot; never pass the source path to decoders.

    The only writable descriptor is closed before hashing/probing/decoding. Child
    processes inherit only the read-only descriptor. The generated temporary name
    is removed before measurement, including on failures. This is not custody.
    """
    temporary = PROOFS_DIR / "archive-media" / ("snapshot-" + uuid.uuid4().hex)
    with parent_fd(temporary, create=True) as (directory, name):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=directory)
        linked = True
        reader = None
        try:
            with os.fdopen(fd, "wb") as destination:
                with regular_reader(path) as source:
                    while block := source.read(1024 * 1024):
                        destination.write(block)
                destination.flush()
                os.fsync(destination.fileno())
            reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            os.unlink(name, dir_fd=directory)
            linked = False
            handle = os.fdopen(reader, "rb")
            reader = None
            with handle:
                yield handle
        finally:
            if reader is not None:
                os.close(reader)
            if linked:
                os.unlink(name, dir_fd=directory)


def descriptor_path(source: BinaryIO) -> str:
    """Linux and macOS descriptor paths support seekable inherited video inputs."""
    for directory in (Path("/proc/self/fd"), Path("/dev/fd")):
        if directory.is_dir():
            return str(directory / str(source.fileno()))
    raise IntegrityError("seekable inherited file descriptors are unavailable")


def measure(relative: str, *, revision: str) -> dict:
    if relative not in MEDIA.values() or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise IntegrityError("expected a known archive path and pinned Git commit")
    expected_blob = git_identity(revision + ":" + relative)
    with private_snapshot(REPO_ROOT / relative) as source:
        size = os.fstat(source.fileno()).st_size
        checksum, git_blob = hashlib.sha256(), hashlib.sha1()
        git_blob.update(f"blob {size}\0".encode())
        while block := source.read(1024 * 1024):
            checksum.update(block)
            git_blob.update(block)
        if git_blob.hexdigest() != expected_blob:
            raise IntegrityError("snapshot bytes do not match the pinned Git blob")
        input_path = descriptor_path(source)
        source.seek(0)
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height,pix_fmt:format=duration", "-of", "json", input_path,
        ], capture_output=True, text=True, check=True, timeout=30, pass_fds=(source.fileno(),))
        probe = json.loads(result.stdout)
        source.seek(0)
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", input_path,
            "-map", "0", "-f", "null", "-",
        ], capture_output=True, text=True, check=True, timeout=60, pass_fds=(source.fileno(),))
    return {"path": relative, "git_blob": expected_blob, "bytes": size,
            "sha256": checksum.hexdigest(), "probe": probe, "full_decode": True,
            "verification_source": "private-unlinked-read-only-snapshot"}


def main() -> int:
    try:
        # Resolve once so a moving HEAD cannot mix identities from two revisions.
        head = git_identity("HEAD^{commit}")
        result = {"schema": "simvltanea.archive-media-proof.v1", "git_head": head,
                  "observed_at": datetime.now(timezone.utc).isoformat(),
                  "media": {identity: measure(path, revision=head) for identity, path in MEDIA.items()},
                  "historical_originals_recovered": False, "artist_approval": False,
                  "independent_private_custody": False, "retirement_authorized": False}
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        output = PROOFS_DIR / "archive-media" / ("run-" + uuid.uuid4().hex) / "receipt.json"
        with new_output(output) as destination:
            destination.write(encoded.encode())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"archive verification refused ({type(error).__name__}); no verified receipt issued",
              file=sys.stderr)
        return 2
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
