# Kalshi Crypto Proxy Feature Model Falsification

- Status: `crypto_proxy_feature_model_falsification_ready_with_research_candidates`
- Raw label rows: `1209`
- Independent contract labels: `318`
- Research candidates: `1`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `label_packets_safe` | `pass` | 5 safe packet(s), 0 unsafe packet(s). |
| `label_dir_outside_repo` | `pass` | Crypto proxy label packets must stay outside the repo. |
| `independent_label_minimum` | `pass` | 318 independent label(s); minimum is 30. |
| `oos_label_minimum` | `pass` | 0 testable model(s); minimum OOS labels is 10. |
| `no_probability_ev_or_execution_claims` | `pass` | Falsification output remains research-only and does not produce usable EV. |

## Evaluations

| Model | Status | OOS Count | Accuracy | p | q |
| --- | --- | ---: | ---: | ---: | ---: |
| `proxy_state_directional_accuracy` | `research_candidate_fdr_passed` | 95 | 0.6 | 0.0321064033135655 | 0.0321064033135655 |
| `market_yes_ask_probability_baseline` | `diagnostic_baseline_only` | 96 | None | None | None |

## Next Action

- Name: `kalshi_crypto_proxy_probability_calibration`
- Why: At least one feature family survived OOS/FDR as a research candidate; next work is calibrated probability modeling and cost replay.
- Stop condition: Stop before sizing or execution until calibrated probabilities, all-in costs, capacity, correlation, and kill-switch gates exist.

## Guardrail

This report is not a betting recommendation. It does not produce calibrated probabilities, EV, sizing, or orders.
