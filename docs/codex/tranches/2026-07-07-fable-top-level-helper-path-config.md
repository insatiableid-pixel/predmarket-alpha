# 2026-07-07 Fable Top-Level Helper Path Config

## Landing

Removed machine-specific project roots from:

- `setup_env.sh`
- `run_smoke_test.sh`
- `predmarket/mlb_platform_bridge.py` docstring

The shell helpers now self-locate from their script directory and can be overridden with:

- `PREDMARKET_PROJECT_ROOT`
- `PREDMARKET_VENV_DIR`

The MLB bridge documentation now describes the sibling-checkout artifact boundary without naming a workstation path.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No manual EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py -q` -> `19 passed`
- `bash -n setup_env.sh && bash -n run_smoke_test.sh` -> pass
- `ruff check predmarket/mlb_platform_bridge.py tests/test_kalshi_path_defaults.py` -> pass
- `python -m py_compile predmarket/mlb_platform_bridge.py` -> pass
- `make lint-baseline-check` -> pass (`lint 98/1422`, `format 17/94`)
