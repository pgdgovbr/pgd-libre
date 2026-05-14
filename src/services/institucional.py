import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.institucional import (
    AtoAutorizacao,
    Competencia,
    DelegacaoCompetencia,
    OrigemUnidade,
    StatusAto,
    StatusPgd,
    UnidadeAutorizadora,
    UnidadeExecucao,
    UnidadeInstituidora,
)
from ..models.user import User
from .audit import log_audit


class ValidationError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure validators (no I/O) — testáveis como unit tests
# ---------------------------------------------------------------------------


def validate_vagas_tt_exterior(val: int | None) -> None:
    if val is not None and val > 2:
        raise ValidationError(
            "Teletrabalho no exterior limitado a 2% do total de participantes"
            " em PGD (IN24 Art.12 §único)"
        )


def validate_motivo_suspensao_required(motivo: str | None) -> None:
    if not motivo or not motivo.strip():
        raise ValidationError("Fundamentação obrigatória para suspensão/revogação")


# ---------------------------------------------------------------------------
# CRUD — UnidadeAutorizadora
# ---------------------------------------------------------------------------


async def criar_unidade_autorizadora(
    db: AsyncSession,
    *,
    cod_unidade_autorizadora: int,
    origem_unidade: OrigemUnidade,
    nome: str,
    sigla: str,
    user: User,
    ip_address: str | None = None,
) -> UnidadeAutorizadora:
    ua = UnidadeAutorizadora(
        cod_unidade_autorizadora=cod_unidade_autorizadora,
        origem_unidade=origem_unidade,
        nome=nome,
        sigla=sigla,
    )
    db.add(ua)
    await db.flush()  # get id before commit
    await log_audit(
        db,
        table_name="unidades_autorizadoras",
        record_id=str(ua.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"cod_unidade_autorizadora": cod_unidade_autorizadora, "nome": nome},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(ua)
    return ua


async def get_unidade_autorizadora(
    db: AsyncSession, ua_id: uuid.UUID
) -> UnidadeAutorizadora | None:
    result = await db.execute(select(UnidadeAutorizadora).where(UnidadeAutorizadora.id == ua_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD — AtoAutorizacao
# ---------------------------------------------------------------------------


async def criar_ato_autorizacao(
    db: AsyncSession,
    *,
    unidade_autorizadora_id: uuid.UUID,
    autoridade: str,
    data_publicacao: date,
    referencia: str,
    user: User,
    ip_address: str | None = None,
) -> AtoAutorizacao:
    ua = await get_unidade_autorizadora(db, unidade_autorizadora_id)
    if ua is None:
        raise ValidationError("UnidadeAutorizadora não encontrada")

    ato = AtoAutorizacao(
        unidade_autorizadora_id=unidade_autorizadora_id,
        autoridade=autoridade,
        data_publicacao=data_publicacao,
        referencia=referencia,
        status=StatusAto.ATIVO,
    )
    db.add(ato)
    await db.flush()

    # Ato ativo → pgd_autorizado = True
    ua.pgd_autorizado = True
    await db.flush()

    await log_audit(
        db,
        table_name="atos_autorizacao",
        record_id=str(ato.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "autoridade": autoridade,
            "referencia": referencia,
            "status": StatusAto.ATIVO.value,
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(ato)
    return ato


async def atualizar_status_ato(
    db: AsyncSession,
    *,
    ato_id: uuid.UUID,
    novo_status: StatusAto,
    user: User,
    ip_address: str | None = None,
) -> AtoAutorizacao:
    result = await db.execute(select(AtoAutorizacao).where(AtoAutorizacao.id == ato_id))
    ato = result.scalar_one_or_none()
    if ato is None:
        raise ValidationError("AtoAutorizacao não encontrado")

    old_status = ato.status
    ato.status = novo_status

    # Atualiza pgd_autorizado na autorizadora
    ua = await get_unidade_autorizadora(db, ato.unidade_autorizadora_id)
    if ua is not None:
        ua.pgd_autorizado = novo_status == StatusAto.ATIVO

    await log_audit(
        db,
        table_name="atos_autorizacao",
        record_id=str(ato.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old_status.value},
        new_values={"status": novo_status.value},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(ato)
    return ato


# ---------------------------------------------------------------------------
# CRUD — UnidadeInstituidora
# ---------------------------------------------------------------------------


async def _require_ato_autorizacao_ativo(
    db: AsyncSession, unidade_autorizadora_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(AtoAutorizacao).where(
            AtoAutorizacao.unidade_autorizadora_id == unidade_autorizadora_id,
            AtoAutorizacao.status == StatusAto.ATIVO,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValidationError("Ato de autorização ativo obrigatório")


async def criar_unidade_instituidora(
    db: AsyncSession,
    *,
    unidade_autorizadora_id: uuid.UUID,
    cod_unidade_instituidora: int,
    nome: str,
    sigla: str,
    ato_instituicao_ref: str,
    data_instituicao: date,
    tipos_atividades: str,
    modalidades_autorizadas: list[int] | None = None,
    conteudo_minimo_tcr: str,
    prazo_antecedencia_convocacao_dias: int,
    vagas_percentual_presencial: int | None = None,
    vagas_percentual_tt_parcial: int | None = None,
    vagas_percentual_tt_integral: int | None = None,
    vagas_percentual_tt_exterior: int | None = None,
    nivel_produtividade_adicional_tt: str | None = None,
    vedacoes_participacao: str | None = None,
    criterios_selecao_adicionais: str | None = None,
    procedimento_registro_comparecimento: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> UnidadeInstituidora:
    if modalidades_autorizadas is None:
        modalidades_autorizadas = [1, 2, 3]
    validate_vagas_tt_exterior(vagas_percentual_tt_exterior)
    await _require_ato_autorizacao_ativo(db, unidade_autorizadora_id)

    ui = UnidadeInstituidora(
        unidade_autorizadora_id=unidade_autorizadora_id,
        cod_unidade_instituidora=cod_unidade_instituidora,
        nome=nome,
        sigla=sigla,
        ato_instituicao_ref=ato_instituicao_ref,
        data_instituicao=data_instituicao,
        tipos_atividades=tipos_atividades,
        modalidades_autorizadas=modalidades_autorizadas,
        conteudo_minimo_tcr=conteudo_minimo_tcr,
        prazo_antecedencia_convocacao_dias=prazo_antecedencia_convocacao_dias,
        vagas_percentual_presencial=vagas_percentual_presencial,
        vagas_percentual_tt_parcial=vagas_percentual_tt_parcial,
        vagas_percentual_tt_integral=vagas_percentual_tt_integral,
        vagas_percentual_tt_exterior=vagas_percentual_tt_exterior,
        nivel_produtividade_adicional_tt=nivel_produtividade_adicional_tt,
        vedacoes_participacao=vedacoes_participacao,
        criterios_selecao_adicionais=criterios_selecao_adicionais,
        procedimento_registro_comparecimento=procedimento_registro_comparecimento,
        status=StatusPgd.EM_VIGOR,
    )
    db.add(ui)
    await db.flush()

    await log_audit(
        db,
        table_name="unidades_instituidoras",
        record_id=str(ui.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"cod_unidade_instituidora": cod_unidade_instituidora, "nome": nome},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(ui)
    return ui


async def suspender_pgd(
    db: AsyncSession,
    *,
    unidade_instituidora_id: uuid.UUID,
    motivo: str,
    user: User,
    ip_address: str | None = None,
) -> UnidadeInstituidora:
    validate_motivo_suspensao_required(motivo)

    result = await db.execute(
        select(UnidadeInstituidora).where(UnidadeInstituidora.id == unidade_instituidora_id)
    )
    ui = result.scalar_one_or_none()
    if ui is None:
        raise ValidationError("UnidadeInstituidora não encontrada")

    old_status = ui.status
    ui.status = StatusPgd.SUSPENSO
    ui.motivo_suspensao_revogacao = motivo
    from datetime import date as _date

    ui.data_suspensao_revogacao = _date.today()

    await log_audit(
        db,
        table_name="unidades_instituidoras",
        record_id=str(ui.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old_status.value},
        new_values={"status": StatusPgd.SUSPENSO.value, "motivo": motivo},
        ip_address=ip_address,
    )

    # Cancel active PlanoTrabalho for this instituidora (TC-M01-011)
    try:
        from sqlalchemy import select as _sel

        from ..models.institucional import UnidadeExecucao
        from ..models.plano import (  # noqa: F401
            STATUS_PT_APROVADO,
            STATUS_PT_CANCELADO,
            STATUS_PT_EM_EXECUCAO,
            PlanoTrabalho,
        )

        unidades_result = await db.execute(
            _sel(UnidadeExecucao.id).where(
                UnidadeExecucao.unidade_instituidora_id == unidade_instituidora_id
            )
        )
        ue_ids = [row[0] for row in unidades_result]

        if ue_ids:
            from ..models.participante import Participante

            participantes_result = await db.execute(
                _sel(Participante.id).where(Participante.unidade_execucao_id.in_(ue_ids))
            )
            p_ids = [row[0] for row in participantes_result]

            if p_ids:
                planos_result = await db.execute(
                    _sel(PlanoTrabalho).where(
                        PlanoTrabalho.participante_id.in_(p_ids),
                        PlanoTrabalho.status.in_([STATUS_PT_EM_EXECUCAO, STATUS_PT_APROVADO]),
                    )
                )
                for pt in planos_result.scalars():
                    old_pt_status = pt.status
                    pt.status = STATUS_PT_CANCELADO
                    await log_audit(
                        db,
                        table_name="planos_trabalho",
                        record_id=str(pt.id),
                        action=AuditAction.UPDATE,
                        user=user,
                        old_values={"status": old_pt_status},
                        new_values={
                            "status": STATUS_PT_CANCELADO,
                            "motivo": "PGD suspenso",
                        },
                        ip_address=ip_address,
                    )
    except ImportError:
        pass

    from ..models.notificacao import TipoEvento
    from .notificacao import criar_notificacao

    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PGD_SUSPENSO_REVOGADO,
        conteudo=f"O PGD da unidade instituidora foi suspenso. Motivo: {motivo}",
        contexto={
            "unidade_instituidora_id": str(unidade_instituidora_id),
            "motivo": motivo,
        },
    )
    await db.commit()
    await db.refresh(ui)
    return ui


async def get_unidade_instituidora(
    db: AsyncSession, ui_id: uuid.UUID
) -> UnidadeInstituidora | None:
    result = await db.execute(select(UnidadeInstituidora).where(UnidadeInstituidora.id == ui_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Resultados públicos
# ---------------------------------------------------------------------------


async def listar_resultados_publicos(
    db: AsyncSession,
) -> list[dict]:
    from sqlalchemy import case, func

    from ..models.plano import STATUS_PE_AVALIADO, PlanoEntregas

    result = await db.execute(
        select(
            UnidadeExecucao.cod_unidade_executora,
            UnidadeExecucao.nome,
            func.count(case((PlanoEntregas.status == STATUS_PE_AVALIADO, PlanoEntregas.id))).label(
                "total_planos_avaliados"
            ),
            func.avg(case((PlanoEntregas.avaliacao.isnot(None), PlanoEntregas.avaliacao))).label(
                "media_avaliacao"
            ),
        )
        .outerjoin(PlanoEntregas, PlanoEntregas.unidade_execucao_id == UnidadeExecucao.id)
        .group_by(
            UnidadeExecucao.id,
            UnidadeExecucao.cod_unidade_executora,
            UnidadeExecucao.nome,
        )
    )
    rows = result.all()
    return [
        {
            "cod_unidade_executora": r.cod_unidade_executora,
            "nome": r.nome,
            "total_planos_avaliados": r.total_planos_avaliados or 0,
            "media_avaliacao": float(r.media_avaliacao) if r.media_avaliacao is not None else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Delegação de competência (RF-037)
# ---------------------------------------------------------------------------


async def delegar_competencia(
    db: AsyncSession,
    *,
    delegante_user_id: int,
    delegatario_user_id: int,
    competencia: Competencia,
    data_inicio: date,
    data_fim: date | None = None,
    unidade_execucao_id: uuid.UUID | None = None,
    motivo: str | None = None,
    user: User,
    ip_address: str | None = None,
) -> DelegacaoCompetencia:
    if data_fim is not None and data_fim < data_inicio:
        raise ValidationError("Data fim da delegação não pode ser anterior à data de início")
    d = DelegacaoCompetencia(
        delegante_user_id=delegante_user_id,
        delegatario_user_id=delegatario_user_id,
        competencia=competencia,
        unidade_execucao_id=unidade_execucao_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        motivo=motivo,
        ativo=True,
    )
    db.add(d)
    await db.flush()
    await log_audit(
        db,
        table_name="delegacoes_competencia",
        record_id=str(d.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "delegante_user_id": delegante_user_id,
            "delegatario_user_id": delegatario_user_id,
            "competencia": competencia.value,
            "unidade_execucao_id": (str(unidade_execucao_id) if unidade_execucao_id else None),
            "data_inicio": str(data_inicio),
            "data_fim": str(data_fim) if data_fim else None,
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(d)
    return d


async def revogar_delegacao(
    db: AsyncSession,
    *,
    delegacao_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> DelegacaoCompetencia:
    result = await db.execute(
        select(DelegacaoCompetencia).where(DelegacaoCompetencia.id == delegacao_id)
    )
    d = result.scalar_one_or_none()
    if d is None:
        raise ValidationError("Delegação não encontrada")
    if not d.ativo:
        return d
    d.ativo = False
    await log_audit(
        db,
        table_name="delegacoes_competencia",
        record_id=str(d.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"ativo": True},
        new_values={"ativo": False},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(d)
    return d


async def has_delegated_permission(
    db: AsyncSession,
    *,
    user_id: int,
    competencia: Competencia,
    unidade_execucao_id: uuid.UUID | None = None,
    referencia: date | None = None,
) -> bool:
    """Verifica se `user_id` possui delegação ativa para `competencia` vigente
    em `referencia`. Quando `unidade_execucao_id` é informado, a delegação
    pode ser global (sem escopo de UE) ou específica para essa UE.
    """
    ref = referencia or date.today()
    q = select(DelegacaoCompetencia).where(
        DelegacaoCompetencia.delegatario_user_id == user_id,
        DelegacaoCompetencia.competencia == competencia,
        DelegacaoCompetencia.ativo.is_(True),
        DelegacaoCompetencia.data_inicio <= ref,
        or_(
            DelegacaoCompetencia.data_fim.is_(None),
            DelegacaoCompetencia.data_fim >= ref,
        ),
    )
    if unidade_execucao_id is not None:
        q = q.where(
            or_(
                DelegacaoCompetencia.unidade_execucao_id.is_(None),
                DelegacaoCompetencia.unidade_execucao_id == unidade_execucao_id,
            )
        )
    result = await db.execute(q)
    return result.scalars().first() is not None
