"""rf_adicional_noturno — Sprint 2.7 TC-M10-005/006

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-13 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "autorizacoes_adicional_noturno",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participante_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_inicio_autorizacao", sa.Date(), nullable=False),
        sa.Column("data_fim_autorizacao", sa.Date(), nullable=True),
        sa.Column("horario_inicio_noturno", sa.Time(), nullable=False),
        sa.Column("horario_fim_noturno", sa.Time(), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("autorizado_por_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["participante_id"], ["participantes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["autorizado_por_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "planos_trabalho",
        sa.Column(
            "trabalho_noturno",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("planos_trabalho", "trabalho_noturno")
    op.drop_table("autorizacoes_adicional_noturno")
