# Tranche: Generalized Falsification + Replay for Sports (Milestone 2)

**Date:** 2026-07-03

## Outcome

Generalized the falsification harness and research-candidate replay to accept a family's model-evaluator list + prediction rule, then ran the sports strength-win-probability model through them. Created shared companion module `scripts/kalshi_falsification_replay_shared.py` with the generic statistical core reused unchanged. Built `scripts/kalshi_sports_proxy_feature_model_falsification.py` and `scripts/kalshi_sports_proxy_research_candidate_replay.py`. All 27 artifact-replay tests pass (promotion AND block branches); crypto invariance confirmed (12+143 tests unchanged).

## Evidence

- `make test-unit`: 521 passed, 11 deselected
- Crypto characterization suite: 143 passed
- Crypto falsification/replay tests: 12 passed
- Sports falsification tests: 14 passed
- Sports replay tests: 13 passed
- All 5 binding quality gates: green (lint-baseline-check, tech-debt-check, file-sizes-check, modularize, validate-agents)

## Learned

- The shared companion module pattern (`scripts/` importing `scripts/` via `sys.path.insert`) works cleanly for the falsification/replay shared core.
- The generic `evaluate_models` function parameterized by `model_evaluators` list is the clean generalization: sports passes `[evaluate_sports_strength_win_prob]`, crypto keeps its inline version.
- Wilson lower-bound calibration correctly ensures `conservative_calibrated_side_probability <= raw_oos_accuracy` for sports just as for crypto.

## Next Route

- CCD gate (capacity/correlation/decay) for sports
- Correlation cluster control for sports
- Wire into the sports watch-once chain (already done for falsification + replay)
- Extract shared spine into full SignalFamily engine (M3)

## Guardrail

- Crypto invariance is sacred: the 12 falsification/replay crypto tests + 143 characterization tests must stay green.
- Threshold constants (30/10/0.30/0.10) must remain identical across families.
- Every row `usable=false`.
