# Repository-specific derivation and governance

## Scope and activation

The `repository_profile` table in `src/simvltanea/layout.toml` is a bounded,
**draft, preview-only** binding: profile `1.0.0-draft.1`, metadata schema
`simvltanea.repository-profile/v1`, vocabulary `1.0.0`. It classifies the existing
22 logical roles and registers three maintenance objects, not every file.
`--enforce` and every non-draft profile state remain rejected by the reader.
A merge does not approve or activate a profile or establish GES parity.

The [initial detailed protocol and twelve-deliverable analysis](https://github.com/4444J99/simvltanea/blob/6b61c77888b4597877b09d9b0c4e932ca9e71d97/docs/governance/REPOSITORY_PROFILE.md)
is retained at its immutable implementation revision. Its initial branch states,
old test path and local-test observations are historical, not current projections.
This guide records the integration amendments; the unamended metadata validation,
authority, exception and fail-closed reader contracts remain in force.

## Current authority and placement

Stable identity is not derived from a filename. Registered class, concept and
logical-role facts derive a path; discovery keywords never affect it. Relations
`tests` and `documents` bind existing identities with class and target checks.

| Identity | Class and concept | Derived location |
| --- | --- | --- |
| `simvltanea.governance.profile-verifier` | verification-command; repository-profile | `tools/verification/verify_repository_profile.py` |
| `simvltanea.governance.profile-tests` | governance-test; repository-profile | `tools/verification/test_repository_profile.py` |
| `simvltanea.governance.profile-guide` | governance-guide; repository-profile | `docs/governance/REPOSITORY_PROFILE.md` |

The effective `[contract]`, `[paths]`, `[policy]` and `[lint]` tables retain the
integrated feature baseline. Native layout, spelling, CODEOWNERS, edition registry
and archive catalogue remain their original authorities; no competing registry
or naming database is introduced. The spelling-authority pin now identifies the
reviewed PR #20 policy blob `faf6e3b6f0d17c507f696cfdc39a73b3109d9793`.
Ownership and provenance pins are not silently refreshed. `--check` checks their
actual bytes and registered-file placement; a green general test run alone does
not establish that a shadow report contains no drift.

## Metadata, compatibility and trust

`derive()` is the strict machine contract. Unknown fields, schemas, profile or
vocabulary versions, states, classes, concepts, relationships, missing authorities,
identity collisions, unsafe paths and conflicting authorities fail visibly.
Native TOML rejects duplicate keys. The preview uses a 240-byte relative-path
budget, NFC/case-fold collision checks and portable reserved-name checks; these
are not a certification of every operating system. Audited objects cannot be
symlinks or escape their root. Protected/private objects are not projected.

Historical originals, renderer baselines and generated/private roles keep their
explicit exceptions and canonical owners. The verifier is not a secret scanner,
access-control service, private archive, original-media backup or artistic judge.
SemVer syntax does not imply that package, layout, composition/audio, profile,
vocabulary, edition and media-snapshot identities move in lockstep.

The October 3 migration moves only the profile test from
`tests/governance/test_repository_profile.py` to its operational verification
owner. Its stable ID and class are unchanged; class role/area facts, the derivation
assertion, this guide and executable commands change together. The old test is
removed from discovery rather than duplicated. No supported external test-module
import contract was identified in the reviewed repository; uninspected external
consumers are not certified absent. Runtime import/command paths do not change.

Recovery is a reviewed revert of the reconciliation, restoring its previous test
placement and pin. Do not rewrite branch history, roll back PR #20's effective
layout, infer approval, retire original media or alter historical baseline bytes.
Future promised-path/schema changes require an explicit consumer map, compatibility
decision, migration order, recovery and acceptance evidence before activation.

## Executable verification

```bash
python3 -m tools.verification.verify_repository_profile --json
python3 -m tools.verification.verify_repository_profile --check --json
python3 -m unittest tools.verification.test_repository_profile -v
python3 -m tools.verification.sync_layout
python3 -m tools.verification.verify_repository_structure
python3 -m tools.verification.verify_feature_boundaries
python3 -m unittest discover -s tests -v
python3 -m tools.verification.verify_local_lifecycle
```

Exit 0 means the requested scoped preview/check passed, not conformance. Exit 1
means observed file/pin drift; exit 2 means invalid/unsupported inputs, unavailable
context or attempted activation. Diagnostics do not echo submitted private facts.
The report binds canonical inputs and verifier hashes; the full-checkout shadow
report also binds its Git head, diffs and visible-path inventory. It is not a
complete identity for ignored/private or untracked contents.

The reconstructed October 3 candidate ran 47 focused tests: 46 passed and the
complete-checkout integration check was explicitly skipped. The reconstruction
excluded archive/evidence payload and full Git history. Full repository CI and
installed-wheel evidence must come from the assembled GitHub candidate and then
the resulting `main`, not that limited local run. The complete-checkout unit test
emits shadow diagnostics without making draft pin drift a new blocking policy.

## Deliverable and applicability index

The maintainer is resolved through `.github/CODEOWNERS`. The initial detailed
analysis remains linked above; these dispositions are scoped, not estate-wide.

| Deliverable | Integrated treatment | Remaining condition |
| --- | --- | --- |
| 1. Current-state evidence | Exact-head CI and source-reconstruction receipts | Refresh observations; do not reuse old lane/PR assertions |
| 2. Characterization and scope | 22 logical roles; artwork/system and operational consumers | No claim of whole-estate characterization |
| 3. Authority and standards ledger | Existing authorities and reviewed Git blob pins | Full toolchain locking and accepted GES binding |
| 4. Identity/classification | Three stable maintenance identities | Meaning-led broader onboarding, not guessed filenames |
| 5. Vocabulary and facets | Native controlled concepts, classes, lifecycle and access | Wider domain vocabulary decisions |
| 6. Metadata contract | Strict `derive()` and positive/negative tests | Unknown versions remain rejected |
| 7. Ideal-form profile | Draft binding retained | Exact owner approval and activation successor |
| 8. Gap analysis | Initial protocol plus this integration correction | Consumer, semantic, reproducibility and enforcement gaps |
| 9. Migration and recovery | Single test relocation and reviewed pin update | Future breaking moves need their own migration evidence |
| 10. Executable enforcement | Preview and shadow audit | Activation and native platform enforcement are not installed |
| 11. Governance/exceptions | Explicit historical/generated/private boundaries | No automatic approval, expiry deletion or retirement |
| 12. Verification | Focused tests plus assembled-candidate CI/package gates | Post-merge evidence and separately required environments |

Issue #18 retains broader consumer/reproducibility/profile-approval obligations.
Issue #12 retains its assigned-copy custody scope; the PR #20 Photos session has
separate custody and ownership obligations. None is closed by a merged preview,
a successful wheel, or synthetic media. Release, deployment, real-edition audio,
historical reconstruction and artist approval remain separate gates.

See the [integration acceptance record](../continuations/pr-19/integration-acceptance.md).
