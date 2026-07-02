# 2026-06-29 Late Pregame Refresh And Clean No-Signal

Codex ran the late same-slate refresh and propagated the result through the
macro command center.

Predmarket result:

- Odds raw: `/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260629T224907Z.json`
- Kalshi raw: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260629T224907Z.json`
- Reference rows: 52
- Preflight: `reference_ready`
- Disposition: `candidate_disposition_watch_only`
- Threshold sensitivity: 0 candidates at threshold 0.1000; max positive net
  divergence 0.0161.

MLB result:

- Clean subset intake: `/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/2026-06-29-late-current-clean-subset-intake/`
- Readiness: `pregame_pair_ready`
- Candidate rows: 264
- Review-ready rows: 0
- Latest ledger: `repeatability_no_signal_clean_packets`

Macro result:

- `make macro-route` reports `all_lanes_parked=true`.
- MLB status is now `primary_type2_repeatability_no_signal_clean_packets`.
- Predmarket remains `kalshi_type2_candidate_disposition_watch_only`.

Next useful unlock: explicit threshold-policy review, a new clean calendar
slate, settled-outcome evidence, or closing-line validation.
