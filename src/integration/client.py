"""Async HTTP client for API PGD Central."""

from __future__ import annotations

import httpx

_USER_AGENT = "pgd-libre/0.1"


class ApiPgdError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class ApiPgdClient:
    """Thin async wrapper around the API PGD Central REST API.

    Usage:
        async with ApiPgdClient(url, user, password) as client:
            await client.send_participante(...)
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ApiPgdClient:
        self._http = httpx.AsyncClient(headers={"User-Agent": _USER_AGENT})
        await self._authenticate()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http:
            await self._http.aclose()

    async def _authenticate(self) -> None:
        assert self._http is not None
        resp = await self._http.post(
            f"{self._base}/token",
            data={"username": self._username, "password": self._password},
        )
        if resp.status_code != 200:
            raise ApiPgdError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _put(self, path: str, payload: dict) -> dict:
        assert self._http is not None
        resp = await self._http.put(
            f"{self._base}{path}",
            json=payload,
            headers=self._auth_headers(),
        )
        if resp.status_code == 401:
            await self._authenticate()
            resp = await self._http.put(
                f"{self._base}{path}",
                json=payload,
                headers=self._auth_headers(),
            )
        if resp.status_code not in (200, 201):
            raise ApiPgdError(resp.status_code, resp.text)
        return resp.json()

    async def send_participante(
        self,
        cod_unidade_lotacao: int,
        matricula_siape: str,
        payload: dict,
    ) -> dict:
        path = f"/{cod_unidade_lotacao}/participante/{matricula_siape}"
        return await self._put(path, payload)

    async def send_plano_entregas(
        self,
        origem_unidade: str,
        cod_unidade_autorizadora: int,
        id_plano_entregas: str,
        payload: dict,
    ) -> dict:
        path = (
            f"/organizacao/{origem_unidade}/{cod_unidade_autorizadora}"
            f"/plano_entregas/{id_plano_entregas}"
        )
        return await self._put(path, payload)

    async def send_plano_trabalho(
        self,
        origem_unidade: str,
        cod_unidade_autorizadora: int,
        id_plano_trabalho: str,
        payload: dict,
    ) -> dict:
        path = (
            f"/organizacao/{origem_unidade}/{cod_unidade_autorizadora}"
            f"/plano_trabalho/{id_plano_trabalho}"
        )
        return await self._put(path, payload)
