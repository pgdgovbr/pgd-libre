"""Fase 0 — Middleware CSP para /docs e /redoc.

Em produção `/docs` e `/redoc` já vêm desabilitados (src/main.py:21-22).
O middleware aplica `Content-Security-Policy` apenas em dev/staging onde
o Swagger UI carrega assets do CDN.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_csp_header_presente_em_docs(db: AsyncSession, client: AsyncClient):
    resp = await client.get("/docs", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "cdn.jsdelivr.net" in csp


async def test_csp_header_presente_em_redoc(db: AsyncSession, client: AsyncClient):
    resp = await client.get("/redoc", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp is not None
    assert "default-src 'self'" in csp


async def test_csp_header_ausente_em_health(db: AsyncSession, client: AsyncClient):
    """Middleware é escopo-restrito: outras rotas não recebem o header."""
    resp = await client.get("/health", headers={"user-agent": "pytest"})
    assert resp.status_code == 200
    assert resp.headers.get("content-security-policy") is None
