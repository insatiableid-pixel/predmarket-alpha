# Sports Paper Blockers And Microstructure Evidence

Date: 2026-07-04

## Summary

This tranche moved current sports markets from inventory into the shared gate chain without relaxing any promotion rule. World Cup/FIFA, MLB, and ATP now emit exact-contract paper decision blocker rows, so the paper/live engines can audit why each sports row is not tradable yet instead of ignoring it upstream.

It also added the first research-only substrate for the medium-term sports microstructure families: near-resolution informed-flow detection and passive-liquidity provision. Both families now have concrete observation/evidence artifacts and remain correctly blocked until they have the labels/fills required to falsify them.

## What Changed

- Added sports gate-evidence ingestion to `predmarket/paper_decision_engine.py`.
- Added default sports gate-evidence input and CLI controls to `scripts/kalshi_paper_decision_candidates.py`.
- Extended `scripts/kalshi_sports_stack_sequencing.py` with 90 exact-contract paper blocker rows:
  - 30 World Cup/FIFA rows.
  - 30 MLB rows.
  - 30 ATP rows.
- Added a strict future promotion path in `scripts/kalshi_contract_ev_ledger.py` for sports CCD output:
  - CCD status must be ready.
  - Correlation-cluster status must be ready.
  - Controlled depth must be positive.
  - Official terms and all paper gates must pass.
- Added `scripts/kalshi_sports_microstructure_observation_loop.py` for public sports orderbook observation capture.
- Added `scripts/kalshi_near_resolution_informed_flow_evidence_gate.py`.
- Added `scripts/kalshi_passive_liquidity_provision_evidence_gate.py`.
- Added Make targets:
  - `kalshi-sports-microstructure-observation-loop`
  - `kalshi-sports-microstructure-observation-watch-once`
  - `kalshi-near-resolution-informed-flow-evidence-gate`
  - `kalshi-passive-liquidity-provision-evidence-gate`
  - `kalshi-sports-nondirectional-evidence-watch-once`

## Latest Artifacts

- `latest-kalshi-sports-stack-sequencing.json`
  - Status: `sports_stack_sequencing_ready_current_depth_passed`
  - Candidate count: 5974
  - Paper blocker rows: 90 sampled exact-contract blockers.
- `latest-paper-decision-candidates.json`
  - Status: `paper_decision_candidates_ready_all_rows_blocked`
  - Candidates: 478
  - EV-ledger rows: 388
  - Gate-evidence rows: 90
  - Paper usable: 0
  - Blocked: 478
- `latest-kalshi-live-preflight.json`
  - Status: `kalshi_live_blocked`
  - Live decisions: 478
  - Live eligible: 0
  - Total live stake: 0
- `latest-kalshi-sports-microstructure-observation-loop.json`
  - Status: `sports_microstructure_observation_loop_ready`
- `latest-kalshi-near-resolution-informed-flow-evidence-gate.json`
  - Status: `near_resolution_informed_flow_blocked_missing_settled_labels`
  - Flow rows: 120
- `latest-kalshi-passive-liquidity-provision-evidence-gate.json`
  - Status: `passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels`
  - Virtual order rows: 94

Raw public orderbooks and microstructure observation packets are written outside the repo:

- `/home/mrwatson/manual_drops/kalshi_sports_microstructure_orderbooks/`
- `/home/mrwatson/manual_drops/kalshi_sports_microstructure_observations/`

## Guardrails

- No discretionary approval queue.
- No threshold lowering.
- No sportsbook shortcut to tradable probability.
- No donor repo runtime dependency.
- No live account/order path from research artifacts.
- No paper/live stake unless OOS/FDR, cost, capacity, cluster, decay, and live-risk gates all pass.
- Every current sports blocker row has `usable=false`, `execution_enabled=false`, and zero stake.

## Verification

- Focused tranche tests: 9 passed.
- `make test-unit`: 690 passed / 14 deselected.
- `make test-integration`: 14 passed.
- `make lint-baseline-check`: passed (`lint 1407/1422`, `format 88/94`).
- `make tech-debt-check`: passed (`22/22`).
- `make file-sizes-check`: passed with no new oversized files.
- `make modularize`: passed, 2 contracts kept.
- `make quality`: exits 0 with expected advisory Ruff/deptry backlog.

## Next Bottleneck

Collect settlement labels and repeated near-resolution snapshots until World Cup/FIFA, MLB, and ATP can move from explicit blockers into falsification. For the passive-liquidity family, real or exchange-observable fill/adverse-selection evidence is still missing; keep it counterfactual-only until that evidence exists.
