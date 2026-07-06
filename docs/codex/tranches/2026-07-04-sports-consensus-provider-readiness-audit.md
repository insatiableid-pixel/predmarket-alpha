# Sports Consensus Provider Readiness Audit

Date: 2026-07-04

## Objective

Advance the sharp no-vig consensus lane in parallel with the Droid fee/live
mission without touching fee, live, risk, paper sizing, shared config, or
Makefile surfaces.

## Landing

Added an isolated provider policy and audit surface:

- `predmarket/sports_consensus_provider_policy.py`
- `scripts/kalshi_sports_consensus_provider_audit.py`
- `tests/test_kalshi_sports_consensus_provider_policy.py`

The audit classifies observed local providers as:

- A+ anchors: Pinnacle, Circa
- A anchors: Bookmaker, BetCRIS, SBOBet, Singbet, IBC
- Exchange anchors: Betfair Exchange, Matchbook, Smarkets
- Secondary: LowVig, BetOnline
- Comparison-only: DraftKings, FanDuel, BetMGM, Caesars

The policy states that soft books can be stale-lag/comparison features but cannot
anchor sports consensus probability. Exchange prices can anchor only with
timestamp, liquidity, and commission caveats.

## Safety

- No provider/API calls.
- No paid calls.
- No database writes.
- No account, order, execution, fee, risk, or paper-sizing changes.
- No Makefile wiring, to avoid collision with the concurrent Droid mission.
- Raw provider payloads remain outside the repo; the audit only reads local
  artifacts.

## Current Expected Gap

The current predmarket strict consensus feed is MLB secondary-only
(`lowvig`, `betonlineag`). ATP donor artifacts show exchange sharp coverage
such as Betfair Exchange / Matchbook / Smarkets-style rows, but those rows still
need an adapter into the strict predmarket consensus manifest before they can
enter the normal preflight, observation, settlement, and OOS/FDR chain.

## Next Move

Run the standalone audit:

```bash
python3 scripts/kalshi_sports_consensus_provider_audit.py
```

Then adapt the highest-readiness donor exchange rows into the strict consensus
schema. Do not promote any row to paper stake until exact Kalshi mapping,
settlement labels, OOS/FDR, cost/spread replay, capacity, cluster, and decay
gates pass.
