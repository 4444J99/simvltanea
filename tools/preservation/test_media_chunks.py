"""Exact reconstruction must fail closed without damaging source or prior output."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.media import atomize_media as producer
from tools.preservation import media_chunks as chunks


class MediaChunkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "samples" / "private.bin"
        self.source.parent.mkdir()
        self.data = b"repeat--repeat--tail"
        self.source.write_bytes(self.data)
        self.store = self.root / "work" / "chunks"
        roles = {name: self.root / name for name in producer.LANE_POLICIES}
        self.layout = SimpleNamespace(path=lambda role: roles[role])
        self.enterContext(patch.object(producer, "ROOT", self.root))
        self.enterContext(patch.object(producer, "LAYOUT", self.layout))
        self.enterContext(patch.object(producer, "load_project_recipes", return_value=[]))

    def manifest(self, data: bytes | None = None, size: int = 4):
        if data is not None:
            self.source.write_bytes(data)
        value = producer.atom_for_path(self.source, chunk_bytes=size, write_chunks=True,
                                       chunk_dir=self.store, no_ffprobe=True)
        return {"schema": chunks.SCHEMA, "chunk_bytes": size, "atoms": [asdict(value)],
                "root": "UNTRUSTED: must never be used for a filesystem operation"}

    def restore(self, manifest, name="restored.bin"):
        return chunks.restore(manifest, manifest["atoms"][0]["id"], store=self.store,
                              destination=self.root / name, root=self.root)

    def assert_no_parts(self):
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_exact_restore_from_transported_store_without_source(self):
        manifest = self.manifest()
        transported = self.root / "transported" / "chunks"
        shutil.copytree(self.store, transported)
        self.source.unlink()  # Synthetic fixture only; demonstrate zero source dependency.
        shutil.rmtree(self.store)
        self.store = transported
        manifest["atoms"][0]["path"] = "../../must-not-open-or-write"
        receipt = self.restore(manifest)
        self.assertEqual((self.root / "restored.bin").read_bytes(), self.data)
        self.assertTrue(receipt["exact_reconstruction"])
        self.assertFalse(receipt["independent_private_custody"])
        self.assertFalse(receipt["retirement_authorized"])
        self.assert_no_parts()

    def test_empty_and_repeated_chunks_reconstruct(self):
        for i, data in enumerate((b"", b"abcd" * 5, b"abc")):
            with self.subTest(data=data):
                manifest = self.manifest(data)
                self.restore(manifest, f"result-{i}")
                self.assertEqual((self.root / f"result-{i}").read_bytes(), data)
        self.assert_no_parts()

    def test_duplicate_paths_for_same_identity_are_valid(self):
        manifest = self.manifest()
        another = deepcopy(manifest["atoms"][0]); another["path"] = "different-source.mov"
        manifest["atoms"].append(another)
        self.restore(manifest)
        another["bytes"] += 1
        with self.assertRaises(chunks.IntegrityError):
            self.restore(manifest, "conflicting")

    def test_corrupt_existing_chunk_is_not_reused_or_overwritten(self):
        manifest = self.manifest()
        part = manifest["atoms"][0]["chunks"][0]
        path = chunks.chunk_path(self.store, part["sha256"], self.root)
        path.write_bytes(b"z" * part["bytes"])
        with self.assertRaises(chunks.IntegrityError):
            self.manifest()
        self.assertEqual(path.read_bytes(), b"z" * part["bytes"])
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assert_no_parts()

    def test_corrupt_missing_and_truncated_chunks_never_publish(self):
        for mode in ("corrupt", "missing", "truncated", "trailing"):
            with self.subTest(mode=mode):
                manifest = self.manifest()
                part = manifest["atoms"][0]["chunks"][-1]
                path = chunks.chunk_path(self.store, part["sha256"], self.root)
                original = path.read_bytes()
                if mode == "missing":
                    path.unlink()
                else:
                    path.write_bytes({"corrupt": b"z" * len(original),
                                      "truncated": original[:-1], "trailing": original + b"x"}[mode])
                with self.assertRaises((OSError, chunks.IntegrityError)):
                    self.restore(manifest)
                self.assertFalse((self.root / "restored.bin").exists())
                self.assertEqual(self.source.read_bytes(), self.data)
                self.assert_no_parts()
                path.write_bytes(original)

    def test_whole_hash_is_checked_in_addition_to_chunk_hashes(self):
        manifest = self.manifest()
        manifest["atoms"][0].update(id="sha256:" + "0" * 64, sha256="0" * 64)
        with self.assertRaisesRegex(chunks.IntegrityError, "original SHA"):
            self.restore(manifest)
        self.assertFalse((self.root / "restored.bin").exists())
        self.assert_no_parts()

    def test_invalid_manifest_fields_and_order_refused(self):
        original = self.manifest()
        variants = []
        for key, value in (("index", 2), ("offset", 1), ("bytes", 0), ("bytes", True),
                           ("sha256", "../../escape"), ("bytes", 5)):
            item = deepcopy(original); item["atoms"][0]["chunks"][0][key] = value; variants.append(item)
        for value in (-1, True, 0, chunks.MAX_CHUNK_BYTES + 1):
            item = deepcopy(original); item["chunk_bytes"] = value; variants.append(item)
        item = deepcopy(original); item["schema"] = "unknown"; variants.append(item)
        item = deepcopy(original); item["atoms"][0]["bytes"] += 1; variants.append(item)
        item = deepcopy(original); item["atoms"][0]["chunks"].reverse(); variants.append(item)
        for index, manifest in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(chunks.IntegrityError):
                self.restore(manifest)
        self.assertFalse((self.root / "restored.bin").exists())

    def test_existing_output_and_original_are_never_overwritten(self):
        manifest = self.manifest()
        target = self.root / "restored.bin"; target.write_bytes(b"prior output")
        with self.assertRaises(FileExistsError):
            self.restore(manifest)
        with self.assertRaises(FileExistsError):
            self.restore(manifest, "samples/private.bin")
        self.assertEqual(target.read_bytes(), b"prior output")
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assert_no_parts()

    def test_concurrent_output_creation_is_not_clobbered(self):
        manifest = self.manifest()
        actual = chunks.os.link
        def race(src, dst, **kwargs):
            (self.root / "restored.bin").write_bytes(b"another writer")
            return actual(src, dst, **kwargs)
        with patch.object(chunks.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            self.restore(manifest)
        self.assertEqual((self.root / "restored.bin").read_bytes(), b"another writer")
        self.assert_no_parts()

    def test_source_symlink_and_directory_symlink_are_refused(self):
        alias = self.root / "samples" / "alias.bin"; alias.symlink_to(self.source)
        with self.assertRaises((OSError, chunks.IntegrityError)):
            producer.hash_file(alias, chunk_bytes=4, write_chunks=False, chunk_dir=self.store)
        with self.assertRaises(chunks.IntegrityError):
            list(producer.iter_files(["samples"]))
        alias.unlink()
        link = self.root / "samples" / "nested"; link.symlink_to(self.root / "work", target_is_directory=True)
        with self.assertRaises(chunks.IntegrityError):
            list(producer.iter_files(["samples"]))

    def test_store_shard_and_destination_symlinks_are_refused(self):
        manifest = self.manifest()
        part = manifest["atoms"][0]["chunks"][0]
        path = chunks.chunk_path(self.store, part["sha256"], self.root)
        original = path.read_bytes(); path.unlink(); path.symlink_to(self.source)
        with self.assertRaises((OSError, chunks.IntegrityError)):
            self.restore(manifest)
        path.unlink(); path.write_bytes(original)
        shard = path.parent; renamed = shard.with_name("old-shard"); shard.rename(renamed)
        shard.symlink_to(renamed, target_is_directory=True)
        with self.assertRaises((OSError, chunks.IntegrityError)):
            self.restore(manifest)
        shard.unlink(); renamed.rename(shard)
        (self.root / "output-link").symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaises((OSError, chunks.IntegrityError)):
            self.restore(manifest, "output-link/result.bin")
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assert_no_parts()

    def test_mutation_during_hash_is_rejected(self):
        actual = producer.materialize_chunk
        changed = False
        def mutate(*args):
            nonlocal changed
            result = actual(*args)
            if not changed:
                changed = True
                with self.source.open("ab") as handle:
                    handle.write(b"mutation")
            return result
        with patch.object(producer, "materialize_chunk", side_effect=mutate):
            with self.assertRaisesRegex(chunks.IntegrityError, "changed"):
                self.manifest()
        self.assert_no_parts()

    def test_chunk_reads_are_bounded_and_streamed(self):
        manifest = self.manifest(b"x" * (chunks.READ_BYTES * 2 + 3), size=chunks.READ_BYTES * 3)
        requests = []
        original = chunks.regular_reader
        @contextmanager
        def measured(path):
            with original(path) as source:
                class Reader:
                    def fileno(self):
                        return source.fileno()
                    def read(self, count):
                        requests.append(count)
                        return source.read(count)
                yield Reader()
        with patch.object(chunks, "regular_reader", side_effect=measured):
            self.restore(manifest)
        self.assertTrue(requests)
        self.assertTrue(all(0 < count <= chunks.READ_BYTES for count in requests))

    def test_outside_boundary_and_store_output_refused(self):
        manifest = self.manifest()
        for destination in (self.root.parent / "outside", self.root / ".." / "outside", self.store / "output"):
            with self.subTest(path=destination), self.assertRaises(chunks.IntegrityError):
                chunks.restore(manifest, manifest["atoms"][0]["id"], store=self.store,
                               destination=destination, root=self.root)

    def test_bad_chunk_bounds_rejected_before_reads(self):
        for value in (-1, 0, True, chunks.MAX_CHUNK_BYTES + 1):
            with self.subTest(value=value), self.assertRaises(chunks.IntegrityError):
                producer.hash_file(self.source, chunk_bytes=value, write_chunks=False, chunk_dir=self.store)

    def test_manifest_loading_bounds_and_duplicate_keys(self):
        path = self.root / "manifest.json"
        path.write_text('{"schema": "first", "schema": "second"}')
        with self.assertRaises(chunks.IntegrityError):
            chunks.load_manifest(path, self.root)
        path.write_bytes(b" " * 11)
        with patch.object(chunks, "MAX_MANIFEST_BYTES", 10), self.assertRaises(chunks.IntegrityError):
            chunks.load_manifest(path, self.root)
        path.unlink(); path.symlink_to(self.source)
        with self.assertRaises((OSError, chunks.IntegrityError)):
            chunks.load_manifest(path, self.root)

    def test_special_input_is_rejected_without_blocking(self):
        fifo = self.root / "samples" / "pipe"; os.mkfifo(fifo)
        with self.assertRaises(chunks.IntegrityError):
            list(producer.iter_files(["samples"]))
        with self.assertRaises(chunks.IntegrityError):
            with chunks.regular_reader(fifo):
                self.fail("FIFO must not be yielded")

    def test_work_lane_excludes_chunks_and_current_receipts(self):
        manifest = self.manifest()
        output, summary = self.root / "work" / "media-atoms.json", self.root / "work" / "media-atoms.md"
        output.write_text(json.dumps(manifest)); summary.write_text("old receipt")
        source = self.root / "work" / "keep.bin"; source.write_bytes(b"keep")
        args = argparse.Namespace(lanes="work", output=output, summary=summary,
                                  chunk_dir=self.store, chunk_bytes=4, limit=None,
                                  write_chunks=True, no_ffprobe=True)
        payload = producer.build_payload(args)
        self.assertEqual([a["path"] for a in payload["atoms"]], ["work/keep.bin"])
        self.assertEqual(payload["totals"]["files"], 1)

    def test_producer_chunk_and_atom_count_bounds(self):
        with patch.object(producer, "MAX_CHUNKS", 2), self.assertRaises(chunks.IntegrityError):
            self.manifest()
        args = argparse.Namespace(lanes="samples", output=self.root / "out.json",
                                  summary=self.root / "out.md", chunk_dir=self.store,
                                  chunk_bytes=4, limit=None, write_chunks=False, no_ffprobe=True)
        with patch.object(producer, "MAX_ATOMS", 0), self.assertRaises(chunks.IntegrityError):
            producer.build_payload(args)

    def test_new_chunk_digest_is_checked(self):
        with self.assertRaises(chunks.IntegrityError):
            chunks.materialize(self.store, "0" * 64, b"wrong", self.root)
        self.assertFalse(self.store.exists())


if __name__ == "__main__":
    unittest.main()
