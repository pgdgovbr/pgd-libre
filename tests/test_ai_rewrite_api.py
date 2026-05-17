"""TDD — Endpoint REST POST /api/ai/rewrite-registro.

Cobre:
- 401 sem auth
- 403 para non-servidor (chefe, gestor, admin)
- 422 texto < 80 chars
- 422 template_id inválido
- 200 happy path (mock Bedrock)
- 429 rate limit excedido (popular 10 events, 11ª retorna 429)
- 503 quando service levanta RewriteError
- /applied marca evento como aplicado (404 se não pertencer ao user)
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.conftest import persist_user, set_auth_cookie

LONG_TEXT = "Realizei diversas atividades no mês. " * 5  # > 80 chars


def _mock_bedrock_response(
    text: str = "ENTREGA 1\n  Resultado: ok", tokens_in: int = 100, tokens_out: int = 200
):
    body = json.dumps(
        {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
        }
    ).encode("utf-8")
    client = MagicMock()
    client.invoke_model.return_value = {"body": io.BytesIO(body)}
    return client


@pytest.fixture
async def servidor(db: AsyncSession):
    return await persist_user(db, email="srv@t.com", role=UserRole.SERVIDOR)


@pytest.fixture
async def chefe(db: AsyncSession):
    return await persist_user(db, email="chefe@t.com", role=UserRole.CHEFE_IMEDIATO)


# ---------------------------------------------------------------------------
# Auth + RBAC
# ---------------------------------------------------------------------------


async def test_endpoint_exige_autenticacao(client: AsyncClient):
    resp = await client.post(
        "/api/ai/rewrite-registro",
        json={"texto_atual": LONG_TEXT, "template_id": "entrega", "instrucao_adicional": ""},
    )
    assert resp.status_code == 401


async def test_endpoint_rejeita_chefia(client: AsyncClient, db, chefe):
    set_auth_cookie(client, chefe)
    resp = await client.post(
        "/api/ai/rewrite-registro",
        json={"texto_atual": LONG_TEXT, "template_id": "entrega", "instrucao_adicional": ""},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Validação de payload
# ---------------------------------------------------------------------------


async def test_endpoint_texto_curto_retorna_422(client: AsyncClient, db, servidor):
    set_auth_cookie(client, servidor)
    resp = await client.post(
        "/api/ai/rewrite-registro",
        json={"texto_atual": "curto", "template_id": "entrega", "instrucao_adicional": ""},
    )
    assert resp.status_code == 422


async def test_endpoint_template_invalido_retorna_422(client: AsyncClient, db, servidor):
    set_auth_cookie(client, servidor)
    resp = await client.post(
        "/api/ai/rewrite-registro",
        json={"texto_atual": LONG_TEXT, "template_id": "alien", "instrucao_adicional": ""},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_endpoint_sucesso_retorna_texto_reescrito(client: AsyncClient, db, servidor):
    set_auth_cookie(client, servidor)
    mock_client = _mock_bedrock_response("ENTREGA 1 · Migração\n  Resultado: ok", 120, 250)
    with patch("src.services.ai_rewrite._bedrock_client", return_value=mock_client):
        resp = await client.post(
            "/api/ai/rewrite-registro",
            json={
                "texto_atual": LONG_TEXT,
                "template_id": "entrega",
                "instrucao_adicional": "",
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "event_id" in data
    assert "ENTREGA 1" in data["rewritten_text"]
    assert data["tokens_in"] == 120
    assert data["tokens_out"] == 250
    assert "latency_ms" in data


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


async def test_endpoint_rate_limit_excedido_retorna_429(
    client: AsyncClient, db: AsyncSession, servidor
):
    """Pré-popula 10 eventos; 11ª chamada deve falhar com 429 e Retry-After."""
    from src.services.ai_rewrite import registrar_evento_geracao

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
    set_auth_cookie(client, servidor)
    resp = await client.post(
        "/api/ai/rewrite-registro",
        json={"texto_atual": LONG_TEXT, "template_id": "entrega", "instrucao_adicional": ""},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


# ---------------------------------------------------------------------------
# Erros do LLM
# ---------------------------------------------------------------------------


async def test_endpoint_503_quando_service_falha(client: AsyncClient, db, servidor):
    set_auth_cookie(client, servidor)
    from src.services.ai_rewrite import RewriteError

    with patch(
        "src.api.ai_rewrite.reescrever_registro",
        side_effect=RewriteError("Bedrock down"),
    ):
        resp = await client.post(
            "/api/ai/rewrite-registro",
            json={
                "texto_atual": LONG_TEXT,
                "template_id": "entrega",
                "instrucao_adicional": "",
            },
        )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# /applied
# ---------------------------------------------------------------------------


async def test_endpoint_applied_marca_evento_como_aplicado(
    client: AsyncClient, db: AsyncSession, servidor
):
    from src.services.ai_rewrite import registrar_evento_geracao

    ev = await registrar_evento_geracao(
        db,
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=100,
        chars_out=300,
        tokens_in=120,
        tokens_out=350,
        latency_ms=2400,
        model="haiku",
    )
    set_auth_cookie(client, servidor)
    resp = await client.post(f"/api/ai/rewrite-registro/{ev.id}/applied")
    assert resp.status_code == 200, resp.text
    await db.refresh(ev)
    assert ev.applied is True


async def test_endpoint_applied_outro_user_retorna_404(
    client: AsyncClient, db: AsyncSession, servidor
):
    from src.services.ai_rewrite import registrar_evento_geracao

    intruso = await persist_user(db, email="x@t.com", role=UserRole.SERVIDOR)
    ev = await registrar_evento_geracao(
        db,
        user_id=intruso.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=100,
        chars_out=300,
        tokens_in=120,
        tokens_out=350,
        latency_ms=2400,
        model="haiku",
    )
    set_auth_cookie(client, servidor)
    resp = await client.post(f"/api/ai/rewrite-registro/{ev.id}/applied")
    assert resp.status_code == 404
