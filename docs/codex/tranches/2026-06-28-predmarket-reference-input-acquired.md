# Predmarket Reference Input Acquired

Date: 2026-06-28

## Summary

Converted the existing local June 20 MLB Odds API drop plus the matching local Kalshi MLB game-series snapshot into a small derived sportsbook reference file outside the repo.

## Input Created

- `/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference-20260620-mlb-game-winners.json`
- `/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`

The file contains 42 explicit `kalshi_ticker` mappings for MLB game-winner markets. It is a derived review-only reference, not a raw provider payload.

## Verification

- `make type2-reference-preflight TYPE2_KALSHI_JSON=data/kalshi_mlb_game_series_live_current_20260620T230203Z.json TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`
  - Status: `reference_ready`
  - Valid references: 42/42
  - Blockers: 0
- `make type2-paper-matcher TYPE2_KALSHI_JSON=data/kalshi_mlb_game_series_live_current_20260620T230203Z.json TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`
  - Status: `review_candidates_present`
  - Candidates: 42
  - Review-only pass/watch/blocked: 8/34/0
- `make macro-status`
  - Status: `kalshi_type2_reference_preflight_ready`
  - Execution enabled: false
  - Live calls allowed: false
- `python3 scripts/codex_macro_router.py route --write`
  - `all_lanes_parked=false`
  - Recommended repo: `predmarket-alpha`

## Guardrail

This only removes the missing-input blocker. It does not make any trading recommendation, execution claim, account action, order path, stake, size, or bankroll decision.
