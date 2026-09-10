## Intention
<!-- What living intention does this PR finish? Link issue(s). One intention per PR. -->

## Lane
<!-- lane/verify | lane/heal | lane/expand | lane/evolve | hotfix | trunk -->

## How to verify
<!-- Exact commands / evidence that prove the class is gone -->
```bash
python3 -m pytest -q
python3 tools/verify_local_lifecycle.py
python3 tools/verify_editions.py
```

## Checklist
- [ ] Tests pass (120/120)
- [ ] `verify_local_lifecycle.py` → `local lifecycle ok`
- [ ] No generated lane files in diff (`git status --porcelain`)
- [ ] Linked issue(s)

## Notes
<!-- Preserve unique residue if amalgamating a family: amalgamated-into:#N -->
