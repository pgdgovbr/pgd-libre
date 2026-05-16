"""TDD — Testes para queries/mutations de ARE e Convocação que estavam faltando no schema GraphQL.

Cobre:
- planoTrabalho.avaliacoes (campo faltava em PlanoTrabalhoType)
- registroExecucao(id) query standalone
- listarConvocacoes(participanteId) query
- registrarComparecimento mutation
- cancelarConvocacao mutation
"""

from datetime import date, timedelta

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
    criar_convocacao,
    pactu_tcr,
)
from src.services.plano_trabalho import (
    criar_plano_trabalho,
    iniciar_execucao_pt,
    registrar_execucao,
)
from tests.conftest import persist_user, set_auth_cookie

TODAY = date.today()


# ---------------------------------------------------------------------------
# Fixture de infraestrutura mínima
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession):
    admin = await persist_user(db, email="adm@t.com", role=UserRole.ADMIN)
    chefe = await persist_user(db, email="chefe@t.com", role=UserRole.CHEFE_IMEDIATO)
    serv_user = await persist_user(db, email="srv@t.com", role=UserRole.SERVIDOR)

    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA T",
        sigla="UAT",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min",
        data_publicacao=date(2024, 1, 1),
        referencia="REF-T",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=10,
        nome="UI T",
        sigla="UIT",
        ato_instituicao_ref="REF-T",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=11,
        nome="UE T",
        sigla="UET",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="7654321",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="52998224725",
        nome="Servidor T",
        email="srv@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=chefe.id,
        modalidade_execucao=1,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=chefe,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=chefe)

    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-T",
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
        criterios_avaliacao="C",
        user=chefe,
    )
    pt = await iniciar_execucao_pt(db, plano_id=pt.id, user=chefe)

    are = await registrar_execucao(
        db,
        id_periodo_avaliativo="P-T-001",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2024, 3, 1),
        data_fim_periodo_avaliativo=date(2024, 3, 31),
        descricao_execucao="Executei as atividades do mês",
        user=p.user if hasattr(p, "user") else serv_user,
    )

    conv = await criar_convocacao(
        db,
        participante_id=p.id,
        unidade_execucao_id=ue.id,
        chefia_user_id=chefe.id,
        canal_comunicacao="email",
        data_convocacao=TODAY,
        data_comparecimento_prevista=TODAY + timedelta(days=10),
        horario_comparecimento="09:00",
        local_comparecimento="Sala 101",
        periodo_presencial_inicio=TODAY + timedelta(days=10),
        periodo_presencial_fim=TODAY + timedelta(days=10),
        motivo="Reunião de alinhamento",
        user=chefe,
    )

    return {
        "admin": admin,
        "chefe": chefe,
        "serv_user": serv_user,
        "ua": ua,
        "ue": ue,
        "p": p,
        "tcr": tcr,
        "pt": pt,
        "are": are,
        "conv": conv,
    }


# ---------------------------------------------------------------------------
# A1b — servidor vê seus próprios planos via meusPlanosTrabalho
# ---------------------------------------------------------------------------


async def test_meus_planos_trabalho_para_servidor(client: AsyncClient, db: AsyncSession):
    """Servidor deve ver seus próprios planos via meusPlanosTrabalho."""
    ctx = await _setup(db)
    # serv_user já foi criado no setup com email srv@t.com (mesmo do participante)
    set_auth_cookie(client, ctx["serv_user"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                query {
                    meusPlanosTrabalho {
                        id
                        avaliacoes {
                            id
                            idPeriodoAvaliativo
                        }
                    }
                }
            """,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    planos = data["data"]["meusPlanosTrabalho"]
    assert len(planos) == 1
    assert len(planos[0]["avaliacoes"]) == 1


# ---------------------------------------------------------------------------
# A1 — planoTrabalho.avaliacoes exposto no GraphQL
# ---------------------------------------------------------------------------


async def test_plano_trabalho_expoe_avaliacoes(client: AsyncClient, db: AsyncSession):
    """planoTrabalho(id) deve retornar campo avaliacoes com os registros."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                query($id: ID!) {
                    planoTrabalho(id: $id) {
                        id
                        avaliacoes {
                            id
                            idPeriodoAvaliativo
                            descricaoExecucao
                            avaliacaoRegistrosExecucao
                        }
                    }
                }
            """,
            "variables": {"id": str(ctx["pt"].id)},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    pt = data["data"]["planoTrabalho"]
    assert pt is not None
    assert len(pt["avaliacoes"]) == 1
    are = pt["avaliacoes"][0]
    assert are["idPeriodoAvaliativo"] == "P-T-001"
    assert are["descricaoExecucao"] == "Executei as atividades do mês"
    assert are["avaliacaoRegistrosExecucao"] is None  # ainda não avaliada


# ---------------------------------------------------------------------------
# A2 — registroExecucao(id) query standalone
# ---------------------------------------------------------------------------


async def test_registro_execucao_query_retorna_are(client: AsyncClient, db: AsyncSession):
    """registroExecucao(id) deve retornar o ARE pelo id."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                query($id: ID!) {
                    registroExecucao(id: $id) {
                        id
                        idPeriodoAvaliativo
                        descricaoExecucao
                        statusRecurso
                    }
                }
            """,
            "variables": {"id": str(ctx["are"].id)},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    are = data["data"]["registroExecucao"]
    assert are is not None
    assert are["idPeriodoAvaliativo"] == "P-T-001"
    assert are["statusRecurso"] is None


async def test_registro_execucao_query_id_invalido_retorna_none(
    client: AsyncClient, db: AsyncSession
):
    """registroExecucao(id) com id inexistente deve retornar null."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                query {
                    registroExecucao(id: "00000000-0000-0000-0000-000000000000") {
                        id
                    }
                }
            """,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    assert data["data"]["registroExecucao"] is None


# ---------------------------------------------------------------------------
# A3 — listarConvocacoes query
# ---------------------------------------------------------------------------


async def test_listar_convocacoes_retorna_lista(client: AsyncClient, db: AsyncSession):
    """listarConvocacoes(participanteId) deve retornar convocações do participante."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                query($pid: ID!) {
                    listarConvocacoes(participanteId: $pid) {
                        id
                        motivo
                        status
                        dataComparecimentoPrevista
                    }
                }
            """,
            "variables": {"pid": str(ctx["p"].id)},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    convs = data["data"]["listarConvocacoes"]
    assert len(convs) == 1
    assert convs[0]["motivo"] == "Reunião de alinhamento"
    assert convs[0]["status"] == "PENDENTE"


# ---------------------------------------------------------------------------
# A3 — registrarComparecimento mutation
# ---------------------------------------------------------------------------


async def test_registrar_comparecimento_muda_status_para_atendida(
    client: AsyncClient, db: AsyncSession
):
    """registrarComparecimento deve atualizar status para ATENDIDA."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                mutation($id: ID!, $data: Date!) {
                    registrarComparecimento(convocacaoId: $id, dataEfetiva: $data) {
                        id
                        status
                        dataComparecimentoEfetivo
                    }
                }
            """,
            "variables": {
                "id": str(ctx["conv"].id),
                "data": str(TODAY + timedelta(days=10)),
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    conv = data["data"]["registrarComparecimento"]
    assert conv["status"] == "ATENDIDA"
    assert conv["dataComparecimentoEfetivo"] == str(TODAY + timedelta(days=10))


# ---------------------------------------------------------------------------
# A3 — cancelarConvocacao mutation
# ---------------------------------------------------------------------------


async def test_cancelar_convocacao_muda_status_para_cancelada(
    client: AsyncClient, db: AsyncSession
):
    """cancelarConvocacao deve mudar status para CANCELADA."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                mutation($id: ID!) {
                    cancelarConvocacao(convocacaoId: $id) {
                        id
                        status
                    }
                }
            """,
            "variables": {"id": str(ctx["conv"].id)},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data, data.get("errors")
    conv = data["data"]["cancelarConvocacao"]
    assert conv["status"] == "CANCELADA"


# ---------------------------------------------------------------------------
# A3 — validação de prazo de convocação
# ---------------------------------------------------------------------------


async def test_criar_convocacao_com_prazo_insuficiente_falha(client: AsyncClient, db: AsyncSession):
    """criar_convocacao com data_comparecimento_prevista < prazo mínimo do TCR deve falhar."""
    ctx = await _setup(db)
    set_auth_cookie(client, ctx["chefe"])

    # TCR tem prazo_antecedencia_convocacao_dias=5; usar data em 2 dias deve falhar
    data_invalida = TODAY + timedelta(days=2)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
                mutation($pid: ID!, $ueid: ID!, $data: Date!) {
                    criarConvocacao(
                        participanteId: $pid
                        unidadeExecucaoId: $ueid
                        input: {
                            canalComunicacao: "email"
                            dataConvocacao: "2024-01-01"
                            dataComparecimentoPrevista: $data
                            horarioComparecimento: "09:00"
                            localComparecimento: "Sala 1"
                            periodoPresencialInicio: $data
                            periodoPresencialFim: $data
                            motivo: "Reunião urgente"
                        }
                    ) { id }
                }
            """,
            "variables": {
                "pid": str(ctx["p"].id),
                "ueid": str(ctx["ue"].id),
                "data": str(data_invalida),
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Deve retornar erro de prazo insuficiente
    assert data.get("errors") or (data.get("data", {}).get("criarConvocacao") is None), (
        "Esperava erro de prazo insuficiente"
    )
