# Sports Game Discovery Repair: Wimbledon + MLB Routing

Date: 2026-07-03

## Summary

Repaired Kalshi sports-game discovery so visible sports game/match markets no longer depend on the broad `/markets` page order. The universe scanner now runs targeted public series fetches for baseball and tennis game series, merges them by exact ticker, and routes them deterministically:

- `KXMLBGAME`, `KXLMBGAME`, `KXKBOGAME`, `KXMLBASGAME`, `KXMLBSTGAME` -> `mlb-platform`
- `KXATPMATCH`, `KXATPGAME`, ATP set/game winner series, and Wimbledon series -> `atp-oracle`

The classifier now recognizes `KXLMB*`, `KXKBO*`, and `KXATP*`/`KXWIM*` prefixes directly, even when Kalshi omits `series_ticker` in the payload.

## Chain Landing

- Refreshed the universe scan with a 720-hour window. Current artifact shows `470` ATP-routed candidates and `785` MLB-routed candidates.
- Current exact examples are present:
  - `KXATPMATCH-*` Wimbledon rows routed to `atp-oracle`
  - `KXMLBGAME-*` MLB rows and `KXLMBGAME-*` rows routed to `mlb-platform`
- Refreshed the sports feature packet. It now has `176` baseball game rows: `88` MLB, `68` LMB, and `20` KBO. MLB feature rows are exact contract keyed and feature-ready; LMB/KBO remain partial where proxy sources are unavailable.
- Routed ATP match snapshots into the EV ledger as exact, blocked rows from `/home/mrwatson/projects/atp-oracle/data/kalshi/matches-2026-07-03.json`. Both YES contracts per match are emitted.
- Routed current sports feature-packet rows into the EV ledger as exact, blocked current-game rows.
- Refreshed paper decisions and live preflight. Wimbledon and current baseball rows now reach paper/live artifacts with `paper_stake=0`; no live row is eligible.

## Guardrails

No calibrated probability, EV, paper stake, or live eligibility is created by discovery. Newly routed sports rows are blocked unless the existing gates later receive calibrated contract probabilities, verified terms, falsification/replay evidence, capacity, correlation, and decay survival.

Current blockers:

- ATP: exact ticker/quote rows exist, but calibrated contract probability, official terms verification, and forward-OOS/decay survival are missing.
- Current MLB/LMB/KBO: exact ticker/quote rows exist, but the feature packet is feature-only; falsification, replay, capacity, correlation, and decay gates have not passed.

## Verification

- `python -m pytest -s tests/test_kalshi_universe_scan.py tests/test_kalshi_contract_ev_ledger.py -q`: 38 passed.
- `make test-unit`: 640 passed, 14 deselected.
- `make test-integration`: 14 passed.
- `make kalshi-universe-scan` with `KALSHI_UNIVERSE_MAX_CLOSE_HOURS=720`: status `universe_scan_ready_with_model_routes`.
- `make kalshi-sports-proxy-feature-packet` with `KALSHI_SPORTS_PROXY_FEATURE_MAX_CLOSE_HOURS=720`: status `sports_proxy_feature_packet_partial_feature_coverage`.
- Sports gate chain (`feature-model-falsification`, `research-candidate-replay`, `capacity-correlation-decay`, `correlation-cluster-control`) exits 0 and blocks honestly on missing labels/replay candidates.
- `make kalshi-ev-ledger`, `make kalshi-paper-decision-candidates`, `make kalshi-live-preflight`: exit 0; paper/live rows remain blocked.
- `make lint-baseline-check` still fails on inherited format ratchet overage (`format 98 > 94`); touched Python files were Ruff-formatted. This overage pre-existed this repair tranche.
