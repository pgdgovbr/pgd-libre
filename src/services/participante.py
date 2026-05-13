import uuid
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.institucional import OrigemUnidade, UnidadeExecucao
from ..models.participante import (
    Convocacao,
    MotivoDesligamento,
    Participante,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
    TCR,
    TipoVinculo,
)
from ..models.notificacao import TipoEvento
from ..models.user import User
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao

MIN_DATA_ASSINATURA_TCR = date(2023, 7, 31)


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def validate_cpf(cpf: str) -> None:
    if not cpf.isdigit() or len(cpf) != 11:
        raise ValidationError("CPF inválido")
    if len(set(cpf)) == 1:
        raise ValidationError("CPF inválido")
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    rem = total % 11
    d1 = 0 if rem < 2 else 11 - rem
    if int(cpf[9]) != d1:
        raise ValidationError("CPF inválido")
    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    rem = total % 11
    d2 = 0 if rem < 2 else 11 - rem
    if int(cpf[10]) != d2:
        raise ValidationError("CPF inválido")


def validate_matricula_siape(matricula: str) -> None:
    if not matricula.isdigit() or len(matricula) != 7:
        raise ValidationError("Matrícula SIAPE deve ter 7 dígitos")
    if len(set(matricula)) == 1:
        raise ValidationError("Matrícula SIAPE inválida: todos os dígitos são iguais")


def validate_estagio_probatorio(
    modalidade_execucao: int, cumpriu_estagio_probatorio: bool | None
) -> None:
    if modalidade_execucao in (2, 3, 4, 5):
        if not cumpriu_estagio_probatorio:
            raise ValidationError(
                "Teletrabalho exige cumprimento de 1 ano de estágio probatório"
                " (IN24 Art.10 §2º)"
            )


def validate_data_assinatura_tcr_minima(data: date) -> None:
    if data < MIN_DATA_ASSINATURA_TCR:
        raise ValidationError(
            "Data de assinatura do TCR anterior ao início da vigência do"
            " Decreto 11.072/2022"
        )


def validate_motivo_desligamento_required(motivo: MotivoDesligamento | None) -> None:
    if motivo is None:
        raise ValidationError("Hipótese de desligamento obrigatória")


def validate_prazo_antecedencia_convocacao(
    data_convocacao: date,
    data_comparecimento: date,
    prazo_dias: int,
) -> None:
    delta = (data_comparecimento - data_convocacao).days
    if delta < prazo_dias:
        raise ValidationError(
            f"Convocação deve respeitar antecedência mínima de {prazo_dias} dias"
            " conforme TCR (IN24 Art.11)"
        )


# ---------------------------------------------------------------------------
# CRUD — Participante
# ---------------------------------------------------------------------------


async def _count_tt_exterior(
    db: AsyncSession, unidade_execucao_id: uuid.UUID
) -> tuple[int, int]:
    """Returns (total_active, total_exterior_active) for the unidade."""
    total_result = await db.execute(
        select(func.count()).where(
            Participante.unidade_execucao_id == unidade_execucao_id,
            Participante.situacao == 1,
        )
    )
    total = total_result.scalar_one()

    exterior_result = await db.execute(
        select(func.count()).where(
            Participante.unidade_execucao_id == unidade_execucao_id,
            Participante.situacao == 1,
            Participante.modalidade_execucao.in_([4, 5]),
        )
    )
    exterior = exterior_result.scalar_one()
    return total, exterior


async def validate_limite_tt_exterior(
    db: AsyncSession,
    unidade_execucao_id: uuid.UUID,
    modalidade_execucao: int,
) -> None:
    if modalidade_execucao not in (4, 5):
        return
    total, exterior = await _count_tt_exterior(db, unidade_execucao_id)
    if total > 0 and (exterior / total) >= 0.02:
        raise ValidationError(
            "Limite de 2% para teletrabalho no exterior atingido (IN24 Art.12 §único)"
        )


async def cadastrar_participante(
    db: AsyncSession,
    *,
    origem_unidade: OrigemUnidade,
    cod_unidade_autorizadora: int,
    cod_unidade_lotacao: int,
    matricula_siape: str,
    cod_unidade_instituidora: int,
    cpf: str,
    nome: str,
    email: str,
    modalidade_execucao: int,
    data_assinatura_tcr: date,
    tipo_vinculo: TipoVinculo,
    unidade_execucao_id: uuid.UUID,
    cumpriu_estagio_probatorio: bool | None = None,
    data_fim_estagio_probatorio: date | None = None,
    data_ingresso_pgd: date | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> Participante:
    validate_cpf(cpf)
    validate_matricula_siape(matricula_siape)
    validate_estagio_probatorio(modalidade_execucao, cumpriu_estagio_probatorio)
    validate_data_assinatura_tcr_minima(data_assinatura_tcr)
    await validate_limite_tt_exterior(db, unidade_execucao_id, modalidade_execucao)

    p = Participante(
        origem_unidade=origem_unidade,
        cod_unidade_autorizadora=cod_unidade_autorizadora,
        cod_unidade_lotacao=cod_unidade_lotacao,
        matricula_siape=matricula_siape,
        cod_unidade_instituidora=cod_unidade_instituidora,
        cpf=cpf,
        nome=nome,
        email=email,
        situacao=1,
        modalidade_execucao=modalidade_execucao,
        data_assinatura_tcr=data_assinatura_tcr,
        tipo_vinculo=tipo_vinculo,
        unidade_execucao_id=unidade_execucao_id,
        cumpriu_estagio_probatorio=cumpriu_estagio_probatorio,
        data_fim_estagio_probatorio=data_fim_estagio_probatorio,
        data_ingresso_pgd=data_ingresso_pgd,
    )
    db.add(p)
    await db.flush()
    await log_audit(
        db,
        table_name="participantes",
        record_id=str(p.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"cpf": cpf[-4:], "matricula_siape": matricula_siape, "nome": nome},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(p)
    return p


async def get_participante(
    db: AsyncSession, participante_id: uuid.UUID
) -> Participante | None:
    result = await db.execute(
        select(Participante).where(Participante.id == participante_id)
    )
    return result.scalar_one_or_none()


async def desligar_participante(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    motivo: MotivoDesligamento,
    user: User,
    ip_address: str | None = None,
) -> Participante:
    validate_motivo_desligamento_required(motivo)

    result = await db.execute(
        select(Participante).where(Participante.id == participante_id)
    )
    p = result.scalar_one_or_none()
    if p is None:
        raise ValidationError("Participante não encontrado")

    old_situacao = p.situacao
    p.situacao = 0
    p.motivo_desligamento = motivo
    p.data_desligamento = date.today()

    await log_audit(
        db,
        table_name="participantes",
        record_id=str(p.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"situacao": old_situacao},
        new_values={"situacao": 0, "motivo_desligamento": motivo.value},
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.DESLIGAMENTO_REGISTRADO,
        conteudo="Seu desligamento do PGD foi registrado.",
        destinatario_email=p.email,
        contexto={"motivo": motivo.value},
    )
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# CRUD — TCR
# ---------------------------------------------------------------------------


async def get_tcr_ativo(db: AsyncSession, participante_id: uuid.UUID) -> TCR | None:
    result = await db.execute(
        select(TCR).where(
            TCR.participante_id == participante_id,
            TCR.status == StatusTCR.ATIVO,
        )
    )
    return result.scalar_one_or_none()


async def pactu_tcr(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    chefia_user_id: int | None,
    modalidade_execucao: int,
    regime_execucao: RegimeExecucao,
    prazo_antecedencia_convocacao_dias: int,
    canais_comunicacao: list,
    responsabilidades: str,
    ciencia_instalacoes_ergonomia: bool,
    ciencia_nao_direito_adquirido: bool,
    ciencia_custeio_estrutura: bool,
    saldo_banco_horas: int | None = None,
    acoes_melhoria: str | None = None,
    tcr_anterior_id: uuid.UUID | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> TCR:
    prazo_compensacao = None
    if saldo_banco_horas is not None:
        prazo_compensacao = date.today() + relativedelta(months=6)

    tcr = TCR(
        participante_id=participante_id,
        chefia_user_id=chefia_user_id,
        modalidade_execucao=modalidade_execucao,
        regime_execucao=regime_execucao,
        prazo_antecedencia_convocacao_dias=prazo_antecedencia_convocacao_dias,
        canais_comunicacao=canais_comunicacao,
        responsabilidades=responsabilidades,
        ciencia_instalacoes_ergonomia=ciencia_instalacoes_ergonomia,
        ciencia_nao_direito_adquirido=ciencia_nao_direito_adquirido,
        ciencia_custeio_estrutura=ciencia_custeio_estrutura,
        saldo_banco_horas=saldo_banco_horas,
        prazo_compensacao_banco_horas=prazo_compensacao,
        acoes_melhoria=acoes_melhoria,
        tcr_anterior_id=tcr_anterior_id,
        data_assinatura_participante=datetime.utcnow(),
        status=StatusTCR.PENDENTE,
    )
    db.add(tcr)
    await db.flush()
    await log_audit(
        db,
        table_name="tcrs",
        record_id=str(tcr.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={"participante_id": str(participante_id), "status": StatusTCR.PENDENTE.value},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(tcr)
    return tcr


async def assinar_tcr_chefia(
    db: AsyncSession,
    *,
    tcr_id: uuid.UUID,
    user: User,
    ip_address: str | None = None,
) -> TCR:
    result = await db.execute(select(TCR).where(TCR.id == tcr_id))
    tcr = result.scalar_one_or_none()
    if tcr is None:
        raise ValidationError("TCR não encontrado")
    if tcr.status != StatusTCR.PENDENTE:
        raise ValidationError("TCR não está pendente de assinatura")

    # Substituir TCR anterior se houver
    if tcr.tcr_anterior_id:
        r2 = await db.execute(select(TCR).where(TCR.id == tcr.tcr_anterior_id))
        tcr_ant = r2.scalar_one_or_none()
        if tcr_ant and tcr_ant.status == StatusTCR.ATIVO:
            tcr_ant.status = StatusTCR.SUBSTITUIDO

    tcr.data_assinatura_chefia = datetime.utcnow()
    tcr.status = StatusTCR.ATIVO

    await log_audit(
        db,
        table_name="tcrs",
        record_id=str(tcr.id),
        action=AuditAction.UPDATE,
        user=user,
        old_values={"status": StatusTCR.PENDENTE.value},
        new_values={"status": StatusTCR.ATIVO.value},
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(tcr)
    return tcr


# ---------------------------------------------------------------------------
# CRUD — Convocacao
# ---------------------------------------------------------------------------


async def criar_convocacao(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    unidade_execucao_id: uuid.UUID,
    canal_comunicacao: str,
    data_convocacao: date,
    data_comparecimento_prevista: date,
    horario_comparecimento: str,
    local_comparecimento: str,
    periodo_presencial_inicio: date,
    periodo_presencial_fim: date,
    motivo: str,
    chefia_user_id: int | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> Convocacao:
    # Fetch TCR ativo to get prazo
    tcr = await get_tcr_ativo(db, participante_id)
    if tcr is None:
        raise ValidationError(
            "Participante não possui TCR ativo para emissão de convocação"
        )

    validate_prazo_antecedencia_convocacao(
        data_convocacao,
        data_comparecimento_prevista,
        tcr.prazo_antecedencia_convocacao_dias,
    )

    c = Convocacao(
        participante_id=participante_id,
        unidade_execucao_id=unidade_execucao_id,
        chefia_user_id=chefia_user_id,
        canal_comunicacao=canal_comunicacao,
        data_convocacao=data_convocacao,
        data_comparecimento_prevista=data_comparecimento_prevista,
        horario_comparecimento=horario_comparecimento,
        local_comparecimento=local_comparecimento,
        periodo_presencial_inicio=periodo_presencial_inicio,
        periodo_presencial_fim=periodo_presencial_fim,
        motivo=motivo,
        status=StatusConvocacao.PENDENTE,
    )
    db.add(c)
    await db.flush()
    email_res = await db.execute(
        select(Participante.email).where(Participante.id == participante_id)
    )
    p_email = email_res.scalar_one_or_none()
    await log_audit(
        db,
        table_name="convocacoes",
        record_id=str(c.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "participante_id": str(participante_id),
            "data_comparecimento_prevista": str(data_comparecimento_prevista),
        },
        ip_address=ip_address,
    )
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.CONVOCACAO_EMITIDA,
        conteudo=f"Você foi convocado para comparecer presencialmente em {data_comparecimento_prevista}.",
        destinatario_email=p_email,
        contexto={
            "data_comparecimento": str(data_comparecimento_prevista),
            "local": local_comparecimento,
            "motivo": motivo,
        },
    )
    await db.commit()
    await db.refresh(c)
    return c
