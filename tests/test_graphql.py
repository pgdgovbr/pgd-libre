"""Testes para src/graphql/schema.py — queries GraphQL autenticadas."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import UserRole
from tests.conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# TC-M06-006  query { me } — autenticado retorna dados do usuário
# ---------------------------------------------------------------------------


async def test_graphql_me_authenticated_returns_user(db: AsyncSession, client: AsyncClient) -> None:
    user = await persist_user(db, email="me@test.gov.br", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, user)

    response = await client.post(
        "/graphql",
        json={"query": "{ me { id email name role } }"},
        headers={"user-agent": "pytest"},
    )
    assert response.status_code == 200
    data = response.json()["data"]["me"]
    assert data["email"] == "me@test.gov.br"
    assert data["role"] == UserRole.CHEFE_IMEDIATO.value
    assert data["name"] == "me"
    assert isinstance(data["id"], int)


async def test_graphql_me_returns_correct_role_for_admin(
    db: AsyncSession, client: AsyncClient
) -> None:
    user = await persist_user(db, email="adm@test.gov.br", role=UserRole.ADMIN)
    set_auth_cookie(client, user)

    response = await client.post(
        "/graphql",
        json={"query": "{ me { role } }"},
        headers={"user-agent": "pytest"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["me"]["role"] == "admin"
