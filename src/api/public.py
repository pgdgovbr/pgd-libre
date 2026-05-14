"""Sprint 1.6 — Endpoint público de resultados consolidados (RF-004)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.institucional import listar_resultados_publicos

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/resultados")
async def resultados_publicos(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await listar_resultados_publicos(db)


@router.get("/resultados/{cod_unidade_executora}")
async def resultado_por_unidade(
    cod_unidade_executora: int,
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    rows = await listar_resultados_publicos(db)
    for row in rows:
        if row["cod_unidade_executora"] == cod_unidade_executora:
            return row
    return None
