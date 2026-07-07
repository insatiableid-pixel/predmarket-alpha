# 2026-07-07 Fable EV Ledger Path Config

## Landing

Removed machine-specific path defaults from `scripts/kalshi_contract_ev_ledger.py`.

The EV ledger now resolves:

- NFL fair-line and validation artifacts through `project_path()`.
- Official Kalshi terms snapshots through `manual_drop_path("kalshi")`.
- Calibrated-probability overlays through `manual_drop_path("kalshi_ev_probabilities")`.
- Contract-mapping overlays through `manual_drop_path("kalshi_ev_contract_mappings")`.
- Generated next-action command strings through configurable project roots.

This preserves the current workstation behavior while allowing fresh clones to relocate data and sibling repos with `PREDMARKET_MANUAL_DROPS_ROOT` and `PREDMARKET_PROJECTS_ROOT`.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No manual EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py tests/test_kalshi_contract_ev_ledger.py -q` -> `49 passed`
- `ruff check scripts/kalshi_contract_ev_ledger.py tests/test_kalshi_path_defaults.py` -> pass
- `python -m py_compile scripts/kalshi_contract_ev_ledger.py` -> pass
- `make -n kalshi-ev-ledger` -> pass
- `make -n kalshi-ev-overlay-preflight` -> pass
- `make -n kalshi-ev-calibration-work-order` -> pass
- `make -n kalshi-ev-contract-mapping-work-order` -> pass
