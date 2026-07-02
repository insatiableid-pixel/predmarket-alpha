# Kalshi Crypto Proxy Feature Packet

- Status: `crypto_proxy_feature_packet_ready`
- Research only: `true`
- Execution enabled: `false`
- Feature rows: `9`
- Feature-ready rows: `9`
- Assets: `{'BNB': 1, 'BTC': 1, 'DOGE': 1, 'ETH': 1, 'HYPE': 1, 'NEAR': 1, 'SOL': 1, 'XRP': 1, 'ZEC': 1}`

## Source Policy

- Official settlement source: `CF Benchmarks RTI`
- Public exchange data role: `proxy feature only`
- Labels require settled Kalshi outcomes or authenticated official settlement data.
- This packet does not compute probability, EV, sizing, or execution instructions.

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `safe_universe_scan_present` | `pass` | Safe universe scan is required. |
| `probability_breadth_scout_present` | `pass` | Probability breadth scout is required. |
| `raw_universe_snapshot_available` | `pass` | Raw Kalshi snapshot enriches contract parsing. |
| `raw_proxy_snapshot_outside_repo` | `pass` | Raw public proxy payloads must stay outside the repo. |
| `feature_rows_keyed` | `pass` | Feature rows must be keyed to exact contract tickers. |
| `no_ev_or_label_claims` | `pass` | Feature packet must not compute EV, labels, sizing, or usable rows. |

## Next Action

- Name: `kalshi_crypto_proxy_observation_loop`
- Why: Contract-keyed crypto proxy features are available. The next useful step is repeated feature snapshots plus settled Kalshi outcome matching for OOS falsification.
- Stop condition: Stop before treating proxy states as settlement labels, computing usable EV, sizing, execution, or account/order paths.
