# Tranche Note: Sports Blocker Clearance Cycle

## North-Star Alignment

This tranche clears the remaining operational ambiguity around Claude's sports
advice without weakening any statistical gate. The system now has a
machine-readable control loop that knows which sports evidence blockers are
actually due, which are waiting on exact settlement/probe clocks, and which
Make commands are allowed when a clock arrives.

## What Changed

- Added `scripts/kalshi_sports_blocker_clearance_cycle.py`.
- Added `make kalshi-sports-blocker-clearance-cycle`.
- Added opt-in execution controls:
  - `KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1`
  - `KALSHI_SPORTS_BLOCKER_CLEARANCE_ATP_REPO`
  - `KALSHI_SPORTS_BLOCKER_CLEARANCE_COMMAND_TIMEOUT_SECONDS`
- Added focused tests in `tests/test_kalshi_sports_blocker_clearance_cycle.py`.

The default target is dry/control-plane only. If a clock is due and
`RUN_DUE=1` is set, the cycle runs the exact public-data refresh path and then
re-runs the Claude advice audit. It does not select trades, compute EV, size
stake, or touch account/order paths.

## Current Real State

After refreshing ATP donor evidence from `atp-oracle` and re-importing it into
`predmarket-alpha`:

- Claude advice audit: `8/10` satisfied, `2/10` clock-bound.
- Consensus rule-bucket blocker: `sports_consensus_rule_bucket_accumulation`,
  OOS deficit `5`, next clock `2026-07-06T21:10:00Z`.
- ATP forward-OOS blocker: `8/10` resolved, next exact clock
  `2026-07-07T06:00:00Z`.
- ATP preliminary evidence is adverse: true-CLV mean `-5.06pp`, lower bound
  `-11.27pp`, executable liquidity `0/25`, and donor report says the forward
  residual is negative.
- Live remains blocked; no account/order/execution path was touched.

## Verification

- `pytest tests/test_kalshi_sports_blocker_clearance_cycle.py -v`: `4 passed`
- `ruff check scripts/kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_sports_blocker_clearance_cycle.py`: clean
- `python3 -m py_compile scripts/kalshi_sports_blocker_clearance_cycle.py`: clean
- `make kalshi-sports-event-velocity-eta`: exits `0`
- `make kalshi-claude-advice-audit`: exits `0`
- `make kalshi-sports-blocker-clearance-cycle`: exits `0`

## Next Mechanical Action

At or after `2026-07-06T21:10:00Z`, run:

```bash
make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1
```

If labels land, the existing OOS/FDR gates decide. If they do not, the artifact
will advance the next clock without threshold lowering or inferred labels.
