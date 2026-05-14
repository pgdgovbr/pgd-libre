"""Testes para isolamento multi-tenant por cod_unidade_autorizadora.

Regra: ADMIN vê todos os dados; qualquer outro role vê apenas os registros
onde cod_unidade_autorizadora == user.cod_unidade_autorizadora.
"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import (
    OrigemUnidade,
    UnidadeAutorizadora,
    UnidadeExecucao,
    UnidadeInstituidora,
)
from src.models.participante import Participante, TipoVinculo
from src.models.plano import PlanoEntregas
from src.models.user import UserRole
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_ua(db: AsyncSession, cod: int) -> UnidadeAutorizadora:
    ua = UnidadeAutorizadora(
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod,
        nome=f"UA {cod}",
        sigla=f"UA{cod}",
    )
    db.add(ua)
    await db.flush()
    return ua


async def _make_ue(db: AsyncSession, ua: UnidadeAutorizadora) -> UnidadeExecucao:
    ui = UnidadeInstituidora(
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=ua.cod_unidade_autorizadora * 10,
        nome="UI",
        sigla="UI",
        ato_instituicao_ref="PORT-1",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="x",
        prazo_antecedencia_convocacao_dias=2,
    )
    db.add(ui)
    await db.flush()
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=ua.cod_unidade_autorizadora * 100,
        nome="UE",
        sigla="UE",
    )
    db.add(ue)
    await db.flush()
    return ue


async def _make_participante(
    db: AsyncSession, ue: UnidadeExecucao, ua: UnidadeAutorizadora, matricula: str
) -> Participante:
    p = Participante(
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ua.cod_unidade_autorizadora * 100,
        matricula_siape=matricula,
        cod_unidade_instituidora=ua.cod_unidade_autorizadora * 10,
        cpf="52998224725",
        nome="Participante Teste",
        email="p@test.gov.br",
        modalidade_execucao=3,
        data_assinatura_tcr=date(2024, 1, 15),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_pe(
    db: AsyncSession, ue: UnidadeExecucao, ua: UnidadeAutorizadora, id_pe: str
) -> PlanoEntregas:
    pe = PlanoEntregas(
        id_plano_entregas=id_pe,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=ua.cod_unidade_autorizadora * 10,
        cod_unidade_executora=ua.cod_unidade_autorizadora * 100,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 12, 31),
    )
    db.add(pe)
    await db.flush()
    return pe


def _gql(query: str) -> dict:
    return {"query": query}


# ---------------------------------------------------------------------------
# TC-MT-001  listar_participantes — gestor vê só sua unidade
# ---------------------------------------------------------------------------


async def test_gestor_lista_apenas_propria_unidade(db: AsyncSession, client: AsyncClient) -> None:
    ua_a = await _make_ua(db, 100)
    ua_b = await _make_ua(db, 200)
    ue_a = await _make_ue(db, ua_a)
    ue_b = await _make_ue(db, ua_b)
    await _make_participante(db, ue_a, ua_a, "1234567")
    await _make_participante(db, ue_b, ua_b, "7654321")
    await db.commit()

    gestor = await persist_user(
        db,
        email="g@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=100,
    )
    set_auth_cookie(client, gestor)

    resp = await client.post(
        "/graphql",
        json=_gql("{ listarParticipantes { matriculaSiape codUnidadeAutorizadora } }"),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["listarParticipantes"]
    assert len(data) == 1
    assert data[0]["codUnidadeAutorizadora"] == 100
    assert data[0]["matriculaSiape"] == "1234567"


# ---------------------------------------------------------------------------
# TC-MT-002  listar_participantes — admin vê todas as unidades
# ---------------------------------------------------------------------------


async def test_admin_lista_participantes_de_todas_unidades(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua_a = await _make_ua(db, 101)
    ua_b = await _make_ua(db, 201)
    ue_a = await _make_ue(db, ua_a)
    ue_b = await _make_ue(db, ua_b)
    await _make_participante(db, ue_a, ua_a, "1111111")
    await _make_participante(db, ue_b, ua_b, "2222222")
    await db.commit()

    admin = await persist_user(db, email="admin@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json=_gql("{ listarParticipantes { matriculaSiape } }"),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    matriculas = {p["matriculaSiape"] for p in resp.json()["data"]["listarParticipantes"]}
    assert "1111111" in matriculas
    assert "2222222" in matriculas


# ---------------------------------------------------------------------------
# TC-MT-003  participante(id) — gestor não acessa outra unidade
# ---------------------------------------------------------------------------


async def test_gestor_nao_acessa_participante_de_outra_unidade(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua_b = await _make_ua(db, 202)
    ue_b = await _make_ue(db, ua_b)
    p = await _make_participante(db, ue_b, ua_b, "3333333")
    await db.commit()

    gestor = await persist_user(
        db,
        email="g2@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=102,
    )
    set_auth_cookie(client, gestor)

    resp = await client.post(
        "/graphql",
        json=_gql(f'{{ participante(id: "{p.id}") {{ id }} }}'),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["participante"] is None


# ---------------------------------------------------------------------------
# TC-MT-004  participante(id) — gestor acessa sua própria unidade
# ---------------------------------------------------------------------------


async def test_gestor_acessa_participante_da_propria_unidade(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua = await _make_ua(db, 103)
    ue = await _make_ue(db, ua)
    p = await _make_participante(db, ue, ua, "4444444")
    await db.commit()

    gestor = await persist_user(
        db,
        email="g3@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=103,
    )
    set_auth_cookie(client, gestor)

    resp = await client.post(
        "/graphql",
        json=_gql(f'{{ participante(id: "{p.id}") {{ matriculaSiape codUnidadeAutorizadora }} }}'),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["participante"]
    assert data is not None
    assert data["matriculaSiape"] == "4444444"
    assert data["codUnidadeAutorizadora"] == 103


# ---------------------------------------------------------------------------
# TC-MT-005  listar_planos_entregas — gestor vê só sua unidade
# ---------------------------------------------------------------------------


async def test_gestor_lista_apenas_planos_entregas_propria_unidade(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua_a = await _make_ua(db, 104)
    ua_b = await _make_ua(db, 204)
    ue_a = await _make_ue(db, ua_a)
    ue_b = await _make_ue(db, ua_b)
    await _make_pe(db, ue_a, ua_a, "PE-A-001")
    await _make_pe(db, ue_b, ua_b, "PE-B-001")
    await db.commit()

    gestor = await persist_user(
        db,
        email="g4@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=104,
    )
    set_auth_cookie(client, gestor)

    resp = await client.post(
        "/graphql",
        json=_gql("{ listarPlanosEntregas { idPlanoEntregas codUnidadeAutorizadora } }"),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["listarPlanosEntregas"]
    assert len(data) == 1
    assert data[0]["idPlanoEntregas"] == "PE-A-001"
    assert data[0]["codUnidadeAutorizadora"] == 104


# ---------------------------------------------------------------------------
# TC-MT-006  listar_planos_entregas — admin vê todas unidades
# ---------------------------------------------------------------------------


async def test_admin_lista_planos_entregas_todas_unidades(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua_a = await _make_ua(db, 105)
    ua_b = await _make_ua(db, 205)
    ue_a = await _make_ue(db, ua_a)
    ue_b = await _make_ue(db, ua_b)
    await _make_pe(db, ue_a, ua_a, "PE-105-001")
    await _make_pe(db, ue_b, ua_b, "PE-205-001")
    await db.commit()

    admin = await persist_user(db, email="admin2@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json=_gql("{ listarPlanosEntregas { idPlanoEntregas } }"),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    ids = {pe["idPlanoEntregas"] for pe in resp.json()["data"]["listarPlanosEntregas"]}
    assert "PE-105-001" in ids
    assert "PE-205-001" in ids


# ---------------------------------------------------------------------------
# TC-MT-007  chefe_imediato também fica limitado à sua unidade
# ---------------------------------------------------------------------------


async def test_chefe_imediato_limitado_propria_unidade(
    db: AsyncSession, client: AsyncClient
) -> None:
    ua_a = await _make_ua(db, 106)
    ua_b = await _make_ua(db, 206)
    ue_a = await _make_ue(db, ua_a)
    ue_b = await _make_ue(db, ua_b)
    await _make_participante(db, ue_a, ua_a, "5555555")
    await _make_participante(db, ue_b, ua_b, "6666666")
    await db.commit()

    chefe = await persist_user(
        db,
        email="c@test.gov.br",
        role=UserRole.CHEFE_IMEDIATO,
        cod_unidade_autorizadora=106,
    )
    set_auth_cookie(client, chefe)

    resp = await client.post(
        "/graphql",
        json=_gql("{ listarParticipantes { matriculaSiape } }"),
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["listarParticipantes"]
    assert len(data) == 1
    assert data[0]["matriculaSiape"] == "5555555"
