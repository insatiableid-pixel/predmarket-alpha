# Always-On Consensus Collector Target

Date: 2026-07-04

## Objective

Continue implementing Claude's advice by making the always-on collector feed the sports sharp-consensus evidence loop directly. The previous default collector ran legacy sports paper burn-in plus crypto, but did not explicitly run the timestamp-matched no-vig consensus watch-once target.

## Landing

- Added a `sports_consensus` collector target in `scripts/kalshi_always_on_collector.py`.
- The new target runs `make kalshi-sports-consensus-observation-watch-once`, which refreshes the strict consensus feed, archives observations, probes exact public Kalshi settlements, and reruns consensus falsification.
- Changed default collector targets to `sports_consensus,crypto`.
- Left the older heavier `sports` paper burn-in target available but opt-in via `KALSHI_ALWAYS_ON_COLLECTOR_TARGETS=sports_consensus,sports,crypto`; this avoids making the default collector fail on public endpoint `429` bursts from the legacy sports proxy loop.
- Updated collector tests to cover the new target.

## Latest Run

`make kalshi-always-on-collector-once` now exits 0:

- Collector status: `kalshi_always_on_collector_ready`
- Targets: `sports_consensus`, `crypto`
- Safe artifacts: `2/2`
- Total label count: `1234`
- Total due count: `7745`
- Cadence: `60` seconds because due settlement rows are present

Sports consensus target:

- Target status: `pass`
- Artifact status: `sports_consensus_observation_loop_label_rows_ready`
- Total observations: `104`
- New observations: `26`
- Label rows: `16`
- New labels: `16`
- Due observation rows: `28`
- Valid preflight candidates: `40`

Sports consensus falsification remains correctly blocked:

- Status: `sports_consensus_falsification_blocked_insufficient_labels`
- Joined labels: `16`
- Independent labels: `8`
- OOS labels: `3`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Required minimums: `30` independent labels and `10` OOS labels

## Verification

- `.venv/bin/python -m pytest -s -q tests/test_kalshi_always_on_collector.py` -> `6 passed`
- `.venv/bin/python -m ruff check scripts/kalshi_always_on_collector.py tests/test_kalshi_always_on_collector.py` -> pass
- `.venv/bin/python -m ruff format --check scripts/kalshi_always_on_collector.py tests/test_kalshi_always_on_collector.py` -> pass
- `make kalshi-always-on-collector-once` -> exit 0

## Guardrails

- Research-only remains true.
- No account/order/live execution path.
- No non-Kalshi labels.
- No threshold lowering.
- Consensus rows still require exact Kalshi ticker/side mapping and OOS/FDR before any promotion.

## Next Machine Action

Keep running the default collector until sports consensus reaches at least `30` independent labels and `10` OOS labels, then let `make kalshi-sports-consensus-falsification` decide whether any Kalshi-vs-consensus divergence rule survives FDR. In parallel, expand provider coverage beyond ATP/secondary MLB, especially soccer Asian sharp providers.
