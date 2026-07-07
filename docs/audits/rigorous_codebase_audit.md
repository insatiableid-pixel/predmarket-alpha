# Codebase Audit & Actionable Remediation Report — predmarket-alpha

This report presents a rigorous, evidence-based audit of the `predmarket-alpha` platform. Both backend and frontend layers have been evaluated against a 0–100 production-grade scale. Actions taken in the current session are highlighted, and a complete remediation plan is laid out to bring both systems to a verified score of 100/100.

---

## Backend Audit

### Checklist
- [✅] [predmarket/](file:///home/mrwatson/projects/predmarket-alpha/predmarket) — Directory / module structure
- [✅] [requirements.txt](file:///home/mrwatson/projects/predmarket-alpha/requirements.txt) — Dependency manifest
- [✅] [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py) — Entry point(s)
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Route / controller layer
- [✅] [predmarket/ensemble.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/ensemble.py) — Business-logic / service layer
- [✅] [predmarket/audit.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/audit.py) — Data / persistence layer
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Authentication & authorization implementation (API Key header dependencies)
- [✅] [predmarket/config.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/config.py) — Input validation & sanitization (partial)
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Error handling strategy (partial, returns 200 on error)
- [✅] [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py) — Logging & observability hooks (lacks structured tracing)
- [✅] [tests/](file:///home/mrwatson/projects/predmarket-alpha/tests) — Test suite
- [✅] [.env](file:///home/mrwatson/projects/predmarket-alpha/.env) — Environment / secrets hygiene (hardcoded fallback key in signals)
- [❌] NOT FOUND — Build & packaging configuration (no Dockerfile, Makefile, or CI configs)
- [❌] NOT FOUND — API contract surface (no Swagger/OpenAPI spec checked in)

### Score: [55 / 100]

### Findings
| # | Severity | File / Layer | Issue | Points Deducted |
|---|----------|--------------|-------|-----------------|
| 1 | Critical | [main.py:L58](file:///home/mrwatson/projects/predmarket-alpha/main.py#L58) | **Undefined Variable (NameError) in Seeding**: The seeding database loop references `np_gain` instead of `daily_gain`, causing immediate crash on startup. *(Fixed in this session)* | 0 |
| 2 | Critical | [dashboard.py:L117-133](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L117-L133) | **Missing API Authentication**: Routes `/api/staged` and `/api/approve` have no authentication or authorization checks, allowing anyone to trigger live cash orders. *(Fixed in this session)* | 0 |
| 3 | High | [ingest.py:L115](file:///home/mrwatson/projects/predmarket-alpha/predmarket/ingest.py#L115) & [signals.py:L157](file:///home/mrwatson/projects/predmarket-alpha/predmarket/signals.py#L157) | **Unmocked Live Network Requests in Tests**: Test execution makes live network connections to Polymarket CLOB and FRED API instead of utilizing isolated mocks. | −10 |
| 4 | High | [dashboard.py:L111-125](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L111-L125) | **Improper HTTP Error Envelopes**: FastAPI handlers return `200 OK` on exception with `{"status": "error", "message": str(e)}`, leaking raw database details. | −10 |
| 5 | High | Repository Root | **Missing Build & CI Configurations**: No `Dockerfile`, `Makefile`/`Taskfile`, or CI configurations (like GitHub Actions) are present in the codebase. | −10 |
| 6 | Medium | [signals.py:L146](file:///home/mrwatson/projects/predmarket-alpha/signals.py#L146) | **Hardcoded API Key Fallback**: FRED signal extractor uses a hardcoded default credential fallback string if env vars are missing. | −5 |
| 7 | Medium | [main.py:L26-33](file:///home/mrwatson/projects/predmarket-alpha/main.py#L26-L33) | **Lack of Structured Logging / Tracing**: Text logging format is unstructured (not JSON) and lacks span/trace IDs or a metrics `/metrics` endpoint. | −5 |
| 8 | Low | Repository Root | **API Contract Surface Undocumented**: No static Swagger/OpenAPI specification file is committed. | −2 |
| 9 | Low | [dashboard.py:L127-130](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L127-L130) | **Missing Request Model Validation**: `/api/approve` takes a generic `payload: dict` instead of a typed Pydantic body class. | −2 |
| 10 | Style | [execution.py:L91](file:///home/mrwatson/projects/predmarket-alpha/predmarket/execution.py#L91) | **Inconsistent Logger String Formatting**: Mixes old format strings and f-strings in logging. | −1 |

**Score math:** 100 − 45 = 55

---

### Remediation Plan — Backend (target: 100)

**Step 1 — Fix Seeding Loop NameError (+20 pts)**
- **Files**: [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py)
- **Action**: Replace `np_gain` with `daily_gain` on line 58.
- **Verification**: Run `python main.py` and verify the seeding database is successfully initialized without NameError.
- **Resolves**: Finding #1, Critical. *(Completed in this session)*

**Step 2 — Implement API Key Middleware / OAuth2 Authentication (+20 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Add an API key dependency/OAuth2 scheme to protect `/api/staged` and `/api/approve` endpoints.
- **Verification**: `curl -I -X POST http://localhost:8050/api/approve` returns `401 Unauthorized`.
- **Resolves**: Finding #2, Critical. *(Completed in this session)*

**Step 3 — Implement Mocking in Test Suites (+10 pts)**
- **Files**: [tests/test_ingest.py](file:///home/mrwatson/projects/predmarket-alpha/tests/test_ingest.py), [tests/test_signals.py](file:///home/mrwatson/projects/predmarket-alpha/tests/test_signals.py)
- **Action**: Use `unittest.mock` or `pytest-mock` to patch `ClientSession.get` and `urllib.request.urlopen` in signals and ingestion pipelines.
- **Verification**: Run tests with network interfaces disabled; verify the suite still completes successfully.
- **Resolves**: Finding #3, High.

**Step 4 — Clean HTTP Error Envelopes and Hide Exceptions (+10 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Raise `HTTPException` with appropriate status code (e.g. 404, 500) and return sanitized error envelopes, logging the raw exception trace internally.
- **Verification**: Requests with invalid IDs return `400 Bad Request` or `404 Not Found` with a generic description.
- **Resolves**: Finding #4, High.

**Step 5 — Create Deployment and CI Configs (+10 pts)**
- **Files**: `Dockerfile`, `Makefile`, `.github/workflows/ci.yml`
- **Action**: Author a multi-stage `Dockerfile`, a `Makefile` for developer tasks, and a GitHub Actions workflow to run the test suite on push.
- **Verification**: `docker build -t predmarket .` completes successfully; GitHub Actions runner reports green.
- **Resolves**: Finding #5, High.

**Step 6 — Remove Hardcoded Fallback API Key (+5 pts)**
- **Files**: [predmarket/signals.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/signals.py)
- **Action**: Raise an initialization error or log a warning and return default mock values immediately if `FRED_API_KEY` is not set, instead of falling back to a dummy key.
- **Verification**: Confirm `FRED_API_KEY` is mandatory or handled gracefully without fallback strings.
- **Resolves**: Finding #6, Medium.

**Step 7 — Implement JSON Logging and Prom metrics (+5 pts)**
- **Files**: [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py), [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Configure `python-json-logger` for structured logging, inject trace/span IDs, and expose a `/metrics` route using `prometheus-client`.
- **Verification**: Querying `/metrics` returns Prometheus format metrics.
- **Resolves**: Finding #7, Medium.

**Step 8 — Generate OpenAPI Spec and Pydantic Request Models (+4 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Define a Pydantic class `class ApprovalRequest(BaseModel): id: int` for `/api/approve`, export static `openapi.json` contract file.
- **Verification**: Invalid payloads return `422 Unprocessable Entity` automatically from FastAPI.
- **Resolves**: Findings #8 & #9, Low.

**Step 9 — Log Formatting Standardization (+1 pt)**
- **Files**: [predmarket/execution.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/execution.py)
- **Action**: Refactor log strings to consistently use f-strings or placeholders.
- **Verification**: Code quality linter reports clean formatting.
- **Resolves**: Finding #10, Style.

---

## Frontend Audit

### Checklist
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Directory / component structure (monolithic)
- [✅] [requirements.txt](file:///home/mrwatson/projects/predmarket-alpha/requirements.txt) — Dependency manifest and lock file (lock file missing)
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Entry point and root component
- [❌] NOT FOUND — Routing layer
- [❌] NOT FOUND — State management strategy (no client store, DB polling only)
- [❌] NOT FOUND — Data-fetching layer (direct synchronous SQLite calls in callbacks)
- [❌] NOT FOUND — Form handling & client-side validation
- [❌] NOT FOUND — Authentication flow
- [❌] NOT FOUND — Accessibility baseline
- [✅] [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) — Responsive layout strategy (Dash Bootstrap Components)
- [❌] NOT FOUND — Build configuration
- [✅] [tests/test_dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/tests/test_dashboard.py) — Test suite
- [✅] [predmarket/dashboard.py](fil### Score: [30 / 100]

### Findings
| # | Severity | File / Layer | Issue | Points Deducted |
|---|----------|--------------|-------|-----------------|
| 1 | Critical | [dashboard.py:L394-401](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L394-L401) | **Asyncio Event Loop Deadlock**: Calling `loop.run_until_complete()` inside Dash callbacks blocks the web thread, throwing a `RuntimeError` or deadlocking under active server loops. | −20 |
| 2 | Critical | [dashboard.py:L485-526](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L485-L526) | **Synchronous Thread Blocking in Callbacks**: Running `loop.run_until_complete()` inside button callbacks freezes the UI thread during trade approvals. | −20 |
| 3 | High | [dashboard.py:L217](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L217) | **Missing Auth & Session Views**: UI dashboard lacks login views, session persistence, or router protection. | −10 |
| 4 | High | [test_dashboard.py:L118-149](file:///home/mrwatson/projects/predmarket-alpha/tests/test_dashboard.py#L118-L149) | **Broken Test Suite**: Test client execution deadlocked on `POST /api/approve` due to anyio portal conflicts on Python 3.14. *(Fixed in this session)* | 0 |
| 5 | Medium | [dashboard.py:L351](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L351) & [L444](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L444) | **Direct Database Queries in Render Path**: Direct synchronous `pd.read_sql_query` database connections inside UI components block renders on lock contention. | −5 |
| 6 | Medium | [dashboard.py:L217](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L217) | **Lack of State Management**: No global store (`dcc.Store`) or client-side caching is utilized; every callback execution runs full calculations. | −5 |
| 7 | Medium | [dashboard.py:L217-289](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L217-289) | **Lack of A11y baseline**: Missing keyboard controls and explicit ARIA descriptors. | −5 |
| 8 | Low | [dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py) | **Monolithic File Architecture**: UI layout, styles, callbacks, and REST routes are coupled into a single 530-line file. | −2 |
| 9 | Low | [dashboard.py:L27-28](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L27-L28) | **Public CDN Asset Reliance**: Loads CSS/fonts via external CDNs without local caching or subresource integrity checks. | −2 |
| 10 | Style | [dashboard.py:L32-37](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L32-L37) | **Hardcoded Color Palettes**: Styling color constants are declared in Python instead of a unified CSS theme module. | −1 |

**Score math:** 100 − 70 = 30
shboard.py#L32-L37) | **Hardcoded Color Palettes**: Styling color constants are declared in Python instead of a unified CSS theme module. | −1 |

**Score math:** 100 − 80 = 20

---

### Remediation Plan — Frontend (target: 100)

**Step 1 — Rewrite Dash Callbacks to be Async Native (+20 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Register callbacks as async-native functions (`async def`) and use `await` on async managers directly instead of running `loop.run_until_complete()`.
- **Verification**: Callbacks resolve instantly without blocking the server loop or freezing the dashboard.
- **Resolves**: Finding #1, Critical.

**Step 2 — Implement Background Worker for Approvals (+20 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Offload order approval execution to a background queue (e.g. `Celery` or an async executor task) and poll/update transaction status.
- **Verification**: UI remains fully interactive and responsive during the approval execution.
- **Resolves**: Finding #2, Critical.

**Step 3 — Implement UI Login and Protect Layouts (+10 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Add login widgets, store session cookies, and conditionally render the dashboard layout only for authenticated users.
- **Verification**: Loading page redirect to login when session cookie is absent.
- **Resolves**: Finding #3, High.

**Step 4 — Refactor Test Client to Async direct Calls (+10 pts)**
- **Files**: [tests/test_dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/tests/test_dashboard.py)
- **Action**: Call backend handlers (`get_staged_orders()`, `approve_order_endpoint()`) directly in async tests, avoiding Starlette AnyIO TestClient thread portal conflicts under Python 3.14.
- **Verification**: Pytest runs and passes 100% of dashboard tests in < 2 seconds.
- **Resolves**: Finding #4, High. *(Completed in this session)*

**Step 5 — Route Data Fetching through REST Client (+5 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Replace direct `sqlite3` connects in layout updates with HTTP requests to `/api/staged` or local internal controller calls.
- **Verification**: Code contains no SQLite imports/connections inside the layout-rendering functions.
- **Resolves**: Finding #5, Medium.

**Step 6 — Introduce Client-side State Storage (+5 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Add `dcc.Store` components to host the active slate and dashboard metrics on the client.
- **Verification**: Navigating tabs or loading charts uses local cached data without query repeats.
- **Resolves**: Finding #6, Medium.

**Step 7 — Implement Accessibility Controls (+5 pts)**
- **Files**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Add ARIA roles to custom tables and register keyboard focus styles/shortcuts for buttons.
- **Verification**: Screen reader identifies controls; elements are tab-navigable.
- **Resolves**: Finding #7, Medium.

**Step 8 — Modularize UI Code into Components (+4 pts)**
- **Files**: `predmarket/dashboard.py` (split into `dashboard/layout.py`, `dashboard/callbacks.py`, `dashboard/routes.py`)
- **Action**: Extract component code blocks (KPI widgets, plots, opportunity board) into separate modules.
- **Verification**: Modules can be imported and unit-tested in isolation.
- **Resolves**: Finding #8 & #9, Low.

**Step 9 — CSS Variable Styling Theme (+1 pt)**
- **Files**: `assets/custom.css`
- **Action**: Migrate Python styling dict constants to a global CSS variable stylesheet.
- **Verification**: Visual changes are styled using class tags instead of inline style dicts.
- **Resolves**: Finding #10, Style.

---

## Executive Summary

**Current state:**
The `predmarket-alpha` platform is a prediction market orchestrator utilizing high-quality analytical modules (Bayesian Belief Networks, scikit-learn calibration, and correlation-adjusted Kelly optimization). However, the system is hindered by critical structural issues. The backend contains a NameError crash path in database seeding and lacks any API route authentication. The frontend dashboard operates on a flawed synchronous loop execution that blocks the main server thread, suffers from direct database coupling in UI layers, and previously had a deadlocking test suite under Python 3.14.

**Biggest backend risk:**
Observability gaps (unstructured logs, lack of trace IDs) and synchronous external client test paths that require cleaner mocking.

**Biggest frontend risk:**
Direct event loop blocking in Dash data fetching (`loop.run_until_complete()`) and button execution creates a high probability of thread deadlocks, locking up the interface under high load or multi-user access.

**Effort to reach 100:**
| Side     | Estimated effort | Blocking items before deploy |
|----------|-----------------|------------------------------|
| Backend  | M (1–3 days)    | 0 critical + 3 high (mocks, envelopes, Docker/CI) |
| Frontend | M (1–3 days)    | 2 critical (loop deadlocks) + 1 high (UI auth protection) |
