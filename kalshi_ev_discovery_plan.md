# Kalshi +EV Discovery: Research & Architecture Plan

*Market structure, cost model, documented inefficiencies, regulatory perimeter, and execution architecture — compiled July 3, 2026*

---

## Where the Volume Actually Is

Sports isn't a segment of Kalshi. It's Kalshi. Sports constitutes more than 90% of site activity and 89% of revenue in 2025. Through mid-June 2026, sports plus its sports-derived "Exotics" category (parlays, cross-category combiners, tournament markets) run roughly 85% of an approximately $112 billion total lifetime volume — $73.9 billion across 1,949 sports markets and $20.9 billion across ten Exotics markets, with sampled Exotics contracts confirmed entirely sports-derived. The category didn't exist before December 2024; the Super Bowl in February 2025 activated it at 39% of that week's volume, March Madness pushed it past 90%, and it has held above 87% since the September 2025 NFL season. The World Cup is live right now — Round of 32 wraps today, Round of 16 starts July 6 — and is driving record 2026 volume across both Kalshi and Polymarket, with Kalshi carrying more total sports volume spread across more match-level contracts, producing tighter pricing on NFL, NBA, and MLB specifically — the exact leagues the existing pipelines already cover.

This isn't just directional support for sports-first. It's where nearly all the executable liquidity actually is. Politics has solid federal footing since a 2024 court ruling held political event contracts fall within the Commodity Exchange Act, cemented when the CFTC withdrew its appeal in May 2025, but it's a fraction of volume by comparison. Economics, weather, and culture are real but thin; crypto is minor on Kalshi specifically.

**Capacity reality check:** 1,949 sports markets carrying $73.9B looks abundant on average, but that average is almost certainly dominated by a handful of marquee events with a long thin tail behind them — consistent with, though not an independent re-confirmation of, the existing ~82% ghost-listing finding. Given the platform's scale has grown roughly threefold in revenue terms since that measurement, the diagnostic is worth re-running against current order-book depth before cap_i gets treated as settled.

## The Exact Cost Structure

This corrects something flagged too casually earlier: TC(w) wasn't wrong to identify as the wrong *shape* — Kalshi has no smooth market-impact curve. But treating it as *nonexistent* was an oversimplification. There is a real, deterministic, published cost, and it belongs back in the objective.

**Taker fee:** fee = ⌈0.07 × C × P × (1−P)⌉, rounded up to the nearest cent, where C is contracts and P is price in dollars — an inverted-U curve peaking at 50¢ and declining toward the extremes. 100 contracts at $0.50 costs $1.75 in fees; the same 100 at $0.10 costs $0.63.

Given a $1-payout contract, this formula has an exact property worth naming precisely: **the taker fee, in cents, is exactly the minimum edge in probability points that p̂ must clear over p_market to break even.** At 50¢ that's 1.75 points. At 90¢, roughly 0.63 points.

**Maker fee:** a quarter of the taker multiplier (0.0175 instead of 0.07), and Kalshi's maker fee schedule produces an effective $0.00 per contract for most small trades because of the rounding step. This is the single most actionable execution-design conclusion in this document:

> **Default to posting, not crossing.** The execution layer should rest limit orders and only cross the spread when a signal's estimated decay rate outweighs the ~4x fee saved by waiting. A limit resting one tick off the touch in Kalshi's most popular sports and political markets typically fills within minutes, and a no-discretion system can hold that discipline systematically better than a human can.

Two portfolio-accounting items — not edges, just don't leave them on the table:

- Kalshi pays roughly 3.75–4% APY on idle balances through its banking partner, compounding while capital waits for the next validated signal.
- Fund via ACH or wire, not debit card. Debit deposits carry a 2% fee that ACH and wire transfers avoid entirely.

## What's Actually Been Documented as Mispriced

The most rigorous evidence is a working paper ("Makers and Takers: The Economics of the Kalshi Prediction Market") using transaction-level data on over 300,000 Kalshi contracts, testing price unbiasedness. The null hypothesis — that prices are an unbiased forecaster of outcomes — is rejected for every category tested (sports, climate and weather, crypto, politics, entertainment, economics) and for every year tested. The pattern is classic favorite-longshot bias: low-price contracts win far less often than required to break even after fees, while high-price contracts win more often and yield small positive returns.

Critically, it isn't a thin-market artifact. The bias holds across every volume quintile and every transaction-size quintile; the lowest-volume quintile shows the largest coefficient, but there's no clean evidence that higher-volume markets are meaningfully more efficient. That's a direct empirical argument for breadth over depth — this edge has genuine width across the market count, not just in a handful of thin corners.

**Two honest caveats, and they matter:**

1. An early-2026 analysis of similarly large Kalshi datasets found the *average* trader's pre-fee return was roughly negative 20%. Most participants are on the wrong side of this bias, not the right one. Documented inefficiency is not free money.
2. The bias is decaying in the wild — the 2025 coefficient is smaller and less statistically significant than in earlier years. This is the argument *for* the falsification gate, not against the strategy: a real, shrinking edge is exactly the condition under which an undisciplined pipeline manufactures false confidence fastest.

**Secondary edges worth their own signal families:**

- Contract prices become more accurate as markets approach closing — edge is generally better captured earlier in a market's life.
- A synthesis spanning twenty academic studies (2006–2026) identifies **informed-participant flow near event resolution** as a distinct signal family — sharp, size-driven moves late in a contract's life as a feature, not just noise.
- The same synthesis identifies **passive liquidity provision** on Kalshi — resting two-sided markets, functioning closer to an underwriter than a forecaster — as a separate, real sleeve, with aggregate positive returns around $29 million across a single NFL season. This should be its own falsification-gated strategy family with its own acceptance criteria, not scored against directional signals — the return driver (spread plus fee asymmetry) is structurally different from calibration beating the crowd.
- **Cross-platform divergence** against Polymarket is real and studied, but a gross spread must be adjusted for fees, slippage, liquidity, access rules, and settlement-rule mismatch before it's anything more than a consensus-divergence signal — and it requires capital and infrastructure on a second venue, outside a Kalshi-only mandate. File it as opportunistic, third-priority monitoring.

## The Regulatory Perimeter

A live constraint, not a checkbox. Political contracts have settled federal status. Sports contracts don't — they're contested state-by-state under gambling law rather than federal derivatives law. As of July 2026, Kalshi is restricted or limited in **Arizona, Massachusetts, Maryland, Michigan, Montana, New Jersey, Nevada, and Ohio**, against a backdrop of a March 2026 Arizona criminal filing carrying 20 misdemeanor counts and a Massachusetts civil suit dating to September 2025.

**Texas is unrestricted** — Kalshi is legal and available for eligible users 18 and older. Jurisdiction resolves cleanly here.

Pull the state list into the compliance layer as a periodically-refreshed input, the same way cap_i gets refreshed — not a one-time assumption baked in once.

## The Execution Substrate

All market data — prices, order books, market details, series information, historical data — is publicly available without authentication, so the entire research and falsification-gate backtesting layer can run without touching account credentials at all. Authentication is required only for placing orders, viewing portfolio positions, checking balance, and accessing trade history, via API-key plus per-request RSA-PSS signing rather than a JWT flow.

Rate limits are tiered and largely volume-earned: public data runs around 30 requests/second, authenticated operations around 10/second at base tier, scaling toward roughly 100 sustained orders/second at the Premier tier and above. WebSocket is **read-only** for market data — order placement and cancellation must go through REST regardless of tier — and each account is capped at five concurrent WebSocket connections, meant to be multiplexed rather than multiplied.

Stated plainly across multiple independent sources: rate limits make true HFT impractical; the API is better suited to medium-frequency or event-driven strategies. **This is not a constraint on this build — it's confirmation of fit.** An agentic-hypothesis, decay-tracked architecture was never trying to win a latency race, and Kalshi's own rate-limit design guarantees no competitor can buy one either. The edge here is genuinely about who has the better probability estimate, not who has the faster wire.

A sandboxed demo environment exists ahead of production trading — the natural target for the paper-trading harness before `live_execution_enabled` ever flips to true.

## The Refined Objective

The north-star architecture doesn't change shape. One term gets specified precisely, and sizing gets a maker/taker branch:

```
argmax_w [ w⊤(p̂ − p_market − fee(P)) − λw⊤Σw ]   s.t.   w_i ≤ cap_i (ghost-listing-adjusted)
```

where `fee(P) = 0.07·P(1−P)` for a taker fill and `fee(P) = 0.0175·P(1−P)` for a maker fill that gets hit — a known, price-dependent haircut on the raw edge, distinct from the impact curve correctly dropped earlier and from the capacity constraint, which stays.

Maker-vs-taker becomes a per-signal execution decision: compare the fee saved by waiting against the decay rate already tracked for that signal family. A system that already estimates how fast an edge decays is exactly the system that should decide whether it can afford to wait for a passive fill.

## Sequencing Against the Existing Stack

**Near term.** World Cup volume is live on the exact category already prioritized. MLB is mid-season. NFL preseason is weeks out. NBA is in the offseason — prop liquidity there will be thin until fall, so sequence the reusable ATP/NBA/NFL/MLB feature pipelines accordingly rather than treating "sports props" as one undifferentiated bucket; the adaptation remains output-layer, not feature-layer. Re-run the ghost-listing diagnostic against current depth before cap_i gets locked in.

**Medium term.** Instrument near-resolution informed-flow detection and passive liquidity provision as their own falsification-gated families, graded on their own acceptance criteria rather than the directional-signal bar.

**Longer term**, unchanged from the existing flywheel logic: economics and politics once resolved base rates accumulate — those categories resolve in quarters, and the gate needs the sample size sports already delivers weekly.

---

## Sources

**Market structure & volume**
- Kalshi — Wikipedia. https://en.wikipedia.org/wiki/Kalshi
- "Kalshi Booms on Sports," SGI Europe. https://www.sgieurope.com/technology/kalshi-booms-on-sports/121847.article
- "Polymarket vs Kalshi: Which Prediction Market Should You Use in 2026?," FOX Sports. https://www.foxsports.com/stories/betting/polymarket-vs-kalshi

**Fees**
- "How Kalshi Makes Money," RevenueMemo. https://www.revenuememo.com/p/how-does-kalshi-make-money
- "Kalshi Fees 2026: Complete Guide," PredictionHunt. https://www.predictionhunt.com/blog/kalshi-fees-complete-guide-2026
- "Kalshi Fees 2026: Fee Schedule, Maker & Taker Rates Explained," pm.wiki. https://pm.wiki/learn/kalshi-fees-explained
- "Kalshi Fees: Understanding Kalshi Trading Fees in 2026," Deadspin. https://deadspin.com/prediction-markets/kalshi/fees/

**Regulatory**
- "Kalshi Election Markets 2026," TheLines.com. https://www.thelines.com/prediction-markets/kalshi/election/
- "Where is Kalshi Legal in the U.S.? Full State-by-State Guide (2026)," Saturday Down South. https://www.saturdaydownsouth.com/prediction-markets/kalshi-promo-code/legal-states/

**Academic research on pricing efficiency**
- Whelan, K. et al., "Makers and Takers: The Economics of the Kalshi Prediction Market." https://www.karlwhelan.com/Papers/Kalshi.pdf
- "Trading Strategies for Prediction Markets," Frenzy Capital (Medium). https://medium.com/@FrenzyCapital/trading-strategies-for-prediction-markets-4025a050e2e2
- "Kalshi Prediction Market: 7 Proven Strategies to Make Profit," LaikaLabs. https://laikalabs.ai/prediction-markets/kalshi-prediction-market-trading-strategies
- "Systematic Edges in Prediction Markets," QuantPedia. https://quantpedia.com/systematic-edges-in-prediction-markets/
- "Prediction Market Arbitrage Calculator 2026," AhaSignals. https://ahasignals.com/research/prediction-market-arbitrage-strategies/

**API & infrastructure**
- "Rate Limits and Tiers," Kalshi API Documentation. https://docs.kalshi.com/getting_started/rate_limits
- "Kalshi API Guide 2026," pm.wiki. https://pm.wiki/learn/kalshi-api
- "Kalshi Order Book API Explained," QuantVPS. https://www.quantvps.com/blog/kalshi-order-book-api-endpoints-explained

**Event context**
- "2026 FIFA World Cup Knockout Stage," Wikipedia. https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
