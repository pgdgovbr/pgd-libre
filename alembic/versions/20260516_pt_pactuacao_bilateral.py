"""PT pactuacao bilateral: assinaturas, criado_por_role, clonado_de_id

Adiciona campos para suportar pactuação bilateral do Plano de Trabalho:
- data_assinatura_participante, data_assinatura_chefia (DateTime nullable)
- criado_por_role (enum: participante|chefia)
- clonado_de_id (FK self-reference nullable)

Status novos (5, 6, 7) são inteiros — não exigem alteração de enum no DB
pois o campo `status` em planos_trabalho é Integer, não Enum.

Migração de dados:
- PTs em STATUS_PT_EM_EXECUCAO (3) ganham data_assinatura_X = data_inicio
- criado_por_role default = 'chefia' (compatível com workflow antigo)

Revision ID: pt_pactuacao_bilateral
Revises: 213398d03375
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pt_pactuacao_bilateral"
down_revision: str | None = "213398d03375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Cria enum criadoporrole
    criado_por_role_enum = sa.Enum(
        "participante",
        "chefia",
        name="criadoporrole",
    )
    criado_por_role_enum.create(op.get_bind(), checkfirst=True)

    # Adiciona novos valores ao enum tipoevento (deve ser fora de transação no Postgres)
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE tipoevento ADD VALUE IF NOT EXISTS 'PLANO_TRABALHO_RECEBIDO_PARA_ASSINATURA'"
        )
        op.execute(
            "ALTER TYPE tipoevento ADD VALUE IF NOT EXISTS 'PLANO_TRABALHO_DEVOLVIDO_PARA_AJUSTES'"
        )
        op.execute(
            "ALTER TYPE tipoevento ADD VALUE IF NOT EXISTS 'PLANO_TRABALHO_PACTUADO'"
        )

    # Adiciona colunas em planos_trabalho
    op.add_column(
        "planos_trabalho",
        sa.Column("data_assinatura_participante", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column("data_assinatura_chefia", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column(
            "criado_por_role",
            criado_por_role_enum,
            nullable=False,
            server_default="chefia",  # PTs existentes assumem origem chefia
        ),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column("clonado_de_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_planos_trabalho_clonado_de_id_planos_trabalho"),
        "planos_trabalho",
        "planos_trabalho",
        ["clonado_de_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill: PTs já EM_EXECUCAO ou CONCLUIDO recebem assinaturas retroativas
    # (data_inicio como valor mínimo plausível)
    op.execute(
        """
        UPDATE planos_trabalho
        SET data_assinatura_participante = data_inicio::timestamp,
            data_assinatura_chefia = data_inicio::timestamp
        WHERE status IN (3, 4)
          AND data_assinatura_participante IS NULL
        """
    )

    # Remove server_default — novos PTs definem criado_por_role explicitamente
    op.alter_column("planos_trabalho", "criado_por_role", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_planos_trabalho_clonado_de_id_planos_trabalho"),
        "planos_trabalho",
        type_="foreignkey",
    )
    op.drop_column("planos_trabalho", "clonado_de_id")
    op.drop_column("planos_trabalho", "criado_por_role")
    op.drop_column("planos_trabalho", "data_assinatura_chefia")
    op.drop_column("planos_trabalho", "data_assinatura_participante")
    sa.Enum(name="criadoporrole").drop(op.get_bind(), checkfirst=True)
