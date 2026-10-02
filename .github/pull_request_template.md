# Pull request

## Intention
<!-- What living intention does this PR finish? Link issue(s). One intention per PR. -->

## Lane
<!-- lane/verify | lane/heal | lane/expand | lane/evolve | hotfix | trunk -->

## How to verify
<!-- Exact commands / evidence that prove the class is gone -->
```bash
set -o pipefail
ls-lint --config config/lint/ls-lint.yml
git diff --name-only --diff-filter=ACMR -z origin/main...HEAD -- '*.md' |
  xargs -0 -r npx --yes markdownlint-cli@0.45.0 \
    --config config/lint/markdownlint.json --ignore-path config/lint/markdownlintignore --
python3 -m tools.verification.verify_repository_structure
python3 -m pytest -q
python3 -m tools.verification.verify_local_lifecycle
python3 -m tools.verification.verify_editions
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
