# 2026-07-03 Paper-Autonomous EV Engine Foundation

## Summary

Implemented the first paper-autonomous Kalshi EV engine layer: donor inventory, generic external artifact validation, safe formula specs, fail-closed paper decision candidates, and signal decay/retirement tracking.

The system now has a mechanical path from broad donor surfaces into paper decision artifacts, but the current landing intentionally admits no stake until every statistical and market-structure gate is explicitly satisfied.

## What Changed

- Added `predmarket/source_inventory.py` with typed donor repo descriptors and read-only git/provenance snapshots.
- Added `predmarket/external_artifact_bridge.py` with a generic manifest and strict preflight validation for external artifacts.
- Migrated `predmarket/mlb_platform_bridge.py` onto the generic bridge without changing its optional/missing/unsafe behavior.
- Added `predmarket/signal_formula.py`, a Kalshi-safe formula DSL for generated weak signals. Formulas may compute numeric features/signals, but cannot execute Python, import modules, access attributes, index objects, or bypass the whitelist.
- Added `predmarket/paper_decision_engine.py` with unified `PaperDecisionCandidate` rows and fractional Kelly sizing that is forced to zero unless all upstream gates pass.
- Paper decision rows preserve `signal_key`, `signal_formula_key`, close bucket, predicted outcome, and settlement outcome so decay/retirement can feed deterministically into the next run.
- Added `predmarket/signal_decay_retirement.py` with per-signal survival summaries and deterministic retirement status.
- Added scripts and Make targets for:
  - `kalshi-source-repo-inventory`
  - `kalshi-external-artifact-wrap`
  - `kalshi-external-artifact-preflight`
  - `kalshi-signal-formula-registry`
  - `kalshi-paper-decision-candidates`
  - `kalshi-signal-decay-retirement`
- Added `tests/test_kalshi_paper_autonomous_engine.py`.

## Current Artifact State

- Source inventory: `source_repo_inventory_ready`; 8 existing donor repos, 13 candidate artifacts, 12 existing artifacts, 6 dirty donor repos.
- External artifact wrap: `external_artifact_wrap_ready`; 12 wrapped artifacts, 910 wrapped rows, 1 blocked missing optional MLB-platform live model drop.
- External artifact preflight: `external_artifact_preflight_ready`; 13 artifacts checked, 12 admitted, 910 safe rows, 1 blocked missing optional MLB-platform live model drop.
- Formula registry: `signal_formula_registry_ready`; 2 safe formulas, 2 multiple-testing hypotheses.
- Paper decisions: `paper_decision_candidates_ready_all_rows_blocked`; 348 ledger rows, 348 blocked, 0 paper-usable, $0 total paper stake.
- Decay retirement: `signal_decay_retirement_ledger_ready`; 4 active signals, 0 retired.

## Guardrails

- No live execution, account, order, approval queue, or trading path was added.
- Donor repos are inventoried and validated as artifacts only; none becomes a runtime import dependency.
- Existing Kalshi gates remain hard. Thresholds were not lowered.
- External model probabilities are not tradable until they pass falsification, replay, capacity/depth, correlation cluster, and decay survival gates.
- Blocked paper rows are emitted with explicit blockers rather than silently disappearing.

## Verification

- `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/test_kalshi_paper_autonomous_engine.py`: 9 passed.
- Focused MLB bridge compatibility tests: 2 passed.
- Targeted ruff check on new files: passed.
- `make kalshi-source-repo-inventory`: passed.
- `make kalshi-external-artifact-wrap`: passed.
- `make kalshi-external-artifact-preflight`: passed.
- `make kalshi-signal-formula-registry`: passed.
- `make kalshi-paper-decision-candidates`: passed.
- `make kalshi-signal-decay-retirement`: passed.
- `make kalshi-signal-factory-status`: passed.
- `make kalshi-ev-ledger`: passed.
- `make test-unit`: 631 passed, 14 deselected.
- Paper-autonomous integration replay: 2 passed.
- `make test-integration`: 14 passed.
- `make quality`: passed; deptry remains advisory and reports existing dependency findings.

## Next Step

Route the admitted wrapped rows into the family-specific falsification/replay adapters. Start with contract-keyed NFL overlay rows because they already have exact Kalshi ticker/side mappings and calibrated probabilities, but keep paper stake at zero until falsification, all-in cost, capacity, correlation, and decay gates all pass.
