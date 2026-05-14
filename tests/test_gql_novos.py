"""Sprint 2.4 — Testes GraphQL para mutations e queries novas (TC-M04-*, TC-M07-*)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import TipoMeta
from src.models.user import UserRole
from src.services.institucional import (
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    assinar_tcr_chefia,
    cadastrar_participante,
    pactu_tcr,
)
from src.services.plano_entregas import criar_entrega, criar_plano_entregas
from src.services.plano_trabalho import adicionar_contribuicao, criar_plano_trabalho
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------


async def _setup_base(db: AsyncSession, admin, cod_ua: int = 220001):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA GQL",
        sigla="UGQ",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="GQL1",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=220010,
        nome="UI GQL",
        sigla="IQL",
        ato_instituicao_ref="GQL1",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=220020,
        nome="UE GQL",
        sigla="EQL",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="2200001", modalidade=3):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Part GQL",
        email=f"{matricula}@gql.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        cumpriu_estagio_probatorio=True if modalidade in (2, 3, 4, 5) else None,
        user=admin,
    )


async def _make_tcr(db, admin, participante, modalidade=3):
    tcr = await pactu_tcr(
        db,
        participante_id=participante.id,
        chefia_user_id=None,
        modalidade_execucao=modalidade,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=admin,
    )
    return await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)


# ---------------------------------------------------------------------------
# TC — confirmarSelecao
# ---------------------------------------------------------------------------


async def test_gql_confirmar_selecao(db: AsyncSession, client: AsyncClient) -> None:
    """Mutation confirmarSelecao cria ProcessoSelecao com resultado ordenado."""
    admin = await persist_user(db, email="gql_sel@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    _, _, ue = await _setup_base(db, admin)

    mutation = """
    mutation($input: ConfirmarSelecaoInput!) {
      confirmarSelecao(input: $input) {
        id
        nVagas
        criteriosTecnicos
        resultado
      }
    }
    """
    variables = {
        "input": {
            "unidadeExecucaoId": str(ue.id),
            "nVagas": 2,
            "criteriosTecnicos": "Experiência comprovada em TI",
            "candidatos": [
                {"id": "C1", "nome": "Alice", "criterio": "SEM_PRIORIDADE"},
                {"id": "C2", "nome": "Bob", "criterio": "PCD"},
                {"id": "C3", "nome": "Carla", "criterio": "MOBILIDADE_REDUZIDA"},
            ],
        }
    }
    resp = await client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    ps = data["data"]["confirmarSelecao"]
    assert ps["nVagas"] == 2
    assert ps["criteriosTecnicos"] == "Experiência comprovada em TI"
    resultado = ps["resultado"]
    # PCD e MOBILIDADE_REDUZIDA têm prioridade; eles devem ser selecionados
    selecionados = [r for r in resultado if r["selecionado"]]
    assert len(selecionados) == 2
    criterios_sel = {r["criterio"] for r in selecionados}
    assert "pcd" in criterios_sel
    assert "mobilidade_reduzida" in criterios_sel


# ---------------------------------------------------------------------------
# TC — aprovarPlanoEntregas
# ---------------------------------------------------------------------------


async def test_gql_aprovar_plano_entregas(db: AsyncSession, client: AsyncClient) -> None:
    """Mutation aprovarPlanoEntregas define aprovado_por_user_id e data_aprovacao."""
    admin = await persist_user(db, email="gql_apr@test.gov.br", role=UserRole.ADMIN)
    aprovador = await persist_user(db, email="gql_apr2@test.gov.br", role=UserRole.GESTOR_UNIDADE)
    set_auth_cookie(client, admin)
    _, _, ue = await _setup_base(db, admin, cod_ua=220002)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-GQL-APR-1",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=220002,
        cod_unidade_instituidora=220010,
        cod_unidade_executora=220020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 6, 30),
        user=admin,
    )

    mutation = """
    mutation($input: AprovarPlanoEntregasInput!) {
      aprovarPlanoEntregas(input: $input) {
        id
        aprovadoPorUserId
        dataAprovacao
      }
    }
    """
    variables = {
        "input": {
            "planoId": str(pe.id),
            "aprovadorUserId": aprovador.id,
        }
    }
    resp = await client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["aprovarPlanoEntregas"]
    assert result["aprovadoPorUserId"] == aprovador.id
    assert result["dataAprovacao"] is not None


async def test_gql_aprovar_instituidora_rejeitado(db: AsyncSession, client: AsyncClient) -> None:
    """Plano de unidade que coincide com instituidora não pode ser aprovado hierarquicamente."""
    admin = await persist_user(db, email="gql_aprx@test.gov.br", role=UserRole.ADMIN)
    aprovador = await persist_user(db, email="gql_aprx2@test.gov.br", role=UserRole.GESTOR_UNIDADE)
    set_auth_cookie(client, admin)

    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=220003,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA GQL X",
        sigla="UGX",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="GQL2",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=220030,
        nome="UI GQL X",
        sigla="IQX",
        ato_instituicao_ref="GQL2",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=220031,
        nome="UE GQL X",
        sigla="EQX",
        coincide_com_instituidora=True,
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-GQL-INST-1",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=220003,
        cod_unidade_instituidora=220030,
        cod_unidade_executora=220031,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 6, 30),
        user=admin,
    )

    mutation = """
    mutation($input: AprovarPlanoEntregasInput!) {
      aprovarPlanoEntregas(input: $input) { id }
    }
    """
    resp = await client.post(
        "/graphql",
        json={
            "query": mutation,
            "variables": {"input": {"planoId": str(pe.id), "aprovadorUserId": aprovador.id}},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors, "Esperava erro GQL para unidade instituidora"
    assert any("instituidora" in str(e).lower() for e in errors)


# ---------------------------------------------------------------------------
# TC — registrarAutorizacaoEquipamentos
# ---------------------------------------------------------------------------


async def test_gql_registrar_autorizacao_equipamentos(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Mutation registrarAutorizacaoEquipamentos cria TermoGuardaEquipamento."""
    admin = await persist_user(db, email="gql_equip@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=220004)

    p = await _make_participante(db, admin, ue, ua, ui, matricula="2200040", modalidade=3)
    tcr = await _make_tcr(db, admin, p, modalidade=3)

    mutation = """
    mutation($input: RegistrarAutorizacaoEquipamentosInput!) {
      registrarAutorizacaoEquipamentos(input: $input) {
        id
        descricaoEquipamentos
        dataAutorizacao
      }
    }
    """
    variables = {
        "input": {
            "participanteId": str(p.id),
            "tcrId": str(tcr.id),
            "descricaoEquipamentos": "Notebook Dell XPS",
            "dataAutorizacao": "2026-03-01",
            "modalidadeExecucao": 3,
        }
    }
    resp = await client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    t = data["data"]["registrarAutorizacaoEquipamentos"]
    assert t["descricaoEquipamentos"] == "Notebook Dell XPS"
    assert t["dataAutorizacao"] == "2026-03-01"


# ---------------------------------------------------------------------------
# TC — relatorioSemPlanoTrabalho
# ---------------------------------------------------------------------------


async def test_gql_relatorio_sem_plano_trabalho(db: AsyncSession, client: AsyncClient) -> None:
    """Query relatorioSemPlanoTrabalho retorna participante ativo sem PT."""
    admin = await persist_user(
        db,
        email="gql_rel@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=220005,
    )
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=220005)

    p = await _make_participante(db, admin, ue, ua, ui, matricula="2200050", modalidade=1)

    query = """
    query($ua: Int) {
      relatorioSemPlanoTrabalho(codUnidadeAutorizadora: $ua) {
        id
        matriculaSiape
      }
    }
    """
    resp = await client.post(
        "/graphql",
        json={"query": query, "variables": {"ua": 220005}},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    ids = [r["id"] for r in data["data"]["relatorioSemPlanoTrabalho"]]
    assert str(p.id) in ids


# ---------------------------------------------------------------------------
# TC — rotulo da contribuição via query GQL
# ---------------------------------------------------------------------------


async def test_gql_rotulo_contribuicao_em_query(db: AsyncSession, client: AsyncClient) -> None:
    """Query planoTrabalho { contribuicoes { rotulo } } retorna rótulo correto."""
    admin = await persist_user(db, email="gql_rot@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=220006)

    p = await _make_participante(db, admin, ue, ua, ui, matricula="2200060", modalidade=1)
    await _make_tcr(db, admin, p, modalidade=1)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-GQL-ROT-1",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=220006,
        cod_unidade_instituidora=220010,
        cod_unidade_executora=220020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-GQL-ROT-1",
        plano_entregas_id=pe.id,
        nome_entrega="Entrega GQL",
        meta_entrega=10,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="UD",
        nome_unidade_destinataria="UDS",
        user=admin,
    )

    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-GQL-ROT-1",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=220006,
        cod_unidade_executora=220020,
        cod_unidade_lotacao_participante=220020,
        participante_id=p.id,
        cpf_participante="11144477735",
        matricula_siape="2200060",
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="Qualidade",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        id_contribuicao="C-GQL-ROT-1",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="Ação de desenvolvimento",
        rotulo="capacitacao_python",
        user=admin,
    )

    query = """
    query($id: ID!) {
      planoTrabalho(id: $id) {
        contribuicoes { rotulo }
      }
    }
    """
    resp = await client.post(
        "/graphql",
        json={"query": query, "variables": {"id": str(pt.id)}},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    contribuicoes = data["data"]["planoTrabalho"]["contribuicoes"]
    assert len(contribuicoes) == 1
    assert contribuicoes[0]["rotulo"] == "capacitacao_python"
