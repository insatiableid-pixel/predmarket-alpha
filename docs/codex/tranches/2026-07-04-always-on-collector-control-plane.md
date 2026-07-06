# Always-On Collector Control Plane

Date: 2026-07-04

## Why

Claude/Fable's central diagnosis was correct: the bottleneck is labeled
observations per day, not more model architecture. The repo already had strong
one-shot collectors and falsification gates, but no control plane that owns
cadence, due rows, next wake time, and safe repeated operation.

## What Changed

- Added `scripts/kalshi_always_on_collector.py`.
- Added `make kalshi-always-on-collector-once`.
- Added `make kalshi-always-on-collector`.
- Added `tests/test_kalshi_always_on_collector.py`.
- The collector wraps existing safe targets:
  - `sports`: `kalshi-sports-paper-burn-in-cycle`, with due exact-settlement probing armed.
  - `crypto`: `kalshi-crypto-proxy-observation-watch-once`, with public settlement capture/probing armed.
- The collector writes:
  - `docs/codex/macro/latest-kalshi-always-on-collector.json`
  - `docs/codex/macro/latest-kalshi-always-on-collector.md`
  - `docs/codex/macro/latest-kalshi-always-on-collector.csv`
  - `docs/codex/macro/latest-kalshi-always-on-collector.timer.example`

## Cadence Policy

- Due settlement rows present: `60` seconds.
- Near close/probe window: `60` seconds.
- Base interval: `300` seconds.
- All intervals are configurable through Make variables.

## Latest Run

Command:

```bash
make kalshi-always-on-collector-once
```

Result:

- Status: `kalshi_always_on_collector_ready`
- Targets passed: `2/2`
- Safe artifacts: `2/2`
- Total labels: `1545`
- Total due rows: `6231`
- Next interval: `60` seconds
- Cadence reason: `due_settlement_rows_present`
- Sports: `sports_paper_burn_in_waiting_for_next_close`, `327` exact labels, next close `2026-07-04T20:00:00Z`
- Crypto: `crypto_proxy_observation_loop_label_rows_ready`, `1218` labels, next public probe `2026-07-04T18:22:14Z`

## Guardrails

- Research-only.
- No account paths.
- No order paths.
- No live execution.
- No manual approval queue.
- No threshold lowering.
- No non-Kalshi settlement labels.

## Verification

- `.venv/bin/ruff check scripts/kalshi_always_on_collector.py tests/test_kalshi_always_on_collector.py` -> pass
- `PYTEST_ADDOPTS=-s .venv/bin/python -m pytest -q tests/test_kalshi_always_on_collector.py` -> `5 passed`
- `.venv/bin/python -m py_compile scripts/kalshi_always_on_collector.py` -> pass
- `make kalshi-always-on-collector-once` -> exit `0`
- `make test-unit` -> `814 passed, 14 deselected`
- `make test-integration` -> `14 passed`
- `make quality` -> exit `0` with expected advisory Ruff/deptry backlog

## Next Action

Run this under a long-lived supervisor when ready:

```bash
make kalshi-always-on-collector
```

Until then, run the one-shot form repeatedly:

```bash
make kalshi-always-on-collector-once
```
