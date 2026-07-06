# Sports Paper Burn-In Cycle

Date: 2026-07-04

## What Changed

- Added `scripts/kalshi_sports_paper_burn_in_cycle.py`.
- Added `make kalshi-sports-paper-burn-in-cycle`.
- The target runs `kalshi-sports-label-accumulation-cycle` first, then refreshes paper settlement, signal retirement, sports evidence, label accumulation, and one burn-in audit.
- If `KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1`, only due paper-usable exact tickers are eligible for public Kalshi settlement probing.
- The cycle writes `latest-kalshi-sports-paper-burn-in-cycle.{json,md,csv}`.

## Latest Run

Command:

```bash
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

Result:

- Status: `sports_paper_burn_in_waiting_for_next_close`
- Paper usable: `14`
- Due before fetch: `0`
- Due after fetch: `0`
- Settled paper usable: `0`
- Next paper close: `2026-07-04T20:00:00Z`
- Live eligible: `0`
- Retirement: `signal_decay_retirement_ledger_ready`, `10` active / `0` retired
- Sports evidence: `sports_evidence_cycle_ready_with_label_progress`

Label state:

- Total exact labels: `327`
- Total independent labels: `80`
- Total deficit: `10`
- MLB: `28/30`, deficit `2`
- World Cup/FIFA: OOS/FDR candidate-ready, `50` independent, deficit `0`
- ATP: `2/10`, deficit `8`

## Guardrails

- Research-only.
- No live orders, account paths, approval queues, or execution paths.
- No threshold lowering.
- No duplicate contract labels counted as independent evidence.
- No non-Kalshi settlement source used as outcome truth.

## Verification

- `PYTEST_ADDOPTS=-s .venv/bin/python -m pytest -q tests/test_kalshi_sports_paper_burn_in_cycle.py tests/test_kalshi_sports_label_accumulation_cycle.py tests/test_kalshi_paper_settlement_reconcile.py` -> `36 passed`
- `.venv/bin/ruff check scripts/kalshi_sports_paper_burn_in_cycle.py tests/test_kalshi_sports_paper_burn_in_cycle.py` -> pass
- `.venv/bin/python -m py_compile scripts/kalshi_sports_paper_burn_in_cycle.py` -> pass
- `make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1` -> exit `0`
- `PYTEST_ADDOPTS=-s make test-unit` -> `809 passed`, `14 deselected`
- `make test-integration` -> `14 passed`
- `make quality` -> exit `0` with expected advisory Ruff/deptry backlog

## Next Action

At or after `2026-07-04T20:00:00Z`, rerun:

```bash
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

If rows settle, audit realized paper P&L and retirement first. If they remain unresolved, keep waiting/probing exact public Kalshi settlement payloads.
