# Lab

The playable lab: a static, client-only web instrument in `app/` (ES modules, HTML
and CSS, no build step and no dependencies). The user guide, the `?data=` dataset
contract, the privacy rules and the generated configuration reference are in
[docs/authoring/LAB.md](../../../docs/authoring/LAB.md).

| Path | Role |
| --- | --- |
| `app/` | the instrument, distributed with this subpackage |
| `make_fixtures.py` | synthetic clips for the tests, written below `var/proofs/lab-fixtures/` (FFmpeg) |
| `scripts/gen_config_reference.mjs` | regenerates or checks the configuration reference in `LAB.md` |
| `tests/unit/` | `node --test` unit tests |
| `tests/e2e/` | Playwright suite (`e2e_*.py`), run by `test_lab_e2e.py` |
| `test_lab_*.py` | the Python wrappers, discovered with the other co-located suites |
| `package.json` | `"type": "module"` for Node, plus `npm run test:unit` and `npm run docs` |

Never place a dataset here: `data/`, `media/` and `still/` folders below this
directory are git-ignored and rejected by the structure verifier.
