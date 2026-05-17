"""Endpoint REST `POST /api/ai/rewrite-registro`.

Apenas servidores autenticados. Rate-limit 10/h por user. Erros do LLM viram
503 com Retry-After ausente; rate-limit vira 429 com Retry-After.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_optional_user
from ..config import get_settings
from ..database import get_db
from ..models.user import User, UserRole
from ..services.ai_rewrite import (
    TEMPLATES,
    RewriteError,
    TemplateInvalidoError,
    marcar_evento_aplicado,
    reescrever_registro,
    registrar_evento_geracao,
    verificar_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class RewriteRequest(BaseModel):
    registro_id: uuid.UUID | None = None
    texto_atual: str = Field(..., min_length=80)
    template_id: Literal["entrega", "cronologico", "contribuicao", "star"]
    instrucao_adicional: str = ""


class RewriteResponse(BaseModel):
    event_id: uuid.UUID
    rewritten_text: str
    latency_ms: int
    tokens_in: int
    tokens_out: int


def _ip(request: Request) -> str | None:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _require_servidor(
    user: User | None = Depends(get_optional_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if user.role != UserRole.SERVIDOR:
        raise HTTPException(
            status_code=403, detail="Apenas servidores podem usar a reescrita por IA"
        )
    return user


@router.post("/rewrite-registro", response_model=RewriteResponse)
async def rewrite_registro(
    payload: RewriteRequest,
    response: Response,
    request: Request,
    user: User = Depends(_require_servidor),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    # Rate limit
    allowed, retry_after = await verificar_rate_limit(db, user.id)
    if not allowed:
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {settings.AI_REWRITE_RATE_LIMIT_PER_HOUR} reescritas/h atingido",
            headers={"Retry-After": str(retry_after)},
        )

    # Chamada ao LLM (síncrona)
    try:
        rewritten, tokens_in, tokens_out, latency = reescrever_registro(
            texto_atual=payload.texto_atual,
            template_id=payload.template_id,
            instrucao_adicional=payload.instrucao_adicional,
        )
    except TemplateInvalidoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RewriteError as exc:
        logger.warning(f"Bedrock falhou para user {user.id}: {exc}")
        # Registra evento de falha para auditoria (chars_out=0 sinaliza erro)
        try:
            await registrar_evento_geracao(
                db,
                user_id=user.id,
                registro_id=payload.registro_id,
                template_id=payload.template_id,
                instrucao_custom=bool(payload.instrucao_adicional.strip()),
                chars_in=len(payload.texto_atual),
                chars_out=0,
                tokens_in=0,
                tokens_out=0,
                latency_ms=0,
                model=settings.BEDROCK_MODEL_ID,
                ip_address=_ip(request),
                error_message=str(exc)[:1000],
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail="A IA está temporariamente indisponível. Tente novamente em instantes.",
        ) from exc

    # Persiste evento
    ev = await registrar_evento_geracao(
        db,
        user_id=user.id,
        registro_id=payload.registro_id,
        template_id=payload.template_id,
        instrucao_custom=bool(payload.instrucao_adicional.strip()),
        chars_in=len(payload.texto_atual),
        chars_out=len(rewritten),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency,
        model=settings.BEDROCK_MODEL_ID,
        ip_address=_ip(request),
    )

    return RewriteResponse(
        event_id=ev.id,
        rewritten_text=rewritten,
        latency_ms=latency,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


@router.post("/rewrite-registro/{event_id}/applied")
async def rewrite_applied(
    event_id: uuid.UUID,
    user: User = Depends(_require_servidor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ev = await marcar_evento_aplicado(db, event_id=event_id, user_id=user.id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return {"ok": True, "applied": True, "event_id": str(ev.id)}


@router.get("/templates")
async def listar_templates() -> dict:
    """Expõe os templates disponíveis (id, nome, desc) para o frontend."""
    return {
        "templates": [
            {"id": tid, "nome": t["nome"], "desc": t["desc"]} for tid, t in TEMPLATES.items()
        ]
    }
