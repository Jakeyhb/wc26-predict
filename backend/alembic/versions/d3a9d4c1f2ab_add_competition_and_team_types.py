"""add competition and team types

Revision ID: d3a9d4c1f2ab
Revises: b8b7d1a21f6b
Create Date: 2026-04-21 23:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3a9d4c1f2ab"
down_revision: Union[str, Sequence[str], None] = "b8b7d1a21f6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "competition_type",
                sa.String(length=20),
                nullable=False,
                server_default="national",
            )
        )

    with op.batch_alter_table("teams") as batch_op:
        batch_op.add_column(
            sa.Column(
                "team_type",
                sa.String(length=20),
                nullable=False,
                server_default="national",
            )
        )
        batch_op.add_column(sa.Column("country", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("teams") as batch_op:
        batch_op.drop_column("country")
        batch_op.drop_column("team_type")

    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_column("competition_type")
