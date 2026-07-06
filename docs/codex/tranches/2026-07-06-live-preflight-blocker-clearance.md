# 2026-07-06 Live Preflight Blocker Clearance

## Objective

Clear false software/data blockers at the paper-to-live boundary while keeping live execution disabled and all donor/artifact controls intact.

## What Changed

- Internal control-repo paper candidates with `source_repo_id="predmarket-alpha"` no longer have to pass the external donor artifact preflight. This fixes the false `source repo artifact did not pass external preflight` blocker for internally generated FDR-gated evidence.
- External donor candidates still require strict external-artifact preflight before live eligibility.
- `kalshi-live-preflight` can now load market snapshots from a file and, by default, capture read-only unauthenticated public Kalshi market + orderbook snapshots for `paper_usable=true` tickers.
- Public market snapshots merge `/markets/{ticker}` status/price data with `/markets/{ticker}/orderbook` top reciprocal ask depth, so live preflight can evaluate current ask and size before credentials or arming.
- `kalshi-live-trader` fallback uses the same read-only snapshot path when unarmed or missing credentials, so trader and preflight artifacts agree.
- Suppressed noisy `live stake rounds down below one contract` blockers when account balance is missing; the real blocker remains `account balance missing`.

## Latest State

- `make kalshi-live-preflight`: `kalshi_live_blocked`
- Live decisions: `447`
- Live eligible: `0`
- Total live stake: `$0`
- Safe external artifacts: `15`
- Informed-flow rows with fresh current ask/size: `17/17`
- Remaining informed-flow live blockers:
  - `live execution mode is disabled`
  - `config venues.kalshi.execution_enabled is false`
  - `KALSHI_LIVE_TRADING_ENABLED is not armed`
  - `account balance missing`

## Sports Evidence Context

- Paper-usable rows: `17`
- Paper stake: `$2119.664117`
- Consensus preflight: `78/80` valid rows, `0` timestamp blockers
- Consensus falsification: `sports_consensus_falsification_blocked_no_testable_hypotheses`
- Consensus joined labels: `185`
- Nearest hypothesis OOS deficit: `5`
- Passive liquidity: `0` FDR survivors
- Provider gaps: soccer actionable; NBA deferred; covered sports are `mlb`, `tennis`, and `nfl`.

## Verification

- `PYTHONPATH=. .venv/bin/pytest -s tests/test_kalshi_live_engine.py -q` -> `12 passed`
- `.venv/bin/ruff check predmarket/kalshi_live_engine.py scripts/kalshi_live_preflight.py scripts/kalshi_live_trader.py tests/test_kalshi_live_engine.py` -> pass
- `PYTHONPATH=. .venv/bin/python -m py_compile predmarket/kalshi_live_engine.py scripts/kalshi_live_preflight.py scripts/kalshi_live_trader.py tests/test_kalshi_live_engine.py` -> pass
- `make kalshi-live-preflight` -> pass
- `make kalshi-live-trader` -> pass
- `make kalshi-sports-evidence-cycle-report` -> pass
- `make kalshi-sports-evidence-cycle` -> pass
- `make test-unit` -> `1348 passed / 15 deselected`
- `make test-integration` -> `14 passed`
- `make lint-baseline-check` -> pass
- `make quality` -> pass with existing advisory Ruff/deptry backlog

## Guardrails

- No live orders submitted.
- No credentials required.
- No execution mode armed.
- No account/order path used by public snapshot capture.
- No statistical gate changed or loosened.
