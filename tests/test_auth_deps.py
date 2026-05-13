"""Testes para src/auth/deps.py — criação/decodificação de JWT e get_optional_user."""
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import create_access_token, decode_access_token
from src.models.user import User, UserRole
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# TC-M06-004a  create_access_token — payload correto
# ---------------------------------------------------------------------------

def test_create_access_token_payload():
    user = User(id=42, email="srv@test.gov.br", name="Srv", role=UserRole.SERVIDOR)
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "srv@test.gov.br"
    assert payload["role"] == "servidor"


def test_create_access_token_all_roles():
    for role in UserRole:
        user = User(id=1, email="u@u.br", name="U", role=role)
        token = create_access_token(user)
        payload = decode_access_token(token)
        assert payload["role"] == role.value


# TC-M06-004b  token recém criado não está expirado
def test_create_access_token_not_expired():
    user = User(id=1, email="u@u.br", name="U", role=UserRole.SERVIDOR)
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload["exp"] > datetime.now(UTC).timestamp()


# ---------------------------------------------------------------------------
# TC-M06-005  tokens inválidos / expirados levantam erro
# ---------------------------------------------------------------------------

def test_decode_expired_token_raises():
    from src.config import get_settings

    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "email": "u@u.br",
        "role": "servidor",
        "iat": now - timedelta(hours=10),
        "exp": now - timedelta(hours=1),
    }
    token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_garbage_token_raises():
    with pytest.raises(pyjwt.exceptions.DecodeError):
        decode_access_token("not.a.jwt")


def test_decode_wrong_signature_raises():
    user = User(id=1, email="u@u.br", name="U", role=UserRole.SERVIDOR)
    token = create_access_token(user)
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + "." + "invalidsignature"
    with pytest.raises(pyjwt.exceptions.DecodeError):
        decode_access_token(tampered)


# ---------------------------------------------------------------------------
# get_optional_user (via /auth/me que usa a dependência)
# ---------------------------------------------------------------------------

# TC-M06-004c  sem cookie → 401
async def test_auth_me_no_cookie(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 401


# TC-M06-004d  cookie com token inválido → 401
async def test_auth_me_invalid_cookie(client: AsyncClient) -> None:
    client.cookies.set("access_token", "lixo.nao.eh.jwt")
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 401


# TC-M06-004e  usuário inativo → 401 (is_active=False filtrado na query)
async def test_auth_me_inactive_user(db: AsyncSession, client: AsyncClient) -> None:
    user = await persist_user(db, email="inativo@test.gov.br", is_active=False)
    set_auth_cookie(client, user)
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 401


# TC-M06-006  token válido para usuário ativo → 200 + dados corretos
async def test_auth_me_valid_user(db: AsyncSession, client: AsyncClient) -> None:
    user = await persist_user(
        db, email="ativo@test.gov.br", role=UserRole.GESTOR_UNIDADE
    )
    set_auth_cookie(client, user)
    response = await client.get("/auth/me", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "ativo@test.gov.br"
    assert data["role"] == UserRole.GESTOR_UNIDADE.value
