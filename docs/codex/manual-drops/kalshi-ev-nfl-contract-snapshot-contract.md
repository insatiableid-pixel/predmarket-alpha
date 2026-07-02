# Kalshi EV NFL Contract Snapshot Manual-Drop Contract

This contract defines the missing input for the federated Kalshi contract EV ledger when NFL model probabilities are ready but exact Kalshi contract evidence is absent.

## Purpose

Provide local, auditable evidence for one selected NFL work-order side so the command center can fill a safe contract-mapping overlay and matching calibrated-probability overlay.

This is not a bet recommendation, order instruction, staking plan, or execution approval.

## Where To Put The File

Drop the raw local Kalshi NFL snapshot outside every repo:

`/home/mrwatson/manual_drops/kalshi/`

Recommended filename:

`kalshi_nfl_contract_snapshot_<UTC_TIMESTAMP>.json`

Do not copy raw payloads into any project repo.

## Required Contract Evidence

The snapshot must include at least one market object for a selected row from:

`/home/mrwatson/projects/predmarket-alpha/docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json`

Required fields, directly or equivalently:

- `ticker`: exact Kalshi contract ticker
- `event_ticker`: exact Kalshi event ticker
- `title`: enough text to identify the NFL game and selected side
- `rules_primary`: official Kalshi resolution text
- `rules_secondary` or equivalent official supplemental terms when available
- `yes_ask_dollars` or an equivalent executable YES ask/cost field
- `yes_bid_dollars` when available, so spread can be recorded
- `status`
- `open_time`, `close_time`, `expiration_time`, or equivalent timing fields when available

If the evidence comes from an order ticket instead of a market JSON object, include the ticket-derived cost fields in the local JSON:

- `ticket_payout_multiple` or `displayed_payout_multiple`
- `ticket_cost` or `all_in_cost` if shown
- `captured_at_utc`
- `side`

## Safety Requirements

The dropped file must not contain:

- API keys, tokens, cookies, session IDs, account IDs, or payment details
- order IDs from a real submitted order
- account balances or portfolio positions
- instructions to buy, sell, size, stake, or execute

The workflow remains research-only:

- provider/API calls: false unless separately authorized
- account/order paths: false
- market execution: false
- database writes: false
- raw payloads copied into repos: false

## After Dropping The File

Run from `/home/mrwatson/projects/predmarket-alpha`:

```bash
make kalshi-ev-contract-mapping-work-order
make kalshi-ev-local-contract-evidence-scout
make kalshi-ev-overlay-preflight
make kalshi-ev-ledger
make macro-route
```

Expected first unlock:

- `make kalshi-ev-local-contract-evidence-scout` should move from `local_contract_evidence_blocked_no_nfl_target_snapshot` to either `local_contract_evidence_ready_for_overlay_fill` or a more specific blocked status explaining the missing field.

Only after the scout reports ready local target evidence should a worker fill overlays under:

- `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/`
- `/home/mrwatson/manual_drops/kalshi_ev_probabilities/`
