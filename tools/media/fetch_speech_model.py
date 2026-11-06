#!/usr/bin/env python3
"""Download the local speech model for audio screening and VERIFY it against the publisher's own checksum.

File: ggml-base.en.bin (whisper.cpp English base model, about 148 MB) from huggingface.co/ggerganov/whisper.cpp.
The expected size and SHA-256 are read from the repository's own Git LFS metadata, and the file is deleted when
either does not match. A partly downloaded ``.part`` file is resumed. Nothing about anyone's media is sent anywhere:
this only fetches a public model file, and it is the only tool here that touches the network.

Run:  python3 -m tools.media.fetch_speech_model --dest /path/to/models/whisper
--dest falls back to $SIMVLTANEA_WHISPER_MODEL_DIR; there is no default path. Point screen_audio.py at the result
with --model /path/to/models/whisper/ggml-base.en.bin. --endpoint exists for mirrors and for tests.
Exit codes: 0 verified, 1 checksum or size mismatch (file deleted), 2 bad options, 3 network or metadata error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

from tools.media.private_root import resolve_private_root

DEST_ENV = "SIMVLTANEA_WHISPER_MODEL_DIR"
DEFAULT_ENDPOINT = "https://huggingface.co"
REPO = "ggerganov/whisper.cpp"
NAME = "ggml-base.en.bin"
EXIT_MISMATCH, EXIT_USAGE, EXIT_NETWORK = 1, 2, 3
CHUNK = 1 << 20


def expected_file(endpoint: str, opener=urllib.request.urlopen) -> tuple[int, str]:
    """(size, sha256) of the model file from the repository tree listing."""
    with opener(f"{endpoint}/api/models/{REPO}/tree/main", timeout=60) as response:
        entries = json.load(response)
    entry = next((e for e in entries if e.get("path") == NAME), None)
    lfs = (entry or {}).get("lfs") or {}
    if not isinstance(lfs.get("size"), int) or not isinstance(lfs.get("oid"), str):
        raise ValueError(f"{NAME} has no size and checksum in the repository metadata")
    return lfs["size"], lfs["oid"]


def download(endpoint: str, part: pathlib.Path, target: pathlib.Path, size: int,
             opener=urllib.request.urlopen) -> None:
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink()
        have = 0
    request = urllib.request.Request(f"{endpoint}/{REPO}/resolve/main/{NAME}",
                                     headers={"Range": f"bytes={have}-"} if have else {})
    with opener(request, timeout=120) as response:
        if have and getattr(response, "status", 200) != 206:
            have = 0  # the server ignored the Range header: start again instead of appending to a stale prefix
        done = have
        with part.open("ab" if have else "wb") as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)
                done += len(chunk)
    os.replace(part, target)


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", type=pathlib.Path, default=os.environ.get(DEST_ENV) or None,
                        help=f"directory for {NAME} (outside the checkout, or under var/); default ${DEST_ENV}")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="model host (mirror or test server)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dest is None:
        print(f"no --dest given and ${DEST_ENV} is not set", file=sys.stderr)
        return EXIT_USAGE
    dest = resolve_private_root(args.dest)
    endpoint = args.endpoint.rstrip("/")
    try:
        size, sha = expected_file(endpoint)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"could not read the model metadata ({type(exc).__name__}: {exc})", file=sys.stderr)
        return EXIT_NETWORK
    print(f"expected: {NAME} {size / 1e6:.1f} MB sha256 {sha[:12]}...", flush=True)
    dest.mkdir(parents=True, exist_ok=True)
    target, part = dest / NAME, dest / (NAME + ".part")
    if target.exists() and target.stat().st_size == size:
        print("already present", flush=True)
    else:
        try:
            download(endpoint, part, target, size)
        except (OSError, urllib.error.URLError) as exc:
            print(f"download failed ({type(exc).__name__}); re-run to resume", file=sys.stderr)
            return EXIT_NETWORK
    if target.stat().st_size != size or sha256_of(target) != sha:
        target.unlink()
        part.unlink(missing_ok=True)
        print("CHECKSUM MISMATCH: file deleted", file=sys.stderr)
        return EXIT_MISMATCH
    print(f"verified: {NAME} ({size / 1e6:.1f} MB, sha256 matches the publisher)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
