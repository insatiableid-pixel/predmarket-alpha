# 2026-06-30 MLB BetExplorer Market Command-Center Refresh

## Summary

Updated the macro command center to recognize MLB's public BetExplorer
multi-market comparison as the latest MLB evidence state.

## Evidence

- MLB full-slate import: 13 events, 953 rows, 3 books
- MLB market comparison: 24 direct matches (`ml=22`, `run_line=2`, `total=0`)
- Current-threshold rows: 0
- Macro status: `primary_type2_betexplorer_market_closing_comparison_no_policy_change`

## Routing

All lanes remain parked. Predmarket remains the command center because no active
lane has a positive-priority local tranche.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=. pytest tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py -q`
- `ruff check scripts/codex_macro_router.py scripts/codex_macro_unlock_scout.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
- `make macro-route`
- `make macro-unlock-scout`

## Guardrails

Research-only. The router does not authorize provider/API calls, paid calls,
database writes, account/order paths, execution, threshold changes, or tradable
claims.
