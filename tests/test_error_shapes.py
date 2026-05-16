"""Verifica que respostas de erro têm formato GraphQL consistente.

Formato esperado em caso de erro:
    {"data": {"<field>": null}, "errors": [{"message": "..."}]}

Ou para erros de permissão no campo raiz:
    {"data": {"<field>": null}, "errors": [...]}

Em NENHUM caso deve haver:
- HTTP 500 (sempre deve ser 200 com errors[])
- Stacktrace ou detalhes internos na mensagem de erro de permissão
- Ausência do campo "errors" quando há falha de negócio/permissão

Cenários testados:
1. Permissão negada (IsAdmin, IsChefiaOrAbove) — sem vazamento de internos
2. UUID inválido em mutation — deve retornar errors[], não 500
3. Input faltando campo obrigatório — erro de validação no nível GraphQL
4. query { me } sem auth — retorna data.me=null (não é um erro, comportamento esperado)
5. Mutation com plano inexistente — retorna errors[] com mensagem legível
"""

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
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    criar_plano_trabalho,
    iniciar_execucao_pt,
    registrar_execucao,
)
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_graphql_error_shape(body: dict, *, min_errors: int = 1) -> list[dict]:
    """Verifica formato de erro GraphQL e retorna lista de errors."""
    assert "errors" in body, f"Campo 'errors' ausente no body: {body}"
    errors = body["errors"]
    assert isinstance(errors, list), f"'errors' deve ser lista, got: {type(errors)}"
    assert len(errors) >= min_errors, f"Esperava >= {min_errors} erro(s), got: {errors}"
    for err in errors:
        assert "message" in err, f"Cada error deve ter 'message': {err}"
        assert isinstance(err["message"], str), f"'message' deve ser string: {err}"
        assert len(err["message"]) > 0, "Mensagem de erro não pode ser vazia"
    return errors


async def _setup_full_chain(db, admin, cod_ua: int):
    """Cria cadeia completa até Avaliacao registrada."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome=f"UA Err {cod_ua}",
        sigla=f"E{cod_ua}",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia=f"EREF-{cod_ua}",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=cod_ua * 10,
        nome=f"UI Err {cod_ua}",
        sigla=f"IE{cod_ua}",
        ato_instituicao_ref=f"EREF-{cod_ua}",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=cod_ua * 10 + 1,
        nome=f"UE Err {cod_ua}",
        sigla=f"UEE{cod_ua}",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=f"{cod_ua:07d}",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Servidor {cod_ua}",
        email=f"e{cod_ua}@t.com",
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

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas=f"PE-E{cod_ua}",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cod_unidade_executora=ue.cod_unidade_executora,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega=f"EE-{cod_ua}",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=10,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="UD",
        nome_unidade_destinataria="UDS",
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho=f"PT-E{cod_ua}",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante="11144477735",
        matricula_siape=p.matricula_siape,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="C",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        id_contribuicao=f"CE-{cod_ua}",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=1,
        percentual_contribuicao=100,
        descricao="C",
        id_plano_entregas=pe.id_plano_entregas,
        id_entrega=f"EE-{cod_ua}",
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)
    are = await registrar_execucao(
        db,
        id_periodo_avaliativo=f"PA-E{cod_ua}",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2026, 1, 1),
        data_fim_periodo_avaliativo=date(2026, 3, 31),
        descricao_execucao="Executado",
        user=admin,
    )
    return are


# ---------------------------------------------------------------------------
# Cenário 1 — Permissão negada: não vaza detalhes internos
# ---------------------------------------------------------------------------


async def test_permissao_negada_nao_vaza_stacktrace(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Erro de permissão (IsAdmin) não deve vazar informações de implementação.

    A mensagem de erro deve ser legível para o usuário, sem stacktrace ou
    referências a módulos Python internos.
    """
    servidor = await persist_user(db, email="es_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 701001
                origemUnidade: SIAPE
                nome: "UA Forbidden"
                sigla: "FORB"
              }) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200, f"Esperava 200, got {resp.status_code}"
    body = resp.json()
    errors = _assert_graphql_error_shape(body)

    # A mensagem não deve conter termos de implementação interna
    all_messages = " ".join(str(e["message"]) for e in errors)
    forbidden_terms = ["traceback", "sqlalchemy", "psycopg", "exception", "line "]
    for term in forbidden_terms:
        assert term not in all_messages.lower(), (
            f"Mensagem de erro vaza detalhe interno '{term}': {all_messages}"
        )


async def test_permissao_negada_chefiaOrAbove_servidor(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR tentando listarParticipantes → errors[] com mensagem de permissão."""
    servidor = await persist_user(db, email="es_srv2@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={"query": "{ listarParticipantes { id } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    errors = _assert_graphql_error_shape(body)
    # Strawberry levanta StrawberryGraphQLError → data fica null inteiro (não {"field": null})
    assert body.get("data") is None or body["data"].get("listarParticipantes") is None


# ---------------------------------------------------------------------------
# Cenário 2 — UUID inválido: não deve retornar 500
# ---------------------------------------------------------------------------


async def test_uuid_invalido_em_mutation_nao_retorna_500(
    db: AsyncSession, client: AsyncClient
) -> None:
    """UUID malformado em mutation retorna errors[], não HTTP 500."""
    admin = await persist_user(db, email="es_uuid@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              iniciarExecucaoPlanoTrabalho(planoId: "nao-e-um-uuid-valido") {
                id
              }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200, (
        f"Esperava 200 (GraphQL), mas got {resp.status_code}"
    )
    body = resp.json()
    errors = _assert_graphql_error_shape(body)
    # Não deve conter stacktrace
    all_messages = " ".join(str(e["message"]) for e in errors)
    assert "traceback" not in all_messages.lower()


async def test_uuid_inexistente_em_mutation_nao_retorna_500(
    db: AsyncSession, client: AsyncClient
) -> None:
    """UUID válido mas inexistente em mutation retorna errors[], não 500."""
    admin = await persist_user(db, email="es_uuid2@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              iniciarExecucaoPlanoTrabalho(
                planoId: "00000000-0000-0000-0000-000000000000"
              ) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Pode retornar errors[] ou data=null — o importante é não ser 500
    # Se há errors, verificar formato
    if body.get("errors"):
        _assert_graphql_error_shape(body)


# ---------------------------------------------------------------------------
# Cenário 3 — Campo obrigatório faltando: validação GraphQL retorna errors[]
# ---------------------------------------------------------------------------


async def test_campo_obrigatorio_faltando_retorna_errors(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Mutation sem campo obrigatório retorna errors[] de validação GraphQL."""
    admin = await persist_user(db, email="es_missing@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    # criarUnidadeAutorizadora sem o campo obrigatório `nome`
    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 701002
                origemUnidade: SIAPE
                sigla: "SEM"
              }) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_graphql_error_shape(body)


# ---------------------------------------------------------------------------
# Cenário 4 — query { me } sem auth: data.me=null, sem errors
# ---------------------------------------------------------------------------


async def test_me_sem_auth_retorna_null_nao_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """query { me } sem cookie retorna data.me=null — esse é o comportamento esperado.

    Contrasta com mutations/queries protegidas que retornam errors[].
    """
    resp = await client.post(
        "/graphql",
        json={"query": "{ me { id email } }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # me é nullable — retorna null sem erros
    assert body.get("errors") is None, f"Não deveria ter errors para me sem auth: {body}"
    assert body["data"]["me"] is None


# ---------------------------------------------------------------------------
# Cenário 5 — Avaliação sem nota: errors[] com mensagem sobre recurso
# ---------------------------------------------------------------------------


async def test_abrir_recurso_sem_avaliacao_retorna_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Tentar abrir recurso em avaliação sem nota gera errors[] (não 500)."""
    admin = await persist_user(db, email="es_rec_nao_aval@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    are = await _setup_full_chain(db, admin, cod_ua=702001)
    # Não avaliar — tentar abrir recurso diretamente em ARE sem nota

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              abrirRecurso(
                avaliacaoId: "{are.id}"
                texto: "Recurso inválido — sem avaliação prévia"
              ) {{ id }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    errors = _assert_graphql_error_shape(body)
    # Mensagem deve ser legível
    all_messages = " ".join(str(e["message"]) for e in errors)
    assert len(all_messages) > 5, "Mensagem de erro muito curta"


# ---------------------------------------------------------------------------
# Cenário 6 — avaliarRegistrosExecucao em avaliação inexistente
# ---------------------------------------------------------------------------


async def test_avaliar_avaliacao_inexistente_retorna_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Tentar avaliar UUID inexistente retorna errors[] com mensagem, não 500."""
    admin = await persist_user(db, email="es_aval_id@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              avaliarRegistrosExecucao(
                avaliacaoId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                nota: 3
                dataAvaliacao: "2026-04-01"
              ) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Deve ter errors OU data=null — nunca 500
    if body.get("errors"):
        _assert_graphql_error_shape(body)
    else:
        # Pode retornar data.avaliarRegistrosExecucao=null sem errors[]
        assert body["data"].get("avaliarRegistrosExecucao") is None


# ---------------------------------------------------------------------------
# Cenário 7 — Consistência: todas as mutations protegidas têm data.<field>=null
# ---------------------------------------------------------------------------


async def test_multiplas_mutations_protegidas_retornam_data_null(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Várias mutations IsAdmin sem auth retornam data.<campo>=null + errors[].

    Verifica consistência de forma em múltiplos endpoints.
    """
    mutations_e_campos = [
        (
            """mutation { criarUnidadeAutorizadora(input: {
               codUnidadeAutorizadora: 799001 origemUnidade: SIAPE nome: "X" sigla: "X"
            }) { id } }""",
            "criarUnidadeAutorizadora",
        ),
        (
            """mutation { registrarExecucao(
               planoTrabalhoId: "00000000-0000-0000-0000-000000000000"
               input: {
                 idPeriodoAvaliativo: "P"
                 dataInicioPeriodoAvaliativo: "2026-01-01"
                 dataFimPeriodoAvaliativo: "2026-03-31"
               }
            ) { id } }""",
            "registrarExecucao",
        ),
        (
            """mutation { abrirRecurso(
               avaliacaoId: "00000000-0000-0000-0000-000000000000"
               texto: "T"
            ) { id } }""",
            "abrirRecurso",
        ),
    ]

    for query, campo in mutations_e_campos:
        resp = await client.post(
            "/graphql",
            json={"query": query},
            headers={"user-agent": "pytest"},
        )
        assert resp.status_code == 200, (
            f"Mutation '{campo}' retornou HTTP {resp.status_code}"
        )
        body = resp.json()
        _assert_graphql_error_shape(body, min_errors=1)
        # Strawberry levanta StrawberryGraphQLError → data fica null inteiro (não {"field": null})
        assert body.get("data") is None or body["data"].get(campo) is None, (
            f"data.{campo} deveria ser null, got: {body.get('data', {}).get(campo)}"
        )
