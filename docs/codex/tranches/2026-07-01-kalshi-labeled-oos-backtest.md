# Kalshi Labeled OOS Backtest Harness

Date: 2026-07-01

## Summary

Built the first universal labeled out-of-sample falsification harness for the Kalshi signal factory. It reads safe local label packets keyed to `HypothesisCandidate` IDs, enforces point-in-time timing checks, evaluates all-in cost-aware OOS outcomes, applies Benjamini-Hochberg FDR correction, and emits research-only promotion/rejection/blocker decisions.

## Artifacts

- `scripts/kalshi_labeled_oos_backtest.py`
- `docs/codex/macro/kalshi-labeled-oos-observation.schema.json`
- `docs/codex/macro/latest-kalshi-labeled-oos-backtest.json`
- `docs/codex/macro/latest-kalshi-labeled-oos-backtest.md`
- `docs/codex/macro/latest-kalshi-labeled-oos-backtest.csv`
- `docs/codex/macro/latest-kalshi-oos-falsification-gate.json`
- `docs/codex/macro/latest-kalshi-oos-falsification-gate.md`
- `tests/test_kalshi_labeled_oos_backtest.py`

## Current Result

- Backtest status: `labeled_oos_backtest_blocked_missing_labeled_observations`
- Hypotheses: 36
- Label packets: 0
- Valid observations: 0
- Testable hypotheses: 0
- Research promotions: 0

## Macro Routing

`make macro-route` now routes predmarket to the next exact bottleneck:

`Use predmarket as the Kalshi signal-factory command center: build safe labeled-observation packets keyed to registered HypothesisCandidate IDs by attaching settled outcomes, point-in-time quote/model timestamps, and all-in costs without relabeling proxy evidence as OOS proof.`

## Guardrail

This tranche did not make provider calls, database writes, account/order calls, sizing recommendations, or execution changes. Same-slate proxy evidence is not relabeled as OOS proof.
