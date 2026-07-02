# Federated Market Edge Operating System Plan

Date: 2026-06-16

## Active Universe

This operation covers exactly five repositories:

- `/home/mrwatson/projects/predmarket-alpha`
- `/home/mrwatson/projects/mlb-platform`
- `/home/mrwatson/projects/atp-oracle`
- `/home/mrwatson/projects/nba-analytics-platform`
- `/home/mrwatson/projects/nfl_quant_glm51_greenfield`

The repos stay separate. `predmarket-alpha` is the macro command center because it has the fastest paper-evidence loop and already contains the Kalshi strategy memo. No fourth repo and no shared package extraction in phase 1.

## Strategic Read

The Kalshi strategy memo makes Type 2 sports props the operating spine: compare a market-implied no-vig probability against Kalshi, require a large edge threshold after fees/spread/friction, and keep everything paper/replay-only until evidence is durable. That changes the priority order:

1. `mlb-platform` is the highest-leverage Type 2 implementation source because it already has odds, implied probability, CLV, Kelly, backtest, source-preflight, and operator gates.
2. `predmarket-alpha` remains the command center and Kalshi paper ledger. It should receive frequent short sessions to keep router, artifacts, and Kalshi evidence coherent.
3. `atp-oracle` is a high-upside tennis Type 2 candidate, but promotion is blocked by model-quality and external evidence gaps.
4. `nba-analytics-platform` has major upside, but first work is stabilization only: dirty-tree classification, T21 completion note, and preservation of the passing platform consistency state.
5. `nfl_quant_glm51_greenfield` is the governance exemplar. Its job is to export status, validation ledger, artifact audit, and profile-validation patterns into the macro contract.

## Phase 1 Contract

Every repo exposes:

```bash
make macro-status
```

Default behavior:

- JSON only on stdout.
- Read-only filesystem behavior.
- No live/API/provider calls.
- No market execution.
- No database writes.
- No paid historical calls.
- No repo package imports required for the macro adapter.

The contract is `MacroRepoStatusV1`, stored in `docs/codex/macro/status.schema.json`.

## Scheduler Doctrine

The router computes:

```text
priority = 3*architecture_leverage + 2*evidence_delta + 2*edge_feedback_speed + blocker_criticality - dirty_risk - live_data_risk - verification_cost
```

One Codex session touches one repo unless the task is strictly macro-status aggregation.

Stop on the first failed gate, stale artifact, unexpected live-call requirement, unsupported betting/execution claim, or dirty-state surprise that changes the risk class.

## First Coding Tranches

1. Macro contract and router:
   - Add `active-universe.json`, `status.schema.json`, this plan, and `scripts/codex_macro_router.py`.
   - Add `make macro-status` to all five repos.
   - Router writes `latest-status.json`, `latest-decision.json`, and `latest-decision.md` when invoked with `route --write`.

2. MLB Type 2 adapter:
   - Surface existing odds, implied probability, edge, Kelly, CLV, backtest, source-preflight, and operator-readiness modules.
   - Treat live data quality/source freshness as a gate, not a green light.
   - Do not execute provider or market paths.

3. Predmarket command center:
   - Hash and summarize the Kalshi strategy memo plus current June 16 Kalshi paper artifacts.
   - Keep `REVIEW_READY` as review-only, never tradable.
   - Use this repo for router hardening and compact session-state updates.

4. ATP tennis adapter:
   - Surface 93/100 vision state, G1/G2 model-quality blockers, and external evidence gaps.
   - Keep promotion blocked until tennis validation and commercial/source proof clear.

5. NBA stabilization adapter:
   - Read existing annex JSON artifacts only.
   - Surface `macro_partial_truth_gated`, 13 blockers, 14 claims, 6 ready, 8 blocked, T21 counts, and dirty-tree risk.
   - Add or verify the T21 completion note before any resolver/model work.

6. NFL governance adapter:
   - Surface offline status availability, artifact audit, validation ledger/profile-validation evidence, and current dirty-tree risk.
   - Treat NFL as validation-pattern source, not as a new betting-feature target.

## Acceptance

- `make macro-status` succeeds in all five repos without network, execution, provider calls, or data mutation.
- The router recommends exactly one next tranche with a clear stop condition.
- Macro outputs are readable by a future Codex session before choosing any repo-specific work.
- Phase 1 remains research/paper-only.

## 2026-06-29 Plan Update

The Kalshi half of the MLB Type 2 pair is no longer missing: `predmarket-alpha`
captured a fresh research-only Kalshi MLB game-series snapshot with 376 markets
and 0 series errors. The old June 20 sportsbook file does not pair with it, so
the current blocker is specifically a fresh same-slate sportsbook snapshot.

Highest-leverage next tranche:

1. Work in `mlb-platform`, because the blocker is now the sportsbook side of
   the Type 2 evidence pair.
2. Add a guarded current sportsbook capture command that makes one bounded
   `baseball_mlb` current-odds request only when explicitly invoked, reads the
   local key without printing it, and writes raw payload plus sidecar outside
   the repo under `/home/mrwatson/manual_drops/odds_api/`.
3. Immediately run the existing no-provider `type2-pregame-drop-intake` against
   the new sportsbook snapshot and the fresh Kalshi snapshot.
4. If the pair is still not ready, record the exact machine-readable reason
   instead of coding against invented evidence.

This is still review-only. It does not touch account, order, execution,
database-write, staking, sizing, bankroll, or paid historical paths.

## 2026-06-29 Review-Adjudication Update

The first clean MLB same-slate pregame Type 2 packet has now cleared review
adjudication:

- bundle: `/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/2026-06-29-current-pregame-subset-intake/`
- status: `review_adjudication_ready`
- review-ready rows: 58
- review-ready clusters: 8
- cluster shape: full-game run line, away `+1.5`
- adjudication gates: 9 pass, 0 warn, 0 blocked, 0 fail
- provider/API calls during adjudication: false
- market execution/account/order paths: false

The operating question has moved from "can we form a clean pair?" to "does the
measured cluster pattern repeat across clean pregame pairs?" The next highest
leverage MLB tranche is therefore a repeatability ledger, not a new model:

1. Append each clean `review-adjudication.json` to a compact derived ledger.
2. Group by stable game/market/selection/line descriptors and preserve book
   depth, exchange spread, sportsbook probability range, and measured net
   difference summary.
3. Define a minimum repeated-clean-snapshot evidence rule before making any
   stronger research claim.
4. Park promotion until at least one additional same-slate pregame pair clears
   the same intake and adjudication gates.

This remains research-only. Do not make another provider call unless a future
directive explicitly authorizes it.

## 2026-06-29 Repeatability Update

The second authorized current MLB capture completed and produced a second clean
pregame Type 2 packet:

- first clean bundle: `2026-06-29-current-pregame-subset-intake`
- second clean bundle: `2026-06-29-second-current-pregame-subset-intake`
- latest ledger: `type2-repeatability-ledger-latest/type2-repeatability-ledger.json`
- ledger status: `repeatability_observed_two_clean_packets`
- clean packets: 2
- cluster rows: 18
- repeated descriptor shapes: 2
- three-packet recurring descriptors: 0

The operating question has moved again: the system has observed the same kind
of run-line disagreement shape across two clean packets, but the three-packet
research-review threshold is not met. MLB is therefore parked until the user
explicitly authorizes another bounded current capture or supplies another clean
same-slate pregame pair.

Current macro posture:

1. Predmarket is command center for blocker collection.
2. MLB is parked at `primary_type2_repeatability_observed`.
3. ATP remains blocked on G1/G2 model-quality evidence plus D3/G5/P5 external proof.
4. NBA remains parked at shrinkage/clipped residual market parity until new source-backed signal/data exists.
5. NFL governance snapshots are fresh; no new NFL feature work is routed.

Do not make another provider call by default.

## 2026-06-29 Late Pregame Clean No-Signal Update

The next valuable question was whether a later same-slate capture would reveal
any corrected, timing-clean Type 2 signal at the existing review threshold.
It did not.

Predmarket late refresh:

- sportsbook raw: `/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260629T224907Z.json`
- Kalshi raw: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260629T224907Z.json`
- reference rows: 52
- preflight: `reference_ready`
- candidate disposition: `candidate_disposition_watch_only`
- threshold sensitivity: 48 timing-clean candidates, 27 positive-net rows, max
  positive review-only net divergence 0.0161, 0 rows at the 0.1000 threshold

MLB clean-subset salvage:

- unfiltered intake: 487 candidates, 8 threshold rows, blocked by started games
  and unverified tolerance matches
- clean subset report: `/home/mrwatson/manual_drops/mlb_type2_clean_subsets/2026-06-29-late-current-clean-subset/2026-06-29-late-current-clean-subset_clean_subset_report.json`
- clean subset kept 14 games and removed 13 game ids
- clean subset intake: `docs/codex/artifacts/2026-06-29-late-current-clean-subset-intake/`
- clean subset result: `ready_pregame_pair`, 264 candidates, 0 review-ready
  rows, 0 temporal suspicious rows, 0 readiness failing gates
- latest ledger: `repeatability_no_signal_clean_packets`
- ledger summary: 4 clean no-signal packets, 0 positive clean packets, 0
  repeated descriptors

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. Predmarket is parked at `kalshi_type2_candidate_disposition_watch_only`.
3. MLB is parked at `primary_type2_repeatability_no_signal_clean_packets`.
4. The next useful MLB/predmarket unlock is one of: explicit threshold-policy
   review, a new clean calendar slate, settled-outcome evidence, or
   closing-line validation evidence.
5. ATP, NBA, and NFL routing posture remains unchanged.

Do not lower thresholds, make another provider call, or state an edge by
default.

## 2026-06-30 BetExplorer Multi-Market Update

The public closing/reference evidence lane advanced one step without changing
policy. MLB expanded the BetExplorer public import from moneyline-only to
moneyline, totals, and run-line tabs:

- full-slate import: 13 events, 953 public rows, 3 books
- market rows: `moneyline=78`, `run_line=203`, `total=672`
- comparison artifact: `type2-betexplorer-market-closing-comparison-latest/type2-betexplorer-market-closing-comparison.json`
- comparison status: `betexplorer_market_closing_comparison_ready_no_policy_change`
- direct matches: 24 total (`ml=22`, `run_line=2`, `total=0`)
- current-threshold rows: 0

The useful learning is that public BetExplorer can supply broader closing-style
reference data, but direct same-book, same-line coverage against the current
Type 2 evidence remains too narrow. The macro router now parks MLB at
`primary_type2_betexplorer_market_closing_comparison_no_policy_change`.

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB needs broader book/line/source coverage, an independent clean slate, or
   stronger true closing-line validation before policy work resumes.
3. ATP, NBA, and NFL routing posture remains unchanged.

Do not lower thresholds, make another provider/API call, write databases, touch
execution/account/order paths, or state an edge by default.

## 2026-06-30 Public Closing Evidence Update

The next bottleneck was whether any true/public closing-line evidence could be
obtained without paid historical data or provider-key calls. MLB found a public
BetExplorer moneyline odds endpoint and built a narrow import/comparison path:

- raw public-web snapshots stay outside repos under
  `/home/mrwatson/manual_drops/public_web/`
- public closing scout: `public_closing_importer_ready`
- full-slate BetExplorer import: 13 events, 78 moneyline rows, 3 books
- moneyline comparison: 22 date-matched direct BetMGM rows
- comparison result: 16 converged, 6 diverged, 17 direction-support,
  5 direction-against, 0 current-threshold rows
- router status:
  `primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change`

This answers the acquisition question but does not change policy. The evidence
is useful and narrow: moneyline only, direct book matches only, not full
closing-line validation, and still no current-threshold signal.

Current macro posture:

1. Predmarket remains command center because all lanes are parked.
2. MLB is parked until broader book/market mapping, an independent clean slate,
   or stronger full closing-line validation evidence appears.
3. Predmarket remains parked at timing-safe watch-only evidence.
4. ATP, NBA, and NFL remain unchanged: ATP needs fresh validation/promotion
   proof, NBA needs new source-backed signal/data, and NFL governance is fresh.

Do not lower thresholds, make provider/API calls, write databases, touch
execution/account/order paths, or make tradable/profitability claims.

## 2026-06-30 MLB Settled-Outcome Validation Update

The threshold-policy hold was followed by a local settled-outcome validation
pass. Final scores were recorded in a local manual-drop file outside the repo
from the public MLB.com June 29 scoreboard. The generator itself reads only
that local score file plus local derived Type 2 artifacts.

- settled-validation artifact: `type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json`
- status: `settled_validation_no_policy_change_same_slate`
- candidate rows reviewed: 1,278
- settled directional rows: 1,239
- directional correct: 558
- directional incorrect: 681
- directional correctness: 45.0%
- rows at current 0.1000 threshold: 0
- rows at 0.0200 threshold: 65, with 16 correct and 49 incorrect
- slate dates represented: 1 (`2026-06-29`)

The important learning is negative and useful: settled final scores do not
support lowering the Type 2 threshold from this same-slate evidence. The
next useful MLB evidence is no longer "run settled validation"; it is an
independent clean slate or closing-line validation.

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB is parked at `primary_type2_settled_validation_no_policy_change_same_slate`.
3. The next useful MLB evidence is a new independent clean slate or
   closing-line validation.
4. ATP, NBA, and NFL routing posture remains unchanged.

Do not lower thresholds, make another provider call, or state an edge by
default.

## 2026-06-30 MLB Closing-Proxy Validation Update

The settled-validation result was followed by a local closing-line-style proxy.
This is not a true close; it compares already-captured clean snapshots against
later already-captured clean snapshots for the same game, market, selection,
line, book, and exchange contract. It made no provider/API calls and used no
raw payloads inside the repo.

- closing-proxy artifact: `type2-closing-proxy-validation-latest/type2-closing-proxy-validation.json`
- status: `closing_proxy_same_slate_support_insufficient`
- clean packets reviewed: 4
- paired later-snapshot rows: 819
- rows at current 0.1000 threshold: 0
- slate dates represented: 1 (`2026-06-29`)
- at 0.0200: 58 paired rows, 50 exchange-support, 0 against, 8 flat
- at 0.0250: 6 paired rows, 6 support, 0 against

The useful learning is mixed. Later same-slate snapshots moved favorably for
some lower-threshold rows, which is encouraging as market-movement behavior.
But settled outcomes were poor and the proxy is not a true closing line, so the
macro OS must not lower thresholds or promote MLB Type 2. The next useful
evidence is an independent clean slate or true closing-line validation.

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB is parked at `primary_type2_closing_proxy_same_slate_support_insufficient`.
3. The next useful MLB evidence is a new independent clean slate or true
   closing-line validation.
4. ATP, NBA, and NFL routing posture remains unchanged.

Do not lower thresholds, make another provider call, or state an edge by
default.

## 2026-06-29 Three-Packet Research-Review Update

The third explicitly authorized current MLB capture completed and produced a
third clean pregame Type 2 packet:

- third clean bundle: `2026-06-29-third-current-intake`
- latest ledger: `type2-repeatability-ledger-latest/type2-repeatability-ledger.json`
- ledger status: `repeatability_ready_for_research_review`
- clean packets: 3
- cluster rows: 28
- repeated descriptor shapes: 3
- three-packet recurring descriptors: 2
- research-review artifact: `type2-repeatability-research-review-latest/type2-repeatability-research-review.json`
- research-review status: `repeatability_research_review_ready`

The useful learning is narrow but real: the recurring measured-disagreement
shape is concentrated in full-game away `+1.5` run-line descriptors. The main
caveat is also now explicit: all three clean packets are current captures from
the same 2026-06-29 slate. That means cross-slate recurrence, settled outcomes,
closing-line validation, and any tradable/profitability interpretation remain
unproven.

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB is parked at `primary_type2_repeatability_research_review_ready_same_slate_caveat`.
3. The next useful MLB evidence is another calendar-slate clean pregame packet
   or settled/closing-line validation evidence.
4. ATP, NBA, and NFL routing posture remains unchanged from the prior update.

Do not make another provider call by default.

## 2026-06-29 Run-Line Contract Audit Update

The three-packet MLB repeatability result above is now superseded. A targeted
contract audit found that the repeated away `+1.5` run-line shape came from a
contract-sign mismatch, not proven market disagreement.

Kalshi `KXMLBSPREAD-...-TEAM2` YES contracts represent the selected team
winning by more than 1.5 runs. That is selected-team `-1.5`. The old MLB
adapter/candidate path compared those contracts to sportsbook selected-team
`+1.5` cover rows. After correcting the mapping and regenerating the three
local packets from already-captured raw files only:

- latest ledger status: `repeatability_blocked_no_clean_packets`
- clean packets: 0
- stable recurring descriptors: 0
- latest research-review status: `repeatability_research_review_blocked_threshold_not_met`

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB is parked at `primary_type2_repeatability_blocked_no_clean_packets`.
3. The old same-slate away `+1.5` repeatability finding must not be used as
   evidence.
4. Next useful MLB evidence requires a new contract-safe clean pregame packet,
   settled-outcome evidence, or closing-line validation evidence.
5. ATP, NBA, and NFL routing posture remains unchanged.

Do not make another provider call by default.

## 2026-06-29 Predmarket Timing-Safe Reference Update

The predmarket timing-safe sportsbook-reference blocker was solved with one
bounded current sportsbook request and one bounded Kalshi manual-drop capture:

- sportsbook raw: `/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260629T033913Z.json`
- Kalshi raw: `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260629T033913Z.json`
- reference rows: 24
- valid explicit mappings: 24/24
- temporal downgrades: 0
- manual timing unknown: 0
- disposition status: `candidate_disposition_watch_only`

This moved predmarket from "missing timing-safe evidence" to "clean mapped
evidence, but no review-threshold candidate." The follow-up threshold
sensitivity report showed the clean pair is far below the current threshold:
max positive review-only net divergence is 0.0177 versus a 0.1000 threshold,
leaving a 0.0823 gap. Current macro status is
`kalshi_type2_candidate_disposition_watch_only`.

Current macro posture:

1. Predmarket remains the command center, but this lane is parked until a new
   timing-safe reference/slate produces a review-threshold candidate or the user
   explicitly changes threshold policy.
2. MLB remains parked at `primary_type2_repeatability_blocked_no_clean_packets`.
3. ATP, NBA, and NFL routing posture remains unchanged.

Do not make another provider call by default.

## 2026-06-30 MLB Threshold-Policy Review Update

The clean no-signal MLB state has now been followed by an explicit
threshold-policy review. The review reads only local derived artifacts and
does not make provider/API calls, database writes, execution calls, or account
path calls.

- threshold-policy artifact: `type2-threshold-policy-review-latest/type2-threshold-policy-review.json`
- status: `threshold_policy_hold_current`
- clean packets reviewed: 4
- slate dates represented: 1 (`2026-06-29`)
- candidate rows reviewed: 1,278
- rows at current 0.1000 threshold: 0
- max absolute net difference: 0.0277
- best lower-threshold candidate: 0.0200, same-slate-only

The important learning is that the current threshold should not be lowered
from this evidence. There is a small recurring lower-threshold shape, but it is
only observed on one slate and remains far below the current 0.1000 review
threshold.

Current macro posture:

1. Predmarket remains the command center for blocker collection.
2. MLB is parked at `primary_type2_threshold_policy_hold_current`.
3. The next useful MLB evidence is a new independent clean slate,
   settled-outcome evidence, or closing-line validation evidence.
4. ATP, NBA, and NFL routing posture remains unchanged.

Do not lower thresholds, make another provider call, or state an edge by
default.
