# Strangler-Fig Migration Complete

**Outcome:** Completed the sports family migration onto the SignalFamily engine. All shared helpers single-sourced from `predmarket.shared_helpers`. M1 tech debt items addressed. Behavioral invariance verified for both crypto and sports families.

**Evidence:**
- 563 unit tests pass (no regressions)
- 143 crypto characterization + router tests pass without assertion changes
- 89 sports tests pass without assertion changes
- Net code reduction: -171 lines (120 insertions, 291 deletions)
- All 5 binding quality gates green
- Spine modules under 1,500 lines (engine.py 746, shared_helpers.py 453)
- `predmarket/` has zero imports of `scripts/`

**Changes:**
- `kalshi_falsification_replay_shared.py`: removed 23 duplicated function definitions, replaced with imports from `predmarket.shared_helpers`
- Tech debt (a): split sports blocked-label reason into `pending_contract_not_settled_in_snapshot` / `settlement_outcome_missing`
- Tech debt (b): standardized `path_is_within(MACRO_DIR, out_dir)` guard across all families' write_* functions
- Tech debt (c): added `test_lmb_team_resolver_via_espn` (mirrors KBO test)
- Tech debt (d): replaced `proxy_state_prediction(string)` with `crypto_prediction_rule(row)[0]` at all 3 crypto call sites

**Learned:** Single-sourcing requires careful signature compatibility. The `outside_repo` function in `kalshi_falsification_replay_shared.py` used a module-level `CONTROL_REPO` global while `predmarket.shared_helpers.outside_repo` requires an explicit parameter — resolved with a thin wrapper. The `safety_flags()` and `bucket_time()` signatures were backward-compatible (additional optional kwargs with defaults). The `proxy_state_prediction` → `crypto_prediction_rule` transition was safe because both return identical side predictions for the same inputs, just with different calling conventions.

**Next Route:** Weather family (Milestone 4). The engine spine is closed for modification — adding weather requires only a new descriptor + family-specific modules, zero edits to the generic spine.

**Guardrail:** Crypto characterization tests remain the safety net for strangler-fig. Any divergence on identical inputs is a defect.
