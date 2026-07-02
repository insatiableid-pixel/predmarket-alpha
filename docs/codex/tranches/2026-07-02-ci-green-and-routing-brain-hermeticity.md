# 2026-07-02 CI Green and Routing Brain Hermeticity

## Problem

The CI built in the prior tranche (README, pre-commit, CI workflow, security
workflows, docs) was red on day one for two compounding reasons:

1. **Lint job**: `ruff check predmarket/ tests/ main.py` produced 1362 errors
   across legacy code. Pre-commit only lints staged files, so the legacy tree
   was never cleaned. `ruff format --check` had 77 unformatted files.

2. **Test job**: 9 tests failed in `test_kalshi_signal_factory_status.py` --
   the routing brain of the entire macro operation. Root cause: a
   non-hermetic default-path leak. `build_signal_factory_status()` had 13 path
   parameters with defaults pointing to real on-disk artifacts. Tests that
   omitted `crypto_proxy_research_candidate_replay_path` silently read the real
   `latest-kalshi-crypto-proxy-research-candidate-replay.json`, whose status
   (`blocked_predeployment_gates`) short-circuited `next_tranche()` to
   `kalshi_crypto_proxy_capacity_correlation_decay` regardless of the synthetic
   inputs.

## Changes

### Routing brain hardening (`scripts/kalshi_signal_factory_status.py`)

- Introduced `Artifacts` frozen dataclass bundling all 13 upstream artifact
  paths. `build_signal_factory_status()` now takes a single `artifacts:
  Artifacts` parameter instead of 13 individual path params with on-disk
  defaults.
- `Artifacts.isolated(base)` returns a bundle where every path points to a
  missing file under `base` -- the hermetic default for tests.
- `Artifacts.from_macro_dir()` resolves all paths to the macro directory for
  production use.
- `main()` and `parse_args()` updated to construct and pass an `Artifacts`
  bundle.
- This eliminates the 13-parameter footgun: callers cannot forget a path and
  accidentally leak real disk state.

### Test updates

- `tests/test_kalshi_signal_factory_status.py`: rewrote all 15 tests to use
  `Artifacts.isolated(tmp_path)` + `dataclasses.replace()` pattern. Updated
  `load_status_module()` to register in `sys.modules` (Python 3.14 dataclass
  requirement). Updated `write_crypto_signal_foundation()` to return an
  `Artifacts` bundle. Added `test_signal_factory_status_is_hermetic_with_isolated_bundle`
  regression test proving the module never leaks disk state when given an
  isolated bundle.
- `tests/integration/test_local_artifact_replay.py`: updated `load_module()`
  to register in `sys.modules`. Updated `write_crypto_signal_foundation()` to
  return an `Artifacts` bundle. Updated 3 call sites.

### CI lint baseline/ratchet gate

- `.ruff-baseline.json`: captures current violation counts (1362 lint, 77
  format).
- `scripts/ruff_baseline_check.py`: runs `ruff check` and `ruff format
  --check`, compares counts to baseline, fails only when a count *increases*.
  This keeps CI green today while preventing new violations.
- `.github/workflows/ci.yml`: lint job now runs
  `python3 scripts/ruff_baseline_check.py` instead of full-tree ruff.
- Makefile: added `lint-baseline-check` and `lint-baseline-regen` targets.

## Verification

- 390 unit tests pass (was 381 with 9 failures).
- 11 integration tests pass.
- `make lint-baseline-check` passes (lint 1362/1362, format 77/77).

## What This Unblocks

The macro router and signal-factory status report are now trustworthy: their
test suite is hermetic and green, and CI will catch regressions. The routed
product tranche (capacity-depth, correlation-cluster, decay-survival gates for
crypto proxy replay) can proceed on a reliable foundation.
