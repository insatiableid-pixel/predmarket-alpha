# Kalshi Labeled Observation Builder

Date: 2026-07-01

## Summary

Built the bridge between registered hypotheses and the labeled OOS backtest harness. The new builder records model-backed pending observations from the EV ledger and emits settled label packets only when public Kalshi settlement evidence exists. It also adds a safe watch-once command that fetches public settled markets outside the repo before rebuilding the packets.

## Artifacts

- `scripts/kalshi_labeled_observation_builder.py`
- `docs/codex/macro/latest-kalshi-labeled-observation-builder.json`
- `docs/codex/macro/latest-kalshi-labeled-observation-builder.md`
- `docs/codex/macro/latest-kalshi-labeled-observation-builder.csv`
- `tests/test_kalshi_labeled_observation_builder.py`
- `Makefile` targets: `kalshi-labeled-observation-builder`, `kalshi-labeled-observation-watch-once`

## Current Result

- Builder status: `labeled_observation_builder_pending_observations_waiting_settlement`
- Pending observations: 44
- Public settled markets loaded by watch-once: 1,000
- Settled label rows: 0
- Labeled OOS backtest remains: `labeled_oos_backtest_blocked_missing_labeled_observations`

## Macro Routing

`make macro-route` now routes predmarket to calibrated-probability breadth while pending observations wait for settlement:

`Use predmarket as the Kalshi signal-factory command center: while pending OOS observations wait for settlement, expand calibrated-probability coverage across exact Kalshi contracts and fast-settling routes without treating unresolved rows as proof.`

## Guardrail

Pending observations are not OOS proof. The builder does not test, promote, size, or execute. Raw public settled-market payloads stay outside the repo under `/home/mrwatson/manual_drops/kalshi_oos_settlements/`.
