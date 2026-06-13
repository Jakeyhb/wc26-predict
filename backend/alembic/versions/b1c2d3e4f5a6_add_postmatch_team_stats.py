"""add_postmatch_team_stats

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3, d3a9d4c1f2ab
Create Date: 2026-06-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = ("a8b9c0d1e2f3", "d3a9d4c1f2ab")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "postmatch_team_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("source_match_id", sa.String(64), nullable=False),
        sa.Column("source_time", sa.String(40), nullable=False),
        sa.Column("available_at", sa.String(40), nullable=False),
        sa.Column("captured_at", sa.String(40), nullable=False),
        sa.Column("home_xg", sa.Float(), nullable=True),
        sa.Column("away_xg", sa.Float(), nullable=True),
        sa.Column("home_shots", sa.Integer(), nullable=True),
        sa.Column("away_shots", sa.Integer(), nullable=True),
        sa.Column("home_shots_on_target", sa.Integer(), nullable=True),
        sa.Column("away_shots_on_target", sa.Integer(), nullable=True),
        sa.Column("home_yellow_cards", sa.Integer(), nullable=True),
        sa.Column("away_yellow_cards", sa.Integer(), nullable=True),
        sa.Column("home_red_cards", sa.Integer(), nullable=True),
        sa.Column("away_red_cards", sa.Integer(), nullable=True),
        sa.Column("home_corners", sa.Integer(), nullable=True),
        sa.Column("away_corners", sa.Integer(), nullable=True),
        sa.Column("home_possession", sa.Float(), nullable=True),
        sa.Column("away_possession", sa.Float(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "provider", "source_match_id", name="uq_postmatch_stats_source_match"),
    )
    op.create_index("ix_postmatch_stats_match", "postmatch_team_stats", ["match_id"])
    op.create_index("ix_postmatch_stats_provider", "postmatch_team_stats", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_postmatch_stats_provider", table_name="postmatch_team_stats")
    op.drop_index("ix_postmatch_stats_match", table_name="postmatch_team_stats")
    op.drop_table("postmatch_team_stats")
