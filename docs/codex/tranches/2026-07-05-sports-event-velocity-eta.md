# Sports Event-Velocity ETA

Date: 2026-07-05

## Purpose

Continue implementing Claude's advice by making label velocity and ETA explicit per sports evidence surface.

Before this tranche, several lanes correctly blocked on insufficient labels or OOS evidence, but the control plane did not show whether the bottleneck was calendar settlement, missing feed construction, compute/downstream gates, or passive maker-fill accumulation. Claude explicitly called for a calendar/event-velocity forecast so "blocked, insufficient labels" becomes "blocked, ETA N days" or at least a precise evidence-backlog state.

## Landing

- Added `scripts/kalshi_sports_event_velocity_eta.py`.
- Added `make kalshi-sports-event-velocity-eta`.
- Added `latest-kalshi-sports-event-velocity-eta.{json,md,csv}` under the macro artifact pattern.
- Wired the target into `make kalshi-sports-evidence-cycle` before the final sports evidence report.
- Updated `scripts/kalshi_sports_evidence_cycle_report.py` so the event-velocity artifact is the 27th required safe artifact.
- Added focused tests in `tests/test_kalshi_sports_event_velocity_eta.py`.
- Updated `tests/test_kalshi_sports_evidence_cycle_report.py` to avoid real macro fallback and assert the new event-velocity summary fields.

## Method

The artifact reports control-plane rows for:

- `sports_consensus_all`
- `sports_consensus_mlb`
- `sports_consensus_atp`
- `sports_consensus_world_cup_soccer`
- `sports_consensus_nfl`
- `sports_consensus_nba`
- `mlb_proxy_directional`
- `atp_proxy_settlement_window`
- `world_cup_proxy_directional`
- `near_resolution_informed_flow`
- `passive_liquidity_paper_fill`

Each row carries:

- source status
- bottleneck type
- ETA/probe status
- active candidate count
- due count
- current labels
- independent labels
- OOS labels
- minimum labels
- label/OOS deficits
- paper fill counts/deficits where applicable
- next public label probe when known

The ETA policy is conservative: use exact next-probe timestamps when present; otherwise classify the blocker without inventing a deterministic settlement date.

## Guardrails

- `research_only=true`.
- `execution_enabled=false`.
- `market_execution=false`.
- `account_or_order_paths=false`.
- `staking_or_sizing_guidance=false`.
- No calibrated probability, EV, paper stake, live order, account call, provider call, or database write.
- The artifact does not lower thresholds and does not promote candidates.

## Real Run

`make kalshi-sports-event-velocity-eta` exits 0.

Current status:

- Status: `sports_event_velocity_eta_ready_with_paper_fill_deficits`
- Safe artifacts: `9/9`
- ETA surfaces: `11`
- Label/OOS-blocked surfaces: `9`
- Paper-fill-blocked surfaces: `1`
- Next due surface: `sports_consensus_all`, `14` due contracts
- NBA strict consensus: `blocked_missing_strict_consensus_feed`
- Passive liquidity: `blocked_waiting_for_paper_maker_fills`
- Near-resolution informed flow: `label_threshold_met_downstream_gates_active`
- World Cup proxy: `label_threshold_met`

`make kalshi-sports-evidence-cycle-report` exits 0.

Latest sports cycle:

- Status: `sports_evidence_cycle_ready_with_label_progress`
- Safe artifacts: `27/27`
- Event-velocity status: `sports_event_velocity_eta_ready_with_paper_fill_deficits`
- Live eligible rows: `0`

## Verification

- `python -m pytest -s -q tests/test_kalshi_sports_event_velocity_eta.py tests/test_kalshi_sports_evidence_cycle_report.py` -> `7 passed`
- `python -m ruff check` on touched script/test files -> clean
- `python -m ruff format --check` on touched script/test files -> clean
- `python -m py_compile` on touched scripts -> clean
- `make kalshi-sports-event-velocity-eta` -> exits 0
- `make kalshi-sports-evidence-cycle-report` -> exits 0
- `make test-unit` -> `1305 passed / 15 deselected`
- `make test-integration` -> `14 passed`
- `make lint-baseline-check` -> exits 0 (`lint 100/1422`, `format 8/94`)

## Claude Implementation Estimate

After this tranche, the Claude attachment is roughly `85%` implemented.

Still incomplete:

- Consensus lane needs enough exact settlement labels and OOS labels to test real survivors.
- NBA strict consensus is still missing.
- Soccer needs Asian-sharp enrichment before provider coverage is mature.
- World Cup outcome-level independence diagnostics for totals/BTTS are not yet first-class.
- Passive liquidity has no actual paper fills yet, so its FDR gate correctly has no tested hypotheses.
- Paper P&L, calibration drift, and decay retirement need repeated post-close updates.
- Live remains correctly blocked until paper evidence and live-risk gates justify an explicit execution tranche.
