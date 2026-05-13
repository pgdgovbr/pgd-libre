"""rf_delegacao_competencia — Sprint 2.8 RF-037

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-05-13 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    competencia = sa.Enum(
        "APROVAR_PLANO_ENTREGAS",
        "REALIZAR_SELECAO",
        "AVALIAR_REGISTROS",
        name="competencia",
    )
    competencia.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "delegacoes_competencia",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delegante_user_id", sa.Integer(), nullable=False),
        sa.Column("delegatario_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "competencia",
            sa.Enum(
                "APROVAR_PLANO_ENTREGAS",
                "REALIZAR_SELECAO",
                "AVALIAR_REGISTROS",
                name="competencia",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "unidade_execucao_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "ativo",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["delegante_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["delegatario_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["unidade_execucao_id"], ["unidades_execucao.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("delegacoes_competencia")
    sa.Enum(name="competencia").drop(op.get_bind(), checkfirst=True)
