# Paper Portfolio Risk Audit

Date: 2026-07-04

## Goal

Make current paper-usable Kalshi sports EV candidates auditable as a portfolio
before any live execution work. The north-star risk was that individually
passing paper rows could look like unconstrained deployable edge while still
being concentrated in one signal, one family, or one close-time cluster.

## What Changed

- Added `predmarket/paper_portfolio_risk.py`.
- Wired portfolio diagnostics into:
  - `predmarket/paper_decision_engine.py`
  - `scripts/kalshi_paper_decision_candidates.py`
  - `scripts/kalshi_paper_settlement_reconcile.py`
  - `scripts/kalshi_sports_paper_burn_in_cycle.py`
  - `scripts/kalshi_sports_evidence_cycle_report.py`
- Added focused regressions in:
  - `tests/test_kalshi_paper_autonomous_engine.py`
  - `tests/test_kalshi_paper_settlement_reconcile.py`
  - `tests/test_kalshi_sports_paper_burn_in_cycle.py`
  - `tests/test_kalshi_sports_evidence_cycle_report.py`

## Artifact Contract

Paper artifacts now emit:

- total paper stake
- settled, unresolved, and due-unresolved paper stake
- largest family exposure
- largest signal exposure
- largest cluster exposure
- largest contract exposure
- cluster and contract cap status
- explicit cap-breach rows

This is diagnostic reporting only. It does not authorize live trading, change
thresholds, rewrite stakes after outcomes, or infer settlement from non-Kalshi
sources.

## Latest Real Run

Commands:

```bash
make kalshi-paper-decision-candidates
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

State:

- Paper decisions: `paper_decision_candidates_ready_with_paper_sized_rows`
- Paper usable rows: `14`
- Total paper stake: `$890.54206`
- Portfolio cap status: `paper_portfolio_caps_observed`
- Cap breaches: `0`
- Largest cluster: `mlb|KXMLBGAME-26JUL041335MINNYY|2026-07-04T20:35Z`
- Largest cluster stake/share: `$200` / `0.2245823179`
- Largest signal: `microstructure_informed_flow|flow_depth_imbalance_settlement_directional|depth_imbalance_yes_abs_gt_0_25|predmarket-alpha`
- Largest signal stake/share: `$890.54206` / `1.0`
- Settlement: `paper_settlement_reconciliation_waiting_for_close`
- Settled paper rows: `0`
- Unresolved paper rows: `14`
- Due unresolved paper rows: `0`
- Next paper close: `2026-07-04T20:00:00Z`
- Live preflight: `kalshi_live_blocked`, `0` live-eligible, `$0` live stake

Sports labels:

- Status: `sports_label_accumulation_oos_fdr_paper_candidates_ready`
- Exact labels: `327`
- Independent labels: `80`
- Total label deficit: `10`

## Guardrails

- Exact public Kalshi settlement labels only.
- No threshold lowering.
- No manual candidate/trade approval queue.
- No account paths.
- No order paths.
- No live execution.
- No live eligibility created.

## Verification

- Touched-file Ruff check: pass
- Focused paper/settlement/burn-in/evidence tests: `34 passed`
- `make test-unit`: `814 passed, 14 deselected`
- `make test-integration`: `14 passed`
- `make quality`: exits `0` with expected advisory Ruff/deptry backlog
- `make lint-baseline-check`: pass, `lint 118/1422`, `format 94/94`
- `make tech-debt-check`: pass, `22/22`
- `make file-sizes-check`: pass, no new oversized files
- `make modularize`: pass, `2` contracts kept, `0` broken

`predmarket/aggregator.py` was Ruff-formatted only to restore the format
ratchet without regenerating the baseline. No logic change was made there.

## Next Action

After `2026-07-04T20:00:00Z`, run:

```bash
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

If paper rows settle, judge realized PnL, calibration, and decay/retirement
before any live promotion. If they remain unresolved, keep the exact public
settlement loop running. Separately, macro routing now points to crypto proxy
cluster-control-ready paper overlay as the next non-sports lane.
