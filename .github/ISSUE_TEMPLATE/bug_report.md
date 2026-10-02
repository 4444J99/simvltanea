---
name: Bug report
about: Report a correctness or lifecycle failure
title: "[bug] "
labels: ["bug"]
---

## Intention / invariant broken
<!-- Which invariant or contract failed? Reference docs/BRANCHES.md green definition. -->

## Repro
```bash
# minimal commands
python3 -m pytest tests/test_xxx.py -v
python3 -m tools.verification.verify_local_lifecycle
```

## Evidence
<!-- Logs, SHA, branch, CI run link -->

## Finish line
<!-- What would prove the class is gone? -->
