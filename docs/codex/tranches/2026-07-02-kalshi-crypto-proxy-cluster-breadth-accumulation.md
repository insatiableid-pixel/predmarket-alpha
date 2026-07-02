# 2026-07-02 Kalshi Crypto Proxy Cluster Breadth Accumulation

## Change

- Changed CCD current-candidate selection in `scripts/kalshi_crypto_proxy_capacity_correlation_decay.py` from time-first truncation to cluster-round-robin selection.
- CCD now reports `candidate_selection_policy`, `candidate_cluster_count`, and `candidate_cluster_counts`.
- Added tests proving dense same-cluster rows cannot starve independent clusters under the ticker cap.
- Tightened signal-factory routing so a cluster-control upstream block caused by decay routes to decay/sample accumulation rather than another CCD implementation tranche.

## Live Run

Ran `make kalshi-crypto-proxy-observation-watch-once`.

Latest CCD result:

- Status: `crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration`.
- Candidate selection policy: `cluster_round_robin`.
- Current candidates: 9.
- Candidate clusters: 9.
- Orderbooks: 9.
- Orderbook errors: 0.
- Positive-depth rows: 3.
- Positive clusters: BTC, ETH, and XRP fifteen-minute up/down buckets.
- Positive-depth contracts: `41177.87`.
- Positive-depth cost: `16219.659089`.
- Largest positive cluster: `BTC|fifteen_minute_up_down|2026-07-02T05:15Z`.
- Largest positive cluster share: `0.9060260121`.
- Capacity status: `capacity_depth_positive`.
- Decay status: `decay_survival_blocked`.
- Replay decay status: `recent_bucket_below_random`.
- Usable rows: 0.

Latest cluster-control result:

- Status: `crypto_proxy_correlation_cluster_control_blocked_upstream_ccd`.
- Positive clusters: 3.
- Required positive clusters: 3.
- Controlled-depth cost: `1409.966306669`.
- Largest controlled cluster share: `0.35`.
- Usable rows: 0.

## Route

Latest signal-factory status: `signal_factory_crypto_proxy_decay_survival_blocked`.

Latest macro next tranche: accumulate repeated settled buckets and keep the crypto proxy signal blocked until decay survival is passing.

Stop before lowering decay/sample thresholds, paper overlay, sizing, execution, or account/order paths.

## Verification

- `.venv/bin/python -m pytest -q -s tests/test_kalshi_crypto_proxy_capacity_correlation_decay.py tests/test_kalshi_crypto_proxy_correlation_cluster_control.py tests/test_kalshi_signal_factory_status.py tests/test_codex_macro_router.py tests/integration/test_local_artifact_replay.py`
- `.venv/bin/ruff check scripts/kalshi_crypto_proxy_capacity_correlation_decay.py scripts/kalshi_signal_factory_status.py tests/test_kalshi_crypto_proxy_capacity_correlation_decay.py tests/test_kalshi_signal_factory_status.py`
- `make lint-baseline-check`
- `make kalshi-crypto-proxy-observation-watch-once`
- `make kalshi-signal-factory-status`
- `make macro-route`
