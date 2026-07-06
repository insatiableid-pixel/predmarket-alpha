# Completion Report: Sports CCD + Cluster Control + Decay E2E (Milestone 2 Complete)

**Date:** 2026-07-03

## Summary

Completed the sports lane end-to-end through the full gate chain: CCD gate (public Kalshi orderbook depth, YES/NO reciprocal-ask depth, round-robin cluster selection), correlation-cluster control (35% max-share binary-search capping, fully generic), and decay gate (recent bucket >= 0.5 accuracy + min buckets/labels on sports close_times). Ran a real public-data baseball E2E run producing honest gated artifacts throughout. Crypto characterization tests pass unchanged.

## What Changed

- **New module:** `scripts/kalshi_sports_proxy_capacity_correlation_decay.py` — Sports CCD gate (public Kalshi orderbook depth probe, ask_levels YES/NO reciprocal derivation, capacity_row computation, round-robin cluster selection by `league|event_ticker|date`, positive-depth fraction recording vs ~0.18 Axiom 3 prior, decay gate from replay artifact, sports-specific status strings).
- **New module:** `scripts/kalshi_sports_proxy_correlation_cluster_control.py` — Sports cluster control (fully generic binary-search max-share capping at 35%, reused unchanged on sports capacity_rows, family-agnostic).
- **New tests:** `tests/test_kalshi_sports_proxy_capacity_correlation_decay.py` (21 test cases) and `tests/test_kalshi_sports_proxy_correlation_cluster_control.py` (8 test cases).
- **Makefile:** Added `kalshi-sports-proxy-capacity-correlation-decay` and `kalshi-sports-proxy-correlation-cluster-control` targets; wired both into `kalshi-sports-proxy-observation-watch-once` chain.
- **Signal factory:** Extended `scripts/kalshi_signal_factory_families.py` with falsification/replay/CCD/cluster-control capability detection and status computation. Extended `Artifacts` dataclass in `scripts/kalshi_signal_factory_status.py` with 4 new sports artifact paths (model falsification, replay, CCD, cluster control) and added CLI args.
- **Bugfix:** Fixed `scripts/kalshi_falsification_replay_shared.py` sys.path insert (inserts `CONTROL_REPO` so `from predmarket` imports resolve).

## Latest Evidence

All artifacts from the real public-data E2E run:

| Artifact | Status |
|---|---|
| `latest-kalshi-sports-proxy-feature-packet.json` | `sports_proxy_feature_packet_blocked_no_open_fast_sports_contracts` |
| `latest-kalshi-sports-proxy-observation-loop.json` | `sports_proxy_observation_loop_blocked_no_observations` |
| `latest-kalshi-sports-proxy-feature-model-falsification.json` | `sports_proxy_feature_model_falsification_blocked_missing_labels` |
| `latest-kalshi-sports-proxy-research-candidate-replay.json` | `sports_proxy_research_candidate_replay_blocked_missing_research_candidate` |
| `latest-kalshi-sports-proxy-capacity-correlation-decay.json` | `sports_proxy_capacity_correlation_decay_blocked_missing_replay_candidate` |
| `latest-kalshi-sports-proxy-correlation-cluster-control.json` | `sports_proxy_correlation_cluster_control_blocked_upstream_ccd` |
| `latest-kalshi-signal-factory-status.json` | `signal_factory_crypto_proxy_capacity_depth_blocked` (crypto leads; sports is `signal_factory_sports_baseball_ccd_blocked`) |

Sports cluster key `league|event_ticker|date` is used throughout — each game is an independent cluster.

## Artifacts

- `scripts/kalshi_sports_proxy_capacity_correlation_decay.py` (~795 lines)
- `scripts/kalshi_sports_proxy_correlation_cluster_control.py` (~455 lines)
- `tests/test_kalshi_sports_proxy_capacity_correlation_decay.py` (21 tests)
- `tests/test_kalshi_sports_proxy_correlation_cluster_control.py` (8 tests)
- Fresh `latest-kalshi-sports-proxy-capacity-correlation-decay.*` and `latest-kalshi-sports-proxy-correlation-cluster-control.*` macro pointers

## Verification

- **Tests:** 542 passed, 11 deselected (`make test-unit`), 21 sports CCD tests, 8 sports cluster control tests, 103 crypto characterization + router + cost tests
- **Quality gates:** `make lint-baseline-check` OK (1417/1422 lint, 93/94 format), `make tech-debt-check` OK (22/22), `make file-sizes-check` OK (3 known oversized files in baseline), `make modularize` OK (2 contracts kept, 0 broken), `make validate-agents` passes
- **Crypto invariance:** All crypto CCD/cluster-control/falsification/replay/observation/feature-packet tests (103) pass unchanged

## Safety

- Every row across all sports artifacts: `usable=false`, `calibrated_probability=null`
- No execution, account/order, database-write, or staking paths introduced
- Raw public payloads stay outside the repo under `/home/mrwatson/manual_drops/`
- Honest gating: all sports statuses are `*_blocked_*` variants in the public-data run (expected: no open fast-settling sports contracts right now)

## Next Blocker

Efficient-market expected: the sports lane has no open fast-settling contracts to produce candidates. This is honest gating. Next focus returns to crypto: accumulate public orderbook depth for current crypto proxy candidates while keeping capacity blocked until positive depth clears the conservative probability hurdle. KBO/LMB ESPN map re-verification is carried forward (endpoints still return HTTP 400; off-season/drift).
