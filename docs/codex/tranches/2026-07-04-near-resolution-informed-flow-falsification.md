# Near-Resolution Informed-Flow Falsification

Date: 2026-07-04

## Objective

Act on the advice that near-resolution informed flow is the compute-bound sports family to attack now, while directional MLB, World Cup/FIFA, and ATP labels continue accumulating on the calendar.

The goal was not to create a tradable probability. The goal was to test whether the existing public orderbook microstructure history contains a pre-registered, non-random settlement signal after exact contract independence, chronological OOS scoring, and FDR control.

## Changes

- Extended `scripts/kalshi_near_resolution_informed_flow_evidence_gate.py`.
  - Added four pre-registered candidate hypotheses:
    - `flow_quote_momentum_forward_quote`
    - `flow_depth_imbalance_forward_quote`
    - `flow_depth_delta_forward_quote`
    - `flow_depth_imbalance_settlement_directional`
  - Collapses each candidate to one row per exact `contract_ticker`.
  - Uses chronological OOS splitting via `chronological_split_index`.
  - Scores exact binomial p-values when the candidate has enough independent and OOS labels.
  - Applies Benjamini-Hochberg FDR across testable candidates.
  - Emits best candidate metadata, candidate counts, and explicit gates for pre-registration, OOS split, and FDR survival.

- Added a regression test in `tests/test_kalshi_sports_microstructure_evidence.py`.
  - Synthetic microstructure rows create a known depth-imbalance settlement relationship.
  - The gate finds a `research_candidate_fdr_passed`.
  - The artifact still reports `usable_row_count == 0`.

## Latest Run

Command:

```bash
make kalshi-sports-label-accumulation-cycle
```

Result: `near_resolution_informed_flow_research_candidates_ready`.

- Flow rows: 605
- Distinct contracts: 359
- Repeated-snapshot contracts: 131
- Settled contract labels: 107
- Forward quote labels: 56
- Pre-registered candidates: 4
- Testable candidates: 1
- FDR-surviving research candidates: 1

Survivor:

- Model id: `flow_depth_imbalance_settlement_directional`
- Label type: exact Kalshi settlement
- Independent contract labels: 107
- OOS labels: 33
- OOS correct: 30
- OOS accuracy: `0.9090909091`
- p-value: `7.006e-7`
- q-value: `7.006e-7`

Blocked candidates:

- `flow_quote_momentum_forward_quote`: 11 independent labels, 4 OOS labels.
- `flow_depth_imbalance_forward_quote`: 24 independent labels, 8 OOS labels.
- `flow_depth_delta_forward_quote`: 10 independent labels, 3 OOS labels.

## Boundary

This is a research candidate only.

- No calibrated probability was emitted.
- No EV row was emitted.
- No paper stake was emitted.
- No live eligibility was emitted.
- No account or order path was touched.
- No threshold was lowered.
- No broad hypothesis search was run.

Latest downstream state:

- `latest-paper-decision-candidates.json`: `paper_decision_candidates_ready_all_rows_blocked`, 492 candidates, 0 usable, total paper stake `$0`.
- `latest-kalshi-live-preflight.json`: `kalshi_live_blocked`, 492 decisions, 0 eligible, total live stake `$0`.

## Verification

- `python -m py_compile scripts/kalshi_near_resolution_informed_flow_evidence_gate.py`: passed.
- `PYTHONPATH=. PYTEST_ADDOPTS=-s pytest -q tests/test_kalshi_sports_microstructure_evidence.py`: 5 passed.
- `ruff check scripts/kalshi_near_resolution_informed_flow_evidence_gate.py tests/test_kalshi_sports_microstructure_evidence.py`: passed.
- `make kalshi-sports-label-accumulation-cycle`: exits 0.
- `make test-unit`: 699 passed, 14 deselected.
- `make test-integration`: 14 passed.
- `make lint-baseline-check`: OK, lint 1407/1422 and format 91/94.
- `make tech-debt-check`: OK, 22/22.
- `make file-sizes-check`: OK, no new oversized files.
- `make modularize`: OK, 2 import-linter contracts kept.
- `make quality`: exits 0 with expected advisory Ruff and deptry backlog.

## Next Machine Action

Build the downstream replay for `flow_depth_imbalance_settlement_directional`:

- all-in Kalshi cost replay,
- current depth and capacity support,
- correlation-cluster control,
- decay-survival buckets,
- then paper decision admission only if every gate passes.

Stop before paper stake if any downstream gate blocks. The candidate is strong enough to deserve the replay, not strong enough to trade.
