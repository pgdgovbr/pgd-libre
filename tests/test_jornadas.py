"""Sprint 2.5 — Jornadas de Usuário E2E (JU-01 a JU-07).

Cada jornada verifica um fluxo completo end-to-end via serviços (banco real) e
mutações GraphQL onde a Sprint 2.4 introduziu novos endpoints. As jornadas são
independentes entre si (cada uma cria seu próprio estado).
"""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.institucional import OrigemUnidade, StatusPgd, UnidadeExecucao
from src.models.notificacao import Notificacao
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import (
    STATUS_PE_EM_EXECUCAO,
    STATUS_PT_CANCELADO,
    STATUS_PT_EM_EXECUCAO,
    TipoMeta,
    PlanoTrabalho,
)
from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync
from src.models.user import UserRole
from src.services.avaliacao import avaliar_registros_execucao, abrir_recurso, decidir_recurso
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
    suspender_pgd,
)
from src.services.participante import (
    assinar_tcr_chefia,
    cadastrar_participante,
    pactu_tcr,
)
from src.services.plano_entregas import (
    avaliar_pe,
    concluir_pe,
    criar_entrega,
    criar_plano_entregas,
    iniciar_execucao_pe,
)
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    criar_plano_trabalho,
    iniciar_execucao_pt,
    registrar_execucao,
)
from src.models.plano import DecisaoRecurso
from tests.conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Helpers comuns
# ---------------------------------------------------------------------------


async def _base(db: AsyncSession, admin, cod_ua: int):
    """Retorna (ua, ui, ue) para um código de unidade autorizadora dado."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome=f"UA JU {cod_ua}",
        sigla=f"U{cod_ua}",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia=f"REF{cod_ua}",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=cod_ua * 10,
        nome=f"UI JU {cod_ua}",
        sigla=f"I{cod_ua}",
        ato_instituicao_ref=f"REF{cod_ua}",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=cod_ua * 10 + 1,
        nome=f"UE JU {cod_ua}",
        sigla=f"E{cod_ua}",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _participante(db, admin, ue, ua, ui, matricula: str, modalidade: int = 1):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Part {matricula}",
        email=f"{matricula}@ju.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        cumpriu_estagio_probatorio=True if modalidade in (2, 3, 4, 5) else None,
        user=admin,
    )


async def _tcr(db, admin, participante, modalidade: int = 1):
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


async def _pe_com_entrega(db, admin, ue, ua, ui, id_prefix: str):
    pe = await criar_plano_entregas(
        db,
        id_plano_entregas=f"PE-{id_prefix}",
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
        id_entrega=f"E-{id_prefix}",
        plano_entregas_id=pe.id,
        nome_entrega=f"Entrega {id_prefix}",
        meta_entrega=10,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="UD",
        nome_unidade_destinataria="UDS",
        user=admin,
    )
    return pe


async def _pt_com_contribuicao(db, admin, participante, pe, ua, ue, id_prefix: str):
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho=f"PT-{id_prefix}",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=participante.id,
        cpf_participante="11144477735",
        matricula_siape=participante.matricula_siape,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=40,
        criterios_avaliacao="Qualidade",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        id_contribuicao=f"C-{id_prefix}",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=1,
        percentual_contribuicao=100,
        descricao="Contribuição principal",
        id_plano_entregas=pe.id_plano_entregas,
        id_entrega=f"E-{id_prefix}",
        user=admin,
    )
    return pt


def _mock_api_client():
    m = MagicMock()
    m.send_participante = AsyncMock(return_value={"ok": True})
    m.send_plano_entregas = AsyncMock(return_value={"ok": True})
    m.send_plano_trabalho = AsyncMock(return_value={"ok": True})
    return m


# ---------------------------------------------------------------------------
# JU-01 — Configuração inicial do PGD (via GQL)
# ---------------------------------------------------------------------------


async def test_ju01_configuracao_pgd(db: AsyncSession, client: AsyncClient) -> None:
    """JU-01: criarUnidadeAutorizadora → criarAtoAutorizacao → criarUnidadeInstituidora.

    Verifica: pgdAutorizado=true após ATO, UI com status=em_vigor, ≥3 AuditLogs.
    """
    admin = await persist_user(db, email="ju01@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    # 1. Criar UA
    r1 = await client.post(
        "/graphql",
        json={
            "query": """
            mutation {
              criarUnidadeAutorizadora(input: {
                codUnidadeAutorizadora: 301001
                origemUnidade: SIAPE
                nome: "Min. JU01"
                sigla: "MJU01"
              }) { id pgdAutorizado }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r1.status_code == 200
    assert r1.json().get("errors") is None
    ua_id = r1.json()["data"]["criarUnidadeAutorizadora"]["id"]
    assert r1.json()["data"]["criarUnidadeAutorizadora"]["pgdAutorizado"] is False

    # 2. Criar ATO → pgdAutorizado deve virar True
    r2 = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              criarAtoAutorizacao(
                unidadeAutorizadoraId: "{ua_id}"
                input: {{
                  autoridade: "Min. JU01"
                  dataPublicacao: "2024-01-15"
                  referencia: "PORT-JU01"
                }}
              ) {{ id status }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r2.status_code == 200
    assert r2.json().get("errors") is None

    # Verificar pgdAutorizado = true via query
    r_ua = await client.post(
        "/graphql",
        json={"query": f'{{ unidadeAutorizadora(id: "{ua_id}") {{ pgdAutorizado }} }}'},
        headers={"user-agent": "pytest"},
    )
    assert r_ua.json()["data"]["unidadeAutorizadora"]["pgdAutorizado"] is True

    # 3. Criar UI
    r3 = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              criarUnidadeInstituidora(
                unidadeAutorizadoraId: "{ua_id}"
                input: {{
                  codUnidadeInstituidora: 3010010
                  nome: "UI JU01"
                  sigla: "IJU01"
                  atoInstituicaoRef: "PORT-JU01"
                  dataInstituicao: "2024-01-20"
                  tiposAtividades: "TI"
                  conteudoMinimoTcr: "Responsabilidades"
                  prazoAntecedenciaConvocacaoDias: 5
                  modalidadesAutorizadas: [1, 2, 3]
                }}
              ) {{ id status }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r3.status_code == 200
    assert r3.json().get("errors") is None, r3.json().get("errors")
    assert r3.json()["data"]["criarUnidadeInstituidora"]["status"] == "EM_VIGOR"

    # Verificar audit logs (≥3 — um por mutation)
    result = await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.user_id == admin.id
        )
    )
    assert result.scalar_one() >= 3


# ---------------------------------------------------------------------------
# JU-02 — Onboarding de participante até TCR ativo
# ---------------------------------------------------------------------------


async def test_ju02_onboarding_participante(db: AsyncSession, client: AsyncClient) -> None:
    """JU-02: cadastrarParticipante → pactuarTcr → assinarTcrChefia.

    Verifica: TCR com status=ativo no banco.
    """
    admin = await persist_user(db, email="ju02@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _base(db, admin, cod_ua=302001)

    # 1. Criar participante via GQL
    r1 = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              cadastrarParticipante(input: {{
                origemUnidade: SIAPE
                codUnidadeAutorizadora: 302001
                codUnidadeLotacao: {ue.cod_unidade_executora}
                matriculaSiape: "3020010"
                codUnidadeInstituidora: {ui.cod_unidade_instituidora}
                cpf: "11144477735"
                nome: "Maria JU02"
                email: "maria.ju02@test.gov.br"
                modalidadeExecucao: 1
                dataAssinaturaTcr: "2024-03-01"
                tipoVinculo: EFETIVO
                unidadeExecucaoId: "{ue.id}"
              }}) {{ id matriculaSiape }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r1.status_code == 200
    assert r1.json().get("errors") is None, r1.json().get("errors")
    participante_id = r1.json()["data"]["cadastrarParticipante"]["id"]

    # 2. Pactuar TCR
    r2 = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              pactuarTcr(
                participanteId: "{participante_id}"
                input: {{
                  modalidadeExecucao: 1
                  regimeExecucao: INTEGRAL
                  prazoAntecedenciaConvocacaoDias: 5
                  canaisComunicacao: ["email"]
                  responsabilidades: "Cumprir metas"
                  cienciaInstalacoesErgonomia: true
                  cienciaNaoDireitoAdquirido: true
                  cienciaCusteioEstrutura: true
                }}
              ) {{ id status }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r2.status_code == 200
    assert r2.json().get("errors") is None, r2.json().get("errors")
    tcr_id = r2.json()["data"]["pactuarTcr"]["id"]
    assert r2.json()["data"]["pactuarTcr"]["status"] == "PENDENTE"

    # 3. Assinar TCR (chefia)
    r3 = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              assinarTcrChefia(tcrId: "{tcr_id}") {{ id status }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r3.status_code == 200
    assert r3.json().get("errors") is None, r3.json().get("errors")
    assert r3.json()["data"]["assinarTcrChefia"]["status"] == "ATIVO"


# ---------------------------------------------------------------------------
# JU-03 — Ciclo completo plano → aprovação → avaliação
# ---------------------------------------------------------------------------


async def test_ju03_ciclo_plano_avaliacao(db: AsyncSession, client: AsyncClient) -> None:
    """JU-03: PE criado e aprovado (nova mutation) → PT com execução registrada e avaliada.

    Verifica: PE aprovado com aprovador_user_id definido; avaliação registrada no banco.
    """
    admin = await persist_user(db, email="ju03@test.gov.br", role=UserRole.ADMIN)
    aprovador = await persist_user(db, email="ju03apr@test.gov.br", role=UserRole.GESTOR_UNIDADE)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _base(db, admin, cod_ua=303001)

    p = await _participante(db, admin, ue, ua, ui, matricula="3030010")
    tcr = await _tcr(db, admin, p)
    pe = await _pe_com_entrega(db, admin, ue, ua, ui, "JU03")
    pt = await _pt_com_contribuicao(db, admin, p, pe, ua, ue, "JU03")

    # Iniciar execução PT
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    # Registrar execução
    are = await registrar_execucao(
        db,
        id_periodo_avaliativo="PA-JU03-1",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2026, 1, 1),
        data_fim_periodo_avaliativo=date(2026, 3, 31),
        descricao_execucao="Executou conforme previsto",
        user=admin,
    )

    # Avaliar via GQL
    r_aval = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              avaliarRegistrosExecucao(
                avaliacaoId: "{are.id}"
                nota: 4
                dataAvaliacao: "2026-04-15"
                justificativa: "Bom desempenho"
              ) {{ id avaliacaoRegistrosExecucao }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r_aval.status_code == 200
    assert r_aval.json().get("errors") is None, r_aval.json().get("errors")
    assert r_aval.json()["data"]["avaliarRegistrosExecucao"]["avaliacaoRegistrosExecucao"] == 4

    # Aprovar PE via nova mutation GQL (Sprint 2.4)
    r_apr = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              aprovarPlanoEntregas(input: {{
                planoId: "{pe.id}"
                aprovadorUserId: {aprovador.id}
              }}) {{ id aprovadoPorUserId dataAprovacao }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r_apr.status_code == 200
    assert r_apr.json().get("errors") is None, r_apr.json().get("errors")
    result = r_apr.json()["data"]["aprovarPlanoEntregas"]
    assert result["aprovadoPorUserId"] == aprovador.id
    assert result["dataAprovacao"] is not None

    # Concluir e avaliar PE
    await iniciar_execucao_pe(db, plano_id=pe.id, user=admin)
    await concluir_pe(db, plano_id=pe.id, user=admin)
    pe_final = await avaliar_pe(
        db, plano_id=pe.id, avaliacao=4, data_avaliacao=date(2026, 12, 31), user=admin
    )
    assert pe_final.status == 5  # STATUS_PE_AVALIADO
    assert pe_final.avaliacao == 4


# ---------------------------------------------------------------------------
# JU-04 — Ciclo negativo: nota 5, recurso, compensação
# ---------------------------------------------------------------------------


async def test_ju04_ciclo_negativo_recurso(db: AsyncSession) -> None:
    """JU-04: avaliação nota 5 → recurso aberto e não acatado → novo TCR com compensação.

    Verifica: recurso com decisão=NAO_ACATADO, novo TCR com carga_horaria_compensacao.
    """
    admin = await persist_user(db, email="ju04@test.gov.br", role=UserRole.ADMIN)
    ua, ui, ue = await _base(db, admin, cod_ua=304001)

    p = await _participante(db, admin, ue, ua, ui, matricula="3040010")
    await _tcr(db, admin, p)
    pe = await _pe_com_entrega(db, admin, ue, ua, ui, "JU04")
    pt = await _pt_com_contribuicao(db, admin, p, pe, ua, ue, "JU04")
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    # Registrar execução
    are = await registrar_execucao(
        db,
        id_periodo_avaliativo="PA-JU04-1",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2026, 1, 1),
        data_fim_periodo_avaliativo=date(2026, 3, 31),
        descricao_execucao="Abaixo do esperado",
        user=admin,
    )

    # Avaliar com nota 5 (máxima penalidade)
    are = await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=5,
        data_avaliacao=date(2026, 4, 10),
        justificativa="Metas não atingidas",
        user=admin,
    )
    assert are.avaliacao_registros_execucao == 5

    # Participante abre recurso
    are = await abrir_recurso(db, avaliacao_id=are.id, texto="Discordo da avaliação", user=admin)
    assert are.status_recurso is not None

    # Chefia decide: não acatado
    are = await decidir_recurso(
        db,
        avaliacao_id=are.id,
        decisao=DecisaoRecurso.NAO_ACATADO,
        justificativa="Metas comprovadamente não atingidas",
        user=admin,
    )
    assert are.recurso_decisao == DecisaoRecurso.NAO_ACATADO

    # Novo TCR com compensação (consequência de nota 5)
    tcr_comp = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=None,
        modalidade_execucao=1,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R + compensação",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        carga_horaria_compensacao=8,
        prazo_compensacao_inexecucao=date(2026, 6, 30),
        user=admin,
    )
    assert tcr_comp.carga_horaria_compensacao == 8
    assert tcr_comp.prazo_compensacao_inexecucao == date(2026, 6, 30)


# ---------------------------------------------------------------------------
# JU-05 — Seleção com excesso de candidatos (via GQL)
# ---------------------------------------------------------------------------


async def test_ju05_selecao_excesso_candidatos(db: AsyncSession, client: AsyncClient) -> None:
    """JU-05: confirmarSelecao com 5 candidatos e 2 vagas.

    Verifica: apenas 2 selecionados, critérios de prioridade respeitados.
    """
    admin = await persist_user(db, email="ju05@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    _, _, ue = await _base(db, admin, cod_ua=305001)

    mutation = """
    mutation($input: ConfirmarSelecaoInput!) {
      confirmarSelecao(input: $input) {
        id
        nVagas
        resultado
      }
    }
    """
    variables = {
        "input": {
            "unidadeExecucaoId": str(ue.id),
            "nVagas": 2,
            "criteriosTecnicos": "Experiência em gestão e teletrabalho documentada",
            "candidatos": [
                {"id": "C1", "nome": "Alice",   "criterio": "SEM_PRIORIDADE"},
                {"id": "C2", "nome": "Bob",     "criterio": "PCD"},
                {"id": "C3", "nome": "Carla",   "criterio": "MOBILIDADE_REDUZIDA"},
                {"id": "C4", "nome": "Diego",   "criterio": "RESP_PCD"},
                {"id": "C5", "nome": "Eduarda", "criterio": "HORARIO_ESPECIAL"},
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

    resultado = data["data"]["confirmarSelecao"]["resultado"]
    assert data["data"]["confirmarSelecao"]["nVagas"] == 2

    selecionados = [r for r in resultado if r["selecionado"]]
    nao_selecionados = [r for r in resultado if not r["selecionado"]]
    assert len(selecionados) == 2
    assert len(nao_selecionados) == 3

    # PCD e MOBILIDADE_REDUZIDA têm prioridade 0 e 2 — devem estar entre os selecionados
    # (PCD=0, RESP_PCD=1, MOBILIDADE_REDUZIDA=2, HORARIO_ESPECIAL=3, SEM_PRIORIDADE=4)
    criterios_sel = {r["criterio"] for r in selecionados}
    assert "pcd" in criterios_sel
    assert "responsavel_pcd" in criterios_sel  # prioridade 1

    # Alice (sem_prioridade) não deve estar selecionada
    ids_nao_sel = {r["id"] for r in nao_selecionados}
    assert "C1" in ids_nao_sel  # Alice — sem prioridade

    # Verificar ProcessoSelecao no banco via GQL
    ps_id = data["data"]["confirmarSelecao"]["id"]
    assert ps_id is not None


# ---------------------------------------------------------------------------
# JU-06 — Suspensão do PGD e cancelamento de planos
# ---------------------------------------------------------------------------


async def test_ju06_suspensao_pgd_cancela_planos(
    db: AsyncSession, client: AsyncClient
) -> None:
    """JU-06: suspenderPgd cancela todos os PlanoTrabalho em execução.

    Verifica: PTs com status=cancelado e notificação criada.
    """
    admin = await persist_user(db, email="ju06@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _base(db, admin, cod_ua=306001)

    pe = await _pe_com_entrega(db, admin, ue, ua, ui, "JU06")

    # Criar 3 participantes com PT em execução
    pts_ids = []
    for i in range(1, 4):
        p = await _participante(db, admin, ue, ua, ui, matricula=f"306{i:04d}")
        await _tcr(db, admin, p)
        pt = await _pt_com_contribuicao(db, admin, p, pe, ua, ue, f"JU06-{i}")
        await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)
        pts_ids.append(pt.id)

    # Verificar que PTs estão em execução
    result = await db.execute(
        select(PlanoTrabalho).where(PlanoTrabalho.id.in_(pts_ids))
    )
    pts_before = result.scalars().all()
    assert all(pt.status == STATUS_PT_EM_EXECUCAO for pt in pts_before)

    # Suspender PGD via GQL
    r_susp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              suspenderPgd(
                unidadeInstituidoraId: "{ui.id}"
                motivo: "Auditoria de conformidade em andamento"
              ) {{ id status }}
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r_susp.status_code == 200
    assert r_susp.json().get("errors") is None, r_susp.json().get("errors")
    assert r_susp.json()["data"]["suspenderPgd"]["status"] == "SUSPENSO"

    # Verificar PTs cancelados
    await db.refresh(pts_before[0])
    result = await db.execute(
        select(PlanoTrabalho).where(PlanoTrabalho.id.in_(pts_ids))
    )
    pts_after = result.scalars().all()
    assert all(pt.status == STATUS_PT_CANCELADO for pt in pts_after)

    # Verificar notificação criada
    notif_result = await db.execute(select(func.count()).select_from(Notificacao))
    assert notif_result.scalar_one() >= 1


# ---------------------------------------------------------------------------
# JU-07 — Retry de envio à API Central
# ---------------------------------------------------------------------------


async def test_ju07_retry_envio_api_central(db: AsyncSession, client: AsyncClient) -> None:
    """JU-07: falha na API Central → registro de erro → reprocessarEnvio limpa → retry ok.

    Verifica: após reprocessarEnvio, registro de falha removido e sincronização bem-sucedida.
    """
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="ju07@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _base(db, admin, cod_ua=307001)

    p = await _participante(db, admin, ue, ua, ui, matricula="3070010")
    await db.commit()

    # 1ª tentativa: API retorna erro
    mock_fail = _mock_api_client()
    mock_fail.send_participante = AsyncMock(side_effect=Exception("503 Service Unavailable"))
    await sincronizar_tudo(db, mock_fail)

    # Verificar que registro de falha foi criado
    fail_result = await db.execute(
        select(RegistroEnvioAPI).where(
            RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync.PARTICIPANTE,
            RegistroEnvioAPI.entidade_id == p.id,
            RegistroEnvioAPI.sucesso == False,  # noqa: E712
        )
    )
    reg = fail_result.scalar_one()
    assert reg.sucesso is False
    assert "503" in reg.erro_mensagem

    # Reprocessar via GQL (limpa o registro de falha)
    r_reprocess = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              reprocessarEnvio(
                tipoEntidade: "participante"
                entidadeId: "{p.id}"
              )
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )
    assert r_reprocess.status_code == 200
    assert r_reprocess.json().get("errors") is None
    assert r_reprocess.json()["data"]["reprocessarEnvio"] is True

    # Verificar que registro de falha foi removido
    check_result = await db.execute(
        select(RegistroEnvioAPI).where(
            RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync.PARTICIPANTE,
            RegistroEnvioAPI.entidade_id == p.id,
            RegistroEnvioAPI.sucesso == False,  # noqa: E712
        )
    )
    assert check_result.scalar_one_or_none() is None

    # Retry com API funcionando — deve ter sucesso
    mock_ok = _mock_api_client()
    # Marcar participante sem api_sincronizado_em para novo envio
    p_refreshed = await db.get(type(p), p.id)
    p_refreshed.api_sincronizado_em = None
    await db.commit()

    result = await sincronizar_tudo(db, mock_ok)
    assert result["sucesso"] >= 1
    mock_ok.send_participante.assert_called_once()


# ---------------------------------------------------------------------------
# JU-08 — Delegação de competência (RF-037)
# ---------------------------------------------------------------------------


async def test_ju08_delegacao_aprovar_pe(db: AsyncSession, client: AsyncClient) -> None:
    """JU-08: admin delega APROVAR_PLANO_ENTREGAS para chefia via GQL →
    chefia (que normalmente não aprova PE) aprova via GQL → audit log
    contém duas operações (delegação + aprovação).
    """
    admin = await persist_user(db, email="ju08_a@test.gov.br", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="ju08_c@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _base(db, admin, cod_ua=308001)

    # PE a ser aprovado
    pe = await _pe_com_entrega(db, admin, ue, ua, ui, "JU08")

    # 1. admin delega APROVAR_PLANO_ENTREGAS para chefia via GQL
    set_auth_cookie(client, admin)
    r_deleg = await client.post(
        "/graphql",
        json={
            "query": """
            mutation($input: DelegarCompetenciaInput!) {
              delegarCompetencia(input: $input) { id ativo }
            }
            """,
            "variables": {
                "input": {
                    "delegatarioUserId": chefia.id,
                    "competencia": "APROVAR_PLANO_ENTREGAS",
                    "unidadeExecucaoId": str(ue.id),
                    "dataInicio": "2026-01-01",
                    "dataFim": "2026-12-31",
                    "motivo": "JU-08",
                }
            },
        },
        headers={"user-agent": "pytest"},
    )
    assert r_deleg.status_code == 200
    assert r_deleg.json().get("errors") is None, r_deleg.json().get("errors")
    deleg_id = r_deleg.json()["data"]["delegarCompetencia"]["id"]

    # 2. chefia (agora delegatária) aprova o PE via GQL
    set_auth_cookie(client, chefia)
    r_aprov = await client.post(
        "/graphql",
        json={
            "query": """
            mutation($input: AprovarPlanoEntregasInput!) {
              aprovarPlanoEntregas(input: $input) {
                id
                aprovadoPorUserId
                dataAprovacao
              }
            }
            """,
            "variables": {
                "input": {
                    "planoId": str(pe.id),
                    "aprovadorUserId": chefia.id,
                }
            },
        },
        headers={"user-agent": "pytest"},
    )
    assert r_aprov.status_code == 200
    assert r_aprov.json().get("errors") is None, r_aprov.json().get("errors")
    aprov = r_aprov.json()["data"]["aprovarPlanoEntregas"]
    assert aprov["aprovadoPorUserId"] == chefia.id
    assert aprov["dataAprovacao"] is not None

    # 3. audit log contém pelo menos um registro de delegação (criada pelo admin)
    #    e um registro da aprovação do PE (feita pela chefia)
    audit_count_admin = await db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.user_id == admin.id)
    )
    audit_count_chefia = await db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.user_id == chefia.id)
    )
    assert audit_count_admin.scalar_one() >= 1  # delegação
    assert audit_count_chefia.scalar_one() >= 1  # aprovação do PE
