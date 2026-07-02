# Kalshi Crypto Proxy Observation Loop

- Status: `crypto_proxy_observation_loop_label_rows_ready`
- New observations: `9`
- Total observations: `7443`
- Due observations: `7434`
- Due contracts: `3735`
- Next expected expiration: `2026-07-02T05:20:00Z`
- Next public label probe: `2026-07-02T05:08:49Z`
- Label rows: `1200`
- Assets: `{'BTC': 2263, 'BNB': 907, 'ETH': 907, 'HYPE': 907, 'SOL': 907, 'XRP': 907, 'DOGE': 631, 'NEAR': 7, 'ZEC': 7}`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `crypto_proxy_feature_packet_safe` | `pass` | Ready, research-only crypto proxy feature packet is required. |
| `new_observations_recorded` | `pass` | 9 new observation row(s) from latest feature packet. |
| `observations_available` | `pass` | 7443 total crypto proxy observation row(s). |
| `settled_markets_available` | `pass` | 1300 public settled market row(s) loaded. |
| `label_rows_available` | `pass` | 1200 crypto proxy label row(s) emitted. |
| `manual_drop_dirs_outside_repo` | `pass` | Observation and label packets must stay outside the repo. |
| `no_probability_ev_or_execution_claims` | `pass` | Observations and labels remain feature/outcome data only. |

## Next Action

- Name: `kalshi_crypto_proxy_feature_model_falsification`
- Why: Feature observations now have real Kalshi settled outcomes; next work is a cost-aware feature model and OOS falsification.
- Stop condition: Stop before promoting, sizing, or executing without calibrated probabilities and FDR-controlled OOS survival.

## Guardrail

This loop archives features and settled outcomes only. It does not produce model probabilities, EV, sizing, or orders.
