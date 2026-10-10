# Consumer integration and merge acceptance

2026-10-10. TMB PR #3 merged as `e5900ef98fa7a9644af1708e0e6c6cbbcde5b180`.
Its entire tree equals the verified `7fa91812369b5b60f09b733565c9a2507ea177ab`.
The consumer now pins that merged commit on `main`, retaining all six runtime
digests. Squash ancestry is handled explicitly; a topic-only pin is not left behind.

Merged upstream `d60553ad4901a683fae08e09610915f03fdaabc5` into the consumer
branch without rewriting history. Conflict resolution preserves the upstream
archive, package, status projection and generated plan-index work and retains
shared-engine CI, atomic preview staging and the pin policy exception.

The first post-merge browser run found a real snapshot race: composition time
and evaluated poses sampled the moving clock separately. Snapshot now samples
once and uses that instant for both fields. The original twelve-decimal parity
assertion is unchanged. Corrected browser/owner batch: **11 passed, zero skips**
(eight rendered consumer cases and three owner-binding cases), 9.91 seconds of
pytest execution. Initial one failure / ten passes remains historical evidence.

Additional verification: 40 shared-engine, staging and plan-index tests plus five
subtests passed; layout synchronization, structure, import boundaries and plan
index passed. JavaScript syntax and diff whitespace checks passed. Upstream
Markdown hard line breaks remain as generated; the diff against upstream is clean.

The human memory-pressure override remains process-local; the final short browser
batch used warning sustain 0, swap fraction 0.5 and swap growth 4 GiB/min after
transient disk and swap-growth admission denials. Exclusive heavy ownership,
critical pressure, disk and backup checks remained active. The lease was released.
No private originals or prior budget records were changed. Physical source/device
acceptance remains in TMB acceptance PR #4; this receipt certifies integration.

The remote naming gate exposed the adapter's kebab-case source filename. It now
uses the repository's snake_case convention; staged browser URLs stay unchanged.
The merge-policy launcher also needs the installed Python 3.14 runtime (which has
PyYAML); Python 3.15 could not read the deploy registry and misclassified every
change as a website deployment. No deployment classification or policy was edited.
