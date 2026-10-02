# Repository-specific derivation and governance

## Scope and activation

This is the deliverable index and explanation for the **draft**
`repository_profile` binding in `src/simvltanea/layout.toml`.
It implements a bounded application of the Repository Ideal-Form Derivation and
Governance Handoff, not a replacement repository layout or a conformance claim.
The current effective `[contract]`, `[paths]`, `[policy]`, and `[lint]` tables
are unchanged. No runtime, media, edition, archive, release, or deployment
behavior is changed by this profile.

The initial reader accepts profile `1.0.0-draft.1`, metadata binding
`simvltanea.repository-profile/v1`, and vocabulary `1.0.0` exactly. It classifies
all **22 existing logical roles** and registers **three new maintenance objects**.
Other repository files have not been given invented identities or inferred
semantic names. Existing structure, naming, edition, and lifecycle checks remain
responsible for their existing scopes.

Only draft preview is implemented. `--enforce` always fails; changing the state
to approved, effective, deprecated, or rolled-back also fails in this reader.
The maintainer identified by `.github/CODEOWNERS` must approve the exact profile,
compatibility decision, migration scope, and recovery plan before a successor
can implement activation. This document is not that approval. A merge of the
preview implementation alone does not activate the profile.

## Observed repository and protected baseline

The derivation baseline is repository ID `1364497735`, `4444J99/simvltanea`, at
`f063a3d2aec61bf075d8d7243f9d4300af6c42f2`. The initial live read found `main` and
all four standing lanes at that commit and no open pull requests. These are
observations of that read, not permanent assertions about the branches.

The implementation request authorizes bounded code, metadata, tests, and
explanations on an isolated working branch, with review through the existing
branch constitution. It does not authorize direct commits to main, movement or
retirement of the user's local checkout, raw-media publication, artist acceptance,
release, or production activation.

This execution used GitHub API reads and a fresh, bounded source reconstruction
for local unit tests. The reconstruction is **not a full checkout**. User-local
staged, unstaged, untracked, ignored, nested-repository, worktree, reflog, and
large-file state was not accessible. No local-user paths or contents were copied
into these projections. The separately owned custody and retirement work in
issue #12 remains open; neither remote Git presence nor these tests proves
independent encrypted backup or restore.

Recovery for this additive review branch is to reject it without changing main.
If later merged, use a reviewed revert of its commit rather than history rewriting.
There are no moves, deletions, schema conversions, bridges, or original-file
retirements in this tranche. Existing archival and baseline bytes remain intact.

## Characterization and the ideal form

SIMVLTANEA is a Python audiovisual artwork/system and operational tool suite,
with browser JavaScript, FFmpeg rendering, authored composition models, synthetic
proof generation, production-edition metadata, and preserved historical records.
Its consumers include Python imports, module commands, authoring JSON, the browser
runtime, edition workflows, GitHub CI, and readers of published provenance.

The evidenced topology is the existing responsibility-based package and workflow
groups, not a new generic tree. Runtime authoring, browser behavior, rendering,
and generators stay in the package. Operational verification stays with the
other operational commands. Governance regressions stay with the current test
suite. Current explanations stay in the governance documentation group. Editions
retain their existing registry. Generated/private outputs remain outside tracked
authorities, while historical originals and curated evidence remain distinct.
No cross-repository split, consolidation, or estate-level registry is introduced.

The three new objects demonstrate this derivation:

| Stable identity | Registered class and concept | Derived physical location |
| --- | --- | --- |
| `simvltanea.governance.profile-verifier` | verification command; repository profile | `tools/verification/verify_repository_profile.py` |
| `simvltanea.governance.profile-tests` | governance test; repository profile | `tests/governance/test_repository_profile.py` |
| `simvltanea.governance.profile-guide` | governance guide; repository profile | `docs/governance/REPOSITORY_PROFILE.md` |

The identity is not computed from the path. The class supplies the logical role,
responsibility group, prefix, case, and extension; the concept supplies its
registered term. `[paths]` supplies the physical role location. Their combination
produces the name and path. Renaming a concept or relocating a role leaves the
identity intact but changes a proposed consumer-facing path; it never moves files.
A changed responsibility requiring semantic replacement needs a new identity
and an explicit replacement mapping, not reuse of the old identity by convenience.

## Authority and standards ledger

| Fact family | Canonical source and write path | Projection or validation |
| --- | --- | --- |
| Physical roles and placement | Existing `[paths]` and `[policy]` in `layout.toml`; reviewed layout change | `simvltanea.paths`, `tools.paths`, structure and lifecycle checks |
| Lint exclusions | Existing `[lint]` in that manifest | `sync_layout`; generated Git and lint exclusions |
| Effective spelling rules | `config/lint/ls-lint.yml`, as declared by `NAMING.md` | Existing ls-lint; the new profile pins its Git blob, not a copied grammar |
| Review owner | `.github/CODEOWNERS`; owner-reviewed PR | Pinned source locator, not a second editable owner list |
| New class, concept, identity, relationship, and lifecycle facts | `repository_profile` in the same manifest | Read-only derivation and strict model validation |
| Production editions | `editions/registry.json` and its existing validator | Not copied into the new profile |
| Historical catalog | `archive/PROJECT_MANIFEST.md`; annotate rather than rewriting originals | Pinned source locator; not rights, backup, or artist approval |
| Package and verification dependencies | `pyproject.toml` | Existing packaging and test installation |
| Composition/audio contracts | Existing implementation, architecture documents, and regression fixtures | Existing model, browser, render, and historical comparison tests |

The three adopted external-to-the-profile file inputs are pinned by Git blob
identity in `repository_profile.authorities`. Their bytes are verified by
`--check`. A changed authority is a reviewable input update, not permission to
silently refresh the expected hash. The layout, embedded vocabulary, classes,
and object facts are read together; the report includes their combined canonical
input SHA-256. The CLI also records its own implementation SHA-256.

SemVer 2.0.0 informs version syntax and compatibility terminology; the parser
checks prerelease numeric identifiers and rejects leading zeroes. The named
specification is `https://semver.org/spec/v2.0.0.html` (CC BY 3.0); it is not
fetched at validation time or copied as a new vocabulary database. Python's
existing standard-library TOML binding is retained. No additional database,
YAML dependency, external taxonomy service, or per-file sidecar is introduced.

The existing spelling policy permits both screaming-snake and kebab Markdown
names, while the naming guide recommends screaming-snake for canonical docs.
The draft's canonical-guide rule chooses that already permitted subset. It does
not retroactively prohibit other currently conforming Markdown names.

## Metadata binding, facets, and trust boundaries

The equivalent machine contract is `derive()` in the new verifier. Tables and
records have exact required fields; unknown fields, schema versions, vocabulary
versions, states, object classes, concepts, relationships, and missing authorities
fail visibly. There are no implicit defaults or inferred filename classifications.
TOML duplicate keys are rejected by the native parser. All declaration changes
are reviewed through the canonical manifest, not edited in generated previews.

The orthogonal controlled facets are object class, concept, lifecycle, and access.
Role records additionally declare material, lifecycle, and purpose. Relationship
types are `tests` and `documents`, with source-class and target-integrity checks.
Keywords are non-authoritative discovery text and cannot affect derived paths.
Git release tags are unrelated to those keywords.

The initial naming binding accepts ASCII registered terms, preserving rather than
transliterating unknown terms. Role paths are checked for canonical relative form,
case-folded/NFC collisions, reserved device names, unsafe characters, and a draft
240-byte relative-path budget. This is a new scoped preview constraint, not a
claim of complete Windows support or an amendment to the effective layout reader.
Filesystem checks reject symlinks for audited records, including parent escapes.
Only public, active registered objects are projected. The tool is not a secret
scanner or an access-control system; never register protected facts as public.

Historical, baseline, and generated/private scopes have explicit exceptions with
reason, canonical authority, owner source, compatibility effect, and review event.
There is no automatic expiry deletion, migration, archive rewriting, or cleanup.

## Compatibility and migration decisions

The package version, existing layout contract `0.1.0`, audiovisual schema IDs,
new profile version, vocabulary version, implementation version, Git revisions,
edition identities, and historical titles remain independent. The additive TOML
table is ignored by the existing layout reader; no existing role or policy value
is changed. The new reader is intentionally strict and prerelease.

The proposed stable surface is the registered-fact-to-path derivation and its
structured report. Before activation, the owner must approve supported readers,
writers, version ranges, and diagnostic compatibility. A change to a promised
canonical path, admitted record, class meaning, or strict-reader field set can be
breaking even when an added field looks optional. A major label alone is not a
migration. Existing consumers must be mapped and repaired, with aliases or an
explicit cutover, before any later move. No forward compatibility with an unknown
profile or schema is claimed by this reader.

| Actual-to-ideal difference | Classification | Implemented treatment or remaining condition |
| --- | --- | --- |
| Existing roles lacked explicit material/lifecycle characterization | Missing metadata | Characterize all 22 roles without moving them |
| Maintenance names required arbitrary selection | Missing derivation | Three registered classes and objects now derive names from meaning and responsibility |
| Shared facts could become competing copies | Authority conflict risk | Reuse layout, ownership, spelling policy, catalog, and edition authorities |
| No reviewable semantic profile or activation boundary | Missing governance | Draft binding, scope, explanation, and fail-closed activation boundary |
| Old command/output references in the branch guide | Stale projection | Repair active instructions only; historical records stay unchanged |
| Wider repository objects lack registered semantic identities | Applicable-deferred | Owner-led incremental classification; do not infer full coverage from the three objects |
| Existing package/layout compatibility promises are incomplete | Compatibility debt | Preserve versions and paths; inventory consumers before stable activation |
| Some CI actions, system packages, and Python dependencies are mutable | Reproducibility debt | Existing toolchain unchanged; review lock/pin updates before claiming full reproducibility |
| Independent local custody and restore are not verified | Blocked | Owner continues issue #12; no retirement or custody claim here |

The migration map for this tranche consists of the three new objects above and
additive metadata/documentation updates. No old object has a new physical target.
For a future existing-object change, record its stable identity, current/target
paths, governing facts, consumer inventory, minimum version effect, collision and
reference analysis, bridge/cutover, owner, ordered dry run, rollback, and acceptance
evidence before writing. That future map is not supplied by a guessed rename.

## Executable verification

```bash
# Read-only deterministic derivation; does not require media or browser execution.
python3 -m tools.verification.verify_repository_profile --json

# Explicit shadow audit of registered files and pinned existing authorities.
python3 -m tools.verification.verify_repository_profile --check --json

# Positive and deliberately invalid metadata/path/authority/reference cases.
python3 -m unittest discover -s tests/governance -p 'test_repository_profile.py' -v

# Keep the existing repository gates and full runtime regressions.
python3 -m tools.verification.sync_layout
python3 -m tools.verification.verify_repository_structure
python3 -m unittest discover -s tests -v
python3 -m tools.verification.verify_local_lifecycle
```

Exit `0` means the requested scoped preview/check succeeded, not repository
conformance. Exit `1` means a registered-object or authority-pin deviation was
observed. Exit `2` means invalid/unsupported input, unavailable context, or an
activation attempt. Model errors expose stable diagnostic categories without
printing submitted metadata or private input paths. JSON ordering is deterministic
for the same input and state; provenance digests can change when input changes.

Both local development and existing CI discover the same unit tests. In a full
checkout, the integration test emits a **shadow report** rather than turning
pin drift or draft conformance into a new blocking CI gate. `--check` may be run
explicitly for the dry-run exit status. Existing blocking rules remain unchanged.
No CI or repository protection configuration is changed in this tranche.

The shadow report binds observed errors to HEAD, staged/unstaged diff digests,
and the Git-visible path inventory digest. It explicitly excludes untracked
content and ignored/private work from that identity; it is not a full custody
receipt. Exact invocation, environment, timestamp, code hashes, output logs, and
CI status belong in the associated implementation receipt, not a mutable claim
that the current tree will always pass. Full media/browser validation and artist
acceptance remain distinct from governance tests.

## Deliverable and applicability index

Owner for each item is the maintainer resolved through `.github/CODEOWNERS`.
This table indexes the current draft implementation scope; a deferred item is
not reclassified as not applicable merely because approval or access is missing.

| Deliverable | Current status | Authoritative locator and remaining condition |
| --- | --- | --- |
| 1. Current-state evidence | applicable-complete | Protected baseline section plus exact implementation/PR receipt; remote tracked scope only |
| 2. Characterization and scope | applicable-complete | Characterization section and `repository_profile.role_metadata` |
| 3. Authority and standards ledger | applicable-complete | Ledger above and pinned `repository_profile.authorities`; full toolchain locking separately deferred |
| 4. Identity/classification model | applicable-complete | `repository_profile.objects`, role metadata, and derivation rules; three-object onboarding scope |
| 5. Vocabulary and facets | applicable-complete | `repository_profile.concepts`, classes, and the strict binding; broader domain vocabularies deferred |
| 6. Metadata contract | applicable-complete | `derive()` with positive/negative tests and existing native TOML binding |
| 7. Normative ideal-form profile | applicable-deferred | Draft in `layout.toml`; exact owner approval and activation successor still required |
| 8. Gap analysis | applicable-complete | Actual-to-ideal table; full file-level semantic classification not claimed |
| 9. Migration and recovery | applicable-complete | Additive-only map and recovery above; later moves require their own approved maps |
| 10. Executable enforcement | applicable-deferred | Preview, shadow audit, and tests implemented; blocking activation intentionally unavailable |
| 11. Governance and exceptions | applicable-complete | Explicit exceptions and review events; no automatic approval or retirement |
| 12. Verification | applicable-deferred | Local unit receipt plus exact-head CI result; full supported-context and conformance evidence remain required |

| Phase or validation family | Applicability and evidence boundary |
| --- | --- |
| Phase 0 | Remote branch baseline and protected-work boundary established; inaccessible local custody remains blocked in issue #12 |
| Phases 1-2 | All existing logical roles characterized; only three maintenance files semantically registered |
| Phases 3-5 | Existing authorities reused, pinned inputs checked, metadata/facets modeled; estate-wide taxonomy outside this request |
| Phase 6 | Deterministic new-object derivation implemented; no retroactive normalization |
| Phase 7 | Version dimensions and migration obligations documented; stable consumer promises and full toolchain pins deferred |
| Phase 8 | Same model and tests available locally/CI; draft audit is shadow-only |
| Profile activation | Unauthorized without exact owner approval; blocked by the current reader |
| Phase 9 | Additive implementation requires no existing-object moves; future breaking migrations deferred |
| Syntax, values, identities, relationships | Positive and negative unit tests; exact schema and version handling |
| Names, paths, collisions, Unicode, portability | Unit fixtures and registered-file audit; not all filesystem/hardware platforms certified |
| Authority, pins, missing inputs, exceptions | Unit fixtures plus full-checkout shadow audit; no live-network lookup during validation |
| Generated, ignored, historical, private material | Preserved; existing lifecycle/structure gates retained; no private content ingestion |
| Backward compatibility | Existing layout tables retained byte-for-byte before the additive binding; existing tests still required |
| Forward compatibility | Unknown schema/profile/vocabulary rejected; no unsupported acceptance promise |
| Browser, rendering, decoded historical comparison | Existing full suite and CI remain the evidence source; not substituted by new governance tests |
| Release, deployment, publication, artist acceptance | Unauthorized in this tranche; no such completion claim |

Neither request-wide ideal-form completion nor repository-conformance completion
is asserted by this draft. The next owner decisions are scoped object onboarding,
compatibility/pinning review, exact profile approval, and a separately reviewed
activation implementation. Independent custody work retains its existing owner.
