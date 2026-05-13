"""Sprint 1.4 — Plano de Trabalho: service tests (TC-M04)."""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import (
    STATUS_PT_APROVADO,
    STATUS_PT_CANCELADO,
    STATUS_PT_EM_EXECUCAO,
    TipoMeta,
)
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    assinar_tcr_chefia,
    cadastrar_participante,
    pactu_tcr,
)
from src.services.plano_entregas import criar_plano_entregas
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    cancelar_pt,
    criar_plano_trabalho,
    iniciar_execucao_pt,
    registrar_execucao,
    validate_soma_percentuais,
    validate_tipo_contribuicao,
)

from httpx import AsyncClient

from .conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def test_validate_soma_percentuais_ok():
    validate_soma_percentuais([50, 30, 20])  # no exception


def test_validate_soma_percentuais_invalida():
    with pytest.raises(ValidationError, match="100%"):
        validate_soma_percentuais([50, 30])


def test_validate_soma_percentuais_com_compensacao():
    validate_soma_percentuais([60, 60], carga_horaria_compensacao=20)  # no exception


def test_validate_tipo_contribuicao_1_ok():
    validate_tipo_contribuicao(1, "PE-001", "E-001")  # no exception


def test_validate_tipo_contribuicao_1_sem_entrega():
    with pytest.raises(ValidationError, match="tipo 1"):
        validate_tipo_contribuicao(1, None, None)


def test_validate_tipo_contribuicao_2_ok():
    validate_tipo_contribuicao(2, None, None)  # no exception


def test_validate_tipo_contribuicao_2_com_plano():
    with pytest.raises(ValidationError, match="tipo 2"):
        validate_tipo_contribuicao(2, "PE-001", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_full(db, admin):
    """Creates UA + ato + UI + UE + Participante + TCR ativo."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Min PT",
        sigla="MPT",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="Port. 001",
        user=admin,
    )
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=100,
        nome="UI PT",
        sigla="UIPT",
        ato_instituicao_ref="Port. 002",
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
        nome="UE PT",
        sigla="UEPT",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Participante PT",
        email="pt@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=admin.id,
        modalidade_execucao=1,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=admin,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)
    return ua, ui, ue, p


async def _criar_pt(db, admin, ua, ue, p, cod="PT-001", data_inicio=date(2024, 3, 1), data_termino=date(2024, 12, 31), plano_entregas_id=None):
    return await criar_plano_trabalho(
        db,
        id_plano_trabalho=cod,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante=p.cpf,
        matricula_siape=p.matricula_siape,
        data_inicio=data_inicio,
        data_termino=data_termino,
        carga_horaria_disponivel=160,
        criterios_avaliacao="Entregáveis cumpridos no prazo",
        plano_entregas_id=plano_entregas_id,
        user=admin,
    )


# ---------------------------------------------------------------------------
# Service — PlanoTrabalho CRUD
# ---------------------------------------------------------------------------


async def test_criar_plano_trabalho_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    assert pt.id is not None
    assert pt.status == STATUS_PT_APROVADO


async def test_criar_plano_trabalho_sem_tcr_ativo(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=99,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Sem TCR",
        sigla="UST",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="A",
        data_publicacao=date(2024, 1, 1),
        referencia="R",
        user=admin,
    )
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=99,
        nome="UI",
        sigla="UI",
        ato_instituicao_ref="R",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    from src.models.institucional import UnidadeExecucao

    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=99,
        nome="UE",
        sigla="UE",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="9876543",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Sem TCR",
        email="stcr@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    with pytest.raises(ValidationError, match="TCR ativo"):
        await criar_plano_trabalho(
            db,
            id_plano_trabalho="PT-X",
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_executora=ue.cod_unidade_executora,
            cod_unidade_lotacao_participante=ue.cod_unidade_executora,
            participante_id=p.id,
            cpf_participante=p.cpf,
            matricula_siape=p.matricula_siape,
            data_inicio=date(2024, 3, 1),
            data_termino=date(2024, 12, 31),
            carga_horaria_disponivel=160,
            criterios_avaliacao="Critérios",
            user=admin,
        )


async def test_criar_plano_trabalho_sobreposicao(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    await _criar_pt(db, admin, ua, ue, p)
    with pytest.raises(ValidationError, match="período"):
        await _criar_pt(db, admin, ua, ue, p, cod="PT-002")


async def test_criar_pt_data_inicio_antes_pe(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-PT",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 4, 1),
        data_termino=date(2024, 12, 31),
        user=admin,
    )
    with pytest.raises(ValidationError, match="data_inicio"):
        await criar_plano_trabalho(
            db,
            id_plano_trabalho="PT-PRE",
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_executora=ue.cod_unidade_executora,
            cod_unidade_lotacao_participante=ue.cod_unidade_executora,
            participante_id=p.id,
            cpf_participante=p.cpf,
            matricula_siape=p.matricula_siape,
            data_inicio=date(2024, 3, 1),  # < PE data_inicio 2024-04-01
            data_termino=date(2024, 12, 31),
            carga_horaria_disponivel=160,
            criterios_avaliacao="C",
            plano_entregas_id=pe.id,
            user=admin,
        )


# ---------------------------------------------------------------------------
# Contribuições
# ---------------------------------------------------------------------------


async def test_adicionar_contribuicao_tipo1(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    c = await adicionar_contribuicao(
        db,
        id_contribuicao="C-001",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=1,
        percentual_contribuicao=100,
        descricao="Contribuição principal",
        id_plano_entregas="PE-001",
        id_entrega="E-001",
        user=admin,
    )
    assert c.id is not None
    assert c.tipo_contribuicao == 1


async def test_adicionar_contribuicao_tipo2_com_plano_rejeitado(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    with pytest.raises(ValidationError, match="tipo 2"):
        await adicionar_contribuicao(
            db,
            id_contribuicao="C-002",
            plano_trabalho_id=pt.id,
            tipo_contribuicao=2,
            percentual_contribuicao=100,
            descricao="Inválida",
            id_plano_entregas="PE-001",  # should be None for tipo 2
            user=admin,
        )


# ---------------------------------------------------------------------------
# Máquina de estados PT
# ---------------------------------------------------------------------------


async def test_maquina_estados_pt(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    assert pt.status == STATUS_PT_APROVADO

    pt = await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)
    assert pt.status == STATUS_PT_EM_EXECUCAO


async def test_cancelar_pt(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    pt = await cancelar_pt(db, plano_id=pt.id, user=admin)
    assert pt.status == STATUS_PT_CANCELADO


# ---------------------------------------------------------------------------
# Registro de execução
# ---------------------------------------------------------------------------


async def test_registrar_execucao(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p)
    pt = await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    are = await registrar_execucao(
        db,
        id_periodo_avaliativo="P-001",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2024, 3, 1),
        data_fim_periodo_avaliativo=date(2024, 3, 31),
        descricao_execucao="Realizei análise dos dados",
        user=admin,
    )
    assert are.id is not None
    assert are.data_registro_participante is not None


# ---------------------------------------------------------------------------
# GraphQL mutations via HTTP
# ---------------------------------------------------------------------------


async def test_gql_criar_plano_trabalho(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue, p = await _setup_full(db, admin)

    query = f"""
    mutation {{
      criarPlanoTrabalho(
        participanteId: "{p.id}"
        input: {{
          idPlanoTrabalho: "PT-GQL-001"
          origemUnidade: SIAPE
          codUnidadeAutorizadora: {ua.cod_unidade_autorizadora}
          codUnidadeExecutora: {ue.cod_unidade_executora}
          codUnidadeLotacaoParticipante: {ue.cod_unidade_executora}
          cpfParticipante: "{p.cpf}"
          matriculaSiape: "{p.matricula_siape}"
          dataInicio: "2024-03-01"
          dataTermino: "2024-12-31"
          cargaHorariaDisponivel: 160
          criteriosAvaliacao: "Critérios GQL"
        }}
      ) {{
        id
        idPlanoTrabalho
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["criarPlanoTrabalho"]
    assert payload["idPlanoTrabalho"] == "PT-GQL-001"
    assert payload["status"] == 2  # STATUS_PT_APROVADO


async def test_gql_adicionar_contribuicao(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p, cod="PT-CONTRIB")

    query = f"""
    mutation {{
      adicionarContribuicao(
        planoTrabalhoId: "{pt.id}"
        input: {{
          idContribuicao: "C-GQL-001"
          tipoContribuicao: 3
          percentualContribuicao: 100
          descricao: "Contribuição GQL"
        }}
      ) {{
        id
        idContribuicao
        percentualContribuicao
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["adicionarContribuicao"]
    assert payload["idContribuicao"] == "C-GQL-001"
    assert payload["percentualContribuicao"] == 100


async def test_gql_iniciar_cancelar_plano_trabalho(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p, cod="PT-SM-GQL")

    iniciar_q = f"""
    mutation {{ iniciarExecucaoPlanoTrabalho(planoId: "{pt.id}") {{ id status }} }}
    """
    r1 = await client.post("/graphql", json={"query": iniciar_q})
    assert "errors" not in r1.json()
    assert r1.json()["data"]["iniciarExecucaoPlanoTrabalho"]["status"] == 3  # STATUS_PT_EM_EXECUCAO

    # create a separate PT to cancel (can't cancel one in execucao without specific service)
    pt2 = await _criar_pt(db, admin, ua, ue, p, cod="PT-CAN-GQL", data_inicio=date(2025, 1, 1), data_termino=date(2025, 12, 31))
    cancel_q = f"""
    mutation {{ cancelarPlanoTrabalho(planoId: "{pt2.id}") {{ id status }} }}
    """
    r2 = await client.post("/graphql", json={"query": cancel_q})
    assert "errors" not in r2.json()
    assert r2.json()["data"]["cancelarPlanoTrabalho"]["status"] == 1  # STATUS_PT_CANCELADO


async def test_gql_registrar_execucao(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p, cod="PT-EXEC-GQL")
    pt = await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    query = f"""
    mutation {{
      registrarExecucao(
        planoTrabalhoId: "{pt.id}"
        input: {{
          idPeriodoAvaliativo: "P-GQL-001"
          dataInicioPeriodoAvaliativo: "2024-03-01"
          dataFimPeriodoAvaliativo: "2024-03-31"
          descricaoExecucao: "Executei GQL"
        }}
      ) {{
        id
        idPeriodoAvaliativo
        descricaoExecucao
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["registrarExecucao"]
    assert payload["idPeriodoAvaliativo"] == "P-GQL-001"
    assert payload["descricaoExecucao"] == "Executei GQL"


async def test_gql_query_plano_trabalho(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue, p = await _setup_full(db, admin)
    pt = await _criar_pt(db, admin, ua, ue, p, cod="PT-QUERY-GQL")

    query = f"""
    query {{
      planoTrabalho(id: "{pt.id}") {{
        id
        idPlanoTrabalho
        status
      }}
    }}
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    payload = data["data"]["planoTrabalho"]
    assert payload["idPlanoTrabalho"] == "PT-QUERY-GQL"
    assert payload["status"] == 2
