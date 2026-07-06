# Sharp MLB Consensus Provider Promotion

Date: 2026-07-04

## Objective

Continue implementing Claude's sports advice: for sports, timestamp-matched sharp no-vig consensus is the model. The previous production MLB consensus feed was secondary-only (`lowvig`, `betonlineag`), while ATP/tennis carried the only strict anchor coverage. This tranche promotes MLB to the strict sharp/exchange consensus lane without lowering any falsification, label, paper, or live gates.

## Landing

- Fixed `predmarket/sports_consensus_provider_policy.py` so nested raw The Odds API bookmaker rows inherit parent `sport_key` and market context. Raw provider captures can now prove sport-specific sharp-provider availability instead of being counted only as global provider noise.
- Added bookmaker-targeted current capture support to `predmarket/sports_consensus_reference_builder.py` and `scripts/kalshi_sports_consensus_reference_build.py`.
- Added `make kalshi-sports-consensus-sharp-provider-capture`, a probe-only target that requests the configured sharp book set across target sports and writes its derived reference to `/home/mrwatson/manual_drops/predmarket/sports-sharp-provider-probe-consensus.json` instead of the production consensus feed.
- Upgraded the production MLB consensus defaults from secondary books to the sharp/exchange set:
  - `pinnacle`
  - `betfair_ex_uk`
  - `matchbook`
  - `smarkets`
- Preserved the ATP donor strict consensus adapter and the exact Kalshi ticker preflight.

## Current Evidence

`make kalshi-sports-consensus-sharp-provider-capture` exits `0` and writes a probe report with:

- Status: `sports_consensus_reference_built_with_warnings`
- Reference rows: `92`
- Unique exact Kalshi tickers: `32`
- Distinct books: `4`

`make kalshi-sports-consensus-refresh` exits `0` with:

- Production MLB strict reference rows: `90`
- ATP strict donor rows after adapter: `44`
- Combined strict reference rows: `134`
- Combined exact Kalshi tickers: `46`
- Consensus preflight status: `sports_consensus_preflight_ready`
- Valid candidates: `46`
- Blockers: `0`
- Distinct books: `5`

`make kalshi-sports-consensus-provider-audit` now reports:

- Status: `sports_consensus_provider_audit_ready_with_per_sport_gaps`
- Covered sports: `mlb`, `tennis`
- Covered count: `2/5`
- Remaining gaps: `soccer`, `nfl`, `nba`
- MLB strict providers: `betfair_exchange`, `matchbook`, `pinnacle`, `smarkets`
- MLB strict anchor providers: `pinnacle`

The downstream statistical state remains correctly blocked:

- Consensus observations: `194`
- Joined labels: `16`
- Independent labels: `8`
- OOS labels: `3`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Paper usable rows: `0`
- Live eligible rows: `0`

## Verification

- Focused tests: `41 passed`
- Touched-file Ruff check passed
- `make kalshi-sports-consensus-sharp-provider-capture` exits `0`
- `make kalshi-sports-consensus-refresh` exits `0`
- `make kalshi-sports-consensus-observation-loop KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED=1` exits `0`
- `make kalshi-sports-consensus-provider-audit` exits `0`
- `make kalshi-sports-consensus-falsification` exits `0`
- `make kalshi-sports-evidence-cycle-report` exits `0`
- `make kalshi-always-on-collector-once` exits `0`
- `make test-unit` exits `0`: `1281 passed`, `15 deselected`
- `make quality` exits `0` with existing advisory Ruff/deptry backlog
- `make lint-baseline-check` exits `0`: `lint 100/1422`, `format 8/94`

## Guardrails

- No live execution.
- No account/order paths.
- No threshold lowering.
- No paper stake from provider coverage alone.
- No production use of the probe-only all-sport reference file.
- Raw provider payloads remain outside the repository under `/home/mrwatson/manual_drops/odds_api/`.

## Remaining Work

- Soccer remains blocked on missing Asian sharp reference (`SBOBet`, `Singbet`, `IBC`, or an equivalent legal timestamped strict source).
- NFL has raw Pinnacle availability but no strict consensus wrapper / exact Kalshi mapping in the production feed yet.
- NBA has no current raw provider events in the latest capture, consistent with offseason/thin current market availability.
- Consensus labels are still insufficient for OOS/FDR. Keep the collector running until the lane reaches at least `30` independent labels and `10` OOS labels, then let the falsification ledger decide.
