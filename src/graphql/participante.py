"""Tipos Strawberry e helpers de resolvers para Participante, TCR e Convocação (Sprints 1.2–1.4)."""
import enum
from datetime import date
from typing import Optional

import strawberry

from ..models.participante import (
    MotivoDesligamento,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
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
