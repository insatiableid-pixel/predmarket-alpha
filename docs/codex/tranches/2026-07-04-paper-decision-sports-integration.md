# Paper-Decision Sports Integration

## What

Ensured that sports blocker rows from the stack sequencing and flow replay gates emit correct family_id prefixes (`mlb_sports`, `atp_tennis`, `world_cup_soccer`, `microstructure_informed_flow`) so VAL-PAPER-001 prefix checks pass. Blocked candidates carry `paper_stake=0`, `kelly_fraction=0`, and explicit `blocker_list`. Live preflight correctly mirrors paper state with "paper candidate is not usable" blockers when paper_usable=0.

## Changes

1. **scripts/kalshi_sports_stack_sequencing.py**: Added `paper_blocker_family_id()` mapping to convert `mlb`→`mlb_sports` and `atp`→`atp_tennis` in paper blocker row family_ids.
2. **scripts/kalshi_near_resolution_flow_replay_gates.py**: Changed blocker row family_id from `near_resolution_informed_flow` to `microstructure_informed_flow`.
3. **tests/test_kalshi_paper_autonomous_engine.py**: Added 9 new unit tests covering all VAL-PAPER-001 through VAL-PAPER-009 assertions.
4. **tests/test_kalshi_sports_stack_sequencing.py**: Updated existing test for new family_id values.

## Verification

- 769 unit tests pass, 14 integration tests pass
- `make quality` exits 0 (all gates green)
- `make kalshi-sports-label-accumulation-cycle` exits 0
- Real artifact inspection confirms:
  - 140 sports blocker rows with `atp_tennis`, `mlb_sports`, `world_cup_soccer`, `microstructure_informed_flow`
  - All 460 candidates blocked with paper_stake=0
  - Live preflight shows 0 eligible (mirrors paper state)
  - Sports blocker rows ingested by default (88 gate evidence rows from stack sequencing + flow replay)
