"""Tipos Strawberry e helpers de resolvers para o módulo Institucional (Sprint 1.1)."""
import enum
import uuid
from datetime import date, datetime
from typing import Optional

import strawberry

from ..models.institucional import Competencia, OrigemUnidade, StatusAto, StatusPgd


# ---------------------------------------------------------------------------
# Enums GraphQL
# ---------------------------------------------------------------------------


@strawberry.enum
class OrigemUnidadeGql(enum.Enum):
    SIAPE = "SIAPE"
    SIORG = "SIORG"


@strawberry.enum
class StatusAtoGql(enum.Enum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"
    REVOGADO = "revogado"


@strawberry.enum
class StatusPgdGql(enum.Enum):
    EM_VIGOR = "em_vigor"
    SUSPENSO = "suspenso"
    REVOGADO = "revogado"


@strawberry.enum
class CompetenciaGql(enum.Enum):
    APROVAR_PLANO_ENTREGAS = "aprovar_plano_entregas"
    REALIZAR_SELECAO = "realizar_selecao"
    AVALIAR_REGISTROS = "avaliar_registros"


# ---------------------------------------------------------------------------
# Types GraphQL
# ---------------------------------------------------------------------------


@strawberry.type
class UnidadeAutorizadoraType:
    id: strawberry.ID
    cod_unidade_autorizadora: int
    origem_unidade: OrigemUnidadeGql
    nome: str
    sigla: str
    pgd_autorizado: bool


@strawberry.type
class AtoAutorizacaoType:
    id: strawberry.ID
    unidade_autorizadora_id: strawberry.ID
    autoridade: str
    data_publicacao: date
    referencia: str
    status: StatusAtoGql


@strawberry.type
class UnidadeInstituidoraType:
    id: strawberry.ID
    unidade_autorizadora_id: strawberry.ID
    cod_unidade_instituidora: int
    nome: str
    sigla: str
    ato_instituicao_ref: str
    data_instituicao: date
    status: StatusPgdGql
    conteudo_minimo_tcr: str
    prazo_antecedencia_convocacao_dias: int
    nivel_produtividade_adicional_tt: Optional[str]


@strawberry.type
class ResultadoPublicoType:
    cod_unidade_executora: int
    nome: str
    total_planos_avaliados: int
    media_avaliacao: Optional[float]


# ---------------------------------------------------------------------------
# Inputs GraphQL
# ---------------------------------------------------------------------------


@strawberry.input
class CriarUnidadeAutorizadoraInput:
    cod_unidade_autorizadora: int
    origem_unidade: OrigemUnidadeGql
    nome: str
    sigla: str


@strawberry.input
class CriarAtoAutorizacaoInput:
    autoridade: str
    data_publicacao: date
    referencia: str


@strawberry.input
class CriarUnidadeInstituidoraInput:
    cod_unidade_instituidora: int
    nome: str
    sigla: str
    ato_instituicao_ref: str
    data_instituicao: date
    tipos_atividades: str
    modalidades_autorizadas: list[int]
    conteudo_minimo_tcr: str
    prazo_antecedencia_convocacao_dias: int
    vagas_percentual_presencial: Optional[int] = None
    vagas_percentual_tt_parcial: Optional[int] = None
    vagas_percentual_tt_integral: Optional[int] = None
    vagas_percentual_tt_exterior: Optional[int] = None
    nivel_produtividade_adicional_tt: Optional[str] = None
    vedacoes_participacao: Optional[str] = None
    criterios_selecao_adicionais: Optional[str] = None
    procedimento_registro_comparecimento: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers de mapeamento ORM → GraphQL type
# ---------------------------------------------------------------------------


def _ua_to_type(ua) -> UnidadeAutorizadoraType:  # type: ignore[no-untyped-def]
    return UnidadeAutorizadoraType(
        id=strawberry.ID(str(ua.id)),
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        origem_unidade=OrigemUnidadeGql(ua.origem_unidade.value),
        nome=ua.nome,
        sigla=ua.sigla,
        pgd_autorizado=ua.pgd_autorizado,
    )


def _ato_to_type(ato) -> AtoAutorizacaoType:  # type: ignore[no-untyped-def]
    return AtoAutorizacaoType(
        id=strawberry.ID(str(ato.id)),
        unidade_autorizadora_id=strawberry.ID(str(ato.unidade_autorizadora_id)),
        autoridade=ato.autoridade,
        data_publicacao=ato.data_publicacao,
        referencia=ato.referencia,
        status=StatusAtoGql(ato.status.value),
    )


def _ui_to_type(ui) -> UnidadeInstituidoraType:  # type: ignore[no-untyped-def]
    return UnidadeInstituidoraType(
        id=strawberry.ID(str(ui.id)),
        unidade_autorizadora_id=strawberry.ID(str(ui.unidade_autorizadora_id)),
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        nome=ui.nome,
        sigla=ui.sigla,
        ato_instituicao_ref=ui.ato_instituicao_ref,
        data_instituicao=ui.data_instituicao,
        status=StatusPgdGql(ui.status.value),
        conteudo_minimo_tcr=ui.conteudo_minimo_tcr,
        prazo_antecedencia_convocacao_dias=ui.prazo_antecedencia_convocacao_dias,
        nivel_produtividade_adicional_tt=ui.nivel_produtividade_adicional_tt,
    )


# ---------------------------------------------------------------------------
# Sprint 2.8 — Delegação de competência (RF-037)
# ---------------------------------------------------------------------------


@strawberry.type
class DelegacaoCompetenciaType:
    id: strawberry.ID
    delegante_user_id: int
    delegatario_user_id: int
    competencia: CompetenciaGql
    unidade_execucao_id: Optional[strawberry.ID]
    data_inicio: date
    data_fim: Optional[date]
    motivo: Optional[str]
    ativo: bool
    created_at: datetime


@strawberry.input
class DelegarCompetenciaInput:
    delegatario_user_id: int
    competencia: CompetenciaGql
    data_inicio: date
    data_fim: Optional[date] = None
    unidade_execucao_id: Optional[strawberry.ID] = None
    motivo: Optional[str] = None


def _delegacao_to_type(d) -> DelegacaoCompetenciaType:  # type: ignore[no-untyped-def]
    return DelegacaoCompetenciaType(
        id=strawberry.ID(str(d.id)),
        delegante_user_id=d.delegante_user_id,
        delegatario_user_id=d.delegatario_user_id,
        competencia=CompetenciaGql(d.competencia.value),
        unidade_execucao_id=(
            strawberry.ID(str(d.unidade_execucao_id))
            if d.unidade_execucao_id
            else None
        ),
        data_inicio=d.data_inicio,
        data_fim=d.data_fim,
        motivo=d.motivo,
        ativo=d.ativo,
        created_at=d.created_at,
    )
