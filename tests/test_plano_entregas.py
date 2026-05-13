"""Sprint 1.3 — Plano de Entregas: service tests (TC-M03)."""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.plano import (
    STATUS_PE_APROVADO,
    STATUS_PE_AVALIADO,
    STATUS_PE_CANCELADO,
    STATUS_PE_CONCLUIDO,
    STATUS_PE_EM_EXECUCAO,
    TipoMeta,
)
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.plano_entregas import (
    avaliar_pe,
    cancelar_pe,
    concluir_pe,
    criar_entrega,
    criar_plano_entregas,
    iniciar_execucao_pe,
    validate_duracao_maxima_pe,
    validate_sem_sobreposicao_pe,
)

from httpx import AsyncClient

from .conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def test_validate_duracao_maxima_ok():
    validate_duracao_maxima_pe(date(2024, 1, 1), date(2024, 12, 31))  # no exception


def test_validate_duracao_maxima_exatamente_1_ano():
    validate_duracao_maxima_pe(date(2024, 1, 1), date(2025, 1, 1))  # no exception


def test_validate_duracao_maxima_excede():
    with pytest.raises(ValidationError, match="1 ano"):
        validate_duracao_maxima_pe(date(2024, 1, 1), date(2025, 1, 2))


def test_validate_duracao_termino_antes_inicio():
    with pytest.raises(ValidationError, match="data_termino"):
        validate_duracao_maxima_pe(date(2024, 6, 1), date(2024, 1, 1))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _make_unidade_execucao(db, admin):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Min PE",
        sigla="MPE",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="Port.",
        user=admin,
    )
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=100,
        nome="UI PE",
        sigla="UIPE",
        ato_instituicao_ref="Port. 2",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    from src.models.institucional import UnidadeExecucao

    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=200,
        nome="UE PE",
        sigla="UPE",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ue


async def _criar_pe(db, admin, ue, cod=1, data_inicio=date(2024, 1, 1), data_termino=date(2024, 12, 31)):
    ua_result = await db.execute(
        __import__("sqlalchemy").select(
            __import__("src.models.institucional", fromlist=["UnidadeAutorizadora"]).UnidadeAutorizadora
        ).limit(1)
    )
    from src.models.institucional import UnidadeAutorizadora
    from sqlalchemy import select
    ua = (await db.execute(select(UnidadeAutorizadora).limit(1))).scalar_one()
    return await criar_plano_entregas(
        db,
        id_plano_entregas=f"PE-{cod}",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=data_inicio,
        data_termino=data_termino,
        user=admin,
    )


# ---------------------------------------------------------------------------
# Service — PlanoEntregas CRUD
# ---------------------------------------------------------------------------


async def test_criar_plano_entregas_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 12, 31),
        user=admin,
    )
    assert pe.id is not None
    assert pe.status == STATUS_PE_APROVADO


async def test_criar_plano_entregas_duracao_invalida(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    with pytest.raises(ValidationError, match="1 ano"):
        await criar_plano_entregas(
            db,
            id_plano_entregas="PE-X",
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_instituidora=100,
            cod_unidade_executora=200,
            unidade_execucao_id=ue.id,
            data_inicio=date(2024, 1, 1),
            data_termino=date(2025, 6, 1),
            user=admin,
        )


async def test_criar_plano_entregas_sobreposicao(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    await criar_plano_entregas(
        db,
        id_plano_entregas="PE-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 12, 31),
        user=admin,
    )
    with pytest.raises(ValidationError, match="período"):
        await criar_plano_entregas(
            db,
            id_plano_entregas="PE-002",
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_instituidora=100,
            cod_unidade_executora=200,
            unidade_execucao_id=ue.id,
            data_inicio=date(2024, 6, 1),
            data_termino=date(2024, 12, 31),
            user=admin,
        )


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


async def test_maquina_estados_pe(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-SM",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
        user=admin,
    )
    assert pe.status == STATUS_PE_APROVADO

    pe = await iniciar_execucao_pe(db, plano_id=pe.id, user=admin)
    assert pe.status == STATUS_PE_EM_EXECUCAO

    pe = await concluir_pe(db, plano_id=pe.id, user=admin)
    assert pe.status == STATUS_PE_CONCLUIDO

    pe = await avaliar_pe(
        db,
        plano_id=pe.id,
        avaliacao=3,
        data_avaliacao=date(2024, 7, 15),
        user=admin,
    )
    assert pe.status == STATUS_PE_AVALIADO
    assert pe.avaliacao == 3


async def test_avaliar_pe_apos_30_dias_rejeitado(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-30d",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
        user=admin,
    )
    pe = await iniciar_execucao_pe(db, plano_id=pe.id, user=admin)
    pe = await concluir_pe(db, plano_id=pe.id, user=admin)

    with pytest.raises(ValidationError, match="30 dias"):
        await avaliar_pe(
            db,
            plano_id=pe.id,
            avaliacao=3,
            data_avaliacao=date(2024, 8, 15),  # > 30 days after 2024-06-30
            user=admin,
        )


async def test_cancelar_pe(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-CAN",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
        user=admin,
    )
    pe = await cancelar_pe(db, plano_id=pe.id, user=admin)
    assert pe.status == STATUS_PE_CANCELADO


# ---------------------------------------------------------------------------
# Entrega
# ---------------------------------------------------------------------------


async def test_criar_entrega(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-E",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 12, 31),
        user=admin,
    )
    e = await criar_entrega(
        db,
        id_entrega="E-001",
        plano_entregas_id=pe.id,
        nome_entrega="Relatório Anual",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2024, 12, 15),
        nome_unidade_demandante="Chefia",
        nome_unidade_destinataria="Ministério",
        user=admin,
    )
    assert e.id is not None
    assert e.nome_entrega == "Relatório Anual"


# ---------------------------------------------------------------------------
# GraphQL mutations via HTTP
# ---------------------------------------------------------------------------


async def test_gql_criar_plano_entregas(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ue = await _make_unidade_execucao(db, admin)

    query = f"""
    mutation {{
      criarPlanoEntregas(input: {{
        idPlanoEntregas: "PE-GQL-001"
        origemUnidade: SIAPE
        codUnidadeAutorizadora: {ua.cod_unidade_autorizadora}
        codUnidadeInstituidora: 100
        codUnidadeExecutora: {ue.cod_unidade_executora}
        unidadeExecucaoId: "{ue.id}"
        dataInicio: "2024-01-01"
        dataTermino: "2024-12-31"
      }}) {{
        id
        idPlanoEntregas
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["criarPlanoEntregas"]
    assert payload["idPlanoEntregas"] == "PE-GQL-001"
    assert payload["status"] == 2  # STATUS_PE_APROVADO


async def test_gql_ciclo_vida_plano_entregas(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ue = await _make_unidade_execucao(db, admin)

    # criar PE
    create_q = f"""
    mutation {{
      criarPlanoEntregas(input: {{
        idPlanoEntregas: "PE-CICLO"
        origemUnidade: SIAPE
        codUnidadeAutorizadora: {ua.cod_unidade_autorizadora}
        codUnidadeInstituidora: 100
        codUnidadeExecutora: {ue.cod_unidade_executora}
        unidadeExecucaoId: "{ue.id}"
        dataInicio: "2024-01-01"
        dataTermino: "2024-06-30"
      }}) {{ id }}
    }}
    """
    r1 = await client.post("/graphql", json={"query": create_q})
    pe_id = r1.json()["data"]["criarPlanoEntregas"]["id"]

    # criar entrega
    entrega_q = f"""
    mutation {{
      criarEntrega(
        planoEntregasId: "{pe_id}"
        input: {{
          idEntrega: "E-CICLO-001"
          nomeEntrega: "Relatório GQL"
          metaEntrega: 1
          tipoMeta: UNIDADE
          dataEntrega: "2024-06-15"
          nomeUnidadeDemandante: "Chefia"
          nomeUnidadeDestinataria: "Min."
        }}
      ) {{ id nomeEntrega }}
    }}
    """
    r2 = await client.post("/graphql", json={"query": entrega_q})
    assert "errors" not in r2.json()

    # iniciar execução
    iniciar_q = f"""
    mutation {{ iniciarExecucaoPlanoEntregas(planoId: "{pe_id}") {{ id status }} }}
    """
    r3 = await client.post("/graphql", json={"query": iniciar_q})
    assert r3.json()["data"]["iniciarExecucaoPlanoEntregas"]["status"] == 3

    # concluir
    concluir_q = f"""
    mutation {{ concluirPlanoEntregas(planoId: "{pe_id}") {{ id status }} }}
    """
    r4 = await client.post("/graphql", json={"query": concluir_q})
    assert r4.json()["data"]["concluirPlanoEntregas"]["status"] == 4

    # avaliar
    avaliar_q = f"""
    mutation {{
      avaliarPlanoEntregas(planoId: "{pe_id}" avaliacao: 4 dataAvaliacao: "2024-07-15") {{
        id status avaliacao
      }}
    }}
    """
    r5 = await client.post("/graphql", json={"query": avaliar_q})
    assert "errors" not in r5.json()
    payload = r5.json()["data"]["avaliarPlanoEntregas"]
    assert payload["status"] == 5
    assert payload["avaliacao"] == 4


async def test_gql_cancelar_plano_entregas(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ue = await _make_unidade_execucao(db, admin)

    create_q = f"""
    mutation {{
      criarPlanoEntregas(input: {{
        idPlanoEntregas: "PE-CAN-GQL"
        origemUnidade: SIAPE
        codUnidadeAutorizadora: {ua.cod_unidade_autorizadora}
        codUnidadeInstituidora: 100
        codUnidadeExecutora: {ue.cod_unidade_executora}
        unidadeExecucaoId: "{ue.id}"
        dataInicio: "2024-01-01"
        dataTermino: "2024-06-30"
      }}) {{ id }}
    }}
    """
    r1 = await client.post("/graphql", json={"query": create_q})
    pe_id = r1.json()["data"]["criarPlanoEntregas"]["id"]

    cancel_q = f"""
    mutation {{ cancelarPlanoEntregas(planoId: "{pe_id}") {{ id status }} }}
    """
    r2 = await client.post("/graphql", json={"query": cancel_q})
    assert "errors" not in r2.json()
    assert r2.json()["data"]["cancelarPlanoEntregas"]["status"] == 1  # STATUS_PE_CANCELADO


async def test_gql_query_plano_entregas(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ue = await _make_unidade_execucao(db, admin)
    pe = await _criar_pe(db, admin, ue, cod=99)

    query = f"""
    query {{
      planoEntregas(id: "{pe.id}") {{
        id
        idPlanoEntregas
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["planoEntregas"]
    assert payload["idPlanoEntregas"] == "PE-99"
    assert payload["status"] == 2
