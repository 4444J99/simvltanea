# Photos Universe Proxy

Generated: `2026-06-30T17:31:39.055490+00:00`

This is a public-safe creative steering proxy for the triptych incubator. It
contains aggregate proof only: no raw media paths, no raw hashes, no Photos
library writes, no file moves/deletes, and no render authorization.

## Source

- Photos lane head: `d45b030d1427826c1c0c54b3cb54d552b94104a0`
- Aggregate receipt: `docs/photos-universe-duplicate-proof-2026-06-29.json`

## Aggregate Proof

- Candidate groups total: `19308`
- Processed groups total: `80`
- Hash-matching duplicate groups: `79`
- Hash-rejected candidate groups: `1`
- Bytes in hash-proven duplicate groups: `663972891`
- Photos metadata preview assets: `50`
- Screenshot-flagged preview assets: `32`

## Creative Steering

- Allowed use: source-selection steering through local proxy manifests only.
- Duplicate groups: Treat hash-proven duplicate groups as dedupe evidence, not as source media.
- Rejected candidates: Treat rejected duplicate candidates as signal that visual similarity needs human review before any staging decision.
- Screenshot preview: Use the screenshot-heavy preview as a candidate mood/source lane only after human-selected exports or generated proxies exist.
- Next triptych action: Review staged project manifests and dry-run edition builders; do not call Photos export or render from this proxy.

## Gates

- No Photos export, album mutation, delete, move, or library write follows from this proxy.
- No render is authorized by this proxy; render queues still require their own dry-run gates.
- Operational JSON/Markdown proxies may be regenerated under ignored `work/`.
