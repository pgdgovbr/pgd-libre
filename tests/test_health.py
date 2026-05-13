import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


@pytest.mark.asyncio
async def test_health_requires_user_agent(client: AsyncClient) -> None:
    # Sobrescreve o User-Agent padrão do httpx com string vazia
    response = await client.get("/health", headers={"user-agent": ""})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_graphql_health(client: AsyncClient) -> None:
    response = await client.post(
        "/graphql",
        json={"query": "{ health }"},
        headers={"user-agent": "pytest"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["health"] == "ok"


@pytest.mark.asyncio
async def test_graphql_me_unauthenticated(client: AsyncClient) -> None:
    response = await client.post(
        "/graphql",
        json={"query": "{ me { id email } }"},
        headers={"user-agent": "pytest"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["me"] is None


@pytest.mark.asyncio
async def test_auth_providers_empty(client: AsyncClient) -> None:
    """Sem env vars de OAuth, a lista de providers deve estar vazia."""
    response = await client.get("/auth/providers", headers={"user-agent": "pytest"})
    assert response.status_code == 200
    assert response.json() == []
