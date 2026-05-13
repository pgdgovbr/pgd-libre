"""rf006_011_019_020_028_031_032_033_034_035

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-13 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RF-011 — aprovação hierárquica do plano de entregas
    op.add_column(
        "planos_entregas",
        sa.Column("aprovado_por_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "planos_entregas",
        sa.Column("data_aprovacao", sa.Date(), nullable=True),
    )

    # RF-019/020 — compensação e banco de horas (TCR)
    op.add_column(
        "tcrs",
        sa.Column("carga_horaria_compensacao", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tcrs",
        sa.Column("prazo_compensacao_inexecucao", sa.Date(), nullable=True),
    )
    op.add_column(
        "tcrs",
        sa.Column("saldo_banco_horas", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tcrs",
        sa.Column("prazo_compensacao_banco_horas", sa.Date(), nullable=True),
    )

    # RF-031 — escala customizada de avaliação
    op.add_column(
        "unidades_instituidoras",
        sa.Column("escala_customizada_mapeamento", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )

    # RF-032 — declaração de ausência de prejuízo (plano de trabalho)
    op.add_column(
        "planos_trabalho",
        sa.Column("declaracao_ausencia_prejuizo_plano", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column("declaracao_ausencia_prejuizo_comparecer", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column("declaracao_ausencia_prejuizo_contato", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "planos_trabalho",
        sa.Column("declaracao_ausencia_prejuizo_sincrono", sa.Boolean(), nullable=False, server_default="false"),
    )

    # RF-033 — acumulação de cargos (participante)
    op.add_column(
        "participantes",
        sa.Column("acumula_cargos", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "participantes",
        sa.Column("sujeito_adicional_ocupacional", sa.Boolean(), nullable=False, server_default="false"),
    )

    # RF-034 — rótulo de ação de desenvolvimento na contribuição
    op.add_column(
        "contribuicoes",
        sa.Column("rotulo", sa.String(50), nullable=True),
    )

    # RF-028 — horas de inexecução na avaliação
    op.add_column(
        "avaliacoes_registros_execucao",
        sa.Column("horas_inexecucao", sa.Integer(), nullable=True),
    )

    # RF-006 — seleção com critérios de prioridade
    op.create_table(
        "processos_selecao",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unidade_execucao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterios_tecnicos", sa.Text(), nullable=False),
        sa.Column("n_vagas", sa.Integer(), nullable=False),
        sa.Column("resultado", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("realizado_por_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["unidade_execucao_id"], ["unidades_execucao.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["realizado_por_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # RF-032 — retirada de equipamentos
    op.create_table(
        "termos_guarda_equipamento",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participante_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tcr_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("descricao_equipamentos", sa.Text(), nullable=False),
        sa.Column("data_autorizacao", sa.Date(), nullable=False),
        sa.Column("autorizado_por_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["participante_id"], ["participantes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tcr_id"], ["tcrs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["autorizado_por_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("termos_guarda_equipamento")
    op.drop_table("processos_selecao")
    op.drop_column("avaliacoes_registros_execucao", "horas_inexecucao")
    op.drop_column("contribuicoes", "rotulo")
    op.drop_column("participantes", "sujeito_adicional_ocupacional")
    op.drop_column("participantes", "acumula_cargos")
    op.drop_column("planos_trabalho", "declaracao_ausencia_prejuizo_sincrono")
    op.drop_column("planos_trabalho", "declaracao_ausencia_prejuizo_contato")
    op.drop_column("planos_trabalho", "declaracao_ausencia_prejuizo_comparecer")
    op.drop_column("planos_trabalho", "declaracao_ausencia_prejuizo_plano")
    op.drop_column("unidades_instituidoras", "escala_customizada_mapeamento")
    op.drop_column("tcrs", "prazo_compensacao_banco_horas")
    op.drop_column("tcrs", "saldo_banco_horas")
    op.drop_column("tcrs", "prazo_compensacao_inexecucao")
    op.drop_column("tcrs", "carga_horaria_compensacao")
    op.drop_column("planos_entregas", "data_aprovacao")
    op.drop_column("planos_entregas", "aprovado_por_user_id")
