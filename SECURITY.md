# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| `main` (latest) | ✅ |

Historical tags (none currently) are unsupported.

## Reporting a vulnerability

Do not open a public issue for security-sensitive reports.

- Preferred: use GitHub's **Report a vulnerability** (Security tab → Advisories) on `4444J99/simvltanea`.
- Fallback: contact the maintainer via the profile email associated with `@4444J99` on GitHub.

Include: affected file/commit, reproduction steps, and impact. No credentials or production data in the report.

## What not to commit

Secrets, credentials, production media, and raw photo-library paths must never be committed (see `CONTRIBUTING.md` and the `FORBIDDEN_TEXT` gate in `tools/verify_editions.py`).
