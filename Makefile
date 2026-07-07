.PHONY: setup check-env test test-unit test-integration lint lint-baseline-check lint-baseline-regen format typecheck modularize deadcode deptry dup-check tech-debt tech-debt-check tech-debt-regen file-sizes file-sizes-check file-sizes-regen feature-flags-check validate-agents sync-labels quality-metrics quality run clean coverage openapi kalshi-discovery kalshi-rank kalshi-cycle kalshi-ledger kalshi-desk kalshi-smoke kalshi-verify kalshi-manual-drop-capture kalshi-universe-scan kalshi-universe-watch-once kalshi-signal-factory-status kalshi-hypothesis-registry kalshi-labeled-observation-builder kalshi-labeled-observation-watch-once kalshi-labeled-oos-backtest kalshi-probability-breadth-scout kalshi-probability-breadth-watch-once kalshi-crypto-proxy-feature-packet kalshi-crypto-proxy-feature-watch-once kalshi-crypto-proxy-observation-loop kalshi-crypto-proxy-observation-watch-once kalshi-crypto-proxy-feature-model-falsification kalshi-crypto-proxy-research-candidate-replay kalshi-crypto-proxy-capacity-correlation-decay kalshi-crypto-proxy-correlation-cluster-control kalshi-sports-proxy-feature-packet kalshi-sports-proxy-observation-loop kalshi-sports-proxy-observation-watch-once kalshi-atp-proxy-observation-loop kalshi-atp-proxy-evidence-gate kalshi-atp-proxy-observation-watch-once kalshi-world-cup-proxy-observation-loop kalshi-world-cup-proxy-feature-model-falsification kalshi-world-cup-outcome-independence-diagnostic kalshi-world-cup-proxy-observation-watch-once kalshi-ghost-listing-depth-diagnostic kalshi-sports-stack-sequencing kalshi-sports-consensus-reference-build kalshi-sports-consensus-sharp-provider-capture kalshi-sports-consensus-soccer-asian-provider-diagnostic kalshi-sports-consensus-public-kalshi-refresh kalshi-sports-consensus-atp-donor-adapter kalshi-sports-consensus-nfl-adapter kalshi-sports-consensus-soccer-adapter kalshi-sports-consensus-nba-adapter kalshi-sports-consensus-refresh kalshi-sports-consensus-preflight kalshi-sports-consensus-observation-loop kalshi-sports-consensus-observation-watch-once kalshi-sports-consensus-falsification kalshi-resolved-archive-backfill kalshi-sports-historical-consensus-feasibility kalshi-sports-consensus-provider-audit kalshi-sports-event-velocity-eta kalshi-claude-advice-audit kalshi-sports-blocker-clearance-cycle kalshi-sports-line-move-delta-logger kalshi-tick-recorder kalshi-sports-microstructure-observation-loop kalshi-sports-microstructure-observation-watch-once kalshi-near-resolution-informed-flow-evidence-gate kalshi-near-resolution-flow-replay-gates kalshi-near-resolution-flow-terms-capture kalshi-passive-liquidity-provision-evidence-gate kalshi-passive-liquidity-paper-fill-loop kalshi-passive-liquidity-paper-fill-falsification kalshi-passive-liquidity-fill-clock-diagnostic kalshi-sports-nondirectional-evidence-watch-once kalshi-sports-evidence-cycle-report kalshi-sports-evidence-cycle kalshi-sports-label-accumulation-cycle kalshi-sports-paper-burn-in-cycle kalshi-always-on-collector kalshi-always-on-collector-once kalshi-sports-proxy-feature-model-falsification kalshi-sports-proxy-research-candidate-replay kalshi-sports-proxy-capacity-correlation-decay kalshi-sports-proxy-correlation-cluster-control kalshi-weather-proxy-feature-packet kalshi-weather-proxy-feature-watch-once kalshi-weather-proxy-observation-loop kalshi-weather-proxy-observation-watch-once kalshi-weather-proxy-feature-model-falsification kalshi-weather-proxy-research-candidate-replay kalshi-weather-proxy-capacity-correlation-decay kalshi-weather-proxy-correlation-cluster-control type2-reference-build type2-reference-preflight type2-paper-matcher type2-candidate-disposition type2-threshold-sensitivity kalshi-source-repo-inventory kalshi-external-artifact-wrap kalshi-external-artifact-preflight kalshi-signal-formula-registry kalshi-prior-only-donor-gate kalshi-paper-decision-candidates kalshi-paper-settlement-reconcile kalshi-signal-decay-retirement kalshi-jurisdiction-refresh kalshi-live-preflight kalshi-live-demo kalshi-live-trader kalshi-live-reconcile kalshi-live-risk-snapshot kalshi-ev-ledger kalshi-ev-overlay-preflight kalshi-ev-calibration-work-order kalshi-ev-contract-mapping-work-order kalshi-ev-local-contract-evidence-scout kalshi-ev-nfl-overlay-assembler kalshi-ev-review-queue kalshi-ev-queue-robustness macro-status macro-route macro-unlock-scout macro-blocker-audit

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
	@echo "  make kalshi-sports-proxy-feature-packet — Build contract-keyed baseball proxy feature packets"
	@echo "  make kalshi-sports-proxy-feature-model-falsification — Falsify sports proxy strength model against settled labels"
	@echo "  make kalshi-sports-proxy-research-candidate-replay — Replay sports research candidates against all-in cost gates"
	@echo "  make kalshi-sports-proxy-capacity-correlation-decay — Gate sports replay candidates on depth, clusters, and decay"
	@echo "  make kalshi-sports-proxy-correlation-cluster-control — Apply cluster exposure controls to sports candidates before overlay"
	@echo "  make kalshi-world-cup-proxy-observation-loop — Archive World Cup/FIFA soft-watch rows as research evidence"
	@echo "  make kalshi-world-cup-proxy-feature-model-falsification — Falsify World Cup market-structure rules"
	@echo "  make kalshi-world-cup-outcome-independence-diagnostic — Diagnose World Cup outcome-family labels vs match correlation"
	@echo "  make kalshi-ghost-listing-depth-diagnostic — Probe current public depth before cap_i lock"
	@echo "  make kalshi-sports-stack-sequencing — Sequence sports lanes by current season/evidence"
	@echo "  make kalshi-sports-consensus-reference-build — Build derived no-vig sports consensus reference"
	@echo "  make kalshi-sports-consensus-sharp-provider-capture — Probe sharp provider availability across target sports"
	@echo "  make kalshi-sports-consensus-refresh — Fetch current odds, build consensus reference, then preflight"
	@echo "  make kalshi-sports-consensus-preflight — Validate timestamp-matched no-vig multi-book sports consensus"
	@echo "  make kalshi-sports-consensus-nfl-adapter — Adapt NFL sharp consensus rows into strict manifest"
	@echo "  make kalshi-sports-consensus-soccer-adapter — Adapt World Cup sharp consensus rows into strict manifest"
	@echo "  make kalshi-sports-consensus-nba-adapter — Adapt NBA sharp consensus rows into strict manifest"
	@echo "  make kalshi-sports-consensus-observation-loop — Archive no-vig consensus observations and exact Kalshi labels"
	@echo "  make kalshi-sports-consensus-observation-watch-once — Refresh, archive consensus observations, probe labels, then falsify"
	@echo "  make kalshi-sports-consensus-falsification — OOS/FDR-test Kalshi-vs-consensus divergence before any paper sizing"
	@echo "  make kalshi-resolved-archive-backfill — Backfill settled Kalshi sports prices into bucket-bias falsification"
	@echo "  make kalshi-sports-historical-consensus-feasibility — Check historical consensus skew and paid-access gate"
	@echo "  make kalshi-sports-consensus-provider-audit — Audit sharp-provider coverage per sport"
	@echo "  make kalshi-sports-event-velocity-eta — Report per-surface sports label/OOS/paper-fill deficits"
	@echo "  make kalshi-claude-advice-audit — Audit implementation status against Claude sports advice"
	@echo "  make kalshi-sports-blocker-clearance-cycle — Plan/run due sports blocker refreshes without lowering gates"
	@echo "  make kalshi-sports-line-move-delta-logger — Record sharp sportsbook line-move deltas for stale-quote evidence"
	@echo "  make kalshi-tick-recorder — Record read-only Kalshi sports ticker/orderbook_delta messages"
	@echo "  make kalshi-sports-nondirectional-evidence-watch-once — Capture sports microstructure and run flow/liquidity gates"
	@echo "  make kalshi-passive-liquidity-paper-fill-loop — Persist passive maker paper intents and label prior intents from later snapshots"
	@echo "  make kalshi-passive-liquidity-paper-fill-falsification — Falsify passive maker paper fill labels"
	@echo "  make kalshi-passive-liquidity-fill-clock-diagnostic — Diagnose passive paper fill drought causes"
	@echo "  make kalshi-near-resolution-flow-replay-gates — Replay FDR-surviving flow candidates through cost/depth/decay gates"
	@echo "  make kalshi-sports-evidence-cycle — Refresh sports labels/snapshots/gates and write cycle report"
	@echo "  make kalshi-sports-paper-burn-in-cycle — Advance paper settlement, retirement, and sports evidence audit"
	@echo "  make kalshi-always-on-collector-once — Run one safe collector cycle for sports burn-in + crypto"
	@echo "  make kalshi-always-on-collector — Run continuous safe sports burn-in + crypto collector"
	@echo "  make kalshi-weather-proxy-feature-packet — Build contract-keyed weather proxy feature packets"
	@echo "  make kalshi-weather-proxy-observation-loop — Archive weather proxy observations and labels"
	@echo "  make kalshi-weather-proxy-feature-model-falsification — Falsify weather proxy bracket model against settled labels"
	@echo "  make kalshi-weather-proxy-research-candidate-replay — Replay weather research candidates against all-in cost gates"
	@echo "  make kalshi-weather-proxy-capacity-correlation-decay — Gate weather replay candidates on depth, clusters, and decay"
	@echo "  make kalshi-weather-proxy-correlation-cluster-control — Apply cluster exposure controls to weather candidates before overlay"
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
	@echo "  make kalshi-source-repo-inventory — Inventory donor repos and admissible artifacts"
	@echo "  make kalshi-external-artifact-wrap — Wrap donor artifacts in strict intake manifests"
	@echo "  make kalshi-external-artifact-preflight — Validate external research artifacts"
	@echo "  make kalshi-signal-formula-registry — Build safe agentic formula registry"
	@echo "  make kalshi-prior-only-donor-gate — Admit donor priors only as pre-falsification context"
	@echo "  make kalshi-paper-decision-candidates — Build paper-autonomous decision candidates"
	@echo "  make kalshi-paper-settlement-reconcile — Reconcile paper decisions to public Kalshi settlements"
	@echo "  make kalshi-signal-decay-retirement — Build signal decay/retirement ledger"
	@echo "  make kalshi-jurisdiction-refresh — Refresh jurisdiction state from config, optionally validating against external Kalshi agreement via source_url"
	@echo "  make kalshi-live-preflight — Build live-autonomous eligibility and blocker report"
	@echo "  make kalshi-live-demo — Run one demo-mode autonomous live pass when armed"
	@echo "  make kalshi-live-trader — Run one configured live-autonomous trader pass"
	@echo "  make kalshi-live-reconcile — Reconcile unresolved live Kalshi orders"
	@echo "  make kalshi-live-risk-snapshot — Write live risk/exposure snapshot"
	@echo "  make kalshi-ev-ledger — Build federated Kalshi contract EV ledger"
	@echo "  make kalshi-near-resolution-flow-terms-capture — Capture public official terms for current flow candidates"
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
KALSHI_SPORTS_CONSENSUS_JSON ?= /home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json
KALSHI_SPORTS_CONSENSUS_KALSHI_JSON ?= /home/mrwatson/manual_drops/predmarket/sports-consensus-kalshi-snapshot.json
KALSHI_SPORTS_CONSENSUS_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-preflight-latest
KALSHI_SPORTS_CONSENSUS_MIN_BOOKS ?= 2
KALSHI_SPORTS_CONSENSUS_MAX_SKEW_SECONDS ?= 180
KALSHI_SPORTS_CONSENSUS_BUILD_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-reference-build-latest
KALSHI_SPORTS_CONSENSUS_ATP_ADAPTER_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-atp-donor-adapter-latest
KALSHI_SPORTS_CONSENSUS_ATP_BOOK_JSONL ?= /home/mrwatson/projects/atp-oracle/data/sports/books/the-odds-api-atp-wimbledon-sharp-20260704T234540Z.jsonl
KALSHI_SPORTS_CONSENSUS_ATP_KALSHI_JSONL ?= /home/mrwatson/projects/atp-oracle/data/sports/kalshi/kalshi-atp-wimbledon-20260704T234559Z.jsonl
KALSHI_SPORTS_CONSENSUS_ATP_ODDS_JSON ?=
KALSHI_SPORTS_CONSENSUS_ATP_ODDS_META_JSON ?=
KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE ?= 0
KALSHI_SPORTS_CONSENSUS_NFL_ADAPTER_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-nfl-adapter-latest
KALSHI_SPORTS_CONSENSUS_NFL_KALSHI_JSON ?= /home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json
KALSHI_SPORTS_CONSENSUS_NFL_ODDS_JSON ?=
KALSHI_SPORTS_CONSENSUS_NFL_ODDS_META_JSON ?=
KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE ?= 0
KALSHI_SPORTS_CONSENSUS_SOCCER_ADAPTER_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-soccer-adapter-latest
KALSHI_SPORTS_CONSENSUS_SOCCER_KALSHI_JSON ?= /home/mrwatson/manual_drops/kalshi/kalshi_world_cup_game_series_latest.json
KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_JSON ?=
KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_META_JSON ?=
KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE ?= 0
KALSHI_SPORTS_CONSENSUS_NBA_ADAPTER_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-nba-adapter-latest
KALSHI_SPORTS_CONSENSUS_NBA_KALSHI_JSON ?= docs/codex/macro/latest-kalshi-universe-scan.json
KALSHI_SPORTS_CONSENSUS_NBA_ODDS_JSON ?=
KALSHI_SPORTS_CONSENSUS_NBA_ODDS_META_JSON ?=
KALSHI_SPORTS_CONSENSUS_NBA_CAPTURE ?= 0
KALSHI_SPORTS_CONSENSUS_KEY_FILE ?= /mnt/c/Users/mrwat/OneDrive/Desktop/Welcome to The Odds API!.txt
KALSHI_SPORTS_CONSENSUS_RAW_DIR ?= /home/mrwatson/manual_drops/odds_api
KALSHI_SPORTS_CONSENSUS_SPORT_KEYS ?= baseball_mlb
KALSHI_SPORTS_CONSENSUS_BOOKMAKERS ?= pinnacle,betfair_ex_uk,matchbook,smarkets
KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_SPORT_KEYS ?= baseball_mlb,tennis_atp_wimbledon,soccer_fifa_world_cup,americanfootball_nfl,basketball_nba
KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS ?= pinnacle,circa,bookmaker,betcris,betfair_ex_uk,matchbook,smarkets
KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_PROBE_JSON ?= /home/mrwatson/manual_drops/predmarket/sports-sharp-provider-probe-consensus.json
KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_PROBE_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-sharp-provider-capture-latest
KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDER_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-soccer-asian-provider-diagnostic-latest
KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDERS ?= sbobet,singbet,ibc
KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_CAPTURE ?= 0
KALSHI_SPORTS_CONSENSUS_REQUIRED_BOOKS ?= pinnacle,betfair_ex_uk,matchbook,smarkets
KALSHI_SPORTS_CONSENSUS_MAX_EVENT_DELTA_SECONDS ?= 900
KALSHI_SPORTS_CONSENSUS_MAX_SOURCE_AGE_SECONDS ?= 900
KALSHI_SPORTS_CONSENSUS_ODDS_RAW_JSON ?=
KALSHI_SPORTS_CONSENSUS_ODDS_META_JSON ?=
KALSHI_SPORTS_CONSENSUS_FALSIFICATION_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-falsification-latest
KALSHI_SPORTS_CONSENSUS_FALSIFICATION_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_observations
KALSHI_SPORTS_CONSENSUS_FALSIFICATION_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_labels
KALSHI_RESOLVED_ARCHIVE_BACKFILL_OUT_DIR ?= docs/codex/macro/kalshi-resolved-archive-backfill-latest
KALSHI_RESOLVED_ARCHIVE_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_resolved_archive_backfill
KALSHI_RESOLVED_ARCHIVE_MARKETS_RAW_PATH ?= /home/mrwatson/manual_drops/kalshi_resolved_archive_backfill/kalshi_resolved_archive_markets_latest.json
KALSHI_RESOLVED_ARCHIVE_CANDLESTICKS_RAW_PATH ?= /home/mrwatson/manual_drops/kalshi_resolved_archive_backfill/kalshi_resolved_archive_candlesticks_latest.json
KALSHI_RESOLVED_ARCHIVE_SERIES_TICKERS ?= KXMLBGAME,KXMLBTOTAL,KXMLBSPREAD,KXWCGAME,KXATPMATCH,KXNFLGAME,KXNBA
KALSHI_RESOLVED_ARCHIVE_LIMIT ?= 100
KALSHI_RESOLVED_ARCHIVE_MAX_PAGES ?= 1
KALSHI_RESOLVED_ARCHIVE_DAYS_BACK ?= 120
KALSHI_RESOLVED_ARCHIVE_PERIOD_INTERVAL ?= 60
KALSHI_RESOLVED_ARCHIVE_REQUEST_DELAY_SECONDS ?= 0
KALSHI_RESOLVED_ARCHIVE_CAPTURE ?= 0
KALSHI_SPORTS_HISTORICAL_CONSENSUS_OUT_DIR ?= docs/codex/macro/kalshi-sports-historical-consensus-feasibility-latest
KALSHI_SPORTS_HISTORICAL_CONSENSUS_SNAPSHOT_INTERVAL_SECONDS ?= 300
KALSHI_SPORTS_HISTORICAL_CONSENSUS_MAX_SKEW_SECONDS ?= 180
KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE ?= 0
KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_SPORT_KEY ?= baseball_mlb
KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_MARKETS ?= h2h
KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_REGIONS ?= us
KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_DATE_UTC ?= 2026-07-01T12:00:00Z
KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-provider-audit-latest
KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_TARGET_SPORTS ?= mlb,tennis,soccer,nfl,nba
KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_DEFERRED_SPORTS ?= nba
KALSHI_SPORTS_CONSENSUS_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-sports-consensus-observation-loop-latest
KALSHI_SPORTS_CONSENSUS_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_observations
KALSHI_SPORTS_CONSENSUS_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_labels
KALSHI_SPORTS_CONSENSUS_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_settlements
KALSHI_SPORTS_CONSENSUS_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_sports_consensus_settlements/kalshi_sports_consensus_observed_markets_latest.json
KALSHI_SPORTS_CONSENSUS_OBSERVED_PROBE_MAX_TICKERS ?= 100
KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED ?= 1
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
KALSHI_SOURCE_REPO_INVENTORY_OUT_DIR ?= docs/codex/macro/source-repo-inventory-latest
KALSHI_EXTERNAL_ARTIFACT_WRAP_OUT_DIR ?= docs/codex/macro/external-artifact-wrap-latest
KALSHI_EXTERNAL_ARTIFACT_WRAP_ROOT ?= /home/mrwatson/manual_drops/predmarket_external_artifacts
KALSHI_EXTERNAL_ARTIFACT_PREFLIGHT_OUT_DIR ?= docs/codex/macro/external-artifact-preflight-latest
KALSHI_SIGNAL_FORMULA_REGISTRY_OUT_DIR ?= docs/codex/macro/signal-formula-registry-latest
KALSHI_SIGNAL_FORMULA_REGISTRY_SPEC ?=
KALSHI_PRIOR_ONLY_DONOR_GATE_OUT_DIR ?= docs/codex/macro/prior-only-donor-gate-latest
KALSHI_PRIOR_ONLY_DONOR_GATE_EXTERNAL_PREFLIGHT ?= docs/codex/macro/latest-external-artifact-preflight.json
KALSHI_PRIOR_ONLY_DONOR_GATE_FORMULA_REGISTRY ?= docs/codex/macro/latest-signal-formula-registry.json
KALSHI_PAPER_DECISION_OUT_DIR ?= docs/codex/macro/paper-decision-candidates-latest
KALSHI_PAPER_DECISION_LEDGER ?= docs/codex/macro/latest-kalshi-contract-ev-ledger.json
KALSHI_PAPER_DECISION_RETIREMENT ?= docs/codex/macro/latest-signal-decay-retirement-ledger.json
KALSHI_PAPER_DECISION_BANKROLL ?= 10000
KALSHI_PAPER_DECISION_KELLY_FRACTION ?= 0.25
KALSHI_PAPER_DECISION_MAX_FRACTION ?= 0.02
KALSHI_PAPER_DECISION_MAX_CLUSTER_SHARE ?= 0.35
KALSHI_PAPER_DECISION_GHOST_DEPTH ?= docs/codex/macro/latest-kalshi-ghost-listing-depth-diagnostic.json
KALSHI_PAPER_SETTLEMENT_OUT_DIR ?= docs/codex/macro/paper-settlement-reconciliation-latest
KALSHI_PAPER_SETTLEMENT_PAPER_DECISIONS ?= docs/codex/macro/latest-paper-decision-candidates.json
KALSHI_PAPER_SETTLEMENT_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_paper_settlements/kalshi_paper_observed_markets_latest.json
KALSHI_PAPER_SETTLEMENT_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_paper_settlements
KALSHI_PAPER_SETTLEMENT_FETCH ?= 0
KALSHI_PAPER_SETTLEMENT_MAX_FETCH_TICKERS ?= 100
KALSHI_SPORTS_PAPER_BURN_IN_OUT_DIR ?= docs/codex/macro/kalshi-sports-paper-burn-in-cycle-latest
KALSHI_SPORTS_PAPER_BURN_IN_FETCH ?= 0
KALSHI_SPORTS_PAPER_BURN_IN_MAX_FETCH_TICKERS ?= 100
KALSHI_ALWAYS_ON_COLLECTOR_OUT_DIR ?= docs/codex/macro/kalshi-always-on-collector-latest
KALSHI_ALWAYS_ON_COLLECTOR_TARGETS ?= sports,crypto
KALSHI_ALWAYS_ON_COLLECTOR_BASE_INTERVAL_SECONDS ?= 300
KALSHI_ALWAYS_ON_COLLECTOR_NEAR_INTERVAL_SECONDS ?= 60
KALSHI_ALWAYS_ON_COLLECTOR_DUE_INTERVAL_SECONDS ?= 60
KALSHI_ALWAYS_ON_COLLECTOR_NEAR_CLOSE_WINDOW_SECONDS ?= 1800
KALSHI_ALWAYS_ON_COLLECTOR_MAX_CYCLES ?= 0
KALSHI_SIGNAL_DECAY_RETIREMENT_OUT_DIR ?= docs/codex/macro/signal-decay-retirement-ledger-latest
KALSHI_SIGNAL_DECAY_RETIREMENT_PAPER_DECISIONS ?= docs/codex/macro/latest-paper-decision-candidates.json
KALSHI_SIGNAL_DECAY_RETIREMENT_MIN_RECENT ?= 3
KALSHI_SIGNAL_DECAY_RETIREMENT_MIN_ACCURACY ?= 0.50
KALSHI_SIGNAL_DECAY_RETIREMENT_MAX_CAL_ERROR ?= 0.20
KALSHI_LIVE_STATE_DIR ?= data/kalshi_live
KALSHI_LIVE_MARKET_SNAPSHOTS ?=
KALSHI_LIVE_CAPTURE_MARKET_SNAPSHOTS ?= 1
KALSHI_LIVE_MARKET_SNAPSHOT_DEPTH ?= 10
KALSHI_LIVE_PREFLIGHT_OUT_DIR ?= docs/codex/macro/kalshi-live-preflight-latest
KALSHI_LIVE_TRADER_OUT_DIR ?= docs/codex/macro/kalshi-live-trader-latest
KALSHI_LIVE_RECONCILE_OUT_DIR ?= docs/codex/macro/kalshi-live-reconcile-latest
KALSHI_LIVE_RISK_SNAPSHOT_OUT_DIR ?= docs/codex/macro/kalshi-live-risk-snapshot-latest
KALSHI_LIVE_EXECUTION_MODE ?= disabled
KALSHI_LIVE_PAPER_DECISIONS ?= docs/codex/macro/latest-paper-decision-candidates.json
KALSHI_LIVE_EXTERNAL_PREFLIGHT ?= docs/codex/macro/latest-external-artifact-preflight.json
KALSHI_LIVE_RETIREMENT ?= docs/codex/macro/latest-signal-decay-retirement-ledger.json
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
KALSHI_UNIVERSE_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS ?= 720
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
KALSHI_SPORTS_PROXY_FEATURE_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-feature-packet-latest
KALSHI_SPORTS_PROXY_FEATURE_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_proxy_features
KALSHI_SPORTS_PROXY_FEATURE_RAW_UNIVERSE ?= /home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json
KALSHI_SPORTS_PROXY_FEATURE_MLB_PLATFORM_MODEL ?= /home/mrwatson/manual_drops/mlb_platform_signal_features/mlb_platform_sports_model_latest.json
KALSHI_SPORTS_PROXY_FEATURE_MAX_CLOSE_HOURS ?= 6
KALSHI_SPORTS_PROXY_FEATURE_MAX_CONTRACTS ?= 1500
KALSHI_SPORTS_PROXY_FEATURE_CAPTURE ?= 1
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
KALSHI_SPORTS_PROXY_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-observation-loop-latest
KALSHI_SPORTS_PROXY_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_proxy_observations
KALSHI_SPORTS_PROXY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_proxy_labels
KALSHI_SPORTS_PROXY_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_sports_settlements/kalshi_settled_markets_latest.json
KALSHI_SPORTS_PROXY_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_settlements
KALSHI_SPORTS_PROXY_SETTLED_LIMIT ?= 1000
KALSHI_SPORTS_PROXY_SETTLED_MAX_PAGES ?= 1
KALSHI_SPORTS_PROXY_OBSERVATION_CAPTURE_SETTLED ?= 1
KALSHI_SPORTS_PROXY_OBSERVATION_PROBE_OBSERVED ?= 1
KALSHI_SPORTS_PROXY_OBSERVATION_PROBE_MAX_TICKERS ?= 300
KALSHI_ATP_PROXY_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-atp-proxy-observation-loop-latest
KALSHI_ATP_PROXY_MATCH_SNAPSHOT ?= $(lastword $(sort $(wildcard /home/mrwatson/projects/atp-oracle/data/kalshi/matches-*.json)))
KALSHI_ATP_PROXY_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_atp_proxy_observations
KALSHI_ATP_PROXY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_atp_proxy_labels
KALSHI_ATP_PROXY_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_atp_settlements/kalshi_atp_settled_markets_latest.json
KALSHI_ATP_PROXY_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_atp_settlements
KALSHI_ATP_PROXY_SETTLED_LIMIT ?= 1000
KALSHI_ATP_PROXY_SETTLED_MAX_PAGES ?= 1
KALSHI_ATP_PROXY_OBSERVATION_CAPTURE_SETTLED ?= 1
KALSHI_ATP_PROXY_OBSERVATION_PROBE_OBSERVED ?= 1
KALSHI_ATP_PROXY_OBSERVATION_PROBE_MAX_TICKERS ?= 300
KALSHI_ATP_PROXY_EVIDENCE_OUT_DIR ?= docs/codex/macro/kalshi-atp-proxy-evidence-gate-latest
KALSHI_ATP_PROXY_FORWARD_OOS ?= /home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-latest/report.json
KALSHI_ATP_PROXY_LIQUIDITY ?= /home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-liquidity-latest/liquidity.json
KALSHI_ATP_PROXY_BETTABLE_GATE ?= /home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-bettable-line-gate-latest/bettable-line-gate.json
KALSHI_ATP_PROXY_PRICE_OBSERVATIONS ?= /home/mrwatson/projects/atp-oracle/docs/codex/artifacts/kalshi-forward-oos-price-observations-latest/prices.json
KALSHI_ATP_PROXY_MIN_SETTLED_LABELS ?= 10
KALSHI_WORLD_CUP_PROXY_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-world-cup-proxy-observation-loop-latest
KALSHI_WORLD_CUP_PROXY_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_world_cup_proxy_observations
KALSHI_WORLD_CUP_PROXY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_world_cup_proxy_labels
KALSHI_WORLD_CUP_PROXY_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_world_cup_settlements/kalshi_observed_markets_latest.json
KALSHI_WORLD_CUP_PROXY_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_world_cup_settlements
KALSHI_WORLD_CUP_PROXY_UNIVERSE_SCAN ?= docs/codex/macro/latest-kalshi-universe-scan.json
KALSHI_WORLD_CUP_PROXY_MAX_CONTRACTS ?= 300
KALSHI_WORLD_CUP_PROXY_OBSERVATION_PROBE_OBSERVED ?= 1
KALSHI_WORLD_CUP_PROXY_OBSERVATION_PROBE_MAX_TICKERS ?= 300
KALSHI_WORLD_CUP_PROXY_MODEL_OUT_DIR ?= docs/codex/macro/kalshi-world-cup-proxy-feature-model-falsification-latest
KALSHI_WORLD_CUP_PROXY_MODEL_MIN_INDEPENDENT_LABELS ?= 30
KALSHI_WORLD_CUP_PROXY_MODEL_MIN_OOS_LABELS ?= 10
KALSHI_WORLD_CUP_PROXY_MODEL_TEST_FRACTION ?= 0.30
KALSHI_WORLD_CUP_PROXY_MODEL_FDR_ALPHA ?= 0.10
KALSHI_WORLD_CUP_OUTCOME_INDEPENDENCE_OUT_DIR ?= docs/codex/macro/kalshi-world-cup-outcome-independence-diagnostic-latest
KALSHI_SPORTS_LABEL_ACCUMULATION_OUT_DIR ?= docs/codex/macro/kalshi-sports-label-accumulation-cycle-latest
KALSHI_GHOST_LISTING_DEPTH_OUT_DIR ?= docs/codex/macro/kalshi-ghost-listing-depth-diagnostic-latest
KALSHI_GHOST_LISTING_DEPTH_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_ghost_listing_depth
KALSHI_GHOST_LISTING_DEPTH_MAX_CONTRACTS ?= 120
KALSHI_GHOST_LISTING_DEPTH_DEPTH ?= 0
KALSHI_GHOST_LISTING_DEPTH_DELAY_SECONDS ?= 0.03
KALSHI_GHOST_LISTING_DEPTH_CAPTURE ?= 1
KALSHI_GHOST_LISTING_DEPTH_MIN_PROBE_COVERAGE ?= 0.80
KALSHI_GHOST_LISTING_DEPTH_MIN_POSITIVE_FRACTION ?= 0.18
KALSHI_GHOST_LISTING_CLASSIFICATIONS ?= other_sports,mlb,atp,nfl,nba,weather,finance_crypto,macro_econ,politics_policy
KALSHI_SPORTS_STACK_SEQUENCING_OUT_DIR ?= docs/codex/macro/kalshi-sports-stack-sequencing-latest
KALSHI_SPORTS_STACK_MLB_REPLAY_PATH ?= docs/codex/macro/latest-kalshi-sports-proxy-research-candidate-replay.json
KALSHI_SPORTS_STACK_MLB_CCD_PATH ?= docs/codex/macro/latest-kalshi-sports-proxy-capacity-correlation-decay.json
KALSHI_SPORTS_STACK_MLB_CLUSTER_PATH ?= docs/codex/macro/latest-kalshi-sports-proxy-correlation-cluster-control.json
KALSHI_SPORTS_MICROSTRUCTURE_OUT_DIR ?= docs/codex/macro/kalshi-sports-microstructure-observation-loop-latest
KALSHI_SPORTS_MICROSTRUCTURE_RAW_ORDERBOOK_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_microstructure_orderbooks
KALSHI_SPORTS_MICROSTRUCTURE_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_microstructure_observations
KALSHI_SPORTS_MICROSTRUCTURE_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_sports_microstructure_settlements/kalshi_sports_microstructure_observed_markets_latest.json
KALSHI_SPORTS_MICROSTRUCTURE_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_microstructure_settlements
KALSHI_SPORTS_MICROSTRUCTURE_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_microstructure_labels
KALSHI_SPORTS_LINE_MOVE_OUT_DIR ?= docs/codex/macro/kalshi-sports-line-move-delta-logger-latest
KALSHI_SPORTS_LINE_MOVE_STATE_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_line_moves
KALSHI_SPORTS_LINE_MOVE_SPORT_KEYS ?= baseball_mlb,tennis_atp_wimbledon,soccer_fifa_world_cup,americanfootball_nfl
KALSHI_SPORTS_LINE_MOVE_BOOKMAKERS ?= pinnacle,betfair_ex_uk,matchbook,smarkets
KALSHI_SPORTS_LINE_MOVE_REGIONS ?= us
KALSHI_SPORTS_LINE_MOVE_MARKETS ?= h2h
KALSHI_SPORTS_LINE_MOVE_INTERVAL_SECONDS ?= 60
KALSHI_SPORTS_LINE_MOVE_MAX_CYCLES ?= 1
KALSHI_SPORTS_LINE_MOVE_TIMEOUT_SECONDS ?= 20
KALSHI_TICK_RECORDER_OUT_DIR ?= docs/codex/macro/kalshi-tick-recorder-latest
KALSHI_TICK_RECORDER_JSONL_DIR ?= /home/mrwatson/manual_drops/kalshi_ticks
KALSHI_TICK_RECORDER_UNIVERSE_PATH ?= docs/codex/macro/latest-kalshi-universe-scan.json
KALSHI_TICK_RECORDER_TICKERS ?=
KALSHI_TICK_RECORDER_CHANNELS ?= ticker,orderbook_delta
KALSHI_TICK_RECORDER_MAX_TICKERS ?= 250
KALSHI_TICK_RECORDER_DURATION_SECONDS ?= 30
KALSHI_TICK_RECORDER_MAX_GAP_SECONDS ?= 30
KALSHI_TICK_RECORDER_EXECUTION_MODE ?= live
KALSHI_SPORTS_MICROSTRUCTURE_MAX_TICKERS ?= 120
KALSHI_SPORTS_MICROSTRUCTURE_MAX_CLOSE_HOURS ?= 48
KALSHI_SPORTS_MICROSTRUCTURE_DEPTH ?= 0
KALSHI_SPORTS_MICROSTRUCTURE_DELAY_SECONDS ?= 0.03
KALSHI_SPORTS_MICROSTRUCTURE_CAPTURE ?= 1
KALSHI_SPORTS_MICROSTRUCTURE_PROBE_OBSERVED ?= 1
KALSHI_SPORTS_MICROSTRUCTURE_PROBE_MAX_TICKERS ?= 300
KALSHI_NEAR_RESOLUTION_FLOW_OUT_DIR ?= docs/codex/macro/kalshi-near-resolution-informed-flow-evidence-gate-latest
KALSHI_NEAR_RESOLUTION_FLOW_MICROSTRUCTURE_PATH ?= docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_OUT_DIR ?= docs/codex/macro/kalshi-near-resolution-flow-replay-gates-latest
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CLOSE_HOURS ?= 6
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CURRENT_CANDIDATES ?= 60
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_OBSERVATION_AGE_SECONDS ?= 900
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CLUSTER_SHARE ?= 0.35
KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MIN_POSITIVE_CAPACITY_CONTRACTS ?= 1
KALSHI_NEAR_RESOLUTION_FLOW_TERMS_OUT_DIR ?= docs/codex/macro/kalshi-near-resolution-flow-terms-capture-latest
KALSHI_NEAR_RESOLUTION_FLOW_TERMS_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi
KALSHI_NEAR_RESOLUTION_FLOW_TERMS_MAX_MARKETS ?= 120
KALSHI_NEAR_RESOLUTION_FLOW_TERMS_CAPTURE ?= 1
KALSHI_NEAR_RESOLUTION_FLOW_TERMS_DELAY_SECONDS ?= 0.03
KALSHI_PASSIVE_LIQUIDITY_OUT_DIR ?= docs/codex/macro/kalshi-passive-liquidity-provision-evidence-gate-latest
KALSHI_PASSIVE_LIQUIDITY_TTL_SECONDS ?= 43200
KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_OUT_DIR ?= docs/codex/macro/kalshi-passive-liquidity-paper-fill-loop-latest
KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_STATE_DIR ?= /home/mrwatson/manual_drops/kalshi_passive_liquidity_paper_fills
KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_FALSIFICATION_OUT_DIR ?= docs/codex/macro/kalshi-passive-liquidity-paper-fill-falsification-latest
KALSHI_PASSIVE_LIQUIDITY_FILL_CLOCK_DIAGNOSTIC_OUT_DIR ?= docs/codex/macro/kalshi-passive-liquidity-fill-clock-diagnostic-latest
KALSHI_SPORTS_EVENT_VELOCITY_ETA_OUT_DIR ?= docs/codex/macro/kalshi-sports-event-velocity-eta-latest
KALSHI_CLAUDE_ADVICE_AUDIT_OUT_DIR ?= docs/codex/macro/kalshi-claude-advice-audit-latest
KALSHI_SPORTS_BLOCKER_CLEARANCE_OUT_DIR ?= docs/codex/macro/kalshi-sports-blocker-clearance-cycle-latest
KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE ?= 0
KALSHI_SPORTS_BLOCKER_CLEARANCE_ATP_REPO ?= /home/mrwatson/projects/atp-oracle
KALSHI_SPORTS_BLOCKER_CLEARANCE_COMMAND_TIMEOUT_SECONDS ?= 900
KALSHI_SPORTS_EVIDENCE_CYCLE_OUT_DIR ?= docs/codex/macro/kalshi-sports-evidence-cycle-latest
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
KALSHI_SPORTS_PROXY_MODEL_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-feature-model-falsification-latest
KALSHI_SPORTS_PROXY_REPLAY_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-research-candidate-replay-latest
KALSHI_SPORTS_PROXY_REPLAY_MODEL_PATH ?= docs/codex/macro/latest-kalshi-sports-proxy-feature-model-falsification.json
KALSHI_SPORTS_PROXY_REPLAY_PREFERRED_MODEL_ID ?=
KALSHI_SPORTS_PROXY_CCD_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-capacity-correlation-decay-latest
KALSHI_SPORTS_PROXY_CCD_FEATURE_PACKET ?= docs/codex/macro/latest-kalshi-sports-proxy-feature-packet.json
KALSHI_SPORTS_PROXY_CCD_REPLAY ?= docs/codex/macro/latest-kalshi-sports-proxy-research-candidate-replay.json
KALSHI_SPORTS_PROXY_CCD_RAW_ORDERBOOK_DIR ?= /home/mrwatson/manual_drops/kalshi_sports_proxy_orderbooks
KALSHI_SPORTS_PROXY_CCD_MAX_CLOSE_HOURS ?= 6
KALSHI_SPORTS_PROXY_CCD_MAX_TICKERS ?= 60
KALSHI_SPORTS_PROXY_CCD_DEPTH ?= 0
KALSHI_SPORTS_PROXY_CCD_DELAY_SECONDS ?= 0.05
KALSHI_SPORTS_PROXY_CCD_CAPTURE_ORDERBOOKS ?= 1
KALSHI_SPORTS_PROXY_CLUSTER_OUT_DIR ?= docs/codex/macro/kalshi-sports-proxy-correlation-cluster-control-latest
KALSHI_SPORTS_PROXY_CLUSTER_CCD ?= docs/codex/macro/latest-kalshi-sports-proxy-capacity-correlation-decay.json
KALSHI_SPORTS_PROXY_CLUSTER_MAX_SHARE ?= 0.35
KALSHI_SPORTS_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS ?= 0
# Weather proxy variables
KALSHI_WEATHER_PROXY_FEATURE_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-feature-packet-latest
KALSHI_WEATHER_PROXY_FEATURE_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_features
KALSHI_WEATHER_PROXY_FEATURE_RAW_UNIVERSE ?= /home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json
KALSHI_WEATHER_PROXY_FEATURE_MAX_CLOSE_HOURS ?= 48
KALSHI_WEATHER_PROXY_FEATURE_MAX_CONTRACTS ?= 1500
KALSHI_WEATHER_PROXY_FEATURE_CAPTURE ?= 0
KALSHI_WEATHER_PROXY_OBSERVATION_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-observation-loop-latest
KALSHI_WEATHER_PROXY_OBSERVATION_DIR ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_observations
KALSHI_WEATHER_PROXY_LABEL_DIR ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_labels
KALSHI_WEATHER_PROXY_SETTLED_SNAPSHOT ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_settlements/kalshi_weather_settled_markets_latest.json
KALSHI_WEATHER_PROXY_SETTLED_RAW_DIR ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_settlements
KALSHI_WEATHER_PROXY_SETTLED_LIMIT ?= 1000
KALSHI_WEATHER_PROXY_SETTLED_MAX_PAGES ?= 1
KALSHI_WEATHER_PROXY_OBSERVATION_CAPTURE_SETTLED ?= 1
KALSHI_WEATHER_PROXY_OBSERVATION_PROBE_MAX_TICKERS ?= 300
KALSHI_WEATHER_PROXY_MODEL_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-feature-model-falsification-latest
KALSHI_WEATHER_PROXY_MODEL_MIN_INDEPENDENT_LABELS ?= 30
KALSHI_WEATHER_PROXY_MODEL_MIN_OOS_LABELS ?= 10
KALSHI_WEATHER_PROXY_MODEL_TEST_FRACTION ?= 0.30
KALSHI_WEATHER_PROXY_MODEL_FDR_ALPHA ?= 0.10
KALSHI_WEATHER_PROXY_REPLAY_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-research-candidate-replay-latest
KALSHI_WEATHER_PROXY_REPLAY_MODEL_PATH ?= docs/codex/macro/latest-kalshi-weather-proxy-feature-model-falsification.json
KALSHI_WEATHER_PROXY_CCD_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-capacity-correlation-decay-latest
KALSHI_WEATHER_PROXY_CCD_FEATURE_PACKET ?= docs/codex/macro/latest-kalshi-weather-proxy-feature-packet.json
KALSHI_WEATHER_PROXY_CCD_REPLAY ?= docs/codex/macro/latest-kalshi-weather-proxy-research-candidate-replay.json
KALSHI_WEATHER_PROXY_CCD_RAW_ORDERBOOK_DIR ?= /home/mrwatson/manual_drops/kalshi_weather_proxy_orderbooks
KALSHI_WEATHER_PROXY_CCD_MAX_CLOSE_HOURS ?= 48
KALSHI_WEATHER_PROXY_CCD_MAX_TICKERS ?= 60
KALSHI_WEATHER_PROXY_CCD_DEPTH ?= 0
KALSHI_WEATHER_PROXY_CCD_DELAY_SECONDS ?= 0.05
KALSHI_WEATHER_PROXY_CCD_CAPTURE_ORDERBOOKS ?= 0
KALSHI_WEATHER_PROXY_CLUSTER_OUT_DIR ?= docs/codex/macro/kalshi-weather-proxy-correlation-cluster-control-latest
KALSHI_WEATHER_PROXY_CLUSTER_CCD ?= docs/codex/macro/latest-kalshi-weather-proxy-capacity-correlation-decay.json
KALSHI_WEATHER_PROXY_CLUSTER_MAX_SHARE ?= 0.35
KALSHI_WEATHER_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS ?= 0
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
		--focused-sports-fetch-max-close-hours $(KALSHI_UNIVERSE_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS) \
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

kalshi-sports-proxy-feature-packet:
	@python3 scripts/kalshi_sports_proxy_feature_packet.py \
		--write \
		--max-close-hours $(KALSHI_SPORTS_PROXY_FEATURE_MAX_CLOSE_HOURS) \
		--max-contracts $(KALSHI_SPORTS_PROXY_FEATURE_MAX_CONTRACTS) \
		--raw-universe-path $(KALSHI_SPORTS_PROXY_FEATURE_RAW_UNIVERSE) \
		--raw-proxy-dir $(KALSHI_SPORTS_PROXY_FEATURE_RAW_DIR) \
		--mlb-platform-model-path $(KALSHI_SPORTS_PROXY_FEATURE_MLB_PLATFORM_MODEL) \
		--out-dir $(KALSHI_SPORTS_PROXY_FEATURE_OUT_DIR) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_PROXY_FEATURE_CAPTURE)),--capture-public-features,)

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

kalshi-sports-proxy-observation-loop:
	@python3 scripts/kalshi_sports_proxy_observation_loop.py \
		--write \
		--out-dir $(KALSHI_SPORTS_PROXY_OBSERVATION_OUT_DIR) \
		--observation-dir $(KALSHI_SPORTS_PROXY_OBSERVATION_DIR) \
		--label-dir $(KALSHI_SPORTS_PROXY_LABEL_DIR) \
		--settled-snapshot-path $(KALSHI_SPORTS_PROXY_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_SPORTS_PROXY_SETTLED_RAW_DIR) \
		--settled-limit $(KALSHI_SPORTS_PROXY_SETTLED_LIMIT) \
		--settled-max-pages $(KALSHI_SPORTS_PROXY_SETTLED_MAX_PAGES) \
		--observed-probe-max-tickers $(KALSHI_SPORTS_PROXY_OBSERVATION_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_PROXY_OBSERVATION_PROBE_OBSERVED)),--probe-observed-public,) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_PROXY_OBSERVATION_CAPTURE_SETTLED)),--capture-settled-public,)

kalshi-sports-proxy-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-sports-proxy-feature-packet
	@$(MAKE) --no-print-directory kalshi-sports-proxy-observation-loop
	@$(MAKE) --no-print-directory kalshi-sports-proxy-feature-model-falsification
	@$(MAKE) --no-print-directory kalshi-sports-proxy-research-candidate-replay
	@$(MAKE) --no-print-directory kalshi-sports-proxy-capacity-correlation-decay
	@$(MAKE) --no-print-directory kalshi-sports-proxy-correlation-cluster-control
	@$(MAKE) --no-print-directory kalshi-signal-factory-status
	@$(MAKE) --no-print-directory macro-route

kalshi-atp-proxy-observation-loop:
	@python3 scripts/kalshi_atp_proxy_observation_loop.py \
		--write \
		--out-dir $(KALSHI_ATP_PROXY_OBSERVATION_OUT_DIR) \
		--atp-match-snapshot-path $(KALSHI_ATP_PROXY_MATCH_SNAPSHOT) \
		--observation-dir $(KALSHI_ATP_PROXY_OBSERVATION_DIR) \
		--label-dir $(KALSHI_ATP_PROXY_LABEL_DIR) \
		--settled-snapshot-path $(KALSHI_ATP_PROXY_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_ATP_PROXY_SETTLED_RAW_DIR) \
		--settled-limit $(KALSHI_ATP_PROXY_SETTLED_LIMIT) \
		--settled-max-pages $(KALSHI_ATP_PROXY_SETTLED_MAX_PAGES) \
		--observed-probe-max-tickers $(KALSHI_ATP_PROXY_OBSERVATION_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_ATP_PROXY_OBSERVATION_PROBE_OBSERVED)),--probe-observed-public,) \
		$(if $(filter 1 true yes,$(KALSHI_ATP_PROXY_OBSERVATION_CAPTURE_SETTLED)),--capture-settled-public,)

kalshi-atp-proxy-evidence-gate:
	@python3 scripts/kalshi_atp_proxy_evidence_gate.py \
		--write \
		--out-dir $(KALSHI_ATP_PROXY_EVIDENCE_OUT_DIR) \
		--observation-loop-path docs/codex/macro/latest-kalshi-atp-proxy-observation-loop.json \
		--forward-oos-path $(KALSHI_ATP_PROXY_FORWARD_OOS) \
		--liquidity-path $(KALSHI_ATP_PROXY_LIQUIDITY) \
		--bettable-gate-path $(KALSHI_ATP_PROXY_BETTABLE_GATE) \
		--price-observations-path $(KALSHI_ATP_PROXY_PRICE_OBSERVATIONS) \
		--min-settled-labels $(KALSHI_ATP_PROXY_MIN_SETTLED_LABELS)

kalshi-atp-proxy-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-atp-proxy-observation-loop
	@$(MAKE) --no-print-directory kalshi-atp-proxy-evidence-gate
	@$(MAKE) --no-print-directory kalshi-signal-factory-status
	@$(MAKE) --no-print-directory macro-route

kalshi-world-cup-proxy-observation-loop:
	@python3 scripts/kalshi_world_cup_proxy_observation_loop.py \
		--write \
		--universe-scan-path $(KALSHI_WORLD_CUP_PROXY_UNIVERSE_SCAN) \
		--out-dir $(KALSHI_WORLD_CUP_PROXY_OBSERVATION_OUT_DIR) \
		--observation-dir $(KALSHI_WORLD_CUP_PROXY_OBSERVATION_DIR) \
		--label-dir $(KALSHI_WORLD_CUP_PROXY_LABEL_DIR) \
		--settled-snapshot-path $(KALSHI_WORLD_CUP_PROXY_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_WORLD_CUP_PROXY_SETTLED_RAW_DIR) \
		--max-contracts $(KALSHI_WORLD_CUP_PROXY_MAX_CONTRACTS) \
		--observed-probe-max-tickers $(KALSHI_WORLD_CUP_PROXY_OBSERVATION_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_WORLD_CUP_PROXY_OBSERVATION_PROBE_OBSERVED)),--probe-observed-public,)

kalshi-world-cup-proxy-feature-model-falsification:
	@python3 scripts/kalshi_world_cup_proxy_feature_model_falsification.py \
		--write \
		--label-dir $(KALSHI_WORLD_CUP_PROXY_LABEL_DIR) \
		--out-dir $(KALSHI_WORLD_CUP_PROXY_MODEL_OUT_DIR) \
		--min-independent-labels $(KALSHI_WORLD_CUP_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_WORLD_CUP_PROXY_MODEL_MIN_OOS_LABELS) \
		--test-fraction $(KALSHI_WORLD_CUP_PROXY_MODEL_TEST_FRACTION) \
		--fdr-alpha $(KALSHI_WORLD_CUP_PROXY_MODEL_FDR_ALPHA)

kalshi-world-cup-outcome-independence-diagnostic:
	@python3 scripts/kalshi_world_cup_outcome_independence_diagnostic.py \
		--write \
		--label-dir $(KALSHI_WORLD_CUP_PROXY_LABEL_DIR) \
		--world-cup-model-path docs/codex/macro/latest-kalshi-world-cup-proxy-feature-model-falsification.json \
		--out-dir $(KALSHI_WORLD_CUP_OUTCOME_INDEPENDENCE_OUT_DIR) \
		--min-independent-labels $(KALSHI_WORLD_CUP_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_WORLD_CUP_PROXY_MODEL_MIN_OOS_LABELS)

kalshi-world-cup-proxy-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-universe-scan
	@$(MAKE) --no-print-directory kalshi-world-cup-proxy-observation-loop
	@$(MAKE) --no-print-directory kalshi-world-cup-proxy-feature-model-falsification
	@$(MAKE) --no-print-directory kalshi-world-cup-outcome-independence-diagnostic
	@$(MAKE) --no-print-directory kalshi-ghost-listing-depth-diagnostic
	@$(MAKE) --no-print-directory kalshi-sports-stack-sequencing
	@$(MAKE) --no-print-directory kalshi-signal-factory-status
	@$(MAKE) --no-print-directory macro-route

kalshi-ghost-listing-depth-diagnostic:
	@python3 scripts/kalshi_ghost_listing_depth_diagnostic.py \
		--write \
		--universe-scan-path docs/codex/macro/latest-kalshi-universe-scan.json \
		--raw-orderbook-dir $(KALSHI_GHOST_LISTING_DEPTH_RAW_DIR) \
		--out-dir $(KALSHI_GHOST_LISTING_DEPTH_OUT_DIR) \
		--max-contracts $(KALSHI_GHOST_LISTING_DEPTH_MAX_CONTRACTS) \
		--depth $(KALSHI_GHOST_LISTING_DEPTH_DEPTH) \
		--delay-seconds $(KALSHI_GHOST_LISTING_DEPTH_DELAY_SECONDS) \
		--classifications $(KALSHI_GHOST_LISTING_CLASSIFICATIONS) \
		--min-probe-coverage $(KALSHI_GHOST_LISTING_DEPTH_MIN_PROBE_COVERAGE) \
		--min-positive-depth-fraction $(KALSHI_GHOST_LISTING_DEPTH_MIN_POSITIVE_FRACTION) \
		$(if $(filter 1 true yes,$(KALSHI_GHOST_LISTING_DEPTH_CAPTURE)),--capture-orderbooks,)

kalshi-sports-stack-sequencing:
	@python3 scripts/kalshi_sports_stack_sequencing.py \
		--write \
		--out-dir $(KALSHI_SPORTS_STACK_SEQUENCING_OUT_DIR) \
		--universe-scan-path docs/codex/macro/latest-kalshi-universe-scan.json \
		--world-cup-observation-path docs/codex/macro/latest-kalshi-world-cup-proxy-observation-loop.json \
		--world-cup-model-path docs/codex/macro/latest-kalshi-world-cup-proxy-feature-model-falsification.json \
		--mlb-observation-path docs/codex/macro/latest-kalshi-sports-proxy-observation-loop.json \
		--mlb-model-path docs/codex/macro/latest-kalshi-sports-proxy-feature-model-falsification.json \
		--mlb-replay-path $(KALSHI_SPORTS_STACK_MLB_REPLAY_PATH) \
		--mlb-ccd-path $(KALSHI_SPORTS_STACK_MLB_CCD_PATH) \
		--mlb-cluster-path $(KALSHI_SPORTS_STACK_MLB_CLUSTER_PATH) \
		--atp-observation-path docs/codex/macro/latest-kalshi-atp-proxy-observation-loop.json \
		--atp-evidence-path docs/codex/macro/latest-kalshi-atp-proxy-evidence-gate.json \
		--ghost-depth-path docs/codex/macro/latest-kalshi-ghost-listing-depth-diagnostic.json

kalshi-sports-consensus-reference-build:
	@args="--kalshi-json docs/codex/macro/latest-kalshi-universe-scan.json --reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) --report-dir $(KALSHI_SPORTS_CONSENSUS_BUILD_OUT_DIR) --required-books $(KALSHI_SPORTS_CONSENSUS_REQUIRED_BOOKS) --max-event-delta-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_EVENT_DELTA_SECONDS) --max-source-age-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_SOURCE_AGE_SECONDS)"; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_ODDS_RAW_JSON)" ]; then args="$$args --odds-raw-json $(KALSHI_SPORTS_CONSENSUS_ODDS_RAW_JSON)"; fi; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_ODDS_META_JSON)" ]; then args="$$args --odds-meta-json $(KALSHI_SPORTS_CONSENSUS_ODDS_META_JSON)"; fi; \
	python3 scripts/kalshi_sports_consensus_reference_build.py $$args

kalshi-sports-consensus-sharp-provider-capture:
	@python3 scripts/kalshi_sports_consensus_reference_build.py \
		--capture-current \
		--kalshi-json docs/codex/macro/latest-kalshi-universe-scan.json \
		--reference-json $(KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_PROBE_JSON) \
		--report-dir $(KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_PROBE_OUT_DIR) \
		--api-key-file "$(KALSHI_SPORTS_CONSENSUS_KEY_FILE)" \
		--sport-keys $(KALSHI_SPORTS_CONSENSUS_SHARP_PROVIDER_SPORT_KEYS) \
		--bookmakers $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) \
		--raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR) \
		--required-books $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) \
		--max-event-delta-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_EVENT_DELTA_SECONDS) \
		--max-source-age-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_SOURCE_AGE_SECONDS)

kalshi-sports-consensus-soccer-asian-provider-diagnostic:
	@if [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_CAPTURE)" = "1" ] || [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_CAPTURE)" = "true" ] || [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_CAPTURE)" = "yes" ]; then \
		python3 scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py \
			--out-dir $(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDER_OUT_DIR) \
			--target-providers $(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDERS) \
			--max-raw-files 20 \
			--capture-current \
			--api-key-file "$(KALSHI_SPORTS_CONSENSUS_KEY_FILE)" \
			--raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR); \
	else \
		python3 scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py \
			--out-dir $(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDER_OUT_DIR) \
			--target-providers $(KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDERS) \
			--max-raw-files 20; \
	fi

kalshi-sports-consensus-public-kalshi-refresh:
	@$(MAKE) --no-print-directory kalshi-manual-drop-capture \
		KALSHI_MANUAL_DROP_SERIES=KXNFLGAME \
		KALSHI_MANUAL_DROP_LATEST=$(KALSHI_SPORTS_CONSENSUS_NFL_KALSHI_JSON) \
		KALSHI_MANUAL_DROP_RUN_ID=kalshi-nfl-manual-drop-capture-latest \
		KALSHI_MANUAL_DROP_LIMIT=100 \
		KALSHI_MANUAL_DROP_MAX_PAGES=1 \
		KALSHI_MANUAL_DROP_DELAY_SECONDS=0
	@$(MAKE) --no-print-directory kalshi-manual-drop-capture \
		KALSHI_MANUAL_DROP_SERIES=KXWCGAME \
		KALSHI_MANUAL_DROP_LATEST=$(KALSHI_SPORTS_CONSENSUS_SOCCER_KALSHI_JSON) \
		KALSHI_MANUAL_DROP_RUN_ID=kalshi-world-cup-game-capture-latest \
		KALSHI_MANUAL_DROP_LIMIT=100 \
		KALSHI_MANUAL_DROP_MAX_PAGES=1 \
		KALSHI_MANUAL_DROP_DELAY_SECONDS=0

kalshi-sports-consensus-atp-donor-adapter:
	@args="--write --reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) --combined-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --base-kalshi-json docs/codex/macro/latest-kalshi-universe-scan.json --atp-book-jsonl $(KALSHI_SPORTS_CONSENSUS_ATP_BOOK_JSONL) --atp-kalshi-jsonl $(KALSHI_SPORTS_CONSENSUS_ATP_KALSHI_JSONL) --out-dir $(KALSHI_SPORTS_CONSENSUS_ATP_ADAPTER_OUT_DIR) --allowed-books $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) --raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR)"; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_ATP_ODDS_JSON)" ]; then args="$$args --atp-odds-json $(KALSHI_SPORTS_CONSENSUS_ATP_ODDS_JSON)"; fi; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_ATP_ODDS_META_JSON)" ]; then args="$$args --atp-odds-meta-json $(KALSHI_SPORTS_CONSENSUS_ATP_ODDS_META_JSON)"; fi; \
	if [ "$(KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE)" = "1" ] || [ "$(KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE)" = "true" ] || [ "$(KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE)" = "yes" ]; then args="$$args --capture-current"; fi; \
	python3 scripts/kalshi_sports_consensus_atp_donor_adapter.py $$args

kalshi-sports-consensus-nfl-adapter:
	@args="--write --reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) --combined-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --base-kalshi-json docs/codex/macro/latest-kalshi-universe-scan.json --nfl-kalshi-json $(KALSHI_SPORTS_CONSENSUS_NFL_KALSHI_JSON) --out-dir $(KALSHI_SPORTS_CONSENSUS_NFL_ADAPTER_OUT_DIR) --allowed-books $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) --raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR)"; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_NFL_ODDS_JSON)" ]; then args="$$args --nfl-odds-json $(KALSHI_SPORTS_CONSENSUS_NFL_ODDS_JSON)"; fi; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_NFL_ODDS_META_JSON)" ]; then args="$$args --nfl-odds-meta-json $(KALSHI_SPORTS_CONSENSUS_NFL_ODDS_META_JSON)"; fi; \
	if [ "$(KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE)" = "1" ] || [ "$(KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE)" = "true" ] || [ "$(KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE)" = "yes" ]; then args="$$args --capture-current"; fi; \
	python3 scripts/kalshi_sports_consensus_nfl_adapter.py $$args

kalshi-sports-consensus-soccer-adapter:
	@args="--write --reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) --combined-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --base-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --soccer-kalshi-json $(KALSHI_SPORTS_CONSENSUS_SOCCER_KALSHI_JSON) --out-dir $(KALSHI_SPORTS_CONSENSUS_SOCCER_ADAPTER_OUT_DIR) --allowed-books $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) --raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR)"; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_JSON)" ]; then args="$$args --soccer-odds-json $(KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_JSON)"; fi; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_META_JSON)" ]; then args="$$args --soccer-odds-meta-json $(KALSHI_SPORTS_CONSENSUS_SOCCER_ODDS_META_JSON)"; fi; \
	if [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE)" = "1" ] || [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE)" = "true" ] || [ "$(KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE)" = "yes" ]; then args="$$args --capture-current"; fi; \
	python3 scripts/kalshi_sports_consensus_soccer_adapter.py $$args

kalshi-sports-consensus-nba-adapter:
	@args="--write --reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) --combined-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --base-kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) --nba-kalshi-json $(KALSHI_SPORTS_CONSENSUS_NBA_KALSHI_JSON) --out-dir $(KALSHI_SPORTS_CONSENSUS_NBA_ADAPTER_OUT_DIR) --allowed-books $(KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS) --raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR)"; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_NBA_ODDS_JSON)" ]; then args="$$args --nba-odds-json $(KALSHI_SPORTS_CONSENSUS_NBA_ODDS_JSON)"; fi; \
	if [ -n "$(KALSHI_SPORTS_CONSENSUS_NBA_ODDS_META_JSON)" ]; then args="$$args --nba-odds-meta-json $(KALSHI_SPORTS_CONSENSUS_NBA_ODDS_META_JSON)"; fi; \
	if [ "$(KALSHI_SPORTS_CONSENSUS_NBA_CAPTURE)" = "1" ] || [ "$(KALSHI_SPORTS_CONSENSUS_NBA_CAPTURE)" = "true" ] || [ "$(KALSHI_SPORTS_CONSENSUS_NBA_CAPTURE)" = "yes" ]; then args="$$args --capture-current"; fi; \
	python3 scripts/kalshi_sports_consensus_nba_adapter.py $$args

kalshi-sports-consensus-refresh:
	@$(MAKE) --no-print-directory kalshi-universe-scan
	@$(MAKE) --no-print-directory kalshi-sports-consensus-public-kalshi-refresh
	@python3 scripts/kalshi_sports_consensus_reference_build.py \
		--capture-current \
		--kalshi-json docs/codex/macro/latest-kalshi-universe-scan.json \
		--reference-json $(KALSHI_SPORTS_CONSENSUS_JSON) \
		--report-dir $(KALSHI_SPORTS_CONSENSUS_BUILD_OUT_DIR) \
		--api-key-file "$(KALSHI_SPORTS_CONSENSUS_KEY_FILE)" \
		--sport-keys $(KALSHI_SPORTS_CONSENSUS_SPORT_KEYS) \
		--bookmakers $(KALSHI_SPORTS_CONSENSUS_BOOKMAKERS) \
		--raw-output-dir $(KALSHI_SPORTS_CONSENSUS_RAW_DIR) \
		--required-books $(KALSHI_SPORTS_CONSENSUS_REQUIRED_BOOKS) \
		--max-event-delta-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_EVENT_DELTA_SECONDS) \
		--max-source-age-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_SOURCE_AGE_SECONDS)
	@$(MAKE) --no-print-directory kalshi-sports-consensus-atp-donor-adapter \
		KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE=1
	@$(MAKE) --no-print-directory kalshi-sports-consensus-nfl-adapter \
		KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE=1
	@$(MAKE) --no-print-directory kalshi-sports-consensus-soccer-adapter \
		KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE=1
	@$(MAKE) --no-print-directory kalshi-sports-consensus-nba-adapter \
		KALSHI_SPORTS_CONSENSUS_NBA_CAPTURE=1
	@$(MAKE) --no-print-directory kalshi-sports-consensus-preflight

kalshi-sports-consensus-preflight:
	@python3 scripts/kalshi_sports_consensus_preflight.py \
		--write \
		--kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) \
		--consensus-json $(KALSHI_SPORTS_CONSENSUS_JSON) \
		--out-dir $(KALSHI_SPORTS_CONSENSUS_OUT_DIR) \
		--min-distinct-books $(KALSHI_SPORTS_CONSENSUS_MIN_BOOKS) \
		--max-timestamp-skew-seconds $(KALSHI_SPORTS_CONSENSUS_MAX_SKEW_SECONDS)

kalshi-sports-consensus-observation-loop:
	@python3 scripts/kalshi_sports_consensus_observation_loop.py \
		--write \
		--preflight-path docs/codex/macro/latest-kalshi-sports-consensus-preflight.json \
		--universe-path $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON) \
		--settled-snapshot-path $(KALSHI_SPORTS_CONSENSUS_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_SPORTS_CONSENSUS_SETTLED_RAW_DIR) \
		--observation-dir $(KALSHI_SPORTS_CONSENSUS_OBSERVATION_DIR) \
		--label-dir $(KALSHI_SPORTS_CONSENSUS_LABEL_DIR) \
		--out-dir $(KALSHI_SPORTS_CONSENSUS_OBSERVATION_OUT_DIR) \
		--observed-probe-max-tickers $(KALSHI_SPORTS_CONSENSUS_OBSERVED_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED)),--probe-observed-public,)

kalshi-sports-consensus-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-sports-consensus-refresh
	@$(MAKE) --no-print-directory kalshi-sports-consensus-observation-loop \
		KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED=1
	@$(MAKE) --no-print-directory kalshi-sports-consensus-falsification
	@$(MAKE) --no-print-directory kalshi-sports-consensus-provider-audit

kalshi-sports-consensus-falsification:
	@python3 scripts/kalshi_sports_consensus_falsification.py \
		--write \
		--preflight-path docs/codex/macro/latest-kalshi-sports-consensus-preflight.json \
		--observation-dir $(KALSHI_SPORTS_CONSENSUS_FALSIFICATION_OBSERVATION_DIR) \
		--label-dir $(KALSHI_SPORTS_CONSENSUS_FALSIFICATION_LABEL_DIR) \
		--out-dir $(KALSHI_SPORTS_CONSENSUS_FALSIFICATION_OUT_DIR)

kalshi-resolved-archive-backfill:
	@python3 scripts/kalshi_resolved_archive_backfill.py \
		--write \
		--out-dir $(KALSHI_RESOLVED_ARCHIVE_BACKFILL_OUT_DIR) \
		--raw-dir $(KALSHI_RESOLVED_ARCHIVE_RAW_DIR) \
		--markets-raw-path $(KALSHI_RESOLVED_ARCHIVE_MARKETS_RAW_PATH) \
		--candlesticks-raw-path $(KALSHI_RESOLVED_ARCHIVE_CANDLESTICKS_RAW_PATH) \
		--series-tickers $(KALSHI_RESOLVED_ARCHIVE_SERIES_TICKERS) \
		--limit $(KALSHI_RESOLVED_ARCHIVE_LIMIT) \
		--max-pages $(KALSHI_RESOLVED_ARCHIVE_MAX_PAGES) \
		--days-back $(KALSHI_RESOLVED_ARCHIVE_DAYS_BACK) \
		--period-interval $(KALSHI_RESOLVED_ARCHIVE_PERIOD_INTERVAL) \
		--request-delay-seconds $(KALSHI_RESOLVED_ARCHIVE_REQUEST_DELAY_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_RESOLVED_ARCHIVE_CAPTURE)),--capture-public,)

kalshi-sports-historical-consensus-feasibility:
	@python3 scripts/kalshi_sports_historical_consensus_feasibility.py \
		--write \
		--out-dir $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_OUT_DIR) \
		--snapshot-interval-seconds $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_SNAPSHOT_INTERVAL_SECONDS) \
		--max-allowed-skew-seconds $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_MAX_SKEW_SECONDS) \
		--api-key-file "$(KALSHI_SPORTS_CONSENSUS_KEY_FILE)" \
		--probe-sport-key $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_SPORT_KEY) \
		--probe-regions $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_REGIONS) \
		--probe-markets $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_MARKETS) \
		--probe-date-utc $(KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE_DATE_UTC) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE)),--probe-paid-endpoint,)

kalshi-sports-consensus-provider-audit:
	@$(MAKE) --no-print-directory kalshi-sports-consensus-soccer-asian-provider-diagnostic
	@python3 scripts/kalshi_sports_consensus_provider_audit.py \
		--out-dir $(KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_OUT_DIR) \
		--target-sports $(KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_TARGET_SPORTS) \
		--deferred-target-sports $(KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_DEFERRED_SPORTS)

kalshi-sports-event-velocity-eta:
	@python3 scripts/kalshi_sports_event_velocity_eta.py \
		--write \
		--out-dir $(KALSHI_SPORTS_EVENT_VELOCITY_ETA_OUT_DIR)

kalshi-claude-advice-audit:
	@python3 scripts/kalshi_claude_advice_audit.py \
		--out-dir $(KALSHI_CLAUDE_ADVICE_AUDIT_OUT_DIR)

kalshi-sports-blocker-clearance-cycle:
	@python3 scripts/kalshi_sports_blocker_clearance_cycle.py \
		--write \
		--out-dir $(KALSHI_SPORTS_BLOCKER_CLEARANCE_OUT_DIR) \
		--atp-repo $(KALSHI_SPORTS_BLOCKER_CLEARANCE_ATP_REPO) \
		--command-timeout-seconds $(KALSHI_SPORTS_BLOCKER_CLEARANCE_COMMAND_TIMEOUT_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE)),--run-due,)

kalshi-sports-line-move-delta-logger:
	@python3 scripts/kalshi_sports_line_move_delta_logger.py \
		--write \
		--out-dir $(KALSHI_SPORTS_LINE_MOVE_OUT_DIR) \
		--state-dir $(KALSHI_SPORTS_LINE_MOVE_STATE_DIR) \
		--api-key-file "$(KALSHI_SPORTS_CONSENSUS_KEY_FILE)" \
		--sport-keys $(KALSHI_SPORTS_LINE_MOVE_SPORT_KEYS) \
		--bookmakers $(KALSHI_SPORTS_LINE_MOVE_BOOKMAKERS) \
		--regions $(KALSHI_SPORTS_LINE_MOVE_REGIONS) \
		--markets $(KALSHI_SPORTS_LINE_MOVE_MARKETS) \
		--interval-seconds $(KALSHI_SPORTS_LINE_MOVE_INTERVAL_SECONDS) \
		--max-cycles $(KALSHI_SPORTS_LINE_MOVE_MAX_CYCLES) \
		--timeout-seconds $(KALSHI_SPORTS_LINE_MOVE_TIMEOUT_SECONDS)

kalshi-tick-recorder:
	@python3 scripts/kalshi_tick_recorder.py \
		--write \
		--out-dir $(KALSHI_TICK_RECORDER_OUT_DIR) \
		--jsonl-dir $(KALSHI_TICK_RECORDER_JSONL_DIR) \
		--universe-path $(KALSHI_TICK_RECORDER_UNIVERSE_PATH) \
		--tickers "$(KALSHI_TICK_RECORDER_TICKERS)" \
		--channels $(KALSHI_TICK_RECORDER_CHANNELS) \
		--max-tickers $(KALSHI_TICK_RECORDER_MAX_TICKERS) \
		--duration-seconds $(KALSHI_TICK_RECORDER_DURATION_SECONDS) \
		--max-gap-seconds $(KALSHI_TICK_RECORDER_MAX_GAP_SECONDS) \
		--execution-mode $(KALSHI_TICK_RECORDER_EXECUTION_MODE)

kalshi-sports-microstructure-observation-loop:
	@python3 scripts/kalshi_sports_microstructure_observation_loop.py \
		--write \
		--out-dir $(KALSHI_SPORTS_MICROSTRUCTURE_OUT_DIR) \
		--universe-scan-path docs/codex/macro/latest-kalshi-universe-scan.json \
		--raw-orderbook-dir $(KALSHI_SPORTS_MICROSTRUCTURE_RAW_ORDERBOOK_DIR) \
		--observation-dir $(KALSHI_SPORTS_MICROSTRUCTURE_OBSERVATION_DIR) \
		--settled-snapshot-path $(KALSHI_SPORTS_MICROSTRUCTURE_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_SPORTS_MICROSTRUCTURE_SETTLED_RAW_DIR) \
		--label-dir $(KALSHI_SPORTS_MICROSTRUCTURE_LABEL_DIR) \
		--max-tickers $(KALSHI_SPORTS_MICROSTRUCTURE_MAX_TICKERS) \
		--max-close-hours $(KALSHI_SPORTS_MICROSTRUCTURE_MAX_CLOSE_HOURS) \
		--depth $(KALSHI_SPORTS_MICROSTRUCTURE_DEPTH) \
		--delay-seconds $(KALSHI_SPORTS_MICROSTRUCTURE_DELAY_SECONDS) \
		--observed-probe-max-tickers $(KALSHI_SPORTS_MICROSTRUCTURE_PROBE_MAX_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_MICROSTRUCTURE_PROBE_OBSERVED)),--probe-observed-public,) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_MICROSTRUCTURE_CAPTURE)),--capture-orderbooks,)

kalshi-near-resolution-informed-flow-evidence-gate:
	@python3 scripts/kalshi_near_resolution_informed_flow_evidence_gate.py \
		--write \
		--out-dir $(KALSHI_NEAR_RESOLUTION_FLOW_OUT_DIR) \
		--microstructure-path $(KALSHI_NEAR_RESOLUTION_FLOW_MICROSTRUCTURE_PATH)

kalshi-near-resolution-flow-replay-gates:
	@python3 scripts/kalshi_near_resolution_flow_replay_gates.py \
		--write \
		--out-dir $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_OUT_DIR) \
		--evidence-path docs/codex/macro/latest-kalshi-near-resolution-informed-flow-evidence-gate.json \
		--microstructure-path docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json \
		--max-close-hours $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CLOSE_HOURS) \
		--max-current-candidates $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CURRENT_CANDIDATES) \
		--max-observation-age-seconds $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_OBSERVATION_AGE_SECONDS) \
		--max-cluster-share $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MAX_CLUSTER_SHARE) \
		--min-positive-capacity-contracts $(KALSHI_NEAR_RESOLUTION_FLOW_REPLAY_MIN_POSITIVE_CAPACITY_CONTRACTS)

kalshi-near-resolution-flow-terms-capture:
	@python3 scripts/kalshi_near_resolution_flow_terms_capture.py \
		--write \
		--out-dir $(KALSHI_NEAR_RESOLUTION_FLOW_TERMS_OUT_DIR) \
		--flow-replay-path docs/codex/macro/latest-kalshi-near-resolution-flow-replay-gates.json \
		--raw-terms-dir $(KALSHI_NEAR_RESOLUTION_FLOW_TERMS_RAW_DIR) \
		--max-markets $(KALSHI_NEAR_RESOLUTION_FLOW_TERMS_MAX_MARKETS) \
		--delay-seconds $(KALSHI_NEAR_RESOLUTION_FLOW_TERMS_DELAY_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_NEAR_RESOLUTION_FLOW_TERMS_CAPTURE)),--capture-terms,)

kalshi-passive-liquidity-provision-evidence-gate:
	@python3 scripts/kalshi_passive_liquidity_provision_evidence_gate.py \
		--write \
		--out-dir $(KALSHI_PASSIVE_LIQUIDITY_OUT_DIR) \
		--microstructure-path docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json \
		--ttl-seconds $(KALSHI_PASSIVE_LIQUIDITY_TTL_SECONDS)

kalshi-passive-liquidity-paper-fill-loop:
	@python3 scripts/kalshi_passive_liquidity_paper_fill_loop.py \
		--write \
		--out-dir $(KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_OUT_DIR) \
		--state-dir $(KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_STATE_DIR) \
		--passive-path docs/codex/macro/latest-kalshi-passive-liquidity-provision-evidence-gate.json \
		--microstructure-path docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json

kalshi-passive-liquidity-paper-fill-falsification:
	@python3 scripts/kalshi_passive_liquidity_paper_fill_falsification.py \
		--write \
		--out-dir $(KALSHI_PASSIVE_LIQUIDITY_PAPER_FILL_FALSIFICATION_OUT_DIR) \
		--paper-fill-path docs/codex/macro/latest-kalshi-passive-liquidity-paper-fill-loop.json \
		--microstructure-path docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json

kalshi-passive-liquidity-fill-clock-diagnostic:
	@python3 scripts/kalshi_passive_liquidity_fill_clock_diagnostic.py \
		--write \
		--out-dir $(KALSHI_PASSIVE_LIQUIDITY_FILL_CLOCK_DIAGNOSTIC_OUT_DIR) \
		--paper-fill-path docs/codex/macro/latest-kalshi-passive-liquidity-paper-fill-loop.json \
		--microstructure-path docs/codex/macro/latest-kalshi-sports-microstructure-observation-loop.json

kalshi-sports-microstructure-observation-watch-once:
	@$(MAKE) --no-print-directory kalshi-sports-stack-sequencing
	@$(MAKE) --no-print-directory kalshi-sports-microstructure-observation-loop

kalshi-sports-nondirectional-evidence-watch-once:
	@$(MAKE) --no-print-directory kalshi-sports-microstructure-observation-watch-once
	@$(MAKE) --no-print-directory kalshi-near-resolution-informed-flow-evidence-gate
	@$(MAKE) --no-print-directory kalshi-near-resolution-flow-replay-gates
	@$(MAKE) --no-print-directory kalshi-passive-liquidity-provision-evidence-gate
	@$(MAKE) --no-print-directory kalshi-passive-liquidity-paper-fill-loop
	@$(MAKE) --no-print-directory kalshi-passive-liquidity-paper-fill-falsification
	@$(MAKE) --no-print-directory kalshi-passive-liquidity-fill-clock-diagnostic

kalshi-sports-evidence-cycle-report:
	@python3 scripts/kalshi_sports_evidence_cycle_report.py \
		--write \
		--out-dir $(KALSHI_SPORTS_EVIDENCE_CYCLE_OUT_DIR)

kalshi-sports-evidence-cycle:
	@$(MAKE) --no-print-directory kalshi-universe-scan
	@$(MAKE) --no-print-directory kalshi-sports-proxy-observation-watch-once
	@$(MAKE) --no-print-directory kalshi-atp-proxy-observation-watch-once
	@$(MAKE) --no-print-directory kalshi-world-cup-proxy-observation-watch-once
	@$(MAKE) --no-print-directory kalshi-sports-nondirectional-evidence-watch-once
	@$(MAKE) --no-print-directory kalshi-sports-stack-sequencing
	@$(MAKE) --no-print-directory kalshi-sports-consensus-refresh
	@$(MAKE) --no-print-directory kalshi-sports-consensus-observation-loop
	@$(MAKE) --no-print-directory kalshi-sports-consensus-falsification
	@$(MAKE) --no-print-directory kalshi-sports-consensus-provider-audit
	@$(MAKE) --no-print-directory kalshi-sports-event-velocity-eta
	@$(MAKE) --no-print-directory kalshi-world-cup-outcome-independence-diagnostic
	@$(MAKE) --no-print-directory kalshi-near-resolution-flow-terms-capture
	@$(MAKE) --no-print-directory kalshi-ev-ledger
	@$(MAKE) --no-print-directory kalshi-paper-decision-candidates
	@$(MAKE) --no-print-directory kalshi-paper-settlement-reconcile
	@$(MAKE) --no-print-directory kalshi-signal-decay-retirement \
		KALSHI_SIGNAL_DECAY_RETIREMENT_PAPER_DECISIONS=docs/codex/macro/latest-paper-settlement-reconciliation.json
	@$(MAKE) --no-print-directory kalshi-live-preflight
	@$(MAKE) --no-print-directory kalshi-sports-evidence-cycle-report

kalshi-sports-label-accumulation-cycle:
	@$(MAKE) --no-print-directory kalshi-sports-evidence-cycle
	@python3 scripts/kalshi_sports_label_accumulation_cycle.py \
		--write \
		--out-dir $(KALSHI_SPORTS_LABEL_ACCUMULATION_OUT_DIR)

kalshi-weather-proxy-feature-packet:
	python3 scripts/kalshi_weather_proxy_feature_packet.py \
		--write \
		--max-close-hours $(KALSHI_WEATHER_PROXY_FEATURE_MAX_CLOSE_HOURS) \
		--max-contracts $(KALSHI_WEATHER_PROXY_FEATURE_MAX_CONTRACTS) \
		--raw-universe-path $(KALSHI_WEATHER_PROXY_FEATURE_RAW_UNIVERSE) \
		--raw-proxy-dir $(KALSHI_WEATHER_PROXY_FEATURE_RAW_DIR) \
		--out-dir $(KALSHI_WEATHER_PROXY_FEATURE_OUT_DIR) \
		$(if $(filter 1 true yes,$(KALSHI_WEATHER_PROXY_FEATURE_CAPTURE)),--capture-public-proxy,)

kalshi-weather-proxy-feature-watch-once:
	$(MAKE) --no-print-directory kalshi-universe-watch-once
	$(MAKE) --no-print-directory kalshi-probability-breadth-scout
	$(MAKE) --no-print-directory kalshi-weather-proxy-feature-packet

kalshi-weather-proxy-observation-loop:
	python3 scripts/kalshi_weather_proxy_observation_loop.py \
		--write \
		--out-dir $(KALSHI_WEATHER_PROXY_OBSERVATION_OUT_DIR) \
		--settled-snapshot-path $(KALSHI_WEATHER_PROXY_SETTLED_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_WEATHER_PROXY_SETTLED_RAW_DIR) \
		--settled-limit $(KALSHI_WEATHER_PROXY_SETTLED_LIMIT) \
		--settled-max-pages $(KALSHI_WEATHER_PROXY_SETTLED_MAX_PAGES) \
		--observed-probe-max-tickers $(KALSHI_WEATHER_PROXY_OBSERVATION_PROBE_MAX_TICKERS) \
		--observation-dir $(KALSHI_WEATHER_PROXY_OBSERVATION_DIR) \
		--label-dir $(KALSHI_WEATHER_PROXY_LABEL_DIR) \
		$(if $(filter 1 true yes,$(KALSHI_WEATHER_PROXY_OBSERVATION_CAPTURE_SETTLED)),--capture-settled-public,)

kalshi-weather-proxy-observation-watch-once:
	$(MAKE) --no-print-directory kalshi-weather-proxy-feature-watch-once
	$(MAKE) --no-print-directory kalshi-weather-proxy-observation-loop
	$(MAKE) --no-print-directory kalshi-weather-proxy-feature-model-falsification
	$(MAKE) --no-print-directory kalshi-weather-proxy-research-candidate-replay
	$(MAKE) --no-print-directory kalshi-weather-proxy-capacity-correlation-decay
	$(MAKE) --no-print-directory kalshi-weather-proxy-correlation-cluster-control
	$(MAKE) --no-print-directory kalshi-signal-factory-status
	$(MAKE) --no-print-directory macro-route

kalshi-weather-proxy-feature-model-falsification:
	python3 scripts/kalshi_weather_proxy_feature_model_falsification.py \
		--write \
		--label-dir $(KALSHI_WEATHER_PROXY_LABEL_DIR) \
		--out-dir $(KALSHI_WEATHER_PROXY_MODEL_OUT_DIR) \
		--min-independent-labels $(KALSHI_WEATHER_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_WEATHER_PROXY_MODEL_MIN_OOS_LABELS) \
		--test-fraction $(KALSHI_WEATHER_PROXY_MODEL_TEST_FRACTION) \
		--fdr-alpha $(KALSHI_WEATHER_PROXY_MODEL_FDR_ALPHA)

kalshi-weather-proxy-research-candidate-replay:
	python3 scripts/kalshi_weather_proxy_research_candidate_replay.py \
		--write \
		--label-dir $(KALSHI_WEATHER_PROXY_LABEL_DIR) \
		--model-falsification-path $(KALSHI_WEATHER_PROXY_REPLAY_MODEL_PATH) \
		--out-dir $(KALSHI_WEATHER_PROXY_REPLAY_OUT_DIR)

kalshi-weather-proxy-capacity-correlation-decay:
	python3 scripts/kalshi_weather_proxy_capacity_correlation_decay.py \
		--write \
		--feature-packet-path $(KALSHI_WEATHER_PROXY_CCD_FEATURE_PACKET) \
		--replay-path $(KALSHI_WEATHER_PROXY_CCD_REPLAY) \
		--raw-orderbook-dir $(KALSHI_WEATHER_PROXY_CCD_RAW_ORDERBOOK_DIR) \
		--out-dir $(KALSHI_WEATHER_PROXY_CCD_OUT_DIR) \
		--max-close-hours $(KALSHI_WEATHER_PROXY_CCD_MAX_CLOSE_HOURS) \
		--max-tickers $(KALSHI_WEATHER_PROXY_CCD_MAX_TICKERS) \
		--depth $(KALSHI_WEATHER_PROXY_CCD_DEPTH) \
		--delay-seconds $(KALSHI_WEATHER_PROXY_CCD_DELAY_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_WEATHER_PROXY_CCD_CAPTURE_ORDERBOOKS)),--capture-orderbooks,)

kalshi-weather-proxy-correlation-cluster-control:
	python3 scripts/kalshi_weather_proxy_correlation_cluster_control.py \
		--write \
		--ccd-path $(KALSHI_WEATHER_PROXY_CLUSTER_CCD) \
		--out-dir $(KALSHI_WEATHER_PROXY_CLUSTER_OUT_DIR) \
		--max-cluster-share $(KALSHI_WEATHER_PROXY_CLUSTER_MAX_SHARE) \
		--min-positive-clusters $(KALSHI_WEATHER_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS)

kalshi-sports-proxy-capacity-correlation-decay:
	@python3 scripts/kalshi_sports_proxy_capacity_correlation_decay.py \
		--write \
		--feature-packet-path $(KALSHI_SPORTS_PROXY_CCD_FEATURE_PACKET) \
		--replay-path $(KALSHI_SPORTS_PROXY_CCD_REPLAY) \
		--raw-orderbook-dir $(KALSHI_SPORTS_PROXY_CCD_RAW_ORDERBOOK_DIR) \
		--out-dir $(KALSHI_SPORTS_PROXY_CCD_OUT_DIR) \
		--max-close-hours $(KALSHI_SPORTS_PROXY_CCD_MAX_CLOSE_HOURS) \
		--max-tickers $(KALSHI_SPORTS_PROXY_CCD_MAX_TICKERS) \
		--depth $(KALSHI_SPORTS_PROXY_CCD_DEPTH) \
		--delay-seconds $(KALSHI_SPORTS_PROXY_CCD_DELAY_SECONDS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_PROXY_CCD_CAPTURE_ORDERBOOKS)),--capture-orderbooks,)

kalshi-sports-proxy-correlation-cluster-control:
	@python3 scripts/kalshi_sports_proxy_correlation_cluster_control.py \
		--write \
		--ccd-path $(KALSHI_SPORTS_PROXY_CLUSTER_CCD) \
		--out-dir $(KALSHI_SPORTS_PROXY_CLUSTER_OUT_DIR) \
		--max-cluster-share $(KALSHI_SPORTS_PROXY_CLUSTER_MAX_SHARE) \
		--min-positive-clusters $(KALSHI_SPORTS_PROXY_CLUSTER_MIN_POSITIVE_CLUSTERS)

kalshi-crypto-proxy-feature-model-falsification:
	@python3 scripts/kalshi_crypto_proxy_feature_model_falsification.py \
		--write \
		--label-dir $(KALSHI_CRYPTO_PROXY_MODEL_LABEL_DIR) \
		--out-dir $(KALSHI_CRYPTO_PROXY_MODEL_OUT_DIR) \
		--min-independent-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_OOS_LABELS) \
		--test-fraction $(KALSHI_CRYPTO_PROXY_MODEL_TEST_FRACTION) \
		--fdr-alpha $(KALSHI_CRYPTO_PROXY_MODEL_FDR_ALPHA)

kalshi-sports-proxy-feature-model-falsification:
	@python3 scripts/kalshi_sports_proxy_feature_model_falsification.py \
		--write \
		--label-dir $(KALSHI_SPORTS_PROXY_LABEL_DIR) \
		--out-dir $(KALSHI_SPORTS_PROXY_MODEL_OUT_DIR) \
		--min-independent-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_INDEPENDENT_LABELS) \
		--min-oos-labels $(KALSHI_CRYPTO_PROXY_MODEL_MIN_OOS_LABELS) \
		--test-fraction $(KALSHI_CRYPTO_PROXY_MODEL_TEST_FRACTION) \
		--fdr-alpha $(KALSHI_CRYPTO_PROXY_MODEL_FDR_ALPHA)

kalshi-sports-proxy-research-candidate-replay:
	@python3 scripts/kalshi_sports_proxy_research_candidate_replay.py \
		--write \
		--label-dir $(KALSHI_SPORTS_PROXY_LABEL_DIR) \
		--model-falsification-path $(KALSHI_SPORTS_PROXY_REPLAY_MODEL_PATH) \
		--out-dir $(KALSHI_SPORTS_PROXY_REPLAY_OUT_DIR) \
		--min-side-oos-labels $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_SIDE_OOS_LABELS) \
		--min-decay-buckets $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_BUCKETS) \
		--min-decay-labels $(KALSHI_CRYPTO_PROXY_REPLAY_MIN_DECAY_LABELS) \
		$(if $(KALSHI_SPORTS_PROXY_REPLAY_PREFERRED_MODEL_ID),--preferred-model-id $(KALSHI_SPORTS_PROXY_REPLAY_PREFERRED_MODEL_ID),)

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

kalshi-source-repo-inventory:
	@python3 scripts/kalshi_source_repo_inventory.py \
		--write \
		--out-dir $(KALSHI_SOURCE_REPO_INVENTORY_OUT_DIR)

kalshi-external-artifact-wrap:
	@python3 scripts/kalshi_external_artifact_wrap.py \
		--write \
		--wrap-root $(KALSHI_EXTERNAL_ARTIFACT_WRAP_ROOT) \
		--out-dir $(KALSHI_EXTERNAL_ARTIFACT_WRAP_OUT_DIR)

kalshi-external-artifact-preflight:
	@python3 scripts/kalshi_external_artifact_preflight.py \
		--write \
		--wrap-root $(KALSHI_EXTERNAL_ARTIFACT_WRAP_ROOT) \
		--out-dir $(KALSHI_EXTERNAL_ARTIFACT_PREFLIGHT_OUT_DIR)

kalshi-signal-formula-registry:
	@args="--write --out-dir $(KALSHI_SIGNAL_FORMULA_REGISTRY_OUT_DIR)"; \
	if [ -n "$(KALSHI_SIGNAL_FORMULA_REGISTRY_SPEC)" ]; then args="$$args --spec-path $(KALSHI_SIGNAL_FORMULA_REGISTRY_SPEC)"; fi; \
	python3 scripts/kalshi_signal_formula_registry.py $$args

kalshi-prior-only-donor-gate:
	@python3 scripts/kalshi_prior_only_donor_gate.py \
		--write \
		--external-preflight-path $(KALSHI_PRIOR_ONLY_DONOR_GATE_EXTERNAL_PREFLIGHT) \
		--formula-registry-path $(KALSHI_PRIOR_ONLY_DONOR_GATE_FORMULA_REGISTRY) \
		--out-dir $(KALSHI_PRIOR_ONLY_DONOR_GATE_OUT_DIR)

kalshi-paper-decision-candidates:
	@python3 scripts/kalshi_paper_decision_candidates.py \
		--write \
		--ledger-path $(KALSHI_PAPER_DECISION_LEDGER) \
		--retirement-path $(KALSHI_PAPER_DECISION_RETIREMENT) \
		--ghost-depth-path $(KALSHI_PAPER_DECISION_GHOST_DEPTH) \
		--out-dir $(KALSHI_PAPER_DECISION_OUT_DIR) \
		--paper-bankroll $(KALSHI_PAPER_DECISION_BANKROLL) \
		--kelly-fraction $(KALSHI_PAPER_DECISION_KELLY_FRACTION) \
		--max-fraction-per-contract $(KALSHI_PAPER_DECISION_MAX_FRACTION) \
		--max-cluster-share $(KALSHI_PAPER_DECISION_MAX_CLUSTER_SHARE)

kalshi-paper-settlement-reconcile:
	@python3 scripts/kalshi_paper_settlement_reconcile.py \
		--write \
		--paper-decisions-path $(KALSHI_PAPER_SETTLEMENT_PAPER_DECISIONS) \
		--settled-snapshot-path $(KALSHI_PAPER_SETTLEMENT_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_PAPER_SETTLEMENT_RAW_DIR) \
		--out-dir $(KALSHI_PAPER_SETTLEMENT_OUT_DIR) \
		--max-fetch-tickers $(KALSHI_PAPER_SETTLEMENT_MAX_FETCH_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_PAPER_SETTLEMENT_FETCH)),--fetch-settled,)

kalshi-sports-paper-burn-in-cycle:
	@$(MAKE) --no-print-directory kalshi-sports-label-accumulation-cycle
	@python3 scripts/kalshi_sports_paper_burn_in_cycle.py \
		--write \
		--paper-decisions-path $(KALSHI_PAPER_SETTLEMENT_PAPER_DECISIONS) \
		--settled-snapshot-path $(KALSHI_PAPER_SETTLEMENT_SNAPSHOT) \
		--settled-raw-dir $(KALSHI_PAPER_SETTLEMENT_RAW_DIR) \
		--out-dir $(KALSHI_SPORTS_PAPER_BURN_IN_OUT_DIR) \
		--max-fetch-tickers $(KALSHI_SPORTS_PAPER_BURN_IN_MAX_FETCH_TICKERS) \
		$(if $(filter 1 true yes,$(KALSHI_SPORTS_PAPER_BURN_IN_FETCH)),--fetch-due-settlements,)

kalshi-always-on-collector-once:
	@python3 scripts/kalshi_always_on_collector.py \
		--write \
		--once \
		--targets $(KALSHI_ALWAYS_ON_COLLECTOR_TARGETS) \
		--out-dir $(KALSHI_ALWAYS_ON_COLLECTOR_OUT_DIR) \
		--base-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_BASE_INTERVAL_SECONDS) \
		--near-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_NEAR_INTERVAL_SECONDS) \
		--due-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_DUE_INTERVAL_SECONDS) \
		--near-close-window-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_NEAR_CLOSE_WINDOW_SECONDS)

kalshi-always-on-collector:
	@python3 scripts/kalshi_always_on_collector.py \
		--write \
		--targets $(KALSHI_ALWAYS_ON_COLLECTOR_TARGETS) \
		--out-dir $(KALSHI_ALWAYS_ON_COLLECTOR_OUT_DIR) \
		--max-cycles $(KALSHI_ALWAYS_ON_COLLECTOR_MAX_CYCLES) \
		--base-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_BASE_INTERVAL_SECONDS) \
		--near-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_NEAR_INTERVAL_SECONDS) \
		--due-interval-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_DUE_INTERVAL_SECONDS) \
		--near-close-window-seconds $(KALSHI_ALWAYS_ON_COLLECTOR_NEAR_CLOSE_WINDOW_SECONDS)

kalshi-signal-decay-retirement:
	@python3 scripts/kalshi_signal_decay_retirement.py \
		--write \
		--paper-decisions-path $(KALSHI_SIGNAL_DECAY_RETIREMENT_PAPER_DECISIONS) \
		--out-dir $(KALSHI_SIGNAL_DECAY_RETIREMENT_OUT_DIR) \
		--min-recent-decisions $(KALSHI_SIGNAL_DECAY_RETIREMENT_MIN_RECENT) \
		--min-recent-accuracy $(KALSHI_SIGNAL_DECAY_RETIREMENT_MIN_ACCURACY) \
		--max-calibration-error $(KALSHI_SIGNAL_DECAY_RETIREMENT_MAX_CAL_ERROR)

kalshi-live-preflight:
	@python3 scripts/kalshi_live_preflight.py \
		--write \
		--paper-decisions-path $(KALSHI_LIVE_PAPER_DECISIONS) \
		--external-preflight-path $(KALSHI_LIVE_EXTERNAL_PREFLIGHT) \
		--retirement-path $(KALSHI_LIVE_RETIREMENT) \
		--state-dir $(KALSHI_LIVE_STATE_DIR) \
		$(if $(KALSHI_LIVE_MARKET_SNAPSHOTS),--market-snapshots-path $(KALSHI_LIVE_MARKET_SNAPSHOTS),) \
		$(if $(filter 1 true yes,$(KALSHI_LIVE_CAPTURE_MARKET_SNAPSHOTS)),--capture-market-snapshots,) \
		--market-snapshot-depth $(KALSHI_LIVE_MARKET_SNAPSHOT_DEPTH) \
		--execution-mode $(KALSHI_LIVE_EXECUTION_MODE) \
		--out-dir $(KALSHI_LIVE_PREFLIGHT_OUT_DIR)

kalshi-live-demo:
	@python3 scripts/kalshi_live_trader.py \
		--write \
		--paper-decisions-path $(KALSHI_LIVE_PAPER_DECISIONS) \
		--external-preflight-path $(KALSHI_LIVE_EXTERNAL_PREFLIGHT) \
		--retirement-path $(KALSHI_LIVE_RETIREMENT) \
		--state-dir $(KALSHI_LIVE_STATE_DIR) \
		--execution-mode demo \
		--out-dir $(KALSHI_LIVE_TRADER_OUT_DIR)

kalshi-live-trader:
	@python3 scripts/kalshi_live_trader.py \
		--write \
		--paper-decisions-path $(KALSHI_LIVE_PAPER_DECISIONS) \
		--external-preflight-path $(KALSHI_LIVE_EXTERNAL_PREFLIGHT) \
		--retirement-path $(KALSHI_LIVE_RETIREMENT) \
		--state-dir $(KALSHI_LIVE_STATE_DIR) \
		--execution-mode $(KALSHI_LIVE_EXECUTION_MODE) \
		--out-dir $(KALSHI_LIVE_TRADER_OUT_DIR)

kalshi-live-reconcile:
	@python3 scripts/kalshi_live_reconcile.py \
		--write \
		--state-dir $(KALSHI_LIVE_STATE_DIR) \
		--execution-mode $(KALSHI_LIVE_EXECUTION_MODE) \
		--out-dir $(KALSHI_LIVE_RECONCILE_OUT_DIR)

KALSHI_JURISDICTION_SOURCE_URL ?=
kalshi-jurisdiction-refresh:
	@PYTHONPATH=. $(PYTHON) -c "import os; from predmarket.kalshi_jurisdiction import refresh_jurisdiction_state_from_config; from predmarket.config import load_config; cfg = load_config(); d = cfg.model_dump(); src = (os.environ.get('KALSHI_JURISDICTION_SOURCE_URL') or '').strip(); src and d.setdefault('kalshi_live', {}).setdefault('jurisdiction', {}) and d['kalshi_live']['jurisdiction'].update({'source_url': src}); s = refresh_jurisdiction_state_from_config(d); print('OK restricted_states=' + str(sorted(s.restricted_states)) + ' last_refreshed=' + s.last_refreshed.isoformat())"

kalshi-live-risk-snapshot:
	@python3 scripts/kalshi_live_risk_snapshot.py \
		--write \
		--state-dir $(KALSHI_LIVE_STATE_DIR) \
		--out-dir $(KALSHI_LIVE_RISK_SNAPSHOT_OUT_DIR)

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
