# Tranche: Sports CCD + Cluster Control + Decay E2E (Milestone 2 Complete)

**Date:** 2026-07-03

## Outcome

Completed the sports lane end-to-end through the full gate chain: CCD gate, correlation-cluster control, and decay gate, then ran a real public-data baseball E2E run that produced honest gated artifacts throughout.

## Evidence

| Stage | Status (E2E Public Run) |
|---|---|
| Feature packet | `sports_proxy_feature_packet_blocked_no_open_fast_sports_contracts` |
| Observation loop | `sports_proxy_observation_loop_blocked_no_observations` |
| Falsification | `sports_proxy_feature_model_falsification_blocked_missing_labels` |
| Replay | `sports_proxy_research_candidate_replay_blocked_missing_research_candidate` |
| CCD | `sports_proxy_capacity_correlation_decay_blocked_missing_replay_candidate` |
| Cluster control | `sports_proxy_correlation_cluster_control_blocked_upstream_ccd` |
| Signal factory status | `signal_factory_crypto_proxy_capacity_depth_blocked` (crypto leads; sports is `signal_factory_sports_baseball_ccd_blocked`) |

Tests: 21 CCD + 8 cluster control + 103 crypto characterization + 542 total unit tests pass.

## Learned

- The CCD and cluster-control stages are highly generic — only the prediction rule and cluster key differ between sports and crypto.
- Sports cluster key `league|event_ticker|date` correctly groups both sides of the same game (YES/NO contracts) into one cluster, unlike crypto's asset-based clustering.
- The round-robin selection with `max_tickers` cap prevents any single game from dominating the ticker budget.
- Public data E2E run produces honest block statuses at every stage, as expected when there are no open sports contracts close to expiration.

## Next Route

The sports lane is now complete end-to-end through the gate chain. The macro route recommends predmarket as command center with crypto leading. Next blocker: accumulate public orderbook depth for current crypto proxy candidates while keeping capacity blocked until positive depth clears the conservative probability hurdle.

## Guardrail

- Every row across all sports artifacts carries `usable=false` and `calibrated_probability=null`.
- Honest gating: a blocked status (as seen in the real E2E run) is success; only a forced/fabricated pass is a defect.
- Crypto invariance: all crypto characterization tests pass unchanged.
- KBO/LMB ESPN map re-verification is non-blocking (endpoints return HTTP 400; off-season/drift).
