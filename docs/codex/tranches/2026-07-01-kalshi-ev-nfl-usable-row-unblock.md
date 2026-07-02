# 2026-07-01 Kalshi EV NFL Usable Row Unblock

## Summary

The blocked macro goal was unblocked by obtaining a bounded public Kalshi NFL game-market snapshot, hardening local contract matching, assembling one safe NFL overlay pair outside the repo, and regenerating the federated Kalshi EV ledger.

The ledger now has one usable research-only row:

- Contract: `KXNFLGAME-26SEP13ARILAC-ARI`
- Side: `yes`
- Selection: `ARI`
- Executable price: `0.19`
- Estimated taker fee: `0.0108`
- All-in break-even: `0.2008`
- Calibrated probability: `0.2081959141556554`
- Margin: `0.007395914155655381`
- Gate status: `pass`
- Research-only: `true`
- Execution enabled: `false`

This is not a bet recommendation, staking plan, execution instruction, or tradable claim.

## Inputs

- Public Kalshi market-data capture for `KXNFLGAME`
- Raw latest snapshot outside the repo: `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json`
- Timestamped raw snapshot outside the repo: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json`
- Capture report in repo: `docs/codex/artifacts/kalshi-nfl-manual-drop-capture-latest/kalshi-nfl-manual-drop-capture-latest.json`

The timestamped file keeps the legacy `kalshi_mlb_game_series_` prefix from the generic capture helper, but the content is `KXNFLGAME`.

## Code Changes

- `scripts/kalshi_ev_local_contract_evidence_scout.py`
  - Derives `pregame_clean` only when a source capture time exists and a future expiration/close time is at least six hours away.
  - Requires the selected team side to match the exact contract ticker suffix or `yes_sub_title`, preventing wrong-side event matches.
- `scripts/kalshi_ev_nfl_overlay_assembler.py`
  - Writes stable overlay filenames keyed by assembled contract set so reruns do not create duplicate overlay files.
- `scripts/kalshi_contract_ev_ledger.py`
  - Deduplicates contract-mapping overlays by `source_repo_id + contract_ticker + side`.
- `tests/test_kalshi_ev_local_contract_evidence_scout.py`
  - Added future-snapshot timing derivation coverage.
  - Added wrong-contract-side rejection coverage.
- `tests/test_kalshi_ev_nfl_overlay_assembler.py`
  - Added idempotent overlay rewrite coverage.
- `tests/test_kalshi_contract_ev_ledger.py`
  - Added duplicate mapping overlay dedupe coverage and updated current-state assertions for the usable NFL row.

## Outputs

- `docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json`
- `docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json`
- `docs/codex/macro/latest-kalshi-ev-overlay-preflight.json`
- `docs/codex/macro/latest-kalshi-contract-ev-ledger.json`
- `docs/codex/macro/latest-decision.json`
- `docs/codex/macro/latest-unlock-scout.json`
- `docs/codex/macro/latest-macro-blocker-audit.json`

## Verification

- `PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_manual_drop_capture --series-tickers KXNFLGAME ...`
- `make kalshi-ev-local-contract-evidence-scout`
- `make kalshi-ev-nfl-overlay-assembler`
- `make kalshi-ev-overlay-preflight`
- `make kalshi-ev-ledger`
- `make macro-route`
- `make macro-unlock-scout`
- `make macro-blocker-audit`
- `make macro-status`
- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_execution_cost.py tests/test_kalshi_contract_ev_ledger.py tests/test_kalshi_ev_local_contract_evidence_scout.py tests/test_kalshi_ev_nfl_overlay_assembler.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py tests/test_codex_macro_blocker_audit.py` -> 107 passed
- `ruff check` on touched scripts/tests -> all checks passed

## Result

The previous all-lanes blocker is no longer true. Predmarket now emits a usable fee-aware calibrated Kalshi EV row with verified official terms and clean timing. The macro blocker audit correctly reports `macro_blocker_audit_incomplete` because not every lane is blocked anymore.
