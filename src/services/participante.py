import uuid
from dataclasses import dataclass
from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction
from ..models.institucional import OrigemUnidade
from ..models.notificacao import TipoEvento
from ..models.participante import (
    TCR,
    Afastamento,
    AutorizacaoAdicionalNoturno,
    Convocacao,
    CriteriosPrioridade,
    MotivoDesligamento,
    Participante,
    ProcessoSelecao,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
    TermoGuardaEquipamento,
    TipoAfastamento,
    TipoVinculo,
)
from ..models.user import User
from .audit import log_audit
from .institucional import ValidationError
from .notificacao import criar_notificacao

MIN_DATA_ASSINATURA_TCR = date(2023, 7, 31)

# ---------------------------------------------------------------------------
# Seleção com critérios de prioridade (RF-006)
# ---------------------------------------------------------------------------

ORDEM_PRIORIDADE: dict[CriteriosPrioridade, int] = {
    CriteriosPrioridade.PCD: 0,
    CriteriosPrioridade.RESP_PCD: 1,
    CriteriosPrioridade.MOBILIDADE_REDUZIDA: 2,
    CriteriosPrioridade.HORARIO_ESPECIAL: 3,
    CriteriosPrioridade.SEM_PRIORIDADE: 4,
}


@dataclass
class CandidatoSelecao:
    id: str
    nome: str
    criterio: CriteriosPrioridade


def ordenar_candidatos(
    candidatos: list[CandidatoSelecao], n_vagas: int
) -> tuple[list[CandidatoSelecao], list[CandidatoSelecao]]:
    """Ordena candidatos pelas prioridades legais e separa em selecionados/não selecionados."""
    ordenados = sorted(candidatos, key=lambda c: ORDEM_PRIORIDADE[c.criterio])
    return ordenados[:n_vagas], ordenados[n_vagas:]


async def confirmar_selecao(
    db: AsyncSession,
    *,
    unidade_execucao_id: uuid.UUID,
    candidatos: list[CandidatoSelecao],
    n_vagas: int,
    criterios_tecnicos: str,
    user: User | None = None,
    ip_address: str | None = None,
) -> ProcessoSelecao:
    if not criterios_tecnicos or not criterios_tecnicos.strip():
        raise ValidationError(
            "Critérios técnicos de adesão são obrigatórios para garantir seleção impessoal"
            " (D11 Art.7º §2º)"
        )
    selecionados, nao_selecionados = ordenar_candidatos(candidatos, n_vagas)
    resultado = [
        {"id": c.id, "nome": c.nome, "criterio": c.criterio.value, "selecionado": True}
        for c in selecionados
    ] + [
        {"id": c.id, "nome": c.nome, "criterio": c.criterio.value, "selecionado": False}
        for c in nao_selecionados
    ]
    processo = ProcessoSelecao(
        unidade_execucao_id=unidade_execucao_id,
        criterios_tecnicos=criterios_tecnicos,
        n_vagas=n_vagas,
        resultado=resultado,
        realizado_por_user_id=user.id if user else None,
    )
    db.add(processo)
    await db.flush()
    await log_audit(
        db,
        table_name="processos_selecao",
        record_id=str(processo.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "criterios_tecnicos": criterios_tecnicos,
            "n_vagas": n_vagas,
            "unidade_execucao_id": str(unidade_execucao_id),
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(processo)
    return processo


# ---------------------------------------------------------------------------
# Banco de horas (RF-020)
# ---------------------------------------------------------------------------


def bloquear_adesao_banco_horas(participante_situacao: int) -> None:
    """Participantes do PGD (situacao=1) não podem aderir ao banco de horas."""
    if participante_situacao == 1:
        raise ValidationError(
            "Participantes do PGD não podem aderir ao banco de horas (IN52 Art.18)"
        )


# ---------------------------------------------------------------------------
# Compensação de carga horária — consulta pendência (RF-019)
# ---------------------------------------------------------------------------


async def get_carga_compensacao_pendente(db: AsyncSession, participante_id: uuid.UUID) -> int:
    """Retorna horas de compensação pendentes do último plano com inexecução."""
    from ..models.plano import AvaliacaoRegistrosExecucao, PlanoTrabalho

    result = await db.execute(
        select(AvaliacaoRegistrosExecucao)
        .join(
            PlanoTrabalho,
            AvaliacaoRegistrosExecucao.plano_trabalho_id == PlanoTrabalho.id,
        )
        .where(
            PlanoTrabalho.participante_id == participante_id,
            AvaliacaoRegistrosExecucao.avaliacao_registros_execucao.in_([4, 5]),
            AvaliacaoRegistrosExecucao.horas_inexecucao.isnot(None),
            AvaliacaoRegistrosExecucao.horas_inexecucao > 0,
        )
        .order_by(AvaliacaoRegistrosExecucao.data_fim_periodo_avaliativo.desc())
    )
    avaliacao = result.scalars().first()
    if avaliacao is None:
        return 0

    tcr_result = await db.execute(
        select(TCR).where(
            TCR.participante_id == participante_id,
            TCR.carga_horaria_compensacao.isnot(None),
            TCR.carga_horaria_compensacao > 0,
            TCR.created_at > avaliacao.data_avaliacao_registros_execucao,
        )
    )
    if tcr_result.scalars().first() is not None:
        return 0

    return avaliacao.horas_inexecucao or 0


# ---------------------------------------------------------------------------
# Equipamentos (RF-032)
# ---------------------------------------------------------------------------


async def registrar_autorizacao_equipamentos(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    tcr_id: uuid.UUID,
    descricao_equipamentos: str,
    data_autorizacao: date,
    modalidade_execucao: int,
    user: User | None = None,
    ip_address: str | None = None,
) -> TermoGuardaEquipamento:
    if modalidade_execucao != 3:
        raise ValidationError(
            "Retirada de equipamentos permitida apenas para teletrabalho integral (IN24 Art.16)"
        )
    termo = TermoGuardaEquipamento(
        participante_id=participante_id,
        tcr_id=tcr_id,
        descricao_equipamentos=descricao_equipamentos,
        data_autorizacao=data_autorizacao,
        autorizado_por_user_id=user.id if user else None,
    )
    db.add(termo)
    await db.flush()
    await log_audit(
        db,
        table_name="termos_guarda_equipamento",
        record_id=str(termo.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "participante_id": str(participante_id),
            "tcr_id": str(tcr_id),
            "data_autorizacao": str(data_autorizacao),
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(termo)
    return termo


# ---------------------------------------------------------------------------
# Afastamentos legais (TC-M10-008)
# ---------------------------------------------------------------------------


async def registrar_afastamento(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    tipo_afastamento: TipoAfastamento,
    data_inicio: date,
    data_fim: date | None = None,
    observacao: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> Afastamento:
    if data_fim is not None and data_fim < data_inicio:
        raise ValidationError("Data fim do afastamento não pode ser anterior à data de início")
    afa = Afastamento(
        participante_id=participante_id,
        tipo_afastamento=tipo_afastamento,
        data_inicio=data_inicio,
        data_fim=data_fim,
        observacao=observacao,
        registrado_por_user_id=user.id if user else None,
    )
    db.add(afa)
    await db.flush()
    await log_audit(
        db,
        table_name="afastamentos",
        record_id=str(afa.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "participante_id": str(participante_id),
            "tipo_afastamento": tipo_afastamento.value,
            "data_inicio": str(data_inicio),
            "data_fim": str(data_fim) if data_fim else None,
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(afa)
    return afa


# ---------------------------------------------------------------------------
# Adicional noturno (TC-M10-005/006)
# ---------------------------------------------------------------------------


async def autorizar_adicional_noturno(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    data_inicio_autorizacao: date,
    data_fim_autorizacao: date | None = None,
    horario_inicio_noturno: time = time(22, 0),
    horario_fim_noturno: time = time(5, 0),
    justificativa: str | None = None,
    user: User,
    ip_address: str | None = None,
) -> AutorizacaoAdicionalNoturno:
    if data_fim_autorizacao is not None and data_fim_autorizacao < data_inicio_autorizacao:
        raise ValidationError("Data fim da autorização não pode ser anterior à data de início")
    auth = AutorizacaoAdicionalNoturno(
        participante_id=participante_id,
        data_inicio_autorizacao=data_inicio_autorizacao,
        data_fim_autorizacao=data_fim_autorizacao,
        horario_inicio_noturno=horario_inicio_noturno,
        horario_fim_noturno=horario_fim_noturno,
        justificativa=justificativa,
        autorizado_por_user_id=user.id if user else None,
    )
    db.add(auth)
    await db.flush()
    await log_audit(
        db,
        table_name="autorizacoes_adicional_noturno",
        record_id=str(auth.id),
        action=AuditAction.CREATE,
        user=user,
        new_values={
            "participante_id": str(participante_id),
            "data_inicio_autorizacao": str(data_inicio_autorizacao),
            "data_fim_autorizacao": (str(data_fim_autorizacao) if data_fim_autorizacao else None),
        },
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(auth)
    return auth


async def validate_adicional_noturno_autorizado(
    db: AsyncSession,
    *,
    participante_id: uuid.UUID,
    trabalho_noturno: bool,
    data_inicio_pt: date,
    data_termino_pt: date,
) -> None:
    """Verifica se existe autorização cobrindo todo o período do PT.

    Uma autorização "cobre" o período do PT quando:
      - data_inicio_autorizacao <= data_inicio_pt
      - data_fim_autorizacao is NULL OR data_fim_autorizacao >= data_termino_pt
    """
    if not trabalho_noturno:
        return
    from sqlalchemy import or_

    q = select(AutorizacaoAdicionalNoturno).where(
        AutorizacaoAdicionalNoturno.participante_id == participante_id,
        AutorizacaoAdicionalNoturno.data_inicio_autorizacao <= data_inicio_pt,
        or_(
            AutorizacaoAdicionalNoturno.data_fim_autorizacao.is_(None),
            AutorizacaoAdicionalNoturno.data_fim_autorizacao >= data_termino_pt,
        ),
    )
    result = await db.execute(q)
    if result.scalars().first() is None:
        raise ValidationError(
            "Plano de Trabalho com trabalho noturno requer autorização prévia"
            " da chefia (IN24 Art.14)"
        )


# ---------------------------------------------------------------------------
# Acumulação de cargos — validação da declaração (RF-033)
# ---------------------------------------------------------------------------


def validate_acumulacao_cargos_declaracao(
    acumula_cargos: bool,
    declaracao_plano: bool,
    declaracao_comparecer: bool,
    declaracao_contato: bool,
    declaracao_sincrono: bool,
) -> None:
    if not acumula_cargos:
        return
    if not all(
        [
            declaracao_plano,
            declaracao_comparecer,
            declaracao_contato,
            declaracao_sincrono,
        ]
    ):
        raise ValidationError(
            "Declaração de ausência de prejuízo obrigatória para acumuladores de cargos"
            " (IN52 Art.19)"
        )


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
                "Teletrabalho exige cumprimento de 1 ano de estágio probatório (IN24 Art.10 §2º)"
            )


def validate_data_assinatura_tcr_minima(data: date) -> None:
    if data < MIN_DATA_ASSINATURA_TCR:
        raise ValidationError(
            "Data de assinatura do TCR anterior ao início da vigência do Decreto 11.072/2022"
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


async def _count_tt_exterior(db: AsyncSession, unidade_execucao_id: uuid.UUID) -> tuple[int, int]:
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


async def get_participante(db: AsyncSession, participante_id: uuid.UUID) -> Participante | None:
    result = await db.execute(select(Participante).where(Participante.id == participante_id))
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

    result = await db.execute(select(Participante).where(Participante.id == participante_id))
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
    carga_horaria_compensacao: int | None = None,
    prazo_compensacao_inexecucao: date | None = None,
    acoes_melhoria: str | None = None,
    tcr_anterior_id: uuid.UUID | None = None,
    user: User | None = None,
    ip_address: str | None = None,
) -> TCR:
    if carga_horaria_compensacao and carga_horaria_compensacao > 0:
        if prazo_compensacao_inexecucao is None:
            raise ValidationError(
                "Prazo de compensação de inexecução obrigatório quando há carga horária"
                " a compensar (IN52 Art.4º §único)"
            )

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
        carga_horaria_compensacao=carga_horaria_compensacao,
        prazo_compensacao_inexecucao=prazo_compensacao_inexecucao,
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
        new_values={
            "participante_id": str(participante_id),
            "status": StatusTCR.PENDENTE.value,
        },
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
        raise ValidationError("Participante não possui TCR ativo para emissão de convocação")

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
