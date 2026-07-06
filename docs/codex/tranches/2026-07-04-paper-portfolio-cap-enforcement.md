# Paper Portfolio Cap Enforcement

Date: 2026-07-04

## Objective

Continue implementing Claude's advice by turning paper portfolio cap diagnostics into an operational gate. The prior paper artifact could report `paper_portfolio_cap_breaches_present` while still emitting nonzero paper-usable stake, which violates the breadth/correlation discipline Claude called out.

## Landing

- Added hard paper portfolio cap enforcement in `predmarket/paper_decision_engine.py`.
- Added `max_cluster_share` and `enforce_portfolio_caps` controls to paper decision construction.
- Wired `scripts/kalshi_paper_decision_candidates.py` so the operational CLI/Make path enforces portfolio caps by default.
- Added `KALSHI_PAPER_DECISION_MAX_CLUSTER_SHARE ?= 0.35` to the Makefile and passed it through `make kalshi-paper-decision-candidates`.
- Added a regression test proving a single-cluster paper candidate is converted to a zero-stake blocked row with explicit `max_cluster_share` blocker text.

## Latest Run

`make kalshi-paper-decision-candidates` now writes:

- Status: `paper_decision_candidates_ready_all_rows_blocked`
- Candidate count: `487`
- Paper-usable count: `0`
- Total paper stake: `0.0`
- Pre-enforcement cap status: `paper_portfolio_cap_breaches_present`
- Pre-enforcement cap breaches: `1`
- Cap-blocked candidates: `4`
- Final cap status: `paper_portfolio_caps_observed`
- Final cap breaches: `0`

The blocked rows remain in the artifact with `paper_stake_before_portfolio_cap_block` and explicit portfolio cap blockers. No rows are deleted, and no live/account/order path is enabled.

## Verification

- `.venv/bin/python -m pytest -s -q tests/test_kalshi_paper_autonomous_engine.py tests/test_paper_decision_fee_aware.py tests/integration/test_paper_autonomous_engine_replay.py` -> `84 passed`
- `.venv/bin/python -m ruff check predmarket/paper_decision_engine.py scripts/kalshi_paper_decision_candidates.py tests/test_kalshi_paper_autonomous_engine.py` -> pass
- `.venv/bin/python -m ruff format --check predmarket/paper_decision_engine.py scripts/kalshi_paper_decision_candidates.py tests/test_kalshi_paper_autonomous_engine.py` -> pass
- `make kalshi-paper-decision-candidates` -> exit 0

## Guardrails

- Research-only remains true.
- Live execution remains blocked.
- No threshold lowering.
- No manual approval queue.
- Paper stake is forced to zero when portfolio caps fail.

## Next Machine Action

Run `make kalshi-live-preflight` after the refreshed paper artifact and confirm `live_eligible_count=0`. Then continue toward Claude's main remaining gap: high-coverage timestamp-matched sharp consensus plus exact settlement labels.
