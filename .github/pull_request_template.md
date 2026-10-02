# Pull request

## Intention
<!-- What living intention does this PR finish? Link issue(s). One intention per PR. -->

## Lane
<!-- lane/verify | lane/heal | lane/expand | lane/evolve | hotfix | trunk -->

## How to verify
<!-- Exact commands / evidence that prove the class is gone -->
```bash
set -o pipefail
ls-lint
git diff --name-only --diff-filter=ACMR -z origin/main...HEAD -- '*.md' |
  xargs -0 -r npx --yes markdownlint-cli@0.45.0 \
    --config .markdownlint.json --ignore-path .markdownlintignore --
python3 tools/verify_repository_structure.py
python3 -m pytest -q
python3 tools/verify_local_lifecycle.py
python3 tools/verify_editions.py
```

## Checklist

- [ ] New files and directories pass `ls-lint`
- [ ] Added or edited Markdown passes `markdownlint-cli@0.45.0`
- [ ] `verify_repository_structure.py` → `repository structure ok`
- [ ] Intentional layout changes update the structure policy and documentation in this PR
- [ ] Tests pass
- [ ] `verify_local_lifecycle.py` → `local lifecycle ok`
- [ ] No generated lane files in diff (`git status --porcelain`)
- [ ] Linked issue(s)

## Notes
<!-- Preserve unique residue if amalgamating a family: amalgamated-into:#N -->
