"""add_feedback_table

Revision ID: 6fd1704b7a1b
Revises: 2cd562a353a5
Create Date: 2026-04-21 13:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6fd1704b7a1b"
down_revision: Union[str, Sequence[str], None] = "2cd562a353a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("match_id", sa.Uuid(), nullable=True),
        sa.Column("article_id", sa.Uuid(), nullable=True),
        sa.Column("feedback_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["content_articles.id"], name=op.f("fk_feedback_article_id_content_articles"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name=op.f("fk_feedback_match_id_matches"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )


def downgrade() -> None:
    op.drop_table("feedback")
