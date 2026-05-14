"""Sprint 1.1 — Gestão Institucional: service + GraphQL resolver tests."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import (
    OrigemUnidade,
    StatusAto,
    StatusPgd,
)
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    atualizar_status_ato,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
    get_unidade_autorizadora,
    listar_resultados_publicos,
    suspender_pgd,
    validate_motivo_suspensao_required,
    validate_vagas_tt_exterior,
)

from .conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def test_validate_vagas_tt_exterior_none():
    validate_vagas_tt_exterior(None)  # no exception


def test_validate_vagas_tt_exterior_within_limit():
    validate_vagas_tt_exterior(2)  # no exception


def test_validate_vagas_tt_exterior_exceeds_limit():
    with pytest.raises(ValidationError, match="exterior"):
        validate_vagas_tt_exterior(3)


def test_validate_motivo_suspensao_required_valid():
    validate_motivo_suspensao_required("motivo válido")  # no exception


def test_validate_motivo_suspensao_required_empty():
    with pytest.raises(ValidationError, match="Fundamentação"):
        validate_motivo_suspensao_required("")


def test_validate_motivo_suspensao_required_whitespace():
    with pytest.raises(ValidationError, match="Fundamentação"):
        validate_motivo_suspensao_required("   ")


def test_validate_motivo_suspensao_required_none():
    with pytest.raises(ValidationError):
        validate_motivo_suspensao_required(None)


# ---------------------------------------------------------------------------
# Service — UnidadeAutorizadora
# ---------------------------------------------------------------------------


async def test_criar_unidade_autorizadora(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Ministério Teste",
        sigla="MT",
        user=user,
    )
    assert ua.id is not None
    assert ua.cod_unidade_autorizadora == 1
    assert ua.origem_unidade == OrigemUnidade.SIAPE
    assert ua.pgd_autorizado is False


async def test_get_unidade_autorizadora_found(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=2,
        origem_unidade=OrigemUnidade.SIORG,
        nome="Órgão Central",
        sigla="OC",
        user=user,
    )
    found = await get_unidade_autorizadora(db, ua.id)
    assert found is not None
    assert found.id == ua.id


async def test_get_unidade_autorizadora_not_found(db: AsyncSession):
    result = await get_unidade_autorizadora(db, uuid.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# Service — AtoAutorizacao
# ---------------------------------------------------------------------------


async def test_criar_ato_autorizacao_sets_pgd_autorizado(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=10,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Min. Ato",
        sigla="MA",
        user=user,
    )
    assert ua.pgd_autorizado is False

    ato = await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Ministro X",
        data_publicacao=date(2024, 1, 15),
        referencia="Portaria 001/2024",
        user=user,
    )
    assert ato.id is not None
    assert ato.status == StatusAto.ATIVO

    await db.refresh(ua)
    assert ua.pgd_autorizado is True


async def test_criar_ato_autorizacao_ua_not_found(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    with pytest.raises(ValidationError, match="UnidadeAutorizadora"):
        await criar_ato_autorizacao(
            db,
            unidade_autorizadora_id=uuid.uuid4(),
            autoridade="Ministro X",
            data_publicacao=date(2024, 1, 15),
            referencia="Portaria 001/2024",
            user=user,
        )


async def test_atualizar_status_ato_suspenso(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=20,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Min. Status",
        sigla="MS",
        user=user,
    )
    ato = await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min. Y",
        data_publicacao=date(2024, 2, 1),
        referencia="Port. 002/2024",
        user=user,
    )

    updated = await atualizar_status_ato(
        db, ato_id=ato.id, novo_status=StatusAto.SUSPENSO, user=user
    )
    assert updated.status == StatusAto.SUSPENSO

    await db.refresh(ua)
    assert ua.pgd_autorizado is False


async def test_atualizar_status_ato_not_found(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    with pytest.raises(ValidationError, match="AtoAutorizacao"):
        await atualizar_status_ato(
            db, ato_id=uuid.uuid4(), novo_status=StatusAto.REVOGADO, user=user
        )


# ---------------------------------------------------------------------------
# Service — UnidadeInstituidora
# ---------------------------------------------------------------------------


async def _make_ua_with_ato(db: AsyncSession, user, cod: int = 100):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod,
        origem_unidade=OrigemUnidade.SIAPE,
        nome=f"UA {cod}",
        sigla=f"U{cod}",
        user=user,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Aut.",
        data_publicacao=date(2024, 1, 1),
        referencia=f"Port. {cod}/2024",
        user=user,
    )
    await db.refresh(ua)
    return ua


async def test_criar_unidade_instituidora_ok(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await _make_ua_with_ato(db, user)

    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=500,
        nome="Unidade Instituidora Teste",
        sigla="UIT",
        ato_instituicao_ref="Portaria 010/2024",
        data_instituicao=date(2024, 3, 1),
        tipos_atividades="Análise, Pesquisa",
        modalidades_autorizadas=[1, 2],
        conteudo_minimo_tcr="Cláusulas mínimas conforme IN24",
        prazo_antecedencia_convocacao_dias=5,
        user=user,
    )
    assert ui.id is not None
    assert ui.status == StatusPgd.EM_VIGOR
    assert ui.cod_unidade_instituidora == 500


async def test_criar_unidade_instituidora_requer_ato_ativo(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=200,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Sem Ato",
        sigla="USA",
        user=user,
    )

    with pytest.raises(ValidationError, match="[Aa]to de autorização ativo"):
        await criar_unidade_instituidora(
            db,
            unidade_autorizadora_id=ua.id,
            cod_unidade_instituidora=501,
            nome="Não vai criar",
            sigla="NVC",
            ato_instituicao_ref="Port. X",
            data_instituicao=date(2024, 3, 1),
            tipos_atividades="Atividades",
            modalidades_autorizadas=[1],
            conteudo_minimo_tcr="Conteúdo",
            prazo_antecedencia_convocacao_dias=5,
            user=user,
        )


async def test_criar_unidade_instituidora_tt_exterior_excede(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await _make_ua_with_ato(db, user, cod=300)

    with pytest.raises(ValidationError, match="exterior"):
        await criar_unidade_instituidora(
            db,
            unidade_autorizadora_id=ua.id,
            cod_unidade_instituidora=502,
            nome="Excede Exterior",
            sigla="EXT",
            ato_instituicao_ref="Port. Y",
            data_instituicao=date(2024, 3, 1),
            tipos_atividades="Atividades",
            modalidades_autorizadas=[1],
            conteudo_minimo_tcr="Conteúdo",
            prazo_antecedencia_convocacao_dias=5,
            vagas_percentual_tt_exterior=5,
            user=user,
        )


async def test_suspender_pgd_ok(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    ua = await _make_ua_with_ato(db, user, cod=400)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=503,
        nome="Vai Suspender",
        sigla="VS",
        ato_instituicao_ref="Port. Z",
        data_instituicao=date(2024, 3, 1),
        tipos_atividades="Atividades",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="Conteúdo",
        prazo_antecedencia_convocacao_dias=5,
        user=user,
    )
    assert ui.status == StatusPgd.EM_VIGOR

    updated = await suspender_pgd(
        db,
        unidade_instituidora_id=ui.id,
        motivo="Decisão judicial",
        user=user,
    )
    assert updated.status == StatusPgd.SUSPENSO
    assert updated.motivo_suspensao_revogacao == "Decisão judicial"
    assert updated.data_suspensao_revogacao is not None


async def test_suspender_pgd_motivo_vazio(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    with pytest.raises(ValidationError, match="Fundamentação"):
        await suspender_pgd(
            db,
            unidade_instituidora_id=uuid.uuid4(),
            motivo="",
            user=user,
        )


async def test_suspender_pgd_not_found(db: AsyncSession):
    user = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    with pytest.raises(ValidationError, match="UnidadeInstituidora"):
        await suspender_pgd(
            db,
            unidade_instituidora_id=uuid.uuid4(),
            motivo="Motivo válido",
            user=user,
        )


async def test_listar_resultados_publicos_empty(db: AsyncSession):
    rows = await listar_resultados_publicos(db)
    assert rows == []


# ---------------------------------------------------------------------------
# GraphQL mutations via HTTP
# ---------------------------------------------------------------------------


async def test_gql_criar_unidade_autorizadora(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    query = """
    mutation {
      criarUnidadeAutorizadora(input: {
        codUnidadeAutorizadora: 42
        origemUnidade: SIAPE
        nome: "Ministério da Tecnologia"
        sigla: "MT"
      }) {
        id
        codUnidadeAutorizadora
        pgdAutorizado
      }
    }
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["criarUnidadeAutorizadora"]
    assert payload["codUnidadeAutorizadora"] == 42
    assert payload["pgdAutorizado"] is False


async def test_gql_criar_unidade_autorizadora_requires_admin(client: AsyncClient, db: AsyncSession):
    servidor = await persist_user(db, email="srv@test.com", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    query = """
    mutation {
      criarUnidadeAutorizadora(input: {
        codUnidadeAutorizadora: 99
        origemUnidade: SIAPE
        nome: "Test"
        sigla: "T"
      }) { id }
    }
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" in data
    assert "ADMIN" in data["errors"][0]["message"]


async def test_gql_criar_ato_autorizacao(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    # first create UA
    ua_mutation = """
    mutation {
      criarUnidadeAutorizadora(input: {
        codUnidadeAutorizadora: 55
        origemUnidade: SIAPE
        nome: "Min. Ato Gql"
        sigla: "MAG"
      }) { id }
    }
    """
    r1 = await client.post("/graphql", json={"query": ua_mutation})
    ua_id = r1.json()["data"]["criarUnidadeAutorizadora"]["id"]

    query = f"""
    mutation {{
      criarAtoAutorizacao(
        unidadeAutorizadoraId: "{ua_id}"
        input: {{
          autoridade: "Min. Silva"
          dataPublicacao: "2024-01-15"
          referencia: "Portaria 001/2024"
        }}
      ) {{
        id
        status
        unidadeAutorizadoraId
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["criarAtoAutorizacao"]
    assert payload["status"] == "ATIVO"
    assert payload["unidadeAutorizadoraId"] == ua_id


async def test_gql_atualizar_status_ato(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    # create UA + Ato
    r1 = await client.post(
        "/graphql",
        json={
            "query": """mutation { criarUnidadeAutorizadora(input: {
              codUnidadeAutorizadora: 77 origemUnidade: SIAPE nome: "UA77" sigla: "U77"
            }) { id } }"""
        },
    )
    ua_id = r1.json()["data"]["criarUnidadeAutorizadora"]["id"]

    r2 = await client.post(
        "/graphql",
        json={
            "query": f"""mutation {{ criarAtoAutorizacao(
              unidadeAutorizadoraId: "{ua_id}"
              input: {{ autoridade: "A" dataPublicacao: "2024-01-01" referencia: "R" }}
            ) {{ id }} }}"""
        },
    )
    ato_id = r2.json()["data"]["criarAtoAutorizacao"]["id"]

    query = f"""
    mutation {{
      atualizarStatusAto(atoId: "{ato_id}" status: SUSPENSO) {{
        id
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    assert data["data"]["atualizarStatusAto"]["status"] == "SUSPENSO"


async def test_gql_resultados_publicos_sem_autenticacao(client: AsyncClient, db: AsyncSession):
    query = "{ resultadosPublicos { codUnidadeExecutora nome totalPlanosAvaliados } }"
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    assert data["data"]["resultadosPublicos"] == []


async def test_gql_criar_unidade_instituidora(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    r1 = await client.post(
        "/graphql",
        json={
            "query": """mutation { criarUnidadeAutorizadora(input: {
              codUnidadeAutorizadora: 88 origemUnidade: SIAPE nome: "UA88" sigla: "U88"
            }) { id } }"""
        },
    )
    ua_id = r1.json()["data"]["criarUnidadeAutorizadora"]["id"]

    await client.post(
        "/graphql",
        json={
            "query": f"""mutation {{ criarAtoAutorizacao(
              unidadeAutorizadoraId: "{ua_id}"
              input: {{ autoridade: "A" dataPublicacao: "2024-01-01" referencia: "R" }}
            ) {{ id }} }}"""
        },
    )

    query = f"""
    mutation {{
      criarUnidadeInstituidora(
        unidadeAutorizadoraId: "{ua_id}"
        input: {{
          codUnidadeInstituidora: 900
          nome: "Unidade GQL"
          sigla: "UG"
          atoInstituicaoRef: "Port. GQL"
          dataInstituicao: "2024-04-01"
          tiposAtividades: "Análise"
          modalidadesAutorizadas: [1]
          conteudoMinimoTcr: "Mínimo"
          prazoAntecedenciaConvocacaoDias: 5
        }}
      ) {{
        id
        status
        codUnidadeInstituidora
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["criarUnidadeInstituidora"]
    assert payload["status"] == "EM_VIGOR"
    assert payload["codUnidadeInstituidora"] == 900


async def test_gql_suspender_pgd(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@test.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    r1 = await client.post(
        "/graphql",
        json={
            "query": """mutation { criarUnidadeAutorizadora(input: {
              codUnidadeAutorizadora: 99 origemUnidade: SIAPE nome: "UA99" sigla: "U99"
            }) { id } }"""
        },
    )
    ua_id = r1.json()["data"]["criarUnidadeAutorizadora"]["id"]
    await client.post(
        "/graphql",
        json={
            "query": f"""mutation {{ criarAtoAutorizacao(
              unidadeAutorizadoraId: "{ua_id}"
              input: {{ autoridade: "A" dataPublicacao: "2024-01-01" referencia: "R" }}
            ) {{ id }} }}"""
        },
    )
    r3 = await client.post(
        "/graphql",
        json={
            "query": f"""mutation {{
              criarUnidadeInstituidora(
                unidadeAutorizadoraId: "{ua_id}"
                input: {{
                  codUnidadeInstituidora: 950 nome: "Suspender" sigla: "SP"
                  atoInstituicaoRef: "P" dataInstituicao: "2024-04-01"
                  tiposAtividades: "T" modalidadesAutorizadas: [1]
                  conteudoMinimoTcr: "C" prazoAntecedenciaConvocacaoDias: 5
                }}
              ) {{ id }}
            }}"""
        },
    )
    ui_id = r3.json()["data"]["criarUnidadeInstituidora"]["id"]

    query = f"""
    mutation {{
      suspenderPgd(
        unidadeInstituidoraId: "{ui_id}"
        motivo: "Decisão judicial"
      ) {{
        id
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    assert data["data"]["suspenderPgd"]["status"] == "SUSPENSO"
