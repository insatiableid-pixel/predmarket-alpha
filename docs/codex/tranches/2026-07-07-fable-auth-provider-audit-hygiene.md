# Fable Auth / Provider Audit Hygiene

Date: 2026-07-07

## Why

Two repo-side issues were making the remaining Fable blockers harder to clear cleanly:

- `.env.template` still described `KALSHI_API_SECRET` as a base64 API secret, while the consolidated Kalshi V2 auth client requires an RSA private key PEM or path.
- The top-level Fable provider coverage row counted deferred/off-surface sports in the same denominator as active provider gaps, even though the provider audit itself already separates non-actionable deferred sports from actionable gaps.

## Landed

- `predmarket.config.KalshiConfig` now accepts `KALSHI_PRIVATE_KEY_PEM` and `KALSHI_PRIVATE_KEY_PATH` ahead of legacy `KALSHI_API_SECRET` when `venues.kalshi.api_secret` is unset.
- `load_private_key("")` now names the modern private-key inputs in its actionable error message.
- `.env.template` now documents `KALSHI_PRIVATE_KEY_PATH` and `KALSHI_PRIVATE_KEY_PEM`; it no longer implies a base64 API secret.
- `scripts/kalshi_claude_advice_audit.py` now computes provider completion over actionable current-surface sports while still reporting total, deferred, and gap counts.

## Real State After Refresh

- Tick recorder: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`
- Tick recorder selected tickers: `250`
- Tick recorder channels: `ticker`, `orderbook_delta`
- Tick recorder recorded lines: `0`
- Tick recorder blocker: missing Kalshi RSA private key / API key in this environment
- Provider audit: `sports_consensus_provider_audit_ready_with_per_sport_gaps`
- Provider Fable row: `actionable_strict=3/3`, `actionable_mature=2/3`, `gaps=1`, `deferred=2`
- True actionable provider gap: soccer Asian sharp anchor unavailable in the current legal feed
- Fable audit: `15/15` implementation satisfied, `10/15` evidence satisfied
- Open Fable requirements: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`
- Next blocker clock: `2026-07-07T23:00:00Z`

## Guardrails

- No thresholds changed.
- No settlement labels inferred from sportsbooks.
- No EV, paper, or live promotion occurred.
- No account/order/live execution path was touched.
- Deferred tennis/NBA surfaces remain visible; they are not silently removed.

## Verification

- `pytest tests/test_kalshi_claude_advice_audit.py tests/test_config.py tests/test_auth_consolidation.py tests/test_kalshi_tick_recorder.py -q` -> `55 passed`
- `ruff check scripts/kalshi_claude_advice_audit.py predmarket/config.py predmarket/kalshi_live_client.py tests/test_kalshi_claude_advice_audit.py tests/test_config.py tests/test_auth_consolidation.py tests/test_kalshi_tick_recorder.py` -> passed
- `py_compile scripts/kalshi_claude_advice_audit.py predmarket/config.py predmarket/kalshi_live_client.py scripts/kalshi_tick_recorder.py` -> passed
- `make kalshi-tick-recorder` -> exited `0`, still safely blocked on missing auth
- `make kalshi-claude-advice-audit` -> exited `0`
- `make kalshi-sports-blocker-clearance-cycle` -> exited `0`, waiting for `2026-07-07T23:00:00Z`
