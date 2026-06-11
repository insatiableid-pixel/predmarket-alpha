# Codebase Audit Report — predmarket-alpha

This audit evaluates the current state of the `predmarket-alpha` platform, scoring both backend and frontend systems on a 0–100 scale. Actionable remediation steps are detailed below to bring both layers to a perfect 100/100 score.

---

## Backend Audit
**Score: [27 / 100]**

### Findings
| # | Severity | File / Layer | Issue | Points Deducted |
|---|----------|--------------|-------|-----------------|
| 1 | Critical | [main.py:L94-105](file:///home/mrwatson/projects/predmarket-alpha/main.py#L94-L105) | **Broken Cryptographic Audit Chain in Seeding**: Seeds `prev_hash` and `entry_hash` with identical non-standard Python `hash()` string values instead of building a proper SHA-256 blockchain backlink using `_compute_hash` from `AuditLogger`. This breaks `verify_audit_chain()` validation once historical data is seeded. | -15 |
| 2 | Critical | [predmarket/execution.py:L142-169](file:///home/mrwatson/projects/predmarket-alpha/predmarket/execution.py#L142-L169) | **Incomplete/Mocked Exchange Execution**: The execution loop is entirely mocked. It does not invoke any actual API endpoints for Polymarket, Kalshi, or IB. Even when `execution_enabled` is true, it merely sleeps for `0.1` seconds, generates a mock ID, and returns a simulated success payload. | -20 |
| 3 | High | [predmarket/ingest.py:L179-188](file:///home/mrwatson/projects/predmarket-alpha/predmarket/ingest.py#L179-L188) | **Incomplete/Stubbed Market Ingestion**: The connection to real APIs is stubbed out with `pass` statements. Even when `polymarket_connected`, `kalshi_connected`, or `ib_connected` are true, the code only returns static mock values from the local `mock_db` instead of querying the actual exchange endpoints. | -15 |
| 4 | High | [requirements.txt](file:///home/mrwatson/projects/predmarket-alpha/requirements.txt) / [predmarket/dashboard.py:L7](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L7) | **Missing Dependency in Build Config**: `dash_bootstrap_components` is imported and required by the UI but is completely absent from the `requirements.txt` file, causing immediate import errors on fresh installations. | -10 |
| 5 | Medium | [predmarket/dashboard.py:L31](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L31) / [main.py:L202](file:///home/mrwatson/projects/predmarket-alpha/main.py#L202) | **Hardcoded Database and Log Paths**: Hardcodes paths like `/home/mrwatson/projects/predmarket-alpha/data/database.sqlite` and log files as literal strings, ignoring the type-safe Pydantic configuration (`global_cfg.data_dir`). This breaks environment portability. | -5 |
| 6 | Medium | [tests/](file:///home/mrwatson/projects/predmarket-alpha/tests) | **Deficient Test Coverage (Untested UI & Main Orchestrator)**: The test suite has 0% coverage for the dashboard server and main loop orchestrator. Because the dashboard file is never imported or executed in tests, the missing `dash_bootstrap_components` dependency went undetected. | -5 |
| 7 | Low | [predmarket/signals.py:L134-141](file:///home/mrwatson/projects/predmarket-alpha/predmarket/signals.py#L134-L141) | **Mocked Macroeconomic Data Ingestion**: Macro data retrieval in `MacroSignalExtractor.fetch_fred_rate` is stubbed with hardcoded defaults (e.g., CPI 3.1%, Unemployment 3.9%) instead of integrating with real FRED APIs. | -3 |

### Remediation Plan — Backend (target: 100)

**Step 1 — Correct Cryptographic Chain in Data Seeding (+15 pts)**
- **File(s)**: [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py)
- **Action**: Update the `seed_historical_data` function to use a standard SHA-256 computation sequence to generate a valid blockchain backlink. Track `prev_hash` across the loop and compute the proper `entry_hash` via `hashlib.sha256` matching the logic in `predmarket/audit.py`.
- **Why**: Ties back to backend finding #1 (Broken Cryptographic Audit Chain in Seeding).

**Step 2 — Implement Real Exchange API Clients (+20 pts)**
- **File(s)**: [predmarket/execution.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/execution.py)
- **Action**: Replace the simulated order execution loops with actual venue calls using `kalshi-python` SDK (for Kalshi) and `ib-insync` API clients (for Interactive Brokers) using credentials loaded from the environment variables, handling trade routing, limits, and real exceptions.
- **Why**: Ties back to backend finding #2 (Incomplete/Mocked Exchange Execution).

**Step 3 — Implement Live Market Data Ingestion (+15 pts)**
- **File(s)**: [predmarket/ingest.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/ingest.py)
- **Action**: Replace `pass` statements in `get_market_snapshot` with actual orderbook queries using the `kalshi_python` SDK, `ib_insync` library, and `aiohttp` calls to Polymarket's CLOB API to fetch live bid, ask, last price, volume, and open interest.
- **Why**: Ties back to backend finding #3 (Incomplete/Stubbed Market Ingestion).

**Step 4 — Add Missing UI Dependencies (+10 pts)**
- **File(s)**: [requirements.txt](file:///home/mrwatson/projects/predmarket-alpha/requirements.txt)
- **Action**: Add `dash-bootstrap-components>=1.0.0` to `requirements.txt` to prevent import failures.
- **Why**: Ties back to backend finding #4 (Missing Dependency in Build Config).

**Step 5 — Enforce Config-driven File Paths (+5 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py), [main.py](file:///home/mrwatson/projects/predmarket-alpha/main.py)
- **Action**: Remove hardcoded file paths (like `"/home/mrwatson/projects/predmarket-alpha/data/database.sqlite"` and logging files) and instead pass the runtime config object (which reads `data_dir` from Pydantic config) down to all classes, constructing relative paths dynamically.
- **Why**: Ties back to backend finding #5 (Hardcoded Database and Log Paths).

**Step 6 — Expand Test Suite for UI and Orchestrator (+5 pts)**
- **File(s)**: [tests/](file:///home/mrwatson/projects/predmarket-alpha/tests)
- **Action**: Implement automated tests that import `predmarket.dashboard` and verify layout structure/callbacks, and tests for `main.py` platform loop behaviors using mocked asyncio tasks.
- **Why**: Ties back to backend finding #6 (Deficient Test Coverage).

**Step 7 — Implement Live Macroeconomic Data Fetcher (+3 pts)**
- **File(s)**: [predmarket/signals.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/signals.py)
- **Action**: Update `MacroSignalExtractor` to query real FRED API endpoints using `aiohttp` or a library, rather than returning hardcoded default values.
- **Why**: Ties back to backend finding #7 (Mocked Macroeconomic Data Ingestion).

---

## Frontend Audit
**Score: [18 / 100]**

### Findings
| # | Severity | File / Layer | Issue | Points Deducted |
|---|----------|--------------|-------|-----------------|
| 1 | Critical | [predmarket/dashboard.py:L314](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L314) | **Non-functional "Approve Trade Intent" Button**: The "Approve Trade Intent" button has an ID (`approve-btn`) but has absolutely no registered callback. Clicking it does nothing, and there is no API endpoint or logic to accept and execute staged trades from the UI. | -25 |
| 2 | Critical | [predmarket/dashboard.py:L259-263](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L259-L263) / [L282-301](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L282-L301) | **Hardcoded UI Data**: The "Market Opportunity Board" and "Kelly Position Sizing Slate" displayed in the UI are populated via fully hardcoded data structures (`sim_opportunities` and `sim_slate`) defined directly inside the dashboard callback. They are not read from the SQLite database or the ingestion/risk managers. | -25 |
| 3 | High | [predmarket/dashboard.py:L60-61](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L60-L61) | **Randomized Outcome Simulation in UI**: The dashboard simulates resolved outcomes on the fly using `np.random.rand()` inside the performance calculation. The calibration curve and Brier score metrics are therefore randomized on every data refresh, presenting fabricated analytics to the user instead of displaying true historical resolutions. | -15 |
| 4 | Medium | [predmarket/dashboard.py:L111-175](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L111-L175) | **Missing Error States and Loading Feedback**: The Dash layout lacks any error-handling UI elements or loading/spinner components for long-running callback processes (e.g. while performing statistical or calibration updates), which could result in a frozen or silent-failure UI state when the backend database is locked or slow. | -5 |
| 5 | Medium | [predmarket/dashboard.py:L12](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L12) | **FastAPI Wrapper Has No Routes**: The codebase initializes a FastAPI server as the Dash backing server but declares zero REST routes or controllers. The manifest comment indicates it should act as a "REST API wrapper for staging manual approvals", but it is completely unused dead code. | -10 |
| 6 | Low | [predmarket/dashboard.py:L115](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py#L115) | **Typography Stylesheet Fallback**: The typography styling tries to use `"Outfit, sans-serif"`, but this Google Font is not imported in the Dash app (via external stylesheets or custom HTML headers), causing the browser to fall back to generic system sans-serif. | -2 |

### Remediation Plan — Frontend (target: 100)

**Step 1 — Implement Trade Approval Callback & Action Route (+25 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Register a Dash callback listening to clicks on the `"Approve Trade Intent"` button (`approve-btn`), extracting the staging details, and either triggering an action via `ExecutionManager` or sending an approval request to a new FastAPI endpoint.
- **Why**: Ties back to frontend finding #1 (Non-functional "Approve Trade Intent" Button).

**Step 2 — Bind Opportunity Board and Kelly Slate to Live Data (+25 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Modify the `update_dashboard_data` callback to read the live sizing slate and active market opportunities from the SQLite `audit_trail` database (or by calling `RiskManager.optimize_portfolio_kelly` and `MarketIngestManager.get_all_snapshots` dynamically) instead of returning static hardcoded lists.
- **Why**: Ties back to frontend finding #2 (Hardcoded UI Data).

**Step 3 — Read Real Resolved Outcomes from DB (+15 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Remove `np.random.rand()` logic from `fetch_performance_metrics` and replace it with queries to retrieve true, persistent resolved outcomes from a new column (e.g. `resolution_outcome` or `outcome`) in the `audit_trail` table.
- **Why**: Ties back to frontend finding #3 (Randomized Outcome Simulation in UI).

**Step 4 — Define FastAPI REST API Endpoints (+10 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Implement REST endpoints (e.g., `POST /api/approve`, `GET /api/staged`) on the FastAPI `server` instance to allow programmatic review, staging, and approval of manual orders.
- **Why**: Ties back to frontend finding #5 (FastAPI Wrapper Has No Routes).

**Step 5 — Add Loading Spinners and Error Handling (+5 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Wrap the plotly figures and dashboard tables in `dcc.Loading` wrappers, and add try-except blocks inside callbacks with UI alert banners (`dbc.Alert`) to handle and display database connection errors or network timeouts gracefully.
- **Why**: Ties back to frontend finding #4 (Missing Error States and Loading Feedback).

**Step 6 — Embed Google Fonts Stylesheet Link (+2 pts)**
- **File(s)**: [predmarket/dashboard.py](file:///home/mrwatson/projects/predmarket-alpha/predmarket/dashboard.py)
- **Action**: Add the Outfit font stylesheet URL (`https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap`) to `external_stylesheets` in the `Dash` initialization block.
- **Why**: Ties back to frontend finding #6 (Typography Stylesheet Fallback).

---

## Executive Summary

The `predmarket-alpha` platform exhibits a solid high-level architecture with clear modular boundaries, separating configuration, ingestion, forecasting, risk management, and audit trailing. However, under the hood, the system is primarily a simulated mock. The core data ingestion and trade execution layers are stubbed out with empty statements or simulated payloads, meaning the platform cannot execute trades or ingest live exchange data in its current state. Additionally, critical build configuration oversights (a missing UI dependency) and cryptographic seeding issues pose immediate operational and validation failures.

The frontend dashboard (built using Dash) is visually attractive but behaves as a static mockup. The key telemetry displays (such as the Opportunity Board and Kelly Sizing Slate) use hardcoded datasets, and critical user interactions like the "Approve Trade Intent" button are completely non-functional. To transition the platform to a production-grade status, the estimated effort is **Medium (M)** for the backend (primarily integrating the live exchange client SDKs) and **Small (S)** for the frontend (registering the missing callbacks, mapping layout components to database queries, and adding UI polish).
