# Kalshi EV Calibrated Probability Manual-Drop Contract

Use this contract when a repo or worker has a validated calibrated probability for an exact Kalshi contract.

Drop JSON files outside the repos under:

`/home/mrwatson/manual_drops/kalshi_ev_probabilities/`

The central ledger reads these files with `make kalshi-ev-ledger`. It never calls providers or execution paths while reading them.

## Required Shape

```json
{
  "research_only": true,
  "execution_enabled": false,
  "safety": {
    "market_execution": false,
    "account_or_order_paths": false
  },
  "rows": [
    {
      "contract_ticker": "KXMLBGAME-26JUN291835CWSBAL-CWS",
      "side": "yes",
      "calibrated_probability": 0.534,
      "calibrated_probability_source": "model_or_artifact_name",
      "calibration_status": "validated_calibrated_probability",
      "probability_uncertainty": 0.025
    }
  ]
}
```

## Rules

- `contract_ticker` must be an exact Kalshi contract ticker.
- `side` must be `yes` or `no`.
- `calibrated_probability` must be between `0` and `1`.
- `calibration_status` must be one of:
  - `validated_calibrated_probability`
  - `review_only_calibrated_probability`
- Only `validated_calibrated_probability` can remove the validation blocker.
- Sportsbook no-vig, market midpoint, consensus price, or unvalidated model output must not be relabeled as calibrated probability.
- Raw provider payloads stay outside repos.
- No account, order, execution, staking, sizing, or live-money fields belong in this file.

## Run

```bash
cd /home/mrwatson/projects/predmarket-alpha
make kalshi-ev-ledger
```

The ledger records the source artifact path and SHA-256 hash on every row that uses a dropped probability.
