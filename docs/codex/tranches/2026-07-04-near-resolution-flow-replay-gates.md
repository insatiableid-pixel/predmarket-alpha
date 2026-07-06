# Near-Resolution Flow Replay Gates

Date: 2026-07-04

## Objective

Take the FDR-surviving near-resolution informed-flow candidate and force it through the next deployment boundary: conservative calibration, all-in Kalshi cost replay, current depth/capacity, correlation-cluster control, and decay survival.

The goal was not to create a trade. The goal was to determine exactly which downstream gate still blocks the candidate before paper stake.

## Changes

- Added `scripts/kalshi_near_resolution_flow_replay_gates.py`.
  - Consumes `latest-kalshi-near-resolution-informed-flow-evidence-gate.json`.
  - Replays only `flow_depth_imbalance_settlement_directional`.
  - Uses Wilson lower-bound calibration from the OOS survivor.
  - Replays historical exact-contract rows through `normalize_kalshi_execution_cost`.
  - Selects fresh current rows from sports microstructure snapshots.
  - Measures top-of-book selected-side depth and capacity.
  - Applies mechanical cluster control using controlled cluster costs.
  - Checks close-time decay buckets.
  - Emits `paper_decision_blocker_rows`.

- Hardened `scripts/kalshi_near_resolution_informed_flow_evidence_gate.py`.
  - Flow rows now carry event/series/surface provenance.
  - Flow rows now carry settlement time, quotes, and top-of-book depth fields needed for replay.

- Wired the artifact into the operating loop.
  - Added `make kalshi-near-resolution-flow-replay-gates`.
  - Added the target to `kalshi-sports-nondirectional-evidence-watch-once`.
  - Added the replay gate to default paper gate-evidence paths.
  - Added the replay artifact to the sports evidence-cycle report.

## Latest Run

Command:

```bash
make kalshi-sports-label-accumulation-cycle
make kalshi-near-resolution-flow-replay-gates
make kalshi-paper-decision-candidates
make kalshi-live-preflight
make kalshi-sports-evidence-cycle-report
```

Flow replay status: `near_resolution_flow_replay_gates_blocked_decay_survival`.

Passing evidence:

- FDR candidate: `flow_depth_imbalance_settlement_directional`
- OOS: 30/33 correct
- Conservative selected-side probability: `0.7931031818`
- Historical replay rows: 107
- Costed replay rows: 31
- Positive cost-adjusted replay rows: 4
- Fresh current candidates: 22
- Positive-depth current candidates: 8
- Positive-depth contracts: `154715.45`
- Positive-depth cost: `54451.564096`
- Raw largest cluster share: `0.7756268879`
- Controlled largest cluster share: `0.35`
- Controlled clusters: 6/3
- Controlled positive-depth cost: `18796.1029138467`

Blocking evidence:

- Decay labels: 107
- Decay buckets: 2
- Required buckets: 3
- Recent bucket accuracy: `1.0`
- Cumulative decay accuracy: `0.8878504673`

Interpretation: the candidate is no longer blocked by cost, current depth, or cluster control. It is blocked by insufficient decay breadth across close-time buckets.

## Paper And Live State

- Paper decisions: `paper_decision_candidates_ready_all_rows_blocked`
- Paper candidates: 484
- Gate-evidence rows: 82
- Flow blocker rows: 22
- Paper usable: 0
- Total paper stake: `$0`
- Live preflight: `kalshi_live_blocked`
- Live decisions: 484
- Live eligible: 0
- Total live stake: `$0`

Flow rows now enter the paper decision artifact with exact ticker, side, calibrated probability, market probability, all-in cost, EV, capacity estimate, cluster key, and a blocker list. Current blocker: `decay_survival not passing`.

## Guardrails

- No threshold lowering.
- No discretionary candidate approval.
- No paper stake.
- No live eligibility.
- No account path.
- No order path.
- No execution side effect.

## Verification

- `python -m py_compile` on touched scripts: passed.
- `ruff check` on touched scripts/tests: passed.
- Focused tests: 23 passed.
- New flow replay tests: 3 passed after cluster-control patch.
- `make kalshi-sports-label-accumulation-cycle`: exits 0.
- `make kalshi-near-resolution-flow-replay-gates`: exits 0.
- `make kalshi-paper-decision-candidates`: exits 0.
- `make kalshi-live-preflight`: exits 0.
- `make kalshi-sports-evidence-cycle-report`: exits 0.

## Next Machine Action

Accumulate one more independent close-time decay bucket for `flow_depth_imbalance_settlement_directional`, then rerun:

```bash
make kalshi-sports-label-accumulation-cycle
make kalshi-near-resolution-flow-replay-gates
make kalshi-paper-decision-candidates
make kalshi-live-preflight
```

Stop before paper stake unless the existing 3-bucket/100-label decay survival gate passes. Do not lower the threshold.
