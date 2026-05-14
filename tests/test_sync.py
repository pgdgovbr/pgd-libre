"""Sprint 2.2 — TDD: serviço de sync e endpoint interno.

Ordem TDD:
1. Estes testes foram escritos ANTES da implementação (falham inicialmente).
2. A implementação deve fazer todos passarem sem modificar os testes.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.participante import (
    TCR,
    Participante,
    RegimeExecucao,
    StatusTCR,
    TipoVinculo,
)
from src.models.plano import (
    STATUS_PE_EM_EXECUCAO,
    STATUS_PT_APROVADO,
    Contribuicao,
    Entrega,
    PlanoEntregas,
    PlanoTrabalho,
    TipoMeta,
)
from src.models.user import UserRole
from src.services.institucional import (
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)

from .conftest import persist_user

# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------


async def _make_ue(db, admin):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Sync",
        sigla="UAS",
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
        cod_unidade_instituidora=100,
        nome="UI Sync",
        sigla="UIS",
        ato_instituicao_ref="R2",
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
        nome="UE Sync",
        sigla="UES",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ue


async def _make_participante(db, ue, *, matricula: str = "1234567") -> Participante:
    p = Participante(
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_lotacao=99,
        matricula_siape=matricula,
        cod_unidade_instituidora=100,
        cpf="64635210600",
        nome="Sync Test",
        email=f"{matricula}@sync.gov.br",
        situacao=1,
        modalidade_execucao=3,
        data_assinatura_tcr=date(2024, 6, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _make_tcr_ativo(db, participante: Participante) -> TCR:
    tcr = TCR(
        participante_id=participante.id,
        modalidade_execucao=3,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="Responsável por entregas",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        status=StatusTCR.ATIVO,
    )
    db.add(tcr)
    await db.commit()
    await db.refresh(tcr)
    return tcr


async def _make_pe(db, ue, *, id_pe: str = "PE-SYNC-001") -> PlanoEntregas:
    pe = PlanoEntregas(
        id_plano_entregas=id_pe,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_instituidora=100,
        cod_unidade_executora=200,
        unidade_execucao_id=ue.id,
        status=STATUS_PE_EM_EXECUCAO,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
    )
    db.add(pe)
    await db.flush()
    entrega = Entrega(
        id_entrega="E-001",
        plano_entregas_id=pe.id,
        nome_entrega="Entrega Sync",
        meta_entrega=5,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2024, 6, 1),
        nome_unidade_demandante="UA",
        nome_unidade_destinataria="UI",
        entrega_cancelada=False,
    )
    db.add(entrega)
    await db.commit()
    await db.refresh(pe)
    return pe


async def _make_pt(db, ue, participante: Participante, tcr: TCR) -> PlanoTrabalho:
    pt = PlanoTrabalho(
        id_plano_trabalho="PT-SYNC-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_executora=200,
        cod_unidade_lotacao_participante=99,
        participante_id=participante.id,
        cpf_participante="64635210600",
        matricula_siape=participante.matricula_siape,
        tcr_id=tcr.id,
        status=STATUS_PT_APROVADO,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
        carga_horaria_disponivel=160,
        criterios_avaliacao="Qualidade e prazo",
    )
    db.add(pt)
    await db.flush()
    contrib = Contribuicao(
        id_contribuicao="C-001",
        plano_trabalho_id=pt.id,
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="Contribuição geral",
    )
    db.add(contrib)
    await db.commit()
    await db.refresh(pt)
    return pt


def _mock_client():
    m = MagicMock()
    m.send_participante = AsyncMock(return_value={"ok": True})
    m.send_plano_entregas = AsyncMock(return_value={"ok": True})
    m.send_plano_trabalho = AsyncMock(return_value={"ok": True})
    return m


# ---------------------------------------------------------------------------
# Testes — lógica de sincronização
# ---------------------------------------------------------------------------


async def test_sem_dados_retorna_zero_sem_chamadas(db: AsyncSession):
    """DB vazio: nenhuma chamada ao cliente, resultado limpo."""
    from src.integration.sync import sincronizar_tudo

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    assert result == {"sucesso": 0, "erros": []}
    mock.send_participante.assert_not_called()
    mock.send_plano_entregas.assert_not_called()
    mock.send_plano_trabalho.assert_not_called()


async def test_participante_nao_sincronizado_e_enviado(db: AsyncSession):
    """Participante com api_sincronizado_em=None deve ser enviado."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync1.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    p = await _make_participante(db, ue)

    assert p.api_sincronizado_em is None

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    assert result["sucesso"] == 1
    assert result["erros"] == []
    mock.send_participante.assert_called_once()
    call = mock.send_participante.call_args
    assert call.kwargs["matricula_siape"] == "1234567"
    assert call.kwargs["cod_unidade_lotacao"] == 99

    await db.refresh(p)
    assert p.api_sincronizado_em is not None


async def test_participante_ja_sincronizado_nao_reenviado(db: AsyncSession):
    """Participante com api_sincronizado_em preenchido deve ser ignorado."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync2.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    p = await _make_participante(db, ue)
    p.api_sincronizado_em = datetime.now(UTC)
    await db.commit()

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    assert result == {"sucesso": 0, "erros": []}
    mock.send_participante.assert_not_called()


async def test_pe_nao_sincronizado_e_enviado(db: AsyncSession):
    """PlanoEntregas com api_sincronizado_em=None deve ser enviado com entregas."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync3.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    pe = await _make_pe(db, ue)

    assert pe.api_sincronizado_em is None

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    assert result["sucesso"] == 1
    assert result["erros"] == []
    mock.send_plano_entregas.assert_called_once()
    call = mock.send_plano_entregas.call_args
    assert call.kwargs["id_plano_entregas"] == "PE-SYNC-001"
    payload = call.kwargs["payload"]
    assert len(payload["entregas"]) == 1

    await db.refresh(pe)
    assert pe.api_sincronizado_em is not None


async def test_pt_nao_sincronizado_e_enviado(db: AsyncSession):
    """PlanoTrabalho com api_sincronizado_em=None deve ser enviado com contribuições."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync4.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    p = await _make_participante(db, ue)
    tcr = await _make_tcr_ativo(db, p)
    pt = await _make_pt(db, ue, p, tcr)

    assert pt.api_sincronizado_em is None

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    # pt + p ambos pendentes
    assert result["sucesso"] == 2
    assert result["erros"] == []
    mock.send_plano_trabalho.assert_called_once()
    call = mock.send_plano_trabalho.call_args
    assert call.kwargs["id_plano_trabalho"] == "PT-SYNC-001"
    payload = call.kwargs["payload"]
    assert len(payload["contribuicoes"]) == 1

    await db.refresh(pt)
    assert pt.api_sincronizado_em is not None


async def test_multiplos_pendentes_todos_sincronizados(db: AsyncSession):
    """Vários registos pendentes: todos são sincronizados num único ciclo."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync5.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    await _make_participante(db, ue, matricula="1234567")
    await _make_pe(db, ue, id_pe="PE-A")
    await _make_pe(db, ue, id_pe="PE-B")

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    # 1 participante + 2 PEs = 3 sucesso
    assert result["sucesso"] == 3
    assert mock.send_participante.call_count == 1
    assert mock.send_plano_entregas.call_count == 2


async def test_erro_cliente_registado_sem_abortar(db: AsyncSession):
    """Falha num envio regista o erro mas continua com os demais."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync6.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    await _make_participante(db, ue)
    await _make_pe(db, ue)

    mock = _mock_client()
    mock.send_participante = AsyncMock(side_effect=Exception("timeout de rede"))

    result = await sincronizar_tudo(db, mock)

    # PE sucede, participante falha
    assert result["sucesso"] == 1
    assert len(result["erros"]) == 1
    erro = result["erros"][0]
    assert erro["tipo"] == "participante"
    assert "timeout de rede" in erro["erro"]


async def test_erro_nao_impede_api_sincronizado_em_dos_outros(db: AsyncSession):
    """Registos que sincronizam com sucesso têm api_sincronizado_em preenchido
    mesmo que outros falhem no mesmo ciclo."""
    from src.integration.sync import sincronizar_tudo

    admin = await persist_user(db, email="admin@sync7.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)
    p = await _make_participante(db, ue)
    pe = await _make_pe(db, ue)

    mock = _mock_client()
    mock.send_participante = AsyncMock(side_effect=Exception("falhou"))

    await sincronizar_tudo(db, mock)

    await db.refresh(p)
    await db.refresh(pe)
    assert p.api_sincronizado_em is None  # falhou — não deve ser marcado
    assert pe.api_sincronizado_em is not None  # sucesso — deve estar marcado


# ---------------------------------------------------------------------------
# Testes — endpoint /internal/sync
# ---------------------------------------------------------------------------


async def test_endpoint_sem_secret_retorna_403(client: AsyncClient):
    resp = await client.post("/internal/sync")
    assert resp.status_code == 403


async def test_endpoint_com_secret_errado_retorna_403(client: AsyncClient):
    resp = await client.post(
        "/internal/sync",
        headers={"X-Sync-Secret": "segredo-errado"},
    )
    assert resp.status_code == 403


async def test_endpoint_com_secret_correto_sem_api_pgd_retorna_skipped(
    client: AsyncClient,
):
    """Quando API_PGD_URL não está configurada, retorna status=skipped (não erro)."""
    resp = await client.post(
        "/internal/sync",
        headers={"X-Sync-Secret": "dev-sync-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


async def test_endpoint_com_secret_correto_e_api_pgd_executa_sync(
    client: AsyncClient,
    db: AsyncSession,
):
    """Com API_PGD_URL configurada, o sync é executado e retorna relatório."""
    from unittest.mock import AsyncMock as AM
    from unittest.mock import patch

    fake_result = {"sucesso": 2, "erros": []}

    with (
        patch("src.api.sync.get_settings") as mock_settings,
        patch("src.api.sync.sincronizar_tudo", new=AM(return_value=fake_result)),
        patch("src.api.sync.ApiPgdClient") as mock_cls,
    ):
        settings = MagicMock()
        settings.SYNC_SECRET = "dev-sync-secret"
        settings.API_PGD_URL = "http://fake-api:5057"
        settings.API_PGD_USERNAME = "user"
        settings.API_PGD_PASSWORD = "pass"
        mock_settings.return_value = settings

        mock_instance = MagicMock()
        mock_instance.__aenter__ = AM(return_value=mock_instance)
        mock_instance.__aexit__ = AM(return_value=None)
        mock_cls.return_value = mock_instance

        resp = await client.post(
            "/internal/sync",
            headers={"X-Sync-Secret": "dev-sync-secret"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["sucesso"] == 2
    assert data["erros"] == []
