# Sports Evidence Velocity Cycle

Date: 2026-07-04

## Objective

Run a multi-hour sports-EV advancement mission in the vector direction of extracting and exploiting Kalshi sports mispricings before the crowd corrects them, without lowering gates or introducing human discretion.

The concrete bottleneck was evidence velocity: World Cup/FIFA, MLB, ATP/Wimbledon, and near-resolution sports rows were visible, but too many rows were still one-shot inventory or blocker rows. This tranche made repeated observations, public settlement probing, proxy labels, and consolidated sports evidence reporting mechanical.

## Subagent Audits

- Russell audited settlement/label readiness. Finding: MLB, World Cup, and ATP had observations but too few exact Kalshi settlement labels; microstructure had repeated snapshots but did not consume enough history.
- Harvey audited donor/model promotion. Finding: donor/model artifacts must remain non-tradable until they pass strict paper-gate readiness; NFL had usable-looking upstream rows but missing promotion fields.
- Kierkegaard audited paper/live eligibility. Finding: the right live boundary is still zero eligibility until paper gates, source preflight, current market state, risk caps, and execution arming all pass.

## Implementation

- Enhanced `scripts/kalshi_sports_microstructure_observation_loop.py`.
  - Loads historical public sports microstructure observations instead of only the latest packet.
  - Detects repeated snapshots, max snapshots per contract, and forward quote pairs.
  - Probes exact public Kalshi settled market payloads for due observed tickers.
  - Writes safe label packets outside the repo under `/home/mrwatson/manual_drops/kalshi_sports_microstructure_labels/`.
  - Reports historical observation breadth and label readiness.

- Enhanced `scripts/kalshi_near_resolution_informed_flow_evidence_gate.py`.
  - Consumes external microstructure history.
  - Joins exact settlement labels when available.
  - Emits forward quote labels for future-snapshot movement while still blocking on missing settled contract labels.

- Enhanced `scripts/kalshi_passive_liquidity_provision_evidence_gate.py`.
  - Consumes external microstructure history.
  - Builds virtual order rows from ordered snapshot sequences.
  - Emits counterfactual touch/timeout and adverse-selection proxy labels.
  - Keeps the family blocked until real fill labels and net EV evidence exist.

- Added `scripts/kalshi_sports_evidence_cycle_report.py`.
  - Consolidates universe, MLB, ATP, World Cup, microstructure, informed-flow, passive-liquidity, paper, and live-preflight artifacts.
  - Emits `latest-kalshi-sports-evidence-cycle.{json,md,csv}`.
  - Reports missing/unsafe artifacts, observation count, label/proxy-label count, paper eligibility, and live eligibility.

- Added Make targets:
  - `kalshi-sports-evidence-cycle-report`
  - `kalshi-sports-evidence-cycle`

## Latest Refreshed Evidence

Latest sports evidence cycle status: `sports_evidence_cycle_ready_with_label_progress`.

- Safe artifacts: 16/16
- Sports stack candidates: 7,329
- Sports surfaces: 4
- Total observations: 945
- Total exact/proxy labels: 43
- Total due rows: 21
- Sports paper-gate blocker rows: 90
- Paper candidates: 506
- Paper usable rows: 0
- Live decisions: 506
- Live eligible rows: 0

Family evidence:

- MLB observation loop: 122 observations, 58 distinct contracts, 4 exact public Kalshi settlement labels.
- MLB falsification: blocked with 2 independent contract labels vs. 30 minimum.
- World Cup/FIFA observation loop: 362 observations, 260 distinct contracts, 9 exact public Kalshi settlement labels.
- World Cup/FIFA falsification: blocked with 6 independent contract labels vs. 30 minimum.
- ATP/Wimbledon observation loop: 96 observations, 26 distinct contracts, 0 labels; still waiting settlement.
- Sports microstructure: 365 historical observations, 151 distinct contracts, 110 repeated-snapshot contracts, 214 forward quote pairs.
- Near-resolution informed-flow: 365 flow rows, 30 forward quote labels, 0 settled contract labels, 0 research candidates.
- Passive liquidity: 218 virtual orders, 10 counterfactual fill proxy labels, 10 adverse-selection windows, 0 real fill labels.
- Paper engine: 506 candidates, 506 blocked, 0 usable, total paper stake 0.
- Live preflight: 506 decisions, 0 eligible, total live stake 0.

## Guardrails Preserved

- No threshold lowering.
- No sportsbook or donor output treated as a settlement label.
- No manual approval or discretionary candidate picking.
- No donor repo runtime dependency.
- No account/order side effects from evidence jobs.
- No nonzero paper stake unless upstream falsification, EV, capacity, correlation, decay, and paper sizing gates pass.
- No live eligibility unless paper and live-risk gates pass.

## Verification

- `make kalshi-sports-evidence-cycle` exits 0.
- Focused sports evidence tests: 12 passed.
- `make test-unit`: 694 passed, 14 deselected.
- `make test-integration`: 14 passed.
- Touched-file Ruff check: clean.
- `make lint-baseline-check`: OK, lint 1407/1422 and format 89/94.
- `make tech-debt-check`: OK, 22/22.
- `make file-sizes-check`: OK, no new oversized files.
- `make modularize`: OK, 2 import-linter contracts kept.
- `make quality`: exits 0 with expected advisory deptry backlog.

## Remaining Blockers

- MLB and World Cup need more independent exact Kalshi settlement labels before their directional model families can enter OOS/FDR promotion.
- ATP/Wimbledon needs settled labels; current observations are not yet enough.
- Near-resolution informed-flow has forward quote labels, but still needs settled contract labels to test directional information survival.
- Passive liquidity has proxy labels and adverse-selection windows, but no real fill labels; it remains a separate medium-term family, not a directional shortcut.
- NFL donor rows need a strict sports paper-gate readiness envelope before they can promote from donor evidence into the paper/live chain.
- Future live-preflight hardening still needs live source registration, current market/account snapshots, and risk-state reconciliation when production arming becomes the task.
