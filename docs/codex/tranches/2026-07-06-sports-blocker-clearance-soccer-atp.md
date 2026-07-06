# 2026-07-06 Sports Blocker Clearance: Soccer Provider Proof + ATP Market Compatibility

## North Star Alignment

This tranche keeps the sports stack pointed at timestamp-matched sharp no-vig
consensus as the sports model surface, while preserving the hard gates:
exact Kalshi mapping, OOS/FDR, cost/spread replay, capacity/depth,
correlation control, decay survival, paper-only promotion, and live block.

No projection model was introduced. No threshold was lowered. No provider row
or donor row was promoted to a tradable probability.

## What Cleared

- Added a first-class soccer Asian-sharp provider diagnostic:
  `make kalshi-sports-consensus-soccer-asian-provider-diagnostic`.
- Wired the diagnostic into provider audit and the sports evidence-cycle report.
- Ran a bounded current probe at `2026-07-06T00:30:16Z` for `sbobet`,
  `singbet`, and `ibc`.
- Observed target provider rows: `0`.
- Missing target providers: `ibc`, `sbobet`, `singbet`.
- Observed non-target sharp/exchange providers: `pinnacle`,
  `betfair_exchange`, `matchbook`, `smarkets`.

Result: the World Cup/soccer provider blocker is no longer ambiguous repo
wiring. It is an external legal-feed availability blocker. Stop before
downgrading or bypassing the soccer Asian-sharp maturity rule.

## ATP Fix

Current Kalshi ATP inventory is set-winner contracts:

- `36` current `KXATPSETWINNER` rows.
- `0` current compatible `KXATPMATCH` rows.

The available sharp feed is tennis match-winner `h2h`. It cannot be mapped onto
set-winner contracts without introducing a separate set-probability model, which
would violate the current sports-consensus doctrine.

Changed:

- `scripts/kalshi_sports_consensus_atp_donor_adapter.py` now preserves the
  conversion reason and reports
  `sports_consensus_atp_donor_adapter_blocked_no_compatible_atp_match_markets`
  instead of generic `sports_consensus_atp_donor_adapter_blocked_no_atp_rows`
  when all current h2h rows fail because no exact `KXATPMATCH` event exists.
- `predmarket/sports_consensus_provider_policy.py` now supports
  `deferred_no_compatible_current_market`.
- `scripts/kalshi_sports_consensus_provider_audit.py` auto-detects the latest
  ATP adapter status and excludes tennis from actionable provider-gap counts
  when the blocker is incompatible current Kalshi contract type.

Latest provider audit:

- Covered: `mlb`, `nfl`.
- Deferred: `tennis`, `nba`.
- Actionable provider gap: `soccer`.

## Current Evidence State

- Sports consensus falsification:
  `sports_consensus_falsification_blocked_no_testable_hypotheses`.
- Joined labels: `185`.
- Max hypothesis OOS count: `5/10`.
- Nearest pre-registered hypothesis OOS deficit: `5`.
- FDR survivors: `0`.
- Passive liquidity paper-fill falsification: `3` tested hypotheses,
  `0` FDR survivors, `1475` valid paper-fill labels, best candidate net EV
  `-0.0277421875`.
- Paper decisions: `11` usable rows, `$1679.517429` paper stake.
- Live: `kalshi_live_blocked`, `0` eligible rows.

## Verification

- `make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1`
- `make kalshi-sports-consensus-atp-donor-adapter KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE=1`
- `make kalshi-sports-consensus-provider-audit`
- `make kalshi-sports-evidence-cycle-report`
- Focused tests:
  `PYTHONPATH=. .venv/bin/pytest -s tests/test_kalshi_sports_consensus_atp_adapter.py tests/test_kalshi_sports_consensus_provider_policy.py tests/test_kalshi_sports_consensus_soccer_asian_provider.py tests/test_kalshi_sports_evidence_cycle_report.py -q`
  -> `29 passed`.
- `make test-unit` -> `1342 passed / 15 deselected`.
- `make test-integration` -> `14 passed`.
- `make lint-baseline-check` -> `lint 98/1422`, `format 12/94`.
- `make quality` -> exits `0` with the existing advisory Ruff/deptry backlog.
- Touched-file Ruff clean.
- `git diff --check` -> exits `0` with only the existing Makefile CRLF warning.

## Remaining Blockers

- Source: legal soccer Asian-sharp feed with actual `sbobet`, `singbet`, or
  `ibc` rows.
- Evidence: more exact Kalshi settlement labels in the pre-registered sports
  consensus hypothesis cells.
- Passive liquidity: no FDR survivor despite paper-fill evidence.
- Live: still correctly blocked until upstream evidence produces eligible rows.
