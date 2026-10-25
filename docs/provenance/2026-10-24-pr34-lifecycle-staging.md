# PR 34 lifecycle and staging repair

Inspection date: October 24, 2026 (America/New_York).
Repository: `4444J99/simvltanea`; existing PR: <https://github.com/4444J99/simvltanea/pull/34>.
Inspected starting head: `36102eca654e9cc7ec8abe721f8578984488219f`.
The 22 unresolved threads describe overlapping findings, grouped below. No finding was rejected as a false positive.
Pillow PR 33 is independently owned; this repair does not change its dependency pin.

## Findings and regression evidence

| Root cause | Reproduction and correction | Regression coverage |
| --- | --- | --- |
| Deferred pause lost after a boundary transition | A real delayed activation never consumed the request. Consume it when the last transition settles. Remove the old test's manual pause application. | `test_paused_intent_during_busy_transition` |
| Retry reused failed resources and erased subsequent failure state | Retry after mounted-node failure could encounter duplicate loops; a failed retry could become non-retryable. Release the previous generation and route initialization errors through the failure handler. | `test_pr34_retry_releases_nodes_and_can_retry_again_after_failure` |
| Soundtrack restart used stale transport position | Recovery restarted the audio envelope/offset from the last pause/seek. Use composition time after re-anchoring. | `test_pr34_interruption_freezes_videos_and_recovers_current_offset` |
| Audio suspension let native video advance against a frozen clock | Freeze transport and pause videos; align all sources before explicit or automatic recovery. Keep paused status truthful. | Same recovery test exercises both paths; `test_pr34_recover_while_paused_does_not_publish_playing` |
| Disposal did not invalidate asynchronous initialization | Delayed plan, bytes, digest, audio decode, and media activation could republish readiness after disposal. Guard each asynchronous boundary with an epoch; abort media waits; ignore stale callbacks. | `test_pr34_dispose_cancels_plan_and_media_initialization`, `test_pr34_dispose_cancels_audio_decode`, `test_pr34_dispose_cancels_media_activation`, `test_pr34_stale_initialization_cannot_overwrite_new_generation`, `test_pr34_decoded_frame_callback_after_dispose_is_inert` |
| Reinitialization retained completion | Finished runtimes remained unstartable after disposal/reinitialization. Reset completion with transport state. | `test_pr34_finished_runtime_reinitializes_for_gesture` |
| Symlink destination containment followed the replaceable final entry | Second symlink import incorrectly treated an external staging entry as library storage. Check the destination parent, resolving ancestor symlinks; unlink the staging entry only. | `test_repeat_symlink_staging_preserves_original` also checks a directory alias into the library remains forbidden |
| Edition and Photos provenance did not bind the destination | An edition marker alone, or a project belonging elsewhere, authorized collisions. Require library identity where applicable and canonical staging destination. Bind markers to their location and preserve both Photos and edition metadata across repeat imports. | `test_provenance_requires_library_and_destination`, `test_copied_staging_markers_do_not_authorize_new_destination`, `test_edition_manifest_preserves_photos_provenance_for_reimport` |
| Edition presets promoted reused partial coverage | Settings reapplication inferred completeness without importing more media; default Photos limit 12 was ignored. Import evidence owns coverage; unknown ingestion stays unknown. | `test_reused_bounded_import_cannot_be_promoted`, `test_default_photos_limit_is_bounded`, `test_all_local_preset_without_import_evidence_is_not_complete` |
| Offset selections claimed complete albums | Unlimited imports with a nonzero offset omit earlier assets. Mark them partial. | `test_offset_import_is_partial_without_limit` |
| Decimal viewports used the strict compiled-rational parser | Object-shaped decimal viewports threw. Permit finite numeric coordinates in that path; preserve strict compiled-clock and plan-field parsing. | `test_pr34_decimal_viewport_and_partial_to_full_fit` |
| Full-frame slices retained partial-slice stretching | A prior partial slice left `objectFit: fill`. Share slice resolution across rendering paths and restore authored fit for full-frame views. | Same viewport regression |
| New optional loop fields broke historical snapshots and round trips | Omit unset extensions and normalize list color profiles on deserialization. | `ReviewIdentityTests` |
| Object addresses contaminated seeded candidate identity | Missing identifiers used process-local addresses. Require a stable id, source, or path. | `test_neighbor_selection_rejects_unidentified_candidates` |
| Invalid decoder caps produced NaN | Invalid input disabled all decoders. Use the documented default while retaining finite 0–6 clamping. | `test_pr34_invalid_decoder_cap_uses_default` |

Additional review and cancellation checks found and corrected pause loss during a running seek, suspension during asynchronous startup, repeated interruption during recovery, and unlimited imports omitting unavailable originals. These are covered by `test_pr34_pause_during_running_seek_prevents_restart`, `test_pr34_interruption_during_async_start_cannot_publish_playing`, `test_pr34_second_interruption_during_recovery_is_not_lost`, and `test_missing_originals_cannot_claim_full_album`. Successful opt-in Photos exports count as staged originals rather than omissions.

## Verification at publication

- Python staging plus authoring: 55 passed, with five passing subtests.
- Latest-source native lifecycle regressions: 14 passed, including repeated interruption recovery. The runner used existing synthetic fixtures with the current runtime source, without regenerating media while the full suite owned fixture generation.
- Node paging/slicing/callback helper checks: three passed.
- Structure, feature boundaries, layout synchronization, plan index, local lifecycle, edition presets, JavaScript syntax, and whitespace checks passed.
- Environment: Python 3.12.14, Pillow 12.3.0, Playwright 1.57.0, Chrome for Testing 156.0.8078.47; in-memory fixture IO with real Chromium video decoding and Web Audio.
- The full historical unittest discovery command is running at publication. Its terminal result and exact-head hosted checks must be recorded in the PR conversation before integration. An earlier broad pytest run was interrupted while implementation was still changing; it is not a successful full-suite receipt.

Reproduction runs failed on the reviewed behavior before the corresponding fixes. The independent code review additionally reproduced the running-seek and repeated-recovery races in an isolated Node harness. Tests never apply the runtime's deferred pause themselves.

## Remaining acceptance and preservation

No original Photos library or real personal media was used or modified. Staging tests use disposable source bytes and verify their preservation. Existing source UUIDs and deterministic compiled composition timing remain authoritative.

Safari/iPhone interruptions and gestures, real Photos repeat import/export on macOS, and long-running real-media album playback remain acceptance requirements. The accepted shared-engine checkout was unavailable to this CLI; native lifecycle tests exercise the browser runtime and synthetic media, not acceptance of the full spatial-engine installation. Hermetic resolver tests and any skipped consumer tests must retain that distinction.

This document records engineering evidence, not artist acceptance, external delivery, or a merge authorization. Integration follows repository review and CI requirements against the corrected PR head; original PR history and unrelated local material are retained.

## Follow-up review of the first repair

CodeRabbit's completed review of `c46f6aa` raised four further functional findings. Each was reproduced and corrected in the same PR:

- Direct execution defined `ReviewIdentityTests` after `unittest.main()`. The runner now follows every test class; direct invocation runs all three identity regressions.
- Numeric slice arrays produced by authoring still rejected decimal coordinates. Slice arrays and objects now share finite coordinate parsing; arrays must contain exactly four values. Compiled clock parsing remains strict. `test_decimal_slice_arrays_render_and_malformed_arrays_fail` covers decimals, fractions, invalid lengths, NaN, and strict clock rejection.
- Reapplying settings changed recorded `unknown` coverage into an unbounded `bounded_preview`. `test_unknown_coverage_is_stable_across_reapplication` preserves unknown on repeated application.
- Date/UUID filters and actual duration omissions could leave partial imports labeled complete. Duration filtering now happens after album scoping, records the actual omitted count, and retains existing Live Photo handling. Active date/UUID filters and duration omissions mark partial coverage. The real disposable SQLite-catalog test `test_cli_records_album_duration_omissions_with_real_sqlite_catalog` exercises the complete CLI twice: a 60-second clip omitted by the default 45-second cap produces partial metadata, while the same import with no actual duration omission can be complete. Both original fixture files remain unchanged.

The additional audio-test suggestion is covered without discarding the original race reproduction: `test_pr34_second_interruption_during_recovery_is_not_lost` now exercises both resume-before-release (the lost-event race) and remaining suspended until the first recovery ends. Both cases pass. The original test already waited for the second interrupted state; merely replacing its event order would have stopped testing the lost-event race.

First-repair receipts remain historical: its clean five-suite run passed 133 tests and 29 subtests; its broader local discovery run completed 586 tests with two owner-checkout integration skips. Fresh hosted checks and review receipts for the follow-up head are required before integration.
