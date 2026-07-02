# 2026-06-16 Federated Macro Router

## Scope

Implemented the first phase of the five-repo Federated Market Edge Operating System:

- `/home/mrwatson/projects/predmarket-alpha`
- `/home/mrwatson/projects/mlb-platform`
- `/home/mrwatson/projects/atp-oracle`
- `/home/mrwatson/projects/nba-analytics-platform`
- `/home/mrwatson/projects/nfl_quant_glm51_greenfield`

## Changes

- Saved the refreshed macro plan at `docs/codex/macro/federated-market-edge-os-plan.md`.
- Added `docs/codex/macro/active-universe.json`.
- Added `docs/codex/macro/status.schema.json` for `MacroRepoStatusV1`.
- Added `scripts/codex_macro_router.py` with read-only `status` and aggregate `route` commands.
- Added `make macro-status` to all five active repos.
- Added `make macro-route` in predmarket to write:
  - `docs/codex/macro/latest-status.json`
  - `docs/codex/macro/latest-decision.json`
  - `docs/codex/macro/latest-decision.md`

## Latest Routing Result

Recommended next repo: `/home/mrwatson/projects/mlb-platform`

Recommended tranche: promote MLB into the primary Type 2 sports-prop adapter by exposing no-spend odds, no-vig probability, edge, CLV, and backtest evidence.

Stop condition: stop before provider/API calls, paid historical requests, database writes, or market execution; unknown source freshness blocks promotion.

## Follow-Up Landed In MLB

After routing selected MLB, the first Type 2 coding tranche added:

- `src/mlb_platform/market/type2_edge.py`
- `src/mlb_platform/cli/type2_evidence.py`
- `tests/test_market/test_type2_edge.py`
- `tests/test_cli/test_type2_evidence.py`
- `make type2-evidence TYPE2_CANDIDATES=/path/to/candidates.json`

The surface is review-only and local-input-only. The next MLB tranche is a local/cached odds-row adapter that emits candidate JSON for `mlb-type2-evidence`.

The follow-up tranche also landed:

- `src/mlb_platform/backtest/type2_candidates.py`
- `src/mlb_platform/cli/type2_candidates.py`
- `tests/test_backtest/test_type2_candidates.py`
- `tests/test_cli/test_type2_candidates.py`
- `make type2-candidates ODDS_PATH=/path/to/odds EXCHANGE_JSON=/path/to/exchange.json`

The next MLB step is feeding real local/cached files through candidate/evidence CLIs and adding a compact no-spend manifest/audit layer.

The no-spend audit tranche also landed:

- `src/mlb_platform/reports/type2_audit.py`
- `src/mlb_platform/cli/type2_audit.py`
- `tests/test_reports/test_type2_audit.py`
- `tests/test_cli/test_type2_audit.py`
- `make type2-audit ODDS_PATH=/path/to/odds EXCHANGE_JSON=/path/to/exchange.json`

The next MLB step is running `make type2-audit` on real local/cached files with `TYPE2_BUNDLE_DIR` and reviewing the generated gates and candidates.

## Verification

- `python3 -m py_compile scripts/codex_macro_router.py`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=. .venv/bin/pytest tests/test_codex_macro_router.py -q`
- `make macro-status` in predmarket
- `make -C /home/mrwatson/projects/mlb-platform macro-status`
- `make -C /home/mrwatson/projects/atp-oracle macro-status`
- `make -C /home/mrwatson/projects/nba-analytics-platform macro-status`
- `make -C /home/mrwatson/projects/nfl_quant_glm51_greenfield macro-status`
- `python3 scripts/codex_macro_router.py route --write`

## Notes

The router is stdlib-only and does not import repo packages. Default macro-status commands do not call providers, live APIs, market execution paths, or database writers.
