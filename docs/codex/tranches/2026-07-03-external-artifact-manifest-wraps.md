# 2026-07-03 External Artifact Manifest Wraps

## Summary

Wrapped the highest-value donor outputs in strict external artifact manifests so they can pass the Kalshi EV engine preflight gate without becoming runtime dependencies or tradable probabilities.

Preflight moved from `0/10` safe artifacts to `12/13` safe artifacts and `910` admitted research rows. The only remaining blocked artifact is the optional missing MLB-platform live model drop at `/home/mrwatson/manual_drops/mlb_platform_signal_features/mlb_platform_sports_model_latest.json`.

## What Changed

- Added `predmarket/external_artifact_wrappers.py`.
- Added `scripts/kalshi_external_artifact_wrap.py`.
- Added Make target `kalshi-external-artifact-wrap`.
- Updated `kalshi-external-artifact-preflight` to auto-wrap donor artifacts before strict bridge validation.
- Updated `predmarket/external_artifact_bridge.py` to validate embedded `external_manifest` fields and fail when the donor source SHA no longer matches.
- Registered additional NFL donor surfaces:
  - contract-mapping overlay
  - calibrated-probability overlay
  - current historical-line backtest
  - calibration overlay

## Admitted Surfaces

- MLB closing-line comparison evidence.
- MLB settled-outcome validation evidence.
- NFL contract mapping overlay.
- NFL calibrated probability overlay.
- NFL fair-line review.
- NFL historical-line backtest.
- NFL calibration overlay.
- ATP forward-OOS report.
- ATP Kalshi match snapshot.
- NBA market-claim gate evidence.
- us-statarb public snapshot adapter audit.
- us-statarb daily gate summary.

## Current Artifact State

- Source inventory: `13` candidate artifacts, `12` existing, `8` donor repos.
- Wrap report: `12` wrapped artifacts, `910` wrapped rows, `1` blocked missing source.
- Preflight: `12` safe artifacts, `910` safe rows, `1` blocked missing source.
- Wrapped artifacts live outside the repo under `/home/mrwatson/manual_drops/predmarket_external_artifacts/`.

## Guardrails

- No donor repo is imported as a runtime dependency.
- No live execution, account, order, approval queue, or trading path was added.
- Wrapped rows remain research-only and `usable=false` / `paper_usable=false`.
- Source SHA validation means a donor artifact changed after wrapping will fail preflight until rewrapped.
- Missing donor sources remain blocked; no placeholder rows are invented.

## Verification

- Focused wrapper/preflight tests: 14 passed.
- `make kalshi-source-repo-inventory`: passed.
- `make kalshi-external-artifact-wrap`: passed.
- `make kalshi-external-artifact-preflight`: passed.
- `make test-unit`: 631 passed, 14 deselected.
- `make test-integration`: 14 passed.
- `make quality`: passed; deptry remains advisory and reports existing dependency findings.

## Next Step

Route the admitted wrapped rows into the family-specific falsification/replay adapters. The contract-keyed NFL overlay rows are the first candidate surface because they already carry exact Kalshi ticker/side mappings and calibrated probabilities, but they still need the hard falsification, all-in cost, capacity, correlation, and decay gates before any nonzero paper stake.
