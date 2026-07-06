# Near-Resolution Flow EV Ledger And Paper Promotion

Date: 2026-07-04

## Objective

Complete the sports evidence mission by moving the FDR-surviving near-resolution informed-flow signal from replay-gate evidence into the EV ledger and paper decision chain, without opening live execution.

## Landing

- Added `scripts/kalshi_near_resolution_flow_terms_capture.py` plus `make kalshi-near-resolution-flow-terms-capture`.
- The terms capture reads current pass-status flow capacity rows, fetches public Kalshi market-detail payloads, writes raw official terms outside the repo under `/home/mrwatson/manual_drops/kalshi/kalshi_scored_sports_flow_terms_*.json`, and emits latest JSON/MD/CSV artifacts under `docs/codex/macro/`.
- Extended `scripts/kalshi_contract_ev_ledger.py` so a ready `near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion` artifact can create usable `microstructure_informed_flow` EV rows only when official Kalshi terms are verified.
- Updated `predmarket/paper_decision_engine.py` to stop ingesting duplicate flow blocker rows once the flow replay is ready for EV-ledger promotion; the EV ledger becomes the single paper source for that promoted signal.
- Added the flow terms artifact to `scripts/kalshi_sports_evidence_cycle_report.py` and wired `make kalshi-sports-evidence-cycle` to run terms capture before EV ledger promotion.

## Current Evidence

Latest full cycle status:

- Flow replay: `near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion`
- Conservative calibrated side probability: `0.7592066891`
- FDR q-value: `3.08e-8`
- Independent labels: `198`
- Decay buckets: `4/4` pass, recent bucket accuracy `0.8472222222`
- Controlled clusters: `10`
- Controlled positive-depth cost: `$43,459.7562938467`
- Official terms capture: `near_resolution_flow_terms_capture_ready`, `18/18` current targets captured, `18` official-rule markets
- EV ledger: `kalshi_ev_ledger_ready_with_usable_contract_edges`, `392` rows, `30` usable rows, `18/18` usable flow rows
- Paper decisions: `paper_decision_candidates_ready_with_paper_sized_rows`, `460` candidates, `18` usable paper rows, `$2,006.686796` total paper stake
- Live preflight: `kalshi_live_blocked`, `460` decisions, `0` live eligible, `$0` live stake
- Retirement: `signal_decay_retirement_ledger_ready`, `10` active signals, `0` retired

World Cup also advanced to `world_cup_proxy_feature_model_falsification_ready_with_research_candidates` with `50` independent labels and `1` research candidate. It is still research evidence only until downstream cost, capacity, cluster, decay, EV, and paper gates promote it.

## Guardrails

- No execution mode was armed.
- No account/order path was introduced or called by the new terms capture.
- Live preflight remains blocked.
- Official terms are captured from public Kalshi market-detail endpoints and raw payloads remain outside the repo.
- The paper promotion uses the existing paper decision machinery; no manual approval queue or discretionary candidate selection was added.

## Verification

- `TMPDIR=/home/mrwatson/projects/predmarket-alpha/.tmp PYTHONPATH=. PYTEST_ADDOPTS=-s pytest -q tests/test_kalshi_sports_evidence_cycle_report.py tests/test_kalshi_near_resolution_flow_terms_capture.py`
- `ruff check scripts/kalshi_sports_evidence_cycle_report.py scripts/kalshi_near_resolution_flow_terms_capture.py scripts/kalshi_contract_ev_ledger.py predmarket/paper_decision_engine.py tests/test_kalshi_sports_evidence_cycle_report.py tests/test_kalshi_near_resolution_flow_terms_capture.py tests/test_kalshi_contract_ev_ledger.py tests/test_kalshi_paper_autonomous_engine.py`
- `python -m py_compile scripts/kalshi_near_resolution_flow_terms_capture.py scripts/kalshi_contract_ev_ledger.py predmarket/paper_decision_engine.py`
- `make test-unit` -> `800 passed, 14 deselected`
- `make test-integration` -> `14 passed`
- `make quality` -> exits `0` with expected advisory Ruff/deptry backlog
- `make kalshi-sports-evidence-cycle` -> exits `0`

## Next

1. Add portfolio-level paper risk reporting/capping so total and cluster paper stake cannot be mistaken for production bankroll deployment.
2. Let the new World Cup research candidate enter the same replay/capacity/cluster/decay chain without lowering thresholds.
3. Build the current-market snapshot and external-preflight joins needed to reduce live preflight blockers while keeping execution disabled.
