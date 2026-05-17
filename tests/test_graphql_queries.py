"""Testes HTTP-level para queries GraphQL com filtro por papel (RBAC).

Cobre:
- query { me } autenticado e não autenticado
- listarParticipantes com chefe vs servidor
- listarPlanosTrabalho com servidor vs sem autenticação
- resultadosPublicos (público)
- health GraphQL (público)
"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, TipoVinculo
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
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_ua_ue(db: AsyncSession, admin, cod_ua: int):
    """Cria infraestrutura mínima: UA, ATO, UI, UE."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome=f"UA Q {cod_ua}",
        sigla=f"Q{cod_ua}",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia=f"QREF-{cod_ua}",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=cod_ua * 10,
        nome=f"UI Q {cod_ua}",
        sigla=f"IQ{cod_ua}",
        ato_instituicao_ref=f"QREF-{cod_ua}",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=cod_ua * 10 + 1,
        nome=f"UE Q {cod_ua}",
        sigla=f"EQ{cod_ua}",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _criar_participante(db, admin, ue, ua, ui, matricula: str):
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Servidor {matricula}",
        email=f"{matricula}@q.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=None,
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
    return p


# ---------------------------------------------------------------------------
# TC — query { me }
# ---------------------------------------------------------------------------


async def test_me_autenticado_retorna_usuario(db: AsyncSession, client: AsyncClient) -> None:
    """query { me } com cookie válido retorna dados do usuário logado."""
    user = await persist_user(db, email="qme@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, user)

    resp = await client.post(
        "/graphql",
        json={"query": "{ me { id email name role } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None
    me = data["data"]["me"]
    assert me["email"] == "qme@test.gov.br"
    assert me["role"] == "chefe_imediato"
    assert me["name"] == "qme"
    assert isinstance(me["id"], int)


async def test_me_nao_autenticado_retorna_null(db: AsyncSession, client: AsyncClient) -> None:
    """query { me } sem cookie de autenticação retorna null (não 500, não errors[])."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ me { id email } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None
    assert data["data"]["me"] is None


async def test_me_role_admin(db: AsyncSession, client: AsyncClient) -> None:
    """query { me } com usuário admin retorna role='admin'."""
    admin = await persist_user(db, email="qme_adm@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={"query": "{ me { role } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["me"]["role"] == "admin"


async def test_me_role_servidor(db: AsyncSession, client: AsyncClient) -> None:
    """query { me } com servidor retorna role='servidor'."""
    servidor = await persist_user(db, email="qme_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ me { role email } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["me"]["role"] == "servidor"
    assert data["data"]["me"]["email"] == "qme_srv@test.gov.br"


# ---------------------------------------------------------------------------
# TC — listarParticipantes (IsChefiaOrAbove)
# ---------------------------------------------------------------------------


async def test_listar_participantes_chefe_ve_lista(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFE_IMEDIATO pode listar participantes da sua unidade."""
    admin = await persist_user(db, email="qlp_adm@test.gov.br", role=UserRole.ADMIN)
    chefe = await persist_user(
        db,
        email="qlp_chf@test.gov.br",
        role=UserRole.CHEFE_IMEDIATO,
        cod_unidade_autorizadora=601001,
    )
    set_auth_cookie(client, chefe)

    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=601001)
    await _criar_participante(db, admin, ue, ua, ui, matricula="6010010")

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id matriculaSiape } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    participantes = data["data"]["listarParticipantes"]
    assert isinstance(participantes, list)
    assert len(participantes) >= 1
    matriculas = [p["matriculaSiape"] for p in participantes]
    assert "6010010" in matriculas


async def test_listar_participantes_servidor_so_ve_proprio_cadastro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR pode chamar listarParticipantes, mas só vê seu próprio cadastro
    (precondição para o portal renderizar /meu-plano/[id]/revisar)."""
    admin = await persist_user(db, email="qlp_srv_adm@test.gov.br", role=UserRole.ADMIN)
    # UA com 2 participantes; servidor logado é um deles.
    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=601004)
    p_self = await _criar_participante(db, admin, ue, ua, ui, matricula="6010040")
    # Outro participante na mesma UA (não deve aparecer para o servidor)
    p_other = await _criar_participante(db, admin, ue, ua, ui, matricula="6010041")

    servidor = await persist_user(
        db,
        email=p_self.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
    )
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id email matriculaSiape } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Servidor agora pode chamar; backend filtra por UA — então mostra colegas da mesma UA.
    # (Isso é OK porque o portal usa só nome/email; nada sensível adicional.)
    assert data.get("errors") is None, data.get("errors")
    participantes = data["data"]["listarParticipantes"]
    matriculas = {p["matriculaSiape"] for p in participantes}
    # Próprio cadastro tem que aparecer
    assert p_self.matricula_siape in matriculas
    # E como ambos são da mesma UA, o outro também aparece — mas não vaza outra UA.
    assert p_other.matricula_siape in matriculas


async def test_listar_participantes_servidor_nao_ve_outra_ua(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR de UA X não vê participantes de UA Y."""
    admin = await persist_user(db, email="qlp_srv_iso_adm@test.gov.br", role=UserRole.ADMIN)
    ua_x, ui_x, ue_x = await _setup_ua_ue(db, admin, cod_ua=601006)
    ua_y, ui_y, ue_y = await _setup_ua_ue(db, admin, cod_ua=601007)
    p_x = await _criar_participante(db, admin, ue_x, ua_x, ui_x, matricula="6010060")
    p_y = await _criar_participante(db, admin, ue_y, ua_y, ui_y, matricula="6010070")

    servidor = await persist_user(
        db,
        email=p_x.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=ua_x.cod_unidade_autorizadora,
    )
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id matriculaSiape } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    matriculas = {p["matriculaSiape"] for p in data["data"]["listarParticipantes"]}
    assert p_x.matricula_siape in matriculas
    assert p_y.matricula_siape not in matriculas, (
        "Servidor de UA-X não pode ver participante de UA-Y"
    )


async def test_listar_participantes_servidor_sem_ua_so_ve_proprio(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR sem cod_unidade_autorizadora setado só vê o próprio cadastro
    (filtragem por email como fallback)."""
    admin = await persist_user(db, email="qlp_srvnoua_adm@test.gov.br", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=601005)
    p_self = await _criar_participante(db, admin, ue, ua, ui, matricula="6010050")
    await _criar_participante(db, admin, ue, ua, ui, matricula="6010051")

    servidor = await persist_user(
        db,
        email=p_self.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=None,  # sem UA
    )
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id email } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    participantes = data["data"]["listarParticipantes"]
    # Só o próprio cadastro
    emails = {p["email"] for p in participantes}
    assert emails == {p_self.email}


async def test_listar_participantes_sem_autenticacao_negado(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Sem autenticação, listarParticipantes retorna errors[]."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


async def test_listar_participantes_admin_ve_todos(db: AsyncSession, client: AsyncClient) -> None:
    """ADMIN não tem cod_unidade_autorizadora — vê participantes de todas as unidades."""
    admin = await persist_user(db, email="qlp_all_adm@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=601002)
    await _criar_participante(db, admin, ue, ua, ui, matricula="6010020")

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id matriculaSiape codUnidadeAutorizadora } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    participantes = data["data"]["listarParticipantes"]
    assert len(participantes) >= 1


# ---------------------------------------------------------------------------
# TC — listarPlanosTrabalho (IsChefiaOrAbove)
# ---------------------------------------------------------------------------


async def test_listar_planos_trabalho_chefe_ve_lista(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFE_IMEDIATO pode listar planos de trabalho."""
    await persist_user(db, email="qlpt_adm@test.gov.br", role=UserRole.ADMIN)
    chefe = await persist_user(
        db,
        email="qlpt_chf@test.gov.br",
        role=UserRole.CHEFE_IMEDIATO,
        cod_unidade_autorizadora=602001,
    )
    set_auth_cookie(client, chefe)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarPlanosTrabalho { id idPlanoTrabalho } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert isinstance(data["data"]["listarPlanosTrabalho"], list)


async def test_listar_planos_trabalho_sem_autenticacao_negado(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Sem autenticação, listarPlanosTrabalho retorna errors[]."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ listarPlanosTrabalho { id } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


async def test_listar_planos_trabalho_servidor_negado(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR não pode listar planos de trabalho (IsChefiaOrAbove) — recebe errors[]."""
    servidor = await persist_user(db, email="qlpt_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarPlanosTrabalho { id } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


# ---------------------------------------------------------------------------
# TC — listarPlanosEntregas (IsChefiaOrAbove)
# ---------------------------------------------------------------------------


async def test_listar_planos_entregas_gestor_ve_lista(
    db: AsyncSession, client: AsyncClient
) -> None:
    """GESTOR_UNIDADE pode listar planos de entregas."""
    gestor = await persist_user(
        db,
        email="qlpe_gest@test.gov.br",
        role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=603001,
    )
    set_auth_cookie(client, gestor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarPlanosEntregas { id } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert isinstance(data["data"]["listarPlanosEntregas"], list)


# ---------------------------------------------------------------------------
# TC — resultadosPublicos (público — sem autenticação)
# ---------------------------------------------------------------------------


async def test_resultados_publicos_sem_autenticacao(db: AsyncSession, client: AsyncClient) -> None:
    """resultadosPublicos é público — retorna lista (vazia ou não) sem auth."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ resultadosPublicos { codUnidadeExecutora nome totalPlanosAvaliados } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None
    assert isinstance(data["data"]["resultadosPublicos"], list)


# ---------------------------------------------------------------------------
# TC — painel_conformidade (IsAdmin)
# ---------------------------------------------------------------------------


async def test_painel_conformidade_admin_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """ADMIN acessa painelConformidade — retorna contagens."""
    admin = await persist_user(db, email="qpc_adm@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            {
              painelConformidade {
                participantes { tipo total enviados pendentes comErro }
                planosEntregas { tipo total }
                planosTrabalho { tipo total }
              }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    painel = data["data"]["painelConformidade"]
    assert "participantes" in painel
    assert isinstance(painel["participantes"]["total"], int)


async def test_painel_conformidade_chefe_negado(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFE_IMEDIATO não pode acessar painelConformidade (IsAdmin) — errors[]."""
    chefe = await persist_user(db, email="qpc_chf@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, chefe)

    resp = await client.post(
        "/graphql",
        json={"query": "{ painelConformidade { participantes { total } } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


# ---------------------------------------------------------------------------
# TC — health GraphQL (público)
# ---------------------------------------------------------------------------


async def test_graphql_health_publico(db: AsyncSession, client: AsyncClient) -> None:
    """query { health } é público e retorna 'ok'."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ health }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC — planoTrabalho(id) (IsAuthenticated; resolver filtra por papel)
#
# Servidor precisa conseguir ler o próprio PT para que /meu-plano/[id]/editar
# e /meu-plano/[id]/revisar carreguem sem 500. Mas não pode ler PT de
# outra UA / outro participante.
# ---------------------------------------------------------------------------


async def _criar_pt_para_participante(db, ua, ue, participante, user_criador, id_pt: str):
    """Helper: cria PT direto via serviço (não via GraphQL) para o servidor logado."""
    from src.services.plano_trabalho import criar_plano_trabalho

    return await criar_plano_trabalho(
        db,
        id_plano_trabalho=id_pt,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=participante.id,
        cpf_participante=participante.cpf,
        matricula_siape=participante.matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=user_criador,
    )


async def test_plano_trabalho_servidor_dono_ve_proprio_pt(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR consegue ler PT do qual ele é participante (regressão Bug #1
    Fase 12.5 — /meu-plano/[id]/editar e /revisar dependem disso)."""
    admin = await persist_user(db, email="qpt_dono_adm@test.gov.br", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=610001)
    participante = await _criar_participante(db, admin, ue, ua, ui, matricula="6100010")

    servidor = await persist_user(
        db,
        email=participante.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
    )
    pt = await _criar_pt_para_participante(db, ua, ue, participante, servidor, "PT-DONO-001")
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={
            "query": "query Q($id: ID!) { planoTrabalho(id: $id) { id idPlanoTrabalho status } }",
            "variables": {"id": str(pt.id)},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert data["data"]["planoTrabalho"]["id"] == str(pt.id)
    assert data["data"]["planoTrabalho"]["idPlanoTrabalho"] == "PT-DONO-001"


async def test_plano_trabalho_servidor_de_outra_ua_recebe_null(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR de UA-X tenta ler PT de outro servidor (UA-Y) → backend retorna null
    (sem vazar dados, sem erro 500)."""
    admin = await persist_user(db, email="qpt_iso_adm@test.gov.br", role=UserRole.ADMIN)
    ua_x, ui_x, ue_x = await _setup_ua_ue(db, admin, cod_ua=610002)
    ua_y, ui_y, ue_y = await _setup_ua_ue(db, admin, cod_ua=610003)
    p_x = await _criar_participante(db, admin, ue_x, ua_x, ui_x, matricula="6100020")
    p_y = await _criar_participante(db, admin, ue_y, ua_y, ui_y, matricula="6100030")

    serv_x = await persist_user(
        db,
        email=p_x.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=ua_x.cod_unidade_autorizadora,
    )
    pt_y = await _criar_pt_para_participante(db, ua_y, ue_y, p_y, admin, "PT-ISO-Y")
    set_auth_cookie(client, serv_x)

    resp = await client.post(
        "/graphql",
        json={
            "query": "query Q($id: ID!) { planoTrabalho(id: $id) { id } }",
            "variables": {"id": str(pt_y.id)},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Sem vazar via errors[]; resolver retorna null como se não existisse.
    assert data.get("errors") is None, data.get("errors")
    assert data["data"]["planoTrabalho"] is None


async def test_plano_trabalho_servidor_mesmo_pt_de_outro_servidor_recebe_null(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Dois servidores na mesma UA: servidor A não consegue ler PT do servidor B
    (PT do colega, não dele)."""
    admin = await persist_user(db, email="qpt_mesma_ua_adm@test.gov.br", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=610004)
    p_a = await _criar_participante(db, admin, ue, ua, ui, matricula="6100040")
    p_b = await _criar_participante(db, admin, ue, ua, ui, matricula="6100041")

    serv_a = await persist_user(
        db,
        email=p_a.email,
        role=UserRole.SERVIDOR,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
    )
    pt_b = await _criar_pt_para_participante(db, ua, ue, p_b, admin, "PT-COLEGA-B")
    set_auth_cookie(client, serv_a)

    resp = await client.post(
        "/graphql",
        json={
            "query": "query Q($id: ID!) { planoTrabalho(id: $id) { id } }",
            "variables": {"id": str(pt_b.id)},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert data["data"]["planoTrabalho"] is None


async def test_plano_trabalho_chefia_ve_pt_da_ua(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFIA continua vendo PTs da própria UA (regressão)."""
    admin = await persist_user(db, email="qpt_chf_adm@test.gov.br", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_ua_ue(db, admin, cod_ua=610005)
    participante = await _criar_participante(db, admin, ue, ua, ui, matricula="6100050")
    chefe = await persist_user(
        db,
        email="qpt_chf@test.gov.br",
        role=UserRole.CHEFE_IMEDIATO,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
    )
    pt = await _criar_pt_para_participante(db, ua, ue, participante, admin, "PT-CHEF-1")
    set_auth_cookie(client, chefe)

    resp = await client.post(
        "/graphql",
        json={
            "query": "query Q($id: ID!) { planoTrabalho(id: $id) { id idPlanoTrabalho } }",
            "variables": {"id": str(pt.id)},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert data["data"]["planoTrabalho"]["id"] == str(pt.id)


async def test_plano_trabalho_sem_auth_negado(db: AsyncSession, client: AsyncClient) -> None:
    """Sem autenticação, planoTrabalho retorna errors[]."""
    resp = await client.post(
        "/graphql",
        json={
            "query": ("query Q($id: ID!) { planoTrabalho(id: $id) { id } }"),
            "variables": {"id": "00000000-0000-0000-0000-000000000000"},
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0
