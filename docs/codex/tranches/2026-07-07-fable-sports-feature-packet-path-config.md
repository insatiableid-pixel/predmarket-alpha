# 2026-07-07 Fable Sports Feature Packet Path Config

## Landing

Removed machine-specific manual-drop defaults from `scripts/kalshi_sports_proxy_feature_packet.py`.

The sports proxy feature packet now uses `manual_drop_path()` for:

- raw Kalshi universe snapshots
- raw sports proxy feature drops
- MLB-platform model bridge artifacts

CLI flags, Make target behavior, and research-only feature semantics are unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py -q` -> `13 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check scripts/kalshi_sports_proxy_feature_packet.py tests/test_kalshi_path_defaults.py` -> `All checks passed`
- Hardcoded root scan over `scripts/kalshi_sports_proxy_feature_packet.py` found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp make -n kalshi-sports-proxy-feature-packet` passed.
- `git diff --check` clean for touched files.
