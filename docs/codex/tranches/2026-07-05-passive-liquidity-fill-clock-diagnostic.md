# Passive-Liquidity Fill Clock Diagnostic

Date: 2026-07-05

## Purpose

Continue following Claude's sports advice by turning the passive-liquidity paper-fill drought into an auditable clock/cadence problem instead of treating timeout-only evidence as a real falsification result.

Passive maker-fill evidence needs actual paper touches observed from later public snapshots before OOS/FDR can test adverse-selection-adjusted maker EV. The previous state had persisted paper intents and timeout labels, but no proof that the collector had any snapshot inside the maker-intent TTL.

## Landing

- Added `scripts/kalshi_passive_liquidity_fill_clock_diagnostic.py`.
- Added `tests/test_kalshi_passive_liquidity_fill_clock_diagnostic.py`.
- Added `make kalshi-passive-liquidity-fill-clock-diagnostic`.
- Wired the diagnostic into `make kalshi-sports-nondirectional-evidence-watch-once`.
- Wired the artifact into `scripts/kalshi_sports_evidence_cycle_report.py`.
- Updated the passive maker-intent TTL Make default to `3600` seconds after the diagnostic observed a snapshot cadence longer than the prior TTL.

## Method

- Join persisted paper maker intents to later sports microstructure snapshots by exact `contract_ticker`.
- Count future snapshots inside and after each intent TTL.
- Diagnose whether each intent is blocked by missing later snapshots, TTL shorter than snapshot cadence, missing side book, quote not reached, or a paper touch fill.
- Keep public orderbook touches as paper labels only; never claim real exchange fills.
- Emit summary fields for TTL/cadence mismatch count, future snapshots inside TTL, recommended TTL, paper fill count, and primary bottleneck.

## Real Run

Initial diagnostic against the existing paper state:

- Status: `passive_liquidity_fill_clock_diagnostic_ready_ttl_cadence_mismatch`
- Paper intents: `462`
- Paper labels: `226`
- Paper fills: `0`
- Paper timeouts: `226`
- Future snapshots inside TTL: `0`
- TTL/cadence mismatches: `226`

After changing the default TTL and running `make kalshi-sports-nondirectional-evidence-watch-once` twice:

- Passive paper-fill loop status: `passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels`
- Paper intents: `942`
- Paper labels: `461`
- Paper fills: `3`
- Paper timeouts: `458`
- Open intents: `481`
- Fill-clock diagnostic status: `passive_liquidity_fill_clock_diagnostic_ready_with_paper_fills`
- Future snapshots inside TTL: `240`
- Recommended TTL seconds: `3600`

The passive paper-fill falsification gate now runs with real paper fills:

- Status: `passive_liquidity_paper_fill_falsification_ready_no_research_candidates`
- Valid paper fill labels: `461`
- Tested hypotheses: `1`
- FDR survivors: `0`
- Research candidates: `0`
- Real exchange fill labels: `0`

This is an honest no-edge result from the gate, not a missing-evidence block.

## Guardrails

- `research_only=true`
- `execution_enabled=false`
- `market_execution=false`
- `account_or_order_paths=false`
- `staking_or_sizing_guidance=false`
- `usable=false`
- `real_exchange_fill_label_count=0`
- No calibrated probability, EV promotion, stake, order, account call, or live eligibility is emitted.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest -q tests/test_kalshi_passive_liquidity_fill_clock_diagnostic.py tests/test_kalshi_sports_evidence_cycle_report.py` -> `7 passed`
- `python -m ruff check` on touched files -> clean
- `python -m ruff format --check` on touched files -> clean
- `python -m py_compile` on touched scripts -> clean
- `make kalshi-sports-nondirectional-evidence-watch-once` -> exits 0 twice
- `make kalshi-sports-evidence-cycle-report` -> exits 0
- `make test-unit` -> `1313 passed / 15 deselected`
- `make test-integration` -> `14 passed`
- `make lint-baseline-check` -> exits 0 (`lint 100/1422`, `format 8/94`)
- `make quality` -> exits 0 with existing advisory Ruff/deptry output
- `git diff --check` -> exits 0 with line-ending warnings only

## Claude Implementation Estimate

After this tranche, the Claude attachment is roughly `90%` implemented.

Still incomplete:

- Consensus lane needs enough exact settlement labels and OOS labels to produce or reject FDR survivors.
- NBA strict consensus is still missing.
- Soccer needs Asian-sharp enrichment before provider coverage is mature.
- Passive liquidity needs more maker paper-fill labels and adverse-selection evidence before it can graduate.
- Paper P&L, calibration drift, and decay retirement need repeated post-close updates.
- Live remains blocked until paper evidence and live-risk gates justify an explicit execution tranche.
