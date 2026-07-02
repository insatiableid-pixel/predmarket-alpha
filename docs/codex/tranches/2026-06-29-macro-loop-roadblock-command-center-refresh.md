# Macro Loop Roadblock: Command Center Refresh

Date: 2026-06-29

## Scope

Ran the macro loop until a real blocker was confirmed. Work stayed in the command center except for read-only macro status aggregation.

## Commands Run

- `make macro-route`
- `make macro-unlock-scout`
- `make type2-reference-build`
- `make type2-reference-preflight TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`
- `make type2-paper-matcher TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`
- `make type2-candidate-disposition`

## Result

The predmarket local sportsbook reference is structurally valid but still not usable for review promotion:

- reference builder: `reference_built_with_warnings`
- reference rows: 42
- duplicate tickers: 0
- max event match delta: 60 seconds
- skipped events: 1
- preflight: `reference_ready`
- valid explicit mappings: 42/42
- paper matcher: `review_candidates_present`
- pass/watch: 2 / 40
- disposition: `candidate_disposition_all_passes_downgraded`
- kept timing-safe review candidates: 0
- downgraded temporal mismatches: 6
- manual timing unknown: 0

The two pass-level rows were San Diego/Texas moneyline candidates captured after first pitch:

- sportsbook capture: `2026-06-20T22:59:34Z`
- Kalshi capture: `2026-06-20T23:02:03Z`
- event start: `2026-06-20T20:06:00Z`

## Roadblock

No local-only command can turn the current predmarket reference into timing-safe evidence. The blocker is a new timing-safe mapped sportsbook reference captured before event start.

## Macro State

Fresh macro route remains parked:

- recommended repo: `predmarket-alpha`
- all lanes parked: true
- predmarket unlock: timing-safe mapped sportsbook reference
- MLB unlock: new contract-safe clean packet or settled/closing-line validation

## Safety

- provider/API calls: false
- paid calls: false
- database writes: false
- account/order paths: false
- market execution: false
- raw provider payload copied into repo: false
