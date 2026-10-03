"""Measure retained MEDA studies before repairing their active catalogue metadata."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from tools.paths import PROOFS_DIR, REPO_ROOT
from tools.preservation.media_chunks import fingerprint, new_output, regular_reader

MEDIA = {
    "MEDA-002": "archive/chatgpt/media/MEDA-002_visual-form-canon-7-portrait.mp4",
    "MEDA-003": "archive/chatgpt/media/MEDA-003_visual-form-canon-7-landscape.mp4",
}


def measure(relative: str) -> dict:
    path = REPO_ROOT / relative
    expected_blob = subprocess.run(["git", "rev-parse", "HEAD:" + relative], cwd=REPO_ROOT,
                                   text=True, capture_output=True, check=True).stdout.strip()
    with regular_reader(path) as source:
        before = os.fstat(source.fileno())
        checksum, git_blob = hashlib.sha256(), hashlib.sha1()
        git_blob.update(f"blob {before.st_size}\0".encode())
        while block := source.read(1024 * 1024):
            checksum.update(block)
            git_blob.update(block)
        if git_blob.hexdigest() != expected_blob:
            raise ValueError("retained bytes do not match the checked-out Git blob")
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height,pix_fmt:format=duration", "-of", "json", str(path),
        ], capture_output=True, text=True, check=True, timeout=30)
        probe = json.loads(result.stdout)
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
            "-map", "0", "-f", "null", "-",
        ], capture_output=True, text=True, check=True, timeout=60)
        if fingerprint(before) != fingerprint(path.stat(follow_symlinks=False)):
            raise ValueError("retained file changed during stream/decode verification")
    return {"path": relative, "git_blob": expected_blob, "bytes": before.st_size,
            "sha256": checksum.hexdigest(), "probe": probe, "full_decode": True}


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                          text=True, capture_output=True, check=True).stdout.strip()
    result = {"schema": "simvltanea.archive-media-proof.v1", "git_head": head,
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "media": {identity: measure(path) for identity, path in MEDIA.items()},
              "historical_originals_recovered": False, "artist_approval": False,
              "independent_private_custody": False, "retirement_authorized": False}
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output = PROOFS_DIR / "archive-media" / ("run-" + uuid.uuid4().hex) / "receipt.json"
    with new_output(output) as destination:
        destination.write(encoded.encode())
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
