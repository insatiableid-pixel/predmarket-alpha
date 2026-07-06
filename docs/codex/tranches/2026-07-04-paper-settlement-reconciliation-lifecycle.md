# 2026-07-04 Paper Settlement Reconciliation Lifecycle

## Purpose

Turn the newly paper-sized near-resolution informed-flow rows into a forward paper experiment that can be resolved, scored, and fed into decay/retirement without human discretion.

## Landing

- Added `scripts/kalshi_paper_settlement_reconcile.py`.
- Added `make kalshi-paper-settlement-reconcile`.
- The reconciler freezes `latest-paper-decision-candidates`, joins exact public Kalshi market payloads by `contract_ticker`, and writes:
  - `docs/codex/macro/latest-paper-settlement-reconciliation.json`
  - `docs/codex/macro/latest-paper-settlement-reconciliation.md`
  - `docs/codex/macro/latest-paper-settlement-reconciliation.csv`
- Added optional exact-ticker public probing with `KALSHI_PAPER_SETTLEMENT_FETCH=1`; raw payloads stay outside the repo under `/home/mrwatson/manual_drops/kalshi_paper_settlements/`.
- Wired `kalshi-sports-evidence-cycle` so paper decisions are built, paper settlement reconciliation runs, retirement consumes the enriched paper artifact, live preflight still consumes paper decisions, and the cycle report surfaces paper settlement status/P&L.
- Fixed retirement calibration for selected-side probabilities. Correct NO-side paper rows now compare `calibrated_probability` to selected-side win/loss, while directional accuracy still compares predicted YES/NO outcome to the market YES outcome.

## Latest Real State

- Paper settlement status: `paper_settlement_reconciliation_waiting_for_close`.
- Paper candidates: `470`.
- Paper-usable rows: `10`.
- Frozen paper stake: `$717.725981`.
- Settled paper-usable rows: `0`.
- Unresolved paper-usable rows: `10`.
- Due unresolved rows: `0`.
- Next close among these paper rows: `2026-07-04T18:05:00Z`.
- Retirement: `signal_decay_retirement_ledger_ready`, 10 active signals, 0 retired.
- Sports cycle: `sports_evidence_cycle_ready_with_label_progress`, 20/20 safe artifacts.
- Live remains blocked: 0 live-eligible rows, $0 live stake.

## Guardrails

- No live orders.
- No account/order paths.
- No manual approval queue.
- No outcome inference from non-Kalshi sources.
- No hindsight rewriting of paper decisions, probabilities, or stakes.

## Verification

- Focused reconciliation/retirement/report/paper tests: 56 passed.
- `make test-unit`: 805 passed / 14 deselected.
- `make test-integration`: 14 passed.
- `make quality`: exits 0 with expected advisory Ruff/deptry backlog.
- `make kalshi-sports-evidence-cycle`: exits 0.
- Touched-file Ruff: clean.
- `py_compile`: clean.

## Next Machine Action

After `2026-07-04T18:05Z`, run:

```bash
make kalshi-paper-settlement-reconcile KALSHI_PAPER_SETTLEMENT_FETCH=1
make kalshi-signal-decay-retirement KALSHI_SIGNAL_DECAY_RETIREMENT_PAPER_DECISIONS=docs/codex/macro/latest-paper-settlement-reconciliation.json
make kalshi-sports-evidence-cycle-report
```

Then inspect realized P&L, selected-side calibration, recent bucket survival, and retirement status before considering any live-readiness work.
