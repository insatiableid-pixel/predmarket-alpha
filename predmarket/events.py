"""Canonical event graph and semantic market identity checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from predmarket.contracts import EventSpec, MarketLink
from predmarket.store import PointInTimeStore

REQUIRED_RESOLUTION_FIELDS = {"resolution_criteria", "cutoff_ts", "oracle", "payout_rule"}


def _rules_key(resolution_rules: dict[str, Any]) -> str:
    selected = {k: resolution_rules.get(k) for k in sorted(REQUIRED_RESOLUTION_FIELDS)}
    payload = json.dumps(selected, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CanonicalEventGraph:
    """Maintain canonical events and venue-specific market links."""

    def __init__(self, store: PointInTimeStore, min_equivalence_confidence: float = 0.85):
        self.store = store
        self.min_equivalence_confidence = float(min_equivalence_confidence)
        self._init_tables()

    def _init_tables(self) -> None:
        self.store._execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_events (
                event_id TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                resolution_rules_json TEXT,
                resolution_key TEXT,
                created_ts DOUBLE,
                metadata_json TEXT
            )
            """
        )
        self.store._execute(
            """
            CREATE TABLE IF NOT EXISTS event_market_links (
                event_id TEXT,
                venue TEXT,
                market_id TEXT PRIMARY KEY,
                resolution_rules_json TEXT,
                resolution_key TEXT,
                confidence DOUBLE,
                linked_ts DOUBLE
            )
            """
        )
        self.store._execute(
            """
            CREATE TABLE IF NOT EXISTS event_relations (
                source_event_id TEXT,
                target_event_id TEXT,
                relation_type TEXT,
                confidence DOUBLE,
                metadata_json TEXT,
                PRIMARY KEY (source_event_id, target_event_id, relation_type)
            )
            """
        )

    @staticmethod
    def validate_resolution_rules(resolution_rules: dict[str, Any]) -> None:
        missing = REQUIRED_RESOLUTION_FIELDS - set(resolution_rules)
        if missing:
            raise ValueError(
                "resolution_rules missing required fields: " + ", ".join(sorted(missing))
            )

    def upsert_event(self, event_spec: EventSpec) -> str:
        self.validate_resolution_rules(event_spec.resolution_rules)
        self.store._execute(
            """
            INSERT OR REPLACE INTO canonical_events
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_spec.event_id,
                event_spec.title,
                event_spec.category,
                json.dumps(event_spec.resolution_rules, sort_keys=True, default=str),
                _rules_key(event_spec.resolution_rules),
                float(event_spec.created_ts),
                json.dumps(event_spec.metadata, sort_keys=True, default=str),
            ),
        )
        return event_spec.event_id

    def link_market(
        self,
        event_id: str,
        venue: str,
        market_id: str,
        resolution_rules: dict[str, Any],
        confidence: float,
    ) -> MarketLink:
        self.validate_resolution_rules(resolution_rules)
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        row = self.store._fetchone(
            "SELECT resolution_key FROM canonical_events WHERE event_id = ?",
            (event_id,),
        )
        if row and row[0] != _rules_key(resolution_rules):
            raise ValueError(f"market {market_id} rules do not match canonical event {event_id}")
        link = MarketLink(
            event_id=event_id,
            venue=venue,
            market_id=market_id,
            resolution_rules=resolution_rules,
            confidence=float(confidence),
        )
        self.store._execute(
            """
            INSERT OR REPLACE INTO event_market_links
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link.event_id,
                link.venue,
                link.market_id,
                json.dumps(link.resolution_rules, sort_keys=True, default=str),
                _rules_key(link.resolution_rules),
                link.confidence,
                link.linked_ts,
            ),
        )
        return link

    def add_relation(
        self,
        source_event_id: str,
        target_event_id: str,
        relation_type: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.store._execute(
            "INSERT OR REPLACE INTO event_relations VALUES (?, ?, ?, ?, ?)",
            (
                source_event_id,
                target_event_id,
                relation_type,
                float(confidence),
                json.dumps(metadata or {}, sort_keys=True, default=str),
            ),
        )

    def get_equivalent_markets(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.store._fetchall(
            """
            SELECT venue, market_id, confidence, resolution_rules_json
            FROM event_market_links
            WHERE event_id = ? AND confidence >= ?
            ORDER BY confidence DESC
            """,
            (event_id, self.min_equivalence_confidence),
        )
        return [
            {
                "event_id": event_id,
                "venue": row[0],
                "market_id": row[1],
                "confidence": float(row[2]),
                "resolution_rules": json.loads(row[3]),
            }
            for row in rows
        ]

    def get_related_events(self, event_id: str, relation_type: str) -> list[dict[str, Any]]:
        rows = self.store._fetchall(
            """
            SELECT target_event_id, confidence, metadata_json
            FROM event_relations
            WHERE source_event_id = ? AND relation_type = ?
            ORDER BY confidence DESC
            """,
            (event_id, relation_type),
        )
        return [
            {
                "event_id": row[0],
                "relation_type": relation_type,
                "confidence": float(row[1]),
                "metadata": json.loads(row[2] or "{}"),
            }
            for row in rows
        ]

    def markets_are_equivalent(self, market_a: str, market_b: str) -> bool:
        rows = self.store._fetchall(
            """
            SELECT event_id, resolution_key, confidence
            FROM event_market_links
            WHERE market_id IN (?, ?)
            """,
            (market_a, market_b),
        )
        if len(rows) != 2:
            return False
        return (
            rows[0][0] == rows[1][0]
            and rows[0][1] == rows[1][1]
            and float(rows[0][2]) >= self.min_equivalence_confidence
            and float(rows[1][2]) >= self.min_equivalence_confidence
        )
