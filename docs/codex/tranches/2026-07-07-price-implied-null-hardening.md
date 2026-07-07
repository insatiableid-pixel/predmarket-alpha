# Price-Implied Null Hardening

Date: 2026-07-07

## Landing

Implemented Fable's null-model correction for near-resolution informed flow:

- The falsification gate now tests against Kalshi's own price-implied probability for the predicted side.
- YES predictions use executable `best_yes_ask`, falling back only to timestamped `yes_mid`.
- NO predictions use executable `best_no_ask`, falling back only to `1 - yes_mid`.
- OOS p-values use exact Poisson-binomial survival over the non-identical price-implied probabilities.
- The old 50/50 p-value remains as `coin_flip_p_value_legacy` for audit only.
- Missing price-implied evidence blocks a candidate as `blocked_missing_price_implied_null`.
- `make kalshi-near-resolution-informed-flow-evidence-gate` now exposes `KALSHI_NEAR_RESOLUTION_FLOW_MICROSTRUCTURE_PATH`.

## Real Replay

Command:

```bash
python3 scripts/kalshi_near_resolution_informed_flow_evidence_gate.py \
  --write \
  --microstructure-path /home/mrwatson/projects/predmarket-alpha/docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json \
  --out-dir docs/codex/macro/kalshi-near-resolution-informed-flow-evidence-gate-latest
```

Result:

- Status: `near_resolution_informed_flow_falsification_ready_no_research_candidate`
- Flow rows: `6021`
- Research candidates: `0`
- Prior settlement-directional lane: `blocked_missing_price_implied_null`
- Settlement-directional OOS: `51/60`, accuracy `0.85`
- Settlement-directional mean price-implied null: `0.8932258065`
- Legacy coin-flip p-value: `1.54e-08`
- Price-implied p-value: `null` because some OOS selected-side null prices are missing

The practical result is automatic demotion: the prior coin-flip-looking near-resolution flow edge is not eligible for EV or paper promotion under the stricter null.

## Guardrails

- No thresholds lowered.
- No sportsbook-inferred settlement labels.
- No calibrated probabilities, EV rows, or paper stake emitted by this gate.
- No account/order/live execution paths touched.

## Verification

```bash
TMPDIR=/home/mrwatson/projects/predmarket-alpha-worktrees/fable-tick-recorder/.tmp \
  /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest \
  tests/test_kalshi_sports_microstructure_evidence.py::test_near_resolution_flow_uses_price_implied_null_not_coin_flip \
  tests/test_kalshi_sports_microstructure_evidence.py::test_near_resolution_flow_blocks_when_price_implied_null_missing \
  tests/test_kalshi_sports_microstructure_evidence.py::test_makefile_exposes_near_resolution_flow_microstructure_path_override \
  -q
```

Focused tests: `3 passed`.
