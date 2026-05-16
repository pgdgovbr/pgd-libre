"""Tipos Strawberry e helpers de resolvers para PlanoEntregas, PlanoTrabalho,
Contribuição e Avaliação (Sprints 1.3–1.5)."""

import enum
from datetime import date, datetime

import strawberry

from .institucional import OrigemUnidadeGql

# ---------------------------------------------------------------------------
# Enums GraphQL
# ---------------------------------------------------------------------------


@strawberry.enum
class TipoMetaGql(enum.Enum):
    UNIDADE = "unidade"
    PERCENTUAL = "percentual"


@strawberry.enum
class DecisaoRecursoGql(enum.Enum):
    ACATADO = "acatado"
    NAO_ACATADO = "nao_acatado"


@strawberry.enum
class StatusRecursoGql(enum.Enum):
    ABERTO = "aberto"
    ENCERRADO = "encerrado"


# ---------------------------------------------------------------------------
# Types GraphQL
# ---------------------------------------------------------------------------


@strawberry.type
class PlanoEntregasType:
    id: strawberry.ID
    id_plano_entregas: str
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_instituidora: int
    cod_unidade_executora: int
    unidade_execucao_id: strawberry.ID
    status: int
    data_inicio: date
    data_termino: date
    avaliacao: int | None
    data_avaliacao: date | None
    aprovado_por_user_id: int | None
    data_aprovacao: date | None


@strawberry.type
class EntregaType:
    id: strawberry.ID
    id_entrega: str
    plano_entregas_id: strawberry.ID
    nome_entrega: str
    meta_entrega: int
    tipo_meta: TipoMetaGql
    data_entrega: date
    nome_unidade_demandante: str
    nome_unidade_destinataria: str
    entrega_cancelada: bool


@strawberry.type
class PlanoTrabalhoType:
    id: strawberry.ID
    id_plano_trabalho: str
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_executora: int
    cod_unidade_lotacao_participante: int
    participante_id: strawberry.ID
    tcr_id: strawberry.ID
    status: int
    data_inicio: date
    data_termino: date
    carga_horaria_disponivel: int
    criterios_avaliacao: str
    plano_entregas_id: strawberry.ID | None
    contribuicoes: list["ContribuicaoType"]
    avaliacoes: list["AvaliacaoType"]


@strawberry.type
class ContribuicaoType:
    id: strawberry.ID
    id_contribuicao: str
    plano_trabalho_id: strawberry.ID
    tipo_contribuicao: int
    percentual_contribuicao: int
    descricao: str
    id_plano_entregas: str | None
    id_entrega: str | None
    rotulo: str | None


@strawberry.type
class AvaliacaoType:
    id: strawberry.ID
    id_periodo_avaliativo: str
    plano_trabalho_id: strawberry.ID
    data_inicio_periodo_avaliativo: date
    data_fim_periodo_avaliativo: date
    descricao_execucao: str | None
    ocorrencias: str | None
    data_registro_participante: datetime | None
    avaliacao_registros_execucao: int | None
    data_avaliacao_registros_execucao: date | None
    avaliacao_justificativa: str | None
    horas_inexecucao: int | None
    status_recurso: StatusRecursoGql | None
    recurso_texto: str | None
    recurso_data: datetime | None
    recurso_decisao: DecisaoRecursoGql | None
    recurso_decisao_justificativa: str | None
    recurso_decisao_data: datetime | None


# ---------------------------------------------------------------------------
# Inputs GraphQL
# ---------------------------------------------------------------------------


@strawberry.input
class CriarPlanoEntregasInput:
    id_plano_entregas: str
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_instituidora: int
    cod_unidade_executora: int
    unidade_execucao_id: strawberry.ID
    data_inicio: date
    data_termino: date


@strawberry.input
class CriarEntregaInput:
    id_entrega: str
    nome_entrega: str
    meta_entrega: int
    tipo_meta: TipoMetaGql
    data_entrega: date
    nome_unidade_demandante: str
    nome_unidade_destinataria: str


@strawberry.input
class CriarPlanoTrabalhoInput:
    id_plano_trabalho: str
    origem_unidade: OrigemUnidadeGql
    cod_unidade_autorizadora: int
    cod_unidade_executora: int
    cod_unidade_lotacao_participante: int
    cpf_participante: str
    matricula_siape: str
    data_inicio: date
    data_termino: date
    carga_horaria_disponivel: int
    criterios_avaliacao: str
    plano_entregas_id: strawberry.ID | None = None


@strawberry.input
class AdicionarContribuicaoInput:
    id_contribuicao: str
    tipo_contribuicao: int
    percentual_contribuicao: int
    descricao: str
    id_plano_entregas: str | None = None
    id_entrega: str | None = None
    rotulo: str | None = None


@strawberry.input
class AprovarPlanoEntregasInput:
    plano_id: strawberry.ID
    aprovador_user_id: int


@strawberry.input
class RegistrarExecucaoInput:
    id_periodo_avaliativo: str
    data_inicio_periodo_avaliativo: date
    data_fim_periodo_avaliativo: date
    descricao_execucao: str | None = None
    ocorrencias: str | None = None


# ---------------------------------------------------------------------------
# Helpers de mapeamento ORM → GraphQL type
# ---------------------------------------------------------------------------


def _pe_to_type(pe) -> PlanoEntregasType:  # type: ignore[no-untyped-def]
    return PlanoEntregasType(
        id=strawberry.ID(str(pe.id)),
        id_plano_entregas=pe.id_plano_entregas,
        origem_unidade=OrigemUnidadeGql(pe.origem_unidade.value),
        cod_unidade_autorizadora=pe.cod_unidade_autorizadora,
        cod_unidade_instituidora=pe.cod_unidade_instituidora,
        cod_unidade_executora=pe.cod_unidade_executora,
        unidade_execucao_id=strawberry.ID(str(pe.unidade_execucao_id)),
        status=pe.status,
        data_inicio=pe.data_inicio,
        data_termino=pe.data_termino,
        avaliacao=pe.avaliacao,
        data_avaliacao=pe.data_avaliacao,
        aprovado_por_user_id=pe.aprovado_por_user_id,
        data_aprovacao=pe.data_aprovacao,
    )


def _entrega_to_type(e) -> EntregaType:  # type: ignore[no-untyped-def]
    return EntregaType(
        id=strawberry.ID(str(e.id)),
        id_entrega=e.id_entrega,
        plano_entregas_id=strawberry.ID(str(e.plano_entregas_id)),
        nome_entrega=e.nome_entrega,
        meta_entrega=e.meta_entrega,
        tipo_meta=TipoMetaGql(e.tipo_meta.value),
        data_entrega=e.data_entrega,
        nome_unidade_demandante=e.nome_unidade_demandante,
        nome_unidade_destinataria=e.nome_unidade_destinataria,
        entrega_cancelada=e.entrega_cancelada,
    )


def _contribuicao_to_type(c) -> ContribuicaoType:  # type: ignore[no-untyped-def]
    return ContribuicaoType(
        id=strawberry.ID(str(c.id)),
        id_contribuicao=c.id_contribuicao,
        plano_trabalho_id=strawberry.ID(str(c.plano_trabalho_id)),
        tipo_contribuicao=c.tipo_contribuicao,
        percentual_contribuicao=c.percentual_contribuicao,
        descricao=c.descricao,
        id_plano_entregas=c.id_plano_entregas,
        id_entrega=c.id_entrega,
        rotulo=c.rotulo,
    )


def _pt_to_type(pt) -> PlanoTrabalhoType:  # type: ignore[no-untyped-def]
    # Use __dict__ to avoid triggering lazy load outside of async context
    raw_contribs = pt.__dict__.get("contribuicoes") or []
    contribuicoes = [_contribuicao_to_type(c) for c in raw_contribs]
    raw_avaliacoes = pt.__dict__.get("avaliacoes") or []
    avaliacoes = [_avaliacao_to_type(a) for a in raw_avaliacoes]
    return PlanoTrabalhoType(
        id=strawberry.ID(str(pt.id)),
        id_plano_trabalho=pt.id_plano_trabalho,
        origem_unidade=OrigemUnidadeGql(pt.origem_unidade.value),
        cod_unidade_autorizadora=pt.cod_unidade_autorizadora,
        cod_unidade_executora=pt.cod_unidade_executora,
        cod_unidade_lotacao_participante=pt.cod_unidade_lotacao_participante,
        participante_id=strawberry.ID(str(pt.participante_id)),
        tcr_id=strawberry.ID(str(pt.tcr_id)),
        status=pt.status,
        data_inicio=pt.data_inicio,
        data_termino=pt.data_termino,
        carga_horaria_disponivel=pt.carga_horaria_disponivel,
        criterios_avaliacao=pt.criterios_avaliacao,
        plano_entregas_id=(
            strawberry.ID(str(pt.plano_entregas_id)) if pt.plano_entregas_id else None
        ),
        contribuicoes=contribuicoes,
        avaliacoes=avaliacoes,
    )


def _avaliacao_to_type(a) -> AvaliacaoType:  # type: ignore[no-untyped-def]
    return AvaliacaoType(
        id=strawberry.ID(str(a.id)),
        id_periodo_avaliativo=a.id_periodo_avaliativo,
        plano_trabalho_id=strawberry.ID(str(a.plano_trabalho_id)),
        data_inicio_periodo_avaliativo=a.data_inicio_periodo_avaliativo,
        data_fim_periodo_avaliativo=a.data_fim_periodo_avaliativo,
        descricao_execucao=a.descricao_execucao,
        ocorrencias=a.ocorrencias,
        data_registro_participante=a.data_registro_participante,
        avaliacao_registros_execucao=a.avaliacao_registros_execucao,
        data_avaliacao_registros_execucao=a.data_avaliacao_registros_execucao,
        avaliacao_justificativa=a.avaliacao_justificativa,
        horas_inexecucao=a.horas_inexecucao,
        status_recurso=(StatusRecursoGql(a.status_recurso.value) if a.status_recurso else None),
        recurso_texto=a.recurso_texto,
        recurso_data=a.recurso_data,
        recurso_decisao=(DecisaoRecursoGql(a.recurso_decisao.value) if a.recurso_decisao else None),
        recurso_decisao_justificativa=a.recurso_decisao_justificativa,
        recurso_decisao_data=a.recurso_decisao_data,
    )
