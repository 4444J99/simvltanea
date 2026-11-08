# Persistent SIMVLTANEA application

One application frame provides Watch, Compose and Iterations. View frames mount lazily once and retain separate sessions. Switching pauses the departing transport; returning requires an explicit Play action. Hiding the browser tab also pauses its active transport. Studio and composition schemas remain separate; no automatic conversion is claimed.

Iterations lists successful recorded Cloudflare builds as external snapshots, with provenance and an explicit reconstruction gap for older source-only versions. Historical YouTube material is excluded. The catalog is a dated snapshot, not an automatically refreshed service.

Verification: Node checks exercise stable frame identity, lazy mounting, outgoing pauses, archive routing, invalid hash fallback and current navigation. Existing media/runtime harnesses that assume the root document itself is Studio require migration to watch.html. Physical iPhone acceptance remains open.
