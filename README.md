# PredMarket Alpha

Prediction-market research platform for discovering and exploiting mispricings
in Kalshi event contracts — systematically, quantitatively, and without
discretion. Runs a multi-family signal factory that scans markets, falsifies
candidate signals out of sample, converts survivors into calibrated
probabilities, sizes paper positions against capacity constraints, and gates
any transition to live execution behind structural preflight checks.

All work is **research-only** unless the user explicitly asks for execution.

## Key Features

- **Canonical Fee Engine** — Full Kalshi net-fee model: trade fee + rounding fee
  − rebate. Includes a `FeeAccumulator` with $0.01 rebate triggers,
  `/series/fee_changes` API integration, and an official fee-table fixture test
  suite. Default fee mode is **maker**, reflecting maker-first execution policy
  with fallback to taker when signal decay exceeds the fee differential.

- **Refined Portfolio Objective** — Paper sizing computes edge as
  **p̂ − p_market − net_fee(P)** with maker/taker branching. Covariance penalty
  λw⊤Σw is sourced from cluster correlation data. Ghost-listed contracts (zero
  visible depth) get capacity forced to zero.

- **Regulatory Compliance** — Config-backed jurisdiction layer
  (`kalshi_jurisdiction.py`) enforces state restrictions. Fail-closed for live
  mode; research-only mode is unaffected. Refreshable via
  `make kalshi-jurisdiction-refresh`.

- **Multi-Family Signal Factory** — Research-only pipeline across independent
  signal families (Crypto Proxy, Sports Baseball, Weather, ATP/Wimbledon,
  World Cup/FIFA, Near-Resolution Informed Flow, Passive Liquidity Provision,
  Favorite-Longshot Bias, Sports No-Vig Consensus). Each family runs through
  feature packet → observation loop → OOS/FDR falsification → replay cost gates
  → capacity/correlation/decay → cluster control. No family reaches paper sizing
  or live execution without passing every gate.

- **Execution Substrate** — Token-bucket rate limiter (30 req/s public, 10 req/s
  authenticated), read-only WebSocket market data client (≤5 connections),
  consolidated RSA-PSS authentication with structured `KalshiAuthError`.

- **EV Ledger & Paper Decision Engine** — Federated contract-level EV ledger
  with calibrated probabilities, fee-aware edge computation, Kelly-fraction
  sizing, and portfolio-level risk capping. Paper settlement reconciliation
  tracks realized P&L against exact public Kalshi settlement outcomes.

## Quick Start

```bash
# 1. Create virtualenv and install dependencies
make setup

# 2. Activate the venv
source .venv/bin/activate

# 3. Copy the env template and fill in credentials
cp .env.template .env
#   edit .env with your Kalshi API key and RSA private key path/PEM

# 4. Verify runtime imports resolve
make check-env

# 5. Run the database migrations
make migrate
```

## Common Commands

| Command | Description |
|---|---|
| `make setup` | Create venv and install dependencies |
| `make check-env` | Verify runtime imports resolve |
| `make test` | Run the full test suite |
| `make test-unit` | Run unit tests only (fast, no I/O) |
| `make test-integration` | Run integration tests (artifact replay, capture paths) |
| `make lint` | Run ruff linting |
| `make format` | Run ruff formatting |
| `make typecheck` | Run mypy type checking |
| `make quality` | Run all code-quality gates (lint, typecheck, modularize, deadcode, etc.) |
| `make coverage` | Run tests and generate HTML coverage report |

### Research Pipeline

| Command | Description |
|---|---|
| `make kalshi-universe-scan` | Scan public Kalshi universe into candidate inventory |
| `make kalshi-crypto-proxy-observation-watch-once` | Crypto proxy full chain |
| `make kalshi-sports-proxy-observation-watch-once` | Sports baseball full chain |
| `make kalshi-weather-proxy-observation-watch-once` | Weather proxy full chain |
| `make kalshi-world-cup-proxy-observation-watch-once` | World Cup/FIFA full chain |
| `make kalshi-atp-proxy-observation-watch-once` | ATP/Wimbledon full chain |
| `make kalshi-sports-nondirectional-evidence-watch-once` | Microstructure + flow + liquidity gates |
| `make kalshi-sports-evidence-cycle` | Full sports evidence cycle (all families + report) |
| `make kalshi-signal-factory-status` | Multi-family status report |
| `make macro-route` | Refresh macro decision artifacts |

### EV Ledger & Paper

| Command | Description |
|---|---|
| `make kalshi-ev-ledger` | Build federated Kalshi contract EV ledger |
| `make kalshi-paper-decision-candidates` | Build paper-autonomous decision candidates |
| `make kalshi-paper-settlement-reconcile` | Reconcile paper decisions to public settlements |
| `make kalshi-signal-decay-retirement` | Build signal decay/retirement ledger |
| `make kalshi-sports-paper-burn-in-cycle` | Advance paper settlement + sports label harvest |

### Live (Blocked)

| Command | Description |
|---|---|
| `make kalshi-live-preflight` | Build live eligibility and blocker report |
| `make kalshi-live-demo` | Run one demo-mode autonomous live pass (when armed) |
| `make kalshi-jurisdiction-refresh` | Refresh jurisdiction state from config |

### Standalone Research

| Command | Description |
|---|---|
| `make kalshi-rank` | Rank live Kalshi markets in research-only mode |
| `make kalshi-cycle` | Run rank + paper-intent research cycle |
| `make kalshi-ledger` | Audit Kalshi paper ledger |
| `make kalshi-smoke` | Generate offline Kalshi desk smoke artifacts |
| `make kalshi-verify` | Run Kalshi smoke plus focused Kalshi tests |
| `make type2-paper-matcher` | Run local Type 2 sportsbook paper matcher |

## Architecture

The research pipeline advances through five guarded stages:

```
Scan → Falsification → EV Ledger → Paper Sizing → Live Preflight
```

1. **Scan** — Public Kalshi universe scan populates candidate inventory.
   Probability breadth scout identifies fast-settling probability-source routes.

2. **Falsification** — Each signal family runs OOS/FDR falsification against
   exact public Kalshi settlement labels. Signal families emit research
   candidates with Benjamini-Hochberg q-values; no calibrated probabilities,
   EV estimates, or edge claims are present until this gate passes.

3. **EV Ledger** — FDR survivors enter the federated contract-level EV ledger.
   Calibrated probabilities are attached, fee-aware edges are computed, and
   capacity/correlation/decay/cluster gates are checked. Only rows with every
   gate passing become EV-usable.

4. **Paper Sizing** — EV-usable rows enter the paper decision engine.
   Kelly-fraction sizing with bankroll constraint, portfolio-level risk capping
   (cluster share, ghost-listing depth, decay survival), covariance penalty from
   cluster correlation data. Paper settlement reconciliation tracks realized P&L
   against exact public settlement outcomes.

5. **Live Preflight** — Paper-eligible rows are gate-checked for live readiness:
   jurisdiction, external-preflight validation, retirement status, and
   execution-mode configuration. Currently fully blocked; no live orders are
   placed.

## Signal Families

| Family | Domain | Status |
|---|---|---|
| Crypto Proxy | KXBTC, KXETH, KXSOL (up/down) | Paper candidates after full gate chain |
| Sports Baseball | KXMLBGAME, KXKBOGAME, KXLMBGAME | Exact-label accumulation; near FDR threshold |
| Weather | KXHIGH, KXLOW (temperature brackets) | Research candidate ready |
| ATP/Wimbledon | ATP match winners | Blocked pending settlement labels |
| World Cup/FIFA | World Cup match/advancement | OOS/FDR candidate ready |
| Near-Resolution Flow | Microstructure flow imbalance | FDR survivor; decay-bucket deficit |
| Passive Liquidity | Maker fill net EV | Proxy-only; blocked without real fill labels |
| Favorite-Longshot Bias | Directional price-bucket bias | Pre-registered; label accumulation |
| Sports No-Vig Consensus | Multi-book consensus vs. Kalshi | Label accumulation; pre-registered OOS rules |

## Research-Only Guardrails

- **No live execution** — `execution_enabled=false` on all artifacts. Live
  preflight is blocked (`kalshi_live_blocked`) with 0 eligible rows.
- **No threshold lowering** — OOS/FDR/decay/capacity gating thresholds are hard
  and non-overridable without an explicit tranche.
- **Exact settlement labels only** — Sportsbook odds, projection models, Elo
  ratings, and quote proxies are never used as outcome labels. Only exact public
  Kalshi settlement payloads qualify.
- **No donor runtime dependency** — External research repos contribute
  reference-only artifacts; no import or execution coupling.
- **No manual approval queue** — Humans configure systems; machines select,
  size, enter, exit, retire, and replace signals.
- **Capacity discipline is structural** — Position size is capped by cluster
  share (35%), ghost-listing depth, and decay survival, not conviction.

## Project Structure

```
predmarket/                 # Core research modules
  kalshi_*.py               # Kalshi-specific research
  crypto_family.py          # Crypto proxy family descriptor
  sports_family.py          # Sports baseball family descriptor
  weather_family.py         # Weather proxy family descriptor
  favorite_longshot_bias_family.py
  passive_liquidity_provision_family.py
  signal_family.py          # Shared family framework
  engine.py                 # Pipeline engine
  paper_decision_engine.py  # Fee-aware paper sizing
  kalshi_execution_cost.py  # Canonical fee engine
  kalshi_jurisdiction.py    # Regulatory compliance
  kalshi_websocket.py       # WebSocket market data client
  resilience.py             # Token-bucket rate limiter
  config.py                 # Pydantic configuration
  execution.py              # Execution layer (Kalshi-only, blocked)
  risk.py                   # Portfolio risk model
scripts/                    # Standalone research scripts
tests/                      # Test suite
  unit/                     # Fast unit tests (mocked I/O)
  integration/              # Integration tests (capture/replay paths)
docs/                       # Documentation
  codex/                    # Codex runway (current state, tranches, artifacts)
  architecture/             # Architecture diagrams and runbooks
```

## Environment

Requires Python 3.12+. Use the local venv at `.venv/`. All runtime artifacts
and raw data payloads land outside the repo under `/home/mrwatson/manual_drops/`.

## Code Quality

```bash
make lint       # ruff check
make format     # ruff format
make typecheck  # mypy (strict mode, mid-migration)
make quality    # All gates: lint, typecheck, modularize, deadcode, deptry, dup-check,
                # tech-debt-check, file-sizes-check, feature-flags-check, validate-agents
```

Pre-commit hooks enforce linting, formatting, and secret scanning:

```bash
pip install pre-commit
pre-commit install
```

## Codex Runway

- `docs/codex/current-state.md` — Current landing, family statuses, resume protocol
- `docs/codex/macro/` — Macro artifacts (`latest-*` pointers, decision, status)
- `docs/codex/tranches/` — Per-milestone tranche notes (`YYYY-MM-DD-slug.md`)
- Root `COMPLETION_REPORT_*.md` — Per-milestone completion reports

Run `make macro-route` before selecting the next repo to refresh the macro
decision.
