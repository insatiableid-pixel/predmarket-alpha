# Sports Blocker Retry Backoff

## Landing

Fixed a scheduler defect in `scripts/kalshi_sports_blocker_clearance_cycle.py`: a successful due settlement/probe run could be followed immediately by another due recommendation when Kalshi had not yet published enough exact labels. The blocker-clearance runner now reads the previous cycle artifact and backs off recently successful due tasks until the later of the configured retry cooldown or the next known future probe clock from event velocity.

Also tightened `scripts/kalshi_claude_advice_audit.py` so `CLAUDE-012` reports a sanitized tick-recorder auth error class. Current evidence is `auth_error=invalid_private_key_pem`, which distinguishes a bad RSA private-key material blocker from a missing worktree `.env`.

## Current Evidence

- Blocker cycle: `sports_blocker_clearance_cycle_waiting_for_next_clock`
- Due tasks: `0`
- Waiting tasks: `2`
- Next clock: `2026-07-08T01:50:03Z`
- Fable audit: `15/15` implementation satisfied, `10/15` evidence satisfied
- Open evidence ids: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`
- Consensus falsification: `828` joined labels, `64` independent labels, `20` OOS labels, `0` tested hypotheses, `0` FDR survivors
- Nearest consensus hypothesis: `sports_consensus_price_bucket_bias_bucket_0.30_0.50`, still `1` OOS label short
- Tick recorder auth probe: canonical root `.env` loaded into subprocess only; `KALSHI_API_SECRET` is not valid RSA PEM/private-key material for current V2/WebSocket auth, so `CLAUDE-012` remains blocked with `250` selected tickers, `0` recorded lines, `0` gaps, and `auth_error=invalid_private_key_pem`
- Paper/live: `0` paper-usable rows, `$0` paper stake, `0` live-eligible rows

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook outcomes used as settlement labels.
- No EV, paper, or live promotion.
- No account/order/live path touched.

## Verification

- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/pytest tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_blocker_clearance_cycle.py -q` -> `17 passed`
- `PYTHONPATH=. .venv/bin/ruff check scripts/kalshi_claude_advice_audit.py scripts/kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_blocker_clearance_cycle.py` -> passed
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make quality` -> exited `0` with existing advisory Ruff/deptry backlog
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-event-velocity-eta` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle` -> exited `0`
- Short credential-scoped `make kalshi-tick-recorder KALSHI_TICK_RECORDER_DURATION_SECONDS=1` with canonical root `.env` values loaded only into subprocess -> exited `0`, blocked on invalid RSA PEM/private-key material
