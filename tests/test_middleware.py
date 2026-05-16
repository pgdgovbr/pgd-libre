"""Testes para middlewares registrados em src/main.py.

Middleware registrados:
1. ProxyHeadersMiddleware (Cloud Run TLS termination)
2. SessionMiddleware (OAuth CSRF state)
3. CORSMiddleware (allow_origins=[FRONTEND_URL], allow_credentials=True)
4. require_user_agent — rejeita requests sem User-Agent com 400
5. csp_for_docs — adiciona Content-Security-Policy em /docs e /redoc

Referência: src/config.py — FRONTEND_URL default = "http://localhost:5173"
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# TC — Health check básico
# ---------------------------------------------------------------------------


async def test_health_ok(db: AsyncSession, client: AsyncClient) -> None:
    """GET /health com User-Agent válido retorna 200 e status='ok'."""
    resp = await client.get("/health", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


# ---------------------------------------------------------------------------
# TC — require_user_agent middleware
# ---------------------------------------------------------------------------


async def test_require_user_agent_ausente_retorna_400(client: AsyncClient) -> None:
    """Requisição sem User-Agent retorna 400 com detalhe."""
    # O httpx envia User-Agent por padrão; precisamos sobrescrever com string vazia.
    resp = await client.get("/health", headers={"user-agent": ""})
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    assert "user-agent" in body["detail"].lower() or "User-Agent" in body["detail"]


async def test_require_user_agent_ausente_em_graphql_retorna_400(client: AsyncClient) -> None:
    """POST /graphql sem User-Agent também retorna 400 (middleware é global)."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ health }"},
        headers={"user-agent": ""},
    )
    assert resp.status_code == 400


async def test_user_agent_presente_passa_middleware(
    db: AsyncSession, client: AsyncClient
) -> None:
    """User-Agent qualquer (mesmo não-browser) é aceito."""
    resp = await client.get("/health", headers={"user-agent": "meu-script/1.0"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC — CORS middleware
# ---------------------------------------------------------------------------


async def test_cors_options_graphql_com_origin_frontend(client: AsyncClient) -> None:
    """OPTIONS /graphql com Origin do frontend retorna header ACAO presente."""
    resp = await client.options(
        "/graphql",
        headers={
            "user-agent": "pytest",
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # Starlette CORSMiddleware responde 200 para preflight
    assert resp.status_code in (200, 204)
    # Header de CORS deve estar presente
    acao = resp.headers.get("access-control-allow-origin")
    assert acao is not None, (
        f"Access-Control-Allow-Origin ausente. Headers: {dict(resp.headers)}"
    )


async def test_cors_origin_desconhecida_nao_tem_acao(client: AsyncClient) -> None:
    """Preflight com Origin desconhecida não deve retornar ACAO permissivo.

    O CORSMiddleware do FastAPI está configurado com allow_origins=[FRONTEND_URL].
    Origins não listadas não recebem o header Access-Control-Allow-Origin.
    """
    resp = await client.options(
        "/graphql",
        headers={
            "user-agent": "pytest",
            "Origin": "https://evil-attacker.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = resp.headers.get("access-control-allow-origin")
    # Não deve refletir a origin desconhecida
    assert acao != "https://evil-attacker.example.com", (
        "CORS não deve permitir origin desconhecida"
    )


async def test_cors_get_health_com_origin_frontend(
    db: AsyncSession, client: AsyncClient
) -> None:
    """GET /health com Origin do frontend recebe header ACAO."""
    resp = await client.get(
        "/health",
        headers={
            "user-agent": "pytest",
            "Origin": "http://localhost:5173",
        },
    )
    assert resp.status_code == 200
    acao = resp.headers.get("access-control-allow-origin")
    assert acao is not None


# ---------------------------------------------------------------------------
# TC — Content-Security-Policy middleware (csp_for_docs)
# ---------------------------------------------------------------------------


async def test_csp_header_em_docs(db: AsyncSession, client: AsyncClient) -> None:
    """GET /docs retorna Content-Security-Policy com diretivas esperadas."""
    resp = await client.get("/docs", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is not None, "Content-Security-Policy ausente em /docs"
    assert "default-src 'self'" in csp
    assert "cdn.jsdelivr.net" in csp


async def test_csp_header_em_redoc(db: AsyncSession, client: AsyncClient) -> None:
    """GET /redoc retorna Content-Security-Policy."""
    resp = await client.get("/redoc", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is not None, "Content-Security-Policy ausente em /redoc"
    assert "default-src 'self'" in csp


async def test_csp_header_ausente_em_health(db: AsyncSession, client: AsyncClient) -> None:
    """GET /health NÃO recebe Content-Security-Policy (middleware é restrito a /docs e /redoc)."""
    resp = await client.get("/health", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is None, f"CSP inesperado em /health: {csp}"


async def test_csp_header_ausente_em_graphql(
    db: AsyncSession, client: AsyncClient
) -> None:
    """POST /graphql NÃO recebe Content-Security-Policy."""
    resp = await client.post(
        "/graphql",
        json={"query": "{ health }"},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is None, f"CSP inesperado em /graphql: {csp}"


# ---------------------------------------------------------------------------
# TC — Rota não existente
# ---------------------------------------------------------------------------


async def test_rota_inexistente_retorna_404_nao_500(client: AsyncClient) -> None:
    """Rota não registrada retorna 404, não 500."""
    resp = await client.get("/rota-que-nao-existe", headers={"user-agent": "pytest"})
    assert resp.status_code == 404
