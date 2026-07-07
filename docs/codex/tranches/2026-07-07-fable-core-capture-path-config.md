# 2026-07-07 Fable Core Capture Path Config

## Landing

Removed machine-specific local roots from the core capture/reference surfaces that feed sports evidence acquisition:

- `predmarket/kalshi_universe_scan.py`
- `predmarket/kalshi_manual_drop_capture.py`
- `predmarket/sports_consensus_reference_builder.py`
- `predmarket/type2_candidate_disposition.py`
- `predmarket/type2_reference_builder.py`
- `scripts/kalshi_paper_settlement_reconcile.py`
- `scripts/kalshi_near_resolution_flow_terms_capture.py`
- `scripts/kalshi_ghost_listing_depth_diagnostic.py`

Defaults now derive manual-drop locations from `manual_drop_path()`. Existing CLI overrides and Make targets are unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py -q` -> `11 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check ...` over touched files -> `All checks passed`
- Hardcoded root scan over touched runtime files found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- Make dry-runs passed for:
  - `kalshi-universe-scan`
  - `kalshi-manual-drop-capture`
  - `kalshi-sports-consensus-reference-build`
  - `type2-reference-build`
  - `type2-candidate-disposition`
  - `kalshi-paper-settlement-reconcile`
  - `kalshi-near-resolution-flow-terms-capture`
  - `kalshi-ghost-listing-depth-diagnostic`
- `git diff --check` clean for touched files.
