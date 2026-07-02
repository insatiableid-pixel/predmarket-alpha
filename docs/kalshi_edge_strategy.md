# Kalshi Edge Strategy Memo

**Date:** 2026-06-16  
**Status:** Living document; research-only operating memo — supersedes Section 4 taxonomy in `kalshi_edge_report_2026-06-16.md`  
**Scope:** Strategic framework for Kalshi edge extraction. Agent report serves as data appendix.  
**Next review:** After 90-day paper research cycle or major catalog shift.

---

## Context

The Hermes agent run (2026-06-16) cataloged 20,000 Kalshi markets, scored 3,583 meaningful ones, and produced a softness ranking. The agent's scoring conflated two structurally different sources of softness — absence of a market-maker and presence of a mispriced market-maker — into a single S(m) number. That distinction drives completely different model architectures, build timelines, and capacity profiles. This memo corrects that conflation and establishes the operative strategic framework.

**Agent report:** `data/kalshi_edge_report_2026-06-16.md`  
**Scored catalog:** `data/kalshi_scored_refined_2026-06-16.json`  
**Raw catalog:** `data/kalshi_catalog_2026-06-16.jsonl`

## Active Operating Guardrail

This memo is strategy context for a research desk, not authorization to trade. In the current macro phase, all Type 2 outputs are paper/review artifacts only: no account access, no order construction, no execution path, no staking instruction, and no tradable claim. Any historical capacity, bankroll, or sizing language below is archived planning context until a separate approval gate explicitly enables execution.

---

## Four-Type Exploitation Taxonomy

### Type 1 — No Market-Maker

**Why it's soft:** Open interest exists but no automated pricing agent is maintaining a fair mid. The spread is not a transaction cost — it is evidence of an absent counterparty.

**Signal:** Spread > 40% of mid, OI > $10, volume = $0.

**Mechanism:** Pure information arbitrage. Build any systematic estimate and you beat the book by construction. The bar is not beating a sharp counterparty; it is existing as a counterparty at all.

**Edge formula:**
```
EV = p̂ - ask                    # long YES
EV = bid - (1 - p̂)              # long NO
Entry threshold: EV > max(0.03, 2 × σ_model)
```

**Categories:** AI benchmarks, niche entertainment (Emmy/Oscar nominations), thin political primaries.

**Capacity:** $500–2,000 across 5–10 simultaneous markets. Hard ceiling — total OI in the AI benchmark cluster is under $200. Once the mispricing is taken, the market corrects or resolves. Non-recurring per contract.

**Build cost:** Low. A leaderboard scraper, a GoldDerby odds extractor, or a poll aggregator suffices. No ensemble required.

**Key risk:** Resolution spec ambiguity. Verify minimum vote thresholds and exact resolution source before entering. The AI benchmark contracts in particular must be checked for whether they resolve on current rank at close vs. requiring a minimum sample size.

---

### Type 2 — Sharp Reference Price Exists, Kalshi Hasn't Synced

**Why it's soft:** DraftKings, FanDuel, and Pinnacle are pricing equivalent propositions with sharp, high-volume books. Kalshi's user base skews prediction-market native — not Statcast users. Kalshi periodically diverges from sportsbook consensus and reverts.

**Mechanism:** The fair value is freely available (sportsbook consensus no-vig midpoint). The model's job is not to beat DraftKings — it is to monitor the spread between Kalshi's implied probability and the no-vig sportsbook mid, and fade the gap when it clears the net edge threshold.

**No-vig midpoint extraction:**
```python
# For a two-outcome market with sportsbook prices p_yes_dk, p_no_dk
# (as implied probabilities including vig):

overround = p_yes_dk + p_no_dk - 1.0
mid_yes   = p_yes_dk - (overround / 2)
mid_no    = p_no_dk  - (overround / 2)
# mid_yes + mid_no == 1.0 by construction
```

**Net edge formula (the operative filter):**
```
net_edge = |kalshi_mid - no_vig_sportsbook_mid| 
           - kalshi_half_spread 
           - σ_model

Entry threshold: net_edge > 0.10
```

The 0.10 floor is derived from the MLB Statcast irreducible model error floor of σ_model ≈ 0.06, plus the Kalshi half-spread on props (typically 0.02–0.04). A 0.03 raw divergence does not clear the bar. Expect 5–15 actionable MLB signals per day at the 0.10 threshold, not 30–40.

**Model architecture note:** The existing ATP and NBA analytics platforms supply the *feature pipeline* (player tracking, matchup data, recent form, lineup context). The *output head* is new and specific to Kalshi prop markets:

- **Sportsbook spread/win-probability models** → not reusable as-is
- **Kalshi prop markets** → Poisson count model: `P(X ≥ k)` where X is a discrete counting variable (threes made, hits, strikeouts, strikeouts allowed)
- Loss function: binary log-loss on a threshold over a Poisson-distributed count
- **Estimate:** 2-week adaptation, not a plug-in. First target: WNBA 3-point props (small player pool, stable Poisson rates, demonstrably unpriced)

**Categories:** MLB props (241 markets, daily resolution), NBA/WNBA props (151), tennis props (21), soccer match props (subset of 721).

**Capacity:**
```
241 MLB props × $100 avg position × 20% simultaneous utilization = ~$4,800/day deployed
Add NBA/WNBA (151 × $75 × 20%)                                  = ~$2,265
Add tennis (21 × $75 × 20%)                                     = ~$315
Total Type 2 capacity:                                           ~$7,400
```

**Build cost:** Medium. Sportsbook odds ingestion, no-vig extractor, divergence monitor, Poisson count head on top of existing player tracking pipeline.

**Sportsbook data source note:** The Odds API enterprise tier ($1,000+/mo) is required for 15-minute polling across 241+ markets. Alternatives: Pinnacle API (free for personal use, near-zero-vig, simpler no-vig extraction since Pinnacle runs ~2% vig) or DraftKings internal API scraping (zero cost, higher maintenance). Pinnacle is the recommended starting source — cleaner data, no vig-removal step needed, and free.

**Flywheel:** 241 daily-resolving MLB markets generates a calibration database fast. 90 days = ~21,000 resolved bets. ECE-gated model retirement is operational within one season. This is the primary reason Type 2 is Priority 1 despite not having the highest per-bet edge.

---

### Type 3 — Long-Dated Contracts with No Active Maintenance

**Why it's soft:** Corporate earnings and long-dated macro markets are priced at listing based on stale consensus and never updated. A quarterly earnings surprise that would instantly reprice a near-dated contract takes weeks to propagate into a 2028 binary. No professional trader has incentive to maintain a position in a $30 OI market with an 18-month horizon.

**Mechanism:** Build a nowcasting model that ingests quarterly earnings releases (EDGAR) and updates the implied binary probability for the 2028 annual target each quarter. Compete against a vacuum — literally zero other participants are doing this.

**Edge formula:**
```
EV = p̂_nowcast - ask            # long YES
EV = bid - (1 - p̂_nowcast)     # long NO
Entry threshold: EV > 0.15      # wider threshold: higher model uncertainty on 18-month horizon
```

**Build layers (in order of priority):**

1. **EDGAR scraper + consensus beat-rate model** — baseline. Ingest 10-Q/10-K filings, map to Kalshi binary thresholds, compute historical beat rates by metric type and company. This alone beats the current Kalshi price on most long-dated corporate markets, because the current price is stale at listing.

2. **Structured consensus data** — Visible Alpha or FactSet for analyst consensus by metric. Not free (~$500-2,000/mo depending on coverage). Can be approximated at lower cost by scraping sell-side summaries, but that introduces noise.

3. **Alt-data nowcasting layer** — web traffic (SimilarWeb/Semrush), credit card transaction data (Second Measure, expensive), job postings as leading indicator (free via BLS/Indeed API). This is where genuine edge concentration lives, and where build cost is highest.

**Recommended sequence:** Ship layers 1 and 2 first. Layer 1 alone generates real edge. Layer 3 is a Phase 2 expansion after calibration data confirms the base model's ECE.

**Categories:** Corporate earnings (50 markets, 2028 expiry), long-dated macro stats, select Fed policy outrights.

**Capacity:**
```
50 corporate earnings × $100 avg position × 30% utilization = ~$1,500
10-15 long-dated macro/Fed markets × $150 avg              = ~$1,875
Total Type 3 capacity:                                      ~$3,375
```

**Correlation risk:** If a macro shock reprices the entire earnings universe simultaneously (e.g., a recession signal), correlated long-dated exposure creates drawdown that position caps per market don't capture. Enforce a factor-level cap: total Type 3 exposure ≤ 15% of bankroll regardless of per-market sizing. This supersedes the per-category cap in the agent report.

---

### Type 4 — Structural Avoid

**Categories and reasoning:**

| Category | Reason to Avoid |
|----------|----------------|
| Crypto price targets | Trivially arbitrageable vs. Deribit/Binance options; populated by professionals with co-location and sub-millisecond feeds. Edge requires microstructure alpha this stack doesn't have. |
| Weather events | GFS/ECMWF are public. Fair value is freely available to all participants. Edge window after model update is minutes. Possible alpha only in ensemble disagreement — requires physical meteorology expertise. |
| High-volume political | Presidential races, major Senate races (>$500/day volume). 538-style aggregators are already in the price. Competing requires genuinely proprietary polling data or methodology improvement over published aggregators. Neither is cheap. |
| Standard soccer match winners | World Cup match *outcomes* (not props) are efficiently priced by offshore books. The over/under goal props are Type 2; the winner markets are Type 4. |

Crypto is not zero-edge — it is wrong-risk-adjusted for this stack. Do not revisit until a dedicated microstructure pipeline exists.

---

## Priority Stack

| Priority | Type | Category | Rationale |
|----------|------|----------|-----------|
| 1 | Type 2 | MLB/NBA/WNBA/Tennis props | Fastest calibration flywheel (daily resolution), lowest model build from existing infrastructure, highest capacity |
| 2 | Type 3 | Corporate earnings nowcasting | Zero competition, recurring alpha each earnings cycle, asymmetric risk-reward vs. build cost |
| 3 | Type 1 | Opportunistic monitor (AI benchmarks, thin entertainment) | Zero build beyond a divergence monitor; freeroll when signals appear |
| 4 | Type 2 | Soccer over/under props (World Cup + ongoing leagues) | Real edge, but requires automated execution for sub-1h signal windows — defer until execution layer is built |
| — | Type 4 | Crypto, weather, high-volume political | Avoid until stack has specific infrastructure to compete |

---

## Capacity Summary

```
Type 1 (opportunistic)         $500  – $2,000
Type 2 (sports props)          $4,800 – $9,600
Type 3 (long-dated nowcasting) $1,500 – $3,375
──────────────────────────────────────────────
Total addressable capacity     $6,800 – $14,975
```

The $5–15K ceiling is a Kalshi liquidity constraint, not a model constraint. Moving more than ~$200 into any single thin market closes the gap against yourself. Revisit capacity ceiling quarterly as Kalshi's total platform volume grows. Cross-list validated signals to Polymarket and PredictIt (deeper books, same model) once ECE scores are gated and stable.

---

## Build Sequence

### Weeks 1–2: Type 2 Foundation
- [ ] Sportsbook odds ingestion (Pinnacle API preferred; DraftKings scrape as fallback)
- [ ] Kalshi props monitor (poll divergence vs. no-vig mid every 15 minutes)
- [ ] Poisson count output head on existing player tracking pipeline (start: WNBA 3PT props)
- [ ] No-vig midpoint extractor
- [ ] Paper research ledger with full review logging

### Weeks 3–4: Type 2 Calibration + Type 1 Monitor
- [ ] MLB Statcast feature extraction → Poisson count model
- [ ] ECE tracking per bucket, rolling Brier score
- [ ] Type 1 divergence monitor: flag any market with spread > 40%, OI > $10, vol = $0
- [ ] AI benchmark leaderboard scraper (daily, LMArena Math Arena + Artificial Analysis)

### Weeks 5–6: Type 3 Build
- [ ] EDGAR scraper: 10-Q/10-K ingestion, map to Kalshi binary thresholds
- [ ] Historical beat-rate model by metric type and company
- [ ] Consensus data integration (Visible Alpha or scraper approximation)
- [ ] First paper positions in corporate earnings cluster

### Weeks 7–8: Hardening + Expansion
- [ ] Anti-bleed controls: 15% drawdown circuit breaker, daily loss limit (-3% allocated bankroll)
- [ ] Factor-level cap enforcement for Type 3 correlated exposure
- [ ] Soccer props execution layer (for sub-1h signal windows)
- [ ] 90-day calibration review: prepare top models for human review; no automatic live promotion

---

## Edge Formulas Reference

```python
# No-vig sportsbook midpoint
overround   = p_yes_dk + p_no_dk - 1.0
mid_yes     = p_yes_dk - (overround / 2)

# Type 2 net edge
net_edge    = abs(kalshi_mid - mid_yes) - kalshi_half_spread - sigma_model
entry_long  = (kalshi_ask < mid_yes) and (net_edge > 0.10)
entry_short = (kalshi_bid > mid_yes) and (net_edge > 0.10)

# Execution sizing
# Disabled in the active research phase.
# Type 2 matcher outputs must not emit stake, bankroll, Kelly, or order fields.
```

---

## Notes and Open Questions

- **Deferred execution review:** Execution API questions are out of scope until a separate approval gate enables live work.
- **WNBA 3PT props as first paper calibration target:** Small player pool (~12 relevant shooters), Poisson rates stable over a season, markets demonstrably unpriced. Ideal first calibration set.
- **MiMo resolution spec:** Before any Type 1 entry on `KXMATHAI-26JUN30-MIMO`, verify whether the LMArena Math Arena requires a minimum vote count for resolution. If so, MiMo's thin Arena coverage may disqualify it from resolving favorably regardless of raw benchmark performance. Per Kalshi resolution rules, tiebreakers are Arena Score → vote count → release date. No explicit minimum vote threshold stated, but Arena's Bayesian ranking algorithm effectively requires sufficient comparisons for a stable #1 rank.
- **Polymarket/PredictIt cross-listing:** Once ECE scores are gated on Type 2 sports props (target: ECE < 0.06 over 50 resolutions), evaluate cross-listing the same signals on Polymarket (crypto-settled) and PredictIt (capped at $850/contract) for capacity expansion.

---

*Memo version: 1.0.0*  
*References: `kalshi_edge_report_2026-06-16.md` (agent output), `kalshi_scored_refined_2026-06-16.json`*
