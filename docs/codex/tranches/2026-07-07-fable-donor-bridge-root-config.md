# 2026-07-07 Fable Donor Bridge Root Config

## Purpose

Continue the Fable path/config cleanup on the donor admission surface. The
Makefile and shared helper roots were configurable, but `DEFAULT_SOURCE_REPOS`
still embedded workstation-specific donor and manual-drop paths.

## Changes

- `predmarket.source_inventory` now imports `manual_drop_path()` and
  `project_path()`.
- Donor repo paths now derive from `project_path(repo_name)`.
- Donor artifact paths under manual drops now derive from `manual_drop_path()`.
- Donor artifact paths under sibling repos now derive from
  `project_path(repo_name, relative_artifact_path)`.
- `predmarket.external_artifact_wrappers.DEFAULT_WRAP_ROOT` now derives from
  `manual_drop_path("predmarket_external_artifacts")`.
- Added a path-default regression test proving the donor bridge no longer
  hardcodes `/home/mrwatson/manual_drops` or `/home/mrwatson/projects`.

## Compatibility

Descriptor fields remain strings. Downstream inventory, wrapper, preflight, and
prior-only donor schemas are unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No candidate promotion.
- No EV/paper/live behavior change.
- No account/order/live execution path touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py tests/test_kalshi_paper_autonomous_engine.py::test_source_inventory_records_donor_state -q`
- `ruff check predmarket/source_inventory.py predmarket/external_artifact_wrappers.py tests/test_kalshi_path_defaults.py`
- `make kalshi-source-repo-inventory`
- `make kalshi-external-artifact-preflight`

Result: focused tests pass; Ruff clean; inventory/preflight targets exit `0`.
