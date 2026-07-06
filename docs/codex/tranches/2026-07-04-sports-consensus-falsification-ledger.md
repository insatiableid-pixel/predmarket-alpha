# 2026-07-04 Sports Consensus Falsification Ledger

## Mission

Promote the working sports no-vig consensus surface from preflight inventory
into a real **falsification-gated sports signal ledger** so that
Kalshi-vs-no-vig-consensus divergence is OOS/FDR-tested before any paper
sizing. Preserve research-only safety, exact Kalshi settlement labels, and
live-blocked status. Do not lower thresholds. Do not claim +EV.

## What Landed

- `predmarket/sports_consensus_falsification.py`: typed helper module that
  takes valid consensus preflight candidates, joins them to settlement
  labels by exact `contract_ticker`+`side`, collapses by exact contract
  ticker, applies a chronological in-sample/OOS split, evaluates four
  pre-registered candidate rules across the threshold grid and price
  buckets, and routes every testable hypothesis through Benjamini-Hochberg
  FDR.
- `scripts/kalshi_sports_consensus_falsification.py`: thin CLI that reads
  the latest preflight artifact plus outside-repo consensus observation
  and settlement label packet directories, calls the helper, and writes
  macro artifacts plus `latest-*` pointers. All artifacts preserve
  `research_only=true`, `execution_enabled=false`, `market_execution=false`,
  `account_or_order_paths=false`.
- `make kalshi-sports-consensus-falsification`: new Make target, wired into
  `make kalshi-sports-evidence-cycle` immediately after
  `kalshi-sports-consensus-preflight` and before EV ledger / paper sizing.
- `scripts/kalshi_sports_evidence_cycle_report.py`: surfaces the new
  falsification artifact as a 22nd safe artifact and reports
  `sports_consensus_falsification_status`,
  `sports_consensus_falsification_joined_label_count`,
  `sports_consensus_falsification_tested_hypothesis_count`,
  `sports_consensus_falsification_fdr_survivor_count`, and
  `sports_consensus_falsification_research_candidate_count`.
- `tests/test_kalshi_sports_consensus_falsification.py`: 9 focused tests
  covering all directive cases (missing preflight, empty preflight,
  no-labels, testable candidate, FDR survivor, every row remains
  `usable=false`/`research_only=true` with no execution flags,
  multi-threshold counting increments the tested hypothesis family,
  CLI writes latest artifacts, and Makefile exposes the target).

## Pre-Registered Candidate Rules

1. `kalshi_vs_consensus_favorite_underpriced` (consensus > 0.5) — predict
   selected side wins when `consensus - kalshi_mid >= threshold`.
2. `kalshi_vs_consensus_underdog_underpriced` (consensus <= 0.5) — predict
   selected side wins when `consensus - kalshi_mid >= threshold`.
3. `kalshi_vs_consensus_fade_overpriced` — predict selected side loses
   when `kalshi_mid - consensus >= threshold`.
4. `sports_consensus_price_bucket_bias` — per-bucket calibration test
   against the bucket midpoint using one-sided binomial survival.

Threshold grid: `0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05`.
Price buckets: `[0.05,0.15), [0.15,0.30), [0.30,0.50), [0.50,0.70),
[0.70,0.85), [0.85,0.95]`.

Every (rule, threshold) for divergence rules plus every (rule, bucket) for
the bucket rule increments the same Benjamini-Hochberg family.

## Independence, Splitting, And Minimums

- Independence: collapse repeated observations by exact `contract_ticker`;
  each contract settles once.
- Cluster key: `sport_key|market_key|event_ticker` (conservative, metadata
  only at this layer; cluster control lives downstream in EV/paper gates).
- Chronological split: `chronological_split_index` from
  `predmarket.shared_helpers` with `test_fraction=0.30` (matches the
  existing sports/flow patterns).
- Minimums: `min_independent_labels=30`, `min_oos_labels=10`,
  `fdr_alpha=0.10`. These match the existing sports/flow minimums and are
  not loosened.

## Statuses

The artifact emits exactly one of:

- `sports_consensus_falsification_ready_with_research_candidates` (at
  least one FDR survivor),
- `sports_consensus_falsification_ready_no_research_candidates`,
- `sports_consensus_falsification_blocked_insufficient_labels`,
- `sports_consensus_falsification_blocked_no_valid_consensus_rows`,
- `sports_consensus_falsification_blocked_missing_inputs`,
- `sports_consensus_falsification_failed_safety_gate` (only if a future
  change violates the research-only boundary).

## Real-Run Status (2026-07-04)

Latest `make kalshi-sports-consensus-refresh` exits 0:
- Reference build `sports_consensus_reference_built_with_warnings`,
  40 reference rows, 20 unique Kalshi tickers, 2 distinct books.
- Preflight `sports_consensus_preflight_ready` with 20 valid candidates
  and 0 blockers.

Latest `make kalshi-sports-consensus-falsification` exits 0:
- Status `sports_consensus_falsification_blocked_insufficient_labels`.
  Preflight is present with 20 valid candidates, but the outside-repo
  consensus observation archive (`/home/mrwatson/manual_drops/
  kalshi_sports_consensus_observations/`) and the consensus settlement
  label archive (`/home/mrwatson/manual_drops/kalshi_sports_consensus_
  labels/`) are still empty, so the join yields zero rows. This is the
  honest expected first-run state — no FDR survivor is claimed.
- Independent label count: 0; OOS label count: 0; tested hypothesis
  count: 0; FDR survivor count: 0; research candidate count: 0.
- All safety flags preserved: `research_only=true`,
  `execution_enabled=false`, `market_execution=false`,
  `account_or_order_paths=false`, `staking_or_sizing_guidance=false`.

Latest `make kalshi-sports-evidence-cycle` exits 0:
- Cycle status `sports_evidence_cycle_ready_with_label_progress`, 22/22
  safe artifacts.
- Sports consensus falsification surfaced as
  `sports_consensus_falsification_blocked_insufficient_labels` with 0
  joined labels, 0 tested hypotheses, 0 FDR survivors, 0 research
  candidates.
- Live remains `kalshi_live_blocked` with 0 live-eligible rows.

## Falsification Surface Has Enough Exact Settlement Labels?

**Not yet.** The preflight surfaces 20 current valid consensus candidates
across MLB game-winner markets, but the consensus observation archive
that joins a snapshot's `(kalshi_ticker, side, consensus_prob_for_side,
kalshi_mid_for_side, observed_utc)` to a later exact Kalshi settlement
outcome is still empty by default. The next machine action is to start
archiving consensus observations and matching them to settlement packets
so the falsification ledger has data to score.

## Any FDR Survivor?

**No.** Zero FDR survivors. Zero testable candidates. Zero research
candidates. The ledger refuses to claim any signal survives because the
joined label count is zero.

## Anything Promoted To EV/Paper?

**No.** The ledger is explicitly NOT a paper sizing artifact. The
directive stop condition requires "stopping at the falsification artifact"
unless EV ledger promotion is added with separate tests. No EV ledger
promotion was added. Every output row remains `usable=false` and
`research_only=true`. No `calibrated_probability` or
`expected_value_per_contract` is computed. Paper and live behaviors are
unchanged.

## Why Live Remains Blocked

The ledger introduces no live path. `make kalshi-live-preflight` continues
to report `kalshi_live_blocked` with 0 live-eligible rows. The
`account_or_order_paths=false`, `market_execution=false`, and
`execution_enabled=false` flags are preserved on every artifact.

## Verification Commands And Results

```bash
PYTHONPATH=. TMPDIR=/tmp .venv/bin/pytest -q \
  tests/test_kalshi_sports_consensus_falsification.py \
  tests/test_kalshi_sports_consensus_preflight.py \
  tests/test_kalshi_sports_evidence_cycle_report.py
# -> 18 passed

make kalshi-sports-consensus-refresh
# -> exit 0; preflight ready with 20 valid candidates

make kalshi-sports-consensus-falsification
# -> exit 0; status sports_consensus_falsification_blocked_insufficient_labels

make kalshi-sports-evidence-cycle
# -> exit 0; cycle ready_with_label_progress, 22/22 safe artifacts,
#    0 live-eligible

make test-unit
# -> 833 passed / 14 deselected

make test-integration
# -> 14 passed

make quality
# -> exit 0 (advisory deptry findings only; no new oversized files;
#    ratchets green: lint-baseline-check 118/1422 + 93/94)

git diff --check
# -> clean (only pre-existing LF/CRLF warnings on existing files)
```

## Stop Condition

The consensus feed is no longer just preflight inventory. The repo now
emits an auditable sports consensus falsification artifact with explicit
pass/block status. No live execution. No threshold lowering. No +EV
claim. The only allowed claim is statistical gate status based on exact
labels and FDR-controlled OOS evidence.

## Next Machine Action

Stand up a consensus observation accumulator (separate tranche) that
writes safe research-only packets under `/home/mrwatson/manual_drops/
kalshi_sports_consensus_observations/` per refresh, then probes the
matching Kalshi tickers after settlement to populate `/home/mrwatson/
manual_drops/kalshi_sports_consensus_labels/`. Re-run
`make kalshi-sports-consensus-falsification` once the joined label count
reaches the minimums. Stop before any EV ledger promotion unless that
gate is added with its own tests.
