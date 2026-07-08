# Sports Consensus First FDR Test

## Landing

The 01:50Z sports blocker-clearance cycle moved the sharp no-vig consensus lane from inventory/accumulation into its first actual pre-registered OOS/FDR test.

## Evidence

- Consensus falsification status: `sports_consensus_falsification_ready_no_research_candidates`
- Joined labels: `964`
- Independent labels: `70`
- OOS labels: `21`
- Testable hypotheses: `1`
- Tested hypotheses: `1`
- FDR survivors: `0`
- Nearest next hypothesis: `sports_consensus_price_bucket_bias_bucket_0.50_0.70`, still `1` OOS label short
- Event velocity deficits: `96` labels, `35` OOS labels
- Fable audit: `15/15` implementation satisfied, `10/15` evidence satisfied
- Open Fable evidence ids: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`
- Paper: `0` usable rows, `$0` stake
- Live: `0` eligible rows
- Next blocker clock: `2026-07-08T02:10:00Z`

## Interpretation

This is a successful falsification event, not a betting signal. A pre-registered consensus bucket accumulated enough OOS evidence to enter FDR, and FDR produced no survivor. Existing downstream gates correctly left paper and live at zero.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook outcomes used as settlement labels.
- No EV, paper, or live promotion.
- No account/order/live path touched.

## Verification

- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-event-velocity-eta` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-blocker-clearance-cycle` -> exited `0`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make test-unit` -> `1442 passed, 15 deselected`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make test-integration` -> `14 passed`
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check` -> `OK lint 98/1422 format 21/94`
- Focused audit/blocker tests -> `17 passed`
- Touched-file Ruff -> passed
