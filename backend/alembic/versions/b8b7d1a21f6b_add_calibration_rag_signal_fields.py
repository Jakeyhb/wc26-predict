"""add_calibration_rag_signal_fields

Revision ID: b8b7d1a21f6b
Revises: 6fd1704b7a1b
Create Date: 2026-04-21 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8b7d1a21f6b"
down_revision: Union[str, Sequence[str], None] = "6fd1704b7a1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("news_signals") as batch_op:
        batch_op.add_column(sa.Column("player_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("claim", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("evidence_snippet", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("normalized_availability", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("expected_minutes_delta", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("conflict_group_id", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("contradiction_risk", sa.String(length=10), nullable=True))

    op.create_index(
        op.f("ix_news_signals_conflict_group_id"),
        "news_signals",
        ["conflict_group_id"],
        unique=False,
    )

    with op.batch_alter_table("news_articles") as batch_op:
        batch_op.add_column(sa.Column("embedding_model", sa.String(length=100), nullable=True))

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        op.execute("ALTER TABLE news_articles ADD COLUMN embedding vector(1536)")
    else:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.add_column(sa.Column("embedding", sa.JSON(), nullable=True))

    op.create_table(
        "article_evidence",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("prediction_run_id", sa.Uuid(), nullable=True),
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_snippet", sa.Text(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("used_in_article", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"], name=op.f("fk_article_evidence_article_id_news_articles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name=op.f("fk_article_evidence_match_id_matches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["prediction_runs.id"], name=op.f("fk_article_evidence_prediction_run_id_prediction_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signal_id"], ["news_signals.id"], name=op.f("fk_article_evidence_signal_id_news_signals"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article_evidence")),
    )
    op.create_index(op.f("ix_article_evidence_match_created"), "article_evidence", ["match_id", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index(op.f("ix_article_evidence_match_created"), table_name="article_evidence")
    op.drop_table("article_evidence")

    if dialect == "postgresql":
        op.execute("ALTER TABLE news_articles DROP COLUMN embedding")
    else:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.drop_column("embedding")

    with op.batch_alter_table("news_articles") as batch_op:
        batch_op.drop_column("embedding_model")

    op.drop_index(op.f("ix_news_signals_conflict_group_id"), table_name="news_signals")
    with op.batch_alter_table("news_signals") as batch_op:
        batch_op.drop_column("contradiction_risk")
        batch_op.drop_column("conflict_group_id")
        batch_op.drop_column("effective_until")
        batch_op.drop_column("expected_minutes_delta")
        batch_op.drop_column("normalized_availability")
        batch_op.drop_column("evidence_snippet")
        batch_op.drop_column("claim")
        batch_op.drop_column("player_name")
