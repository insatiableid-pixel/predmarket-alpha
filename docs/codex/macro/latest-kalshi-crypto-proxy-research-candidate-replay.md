# Kalshi Crypto Proxy Research Candidate Replay

- Status: `crypto_proxy_research_candidate_replay_blocked_predeployment_gates`
- Independent labels: `318`
- OOS selected rows: `95`
- Conservative selected-side probability: `0.5156621967`
- Positive cost-adjusted replay rows: `159`
- Usable rows: `0`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `label_packets_safe` | `pass` | 5 safe packet(s), 0 unsafe packet(s). |
| `label_dir_outside_repo` | `pass` | Crypto proxy label packets must stay outside the repo. |
| `research_candidate_present` | `pass` | Feature-model falsification must have a research_candidate_fdr_passed row. |
| `conservative_probability_preflight` | `pass` | Calibration status is research_only_conservative_probability_ready; OOS selected rows: 95. |
| `all_in_cost_replay` | `pass` | 315 of 315 replay rows have all-in cost. |
| `positive_cost_adjusted_replay_rows` | `warn` | 159 replay row(s) are positive after conservative probability and all-in cost. |
| `capacity_depth_available` | `blocked` | No public depth or validated local order-book depth is attached, so capacity and price impact are unknown. |
| `correlation_control_available` | `blocked` | 30 cluster(s); largest cluster BTC|range|2026-07-02T02:00Z has 140 row(s). Cluster counts are measured, but covariance/exposure controls are not implemented. |
| `decay_survival_available` | `blocked` | Decay status is recent_bucket_below_random across 4 bucket(s); requires 3 bucket(s) and 100 independent labels. Recent bucket 2026-07-02T05:00Z accuracy 0.3333333333 (9 labels); cumulative accuracy 0.6 across 95 labels; 3/4 bucket(s) pass >= 0.5. |
| `no_usable_ev_sizing_or_execution` | `pass` | Replay remains research-only with zero usable rows and no sizing or execution. |

## Replay Summary

- Mean margin probability: `0.0305247364`
- Median margin probability: `0.0181621967`
- Mean expected value per contract: `0.0305247364`
- Historical paper result sum: `17.1817`
- Largest correlation cluster: `BTC|range|2026-07-02T02:00Z` (140 rows)

## Guardrail

This report is not a betting recommendation. It never marks rows usable and does not size or execute.
