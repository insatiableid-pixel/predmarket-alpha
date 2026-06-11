import os
import time
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

class AuditLogger:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = str(Path(__file__).resolve().parents[1] / "data")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "database.sqlite"
        self.jsonl_path = self.data_dir / "audit_log.jsonl"
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        # Table for cryptographic audit logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                venue TEXT,
                contract TEXT,
                category TEXT,
                side TEXT,
                size REAL,
                price REAL,
                model_prob REAL,
                market_implied REAL,
                net_edge REAL,
                status TEXT,
                details TEXT,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                outcome INTEGER
            )
        """)
        # Support schema migration/upgrade for existing databases
        try:
            cursor.execute("ALTER TABLE audit_trail ADD COLUMN outcome INTEGER")
        except sqlite3.OperationalError:
            pass

        # Table for portfolio equity history (used for drawdown calculations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                total_equity REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _get_last_hash(self) -> str:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT entry_hash FROM audit_trail ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        # Seed hash if chain is empty
        return row[0] if row else "0000000000000000000000000000000000000000000000000000000000000000"

    def _compute_hash(self, payload: Dict[str, Any], prev_hash: str) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        hasher = hashlib.sha256()
        hasher.update(prev_hash.encode("utf-8"))
        hasher.update(serialized.encode("utf-8"))
        return hasher.hexdigest()

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
        details: Optional[str] = None,
        outcome: Optional[int] = None
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
            "outcome": outcome
        }
        
        prev_hash = self._get_last_hash()
        entry_hash = self._compute_hash(payload, prev_hash)
        
        # Write to SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_trail (
                timestamp, event_type, venue, contract, category, side, size, price,
                model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, "TRADE_INTENT", venue, contract, category, side, size, price,
            model_prob, market_implied, net_edge, status, details or "", prev_hash, entry_hash, outcome
        ))

        conn.commit()
        conn.close()

        # Write to JSONL
        log_entry = payload.copy()
        log_entry["prev_hash"] = prev_hash
        log_entry["entry_hash"] = entry_hash
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

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
            "outcome": None
        }
        
        prev_hash = self._get_last_hash()
        entry_hash = self._compute_hash(payload, prev_hash)
        
        # Write to SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_trail (
                timestamp, event_type, venue, contract, category, side, size, price,
                model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, event_type, "", "", "", "", 0.0, 0.0,
            0.0, 0.0, 0.0, "INFO", details, prev_hash, entry_hash, None
        ))

        conn.commit()
        conn.close()

        # Write to JSONL
        log_entry = payload.copy()
        log_entry["prev_hash"] = prev_hash
        log_entry["entry_hash"] = entry_hash
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        return entry_hash

    def log_equity(self, total_equity: float):
        timestamp = time.time()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO equity_history (timestamp, total_equity) VALUES (?, ?)",
            (timestamp, total_equity)
        )
        conn.commit()
        conn.close()

    def get_equity_history(self, since_seconds: float) -> List[Dict[str, Any]]:
        limit_time = time.time() - since_seconds
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, total_equity FROM equity_history WHERE timestamp >= ? ORDER BY timestamp ASC",
            (limit_time,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"timestamp": r[0], "total_equity": r[1]} for r in rows]

    def verify_audit_chain(self) -> bool:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, event_type, venue, contract, category, side, size, price,
                   model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
            FROM audit_trail ORDER BY id ASC
        """)
        rows = cursor.fetchall()
        conn.close()

        expected_prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        for row in rows:
            row_id, ts, event_type, venue, contract, category, side, size, price, mp, mi, ne, status, details, p_hash, e_hash, outcome = row
            
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
                "outcome": outcome
            }
            
            # Check link in chain
            if p_hash != expected_prev_hash:
                return False
            
            calculated_hash = self._compute_hash(payload, p_hash)
            if e_hash != calculated_hash:
                return False
            
            expected_prev_hash = e_hash
        
        return True

