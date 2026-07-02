.PHONY: setup check-env test test-unit test-integration lint lint-baseline-check lint-baseline-regen format typecheck modularize deadcode deptry dup-check tech-debt tech-debt-check tech-debt-regen file-sizes file-sizes-check file-sizes-regen feature-flags-check validate-agents sync-labels quality-metrics quality run clean coverage openapi kalshi-discovery kalshi-rank kalshi-cycle kalshi-ledger kalshi-desk kalshi-smoke kalshi-verify kalshi-manual-drop-capture kalshi-universe-scan kalshi-universe-watch-once kalshi-signal-factory-status kalshi-hypothesis-registry kalshi-labeled-observation-builder kalshi-labeled-observation-watch-once kalshi-labeled-oos-backtest kalshi-probability-breadth-scout kalshi-probability-breadth-watch-once kalshi-crypto-proxy-feature-packet kalshi-crypto-proxy-feature-watch-once kalshi-crypto-proxy-observation-loop kalshi-crypto-proxy-observation-watch-once kalshi-crypto-proxy-feature-model-falsification kalshi-crypto-proxy-research-candidate-replay kalshi-crypto-proxy-capacity-correlation-decay kalshi-crypto-proxy-correlation-cluster-control type2-reference-build type2-reference-preflight type2-paper-matcher type2-candidate-disposition type2-threshold-sensitivity kalshi-ev-ledger kalshi-ev-overlay-preflight kalshi-ev-calibration-work-order kalshi-ev-contract-mapping-work-order kalshi-ev-local-contract-evidence-scout kalshi-ev-nfl-overlay-assembler kalshi-ev-review-queue kalshi-ev-queue-robustness macro-status macro-route macro-unlock-scout macro-blocker-audit

# Default target
help:
	@echo "Kalshi Action Alpha — Makefile targets"
	@echo ""
	@echo "  make setup     — Create venv and install dependencies"
	@echo "  make check-env — Verify runtime imports resolve from the venv"
	@echo "  make test      — Run pytest with coverage"
	@echo "  make test-unit — Run unit tests only (fast, no I/O)"
	@echo "  make test-integration — Run integration tests (capture/replay/artifact paths)"
	@echo "  make lint      — Run ruff linting"
	@echo "  make format    — Run ruff formatting"
	@echo "  make typecheck — Run mypy strict type checking (advisory, config in pyproject.toml)"
	@echo "  make modularize — Enforce import boundaries (import-linter)"
	@echo "  make deadcode  — Advisory dead-code analysis (vulture)"
	@echo "  make dup-check — Duplicate-code analysis (jscpd)"
	@echo "  make tech-debt — Report TODO/FIXME markers; tech-debt-check ratchets vs baseline"
	@echo "  make file-sizes — Report oversized files; file-sizes-check ratchets vs baseline"
	@echo "  make quality   — Run all code-quality gates"
	@echo "  make run       — Start the Kalshi Action platform (alembic upgrade + main)"
	@echo "  make dashboard — Start dashboard server only"
	@echo "  make coverage  — Run tests and generate HTML coverage report"
	@echo "  make openapi   — Export OpenAPI spec to docs/openapi.json"
	@echo "  make kalshi-discovery — Run Kalshi resolved-row discovery from stored rows"
	@echo "  make kalshi-rank — Rank live Kalshi markets in research-only mode"
	@echo "  make kalshi-cycle — Run rank + paper-intent research cycle"
	@echo "  make kalshi-ledger — Audit Kalshi paper ledger"
	@echo "  make kalshi-desk — Show the Kalshi research desk runbook"
	@echo "  make kalshi-smoke — Generate offline Kalshi desk smoke artifacts"
	@echo "  make kalshi-verify — Run Kalshi smoke plus focused tests"
	@echo "  make kalshi-manual-drop-capture — Capture Kalshi MLB market data to manual_drops"
	@echo "  make kalshi-universe-scan — Scan public Kalshi universe into candidate inventory"
	@echo "  make kalshi-universe-watch-once — Safe one-shot universe scan for timer/manual use"
	@echo "  make kalshi-signal-factory-status — Report north-star signal factory gaps"
	@echo "  make kalshi-hypothesis-registry — Build hypothesis registry and falsification gate"
	@echo "  make kalshi-labeled-observation-builder — Build pending/settled OOS label packets"
	@echo "  make kalshi-labeled-observation-watch-once — Fetch public settlements once, then build OOS packets"
	@echo "  make kalshi-labeled-oos-backtest — Run labeled OOS hypothesis falsification"
	@echo "  make kalshi-probability-breadth-scout — Scout fast-settling probability-source routes"
	@echo "  make kalshi-crypto-proxy-feature-packet — Build contract-keyed crypto proxy feature packets"
	@echo "  make kalshi-crypto-proxy-observation-loop — Archive crypto proxy observations and labels"
	@echo "  make kalshi-crypto-proxy-feature-model-falsification — Falsify crypto proxy feature families"
	@echo "  make kalshi-crypto-proxy-research-candidate-replay — Replay research candidates against all-in cost gates"
	@echo "  make kalshi-crypto-proxy-capacity-correlation-decay — Gate replay candidates on depth, clusters, and decay"
	@echo "  make kalshi-crypto-proxy-correlation-cluster-control — Apply cluster exposure controls before overlay"
	@echo "  make type2-reference-build — Build local Type 2 sportsbook reference"
	@echo "  make type2-reference-preflight — Check local sportsbook reference readiness"
	@echo "  make type2-paper-matcher — Run local paper-only Type 2 matcher"
	@echo "  make type2-candidate-disposition — Downgrade Type 2 timing artifacts"
	@echo "  make type2-threshold-sensitivity — Analyze watch-only Type 2 threshold distance"
	@echo "  make kalshi-ev-ledger — Build federated Kalshi contract EV ledger"
	@echo "  make kalshi-ev-overlay-preflight — Validate local EV mapping/probability overlays"
	@echo "  make kalshi-ev-calibration-work-order — Queue exact contracts needing calibrated probabilities"
	@echo "  make kalshi-ev-contract-mapping-work-order — Queue model rows needing exact Kalshi contract mapping"
	@echo "  make kalshi-ev-local-contract-evidence-scout — Scout local contract evidence for EV mapping"
	@echo "  make kalshi-ev-nfl-overlay-assembler — Assemble NFL EV overlays from ready local evidence"
	@echo "  make kalshi-ev-review-queue — Rank usable fee-aware Kalshi EV rows for review"
	@echo "  make kalshi-ev-queue-robustness — Check review queue across local Kalshi snapshots"
	@echo "  make macro-status — Print this repo's federated macro status JSON"
	@echo "  make macro-route  — Refresh federated macro status/decision artifacts"
	@echo "  make macro-unlock-scout — Write local-only blocker input checklist"
	@echo "  make macro-blocker-audit — Prove whether all macro lanes have exact blockers"
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
TYPE2_KALSHI_JSON ?= data/kalshi_scored_refined_2026-06-16.json
TYPE2_SPORTSBOOK_JSON ?=
TYPE2_REFERENCE_BUILD_ODDS_RAW ?= /home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260620T225933Z.json
TYPE2_REFERENCE_BUILD_ODDS_META ?= /home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260620T225933Z.meta.json
TYPE2_REFERENCE_BUILD_KALSHI_JSON ?= data/kalshi_mlb_game_series_live_current_20260620T230203Z.json
TYPE2_REFERENCE_BUILD_REFERENCE_JSON ?= /home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json
TYPE2_REFERENCE_BUILD_REPORT_DIR ?= docs/codex/artifacts/type2-reference-builder-latest
TYPE2_REFERENCE_BUILD_RUN_ID ?= type2-reference-builder-latest
TYPE2_REFERENCE_BUILD_MAX_DELTA_SECONDS ?= 180
TYPE2_REFERENCE_OUT_DIR ?= docs/codex/artifacts/type2-reference-preflight-latest
TYPE2_REFERENCE_RUN_ID ?= type2-reference-preflight-latest
TYPE2_MATCHER_OUT_DIR ?= docs/codex/artifacts/type2-paper-matcher-latest
TYPE2_MATCHER_RUN_ID ?= type2-paper-matcher-latest
TYPE2_MATCHER_MIN_NET_DIVERGENCE ?= 0.10
TYPE2_MATCHER_UNCERTAINTY_BUFFER ?= 0.00
TYPE2_DISPOSITION_MATCHER_JSON ?= docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json
TYPE2_DISPOSITION_SPORTSBOOK_JSON ?= /home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json
TYPE2_DISPOSITION_KALSHI_JSON ?= data/kalshi_mlb_game_series_live_current_20260620T230203Z.json
TYPE2_DISPOSITION_OUT_DIR ?= docs/codex/artifacts/type2-candidate-disposition-latest
TYPE2_DISPOSITION_RUN_ID ?= type2-candidate-disposition-latest
TYPE2_THRESHOLD_MATCHER_JSON ?= docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json
TYPE2_THRESHOLD_DISPOSITION_JSON ?= docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json
TYPE2_THRESHOLD_OUT_DIR ?= docs/codex/artifacts/type2-threshold-sensitivity-latest
TYPE2_THRESHOLD_RUN_ID ?= type2-threshold-sensitivity-latest
TYPE2_THRESHOLD_GRID ?= 0.10,0.075,0.05,0.025,0.02,0.015,0.01,0.005,0.0
KALSHI_EV_LEDGER_OUT_DIR ?= docs/codex/macro/kalshi-contract-ev-ledger-latest
KALSHI_EV_LEDGER_MAX_ROWS_PER_REPO ?= 500
KALSHI_EV_OVERLAY_PREFLIGHT_OUT_DIR ?= docs/codex/macro/kalshi-ev-overlay-preflight-latest
KALSHI_EV_CALIBRATION_WORK_ORDER_OUT_DIR ?= docs/codex/macro/kalshi-ev-calibration-work-order-latest
KALSHI_EV_CALIBRATION_WORK_ORDER_LIMIT ?= 25
KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_OUT_DIR ?= docs/codex/macro/kalshi-ev-contract-mapping-work-order-latest
KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_LIMIT ?= 32
KALSHI_EV_NFL_FAIR_LINE_REVIEW_PATH ?= /home/mrwatson/projects/nfl_quant_glm51_greenfield/docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json
KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_OUT_DIR ?= docs/codex/macro/kalshi-ev-local-contract-evidence-scout-latest
KALSHI_EV_NFL_OVERLAY_ASSEMBLER_OUT_DIR ?= docs/codex/macro/kalshi-ev-nfl-overlay-assembler-latest
KALSHI_EV_NFL_OVERLAY_ASSEMBLER_LIMIT ?= 32
KALSHI_EV_REVIEW_QUEUE_OUT_DIR ?= docs/codex/macro/kalshi-ev-review-queue-latest
KALSHI_EV_REVIEW_QUEUE_MIN_ROBUST_MARGIN ?= 0.02
KALSHI_EV_REVIEW_QUEUE_MAX_ROWS ?= 100
KALSHI_EV_QUEUE_ROBUSTNESS_OUT_DIR ?= docs/codex/macro/kalshi-ev-queue-robustness-latest
KALSHI_EV_QUEUE_ROBUSTNESS_MIN_ROBUST_MARGIN ?= 0.02
MACRO_BLOCKER_AUDIT_OUT_DIR ?= docs/codex/macro/macro-blocker-audit-latest
KALSHI_MANUAL_DROP_SERIES ?= KXMLBGAME,KXMLBTOTAL,KXMLBSPREAD,KXMLBF5,KXMLBF5TOTAL,KXMLBF5SPREAD
KALSHI_MANUAL_DROP_STATUS ?= open
KALSHI_MANUAL_DROP_LIMIT ?= 100
KALSHI_MANUAL_DROP_MAX_PAGES ?= 1
KALSHI_MANUAL_DROP_DELAY_SECONDS ?= 0.75
KALSHI_MANUAL_DROP_DIR ?= /home/mrwatson/manual_drops/kalshi
KALSHI_MANUAL_DROP_LATEST ?= /home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_latest.json
KALSHI_MANUAL_DROP_REPORT_DIR ?= docs/codex/artifacts/kalshi-manual-drop-capture-latest
KALSHI_MANUAL_DROP_RUN_ID ?= kalshi-manual-drop-capture-latest
KALSHI_UNIVERSE_MIN_CLOSE_HOURS ?= 0
KALSHI_UNIVERSE_MAX_CLOSE_HOURS ?= 72
KALSHI_UNIVERSE_LIMIT ?= 1000
KALSHI_UNIVERSE_MAX_PAGES ?= 10
KALSHI_UNIVERSE_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_universe
KALSHI_UNIVERSE_LATEST_RAW ?= /home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json
KALSHI_UNIVERSE_OUT_DIR ?= docs/codex/macro/kalshi-universe-scan-latest
KALSHI_SIGNAL_FACTORY_STATUS_OUT_DIR ?= docs/codex/macro/kalshi-signal-factory-status-latest
KALSHI_HYPOTHESIS_REGISTRY_OUT_DIR ?= docs/codex/macro/kalshi-hypothesis-registry-latest
KALSHI_HYPOTHESIS_REGISTRY_MAX_EXAMPLES ?= 5
KALSHI_LABELED_OBSERVATION_BUILDER_OUT_DIR ?= docs/codex/macro/kalshi-labeled-observation-builder-latest
KALSHI_LABELED_OBSERVATION_PENDING_DIR ?= /home/mrwatson/manual_drops/kalshi_oos_pending
KALSHI_LABELED_OBSERVATION_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_oos_labels
KALSHI_LABELED_OBSERVATION_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_oos_settlements/kalshi_settled_markets_latest.json
KALSHI_LABELED_OBSERVATION_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_oos_settlements
KALSHI_LABELED_OBSERVATION_SETTLED_LIMIT ?= 1000
KALSHI_LABELED_OBSERVATION_SETTLED_MAX_PAGES ?= 1
KALSHI_LABELED_OOS_BACKTEST_OUT_DIR ?= docs/codex/macro/kalshi-labeled-oos-backtest-latest
KALSHI_LABELED_OOS_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_oos_labels
KALSHI_LABELED_OOS_MIN_OBSERVATIONS ?= 30
KALSHI_LABELED_OOS_MIN_OOS_OBSERVATIONS ?= 10
KALSHI_LABELED_OOS_FDR_ALPHA ?= 0.10
KALSHI_PROBABILITY_BREADTH_OUT_DIR ?= docs/codex/macro/kalshi-probability-breadth-scout-latest
KALSHI_PROBABILITY_BREADTH_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_probability_sources
KALSHI_PROBABILITY_BREADTH_MAX_CLOSE_HOURS ?= 6
KALSHI_PROBABILITY_BREADTH_PROBE ?= 1
KALSHI_CRYPTO_PROXY_FEATURE_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-feature-packet-latest
KALSHI_CRYPTO_PROXY_FEATURE_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_features
KALSHI_CRYPTO_PROXY_FEATURE_RAW_UNIVERSE ?= /home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json
KALSHI_CRYPTO_PROXY_FEATURE_MAX_CLOSE_HOURS ?= 6
KALSHI_CRYPTO_PROXY_FEATURE_MAX_CONTRACTS ?= 1500
KALSHI_CRYPTO_PROXY_FEATURE_CAPTURE ?= 1
KALSHI_CRYPTO_PROXY_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-observation-loop-latest
KALSHI_CRYPTO_PROXY_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_observations
KALSHI_CRYPTO_PROXY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_labels
KALSHI_CRYPTO_PROXY_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_oos_settlements/kalshi_settled_markets_latest.json
KALSHI_CRYPTO_PROXY_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_oos_settlements
KALSHI_CRYPTO_PROXY_SETTLED_LIMIT ?= 1000
KALSHI_CRYPTO_PROXY_SETTLED_MAX_PAGES ?= 1
KALSHI_CRYPTO_PROXY_OBSERVATION_CAPTURE_SETTLED ?= 1
KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_OBSERVED ?= 1
KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_MAX_TICKERS ?= 300
KALSHI_CRYPTO_PROXY_MODEL_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-feature-model-falsification-latest
KALSHI_CRYPTO_PROXY_MODEL_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_labels
KALSHI_CRYPTO_PROXY_MODEL_MIN_INDEPENDENT_LABELS ?= 30
KALSHI_CRYPTO_PROXY_MODEL_MIN_OOS_LABELS ?= 10
KALSHI_CRYPTO_PROXY_MODEL_TEST_FRACTION ?= 0.30
KALSHI_CRYPTO_PROXY_MODEL_FDR_ALPHA ?= 0.10
KALSHI_CRYPTO_PROXY_REPLAY_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-research-candidate-replay-latest
KALSHI_CRYPTO_PROXY_REPLAY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_labels
KALSHI_CRYPTO_PROXY_REPLAY_MODEL_PATH ?= docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.json
KALSHI_CRYPTO_PROXY_REPLAY_MIN_SIDE_OOS_LABELS ?= 30
KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_BUCKETS ?= 3
KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_LABELS ?= 100
KALSHI_CRYPTO_PROXY_CCD_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-capacity-correlation-decay-latest
KALSHI_CRYPTO_PROXY_CCD_FEATURE_PACKET ?= docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.json
KALSHI_CRYPTO_PROXY_CCD_REPLAY ?= docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.json
KALSHI_CRYPTO_PROXY_CCD_RAW_ORDERBOOK_DIR ?= /home/mrwatson/manual_drops/kalshi_crypto_proxy_orderbooks
KALSHI_CRYPTO_PROXY_CCD_MAX_CLOSE_HOURS ?= 6
KALSHI_CRYPTO_PROXY_CCD_MAX_TICKERS ?= 60
KALSHI_CRYPTO_PROXY_CCD_DEPTH ?= 0
KALSHI_CRYPTO_PROXY_CCD_DELAY_SECONDS ?= 0.05
KALSHI_CRYPTO_PROXY_CCD_CAPTURE_ORDERBOOKS ?= 1
KALSHI_CRYPTO_PROXY_CLUSTER_OUT_DIR ?= docs/codex/macro/kalshi-crypto-proxy-correlation-cluster-control-latest
KALSHI_CRYPTO_PROXY_CLUSTER_CCD ?= docs/codex/macro/latest-kalshi-crypto-proxy-capacity-correlation-decay.json
KALSHI_CRYPTO_PROXY_CLUSTER_MAX_SHARE ?= 0.35
KALSHI_CRYPTO_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS ?= 0
export PATH := $(abspath $(VENV))/bin:$(PATH)

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

setup: $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -r dev-requirements.txt
	@echo "Setup complete. Activate with: source $(VENV)/bin/activate"

$(TMPDIR):
	mkdir -p $(TMPDIR)

check-env: $(VENV)
	PYTHONPATH=. $(PYTHON) -c "import prometheus_client, aiohttp; from pythonjsonlogger.json import JsonFormatter; import predmarket.execution; print('runtime imports ok')"

# ---- Testing ----
test: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/ -v --tb=short --durations=10 --durations-min=0.5

test-unit: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/ -v --tb=short -m "not integration" --durations=10 --durations-min=0.5

test-integration: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/integration/ -v --tb=short

coverage: | $(TMPDIR)
	TMPDIR=$(TMPDIR) PYTHONPATH=. $(PYTEST) tests/ --cov=predmarket --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

lint:
	$(PIP) install -q ruff 2>/dev/null || true
	$(VENV)/bin/ruff check predmarket/ tests/ main.py || echo "ruff not installed — run 'make setup' first"

lint-baseline-check:
	@python3 scripts/ruff_baseline_check.py

lint-baseline-regen:
	@echo "Regenerating .ruff-baseline.json ..."
	@lint=$$(ruff check --output-format=json --exit-zero predmarket/ tests/ main.py | python3 -c "import json,sys; print(len(json.load(sys.stdin)))") && \
	fmt=$$(ruff format --check predmarket/ tests/ main.py 2>/dev/null | grep -c "^Would reformat:" || echo 0) && \
	python3 -c "import json; json.dump({'lint_error_count': $$lint, 'format_file_count': $$fmt}, open('.ruff-baseline.json','w'), indent=2); print()" && \
	cat .ruff-baseline.json

format:
	$(PIP) install -q ruff 2>/dev/null || true
	$(VENV)/bin/ruff format predmarket/ tests/ main.py

typecheck:
	$(PIP) install -q mypy 2>/dev/null || true
	@echo "Running mypy (strict, config in pyproject.toml)..."
	@count=$$($(VENV)/bin/mypy predmarket/ 2>&1 | tee /dev/stderr | grep -c "error:") && \
	echo "---- mypy strict errors: $$count (ratchet this down over time) ----"

# ---- Code quality tooling (configured in pyproject.toml) ----
# These targets run the full-tree analyses. The ratcheted gates (tech-debt,
# file-sizes) compare against committed baselines; the advisory ones (deadcode,
# dup-check, typecheck) surface findings for triage.

modularize:
	@echo "Checking import boundaries (import-linter)..."
	@PYTHONPATH=. $(VENV)/bin/lint-imports || echo "lint-imports not installed — run 'pip install import-linter'"

deadcode:
	$(PIP) install -q vulture 2>/dev/null || true
	@echo "Running vulture (advisory dead-code analysis)..."
	@PYTHONPATH=. $(VENV)/bin/vulture predmarket/ scripts/ --min-confidence 60 || true

dup-check:
	@command -v npx >/dev/null 2>&1 || { echo "npx (Node) required for jscpd"; exit 1; }
	@echo "Running jscpd duplicate-code analysis (config: .jscpd.json)..."
	@npx --yes jscpd predmarket scripts main.py || true

tech-debt:
	@PYTHONPATH=. $(PYTHON) scripts/scan_tech_debt.py

tech-debt-check:
	@PYTHONPATH=. $(PYTHON) scripts/scan_tech_debt.py --check

tech-debt-regen:
	@PYTHONPATH=. $(PYTHON) scripts/scan_tech_debt.py --regen

file-sizes:
	@PYTHONPATH=. $(PYTHON) scripts/check_file_sizes.py

file-sizes-check:
	@PYTHONPATH=. $(PYTHON) scripts/check_file_sizes.py --check

file-sizes-regen:
	@PYTHONPATH=. $(PYTHON) scripts/check_file_sizes.py --regen

# Aggregate: run every configured code-quality gate.
quality: lint typecheck modularize deadcode deptry tech-debt-check file-sizes-check feature-flags-check validate-agents
	@echo "All code-quality gates reported (some are advisory; see output above)."

deptry:
	$(PIP) install -q deptry 2>/dev/null || true
	@echo "Running deptry (unused dependency detection)..."
	@PYTHONPATH=. $(VENV)/bin/deptry predmarket/ || true

validate-agents:
	@PYTHONPATH=. $(PYTHON) scripts/validate_agents_md.py --check

feature-flags-check:
	@PYTHONPATH=. $(PYTHON) scripts/check_feature_flags.py

quality-metrics:
	@echo "Collecting code-quality metrics..."
	@mkdir -p .tmp
	@PYTHONPATH=. $(PYTHON) scripts/collect_quality_metrics.py --output .tmp/quality-metrics.json
	@echo "Quality metrics written to .tmp/quality-metrics.json"

sync-labels:
	@PYTHONPATH=. $(PYTHON) scripts/sync_labels.py --apply

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
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_discovery

kalshi-rank:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_live_rank

kalshi-cycle:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_research_cycle

kalshi-ledger:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_paper_ledger

kalshi-desk:
	@sed -n '1,220p' docs/kalshi_research_desk.md

kalshi-smoke:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_research_smoke

kalshi-verify: | $(TMPDIR)
	@$(MAKE) --no-print-directory kalshi-smoke > $(TMPDIR)/kalshi-smoke.json
	@$(PYTHON) -m json.tool $(TMPDIR)/kalshi-smoke.json > $(TMPDIR)/kalshi-smoke.pretty.json
	TMPDIR=$(TMPDIR) TMP=$(TMPDIR) TEMP=$(TMPDIR) PYTHONPATH=. $(PYTEST) \
		tests/test_kalshi_only_runtime.py \
		tests/test_kalshi_research_cycle.py \
		tests/test_kalshi_paper_ledger.py \
		tests/test_kalshi_research_smoke.py \
		tests/test_kalshi_live_rank.py \
		tests/test_kalshi_discovery.py \
		tests/test_kalshi_dataset.py \
		-q --tb=short

kalshi-manual-drop-capture:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_manual_drop_capture \
		--series-tickers $(KALSHI_MANUAL_DROP_SERIES) \
		--status $(KALSHI_MANUAL_DROP_STATUS) \
		--limit $(KALSHI_MANUAL_DROP_LIMIT) \
		--max-pages $(KALSHI_MANUAL_DROP_MAX_PAGES) \
		--delay-seconds $(KALSHI_MANUAL_DROP_DELAY_SECONDS) \
		--output-dir $(KALSHI_MANUAL_DROP_DIR) \
		--latest-path $(KALSHI_MANUAL_DROP_LATEST) \
		--report-dir $(KALSHI_MANUAL_DROP_REPORT_DIR) \
		--run-id $(KALSHI_MANUAL_DROP_RUN_ID)

kalshi-universe-scan:
	@PYTHONPATH=. $(PYTHON) -m predmarket.kalshi_universe_scan \
		--write \
		--min-close-hours $(KALSHI_UNIVERSE_MIN_CLOSE_HOURS) \
		--max-close-hours $(KALSHI_UNIVERSE_MAX_CLOSE_HOURS) \
		--limit $(KALSHI_UNIVERSE_LIMIT) \
		--max-pages $(KALSHI_UNIVERSE_MAX_PAGES) \
		--raw-output-dir $(KALSHI_UNIVERSE_RAW_DIR) \
		--latest-raw-path $(KALSHI_UNIVERSE_LATEST_RAW) \
		--out-dir $(KALSHI_UNIVERSE_OUT_DIR)

kalshi-universe-watch-once:
	@$(MAKE) --no-print-directory kalshi-universe-scan

kalshi-signal-factory-status:
	@python3 scripts/kalshi_signal_factory_status.py \
		--write \
		--out-dir $(KALSHI_SIGNAL_FACTORY_STATUS_OUT_DIR)

kalshi-hypothesis-registry:
	@python3 scripts/kalshi_hypothesis_registry.py \
		--write \
		--out-dir $(KALSHI_HYPOTHESIS_REGISTRY_OUT_DIR) \
		--max-examples-per-hypothesis $(KALSHI_HYPOTHESIS_REGISTRY_MAX_EXAMPLES)

kalshi-labeled-observation-builder:
	@python3 scripts/kalshi_labeled_observation_builder.py \
		--write \
		--out-dir $(KALSHI_LABELED_OBSERVATION_BUILDER_OUT_DIR) \
		--pending-dir $(KALSHI_LABELED_OBSERVATION_PENDING_DIR) \
		--label-dir $(KALSHI_LABELED_OBSERVATION_LABEL_DIR) \
		--settled-snapshot-path $(KALSHI_LABELED_OBSERVATION_SETTLED_SNAPSHOT)

kalshi-labeled-observation-watch-once:
	@python3 scripts/kalshi_labeled_observation_builder.py \
		--write \
		--capture-settled-public \
		--settled-raw-dir $(KALSHI_LABELED_OBSERVATION_SETTLED_RAW_DIR) \
		--settled-limit $(KALSHI_LABELED_OBSERVATION_SETTLED_LIMIT) \
		--settled-max-pages $(KALSHI_LABELED_OBSERVATION_SETTLED_MAX_PAGES) \
		--out-dir $(KALSHI_LABELED_OBSERVATION_BUILDER_OUT_DIR) \
		--pending-dir $(KALSHI_LABELED_OBSERVATION_PENDING_DIR) \
		--label-dir $(KALSHI_LABELED_OBSERVATION_LABEL_DIR)

kalshi-labeled-oos-backtest:
	@python3 scripts/kalshi_labeled_oos_backtest.py \
		--write \
		--label-dir $(KALSHI_LABELED_OOS_LABEL_DIR) \
		--out-dir $(KALSHI_LABELED_OOS_BACKTEST_OUT_DIR) \
		--min-observations $(KALSHI_LABELED_OOS_MIN_OBSERVATIONS) \
		--min-oos-observations $(KALSHI_LABELED_OOS_MIN_OOS_OBSERVATIONS) \
		--fdr-alpha $(KALSHI_LABELED_OOS_FDR_ALPHA)

kalshi-probability-breadth-scout:
	@python3 scripts/kalshi_probability_breadth_scout.py \
		--write \
		--max-close-hours $(KALSHI_PROBABILITY_BREADTH_MAX_CLOSE_HOURS) \
		--out-dir $(KALSHI_PROBABILITY_BREADTH_OUT_DIR) \
		--raw-probe-dir $(KALSHI_PROBABILITY_BREADTH_RAW_DIR) \
		$(if $(filter 1 true yes,$(KALSHI_PROBABILITY_BREADTH_PROBE)),--probe-public-sources,)

kalshi-probability-breadth-watch-once:
	@$(MAKE) --no-print-directory kalshi-probability-breadth-scout

kalshi-crypto-proxy-feature-packet:
	@python3 scripts/kalshi_crypto_proxy_feature_packet.py \
		--write \
		--max-close-hours $(KALSHI_CRYPTO_PROXY_FEATURE_MAX_CLOSE_HOURS) \
		--max-contracts $(KALSHI_CRYPTO_PROXY_FEATURE_MAX_CONTRACTS) \
		--raw-universe-path $(KALSHI_CRYPTO_PROXY_FEATURE_RAW_UNIVERSE) \
		--raw-proxy-dir $(KALSHI_CRYPTO_PROXY_FEATURE_RAW_DIR) \
		--out-dir $(KALSHI_CRYPTO_PROXY_FEATURE_OUT_DIR) \
		$(if $(filter 1 true yes,$(KALSHI_CRYPTO_PROXY_FEATURE_CAPTURE)),--capture-public-proxy,)

kalshi-crypto-proxy-feature-watch-once:
	@$(MAKE) --no-print-directory kalshi-universe-watch-once
	@$(MAKE) --no-print-directory kalshi-probability-breadth-scout
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-feature-packet

kalshi-crypto-proxy-observation-loop:
	@python3 scripts/kalshi_crypto_proxy_observation_loop.py \
		--write \
		--out-dir $(KALSHI_CRYPTO_PROXY_OBSERVATION_OUT_DIR) \
		--observation-dir $(KALSHI_CRYPTO_PROXY_OBSERVATION_DIR) \
		--label-dir $(KALSHI_CRYPTO_PROXY_LABEL_DIR) \
		--settled-snapshot-path $(KALSHI_CRYPTO_PROXY_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_CRYPTO_PROXY_SETTLED_RAW_DIR) \
		--settled-limit $(KALSHI_CRYPTO_PROXY_SETTLED_LIMIT) \
		--settled-max-pages $(KALSHI_CRYPTO_PROXY_SETTLED_MAX_PAGES) \
		--observed-probe-max-tickers $(KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_OBSERVED)),--probe-observed-public,) \
		$(if $(filter 1 true yes,$(KALSHI_CRYPTO_PROXY_OBSERVATION_CAPTURE_SETTLED)),--capture-settled-public,)

kalshi-crypto-proxy-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-feature-watch-once
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-observation-loop
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-feature-model-falsification
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-research-candidate-replay
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-capacity-correlation-decay
	@$(MAKE) --no-print-directory kalshi-crypto-proxy-correlation-cluster-control
	@$(MAKE) --no-print-directory kalshi-signal-factory-status
	@$(MAKE) --no-print-directory macro-route

kalshi-crypto-proxy-feature-model-falsification:
	@python3 scripts/kalshi_crypto_proxy_feature_model_falsification.py \
		--write \
		--label-dir $(KALSHI_CRYPTO_PROXY_MODEL_LABEL_DIR) \
		--out-dir $(KALSHI_CRYPTO_PROXY_MODEL_OUT_DIR) \
		--min-independent-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_OOS_LABELS) \
		--test-fraction $(KALSHI_CRYPTO_PROXY_MODEL_TEST_FRACTION) \
		--fdr-alpha $(KALSHI_CRYPTO_PROXY_MODEL_FDR_ALPHA)

kalshi-crypto-proxy-research-candidate-replay:
	@python3 scripts/kalshi_crypto_proxy_research_candidate_replay.py \
		--write \
		--label-dir $(KALSHI_CRYPTO_PROXY_REPLAY_LABEL_DIR) \
		--model-falsification-path $(KALSHI_CRYPTO_PROXY_REPLAY_MODEL_PATH) \
		--out-dir $(KALSHI_CRYPTO_PROXY_REPLAY_OUT_DIR) \
		--min-side-oos-labels $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_SIDE_OOS_LABELS) \
		--min-decay-buckets $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_BUCKETS) \
		--min-decay-labels $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_LABELS)

kalshi-crypto-proxy-capacity-correlation-decay:
	@python3 scripts/kalshi_crypto_proxy_capacity_correlation_decay.py \
		--write \
		--feature-packet-path $(KALSHI_CRYPTO_PROXY_CCD_FEATURE_PACKET) \
		--replay-path $(KALSHI_CRYPTO_PROXY_CCD_REPLAY) \
		--raw-orderbook-dir $(KALSHI_CRYPTO_PROXY_CCD_RAW_ORDERBOOK_DIR) \
		--out-dir $(KALSHI_CRYPTO_PROXY_CCD_OUT_DIR) \
		--max-close-hours $(KALSHI_CRYPTO_PROXY_CCD_MAX_CLOSE_HOURS) \
		--max-tickers $(KALSHI_CRYPTO_PROXY_CCD_MAX_TICKERS) \
		--depth $(KALSHI_CRYPTO_PROXY_CCD_DEPTH) \
		--delay-seconds $(KALSHI_CRYPTO_PROXY_CCD_DELAY_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_CRYPTO_PROXY_CCD_CAPTURE_ORDERBOOKS)),--capture-orderbooks,)

kalshi-crypto-proxy-correlation-cluster-control:
	@python3 scripts/kalshi_crypto_proxy_correlation_cluster_control.py \
		--write \
		--ccd-path $(KALSHI_CRYPTO_PROXY_CLUSTER_CCD) \
		--out-dir $(KALSHI_CRYPTO_PROXY_CLUSTER_OUT_DIR) \
		--max-cluster-share $(KALSHI_CRYPTO_PROXY_CLUSTER_MAX_SHARE) \
		--min-positive-clusters $(KALSHI_CRYPTO_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS)

type2-reference-build:
	@PYTHONPATH=. $(PYTHON) -m predmarket.type2_reference_builder \
		--odds-raw-json $(TYPE2_REFERENCE_BUILD_ODDS_RAW) \
		--odds-meta-json $(TYPE2_REFERENCE_BUILD_ODDS_META) \
		--kalshi-json $(TYPE2_REFERENCE_BUILD_KALSHI_JSON) \
		--reference-json $(TYPE2_REFERENCE_BUILD_REFERENCE_JSON) \
		--report-dir $(TYPE2_REFERENCE_BUILD_REPORT_DIR) \
		--run-id $(TYPE2_REFERENCE_BUILD_RUN_ID) \
		--max-event-delta-seconds $(TYPE2_REFERENCE_BUILD_MAX_DELTA_SECONDS)

type2-reference-preflight:
	@args="--kalshi-json $(TYPE2_KALSHI_JSON) --output-dir $(TYPE2_REFERENCE_OUT_DIR) --run-id $(TYPE2_REFERENCE_RUN_ID)"; \
	if [ -n "$(TYPE2_SPORTSBOOK_JSON)" ]; then args="$$args --sportsbook-json $(TYPE2_SPORTSBOOK_JSON)"; fi; \
	PYTHONPATH=. $(PYTHON) -m predmarket.type2_reference_intake $$args

type2-paper-matcher:
	@args="--kalshi-json $(TYPE2_KALSHI_JSON) --output-dir $(TYPE2_MATCHER_OUT_DIR) --run-id $(TYPE2_MATCHER_RUN_ID) --min-net-divergence $(TYPE2_MATCHER_MIN_NET_DIVERGENCE) --uncertainty-buffer $(TYPE2_MATCHER_UNCERTAINTY_BUFFER)"; \
	if [ -n "$(TYPE2_SPORTSBOOK_JSON)" ]; then args="$$args --sportsbook-json $(TYPE2_SPORTSBOOK_JSON)"; fi; \
	PYTHONPATH=. $(PYTHON) -m predmarket.type2_paper_matcher $$args

type2-candidate-disposition:
	@PYTHONPATH=. $(PYTHON) -m predmarket.type2_candidate_disposition \
		--paper-matcher-json $(TYPE2_DISPOSITION_MATCHER_JSON) \
		--sportsbook-json $(TYPE2_DISPOSITION_SPORTSBOOK_JSON) \
		--kalshi-json $(TYPE2_DISPOSITION_KALSHI_JSON) \
		--output-dir $(TYPE2_DISPOSITION_OUT_DIR) \
		--run-id $(TYPE2_DISPOSITION_RUN_ID)

type2-threshold-sensitivity:
	@PYTHONPATH=. $(PYTHON) -m predmarket.type2_threshold_sensitivity \
		--paper-matcher-json $(TYPE2_THRESHOLD_MATCHER_JSON) \
		--disposition-json $(TYPE2_THRESHOLD_DISPOSITION_JSON) \
		--output-dir $(TYPE2_THRESHOLD_OUT_DIR) \
		--run-id $(TYPE2_THRESHOLD_RUN_ID) \
		--thresholds $(TYPE2_THRESHOLD_GRID)

kalshi-ev-ledger:
	@python3 scripts/kalshi_contract_ev_ledger.py \
		--write \
		--out-dir $(KALSHI_EV_LEDGER_OUT_DIR) \
		--max-rows-per-repo $(KALSHI_EV_LEDGER_MAX_ROWS_PER_REPO)

kalshi-ev-overlay-preflight:
	@python3 scripts/kalshi_contract_ev_ledger.py \
		--overlay-preflight \
		--write \
		--out-dir $(KALSHI_EV_OVERLAY_PREFLIGHT_OUT_DIR) \
		--max-rows-per-repo $(KALSHI_EV_LEDGER_MAX_ROWS_PER_REPO)

kalshi-ev-calibration-work-order:
	@python3 scripts/kalshi_contract_ev_ledger.py \
		--calibration-work-order \
		--write \
		--out-dir $(KALSHI_EV_CALIBRATION_WORK_ORDER_OUT_DIR) \
		--max-rows-per-repo $(KALSHI_EV_LEDGER_MAX_ROWS_PER_REPO) \
		--work-order-limit $(KALSHI_EV_CALIBRATION_WORK_ORDER_LIMIT)

kalshi-ev-contract-mapping-work-order:
	@python3 scripts/kalshi_contract_ev_ledger.py \
		--contract-mapping-work-order \
		--write \
		--out-dir $(KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_OUT_DIR) \
		--work-order-limit $(KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_LIMIT) \
		--nfl-fair-line-review-path $(KALSHI_EV_NFL_FAIR_LINE_REVIEW_PATH)

kalshi-ev-local-contract-evidence-scout:
	@python3 scripts/kalshi_ev_local_contract_evidence_scout.py \
		--write \
		--out-dir $(KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_OUT_DIR)

kalshi-ev-nfl-overlay-assembler:
	@python3 scripts/kalshi_ev_nfl_overlay_assembler.py \
		--write \
		--limit $(KALSHI_EV_NFL_OVERLAY_ASSEMBLER_LIMIT) \
		--out-dir $(KALSHI_EV_NFL_OVERLAY_ASSEMBLER_OUT_DIR)

kalshi-ev-review-queue:
	@python3 scripts/kalshi_ev_review_queue.py \
		--write \
		--out-dir $(KALSHI_EV_REVIEW_QUEUE_OUT_DIR) \
		--min-robust-margin $(KALSHI_EV_REVIEW_QUEUE_MIN_ROBUST_MARGIN) \
		--max-rows $(KALSHI_EV_REVIEW_QUEUE_MAX_ROWS)

kalshi-ev-queue-robustness:
	@python3 scripts/kalshi_ev_queue_robustness.py \
		--write \
		--out-dir $(KALSHI_EV_QUEUE_ROBUSTNESS_OUT_DIR) \
		--min-robust-margin $(KALSHI_EV_QUEUE_ROBUSTNESS_MIN_ROBUST_MARGIN)

macro-status:
	@python3 scripts/codex_macro_router.py status --repo-id predmarket-alpha

macro-route:
	@python3 scripts/codex_macro_router.py route --write

macro-unlock-scout:
	@python3 scripts/codex_macro_unlock_scout.py --write

macro-blocker-audit:
	@python3 scripts/codex_macro_blocker_audit.py \
		--write \
		--out-dir $(MACRO_BLOCKER_AUDIT_OUT_DIR)

# ---- Docker ----
docker:
	docker build -t predmarket .

# ---- Cleanup ----
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache .tmp htmlcov dist build *.egg-info
	@echo "Clean complete."
