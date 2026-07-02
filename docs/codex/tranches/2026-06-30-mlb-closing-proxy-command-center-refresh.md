# 2026-06-30 MLB Closing Proxy Command Center Refresh

## Summary

Updated the macro command center to recognize MLB's closing-proxy validation surface as the newest MLB truth state.

## Router State

- MLB status: `primary_type2_closing_proxy_same_slate_support_insufficient`
- Priority: -4
- Route: all lanes parked; predmarket remains command center
- Unlock: independent clean MLB slate or true closing-line validation

## Why It Matters

The proxy found favorable lower-threshold later-snapshot movement, but it is same-slate-only and conflicts with settled-outcome validation. The router therefore parks MLB instead of routing more feature work.

## Files

- `scripts/codex_macro_router.py`
- `scripts/codex_macro_unlock_scout.py`
- `tests/test_codex_macro_router.py`
- `tests/test_codex_macro_unlock_scout.py`
- `docs/codex/macro/latest-status.json`
- `docs/codex/macro/latest-decision.json`
- `docs/codex/macro/latest-decision.md`
- `docs/codex/macro/latest-unlock-scout.json`
- `docs/codex/macro/latest-unlock-scout.md`

## Verification

- `PYTHONPATH=. pytest tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py -q`
- `ruff check scripts/codex_macro_router.py scripts/codex_macro_unlock_scout.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
- `make macro-route`
- `make macro-unlock-scout`
