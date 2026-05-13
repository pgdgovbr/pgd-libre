"""RF-028 — Relatórios de Conformidade."""
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.participante import Afastamento, Participante
from ..models.plano import (
    STATUS_PE_CONCLUIDO,
    STATUS_PT_CANCELADO,
    STATUS_PT_EM_EXECUCAO,
    STATUS_PT_CONCLUIDO,
    AvaliacaoRegistrosExecucao,
    PlanoEntregas,
    PlanoTrabalho,
)


async def relatorio_sem_plano_trabalho(
    db: AsyncSession,
    cod_unidade_autorizadora: int | None = None,
) -> list[Participante]:
    """Participantes ativos sem plano de trabalho em status 3 ou 4."""
    subq = (
        select(PlanoTrabalho.participante_id)
        .where(PlanoTrabalho.status.in_([STATUS_PT_EM_EXECUCAO, STATUS_PT_CONCLUIDO]))
        .scalar_subquery()
    )
    q = select(Participante).where(
        Participante.situacao == 1,
        Participante.id.not_in(subq),
    )
    if cod_unidade_autorizadora is not None:
        q = q.where(Participante.cod_unidade_autorizadora == cod_unidade_autorizadora)
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_registros_atraso(
    db: AsyncSession,
    referencia: date,
    cod_unidade_autorizadora: int | None = None,
) -> list[AvaliacaoRegistrosExecucao]:
    """Períodos avaliativos com prazo de registro vencido sem registro do participante."""
    q = (
        select(AvaliacaoRegistrosExecucao)
        .join(
            PlanoTrabalho,
            AvaliacaoRegistrosExecucao.plano_trabalho_id == PlanoTrabalho.id,
        )
        .where(
            AvaliacaoRegistrosExecucao.data_registro_participante.is_(None),
            AvaliacaoRegistrosExecucao.data_fim_periodo_avaliativo + 10 < referencia,
            PlanoTrabalho.status != STATUS_PT_CANCELADO,
        )
    )
    if cod_unidade_autorizadora is not None:
        q = q.where(
            PlanoTrabalho.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_avaliacoes_pendentes(
    db: AsyncSession,
    referencia: date,
    cod_unidade_autorizadora: int | None = None,
) -> list[AvaliacaoRegistrosExecucao]:
    """Períodos onde o participante registrou mas a chefia ainda não avaliou e prazo venceu."""
    q = (
        select(AvaliacaoRegistrosExecucao)
        .join(
            PlanoTrabalho,
            AvaliacaoRegistrosExecucao.plano_trabalho_id == PlanoTrabalho.id,
        )
        .where(
            AvaliacaoRegistrosExecucao.data_registro_participante.isnot(None),
            AvaliacaoRegistrosExecucao.avaliacao_registros_execucao.is_(None),
            AvaliacaoRegistrosExecucao.data_fim_periodo_avaliativo + 20 < referencia,
            PlanoTrabalho.status != STATUS_PT_CANCELADO,
        )
    )
    if cod_unidade_autorizadora is not None:
        q = q.where(
            PlanoTrabalho.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_pe_avaliacao_pendente(
    db: AsyncSession,
    referencia: date,
    cod_unidade_autorizadora: int | None = None,
) -> list[PlanoEntregas]:
    """Planos de entregas concluídos há mais de 30 dias sem avaliação registrada."""
    q = select(PlanoEntregas).where(
        PlanoEntregas.status == STATUS_PE_CONCLUIDO,
        PlanoEntregas.avaliacao.is_(None),
        PlanoEntregas.data_termino + timedelta(days=30) < referencia,
    )
    if cod_unidade_autorizadora is not None:
        q = q.where(
            PlanoEntregas.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_frequencia(
    db: AsyncSession,
    cod_unidade_autorizadora: int,
    ano: int,
    mes: int,
) -> list[Participante]:
    """Participantes ativos com plano de trabalho cobrindo o período ano/mes."""
    from calendar import monthrange
    ultimo_dia = monthrange(ano, mes)[1]
    inicio_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, ultimo_dia)

    subq = (
        select(PlanoTrabalho.participante_id)
        .where(
            PlanoTrabalho.status.in_([STATUS_PT_EM_EXECUCAO, STATUS_PT_CONCLUIDO]),
            PlanoTrabalho.data_inicio <= fim_mes,
            PlanoTrabalho.data_termino >= inicio_mes,
        )
        .scalar_subquery()
    )
    q = select(Participante).where(
        Participante.situacao == 1,
        Participante.cod_unidade_autorizadora == cod_unidade_autorizadora,
        Participante.id.in_(subq),
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_afastamentos(
    db: AsyncSession,
    cod_unidade_autorizadora: int,
    ano: int,
    mes: int,
) -> list[Afastamento]:
    """Afastamentos legais que cobrem o mês ano/mes da unidade autorizadora.

    Um afastamento "cobre" o mês quando:
      - data_inicio <= fim_mes
      - data_fim >= inicio_mes (ou data_fim is NULL: afastamento em curso)
    """
    from calendar import monthrange
    ultimo_dia = monthrange(ano, mes)[1]
    inicio_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, ultimo_dia)

    q = (
        select(Afastamento)
        .join(Participante, Afastamento.participante_id == Participante.id)
        .where(
            Participante.cod_unidade_autorizadora == cod_unidade_autorizadora,
            Afastamento.data_inicio <= fim_mes,
            or_(
                Afastamento.data_fim.is_(None),
                Afastamento.data_fim >= inicio_mes,
            ),
        )
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def relatorio_nao_enviados(
    db: AsyncSession,
    cod_unidade_autorizadora: int | None = None,
) -> dict[str, list]:
    """Participantes e planos com api_sincronizado_em nulo."""
    q_p = select(Participante).where(
        Participante.situacao == 1,
        Participante.api_sincronizado_em.is_(None),
    )
    if cod_unidade_autorizadora is not None:
        q_p = q_p.where(
            Participante.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    participantes = list((await db.execute(q_p)).scalars().all())

    from ..models.plano import STATUS_PE_EM_EXECUCAO, STATUS_PE_AVALIADO

    q_pe = select(PlanoEntregas).where(
        PlanoEntregas.status.in_([STATUS_PE_EM_EXECUCAO, STATUS_PE_CONCLUIDO, STATUS_PE_AVALIADO]),
        PlanoEntregas.api_sincronizado_em.is_(None),
    )
    if cod_unidade_autorizadora is not None:
        q_pe = q_pe.where(
            PlanoEntregas.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    planos_entregas = list((await db.execute(q_pe)).scalars().all())

    q_pt = select(PlanoTrabalho).where(
        PlanoTrabalho.status.in_([STATUS_PT_EM_EXECUCAO, STATUS_PT_CONCLUIDO]),
        PlanoTrabalho.api_sincronizado_em.is_(None),
    )
    if cod_unidade_autorizadora is not None:
        q_pt = q_pt.where(
            PlanoTrabalho.cod_unidade_autorizadora == cod_unidade_autorizadora
        )
    planos_trabalho = list((await db.execute(q_pt)).scalars().all())

    return {
        "participantes": participantes,
        "planos_entregas": planos_entregas,
        "planos_trabalho": planos_trabalho,
    }
