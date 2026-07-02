# Kalshi Hypothesis Registry And Falsification Gate

Date: 2026-07-01

## Summary

Built the first signal-factory layer after the Kalshi universe scanner. The new registry turns universe-scan candidates and EV-ledger rows into deterministic `HypothesisCandidateV1` rows, then routes every hypothesis through a falsification gate that blocks promotion until labeled out-of-sample, cost-aware, FDR-controlled evidence exists.

## Artifacts

- `scripts/kalshi_hypothesis_registry.py`
- `docs/codex/macro/kalshi-hypothesis-candidate.schema.json`
- `docs/codex/macro/latest-kalshi-hypothesis-registry.json`
- `docs/codex/macro/latest-kalshi-hypothesis-registry.md`
- `docs/codex/macro/latest-kalshi-hypothesis-registry.csv`
- `docs/codex/macro/latest-kalshi-falsification-gate.json`
- `docs/codex/macro/latest-kalshi-falsification-gate.md`
- `tests/test_kalshi_hypothesis_registry.py`

## Current Result

- Registry status: `hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence`
- Registered hypotheses: 36
- Tested hypotheses: 0
- Promoted hypotheses: 0
- Blocked by falsification: 36
- Multiple-testing families: 36

## Macro Routing

`make macro-route` now routes predmarket to the next true blocker:

`Use predmarket as the Kalshi signal-factory command center: build the labeled out-of-sample replay/backtest harness that attaches settled outcomes, time-safe quote snapshots, all-in costs, and FDR-adjusted promotion/rejection evidence to registered HypothesisCandidate IDs.`

## Guardrail

This tranche did not add sizing, execution, account/order paths, discretionary candidate selection, or usable-edge promotion. It intentionally made every hypothesis unvalidated until falsification evidence exists.
