# Kalshi Research Desk

This desk is Kalshi-only for actionable execution research. Polymarket can remain a read-only intelligence source elsewhere in the system, but this loop must not create live Polymarket orders or depend on Polymarket eligibility.

The daily loop is deliberately research-only:

- Paper intents set `research_only: true`.
- Paper intents set `execution_enabled: false`.
- The cycle writes audit artifacts and a paper ledger, not exchange orders.
- Promotion readiness is a review signal, not authorization to trade.

## Daily Sequence

Run from the repository root.

1. Verify the runtime:

   ```bash
   make check-env
   ```

2. Refresh resolved Kalshi rows and run discovery:

   ```bash
   PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_discovery \
     --build-from-api \
     --limit 100 \
     --max-pages 1 \
     --days-back 180 \
     --iterations 32 \
     --top-k 10
   ```

   Use the emitted discovery JSON path as the hypothesis source for the live rank step.

3. Rank current Kalshi markets:

   ```bash
   PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_live_rank \
     --limit 100 \
     --max-pages 1 \
     --orderbooks \
     --top-k 25 \
     --discovery-report path/to/kalshi-discovery.json
   ```

4. Create research-only paper intents and settle any open intents with known outcomes:

   ```bash
   PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_research_cycle \
     --rank-report path/to/kalshi-live-rank.json \
     --max-total-stake-usd 100 \
     --max-event-stake-usd 50 \
     --stale-open-grace-hours 24
   ```

5. Audit the paper ledger:

   ```bash
   PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_paper_ledger \
     --stale-open-grace-hours 24
   ```

## Replay And Settlement

Use replay when investigating a run, reproducing a report, or testing a new paper policy without fetching live data.

```bash
PYTHONPATH=. .venv/bin/python -m predmarket.kalshi_research_cycle \
  --rank-report path/to/kalshi-live-rank.json \
  --outcomes-json path/to/outcomes.json
```

`--outcomes-json` accepts either:

- `{"MARKET-TICKER": 1}` or `{"outcomes": {"MARKET-TICKER": 1}}`
- A list of resolved-row objects with `market_id` or `ticker` plus `outcome`

Outcomes must be `0` or `1`.

## Artifacts To Review

The desk produces JSON and Markdown reports under the research reports directory.

- Discovery report: candidate hypotheses, support, reward, and row summary.
- Live rank report: current opportunities, blocking reasons, watchlist status, and scoring mode.
- Cycle report: paper intents, blocked opportunities, settlement, ledger audit, promotion readiness, event history, and integrity hashes.
- Ledger report: current ledger state, open exposure, settled performance, event history, and promotion readiness.
- Stale open intents: paper intents still open after the original close estimate plus the configured grace window.

Use the integrity hashes to compare runs:

- `rank_report_hash`
- `paper_intents_hash`
- `paper_blocked_hash`
- `settled_hash`
- `ledger_hash`
- `paper_events_hash`
- `config_hash`

## Promotion Gate

The default promotion gate requires:

- At least 30 settled paper intents.
- Brier score at or below 0.20.
- Win rate at or above 0.55.
- Settled PnL at or above 0.

`REVIEW_READY` means the paper ledger has enough evidence for human review. It does not enable execution. Any live execution path must stay behind the existing Kalshi-only approval and risk controls.

## Stop Conditions

Do not promote or act on a candidate when:

- The cycle report is missing event history or integrity hashes.
- Open paper exposure already reaches the event or total cap.
- The opportunity only passes because `allow_blocked_opportunities` was enabled.
- The discovery report has weak support or stale resolved rows.
- The market rules cannot be mapped to a clear Kalshi resolution source.
- The expected edge comes mainly from an untested transformation or a one-off news interpretation.

## Square-Money Focus

The best Kalshi targets for this engine are not the loudest markets by volume. They are liquid markets where retail wording mistakes are plausible and measurable:

- Rule-heavy macro and government markets.
- Markets with ambiguous-sounding titles but precise resolution language.
- Markets where official data release timing matters.
- High-attention events where order flow may chase headlines faster than contract text.

The research cycle should prefer repeatable semantic and calibration edges over single-market speculation.
