# Preview staging repair

Repairs consumer PR #28 from `f0c9be42b22f03b6ea2e2d1c689d3d06dd92fb2f`.
The shared-engine pin and owner implementation are unchanged. Owner PR #3 was
inspected at `69d5ab9d0a434d967026fbfeb66347104c59918d`; its integration and
acceptance remain separate.

Only files named in the consumer's accepted runtime graph enter the staged
engine directory. Their destination bytes are hashed before an HTML receipt is
written. The entire preview is built in a fresh sibling directory, then published
with an atomic directory rename or exchange. Copy, verification and exchange
failures leave any previous preview intact. Successful replacement removes stale
files rather than retaining them. Missing-engine resolution produces a new clean
fallback generation with a visible reason and no engine scripts or verification
receipt. Reused destinations containing symlinks are refused.

Atomic replacement of an existing directory uses Linux `renameat2(RENAME_EXCHANGE)`
or macOS `renamex_np(RENAME_SWAP)`. Filesystems or hosts without that operation
refuse replacement while preserving the previous preview. Linux exchange was
executed here; macOS and Windows were not exercised. This is a filesystem
publication guarantee, not a transaction spanning multiple HTTP requests or a
power-loss durability guarantee. An active browser should reload after a rebuild.

Resolver and refusal tests use a synthetic graph and actual isolated Git history.
Production source verification still uses the unchanged accepted pin. Separate
owner integration suites skip only an absent dependency; a discovered invalid
owner still fails verification. CI explicitly runs the hermetic suites without
checking out another repository.

## Verification in this repair environment

- `PYTHONPATH=src python -m unittest simvltanea.browser.test_preview_staging simvltanea.browser.test_shared_engine -q`:
  31 tests passed; one owner integration class skipped because the owner was absent.
- `PYTHONPATH=src python -m unittest simvltanea.browser.test_browser_runtime.PlanTests simvltanea.authoring.test_composition_model simvltanea.authoring.test_audio_model simvltanea.browser.test_shared_engine_runtime -q`:
  33 tests passed; one owner browser integration class skipped because the owner was absent.
- Feature boundaries, repository structure, layout synchronization, JavaScript
  syntax and `git diff --check` passed.
- Regression cases cover untracked engine files, source mutation during copying,
  destination corruption while source bytes remain valid, copying failure,
  failed atomic exchange, successful replacement, clean missing-engine fallback,
  symlink refusal and non-object provenance JSON.

The existing exact JSON source-policy exception and installed wheel package-data
inclusion were preserved. Runtime integration tests also retain the numeric
Playwright time argument correction. Historical PR evidence has not been rerun
or promoted to current-head acceptance.

Playwright and Chromium are not installed in this environment. No new browser
execution, real original-media acceptance, GPU/headset/mobile acceptance or
deployment acceptance is claimed. Existing owner coordination holds and review
requirements are unchanged. This repair does not merge either PR.
