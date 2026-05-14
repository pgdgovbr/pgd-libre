import uuid
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.institucional import UnidadeExecucao
from ..models.notificacao import TipoEvento
from ..models.plano import (
    STATUS_PE_APROVADO,
    STATUS_PE_AVALIADO,
    STATUS_PE_CANCELADO,
    STATUS_PE_CONCLUIDO,
    STATUS_PE_EM_EXECUCAO,
    Entrega,
    PlanoEntregas,
    TipoMeta,
)
from ..models.user import User
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao

# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def validate_duracao_maxima_pe(data_inicio: date, data_termino: date) -> None:
    if data_termino > data_inicio + relativedelta(years=1):
        raise ValidationError(
            "Plano de Entregas não pode ter duração superior a 1 ano (IN24 Art.18 I)"
        )
    if data_termino < data_inicio:
        raise ValidationError("data_termino deve ser >= data_inicio")


# ---------------------------------------------------------------------------
# DB validators
# ---------------------------------------------------------------------------


async def validate_sem_sobreposicao_pe(
    db: AsyncSession,
    unidade_execucao_id: uuid.UUID,
    data_inicio: date,
    data_termino: date,
    exclude_id: uuid.UUID | None = None,
) -> None:
    q = select(PlanoEntregas).where(
        PlanoEntregas.unidade_execucao_id == unidade_execucao_id,
        PlanoEntregas.status != STATUS_PE_CANCELADO,
        PlanoEntregas.data_inicio <= data_termino,
        PlanoEntregas.data_termino >= data_inicio,
    )
    if exclude_id:
        q = q.where(PlanoEntregas.id != exclude_id)
    result = await db.execute(q)
    if result.scalar_one_or_none() is not None:
        raise ValidationError("Já existe Plano de Entregas no período informado para esta unidade")


# ---------------------------------------------------------------------------
# CRUD — PlanoEntregas
# ---------------------------------------------------------------------------


async def criar_plano_entregas(
    db: AsyncSession,
    *,
    id_plano_entregas: str,
    origem_unidade,
    cod_unidade_autorizadora: int,
    cod_unidade_instituidora: int,
    cod_unidade_executora: int,
    unidade_execucao_id: uuid.UUID,
    data_inicio: date,
    data_termino: date,
    user: User | None = None,
    ip_address: str | None = None,
) -> PlanoEntregas:
    validate_duracao_maxima_pe(data_inicio, data_termino)
    await validate_sem_sobreposicao_pe(db, unidade_execucao_id, data_inicio, data_termino)

    pe = PlanoEntregas(
        id_plano_entregas=id_plano_entregas,
        origem_unidade=origem_unidade,
        cod_unidade_autorizadora=cod_unidade_autorizadora,
        cod_unidade_instituidora=cod_unidade_instituidora,
        cod_unidade_executora=cod_unidade_executora,
        unidade_execucao_id=unidade_execucao_id,
        status=STATUS_PE_APROVADO,
        data_inicio=data_inicio,
        data_termino=data_termino,
    )
    db.add(pe)
    await db.flush()
    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "id_plano_entregas": id_plano_entregas,
            "status": STATUS_PE_APROVADO,
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pe)
    return pe


async def aprovar_plano_entregas(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    aprovador_user_id: int,
    user: User,
    ip_address: str | None = None,
) -> PlanoEntregas:
    from ..models.institucional import Competencia
    from ..models.user import UserRole
    from .institucional import has_delegated_permission

    pe = await get_plano_entregas(db, plano_id)
    if pe is None:
        raise ValidationError("PlanoEntregas não encontrado")

    ue_result = await db.execute(
        select(UnidadeExecucao).where(UnidadeExecucao.id == pe.unidade_execucao_id)
    )
    ue = ue_result.scalar_one_or_none()

    if ue and ue.coincide_com_instituidora:
        raise ValidationError(
            "Plano de unidade instituidora dispensa aprovação hierárquica superior"
            " (IN24 Art.18 §1º)"
        )

    if ue and ue.chefia_user_id == aprovador_user_id:
        raise ValidationError("A chefia criadora não pode aprovar o próprio plano de entregas")

    # RF-037 — autorização: ADMIN/GESTOR podem direto; CHEFE_IMEDIATO requer delegação ativa
    if user.role not in (UserRole.ADMIN, UserRole.GESTOR_UNIDADE):
        has_deleg = await has_delegated_permission(
            db,
            user_id=user.id,
            competencia=Competencia.APROVAR_PLANO_ENTREGAS,
            unidade_execucao_id=pe.unidade_execucao_id,
        )
        if not has_deleg:
            raise ValidationError(
                "Sem permissão para aprovar plano de entregas — delegação"
                " de competência não localizada (RF-037)"
            )

    pe.aprovado_por_user_id = aprovador_user_id
    pe.data_aprovacao = date.today()

    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"aprovado_por_user_id": None},
        new_values={
            "aprovado_por_user_id": aprovador_user_id,
            "data_aprovacao": str(date.today()),
        },
        ip_address=ip_address,
    )

    if ue and ue.chefia_user_id:
        await criar_notificacao(
            db,
            tipo_evento=TipoEvento.PLANO_APROVADO,
            conteudo="Seu plano de entregas foi aprovado pelo nível hierárquico superior.",
            destinatario_user_id=ue.chefia_user_id,
            contexto={"plano_id": str(plano_id)},
        )

    await db.commit()
    await db.refresh(pe)
    return pe


async def get_plano_entregas(db: AsyncSession, pe_id: uuid.UUID) -> PlanoEntregas | None:
    result = await db.execute(select(PlanoEntregas).where(PlanoEntregas.id == pe_id))
    return result.scalar_one_or_none()


async def iniciar_execucao_pe(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoEntregas:
    pe = await get_plano_entregas(db, plano_id)
    if pe is None:
        raise ValidationError("PlanoEntregas não encontrado")
    if pe.status != STATUS_PE_APROVADO:
        raise ValidationError("Plano de Entregas deve estar Aprovado para iniciar execução")
    old = pe.status
    pe.status = STATUS_PE_EM_EXECUCAO
    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PE_EM_EXECUCAO},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pe)
    return pe


async def concluir_pe(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoEntregas:
    pe = await get_plano_entregas(db, plano_id)
    if pe is None:
        raise ValidationError("PlanoEntregas não encontrado")
    if pe.status != STATUS_PE_EM_EXECUCAO:
        raise ValidationError("Plano de Entregas deve estar Em Execução para concluir")
    old = pe.status
    pe.status = STATUS_PE_CONCLUIDO
    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PE_CONCLUIDO},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pe)
    return pe


async def avaliar_pe(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    avaliacao: int,
    data_avaliacao: date,
    user: User,
    ip_address: str | None = None,
) -> PlanoEntregas:
    if avaliacao not in range(1, 6):
        raise ValidationError("Avaliação deve ser entre 1 e 5")

    pe = await get_plano_entregas(db, plano_id)
    if pe is None:
        raise ValidationError("PlanoEntregas não encontrado")
    if pe.status != STATUS_PE_CONCLUIDO:
        raise ValidationError("Plano de Entregas deve estar Concluído para avaliar")

    limite = pe.data_termino + relativedelta(days=30)
    if data_avaliacao > limite:
        raise ValidationError(
            "Avaliação do Plano de Entregas deve ser feita em até 30 dias após o término"
            " (IN24 Art.22 §1º)"
        )

    old = pe.status
    pe.status = STATUS_PE_AVALIADO
    pe.avaliacao = avaliacao
    pe.data_avaliacao = data_avaliacao
    pe.avaliado_por_user_id = user.id

    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PE_AVALIADO, "avaliacao": avaliacao},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pe)
    return pe


async def cancelar_pe(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoEntregas:
    pe = await get_plano_entregas(db, plano_id)
    if pe is None:
        raise ValidationError("PlanoEntregas não encontrado")
    if pe.status in (STATUS_PE_AVALIADO,):
        raise ValidationError("Plano avaliado não pode ser cancelado")
    old = pe.status
    pe.status = STATUS_PE_CANCELADO
    await log_audit(
        db,
        table_name="planos_entregas",
        record_id=str(pe.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old},
        new_values={"status": STATUS_PE_CANCELADO},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pe)
    return pe


# ---------------------------------------------------------------------------
# CRUD — Entrega
# ---------------------------------------------------------------------------


async def criar_entrega(
    db: AsyncSession,
    *,
    id_entrega: str,
    plano_entregas_id: uuid.UUID,
    nome_entrega: str,
    meta_entrega: int,
    tipo_meta: TipoMeta,
    data_entrega: date,
    nome_unidade_demandante: str,
    nome_unidade_destinataria: str,
    user: User | None = None,
    ip_address: str | None = None,
) -> Entrega:
    e = Entrega(
        id_entrega=id_entrega,
        plano_entregas_id=plano_entregas_id,
        nome_entrega=nome_entrega,
        meta_entrega=meta_entrega,
        tipo_meta=tipo_meta,
        data_entrega=data_entrega,
        nome_unidade_demandante=nome_unidade_demandante,
        nome_unidade_destinataria=nome_unidade_destinataria,
    )
    db.add(e)
    await db.flush()
    await log_audit(
        db,
        table_name="entregas",
        record_id=str(e.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"id_entrega": id_entrega, "nome_entrega": nome_entrega},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(e)
    return e
