# SIMVLTANEA — current status

## Read the current observation

Branch equality, open PRs/issues, workflow outcomes and releases are live data,
not enduring statements in this file. The **Current State Projection** workflow
runs after default-branch CI or package verification completes. Its job summary
and timestamped `current-state-<run-id>` artifact contain the observed snapshot.
A newer incomplete or failing observation must not be replaced with an older
successful one to claim current health.

```bash
python3 -m tools.verification.repository_status \
  --repository 4444J99/simvltanea --expected-repository-id 1364497735
```

The command performs fixed-host HTTPS GET requests only and writes fresh evidence
under the configured `proofs` role. An optional `GITHUB_TOKEN` enables authorized
reads; it is not copied into receipts. API failures, pagination bounds and a
moving default-branch head remain explicit unknowns rather than empty results.
Supported loop counts and package/layout/schema versions are read from source
metadata and bound to that source commit, not silently attributed to a later head.

A complete observation can still report red or in-progress CI. Only completed
push workflows for the observed default-branch SHA can satisfy the selected
post-merge workflow scope. A successful PR run is not post-merge evidence.
The observer reads the trusted default branch, not a PR's artifacts or scripts.
It never writes branches, changes settings, publishes media or activates policy.

## Engineering gates

The executable source of the full gate sequence is
[CI Verification](../../.github/workflows/ci.yml). It includes naming, structure,
feature boundaries, changed Markdown, media fixtures, full tests, lifecycle,
historical decoded regression, editions and layouts.
[Package Verification](../../.github/workflows/package.yml) independently builds
and installs a wheel into a fresh external consumer before synthetic preview
compilation and portrait/landscape rendering. Test totals belong to exact-head
receipts; overlapping test runners must not be added as independent coverage.

```bash
python3 -m tools.verification.sync_layout
python3 -m tools.verification.verify_repository_structure
python3 -m tools.verification.verify_feature_boundaries
python3 -m tools.verification.sync_plan_index
python3 -m unittest discover -s tests -v
python3 -m tools.verification.verify_local_lifecycle
```

A passing workflow is not native merge enforcement. The observer exposes branch
protection and ruleset observations but does not certify that approved GES controls
are effective. Accepted policy, trusted required checks, review/bypass decisions,
permissions and installed-setting readback remain distinct requirements.

## Scope and retention boundaries

The authored family and Audio v1.1 are existing engineering capabilities, not
new build requests. Their configuration authorities and implementation receipts
remain the source for supported behavior. Engineering geometry is not final
artist approval; the legacy audio contract remains separately preserved.

Issue #12 concerns independent custody of its assigned copy, including unique
Git objects and ignored payload. The PR #20 Photos session has separate private
artifact, process-responsibility and ownership obligations. A clone, clean tree,
synthetic restore, passing tests, or seven-day CI artifact does not close either
scope. Keep relevant originals and retained copies until their own independent
restore and authorized retirement predicates pass.

Complete remote albums, durable private original storage, full-album playback,
real-edition audible review, target-device/background acceptance, original
TripTicks recovery and artist approval are not inferred from generic CI success.
A merged draft governance profile is not profile approval or activation. Release
and deployment must use their own scoped acceptance, not this observation page.

The standing-lane constitution is in [BRANCHES.md](BRANCHES.md). Lane SHA equality
is calculated by the observer; remote branch equality does not imply local
worktrees are clean, synchronized or safe to remove. Neighboring First Circle,
photo-selector and Floating Points work is not silently reopened here.

## Historical evidence

Dated plans and continuation receipts remain unchanged. The previous static
[status projection](https://github.com/4444J99/simvltanea/blob/89b179576f850edc867324f8a38408c83ae3219a/docs/governance/STATUS.md)
is retained at its original revision; its branch/test/tag assertions must not be
used as current state. [The plans index](../plans/INDEX.md) is regenerated from
actual dated source files and canonical output roles, without rewriting sources.
