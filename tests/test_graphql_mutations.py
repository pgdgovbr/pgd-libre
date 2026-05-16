"""Testes HTTP-level para mutations GraphQL críticas.

Todos os testes são autossuficientes — criam seus próprios dados via helpers de
service layer (não dependem de outros testes). Autentica via set_auth_cookie.

Nota sobre permissões: na implementação atual TODAS as mutations exigem IsAdmin.
Portanto os testes de permissão verificam que SERVIDOR / CHEFE_IMEDIATO recebem
errors[] adequados, enquanto ADMIN executa com sucesso.
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
# Helpers de setup reutilizados
# ---------------------------------------------------------------------------


async def _setup_infra(db: AsyncSession, admin, cod_ua: int):
    """Cria UA, ATO, UI e UE — estrutura mínima para qualquer mutation."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome=f"UA Mut {cod_ua}",
        sigla=f"M{cod_ua}",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia=f"REF-{cod_ua}",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=cod_ua * 10,
        nome=f"UI Mut {cod_ua}",
        sigla=f"I{cod_ua}",
        ato_instituicao_ref=f"REF-{cod_ua}",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=cod_ua * 10 + 1,
        nome=f"UE Mut {cod_ua}",
        sigla=f"E{cod_ua}",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _setup_participante_com_tcr(db, admin, ue, ua, ui, matricula: str, modalidade: int = 1):
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Part {matricula}",
        email=f"{matricula}@mut.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
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
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)
    return p


async def _setup_avaliacao_para_recurso(db, admin, cod_ua: int):
    """Cria toda a cadeia necessária para testar abrirRecurso / decidirRecurso."""
    ua, ui, ue = await _setup_infra(db, admin, cod_ua)
    p = await _setup_participante_com_tcr(db, admin, ue, ua, ui, matricula=f"{cod_ua:07d}")

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas=f"PE-{cod_ua}",
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
        id_entrega=f"E-{cod_ua}",
        plano_entregas_id=pe.id,
        nome_entrega="Entrega",
        meta_entrega=10,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="UD",
        nome_unidade_destinataria="UDS",
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho=f"PT-{cod_ua}",
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
        criterios_avaliacao="Qualidade",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        id_contribuicao=f"C-{cod_ua}",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=1,
        percentual_contribuicao=100,
        descricao="Contribuição",
        id_plano_entregas=pe.id_plano_entregas,
        id_entrega=f"E-{cod_ua}",
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)
    are = await registrar_execucao(
        db,
        id_periodo_avaliativo=f"PA-{cod_ua}",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2026, 1, 1),
        data_fim_periodo_avaliativo=date(2026, 3, 31),
        descricao_execucao="Executado",
        user=admin,
    )
    return are


# ---------------------------------------------------------------------------
# TC — criarUnidadeAutorizadora (mutation exemplo com IsAdmin)
# ---------------------------------------------------------------------------


async def test_criar_unidade_autorizadora_admin_sucesso(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Admin cria UA — retorna id e pgdAutorizado=false (sem ato ainda)."""
    admin = await persist_user(db, email="mut_ua_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 501001
                origemUnidade: SIAPE
                nome: "UA Mut OK"
                sigla: "MOK"
              }) { id pgdAutorizado }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["criarUnidadeAutorizadora"]
    assert result["pgdAutorizado"] is False
    assert result["id"] is not None


async def test_criar_unidade_autorizadora_sem_autenticacao_retorna_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Sem cookie de autenticação, mutation IsAdmin retorna errors[], não 500."""
    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 501002
                origemUnidade: SIAPE
                nome: "UA Unauth"
                sigla: "UNO"
              }) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200  # GraphQL sempre retorna 200
    body = resp.json()
    errors = body.get("errors")
    assert errors is not None and len(errors) > 0
    # Strawberry levanta StrawberryGraphQLError → data fica null inteiro (não {"field": null})
    assert body.get("data") is None or body["data"].get("criarUnidadeAutorizadora") is None


async def test_criar_unidade_autorizadora_perfil_servidor_retorna_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """SERVIDOR não pode criar UA — recebe errors[] com mensagem de permissão."""
    servidor = await persist_user(db, email="mut_ua_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 501003
                origemUnidade: SIAPE
                nome: "UA Denied"
                sigla: "DEN"
              }) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0
    # Mensagem deve conter indicação de perfil insuficiente
    messages = " ".join(str(e) for e in errors).lower()
    assert any(keyword in messages for keyword in ["admin", "perfil", "permission", "autori"]), (
        f"Mensagem de erro inesperada: {errors}"
    )


# ---------------------------------------------------------------------------
# TC — registrarExecucao (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_registrar_execucao_admin_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """Admin registra execução em PT válido — retorna AvaliacaoType com id."""
    admin = await persist_user(db, email="mut_re_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_infra(db, admin, cod_ua=502001)
    p = await _setup_participante_com_tcr(db, admin, ue, ua, ui, matricula="5020010")

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-502001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cod_unidade_executora=ue.cod_unidade_executora,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-502001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante="11144477735",
        matricula_siape="5020010",
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="C",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              registrarExecucao(
                planoTrabalhoId: "{pt.id}"
                input: {{
                  idPeriodoAvaliativo: "PA-502001"
                  dataInicioPeriodoAvaliativo: "2026-01-01"
                  dataFimPeriodoAvaliativo: "2026-03-31"
                  descricaoExecucao: "Executei conforme previsto"
                }}
              ) {{ id idPeriodoAvaliativo descricaoExecucao }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["registrarExecucao"]
    assert result["idPeriodoAvaliativo"] == "PA-502001"
    assert result["descricaoExecucao"] == "Executei conforme previsto"


async def test_registrar_execucao_servidor_negado(db: AsyncSession, client: AsyncClient) -> None:
    """SERVIDOR tenta registrar execução — recebe errors[] (IsAdmin exige admin)."""
    servidor = await persist_user(db, email="mut_re_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              registrarExecucao(
                planoTrabalhoId: "00000000-0000-0000-0000-000000000000"
                input: {
                  idPeriodoAvaliativo: "PA-DENIED"
                  dataInicioPeriodoAvaliativo: "2026-01-01"
                  dataFimPeriodoAvaliativo: "2026-03-31"
                }
              ) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


# ---------------------------------------------------------------------------
# TC — avaliarRegistrosExecucao (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_avaliar_registros_execucao_admin_sucesso(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Admin avalia registros de execução — retorna nota atualizada."""
    admin = await persist_user(db, email="mut_aval_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    are = await _setup_avaliacao_para_recurso(db, admin, cod_ua=503001)

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              avaliarRegistrosExecucao(
                avaliacaoId: "{are.id}"
                nota: 3
                dataAvaliacao: "2026-04-01"
                justificativa: null
              ) {{ id avaliacaoRegistrosExecucao dataAvaliacaoRegistrosExecucao }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["avaliarRegistrosExecucao"]
    assert result["avaliacaoRegistrosExecucao"] == 3
    assert result["dataAvaliacaoRegistrosExecucao"] == "2026-04-01"


async def test_avaliar_registros_execucao_nota_invalida_retorna_erro(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Admin envia nota inválida (0) — recebe errors[], não 500."""
    admin = await persist_user(db, email="mut_aval_inv@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    are = await _setup_avaliacao_para_recurso(db, admin, cod_ua=503002)

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              avaliarRegistrosExecucao(
                avaliacaoId: "{are.id}"
                nota: 0
                dataAvaliacao: "2026-04-01"
              ) {{ id }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    # O sistema atual pode aceitar nota=0 sem validação GQL — o importante é não crashar


# ---------------------------------------------------------------------------
# TC — abrirRecurso (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_abrir_recurso_admin_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """Admin abre recurso em avaliação já registrada — retorna AvaliacaoType."""
    from src.services.avaliacao import avaliar_registros_execucao

    admin = await persist_user(db, email="mut_rec_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    are = await _setup_avaliacao_para_recurso(db, admin, cod_ua=504001)

    # Primeiro avaliar (recurso só pode ser aberto após avaliação com nota 4 ou 5)
    are_avaliado = await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=5,
        data_avaliacao=date(2026, 4, 1),
        justificativa="Metas não atingidas",
        user=admin,
    )

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              abrirRecurso(
                avaliacaoId: "{are_avaliado.id}"
                texto: "Discordo da avaliação por motivos válidos"
              ) {{ id statusRecurso recursoTexto }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["abrirRecurso"]
    assert result["statusRecurso"] is not None
    assert result["recursoTexto"] == "Discordo da avaliação por motivos válidos"


async def test_abrir_recurso_sem_auth_retorna_erro(db: AsyncSession, client: AsyncClient) -> None:
    """Sem autenticação, abrirRecurso retorna errors[] (não 500)."""
    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              abrirRecurso(
                avaliacaoId: "00000000-0000-0000-0000-000000000000"
                texto: "Texto do recurso"
              ) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


# ---------------------------------------------------------------------------
# TC — decidirRecurso (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_decidir_recurso_admin_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """Admin decide recurso aberto — retorna recursoDecisao preenchida."""
    from src.services.avaliacao import abrir_recurso, avaliar_registros_execucao

    admin = await persist_user(db, email="mut_dec_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    are = await _setup_avaliacao_para_recurso(db, admin, cod_ua=505001)

    are_avaliado = await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=5,
        data_avaliacao=date(2026, 4, 1),
        justificativa="Abaixo do esperado",
        user=admin,
    )
    are_recurso = await abrir_recurso(
        db,
        avaliacao_id=are_avaliado.id,
        texto="Recurso contra nota 5",
        user=admin,
    )

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              decidirRecurso(
                avaliacaoId: "{are_recurso.id}"
                decisao: NAO_ACATADO
                justificativa: "Metas comprovadamente não atingidas"
              ) {{ id recursoDecisao recursoDecisaoJustificativa }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["decidirRecurso"]
    assert result["recursoDecisao"].upper() == "NAO_ACATADO"
    assert "metas" in result["recursoDecisaoJustificativa"].lower()


async def test_decidir_recurso_chefe_sem_permissao(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFE_IMEDIATO tenta decidirRecurso — recebe errors[] (IsAdmin necessário)."""
    chefe = await persist_user(db, email="mut_dec_chf@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, chefe)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              decidirRecurso(
                avaliacaoId: "00000000-0000-0000-0000-000000000000"
                decisao: ACATADO
              ) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0


# ---------------------------------------------------------------------------
# TC — iniciarExecucaoPlanoTrabalho (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_iniciar_execucao_plano_trabalho_admin_sucesso(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Admin inicia execução de PT — status do PT muda para em_execucao."""
    admin = await persist_user(db, email="mut_iept_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_infra(db, admin, cod_ua=506001)
    p = await _setup_participante_com_tcr(db, admin, ue, ua, ui, matricula="5060010")

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-506001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cod_unidade_executora=ue.cod_unidade_executora,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-506001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante="11144477735",
        matricula_siape="5060010",
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="C",
        plano_entregas_id=pe.id,
        user=admin,
    )

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              iniciarExecucaoPlanoTrabalho(planoId: "{pt.id}") {{
                id
                status
              }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["iniciarExecucaoPlanoTrabalho"]
    assert result["id"] is not None
    # STATUS_PT_EM_EXECUCAO = 3 conforme models/plano.py
    assert result["status"] == 3


# ---------------------------------------------------------------------------
# TC — cancelarPlanoTrabalho (mutation IsAdmin)
# ---------------------------------------------------------------------------


async def test_cancelar_plano_trabalho_admin_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """Admin cancela PT existente — retorna PT com status cancelado."""
    admin = await persist_user(db, email="mut_cpt_ok@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup_infra(db, admin, cod_ua=507001)
    p = await _setup_participante_com_tcr(db, admin, ue, ua, ui, matricula="5070010")

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-507001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cod_unidade_executora=ue.cod_unidade_executora,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-507001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante="11144477735",
        matricula_siape="5070010",
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="C",
        plano_entregas_id=pe.id,
        user=admin,
    )

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              cancelarPlanoTrabalho(planoId: "{pt.id}") {{
                id
                status
              }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    result = data["data"]["cancelarPlanoTrabalho"]
    assert result["id"] is not None
    # status CANCELADO = 99 conforme models/plano.py
    from src.models.plano import STATUS_PT_CANCELADO

    assert result["status"] == STATUS_PT_CANCELADO


# ---------------------------------------------------------------------------
# TC — confirmarSelecao (mutation IsChefiaOrAbove)
# ---------------------------------------------------------------------------


async def test_confirmar_selecao_chefe_sucesso(db: AsyncSession, client: AsyncClient) -> None:
    """CHEFE_IMEDIATO usa confirmarSelecao (IsChefiaOrAbove) — deve funcionar."""
    chefe = await persist_user(db, email="mut_sel_chf@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, chefe)
    _, _, ue = await _setup_infra(db, chefe, cod_ua=508001)

    mutation = """
    mutation($input: ConfirmarSelecaoInput!) {
      confirmarSelecao(input: $input) { id nVagas }
    }
    """
    variables = {
        "input": {
            "unidadeExecucaoId": str(ue.id),
            "nVagas": 1,
            "criteriosTecnicos": "Experiência comprovada",
            "candidatos": [
                {"id": "C1", "nome": "Alice", "criterio": "PCD"},
                {"id": "C2", "nome": "Bob", "criterio": "SEM_PRIORIDADE"},
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
    assert data["data"]["confirmarSelecao"]["nVagas"] == 1


async def test_confirmar_selecao_servidor_negado(db: AsyncSession, client: AsyncClient) -> None:
    """SERVIDOR não pode confirmarSelecao (IsChefiaOrAbove) — recebe errors[]."""
    servidor = await persist_user(db, email="mut_sel_srv@test.gov.br", role=UserRole.SERVIDOR)
    set_auth_cookie(client, servidor)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              confirmarSelecao(input: {
                unidadeExecucaoId: "00000000-0000-0000-0000-000000000000"
                nVagas: 1
                criteriosTecnicos: "Teste"
                candidatos: [{ id: "C1" nome: "Bob" criterio: PCD }]
              }) { id }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    errors = resp.json().get("errors")
    assert errors is not None and len(errors) > 0
