# 2026-07-01 Kalshi Universe Scanner

## Summary

Implemented the public Kalshi universe scanner in `predmarket-alpha`. The scanner is the new front door: it pulls public market inventory before sport/model repos get involved, filters by settlement window, classifies markets, scores soft-watch triage, and writes universal candidate/routing artifacts.

## Artifacts

- `predmarket/kalshi_universe_scan.py`
- `tests/test_kalshi_universe_scan.py`
- `docs/codex/macro/kalshi-universe-candidate.schema.json`
- `docs/codex/macro/kalshi-universe-scan-latest/kalshi-universe-scan.json`
- `docs/codex/macro/kalshi-universe-scan-latest/kalshi-universe-candidates.csv`
- `docs/codex/macro/kalshi-universe-scan-latest/kalshi-universe-routes.json`
- `docs/codex/macro/kalshi-universe-scan-latest/kalshi-soft-market-watch.md`
- `docs/codex/macro/kalshi-universe-scan-latest/kalshi-universe-scan.timer.example`
- `docs/codex/macro/latest-kalshi-universe-scan.json`
- `docs/codex/macro/latest-kalshi-universe-candidates.csv`
- `docs/codex/macro/latest-kalshi-universe-routes.json`
- `docs/codex/macro/latest-kalshi-soft-market-watch.md`

Raw public snapshot stayed outside the repo:

- `/home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_20260701T224619Z.json`
- `/home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json`

## Result

Status: `universe_scan_ready_with_model_routes`

- Settlement window: 0-72 hours
- Raw public markets: 6,070
- Candidate rows: 6,070
- Model-route candidates: 725
- Soft-watch candidates: 5,345
- Candidate gate counts: 6,070 pass, 0 warn, 0 blocked

Classification counts:

- `finance_crypto`: 3,788
- `mlb`: 725
- `unknown_soft_watch`: 678
- `weather`: 519
- `entertainment`: 200
- `macro_econ`: 95
- `other_sports`: 52
- `politics_policy`: 13

Route counts:

- `mlb-platform`: 725
- `soft_market_research_backlog`: 5,345

## Guardrails

- Public market-data calls only.
- No authenticated API calls.
- No account, order, position, portfolio, or execution paths.
- No database writes.
- No raw public payload copied into the repo.
- No EV computed in the scanner.
- No staking/sizing/tradable claims.

## Verification

- `make kalshi-universe-scan`
- `make macro-route`
- `make macro-status`
- `pytest -q tests/test_kalshi_universe_scan.py tests/test_kalshi_manual_drop_capture.py tests/test_codex_macro_router.py tests/test_kalshi_execution_cost.py tests/test_kalshi_contract_ev_ledger.py`
- `ruff check predmarket/kalshi_universe_scan.py predmarket/kalshi_dataset.py tests/test_kalshi_universe_scan.py scripts/codex_macro_router.py tests/test_codex_macro_router.py`

