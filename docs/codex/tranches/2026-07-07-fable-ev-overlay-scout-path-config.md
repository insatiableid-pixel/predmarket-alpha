# 2026-07-07 Fable EV Overlay Scout Path Config

## Landing

Removed machine-specific manual-drop defaults from:

- `scripts/kalshi_ev_nfl_overlay_assembler.py`
- `scripts/kalshi_ev_local_contract_evidence_scout.py`

Overlay output dirs and local evidence scout search paths now derive from `manual_drop_path()`. The scout instruction now names `PREDMARKET_MANUAL_DROPS_ROOT/kalshi/` instead of a workstation-specific root. Existing CLI overrides, Make targets, and local-only safety semantics are unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py tests/test_kalshi_ev_nfl_overlay_assembler.py tests/test_kalshi_ev_local_contract_evidence_scout.py -q` -> `27 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check scripts/kalshi_ev_nfl_overlay_assembler.py scripts/kalshi_ev_local_contract_evidence_scout.py tests/test_kalshi_path_defaults.py` -> `All checks passed`
- Hardcoded root scan over touched runtime files found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- Make dry-runs passed for:
  - `kalshi-ev-nfl-overlay-assembler`
  - `kalshi-ev-local-contract-evidence-scout`
- `git diff --check` clean for touched files.
