# 2026-07-02 Kalshi Crypto Proxy Research Candidate Replay

## Plain English

The crypto proxy signal finally had enough true Kalshi settlement labels to be tested. It looked mildly real on a first pass: 54 correct out of 92 OOS decisions, with BH q around 0.059.

I did not let that become a pick. I converted the raw 58.7% hit rate into a conservative lower-bound selected-side probability of 50.12%, then replayed each historical selected contract against the actual buy-side hurdle: YES ask, NO ask derived from `1 - yes_bid`, plus the Kalshi fee estimator.

The replay found 156 positive cost-adjusted historical rows out of 306 costed rows. It still produced 0 usable rows because capacity depth, correlation, and decay are not proven.

## Artifacts

- `scripts/kalshi_crypto_proxy_research_candidate_replay.py`
- `tests/test_kalshi_crypto_proxy_research_candidate_replay.py`
- `docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.json`
- `docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.md`
- `docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.csv`
- `NEXT_DIRECTIVE_2026-07-02_KALSHI_CRYPTO_PROXY_RESEARCH_CANDIDATE_REPLAY.md`
- `COMPLETION_REPORT_2026-07-02_KALSHI_CRYPTO_PROXY_RESEARCH_CANDIDATE_REPLAY_FULFILLED.md`

## Current Truth

- Status: `crypto_proxy_research_candidate_replay_blocked_predeployment_gates`
- Independent labels: `309`
- OOS selected rows: `92`
- Conservative probability: `0.5012128514`
- Costed replay rows: `306`
- Positive cost-adjusted rows: `156`
- Usable rows: `0`

## Next Tranche

Build capacity-depth, correlation-cluster, and decay-survival gates. Stop before sizing, execution, account/order paths, staking guidance, or using replay rows as live edges.
