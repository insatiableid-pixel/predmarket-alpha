# 2026-07-03 MLB Platform Sports Model Bridge

## Summary

Predmarket now accepts MLB-platform baseball model output as an optional external research artifact, then treats it as a competing sports model candidate inside the same Kalshi signal-factory falsification/replay machinery.

This is deliberately an artifact bridge, not a code dependency on `/home/mrwatson/projects/mlb-platform`.

## What Changed

- Added an optional safe-artifact bridge to `scripts/kalshi_sports_proxy_feature_packet.py`.
- Default bridge path: `/home/mrwatson/manual_drops/mlb_platform_signal_features/mlb_platform_sports_model_latest.json`.
- Accepted artifacts must be research-only, execution-disabled, and free of account/order/DB paths.
- Rows join by exact `contract_ticker`, then by `league|external_game_id|selected_code`, then by `event_ticker|selected_code`.
- Attached bridge fields flow from feature packet to observations and settled label rows.
- Sports falsification now evaluates two model candidates:
  - `strength_win_prob_directional_accuracy`
  - `mlb_platform_model_directional_accuracy`
- Sports replay now auto-selects the best FDR-passed candidate by q-value, with an optional preferred-model override via `KALSHI_SPORTS_PROXY_REPLAY_PREFERRED_MODEL_ID`.
- Replay rows preserve `source_model_id` and, for the MLB-platform model, `source_model_probability`.

## Guardrails

- Missing MLB-platform artifacts are optional warnings, not blockers.
- Unsafe MLB-platform artifacts are ignored.
- No import from the MLB-platform repo was added.
- No paper overlay, sizing, execution, approval queue, account, order, or DB path was introduced.
- Every generated research row remains `usable=false`.

## Verification

- `make test-unit`: 620 passed, 11 deselected.
- `make test-integration`: 11 passed.
- Focused sports bridge suite: covered feature attachment, missing optional bridge, observation/label propagation, separate falsification candidate, and replay auto-selection.
- `make lint-baseline-check`: OK, lint 1421/1422, format 92/94.
- `make tech-debt-check`: OK, 22/22.
- `make file-sizes-check`: OK, no new oversized files.
- `make modularize`: OK, 2 contracts kept, 0 broken.
- `make feature-flags-check`: OK.
- `make validate-agents`: OK.
- `make deptry`: advisory only, 169 dependency findings reported.

## Next Step

Produce a real MLB-platform artifact at the bridge path with contract-keyed predictions for current baseball Kalshi markets, then let the sports observation/label loop accumulate settled labels. The bridge model should earn capital only by beating the greenfield strength model through OOS/FDR, replay cost, capacity, correlation, and decay gates.
