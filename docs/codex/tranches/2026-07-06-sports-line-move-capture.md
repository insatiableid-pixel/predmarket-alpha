# 2026-07-06 Sports Line-Move Capture

## Summary

Started the Fable-directed stale-quote evidence clock with a narrow tranche. This adds a capture-only sharp sportsbook line-move logger for current sports markets. It records only quote deltas to append-only JSONL outside the repo and writes safety/provenance metadata into the existing macro artifact pattern.

## Landed

- Added `scripts/kalshi_sports_line_move_delta_logger.py`.
- Added `make kalshi-sports-line-move-delta-logger`.
- Added focused tests in `tests/test_kalshi_sports_line_move_delta_logger.py`.
- Default sport coverage: `baseball_mlb`, `tennis_atp_wimbledon`, `soccer_fifa_world_cup`, `americanfootball_nfl`.
- Generic `tennis_atp` safely falls back to `tennis_atp_wimbledon`.
- Provider snapshot metadata is retained in the artifact; raw sportsbook payloads are not copied into the repo.

## Real Evidence

- Status: `kalshi_sports_line_move_delta_logger_ready_with_deltas`
- Delta JSONL: `/home/mrwatson/manual_drops/kalshi_sports_line_moves/sports_line_move_deltas_20260706.jsonl`
- Delta JSONL sha256: `b331c748335ac5167094c40af329b8a3c4134ba2f4c973bc865827cbf82231c6`
- Provider snapshots: `4`
- Events fetched: `104` (`20` MLB, `4` Wimbledon, `5` World Cup, `75` NFL)
- Delta rows: `45`
- Line moves: `41`
- Provider errors: `0`

## Guardrails

- Capture-only: no signal fitting, probability generation, EV, paper stake, live execution, account access, or order path.
- No sportsbook labels are used as settlement labels.
- No thresholds were lowered.
