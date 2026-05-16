import uuid
from datetime import UTC, date, datetime

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.audit import AuditAction
from ..models.institucional import OrigemUnidade
from ..models.notificacao import TipoEvento
from ..models.participante import TCR, Participante, StatusTCR
from ..models.plano import (
    STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA,
    STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE,
    STATUS_PT_CANCELADO,
    STATUS_PT_CONCLUIDO,
    STATUS_PT_EM_EXECUCAO,
    STATUS_PT_RASCUNHO_CHEFIA,
    STATUS_PT_RASCUNHO_PARTICIPANTE,
    AvaliacaoRegistrosExecucao,
    Contribuicao,
    CriadoPorRole,
    PlanoEntregas,
    PlanoTrabalho,
)
from ..models.user import User, UserRole
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao

# Estados em que o PT é considerado rascunho/pactuação em andamento
STATUS_PT_PACTUACAO_EM_ANDAMENTO = {
    STATUS_PT_RASCUNHO_PARTICIPANTE,
    STATUS_PT_RASCUNHO_CHEFIA,
    STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA,
    STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE,
}

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


def _role_to_criado_por(user: User | None) -> CriadoPorRole:
    """Mapeia UserRole para CriadoPorRole. Servidor = participante; demais = chefia."""
    if user is None or user.role == UserRole.SERVIDOR:
        return CriadoPorRole.PARTICIPANTE
    return CriadoPorRole.CHEFIA


def _status_inicial(criado_por: CriadoPorRole) -> int:
    return (
        STATUS_PT_RASCUNHO_PARTICIPANTE
        if criado_por == CriadoPorRole.PARTICIPANTE
        else STATUS_PT_RASCUNHO_CHEFIA
    )


async def _get_pt_or_raise(db: AsyncSession, plano_id: uuid.UUID) -> PlanoTrabalho:
    pt = await get_plano_trabalho(db, plano_id)
    if pt is None:
        raise ValidationError("Plano de Trabalho não encontrado")
    return pt


def _is_servidor_do_pt(pt: PlanoTrabalho, user: User, participante: Participante | None) -> bool:
    """Servidor é o "dono" do PT quando seu email bate com o do participante."""
    return (
        user.role == UserRole.SERVIDOR
        and participante is not None
        and participante.email == user.email
    )


async def _validar_dono_pode_agir(
    db: AsyncSession,
    pt: PlanoTrabalho,
    user: User,
    *,
    acao_servidor_em: set[int],
    acao_chefia_em: set[int],
) -> None:
    """Valida se o user tem a 'bola' para realizar a ação (edição/envio/assinatura).

    `acao_servidor_em` e `acao_chefia_em` são os status em que cada lado pode agir.
    """
    if user.role == UserRole.SERVIDOR:
        # Servidor age em SEU PT quando bola está com ele
        part_res = await db.execute(
            select(Participante).where(Participante.id == pt.participante_id)
        )
        participante = part_res.scalar_one_or_none()
        if not _is_servidor_do_pt(pt, user, participante):
            raise ValidationError("Servidor só pode agir no próprio Plano de Trabalho")
        if pt.status not in acao_servidor_em:
            raise ValidationError("Você não pode agir neste plano agora — a bola está com a chefia")
    else:
        # Chefia age em PT da sua UA quando bola está com ela
        if (
            user.cod_unidade_autorizadora is not None
            and pt.cod_unidade_autorizadora != user.cod_unidade_autorizadora
        ):
            raise ValidationError("Você não tem permissão sobre este Plano de Trabalho")
        if pt.status not in acao_chefia_em:
            raise ValidationError(
                "Você não pode agir neste plano agora — a bola está com o servidor"
            )


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
    clonado_de_id: uuid.UUID | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    """Cria PT em rascunho.

    O status inicial depende de quem criou:
    - Servidor → RASCUNHO_PARTICIPANTE
    - Chefia/Admin → RASCUNHO_CHEFIA

    TCR pode estar PENDENTE durante rascunho; só exige ATIVO ao assinar (transição
    para EM_EXECUCAO).
    """
    from .participante import validate_adicional_noturno_autorizado

    validate_duracao_maxima_pt(data_inicio, data_termino)
    if tcr_id is None:
        # Aceita TCR PENDENTE ou ATIVO durante rascunho
        tcr_res = await db.execute(
            select(TCR)
            .where(TCR.participante_id == participante_id)
            .where(TCR.status.in_([StatusTCR.PENDENTE, StatusTCR.ATIVO]))
            .order_by(TCR.created_at.desc())
        )
        tcr = tcr_res.scalar_one_or_none()
        if tcr is None:
            raise ValidationError(
                "Participante precisa de TCR (PENDENTE ou ATIVO) para criar Plano de Trabalho"
            )
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

    criado_por = _role_to_criado_por(user)
    status_inicial = _status_inicial(criado_por)

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
        status=status_inicial,
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
        criado_por_role=criado_por,
        clonado_de_id=clonado_de_id,
    )
    db.add(pt)
    await db.flush()
    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "id_plano_trabalho": id_plano_trabalho,
            "status": status_inicial,
            "criado_por_role": criado_por.value,
            "clonado_de_id": str(clonado_de_id) if clonado_de_id else None,
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def get_plano_trabalho(db: AsyncSession, pt_id: uuid.UUID) -> PlanoTrabalho | None:
    result = await db.execute(select(PlanoTrabalho).where(PlanoTrabalho.id == pt_id))
    return result.scalar_one_or_none()


async def editar_plano_trabalho(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
    **campos,
) -> PlanoTrabalho:
    """Edita campos do PT em rascunho ou aguardando assinatura.

    Se o PT estava em AGUARDANDO_ASSINATURA_*, a assinatura cai e o status volta
    para RASCUNHO_X do editor.

    Campos editáveis: data_inicio, data_termino, carga_horaria_disponivel,
    criterios_avaliacao, plano_entregas_id, trabalho_noturno, declarações.
    """
    pt = await _get_pt_or_raise(db, plano_id)

    if pt.status in {STATUS_PT_EM_EXECUCAO, STATUS_PT_CONCLUIDO, STATUS_PT_CANCELADO}:
        raise ValidationError(
            f"Plano de Trabalho em execução/concluído/cancelado não pode ser editado"
            f" (status={pt.status})"
        )

    await _validar_dono_pode_agir(
        db,
        pt,
        user,
        acao_servidor_em={
            STATUS_PT_RASCUNHO_PARTICIPANTE,
            STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE,
        },
        acao_chefia_em={
            STATUS_PT_RASCUNHO_CHEFIA,
            STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA,
        },
    )

    old_values = {"status": pt.status}
    # Aplica campos editáveis
    EDITAVEIS = {
        "data_inicio",
        "data_termino",
        "carga_horaria_disponivel",
        "criterios_avaliacao",
        "plano_entregas_id",
        "trabalho_noturno",
        "declaracao_ausencia_prejuizo_plano",
        "declaracao_ausencia_prejuizo_comparecer",
        "declaracao_ausencia_prejuizo_contato",
        "declaracao_ausencia_prejuizo_sincrono",
    }
    for k, v in campos.items():
        if k not in EDITAVEIS:
            raise ValidationError(f"Campo '{k}' não pode ser editado")
        old_values[k] = getattr(pt, k)
        setattr(pt, k, v)

    # Se estava AGUARDANDO_*, qualquer edição derruba assinaturas
    novo_status = pt.status
    if pt.status == STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA:
        # chefia ajustou: zera assinatura participante, vira rascunho chefia
        pt.data_assinatura_participante = None
        novo_status = STATUS_PT_RASCUNHO_CHEFIA
    elif pt.status == STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE:
        # servidor ajustou: zera assinatura chefia, vira rascunho participante
        pt.data_assinatura_chefia = None
        novo_status = STATUS_PT_RASCUNHO_PARTICIPANTE
    pt.status = novo_status

    if pt.data_inicio and pt.data_termino:
        validate_duracao_maxima_pt(pt.data_inicio, pt.data_termino)

    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values=old_values,
        new_values={**campos, "status": pt.status},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def enviar_pt_para_outro_lado(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    """Quem está com a bola assina e envia para o outro lado.

    De RASCUNHO_PARTICIPANTE → AGUARDANDO_ASSINATURA_CHEFIA (registra assinatura participante).
    De RASCUNHO_CHEFIA → AGUARDANDO_ASSINATURA_PARTICIPANTE (registra assinatura chefia).
    """
    pt = await _get_pt_or_raise(db, plano_id)
    await _validar_dono_pode_agir(
        db,
        pt,
        user,
        acao_servidor_em={STATUS_PT_RASCUNHO_PARTICIPANTE},
        acao_chefia_em={STATUS_PT_RASCUNHO_CHEFIA},
    )

    # Valida que tem pelo menos uma contribuição
    contribs_res = await db.execute(
        select(Contribuicao).where(Contribuicao.plano_trabalho_id == pt.id)
    )
    if contribs_res.scalar_one_or_none() is None:
        raise ValidationError(
            "Plano de Trabalho precisa ter pelo menos uma contribuição antes de enviar"
        )

    now = datetime.now(UTC)
    old_status = pt.status
    if user.role == UserRole.SERVIDOR:
        pt.data_assinatura_participante = now
        pt.status = STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA
    else:
        pt.data_assinatura_chefia = now
        pt.status = STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE

    # Notifica o outro lado
    part_res = await db.execute(select(Participante).where(Participante.id == pt.participante_id))
    participante = part_res.scalar_one_or_none()
    destinatario_email = (
        participante.email
        if user.role != UserRole.SERVIDOR and participante
        else None  # se chefia enviou, destinatário é o servidor (email do participante)
    )
    # Se servidor enviou, destinatário é a chefia — buscar via TCR
    if user.role == UserRole.SERVIDOR:
        tcr_res = await db.execute(select(TCR).where(TCR.id == pt.tcr_id))
        tcr = tcr_res.scalar_one_or_none()
        if tcr and tcr.chefia_user_id:
            chefia_res = await db.execute(select(User).where(User.id == tcr.chefia_user_id))
            chefia = chefia_res.scalar_one_or_none()
            destinatario_email = chefia.email if chefia else None

    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PLANO_TRABALHO_RECEBIDO_PARA_ASSINATURA,
        conteudo=(
            f"O plano de trabalho {pt.id_plano_trabalho} foi enviado para sua revisão e assinatura."
        ),
        destinatario_email=destinatario_email,
        contexto={"id_plano_trabalho": pt.id_plano_trabalho, "pt_id": str(pt.id)},
    )

    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old_status},
        new_values={"status": pt.status, "acao": "enviar_para_outro_lado"},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def assinar_pt(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    """Assina o PT recebido. Se ambas as assinaturas existirem → vira EM_EXECUCAO.

    De AGUARDANDO_ASSINATURA_CHEFIA, chefia assina → EM_EXECUCAO.
    De AGUARDANDO_ASSINATURA_PARTICIPANTE, servidor assina → EM_EXECUCAO.
    """
    pt = await _get_pt_or_raise(db, plano_id)
    await _validar_dono_pode_agir(
        db,
        pt,
        user,
        acao_servidor_em={STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE},
        acao_chefia_em={STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA},
    )

    # Valida TCR ativo na hora de pactuar
    tcr_res = await db.execute(select(TCR).where(TCR.id == pt.tcr_id))
    tcr = tcr_res.scalar_one_or_none()
    if tcr is None or tcr.status != StatusTCR.ATIVO:
        raise ValidationError("TCR precisa estar ATIVO para pactuação final do Plano de Trabalho")

    now = datetime.now(UTC)
    old_status = pt.status
    if user.role == UserRole.SERVIDOR:
        pt.data_assinatura_participante = now
    else:
        pt.data_assinatura_chefia = now

    # Transição automática para EM_EXECUCAO quando ambas as datas existem
    if pt.data_assinatura_participante and pt.data_assinatura_chefia:
        pt.status = STATUS_PT_EM_EXECUCAO

    # Notifica
    part_res = await db.execute(select(Participante).where(Participante.id == pt.participante_id))
    participante = part_res.scalar_one_or_none()
    if pt.status == STATUS_PT_EM_EXECUCAO and participante:
        await criar_notificacao(
            db,
            tipo_evento=TipoEvento.PLANO_TRABALHO_PACTUADO,
            conteudo=(
                f"O plano de trabalho {pt.id_plano_trabalho} foi pactuado por ambas as"
                f" partes e entrou em execução."
            ),
            destinatario_email=participante.email,
            contexto={"id_plano_trabalho": pt.id_plano_trabalho, "pt_id": str(pt.id)},
        )

    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old_status},
        new_values={"status": pt.status, "acao": "assinar"},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(pt)
    return pt


async def clonar_plano_trabalho(
    db: AsyncSession,
    *,
    pt_origem_id: uuid.UUID,
    id_plano_trabalho_novo: str,
    nova_data_inicio: date,
    nova_data_termino: date,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    """Cria novo PT copiando campos e contribuições do PT origem.

    Não copia: assinaturas, TCR (reusa do participante), avaliações.
    Status inicial = RASCUNHO_X do user que clonou.
    """
    origem_res = await db.execute(
        select(PlanoTrabalho)
        .options(selectinload(PlanoTrabalho.contribuicoes))
        .where(PlanoTrabalho.id == pt_origem_id)
    )
    pt_origem = origem_res.scalar_one_or_none()
    if pt_origem is None:
        raise ValidationError("Plano de Trabalho origem não encontrado")

    pt_novo = await criar_plano_trabalho(
        db,
        id_plano_trabalho=id_plano_trabalho_novo,
        origem_unidade=pt_origem.origem_unidade,
        cod_unidade_autorizadora=pt_origem.cod_unidade_autorizadora,
        cod_unidade_executora=pt_origem.cod_unidade_executora,
        cod_unidade_lotacao_participante=pt_origem.cod_unidade_lotacao_participante,
        participante_id=pt_origem.participante_id,
        cpf_participante=pt_origem.cpf_participante,
        matricula_siape=pt_origem.matricula_siape,
        data_inicio=nova_data_inicio,
        data_termino=nova_data_termino,
        carga_horaria_disponivel=pt_origem.carga_horaria_disponivel,
        criterios_avaliacao=pt_origem.criterios_avaliacao,
        plano_entregas_id=None,  # não reusar PE (provavelmente período diferente)
        declaracao_ausencia_prejuizo_plano=pt_origem.declaracao_ausencia_prejuizo_plano,
        declaracao_ausencia_prejuizo_comparecer=pt_origem.declaracao_ausencia_prejuizo_comparecer,
        declaracao_ausencia_prejuizo_contato=pt_origem.declaracao_ausencia_prejuizo_contato,
        declaracao_ausencia_prejuizo_sincrono=pt_origem.declaracao_ausencia_prejuizo_sincrono,
        trabalho_noturno=pt_origem.trabalho_noturno,
        clonado_de_id=pt_origem.id,
        user=user,
        ip_address=ip_address,
    )

    # Copiar contribuições
    for c_origem in pt_origem.contribuicoes:
        c_nova = Contribuicao(
            id_contribuicao=c_origem.id_contribuicao,
            plano_trabalho_id=pt_novo.id,
            tipo_contribuicao=c_origem.tipo_contribuicao,
            percentual_contribuicao=c_origem.percentual_contribuicao,
            id_plano_entregas=None,  # não reaproveitar referências a PE
            id_entrega=None,
            descricao=c_origem.descricao,
            rotulo=c_origem.rotulo,
        )
        db.add(c_nova)
    await db.commit()
    await db.refresh(pt_novo)
    return pt_novo


async def iniciar_execucao_pt(
    db: AsyncSession,
    *,
    plano_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> PlanoTrabalho:
    """LEGADO / atalho administrativo: força transição direta para EM_EXECUCAO.

    Útil para seed e testes que não passam pelo fluxo de pactuação bilateral.
    No workflow normal, use assinar_pt() após cada lado enviar.

    Preenche as duas datas de assinatura com `now()` se estiverem vazias.
    """
    pt = await _get_pt_or_raise(db, plano_id)
    if pt.status not in STATUS_PT_PACTUACAO_EM_ANDAMENTO:
        raise ValidationError(f"Plano de Trabalho em status {pt.status} não pode ir para execução")
    now = datetime.now(UTC)
    if pt.data_assinatura_participante is None:
        pt.data_assinatura_participante = now
    if pt.data_assinatura_chefia is None:
        pt.data_assinatura_chefia = now
    old_status = pt.status
    pt.status = STATUS_PT_EM_EXECUCAO
    await log_audit(
        db,
        table_name="planos_trabalho",
        record_id=str(pt.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": old_status},
        new_values={"status": STATUS_PT_EM_EXECUCAO, "acao": "iniciar_execucao_atalho"},
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
