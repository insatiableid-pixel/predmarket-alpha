# 2026-07-07 Fable Crypto Weather Probability Path Config

## Landing

Removed machine-specific manual-drop defaults from:

- crypto proxy feature, observation, falsification, replay, and CCD scripts
- weather proxy feature, observation, falsification, replay, and CCD scripts
- probability breadth scout
- EV queue robustness

Defaults now derive local evidence paths from `manual_drop_path()`. Existing CLI overrides, Make targets, and research-only semantics are unchanged. Two unused variables in the touched weather feature-packet script were removed while keeping behavior unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py -q` -> `15 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check --extend-ignore C901 ...` over touched files -> `All checks passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check` -> `OK`
- Hardcoded root scan over touched runtime files found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- Make dry-runs passed for all touched script targets.
- `git diff --check` clean for touched files.
