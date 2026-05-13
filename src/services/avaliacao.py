import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.participante import Participante
from ..models.plano import AvaliacaoRegistrosExecucao, DecisaoRecurso, PlanoTrabalho, StatusRecurso
from ..models.notificacao import TipoEvento
from ..models.user import User
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def validate_escala_customizada(mapeamento: dict) -> None:
    """Escala customizada deve mapear todos os valores de 1 a 5."""
    valores_mapeados = set(mapeamento.values())
    if not {1, 2, 3, 4, 5}.issubset(valores_mapeados):
        raise ValidationError(
            "A escala deve mapear todos os valores de 1 a 5 para garantir cobertura"
            " completa dos casos (IN24 Art.30)"
        )


def mapear_avaliacao_customizada(valor_customizado: str, mapeamento: dict) -> int:
    """Converte valor customizado para escala padrão 1–5."""
    if valor_customizado not in mapeamento:
        raise ValidationError(
            f"Valor '{valor_customizado}' não encontrado na escala customizada"
        )
    return mapeamento[valor_customizado]


def validate_justificativa_obrigatoria(
    avaliacao: int, justificativa: str | None
) -> None:
    if avaliacao in (1, 4, 5):
        if not justificativa or not justificativa.strip():
            raise ValidationError(
                "Justificativa obrigatória para avaliações 1 (excepcional),"
                " 4 (inadequado) e 5 (não executado) (IN24 Art.21 §3º)"
            )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def _get_email_participante_por_pt(
    db: AsyncSession, plano_trabalho_id: uuid.UUID
) -> str | None:
    r = await db.execute(
        select(Participante.email)
        .join(PlanoTrabalho, PlanoTrabalho.participante_id == Participante.id)
        .where(PlanoTrabalho.id == plano_trabalho_id)
    )
    return r.scalar_one_or_none()


async def _get_avaliacao(
    db: AsyncSession, avaliacao_id: uuid.UUID
) -> AvaliacaoRegistrosExecucao:
    result = await db.execute(
        select(AvaliacaoRegistrosExecucao).where(
            AvaliacaoRegistrosExecucao.id == avaliacao_id
        )
    )
    a = result.scalar_one_or_none()
    if a is None:
        raise ValidationError("AvaliacaoRegistrosExecucao não encontrada")
    return a


async def avaliar_registros_execucao(
    db: AsyncSession,
    *,
    avaliacao_id: uuid.UUID,
    nota: int,
    data_avaliacao: date,
    justificativa: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> AvaliacaoRegistrosExecucao:
    if nota not in range(1, 6):
        raise ValidationError("Avaliação deve ser entre 1 e 5")
    validate_justificativa_obrigatoria(nota, justificativa)

    a = await _get_avaliacao(db, avaliacao_id)
    if a.avaliacao_registros_execucao is not None:
        raise ValidationError("Avaliação já foi registrada")

    a.avaliacao_registros_execucao = nota
    a.data_avaliacao_registros_execucao = data_avaliacao
    a.avaliacao_justificativa = justificativa

    # Avaliações 4 ou 5 abrem janela de recurso
    if nota in (4, 5):
        a.status_recurso = StatusRecurso.ABERTO

    p_email = await _get_email_participante_por_pt(db, a.plano_trabalho_id)
    await log_audit(
        db,
        table_name="avaliacoes_registros_execucao",
        record_id=str(a.id),
        action=AuditAction.UPDATE,
        user=user,
        new_values={"avaliacao": nota, "data_avaliacao": str(data_avaliacao)},
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.AVALIACAO_REALIZADA,
        conteudo=f"Sua avaliação do período {a.id_periodo_avaliativo} foi registrada com nota {nota}.",
        destinatario_email=p_email,
        contexto={"nota": nota, "periodo": a.id_periodo_avaliativo},
    )
    await db.commit()
    await db.refresh(a)
    return a


async def abrir_recurso(
    db: AsyncSession,
    *,
    avaliacao_id: uuid.UUID,
    texto: str,
    user: User | None = None,
    ip_address: str | None = None,
) -> AvaliacaoRegistrosExecucao:
    a = await _get_avaliacao(db, avaliacao_id)
    if a.status_recurso != StatusRecurso.ABERTO:
        raise ValidationError("Não há recurso cabível para esta avaliação")
    if not texto or not texto.strip():
        raise ValidationError("Texto do recurso é obrigatório")
    if a.recurso_data is not None:
        raise ValidationError("Recurso já foi aberto")

    a.recurso_texto = texto
    a.recurso_data = datetime.utcnow()

    p_email = await _get_email_participante_por_pt(db, a.plano_trabalho_id)
    await log_audit(
        db,
        table_name="avaliacoes_registros_execucao",
        record_id=str(a.id),
        action=AuditAction.UPDATE,
        user=user,
        new_values={"recurso": "aberto"},
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.RECURSO_ABERTO,
        conteudo=f"Recurso foi aberto para a avaliação do período {a.id_periodo_avaliativo}.",
        destinatario_user_id=user.id if user else None,
        destinatario_email=p_email if not user else None,
        contexto={"avaliacao_id": str(a.id)},
    )
    await db.commit()
    await db.refresh(a)
    return a


async def decidir_recurso(
    db: AsyncSession,
    *,
    avaliacao_id: uuid.UUID,
    decisao: DecisaoRecurso,
    justificativa: str | None = None,
    nova_nota: int | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> AvaliacaoRegistrosExecucao:
    a = await _get_avaliacao(db, avaliacao_id)
    if a.recurso_data is None:
        raise ValidationError("Participante ainda não abriu recurso")
    if a.recurso_decisao is not None:
        raise ValidationError("Recurso já foi decidido")

    if decisao == DecisaoRecurso.NAO_ACATADO:
        if not justificativa or not justificativa.strip():
            raise ValidationError(
                "Justificativa obrigatória ao não acatar recurso (IN24 Art.21 §5º)"
            )
    elif decisao == DecisaoRecurso.ACATADO and nova_nota is not None:
        if nova_nota not in range(1, 6):
            raise ValidationError("Nova nota deve ser entre 1 e 5")
        validate_justificativa_obrigatoria(nova_nota, justificativa)
        a.avaliacao_registros_execucao = nova_nota
        a.avaliacao_justificativa = justificativa

    a.recurso_decisao = decisao
    a.recurso_decisao_justificativa = justificativa
    a.recurso_decisao_data = datetime.utcnow()
    a.status_recurso = StatusRecurso.ENCERRADO

    p_email = await _get_email_participante_por_pt(db, a.plano_trabalho_id)
    await log_audit(
        db,
        table_name="avaliacoes_registros_execucao",
        record_id=str(a.id),
        action=AuditAction.UPDATE,
        user=user,
        new_values={"recurso_decisao": decisao.value},
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.RECURSO_DECIDIDO,
        conteudo=f"Recurso decidido: {decisao.value}.",
        destinatario_email=p_email,
        contexto={"decisao": decisao.value, "avaliacao_id": str(a.id)},
    )
    await db.commit()
    await db.refresh(a)
    return a
