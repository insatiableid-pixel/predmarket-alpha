# Completion Report: Generalized Falsification + Replay (Milestone 2)

**Date:** 2026-07-03
**Feature ID:** `generalized-falsification-replay`

## Summary

Generalized the falsification harness and research-candidate replay so they accept a family's model-evaluator list + prediction rule, then the sports strength-win-probability model runs through them. The generic statistical core (Benjamini-Hochberg FDR, exact binomial test, chronological OOS split, contract-key independence collapse, Wilson lower-bound calibration, all-in cost via `predmarket.kalshi_execution_cost`) is reused UNCHANGED from the shared companion module.

## What Changed

**New files:**
- `scripts/kalshi_falsification_replay_shared.py` — shared companion module with generic statistical core, label loading, replay math, decay bucketing, and writer scaffolding (family-agnostic)
- `scripts/kalshi_sports_proxy_feature_model_falsification.py` — sports falsification: strength_win_prob_directional evaluator, sports prediction rule via `predicted_side`, BH q-value at alpha=0.10
- `scripts/kalshi_sports_proxy_research_candidate_replay.py` — sports replay: Wilson lower-bound calibration, all-in cost, margin = calibrated - break_even, EV = calibrated - all_in_cost, sports cluster key `league|ticker|date`
- `tests/test_kalshi_sports_proxy_feature_model_falsification.py` — 14 test cases covering VAL-SGATE-001 through VAL-SGATE-010, writer, safety, makefile
- `tests/test_kalshi_sports_proxy_research_candidate_replay.py` — 13 test cases covering VAL-SGATE-011 through VAL-SGATE-018, writer, cluster key, makefile

**Modified files:**
- `Makefile` — added `kalshi-sports-proxy-feature-model-falsification`, `kalshi-sports-proxy-research-candidate-replay` targets + vars; wired into watch-once chain; added to .PHONY and help text
- `docs/codex/current-state.md` — prepended landing entry

## Latest Evidence

- `make test-unit`: 521 passed, 11 deselected
- Crypto characterization suite: 143 passed (unchanged)
- Crypto falsification/replay: 12 passed (unchanged)
- Sports falsification: 14 passed
- Sports replay: 13 passed
- All 5 binding quality gates: green

## Artifacts

- `scripts/kalshi_falsification_replay_shared.py` (shared generic core)
- `scripts/kalshi_sports_proxy_feature_model_falsification.py` (+ `latest-kalshi-sports-proxy-feature-model-falsification.*` pointers)
- `scripts/kalshi_sports_proxy_research_candidate_replay.py` (+ `latest-kalshi-sports-proxy-research-candidate-replay.*` pointers)

## Verification

- Sports falsification promotes statistically significant models to `research_candidate_fdr_passed` (VAL-SGATE-008)
- Sports falsification blocks below-random models (VAL-SGATE-009)
- Wilson lower-bound is never above raw OOS accuracy (VAL-SGATE-012)
- All-in cost via `predmarket.kalshi_execution_cost` (Kalshi-venue-generic, VAL-SGATE-015/018)
- margin = calibrated - break_even; EV = calibrated - all_in_cost (VAL-SGATE-016)

## Safety

- Every row: `usable=false`, `calibrated_probability=null`, `expected_value_per_contract=null`
- No execution, no account/order paths, no database writes
- Only public market data calls; no authenticated/paid calls

## Next Blocker

- CCD gate (capacity/correlation/decay) for sports — currently blocked "No public depth or validated local order-book depth"
- Correlation cluster control for sports
- Engine extraction (M3 strangler-fig)
