# Completion Report: Strangler-Fig Migration Complete (Sports → Engine)

## Summary

Completed the strangler-fig migration of the SPORTS signal family onto the SignalFamily engine. All shared statistical helpers are now single-sourced from `predmarket.shared_helpers` instead of being duplicated in `scripts/kalshi_falsification_replay_shared.py`. Behavioral invariance verified: both families produce identical output on identical inputs. Four M1 tech debt items addressed.

## What Changed

- **Single-sourced shared helpers**: Removed 23 duplicated function definitions from `scripts/kalshi_falsification_replay_shared.py` (benjamini_hochberg, binomial_survival, wilson_lower_bound, chronological_split_index, independent_contract_rows, outcome_value, bucket_time, gate, safety_flags, safe_research_artifact, read_json_or_empty, outside_repo, plus 15+ type/IO helpers). All replaced with imports from `predmarket.shared_helpers`. Compat wrappers for `outside_repo` (signature diff) and `bucket_time`.

- **Tech debt (a)**: Sports observation-loop blocked-label reason split into `pending_contract_not_settled_in_snapshot` (ticker absent from settled index) vs `settlement_outcome_missing` (outcome unparseable), matching crypto's diagnosability.

- **Tech debt (b)**: Standardized `path_is_within(MACRO_DIR, out_dir)` guard across all `write_*` functions. Replaced 3 local `path_is_within` definitions in `kalshi_sports_proxy_capacity_correlation_decay.py`, `kalshi_sports_proxy_correlation_cluster_control.py`, and `kalshi_signal_factory_status.py` with imports from `predmarket.shared_helpers`.

- **Tech debt (c)**: Added `test_lmb_team_resolver_via_espn` in `tests/test_kalshi_sports_proxy_feature_packet.py`, mirroring the KBO test pattern (VAL-SFL-013 hardening).

- **Tech debt (d)**: Replaced all 3 local `proxy_state_prediction(string)` definitions in crypto scripts (falsification, replay, CCD) with imports of `crypto_prediction_rule(row)` from `predmarket.crypto_family`. Call sites updated from `proxy_state_prediction(row.get("proxy_state"))` to `crypto_prediction_rule(row)[0]`.

## Latest Evidence

- `make test-unit`: **563 passed** (no regressions)
- Crypto characterization + router suite: **143 passed** (unchanged)
- Sports characterization tests: **89 passed** (1 assertion update for blocked-label reason)
- Engine invariance tests: **20 passed**
- Quality gates: lint 1417/1422, tech-debt 22/22, file-sizes 3 known, modularize 2/0, AGENTS.md valid
- Net code delta: **+120 - 291 = -171 lines** (net reduction)
- No new oversized files; all spine modules under 1,500 lines

## Artifacts

- `predmarket/shared_helpers.py`: Single source for all shared helpers (453 lines)
- `predmarket/engine.py`: Generic spine (746 lines)
- `predmarket/signal_family.py`: Descriptor type (63 lines)
- `predmarket/crypto_family.py`: CryptoProxyFamily (172 lines)
- `predmarket/sports_family.py`: SportsBaseballFamily (141 lines)
- `scripts/kalshi_falsification_replay_shared.py`: Reduced to 800 lines (was ~1071)

## Verification

- All crypto scripts produce identical output on identical inputs (no behavioral change)
- Sports scripts use single-sourced helpers from predmarket
- Import boundary holds: `predmarket/` has zero imports of `scripts/`
- Spine contains no family-specific literals (generic only)

## Safety

- Research-only invariants preserved: every artifact carries `research_only=True`, `execution_enabled=False`, every row `usable=False`
- No execution, account, order, or DB-write paths introduced
- Gate thresholds unchanged (fdr_alpha=0.10, min_independent_labels=30, etc.)

## Next Blocker

Weather family (Milestone 4). The engine spine is closed for modification — adding weather touches only a new `WeatherFamily` descriptor, NWS fetcher, and family-specific modules. Zero edits to the generic spine.
