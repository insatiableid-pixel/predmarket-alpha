# Kalshi Signal Factory North Star

## Mission

Extract and exploit mispricings in Kalshi event contracts before the crowd corrects them.

The operation is a systematic quantitative factory for finding non-random miscalibration in Kalshi crowd-implied probabilities, validating it, sizing it only after capacity/correlation controls exist, and retiring it when decay appears.

## Axioms

- No discretion: humans may configure systems, but trade selection, entry, exit, and sizing must be machine-gated.
- Signal breadth over depth: the operation scales through many weak, uncorrelated signals across many markets.
- Capacity discipline: Kalshi liquidity is structurally limited, so market count matters more than position size.

## Required Pipeline

```text
Kalshi public universe + external data
→ features
→ agentic hypothesis generation
→ hypothesis registry
→ FDR-controlled, out-of-sample, cost-aware falsification
→ calibrated probability
→ capacity/correlation-adjusted sizing
→ execution control plane
→ realized P&L and decay update
→ automatic retirement/replacement
```

Operational equation:

```text
Kalshi order book + external data
→ features
→ agentic hypothesis generation
→ {alpha_k}_{k=1..K}
→ FDR-controlled, out-of-sample, cost-aware falsification
→ p_hat
→ argmax_w [w^T(p_hat - p_market) - lambda w^T Sigma w]
   subject to w_i <= ghost-listing-adjusted capacity_i
→ contract orders
→ realized P&L
→ decay update
```

Formal architecture note: `docs/codex/macro/kalshi-agentic-falsification-architecture.md`.

## Current Constraint

The universe scanner, hypothesis registry, label loop, first crypto proxy
feature falsification, conservative all-in cost replay, and pre-overlay
capacity/correlation/decay gate now exist. The correlation-cluster exposure
control now exists too. CCD candidate selection is cluster-round-robin, so the
bounded orderbook probe samples independent asset/family/close-time clusters
before taking multiple rows from one bucket.

The current routed bottleneck is not more candidate discovery, not a prettier
model, not sizing, and no longer artificial cluster starvation. It is decay
survival:

- capacity depth from public order books passes for the latest sampled bucket,
- current CCD selection spans 9 clusters/assets,
- positive depth appears in 3 independent clusters,
- the cluster controller can cap controlled exposure at the 35% max-share limit,
- the latest replay decay bucket is below random, so paper overlay remains blocked.

The first crypto proxy research candidate has positive cost-adjusted replay
rows, but it remains non-deployable. Sizing and execution stay disabled until
falsification, calibrated probability, capacity, correlation, kill-switch, and
decay-retirement gates are machine-readable and passing.
