"""TDD — Service ai_rewrite: prompts, retry, parse, rate limit.

Bedrock client mockado via MagicMock. Sem chamada real à AWS.
"""

import io
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from src.services.ai_rewrite import (
    AI_SYSTEM_PROMPT,
    AI_USER_PROMPT_DEFAULT,
    TEMPLATES,
    RewriteError,
    TemplateInvalidoError,
    _build_messages,
    contar_eventos_ultima_hora,
    marcar_evento_aplicado,
    reescrever_registro,
    registrar_evento_geracao,
    verificar_rate_limit,
)
from tests.conftest import persist_user

# ---------------------------------------------------------------------------
# Constantes / templates
# ---------------------------------------------------------------------------


def test_templates_tem_os_quatro_ids_esperados():
    assert set(TEMPLATES.keys()) == {"entrega", "cronologico", "contribuicao", "star"}


def test_cada_template_tem_nome_e_desc():
    for tid, t in TEMPLATES.items():
        assert "nome" in t and t["nome"], f"template {tid} sem nome"
        assert "desc" in t and t["desc"], f"template {tid} sem desc"


def test_system_prompt_contem_regras_invioaveis():
    # Verifica que regras críticas continuam no prompt (não regridem)
    assert "NÃO invente fatos" in AI_SYSTEM_PROMPT
    assert "[precisa de detalhe]" in AI_SYSTEM_PROMPT
    assert "1ª pessoa do singular" in AI_SYSTEM_PROMPT


def test_user_prompt_default_existe_e_e_nao_vazio():
    assert AI_USER_PROMPT_DEFAULT.strip()


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------


def test_build_messages_inclui_texto_template_e_instrucao():
    msgs = _build_messages(
        texto_atual="Trabalhei muito no projeto X.",
        template_id="entrega",
        instrucao_adicional="foque em métricas",
    )
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert "Trabalhei muito no projeto X." in content
    assert TEMPLATES["entrega"]["nome"] in content
    assert "foque em métricas" in content


def test_build_messages_template_invalido_lanca_erro():
    with pytest.raises(TemplateInvalidoError):
        _build_messages(
            texto_atual="x",
            template_id="inexistente",  # type: ignore[arg-type]
            instrucao_adicional="",
        )


# ---------------------------------------------------------------------------
# reescrever_registro — happy path
# ---------------------------------------------------------------------------


def _mock_bedrock(text: str, tokens_in: int = 100, tokens_out: int = 200):
    """Cria um mock client.invoke_model com response Anthropic Bedrock."""
    body = json.dumps(
        {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
        }
    ).encode("utf-8")
    client = MagicMock()
    client.invoke_model.return_value = {"body": io.BytesIO(body)}
    return client


def test_reescrever_registro_sucesso_retorna_texto_e_tokens():
    client = _mock_bedrock("ENTREGA 1 · Migração\n  Resultado: ok", 120, 250)
    text, t_in, t_out, latency = reescrever_registro(
        texto_atual="Migrei o banco. Funcionou.",
        template_id="entrega",
        instrucao_adicional=AI_USER_PROMPT_DEFAULT,
        client=client,
    )
    assert "ENTREGA 1" in text
    assert t_in == 120
    assert t_out == 250
    assert latency >= 0
    # Confirma que o body do request tem system + messages + temperature 0.3
    call = client.invoke_model.call_args
    body = json.loads(call.kwargs["body"])
    assert body["temperature"] == 0.3
    assert body["system"] == AI_SYSTEM_PROMPT
    assert body["messages"][0]["role"] == "user"
    assert "Migrei o banco. Funcionou." in body["messages"][0]["content"]


def test_reescrever_registro_template_invalido_lanca_erro():
    client = _mock_bedrock("...")
    with pytest.raises(TemplateInvalidoError):
        reescrever_registro(
            texto_atual="x",
            template_id="qualquercoisa",  # type: ignore[arg-type]
            instrucao_adicional="",
            client=client,
        )


# ---------------------------------------------------------------------------
# Retry / ThrottlingException / falha persistente
# ---------------------------------------------------------------------------


def _throttling_err():
    return ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "slow"}},
        operation_name="InvokeModel",
    )


def test_retry_em_throttling_recupera_em_2a_tentativa(monkeypatch):
    monkeypatch.setattr("src.services.ai_rewrite.time.sleep", lambda *_: None)
    client = MagicMock()
    body_ok = json.dumps(
        {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    ).encode("utf-8")
    client.invoke_model.side_effect = [
        _throttling_err(),
        {"body": io.BytesIO(body_ok)},
    ]
    text, *_ = reescrever_registro(
        texto_atual="x" * 100,
        template_id="entrega",
        instrucao_adicional="",
        client=client,
    )
    assert text == "ok"
    assert client.invoke_model.call_count == 2


def test_falha_apos_max_retries_lanca_rewrite_error(monkeypatch):
    monkeypatch.setattr("src.services.ai_rewrite.time.sleep", lambda *_: None)
    client = MagicMock()
    client.invoke_model.side_effect = _throttling_err()
    with pytest.raises(RewriteError):
        reescrever_registro(
            texto_atual="x" * 100,
            template_id="entrega",
            instrucao_adicional="",
            client=client,
        )
    # Default = 3 tentativas
    assert client.invoke_model.call_count == 3


# ---------------------------------------------------------------------------
# Persistência: registrar_evento + applied + rate limit
# ---------------------------------------------------------------------------


@pytest.fixture
async def servidor(db: AsyncSession):
    return await persist_user(db, email="s@t.com", role=UserRole.SERVIDOR)


async def test_registrar_evento_geracao_persiste(db: AsyncSession, servidor):
    ev = await registrar_evento_geracao(
        db,
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=100,
        chars_out=300,
        tokens_in=120,
        tokens_out=250,
        latency_ms=2400,
        model="haiku",
    )
    assert ev.id is not None
    assert ev.applied is False
    assert await contar_eventos_ultima_hora(db, servidor.id) == 1


async def test_marcar_evento_aplicado_alterna_flag(db: AsyncSession, servidor):
    ev = await registrar_evento_geracao(
        db,
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=80,
        chars_out=200,
        tokens_in=100,
        tokens_out=240,
        latency_ms=1800,
        model="haiku",
    )
    updated = await marcar_evento_aplicado(db, event_id=ev.id, user_id=servidor.id)
    assert updated is not None
    assert updated.applied is True


async def test_marcar_evento_aplicado_outro_user_retorna_none(db: AsyncSession, servidor):
    intruso = await persist_user(db, email="x@t.com", role=UserRole.SERVIDOR)
    ev = await registrar_evento_geracao(
        db,
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=80,
        chars_out=200,
        tokens_in=100,
        tokens_out=240,
        latency_ms=1800,
        model="haiku",
    )
    result = await marcar_evento_aplicado(db, event_id=ev.id, user_id=intruso.id)
    assert result is None


async def test_rate_limit_permite_abaixo_do_teto(db: AsyncSession, servidor):
    allowed, retry = await verificar_rate_limit(db, servidor.id, limit=10)
    assert allowed is True
    assert retry == 0


async def test_rate_limit_bloqueia_quando_atinge_teto(db: AsyncSession, servidor):
    for _ in range(10):
        await registrar_evento_geracao(
            db,
            user_id=servidor.id,
            registro_id=None,
            template_id="entrega",
            instrucao_custom=False,
            chars_in=80,
            chars_out=200,
            tokens_in=100,
            tokens_out=240,
            latency_ms=1800,
            model="haiku",
        )
    allowed, retry = await verificar_rate_limit(db, servidor.id, limit=10)
    assert allowed is False
    assert retry > 0  # algum tempo até primeiro evento sair da janela
