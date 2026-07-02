# Agentic Falsification Architecture for Kalshi Alpha

## Thesis

The objective is not to find one brilliant Kalshi forecast. The objective is to run a systematic, self-improving research factory that discovers, falsifies, sizes, exploits, and retires non-random miscalibration faster than the crowd corrects it.

## Axioms

- No discretion: humans may define policy, data contracts, and safety gates; the model selects hypotheses, entries, exits, and sizing only after machine-readable gates pass.
- Signal breadth over depth: durable edge comes from many weak, uncorrelated signals across many markets, not concentrated conviction in one market.
- Capacity discipline: Kalshi position capacity is structurally bounded by thin liquidity and price impact, so the operation scales by market count rather than position size.

## Architecture

```text
Kalshi order book + external data
→ features
→ agentic hypothesis generation
→ {alpha_k}_{k=1..K}
→ FDR-controlled, out-of-sample, cost-aware falsification
→ p_hat
→ correlation-adjusted fractional Kelly with capacity constraints
→ contract orders
→ realized P&L
→ decay update and signal retirement
```

## Theorem

In a venue with limited per-contract capacity, noisy crowd-implied probabilities, and cheap machine-generated hypotheses, positive expected value cannot be treated as evidence unless it survives three constraints:

- Statistical falsification: out-of-sample survival with false-discovery control as K grows.
- Market microstructure feasibility: all-in cost, depth, and ghost-listing-adjusted capacity must leave positive capacity at the executable side.
- Portfolio independence: surviving rows must be sufficiently spread across correlation clusters before any paper overlay, sizing, or execution layer may consume them.

Without these constraints, agentic hypothesis generation increases false discoveries faster than it increases exploitable edge.

## Operational Consequence

Every candidate must remain unusable until the chain is complete:

```text
features
→ registered hypothesis
→ labeled OOS evidence
→ FDR/cost-aware falsification
→ conservative calibrated probability
→ capacity-depth gate
→ correlation-cluster gate
→ decay-survival gate
→ paper overlay
→ sizing policy
→ execution controls
```

The current crypto proxy lane now obeys this theorem: capacity and decay pass, but cluster breadth fails. With one positive BNB cluster under a 35% max-share policy, controlled depth is zero and no paper overlay is permitted.
