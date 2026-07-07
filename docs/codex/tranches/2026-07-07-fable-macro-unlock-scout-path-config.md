# 2026-07-07 Fable Macro Unlock Scout Path Config

## Landing

Removed machine-specific path defaults from `scripts/codex_macro_unlock_scout.py`.

The macro unlock scout now resolves:

- Manual drops through `manual_drop_path()`.
- MLB, ATP, NBA, and NFL sibling repo paths through `project_path()`.
- Generated next-local-command strings through configured project roots.
- Predmarket EV overlay missing-input guidance from the `manual_drops` argument passed into `build_unlock_scout()`.

This keeps the macro command-center behavior unchanged on the current workstation while allowing another clone to relocate local drops and sibling sports repos with `PREDMARKET_MANUAL_DROPS_ROOT` and `PREDMARKET_PROJECTS_ROOT`.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No manual EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py tests/test_codex_macro_unlock_scout.py -q` -> `34 passed`
- `ruff check --extend-ignore C901 scripts/codex_macro_unlock_scout.py tests/test_kalshi_path_defaults.py` -> pass
- `make lint-baseline-check` -> pass (`lint 98/1422`, `format 17/94`)
- `python -m py_compile scripts/codex_macro_unlock_scout.py` -> pass
- `make -n macro-unlock-scout` -> pass

Note: plain touched-file Ruff still reports the pre-existing `_mlb_lane` complexity (`C901 29 > 12`). This tranche did not change that function's branching behavior; the repository lint ratchet remains the hard quality gate for that baseline.
