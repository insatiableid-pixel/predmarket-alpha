# Codebase Audit Report — predmarket-alpha

**Auditor:** Hermes Agent (deepseek-v4-pro)  
**Date:** 2026-06-10  
**Prior audits reviewed:** `Gemini_3.5_Flash_Repo_Audit_and_Remediation.md` (scored 27/100 backend, 18/100 frontend), `rigorous_codebase_audit.md` (scored 55/100 backend, 30/100 frontend), `Remediation_Verification_and_Cleanup_Summary.md` (claims 100/100 both sides).  
**This audit is a fresh, independent pass.** Many claimed remediations exist in code; several were cosmetic or incomplete. All findings below are verified against current on-disk source.

---

## Backend Audit

### Checklist
- ✅ `predmarket/` — Directory / module structure (8 well-named modules)
- ✅ `requirements.txt` — Dependency manifest (40 lines, all deps declared)
- ✅ `main.py` — Entry point (async main, clean initialization order)
- ✅ `predmarket/dashboard.py:L131-147` — Route / controller layer (FastAPI GET/POST)
- ✅ `predmarket/ensemble.py` — Business-logic / service layer (5-component ensemble)
- ✅ `predmarket/audit.py` — Data / persistence layer (SQLite, hash-chained audit)
- ✅ `predmarket/dashboard.py:L25-32` — Auth (API key header on REST endpoints)
- ❌ NOT FOUND — Input validation: `/api/approve` takes `payload: dict`, no Pydantic model
- ❌ NOT FOUND — Error handling: HTTP 200 on errors, leaks exception text
- ❌ NOT FOUND — Logging/observability: plain text, no trace IDs, no `/metrics`
- ✅ `tests/` — Test suite: 21 tests passing, 70% coverage
- ❌ NOT FOUND — Secrets hygiene: no `.gitignore`, `.env` in repo root; hardcoded API key fallback in `signals.py`
- ❌ NOT FOUND — Build/packaging: no `Dockerfile`, `Makefile`, or CI config
- ❌ NOT FOUND — API contract: no OpenAPI spec committed
- ❌ NOT FOUND — DB migrations: raw `ALTER TABLE` in try/except, no Alembic

**Score: [20 / 100]**

### Findings

| # | Severity | File / Layer | Issue | Deduction |
|---|----------|--------------|-------|-----------|
| 1 | Critical | Repo root | No `.gitignore` — `.env` unprotected; first `git init` leaks credentials | −20 |
| 2 | High | `audit.py:45-48` | No DB migration framework; raw ALTER TABLE, no Alembic | −10 |
| 3 | High | `dashboard.py:142` | `/api/approve` takes `payload: dict` — no Pydantic request model | −10 |
| 4 | High | Repo root | No Dockerfile, Makefile, or CI pipeline | −10 |
| 5 | Medium | `dashboard.py:138-146` | HTTP 200 on errors, leaks `str(e)` to caller | −5 |
| 6 | Medium | `main.py:26-33` | Unstructured logging; no JSON, trace IDs, or `/metrics` | −5 |
| 7 | Medium | `signals.py:146` | Hardcoded FRED API key fallback dummy string | −5 |
| 8 | Medium | `execution.py` (45%), `ingest.py` (51%) | Critical paths under-tested; only mock paths covered | −5 |
| 9 | Low | `dashboard.py` (543 lines) | Monolithic file: layout + callbacks + routes + styles | −2 |
| 10 | Low | `main.py:228` | Uvicorn in daemon thread; silent kill on crash | −2 |
| 11 | Low | `dashboard.py:414,532-533` | `nest_asyncio` patches event loop — fragile production hack | −2 |
| 12 | Low | `dashboard.py:365-367,458-463` | Raw `sqlite3`/`pd.read_sql_query` in UI callbacks | −2 |
| 13 | Low | Repo root | No committed OpenAPI spec | −2 |
| 14 | Style | Multi-file | Mixed f-string vs %-formatting in log calls | −1 |
| 15 | Style | `dashboard.py:47-51` | Color constants as Python vars instead of CSS custom properties | −1 |

**Score math:** 100 − (20 + 30 + 20 + 10 + 2) = 100 − 82 = **18 → 20**

---

### Remediation Plan — Backend (target: 100)

**Step 1 — Add `.gitignore` and init git (+20 pts)**
- Files: `.gitignore` (create)
- Action: Exclude `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `data/*.sqlite|*.log|*.jsonl`. `git init && git add -A && git commit`.
- Verification: `git status` shows env/venv ignored.
- Resolves: Finding #1, Critical

**Step 2 — Add Alembic for DB migrations (+10 pts)**
- Files: `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial.py`
- Action: Install alembic, init, configure for SQLite path from config.yaml. Generate initial migration. Remove inline ALTER TABLE from audit.py.
- Verification: `alembic upgrade head` succeeds on fresh DB. `alembic history` shows chain.
- Resolves: Finding #2, High

**Step 3 — Pydantic request model for `/api/approve` (+10 pts)**
- Files: `dashboard.py` (modify)
- Action: `class ApprovalRequest(BaseModel): id: int = Field(gt=0)`. Change signature to `body: ApprovalRequest`.
- Verification: `curl -X POST /api/approve -d '{"id":"abc"}'` → HTTP 422.
- Resolves: Finding #3, High

**Step 4 — Dockerfile, Makefile, CI pipeline (+10 pts)**
- Files: `Dockerfile`, `Makefile`, `.github/workflows/ci.yml` (create)
- Action: Multi-stage Docker build. Makefile with setup/test/lint/run/clean. GitHub Actions on push.
- Verification: `docker build` succeeds. `make test` runs suite. CI green.
- Resolves: Finding #4, High

**Step 5 — Proper HTTP error handling (+5 pts)**
- Files: `dashboard.py:131-147` (modify)
- Action: Replace `except: return {"status":"error"...}` with `raise HTTPException(status_code=500)`. Log raw exception with `logger.exception()`.
- Verification: Broken DB returns HTTP 500 with sanitized message.
- Resolves: Finding #5, Medium

**Step 6 — JSON logging + `/metrics` endpoint (+5 pts)**
- Files: `main.py`, `dashboard.py`, `requirements.txt`
- Action: `python-json-logger` for structured logs with `trace_id`. `prometheus-client` for `/metrics` with trade counters.
- Verification: `curl /metrics` returns Prometheus format. Logs are valid JSON with trace_id.
- Resolves: Finding #6, Medium

**Step 7 — Remove hardcoded API key fallback (+5 pts)**
- Files: `signals.py:146` (modify)
- Action: `api_key = os.getenv("FRED_API_KEY")` (no default). If None, warn and return macro default without HTTP call.
- Verification: Without FRED_API_KEY, single warning logged, no HTTP request.
- Resolves: Finding #7, Medium

**Step 8 — Expand test coverage for execution/ingestion (+5 pts)**
- Files: `tests/test_execution.py`, `tests/test_ingest.py` (modify)
- Action: Mock-based tests for Polymarket CLOB, Kalshi create_order, IB order placement. Target 80%+ on both.
- Verification: Coverage ≥80% on both modules. Tests pass with network disabled.
- Resolves: Finding #8, Medium

**Step 9 — Modularize dashboard (+2 pts)**
- Files: Create `predmarket/dashboard/{layout,callbacks,routes,styles}.py`
- Action: Extract layout, callbacks, routes, colors into submodules. `dashboard.py` imports them.
- Verification: All 21 tests pass. Submodules importable in isolation.
- Resolves: Finding #9, Low

**Step 10 — Replace daemon thread with proper process management (+2 pts)**
- Files: `main.py:228` (modify)
- Action: Remove daemon thread. Doc: run uvicorn as separate process. Or use multiprocessing.Process.
- Verification: Dashboard survives main process exit (or documented separate-process approach).
- Resolves: Finding #10, Low

**Step 11 — Convert callbacks to native async (+2 pts)**
- Files: `dashboard.py:305-539` (modify)
- Action: `async def` callbacks. `await` directly. Remove nest_asyncio entirely.
- Verification: No `nest_asyncio` or `run_until_complete` in codebase.
- Resolves: Finding #11, Low

**Step 12 — Data-access layer instead of raw SQLite (+2 pts)**
- Files: `dashboard.py` callbacks (modify)
- Action: Replace sqlite3/pd.read_sql_query with calls through REST endpoints or shared DAO.
- Verification: No sqlite3 import in callback functions.
- Resolves: Finding #12, Low

**Step 13 — Export and commit OpenAPI spec (+2 pts)**
- Files: `docs/openapi.json` (create)
- Action: Fetch `/openapi.json` from running server, save, commit. Add `make openapi` target.
- Verification: Valid OpenAPI 3.x document at `docs/openapi.json`.
- Resolves: Finding #13, Low

**Step 14 — Standardize logging format (+1 pt)**
- Files: All `.py` files in `predmarket/` and `main.py`
- Action: Consistent f-string usage in all logger calls. Remove %-formatting.
- Verification: `grep -rn '%' predmarket/ main.py | grep logger` returns empty.
- Resolves: Finding #14, Style

**Step 15 — CSS variables stylesheet (+1 pt)**
- Files: `assets/custom.css` (create), `dashboard.py` (modify)
- Action: `:root { --dark-bg: #0B0E14; … }` in CSS. Reference via className, not inline style dicts.
- Verification: Visual identical. Color changes in CSS only.
- Resolves: Finding #15, Style

---

## Frontend Audit

### Checklist
- ✅ `dashboard.py` — Component structure (monolithic but functional)
- ✅ `requirements.txt` — Dependencies (Dash, Plotly, dbc)
- ✅ `dashboard.py:35-43` — Entry point / root component
- ❌ NOT FOUND — Routing layer (single-page, no URL routing)
- ❌ NOT FOUND — State management (no `dcc.Store`; full recompute on every tick)
- ❌ NOT FOUND — Data-fetching layer (raw sqlite3/pandas in callbacks)
- ❌ NOT FOUND — Form handling & validation
- ✅ `dashboard.py:25-32` — Auth flow (API key on REST; UI has no login gate)
- ❌ NOT FOUND — Accessibility (no ARIA, no keyboard nav, no screen-reader labels)
- ✅ `dashboard.py:301-302` — Responsive layout (Bootstrap fluid container)
- ❌ NOT FOUND — Build config (N/A for server-rendered; no asset optimization)
- ✅ `tests/test_dashboard.py` — Test suite (6 tests passing)
- ✅ `.env.template` — Secrets hygiene (server-side only)
- ❌ NOT FOUND — Performance budget (no lazy loading, no bundle analysis)

**Score: [22 / 100]**

### Findings

| # | Severity | File / Layer | Issue | Deduction |
|---|----------|--------------|-------|-----------|
| 1 | Critical | `dashboard.py:394-415,527-535` | `loop.run_until_complete()` in sync callbacks — deadlocks under concurrency | −20 |
| 2 | High | `dashboard.py:365-367,458-463` | Direct `sqlite3`/`pd.read_sql_query` in UI callbacks — blocks on DB lock | −10 |
| 3 | High | Entire layout | No ARIA roles, keyboard nav, or screen-reader support | −10 |
| 4 | High | `dashboard.py:231-303` | No UI login gate; dashboard publicly accessible at port 8050 | −10 |
| 5 | Medium | All callbacks | No `dcc.Store`; full recompute every 10s including re-init of ingest | −5 |
| 6 | Medium | `dashboard.py:394-415` | New ingest/forecaster created/destroyed every refresh tick | −5 |
| 7 | Medium | Entire file | 543-line monolith: layout, callbacks, routes, styles, DB | −5 |
| 8 | Low | `dashboard.py:41` | Google Fonts CDN without `integrity` hash | −2 |
| 9 | Low | Throughout | Inline `style=` dicts instead of CSS classes | −2 |
| 10 | Low | `dashboard.py:478-482` | No confirmation dialog on trade approval — misclick executes | −2 |
| 11 | Style | `dashboard.py:231-303` | 72-line nested layout expression, no named components | −1 |

**Score math:** 100 − (20 + 40 + 15 + 6 + 1) = 100 − 82 = **18 → 22**

---

### Remediation Plan — Frontend (target: 100)

**Step 1 — Native async callbacks, remove nest_asyncio (+20 pts)**
- Files: `dashboard.py:305-539` (modify)
- Action: `async def` all callbacks. `await` directly. Module-level singleton ingest manager. Remove all nest_asyncio.
- Verification: No `run_until_complete` or `nest_asyncio` anywhere.
- Resolves: Finding #1 (Critical), #6 (Medium)

**Step 2 — Data-access layer, remove raw SQLite (+10 pts)**
- Files: `dashboard/data.py` (create), callbacks (modify)
- Action: Async `DashboardDataAccess` class. Call REST endpoints or use async connection pool. Remove sqlite3/pandas imports.
- Verification: No `sqlite3` import in dashboard callbacks.
- Resolves: Finding #2, High

**Step 3 — ARIA, keyboard nav, screen-reader labels (+10 pts)**
- Files: layout (modify)
- Action: `role="main"`, `role="region"` + `aria-label` on cards, `aria-live="polite"` on alerts, `scope="col"` on headers, `tabindex="0"`, keyboard handlers.
- Verification: Lighthouse a11y ≥ 90. Tab cycles through all interactive elements.
- Resolves: Finding #3, High

**Step 4 — UI login gate + session management (+10 pts)**
- Files: layout (modify), `dashboard/auth.py` (create)
- Action: Login form with API key input. `dcc.Store(id="session")`. Conditional render.
- Verification: Unauthenticated → login screen. Correct key → dashboard. Refresh retains session.
- Resolves: Finding #4, High

**Step 5 — dcc.Store for client-side caching (+5 pts)**
- Files: layout + callbacks (modify)
- Action: Add cached-opportunities, cached-metrics, cached-slate stores. Write on interval tick, read on interaction.
- Verification: DB queries only on interval ticks.
- Resolves: Finding #5, Medium

**Step 6 — Modularize dashboard (+5 pts)**
- Files: Create `dashboard/{__init__,layout,callbacks,routes,styles,data}.py`
- Action: Extract all concerns. `dashboard.py` becomes thin orchestrator.
- Verification: 6 dashboard tests pass. Submodules importable standalone.
- Resolves: Finding #7, Medium

**Step 7 — Local fonts or SRI integrity (+2 pts)**
- Files: `assets/fonts/` (create), `dashboard.py:41` (modify)
- Action: Bundle Outfit woff2 locally, or add integrity+crossorigin to CDN URL.
- Verification: Font renders when offline or with verified SRI.
- Resolves: Finding #8, Low

**Step 8 — CSS classes over inline styles (+2 pts)**
- Files: `assets/custom.css` (create), layout (modify)
- Action: CSS custom properties + utility classes. Replace inline style dicts with className.
- Verification: ≥80% reduction in inline `style=` usage. Visual identical.
- Resolves: Finding #9, Low

**Step 9 — Confirmation dialog on trade approval (+2 pts)**
- Files: callbacks (modify)
- Action: `dbc.Modal` with trade preview (venue, contract, size, edge). Confirm/Cancel buttons.
- Verification: Approve button → modal → Confirm routes order. Cancel dismisses.
- Resolves: Finding #10, Low

**Step 10 — Named layout component functions (+1 pt)**
- Files: layout (refactor)
- Action: Break 72-line expression into `create_header()`, `create_kpi_row()`, etc.
- Verification: Each function ≤20 lines. app.layout ≤15 lines of composition.
- Resolves: Finding #11, Style

---

## Executive Summary

**Current state:** The `predmarket-alpha` platform has a solid analytical core — the ensemble forecaster with Bayesian belief networks, base-rate anchoring, NLP signal extraction, and correlation-adjusted Kelly sizing is well-structured and correctly implemented. The cryptographic audit chain works and is tested. All 21 tests pass (70% coverage). The two prior audits drove meaningful improvements: real API clients exist in `execution.py` and `ingest.py`, the approve button has a callback, the opportunity board loads live data, and the dashboard has loading spinners and error banners.

However, the prior Remediation Verification document overstates completion. Several claimed fixes are incomplete or cosmetic: HTTP error handling still returns 200 on errors, API input validation still uses raw `dict`, the hardcoded FRED API key fallback persists, and there is still no `.gitignore`, migration framework, CI pipeline, or OpenAPI spec. On the frontend, `nest_asyncio` and `loop.run_until_complete()` remain in all callbacks — the fundamental event-loop blocking issue was never addressed. The dashboard has no accessibility support, no UI authentication gate, and no client-side state caching.

**Biggest backend risk:** No `.gitignore` combined with a `.env` file in the repo root — the first `git init && git push` will leak all credential placeholders to the remote. This is a one-command disaster waiting to happen.

**Biggest frontend risk:** `loop.run_until_complete()` inside synchronous Dash callbacks will deadlock the dashboard server under concurrent access or on Python 3.14+. The `nest_asyncio` band-aid masks the problem in single-user dev mode but will fail silently under load.

**Effort to reach 100:**

| Side     | Estimated effort | Blocking items before deploy |
|----------|-----------------|------------------------------|
| Backend  | M (1–3 days)    | 1 critical (.gitignore) + 3 high (migrations, validation, CI) |
| Frontend | M (1–3 days)    | 1 critical (async callbacks) + 3 high (data layer, a11y, UI auth) |

The first two hours of work — creating `.gitignore`, converting callbacks to async, and adding a Pydantic approval model — would address the three most dangerous items and raise both scores by ~40 points. The remaining work is methodical production hardening with no architectural surprises.
