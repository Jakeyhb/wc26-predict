"""Add match_result_verification table and learning_log status column.

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7d8c9b0
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e5f6a7d8c9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create match_result_verification table
    op.create_table(
        "match_result_verification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "match_id",
            sa.Uuid(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("source_tier", sa.Integer(), nullable=False),
        sa.Column("match_status_at_source", sa.String(20), nullable=False),
        sa.Column(
            "is_consensus",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "consensus_for_id",
            sa.Uuid(),
            sa.ForeignKey("match_result_verification.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_result_verification_match_id",
        "match_result_verification",
        ["match_id"],
    )

    # 2. Add status column to prediction_learning_log (batch mode for SQLite)
    with op.batch_alter_table("prediction_learning_log") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="active",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("prediction_learning_log") as batch_op:
        batch_op.drop_column("status")
    op.drop_index(
        "ix_match_result_verification_match_id",
        table_name="match_result_verification",
    )
    op.drop_table("match_result_verification")
