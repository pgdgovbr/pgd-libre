"""add_registros_envio_api

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-05-13 18:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE tipoentidadesync AS ENUM "
        "('participante', 'plano_entregas', 'plano_trabalho')"
    )
    op.create_table(
        "registros_envio_api",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tipo_entidade",
            sa.Enum("participante", "plano_entregas", "plano_trabalho", name="tipoentidadesync", create_type=False),
            nullable=False,
        ),
        sa.Column("entidade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tentativa", sa.Integer(), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("erro_mensagem", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_registros_envio_api_entidade_id",
        "registros_envio_api",
        ["entidade_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_registros_envio_api_entidade_id", table_name="registros_envio_api")
    op.drop_table("registros_envio_api")
    op.execute("DROP TYPE tipoentidadesync")
