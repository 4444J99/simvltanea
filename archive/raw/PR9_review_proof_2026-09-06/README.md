# PR #9 — executed proof bundle

September 6, 2026. Final branch head: `beecfee905cb2685b7c71ede13a1955faed6c153`.
Tested code: `d523af18797996d9fc3b1446dfb1238cef7bbfbd`; later commit is documentation only.
PR #9 remains open, draft and unmerged. Issue #8 remains open.

Start with `REVIEW_READINESS_RECEIPT.md`. The machine ledger pins source and completed
log/receipt hashes. `PUBLICATION_SNAPSHOT.json` records final GitHub metadata and the
failed latest-head CodeQL check. This is a scoped evidence package, not a full clone.

## Evidence map

- `source/incubator/triptych-video-canon/`: executed source subset, latest receipt,
  baseline original and manifest. Earlier documentation not included in this subset
  remains in the repository; bundled older runtime/canon documents retain their dates.
- `captured/review-reconciled/`: completed final 12-shard run, **90 distinct passes**,
  zero failures/errors/skips. This is the authoritative test-count receipt.
- `captured/runtime-evidence/`: native traces, frame/clock/DOM observations, screenshots,
  decoder checks, source/color checks, portable receipts and render logs.
- `captured/paired-renders/`: ten freshly regenerated small paired exports plus portable
  replay outputs. Earlier full-HD exports were not regenerated or included here.
- `captured/legacy-regression/`: five complete original/current output pairs and logs.
- `captured/fixtures/` and `captured/legacy-fixtures/`: synthetic input bytes and states.
- `captured/portable-preview-7/`: generated silent preview files observed using explicit
  in-memory transport. Inclusion is not a claim that file:// or served HTTP was verified.
- `contact-sheets/`: the three inspected sheets drawn from 35 actual browser screenshots.
- `diagnostics/`: source verification, actual blocked HTTP attempts, before-fix failures,
  sanitized historical access failures and earlier development/aggregate records.

No original archive media, private locators, signed URLs, credentials or font files are
included. All bundled media are synthetic engineering fixtures. Source reuse in its
explicit test is intentional and does not merge instance identity or clocks.

## Reproduction

The source subset has no generated runtime-proof folder, so a new run cannot accidentally
reuse this captured evidence. Run commands from `source/incubator/triptych-video-canon/`.
Prerequisites are system Chromium, FFmpeg/ffprobe and DejaVu fonts, Python with the optional
versions listed in `requirements-runtime-proof.txt`. These prerequisites are not bundled.

```bash
python run_review_proof.py --transport http --output runtime-proof/review-http
```

That full HTTP command is the pending gate. It was not a passing run here. Do not bypass
browser policy: the observed default-HTTP attempt failed before application loading with
ERR_BLOCKED_BY_ADMINISTRATOR. The executed final command was explicitly narrower:

```bash
python run_review_proof.py --transport in-memory --output runtime-proof/review-reconciled
```

Native decoding and clocks are real in both modes; in-memory replaces plan/media IO and
the digest provider, so it does not prove fetch/WebCrypto/hosting. After that suite, the
other completed proof helpers can be reproduced with:

```bash
python verify_legacy_decoded.py
python render_runtime_family.py
python verify_runtime_renders.py
```

Use new output directories and preserve prior evidence before fixed-path helpers are
regenerated. Do not count an old receipt after a failed command. `browser-transport.txt`
contains the last navigation attempt (HTTP); individual traces and the completed runner
summary correctly identify the passing runs as in-memory. Development failures and old
helper summaries are not additional tests or current success evidence.

## Integrity

`SHA256SUMS.txt` hashes every other file in this package. From this directory, run
`sha256sum -c SHA256SUMS.txt`. The archive was opened and all manifest hashes checked after
creation. This detects accidental corruption; it is not a cryptographic author signature.
Historical fidelity, artist approval, physical-device capacity, deployment and hosted-CI
success remain unclaimed. No pending work is scheduled or running from this package.
