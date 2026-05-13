"""Tipos Strawberry e helpers de resolvers para Participante, TCR e Convocação (Sprints 1.2–1.4, 2.4)."""
import enum
from datetime import date, datetime, time
from typing import Optional

import strawberry

from ..models.participante import (
    MotivoDesligamento,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
    TipoAfastamento,
    TipoVinculo,
)
from .institucional import OrigemUnidadeGql


# ---------------------------------------------------------------------------
# Enums GraphQL
# ---------------------------------------------------------------------------


@strawberry.enum
class TipoVinculoGql(enum.Enum):
    EFETIVO = "efetivo"
    COMISSIONADO = "comissionado"
    EMPREGADO_PUBLICO = "empregado_publico"
    CONTRATO_DETERMINADO = "contrato_determinado"
    ESTAGIARIO = "estagiario"


@strawberry.enum
class RegimeExecucaoGql(enum.Enum):
    INTEGRAL = "integral"
    PARCIAL = "parcial"


@strawberry.enum
class MotivoDesligamentoGql(enum.Enum):
    A_PEDIDO = "a_pedido"
    INTERESSE_ADMINISTRACAO = "interesse_administracao"
    MUDANCA_UNIDADE = "mudanca_unidade"
    PGD_REVOGADO = "pgd_revogado"


@strawberry.enum
class StatusTCRGql(enum.Enum):
    PENDENTE = "pendente"
    ATIVO = "ativo"
    SUBSTITUIDO = "substituido"
    CANCELADO = "cancelado"


@strawberry.enum
class StatusConvocacaoGql(enum.Enum):
    PENDENTE = "pendente"
    ATENDIDA = "atendida"
    NAO_ATENDIDA = "nao_atendida"
    CANCELADA = "cancelada"


@strawberry.enum
class CriteriosPrioridadeGql(enum.Enum):
    PCD = "pcd"
    RESP_PCD = "responsavel_pcd"
    MOBILIDADE_REDUZIDA = "mobilidade_reduzida"
    HORARIO_ESPECIAL = "horario_especial"
    SEM_PRIORIDADE = "sem_prioridade"


@strawberry.enum
class TipoAfastamentoGql(enum.Enum):
    LICENCA_MEDICA = "licenca_medica"
    LICENCA_MATERNIDADE = "licenca_maternidade"
    FERIAS = "ferias"
    LICENCA_CAPACITACAO = "licenca_capacitacao"
    OUTROS = "outros"


# ---------------------------------------------------------------------------
# Types GraphQL
# ---------------------------------------------------------------------------


@strawberry.type
class ParticipanteType:
    id: strawberry.ID
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_lotacao: int
    matricula_siape: str
    cod_unidade_instituidora: int
    nome: str
    email: str
    situacao: int
    modalidade_execucao: int
    data_assinatura_tcr: date
    tipo_vinculo: TipoVinculoGql
    unidade_execucao_id: strawberry.ID
    cumpriu_estagio_probatorio: Optional[bool]
    data_desligamento: Optional[date]
    motivo_desligamento: Optional[MotivoDesligamentoGql]


@strawberry.type
class TCRType:
    id: strawberry.ID
    participante_id: strawberry.ID
    status: StatusTCRGql
    modalidade_execucao: int
    regime_execucao: RegimeExecucaoGql
    prazo_antecedencia_convocacao_dias: int
    canais_comunicacao: list[str]
    responsabilidades: str
    saldo_banco_horas: Optional[int]
    prazo_compensacao_banco_horas: Optional[date]


@strawberry.type
class ConvocacaoType:
    id: strawberry.ID
    participante_id: strawberry.ID
    unidade_execucao_id: strawberry.ID
    canal_comunicacao: str
    data_convocacao: date
    data_comparecimento_prevista: date
    horario_comparecimento: str
    local_comparecimento: str
    periodo_presencial_inicio: date
    periodo_presencial_fim: date
    motivo: str
    status: StatusConvocacaoGql


@strawberry.type
class ProcessoSelecaoType:
    id: strawberry.ID
    unidade_execucao_id: strawberry.ID
    criterios_tecnicos: str
    n_vagas: int
    resultado: strawberry.scalars.JSON
    created_at: datetime


@strawberry.type
class TermoGuardaEquipamentoType:
    id: strawberry.ID
    participante_id: strawberry.ID
    tcr_id: strawberry.ID
    descricao_equipamentos: str
    data_autorizacao: date


@strawberry.type
class AfastamentoType:
    id: strawberry.ID
    participante_id: strawberry.ID
    tipo_afastamento: TipoAfastamentoGql
    data_inicio: date
    data_fim: Optional[date]
    observacao: Optional[str]
    created_at: datetime


@strawberry.type
class AutorizacaoAdicionalNoturnoType:
    id: strawberry.ID
    participante_id: strawberry.ID
    data_inicio_autorizacao: date
    data_fim_autorizacao: Optional[date]
    horario_inicio_noturno: time
    horario_fim_noturno: time
    justificativa: Optional[str]
    autorizado_por_user_id: Optional[int]
    created_at: datetime


# ---------------------------------------------------------------------------
# Inputs GraphQL
# ---------------------------------------------------------------------------


@strawberry.input
class CadastrarParticipanteInput:
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_lotacao: int
    matricula_siape: str
    cod_unidade_instituidora: int
    cpf: str
    nome: str
    email: str
    modalidade_execucao: int
    data_assinatura_tcr: date
    tipo_vinculo: TipoVinculoGql
    unidade_execucao_id: strawberry.ID
    cumpriu_estagio_probatorio: Optional[bool] = None
    data_fim_estagio_probatorio: Optional[date] = None
    data_ingresso_pgd: Optional[date] = None


@strawberry.input
class PactuarTCRInput:
    modalidade_execucao: int
    regime_execucao: RegimeExecucaoGql
    prazo_antecedencia_convocacao_dias: int
    canais_comunicacao: list[str]
    responsabilidades: str
    ciencia_instalacoes_ergonomia: bool
    ciencia_nao_direito_adquirido: bool
    ciencia_custeio_estrutura: bool
    chefia_user_id: Optional[int] = None
    saldo_banco_horas: Optional[int] = None
    acoes_melhoria: Optional[str] = None
    tcr_anterior_id: Optional[strawberry.ID] = None


@strawberry.input
class CriarConvocacaoInput:
    canal_comunicacao: str
    data_convocacao: date
    data_comparecimento_prevista: date
    horario_comparecimento: str
    local_comparecimento: str
    periodo_presencial_inicio: date
    periodo_presencial_fim: date
    motivo: str
    chefia_user_id: Optional[int] = None


@strawberry.input
class CandidatoSelecaoInput:
    id: str
    nome: str
    criterio: CriteriosPrioridadeGql


@strawberry.input
class ConfirmarSelecaoInput:
    unidade_execucao_id: strawberry.ID
    candidatos: list[CandidatoSelecaoInput]
    n_vagas: int
    criterios_tecnicos: str


@strawberry.input
class RegistrarAutorizacaoEquipamentosInput:
    participante_id: strawberry.ID
    tcr_id: strawberry.ID
    descricao_equipamentos: str
    data_autorizacao: date
    modalidade_execucao: int


@strawberry.input
class RegistrarAfastamentoInput:
    participante_id: strawberry.ID
    tipo_afastamento: TipoAfastamentoGql
    data_inicio: date
    data_fim: Optional[date] = None
    observacao: Optional[str] = None


@strawberry.input
class AutorizarAdicionalNoturnoInput:
    participante_id: strawberry.ID
    data_inicio_autorizacao: date
    data_fim_autorizacao: Optional[date] = None
    horario_inicio_noturno: time = time(22, 0)
    horario_fim_noturno: time = time(5, 0)
    justificativa: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers de mapeamento ORM → GraphQL type
# ---------------------------------------------------------------------------


def _participante_to_type(p) -> ParticipanteType:  # type: ignore[no-untyped-def]
    return ParticipanteType(
        id=strawberry.ID(str(p.id)),
        origem_unidade=OrigemUnidadeGql(p.origem_unidade.value),
        cod_unidade_autorizadora=p.cod_unidade_autorizadora,
        cod_unidade_lotacao=p.cod_unidade_lotacao,
        matricula_siape=p.matricula_siape,
        cod_unidade_instituidora=p.cod_unidade_instituidora,
        nome=p.nome,
        email=p.email,
        situacao=p.situacao,
        modalidade_execucao=p.modalidade_execucao,
        data_assinatura_tcr=p.data_assinatura_tcr,
        tipo_vinculo=TipoVinculoGql(p.tipo_vinculo.value),
        unidade_execucao_id=strawberry.ID(str(p.unidade_execucao_id)),
        cumpriu_estagio_probatorio=p.cumpriu_estagio_probatorio,
        data_desligamento=p.data_desligamento,
        motivo_desligamento=(
            MotivoDesligamentoGql(p.motivo_desligamento.value)
            if p.motivo_desligamento
            else None
        ),
    )


def _tcr_to_type(tcr) -> TCRType:  # type: ignore[no-untyped-def]
    return TCRType(
        id=strawberry.ID(str(tcr.id)),
        participante_id=strawberry.ID(str(tcr.participante_id)),
        status=StatusTCRGql(tcr.status.value),
        modalidade_execucao=tcr.modalidade_execucao,
        regime_execucao=RegimeExecucaoGql(tcr.regime_execucao.value),
        prazo_antecedencia_convocacao_dias=tcr.prazo_antecedencia_convocacao_dias,
        canais_comunicacao=tcr.canais_comunicacao or [],
        responsabilidades=tcr.responsabilidades,
        saldo_banco_horas=tcr.saldo_banco_horas,
        prazo_compensacao_banco_horas=tcr.prazo_compensacao_banco_horas,
    )


def _convocacao_to_type(c) -> ConvocacaoType:  # type: ignore[no-untyped-def]
    return ConvocacaoType(
        id=strawberry.ID(str(c.id)),
        participante_id=strawberry.ID(str(c.participante_id)),
        unidade_execucao_id=strawberry.ID(str(c.unidade_execucao_id)),
        canal_comunicacao=c.canal_comunicacao,
        data_convocacao=c.data_convocacao,
        data_comparecimento_prevista=c.data_comparecimento_prevista,
        horario_comparecimento=c.horario_comparecimento,
        local_comparecimento=c.local_comparecimento,
        periodo_presencial_inicio=c.periodo_presencial_inicio,
        periodo_presencial_fim=c.periodo_presencial_fim,
        motivo=c.motivo,
        status=StatusConvocacaoGql(c.status.value),
    )


def _processo_selecao_to_type(ps) -> ProcessoSelecaoType:  # type: ignore[no-untyped-def]
    return ProcessoSelecaoType(
        id=strawberry.ID(str(ps.id)),
        unidade_execucao_id=strawberry.ID(str(ps.unidade_execucao_id)),
        criterios_tecnicos=ps.criterios_tecnicos,
        n_vagas=ps.n_vagas,
        resultado=ps.resultado,
        created_at=ps.created_at,
    )


def _termo_guarda_to_type(t) -> TermoGuardaEquipamentoType:  # type: ignore[no-untyped-def]
    return TermoGuardaEquipamentoType(
        id=strawberry.ID(str(t.id)),
        participante_id=strawberry.ID(str(t.participante_id)),
        tcr_id=strawberry.ID(str(t.tcr_id)),
        descricao_equipamentos=t.descricao_equipamentos,
        data_autorizacao=t.data_autorizacao,
    )


def _afastamento_to_type(a) -> AfastamentoType:  # type: ignore[no-untyped-def]
    return AfastamentoType(
        id=strawberry.ID(str(a.id)),
        participante_id=strawberry.ID(str(a.participante_id)),
        tipo_afastamento=TipoAfastamentoGql(a.tipo_afastamento.value),
        data_inicio=a.data_inicio,
        data_fim=a.data_fim,
        observacao=a.observacao,
        created_at=a.created_at,
    )


def _autorizacao_noturna_to_type(a) -> AutorizacaoAdicionalNoturnoType:  # type: ignore[no-untyped-def]
    return AutorizacaoAdicionalNoturnoType(
        id=strawberry.ID(str(a.id)),
        participante_id=strawberry.ID(str(a.participante_id)),
        data_inicio_autorizacao=a.data_inicio_autorizacao,
        data_fim_autorizacao=a.data_fim_autorizacao,
        horario_inicio_noturno=a.horario_inicio_noturno,
        horario_fim_noturno=a.horario_fim_noturno,
        justificativa=a.justificativa,
        autorizado_por_user_id=a.autorizado_por_user_id,
        created_at=a.created_at,
    )
