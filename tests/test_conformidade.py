"""Sprint 2.2 (conclusão) — RegistroEnvioAPI, retry com backoff, painel de conformidade.

TDD: testes escritos antes da implementação.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.participante import Participante, TipoVinculo
from src.models.plano import STATUS_PE_EM_EXECUCAO, PlanoEntregas
from src.models.user import UserRole
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Helpers (duplicados do test_sync.py para isolamento)
# ---------------------------------------------------------------------------


async def _ua_ue(db: AsyncSession):
    from src.models.institucional import (
        UnidadeAutorizadora,
        UnidadeExecucao,
        UnidadeInstituidora,
    )

    ua = UnidadeAutorizadora(
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=999,
        nome="UA Conf",
        sigla="UAC",
    )
    db.add(ua)
    await db.flush()
    ui = UnidadeInstituidora(
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=9990,
        nome="UI Conf",
        sigla="UIC",
        ato_instituicao_ref="PORT-C",
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
        cod_unidade_executora=99900,
        nome="UE Conf",
        sigla="UEC",
    )
    db.add(ue)
    await db.flush()
    return ue


async def _participante(db: AsyncSession, ue, matricula="9990001") -> Participante:
    p = Participante(
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=999,
        cod_unidade_lotacao=99900,
        matricula_siape=matricula,
        cod_unidade_instituidora=9990,
        cpf="52998224725",
        nome="Conf Test",
        email=f"{matricula}@test.gov.br",
        modalidade_execucao=3,
        data_assinatura_tcr=date(2024, 1, 15),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
    )
    db.add(p)
    await db.flush()
    return p


async def _plano_entregas(db: AsyncSession, ue, id_pe="PE-CONF-001") -> PlanoEntregas:
    pe = PlanoEntregas(
        id_plano_entregas=id_pe,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=999,
        cod_unidade_instituidora=9990,
        cod_unidade_executora=99900,
        unidade_execucao_id=ue.id,
        status=STATUS_PE_EM_EXECUCAO,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 12, 31),
    )
    db.add(pe)
    await db.flush()
    return pe


def _mock_client():
    m = MagicMock()
    m.send_participante = AsyncMock(return_value={"ok": True})
    m.send_plano_entregas = AsyncMock(return_value={"ok": True})
    m.send_plano_trabalho = AsyncMock(return_value={"ok": True})
    return m


# ---------------------------------------------------------------------------
# TC-S22-001  Sucesso cria RegistroEnvioAPI com sucesso=True
# ---------------------------------------------------------------------------


async def test_sync_sucesso_cria_registro(db: AsyncSession) -> None:
    from src.integration.sync import sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue)
    await db.commit()

    mock = _mock_client()
    await sincronizar_tudo(db, mock)

    result = await db.execute(
        select(RegistroEnvioAPI).where(
            RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync.PARTICIPANTE,
            RegistroEnvioAPI.entidade_id == p.id,
        )
    )
    reg = result.scalar_one()
    assert reg.sucesso is True
    assert reg.tentativa == 1
    assert reg.http_status is None
    assert reg.erro_mensagem is None


# ---------------------------------------------------------------------------
# TC-S22-002  Falha cria RegistroEnvioAPI com sucesso=False e mensagem
# ---------------------------------------------------------------------------


async def test_sync_falha_cria_registro_com_erro(db: AsyncSession) -> None:
    from src.integration.sync import sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue)
    await db.commit()

    mock = _mock_client()
    mock.send_participante = AsyncMock(side_effect=Exception("timeout"))
    await sincronizar_tudo(db, mock)

    result = await db.execute(
        select(RegistroEnvioAPI).where(
            RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync.PARTICIPANTE,
            RegistroEnvioAPI.entidade_id == p.id,
        )
    )
    reg = result.scalar_one()
    assert reg.sucesso is False
    assert reg.tentativa == 1
    assert "timeout" in reg.erro_mensagem


# ---------------------------------------------------------------------------
# TC-S22-003  Entidade com falha recente não é retentada (backoff)
# ---------------------------------------------------------------------------


async def test_sync_backoff_nao_retenta_falha_recente(db: AsyncSession) -> None:
    from src.integration.sync import sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue, matricula="9990002")
    await db.commit()

    # Simula falha recente (agora mesmo) — tentativa 1
    reg = RegistroEnvioAPI(
        tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
        entidade_id=p.id,
        tentativa=1,
        sucesso=False,
        erro_mensagem="erro anterior",
        created_at=datetime.now(UTC),  # recente
    )
    db.add(reg)
    await db.commit()

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    # Não deve ter tentado reenviar (backoff não expirou)
    mock.send_participante.assert_not_called()
    assert result["sucesso"] == 0


# ---------------------------------------------------------------------------
# TC-S22-004  Entidade com falha antiga É retentada
# ---------------------------------------------------------------------------


async def test_sync_retenta_apos_backoff_expirado(db: AsyncSession) -> None:
    from src.integration.sync import RETRY_DELAYS, sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue, matricula="9990003")
    await db.commit()

    # Simula falha antiga (delay[0] + 10s atrás) — tentativa 1
    old_time = datetime.now(UTC) - timedelta(seconds=RETRY_DELAYS[0] + 10)
    reg = RegistroEnvioAPI(
        tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
        entidade_id=p.id,
        tentativa=1,
        sucesso=False,
        erro_mensagem="erro antigo",
        created_at=old_time,
    )
    db.add(reg)
    await db.commit()

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    mock.send_participante.assert_called_once()
    assert result["sucesso"] == 1


# ---------------------------------------------------------------------------
# TC-S22-005  Entidade que esgotou tentativas é ignorada
# ---------------------------------------------------------------------------


async def test_sync_ignora_entidade_que_esgotou_tentativas(db: AsyncSession) -> None:
    from src.integration.sync import MAX_TENTATIVAS, sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue, matricula="9990004")
    await db.commit()

    # Simula última falha com tentativa = MAX_TENTATIVAS (esgotado), mas já antiga
    old_time = datetime.now(UTC) - timedelta(hours=2)
    reg = RegistroEnvioAPI(
        tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
        entidade_id=p.id,
        tentativa=MAX_TENTATIVAS,
        sucesso=False,
        erro_mensagem="esgotado",
        created_at=old_time,
    )
    db.add(reg)
    await db.commit()

    mock = _mock_client()
    result = await sincronizar_tudo(db, mock)

    # Deve ser ignorado mesmo com backoff expirado
    mock.send_participante.assert_not_called()
    assert result["sucesso"] == 0


# ---------------------------------------------------------------------------
# TC-S22-006  Retry incrementa tentativa corretamente
# ---------------------------------------------------------------------------


async def test_sync_incrementa_tentativa_em_nova_falha(db: AsyncSession) -> None:
    from src.integration.sync import RETRY_DELAYS, sincronizar_tudo
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue, matricula="9990005")
    await db.commit()

    # Primeira falha (antiga)
    old_time = datetime.now(UTC) - timedelta(seconds=RETRY_DELAYS[0] + 10)
    reg = RegistroEnvioAPI(
        tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
        entidade_id=p.id,
        tentativa=1,
        sucesso=False,
        erro_mensagem="primeiro erro",
        created_at=old_time,
    )
    db.add(reg)
    await db.commit()

    mock = _mock_client()
    mock.send_participante = AsyncMock(side_effect=Exception("segundo erro"))
    await sincronizar_tudo(db, mock)

    result = await db.execute(
        select(RegistroEnvioAPI)
        .where(
            RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync.PARTICIPANTE,
            RegistroEnvioAPI.entidade_id == p.id,
        )
        .order_by(RegistroEnvioAPI.created_at.desc())
        .limit(1)
    )
    ultimo = result.scalar_one()
    assert ultimo.tentativa == 2
    assert ultimo.sucesso is False
    assert "segundo erro" in ultimo.erro_mensagem


# ---------------------------------------------------------------------------
# TC-S22-007  painel_conformidade retorna contagens corretas
# ---------------------------------------------------------------------------


async def test_painel_conformidade_contagens(db: AsyncSession, client: AsyncClient) -> None:
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    # 1 participante já sincronizado
    p_sync = await _participante(db, ue, matricula="9991001")
    p_sync.api_sincronizado_em = datetime.now(UTC)
    # 1 participante pendente sem tentativa
    await _participante(db, ue, matricula="9991002")
    # 1 participante com erro (elegível para retry)
    p_err = await _participante(db, ue, matricula="9991003")
    await db.flush()

    from src.integration.sync import RETRY_DELAYS

    reg = RegistroEnvioAPI(
        tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
        entidade_id=p_err.id,
        tentativa=1,
        sucesso=False,
        erro_mensagem="falhou",
        created_at=datetime.now(UTC) - timedelta(seconds=RETRY_DELAYS[0] + 60),
    )
    db.add(reg)
    await db.commit()

    admin = await persist_user(db, email="adm.conf@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": """
            {
              painelConformidade {
                participantes {
                  total
                  enviados
                  pendentes
                  comErro
                }
              }
            }
            """
        },
        headers={"user-agent": "pytest"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]["painelConformidade"]["participantes"]
    assert data["total"] == 3
    assert data["enviados"] == 1
    assert data["pendentes"] == 2  # p_pend + p_err (ambos não enviados)
    assert data["comErro"] == 1  # apenas p_err tem registro de falha


# ---------------------------------------------------------------------------
# TC-S22-008  reprocessar_envio limpa histórico de falhas
# ---------------------------------------------------------------------------


async def test_reprocessar_envio_limpa_falhas(db: AsyncSession, client: AsyncClient) -> None:
    from src.integration.sync import MAX_TENTATIVAS
    from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

    ue = await _ua_ue(db)
    p = await _participante(db, ue, matricula="9992001")
    await db.flush()

    # Esgotou tentativas
    for i in range(1, MAX_TENTATIVAS + 1):
        db.add(
            RegistroEnvioAPI(
                tipo_entidade=TipoEntidadeSync.PARTICIPANTE,
                entidade_id=p.id,
                tentativa=i,
                sucesso=False,
                erro_mensagem="falhou",
                created_at=datetime.now(UTC) - timedelta(hours=MAX_TENTATIVAS - i + 1),
            )
        )
    await db.commit()

    admin = await persist_user(db, email="adm.repr@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    resp = await client.post(
        "/graphql",
        json={
            "query": f"""
            mutation {{
              reprocessarEnvio(
                tipoEntidade: "participante",
                entidadeId: "{p.id}"
              )
            }}
            """
        },
        headers={"user-agent": "pytest"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["reprocessarEnvio"] is True

    # Registros de falha devem ter sido removidos
    result = await db.execute(
        select(RegistroEnvioAPI).where(
            RegistroEnvioAPI.entidade_id == p.id,
            RegistroEnvioAPI.sucesso == False,  # noqa: E712
        )
    )
    assert result.scalars().all() == []
