# Sports Settlement Horizon + ATP Evidence Loop

Date: 2026-07-03

## Scope

Repair the remaining sports-game discovery/gating mismatch and add a first ATP/Wimbledon evidence accumulation loop.

## Changes

- `predmarket/kalshi_universe_scan.py`
  - Widened targeted sports series fetches to `KALSHI_UNIVERSE_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS` / 720h while keeping the reported settlement window bounded.
  - Added explicit settlement-horizon fields: `settlement_time`, `settlement_time_source`, `time_to_settlement_hours`, and `horizon_time_basis`.
  - Sports now filter by expected settlement/probe horizon instead of administrative `close_time`; ATP date-only match tickers can use a conservative event-date label-probe fallback.

- `scripts/kalshi_sports_proxy_feature_packet.py`
  - Baseball feature selection now uses the same sports settlement horizon and emits `fresh_time_to_settlement_*` plus `horizon_time_basis`.

- `scripts/kalshi_sports_proxy_capacity_correlation_decay.py`
  - Current-candidate selection now uses `expected_expiration_time` / settlement horizon instead of raw `close_time`.

- `scripts/kalshi_atp_proxy_observation_loop.py`
  - New research-only ATP/Wimbledon observation and label loop.
  - Archives exact Kalshi ATP match tickers from `/home/mrwatson/projects/atp-oracle/data/kalshi/`.
  - Labels only from exact public Kalshi settlement; donor prices are observations, not probabilities.

- `Makefile`
  - Added `kalshi-atp-proxy-observation-loop` and `kalshi-atp-proxy-observation-watch-once`.

## Latest Artifacts

- 48h universe: 3,552 candidates, 88 ATP-routed, 214 MLB-classified.
- Baseball feature packet: 118 game rows, 58 MLB ready, 60 KBO/LMB proxy unavailable.
- Sports observations: 58 MLB observations, 0 labels, next probe `2026-07-03T23:05:00Z`.
- ATP observations: 24 Wimbledon observations from 12 matches, 0 labels, next probe `2026-07-04T06:00:00Z`.
- Paper/live: 490 paper candidates, 490 blocked, 0 paper usable, 0 live eligible.

## Verification

- Touched-file Ruff: pass.
- Focused sports/ATP tests: 78 passed.
- `make test-unit`: 650 passed / 14 deselected.
- `make test-integration`: 14 passed.
- `make lint-baseline-check`: inherited repo-wide format ratchet still fails, `format 98 > 94`; touched files are not in Ruff's format offender list.

## Next Step

Run the sports and ATP observation loops after the listed probe times, then promote only settled labels into falsification. Do not lower thresholds, use donor market prices as labels, or create any paper/live stake until FDR, replay, capacity, correlation, and decay gates pass.
