"""Bounded, exact byte reconstruction for the existing media-atoms v1 format.

POSIX descriptor-relative operations refuse symlinks and special files. This is
local integrity tooling, not encryption, authentication, archive custody or a
retirement decision. The caller supplies the trusted generated-output boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import BinaryIO, Iterator
import uuid

SCHEMA = "triptych.media-atoms.v1"
MAX_CHUNK_BYTES = 64 * 1024 * 1024
READ_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_ATOMS = 100_000
MAX_CHUNKS = 1_000_000


class IntegrityError(ValueError):
    """An input cannot establish the claimed byte identity."""


def integer(value: object, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise IntegrityError(f"invalid {name}")
    return value


def digest(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise IntegrityError("invalid SHA-256 identity")
    return value


def checked_path(path: Path, root: Path) -> Path:
    """Apply a lexical boundary first; never resolve away a hostile symlink."""
    path, root = Path(path), Path(root).absolute()
    if ".." in path.parts or ".." in root.parts:
        raise IntegrityError("parent traversal is not permitted")
    path = path if path.is_absolute() else root / path
    if path == root or not path.is_relative_to(root):
        raise IntegrityError("path must be below the generated-output boundary")
    return path


def fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def parent_fd(path: Path, *, create: bool = False) -> Iterator[tuple[int, str]]:
    """Anchor every parent component without following links; fail closed off POSIX."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise IntegrityError("descriptor-relative POSIX filesystem required")
    path = Path(path).absolute()
    if ".." in path.parts or not path.name:
        raise IntegrityError("invalid filesystem path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:-1]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd, path.name
    finally:
        os.close(fd)


@contextmanager
def regular_reader(path: Path) -> Iterator[BinaryIO]:
    """Refuse symlinks/FIFOs and reject observable replacement or mutation."""
    with parent_fd(path) as (directory, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise IntegrityError("only regular files can be read")
            yield source
            after = os.fstat(source.fileno())
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if fingerprint(before) != fingerprint(after) or fingerprint(before) != fingerprint(named):
                raise IntegrityError("source changed while being read")


@contextmanager
def new_output(path: Path) -> Iterator[BinaryIO]:
    """Publish a complete new file without clobbering any existing destination."""
    with parent_fd(path, create=True) as (directory, name):
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("output already exists; choose a fresh destination")
        temporary = ".media-atoms-" + uuid.uuid4().hex + ".part"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as output:
                yield output
                output.flush()
                os.fsync(output.fileno())
            # Unlike rename/replace, link cannot silently replace a racing writer.
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
            os.fsync(directory)
        finally:
            # Only this invocation's unique temporary output is ever removed.
            os.unlink(temporary, dir_fd=directory)


def chunk_path(store: Path, sha256: str, root: Path) -> Path:
    sha256 = digest(sha256)
    return checked_path(checked_path(store, root) / sha256[:2] / (sha256 + ".chunk"), root)


def copy_chunk(path: Path, sha256: str, size: int, output: BinaryIO | None = None,
               whole=None) -> None:
    digest(sha256)
    integer(size, "chunk size", minimum=1, maximum=MAX_CHUNK_BYTES)
    checksum = hashlib.sha256()
    with regular_reader(path) as source:
        if os.fstat(source.fileno()).st_size != size:
            raise IntegrityError("chunk size mismatch")
        remaining = size
        while remaining:
            block = source.read(min(READ_BYTES, remaining))
            if not block:
                raise IntegrityError("truncated chunk")
            remaining -= len(block)
            checksum.update(block)
            if whole is not None:
                whole.update(block)
            if output is not None:
                output.write(block)
        if source.read(1):
            raise IntegrityError("chunk has trailing bytes")
        if checksum.hexdigest() != sha256:
            raise IntegrityError("chunk SHA-256 mismatch")


def materialize(store: Path, sha256: str, data: bytes, root: Path) -> Path:
    integer(len(data), "chunk size", minimum=1, maximum=MAX_CHUNK_BYTES)
    if hashlib.sha256(data).hexdigest() != digest(sha256):
        raise IntegrityError("new chunk SHA-256 mismatch")
    target = chunk_path(store, sha256, root)
    try:
        with new_output(target) as output:
            output.write(data)
    except FileExistsError:
        # Existing or concurrently published content is never trusted by name.
        copy_chunk(target, sha256, len(data))
    return target


def load_manifest(path: Path, root: Path) -> dict:
    path = checked_path(path, root)
    with regular_reader(path) as source:
        if os.fstat(source.fileno()).st_size > MAX_MANIFEST_BYTES:
            raise IntegrityError("manifest exceeds the supported size bound")
        payload = source.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise IntegrityError("manifest exceeds the supported size bound")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IntegrityError("duplicate manifest key")
            result[key] = value
        return result
    try:
        value = json.loads(payload, object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise IntegrityError("invalid manifest JSON") from error
    if not isinstance(value, dict):
        raise IntegrityError("manifest must be an object")
    return value


def select_atom(manifest: dict, asset_id: str) -> dict:
    """Validate reconstruction fields; provenance paths are deliberately not used."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise IntegrityError("unsupported manifest schema")
    if not isinstance(asset_id, str) or not asset_id.startswith("sha256:"):
        raise IntegrityError("asset must be a SHA-256 identity")
    expected = digest(asset_id[7:])
    chunk_bytes = integer(manifest.get("chunk_bytes"), "chunk byte bound", minimum=1,
                          maximum=MAX_CHUNK_BYTES)
    atoms = manifest.get("atoms")
    if not isinstance(atoms, list) or len(atoms) > MAX_ATOMS or not all(isinstance(a, dict) for a in atoms):
        raise IntegrityError("invalid atom collection")
    matches = [a for a in atoms if a.get("id") == asset_id]
    if not matches:
        raise IntegrityError("requested asset not present")
    # Identical bytes can legitimately occur in multiple album/source paths.
    atom = matches[0]
    for other in matches[1:]:
        if any(other.get(k) != atom.get(k) for k in ("sha256", "bytes", "chunks")):
            raise IntegrityError("conflicting records for one asset identity")
    if digest(atom.get("sha256")) != expected:
        raise IntegrityError("asset and original SHA-256 disagree")
    total = integer(atom.get("bytes"), "original size")
    chunks = atom.get("chunks")
    if not isinstance(chunks, list) or len(chunks) > MAX_CHUNKS:
        raise IntegrityError("invalid chunk collection")
    offset = 0
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise IntegrityError("invalid chunk record")
        if integer(chunk.get("index"), "chunk index") != index:
            raise IntegrityError("chunk order mismatch")
        if integer(chunk.get("offset"), "chunk offset") != offset:
            raise IntegrityError("chunk offset mismatch")
        size = integer(chunk.get("bytes"), "chunk size", minimum=1, maximum=chunk_bytes)
        if index < len(chunks) - 1 and size != chunk_bytes:
            raise IntegrityError("non-final chunk is not the declared chunk size")
        digest(chunk.get("sha256"))
        offset += size
    if offset != total:
        raise IntegrityError("original size and ordered chunks disagree")
    return atom


def restore(manifest: dict, asset_id: str, *, store: Path, destination: Path, root: Path) -> dict:
    """Restore one identity to an explicit new path; never consult root/path metadata."""
    atom = select_atom(manifest, asset_id)
    store, destination = checked_path(store, root), checked_path(destination, root)
    if destination.is_relative_to(store):
        raise IntegrityError("restore destination cannot be inside the chunk store")
    whole = hashlib.sha256()
    with new_output(destination) as output:
        for chunk in atom["chunks"]:
            path = chunk_path(store, chunk["sha256"], root)
            copy_chunk(path, chunk["sha256"], chunk["bytes"], output, whole)
        if whole.hexdigest() != atom["sha256"]:
            raise IntegrityError("reconstructed original SHA-256 mismatch")
    return {"schema": "triptych.media-atoms-restore.v1", "asset_id": asset_id,
            "bytes": atom["bytes"], "sha256": whole.hexdigest(), "chunks": len(atom["chunks"]),
            "exact_reconstruction": True, "independent_private_custody": False,
            "retirement_authorized": False}
