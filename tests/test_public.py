"""Sprint 1.6 — Endpoint público de resultados consolidados (RF-004)."""
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.user import UserRole
from src.services.institucional import (
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)

from .conftest import persist_user


async def _make_ue(db, admin):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Pub",
        sigla="UPB",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="A",
        data_publicacao=date(2024, 1, 1),
        referencia="R",
        user=admin,
    )
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=100,
        nome="UI Pub",
        sigla="UIP",
        ato_instituicao_ref="R2",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    from src.models.institucional import UnidadeExecucao
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=200,
        nome="UE Pub",
        sigla="UEP",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ue


async def test_resultados_publicos_vazio(client: AsyncClient, db: AsyncSession):
    resp = await client.get("/public/resultados")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_resultados_publicos_lista_unidades(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)

    resp = await client.get("/public/resultados")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    row = next(r for r in data if r["cod_unidade_executora"] == ue.cod_unidade_executora)
    assert row["nome"] == "UE Pub"
    assert row["total_planos_avaliados"] == 0
    assert row["media_avaliacao"] is None


async def test_resultado_por_unidade(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)

    resp = await client.get(f"/public/resultados/{ue.cod_unidade_executora}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cod_unidade_executora"] == ue.cod_unidade_executora


async def test_resultado_por_unidade_inexistente(client: AsyncClient, db: AsyncSession):
    resp = await client.get("/public/resultados/99999")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_resultados_refletem_planos_avaliados(client: AsyncClient, db: AsyncSession):
    """Total and average reflect evaluated PEs."""
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)

    from src.services.plano_entregas import (
        avaliar_pe,
        concluir_pe,
        criar_plano_entregas,
        iniciar_execucao_pe,
    )
    from src.models.plano import STATUS_PE_AVALIADO

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-PUB-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=1,
        cod_unidade_instituidora=100,
        cod_unidade_executora=ue.cod_unidade_executora,
        unidade_execucao_id=ue.id,
        data_inicio=date(2024, 1, 1),
        data_termino=date(2024, 6, 30),
        user=admin,
    )
    pe = await iniciar_execucao_pe(db, plano_id=pe.id, user=admin)
    pe = await concluir_pe(db, plano_id=pe.id, user=admin)
    await avaliar_pe(db, plano_id=pe.id, avaliacao=4, data_avaliacao=date(2024, 7, 5), user=admin)

    resp = await client.get(f"/public/resultados/{ue.cod_unidade_executora}")
    data = resp.json()
    assert data["total_planos_avaliados"] == 1
    assert data["media_avaliacao"] == 4.0
