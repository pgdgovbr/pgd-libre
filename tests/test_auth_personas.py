"""Testes do endpoint GET /auth/personas-demo e do gate de dev-login em demo/prod."""

from httpx import AsyncClient


async def test_personas_demo_retorna_10_itens(client: AsyncClient):
    resp = await client.get("/auth/personas-demo")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10


async def test_personas_demo_estrutura(client: AsyncClient):
    resp = await client.get("/auth/personas-demo")
    data = resp.json()
    p = data[0]
    for key in ("email", "name", "role", "role_label", "ctx", "grupo"):
        assert key in p, f"campo {key} faltando: {p}"


async def test_personas_demo_inclui_recomendados(client: AsyncClient):
    resp = await client.get("/auth/personas-demo")
    data = resp.json()
    recomendados = [p for p in data if p["grupo"] == "recomendados"]
    assert len(recomendados) == 4
    emails = {p["email"] for p in recomendados}
    assert "servidor7@pgd-demo.gov.br" in emails  # Marta
    assert "servidor1@pgd-demo.gov.br" in emails  # Nitai
    assert "chefe1@pgd-demo.gov.br" in emails  # Carlos
    assert "gestor@pgd-demo.gov.br" in emails  # Maria Fernanda


async def test_personas_demo_404_em_production(client: AsyncClient, monkeypatch):
    """Em production, o endpoint não existe (404) — não vaza informação."""
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = await client.get("/auth/personas-demo")
    assert resp.status_code == 404
    get_settings.cache_clear()


async def test_dev_login_liberado_em_demo(client: AsyncClient, monkeypatch):
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "demo")
    resp = await client.post(
        "/auth/dev-login",
        params={
            "email": "marta@pgd-demo.gov.br",
            "name": "Marta Silva",
            "role": "servidor",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "token" in data
    get_settings.cache_clear()


async def test_dev_login_bloqueado_em_production(client: AsyncClient, monkeypatch):
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = await client.post(
        "/auth/dev-login",
        params={
            "email": "marta@pgd-demo.gov.br",
            "name": "Marta Silva",
            "role": "servidor",
        },
    )
    assert resp.status_code == 403
    get_settings.cache_clear()


async def test_dev_login_secure_cookie_em_demo(client: AsyncClient, monkeypatch):
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "demo")
    resp = await client.post(
        "/auth/dev-login",
        params={
            "email": "demo@pgd-demo.gov.br",
            "name": "Demo",
            "role": "servidor",
        },
    )
    assert resp.status_code == 200
    cookie_header = resp.headers.get("set-cookie", "")
    assert "Secure" in cookie_header, f"esperava cookie Secure em demo: {cookie_header}"
    get_settings.cache_clear()


async def test_dev_login_sem_secure_em_development(client: AsyncClient, monkeypatch):
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "development")
    resp = await client.post(
        "/auth/dev-login",
        params={
            "email": "dev@pgd-demo.gov.br",
            "name": "Dev",
            "role": "servidor",
        },
    )
    assert resp.status_code == 200
    cookie_header = resp.headers.get("set-cookie", "")
    assert "Secure" not in cookie_header, f"não esperava Secure em development: {cookie_header}"
    get_settings.cache_clear()
