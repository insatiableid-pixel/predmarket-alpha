# 2026-07-01 Kalshi EV Queue Robustness

## Summary

Built the next predmarket command-center tranche after the north-star EV review queue: a repeat-snapshot robustness check for the current Kalshi NFL EV candidates.

One bounded public Kalshi `KXNFLGAME` market-data capture was made outside the repo. It captured 66 open game markets with 0 series errors and wrote the raw timestamped file at `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T221233Z.json` plus the NFL latest pointer at `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json`.

## Artifacts

- `scripts/kalshi_ev_queue_robustness.py`
- `tests/test_kalshi_ev_queue_robustness.py`
- `docs/codex/macro/kalshi-ev-queue-robustness-latest/kalshi-ev-queue-robustness.json`
- `docs/codex/macro/kalshi-ev-queue-robustness-latest/kalshi-ev-queue-robustness.md`
- `docs/codex/macro/kalshi-ev-queue-robustness-latest/kalshi-ev-queue-robustness.csv`
- `docs/codex/macro/latest-kalshi-ev-queue-robustness.json`
- `docs/codex/macro/latest-kalshi-ev-queue-robustness.md`
- `docs/codex/macro/latest-kalshi-ev-queue-robustness.csv`
- `docs/codex/macro/latest-decision.json`
- `docs/codex/macro/latest-status.json`
- `docs/codex/current-state.md`

## Result

Status: `kalshi_ev_queue_robustness_repeat_positive_cost_caveated`

- Distinct public NFL snapshots: 2
- Queue rows checked: 12
- Rows with two or more snapshots: 12
- Repeat-positive rows: 12
- Missing latest quotes: 0
- Robust candidates: 0
- Cost-caveated rows: 12

Plain English: the positive NFL contract gaps did repeat across two public snapshots. That is useful evidence, but not a usable edge yet. Every row still uses public YES ask plus an official fee estimate, not an observed all-in ticket cost, so the rows remain research-only and cost-caveated.

## Router State

`make macro-route` now routes to predmarket with:

- Evidence status: `kalshi_ev_queue_robustness_repeat_positive_cost_caveated`
- Priority: 32
- Next tranche: verify actual all-in ticket cost without submitting an order, plus forward context and independent validation.

## Safety

- Research-only: true
- Provider/API calls in the robustness script: false
- Account/order paths: false
- Market execution: false
- Database writes: false
- Raw payloads copied into repo: false
- Staking/sizing/tradable claims: false

## Verification

- `make kalshi-ev-queue-robustness`
- `make macro-route`
- `make macro-status`
- `pytest -q tests/test_kalshi_ev_queue_robustness.py tests/test_codex_macro_router.py`
- `ruff check scripts/kalshi_ev_queue_robustness.py tests/test_kalshi_ev_queue_robustness.py scripts/codex_macro_router.py tests/test_codex_macro_router.py`

