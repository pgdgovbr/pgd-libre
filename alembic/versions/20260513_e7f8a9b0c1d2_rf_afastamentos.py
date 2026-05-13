"""rf_afastamentos — Sprint 2.6 TC-M10-008

Revision ID: e7f8a9b0c1d2
Revises: b1c2d3e4f5a6
Create Date: 2026-05-13 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tipo_afastamento = sa.Enum(
        "LICENCA_MEDICA",
        "LICENCA_MATERNIDADE",
        "FERIAS",
        "LICENCA_CAPACITACAO",
        "OUTROS",
        name="tipoafastamento",
    )
    tipo_afastamento.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "afastamentos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participante_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tipo_afastamento",
            sa.Enum(
                "LICENCA_MEDICA",
                "LICENCA_MATERNIDADE",
                "FERIAS",
                "LICENCA_CAPACITACAO",
                "OUTROS",
                name="tipoafastamento",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("registrado_por_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["participante_id"], ["participantes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registrado_por_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("afastamentos")
    sa.Enum(name="tipoafastamento").drop(op.get_bind(), checkfirst=True)
