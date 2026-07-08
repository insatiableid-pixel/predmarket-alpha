# 2026-07-08 World Cup Gate-Chain Routing

## Landing

The World Cup/FIFA proxy family no longer stops at label accumulation. Its OOS/FDR-passed research candidates now route through replay, capacity/depth, cluster control, EV-ledger refresh, paper decisions, and live preflight.

## Changes

- Added World Cup replay wrapper over the shared sports replay spine:
  - `scripts/kalshi_world_cup_proxy_research_candidate_replay.py`
  - latest artifact: `latest-kalshi-world-cup-proxy-research-candidate-replay.*`
- Added World Cup capacity/depth/decay wrapper over the shared sports CCD spine:
  - `scripts/kalshi_world_cup_proxy_capacity_correlation_decay.py`
  - latest artifact: `latest-kalshi-world-cup-proxy-capacity-correlation-decay.*`
- Added World Cup cluster-control wrapper:
  - `scripts/kalshi_world_cup_proxy_correlation_cluster_control.py`
  - latest artifact: `latest-kalshi-world-cup-proxy-correlation-cluster-control.*`
- Extended shared replay normalization and sports replay/CCD adapters so World Cup market-structure fields survive into replay and current observation rows can be selected by the FDR-passed World Cup rule.
- Added EV-ledger ingestion for World Cup price-bucket/market-structure CCD rows, separate from MLB strength/projection rows. MLB projection rows remain blocked by the consensus doctrine.
- Added Make targets and included them in `kalshi-world-cup-proxy-observation-watch-once`.
- Added focused tests in `tests/test_kalshi_world_cup_proxy_gate_chain.py`.

## Current Evidence

- Replay status: `world_cup_proxy_research_candidate_replay_blocked_predeployment_gates`
- Selected model: `world_cup_longshot_fade_directional_accuracy`
- Independent labels: `304`
- OOS selected rows: `42`
- Decay buckets: `17`
- Decay status: `recent_bucket_not_worse_than_random`
- Conservative probability: `0.7467725725`
- Positive historical cost-adjusted replay rows: `0`
- CCD status: `world_cup_proxy_capacity_correlation_decay_blocked_capacity_depth`
- Current candidates selected: `10`
- Orderbooks captured: `10`
- Orderbook errors: `0`
- Positive-depth contracts: `0.0`
- Positive-depth cost: `0.0`
- Cluster status: `world_cup_proxy_correlation_cluster_control_blocked_upstream_ccd`
- Controlled-positive rows: `0`
- Paper: `485` candidates, `0` usable, `$0` stake
- Live: `0` eligible, `$0` stake

## Verification

- `pytest tests/test_kalshi_world_cup_proxy_gate_chain.py tests/test_kalshi_sports_proxy_research_candidate_replay.py tests/test_kalshi_sports_proxy_capacity_correlation_decay.py tests/test_kalshi_contract_ev_ledger.py -q` -> `67 passed`
- Touched-file Ruff -> pass
- `make kalshi-world-cup-proxy-research-candidate-replay` -> exit `0`
- `make kalshi-world-cup-proxy-capacity-correlation-decay` -> exit `0`
- `make kalshi-world-cup-proxy-correlation-cluster-control` -> exit `0`
- `make kalshi-ev-ledger` -> exit `0`
- `make kalshi-paper-decision-candidates` -> exit `0`
- `make kalshi-live-preflight` -> exit `0`
- `make kalshi-claude-advice-audit` -> exit `0`

## Guardrails

No thresholds changed. No labels were inferred. No sportsbook outcomes were used as labels. No live/account/order path was touched. No paper/live promotion occurred because capacity/depth blocked the routed World Cup candidate set.
