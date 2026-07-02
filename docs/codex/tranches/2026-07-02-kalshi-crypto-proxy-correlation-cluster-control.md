# 2026-07-02 Kalshi Crypto Proxy Correlation Cluster Control

## Change

- Added `scripts/kalshi_crypto_proxy_correlation_cluster_control.py`.
- Added `make kalshi-crypto-proxy-correlation-cluster-control`.
- Inserted the cluster-control target into `make kalshi-crypto-proxy-observation-watch-once` after CCD and before signal-factory status.
- Wired `scripts/kalshi_signal_factory_status.py` to consume the cluster-control artifact through the hermetic `Artifacts` bundle.
- Wired `scripts/codex_macro_router.py` to route cluster-control states separately from CCD states.
- Added `docs/codex/macro/kalshi-agentic-falsification-architecture.md`.

## Current Artifact Result

Latest cluster-control status: `crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters`.

- CCD capacity status: `capacity_depth_positive`.
- CCD decay status: `decay_survival_pass`.
- Positive-depth rows: 37.
- Positive-depth cost: `5471.7446`.
- Positive clusters: 1.
- Required positive clusters: 3 under `max_cluster_share=0.35`.
- Largest positive cluster: `BNB|range|2026-07-02T05:00Z`.
- Largest positive cluster share: `1.0`.
- Controlled-depth cost: `0.0`.
- Usable rows: 0.

## Route

Latest signal-factory status: `signal_factory_crypto_proxy_cluster_breadth_blocked`.

Latest macro next tranche: accumulate diversified current crypto proxy candidates across independent asset/family/close-time clusters before any paper probability overlay.

Stop before reducing breadth requirements, paper overlay, sizing positions, execution, or account/order paths without an explicit policy review.

## Verification

- `.venv/bin/python -m pytest -q -s tests/test_kalshi_crypto_proxy_correlation_cluster_control.py tests/test_kalshi_signal_factory_status.py tests/test_codex_macro_router.py tests/integration/test_local_artifact_replay.py`
- `.venv/bin/ruff check scripts/kalshi_crypto_proxy_correlation_cluster_control.py scripts/kalshi_signal_factory_status.py tests/test_kalshi_crypto_proxy_correlation_cluster_control.py tests/test_kalshi_signal_factory_status.py tests/test_codex_macro_router.py tests/integration/test_local_artifact_replay.py`
- `make kalshi-crypto-proxy-correlation-cluster-control`
- `make kalshi-signal-factory-status`
- `make macro-route`
