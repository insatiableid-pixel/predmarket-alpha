.PHONY: setup check-env test lint run clean coverage openapi kalshi-discovery kalshi-rank kalshi-cycle kalshi-ledger

# Default target
help:
	@echo "Kalshi Action Alpha — Makefile targets"
	@echo ""
	@echo "  make setup     — Create venv and install dependencies"
	@echo "  make check-env — Verify runtime imports resolve from the venv"
	@echo "  make test      — Run pytest with coverage"
	@echo "  make lint      — Run ruff linting"
	@echo "  make run       — Start the Kalshi Action platform (alembic upgrade + main)"
	@echo "  make dashboard — Start dashboard server only"
	@echo "  make coverage  — Run tests and generate HTML coverage report"
	@echo "  make openapi   — Export OpenAPI spec to docs/openapi.json"
	@echo "  make kalshi-discovery — Run Kalshi resolved-row discovery from stored rows"
	@echo "  make kalshi-rank — Rank live Kalshi markets in research-only mode"
	@echo "  make kalshi-cycle — Run rank + paper-intent research cycle"
	@echo "  make kalshi-ledger — Audit Kalshi paper ledger"
	@echo "  make clean     — Remove __pycache__, .pytest_cache, build artifacts"
	@echo "  make migrate   — Run Alembic migrations to head"
	@echo "  make docker    — Build Docker image"

# ---- Environment ----
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic
TMPDIR := $(CURDIR)/.tmp
export PATH := $(abspath $(VENV))/bin:$(PATH)

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

setup: $(VENV)
	$(PIP) install -r requirements.txt
	@echo "Setup complete. Activate with: source $(VENV)/bin/activate"

$(TMPDIR):
	mkdir -p $(TMPDIR)

check-env: $(VENV)
	PYTHONPATH=. $(PYTHON) -c "import prometheus_client, aiohttp; from pythonjsonlogger.json import JsonFormatter; import predmarket.execution; print('runtime imports ok')"

# ---- Testing ----
test: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/ -v --tb=short

coverage: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/ --cov=predmarket --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

lint:
	$(PIP) install -q ruff 2>/dev/null || true
	$(VENV)/bin/ruff check predmarket/ tests/ main.py || echo "ruff not installed — run 'make setup' first"

# ---- Running ----
run:
	$(ALEMBIC) upgrade head
	PYTHONPATH=. $(PYTHON) main.py

dashboard:
	PYTHONPATH=. $(PYTHON) -m uvicorn predmarket.dashboard:server --host 0.0.0.0 --port 8050

# ---- Database ----
migrate:
	$(ALEMBIC) upgrade head

# ---- Docs ----
openapi:
	@echo "Starting server to export OpenAPI spec..."
	PYTHONPATH=. $(PYTHON) -c "\
		import json, time, threading; \
		from predmarket.dashboard import server; \
		import uvicorn; \
		t = threading.Thread(target=uvicorn.run, args=(server,), kwargs={'host':'127.0.0.1','port':8051}, daemon=True); \
		t.start(); \
		time.sleep(2); \
		import urllib.request; \
		resp = urllib.request.urlopen('http://127.0.0.1:8051/openapi.json'); \
		spec = json.loads(resp.read()); \
		Path('docs').mkdir(exist_ok=True); \
		json.dump(spec, open('docs/openapi.json','w'), indent=2); \
		print('docs/openapi.json written') \
	"

kalshi-discovery:
	PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_discovery

kalshi-rank:
	PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_live_rank

kalshi-cycle:
	PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_research_cycle

kalshi-ledger:
	PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_paper_ledger

# ---- Docker ----
docker:
	docker build -t predmarket .

# ---- Cleanup ----
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache .tmp htmlcov dist build *.egg-info
	@echo "Clean complete."
