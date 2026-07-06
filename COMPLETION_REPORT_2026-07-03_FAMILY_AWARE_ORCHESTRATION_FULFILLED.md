# COMPLETION REPORT: Family-Aware Orchestration (FULFILLED)

**Date:** 2026-07-03
**Feature:** family-aware-orchestration (Milestone 1: sports-feature-foundation)
**Skill:** signal-factory-worker

## Summary

Generalized the three single-family orchestration scripts so the Kalshi signal
factory reports and routes MULTIPLE signal families (crypto_proxy +
sports_baseball) without being hardcoded to crypto. All changes are ADDITIVE:
crypto behavior and its 143 characterization tests stay green (strangler-fig
precursor). 28 new tests added; `make test-unit` passes with 453 tests; all 5
binding quality gates pass.

## What Changed

### 1. `scripts/kalshi_signal_factory_status.py` (1427 lines) + `scripts/kalshi_signal_factory_families.py` (245 lines, new)

- **Family registry**: a companion module enumerates families so capability
  iteration is data-driven. Adding a family is a data change, not a rewrite.
- **Per-family capability groupings**: `report["families"]["crypto_proxy"]` and
  `report["families"]["sports_baseball"]`, each with its own capability list.
- **Multi-family summary rollup**: `report["summary"]["families"]` with
  per-family status + `capability_gate_counts`, plus overall
  `report["summary"]["capability_gate_counts"]` (unchanged).
- **Artifacts dataclass**: extended with `sports_proxy_feature_packet_path` and
  `sports_proxy_observation_loop_path` (family-keyed). Crypto path defaults are
  intact; sports paths default to `missing-*` files under base (hermetic).
- **Top-level status selection**: chosen across families by advancement rank
  with a documented `report["status_selection"]` note. Ties resolve to crypto
  (preserving crypto behavior).
- **Per-family status strings**: each family's individual status is always
  exposed in the summary, even when it is not the leading family.

### 2. `scripts/kalshi_probability_breadth_scout.py` (760 lines)

- **Sports route**: `sports_baseball_fast_label_route` for KXMLBGAME/KXKBOGAME/
  KXLMBGAME series tickers. Not shadowed or starved by crypto.
- **Order-independent routing**: `select_route` checks crypto first (preserving
  existing tests), then sports, then weather. Sports surfaces in
  `sports_fast_candidate_count`, `fast_classification_counts`, and
  `work_order_candidates` even when crypto wins `selected_route`.
- **Sports source plan**: official game result (league box score) as settlement
  source; MLB Stats API + ESPN as keyless proxy feature sources; proxy policy
  forbids using proxy feeds as settlement labels.
- **Sports classification predicate**: `is_sports_baseball_candidate()` is a
  pure function of the series ticker; explicitly excludes KXMLBRUN and
  KXMLBPLAYER.

### 3. `scripts/codex_macro_router.py` (6757 lines, additive only)

- **Priority-override set**: 4 sports signal statuses + 1 blocked status added
  to `apply_scheduling()` with tier parity to crypto (architecture_leverage=5,
  evidence_delta=5, etc.).
- **Tranche selection**: 5 sports-specific tranche entries with sports next-
  tranche + stop condition (references sports feature packet / observation /
  falsification; forbids execution/account/order paths).
- **PARKED_UNLOCKS**: 5 sports-specific unlock messages.
- **Artifact paths**: sports proxy feature-packet + observation-loop paths
  added to `predmarket_status()`'s artifact_paths list.
- **Parked-state logic**: preserved (all_lanes_parked -> command center +
  blocker summary, including when the sports status is active).

## Latest Evidence

- Latest status report: `docs/codex/macro/latest-kalshi-signal-factory-status.json`
  contains both `crypto_proxy` (8 capabilities, status
  `signal_factory_crypto_proxy_capacity_depth_blocked`) and `sports_baseball`
  (2 capabilities, status
  `signal_factory_sports_baseball_blocked_missing_feature_packet`).
- Latest scout: `docs/codex/macro/latest-kalshi-probability-breadth-scout.json`
  shows `sports_fast_candidate_count: 2` alongside `crypto_fast_candidate_count: 9`
  and `weather_fast_candidate_count: 192`.
- Latest decision: `docs/codex/macro/latest-decision.json` recommends
  predmarket-alpha with the crypto capacity-depth blocked tranche.

## Artifacts

- `scripts/kalshi_signal_factory_families.py` (new companion module)
- `scripts/kalshi_signal_factory_status.py` (modified)
- `scripts/kalshi_probability_breadth_scout.py` (modified)
- `scripts/codex_macro_router.py` (modified, additive)
- `tests/test_kalshi_signal_factory_status.py` (+11 tests)
- `tests/test_kalshi_probability_breadth_scout.py` (+13 tests)
- `tests/test_codex_macro_router.py` (+6 tests)
- `docs/codex/macro/latest-kalshi-signal-factory-status.{json,md}` (refreshed)
- `docs/codex/macro/latest-kalshi-probability-breadth-scout.{json,md}` (refreshed)

## Verification

| Command | Exit | Observation |
|---|---|---|
| `PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_crypto_proxy_*.py tests/test_kalshi_signal_factory_status.py tests/test_kalshi_probability_breadth_scout.py tests/test_codex_macro_router.py -q` | 0 | 143 passed (crypto characterization unchanged) |
| `make test-unit` | 0 | 453 passed, 11 deselected |
| `make lint-baseline-check tech-debt-check file-sizes-check modularize validate-agents` | 0 | All 5 binding gates pass |
| `make kalshi-signal-factory-status` | 0 | Both families present in output |
| `make kalshi-probability-breadth-scout` | 0 | sports_fast_candidate_count: 2 |
| `make macro-route` | 0 | predmarket-alpha recommended |

## Safety

- Every artifact carries `research_only=true`, `execution_enabled=false`,
  `usable=false`, `calibrated_probability=null`.
- No execution, account/order, database-write, staking, or sizing paths.
- Sports source plan names official game results as settlement; MLB Stats API /
  ESPN as proxy model features only.
- Import boundary respected: `predmarket/` does not import `scripts/`.
- Raw public payloads stay outside the repo under `/home/mrwatson/manual_drops/`.

## Next Blocker

The sports feature-packet builder (`sports-feature-packet`) and observation/label
loop (`sports-observation-label-loop`) are the next M1 features. They will
produce the sports artifacts that this orchestration layer is already wired to
consume. Until those exist, the sports family will remain at
`signal_factory_sports_baseball_blocked_missing_feature_packet`.
