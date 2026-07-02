# Kalshi Signal Factory Status

- Status: `signal_factory_crypto_proxy_capacity_depth_blocked`
- Research only: `true`
- Execution enabled: `false`
- Universe candidates: `4359`
- Model-route candidates: `257`
- Soft-watch candidates: `4102`

## Capability Gates

| Capability | Status | Reason |
| --- | --- | --- |
| `kalshi_universe_inventory` | `pass` | 4359 public-market candidates in the configured window. |
| `deterministic_route_inventory` | `pass` | 257 model-route candidate(s), 4102 soft-watch candidate(s). |
| `contract_ev_ledger` | `pass` | 348 contract EV row(s); 12 currently pass legacy research gates. |
| `agentic_hypothesis_registry` | `pass` | 36 HypothesisCandidate row(s) across 36 multiple-testing family/families. |
| `fdr_controlled_falsification_gate` | `blocked` | Falsification gate is `falsification_gate_blocked_missing_labeled_oos_evidence` with 36 registered and 0 tested hypothesis/hypotheses. |
| `labeled_oos_backtest_harness` | `pass` | Labeled OOS harness status is `labeled_oos_backtest_blocked_missing_labeled_observations` with 0 valid observation(s), 0 testable hypothesis/hypotheses, and 0 research promotion(s). |
| `labeled_observation_packet_builder` | `pass` | Observation builder status is `labeled_observation_builder_pending_observations_waiting_settlement` with 44 pending observation(s) and 0 label row(s). |
| `calibrated_probability_feeds` | `warn` | 32 calibrated probability overlay row(s), but no central probability decay/falsification registry. |
| `probability_breadth_scout` | `pass` | Probability breadth scout status is `probability_breadth_scout_ready_crypto_proxy_feature_route` with 9 fast crypto candidate(s), 192 fast weather candidate(s), and 4 available proxy source(s). |
| `crypto_proxy_feature_packet` | `pass` | Crypto proxy feature packet status is `crypto_proxy_feature_packet_ready` with 9 feature row(s), 9 feature-ready row(s), and 9 proxy-covered asset(s). |
| `crypto_proxy_observation_loop` | `pass` | Crypto proxy observation loop status is `crypto_proxy_observation_loop_label_rows_ready` with 7443 total observation row(s), 9 new row(s), and 1200 settled label row(s). |
| `crypto_proxy_feature_model_falsification` | `pass` | Crypto proxy model falsification status is `crypto_proxy_feature_model_falsification_ready_with_research_candidates` with 318 independent label(s), 891 duplicate label row(s), and 1 research candidate(s). |
| `crypto_proxy_research_candidate_replay` | `pass` | Crypto proxy research-candidate replay status is `crypto_proxy_research_candidate_replay_blocked_predeployment_gates` with 315 replay row(s), 159 positive cost-adjusted row(s), 0.5156621967 conservative selected-side probability, and 0 usable row(s). |
| `crypto_proxy_capacity_correlation_decay` | `warn` | Crypto proxy capacity/correlation/decay status is `crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates` with 0 current candidate(s), 0 orderbook(s), 0.0 positive-depth contract(s), largest cluster share `None`, and decay status `decay_survival_blocked`. |
| `crypto_proxy_correlation_cluster_control` | `warn` | Crypto proxy cluster-control status is `crypto_proxy_correlation_cluster_control_blocked_upstream_ccd` with 0 positive cluster(s), 3 required cluster(s), 0.0 controlled-depth cost, largest controlled share `None`, and 0 usable row(s). |
| `capacity_model` | `blocked` | Crypto proxy capacity depth status is `capacity_depth_missing_or_not_positive` with 0.0 positive-depth contract(s). |
| `correlation_model` | `blocked` | Crypto proxy cluster-control status is `crypto_proxy_correlation_cluster_control_blocked_upstream_ccd`; largest controlled cluster share is `None`. |
| `fractional_kelly_sizing_policy` | `blocked` | Sizing is intentionally disabled until falsification, capacity, and correlation gates exist. |
| `execution_control_plane` | `blocked` | Execution remains disabled; no account/order path should be wired before the audited sizing and kill-switch gates. |
| `realized_pnl_decay_loop` | `blocked` | No realized P&L and signal-decay retirement loop exists yet. |

## Next Tranche

- Name: `kalshi_crypto_proxy_orderbook_depth_accumulation`
- Why: The CCD gate exists but public orderbook depth is missing or not positive under the conservative probability hurdle.
- Stop condition: Stop before inferring capacity from top-of-book prices without public depth.

## Guardrail

This is a system status artifact. It does not authorize sizing, orders, or execution.
