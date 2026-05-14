"""Testes para src/auth/router.py — endpoints /auth/*."""

from unittest.mock import MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# TC-M06-001/002  GET /auth/providers
# ---------------------------------------------------------------------------


async def test_providers_empty_when_no_env_vars(client: AsyncClient) -> None:
    response = await client.get("/auth/providers", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    assert response.json() == []


async def test_providers_google_when_client_id_configured(client: AsyncClient) -> None:
    mock_settings = MagicMock()
    mock_settings.GOOGLE_CLIENT_ID = "fake-google-id"
    mock_settings.GOVBR_CLIENT_ID = ""
    with patch("src.auth.router.get_settings", return_value=mock_settings):
        response = await client.get("/auth/providers", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    assert response.json() == [{"id": "google", "name": "Google"}]


async def test_providers_govbr_when_client_id_configured(client: AsyncClient) -> None:
    mock_settings = MagicMock()
    mock_settings.GOOGLE_CLIENT_ID = ""
    mock_settings.GOVBR_CLIENT_ID = "fake-govbr-id"
    with patch("src.auth.router.get_settings", return_value=mock_settings):
        response = await client.get("/auth/providers", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    assert response.json() == [{"id": "govbr", "name": "Gov.Br"}]


async def test_providers_both_when_both_configured(client: AsyncClient) -> None:
    mock_settings = MagicMock()
    mock_settings.GOOGLE_CLIENT_ID = "fake-google-id"
    mock_settings.GOVBR_CLIENT_ID = "fake-govbr-id"
    with patch("src.auth.router.get_settings", return_value=mock_settings):
        response = await client.get("/auth/providers", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    providers = response.json()
    assert len(providers) == 2
    ids = [p["id"] for p in providers]
    assert "google" in ids
    assert "govbr" in ids


# ---------------------------------------------------------------------------
# TC-M06-003  GET /auth/login/{provider} — provider não configurado → 404
# ---------------------------------------------------------------------------


async def test_login_unknown_provider_returns_404(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/login/inexistente",
        headers={"user-agent": "pytest"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert "não configurado" in response.json()["detail"]


async def test_callback_unknown_provider_returns_404(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/callback/inexistente",
        headers={"user-agent": "pytest"},
        follow_redirects=False,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# TC-M06-006  GET /auth/me
# ---------------------------------------------------------------------------


async def test_auth_me_unauthenticated_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 401


async def test_auth_me_returns_user_data(db: AsyncSession, client: AsyncClient) -> None:
    user = await persist_user(db, email="admin@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, user)
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@test.gov.br"
    assert data["role"] == UserRole.ADMIN.value
    assert data["name"] == "admin"


# ---------------------------------------------------------------------------
# TC-M06-010  POST /auth/logout
# ---------------------------------------------------------------------------


async def test_logout_returns_ok(client: AsyncClient) -> None:
    response = await client.post("/auth/logout", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_logout_sends_delete_cookie_header(client: AsyncClient) -> None:
    response = await client.post("/auth/logout", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    # servidor deve enviar Set-Cookie com access_token e Max-Age=0 para deletar
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "access_token" in set_cookie
    assert "max-age=0" in set_cookie
