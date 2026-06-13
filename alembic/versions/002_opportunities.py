"""add opportunities table

Revision ID: 002
Revises: 001
Create Date: 2026-06-11

This migration creates the opportunities table, allowing the background platform loop
to persist live forecasting and market metrics.
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            contract_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            venue TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            model_prob REAL NOT NULL,
            market_implied REAL NOT NULL,
            edge REAL NOT NULL,
            status TEXT NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS opportunities")
