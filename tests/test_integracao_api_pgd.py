"""Sprint 2.1 — Contract tests against the local api-pgd-central instance.

These tests require the api-pgd docker-compose stack to be running:

    cd /path/to/api-pgd && docker-compose up -d

and the env var API_PGD_URL to be set (e.g. http://localhost:5057).
They are skipped automatically when the env var is absent or empty.
"""

import os

import httpx
import pytest

API_PGD_URL = os.getenv("API_PGD_URL", "").rstrip("/")
API_PGD_USERNAME = os.getenv("API_PGD_USERNAME", "johndoe@oi.com")
API_PGD_PASSWORD = os.getenv("API_PGD_PASSWORD", "secret")

pytestmark = pytest.mark.skipif(
    not API_PGD_URL,
    reason="API_PGD_URL not set — skipping api-pgd integration tests",
)

_HEADERS = {"User-Agent": "pgd-libre-test/0.1"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_token() -> str:
    async with httpx.AsyncClient(headers=_HEADERS) as c:
        r = await c.post(
            f"{API_PGD_URL}/token",
            data={"username": API_PGD_USERNAME, "password": API_PGD_PASSWORD},
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"]


async def _put(token: str, path: str, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(headers=_HEADERS) as c:
        return await c.put(
            f"{API_PGD_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


# ---------------------------------------------------------------------------
# Fixtures used across tests — valid cpf from api-pgd data fixtures
# ---------------------------------------------------------------------------

CPF = "64635210600"
MATRICULA = "1237654"
COD_UA = 1
COD_UNIDADE_LOTACAO = 99
COD_UI = 1
COD_UE = 99

PARTICIPANTE_PAYLOAD = {
    "origem_unidade": "SIAPE",
    "cod_unidade_autorizadora": COD_UA,
    "cod_unidade_lotacao": COD_UNIDADE_LOTACAO,
    "matricula_siape": MATRICULA,
    "cod_unidade_instituidora": COD_UI,
    "cpf": CPF,
    "situacao": 1,
    "modalidade_execucao": 3,
    "data_assinatura_tcr": "2024-06-01",
}

PE_PAYLOAD = {
    "origem_unidade": "SIAPE",
    "cod_unidade_autorizadora": COD_UA,
    "cod_unidade_instituidora": COD_UI,
    "cod_unidade_executora": COD_UE,
    "id_plano_entregas": "PE-INTEG-001",
    "status": 3,
    "data_inicio": "2024-01-01",
    "data_termino": "2024-06-30",
    "avaliacao": None,
    "data_avaliacao": None,
    "entregas": [
        {
            "id_entrega": "E-001",
            "entrega_cancelada": False,
            "nome_entrega": "Entrega de integração",
            "meta_entrega": 10,
            "tipo_meta": "unidade",
            "data_entrega": "2024-06-01",
            "nome_unidade_demandante": "UA Demo",
            "nome_unidade_destinataria": "UI Demo",
        }
    ],
}

PT_PAYLOAD = {
    "origem_unidade": "SIAPE",
    "cod_unidade_autorizadora": COD_UA,
    "id_plano_trabalho": "PT-INTEG-001",
    "status": 3,
    "cod_unidade_executora": COD_UE,
    "cpf_participante": CPF,
    "matricula_siape": MATRICULA,
    "cod_unidade_lotacao_participante": COD_UNIDADE_LOTACAO,
    "data_inicio": "2024-01-01",
    "data_termino": "2024-06-30",
    "carga_horaria_disponivel": 160,
    "contribuicoes": [
        {
            "id_contribuicao": "C-001",
            "tipo_contribuicao": 1,
            "percentual_contribuicao": 100,
            "id_plano_entregas": "PE-INTEG-001",
            "id_entrega": "E-001",
        }
    ],
    "avaliacoes_registros_execucao": [],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_auth_retorna_token():
    token = await _get_token()
    assert token and len(token) > 10


async def test_send_participante():
    token = await _get_token()
    r = await _put(
        token,
        f"/{COD_UNIDADE_LOTACAO}/participante/{MATRICULA}",
        PARTICIPANTE_PAYLOAD,
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["matricula_siape"] == MATRICULA
    assert data["cpf"] == CPF


async def test_send_plano_entregas():
    token = await _get_token()
    r = await _put(
        token,
        f"/organizacao/SIAPE/{COD_UA}/plano_entregas/PE-INTEG-001",
        PE_PAYLOAD,
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["id_plano_entregas"] == "PE-INTEG-001"
    assert len(data["entregas"]) == 1


async def test_send_plano_trabalho():
    # participante and PE must exist first
    token = await _get_token()
    await _put(token, f"/{COD_UNIDADE_LOTACAO}/participante/{MATRICULA}", PARTICIPANTE_PAYLOAD)
    await _put(token, f"/organizacao/SIAPE/{COD_UA}/plano_entregas/PE-INTEG-001", PE_PAYLOAD)

    r = await _put(
        token,
        f"/organizacao/SIAPE/{COD_UA}/plano_trabalho/PT-INTEG-001",
        PT_PAYLOAD,
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["id_plano_trabalho"] == "PT-INTEG-001"
    assert len(data["contribuicoes"]) == 1


async def test_send_plano_entregas_avaliado():
    """status=5 requires avaliacao and data_avaliacao."""
    token = await _get_token()
    payload = {
        **PE_PAYLOAD,
        "id_plano_entregas": "PE-INTEG-AVAL",
        "status": 5,
        "avaliacao": 4,
        "data_avaliacao": "2024-07-05",
    }
    r = await _put(token, f"/organizacao/SIAPE/{COD_UA}/plano_entregas/PE-INTEG-AVAL", payload)
    assert r.status_code in (200, 201), r.text
    assert r.json()["avaliacao"] == 4


async def test_client_helper():
    """ApiPgdClient async context manager works end-to-end."""
    from src.integration.client import ApiPgdClient

    async with ApiPgdClient(API_PGD_URL, API_PGD_USERNAME, API_PGD_PASSWORD) as client:
        result = await client.send_participante(
            cod_unidade_lotacao=COD_UNIDADE_LOTACAO,
            matricula_siape=MATRICULA,
            payload=PARTICIPANTE_PAYLOAD,
        )
    assert result["matricula_siape"] == MATRICULA


async def test_mapper_plano_entregas(db):
    """mapper.plano_entregas_to_payload produces valid api-pgd payload."""
    import uuid
    from datetime import date

    from src.integration.mapper import plano_entregas_to_payload
    from src.models.institucional import OrigemUnidade
    from src.models.plano import STATUS_PE_EM_EXECUCAO, Entrega, PlanoEntregas, TipoMeta

    pe = PlanoEntregas(
        id=uuid.uuid4(),
        id_plano_entregas="PE-MAP-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_instituidora=1,
        cod_unidade_executora=99,
        unidade_execucao_id=uuid.uuid4(),
        status=STATUS_PE_EM_EXECUCAO,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
    )
    pe.entregas = [
        Entrega(
            id=uuid.uuid4(),
            id_entrega="E-MAP-001",
            plano_entregas_id=pe.id,
            nome_entrega="Mapper Entrega",
            meta_entrega=5,
            tipo_meta=TipoMeta.UNIDADE,
            data_entrega=date(2024, 6, 1),
            nome_unidade_demandante="UA",
            nome_unidade_destinataria="UI",
            entrega_cancelada=False,
        )
    ]

    payload = plano_entregas_to_payload(pe)
    assert payload["id_plano_entregas"] == "PE-MAP-001"
    assert payload["origem_unidade"] == "SIAPE"
    assert payload["status"] == STATUS_PE_EM_EXECUCAO
    assert len(payload["entregas"]) == 1
    assert payload["entregas"][0]["tipo_meta"] == "unidade"

    # Must be accepted by the real api-pgd
    token = await _get_token()
    r = await _put(
        token,
        "/organizacao/SIAPE/1/plano_entregas/PE-MAP-001",
        payload,
    )
    assert r.status_code in (200, 201), r.text


async def test_mapper_participante():
    """mapper.participante_to_payload produces valid api-pgd payload."""
    import uuid
    from datetime import date

    from src.integration.mapper import participante_to_payload
    from src.models.institucional import OrigemUnidade
    from src.models.participante import Participante, TipoVinculo

    p = Participante(
        id=uuid.uuid4(),
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_lotacao=99,
        matricula_siape=MATRICULA,
        cod_unidade_instituidora=1,
        cpf=CPF,
        nome="João Mapper",
        email="joao@example.gov.br",
        situacao=1,
        modalidade_execucao=3,
        data_assinatura_tcr=date(2024, 6, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=uuid.uuid4(),
    )

    payload = participante_to_payload(p)
    assert payload["cpf"] == CPF
    assert payload["matricula_siape"] == MATRICULA

    token = await _get_token()
    r = await _put(
        token,
        f"/{COD_UNIDADE_LOTACAO}/participante/{MATRICULA}",
        payload,
    )
    assert r.status_code in (200, 201), r.text
