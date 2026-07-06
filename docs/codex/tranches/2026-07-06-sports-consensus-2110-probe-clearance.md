# Sports Consensus 21:10Z Probe Clearance

Date: 2026-07-06

## Summary

Ran the due sports blocker-clearance cycle after the `2026-07-06T21:10:00Z`
sharp-consensus settlement/probe clock. The first due run failed on a public
Kalshi HTTP 429 while fetching settled markets, so the tranche first repaired
the collector path with bounded retry/backoff and a focused regression test.

After the repair, the due cycle completed cleanly and refreshed the sports ETA
and Claude advice audit artifacts.

## Landing

- `scripts/kalshi_sports_proxy_observation_loop.py` now retries HTTP 429 public
  Kalshi fetches with bounded exponential backoff instead of failing on the
  first throttle response.
- `tests/test_kalshi_sports_proxy_observation_loop.py` covers the 429 retry path.
- `make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1`
  now exits `0`.
- Final non-due `make kalshi-sports-blocker-clearance-cycle` reports
  `sports_blocker_clearance_cycle_waiting_for_next_clock`.

## Current Counts

- Consensus observation loop: `338` label rows, `0` due distinct contracts,
  next public probe `2026-07-06T22:00:00Z`.
- Consensus falsification: `320` joined labels, `40` independent labels,
  `12` OOS labels, `0` tested hypotheses, `0` FDR survivors.
- Nearest deficient consensus hypothesis:
  `kalshi_vs_consensus_fade_overpriced_threshold_0.005`, still `5/10` OOS.
- Event velocity: total label deficit `110`, total OOS deficit `45`,
  next probe surface `sports_consensus_rule_bucket_accumulation` at
  `2026-07-06T22:00:00Z`.
- Claude advice audit: `8/10` evidence-satisfied, `10/10`
  implementation-satisfied, open evidence ids `CLAUDE-005` and `CLAUDE-008`.
- Paper: `9` usable rows, `$1798.4` paper stake.
- Live: `0` eligible.

## Guardrails

No thresholds were lowered. No labels were inferred from sportsbook or consensus
data. No candidate was promoted through OOS/FDR. No live/account/order path was
touched.

## Verification

- `make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1`
- `make kalshi-sports-event-velocity-eta`
- `make kalshi-claude-advice-audit`
- `make kalshi-sports-blocker-clearance-cycle`
- `PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_always_on_collector.py tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_proxy_observation_loop.py -q`
  - `30 passed`
- `.venv/bin/ruff check scripts/kalshi_sports_proxy_observation_loop.py tests/test_kalshi_sports_proxy_observation_loop.py scripts/kalshi_sports_blocker_clearance_cycle.py scripts/kalshi_always_on_collector.py scripts/kalshi_claude_advice_audit.py`
- `python -m py_compile scripts/kalshi_sports_proxy_observation_loop.py scripts/kalshi_sports_blocker_clearance_cycle.py scripts/kalshi_always_on_collector.py scripts/kalshi_claude_advice_audit.py`
