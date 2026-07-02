# 2026-07-01 Kalshi Signal Factory Status

## Summary

Recorded the new north star as a machine-readable command-center status. The report evaluates the current operation against the required signal-factory pipeline: universe inventory, deterministic routing, EV ledger, hypothesis registry, falsification, calibrated probabilities, capacity, correlation, sizing, execution controls, and decay.

## Artifacts

- `docs/codex/macro/kalshi-signal-factory-north-star.md`
- `scripts/kalshi_signal_factory_status.py`
- `tests/test_kalshi_signal_factory_status.py`
- `docs/codex/macro/kalshi-signal-factory-status-latest/kalshi-signal-factory-status.json`
- `docs/codex/macro/kalshi-signal-factory-status-latest/kalshi-signal-factory-status.md`
- `docs/codex/macro/latest-kalshi-signal-factory-status.json`
- `docs/codex/macro/latest-kalshi-signal-factory-status.md`

## Result

Status: `signal_factory_foundation_ready_falsification_missing`

- Universe candidates: 6,070
- Model-route candidates: 725
- Soft-watch candidates: 5,345
- EV ledger rows: 348
- Legacy usable EV rows: 12
- Review queue rows: 12
- Repeat-positive rows: 12

Capability gates:

- Pass: universe inventory, deterministic routing, contract EV ledger.
- Warn: calibrated probability feeds.
- Blocked: hypothesis registry, FDR falsification, capacity model, correlation model, fractional Kelly sizing policy, execution control plane, realized P&L decay loop.

## Next Tranche

Build the `HypothesisCandidate` registry and FDR-controlled, out-of-sample, cost-aware falsification gate. Stop before adding sizing, execution, account/order paths, or discretionary candidate selection.

