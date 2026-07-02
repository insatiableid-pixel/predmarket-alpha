# Kalshi Probability Breadth Scout

- Status: `probability_breadth_scout_ready_crypto_proxy_feature_route`
- Research only: `true`
- Execution enabled: `false`
- Fast candidate window: `6.0` hours
- Fast candidates: `212`
- Crypto fast candidates: `9`
- Weather fast candidates: `192`
- Selected route: `crypto_proxy_fast_label_route`

## Learned

- Official settlement source: `CF Benchmarks Real-Time Indices (RTIs)`
- Official availability: `authenticated_or_licensed_required`
- Proxy policy: Proxy exchange prices may be used as model features only. They are not official settlement labels and cannot promote hypotheses without settled Kalshi outcomes.

## Proxy Sources

| Source | Status | Role | Summary |
| --- | --- | --- | --- |
| `coinbase_btc` | `available` | `proxy_feature_source_not_official_settlement` | `{"price": "60658.74", "time": "2026-07-02T05:08:42.534664165Z"}` |
| `coinbase_eth` | `available` | `proxy_feature_source_not_official_settlement` | `{"price": "1629.58", "time": "2026-07-02T05:08:37.830053138Z"}` |
| `coinbase_sol` | `available` | `proxy_feature_source_not_official_settlement` | `{"price": "78.08", "time": "2026-07-02T05:08:43.284565519Z"}` |
| `kraken_btc` | `available` | `proxy_feature_source_not_official_settlement` | `{"error": [], "pair_count": 1}` |

## Next Action

- Name: `kalshi_crypto_proxy_feature_packet`
- Why: Crypto is the highest-count fast-settling route and public proxy feeds are reachable; build feature packets while keeping CF Benchmarks as the official settlement source.
- Stop condition: Stop before treating proxy prices as official labels, computing usable EV, sizing, execution, or account/order paths.

## Guardrail

This is a routing and evidence-source scout. It is not a bet list, EV ledger, or execution signal.
