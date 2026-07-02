# Predmarket Type 2 Threshold Sensitivity

Date: 2026-06-29

## Scope

After the timing-safe reference unlock, measured how far the clean watch-only candidate set sits below the current Type 2 review threshold.

This tranche used local artifacts only.

## Added

- `predmarket/type2_threshold_sensitivity.py`
- `tests/test_type2_threshold_sensitivity.py`
- `make type2-threshold-sensitivity`
- `docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.json`
- `docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.md`

## Result

- status: `threshold_sensitivity_no_current_threshold_candidates`
- candidates: 24
- timing-clean candidates: 24
- positive-net candidates: 10
- current threshold: 0.1000
- current-threshold candidate count: 0
- max positive review-only net divergence: 0.0177
- gap to current threshold: 0.0823

Hypothetical counts:

- threshold 0.020: 0
- threshold 0.015: 1
- threshold 0.010: 2
- threshold 0.005: 6

## Decision

The clean predmarket pair is not close to the current review threshold. The roadblock is not timing, malformed mapping, or missing report plumbing. It is evidence strength under the current threshold policy.

## Guardrail

The report does not lower thresholds, promote candidates, authorize execution, or make a profitability claim.
