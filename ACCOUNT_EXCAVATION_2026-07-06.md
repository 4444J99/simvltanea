# Account Excavation - 2026-07-06

This is the tracked, non-raw summary for the Triptych-first account excavation.
The machine receipt with hashes, search hits, and ChatGPT IDs is local-only:

```text
work/account-excavation-20260706/account-excavation.json
work/account-excavation-20260706/account-excavation.md
```

Generated receipt: `2026-07-06T18:04:15Z`.

## Worktree Boundary

- Worktree: `/Users/4jp/Workspace/4444J99/portvs/.worktrees/triptych-account-excavation-20260706`
- Branch: `work/triptych-account-excavation-20260706`
- Owner surface: Portvs, inside `incubator/triptych-video-canon/`
- Limen queue state was not touched.
- The other live Codex sessions were not touched.

## Located Media

| Asset | Local path | Receipt fact |
| --- | --- | --- |
| TripTicks | `/Users/4jp/Downloads/TripTicks.mp4` | found, 470.483s, 1280x720, h264 |
| God's Ears second draft | `/Users/4jp/Downloads/2020 04 26   god's ears   second draft.mp4` | found, 112.013s, 1280x720, h264 |
| Story Triptych render | `/Users/4jp/Downloads/story-triptych.mp4` | found, 278.021s, 1080x1920, h264 |
| Glyph cascade desktop pack | `/Users/4jp/Desktop/glyph-cascade-ig-2026-06-29` | found, 4 files |

The glyph cascade desktop pack contains:

- `01-remote-canon.png`
- `02-share-recycle-remix-animated-ig.mp4` - 6.0s
- `02-share-recycle-remix.png`
- `03-minimal-ideal-forms.png`

No source media was copied into git.

## Excavated Context

The receipt found these high-signal local surfaces:

- `/Users/4jp/Workspace/session-meta/TRIPTYCH.md` - the source concept note for Tryptich/Triptych as a three-panel organizing principle.
- `/Users/4jp/Workspace/session-meta/analysis/PARTICLE-LEDGER-2026-06-05.md` - additional Triptych references.
- June 28 Codex sessions with Triptych, Narcissus, mocap, and Instagram planning signals, including:
  - `/Users/4jp/.codex/sessions/2026/06/28/rollout-2026-06-28T10-03-38-019f0e8b-0052-75f1-9a46-fecaad48e082.jsonl`
  - `/Users/4jp/.codex/sessions/2026/06/28/rollout-2026-06-28T10-28-13-019f0ea1-820c-7003-9444-ce7e5e3142c3.jsonl`
  - `/Users/4jp/.codex/sessions/2026/06/28/rollout-2026-06-28T10-32-30-019f0ea5-6de9-7b22-9f5b-c948b4e1adbf.jsonl`
- June 29 Codex sessions with Triptych, Narcissus, glyph cascade, audiovisual, and visual-form planning signals.
- July 6 Codex sessions for the active account excavation, including the current prompt surface:
  - `/Users/4jp/.codex/sessions/2026/07/06/rollout-2026-07-06T12-01-59-019f382a-396b-7413-963a-2cfb3118bf86.jsonl`

Broad match counts from the receipt:

- `session-meta`: 822 matches
- Triptych incubator: 38 matches
- `organvm/claude-runtime-state/plans`: 476 matches
- public/private portfolio checkouts: 169 matches combined
- `media-ark`: 7 matches
- Claude desktop project transcripts: 2,128 matches
- Codex June 28 sessions: 15 matches
- Codex June 29 sessions: 88 matches
- Codex July sessions: 267 matches

## ChatGPT Local Status

Correction after re-checking the prior work: ChatGPT is not a fresh backend-only
problem here. The local methods already exist.

Present local method files:

- `/Users/4jp/Workspace/session-meta/ingest/adapters/chatgpt.py` - parses native ChatGPT export JSON mapping trees.
- `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine/src/conversation_corpus_engine/import_chatgpt_export_corpus.py` - imports native ChatGPT export bundles.
- `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine/src/conversation_corpus_engine/import_chatgpt_local_session_corpus.py` - imports a desktop local-session bundle through the signed-in app session.
- `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine/src/conversation_corpus_engine/chatgpt_local_session.py` - discovers the desktop session and backend routes.
- `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine/scripts/chatgpt_exporter_to_bundle.py` - converts ChatGPT-exporter output into the importer bundle shape.

The current `session-meta` checkout also has a manifest proving the prior
ChatGPT archive/corpus existed:

- Manifest: `/Users/4jp/Workspace/session-meta/ingest/manifest.jsonl`
- Manifested ChatGPT entries: 2,709
- Manifested bytes: 1,226,638,602
- Lanes: `attachments` 2,685, `corpus` 14, plus import logs and metadata
- Important manifested corpus files include `threads-index.json.gz`, `pairs-index.json.gz`, `action-ledger.json.gz`, and `unresolved-ledger.json.gz`
- Important manifested transcript files include `attachments/conversations-000.json`, `conversations-001.json`, `conversations-003.json`, `conversations-006.json`, `conversations-007.json`, `conversations-011.json`, and more.

But the payload tree is not present in this checkout:

```text
/Users/4jp/Workspace/session-meta/data/session-transcripts/chatgpt
```

So the right state is:

- The local methods were built.
- The archive is documented in the manifest.
- The actual archive files are missing from this working checkout.
- The live app/backend route is only a fallback or current-session supplement.

The live desktop-app route is still confirmed:

```text
https://chatgpt.com/backend-api/gizmos/<g-p-id>/conversations
```

Earlier receipt runs indexed:

- 79 local `project-g-p-*` directories from `~/Library/Application Support/com.openai.chat`
- 20 non-empty project indexes
- 126 recent global conversation rows

The refreshed receipt skipped live backend calls to avoid more rate limiting.
Earlier live runs found recent global candidates with relevant titles, but detail
fetches hit ChatGPT `429` rate limiting:

- `6a496695-3960-83ea-848e-2d6d33da4741` - `Instagram Automation for Design`
- `6a44f315-2200-83ea-8807-99422496bce0` - `Podcasting and Comedy Struggles`

Do not treat the ChatGPT excavation as complete until either the manifested
archive payload is restored into the checkout or a later low-rate/browser pass
extracts those two live-session conversations.

## Account Architecture Recommendation

- Keep `4444jj999` as the personal/local Anthony account: real person, friends, local audience, artist-engineer identity, rough life context.
- Use one separate audiovisual work account for Triptych, Narcissus, films, photography, music, glyph-cascade, and visual experiments.
- Do not split one account per product yet. Split only when a product has a stable buyer segment, offer, and cadence.
- Put productized design-media pain-point work behind a product/workbench surface later. Narcissus can be redone there if it becomes a useful tool/offering rather than just a visual series.
- Launch order should stay autobiographical: Triptych first, Narcissus redo second.

## Next Excavation Gates

1. Restore or locate the manifested ChatGPT archive payload for `data/session-transcripts/chatgpt/`; then scan the native export/corpus locally before any live backend call.
2. If the payload is unavailable, run a low-rate or browser-inspected ChatGPT detail pass for the two recent global candidates above.
3. Review the Claude desktop project hits only for high-signal terms, not generic `4444j99`.
4. Inspect TripTicks against the existing `story-triptych.mp4` render and decide whether the first public post is a remake, an archival release, or a side-by-side origin/remake statement.
