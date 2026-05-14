import uuid
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.institucional import OrigemUnidade
from ..models.notificacao import TipoEvento
from ..models.participante import TCR, Participante, StatusTCR
from ..models.plano import (
    STATUS_PT_APROVADO,
    STATUS_PT_CANCELADO,
    STATUS_PT_CONCLUIDO,
    STATUS_PT_EM_EXECUCAO,
    AvaliacaoRegistrosExecucao,
    Contribuicao,
    PlanoEntregas,
    PlanoTrabalho,
)
from ..models.user import User
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao

MIN_DATA_INICIO_PT = date(2023, 7, 31)


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def validate_duracao_maxima_pt(data_inicio: date, data_termino: date) -> None:
    if data_termino > data_inicio + relativedelta(years=1):
        raise ValidationError("Plano de Trabalho não pode ter duração superior a 1 ano")
    if data_termino < data_inicio:
        raise ValidationError("data_termino deve ser >= data_inicio")


def validate_tipo_contribuicao(
    tipo: int,
    id_plano_entregas: str | None,
    id_entrega: str | None,
) -> None:
    if tipo == 1:
        if not id_plano_entregas or not id_entrega:
            raise ValidationError("Contribuição tipo 1 exige id_plano_entregas e id_entrega")
    elif tipo == 2:
        if id_plano_entregas or id_entrega:
            raise ValidationError(
                "Contribuição tipo 2 não pode ter id_plano_entregas nem id_entrega"
            )


def validate_soma_percentuais(
    percentuais: list[int],
    carga_horaria_compensacao: int = 0,
    saldo_banco_horas: int = 0,
) -> None:
    total = sum(percentuais)
    if total > 100 and carga_horaria_compensacao > 0:
        return  # compensação permite soma > 100
    if total < 100 and saldo_banco_horas > 0:
        return  # usufruto de saldo permite soma < 100
    if total != 100:
        raise ValidationError(
            f"Soma dos percentuais das contribuições deve ser 100% (atual: {total}%)"
        )


def validate_adicional_ocupacional_periodicidade(
    sujeito_adicional_ocupacional: bool,
    modalidade_execucao: int,
    data_inicio: date,
    data_termino: date,
) -> None:
    if not sujeito_adicional_ocupacional:
        return
    if modalidade_execucao not in (1, 2):
        return
    duracao = (data_termino - data_inicio).days
    if duracao > 31:
        raise ValidationError(
            "Participante sujeito a adicional ocupacional requer plano de trabalho"
            " com periodicidade mensal (IN52 Art.8º §2º)"
        )


# ---------------------------------------------------------------------------
# DB validators
# ---------------------------------------------------------------------------


async def _get_tcr_ativo(db: AsyncSession, participante_id: uuid.UUID) -> TCR:
    result = await db.execute(
        select(TCR).where(
            TCR.participante_id == participante_id,
            TCR.status == StatusTCR.ATIVO,
        )
    )
    tcr = result.scalar_one_or_none()
    if tcr is None:
        raise ValidationError("TCR ativo obrigatório para criação de plano de trabalho")
    return tcr


async def validate_data_inicio_pt_ge_pe(
    db: AsyncSession,
    data_inicio_pt: date,
    plano_entregas_id: uuid.UUID | None,
) -> None:
    if plano_entregas_id is None:
        return
    result = await db.execute(select(PlanoEntregas).where(PlanoEntregas.id == plano_entregas_id))
    pe = result.scalar_one_or_none()
    if pe and data_inicio_pt < pe.data_inicio:
        raise ValidationError(
            "data_inicio do Plano de Trabalho deve ser >= data_inicio do Plano de"
            " Entregas referenciado"
        )


async def validate_sem_sobreposicao_pt(
    db: AsyncSession,
    participante_id: uuid.UUID,
    data_inicio: date,
    data_termino: date,
    exclude_id: uuid.UUID | None = None,
) -> None:
    q = select(PlanoTrabalho).where(
        PlanoTrabalho.participante_id == participante_id,
        PlanoTrabalho.status != STATUS_PT_CANCELADO,
        PlanoTrabalho.data_inicio <= data_termino,
        PlanoTrabalho.data_termino >= data_inicio,
    )
    if exclude_id:
        q = q.where(PlanoTrabalho.id != exclude_id)
    result = await db.execute(q)
    if result.scalar_one_or_none() is not None:
        raise ValidationError("Participante já possui Plano de Trabalho no período informado")


# ---------------------------------------------------------------------------
# CRUD — PlanoTrabalho
# ---------------------------------------------------------------------------


async def criar_plano_trabalho(
    db: AsyncSession,
    *,
    id_plano_trabalho: str,
    origem_unidade: OrigemUnidade,
    cod_unidade_autorizadora: int,
    cod_unidade_executora: int,
    cod_unidade_lotacao_participante: int,
    participante_id: uuid.UUID,
    cpf_participante: str,
    matricula_siape: str,
    data_inicio: date,
    data_termino: date,
    carga_horaria_disponivel: int,
    criterios_avaliacao: str,
    plano_entregas_id: uuid.UUID | None = None,
    tcr_id: uuid.UUID | None = None,
    declaracao_ausencia_prejuizo_plano: bool = False,
    declaracao_ausencia_prejuizo_comparecer: bool = False,
    declaracao_ausencia_prejuizo_contato: bool = False,
    declaracao_ausencia_prejuizo_sincrono: bool = False,
    trabalho_noturno: bool = False,
    user: User | None = None,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    from .participante import validate_adicional_noturno_autorizado

    validate_duracao_maxima_pt(data_inicio, data_termino)
    if tcr_id is None:
        tcr = await _get_tcr_ativo(db, participante_id)
        tcr_id = tcr.id
    await validate_data_inicio_pt_ge_pe(db, data_inicio, plano_entregas_id)
    await validate_sem_sobreposicao_pt(db, participante_id, data_inicio, data_termino)
    await validate_adicional_noturno_autorizado(
        db,
        participante_id=participante_id,
        trabalho_noturno=trabalho_noturno,
        data_inicio_pt=data_inicio,
        data_termino_pt=data_termino,
    )

    pt = PlanoTrabalho(
        id_plano_trabalho=id_plano_trabalho,
        origem_unidade=origem_unidade,
        cod_unidade_autorizadora=cod_unidade_autorizadora,
        cod_unidade_executora=cod_unidade_executora,
        cod_unidade_lotacao_participante=cod_unidade_lotacao_participante,
        participante_id=participante_id,
        cpf_participante=cpf_participante,
        matricula_siape=matricula_siape,
        tcr_id=tcr_id,
        status=STATUS_PT_APROVADO,
        data_inicio=data_inicio,
        data_termino=data_termino,
        carga_horaria_disponivel=carga_horaria_disponivel,
        criterios_avaliacao=criterios_avaliacao,
        plano_entregas_id=plano_entregas_id,
        declaracao_ausencia_prejuizo_plano=declaracao_ausencia_prejuizo_plano,
        declaracao_ausencia_prejuizo_comparecer=declaracao_ausencia_prejuizo_comparecer,
        declaracao_ausencia_prejuizo_contato=declaracao_ausencia_prejuizo_contato,
        declaracao_ausencia_prejuizo_sincrono=declaracao_ausencia_prejuizo_sincrono,
        trabalho_noturno=trabalho_noturno,
    )
    db.add(pt)
    await db.flush()
    email_res = await db.execute(
        select(Participante.email).where(Participante.id == participante_id)
    )
    p_email = email_res.scalar_one_or_none()
    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "id_plano_trabalho": id_plano_trabalho,
            "status": STATUS_PT_APROVADO,
        },
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PLANO_APROVADO,
        conteudo=f"Seu plano de trabalho {id_plano_trabalho} foi aprovado.",
        destinatario_email=p_email,
        contexto={"id_plano_trabalho": id_plano_trabalho},
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def get_plano_trabalho(db: AsyncSession, pt_id: uuid.UUID) -> PlanoTrabalho | None:
    result = await db.execute(select(PlanoTrabalho).where(PlanoTrabalho.id == pt_id))
    return result.scalar_one_or_none()


async def iniciar_execucao_pt(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    pt = await get_plano_trabalho(db, plano_id)
    if pt is None:
        raise ValidationError("PlanoTrabalho não encontrado")
    if pt.status != STATUS_PT_APROVADO:
        raise ValidationError("Plano de Trabalho deve estar Aprovado para iniciar execução")
    old = pt.status
    pt.status = STATUS_PT_EM_EXECUCAO
    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PT_EM_EXECUCAO},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def cancelar_pt(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    pt = await get_plano_trabalho(db, plano_id)
    if pt is None:
        raise ValidationError("PlanoTrabalho não encontrado")
    if pt.status == STATUS_PT_CONCLUIDO:
        raise ValidationError("Plano concluído não pode ser cancelado")
    old = pt.status
    pt.status = STATUS_PT_CANCELADO
    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PT_CANCELADO},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


# ---------------------------------------------------------------------------
# CRUD — Contribuicao
# ---------------------------------------------------------------------------


async def adicionar_contribuicao(
    db: AsyncSession,
    *,
    id_contribuicao: str,
    plano_trabalho_id: uuid.UUID,
    tipo_contribuicao: int,
    percentual_contribuicao: int,
    descricao: str,
    id_plano_entregas: str | None = None,
    id_entrega: str | None = None,
    rotulo: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> Contribuicao:
    validate_tipo_contribuicao(tipo_contribuicao, id_plano_entregas, id_entrega)

    c = Contribuicao(
        id_contribuicao=id_contribuicao,
        plano_trabalho_id=plano_trabalho_id,
        tipo_contribuicao=tipo_contribuicao,
        percentual_contribuicao=percentual_contribuicao,
        id_plano_entregas=id_plano_entregas,
        id_entrega=id_entrega,
        descricao=descricao,
        rotulo=rotulo,
    )
    db.add(c)
    await db.flush()
    await log_audit(
        db,
        table_name="contribuicoes",
        record_id=str(c.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"tipo": tipo_contribuicao, "percentual": percentual_contribuicao},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(c)
    return c


# ---------------------------------------------------------------------------
# CRUD — AvaliacaoRegistrosExecucao (registro de execução)
# ---------------------------------------------------------------------------


async def registrar_execucao(
    db: AsyncSession,
    *,
    id_periodo_avaliativo: str,
    plano_trabalho_id: uuid.UUID,
    data_inicio_periodo_avaliativo: date,
    data_fim_periodo_avaliativo: date,
    descricao_execucao: str | None = None,
    ocorrencias: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> AvaliacaoRegistrosExecucao:
    from datetime import datetime as dt

    are = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo=id_periodo_avaliativo,
        plano_trabalho_id=plano_trabalho_id,
        data_inicio_periodo_avaliativo=data_inicio_periodo_avaliativo,
        data_fim_periodo_avaliativo=data_fim_periodo_avaliativo,
        descricao_execucao=descricao_execucao,
        ocorrencias=ocorrencias,
        data_registro_participante=dt.utcnow(),
    )
    db.add(are)
    await db.flush()
    await log_audit(
        db,
        table_name="avaliacoes_registros_execucao",
        record_id=str(are.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "plano_trabalho_id": str(plano_trabalho_id),
            "periodo": f"{data_inicio_periodo_avaliativo}..{data_fim_periodo_avaliativo}",
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(are)
    return are
