# Kalshi EV Contract Mapping Manual-Drop Contract

Use this contract when a repo has model probabilities but does not yet emit exact Kalshi contract rows.

Drop JSON files outside the repos under:

`/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/`

The central ledger reads these files with `make kalshi-ev-ledger`. It never calls providers, writes databases, or touches account/order/execution paths while reading them.

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
      "source_repo_id": "nfl_quant_glm51_greenfield",
      "contract_ticker": "KXNFLGAME-26SEP09NESEA-SEA",
      "event_ticker": "KXNFLGAME-26SEP09NESEA",
      "side": "yes",
      "selection": "SEA",
      "market_type": "nfl_game_moneyline",
      "title": "Seattle to beat New England",
      "mapping_status": "verified_contract_mapping",
      "mapping_confidence": "operator_verified",
      "resolution_rule": "If Seattle wins, then the market resolves to Yes.",
      "resolution_rule_source": "operator_verified_local_kalshi_snapshot",
      "resolution_rule_status": "verified_official_terms",
      "executable_price": 0.4,
      "timing_status": "clean"
    }
  ]
}
```

## Rules

- `source_repo_id` must be one active macro repo id.
- `contract_ticker` must be an exact Kalshi contract ticker.
- `side` must be `yes` or `no`.
- `mapping_status` must be one of:
  - `verified_contract_mapping`
  - `review_only_contract_mapping`
- Only `verified_contract_mapping` can pass the mapping gate.
- `resolution_rule_status` must be `verified_official_terms`.
- Include an executable price source:
  - `executable_price`, or
  - `kalshi_ask`, or
  - an explicit all-in cost / payout multiple field supported by the ledger.
- `timing_status` should be `clean`, `pregame_clean`, or `not_applicable`.
- Do not include account, order, execution, staking, sizing, API key, or secret fields.
- Raw provider payloads stay outside repos.

## Pair With Probability Overlay

A contract mapping row creates an EV ledger row. It becomes calibrated only when a matching probability overlay exists under:

`/home/mrwatson/manual_drops/kalshi_ev_probabilities/`

The join key is exact:

- `contract_ticker`
- `side`

## Run

```bash
cd /home/mrwatson/projects/predmarket-alpha
make kalshi-ev-ledger
```

The ledger records source artifact paths and SHA-256 hashes for both mapping and probability overlays.
