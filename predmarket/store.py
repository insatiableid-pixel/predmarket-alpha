"""Point-in-time research data store.

The store writes normalized research facts to DuckDB when available and falls
back to SQLite in minimal test environments. Both backends use the same table
shape and JSON payloads so forecasts remain reproducible.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from predmarket.contracts import ForecastRecord, SourceDocument


class PointInTimeStore:
    """Persist market data, evidence, forecasts, outcomes, and experiments."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.research_dir = self.data_dir / "research"
        self.parquet_dir = self.research_dir / "parquet"
        self.samples_dir = self.research_dir / "density_samples"
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.research_dir / "research.duckdb"
        self.backend = "duckdb"
        try:
            import duckdb  # type: ignore

            self._conn = duckdb.connect(str(self.db_path))
            self._param = "?"
        except Exception:
            self.backend = "sqlite"
            self.db_path = self.research_dir / "research.sqlite"
            self._conn = sqlite3.connect(str(self.db_path))
            self._param = "?"
        self._init_tables()

    def close(self) -> None:
        self._conn.close()

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._conn.execute(sql, params)
        if self.backend == "sqlite":
            self._conn.commit()

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cur = self._conn.execute(sql, params)
        return cur.fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> List[Any]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def _init_tables(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                event_id TEXT,
                market_id TEXT,
                venue TEXT,
                as_of_ts DOUBLE,
                bid DOUBLE,
                ask DOUBLE,
                mid DOUBLE,
                volume_24h DOUBLE,
                open_interest DOUBLE,
                title TEXT,
                raw_json TEXT,
                PRIMARY KEY (market_id, as_of_ts)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS orderbooks (
                market_id TEXT,
                as_of_ts DOUBLE,
                bids_json TEXT,
                asks_json TEXT,
                raw_json TEXT,
                PRIMARY KEY (market_id, as_of_ts)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS source_documents (
                source_id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                url TEXT,
                published_ts DOUBLE,
                retrieved_ts DOUBLE,
                text TEXT,
                metadata_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS forecasts (
                forecast_id TEXT PRIMARY KEY,
                event_id TEXT,
                market_id TEXT,
                as_of_ts DOUBLE,
                horizon TEXT,
                method TEXT,
                model_version TEXT,
                p_mean DOUBLE,
                quantiles_json TEXT,
                density_samples_ref TEXT,
                base_rate_ref TEXT,
                evidence_refs_json TEXT,
                feature_hash TEXT,
                calibration_bucket TEXT,
                status_flags_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                event_id TEXT PRIMARY KEY,
                resolved_ts DOUBLE,
                outcome INTEGER,
                source TEXT,
                raw_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS kalshi_resolved_rows (
                row_id TEXT PRIMARY KEY,
                market_id TEXT,
                event_id TEXT,
                as_of_ts DOUBLE,
                resolved_ts DOUBLE,
                outcome INTEGER,
                feature_hash TEXT,
                row_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                run_id TEXT PRIMARY KEY,
                created_ts DOUBLE,
                config_json TEXT,
                report_json TEXT,
                code_version TEXT,
                status TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_runs (
                run_id TEXT PRIMARY KEY,
                created_ts DOUBLE,
                config_json TEXT,
                report_json TEXT,
                status TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_artifacts (
                artifact_id TEXT PRIMARY KEY,
                run_id TEXT,
                trajectory_id TEXT,
                artifact_type TEXT,
                created_ts DOUBLE,
                status TEXT,
                payload_json TEXT,
                reasons_json TEXT,
                parent_ids_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_edges (
                edge_id TEXT PRIMARY KEY,
                run_id TEXT,
                source_artifact_id TEXT,
                target_artifact_id TEXT,
                edge_type TEXT,
                created_ts DOUBLE,
                payload_json TEXT
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_transitions (
                transition_id TEXT PRIMARY KEY,
                run_id TEXT,
                trajectory_id TEXT,
                from_hypothesis_ids_json TEXT,
                to_hypothesis_id TEXT,
                transition_type TEXT,
                reason TEXT,
                accepted INTEGER,
                metrics_json TEXT,
                created_ts DOUBLE
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_trajectory_summaries (
                summary_id TEXT PRIMARY KEY,
                run_id TEXT,
                trajectory_id TEXT,
                created_ts DOUBLE,
                summary_json TEXT
            )
            """
        )

    def write_market_snapshot(
        self,
        snapshot: Any,
        event_id: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        as_of_ts: Optional[float] = None,
    ) -> None:
        ts = float(as_of_ts or time.time())
        market_id = getattr(snapshot, "contract_id", "")
        payload = raw_payload or {
            "venue": getattr(snapshot, "venue", ""),
            "contract_id": market_id,
            "title": getattr(snapshot, "title", ""),
            "bid": getattr(snapshot, "bid", 0.0),
            "ask": getattr(snapshot, "ask", 0.0),
            "mid": getattr(snapshot, "mid", 0.0),
            "open_interest": getattr(snapshot, "open_interest", 0.0),
            "volume_24h": getattr(snapshot, "volume_24h", 0.0),
            "line_history": getattr(snapshot, "line_history", []),
        }
        self._execute(
            """
            INSERT OR REPLACE INTO market_snapshots
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id or market_id,
                market_id,
                getattr(snapshot, "venue", ""),
                ts,
                float(getattr(snapshot, "bid", 0.0)),
                float(getattr(snapshot, "ask", 0.0)),
                float(getattr(snapshot, "mid", 0.0)),
                float(getattr(snapshot, "volume_24h", 0.0)),
                float(getattr(snapshot, "open_interest", 0.0)),
                getattr(snapshot, "title", ""),
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )

    def write_orderbook(
        self,
        market_id: str,
        bids: List[Dict[str, Any]],
        asks: List[Dict[str, Any]],
        as_of_ts: float,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._execute(
            "INSERT OR REPLACE INTO orderbooks VALUES (?, ?, ?, ?, ?)",
            (
                market_id,
                float(as_of_ts),
                json.dumps(bids, sort_keys=True, default=str),
                json.dumps(asks, sort_keys=True, default=str),
                json.dumps(raw_payload or {}, sort_keys=True, default=str),
            ),
        )

    def write_source_document(self, doc: SourceDocument) -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO source_documents
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.source_id,
                doc.source,
                doc.title,
                doc.url,
                float(doc.published_ts),
                float(doc.retrieved_ts),
                doc.text,
                json.dumps(doc.metadata, sort_keys=True, default=str),
            ),
        )

    def write_forecast(self, record: ForecastRecord) -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO forecasts
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.forecast_id,
                record.event_id,
                record.market_id,
                float(record.as_of_ts),
                record.horizon,
                record.method,
                record.model_version,
                float(record.p_mean),
                json.dumps(record.quantiles, sort_keys=True),
                record.density_samples_ref,
                record.base_rate_ref,
                json.dumps(record.evidence_refs, sort_keys=True),
                record.feature_hash,
                record.calibration_bucket,
                json.dumps(record.status_flags, sort_keys=True),
            ),
        )

    def write_density_samples(self, samples_ref: str, samples: List[float]) -> Path:
        """Persist posterior/density samples addressed by ForecastRecord ref."""
        safe_ref = "".join(ch for ch in samples_ref if ch.isalnum() or ch in ("-", "_"))
        out_path = self.samples_dir / f"{safe_ref}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump([float(sample) for sample in samples], f)
        return out_path

    def load_density_samples(self, samples_ref: str) -> List[float]:
        safe_ref = "".join(ch for ch in samples_ref if ch.isalnum() or ch in ("-", "_"))
        path = self.samples_dir / f"{safe_ref}.json"
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            return [float(sample) for sample in json.load(f)]

    def write_outcome(
        self,
        event_id: str,
        outcome: int,
        resolved_ts: float,
        source: str,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._execute(
            "INSERT OR REPLACE INTO outcomes VALUES (?, ?, ?, ?, ?)",
            (
                event_id,
                float(resolved_ts),
                int(outcome),
                source,
                json.dumps(raw_payload or {}, sort_keys=True, default=str),
            ),
        )

    def write_kalshi_resolved_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Persist discovery-ready Kalshi resolved rows."""
        for row in rows:
            row_id = str(row.get("row_id") or self._stable_row_id(row))
            payload = dict(row)
            payload["row_id"] = row_id
            feature_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            self._execute(
                """
                INSERT OR REPLACE INTO kalshi_resolved_rows
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    str(payload.get("market_id", "")),
                    str(payload.get("event_id", "")),
                    float(payload.get("as_of_ts", 0.0)),
                    float(payload.get("resolved_ts", 0.0)),
                    int(payload.get("outcome", 0)),
                    feature_hash,
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )

    def load_kalshi_resolved_rows(
        self,
        *,
        market_id: Optional[str] = None,
        min_as_of_ts: Optional[float] = None,
        max_as_of_ts: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Load persisted Kalshi rows for discovery/backtesting."""
        sql = """
            SELECT row_json
            FROM kalshi_resolved_rows
            WHERE 1 = 1
        """
        params: list[Any] = []
        if market_id is not None:
            sql += " AND market_id = ?"
            params.append(market_id)
        if min_as_of_ts is not None:
            sql += " AND as_of_ts >= ?"
            params.append(float(min_as_of_ts))
        if max_as_of_ts is not None:
            sql += " AND as_of_ts <= ?"
            params.append(float(max_as_of_ts))
        sql += " ORDER BY as_of_ts, market_id, row_json"
        return [json.loads(row[0] or "{}") for row in self._fetchall(sql, tuple(params))]

    def write_experiment_run(
        self,
        run_id: str,
        config: Dict[str, Any],
        report: Dict[str, Any],
        code_version: str,
        status: str,
    ) -> None:
        self._execute(
            "INSERT OR REPLACE INTO experiment_runs VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                time.time(),
                json.dumps(config, sort_keys=True, default=str),
                json.dumps(report, sort_keys=True, default=str),
                code_version,
                status,
            ),
        )

    def write_discovery_run(
        self,
        run_id: str,
        config: Dict[str, Any],
        report: Dict[str, Any],
        status: str,
    ) -> None:
        self._execute(
            "INSERT OR REPLACE INTO discovery_runs VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                float(report.get("created_ts", time.time())),
                json.dumps(config, sort_keys=True, default=str),
                json.dumps(report, sort_keys=True, default=str),
                status,
            ),
        )

    def write_discovery_artifact(self, artifact: Any) -> None:
        payload = self._discovery_payload(artifact)
        self._execute(
            """
            INSERT OR REPLACE INTO discovery_artifacts
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["artifact_id"],
                payload["run_id"],
                payload.get("trajectory_id", ""),
                payload.get("artifact_type", ""),
                float(payload.get("created_ts", time.time())),
                payload.get("status", "RECORDED"),
                json.dumps(payload.get("payload", {}), sort_keys=True, default=str),
                json.dumps(payload.get("reasons", []), sort_keys=True, default=str),
                json.dumps(payload.get("parent_ids", []), sort_keys=True, default=str),
            ),
        )
        for parent_id in payload.get("parent_ids", []):
            self.write_discovery_edge(
                run_id=payload["run_id"],
                source_artifact_id=str(parent_id),
                target_artifact_id=payload["artifact_id"],
                edge_type="parent",
                payload={"artifact_type": payload.get("artifact_type", "")},
            )

    def write_discovery_edge(
        self,
        run_id: str,
        source_artifact_id: str,
        target_artifact_id: str,
        edge_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        edge_payload = payload or {}
        base = json.dumps(
            {
                "run_id": run_id,
                "source": source_artifact_id,
                "target": target_artifact_id,
                "edge_type": edge_type,
                "payload": edge_payload,
            },
            sort_keys=True,
            default=str,
        )
        edge_id = "edge-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
        self._execute(
            "INSERT OR REPLACE INTO discovery_edges VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                edge_id,
                run_id,
                source_artifact_id,
                target_artifact_id,
                edge_type,
                time.time(),
                json.dumps(edge_payload, sort_keys=True, default=str),
            ),
        )

    def write_discovery_transition(self, transition: Any) -> None:
        payload = self._discovery_payload(transition)
        self._execute(
            """
            INSERT OR REPLACE INTO discovery_transitions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["transition_id"],
                payload["run_id"],
                payload.get("trajectory_id", ""),
                json.dumps(payload.get("from_hypothesis_ids", []), sort_keys=True),
                payload.get("to_hypothesis_id", ""),
                payload.get("transition_type", ""),
                payload.get("reason", ""),
                1 if payload.get("accepted", False) else 0,
                json.dumps(payload.get("metrics", {}), sort_keys=True, default=str),
                float(payload.get("created_ts", time.time())),
            ),
        )
        for parent_id in payload.get("from_hypothesis_ids", []):
            self.write_discovery_edge(
                run_id=payload["run_id"],
                source_artifact_id=str(parent_id),
                target_artifact_id=payload.get("to_hypothesis_id", ""),
                edge_type=payload.get("transition_type", "transition"),
                payload={"transition_id": payload["transition_id"]},
            )

    def write_discovery_trajectory_summary(self, run_id: str, summary: Any) -> None:
        payload = self._discovery_payload(summary)
        summary_id = f"{run_id}:{payload.get('trajectory_id', '')}"
        self._execute(
            """
            INSERT OR REPLACE INTO discovery_trajectory_summaries
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                run_id,
                payload.get("trajectory_id", ""),
                time.time(),
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )

    def load_discovery_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            """
            SELECT run_id, created_ts, config_json, report_json, status
            FROM discovery_runs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        if not row:
            return None
        return {
            "run_id": row[0],
            "created_ts": float(row[1]),
            "config": json.loads(row[2] or "{}"),
            "report": json.loads(row[3] or "{}"),
            "status": row[4],
        }

    def load_discovery_artifacts(
        self, run_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT artifact_id, run_id, trajectory_id, artifact_type, created_ts,
                   status, payload_json, reasons_json, parent_ids_json
            FROM discovery_artifacts
            WHERE run_id = ?
        """
        params: tuple[Any, ...] = (run_id,)
        if status is not None:
            sql += " AND status = ?"
            params = (run_id, status)
        sql += " ORDER BY created_ts, artifact_id"
        rows = self._fetchall(sql, params)
        return [
            {
                "artifact_id": row[0],
                "run_id": row[1],
                "trajectory_id": row[2],
                "artifact_type": row[3],
                "created_ts": float(row[4]),
                "status": row[5],
                "payload": json.loads(row[6] or "{}"),
                "reasons": json.loads(row[7] or "[]"),
                "parent_ids": json.loads(row[8] or "[]"),
            }
            for row in rows
        ]

    def load_discovery_edges(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT edge_id, run_id, source_artifact_id, target_artifact_id,
                   edge_type, created_ts, payload_json
            FROM discovery_edges
            WHERE run_id = ?
            ORDER BY created_ts, edge_id
            """,
            (run_id,),
        )
        return [
            {
                "edge_id": row[0],
                "run_id": row[1],
                "source_artifact_id": row[2],
                "target_artifact_id": row[3],
                "edge_type": row[4],
                "created_ts": float(row[5]),
                "payload": json.loads(row[6] or "{}"),
            }
            for row in rows
        ]

    def load_discovery_transitions(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT transition_id, run_id, trajectory_id, from_hypothesis_ids_json,
                   to_hypothesis_id, transition_type, reason, accepted,
                   metrics_json, created_ts
            FROM discovery_transitions
            WHERE run_id = ?
            ORDER BY created_ts, transition_id
            """,
            (run_id,),
        )
        return [
            {
                "transition_id": row[0],
                "run_id": row[1],
                "trajectory_id": row[2],
                "from_hypothesis_ids": json.loads(row[3] or "[]"),
                "to_hypothesis_id": row[4],
                "transition_type": row[5],
                "reason": row[6],
                "accepted": bool(row[7]),
                "metrics": json.loads(row[8] or "{}"),
                "created_ts": float(row[9]),
            }
            for row in rows
        ]

    def load_discovery_trajectory_summaries(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT summary_json
            FROM discovery_trajectory_summaries
            WHERE run_id = ?
            ORDER BY trajectory_id
            """,
            (run_id,),
        )
        return [json.loads(row[0] or "{}") for row in rows]

    @staticmethod
    def _discovery_payload(value: Any) -> Dict[str, Any]:
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return value
        raise TypeError("discovery payload must be a dict or expose to_dict()")

    @staticmethod
    def _stable_row_id(row: Dict[str, Any]) -> str:
        payload = {
            "market_id": row.get("market_id"),
            "as_of_ts": row.get("as_of_ts"),
            "outcome": row.get("outcome"),
            "schema": row.get("row_schema_version", 1),
        }
        return "kalshi-row-" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()[:20]

    def load_context(
        self, event_id: str, market_id: str, as_of_ts: float
    ) -> Dict[str, Any]:
        """Load only records that were known at or before as_of_ts."""
        snap = self._fetchone(
            """
            SELECT raw_json FROM market_snapshots
            WHERE market_id = ? AND as_of_ts <= ?
            ORDER BY as_of_ts DESC LIMIT 1
            """,
            (market_id, float(as_of_ts)),
        )
        book = self._fetchone(
            """
            SELECT bids_json, asks_json, raw_json FROM orderbooks
            WHERE market_id = ? AND as_of_ts <= ?
            ORDER BY as_of_ts DESC LIMIT 1
            """,
            (market_id, float(as_of_ts)),
        )
        docs = self._fetchall(
            """
            SELECT source_id, source, title, url, published_ts, retrieved_ts,
                   text, metadata_json
            FROM source_documents
            WHERE published_ts <= ? AND retrieved_ts <= ?
            ORDER BY published_ts DESC
            """,
            (float(as_of_ts), float(as_of_ts)),
        )
        return {
            "event_id": event_id,
            "market_id": market_id,
            "as_of_ts": float(as_of_ts),
            "snapshot": json.loads(snap[0]) if snap else None,
            "orderbook": {
                "bids": json.loads(book[0]),
                "asks": json.loads(book[1]),
                "raw": json.loads(book[2]),
            }
            if book
            else None,
            "source_documents": [
                SourceDocument(
                    source_id=row[0],
                    source=row[1],
                    title=row[2],
                    url=row[3],
                    published_ts=float(row[4]),
                    retrieved_ts=float(row[5]),
                    text=row[6],
                    metadata=json.loads(row[7] or "{}"),
                )
                for row in docs
            ],
        }

    def export_table_parquet(self, table_name: str) -> Optional[Path]:
        """Export a table to Parquet when the active backend supports it."""
        if self.backend != "duckdb":
            return None
        out_path = self.parquet_dir / f"{table_name}.parquet"
        self._execute(f"COPY {table_name} TO '{out_path}' (FORMAT PARQUET)")
        return out_path
