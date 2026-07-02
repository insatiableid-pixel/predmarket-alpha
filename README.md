# PredMarket Alpha

Prediction-market research platform for Kalshi/Polymarket alpha research: forecasting
pipelines, paper trading, EV analysis, and hypothesis falsification with a
FastAPI/Dash dashboard and SQLite/DuckDB store.

All work is **research-only** unless the user explicitly asks for execution.

## Quick Start

```bash
# 1. Create virtualenv and install dependencies
make setup

# 2. Activate the venv
source .venv/bin/activate

# 3. Copy the env template and fill in credentials
cp .env.template .env
#   edit .env with your Kalshi API key/secret

# 4. Verify runtime imports resolve
make check-env

# 5. Run the database migrations
make migrate

# 6. Start the platform
make run
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
| `make run` | Start the platform (alembic upgrade + main) |
| `make dashboard` | Start dashboard server only |
| `make coverage` | Run tests and generate HTML coverage report |
| `make kalshi-verify` | Run Kalshi smoke plus focused Kalshi tests |
| `make kalshi-smoke` | Generate offline Kalshi desk smoke artifacts |

## Kalshi Research Desk

The Kalshi research desk runs a daily research-only loop. See
[docs/kalshi_research_desk.md](docs/kalshi_research_desk.md) for the full runbook.

Key targets:

```bash
make kalshi-rank          # Rank live Kalshi markets in research-only mode
make kalshi-cycle         # Run rank + paper-intent research cycle
make kalshi-ledger        # Audit Kalshi paper ledger
```

## Architecture

See [docs/architecture/kalshi-signal-factory.md](docs/architecture/kalshi-signal-factory.md)
for the Kalshi signal-factory pipeline architecture and runbook.

## Testing

Tests are split into unit and integration suites:

```bash
make test-unit          # Fast unit tests with mocked I/O
make test-integration   # Integration tests exercising capture/replay/artifact paths
make test               # Full suite (unit + integration)
```

Integration tests cover:

- **Public API capture**: Kalshi universe scan, manual drop capture, crypto proxy
  observation loop, probability breadth scout (with fake/injected sessions).
- **Local DB artifacts**: SQLite/alembic schema, DuckDB analytical store, manual
  drop filesystem paths.
- **Replay gates**: Signal factory status routing, EV ledger replay, crypto proxy
  research candidate replay against cost/capacity/correlation/decay gates.

## Environment Variables

Required environment variables are documented in [.env.template](.env.template).
Key variables:

- `KALSHI_API_KEY` / `KALSHI_API_SECRET` - Kalshi v2 API credentials
- `KALSHI_USE_DEMO` - Set to `true` for demo environment
- `KALSHI_API_URL` / `KALSHI_DEMO_API_URL` - Kalshi API endpoints

## Code Quality

```bash
make lint       # ruff check
make format     # ruff format
make typecheck  # mypy
```

Pre-commit hooks enforce linting, formatting, and secret scanning. Install with:

```bash
pip install pre-commit
pre-commit install
```

## Project Structure

```
predmarket/        # Core prediction-market research modules
  kalshi_*.py      # Kalshi-specific research (ranking, paper ledger, cycle, universe scan)
  type2_*.py       # Type 2 sportsbook reference and paper matching
  dashboard/       # Dash dashboard server
  config.py        # Pydantic configuration
  store.py         # SQLAlchemy data store
  ingest.py        # Async data ingestion
  execution.py     # Execution layer (Kalshi-only)
scripts/           # Standalone research scripts (signal factory, EV ledger, etc.)
tests/             # Test suite
  unit/            # Unit tests (fast, mocked I/O)
  integration/     # Integration tests (artifact replay, capture paths)
docs/              # Documentation
  architecture/    # Architecture diagrams and runbooks
  codex/           # Codex runway (current state, tranches, artifacts)
```
