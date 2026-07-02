"""Integration tests for local artifact replay and pipeline gate routing.

These tests exercise:
1. SQLite/alembic schema migration producing expected tables.
2. Signal factory status routing through multiple upstream artifact files.
3. EV ledger and contract evidence reading from local filesystem artifacts.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
MAKEFILE_PATH = Path(__file__).resolve().parents[2] / "Makefile"


def load_module(name: str, script_name: str):
    """Load a standalone script module that manipulates sys.path."""
    script_path = SCRIPTS_DIR / script_name
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_artifact(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "status": "ready",
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def write_crypto_signal_foundation(module, tmp_path: Path):
    """Write a complete set of upstream artifacts for crypto proxy signal factory.

    Returns an ``Artifacts`` bundle with all paths set.  Observation-loop,
    model-falsification, and replay are left as missing files under *tmp_path*.
    """
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    builder = tmp_path / "builder.json"
    oos = tmp_path / "oos.json"
    breadth = tmp_path / "breadth.json"
    feature = tmp_path / "feature-packet.json"
    write_json(
        universe,
        safe_artifact(
            summary={"candidate_count": 100, "model_route_candidate_count": 2, "soft_watch_candidate_count": 98}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        builder,
        safe_artifact(
            status="labeled_observation_builder_pending_observations_waiting_settlement",
            summary={"total_pending_row_count": 44, "label_row_count": 0},
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={"valid_observation_count": 0},
        ),
    )
    write_json(
        breadth,
        safe_artifact(
            status="probability_breadth_scout_ready_crypto_proxy_feature_route",
            summary={
                "fast_candidate_count": 1538,
                "crypto_fast_candidate_count": 1256,
                "available_proxy_source_count": 3,
            },
        ),
    )
    write_json(
        feature,
        safe_artifact(
            status="crypto_proxy_feature_packet_ready",
            summary={"feature_row_count": 100, "feature_ready_count": 80, "proxy_available_asset_count": 3},
        ),
    )
    return replace(
        module.Artifacts.isolated(tmp_path),
        universe_scan_path=universe,
        ev_ledger_path=ledger,
        review_queue_path=queue,
        robustness_path=robustness,
        hypothesis_registry_path=registry,
        falsification_gate_path=falsification,
        labeled_observation_builder_path=builder,
        labeled_oos_backtest_path=oos,
        probability_breadth_scout_path=breadth,
        crypto_proxy_feature_packet_path=feature,
    )


# ---------------------------------------------------------------------------
# Local DB artifact tests
# ---------------------------------------------------------------------------


class TestSqliteSchema:
    """Verify alembic migrations produce the expected SQLite schema."""

    def test_alembic_migrations_create_expected_tables(self, tmp_path: Path) -> None:
        from alembic.config import Config as AlembicConfig

        from alembic import command

        project_root = Path(__file__).resolve().parents[2]
        db_path = tmp_path / "test.sqlite"
        alembic_cfg = AlembicConfig(str(project_root / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "audit_trail" in tables
        assert "equity_history" in tables
        assert "opportunities" in tables

    def test_audit_trail_has_hash_chain_columns(self, tmp_path: Path) -> None:
        from alembic.config import Config as AlembicConfig

        from alembic import command

        project_root = Path(__file__).resolve().parents[2]
        db_path = tmp_path / "test.sqlite"
        alembic_cfg = AlembicConfig(str(project_root / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(audit_trail)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "prev_hash" in columns
        assert "entry_hash" in columns
        assert "outcome" in columns


# ---------------------------------------------------------------------------
# Signal factory replay gate tests
# ---------------------------------------------------------------------------


class TestSignalFactoryRouting:
    """Exercise the signal factory status module with varying upstream artifact states."""

    def test_routes_to_feature_packet_when_observation_missing(self, tmp_path: Path) -> None:
        """With universe + registry + feature packet ready but observation loop
        and downstream stages missing, status should route to the feature packet
        ready state, indicating the next step is the observation loop."""
        module = load_module("signal_factory_status", "kalshi_signal_factory_status.py")
        foundation = write_crypto_signal_foundation(module, tmp_path)

        report = module.build_signal_factory_status(
            artifacts=foundation,
        )

        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        # Feature packet is ready; next stage is the observation loop
        assert report["status"] == "signal_factory_crypto_proxy_feature_packet_ready"

    def test_status_writes_json_and_markdown_artifacts(self, tmp_path: Path) -> None:
        """write_signal_factory_status writes temp artifacts without mutating latest pointers."""
        module = load_module("signal_factory_status", "kalshi_signal_factory_status.py")
        foundation = write_crypto_signal_foundation(module, tmp_path)

        report = module.build_signal_factory_status(
            artifacts=foundation,
        )

        out_dir = tmp_path / "status-out"
        artifacts = module.write_signal_factory_status(report, out_dir=out_dir)

        assert Path(artifacts["json_path"]).exists()
        assert Path(artifacts["markdown_path"]).exists()
        assert "latest_json_path" not in artifacts

        written = json.loads(Path(artifacts["json_path"]).read_text(encoding="utf-8"))
        assert "capabilities" in written
        assert written["research_only"] is True

        md = Path(artifacts["markdown_path"]).read_text(encoding="utf-8")
        assert "Signal Factory" in md
        assert "Capability Gates" in md

    def test_status_blocks_without_universe_scan(self, tmp_path: Path) -> None:
        """Without a universe scan, status should be blocked at the first stage."""
        module = load_module("signal_factory_status", "kalshi_signal_factory_status.py")

        report = module.build_signal_factory_status(
            artifacts=module.Artifacts.isolated(tmp_path),
        )

        assert "blocked" in report["status"]
        # First capability should be blocked
        universe_cap = [c for c in report["capabilities"] if c["name"] == "kalshi_universe_inventory"][0]
        assert universe_cap["status"] == "blocked"


# ---------------------------------------------------------------------------
# Makefile integration
# ---------------------------------------------------------------------------


class TestMakefileTargets:
    """Verify Make targets are registered for the signal factory pipeline."""

    def test_signal_factory_targets_exist(self) -> None:
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        for target in [
            "kalshi-signal-factory-status",
            "kalshi-hypothesis-registry",
            "kalshi-labeled-oos-backtest",
            "kalshi-crypto-proxy-observation-watch-once",
            "kalshi-crypto-proxy-correlation-cluster-control",
        ]:
            assert target in text, f"Missing Makefile target: {target}"
