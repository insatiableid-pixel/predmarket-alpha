# Sports/ATP 19:00Z Probe Clearance

Date: 2026-07-07

## What Ran

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-event-velocity-eta
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle
```

## Result

The due cycle ran and did not promote any signal. Existing gates remain in force.

## Consensus Falsification

- status: `sports_consensus_falsification_blocked_no_testable_hypotheses`
- joined labels: `723`
- independent labels: `61`
- OOS labels: `19`
- settlement labels: `768`
- consensus observations: `2615`
- preflight reference rows: `234`
- preflight valid candidates: `68`
- tested hypotheses: `0`
- FDR survivors: `0`
- max hypothesis OOS count: `7/10`
- nearest model: `kalshi_vs_consensus_fade_overpriced_threshold_0.005`
- nearest OOS deficit: `3`

Interpretation: the global label floors are met, but every pre-registered rule/bucket cell remains short of the per-hypothesis OOS floor. No threshold was lowered and no post-hoc rule was added.

## ATP Evidence

- status: `atp_proxy_evidence_gate_blocked_forward_oos`
- settled labels: `842`
- forward-OOS resolved: `8/10`
- forward-OOS summary: `Forward-OOS realized residual is -20.5pp (non-positive). Edge does not persist forward.`
- liquidity passing candidates: `0`
- next expected expiration: `2026-07-08T06:00:00Z`

## Paper And Live

- paper status: `paper_decision_candidates_ready_all_rows_blocked`
- paper candidates: `459`
- paper usable rows: `0`
- total paper stake: `$0`
- live status: `kalshi_live_blocked`
- live eligible rows: `0`
- total live stake: `$0`

## Fable Audit

- implementation: `15/15`
- evidence: `10/15`
- open requirements: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`
- next blocker clock: `2026-07-07T23:00:00Z`

## Guardrails

- No labels inferred.
- No thresholds changed.
- No sportsbook rows treated as settlement labels.
- No EV/paper/live promotion occurred.
- No account, order, or execution path touched.

Tracked macro-output churn from this refresh was intentionally not committed.
