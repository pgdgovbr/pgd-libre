"""Endpoint interno para disparar a sincronização com a API PGD Central."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..integration.client import ApiPgdClient
from ..integration.sync import sincronizar_tudo

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sync")
async def trigger_sync(
    x_sync_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dispara sincronização dos dados locais para a API PGD Central.

    Requer cabeçalho X-Sync-Secret igual a SYNC_SECRET (env var).
    Tipicamente chamado pelo Cloud Scheduler.
    """
    settings = get_settings()

    if x_sync_secret != settings.SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not settings.API_PGD_URL:
        return {"status": "skipped", "motivo": "API_PGD_URL não configurada"}

    async with ApiPgdClient(
        settings.API_PGD_URL,
        settings.API_PGD_USERNAME,
        settings.API_PGD_PASSWORD,
    ) as client:
        result = await sincronizar_tudo(db, client)

    return {"status": "ok", **result}
