# Sports Consensus Observation Archive

Date: 2026-07-04

## Purpose

Fulfill `NEXT_DIRECTIVE_2026-07-04_SPORTS_CONSENSUS_OBSERVATION_ARCHIVE.md`: repair the prior consensus preflight latest-pointer leak, then build the missing observation/label archive feeding sports no-vig consensus falsification.

## Cleanup First

- Fixed `scripts/kalshi_sports_consensus_preflight.py` so global `latest-kalshi-sports-consensus-preflight.*` pointers are written only when the output directory is under `docs/codex/macro`.
- Added a regression assertion in `tests/test_kalshi_sports_consensus_preflight.py` proving temp output dirs do not mutate global latest pointers.
- Refreshed real consensus artifacts with `make kalshi-sports-consensus-refresh`; latest preflight is no longer test fixture data.
- Fixed the same latest-pointer leak in `scripts/kalshi_sports_consensus_falsification.py` after broad unit tests exposed temp falsification output could overwrite global latest artifacts.

## New Work

- Added `scripts/kalshi_sports_consensus_observation_loop.py`.
- Added `tests/test_kalshi_sports_consensus_observation_loop.py`.
- Added Make targets:
  - `kalshi-sports-consensus-observation-loop`
  - `kalshi-sports-consensus-observation-watch-once`
- Wired the observation loop into `make kalshi-sports-evidence-cycle` after consensus preflight and before consensus falsification.
- Updated `scripts/kalshi_sports_evidence_cycle_report.py` so the observation loop is the 23rd safe artifact and surfaces consensus observation/label counts.
- Hardened `scripts/kalshi_sports_consensus_falsification.py` to dedupe packet rows by `observation_id`, preventing stamped packet plus `latest` packet copies from inflating evidence counts.

## Latest Real State

- Consensus refresh: `64` reference rows, `32` unique Kalshi tickers, `32` valid candidates.
- Observation loop: `sports_consensus_observation_loop_ready_waiting_settlement`.
- Consensus observations: `64` total, `32` new in latest run.
- Consensus labels: `0`.
- Falsification: `sports_consensus_falsification_blocked_insufficient_labels`.
- Joined labels: `0`.
- Tested hypotheses: `0`.
- FDR survivors: `0`.
- Sports evidence cycle: `sports_evidence_cycle_ready_with_label_progress`.
- Safe artifacts: `23/23`.
- Live preflight: `kalshi_live_blocked`, `0` live eligible.

## Guardrails

- Labels come only from exact public Kalshi market payloads matched by `contract_ticker`.
- No sportsbook outcomes, league scores, or donor model outputs are used as labels.
- Every observation/label row remains `research_only=true`, `usable=false`, `calibrated_probability=null`, `expected_value_per_contract=null`, and `execution_enabled=false`.
- No EV ledger promotion, paper promotion, live eligibility, account path, or order path was added in this tranche.

## Verification

- Focused tests: `26 passed`.
- Touched-file Ruff: clean.
- Py-compile: clean.
- `make kalshi-sports-consensus-refresh`: exits 0.
- `make kalshi-sports-consensus-observation-loop`: exits 0.
- `make kalshi-sports-consensus-falsification`: exits 0.
- `make kalshi-sports-evidence-cycle`: exits 0.
- `make kalshi-sports-evidence-cycle-report`: exits 0 after restoring real falsification latest.
- `make test-unit`: `841 passed`, `14 deselected`.
- `make test-integration`: `14 passed`.
- `make quality`: exits 0 with existing advisory Ruff/deptry backlog.
- `git diff --check`: exits 0 with line-ending warnings only.

## Next

After the observed consensus contracts settle, run `make kalshi-sports-consensus-observation-watch-once` so the loop probes exact public Kalshi tickers, writes label packets, and reruns falsification. Stop before EV or paper promotion unless OOS/FDR evidence passes under the existing thresholds.
