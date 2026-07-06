# Tranche: Sports Observation/Label Loop (Milestone 1)

**Date:** 2026-07-03
**Scope:** `sports-observation-label-loop` (Milestone 1, sports-feature-foundation)

## Outcome

Built `scripts/kalshi_sports_proxy_observation_loop.py`, the sports analog of the
crypto observation/label loop. It snapshots ready sports feature rows, dedupes by
`observation_id`, probes observed Kalshi tickers after game end, and emits label
rows from Kalshi public settlement. Research-only throughout.

## Evidence

- 13 artifact-replay tests pass: `tests/test_kalshi_sports_proxy_observation_loop.py`
  (importlib load + injected `fetch_json`, no network).
- Crypto characterization + router suite unchanged: 120 passed.
- `make test-unit` 494 passed, 11 deselected.
- All 5 binding quality gates green: lint-baseline (1413/1422, not inflated),
  tech-debt-check, file-sizes-check, modularize (2 kept/0 broken), validate-agents.
- `make kalshi-sports-proxy-observation-loop` exits 0; latest artifact is
  `sports_proxy_observation_loop_blocked_no_observations` (honest: no open sports
  contracts in the current scan). Settled-market snapshot fetched 1000 public
  markets.

## Learned

- The crypto observation loop is ~85% generic: the snapshot/dedupe/due-probe/
  settlement-match/label-emit machinery copies directly. Sports differences are
  purely cosmetic constants (`sports_obs_` prefix, sports `packet_type` strings,
  sports output dirs) plus the sports `feature_status` ready value
  (`sports_proxy_features_ready`) and the sports-specific observation fields
  (league, team codes, cluster key, win_probability, predicted_side).
- The label source is identical to crypto: Kalshi public settlement. The
  strength-model `win_probability` is explicitly NOT the label (regression-tested:
  a row where the model predicted "no" but Kalshi settled YES yields
  `yes_outcome == 1`).
- The crypto-proxy orderbook-depth enrichment flag is genuinely crypto-specific
  (it depends on the Coinbase proxy price); it is correctly dropped for sports.

## Next Route

- Milestone 1 sports lane is now feature-packet + observation/label complete.
- Next: Milestone 2 sports falsification harness (FDR binomial + BH q-value on
  sports labels), research-candidate replay (Wilson calibration), and the
  capacity/correlation/decay gate with a sports cluster key.

## Guardrail

Every observation and label row is `usable=false`,
`calibrated_probability=null`, `expected_value_per_contract=null`. Raw observation
and label packets stay outside the repo under `manual_drops/`. No execution,
account, order, sizing, or DB-write paths. The strength model is never the label.
