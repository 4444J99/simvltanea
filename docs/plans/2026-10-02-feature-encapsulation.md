# Feature encapsulation

Implement explicit lazy feature APIs, migrate cross-feature imports to those APIs,
co-locate regression tests and guides, preserve legacy commands, and enforce
imports with an AST check in CI. Validate discovery and existing regressions.

## Validation

- Clean checkout: 109 scoped tests and 275 subtests passed.
- Clean-checkout repository structure and feature import boundaries passed.
- Both discovery commands collect 212 tests.
- Wheel build passed; both renamed JavaScript assets and layout.toml are present.
- Full local suite: 199 passed; failures include the installed FFmpeg rejecting
  filter_complex_script, one browser clock-discontinuity assertion, and the
  existing nonignored generated directories rejected by the structure contract.
- Existing artifact-001, packages, runtime-proof, samples, and site directories
  were retained. Verification checkout is retained in the system temporary
  directory as simvltanea-feature-check-l77y8mop.
