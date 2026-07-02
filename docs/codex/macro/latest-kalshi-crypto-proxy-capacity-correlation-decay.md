# Kalshi Crypto Proxy Capacity Correlation Decay

- Status: `crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates`
- Current candidates: `0`
- Candidate clusters: `0`
- Orderbooks: `0`
- Positive-depth contracts: `0.0`
- Positive-depth cost: `0.0`
- Largest cluster share: `None`
- Decay status: `decay_survival_blocked`
- Usable rows: `0`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `replay_candidate_ready` | `pass` | Replay status is crypto_proxy_research_candidate_replay_blocked_predeployment_gates. |
| `current_candidates_present` | `blocked` | 0 current candidate row(s) selected. |
| `raw_orderbook_dir_outside_repo` | `pass` | Raw public orderbook snapshots must stay outside the repo. |
| `public_orderbook_depth_present` | `blocked` | 0 orderbook(s), 0 error(s). |
| `positive_capacity_depth` | `blocked` | 0.0 positive-depth contract(s), 0.0 cost notional. |
| `correlation_cluster_limit` | `blocked` | Largest cluster None has share None; max is 0.35. |
| `decay_survival` | `blocked` | Replay decay status recent_bucket_below_random, 4 bucket(s), 318 independent label(s). Recent bucket 2026-07-02T05:00Z accuracy 0.3333333333 (9 labels); cumulative accuracy 0.6 across 95 labels; 3/4 bucket(s) pass >= 0.5. |
| `no_usable_sizing_or_execution` | `pass` | Capacity report remains research-only with zero usable rows and no sizing or execution. |

## Next Action

- Name: `kalshi_crypto_proxy_decay_and_sample_accumulation`
- Why: Capacity/correlation/decay gates are not all passing yet.
- Stop condition: Stop before lowering decay, sample, or correlation limits without an explicit policy review.

## Guardrail

This report is not a betting recommendation and never authorizes sizing or execution.
