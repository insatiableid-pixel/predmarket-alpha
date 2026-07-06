import fcntl
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class AuditLogger:
    """
    Immutable hash-chained audit logger with persistent SQLite connection pooling
    and thread-safe file locking for JSONL writes.

    Connection pooling (B4): a single sqlite3.Connection is held open for the
    lifetime of the instance. All writes are serialized through a threading.Lock
    to prevent 'database is locked' errors under concurrent dashboard + platform
    loop access.

    File locking (B6): JSONL appends use fcntl.flock for atomic multi-process
    safety.
    """

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            data_dir = str(Path(__file__).resolve().parents[1] / "data")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "database.sqlite"
        self.jsonl_path = self.data_dir / "audit_log.jsonl"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self):
        # Database table schemas are managed exclusively via Alembic migrations.
        # Ensure the SQLite database file exists.
        pass  # Connection is already established; tables created by migrations.

    def close(self):
        """Close the persistent database connection. Call on shutdown."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_last_hash(self) -> str:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT entry_hash FROM audit_trail ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
        # Seed hash if chain is empty
        return row[0] if row else "0000000000000000000000000000000000000000000000000000000000000000"

    def _compute_hash(self, payload: dict[str, Any], prev_hash: str) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        hasher = hashlib.sha256()
        hasher.update(prev_hash.encode("utf-8"))
        hasher.update(serialized.encode("utf-8"))
        return hasher.hexdigest()

    def _append_jsonl(self, log_entry: dict[str, Any]):
        """Thread-safe and process-safe JSONL append using fcntl file locking."""
        with open(self.jsonl_path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(log_entry) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def log_trade_intent(
        self,
        venue: str,
        contract: str,
        category: str,
        side: str,
        size: float,
        price: float,
        model_prob: float,
        market_implied: float,
        net_edge: float,
        status: str,
        details: str | None = None,
        outcome: int | None = None,
    ) -> str:
        timestamp = time.time()
        payload = {
            "timestamp": timestamp,
            "event_type": "TRADE_INTENT",
            "venue": venue,
            "contract": contract,
            "category": category,
            "side": side,
            "size": size,
            "price": price,
            "model_prob": model_prob,
            "market_implied": market_implied,
            "net_edge": net_edge,
            "status": status,
            "details": details or "",
            "outcome": outcome,
        }

        prev_hash = self._get_last_hash()
        entry_hash = self._compute_hash(payload, prev_hash)

        # Write to SQLite (pooled connection, thread-safe)
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_trail (
                    timestamp, event_type, venue, contract, category, side, size, price,
                    model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    timestamp,
                    "TRADE_INTENT",
                    venue,
                    contract,
                    category,
                    side,
                    size,
                    price,
                    model_prob,
                    market_implied,
                    net_edge,
                    status,
                    details or "",
                    prev_hash,
                    entry_hash,
                    outcome,
                ),
            )
            self._conn.commit()

        # Write to JSONL (file-locked)
        log_entry = payload.copy()
        log_entry["prev_hash"] = prev_hash
        log_entry["entry_hash"] = entry_hash
        self._append_jsonl(log_entry)

        return entry_hash

    def log_system_event(self, event_type: str, details: str) -> str:
        timestamp = time.time()
        payload = {
            "timestamp": timestamp,
            "event_type": event_type,
            "venue": "",
            "contract": "",
            "category": "",
            "side": "",
            "size": 0.0,
            "price": 0.0,
            "model_prob": 0.0,
            "market_implied": 0.0,
            "net_edge": 0.0,
            "status": "INFO",
            "details": details,
            "outcome": None,
        }

        prev_hash = self._get_last_hash()
        entry_hash = self._compute_hash(payload, prev_hash)

        # Write to SQLite (pooled connection, thread-safe)
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_trail (
                    timestamp, event_type, venue, contract, category, side, size, price,
                    model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    timestamp,
                    event_type,
                    "",
                    "",
                    "",
                    "",
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    "INFO",
                    details,
                    prev_hash,
                    entry_hash,
                    None,
                ),
            )
            self._conn.commit()

        # Write to JSONL (file-locked)
        log_entry = payload.copy()
        log_entry["prev_hash"] = prev_hash
        log_entry["entry_hash"] = entry_hash
        self._append_jsonl(log_entry)

        return entry_hash

    def log_equity(self, total_equity: float):
        timestamp = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "INSERT INTO equity_history (timestamp, total_equity) VALUES (?, ?)",
                (timestamp, total_equity),
            )
            self._conn.commit()

    def get_equity_history(self, since_seconds: float) -> list[dict[str, Any]]:
        limit_time = time.time() - since_seconds
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT timestamp, total_equity FROM equity_history WHERE timestamp >= ? ORDER BY timestamp ASC",
                (limit_time,),
            )
            rows = cursor.fetchall()
        return [{"timestamp": r[0], "total_equity": r[1]} for r in rows]

    def verify_audit_chain(self) -> bool:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, event_type, venue, contract, category, side, size, price,
                       model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
                FROM audit_trail ORDER BY id ASC
            """)
            rows = cursor.fetchall()

        expected_prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        for row in rows:
            (
                row_id,
                ts,
                event_type,
                venue,
                contract,
                category,
                side,
                size,
                price,
                mp,
                mi,
                ne,
                status,
                details,
                p_hash,
                e_hash,
                outcome,
            ) = row

            # Reconstruct payload
            payload = {
                "timestamp": ts,
                "event_type": event_type,
                "venue": venue,
                "contract": contract,
                "category": category,
                "side": side,
                "size": size,
                "price": price,
                "model_prob": mp,
                "market_implied": mi,
                "net_edge": ne,
                "status": status,
                "details": details,
                "outcome": outcome,
            }

            # Check link in chain
            if p_hash != expected_prev_hash:
                return False

            calculated_hash = self._compute_hash(payload, p_hash)
            if e_hash != calculated_hash:
                return False

            expected_prev_hash = e_hash

        return True

    def save_opportunities(self, slate: list[dict[str, Any]]):
        timestamp = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            for item in slate:
                # Estimate edge
                raw_edge = item["model_prob"] - item["market_implied"]
                tx_cost = 0.01
                net_edge = raw_edge - tx_cost
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO opportunities (
                        contract_id, timestamp, venue, title, category, model_prob, market_implied, edge, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        item["contract_id"],
                        timestamp,
                        item.get("venue", "Polymarket"),
                        item["title"],
                        item["category"],
                        item["model_prob"],
                        item["market_implied"],
                        net_edge,
                        item["status"],
                    ),
                )
            self._conn.commit()

    def get_opportunities(self) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT contract_id, timestamp, venue, title, category, model_prob, market_implied, edge, status
                FROM opportunities ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
        return [
            {
                "contract_id": r[0],
                "timestamp": r[1],
                "venue": r[2],
                "title": r[3],
                "category": r[4],
                "model_prob": r[5],
                "market_implied": r[6],
                "edge": r[7],
                "status": r[8],
            }
            for r in rows
        ]
