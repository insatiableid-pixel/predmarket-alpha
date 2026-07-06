# World Cup Sports Discovery Soft Watch

Date: 2026-07-03

## Objective

Follow the sports-first market-structure advice by making current World Cup and
FIFA soccer markets visible to the Kalshi universe scanner, without promoting
them to model-routed, paper, or live tradable rows.

## Changes

- Added a bounded set of focused public series fetches for current World Cup
  and FIFA soccer markets:
  `KXWCGAME`, `KXWCSPREAD`, `KXWCTOTAL`, `KXWCBTTS`, first-half/second-half
  lines, team H2H/goals/shots/corners, and `KXFIFA*` game/spread/total lines.
- Classified these markets as `other_sports`, not MLB/ATP/NFL/NBA, so they
  route to `soft_market_research_backlog` until a real soccer probability
  engine exists.
- Expanded soft sports classification text to catch World Cup/FIFA/UEFA/UCL/EPL
  language when series metadata is present.
- Added tests proving World Cup game markets are fetched, classified as
  `other_sports`, remain `usable=false`, and carry no calibrated probability.

## Latest Artifact

`make kalshi-universe-scan` now lands current non-core sports inventory:

- Total candidates: `5,108`
- Model-routed candidates: `912`
- Soft-watch candidates: `4,196`
- MLB: `840`
- ATP: `72`
- Other sports: `81`

Observed `other_sports` series include World Cup game, first-half totals,
second-half spreads, BTTS, and cricket T20 rows. Every row remains research-only.

## Downstream Safety

- `make kalshi-ev-ledger` refreshed the ledger.
- `make kalshi-paper-decision-candidates` still reports
  `paper_decision_candidates_ready_all_rows_blocked`.
- `make kalshi-live-preflight` still reports `kalshi_live_blocked`.
- Latest paper/live counts: `388` paper candidates, `388` blocked, `$0` paper
  stake, `0` live-eligible, `$0` live stake.

## Verification

- `.venv/bin/python -m pytest -s tests/test_kalshi_universe_scan.py -q` -> 13 passed
- `make test-unit` -> 666 passed, 14 deselected
- `make test-integration` -> 14 passed
- `make lint-baseline-check`, `make tech-debt-check`, `make file-sizes-check`,
  `make modularize` -> pass
- `make kalshi-universe-scan`, `make kalshi-ev-ledger`,
  `make kalshi-paper-decision-candidates`, `make kalshi-live-preflight` -> pass

## Guardrails

- No soccer probability model was invented.
- No threshold was lowered.
- No paper stake, live stake, order, account, or execution path was enabled.
