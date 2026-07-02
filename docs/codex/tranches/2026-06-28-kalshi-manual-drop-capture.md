# Kalshi Manual Drop Capture

Date: 2026-06-28
Repo: `/home/mrwatson/projects/predmarket-alpha`
Mode: research-only market-data capture

## What Changed

- Added `predmarket/kalshi_manual_drop_capture.py`.
- Added `make kalshi-manual-drop-capture`.
- Added focused tests in `tests/test_kalshi_manual_drop_capture.py`.
- Tightened `scripts/codex_macro_unlock_scout.py` so MLB is only treated as unblocked when the latest pregame intake is actually ready, not merely because local odds and Kalshi files exist.

## Captured Kalshi Evidence

- Snapshot: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260629T001744Z.json`
- Latest pointer: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_latest.json`
- In-repo report: `docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.json`

Summary:

- Markets captured: 376
- Series errors: 0
- KXMLBGAME: 76
- KXMLBTOTAL: 100
- KXMLBSPREAD: 60
- KXMLBF5: 30
- KXMLBF5TOTAL: 70
- KXMLBF5SPREAD: 40

## Pairing Check

The captured Kalshi file was checked against the existing local sportsbook drop through MLB's no-provider intake runner:

- Intake report: `/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/2026-06-28-kalshi-manual-drop-intake-check/pregame-drop-intake-status.json`
- Status: `blocked_invalid_operator_drop`
- Ready: `false`
- Candidate rows: 0

Plain English: the Kalshi side is now available. The sportsbook side is stale and not a valid same-slate pair for this Kalshi capture.

## Safety

- Research only: true
- Execution enabled: false
- Market-data calls: true
- Account/order paths: false
- Market execution: false
- Database writes: false
- Paid calls: false
- Raw secrets copied: false

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_manual_drop_capture.py tests/test_codex_macro_unlock_scout.py -q` -> 7 passed
- `.venv/bin/ruff check predmarket/kalshi_manual_drop_capture.py scripts/codex_macro_unlock_scout.py tests/test_kalshi_manual_drop_capture.py tests/test_codex_macro_unlock_scout.py` -> passed
- `make macro-unlock-scout` -> refreshed, MLB remains blocked on invalid local pair
- `make macro-route` -> all lanes parked, predmarket command center remains recommended

## Next Bottleneck

Get a current same-slate sportsbook pregame snapshot that pairs with the fresh Kalshi file, or capture both sides again before first pitch for the same slate. Do not continue Type 2 edge review from the stale June 20 sportsbook file.
