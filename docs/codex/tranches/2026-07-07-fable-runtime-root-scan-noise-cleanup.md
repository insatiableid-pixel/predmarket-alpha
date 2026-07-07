# 2026-07-07 Fable Runtime Root Scan Noise Cleanup

## Landing

Removed the remaining machine-specific root literals from non-runtime fixtures and an old run log:

- `tests/test_type2_reference_builder.py` now builds the odds raw-path fixture with `manual_drop_path()`.
- `tests/test_codex_macro_blocker_audit.py` now builds sibling-repo command fixtures with `project_path()`.
- `data/kalshi_run_log_2026-06-16.txt` now records a repo-relative report path.

The active-code root scan over Makefile, scripts, predmarket, top-level helpers, tests, and data is clean except for intentional negative assertion strings in `tests/test_kalshi_path_defaults.py`.

## Guardrails

- No runtime behavior changed.
- No thresholds changed.
- No labels inferred.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `python -m pytest tests/test_type2_reference_builder.py tests/test_codex_macro_blocker_audit.py tests/test_kalshi_path_defaults.py -q` -> `28 passed`
- `ruff check tests/test_type2_reference_builder.py tests/test_codex_macro_blocker_audit.py tests/test_kalshi_path_defaults.py` -> pass
- `make lint-baseline-check` -> pass (`lint 98/1422`, `format 18/94`)
- `rg -n "/home/mrwatson/(manual_drops|projects)|/mnt/c/Users/mrwat" Makefile scripts predmarket setup_env.sh run_smoke_test.sh tests data | rg -v "tests/test_kalshi_path_defaults.py"` -> no matches
