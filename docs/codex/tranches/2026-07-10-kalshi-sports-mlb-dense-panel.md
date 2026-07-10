# Tranche: Dense multi-slate MLB fixed-clock panel

Date: 2026-07-10  
Branch: `codex/kalshi-sports-mlb-dense-panel-20260710T054721Z`  
Worktree: `/home/mrwatson/projects/predmarket-alpha-worktrees/kalshi-sports-mlb-dense-panel-20260710T054721Z`  
Base: `origin/main` @ `708319c` (merged PR #71 repair)  
Directive: `GROK_KALSHI_SPORTS_MLB_INFERENCE_REPAIR_DENSE_PANEL_DIRECTIVE_20260710T052849Z.md` Phase 2

## Landed

### Preregistration (before outcome inspection)

- `docs/codex/macro/kalshi-sports-mlb-dense-panel-registration-latest/mlb-dense-panel-registration.{json,md}`
- `docs/codex/macro/latest-kalshi-sports-mlb-dense-panel-registration.{json,md}`
- Registration hash: `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`
- Primary clocks T-60m / T-15m with strict staleness; secondary T-24h / T-6h non-blocking
- Hard panel gates: ≥10 slates, ≥120 events, ≥100/clock primary, ≤0.20 slate share, source/depth/staleness thresholds

### Frozen candidate (exact; do not retune)

- `tight_spread_favorite_buy_yes_t60m`
- formula_hash `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- threshold 0.62, spread_max 0.03, clock T-60m, side yes
- `forward_confirmation_registered_at_utc`: 2026-07-10T05:37:38Z
- Status: `confirmation_pending` until panel + confirmation power

### Capture / ops

- `predmarket/sports_mlb_dense_panel.py` — registration, readiness, lock, append-only raw, health
- `scripts/kalshi_sports_mlb_dense_panel_ops.py` — `register|capture|status|replay`
- PID lock prevents duplicate collectors
- Append-only raw: `/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_raw/mlb_dense_panel_snapshots.jsonl`
- Status: `docs/codex/macro/latest-kalshi-sports-mlb-dense-panel-status.json`

### First capture cycle (public read-only)

- 30 markets / 30 rows written
- distinct_events=15, distinct_slate_dates=1
- `evidence_panel_ready=false` (honest accumulating)

## Not done (calendar-pending)

- Panel gates require ~10 slate dates / 120 events — multi-week accumulation
- Single-shot frozen confirmation only after `evidence_panel_ready` and confirmation power
- No v2 discovery family until frozen candidate resolved
- No modeling / threshold search / P&L peeking during accumulation

## Commands

```bash
.venv/bin/python scripts/kalshi_sports_mlb_dense_panel_ops.py register
.venv/bin/python scripts/kalshi_sports_mlb_dense_panel_ops.py capture --limit 200
.venv/bin/python scripts/kalshi_sports_mlb_dense_panel_ops.py status
.venv/bin/python scripts/kalshi_sports_mlb_dense_panel_ops.py replay
# Recommended schedule: every 60s via systemd user timer/cron; PID lock is exclusive
```

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_kalshi_sports_mlb_dense_panel.py  # 5 passed
.venv/bin/python -m pytest -q tests/test_kalshi_sports_mlb_settlement_miscalibration.py  # still green
```

## Safety

- Research-only; public/read-only Kalshi
- No live execution, sizing, accounts, orders, credentials
- Canonical dirty checkout untouched
- `.venv` symlink not committed
