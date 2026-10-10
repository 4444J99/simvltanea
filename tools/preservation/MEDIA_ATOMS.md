# Media atoms: exact reconstruction

The existing `triptych.media-atoms.v1` manifest describes original bytes through
ordered, content-addressed chunks. It is not a codec, playback-segment format,
encryption system, authentication boundary, remote provider or custody receipt.

## Produce and reconstruct

Run from the repository root. Relative output/store/manifest arguments below are
relative to the configured generated root, not the caller's current directory.
Use new JSON and Markdown receipt paths on each run; existing files are never
overwritten. Reusing verified chunk bytes is supported.

```bash
python3 -m tools.media.atomize_media \
  --lanes samples --write-chunks --no-ffprobe \
  --chunk-dir work/atom-chunks \
  --output work/capture-001.json --summary work/capture-001.md

python3 -m tools.preservation.restore_media \
  --manifest work/capture-001.json \
  --asset-id sha256:REPLACE_WITH_THE_MANIFEST_ASSET_DIGEST \
  --chunk-dir work/atom-chunks --output work/restore-001/source.mov

python3 -m unittest tools.preservation.test_media_chunks -v
```

The restore command selects an asset by SHA-256 identity and uses only explicitly
supplied manifest, store and destination locations. The manifest's `root`, `path`,
recipes, privacy labels and source filenames never become restore instructions.
Repeated source paths for the same identity are accepted only when their byte
size, SHA-256 and ordered reconstruction records agree.

## Failure boundaries

Chunk size is limited to 64 MiB; reconstruction reads at most 1 MiB at a time.
Manifest loading is limited to 32 MiB, with bounded atom/chunk counts and duplicate
JSON keys rejected. Oversized catalogues need paging rather than disabling bounds.
Every chunk hash, size, index and offset is checked, followed by the complete
original SHA-256. Empty originals have no chunks and still require the correct
whole-file digest. A visually similar transcode cannot pass as the original.

The supported filesystem implementation requires POSIX descriptor-relative
operations. Parent components are opened without following symlinks. Symlinks,
FIFOs, special input files, traversal and writes outside the generated boundary
are refused. Observable source replacement or mutation invalidates hashing.
Use a trusted filesystem namespace; this is not a defense against a malicious
administrator or proof of storage-hardware durability.

Output publication never overwrites an existing file, including a destination
created by another writer during reconstruction. Only the invocation's unique
partial file is removed on failure. Valid chunks produced before an interruption
are retained for verified reuse; they are not automatically garbage-collected.
The producer excludes its chunk store and current JSON/Markdown receipts from
self-ingestion. Two receipt files are not an atomic transaction: a failed summary
write can leave a complete JSON receipt, but the command has not succeeded.

## Evidence and remaining acceptance

Synthetic relocation of a chunk store demonstrates source-independent byte
reconstruction, not independent custody of personal originals. Retain originals
and assigned copies until the separately scoped private destination, encryption,
independent restoration, cryptographic comparison and retirement gates pass.
Issue #12 and PR #20's Photos-session obligations remain open independently.

`tools.verification.verify_archive_media` measures the retained MEDA-002 and
MEDA-003 bytes against their checked-out Git blobs, probes streams and fully
decodes each file. CI stores a dated receipt before active metadata repair.
Those engineering studies are not recovered TripTicks source MOV/archive bytes
and do not establish final artistic approval. Short-lived CI artifacts are not
archive custody.
