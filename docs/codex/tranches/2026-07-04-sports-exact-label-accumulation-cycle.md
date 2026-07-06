# Sports Exact-Label Accumulation Cycle

Date: 2026-07-04

## Objective

Accumulate exact Kalshi settlement labels for MLB, World Cup/FIFA, and ATP/Wimbledon, then let the existing OOS/FDR gates decide whether any sports signal deserves paper stake.

The key constraint is that exact labels are public Kalshi settlement outcomes matched by exact ticker. Quote movement labels, counterfactual fill proxies, donor outputs, sportsbook feeds, and score feeds are not settlement labels.

## Changes

- Made ATP snapshot intake current by default.
  - `scripts/kalshi_atp_proxy_observation_loop.py` now resolves the latest `/home/mrwatson/projects/atp-oracle/data/kalshi/matches-*.json`.
  - `KALSHI_ATP_PROXY_MATCH_SNAPSHOT` in the Makefile now uses the latest lexicographic match snapshot, so `matches-2026-07-04.json` is selected instead of the stale July 3 file.

- Added `scripts/kalshi_sports_label_accumulation_cycle.py`.
  - Reads latest MLB, World Cup/FIFA, ATP, paper, and live artifacts.
  - Counts exact settlement labels separately from proxy labels.
  - Counts independent labels separately from duplicate observation rows.
  - Emits per-family label deficits and next exact public probe times.
  - Refuses to infer paper readiness unless OOS/FDR has produced a research candidate.

- Added `make kalshi-sports-label-accumulation-cycle`.
  - Runs the full sports evidence cycle.
  - Probes exact public Kalshi settlements.
  - Reruns OOS/FDR/evidence gates.
  - Reruns paper decisions and live preflight.
  - Writes `latest-kalshi-sports-label-accumulation-cycle.{json,md,csv}`.

## Latest Run

Command:

```bash
make kalshi-sports-label-accumulation-cycle
```

Result: `sports_label_accumulation_waiting_more_exact_labels`.

- Safe artifacts: 8/8
- Directional observations: 744
- Exact public Kalshi labels: 58
- Independent labels counted by gates: 14
- Total independent-label deficit: 56
- Paper candidates: 496
- Paper usable: 0
- Live decisions: 496
- Live eligible: 0

Family deficits:

- MLB: 52 exact label rows, 8 independent labels, needs 22 more independent labels.
- World Cup/FIFA: 6 independent exact labels, needs 24 more independent labels.
- ATP/Wimbledon: 0 labels, needs 10; next public label probe is `2026-07-04T06:00:00Z`.

Nondirectional evidence also advanced:

- Sports microstructure: `sports_microstructure_observation_loop_ready_with_settlement_labels`
- Historical microstructure observations: 485
- Distinct microstructure contracts: 249
- Settlement-label rows: 306
- Settled contracts: 104
- Forward quote pairs: 236
- Near-resolution informed-flow: `near_resolution_informed_flow_blocked_falsification_not_ready`
- Flow settled contracts: 104
- Flow forward quote labels: 48

## OOS/FDR Decision

OOS/FDR ran where applicable and did not promote any sports family.

- MLB remains `sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels`.
- World Cup/FIFA remains `world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels`.
- ATP remains `atp_proxy_evidence_gate_blocked_waiting_settlement_labels`.

Paper stake stayed zero because no directional sports family passed the label threshold and falsification gate.

## Guardrails

- No threshold lowering.
- No duplicate contract labels counted as independent evidence.
- No proxy quote labels counted as exact settlement labels.
- No donor or sportsbook labels used as outcomes.
- No probability promotion, paper stake, live eligibility, account path, order path, or execution side effect.

## Verification

- `make kalshi-sports-label-accumulation-cycle`: exits 0.
- Focused tests: 12 passed.
- `make test-unit`: 698 passed, 14 deselected.
- `make test-integration`: 14 passed.
- `make lint-baseline-check`: OK, lint 1407/1422 and format 90/94.
- `make tech-debt-check`: OK, 22/22.
- `make file-sizes-check`: OK, no new oversized files.
- `make modularize`: OK, 2 import-linter contracts kept.
- `make quality`: exits 0 with expected advisory deptry backlog.

## Next Machine Action

Run `make kalshi-sports-label-accumulation-cycle` after the next settlement windows, especially after `2026-07-04T06:00:00Z` for ATP/Wimbledon. The stop condition remains unchanged: do not lower thresholds, do not treat duplicate rows as independent labels, and do not allow paper stake until OOS/FDR plus downstream cost/capacity/correlation/decay gates pass.
