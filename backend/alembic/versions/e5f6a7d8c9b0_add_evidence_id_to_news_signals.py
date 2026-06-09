"""Add evidence_id column to news_signals table.

Ticket 7: Every signal that enters the model must have an evidence_id.
This is a UUID that uniquely identifies the evidence chain backing the signal.

Revision ID: e5f6a7d8c9b0
Revises: c1e2f3a4b5c6
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7d8c9b0"
down_revision: Union[str, None] = "c1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_signals",
        sa.Column("evidence_id", sa.String(36), nullable=True, unique=True),
    )
    op.create_index(
        "ix_news_signals_evidence_id",
        "news_signals",
        ["evidence_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_news_signals_evidence_id", table_name="news_signals")
    op.drop_column("news_signals", "evidence_id")
