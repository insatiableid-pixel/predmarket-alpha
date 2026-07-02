# 2026-07-02 Kalshi Crypto Proxy Capacity Correlation Decay

## Landing

- Added CCD as a first-class signal-factory artifact: `latest-kalshi-crypto-proxy-capacity-correlation-decay.{json,md,csv}`.
- `scripts/kalshi_signal_factory_status.py` now consumes the CCD artifact and advances routing past `replay_blocked_predeployment_gates`.
- `scripts/codex_macro_router.py` now routes post-CCD states to paper overlay, orderbook-depth accumulation, correlation-cluster control, decay accumulation, or safety audit.
- Writer isolation now prevents temp test outputs from silently overwriting production `latest-kalshi-signal-factory-status.*` or CCD latest pointers.

## Latest Result

- Full chain command: `make kalshi-crypto-proxy-observation-watch-once`.
- CCD status: `crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration`.
- Current candidates: 60.
- Public orderbooks: 60 with 0 errors.
- Positive-depth rows: 37.
- Positive-depth contracts: 492,018.
- Positive-depth cost notional: 5471.7446.
- Capacity status: `capacity_depth_positive`.
- Decay status: `decay_survival_pass`.
- Blocked gate: `correlation_cluster_limit`.
- Largest cluster: `BNB|range|2026-07-02T05:00Z`, share 1.0 vs max 0.35.
- Usable rows: 0.

## Guardrail

Research-only. No usable edge, no paper overlay, no sizing, no staking guidance, no account/order paths, and no execution.

## Verification

- Focused pytest with capture disabled: CCD/status/router/integration replay tests passed.
- Focused Ruff on touched CCD/status/test files passed.
- `make lint-baseline-check`: `OK  lint 1360/1362  format 77/77`.
- `make kalshi-crypto-proxy-observation-watch-once` refreshed CCD, signal-factory status, and macro route.

## Next

`kalshi_crypto_proxy_correlation_cluster_control`: add machine-readable cluster exposure controls before any paper probability overlay.
