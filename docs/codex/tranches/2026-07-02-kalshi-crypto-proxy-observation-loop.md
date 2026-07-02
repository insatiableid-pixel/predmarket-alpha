# Kalshi Crypto Proxy Observation Loop

Date: 2026-07-02

## Outcome

Built and ran the repeated observation loop for fast-settling Kalshi crypto contracts.

Latest status: `crypto_proxy_observation_loop_ready_waiting_settlement`.

## Evidence

- Latest feature packet: 1,239 feature-ready crypto proxy rows.
- Latest observation loop: 2,478 total observation rows, 1,239 distinct contracts, 0 label rows.
- Raw observations: `/home/mrwatson/manual_drops/kalshi_crypto_proxy_observations/`.
- Public settled/observed market snapshots: `/home/mrwatson/manual_drops/kalshi_oos_settlements/`.
- Repo latest pointers:
  - `docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.json`
  - `docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.md`
  - `docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.csv`
- Schedule template: `docs/codex/macro/kalshi-crypto-proxy-observation-loop-latest/kalshi-crypto-proxy-observation-loop.timer.example`

## Learned

The highest-velocity learning family is still fast-settling crypto, but the current blocker is settlement time. The code now probes exact observed tickers once they are due, so labels should attach without relying on broad settled-market pagination.

## Next Route

`make macro-route` recommends predmarket:

`signal_factory_crypto_proxy_observations_waiting_settlement`

Next tranche: keep accumulating crypto proxy observations and public settled outcomes until true Kalshi labels exist, then route to cost-aware feature-model falsification.

## Guardrail

Proxy prices are model features only. They are not official settlement labels, calibrated probabilities, EV evidence, sizing guidance, or execution authority.
