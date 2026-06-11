"""initial migration — audit_trail + equity_history tables

Revision ID: 001
Revises: None
Create Date: 2026-06-10

This migration creates the two core tables used by predmarket-alpha:
  - audit_trail: cryptographic hash-chained trade intent log
  - equity_history: portfolio equity time-series for drawdown calculations
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # audit_trail — immutable, append-only cryptographic audit log
    op.execute("""
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

    # equity_history — portfolio net equity time-series
    op.execute("""
        CREATE TABLE IF NOT EXISTS equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            total_equity REAL NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS equity_history")
    op.execute("DROP TABLE IF EXISTS audit_trail")
