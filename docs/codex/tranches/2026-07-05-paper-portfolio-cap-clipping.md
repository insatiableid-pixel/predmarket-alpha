# 2026-07-05 Paper Portfolio Cap Clipping

## Why

Claude's sports advice makes near-resolution informed flow the fastest useful family, but the paper layer was still hard-blocking every EV survivor when pre-enforcement cluster shares exceeded the portfolio cap. That was too conservative for a diversified basket: capacity discipline should resize feasible allocations, not erase them.

## What Changed

- Replaced paper portfolio cap hard-blocking with deterministic cap clipping in `predmarket/paper_decision_engine.py`.
- Reused the shared `controlled_cluster_costs` math so paper sizing matches the existing family-agnostic capacity/correlation control.
- Kept the single-cluster case hard-blocked as infeasible under `max_cluster_share=0.35`.
- Added `paper_portfolio_cap_adjusted_candidate_count` and per-row cap clip metadata.
- Added a regression proving a feasible three-cluster basket remains paper-usable with zero cap breaches.

## Real Run

- EV ledger: `kalshi_ev_ledger_ready_with_usable_contract_edges`
- Paper decisions: `paper_decision_candidates_ready_with_paper_sized_rows`
- Paper usable rows: `4`
- Total paper stake: `$33.659219`
- Paper cap breaches: `0`
- Cap-adjusted rows: `1`
- Cap-blocked rows: `0`
- Settlement: `paper_settlement_reconciliation_waiting_for_close`
- Retirement: `0` retired signals
- Live: `kalshi_live_blocked`, `0` live-eligible rows

The four paper-usable rows are all `microstructure_informed_flow` / `flow_depth_imbalance_settlement_directional` rows with verified official terms. No live execution, account, or order path was enabled.

## Verification

- `python -m pytest -s -q tests/test_kalshi_paper_autonomous_engine.py` -> `26 passed`
- `python -m ruff check predmarket/paper_decision_engine.py tests/test_kalshi_paper_autonomous_engine.py`
- `python -m ruff format --check predmarket/paper_decision_engine.py tests/test_kalshi_paper_autonomous_engine.py`
- `make kalshi-paper-decision-candidates`
- `make kalshi-paper-settlement-reconcile`
- `make kalshi-signal-decay-retirement KALSHI_SIGNAL_DECAY_RETIREMENT_PAPER_DECISIONS=docs/codex/macro/latest-paper-settlement-reconciliation.json`
- `make kalshi-live-preflight`
- `make kalshi-sports-evidence-cycle-report`

## Remaining Claude Gaps

- Exact settlement labels for the sharp consensus lane are still insufficient for OOS/FDR promotion.
- NBA strict consensus is not implemented.
- Soccer strict consensus still lacks an Asian sharp anchor.
- Passive liquidity has a real paper intent/label clock, but no FDR survivor from paper fill labels yet.
- The new paper candidates must close, settle, and feed realized paper P&L into decay before any live claim.
