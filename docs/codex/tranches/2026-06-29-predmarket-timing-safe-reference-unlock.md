# Predmarket Timing-Safe Reference Unlock

Date: 2026-06-29

## Scope

Solved the predmarket timing-safe sportsbook reference blocker with one bounded current sportsbook capture and one bounded Kalshi capture, then ran the local reference/matcher/disposition chain.

## Captures

- sportsbook raw: `/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260629T033913Z.json`
- sportsbook meta: `/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260629T033913Z.meta.json`
- Kalshi raw: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260629T033913Z.json`
- Kalshi report: `docs/codex/artifacts/kalshi-manual-drop-capture-20260629T033913Z/kalshi-manual-drop-capture-20260629T033913Z.json`

The sportsbook capture returned 13 events, status 200, and quota headers showing 3 credits used for this request. Raw provider payloads stayed outside repos.

## Derived Evidence

- reference builder: `reference_built_with_warnings`
- mapped rows: 24
- duplicate ticker mappings: 0
- max event match delta: 60 seconds
- skipped events: 1
- preflight: `reference_ready`
- valid mappings: 24/24
- matcher: `watch_only_no_review_candidates`
- disposition: `candidate_disposition_watch_only`
- kept review candidates: 0
- watch-only candidates: 24
- temporal downgrades: 0
- manual timing unknown: 0

## Decision

The timing-safe reference blocker is solved. The new blocker is evidence strength: no candidate cleared the review threshold.

## Macro State

- predmarket status: `kalshi_type2_candidate_disposition_watch_only`
- macro route: all lanes parked
- predmarket unlock: wait for a new timing-safe reference/slate with a review-threshold candidate, or an explicit threshold-study directive

## Safety

- provider/API calls: one bounded current sportsbook request, explicitly needed to solve the blocker
- paid historical calls: false
- database writes: false
- account/order paths: false
- market execution: false
- raw provider payload copied into repo: false
- tradable/profitability claim: false
