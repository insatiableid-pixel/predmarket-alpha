# Fable Sharp-Provider Capture Split

Date: 2026-07-07

## Why

The old `kalshi-sports-consensus-sharp-provider-capture` target reused the MLB-only strict reference builder. That made a multi-sport provider probe look like a no-row or unsupported-sport failure even when raw sharp-provider feeds were present for tennis, soccer, NFL, or NBA. Provider availability and exact Kalshi mapping are separate gates and should be audited separately.

## What Changed

- Added `predmarket/sports_consensus_sharp_provider_capture.py`.
- Added `scripts/kalshi_sports_consensus_sharp_provider_capture.py`.
- Rewired `make kalshi-sports-consensus-sharp-provider-capture` to the new provider-capture CLI.
- Kept the MLB reference builder unchanged for strict consensus-row construction.
- Added sports evidence-cycle reporting for the new capture artifact:
  - capture status
  - source-file count
  - event count
  - provider count
  - anchor-provider count
  - capture-error count
  - sports with provider rows

## Real Smoke

`make kalshi-sports-consensus-sharp-provider-capture` exited `0`.

- Status: `sports_consensus_sharp_provider_capture_ready`
- Source files: `5`
- Events: `99`
- Providers: `4`
- Anchor providers: `4`
- Capture errors: `0`
- Provider rows by sport: MLB, Wimbledon ATP, World Cup soccer, NFL
- No-current-row/deferred surface: NBA
- Anchor providers observed: `betfair_exchange`, `matchbook`, `pinnacle`, `smarkets`

`make kalshi-sports-evidence-cycle-report` exited `0`.

- Status: `sports_evidence_cycle_ready_with_label_progress`
- Safe artifacts: `31/31`
- Live eligible rows: `0`
- Paper usable rows: `0`

## Safety

- Research-only.
- No probabilities computed in the new capture artifact.
- No consensus rows created by the capture artifact.
- No labels inferred from sportsbooks.
- No threshold changes.
- No EV, paper stake, live eligibility, account, or order path touched.
- Raw provider payloads remain outside the repo under the configured manual-drop root.

## Verification

- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/pytest tests/test_kalshi_sports_consensus_sharp_provider_capture.py tests/test_kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_consensus_reference_builder.py tests/test_kalshi_sports_consensus_provider_policy.py tests/test_kalshi_sports_consensus_soccer_asian_provider.py -q` -> `33 passed`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check predmarket/sports_consensus_sharp_provider_capture.py scripts/kalshi_sports_consensus_sharp_provider_capture.py scripts/kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_consensus_sharp_provider_capture.py tests/test_kalshi_sports_evidence_cycle_report.py` -> pass
- `python3 -m py_compile predmarket/sports_consensus_sharp_provider_capture.py scripts/kalshi_sports_consensus_sharp_provider_capture.py scripts/kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_consensus_sharp_provider_capture.py tests/test_kalshi_sports_evidence_cycle_report.py` -> pass
- `make kalshi-sports-consensus-sharp-provider-capture` -> exit `0`
- `make kalshi-sports-evidence-cycle-report` -> exit `0`
- `git diff --check` -> clean except the known Makefile CRLF warning
