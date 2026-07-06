# Engine Extraction (Strangler-Fig)

## Outcome
Extracted the generic SignalFamily engine under `predmarket/` and migrated crypto + sports onto it. Shared helpers single-sourced (no per-family duplication). Import boundary holds (`predmarket/` does not import `scripts/`). Behavioral invariance confirmed: all 573 tests pass; crypto characterization tests pass without assertion changes.

## Evidence
- `predmarket/signal_family.py` — SignalFamily descriptor with 9 plug-in fields
- `predmarket/shared_helpers.py` — single-sourced statistical + IO helpers
- `predmarket/engine.py` — generic spine stages (falsification, calibration, decay, cluster control)
- `predmarket/crypto_family.py` — CryptoProxyFamily (ASSET_CONFIG, prediction rule, cluster key, model evaluators)
- `predmarket/sports_family.py` — SportsBaseballFamily (strength model evaluator, sports cluster key)
- Refactored `scripts/kalshi_crypto_proxy_feature_model_falsification.py`, `_research_candidate_replay.py`, `_capacity_correlation_decay.py`, `_correlation_cluster_control.py` to import shared helpers
- `tests/test_engine_invariance.py` — 20 invariance tests proving engine route produces correct output
- `make test-unit`: 573 passed
- `make lint-baseline-check`: OK (1417/1422, ratchet improved)
- `make modularize`: 2 kept, 0 broken (import boundary intact)

## Learned
The strangler-fig approach (adding the engine behind the existing code, then refactoring scripts to delegate) was essential for maintaining behavioral invariance. Key gotchas: `proxy_state_prediction` takes a raw string value (not a row dict) in the existing scripts, so CryptoProxyFamily's `crypto_prediction_rule` (which takes a row) was not a drop-in replacement — kept local wrappers in scripts. `bucket_time` behavior (exact minute vs 15-minute resolution) must match pre-existing scripts exactly.

## Next Route
Milestone 4 — Weather family through the engine: add a new descriptor + NWS fetcher + bracket prediction rule + station-keyed cluster. Should require zero edits to the generic spine.

## Guardrail
Do not regenerate `.ruff-baseline.json` / `.tech-debt-baseline.json` / `.large-file-baseline.json` without justification. The engine is closed for modification — adding a family must only touch a new descriptor + family-specific modules.
