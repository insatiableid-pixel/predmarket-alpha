# Sports Next-Probe Blocker Clearance

Date: 2026-07-06

## Objective

Clear the remaining sports evidence-cycle ambiguity where the ETA artifact exposed row-level
probe clocks but the summary/top-level cycle report did not name the exact next deficient surface.

## Landing

- `scripts/kalshi_sports_event_velocity_eta.py` now emits `summary.next_probe_surface`.
- `summary.next_probe_surface` selects the earliest future deficient non-rollup surface and
  ignores stale/past probe timestamps.
- `scripts/kalshi_sports_evidence_cycle_report.py` propagates the field as
  `summary.sports_event_velocity_next_probe_surface`.
- Evidence-cycle `next_action` now names the probe surface/time when no contracts are currently
  due.

## Latest State

- Event velocity status: `sports_event_velocity_eta_ready_with_label_deficits`.
- Next due surface: `null`.
- Next probe surface: `sports_consensus_rule_bucket_accumulation`.
- Model: `sports_consensus_price_bucket_bias_bucket_0.50_0.70`.
- Next probe: `2026-07-06T03:00:00Z`.
- OOS labels: `5/10`.
- OOS deficit: `5`.
- Paper state: `10` usable unresolved rows, next close `2026-07-06T03:00:00Z`.
- Passive maker: real paper-fill falsification ready, `0` FDR survivors.
- Live: `0` eligible rows.

## Guardrails

- No thresholds lowered.
- No labels inferred from sportsbooks or donor data.
- No probability, EV, paper promotion, or live eligibility changed.
- No execution, account, or order paths touched.

## Verification

- `TMPDIR=/home/mrwatson/projects/predmarket-alpha/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_sports_event_velocity_eta.py tests/test_kalshi_sports_evidence_cycle_report.py -v --tb=short`
  - `16 passed`
- `.venv/bin/ruff check scripts/kalshi_sports_event_velocity_eta.py scripts/kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_event_velocity_eta.py tests/test_kalshi_sports_evidence_cycle_report.py`
  - `All checks passed`
- `make kalshi-sports-event-velocity-eta`
  - exits `0`
- `make kalshi-sports-evidence-cycle-report`
  - exits `0`
- `make lint-baseline-check`
  - exits `0`
- `make quality`
  - exits `0` with the existing advisory Ruff/deptry backlog

## Next Mechanical Action

At or after `2026-07-06T03:00:00Z`, run:

```bash
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

Stop before lowering label/OOS/FDR thresholds or using non-Kalshi settlement labels.
