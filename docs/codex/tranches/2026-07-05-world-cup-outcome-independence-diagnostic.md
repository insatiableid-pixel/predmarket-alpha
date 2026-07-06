# World Cup Outcome-Independence Diagnostic

## Purpose

Continue implementing Claude's sports advice: resolve the World Cup independence definition before treating same-match soccer markets as additional evidence. The specific trap is counting many exact Kalshi contracts from the same match as independent labels while also failing to cluster the resulting portfolio risk by match.

## What Landed

- Added `scripts/kalshi_world_cup_outcome_independence_diagnostic.py`.
- Added `tests/test_kalshi_world_cup_outcome_independence_diagnostic.py`.
- Added `make kalshi-world-cup-outcome-independence-diagnostic`.
- Wired the diagnostic into `make kalshi-world-cup-proxy-observation-watch-once`.
- Wired the diagnostic into sports event velocity and sports evidence cycle.

The diagnostic separates four evidence units:

- `exact_contract_ticker`
- `event_ticker`
- `match_key|outcome_family`
- `match_key`

It keeps the critical correlation rule explicit: totals, BTTS, spreads, halves, and match-winner markets may be distinct hypothesis clocks, but all outcomes from the same match share the `world_cup_match` portfolio correlation cluster.

## Real Refreshed State

- Diagnostic status: `world_cup_outcome_independence_diagnostic_ready_candidate_independence_review`
- Exact-contract labels: `93`
- Event-market labels: `25`
- Match/outcome-family clocks: `23`
- Match correlation clusters: `3`
- Outcome-family label deficit: `7`
- Current World Cup research candidates: `2`
- Candidate independence review required: `true`

The previous exact-contract count was enough for the World Cup proxy falsification artifact to surface research candidates. Under the stricter match/outcome-family diagnostic, the family is not yet independently cleared for downstream EV/paper promotion.

## Event Velocity Change

`make kalshi-sports-event-velocity-eta` now consumes the diagnostic. The World Cup proxy row is no longer reported as simply label-threshold-met. It is now:

- Surface: `world_cup_proxy_directional`
- Bottleneck: `independence_definition_review`
- ETA status: `blocked_world_cup_independence_review`
- Independent labels: `23`
- Min independent labels: `30`
- Label deficit: `7`
- OOS deficit: `10`
- Portfolio cluster unit: `world_cup_match`

The refreshed ETA artifact now has `10/10` safe inputs, `10` label/OOS-blocked surfaces, `1` paper-fill-blocked surface, and a first-class `independence_definition_review` bottleneck type.

The refreshed sports evidence cycle now has `28/28` safe artifacts and surfaces:

- World Cup outcome independence: `world_cup_outcome_independence_diagnostic_ready_candidate_independence_review`
- World Cup exact-contract labels: `93`
- World Cup outcome-family clocks: `23`
- World Cup match clusters: `3`
- World Cup candidate independence review: `true`
- Live eligible: `0`

## Safety

- Research-only: `true`
- Execution enabled: `false`
- Market execution: `false`
- Account/order paths: `false`
- No calibrated probability, EV, paper stake, live eligibility, or orders emitted.
- No thresholds lowered.
- No existing World Cup falsification behavior silently changed.

## Verification

- Focused World Cup/ETA/cycle tests: `11 passed`
- Touched-file Ruff check: clean
- Touched-file Ruff format check: clean
- Py-compile: clean
- `make kalshi-world-cup-outcome-independence-diagnostic`: exits `0`
- `make kalshi-sports-event-velocity-eta`: exits `0`
- `make kalshi-sports-evidence-cycle-report`: exits `0`
- `make kalshi-signal-factory-status`: exits `0`
- `make test-unit`: `1309 passed / 15 deselected`
- `make test-integration`: `14 passed`
- `make lint-baseline-check`: exits `0` (`lint 100/1422`, `format 8/94`)
- `make quality`: exits `0` with the existing advisory Ruff/deptry backlog
- `git diff --check`: exits `0` with only existing CRLF warnings

## Next

The next highest-value Claude gap is still evidence accumulation, not new modeling:

1. Keep collecting exact sports consensus labels until OOS/FDR can test Kalshi-vs-sharp-consensus divergence.
2. Add NBA strict consensus only when there are current mappable Kalshi NBA markets.
3. Enrich soccer with Asian sharp sources if legally/source-access clean.
4. Keep passive liquidity accumulating real maker paper fills; proxy labels still do not count.
