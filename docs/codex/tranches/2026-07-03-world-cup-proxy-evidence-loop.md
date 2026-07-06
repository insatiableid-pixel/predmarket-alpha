# World Cup Proxy Evidence Loop

Date: 2026-07-03

## Purpose

Move World Cup/FIFA soccer rows out of `other_sports` soft-watch inventory and into the falsification pipeline without inventing a soccer handicap model or using discretionary sports judgment.

## What Changed

- Added `scripts/kalshi_world_cup_proxy_observation_loop.py`.
  - Reads `latest-kalshi-universe-scan.json`.
  - Selects only `other_sports` rows whose `series_ticker` is in the explicit World Cup/FIFA allowlist.
  - Archives exact Kalshi ticker observations with quote-time features.
  - Probes exact observed tickers after due time through Kalshi public market endpoints.
  - Labels only from public Kalshi settlement payloads matched by exact ticker.

- Added `scripts/kalshi_world_cup_proxy_feature_model_falsification.py`.
  - Uses the shared chronological OOS, exact-contract independence, binomial-survival, and BH-FDR spine.
  - Preserves World Cup proxy fields through a World Cup-specific normalizer.
  - Tests only pre-registered market-structure rules:
    - `world_cup_market_consensus_directional_accuracy`
    - `world_cup_longshot_fade_directional_accuracy`

- Added Make targets:
  - `kalshi-world-cup-proxy-observation-loop`
  - `kalshi-world-cup-proxy-feature-model-falsification`
  - `kalshi-world-cup-proxy-observation-watch-once`

- Added tests:
  - `tests/test_kalshi_world_cup_proxy_observation_loop.py`
  - `tests/test_kalshi_world_cup_proxy_feature_model_falsification.py`

## Latest Artifact State

- Universe scan: `universe_scan_ready_with_model_routes`
- Universe candidates: 6,587
- `other_sports` candidates: 133
- World Cup/FIFA observations archived: 115 distinct contracts
- Market types: 57 game, 52 total, 6 both-teams-to-score
- World Cup/FIFA label rows: 0
- Observation status: `world_cup_proxy_observation_loop_ready_waiting_settlement`
- Falsification status: `world_cup_proxy_feature_model_falsification_blocked_missing_labels`
- Independent labels: 0
- Research candidates: 0

Latest files:

- `docs/codex/macro/latest-kalshi-world-cup-proxy-observation-loop.json`
- `docs/codex/macro/latest-kalshi-world-cup-proxy-feature-model-falsification.json`
- `/home/mrwatson/manual_drops/kalshi_world_cup_proxy_observations/world_cup_proxy_observations_latest.json`

## Guardrails

- No soccer handicap model was added.
- No sportsbook probability was admitted.
- No calibrated probability, EV, paper stake, live order, account path, or execution path was introduced.
- Every row remains `usable=false`, `calibrated_probability=null`, and `expected_value_per_contract=null`.
- The only promotion path is settled labels -> independent contract collapse -> chronological OOS -> binomial test -> BH-FDR.

## Verification

- `make kalshi-world-cup-proxy-observation-watch-once`
- `make kalshi-world-cup-proxy-observation-loop`
- `make kalshi-world-cup-proxy-feature-model-falsification`
- `python3 -m json.tool` on both latest World Cup JSON artifacts
- `.venv/bin/python -m pytest -q -s tests/test_kalshi_world_cup_proxy_observation_loop.py tests/test_kalshi_world_cup_proxy_feature_model_falsification.py tests/test_kalshi_universe_scan.py` -> 24 passed
- `make test-unit` -> 677 passed, 14 deselected
- `make test-integration` -> 14 passed
- `make lint-baseline-check` -> `lint 1408/1422`, `format 90/94`
- `make tech-debt-check` -> 22/22
- `make file-sizes-check` -> no new oversized files
- `make modularize` -> 2 contracts kept, 0 broken

## Next Bottleneck

Keep running the World Cup observation watch after match settlement windows. Once exact settled labels accumulate, the falsification artifact will naturally move from `blocked_missing_labels` to independent-label and OOS/FDR evaluation. Do not lower thresholds to force promotion.
