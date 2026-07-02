# Kalshi Crypto Proxy Feature Packet

Date: 2026-07-01

## Plain English

We learned that the quickest source of repeatable learning is still fast-settling crypto, because there are many contracts and they settle quickly. We also learned that the broad finance/crypto bucket had a small classification trap: 17 AAA gas-price contracts looked finance-like but are not crypto and should not go through the Coinbase proxy feature path.

## Outcome

- Built contract-keyed crypto proxy feature packets.
- Captured public Coinbase proxy data outside the repo.
- Produced 1,239 feature rows across 9 assets.
- All rows are feature-ready.
- No row is usable EV.
- No row has a calibrated probability.
- No row is a trade instruction.

## Current Route

`make macro-route` now recommends predmarket and the repeated crypto proxy observation loop.

## Stop Condition

Stop before treating proxy prices as official settlement labels, computing usable EV, sizing positions, execution, account/order paths, or promoting any crypto hypothesis without settled Kalshi outcomes and OOS cost-aware FDR evidence.

