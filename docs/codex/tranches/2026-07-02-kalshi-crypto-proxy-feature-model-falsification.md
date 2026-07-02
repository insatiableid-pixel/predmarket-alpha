# Kalshi Crypto Proxy Feature Model Falsification

Date: 2026-07-02

## Outcome

Built and ran the first feature-model falsification harness for the crypto proxy lane.

Latest status: `crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels`.

## Evidence

- Raw label rows: 36.
- Independent settled contract labels: 9.
- Duplicate label rows: 27.
- Research candidates: 0.
- Minimum independent labels: 30.
- Minimum OOS labels: 10.

## Learned

The label path works: true Kalshi settlements attached to exact observed crypto contract tickers. The model gate correctly refused to promote anything because repeated observations of the same contract are not independent labels.

## Artifacts

- `docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.json`
- `docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.md`
- `docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.csv`
- `/home/mrwatson/manual_drops/kalshi_crypto_proxy_labels/crypto_proxy_labels_latest.json`

## Next Route

`make macro-route` recommends predmarket:

`signal_factory_crypto_proxy_feature_model_insufficient_labels`

Next tranche: continue crypto proxy observation accumulation until enough independent settled contract labels exist for OOS/FDR testing.

## Guardrail

No calibrated probability, EV, sizing, or execution is emitted by this report.
