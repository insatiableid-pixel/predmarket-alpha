# Tranche: MLB dense-panel operations hardening

Date: 2026-07-10  
Branch: `codex/kalshi-sports-mlb-panel-ops-hardening-20260710T060259Z`  
Base: `origin/main` @ `802f48c` (merged PR #72)  
Implementation commit: `ed9b39a`  
PR: #73  

## Why this tranche was required

PR #72 landed the preregistered collector but no durable scheduler existed. The
unfiltered one-minute command also requested every open MLB contract's order
book on every cycle. With 90 open contracts at the first operations audit, that
would have issued up to about 129,600 order-book requests per day if inventory
stayed constant, including games days away from a registered clock.

The original command also wrote runtime status into tracked repository paths by
default and timestamped every row at cycle start rather than after its specific
order-book response. The latter could admit sub-second post-clock information as
if it were pre-clock.

## Changes

- Discovery still runs once per minute, but per-market order-book requests are
  limited to the preregistered as-of lookback windows:
  - T-24h: 30 minutes before the target clock
  - T-6h: 15 minutes before the target clock
  - T-60m: 5 minutes before the target clock
  - T-15m: 2 minutes before the target clock
- Rows now preserve request-start time and use post-response time as
  `observed_at_utc`. Strict as-of replay therefore rejects a response received
  after the target clock.
- Each row records explicit order-book success/failure provenance. The public
  source-share gate is calculated from event/clock books actually selected by
  replay, not every raw snapshot.
- Runtime status defaults to
  `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_status/` and no
  longer dirties tracked macro artifacts unless explicitly requested.
- Empty cycles write no immutable packet files. Coverage is reloaded from the
  append-only raw file after deduplication.
- Health distinguishes the current process's own PID lock from a competing
  collector and reports last cycle separately from last data capture.

The registration hash and frozen candidate formula were not changed.

## Durable operation

The user's existing crontab was preserved and extended with a bounded block:

```cron
# PREDMARKET_KALSHI_MLB_DENSE_PANEL_START
* * * * * cd /home/mrwatson/projects/predmarket-alpha-worktrees/kalshi-sports-mlb-panel-ops-hardening-20260710T060259Z && mkdir -p /home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_logs && TMPDIR=/tmp /usr/bin/flock -n /tmp/predmarket-kalshi-mlb-dense-panel-cron.lock /home/mrwatson/projects/predmarket-alpha/.venv/bin/python scripts/kalshi_sports_mlb_dense_panel_ops.py capture --limit 200 --no-write-repo-latest >> /home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_logs/collector.log 2>&1
# PREDMARKET_KALSHI_MLB_DENSE_PANEL_END
```

- Cron daemon: active
- External lock: `/tmp/predmarket-kalshi-mlb-dense-panel-cron.lock`
- Internal PID lock:
  `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_raw/collector.lock`
- Runtime status:
  `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_status/mlb-dense-panel-status.json`
- Log:
  `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_logs/collector.log`
- Append-only raw:
  `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_raw/mlb_dense_panel_snapshots.jsonl`

The first cron-owned cycle at `2026-07-10T06:14:03Z` discovered 90 markets,
found 0 in a current registered window, avoided all 90 order-book requests,
wrote 0 rows and 0 packet files, and kept repository writes disabled. It
reported the next capture window at `2026-07-10T19:25:00Z`.

## Current evidence state

- `capture_infrastructure_ready_panel_accumulating`
- snapshots: 30
- distinct events: 15
- distinct slate dates: 1
- T-60m eligible events: 0
- T-15m eligible events: 0
- `evidence_panel_ready=false`
- frozen confirmation power: false
- candidate performance revealed: false
- frozen candidate remains `tight_spread_favorite_buy_yes_t60m` with formula
  hash `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- registration hash remains
  `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`

## Verification

```text
Focused dense-panel + inference repair: 23 passed
Full test suite: 1,496 passed
make kalshi-verify: 53 passed
Touched-file Ruff: passed
Python compilation: passed
Lint-baseline ratchet: passed (98/1422 lint, 23/94 format)
File-size ratchet: passed
Technical-debt ratchet: passed (22/22)
Import boundaries: 2 kept, 0 broken
Feature flags: passed
AGENTS validation: passed
Diff check: passed
```

Repository-wide Ruff continues to print the pre-existing advisory backlog; no
touched-file Ruff finding or lint-baseline regression was introduced.

## Next permissible action

Keep cron running and inspect only capture health, coverage, freshness, source,
depth, integrity, and registered gate counts. Do not expose candidate P&L,
retune the frozen formula, or run a v2 family.

When `evidence_panel_ready=true` and frozen confirmation power is mechanically
true, stop repeated monitoring of candidate statistics and run the immutable
single-shot confirmation exactly once. Until then, the research state is
calendar-pending and accumulating, not complete or blocked.

Research-only throughout: no live execution, sizing, accounts, orders,
credentials, approval queues, or settlement-outcome peeking.
